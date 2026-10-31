"""AgentAdapter — the boundary between AOIE and any agent implementation.

AOIE never reaches into an agent's internals. It hands the adapter a task, lets
it run, and takes back two things: a trace of what the agent *did*, and the
agent's own *claim* of success. AOIE then verifies the claim independently.

Concrete adapters (scripted, Playwright, LLM-driven, ...) live in sibling
packages. The MVP ships a scripted adapter (deterministic, can be told to
falsely claim success) because measuring verification requires an agent whose
ground-truth behavior we control.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel, Field

from engine.execution.context import RunContext
from engine.models import AgentClaim, TaskSpec, TraceEvent


class AdapterResult(BaseModel):
    """What an adapter returns after executing a task."""

    claim: AgentClaim
    events: list[TraceEvent] = Field(default_factory=list)
    error: str | None = None


class AgentAdapter(ABC):
    """Lifecycle: initialize -> execute -> (get_trace) -> stop -> cleanup."""

    name: str = "base"

    @abstractmethod
    async def initialize(self, ctx: RunContext) -> None:
        """Prepare resources (browser, client, session). Idempotent per run."""

    @abstractmethod
    async def execute(self, task: TaskSpec) -> AdapterResult:
        """Run the task and return the trace plus the agent's success claim."""

    @abstractmethod
    def get_trace(self) -> list[TraceEvent]:
        """Return trace events captured so far (also embedded in AdapterResult)."""

    async def stop(self) -> None:
        """Best-effort halt of in-flight work."""

    async def cleanup(self) -> None:
        """Release resources. Always safe to call."""
