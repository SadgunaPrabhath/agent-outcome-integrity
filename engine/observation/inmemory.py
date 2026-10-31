"""InMemoryStateSource — a controllable StateSource for tests and demos.

It stands in for any real source (API/DB/DOM) by returning a fixed state dict.
Because AOIE's whole thesis is about *disagreeing* sources, this source is the
primary tool for constructing those scenarios deterministically: register one
as ``DOM`` reporting "Alice" and another as ``DATABASE`` reporting "Bob" and the
reconciler must produce a CONFLICT.

It can also simulate:
  * a source that fails to read (``error``);
  * state that changes over time (``sequence`` of states, advanced per read) —
    useful for temporal verification (``within_s`` eventual consistency).
"""

from __future__ import annotations

from typing import Any

from engine.execution.context import StateSource
from engine.models import Observation, Postcondition, TargetRef, VerifierType


class InMemoryStateSource(StateSource):
    def __init__(
        self,
        verifier_type: VerifierType,
        state: dict[str, Any] | None = None,
        *,
        source_name: str | None = None,
        error: str | None = None,
        sequence: list[dict[str, Any]] | None = None,
    ) -> None:
        self.verifier_type = verifier_type
        self._state = dict(state or {})
        self._source_name = source_name or f"inmemory:{verifier_type.value}"
        self._error = error
        self._sequence = list(sequence) if sequence else None
        self._reads = 0

    # --- mutation helpers (let tests/demo flip persistent state) --------------
    def set_field(self, field: str, value: Any) -> None:
        self._state[field] = value

    def set_state(self, state: dict[str, Any]) -> None:
        self._state = dict(state)

    def fail_with(self, error: str | None) -> None:
        self._error = error

    # --- StateSource ---------------------------------------------------------
    async def read(self, pc: Postcondition, target: TargetRef) -> Observation:
        current = self._advance()
        return Observation(
            observer_type=self.verifier_type,
            source=self._source_name,
            state=dict(current),
            error=self._error,
        )

    def _advance(self) -> dict[str, Any]:
        if self._sequence:
            idx = min(self._reads, len(self._sequence) - 1)
            self._reads += 1
            return self._sequence[idx]
        self._reads += 1
        return self._state
