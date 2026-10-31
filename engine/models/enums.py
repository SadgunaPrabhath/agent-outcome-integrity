"""Shared enumerations for the AOIE engine.

Everything here is a *stable vocabulary*: outcome states, failure taxonomy,
verifier kinds, recovery strategies. These are referenced across models,
persistence, the API, and the dashboard, so they live in one place and are
kept string-valued (not IntEnum) so they serialize legibly in JSON and DB rows.
"""

from __future__ import annotations

from enum import Enum


class VerifierType(str, Enum):
    """Verification sources, ordered from most to least deterministic.

    The engine prefers lower-cost, higher-determinism verifiers first (Section 3
    of the design). ``priority`` encodes that ordering; it is *not* a confidence
    value — confidence describes evidence quality per result.
    """

    API = "api"
    DATABASE = "database"
    NETWORK = "network"
    DOM = "dom"
    VISUAL = "visual"
    SEMANTIC = "semantic"

    @property
    def priority(self) -> int:
        """Lower number = more authoritative source. Used for tie-breaking."""
        return {
            VerifierType.DATABASE: 0,
            VerifierType.API: 1,
            VerifierType.NETWORK: 2,
            VerifierType.DOM: 3,
            VerifierType.VISUAL: 4,
            VerifierType.SEMANTIC: 5,
        }[self]

    @property
    def is_deterministic(self) -> bool:
        return self in (
            VerifierType.DATABASE,
            VerifierType.API,
            VerifierType.NETWORK,
            VerifierType.DOM,
        )

    @property
    def is_authoritative(self) -> bool:
        """Authoritative sources read persistent/backend ground truth and decide
        the verdict. Presentational sources reflect what was *shown or returned*
        (DOM UI, and NETWORK — a mutation's 200 response, which can be an
        optimistic lie) — useful for detecting false completion, but they must
        not mask or override a clear backend read. DB and a read-back API call
        are the two ground-truth reads, and either can be stale, so they are
        co-equal: when they disagree it is a genuine CONFLICT, not a tie to break.
        """
        return self in (VerifierType.DATABASE, VerifierType.API)


class VerifierStatus(str, Enum):
    """Result of a single verifier against a single postcondition."""

    PASS = "PASS"
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"  # verifier ran but could not decide


class VerdictStatus(str, Enum):
    """Reconciled verdict for a postcondition across multiple verifiers."""

    SATISFIED = "SATISFIED"
    VIOLATED = "VIOLATED"
    CONFLICT = "CONFLICT"  # sources disagree — never silently "success"
    UNKNOWN = "UNKNOWN"  # insufficient evidence


class Outcome(str, Enum):
    """Final task-level outcome. The whole system exists to produce this."""

    VERIFIED = "VERIFIED"
    FAILED = "FAILED"
    PARTIAL = "PARTIAL"
    UNKNOWN = "UNKNOWN"


class FailureClass(str, Enum):
    """Failure taxonomy. Extensible; add members as new patterns are observed."""

    UI_FALSE_COMPLETION = "UI_FALSE_COMPLETION"
    BACKEND_FAILURE = "BACKEND_FAILURE"
    PERSISTENCE_FAILURE = "PERSISTENCE_FAILURE"
    WRONG_TARGET = "WRONG_TARGET"
    WRONG_VALUE = "WRONG_VALUE"
    PARTIAL_EXECUTION = "PARTIAL_EXECUTION"
    AUTH_FAILURE = "AUTH_FAILURE"
    TIMEOUT = "TIMEOUT"
    NETWORK_FAILURE = "NETWORK_FAILURE"
    STALE_STATE = "STALE_STATE"
    EXTERNAL_DEPENDENCY_FAILURE = "EXTERNAL_DEPENDENCY_FAILURE"
    VERIFICATION_FAILURE = "VERIFICATION_FAILURE"  # AOIE itself couldn't verify
    STATE_CONFLICT = "STATE_CONFLICT"


class PostconditionType(str, Enum):
    FIELD_EQUALS = "field_equals"
    FIELD_MATCHES = "field_matches"  # regex / pattern
    EXISTS = "exists"
    NOT_EXISTS = "not_exists"  # e.g. delete tasks
    COUNT_EQUALS = "count_equals"
    STATE_TRANSITION = "state_transition"  # move item between states
    RELATION = "relation"  # multi-entity relationship
    VISUAL_MATCH = "visual_match"  # screenshot perceptually matches a reference
    SEMANTIC = "semantic"  # last resort, LLM-interpreted


class MatchMode(str, Enum):
    EXACT = "exact"
    NORMALIZED = "normalized"  # trim + collapse whitespace + casefold
    REGEX = "regex"
    NUMERIC_TOLERANCE = "numeric_tolerance"


class RecoveryStrategy(str, Enum):
    REFRESH_STATE = "refresh_state"
    RECHECK_AUTH = "recheck_auth"
    RETRY_ACTION = "retry_action"
    RERUN_FAILED_STEP = "rerun_failed_step"
    RERUN_WORKFLOW = "rerun_workflow"
    ESCALATE_HUMAN = "escalate_human"
    MARK_UNRESOLVED = "mark_unresolved"


class Idempotency(str, Enum):
    """Safety classification of an action for recovery decisions."""

    IDEMPOTENT = "idempotent"  # safe to repeat (e.g. set field = X)
    NON_IDEMPOTENT = "non_idempotent"  # unsafe to repeat (e.g. create payment)
    UNKNOWN = "unknown"  # treat as non-idempotent for safety


class RunState(str, Enum):
    """Orchestrator finite-state-machine states."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    OBSERVING = "OBSERVING"
    RECONCILING = "RECONCILING"
    VERIFYING = "VERIFYING"
    CLASSIFIED = "CLASSIFIED"
    RECOVERING = "RECOVERING"
    FINAL = "FINAL"
    ERRORED = "ERRORED"
