"""LLMClient — the provider boundary for the LLM-driven agent.

The ``LLMAgentAdapter`` owns the agentic loop (call model → execute tool calls
against the app → feed results back). Everything model-specific lives behind
``LLMClient.complete``, which takes a neutral transcript + tool schemas and
returns the next assistant turn. This mirrors the PageDriver / SemanticJudge
pattern already in the codebase: one interface, a deterministic keyless default
for tests and CI, and a real backend that plugs in unchanged.

Two implementations:
  * ``MockLLMClient`` — deterministic, keyless. Driven by a *policy* callable so
    the adapter's loop can be exercised with zero API access and no skipped
    tests. The bundled ``naive_update_policy`` models the agent AOIE exists to
    check: it performs the mutation, then trusts the tool's (optimistic) result
    and reports success — producing false completions AOIE catches.
  * ``AnthropicLLMClient`` — a real Claude backend (Messages API tool use),
    lazily imported so the package stays importable without the ``anthropic``
    SDK. Model defaults to ``claude-opus-5``.

The neutral transcript is a list of dicts:
  {"role": "user", "text": str}
  {"role": "assistant", "text": str, "tool_calls": [LLMToolCall, ...]}
  {"role": "tool", "tool_call_id": str, "name": str, "result": Any}
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

Transcript = list[dict[str, Any]]


@dataclass
class LLMToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMTurn:
    text: str = ""
    tool_calls: list[LLMToolCall] = field(default_factory=list)
    stop_reason: str = "end_turn"  # "tool_use" | "end_turn" | ...
    # Opaque provider-native content for faithful replay (e.g. Anthropic content
    # blocks, including thinking blocks that must be echoed back unchanged on the
    # same model). Ignored by provider-neutral consumers like the mock client.
    raw: Any = None


@runtime_checkable
class LLMClient(Protocol):
    name: str

    async def complete(
        self, *, system: str, transcript: Transcript, tools: list[dict[str, Any]]
    ) -> LLMTurn: ...


# --- deterministic, keyless backend -----------------------------------------

Policy = Callable[[Transcript, list[dict[str, Any]]], LLMTurn]


class MockLLMClient:
    """A keyless LLM stand-in whose behaviour is a deterministic ``policy``."""

    name = "mock-llm"

    def __init__(self, policy: Policy) -> None:
        self._policy = policy
        self._counter = 0

    async def complete(
        self, *, system: str, transcript: Transcript, tools: list[dict[str, Any]]
    ) -> LLMTurn:
        self._counter += 1
        return self._policy(transcript, tools)


def _goal_from_transcript(transcript: Transcript) -> dict[str, Any]:
    """Recover the structured goal the adapter embedded in the first user turn.

    The adapter serialises the task into the opening user message (as any agent
    prompt does); a real model reads the prose, this policy reads the JSON block.
    """
    for entry in transcript:
        if entry.get("role") == "user":
            text = entry.get("text", "")
            start = text.find("```json")
            if start != -1:
                body = text[start + len("```json") : text.find("```", start + 7)]
                try:
                    return json.loads(body)
                except json.JSONDecodeError:
                    return {}
    return {}


def _last_tool_result(transcript: Transcript, name: str) -> Any:
    for entry in reversed(transcript):
        if entry.get("role") == "tool" and entry.get("name") == name:
            return entry.get("result")
    return None


def naive_update_policy(transcript: Transcript, tools: list[dict[str, Any]]) -> LLMTurn:
    """Model a UI/response-trusting agent: set the fields, then believe the result.

    Turn 1 (no tool run yet): call ``set_fields`` with the desired fields.
    Turn 2 (after the result): call ``finish`` with success taken from whether
    the mutation *appeared* to succeed — exactly the naive inference that yields
    a false completion when the backend silently failed behind an optimistic 200.
    """
    result = _last_tool_result(transcript, "set_fields")
    if result is None:
        goal = _goal_from_transcript(transcript)
        target = goal.get("target", {})
        return LLMTurn(
            stop_reason="tool_use",
            tool_calls=[
                LLMToolCall(
                    id="call_set",
                    name="set_fields",
                    arguments={
                        "collection": target.get("collection", ""),
                        "record_id": target.get("record_id", ""),
                        "fields": goal.get("desired_fields", {}),
                    },
                )
            ],
        )
    ok = bool(isinstance(result, dict) and result.get("ok", False))
    return LLMTurn(
        stop_reason="tool_use",
        tool_calls=[
            LLMToolCall(
                id="call_finish",
                name="finish",
                arguments={
                    "success": ok,
                    "message": "Saved." if ok else "The update did not go through.",
                },
            )
        ],
    )


# --- real Anthropic backend -------------------------------------------------


class AnthropicLLMClient:
    """Real Claude backend via the Messages API tool-use surface.

    Lazily imports ``anthropic`` so importing this module never requires the SDK.
    Install with ``pip install -e ".[llm]"`` and provide credentials
    (``ANTHROPIC_API_KEY`` or an ``ant auth login`` profile).
    """

    name = "anthropic-llm"

    def __init__(self, model: str = "claude-opus-5", *, max_tokens: int = 4096) -> None:
        self.model = model
        self.max_tokens = max_tokens
        self._client: Any = None

    def _ensure_client(self) -> Any:
        if self._client is None:
            try:
                import anthropic
            except ImportError as exc:  # pragma: no cover - only without the extra
                raise RuntimeError(
                    'anthropic SDK not installed. Install with: pip install -e ".[llm]"'
                ) from exc
            self._client = anthropic.AsyncAnthropic()
        return self._client

    async def complete(
        self, *, system: str, transcript: Transcript, tools: list[dict[str, Any]]
    ) -> LLMTurn:  # pragma: no cover - requires network + credentials
        client = self._ensure_client()
        messages = _to_anthropic_messages(transcript)
        response = await client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            tools=tools,
            messages=messages,
        )
        text_parts: list[str] = []
        tool_calls: list[LLMToolCall] = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(
                    LLMToolCall(id=block.id, name=block.name, arguments=dict(block.input))
                )
        return LLMTurn(
            text="".join(text_parts),
            tool_calls=tool_calls,
            stop_reason=response.stop_reason or "end_turn",
            raw=response.content,  # echo back verbatim (preserves thinking blocks)
        )


def _to_anthropic_messages(transcript: Transcript) -> list[dict[str, Any]]:
    """Translate the neutral transcript into Anthropic message blocks."""
    messages: list[dict[str, Any]] = []
    for entry in transcript:
        role = entry.get("role")
        if role == "user":
            messages.append({"role": "user", "content": entry.get("text", "")})
        elif role == "assistant":
            # Prefer the provider-native content for exact replay (keeps thinking
            # blocks in place, as the API requires on the same model).
            if entry.get("raw") is not None:
                messages.append({"role": "assistant", "content": entry["raw"]})
                continue
            content: list[dict[str, Any]] = []
            if entry.get("text"):
                content.append({"type": "text", "text": entry["text"]})
            for call in entry.get("tool_calls", []):
                content.append(
                    {"type": "tool_use", "id": call.id, "name": call.name, "input": call.arguments}
                )
            messages.append({"role": "assistant", "content": content})
        elif role == "tool":
            messages.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": entry.get("tool_call_id", ""),
                            "content": json.dumps(entry.get("result")),
                        }
                    ],
                }
            )
    return messages
