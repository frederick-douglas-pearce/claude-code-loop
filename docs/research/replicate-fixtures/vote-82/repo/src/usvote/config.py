"""Externalized configuration — read connection + path settings from the environment.

Replaces the notebook's hardcoded config (DB params in Section 4.1, the TIGER
shapefile path in Section 1.3 that had to be hand-edited before every run) so the
pipeline runs on a fresh machine by setting environment variables, not by editing
source (E2-S6, #31).

Two naming conventions, by design:

- **Database** settings use libpq's standard ``PG*`` names (``PGHOST``, ``PGPORT``,
  ``PGDATABASE``, ``PGUSER``, ``PGPASSWORD``). These are the same variables ``psql``,
  ``pg_dump``, and every other Postgres tool already read, so there is a single source
  of truth for "which database" — no parallel ``USVOTE_DB_*`` namespace to drift out of
  sync. We nonetheless read them *explicitly* here (rather than handing psycopg2 an
  empty dict and letting libpq read the ambient environment) so the resolution is
  deterministic, the defaults are ours, and tests can drive it through an injected
  ``environ`` dict. The DB is shared across all data sources, so this getter stays
  source-agnostic in the top-level package; the coming ``usvote/ucsb`` / ``usvote/mit``
  subpackages import it rather than re-implementing it.
- **App-specific** inputs use a ``USVOTE_*`` prefix (``USVOTE_SHAPEFILE_PATH``). Future
  per-source inputs follow the same shape (e.g. ``USVOTE_MIT_CSV_PATH``) and live in the
  relevant subpackage's own config module.

No dotenv dependency: read ``os.environ`` directly. To load a local ``.env``
(git-ignored), source it into the shell first — see the README's Configuration
section.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

# psycopg2.connect keyword -> (libpq env var, default). Password is handled
# separately below because it is optional: when unset we omit it from the dict
# entirely so the caller can prompt for it (e.g. __main__ via getpass) instead of
# committing a secret or sending an empty password.
_DB_PARAMS: tuple[tuple[str, str, str], ...] = (
    ("host", "PGHOST", "localhost"),
    ("port", "PGPORT", "5432"),
    ("dbname", "PGDATABASE", "elections"),
    ("user", "PGUSER", "postgres"),
)

#: Environment variable holding the path to the TIGER2019 US states shapefile.
SHAPEFILE_PATH_VAR = "USVOTE_SHAPEFILE_PATH"

#: Environment variable holding the path to the read-only API snapshot (E8, D028).
#: The snapshot build (:mod:`usvote.snapshot`) *writes* it; the API (``usvote/api/``)
#: *reads* it. App-level (not per-source), so it lives here in the source-agnostic
#: top-level config rather than a subpackage config module.
API_SNAPSHOT_PATH_VAR = "USVOTE_API_SNAPSHOT_PATH"


class ConfigError(RuntimeError):
    """Raised when a required setting is missing or invalid.

    Mirrors :class:`usvote.db.DBConnectionError` — a typed exception the caller can
    catch, rather than a bare ``KeyError`` or process exit.
    """


def db_config_from_env(environ: Mapping[str, str] = os.environ) -> dict[str, Any]:
    """Build psycopg2 connection kwargs from the standard libpq ``PG*`` variables.

    Reads ``PGHOST``/``PGPORT``/``PGDATABASE``/``PGUSER`` (falling back to
    ``localhost``/``5432``/``elections``/``postgres`` respectively) and ``PGPASSWORD``.
    The returned dict is passed straight to :class:`usvote.db.DBC`. ``PGPASSWORD`` is
    included only when set; when absent it is omitted so the caller can prompt for it
    rather than committing a secret. ``environ`` is injectable for testing.
    """
    config: dict[str, Any] = {
        key: environ.get(var, default) for key, var, default in _DB_PARAMS
    }
    password = environ.get("PGPASSWORD")
    if password is not None:
        config["password"] = password
    return config


def require_path_from_env(
    var_name: str,
    environ: Mapping[str, str] = os.environ,
    *,
    unset_hint: str,
    missing_hint: str,
) -> str:
    """Return a required machine-local path named by ``var_name``, or raise.

    The shared spine behind every ``*_path_from_env`` getter (the TIGER shapefile
    here, ``USVOTE_MIT_CSV_PATH`` in :mod:`usvote.mit.config`, UCSB's future path).
    There is never a sensible default for a machine-local download, so an unset/empty
    or nonexistent path is a :class:`ConfigError`, not a silent fallback. The two
    hints let each caller point the reader at the right download without re-writing the
    unset/missing branching. ``environ`` is injectable for testing.
    """
    path = environ.get(var_name)
    if not path:
        raise ConfigError(f"{var_name} is not set. {unset_hint}")
    if not os.path.exists(path):
        raise ConfigError(f"{var_name}={path!r} does not exist. {missing_hint}")
    return path


def snapshot_path_from_env(
    environ: Mapping[str, str] = os.environ, *, must_exist: bool = False
) -> str:
    """Return the API snapshot path from ``USVOTE_API_SNAPSHOT_PATH``.

    Unlike the shapefile/CSV getters this path is not always an *input*: the snapshot
    build (:mod:`usvote.snapshot`) resolves it as an **output** target that need not
    exist yet, so ``must_exist`` defaults to ``False`` (require the variable to be set,
    but not the file to be present). The API's serve path (E8-S2) resolves the same
    variable with ``must_exist=True`` — a missing snapshot must fail loud at startup,
    not 500 at request time. An unset/empty variable is always a :class:`ConfigError`.
    ``environ`` is injectable for testing.
    """
    path = environ.get(API_SNAPSHOT_PATH_VAR)
    if not path:
        raise ConfigError(
            f"{API_SNAPSHOT_PATH_VAR} is not set. Point it at the SQLite snapshot path "
            "the API serves — the build target for `python -m usvote.snapshot` and the "
            "read path for the API app (E8, D028)."
        )
    if must_exist and not os.path.exists(path):
        raise ConfigError(
            f"{API_SNAPSHOT_PATH_VAR}={path!r} does not exist. Build it first with "
            "`python -m usvote.snapshot` (needs the local warehouse), or point the "
            "variable at an existing snapshot."
        )
    return path


def shapefile_path_from_env(environ: Mapping[str, str] = os.environ) -> str:
    """Return the TIGER states shapefile path from ``USVOTE_SHAPEFILE_PATH``.

    Required — there is no sensible default for a machine-local download. Raises
    :class:`ConfigError` with an actionable message if the variable is unset/empty or
    points at a path that does not exist. The TIGER2019 STATE shapefile is a free
    download from the Census Bureau (https://www.census.gov/geographies/mapping-files/
    time-series/geo/tiger-line-file.html). ``environ`` is injectable for testing.
    """
    return require_path_from_env(
        SHAPEFILE_PATH_VAR,
        environ,
        unset_hint=(
            "Point it at the unzipped TIGER2019 STATE shapefile (.shp), a free "
            "download from the Census Bureau: https://www.census.gov/geographies/"
            "mapping-files/time-series/geo/tiger-line-file.html"
        ),
        missing_hint=(
            "Check the path points at the unzipped TIGER2019 STATE shapefile (.shp)."
        ),
    )
