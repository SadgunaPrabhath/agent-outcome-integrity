"""End-to-end: a *browser* agent drives the live demo UI; AOIE verifies reality.

Same proof as the scripted e2e, but with the heterogeneous browser agent
(:class:`BrowserUiAdapter`) driven by the browser-free :class:`HttpxPageDriver`
against the real demo app — so it runs in CI without a Chromium binary while
exercising the genuine "trust the on-screen banner" behaviour. The live-Chromium
variant is opt-in (see tests/manual/test_playwright_live.py).
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import pytest_asyncio

from adapters.playwright import BrowserUiAdapter, HttpxPageDriver
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
        await client.post(
            "/admin/seed",
            json={"collection": "profiles", "record_id": "1", "fields": {"name": "Bob"}},
        )
        yield client, db_path


def _profile_task() -> TaskSpec:
    return TaskSpec(
        task_id="browser_profile_update",
        description="Change profile name to Alice via the UI",
        target=TargetRef(
            entity="profiles", entity_id="1",
            locator={"collection": "profiles", "record_id": "1"},
        ),
        actions=[ActionHint(step=1, action_type="fill", description="type name",
                            idempotency=Idempotency.IDEMPOTENT)],
        expected_postconditions=[
            Postcondition(
                ref="name_is_alice", type=PostconditionType.FIELD_EQUALS,
                entity="profiles", field="name", expected="Alice",
            )
        ],
        timeout_s=1,
        recovery_policy=RecoveryPolicyConfig(max_retries=0),
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
    adapter = BrowserUiAdapter(driver=HttpxPageDriver(client=client))
    return await Orchestrator(adapter).run(ctx)


@pytest.mark.asyncio
async def test_demo_serves_drivable_html_page(demo):
    """The /app route returns a real form with the selectors the agent drives."""
    client, _ = demo
    resp = await client.get("/app/profiles/1?field=name")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    body = resp.text
    for selector in ('id="field"', 'id="value"', 'id="save"', 'id="status"'):
        assert selector in body


@pytest.mark.asyncio
async def test_browser_honest_success_is_verified(demo):
    client, db_path = demo
    await _set_scenario(client, Scenario.NONE)
    result = await _run(client, db_path, _profile_task())
    assert result.agent_claim.claimed_success is True
    assert result.final_outcome.outcome is Outcome.VERIFIED
    assert result.false_completion is False


@pytest.mark.asyncio
async def test_browser_false_completion_on_optimistic_ui(demo):
    """The headline: the UI shows 'Saved ✓', the browser agent believes it, but
    the backend never changed — AOIE catches the false completion."""
    client, db_path = demo
    await _set_scenario(client, Scenario.FAIL_BACKEND_WRITE)
    result = await _run(client, db_path, _profile_task())
    assert result.agent_claim.claimed_success is True  # fooled by the banner
    assert result.final_outcome.outcome is Outcome.FAILED
    assert result.final_outcome.failure_class is FailureClass.UI_FALSE_COMPLETION
    assert result.false_completion is True


@pytest.mark.asyncio
async def test_browser_auth_failure_is_honest(demo):
    client, db_path = demo
    await _set_scenario(client, Scenario.AUTH_FAILURE)
    result = await _run(client, db_path, _profile_task())
    # Banner shows 'Error ✗ (401)' -> the agent does not claim success.
    assert result.agent_claim.claimed_success is False
    assert result.final_outcome.outcome is Outcome.FAILED
    assert result.false_completion is False
