"""The E8 internal API (``usvote/api/``) — serves the read-only snapshot over HTTP.

A thin FastAPI serving layer over the E8-S1 SQLite snapshot with **no live DB at serve
time** (D028): it imports only the snapshot artifact + the thin
:class:`~usvote.api.repository.SnapshotRepository` + stdlib-only contract modules, a
structural invariant enforced by ``tests/unit/test_api_import_graph.py``. Postgres stays
the *local* warehouse / source of truth, read only at snapshot-build time
(:mod:`usvote.snapshot`).

Run it locally with ``python -m usvote.api`` (or ``uvicorn --factory
usvote.api:create_app``); requires ``USVOTE_API_SNAPSHOT_PATH`` to point at a built
snapshot.
"""

from __future__ import annotations

from usvote.api.app import create_app

__all__ = ["create_app"]
