"""ScriptedHttpAdapter — a deterministic, controllable agent over HTTP.

It models the *naive* agent AOIE exists to check: it performs the mutation and
concludes success from the HTTP response alone (2xx => "done"). Under an injected
failure scenario the demo app still returns 200, so this agent will confidently
(and wrongly) claim success — producing the false completions AOIE then catches.

The mutation is derived from the task's postconditions and target:
  * a NOT_EXISTS postcondition  -> DELETE
  * an EXISTS postcondition     -> POST (create), fields from an action payload
  * field/state postconditions  -> PUT (update), fields = {field: expected}

Because it is scripted (not an LLM), runs are reproducible and the "claim" can be
trusted to reflect exactly what a response-trusting agent would conclude.
"""

from __future__ import annotations

from typing import Any

import httpx

from adapters.base import AdapterResult, AgentAdapter
from engine.execution.context import RunContext
from engine.models import (
    AgentClaim,
    PostconditionType,
    TargetRef,
    TaskSpec,
    TraceEvent,
)
from engine.tracing import redact


class ScriptedHttpAdapter(AgentAdapter):
    name = "scripted-http"

    def __init__(
        self,
        base_url: str = "http://testserver",
        *,
        client: httpx.AsyncClient | None = None,
        timeout_s: float = 5.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = client
        self.timeout_s = timeout_s
        self._events: list[TraceEvent] = []
        self._ctx: RunContext | None = None

    async def initialize(self, ctx: RunContext) -> None:
        self._ctx = ctx
        self._events.append(TraceEvent(kind="agent.action", name="initialize"))

    async def execute(self, task: TaskSpec) -> AdapterResult:
        method, path, body = self._plan_mutation(task)
        events = [TraceEvent(kind="agent.action", name=method, attributes={"path": path})]
        try:
            resp = await self._request(method, path, body)
        except Exception as exc:  # noqa: BLE001 - agent honestly reports any request failure
            events.append(
                TraceEvent(kind="network", name="error", attributes={"error": str(exc)})
            )
            self._events.extend(events)
            return AdapterResult(
                claim=AgentClaim(claimed_success=False, message=str(exc)),
                events=events,
                error=str(exc),
            )

        status = resp.status_code
        events.append(
            TraceEvent(
                kind="network",
                name=f"{method} {path}",
                attributes={"status": status, "body": redact(_safe_json(resp))},
            )
        )
        success = 200 <= status < 300
        claim = AgentClaim(
            claimed_success=success,
            message=f"HTTP {status}" + ("" if success else " — request rejected"),
        )
        self._events.extend(events)
        return AdapterResult(claim=claim, events=events)

    async def reauthenticate(self) -> None:
        # Placeholder for RECHECK_AUTH recovery; the synthetic demo has no real
        # login, so this is a no-op that records the attempt.
        self._events.append(TraceEvent(kind="agent.action", name="reauthenticate"))

    def get_trace(self) -> list[TraceEvent]:
        return list(self._events)

    # --- internals -----------------------------------------------------------
    def _plan_mutation(
        self, task: TaskSpec
    ) -> tuple[str, str, dict[str, Any] | None]:
        t = task.target
        collection = t.locator.get("collection", t.entity)
        record_id = t.locator.get("record_id", t.entity_id or "")

        types = {pc.type for pc in task.expected_postconditions}
        if PostconditionType.NOT_EXISTS in types:
            return "DELETE", f"/api/{collection}/{record_id}", None

        if PostconditionType.EXISTS in types:
            payload = self._create_payload(task)
            body = {"collection": collection, "record_id": record_id, "fields": payload}
            return "POST", f"/api/{collection}", body

        fields = self._update_fields(task)
        return "PUT", f"/api/{collection}/{record_id}", {"fields": fields}

    @staticmethod
    def _update_fields(task: TaskSpec) -> dict[str, Any]:
        fields: dict[str, Any] = {}
        for pc in task.expected_postconditions:
            if pc.field is not None and pc.type in (
                PostconditionType.FIELD_EQUALS,
                PostconditionType.FIELD_MATCHES,
                PostconditionType.STATE_TRANSITION,
            ):
                fields[pc.field] = pc.expected
        # Action payloads override/extend derived fields.
        for action in task.actions:
            if action.payload:
                fields.update(action.payload)
        return fields

    @staticmethod
    def _create_payload(task: TaskSpec) -> dict[str, Any]:
        for action in task.actions:
            if action.payload:
                return dict(action.payload)
        return ScriptedHttpAdapter._update_fields(task)

    async def _request(
        self, method: str, path: str, body: dict[str, Any] | None
    ) -> httpx.Response:
        if self._client is not None:
            return await self._client.request(method, path, json=body)
        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout_s) as c:
            return await c.request(method, path, json=body)


def _safe_json(resp: httpx.Response) -> Any:
    try:
        return resp.json()
    except Exception:  # noqa: BLE001 - non-JSON body; fall back to truncated text
        return resp.text[:500]


def _target_key(target: TargetRef) -> str:
    collection = target.locator.get("collection", target.entity)
    record_id = target.locator.get("record_id", target.entity_id or "")
    return f"{collection}/{record_id}"
