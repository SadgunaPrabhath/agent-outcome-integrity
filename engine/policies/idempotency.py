"""Idempotency + retry-safety policy.

The single most important safety rule in AOIE lives here (Section 12): never
blindly repeat an action that *might* have already taken effect.

Two distinct questions:

  1. ``is_task_idempotent`` — is repeating this task's mutations inherently safe?
     Declared per-action in the TaskSpec; inferred from postcondition shape when
     no action hints are given.

  2. ``retry_is_safe`` — given the *verified outcome*, is a retry safe *now*?
     Crucially, a FAILED outcome (we proved the state did NOT change) makes retry
     safe even for a non-idempotent action, because it definitively did not take
     effect. An UNKNOWN outcome (we could not prove it either way) is the danger
     zone: retry only if the task is idempotent.
"""

from __future__ import annotations

from engine.models import (
    ActionHint,
    Idempotency,
    Outcome,
    PostconditionType,
    TaskSpec,
)

# Action types that change persistent state (and thus carry retry risk).
_MUTATING_ACTIONS = {
    "fill",
    "click",
    "submit",
    "api_call",
    "create",
    "update",
    "delete",
    "post",
    "put",
    "patch",
}

# Postcondition shapes that are inherently safe to re-establish by repetition.
_IDEMPOTENT_PC_TYPES = {
    PostconditionType.FIELD_EQUALS,
    PostconditionType.FIELD_MATCHES,
    PostconditionType.STATE_TRANSITION,
    PostconditionType.NOT_EXISTS,  # deleting an already-deleted item is safe
}


def _is_mutating(action: ActionHint) -> bool:
    return action.action_type.lower() in _MUTATING_ACTIONS


def is_task_idempotent(task: TaskSpec) -> bool:
    """Return True iff repeating the task's mutations is inherently safe."""
    mutating = [a for a in task.actions if _is_mutating(a)]
    if mutating:
        return all(a.idempotency is Idempotency.IDEMPOTENT for a in mutating)

    # No action hints: infer conservatively from the postconditions. If any
    # postcondition implies creation/accumulation (EXISTS as create, COUNT), a
    # repeat could duplicate, so treat as non-idempotent.
    return all(
        pc.type in _IDEMPOTENT_PC_TYPES for pc in task.expected_postconditions
    )


def retry_is_safe(outcome: Outcome, task: TaskSpec) -> bool:
    """Is retrying the mutation safe given the *verified* outcome?"""
    if outcome is Outcome.FAILED:
        # Proven the state did not change -> retrying cannot double-apply.
        return True
    if outcome in (Outcome.UNKNOWN, Outcome.PARTIAL):
        # Could-have-happened: only safe if the task is inherently idempotent.
        return is_task_idempotent(task)
    return False
