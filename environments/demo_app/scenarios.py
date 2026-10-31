"""Failure-injection scenarios for the demo app.

Each scenario is a *deterministic, reproducible* way to make the world diverge
from what a naive agent would conclude from a 200 OK. They map directly onto the
AOIE failure taxonomy so the benchmark can assert that AOIE classifies each one
correctly.
"""

from __future__ import annotations

from enum import Enum


class Scenario(str, Enum):
    NONE = "none"
    # UI/response says success; the backend never persisted the change.
    FAIL_BACKEND_WRITE = "fail_backend_write"
    # A value IS persisted, but a wrong/mangled one.
    WRONG_VALUE = "wrong_value"
    # The write lands on a different record than the target.
    WRONG_TARGET = "wrong_target"
    # The mutation is rejected (401); nothing changes.
    AUTH_FAILURE = "auth_failure"
    # The handler stalls past the client/agent timeout.
    TIMEOUT = "timeout"
    # The write persists, but authoritative reads return a stale (pre-write) value.
    STALE_READ = "stale_read"
    # The FIRST mutation silently fails to persist; later attempts succeed. This
    # is the recoverable case — a retry heals it — so it exercises recovery.
    TRANSIENT_BACKEND_WRITE = "transient_backend_write"
