"""Execution trace model — structured, append-only event log for a run.

Designed to be OpenTelemetry-friendly later (span_id / parent_id / timestamps)
without pulling in the OTel SDK now. Every FSM transition, agent action,
observation, verification, and recovery attempt emits a TraceEvent.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


def _now() -> datetime:
    return datetime.now(UTC)


def _span_id() -> str:
    return uuid.uuid4().hex[:16]


class TraceEvent(BaseModel):
    span_id: str = Field(default_factory=_span_id)
    parent_id: str | None = None
    kind: str  # e.g. "fsm.transition", "agent.action", "verify", "recover"
    name: str
    attributes: dict[str, Any] = Field(default_factory=dict)
    ts: datetime = Field(default_factory=_now)


class ExecutionTrace(BaseModel):
    run_id: str
    events: list[TraceEvent] = Field(default_factory=list)

    def add(self, kind: str, name: str, **attributes: Any) -> TraceEvent:
        event = TraceEvent(kind=kind, name=name, attributes=attributes)
        self.events.append(event)
        return event
