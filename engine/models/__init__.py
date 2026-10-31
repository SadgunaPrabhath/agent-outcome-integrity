"""Public model surface for the AOIE engine.

Import from ``engine.models`` rather than the submodules so downstream code is
insulated from internal reorganization.
"""

from engine.models.enums import (
    FailureClass,
    Idempotency,
    MatchMode,
    Outcome,
    PostconditionType,
    RecoveryStrategy,
    RunState,
    VerdictStatus,
    VerifierStatus,
    VerifierType,
)
from engine.models.evidence import Evidence, content_hash
from engine.models.observation import Observation
from engine.models.outcome import AgentClaim, TaskOutcome
from engine.models.postcondition import MatcherConfig, Postcondition, TemporalSpec
from engine.models.recovery import (
    NoRecovery,
    RecoveryAttempt,
    RecoveryHistory,
    RecoveryPlan,
)
from engine.models.task import (
    ActionHint,
    Precondition,
    RecoveryPolicyConfig,
    TargetRef,
    TaskSpec,
)
from engine.models.trace import ExecutionTrace, TraceEvent
from engine.models.verification import ReconciledVerdict, VerifierResult

__all__ = [
    # enums
    "FailureClass",
    "Idempotency",
    "MatchMode",
    "Outcome",
    "PostconditionType",
    "RecoveryStrategy",
    "RunState",
    "VerdictStatus",
    "VerifierStatus",
    "VerifierType",
    # evidence
    "Evidence",
    "content_hash",
    # observation
    "Observation",
    # outcome
    "AgentClaim",
    "TaskOutcome",
    # postcondition
    "MatcherConfig",
    "Postcondition",
    "TemporalSpec",
    # recovery
    "NoRecovery",
    "RecoveryAttempt",
    "RecoveryHistory",
    "RecoveryPlan",
    # task
    "ActionHint",
    "Precondition",
    "RecoveryPolicyConfig",
    "TargetRef",
    "TaskSpec",
    # trace
    "ExecutionTrace",
    "TraceEvent",
    # verification
    "ReconciledVerdict",
    "VerifierResult",
]
