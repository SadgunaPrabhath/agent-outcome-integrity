"""Recovery models — plans and history for the recovery control loop."""

from __future__ import annotations

from pydantic import BaseModel, Field

from engine.models.enums import RecoveryStrategy


class RecoveryPlan(BaseModel):
    strategy: RecoveryStrategy
    reason: str
    idempotency_safe: bool
    target_step: int | None = None


class NoRecovery(BaseModel):
    """Explicit "do not attempt recovery" decision, with a reason.

    A separate type (not ``None``) so the orchestrator and audit trail record
    *why* recovery was declined — critical for the non-idempotent safety story.
    """

    reason: str
    escalate: bool = False


class RecoveryAttempt(BaseModel):
    attempt_no: int
    strategy: RecoveryStrategy
    reason: str
    idempotency_safe: bool
    executed: bool
    outcome_after: str | None = None  # Outcome value after re-verification


class RecoveryHistory(BaseModel):
    attempts: list[RecoveryAttempt] = Field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.attempts)
