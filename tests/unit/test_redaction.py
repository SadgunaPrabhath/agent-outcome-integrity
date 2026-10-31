"""Unit tests for the secret-redaction layer."""

from __future__ import annotations

from engine.tracing import REDACTED, redact, redact_text


def test_redacts_sensitive_keys():
    data = {"name": "Alice", "password": "hunter2", "api_key": "abc123"}
    out = redact(data)
    assert out["name"] == "Alice"
    assert out["password"] == REDACTED
    assert out["api_key"] == REDACTED


def test_redacts_nested_structures():
    data = {"user": {"authorization": "Bearer xyz", "profile": {"token": "t"}}, "items": [{"secret": "s"}]}
    out = redact(data)
    assert out["user"]["authorization"] == REDACTED
    assert out["user"]["profile"]["token"] == REDACTED
    assert out["items"][0]["secret"] == REDACTED


def test_redacts_token_shaped_values_in_text():
    assert REDACTED in redact_text("Authorization: Bearer abc.def.ghi123")
    assert REDACTED in redact_text("key sk-ABCDEFGHIJKLMNOP1234")


def test_non_sensitive_untouched():
    data = {"email_pref": "weekly", "count": 3, "flag": True}
    assert redact(data) == data


def test_total_on_odd_input():
    assert redact(None) is None
    assert redact(42) == 42
    assert redact(["a", 1, {"password": "x"}])[2]["password"] == REDACTED
