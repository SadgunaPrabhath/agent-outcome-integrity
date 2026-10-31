"""Evidence model — the explainable record behind every verification decision.

Evidence answers "why did AOIE decide this?". It is content-addressed (the id is
a hash of the canonical payload) so the store is tamper-evident and naturally
deduplicated. Redaction is expected to have already run before an Evidence is
constructed for persistence.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, computed_field

from engine.models.enums import VerifierType


def _now() -> datetime:
    return datetime.now(UTC)


def content_hash(payload: dict[str, Any]) -> str:
    """Stable SHA-256 over a canonical JSON encoding of ``payload``.

    ``default=str`` keeps non-JSON-native values (datetimes, enums) hashable
    without throwing, so evidence can always be sealed.
    """
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class Evidence(BaseModel):
    verifier_type: VerifierType
    source: str
    expected_state: Any = None
    observed_state: Any = None
    comparison: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(..., ge=0.0, le=1.0)

    # Optional provenance pointers — populated by whichever verifier applies.
    request_id: str | None = None
    network_event_id: str | None = None
    screenshot_path: str | None = None
    api_response: dict[str, Any] | None = None
    db_record: dict[str, Any] | None = None
    dom_selector: str | None = None

    redacted: bool = False
    created_at: datetime = Field(default_factory=_now)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def id(self) -> str:
        """Content address. Two evidences with identical payloads share an id.

        Exposed as a computed field so it is serialized into JSON/DB rows and
        can be persisted as the primary key / integrity hash without a second
        wrapper type. Excludes ``created_at`` and the computed fields themselves
        so the hash is stable for identical content produced at different times.
        """
        payload = self.model_dump(exclude={"created_at", "id", "content_hash"})
        return content_hash(payload)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def content_hash(self) -> str:
        return self.id
