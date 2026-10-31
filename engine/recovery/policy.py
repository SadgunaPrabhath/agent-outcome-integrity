"""RecoveryPolicy — decide whether and how to recover from a failed outcome.

``SafeRecoveryPolicy`` maps a classified outcome to a recovery strategy while
enforcing the idempotency safety gate. It never returns a mutating strategy when
retrying could double-apply a non-idempotent action whose success we could not
disprove — in that case it returns ``NoRecovery(escalate=True)``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from engine.models import (
    FailureClass,
    NoRecovery,
    Outcome,
    RecoveryHistory,
    RecoveryPlan,
    RecoveryStrategy,
    TaskOutcome,
    TaskSpec,
)
from engine.policies.idempotency import retry_is_safe

_MUTATING_STRATEGIES = {
    RecoveryStrategy.RETRY_ACTION,
    RecoveryStrategy.RERUN_FAILED_STEP,
    RecoveryStrategy.RERUN_WORKFLOW,
}


class RecoveryPolicy(ABC):
    @abstractmethod
    def plan(
        self, outcome: TaskOutcome, task: TaskSpec, history: RecoveryHistory
    ) -> RecoveryPlan | NoRecovery:
        raise NotImplementedError


class SafeRecoveryPolicy(RecoveryPolicy):
    def plan(
        self, outcome: TaskOutcome, task: TaskSpec, history: RecoveryHistory
    ) -> RecoveryPlan | NoRecovery:
        if outcome.outcome is Outcome.VERIFIED:
            return NoRecovery(reason="Outcome already verified; nothing to recover.")

        if history.count >= task.recovery_policy.max_retries:
            return NoRecovery(
                reason=f"Exhausted max_retries={task.recovery_policy.max_retries}.",
                escalate=True,
            )

        strategy, target_step, reason = self._choose_strategy(outcome, history)

        # Non-mutating strategies (refresh/auth/escalate) are always safe.
        if strategy not in _MUTATING_STRATEGIES:
            return self._finalize(strategy, task, reason, target_step, idempotency_safe=True)

        safe = retry_is_safe(outcome.outcome, task)
        if not safe and task.recovery_policy.conservative_non_idempotent:
            return NoRecovery(
                reason=(
                    "Non-idempotent action may have partially succeeded and the "
                    "outcome could not be disproven; refusing to retry. Escalating."
                ),
                escalate=True,
            )
        return self._finalize(strategy, task, reason, target_step, idempotency_safe=safe)

    def _choose_strategy(
        self, outcome: TaskOutcome, history: RecoveryHistory
    ) -> tuple[RecoveryStrategy, int | None, str]:
        fc = outcome.failure_class
        already_refreshed = any(
            a.strategy is RecoveryStrategy.REFRESH_STATE for a in history.attempts
        )

        if fc is FailureClass.AUTH_FAILURE:
            return RecoveryStrategy.RECHECK_AUTH, None, "Re-establish authentication."

        if fc is FailureClass.STALE_STATE:
            return RecoveryStrategy.REFRESH_STATE, None, "Refresh potentially stale state."

        if fc is FailureClass.STATE_CONFLICT or outcome.outcome is Outcome.UNKNOWN:
            # A conflict/unknown gets exactly one refresh; if that doesn't resolve
            # it, escalate rather than thrash. Signalled by ESCALATE_HUMAN here so
            # the idempotency gate treats it as non-mutating.
            if already_refreshed:
                return (
                    RecoveryStrategy.ESCALATE_HUMAN,
                    None,
                    "Conflict/unknown persisted after refresh; escalating.",
                )
            return (
                RecoveryStrategy.REFRESH_STATE,
                None,
                "Sources conflict or outcome unknown; re-observe before deciding.",
            )

        if fc is FailureClass.WRONG_TARGET:
            return (
                RecoveryStrategy.RERUN_FAILED_STEP,
                None,
                "Wrong target was modified; re-run the step against the correct target.",
            )

        if outcome.outcome is Outcome.PARTIAL:
            return (
                RecoveryStrategy.RERUN_FAILED_STEP,
                None,
                "Some postconditions failed; re-run only the failed steps.",
            )

        # PERSISTENCE/BACKEND/NETWORK/TIMEOUT/WRONG_VALUE/UI_FALSE_COMPLETION
        return (
            RecoveryStrategy.RETRY_ACTION,
            None,
            f"Retry the mutation ({fc.value if fc else 'unclassified'}).",
        )

    @staticmethod
    def _finalize(
        strategy: RecoveryStrategy,
        task: TaskSpec,
        reason: str,
        target_step: int | None,
        idempotency_safe: bool,
    ) -> RecoveryPlan | NoRecovery:
        allowed = task.recovery_policy.allowed_strategies
        if strategy not in allowed:
            if RecoveryStrategy.ESCALATE_HUMAN in allowed:
                return RecoveryPlan(
                    strategy=RecoveryStrategy.ESCALATE_HUMAN,
                    reason=f"{reason} (chosen strategy not permitted; escalating)",
                    idempotency_safe=True,
                )
            return NoRecovery(reason=f"{reason} (no permitted strategy).", escalate=True)
        return RecoveryPlan(
            strategy=strategy,
            reason=reason,
            idempotency_safe=idempotency_safe,
            target_step=target_step,
        )
