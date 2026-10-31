"""VisualVerifier — perceptual comparison of a rendered screenshot to a reference.

This is a *presentational* verifier (confidence tier 0.5): it observes what was
drawn on screen, not what persisted. It therefore never decides a verdict when an
authoritative source is available — the reconciler treats it as presentational
dissent, which is exactly the false-completion signal we want ("the success
screen rendered, but the database never changed").

A ``VISUAL_MATCH`` postcondition carries a reference fingerprint in ``expected``
(a hex aHash string, or a ``{"ahash": ...}`` dict). The verifier reads a
screenshot observation from its source, extracts or computes the aHash, and
PASSes when the Hamming distance is within budget. The budget defaults to ~10%
of the hash bits and can be overridden per-postcondition via
``matcher.tolerance`` (interpreted as an allowed number of differing bits).
"""

from __future__ import annotations

import time
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
from engine.verification.base import Verifier, confidence_for
from engine.verification.perceptual import average_hash, hamming, similarity


class VisualVerifier(Verifier):
    """Judges a ``VISUAL_MATCH`` postcondition against a screenshot source."""

    verifier_type = VerifierType.VISUAL

    def __init__(self, source: StateSource, *, default_tolerance_ratio: float = 0.1) -> None:
        self.source = source
        self.default_tolerance_ratio = default_tolerance_ratio

    def can_verify(self, pc: Postcondition) -> bool:
        return pc.type is PostconditionType.VISUAL_MATCH

    async def verify(
        self, pc: Postcondition, ctx: RunContext
    ) -> tuple[VerifierResult, Evidence]:
        started = time.perf_counter()
        obs = await self.source.read(pc, ctx.task.target)
        status, observed, detail = self._evaluate(pc, obs)
        latency_ms = int((time.perf_counter() - started) * 1000)
        confidence = confidence_for(self.verifier_type, status)

        expected_hash = _reference_hash(pc.expected)
        evidence = Evidence(
            verifier_type=self.verifier_type,
            source=obs.source,
            expected_state=expected_hash,
            observed_state=observed,
            comparison={
                "postcondition": pc.ref,
                "type": pc.type.value,
                "status": status.value,
                "observation_error": obs.error,
                **detail,
            },
            confidence=confidence,
            screenshot_path=obs.state.get("screenshot_path"),
            redacted=obs.redacted,
        )
        result = VerifierResult(
            verifier_type=self.verifier_type,
            postcondition_ref=pc.ref,
            status=status,
            expected=expected_hash,
            observed=observed,
            confidence=confidence,
            latency_ms=latency_ms,
            evidence_id=evidence.id,
            note=obs.error or detail.get("note"),
        )
        return result, evidence

    def _evaluate(
        self, pc: Postcondition, obs: Observation
    ) -> tuple[VerifierStatus, Any, dict[str, Any]]:
        if not obs.ok:
            return VerifierStatus.INCONCLUSIVE, None, {"note": "screenshot unavailable"}

        reference = _reference_hash(pc.expected)
        if not reference:
            return (
                VerifierStatus.INCONCLUSIVE,
                None,
                {"note": "VISUAL_MATCH has no reference hash in 'expected'"},
            )

        try:
            observed = _observed_hash(obs.state)
        except (ValueError, TypeError) as exc:
            return VerifierStatus.INCONCLUSIVE, None, {"note": f"unreadable screenshot: {exc}"}
        if observed is None:
            return (
                VerifierStatus.INCONCLUSIVE,
                None,
                {"note": "no aHash or pixel buffer in observation"},
            )

        try:
            distance = hamming(observed, reference)
        except ValueError as exc:
            return VerifierStatus.INCONCLUSIVE, observed, {"note": str(exc)}

        bits = len(reference) * 4
        budget = self._budget(pc, bits)
        status = VerifierStatus.PASS if distance <= budget else VerifierStatus.FAIL
        detail = {
            "hamming": distance,
            "budget": budget,
            "similarity": round(similarity(observed, reference), 4),
            "hash_bits": bits,
        }
        return status, observed, detail

    def _budget(self, pc: Postcondition, bits: int) -> int:
        if pc.matcher.tolerance and pc.matcher.tolerance > 0:
            return int(pc.matcher.tolerance)
        return max(1, round(self.default_tolerance_ratio * bits))


def _reference_hash(expected: Any) -> str | None:
    if isinstance(expected, str):
        return expected
    if isinstance(expected, dict):
        value = expected.get("ahash") or expected.get("hash")
        return value if isinstance(value, str) else None
    return None


def _observed_hash(state: dict[str, Any]) -> str | None:
    """Prefer a precomputed hash; otherwise fingerprint a grayscale buffer."""
    direct = state.get("ahash") or state.get("hash")
    if isinstance(direct, str):
        return direct
    gray = state.get("gray")
    width = state.get("width")
    height = state.get("height")
    if gray is not None and width and height:
        return average_hash(gray, int(width), int(height))
    return None
