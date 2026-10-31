"""Unit tests for matcher modes and postcondition evaluation."""

from __future__ import annotations

from engine.models import (
    MatcherConfig,
    MatchMode,
    Observation,
    Postcondition,
    PostconditionType,
    VerifierStatus,
    VerifierType,
)
from engine.verification.base import evaluate_postcondition


def _obs(state: dict) -> Observation:
    return Observation(observer_type=VerifierType.API, source="test", state=state)


def test_exact_match_case_sensitive():
    m = MatcherConfig(mode=MatchMode.EXACT, case_sensitive=True)
    assert m.matches("Alice", "Alice")
    assert not m.matches("Alice", "alice")


def test_exact_match_case_insensitive():
    m = MatcherConfig(mode=MatchMode.EXACT, case_sensitive=False)
    assert m.matches("Alice", "alice")


def test_normalized_collapses_whitespace_and_case():
    m = MatcherConfig(mode=MatchMode.NORMALIZED)
    assert m.matches("AI  Research   Platform", " ai research platform ")


def test_regex_full_match_only():
    m = MatcherConfig(mode=MatchMode.REGEX)
    assert m.matches(r"v\d+\.\d+", "v1.2")
    assert not m.matches(r"v\d+", "version 1")  # fullmatch, not search


def test_numeric_tolerance():
    m = MatcherConfig(mode=MatchMode.NUMERIC_TOLERANCE, tolerance=0.5)
    assert m.matches(10, 10.4)
    assert not m.matches(10, 11)


def test_matcher_never_raises_on_bad_input():
    m = MatcherConfig(mode=MatchMode.NUMERIC_TOLERANCE)
    assert m.matches("not-a-number", "x") is False


def test_field_equals_pass_fail_inconclusive():
    pc = Postcondition(
        ref="p1",
        type=PostconditionType.FIELD_EQUALS,
        entity="user",
        field="name",
        expected="Alice",
    )
    assert evaluate_postcondition(pc, _obs({"name": "Alice"}))[0] is VerifierStatus.PASS
    assert evaluate_postcondition(pc, _obs({"name": "Bob"}))[0] is VerifierStatus.FAIL
    # field absent -> we cannot decide, not a failure
    assert evaluate_postcondition(pc, _obs({}))[0] is VerifierStatus.INCONCLUSIVE


def test_not_exists_for_delete():
    pc = Postcondition(ref="p", type=PostconditionType.NOT_EXISTS, entity="item")
    assert evaluate_postcondition(pc, _obs({"exists": False}))[0] is VerifierStatus.PASS
    assert evaluate_postcondition(pc, _obs({"exists": True}))[0] is VerifierStatus.FAIL


def test_count_equals():
    pc = Postcondition(
        ref="p", type=PostconditionType.COUNT_EQUALS, entity="cart", expected=3
    )
    assert evaluate_postcondition(pc, _obs({"count": 3}))[0] is VerifierStatus.PASS
    assert evaluate_postcondition(pc, _obs({"count": 2}))[0] is VerifierStatus.FAIL


def test_read_error_is_inconclusive():
    pc = Postcondition(
        ref="p", type=PostconditionType.FIELD_EQUALS, entity="u", field="name", expected="A"
    )
    bad = Observation(
        observer_type=VerifierType.API, source="t", state={}, error="timeout"
    )
    assert evaluate_postcondition(pc, bad)[0] is VerifierStatus.INCONCLUSIVE
