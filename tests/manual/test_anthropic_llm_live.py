"""Opt-in live proof: a real Claude tool-using agent, verified by AOIE.

Deselected by default (marked ``live``). To run it:

    pip install -e ".[dev,llm]"
    export ANTHROPIC_API_KEY=...        # or: ant auth login
    pytest -m live -k anthropic_llm

Real model output is non-deterministic, so this asserts the *model-independent*
property AOIE guarantees: whatever the agent claims, when the backend write
silently fails AOIE must not certify the run as VERIFIED. The honest-path check
asserts the agent can be verified when it genuinely succeeds.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import pytest_asyncio

from adapters.llm import AnthropicLLMClient, LLMAgentAdapter
from engine.execution.context import RunContext
from engine.models import (
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

pytestmark = pytest.mark.live

BASE_URL = "http://testserver"


@pytest_asyncio.fixture
async def demo(tmp_path: Path):
    db_path = str(tmp_path / "demo.sqlite")
    app = create_app(db_path=db_path, timeout_delay_s=1.5)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        await client.post(
            "/admin/seed",
            json={"collection": "profiles", "record_id": "1", "fields": {"name": "Bob"}},
        )
        yield client, db_path


def _task() -> TaskSpec:
    return TaskSpec(
        task_id="live_llm_update",
        description="Change the profile name to Alice",
        target=TargetRef(entity="profiles", entity_id="1",
                         locator={"collection": "profiles", "record_id": "1"}),
        expected_postconditions=[
            Postcondition(ref="name_is_alice", type=PostconditionType.FIELD_EQUALS,
                          entity="profiles", field="name", expected="Alice")
        ],
        timeout_s=30,
        recovery_policy=RecoveryPolicyConfig(max_retries=0),
    )


async def _run(client, db_path, task):
    ctx = RunContext(task=task)
    for s in demo_sources(BASE_URL, db_path, client=client):
        ctx.register_source(s)
    adapter = LLMAgentAdapter(AnthropicLLMClient(), base_url=BASE_URL, http_client=client)
    return await Orchestrator(adapter).run(ctx)


@pytest.mark.asyncio
async def test_live_llm_honest_success_verifiable(demo):
    client, db_path = demo
    await client.post(
        "/admin/scenario",
        json={"collection": "profiles", "record_id": "1", "scenario": Scenario.NONE.value},
    )
    result = await _run(client, db_path, _task())
    assert result.final_outcome.outcome is Outcome.VERIFIED


@pytest.mark.asyncio
async def test_live_llm_false_completion_is_caught(demo):
    client, db_path = demo
    await client.post(
        "/admin/scenario",
        json={"collection": "profiles", "record_id": "1",
              "scenario": Scenario.FAIL_BACKEND_WRITE.value},
    )
    result = await _run(client, db_path, _task())
    # Model-independent guarantee: a silently-failed write is never VERIFIED.
    assert result.final_outcome.outcome is not Outcome.VERIFIED
