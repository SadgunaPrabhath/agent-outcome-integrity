"""End-to-end: scripted agent drives the live demo app; AOIE verifies reality.

This is the headline proof. For each injected failure scenario we assert:
  * what the naive agent *claims* (from the HTTP response), and
  * what AOIE *independently determines* from API + DB + UI observation.

Everything runs in-process via httpx's ASGI transport against a real SQLite file
that AOIE's DatabaseVerifier reads directly.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import pytest_asyncio

from adapters.scripted import ScriptedHttpAdapter
from engine.execution.context import RunContext
from engine.models import (
    ActionHint,
    FailureClass,
    Idempotency,
    Outcome,
    Postcondition,
    PostconditionType,
    RecoveryPolicyConfig,
    TargetRef,
    TaskSpec,
)
from engine.orchestrator import Orchestrator
from environments.demo_app import Scenario, create_app
from environments.demo_app.wiring import demo_sources

BASE_URL = "http://testserver"


@pytest_asyncio.fixture
async def demo(tmp_path: Path):
    db_path = str(tmp_path / "demo.sqlite")
    app = create_app(db_path=db_path, timeout_delay_s=1.5)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        # seed a profile record
        await client.post(
            "/admin/seed",
            json={"collection": "profiles", "record_id": "1", "fields": {"name": "Bob"}},
        )
        yield client, db_path


def _profile_task(max_retries: int = 0) -> TaskSpec:
    return TaskSpec(
        task_id="profile_update_001",
        description="Change profile name to Alice",
        target=TargetRef(
            entity="profiles",
            entity_id="1",
            locator={"collection": "profiles", "record_id": "1"},
        ),
        actions=[
            ActionHint(step=1, action_type="update", description="set name",
                       idempotency=Idempotency.IDEMPOTENT)
        ],
        expected_postconditions=[
            Postcondition(
                ref="name_is_alice",
                type=PostconditionType.FIELD_EQUALS,
                entity="profiles",
                field="name",
                expected="Alice",
            )
        ],
        timeout_s=1,
        recovery_policy=RecoveryPolicyConfig(max_retries=max_retries),
    )


async def _set_scenario(client: httpx.AsyncClient, scenario: Scenario) -> None:
    await client.post(
        "/admin/scenario",
        json={"collection": "profiles", "record_id": "1", "scenario": scenario.value},
    )


async def _run(client, db_path, task):
    ctx = RunContext(task=task)
    for s in demo_sources(BASE_URL, db_path, client=client):
        ctx.register_source(s)
    adapter = ScriptedHttpAdapter(base_url=BASE_URL, client=client)
    return await Orchestrator(adapter).run(ctx)


@pytest.mark.asyncio
async def test_honest_success_is_verified(demo):
    client, db_path = demo
    await _set_scenario(client, Scenario.NONE)
    result = await _run(client, db_path, _profile_task())
    assert result.agent_claim.claimed_success is True
    assert result.final_outcome.outcome is Outcome.VERIFIED
    assert result.false_completion is False


@pytest.mark.asyncio
async def test_fail_backend_write_is_false_completion(demo):
    """Agent sees 200 and claims success; API+DB show Bob; UI shows Alice."""
    client, db_path = demo
    await _set_scenario(client, Scenario.FAIL_BACKEND_WRITE)
    result = await _run(client, db_path, _profile_task())
    assert result.agent_claim.claimed_success is True  # naive agent fooled
    assert result.final_outcome.outcome is Outcome.FAILED
    assert result.final_outcome.failure_class is FailureClass.UI_FALSE_COMPLETION
    assert result.false_completion is True


@pytest.mark.asyncio
async def test_wrong_value_detected(demo):
    client, db_path = demo
    await _set_scenario(client, Scenario.WRONG_VALUE)
    result = await _run(client, db_path, _profile_task())
    assert result.final_outcome.outcome is Outcome.FAILED
    # A wrong, non-empty value persisted -> WRONG_VALUE or UI_FALSE_COMPLETION
    assert result.final_outcome.failure_class in (
        FailureClass.WRONG_VALUE,
        FailureClass.UI_FALSE_COMPLETION,
    )
    assert result.false_completion is True


@pytest.mark.asyncio
async def test_wrong_target_detected(demo):
    client, db_path = demo
    await _set_scenario(client, Scenario.WRONG_TARGET)
    result = await _run(client, db_path, _profile_task())
    assert result.final_outcome.outcome is Outcome.FAILED
    assert result.false_completion is True


@pytest.mark.asyncio
async def test_auth_failure_agent_is_honest(demo):
    client, db_path = demo
    await _set_scenario(client, Scenario.AUTH_FAILURE)
    result = await _run(client, db_path, _profile_task())
    # agent gets 401 -> does NOT claim success (honest failure)
    assert result.agent_claim.claimed_success is False
    assert result.final_outcome.outcome is Outcome.FAILED
    assert result.false_completion is False


@pytest.mark.asyncio
async def test_stale_read_is_conflict(demo):
    """DB persisted the new value but the API read is stale -> CONFLICT/UNKNOWN."""
    client, db_path = demo
    await _set_scenario(client, Scenario.STALE_READ)
    result = await _run(client, db_path, _profile_task())
    assert result.final_outcome.outcome is Outcome.UNKNOWN
    assert result.final_outcome.failure_class is FailureClass.STATE_CONFLICT


@pytest.mark.asyncio
async def test_timeout_detected(demo):
    client, db_path = demo
    await _set_scenario(client, Scenario.TIMEOUT)
    result = await _run(client, db_path, _profile_task())
    assert result.agent_claim.claimed_success is False
    assert result.final_outcome.outcome in (Outcome.FAILED, Outcome.UNKNOWN)


@pytest.mark.asyncio
async def test_recovery_fixes_backend_write_when_scenario_clears(demo):
    """With retries allowed, clearing the fault mid-run lets recovery verify."""
    client, db_path = demo
    await _set_scenario(client, Scenario.FAIL_BACKEND_WRITE)

    task = _profile_task(max_retries=2)
    ctx = RunContext(task=task)
    for s in demo_sources(BASE_URL, db_path, client=client):
        ctx.register_source(s)

    # An adapter wrapper that clears the fault before the first recovery retry.
    adapter = ScriptedHttpAdapter(base_url=BASE_URL, client=client)
    original_execute = adapter.execute
    calls = {"n": 0}

    async def execute_then_heal(t):
        calls["n"] += 1
        if calls["n"] == 2:  # before the recovery re-execute takes effect
            await _set_scenario(client, Scenario.NONE)
        return await original_execute(t)

    adapter.execute = execute_then_heal  # type: ignore[method-assign]

    result = await Orchestrator(adapter).run(ctx)
    assert result.final_outcome.outcome is Outcome.VERIFIED
    assert result.recovered is True
