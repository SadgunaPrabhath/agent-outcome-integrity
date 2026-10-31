"""Verifier interface, postcondition evaluation, and confidence model.

The evaluation logic (does this observation satisfy this postcondition?) is
shared across all deterministic verifiers; what differs between API/DB/DOM is
only *where the observation comes from*, which is the ``StateSource``. So the
MVP has a single concrete ``SourceVerifier`` parameterized by a source, rather
than three near-identical verifier classes. Semantic/visual verifiers (Phase 9)
will subclass ``Verifier`` directly because their evaluation is not a match.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any

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

# Base confidence per source when a deterministic judgment is reached. These
# describe *evidence quality*, not probability of correctness (Section 15).
_BASE_CONFIDENCE: dict[VerifierType, float] = {
    VerifierType.DATABASE: 1.0,
    VerifierType.API: 1.0,
    VerifierType.NETWORK: 0.9,
    VerifierType.DOM: 0.7,
    VerifierType.VISUAL: 0.5,
    VerifierType.SEMANTIC: 0.4,
}


def confidence_for(verifier_type: VerifierType, status: VerifierStatus) -> float:
    """Confidence a single verifier assigns to its own result."""
    base = _BASE_CONFIDENCE.get(verifier_type, 0.5)
    if status is VerifierStatus.INCONCLUSIVE:
        return 0.0
    return base


def evaluate_postcondition(
    pc: Postcondition, obs: Observation
) -> tuple[VerifierStatus, Any]:
    """Judge whether ``obs`` satisfies ``pc``. Returns (status, observed_value).

    Deterministic for the concrete postcondition types. RELATION/SEMANTIC are
    INCONCLUSIVE here — they require a dedicated verifier, not a plain match.
    """
    if not obs.ok:
        return VerifierStatus.INCONCLUSIVE, None

    state = obs.state
    t = pc.type

    if t in (PostconditionType.FIELD_EQUALS, PostconditionType.STATE_TRANSITION):
        observed = state.get(pc.field) if pc.field else None
        if pc.field not in state:
            return VerifierStatus.INCONCLUSIVE, observed
        ok = pc.matcher.matches(pc.expected, observed)
        return (VerifierStatus.PASS if ok else VerifierStatus.FAIL), observed

    if t is PostconditionType.FIELD_MATCHES:
        observed = state.get(pc.field) if pc.field else None
        if pc.field not in state:
            return VerifierStatus.INCONCLUSIVE, observed
        ok = pc.matcher.matches(pc.expected, observed)
        return (VerifierStatus.PASS if ok else VerifierStatus.FAIL), observed

    if t is PostconditionType.EXISTS:
        exists = bool(state.get("exists", bool(state)))
        return (VerifierStatus.PASS if exists else VerifierStatus.FAIL), exists

    if t is PostconditionType.NOT_EXISTS:
        exists = bool(state.get("exists", bool(state)))
        return (VerifierStatus.PASS if not exists else VerifierStatus.FAIL), exists

    if t is PostconditionType.COUNT_EQUALS:
        if "count" not in state:
            return VerifierStatus.INCONCLUSIVE, None
        observed = state.get("count")
        return (
            VerifierStatus.PASS if observed == pc.expected else VerifierStatus.FAIL
        ), observed

    # RELATION / SEMANTIC: not decidable by a plain source read.
    return VerifierStatus.INCONCLUSIVE, None


class Verifier(ABC):
    """Judges one postcondition, producing a result plus sealed evidence."""

    verifier_type: VerifierType

    @abstractmethod
    def can_verify(self, pc: Postcondition) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def verify(
        self, pc: Postcondition, ctx: RunContext
    ) -> tuple[VerifierResult, Evidence]:
        raise NotImplementedError


class SourceVerifier(Verifier):
    """Deterministic verifier backed by a ``StateSource`` (API/DB/DOM/Network)."""

    def __init__(self, source: StateSource) -> None:
        self.source = source
        self.verifier_type = source.verifier_type

    def can_verify(self, pc: Postcondition) -> bool:
        return pc.type not in (
            PostconditionType.SEMANTIC,
            PostconditionType.RELATION,
            PostconditionType.VISUAL_MATCH,
        )

    async def verify(
        self, pc: Postcondition, ctx: RunContext
    ) -> tuple[VerifierResult, Evidence]:
        started = time.perf_counter()
        obs = await self.source.read(pc, ctx.task.target)
        status, observed = evaluate_postcondition(pc, obs)
        latency_ms = int((time.perf_counter() - started) * 1000)
        confidence = confidence_for(self.verifier_type, status)

        evidence = Evidence(
            verifier_type=self.verifier_type,
            source=obs.source,
            expected_state=pc.expected,
            observed_state=observed,
            comparison={
                "postcondition": pc.ref,
                "type": pc.type.value,
                "match_mode": pc.matcher.mode.value,
                "status": status.value,
                "observation_error": obs.error,
            },
            confidence=confidence,
            redacted=obs.redacted,
        )
        result = VerifierResult(
            verifier_type=self.verifier_type,
            postcondition_ref=pc.ref,
            status=status,
            expected=pc.expected,
            observed=observed,
            confidence=confidence,
            latency_ms=latency_ms,
            evidence_id=evidence.id,
            note=obs.error,
        )
        return result, evidence
