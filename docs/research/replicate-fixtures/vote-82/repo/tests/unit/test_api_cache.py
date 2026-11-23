"""Unit tests for the pure freshness helpers (``usvote.api.cache``).

The ETag is a process constant (the snapshot content hash), so the conditional-request
logic is pure string handling — tested here directly, without HTTP, per the "validation is
load-bearing" rule.
"""

from __future__ import annotations

import pytest

from usvote.api.cache import etag_for, if_none_match_satisfied


def test_etag_is_quoted() -> None:
    assert etag_for("abc123") == '"abc123"'


@pytest.mark.parametrize(
    ("if_none_match", "expected"),
    [
        (None, False),
        ("", False),
        ('"abc123"', True),
        ('"other"', False),
        ('"other", "abc123"', True),  # list — any match
        ("*", True),
        ('W/"abc123"', True),  # weak validator matches for If-None-Match
        ('"abc123", "x"', True),
    ],
)
def test_if_none_match_comparison(if_none_match: str | None, expected: bool) -> None:
    assert if_none_match_satisfied(if_none_match, '"abc123"') is expected
