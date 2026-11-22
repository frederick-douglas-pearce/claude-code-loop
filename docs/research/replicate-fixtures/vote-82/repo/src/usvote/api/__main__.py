"""Runnable entry point — ``python -m usvote.api`` serves the read-only snapshot.

Subcommand-based, consistent with the D027 ``__main__`` convention. A single ``serve``
subcommand is the default, so bare ``python -m usvote.api`` starts the local server:

- ``python -m usvote.api`` / ``python -m usvote.api serve`` — start uvicorn on the app
  from :func:`usvote.api.create_app` (reads ``USVOTE_API_SNAPSHOT_PATH`` at startup;
  needs **no** live DB — D028).

Config is resolved eagerly at app-build time: a missing/unset snapshot raises the typed
:class:`usvote.config.ConfigError` before the server binds a port, printed here as a
clean startup error rather than an in-flight 500. Build the snapshot first with
``python -m usvote.snapshot`` (that step, and only that step, needs the warehouse).

For production/container use, point an ASGI server straight at the factory
(``uvicorn --factory usvote.api:create_app``); this module is the dev-convenience
wrapper.
"""

from __future__ import annotations

import argparse
import sys

from usvote.config import ConfigError


def _run_serve(host: str, port: int) -> int:
    import uvicorn

    from usvote.api import create_app
    from usvote.api.repository import SnapshotError, SnapshotRepository

    try:
        app = create_app()  # eager config resolution — fail loud before binding
    except ConfigError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        return 2

    # Pre-flight the snapshot itself. create_app only resolves config (path exists); the
    # repository open — which validates schema_version and the meta table — otherwise
    # runs inside the lifespan once uvicorn is starting, surfacing a bad snapshot as an
    # ugly "Application startup failed" traceback after the port is claimed. Opening it
    # here (cheap, read-only; the lifespan re-opens it) keeps the "fail loud before
    # binding a port" promise for the mismatched/corrupt case too, not just missing.
    try:
        SnapshotRepository.open(app.state.settings.snapshot_path)
    except SnapshotError as e:
        print(f"Snapshot error: {e}", file=sys.stderr)
        return 3

    uvicorn.run(app, host=host, port=port)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m usvote.api",
        description=(
            "Serve the read-only API snapshot over HTTP (E8, D028). No live DB at "
            "serve time; reads USVOTE_API_SNAPSHOT_PATH."
        ),
    )
    sub = parser.add_subparsers(dest="command")
    serve_p = sub.add_parser(
        "serve", help="Start the local uvicorn server (the bare default)."
    )
    serve_p.add_argument("--host", default="127.0.0.1", help="Bind host.")
    serve_p.add_argument("--port", type=int, default=8000, help="Bind port.")
    args = parser.parse_args(argv)

    host = getattr(args, "host", "127.0.0.1")
    port = getattr(args, "port", 8000)
    return _run_serve(host, port)


if __name__ == "__main__":
    raise SystemExit(main())
