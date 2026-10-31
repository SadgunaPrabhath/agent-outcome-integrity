"""RunResult — the complete, auditable record of one orchestrated run."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field, computed_field

from engine.models import (
    AgentClaim,
    Evidence,
    ExecutionTrace,
    RecoveryHistory,
    RunState,
    TaskOutcome,
)
from engine.verification.engine import VerificationReport


def _now() -> datetime:
    return datetime.now(UTC)


class StateTransition(BaseModel):
    from_state: RunState
    to_state: RunState
    at: datetime = Field(default_factory=_now)
    note: str = ""


class VerificationRound(BaseModel):
    round_no: int
    report: VerificationReport
    outcome: TaskOutcome


class RunResult(BaseModel):
    run_id: str
    task_id: str
    adapter_name: str

    agent_claim: AgentClaim
    initial_outcome: TaskOutcome
    final_outcome: TaskOutcome

    rounds: list[VerificationRound] = Field(default_factory=list)
    recovery_history: RecoveryHistory = Field(default_factory=RecoveryHistory)
    evidence: list[Evidence] = Field(default_factory=list)
    transitions: list[StateTransition] = Field(default_factory=list)
    trace: ExecutionTrace

    started_at: datetime = Field(default_factory=_now)
    ended_at: datetime | None = None
    error: str | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def recovered(self) -> bool:
        """True if the task ended VERIFIED only after ≥1 recovery attempt."""
        return (
            self.final_outcome.outcome.value == "VERIFIED"
            and self.recovery_history.count > 0
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def false_completion(self) -> bool:
        return self.final_outcome.false_completion
