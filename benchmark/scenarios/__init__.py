"""Ground truth for each injected scenario.

For every scenario we record what *actually* happened to persistent state, so the
benchmark can measure AOIE's detection accuracy (not just its raw verdicts). This
ground truth is a property of the demo app's injection logic, defined once here.
"""

from __future__ import annotations

from enum import Enum

from environments.demo_app import Scenario


class GroundTruth(str, Enum):
    SUCCEEDED = "succeeded"  # the requested persistent state was truly achieved
    FAILED = "failed"  # the requested persistent state was NOT achieved


# What really happened to the backend under each scenario.
GROUND_TRUTH: dict[Scenario, GroundTruth] = {
    Scenario.NONE: GroundTruth.SUCCEEDED,
    Scenario.FAIL_BACKEND_WRITE: GroundTruth.FAILED,
    Scenario.WRONG_VALUE: GroundTruth.FAILED,
    Scenario.WRONG_TARGET: GroundTruth.FAILED,
    Scenario.AUTH_FAILURE: GroundTruth.FAILED,
    Scenario.TIMEOUT: GroundTruth.FAILED,
    # State IS correctly persisted; only the authoritative read is stale. AOIE
    # cannot confirm it (sources conflict), which is the honest, safe answer.
    Scenario.STALE_READ: GroundTruth.SUCCEEDED,
    # First write dropped, retry persists: recoverable -> truly succeeds (with recovery).
    Scenario.TRANSIENT_BACKEND_WRITE: GroundTruth.SUCCEEDED,
}
