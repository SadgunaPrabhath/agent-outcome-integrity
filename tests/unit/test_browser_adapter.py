"""BrowserUiAdapter unit tests against a stub PageDriver (no app, no browser)."""

from __future__ import annotations

import pytest

from adapters.playwright.adapter import BrowserUiAdapter
from adapters.playwright.driver import (
    SEL_STATUS,
    NetworkRecord,
)
from engine.execution.context import RunContext
from engine.models import (
    Postcondition,
    PostconditionType,
    TargetRef,
    TaskSpec,
)


class StubDriver:
    """A minimal in-memory PageDriver that returns a canned status banner."""

    def __init__(self, status_text: str, network: list[NetworkRecord] | None = None) -> None:
        self.status_text = status_text
        self._network = network or []
        self.actions: list[tuple[str, str]] = []
        self.closed = False

    async def goto(self, url: str) -> None:
        self.actions.append(("goto", url))

    async def fill(self, selector: str, value: str) -> None:
        self.actions.append(("fill", f"{selector}={value}"))

    async def click(self, selector: str) -> None:
        self.actions.append(("click", selector))

    async def text_content(self, selector: str) -> str | None:
        return self.status_text if selector == SEL_STATUS else None

    async def wait_for_selector(self, selector: str, timeout_ms: int = 5000) -> None:
        return None

    async def screenshot(self) -> bytes:
        return self.status_text.encode()

    def network_events(self) -> list[NetworkRecord]:
        return list(self._network)

    async def close(self) -> None:
        self.closed = True


def _update_task() -> TaskSpec:
    return TaskSpec(
        task_id="t",
        description="set name to Alice",
        target=TargetRef(entity="profiles", entity_id="1",
                         locator={"collection": "profiles", "record_id": "1"}),
        expected_postconditions=[
            Postcondition(
                ref="name", type=PostconditionType.FIELD_EQUALS,
                entity="profiles", field="name", expected="Alice",
            )
        ],
    )


@pytest.mark.asyncio
async def test_claims_success_when_banner_says_saved():
    driver = StubDriver("Saved ✓", [NetworkRecord("PUT", "/api/profiles/1", 200, "{}")])
    adapter = BrowserUiAdapter(driver=driver)
    ctx = RunContext(task=_update_task())
    await adapter.initialize(ctx)
    result = await adapter.execute(ctx.task)
    assert result.claim.claimed_success is True
    # It drove the form: navigate, fill field, fill value, click save.
    assert ("click", "#save") in driver.actions
    assert any(k == "fill" for k, _ in driver.actions)


@pytest.mark.asyncio
async def test_claims_failure_when_banner_says_error():
    driver = StubDriver("Error ✗ (401)", [NetworkRecord("PUT", "/api/profiles/1", 401, "")])
    adapter = BrowserUiAdapter(driver=driver)
    ctx = RunContext(task=_update_task())
    result = await adapter.execute(ctx.task)
    assert result.claim.claimed_success is False


@pytest.mark.asyncio
async def test_network_events_become_trace_events():
    driver = StubDriver("Saved ✓", [NetworkRecord("PUT", "/api/profiles/1", 200, '{"name":"Alice"}')])
    adapter = BrowserUiAdapter(driver=driver)
    result = await adapter.execute(_update_task())
    kinds = {e.kind for e in result.events}
    assert "network" in kinds
    assert "dom" in kinds


@pytest.mark.asyncio
async def test_unsupported_task_shape_claims_failure():
    """A delete-style task has no typeable field -> honest failure, not a guess."""
    task = TaskSpec(
        task_id="del",
        description="delete the record",
        target=TargetRef(entity="profiles", entity_id="1"),
        expected_postconditions=[
            Postcondition(ref="gone", type=PostconditionType.NOT_EXISTS, entity="profiles")
        ],
    )
    adapter = BrowserUiAdapter(driver=StubDriver("Saved ✓"))
    result = await adapter.execute(task)
    assert result.claim.claimed_success is False
    assert "form updates only" in (result.error or "")


@pytest.mark.asyncio
async def test_cleanup_closes_driver():
    driver = StubDriver("Saved ✓")
    adapter = BrowserUiAdapter(driver=driver)
    await adapter.cleanup()
    assert driver.closed is True
