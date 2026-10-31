"""Secret redaction for traces and evidence.

AOIE records a lot of state (requests, responses, DB records) as evidence. This
module scrubs credentials and obvious PII *before* anything is persisted, so the
audit trail never becomes a secrets leak (Section 24).

Two layers:
  * key-based: any mapping key that looks sensitive has its value replaced.
  * value-based: token-shaped substrings in free text are masked.

Redaction is total and side-effect-free: it returns a new structure and never
raises on unexpected input.
"""

from __future__ import annotations

import re
from typing import Any

REDACTED = "***REDACTED***"

# Substrings that, if present in a key, mark its value as sensitive.
_SENSITIVE_KEY_PARTS = (
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "access_key",
    "private_key",
    "authorization",
    "auth",
    "cookie",
    "session",
    "cvv",
    "ssn",
    "card_number",
    "credit_card",
)

# Token-shaped values in free text (bearer tokens, provider keys, long hex/JWT).
_VALUE_PATTERNS = (
    re.compile(r"Bearer\s+[A-Za-z0-9\-._~+/]+=*", re.IGNORECASE),
    re.compile(r"\b(?:sk|pk|rk)-[A-Za-z0-9]{16,}\b"),  # provider-style keys
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),  # JWT
)


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return any(part in lowered for part in _SENSITIVE_KEY_PARTS)


def redact_text(text: str) -> str:
    for pattern in _VALUE_PATTERNS:
        text = pattern.sub(REDACTED, text)
    return text


def redact(value: Any) -> Any:
    """Return a redacted copy of ``value`` (dict/list/str/scalar)."""
    if isinstance(value, dict):
        return {
            k: (REDACTED if isinstance(k, str) and _is_sensitive_key(k) else redact(v))
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact(v) for v in value]
    if isinstance(value, str):
        return redact_text(value)
    return value
