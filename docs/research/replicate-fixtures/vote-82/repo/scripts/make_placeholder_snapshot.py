"""Build a *placeholder* API snapshot for the CI container smoke test (#100 / D033).

The real snapshot is built from the Postgres warehouse (``python -m usvote.snapshot``),
which CI does not have. But the container's Dockerfile bakes a snapshot in, so CI needs
*some* schema-valid snapshot to build + boot the image against.

This reuses the committed synthetic ``ec_pv_redistributable`` frame the API unit tests
already use (:func:`tests.fixtures.api_snapshot.synthetic_ec_pv_frame`) and writes it
through the real :func:`usvote.snapshot.build_snapshot` writer — so the placeholder
carries the current ``SNAPSHOT_SCHEMA_VERSION`` and passes ``SnapshotRepository.open``'s
schema check at container start. It is fabricated MIT/CC0-shaped data (no UCSB bytes,
no warehouse), so it is safe to generate anywhere.

CI does NOT validate real snapshot *contents* through this — only that the Dockerfile
builds, the slim serve closure imports, and the app boots and answers ``/health``. That
is the D033 drift guard: an import added to ``usvote/api/`` that is allowed but not in
the serve closure (which the denylist import-graph test would miss) breaks this boot.

Usage: ``python scripts/make_placeholder_snapshot.py [OUT_PATH]`` (default
``api_snapshot.sqlite`` in the CWD, the Dockerfile's build-context default).
"""

from __future__ import annotations

import sys
from pathlib import Path

# The synthetic frame lives under tests/ (not an installed package). Make the repo root
# importable so a plain `python scripts/...` invocation finds `tests` — usvote itself is
# installed in the venv and needs no shim.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.fixtures.api_snapshot import (  # noqa: E402  (after the sys.path shim)
    SNAPSHOT_TS,
    synthetic_ec_pv_frame,
)
from usvote.snapshot import build_snapshot  # noqa: E402  (after the sys.path shim)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    out_path = args[0] if args else "api_snapshot.sqlite"
    meta = build_snapshot(
        synthetic_ec_pv_frame(), out_path, build_timestamp=SNAPSHOT_TS
    )
    print(
        f"wrote placeholder snapshot -> {out_path} "
        f"(schema_version={meta.schema_version}, version={meta.snapshot_version})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
