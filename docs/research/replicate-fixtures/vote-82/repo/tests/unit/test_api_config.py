"""Unit tests for the API config layer (``usvote.api.config``).

The CORS getter's contract is the D031 guarantee: a configurable allow-list that falls
back to concrete localhost origins, **never** a silent ``*``.
"""

from __future__ import annotations

from usvote.api.config import (
    DEFAULT_CORS_ORIGINS,
    cors_origins_from_env,
)


def test_cors_default_is_localhost_never_star() -> None:
    origins = cors_origins_from_env({})
    assert origins == list(DEFAULT_CORS_ORIGINS)
    assert "*" not in origins


def test_cors_parses_comma_list_and_strips() -> None:
    origins = cors_origins_from_env(
        {"USVOTE_API_CORS_ORIGINS": " https://a.example , https://b.example ,"}
    )
    assert origins == ["https://a.example", "https://b.example"]


def test_cors_blank_falls_back_to_default() -> None:
    assert cors_origins_from_env({"USVOTE_API_CORS_ORIGINS": "   "}) == list(
        DEFAULT_CORS_ORIGINS
    )
