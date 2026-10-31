"""LLMAgentAdapter loop tests against a keyless MockLLMClient (no network)."""

from __future__ import annotations

import httpx
import pytest

from adapters.llm import LLMAgentAdapter, LLMToolCall, LLMTurn, MockLLMClient
from adapters.llm.client import naive_update_policy
from engine.execution.context import RunContext
from engine.models import Postcondition, PostconditionType, TargetRef, TaskSpec

BASE_URL = "http://testserver"


def _echo_app() -> httpx.ASGITransport:
    """A tiny ASGI app: PUT echoes an optimistic 200, GET returns a view."""

    async def app(scope, receive, send):
        assert scope["type"] == "http"
        # Read (and discard) the body.
        while True:
            msg = await receive()
            if not msg.get("more_body", False):
                break
        status = 200
        body = b'{"ok": true}'
        await send({"type": "http.response.start", "status": status,
                    "headers": [(b"content-type", b"application/json")]})
        await send({"type": "http.response.body", "body": body})

    return httpx.ASGITransport(app=app)


def _update_task() -> TaskSpec:
    return TaskSpec(
        task_id="t", description="set name to Alice",
        target=TargetRef(entity="profiles", entity_id="1",
                         locator={"collection": "profiles", "record_id": "1"}),
        expected_postconditions=[
            Postcondition(ref="name", type=PostconditionType.FIELD_EQUALS,
                          entity="profiles", field="name", expected="Alice")
        ],
    )


@pytest.mark.asyncio
async def test_naive_policy_runs_loop_and_claims_success():
    async with httpx.AsyncClient(transport=_echo_app(), base_url=BASE_URL) as http:
        adapter = LLMAgentAdapter(
            MockLLMClient(naive_update_policy), base_url=BASE_URL, http_client=http
        )
        ctx = RunContext(task=_update_task())
        await adapter.initialize(ctx)
        result = await adapter.execute(ctx.task)
    assert result.claim.claimed_success is True
    # It called set_fields then finish, and recorded a network event.
    names = [e.name for e in result.events]
    assert "tool:set_fields" in names
    assert any(e.kind == "network" for e in result.events)


@pytest.mark.asyncio
async def test_policy_claims_failure_when_write_rejected():
    async def reject_app(scope, receive, send):
        while True:
            msg = await receive()
            if not msg.get("more_body", False):
                break
        await send({"type": "http.response.start", "status": 401, "headers": []})
        await send({"type": "http.response.body", "body": b"no"})

    transport = httpx.ASGITransport(app=reject_app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as http:
        adapter = LLMAgentAdapter(
            MockLLMClient(naive_update_policy), base_url=BASE_URL, http_client=http
        )
        result = await adapter.execute(_update_task())
    assert result.claim.claimed_success is False


@pytest.mark.asyncio
async def test_unsupported_task_shape_claims_failure():
    task = TaskSpec(
        task_id="del", description="delete it",
        target=TargetRef(entity="profiles", entity_id="1"),
        expected_postconditions=[
            Postcondition(ref="gone", type=PostconditionType.NOT_EXISTS, entity="profiles")
        ],
    )
    adapter = LLMAgentAdapter(MockLLMClient(naive_update_policy), base_url=BASE_URL)
    result = await adapter.execute(task)
    assert result.claim.claimed_success is False
    assert "field updates only" in (result.error or "")


@pytest.mark.asyncio
async def test_loop_stops_when_model_never_finishes():
    """A model that only ever emits text (never a tool call) must not hang or
    falsely claim success — the adapter concludes not-success after one turn."""
    def chatty_policy(transcript, tools):
        return LLMTurn(text="thinking about it...", stop_reason="end_turn")

    adapter = LLMAgentAdapter(MockLLMClient(chatty_policy), base_url=BASE_URL)
    result = await adapter.execute(_update_task())
    assert result.claim.claimed_success is False


@pytest.mark.asyncio
async def test_turn_budget_is_bounded():
    """A model that keeps calling get_state forever is cut off at max_turns and
    concludes not-success rather than looping unboundedly."""
    def stalling_policy(transcript, tools):
        return LLMTurn(
            stop_reason="tool_use",
            tool_calls=[LLMToolCall(id="c", name="get_state",
                                    arguments={"collection": "profiles", "record_id": "1"})],
        )

    async with httpx.AsyncClient(transport=_echo_app(), base_url=BASE_URL) as http:
        adapter = LLMAgentAdapter(
            MockLLMClient(stalling_policy), base_url=BASE_URL, http_client=http, max_turns=3
        )
        result = await adapter.execute(_update_task())
    assert result.claim.claimed_success is False
    assert "turn budget" in result.claim.message
    # Exactly max_turns model calls were made.
    assert sum(e.name == "llm_turn" for e in result.events) == 3
