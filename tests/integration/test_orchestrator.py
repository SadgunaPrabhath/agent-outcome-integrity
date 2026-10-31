"""Integration tests for the Orchestrator control loop (no browser/app)."""

from __future__ import annotations

import pytest

from engine.execution.context import RunContext
from engine.models import (
    ActionHint,
    Idempotency,
    Outcome,
    Postcondition,
    PostconditionType,
    RecoveryPolicyConfig,
    RecoveryStrategy,
    RunState,
    TargetRef,
    TaskSpec,
    VerifierType,
)
from engine.observation.inmemory import InMemoryStateSource
from engine.orchestrator import Orchestrator
from tests.fakes import FakeAdapter


def _task(idempotent: bool = True, max_retries: int = 2) -> TaskSpec:
    action = ActionHint(
        step=1,
        action_type="update" if idempotent else "create",
        description="mutate",
        idempotency=Idempotency.IDEMPOTENT if idempotent else Idempotency.NON_IDEMPOTENT,
    )
    return TaskSpec(
        task_id="profile_update_001",
        description="Set name to Alice",
        target=TargetRef(entity="user_profile"),
        actions=[action],
        expected_postconditions=[
            Postcondition(
                ref="name_is_alice",
                type=PostconditionType.FIELD_EQUALS if idempotent else PostconditionType.EXISTS,
                entity="user_profile",
                field="name" if idempotent else None,
                expected="Alice" if idempotent else None,
            )
        ],
        recovery_policy=RecoveryPolicyConfig(max_retries=max_retries),
    )


@pytest.mark.asyncio
async def test_verified_run_no_recovery():
    ctx = RunContext(task=_task())
    ctx.register_source(InMemoryStateSource(VerifierType.API, {"name": "Alice"}))
    result = await Orchestrator(FakeAdapter(claim_success=True)).run(ctx)

    assert result.final_outcome.outcome is Outcome.VERIFIED
    assert result.recovery_history.count == 0
    assert result.transitions[-1].to_state is RunState.FINAL
    assert not result.false_completion


@pytest.mark.asyncio
async def test_false_completion_is_caught_and_not_recovered_away():
    """Agent claims success; backend never changed; no fix available -> FAILED."""
    api = InMemoryStateSource(VerifierType.API, {"name": "Bob"})
    ctx = RunContext(task=_task())
    ctx.register_source(api)
    result = await Orchestrator(FakeAdapter(claim_success=True)).run(ctx)

    assert result.agent_claim.claimed_success is True
    assert result.final_outcome.outcome is Outcome.FAILED
    assert result.false_completion is True


@pytest.mark.asyncio
async def test_recovery_succeeds_on_retry():
    """First attempt leaves wrong state; the retry writes the correct value."""
    api = InMemoryStateSource(VerifierType.API, {"name": "Bob"})

    def fix_on_retry(n: int) -> None:
        if n >= 2:  # the recovery re-execute
            api.set_field("name", "Alice")

    ctx = RunContext(task=_task())
    ctx.register_source(api)
    result = await Orchestrator(
        FakeAdapter(claim_success=True, on_execute=fix_on_retry)
    ).run(ctx)

    assert result.final_outcome.outcome is Outcome.VERIFIED
    assert result.recovery_history.count >= 1
    assert result.recovered is True


@pytest.mark.asyncio
async def test_non_idempotent_unknown_is_not_retried():
    """create-payment-like: outcome UNKNOWN + non-idempotent -> escalate, no retry."""
    # Only an erroring source -> UNKNOWN outcome.
    api = InMemoryStateSource(VerifierType.API, {}, error="connection reset")
    ctx = RunContext(task=_task(idempotent=False))
    ctx.register_source(api)
    adapter = FakeAdapter(claim_success=True)
    result = await Orchestrator(adapter).run(ctx)

    assert result.final_outcome.outcome is Outcome.UNKNOWN
    # THE safety invariant: the non-idempotent action is never re-executed.
    assert adapter.execute_count == 1
    # Any recovery attempts must be read-only (never a mutating retry).
    mutating = {
        RecoveryStrategy.RETRY_ACTION,
        RecoveryStrategy.RERUN_FAILED_STEP,
        RecoveryStrategy.RERUN_WORKFLOW,
    }
    assert all(a.strategy not in mutating for a in result.recovery_history.attempts)


@pytest.mark.asyncio
async def test_recovery_respects_max_retries():
    """Unfixable failure exhausts retries then stops."""
    api = InMemoryStateSource(VerifierType.API, {"name": "Bob"})
    ctx = RunContext(task=_task(max_retries=2))
    ctx.register_source(api)
    adapter = FakeAdapter(claim_success=True)
    result = await Orchestrator(adapter).run(ctx)

    assert result.final_outcome.outcome is Outcome.FAILED
    assert result.recovery_history.count <= 2
    # 1 initial + up to 2 retries
    assert adapter.execute_count <= 3
