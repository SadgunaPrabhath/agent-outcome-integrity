"""Observation model — normalized raw state captured from a source.

Observers *capture*; they do not judge. An Observation is the neutral record of
"what a source reported at time T". Verifiers consume Observations (or query
sources directly) and produce judgments. Keeping the two separate lets one
observation feed several verifiers and keeps the audit trail honest.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from engine.models.enums import VerifierType


def _now() -> datetime:
    return datetime.now(UTC)


class Observation(BaseModel):
    observer_type: VerifierType  # which kind of source produced it
    source: str  # concrete source, e.g. "GET /api/profile" or "db:users#42"
    state: dict[str, Any] = Field(default_factory=dict)
    captured_at: datetime = Field(default_factory=_now)
    redacted: bool = False
    error: str | None = None  # set if the observer failed to read the source

    @property
    def ok(self) -> bool:
        return self.error is None
