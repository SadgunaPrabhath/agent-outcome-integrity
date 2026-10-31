"""VerificationEngine — run the right verifiers per postcondition and reconcile.

Responsibilities:
  * select applicable verifiers for each postcondition (preference-ordered,
    intersected with the sources actually registered on the RunContext);
  * run them (concurrently) to get per-source results + sealed evidence;
  * reconcile them into a per-postcondition verdict;
  * handle temporal postconditions by sampling over time.

It deliberately does *not* decide the task-level outcome — that is the
OutcomeClassifier's job. Separation keeps each piece unit-testable.
"""

from __future__ import annotations

import asyncio
import time

from pydantic import BaseModel, Field

from engine.execution.context import RunContext, StateSource
from engine.models import (
    Evidence,
    Postcondition,
    ReconciledVerdict,
    TemporalSpec,
    VerdictStatus,
    VerifierResult,
    VerifierType,
)
from engine.reconciliation.reconciler import StateReconciler
from engine.verification.base import SourceVerifier, Verifier
from engine.verification.semantic import SemanticJudge, SemanticVerifier
from engine.verification.visual import VisualVerifier


class VerificationReport(BaseModel):
    verdicts: list[ReconciledVerdict] = Field(default_factory=list)
    results: list[VerifierResult] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    total_latency_ms: int = 0


class VerificationEngine:
    def __init__(
        self,
        reconciler: StateReconciler | None = None,
        *,
        judge: SemanticJudge | None = None,
    ) -> None:
        self.reconciler = reconciler or StateReconciler()
        # Injected into the SEMANTIC verifier; ``None`` means keyless heuristic.
        self.judge = judge

    def _build_verifier(self, vtype: VerifierType, source: StateSource) -> Verifier:
        """Pick the verifier appropriate to the source kind.

        Deterministic sources share one ``SourceVerifier`` (evaluation is a
        match); the presentational/last-resort tiers need bespoke evaluation.
        """
        if vtype is VerifierType.VISUAL:
            return VisualVerifier(source)
        if vtype is VerifierType.SEMANTIC:
            return SemanticVerifier(source, self.judge)
        return SourceVerifier(source)

    def _select_methods(self, pc: Postcondition, ctx: RunContext) -> list[VerifierType]:
        available = set(ctx.sources.keys())
        preferred = ctx.task.resolved_methods(pc)
        if preferred:
            chosen = [m for m in preferred if m in available]
        else:
            chosen = list(available)
        # Always run every *deterministic* source we have, even beyond the
        # preference list — cross-source agreement is itself evidence, and
        # disagreement is exactly the signal we must not miss.
        for m in available:
            if m.is_deterministic and m not in chosen:
                chosen.append(m)
        return sorted(set(chosen), key=lambda v: v.priority)

    async def _sample(
        self, pc: Postcondition, ctx: RunContext
    ) -> tuple[ReconciledVerdict, list[VerifierResult], list[Evidence]]:
        methods = self._select_methods(pc, ctx)
        verifiers = [self._build_verifier(m, ctx.sources[m]) for m in methods]
        applicable = [v for v in verifiers if v.can_verify(pc)]

        pairs = await asyncio.gather(*(v.verify(pc, ctx) for v in applicable))
        results = [r for r, _ in pairs]
        evidence = [e for _, e in pairs]
        verdict = self.reconciler.reconcile(pc.ref, results)
        return verdict, results, evidence

    async def verify_postcondition(
        self, pc: Postcondition, ctx: RunContext
    ) -> tuple[ReconciledVerdict, list[VerifierResult], list[Evidence]]:
        if pc.temporal is None:
            return await self._sample(pc, ctx)
        if pc.temporal.within_s is not None:
            return await self._verify_within(pc, ctx, pc.temporal)
        return await self._verify_hold(pc, ctx, pc.temporal)

    async def _verify_within(
        self, pc: Postcondition, ctx: RunContext, temporal: TemporalSpec
    ) -> tuple[ReconciledVerdict, list[VerifierResult], list[Evidence]]:
        """Poll until the postcondition becomes SATISFIED or the window elapses."""
        deadline = time.monotonic() + (temporal.within_s or 0)
        last = await self._sample(pc, ctx)
        while last[0].verdict is not VerdictStatus.SATISFIED and time.monotonic() < deadline:
            await asyncio.sleep(temporal.poll_interval_s)
            last = await self._sample(pc, ctx)
        return last

    async def _verify_hold(
        self, pc: Postcondition, ctx: RunContext, temporal: TemporalSpec
    ) -> tuple[ReconciledVerdict, list[VerifierResult], list[Evidence]]:
        """Require the postcondition to stay SATISFIED across the whole window."""
        deadline = time.monotonic() + (temporal.must_hold_s or 0)
        results: list[VerifierResult] = []
        evidence: list[Evidence] = []
        samples: list[ReconciledVerdict] = []
        while True:
            verdict, res, ev = await self._sample(pc, ctx)
            samples.append(verdict)
            results.extend(res)
            evidence.extend(ev)
            if verdict.verdict is not VerdictStatus.SATISFIED:
                verdict.reason = f"did not hold: {verdict.reason}"
                return verdict, results, evidence
            if time.monotonic() >= deadline:
                break
            await asyncio.sleep(temporal.poll_interval_s)
        held = ReconciledVerdict(
            postcondition_ref=pc.ref,
            verdict=VerdictStatus.SATISFIED,
            confidence=min(s.confidence for s in samples),
            contributing=results,
            reason=f"held for {temporal.must_hold_s}s across {len(samples)} samples",
        )
        return held, results, evidence

    async def verify(self, ctx: RunContext) -> VerificationReport:
        started = time.perf_counter()
        report = VerificationReport()
        for pc in ctx.task.expected_postconditions:
            verdict, results, evidence = await self.verify_postcondition(pc, ctx)
            report.verdicts.append(verdict)
            report.results.extend(results)
            report.evidence.extend(evidence)
            if ctx.trace is not None:
                ctx.trace.add(
                    "verify",
                    pc.ref,
                    verdict=verdict.verdict.value,
                    confidence=verdict.confidence,
                    conflict=verdict.conflict,
                )
        report.total_latency_ms = int((time.perf_counter() - started) * 1000)
        return report
