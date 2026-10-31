"""BrowserUiAdapter — a browser agent that trusts what the page shows.

This is the heterogeneous, *non-scripted* agent AOIE exists to check: instead of
reading an HTTP status code, it drives a real UI (type a value, click Save) and
concludes success from the on-screen banner. When the backend write silently
fails but the optimistic UI still renders "Saved ✓", this agent confidently and
wrongly claims success — a false completion AOIE then catches by reading the
authoritative ``/api``/DB behind the page.

It is deliberately written against :class:`PageDriver`, so the exact same agent
logic runs on a real Chromium page (:class:`PlaywrightPageDriver`) or on the
browser-free simulator (:class:`HttpxPageDriver`) used in CI.
"""

from __future__ import annotations

from adapters.base import AdapterResult, AgentAdapter
from adapters.playwright.driver import (
    SEL_FIELD,
    SEL_SAVE,
    SEL_STATUS,
    SEL_VALUE,
    HttpxPageDriver,
    PageDriver,
)
from engine.execution.context import RunContext
from engine.models import (
    AgentClaim,
    PostconditionType,
    TaskSpec,
    TraceEvent,
)

_TYPEABLE = (
    PostconditionType.FIELD_EQUALS,
    PostconditionType.FIELD_MATCHES,
    PostconditionType.STATE_TRANSITION,
)


class BrowserUiAdapter(AgentAdapter):
    name = "browser-ui"

    def __init__(
        self, driver: PageDriver | None = None, *, base_url: str = "http://testserver"
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._driver = driver or HttpxPageDriver(base_url=base_url)
        self._events: list[TraceEvent] = []

    async def initialize(self, ctx: RunContext) -> None:
        self._events.append(TraceEvent(kind="agent.action", name="initialize"))

    async def execute(self, task: TaskSpec) -> AdapterResult:
        plan = self._plan(task)
        if plan is None:
            msg = "no typeable field postcondition; BrowserUiAdapter drives form updates only"
            claim = AgentClaim(claimed_success=False, message=msg)
            return AdapterResult(claim=claim, events=list(self._events), error=msg)

        collection, record_id, field_name, value = plan
        url = f"/app/{collection}/{record_id}?field={field_name}"
        events: list[TraceEvent] = []
        try:
            await self._driver.goto(url)
            events.append(TraceEvent(kind="agent.action", name="navigate", attributes={"url": url}))
            await self._driver.fill(SEL_FIELD, field_name)
            await self._driver.fill(SEL_VALUE, value)
            events.append(
                TraceEvent(
                    kind="agent.action",
                    name="fill",
                    attributes={"field": field_name, "value": value},
                )
            )
            await self._driver.click(SEL_SAVE)
            events.append(TraceEvent(kind="agent.action", name="click", attributes={"selector": SEL_SAVE}))
            await self._driver.wait_for_selector(SEL_STATUS)
            status_text = (await self._driver.text_content(SEL_STATUS)) or ""
        except Exception as exc:  # noqa: BLE001 - agent honestly reports UI-driving failure
            events.append(TraceEvent(kind="agent.error", name="drive_failed", attributes={"error": str(exc)}))
            self._events.extend(events)
            return AdapterResult(
                claim=AgentClaim(claimed_success=False, message=str(exc)),
                events=events,
                error=str(exc),
            )

        # Record what the page reported over the network (a 200 may be a lie).
        for net in self._driver.network_events():
            events.append(
                TraceEvent(
                    kind="network",
                    name=f"{net.method} {net.url}",
                    attributes={"status": net.status, "body": net.body},
                )
            )
        events.append(
            TraceEvent(kind="dom", name="read_status", attributes={"selector": SEL_STATUS, "text": status_text})
        )

        # Naive success rule: believe the on-screen banner.
        claimed = status_text.strip().lower().startswith("saved")
        claim = AgentClaim(
            claimed_success=claimed,
            message=f"UI reported: {status_text!r}",
        )
        self._events.extend(events)
        return AdapterResult(claim=claim, events=events)

    def get_trace(self) -> list[TraceEvent]:
        return list(self._events)

    async def cleanup(self) -> None:
        await self._driver.close()

    # --- planning ------------------------------------------------------------
    def _plan(self, task: TaskSpec) -> tuple[str, str, str, str] | None:
        target = task.target
        collection = target.locator.get("collection", target.entity)
        record_id = target.locator.get("record_id", target.entity_id or "")

        for pc in task.expected_postconditions:
            if pc.field and pc.type in _TYPEABLE:
                value = "" if pc.expected is None else str(pc.expected)
                return collection, record_id, pc.field, value
        # Action payloads are a fallback source of a typeable field/value.
        for action in task.actions:
            if action.payload:
                field_name, value = next(iter(action.payload.items()))
                return collection, record_id, field_name, str(value)
        return None
