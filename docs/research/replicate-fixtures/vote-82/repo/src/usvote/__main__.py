"""Runnable entry point — ``python -m usvote`` runs an ingestion build.

Subcommand-based (#84b), but **bare ``python -m usvote`` still runs the EC pipeline**
for backward compatibility (it is the most common command and the only one needing just
``USVOTE_SHAPEFILE_PATH`` + DB):

- ``python -m usvote`` / ``python -m usvote ec`` — scrape + load the EC spine into
  ``dwh`` (the historical default; ``--replace`` still works bare, before or without
  the subcommand).
- ``python -m usvote all`` — build the **whole** warehouse: EC spine, MIT PV,
  optionally UCSB PV, then the resolved-PV + EC<->PV join views
  (:func:`usvote.warehouse.run_warehouse`).

Bare is kept on EC rather than re-pointed at ``all`` deliberately: ``all`` additionally
requires ``USVOTE_MIT_CSV_PATH`` (and the UCSB snapshot for the full set), so silently
making the default command need more config would break a documented invocation (D027).

**``--replace`` has two scopes.** For ``ec`` / bare it drops and recreates the whole
``dwh`` schema (the destructive EC rebuild). For ``all`` it forwards to the EC step the
same way — which *cascades* the PV tables and views away — while the PV sources
always load ``replace=False`` (append onto the fresh schema) and the views are rebuilt
(:func:`usvote.warehouse.run_warehouse`). A re-run **without** ``--replace`` over an
already-built warehouse fails loud on a unique/PK violation (the intended
non-destructive guard), not silently; recover a partial build with ``--replace``.

**UCSB gating for ``all`` is explicit and loud.** UCSB content is non-redistributable
and lives outside the repo (D016/D022), so a fresh public clone builds EC + MIT (the
redistributable core) and skips UCSB (the analysis-only control) unless the private
snapshot is present. By default ``all`` auto-detects ``USVOTE_UCSB_HTML_DIR`` and, when
it is absent, builds **without** UCSB after printing a prominent notice.
``--require-ucsb`` turns an absent snapshot into a hard failure (for an analysis
workflow that must have the control); ``--no-ucsb`` skips it unconditionally.

Deliberately thin — no pipeline logic lives here; it resolves environment -> config ->
connection and calls the programmatic entry points.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from collections.abc import Mapping
from typing import Any

from usvote import config
from usvote.db import DBC, DBConnectionError
from usvote.mit.config import mit_csv_path_from_env
from usvote.pipeline import run_ec_pipeline
from usvote.ucsb.config import ucsb_html_dir_from_env
from usvote.warehouse import SOURCE_UCSB, run_warehouse

_REPLACE_HELP = (
    "Drop and recreate the dwh schema before loading (destructive full rebuild). "
    "Omit to create-if-absent; a create-if-absent re-run over already-loaded data "
    "fails loud on a unique/PK violation."
)


def _connect(db_config: dict[str, Any]) -> DBC | None:
    """Prompt for the password if needed and connect; return ``None`` on failure."""
    # Prompt only when the password was not supplied via PGPASSWORD, so a preset secret
    # is not re-requested and never has to be committed.
    if "password" not in db_config:
        db_config["password"] = getpass.getpass(
            f"Password for {db_config['user']}@{db_config['host']}: "
        )
    try:
        return DBC(db_config)
    except DBConnectionError as e:
        print(e, file=sys.stderr)
        return None


def _resolve_ucsb_dir(
    args: argparse.Namespace, environ: Mapping[str, str]
) -> str | None:
    """Resolve the UCSB snapshot dir for ``all``, honoring the gating flags.

    ``--no-ucsb`` -> always ``None`` (skip). ``--require-ucsb`` -> resolve or raise
    :class:`~usvote.config.ConfigError` (an absent snapshot is a hard failure). Default
    -> auto-detect: the resolved dir if ``USVOTE_UCSB_HTML_DIR`` is set and exists, else
    ``None`` (skip). Returning ``None`` means "build without UCSB", surfaced loudly by
    the caller.
    """
    if args.no_ucsb:
        return None
    try:
        return ucsb_html_dir_from_env(environ)
    except config.ConfigError:
        # Absent snapshot: a hard failure only under --require-ucsb; otherwise skip.
        if args.require_ucsb:
            raise
        return None


def _run_ec(replace: bool) -> int:
    try:
        shapefile_path = config.shapefile_path_from_env()
        db_config = config.db_config_from_env()
    except config.ConfigError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        return 2

    dbc = _connect(db_config)
    if dbc is None:
        return 1

    run_ec_pipeline(dbc, shapefile_path, replace=replace, close=True)
    print("EC ingestion complete.")
    return 0


def _run_all(args: argparse.Namespace) -> int:
    environ = os.environ
    try:
        shapefile_path = config.shapefile_path_from_env(environ)
        mit_csv_path = mit_csv_path_from_env(environ)
        ucsb_html_dir = _resolve_ucsb_dir(args, environ)
        db_config = config.db_config_from_env(environ)
    except config.ConfigError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        return 2

    if ucsb_html_dir is None:
        # D024/D016: a build missing UCSB is never silent — loud either way. UCSB is the
        # analysis-only consistency control; a hybrid/analysis run over a warehouse that
        # quietly lacks it would produce subtly wrong numbers with no signal. The remedy
        # differs by cause: --no-ucsb is a deliberate choice (nothing to fix), whereas
        # an auto-skip means the snapshot was simply not found (point to the fix).
        remedy = (
            "This was requested with --no-ucsb."
            if args.no_ucsb
            else (
                "Pass --require-ucsb to demand the full set, or set "
                "USVOTE_UCSB_HTML_DIR to the snapshot directory to include it."
            )
        )
        print(
            "NOTICE: building WITHOUT UCSB — the warehouse will hold only the "
            "redistributable EC + MIT core, and any hybrid analysis will lack the UCSB "
            f"consistency control. {remedy}",
            file=sys.stderr,
        )

    dbc = _connect(db_config)
    if dbc is None:
        return 1

    result = run_warehouse(
        dbc,
        shapefile_path,
        mit_csv_path,
        ucsb_html_dir=ucsb_html_dir,
        replace=args.replace,
        environ=environ,
        close=True,
    )
    sources = ", ".join(sorted(result.sources_loaded))
    ucsb_note = (
        f", UCSB {result.ucsb_pv_rows} PV / {result.ucsb_roster_rows} roster rows"
        if SOURCE_UCSB in result.sources_loaded
        else ""
    )
    print(
        f"Warehouse build complete — sources: {sources}; "
        f"EC {result.ec_rows} rows, MIT {result.mit_rows} rows"
        f"{ucsb_note}; join views rebuilt."
    )
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m usvote",
        description="Scrape and load US presidential vote data into the dwh schema.",
    )
    # Kept at the top level too, so bare ``python -m usvote --replace`` (the historical
    # spelling, no subcommand) still works and maps to the EC rebuild.
    parser.add_argument("--replace", action="store_true", help=_REPLACE_HELP)
    sub = parser.add_subparsers(dest="command")

    ec_p = sub.add_parser(
        "ec", help="Scrape and load the Electoral College spine (the bare default)."
    )
    # SUPPRESS default: when ``--replace`` is not given on the subcommand, do not add
    # the attribute, so the top-level ``--replace`` value survives (avoids the argparse
    # subparser-default-clobber gotcha).
    ec_p.add_argument(
        "--replace", action="store_true", default=argparse.SUPPRESS, help=_REPLACE_HELP
    )

    all_p = sub.add_parser(
        "all",
        help="Build the whole warehouse: EC + MIT + (optional) UCSB + join views.",
    )
    all_p.add_argument(
        "--replace", action="store_true", default=argparse.SUPPRESS, help=_REPLACE_HELP
    )
    ucsb_group = all_p.add_mutually_exclusive_group()
    ucsb_group.add_argument(
        "--require-ucsb",
        action="store_true",
        help="Fail if the UCSB snapshot (USVOTE_UCSB_HTML_DIR) is absent, instead of "
        "building without it.",
    )
    ucsb_group.add_argument(
        "--no-ucsb",
        action="store_true",
        help="Skip UCSB unconditionally (build only the EC + MIT core).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "all":
        return _run_all(args)
    # Bare (``command is None``) and explicit ``ec`` both run the EC pipeline. argparse
    # leaves ``replace`` set by the top-level parser (default False) unless the ``ec``
    # subcommand overrode it.
    return _run_ec(getattr(args, "replace", False))


if __name__ == "__main__":
    raise SystemExit(main())
