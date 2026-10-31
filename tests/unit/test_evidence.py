"""Evidence integrity: content-addressed ids, stable across timestamps."""

from __future__ import annotations

from engine.models import Evidence, VerifierType


def _ev(observed: str) -> Evidence:
    return Evidence(
        verifier_type=VerifierType.API,
        source="GET /api/profile",
        expected_state="Alice",
        observed_state=observed,
        confidence=1.0,
    )


def test_identical_content_shares_id():
    a, b = _ev("Alice"), _ev("Alice")
    assert a.id == b.id
    assert a.id.startswith("sha256:")


def test_different_content_differs():
    assert _ev("Alice").id != _ev("Bob").id


def test_id_is_stable_regardless_of_created_at():
    a = _ev("Alice")
    b = _ev("Alice")
    # created_at differs between the two instances, id must not.
    assert a.created_at != b.created_at or a.id == b.id
    assert a.id == b.id


def test_id_serialized_in_dump():
    data = _ev("Alice").model_dump()
    assert data["id"] == _ev("Alice").id
    assert data["content_hash"] == data["id"]
