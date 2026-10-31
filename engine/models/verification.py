"""Verification result models.

Two layers:
  * ``VerifierResult``     — one verifier's judgment of one postcondition.
  * ``ReconciledVerdict``  — the combined judgment across all verifiers for one
                             postcondition, produced by the StateReconciler.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from engine.models.enums import VerdictStatus, VerifierStatus, VerifierType


class VerifierResult(BaseModel):
    verifier_type: VerifierType
    postcondition_ref: str
    status: VerifierStatus
    expected: object = None
    observed: object = None
    confidence: float = Field(..., ge=0.0, le=1.0)
    latency_ms: int = Field(0, ge=0)
    evidence_id: str | None = None
    note: str | None = None


class ReconciledVerdict(BaseModel):
    postcondition_ref: str
    verdict: VerdictStatus
    confidence: float = Field(..., ge=0.0, le=1.0)
    conflict: bool = False
    contributing: list[VerifierResult] = Field(default_factory=list)
    reason: str = ""

    @property
    def is_satisfied(self) -> bool:
        return self.verdict is VerdictStatus.SATISFIED
