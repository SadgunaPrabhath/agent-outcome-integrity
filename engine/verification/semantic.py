"""SemanticVerifier — last-resort, prose-interpreted verification.

This is the lowest tier of the hierarchy (confidence ceiling 0.4). It exists for
postconditions that *cannot* be reduced to a structured predicate — "the summary
mentions the refund was processed" — where the only observable is free text.

Two disciplines keep it honest:

  * **It never outranks a deterministic source.** SEMANTIC is non-authoritative
    and non-deterministic, so the reconciler only lets it decide when nothing
    better is available, and otherwise records it as presentational dissent.

  * **The judge is pluggable and the default is not an LLM.** The engine runs
    keyless by default with :class:`HeuristicSemanticJudge`, a deterministic
    lexical check — clearly labelled as a heuristic, never presented as model
    reasoning. A real LLM judge is a Phase-9 backend that implements the same
    :class:`SemanticJudge` protocol. Whatever the judge, confidence is capped at
    the SEMANTIC tier so a confident judge can never masquerade as ground truth.
"""

from __future__ import annotations

import inspect
import re
import time
from collections.abc import Awaitable
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from engine.execution.context import RunContext, StateSource
from engine.models import (
    Evidence,
    Observation,
    Postcondition,
    PostconditionType,
    VerifierResult,
    VerifierStatus,
    VerifierType,
)
from engine.verification.base import Verifier, confidence_for

_WORD = re.compile(r"[a-z0-9]+")
_NEGATIONS = ("not", "no", "never", "without", "failed", "unable", "cannot", "couldn't", "n't")


@dataclass
class Judgment:
    """A judge's verdict on whether observed text satisfies an expectation."""

    status: VerifierStatus
    confidence: float  # judge's self-reported confidence in [0, 1]
    rationale: str
    judge: str  # identifier of the backend that produced this


@runtime_checkable
class SemanticJudge(Protocol):
    """Backend that decides whether ``observed`` satisfies ``expected`` (prose).

    ``judge`` may be synchronous (the heuristic default) or return an awaitable
    (an LLM backend that makes a network call). The verifier handles both.
    """

    name: str

    def judge(
        self, expected: str, observed: str, context: dict[str, Any]
    ) -> Judgment | Awaitable[Judgment]: ...


class HeuristicSemanticJudge:
    """Deterministic, keyless lexical judge — the honest default.

    It is intentionally simple and says so: PASS when the expectation's salient
    tokens are all present (and not negated) in the observed text, FAIL when they
    are present but negated, INCONCLUSIVE when the text does not address them. It
    is a stand-in for a real LLM judge, never a substitute for a backend read.
    """

    name = "heuristic-lexical"

    def __init__(self, min_overlap: float = 1.0) -> None:
        self.min_overlap = min_overlap

    def judge(self, expected: str, observed: str, context: dict[str, Any]) -> Judgment:
        want = _tokens(expected)
        got = _tokens(observed)
        if not want:
            return Judgment(VerifierStatus.INCONCLUSIVE, 0.0, "empty expectation", self.name)
        if not got:
            return Judgment(
                VerifierStatus.INCONCLUSIVE, 0.0, "no observable text", self.name
            )

        overlap = len(want & got) / len(want)
        if overlap < self.min_overlap:
            return Judgment(
                VerifierStatus.INCONCLUSIVE,
                round(0.3 + 0.3 * overlap, 3),
                f"only {overlap:.0%} of expected terms appear; text does not address the claim",
                self.name,
            )

        negated = _negation_near(observed, want)
        if negated:
            return Judgment(
                VerifierStatus.FAIL,
                0.6,
                f"expected terms present but negated near: '{negated}'",
                self.name,
            )
        return Judgment(
            VerifierStatus.PASS,
            round(0.5 + 0.4 * overlap, 3),
            "all salient expected terms present without negation",
            self.name,
        )


class SemanticVerifier(Verifier):
    """Judges a ``SEMANTIC`` postcondition using a pluggable judge."""

    verifier_type = VerifierType.SEMANTIC

    def __init__(self, source: StateSource, judge: SemanticJudge | None = None) -> None:
        self.source = source
        self.judge: SemanticJudge = judge or HeuristicSemanticJudge()

    def can_verify(self, pc: Postcondition) -> bool:
        return pc.type is PostconditionType.SEMANTIC

    async def verify(
        self, pc: Postcondition, ctx: RunContext
    ) -> tuple[VerifierResult, Evidence]:
        started = time.perf_counter()
        obs = await self.source.read(pc, ctx.task.target)
        status, observed, judgment = await self._evaluate(pc, obs)
        latency_ms = int((time.perf_counter() - started) * 1000)
        # Tier caps the ceiling: a confident judge can never exceed 0.4.
        tier_ceiling = confidence_for(self.verifier_type, status)
        confidence = (
            0.0
            if status is VerifierStatus.INCONCLUSIVE
            else min(tier_ceiling, judgment.confidence)
        )

        expected = pc.expected if isinstance(pc.expected, str) else str(pc.expected)
        evidence = Evidence(
            verifier_type=self.verifier_type,
            source=obs.source,
            expected_state=expected,
            observed_state=observed,
            comparison={
                "postcondition": pc.ref,
                "type": pc.type.value,
                "status": status.value,
                "observation_error": obs.error,
                "judge": judgment.judge,
                "judge_confidence": judgment.confidence,
                "rationale": judgment.rationale,
            },
            confidence=confidence,
            redacted=obs.redacted,
        )
        result = VerifierResult(
            verifier_type=self.verifier_type,
            postcondition_ref=pc.ref,
            status=status,
            expected=expected,
            observed=observed,
            confidence=confidence,
            latency_ms=latency_ms,
            evidence_id=evidence.id,
            note=obs.error or judgment.rationale,
        )
        return result, evidence

    async def _evaluate(
        self, pc: Postcondition, obs: Observation
    ) -> tuple[VerifierStatus, Any, Judgment]:
        if not obs.ok:
            return (
                VerifierStatus.INCONCLUSIVE,
                None,
                Judgment(VerifierStatus.INCONCLUSIVE, 0.0, "observation failed", self.judge.name),
            )
        observed_text = _observed_text(obs.state)
        expected = pc.expected if isinstance(pc.expected, str) else str(pc.expected)
        # A judge may be sync (the heuristic default) or async (an LLM backend).
        outcome = self.judge.judge(expected, observed_text, dict(obs.state))
        judgment = await outcome if inspect.isawaitable(outcome) else outcome
        return judgment.status, observed_text, judgment


def _tokens(text: str) -> set[str]:
    return set(_WORD.findall(text.lower()))


def _is_negation(word: str) -> bool:
    return word in _NEGATIONS or word.endswith("n't")


def _negation_near(text: str, want: set[str], window: int = 3) -> str | None:
    """Return the offending phrase if a negation word sits within ``window``
    tokens before any expected term (a crude but explainable contradiction check)."""
    words = _WORD.findall(text.lower())
    for i, w in enumerate(words):
        if w in want:
            lo = max(0, i - window)
            if any(_is_negation(s) for s in words[lo:i]):
                return " ".join(words[lo : i + 1])
    return None


def _observed_text(state: dict[str, Any]) -> str:
    """Pull the free text to judge from an observation, most-specific first."""
    for key in ("text", "summary", "message", "content", "body"):
        value = state.get(key)
        if isinstance(value, str) and value.strip():
            return value
    # Fall back to a flattened view of the whole state so the judge has *something*.
    return " ".join(str(v) for v in state.values() if isinstance(v, (str, int, float)))
