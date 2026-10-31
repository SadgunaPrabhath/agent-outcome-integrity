"""TaskSpec — the structured request AOIE receives.

A TaskSpec captures *what the user wants to be true* (postconditions) plus
enough context to run an agent, verify the result, and recover safely. Action
hints are advisory: AOIE never trusts them as proof of what happened.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from engine.models.enums import Idempotency, RecoveryStrategy, VerifierType
from engine.models.postcondition import Postcondition


class TargetRef(BaseModel):
    """Identifies the entity a task mutates, so verifiers know what to inspect."""

    entity: str
    entity_id: str | None = None
    locator: dict[str, str] = Field(
        default_factory=dict,
        description="Source-specific hints, e.g. {'api_path': '/api/profile', 'db_table': 'users'}",
    )


class Precondition(BaseModel):
    """A predicate expected to hold *before* the agent runs (advisory)."""

    description: str
    postcondition: Postcondition | None = None


class ActionHint(BaseModel):
    """Advisory description of an action the agent is expected to take.

    ``idempotency`` is the key safety signal for recovery: it declares whether
    repeating this action is safe. Defaults to UNKNOWN, which recovery treats as
    non-idempotent.
    """

    step: int
    action_type: str  # e.g. "navigate", "fill", "click", "api_call"
    description: str
    target: str | None = None
    payload: dict[str, object] | None = None  # e.g. create/update field values
    idempotency: Idempotency = Idempotency.UNKNOWN


class RecoveryPolicyConfig(BaseModel):
    max_retries: int = Field(2, ge=0)
    allowed_strategies: list[RecoveryStrategy] = Field(
        default_factory=lambda: [
            RecoveryStrategy.REFRESH_STATE,
            RecoveryStrategy.RECHECK_AUTH,
            RecoveryStrategy.RETRY_ACTION,
            RecoveryStrategy.RERUN_FAILED_STEP,
            RecoveryStrategy.ESCALATE_HUMAN,
        ]
    )
    # If True, never auto-retry a mutation whose success could not be disproven.
    conservative_non_idempotent: bool = True


class TaskSpec(BaseModel):
    task_id: str
    description: str
    target: TargetRef
    expected_postconditions: list[Postcondition] = Field(..., min_length=1)
    preconditions: list[Precondition] = Field(default_factory=list)
    actions: list[ActionHint] = Field(default_factory=list)
    verification_methods: list[VerifierType] = Field(
        default_factory=list,
        description="Task-level default verifier preference (postconditions may override).",
    )
    recovery_policy: RecoveryPolicyConfig = Field(default_factory=RecoveryPolicyConfig)
    timeout_s: int = Field(60, gt=0)
    max_retries: int = Field(2, ge=0)

    def resolved_methods(self, pc: Postcondition) -> list[VerifierType]:
        """Effective verifier preference for a postcondition (pc > task > any)."""
        return pc.verification_methods or self.verification_methods
