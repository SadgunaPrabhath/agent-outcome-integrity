"""Task-level outcome model — the final, auditable verdict of a run."""

from __future__ import annotations

from pydantic import BaseModel, Field, computed_field

from engine.models.enums import FailureClass, Outcome
from engine.models.verification import ReconciledVerdict


class AgentClaim(BaseModel):
    """What the agent itself reported. Recorded, never trusted as proof."""

    claimed_success: bool
    message: str | None = None


class TaskOutcome(BaseModel):
    """AOIE's independent conclusion, contrasted against the agent's claim."""

    outcome: Outcome
    failure_class: FailureClass | None = None
    agent_claim: AgentClaim
    verdicts: list[ReconciledVerdict] = Field(default_factory=list)
    confidence: float = Field(..., ge=0.0, le=1.0)
    satisfied_weight: float = 0.0
    total_weight: float = 0.0
    reason: str = ""

    @computed_field  # type: ignore[prop-decorator]
    @property
    def false_completion(self) -> bool:
        """True when the agent claimed success but AOIE could not verify it.

        This is the headline signal of the whole project. UNKNOWN counts as a
        false completion only in the strict sense that the claim was unproven;
        the benchmark separates "verified-false" (FAILED) from "unproven"
        (UNKNOWN) via the ``outcome`` field, but both mean "do not trust the
        claim as-is".
        """
        return self.agent_claim.claimed_success and self.outcome is not Outcome.VERIFIED
