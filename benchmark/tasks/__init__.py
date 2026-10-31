"""Benchmark task catalog.

Each ``BenchmarkTask`` bundles a TaskSpec factory, the seed record to plant in
the demo app, and the failure scenarios that are meaningful for that task shape.
Reusing the demo app's generic record model keeps all task types on one code
path while still exercising update / create / delete / state-transition flows.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from engine.models import (
    ActionHint,
    Idempotency,
    Postcondition,
    PostconditionType,
    RecoveryPolicyConfig,
    TargetRef,
    TaskSpec,
)
from environments.demo_app import Scenario

# Standard scenario set for value-bearing update tasks.
_UPDATE_SCENARIOS = [
    Scenario.NONE,
    Scenario.FAIL_BACKEND_WRITE,
    Scenario.WRONG_VALUE,
    Scenario.WRONG_TARGET,
    Scenario.AUTH_FAILURE,
    Scenario.TIMEOUT,
    Scenario.STALE_READ,
    Scenario.TRANSIENT_BACKEND_WRITE,
]
_EXISTENCE_SCENARIOS = [
    Scenario.NONE,
    Scenario.FAIL_BACKEND_WRITE,
    Scenario.WRONG_TARGET,
    Scenario.AUTH_FAILURE,
    Scenario.TIMEOUT,
]


@dataclass
class BenchmarkTask:
    task_id: str
    collection: str
    record_id: str
    seed_fields: dict[str, Any] | None  # None => record starts absent (create)
    spec: TaskSpec
    scenarios: list[Scenario] = field(default_factory=lambda: list(_UPDATE_SCENARIOS))


def _target(collection: str, record_id: str) -> TargetRef:
    return TargetRef(
        entity=collection,
        entity_id=record_id,
        locator={"collection": collection, "record_id": record_id},
    )


def _field_task(
    task_id: str,
    collection: str,
    record_id: str,
    field_name: str,
    initial: Any,
    desired: Any,
    *,
    pc_type: PostconditionType = PostconditionType.FIELD_EQUALS,
    max_retries: int = 1,
) -> BenchmarkTask:
    spec = TaskSpec(
        task_id=task_id,
        description=f"Set {collection}/{record_id}.{field_name} = {desired!r}",
        target=_target(collection, record_id),
        actions=[
            ActionHint(step=1, action_type="update", description="set field",
                       idempotency=Idempotency.IDEMPOTENT)
        ],
        expected_postconditions=[
            Postcondition(
                ref=f"{field_name}_eq",
                type=pc_type,
                entity=collection,
                field=field_name,
                expected=desired,
            )
        ],
        timeout_s=1,
        recovery_policy=RecoveryPolicyConfig(max_retries=max_retries),
    )
    return BenchmarkTask(task_id, collection, record_id, {field_name: initial}, spec)


def _create_task(task_id: str, collection: str, record_id: str, payload: dict[str, Any]) -> BenchmarkTask:
    spec = TaskSpec(
        task_id=task_id,
        description=f"Create {collection}/{record_id}",
        target=_target(collection, record_id),
        actions=[
            ActionHint(step=1, action_type="create", description="create record",
                       payload=payload, idempotency=Idempotency.NON_IDEMPOTENT)
        ],
        expected_postconditions=[
            Postcondition(ref="exists", type=PostconditionType.EXISTS, entity=collection)
        ],
        timeout_s=1,
        recovery_policy=RecoveryPolicyConfig(max_retries=1),
    )
    return BenchmarkTask(task_id, collection, record_id, None, spec, list(_EXISTENCE_SCENARIOS))


def _delete_task(task_id: str, collection: str, record_id: str) -> BenchmarkTask:
    spec = TaskSpec(
        task_id=task_id,
        description=f"Delete {collection}/{record_id}",
        target=_target(collection, record_id),
        actions=[
            ActionHint(step=1, action_type="delete", description="delete record",
                       idempotency=Idempotency.IDEMPOTENT)
        ],
        expected_postconditions=[
            Postcondition(ref="absent", type=PostconditionType.NOT_EXISTS, entity=collection)
        ],
        timeout_s=1,
        recovery_policy=RecoveryPolicyConfig(max_retries=1),
    )
    scenarios = [Scenario.NONE, Scenario.FAIL_BACKEND_WRITE, Scenario.AUTH_FAILURE, Scenario.TIMEOUT]
    return BenchmarkTask(task_id, collection, record_id, {"title": "to-delete"}, spec, scenarios)


def default_catalog() -> list[BenchmarkTask]:
    """A representative benchmark suite spanning update/create/delete/transition."""
    return [
        _field_task("profile_name", "profiles", "1", "name", "Bob", "Alice"),
        _field_task("project_desc", "projects", "1", "description",
                    "Old description", "AI Research Platform"),
        _field_task("settings_email", "settings", "1", "email_pref", "weekly", "never"),
        _field_task("order_status", "orders", "5", "status", "pending", "shipped",
                    pc_type=PostconditionType.STATE_TRANSITION),
        _create_task("create_item", "items", "new1", {"title": "New Item", "done": False}),
        _delete_task("delete_item", "items", "9"),
    ]


# Postcondition types the BrowserUiAdapter can type into a form field.
_TYPEABLE = (
    PostconditionType.FIELD_EQUALS,
    PostconditionType.FIELD_MATCHES,
    PostconditionType.STATE_TRANSITION,
)


def browser_drivable_catalog() -> list[BenchmarkTask]:
    """Subset the BrowserUiAdapter can genuinely drive (form-update tasks).

    The create/delete tasks have no typeable field, so a *form-driving* browser
    agent cannot attempt them; benchmarking it on those would measure adapter
    capability, not verification. This keeps the browser benchmark honest.
    """
    return [
        t
        for t in default_catalog()
        if any(pc.field and pc.type in _TYPEABLE for pc in t.spec.expected_postconditions)
    ]
