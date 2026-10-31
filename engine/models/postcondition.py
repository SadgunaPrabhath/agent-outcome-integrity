"""Postcondition model — typed predicates over persistent state.

A postcondition is the machine-checkable statement of *what must be true in the
world* after the agent acts. It is deliberately structured (not prose) so that
verification can be deterministic. Prose only appears in ``SEMANTIC`` types,
which are the escape hatch of last resort.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field, model_validator

from engine.models.enums import MatchMode, PostconditionType, VerifierType


class MatcherConfig(BaseModel):
    """How an observed value is compared to the expected value."""

    mode: MatchMode = MatchMode.EXACT
    tolerance: float = 0.0  # only for NUMERIC_TOLERANCE
    case_sensitive: bool = True  # only meaningful for EXACT

    def matches(self, expected: Any, observed: Any) -> bool:
        """Return True iff ``observed`` satisfies ``expected`` under this mode.

        Kept dependency-free and total: any comparison error is a non-match,
        never an exception, so a malformed observation degrades to FAIL rather
        than crashing verification.
        """
        try:
            if self.mode is MatchMode.EXACT:
                if isinstance(expected, str) and isinstance(observed, str) and not self.case_sensitive:
                    return expected.casefold() == observed.casefold()
                return expected == observed

            if self.mode is MatchMode.NORMALIZED:
                return _normalize(expected) == _normalize(observed)

            if self.mode is MatchMode.REGEX:
                if observed is None:
                    return False
                return re.fullmatch(str(expected), str(observed)) is not None

            if self.mode is MatchMode.NUMERIC_TOLERANCE:
                return abs(float(expected) - float(observed)) <= self.tolerance
        except (TypeError, ValueError, re.error):
            return False
        return False


def _normalize(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value)).strip().casefold()


class TemporalSpec(BaseModel):
    """Temporal qualifier for a postcondition.

    Exactly one intent applies:
      * ``must_hold_s``  — the predicate must stay true for this many seconds.
      * ``within_s``     — the predicate must become true within this many seconds.
    ``poll_interval_s`` controls how often the engine samples state.
    """

    must_hold_s: float | None = None
    within_s: float | None = None
    poll_interval_s: float = 1.0

    @model_validator(mode="after")
    def _exactly_one_intent(self) -> TemporalSpec:
        if (self.must_hold_s is None) == (self.within_s is None):
            raise ValueError("TemporalSpec requires exactly one of must_hold_s / within_s")
        return self


class Postcondition(BaseModel):
    """A single checkable predicate over persistent state."""

    ref: str = Field(..., description="Stable id used to correlate results/evidence")
    type: PostconditionType
    entity: str = Field(..., description="Logical entity, e.g. 'user_profile'")
    field: str | None = None
    expected: Any = None
    matcher: MatcherConfig = Field(default_factory=MatcherConfig)
    temporal: TemporalSpec | None = None
    weight: float = Field(1.0, gt=0, description="Contribution to PARTIAL scoring")
    verification_methods: list[VerifierType] = Field(
        default_factory=list,
        description="Preferred verifiers, most-authoritative first. Empty = engine chooses.",
    )

    @model_validator(mode="after")
    def _shape_matches_type(self) -> Postcondition:
        needs_field = {
            PostconditionType.FIELD_EQUALS,
            PostconditionType.FIELD_MATCHES,
            PostconditionType.STATE_TRANSITION,
        }
        if self.type in needs_field and not self.field:
            raise ValueError(f"postcondition type {self.type} requires 'field'")
        if self.type is PostconditionType.COUNT_EQUALS and not isinstance(self.expected, int):
            raise ValueError("count_equals requires an integer 'expected'")
        if self.type is PostconditionType.VISUAL_MATCH:
            ref = self.expected
            has_ref = isinstance(ref, str) and ref or (
                isinstance(ref, dict) and (ref.get("ahash") or ref.get("hash"))
            )
            if not has_ref:
                raise ValueError(
                    "visual_match requires a reference aHash in 'expected' "
                    "(a hex string or {'ahash': ...})"
                )
        return self
