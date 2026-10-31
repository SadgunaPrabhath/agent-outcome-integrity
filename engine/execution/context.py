"""RunContext and StateSource — the plumbing shared by adapters and verifiers.

``RunContext`` is the per-run bundle threaded through the FSM. It carries the
task, the trace, and a registry of ``StateSource`` backends keyed by verifier
type. Verifiers *read* persistent state exclusively through these sources, which
is what makes verification independent of the agent: the agent drives the app,
the sources read the ground truth.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from engine.models import (
    ExecutionTrace,
    Observation,
    Postcondition,
    TargetRef,
    TaskSpec,
    VerifierType,
)


class StateSource(ABC):
    """Reads persistent state for one verification channel (api/db/dom/...).

    A StateSource is an *observer*: it captures state, it does not judge. It must
    never raise for an ordinary "could not read" condition — it returns an
    ``Observation`` with ``error`` set, so verification degrades gracefully.
    """

    verifier_type: VerifierType

    @abstractmethod
    async def read(self, pc: Postcondition, target: TargetRef) -> Observation:
        """Return the current observed state relevant to ``pc``."""
        raise NotImplementedError

    async def close(self) -> None:
        """Release any resources. Default no-op."""


@dataclass
class RunContext:
    task: TaskSpec
    run_id: str = field(default_factory=lambda: "run_" + uuid.uuid4().hex[:12])
    trace: ExecutionTrace | None = None
    sources: dict[VerifierType, StateSource] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.trace is None:
            self.trace = ExecutionTrace(run_id=self.run_id)

    def register_source(self, source: StateSource) -> None:
        self.sources[source.verifier_type] = source

    def available_methods(self) -> list[VerifierType]:
        return sorted(self.sources.keys(), key=lambda v: v.priority)
