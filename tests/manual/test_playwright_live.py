"""Opt-in live-browser proof: real Chromium drives the demo UI end to end.

Deselected by default (marked ``live``) so the standard suite needs no browser
binary. To run it:

    pip install -e ".[api,browser]"
    playwright install chromium
    # start the demo app on :8137 in another shell, e.g.
    #   AOIE_DEMO_DB=demo_live.sqlite uvicorn environments.demo_app.wiring:app --port 8137
    pytest -m live

This exercises the *same* BrowserUiAdapter as the CI e2e, but through a genuine
Chromium page — the ultimate check that AOIE wraps a real heterogeneous agent.
"""

from __future__ import annotations

import os

import pytest

from adapters.playwright import BrowserUiAdapter, PlaywrightPageDriver
from engine.execution.context import RunContext
from engine.models import (
    Postcondition,
    PostconditionType,
    TargetRef,
    TaskSpec,
)
from engine.observation.screenshot import ScreenshotStateSource

pytestmark = pytest.mark.live

BASE_URL = os.environ.get("AOIE_DEMO_URL", "http://localhost:8137")


def _task() -> TaskSpec:
    return TaskSpec(
        task_id="live_browser_update",
        description="Change profile name to Alice via a real browser",
        target=TargetRef(
            entity="profiles", entity_id="1",
            locator={"collection": "profiles", "record_id": "1"},
        ),
        expected_postconditions=[
            Postcondition(
                ref="name_is_alice", type=PostconditionType.FIELD_EQUALS,
                entity="profiles", field="name", expected="Alice",
            )
        ],
    )


@pytest.mark.asyncio
async def test_live_browser_drives_ui_and_reports_claim():
    driver = PlaywrightPageDriver(base_url=BASE_URL, headless=True)
    await driver.launch()
    adapter = BrowserUiAdapter(driver=driver, base_url=BASE_URL)
    try:
        ctx = RunContext(task=_task())
        await adapter.initialize(ctx)
        result = await adapter.execute(ctx.task)
        # The agent formed a claim from the on-screen banner and recorded network
        # traffic; AOIE would verify this claim against the backend separately.
        assert isinstance(result.claim.claimed_success, bool)
        assert any(e.kind == "network" for e in result.events)

        # Real-screenshot pipeline: capture a genuine Chromium PNG and confirm the
        # dependency-free codec decodes it into an aHash the Visual verifier can use.
        shot = ScreenshotStateSource.from_driver(driver)
        obs = await shot.read(ctx.task.expected_postconditions[0], ctx.task.target)
        assert obs.ok, obs.error
        assert isinstance(obs.state["ahash"], str) and obs.state["width"] > 0
    finally:
        await adapter.cleanup()
