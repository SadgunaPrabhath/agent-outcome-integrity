"""Reusable test doubles.

``FakeAdapter`` is a controllable agent: it reports whatever claim you give it
and, on each execute (including recovery re-executes), runs an optional callback
so a test can mutate the registered sources — simulating a real agent finally
succeeding on retry.
"""

from __future__ import annotations

from collections.abc import Callable

from adapters.base import AdapterResult, AgentAdapter
from engine.execution.context import RunContext
from engine.models import AgentClaim, TaskSpec, TraceEvent


class FakeAdapter(AgentAdapter):
    name = "fake"

    def __init__(
        self,
        claim_success: bool = True,
        on_execute: Callable[[int], None] | None = None,
        message: str | None = None,
    ) -> None:
        self._claim_success = claim_success
        self._on_execute = on_execute
        self._message = message
        self._events: list[TraceEvent] = []
        self.execute_count = 0

    async def initialize(self, ctx: RunContext) -> None:
        self._events.append(TraceEvent(kind="agent.action", name="initialize"))

    async def execute(self, task: TaskSpec) -> AdapterResult:
        self.execute_count += 1
        if self._on_execute is not None:
            self._on_execute(self.execute_count)
        event = TraceEvent(
            kind="agent.action", name="execute", attributes={"n": self.execute_count}
        )
        self._events.append(event)
        return AdapterResult(
            claim=AgentClaim(claimed_success=self._claim_success, message=self._message),
            events=[event],
        )

    def get_trace(self) -> list[TraceEvent]:
        return list(self._events)
