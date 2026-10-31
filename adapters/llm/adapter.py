"""LLMAgentAdapter — an LLM tool-using agent AOIE can wrap and verify.

The agent is given a goal and a small tool surface (``set_fields``,
``get_state``, ``finish``) and runs an agentic loop: the model proposes tool
calls, the adapter executes them against the app, feeds the results back, and the
model eventually calls ``finish`` with its own success claim. AOIE never trusts
that claim — it verifies the persistent state independently. When the model
performs the mutation, sees an optimistic 200 (or the optimistic ``/ui`` view),
and reports success even though the backend never changed, that is exactly the
false completion AOIE is built to catch — now via a real tool-using agent.

The loop is model-agnostic: inject a keyless :class:`MockLLMClient` for tests and
CI, or an :class:`AnthropicLLMClient` for a real Claude agent. Nothing else
changes.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from adapters.base import AdapterResult, AgentAdapter
from adapters.llm.client import LLMClient, LLMToolCall
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

_SYSTEM = (
    "You are an agent that changes application state to satisfy the user's goal. "
    "Use the provided tools: call set_fields to write the requested values, and "
    "you may call get_state to inspect the current view. When you believe the "
    "goal is achieved, call finish with success=true; if you could not achieve "
    "it, call finish with success=false. Only conclude from what the tools return."
)

_TOOLS: list[dict[str, Any]] = [
    {
        "name": "set_fields",
        "description": "Write field values to a record. Returns the write result.",
        "input_schema": {
            "type": "object",
            "properties": {
                "collection": {"type": "string"},
                "record_id": {"type": "string"},
                "fields": {"type": "object"},
            },
            "required": ["collection", "record_id", "fields"],
        },
    },
    {
        "name": "get_state",
        "description": "Read the current (as-shown) state of a record.",
        "input_schema": {
            "type": "object",
            "properties": {
                "collection": {"type": "string"},
                "record_id": {"type": "string"},
            },
            "required": ["collection", "record_id"],
        },
    },
    {
        "name": "finish",
        "description": "Conclude the task with a success flag and a short message.",
        "input_schema": {
            "type": "object",
            "properties": {
                "success": {"type": "boolean"},
                "message": {"type": "string"},
            },
            "required": ["success"],
        },
    },
]


class LLMAgentAdapter(AgentAdapter):
    name = "llm-agent"

    def __init__(
        self,
        client: LLMClient,
        *,
        base_url: str = "http://testserver",
        http_client: httpx.AsyncClient | None = None,
        max_turns: int = 6,
    ) -> None:
        self.client = client
        self.base_url = base_url.rstrip("/")
        self._http = http_client
        self.max_turns = max_turns
        self._events: list[TraceEvent] = []

    async def initialize(self, ctx: RunContext) -> None:
        self._events.append(TraceEvent(kind="agent.action", name="initialize"))

    async def execute(self, task: TaskSpec) -> AdapterResult:
        goal = self._goal(task)
        if not goal["desired_fields"]:
            msg = "no typeable field postcondition; LLMAgentAdapter drives field updates only"
            return AdapterResult(
                claim=AgentClaim(claimed_success=False, message=msg),
                events=list(self._events),
                error=msg,
            )

        transcript: list[dict[str, Any]] = [{"role": "user", "text": _user_prompt(goal)}]
        events: list[TraceEvent] = []
        claim: AgentClaim | None = None

        for _ in range(self.max_turns):
            turn = await self.client.complete(
                system=_SYSTEM, transcript=transcript, tools=_TOOLS
            )
            transcript.append(
                {"role": "assistant", "text": turn.text, "tool_calls": turn.tool_calls,
                 "raw": turn.raw}
            )
            events.append(
                TraceEvent(
                    kind="agent.action",
                    name="llm_turn",
                    attributes={
                        "text": turn.text,
                        "tool_calls": [c.name for c in turn.tool_calls],
                        "stop_reason": turn.stop_reason,
                    },
                )
            )
            if not turn.tool_calls:
                break  # model ended without concluding via finish

            done = False
            for call in turn.tool_calls:
                if call.name == "finish":
                    claim = AgentClaim(
                        claimed_success=bool(call.arguments.get("success", False)),
                        message=str(call.arguments.get("message", "")),
                    )
                    transcript.append(
                        {"role": "tool", "tool_call_id": call.id, "name": "finish",
                         "result": {"acknowledged": True}}
                    )
                    done = True
                    continue
                result = await self._run_tool(call, events)
                transcript.append(
                    {"role": "tool", "tool_call_id": call.id, "name": call.name, "result": result}
                )
            if done:
                break

        self._events.extend(events)
        if claim is None:
            claim = AgentClaim(
                claimed_success=False, message="agent did not conclude within the turn budget"
            )
        return AdapterResult(claim=claim, events=events)

    def get_trace(self) -> list[TraceEvent]:
        return list(self._events)

    # --- tool execution ------------------------------------------------------
    async def _run_tool(self, call: LLMToolCall, events: list[TraceEvent]) -> dict[str, Any]:
        events.append(
            TraceEvent(kind="agent.action", name=f"tool:{call.name}", attributes=dict(call.arguments))
        )
        args = call.arguments
        if call.name == "set_fields":
            return await self._http_json(
                "PUT",
                f"/api/{args.get('collection')}/{args.get('record_id')}",
                {"fields": args.get("fields", {})},
                events,
            )
        if call.name == "get_state":
            return await self._http_json(
                "GET", f"/ui/{args.get('collection')}/{args.get('record_id')}", None, events
            )
        return {"ok": False, "error": f"unknown tool {call.name}"}

    async def _http_json(
        self, method: str, path: str, body: dict[str, Any] | None, events: list[TraceEvent]
    ) -> dict[str, Any]:
        try:
            resp = await self._request(method, path, body)
        except httpx.HTTPError as exc:
            events.append(TraceEvent(kind="network", name="error", attributes={"error": str(exc)}))
            return {"ok": False, "error": str(exc)}
        events.append(
            TraceEvent(
                kind="network",
                name=f"{method} {path}",
                attributes={"status": resp.status_code, "body": resp.text[:500]},
            )
        )
        return {"ok": resp.is_success, "status": resp.status_code, "response": _safe_json(resp)}

    async def _request(
        self, method: str, path: str, body: dict[str, Any] | None
    ) -> httpx.Response:
        if self._http is not None:
            return await self._http.request(method, path, json=body)
        async with httpx.AsyncClient(base_url=self.base_url, timeout=5.0) as c:
            return await c.request(method, path, json=body)

    # --- planning ------------------------------------------------------------
    def _goal(self, task: TaskSpec) -> dict[str, Any]:
        target = task.target
        collection = target.locator.get("collection", target.entity)
        record_id = target.locator.get("record_id", target.entity_id or "")
        desired: dict[str, Any] = {}
        for pc in task.expected_postconditions:
            if pc.field and pc.type in _TYPEABLE:
                desired[pc.field] = pc.expected
        for action in task.actions:
            if action.payload:
                desired.update({k: v for k, v in action.payload.items()})
        return {
            "description": task.description,
            "target": {"collection": collection, "record_id": record_id},
            "desired_fields": desired,
        }


def _user_prompt(goal: dict[str, Any]) -> str:
    return (
        f"Goal: {goal['description']}\n\n"
        "Achieve this state, then call finish. Details:\n"
        f"```json\n{json.dumps({k: goal[k] for k in ('target', 'desired_fields')})}\n```"
    )


def _safe_json(resp: httpx.Response) -> Any:
    try:
        return resp.json()
    except Exception:  # noqa: BLE001 - non-JSON body; fall back to truncated text
        return resp.text[:500]
