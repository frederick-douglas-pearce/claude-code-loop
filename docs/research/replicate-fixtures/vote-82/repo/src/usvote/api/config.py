"""API-specific configuration — CORS origins, the ``/v1`` prefix, the snapshot path.

App-*level* inputs (the snapshot path, the DB) live in the source-agnostic top-level
:mod:`usvote.config`; the *API*-specific knobs (CORS allow-list, route-version prefix)
live here in the subpackage, mirroring the per-source ``mit/config.py`` / ``ucsb/
config.py`` convention. The snapshot path is resolved by **reusing**
:func:`usvote.config.snapshot_path_from_env` with ``must_exist=True`` — a missing
snapshot is a typed :class:`usvote.config.ConfigError` raised at **startup**, never a
500 at request time (D028's "fail loud at boot").

Deliberately stdlib-only (plus :mod:`usvote.config`, itself stdlib-only): nothing here
may drag pandas / psycopg2 across the ``usvote/api/`` import boundary (D028, enforced by
``tests/unit/test_api_import_graph.py``).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field

from usvote import config

#: Environment variable holding the CORS allow-list (comma-separated origins). The exact
#: dashboard origin is deferred (frontend D001); until it is supplied we default to
#: localhost dev origins and **never** a silent ``*`` (D031) — an open CORS policy on a
#: public-graduation surface is a decision, not a default.
CORS_ORIGINS_VAR = "USVOTE_API_CORS_ORIGINS"

#: The localhost dev origins used when :data:`CORS_ORIGINS_VAR` is unset. Vite (5173)
#: and Create-React-App (3000) defaults, both loopback spellings.
DEFAULT_CORS_ORIGINS: tuple[str, ...] = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
)

#: The versioned route prefix, present from day one so public graduation is a config
#: step, not a breaking change (D031).
API_VERSION_PREFIX = "/v1"

#: Environment variable holding the **origin lock-down secret** (E8-S7, #101 / D034).
#: When the deployed API is fronted by Cloudflare, a Transform Rule injects this secret
#: on every proxied request; the app then rejects any ``/v1`` request that lacks it, so
#: a bot cannot bypass the edge rate-limits/WAF by hitting the raw Cloud Run URL.
#: **Opt-in and fail-open:** unset (local dev, the unit suite, the D033 container smoke
#: test) means no enforcement — the origin guard is a deploy control, not a local one.
ORIGIN_SECRET_VAR = "USVOTE_API_ORIGIN_SECRET"


def cors_origins_from_env(
    environ: Mapping[str, str] = os.environ,
) -> list[str]:
    """Return the CORS allow-list from :data:`CORS_ORIGINS_VAR`, or a localhost default.

    The value is a comma-separated list of origins (``https://a.example,https://b``).
    Whitespace around each entry is stripped and empties dropped. An unset/blank
    variable falls back to :data:`DEFAULT_CORS_ORIGINS` — a concrete localhost list,
    **never** ``["*"]`` (D031). ``environ`` is injectable for testing.
    """
    raw = environ.get(CORS_ORIGINS_VAR, "")
    origins = [o.strip() for o in raw.split(",") if o.strip()]
    return origins or list(DEFAULT_CORS_ORIGINS)


@dataclass(frozen=True)
class ApiSettings:
    """Resolved API configuration — the single object the app factory consumes.

    Centralizes the three knobs the E8-S2 AC names (snapshot path, CORS origins, version
    prefix) so the factory reads settings, not the environment. Built via
    :meth:`from_env`; injectable into :func:`usvote.api.app.create_app` for tests.
    """

    snapshot_path: str
    cors_origins: list[str] = field(default_factory=lambda: list(DEFAULT_CORS_ORIGINS))
    version_prefix: str = API_VERSION_PREFIX
    #: The origin lock-down secret (D034). ``None`` ⇒ the origin guard is inactive
    #: (fail-open) — the local/CI default; set only in the deployed (Cloudflare-fronted)
    #: environment via :data:`ORIGIN_SECRET_VAR`.
    origin_secret: str | None = None

    @classmethod
    def from_env(cls, environ: Mapping[str, str] = os.environ) -> ApiSettings:
        """Resolve settings from the environment, failing loud on a missing snapshot.

        The snapshot path is required **and must exist** (``must_exist=True``): the API
        cannot serve without its data, so an unset variable or absent file is a
        :class:`usvote.config.ConfigError` at startup, not a request-time surprise. The
        origin secret is optional (unset ⇒ the origin guard stays fail-open).
        """
        return cls(
            snapshot_path=config.snapshot_path_from_env(environ, must_exist=True),
            cors_origins=cors_origins_from_env(environ),
            version_prefix=API_VERSION_PREFIX,
            origin_secret=environ.get(ORIGIN_SECRET_VAR) or None,
        )
