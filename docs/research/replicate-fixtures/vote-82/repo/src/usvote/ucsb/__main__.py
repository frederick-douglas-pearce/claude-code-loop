"""Runnable entry point — ``python -m usvote.ucsb`` snapshots or loads the UCSB data.

Subcommand-based (#84b), with **``snapshot`` as the default** so the bare
``python -m usvote.ucsb`` keeps its historical meaning — the D023 reproducible network
refresh, *not* "run the pipeline":

- ``python -m usvote.ucsb`` / ``python -m usvote.ucsb snapshot`` — fetch the raw UCSB
  pages into ``USVOTE_UCSB_HTML_DIR`` (:func:`usvote.ucsb.scrape.snapshot_elections`).
- ``python -m usvote.ucsb load`` — run :func:`usvote.ucsb.pipeline.run_ucsb_pipeline`
  (parse the local snapshot, reconcile against the EC spine, load
  ``dwh.pv_votes`` + ``dwh.pv_state_status``).

Keeping ``snapshot`` as the default is why the cross-package ``python -m X`` asymmetry
the #84 issue names is **reduced to a documented default, not eliminated**: ``python -m
usvote`` loads and ``python -m usvote.ucsb`` snapshots. That asymmetry is principled —
only UCSB has a network stage to snapshot (MIT reads a local CSV), and the snapshot is
the UCSB-specific action (D023). The whole-warehouse ``python -m usvote all`` is the
unified "load everything" front door.

``snapshot`` is a **network-touching, deliberately slow** command: it honors UCSB's
``Crawl-delay: 10``, so a full 60-election run takes ~10 minutes. It is safe to re-run
— pages already snapshotted are skipped. ``load`` requires the EC spine to already be in
``dwh`` (it reconciles UCSB candidates against the EC getters); run ``python -m usvote``
(or ``python -m usvote all``) first.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from typing import Any

from usvote import config
from usvote.config import ConfigError
from usvote.db import DBC, DBConnectionError
from usvote.ucsb.config import ucsb_html_dir_from_env
from usvote.ucsb.pipeline import run_ucsb_pipeline
from usvote.ucsb.scrape import UCSBScrapeError, snapshot_elections


def _run_snapshot() -> int:
    try:
        snapshot_elections()
    except ConfigError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        return 2
    except UCSBScrapeError as e:
        print(e, file=sys.stderr)
        return 1
    return 0


def _run_load(replace: bool) -> int:
    environ = os.environ
    try:
        html_dir = ucsb_html_dir_from_env(environ)
        db_config: dict[str, Any] = config.db_config_from_env(environ)
    except ConfigError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        return 2

    if "password" not in db_config:
        db_config["password"] = getpass.getpass(
            f"Password for {db_config['user']}@{db_config['host']}: "
        )
    try:
        dbc = DBC(db_config)
    except DBConnectionError as e:
        print(e, file=sys.stderr)
        return 1

    run_ucsb_pipeline(dbc, html_dir, replace=replace, close=True)
    print("UCSB ingestion complete.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m usvote.ucsb",
        description="Snapshot or load the UCSB popular-vote data.",
    )
    sub = parser.add_subparsers(dest="command")
    sub.add_parser(
        "snapshot",
        help="Fetch the raw UCSB pages into USVOTE_UCSB_HTML_DIR (the bare default).",
    )
    load_p = sub.add_parser(
        "load", help="Parse the snapshot, reconcile against the EC spine, load dwh."
    )
    load_p.add_argument(
        "--replace",
        action="store_true",
        help="Rebuild both PV tables (pv_votes + pv_state_status) before loading. "
        "Table-level only — never touches the EC spine or the schema.",
    )
    args = parser.parse_args(argv)

    if args.command == "load":
        return _run_load(args.replace)
    # Bare (``command is None``) and explicit ``snapshot`` both snapshot (D023).
    return _run_snapshot()


if __name__ == "__main__":
    raise SystemExit(main())
