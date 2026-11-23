"""Redistributable-only regression guard (E8-S5, #99, D030).

Belt-and-suspenders over the #95 source guarantee and the #97 endpoint layer: the API must
serve **only** MIT/CC0 (redistributable) data, and it must be impossible for a
``redistributable=false`` / non-MIT row to reach either the built snapshot or a served
response.

Two layers:
1. **Build-time** — :func:`usvote.snapshot.build_snapshot` (via ``assert_redistributable_only``)
   fails loud on a ``redistributable=false`` row and on a non-MIT ``source``, rather than
   trusting the upstream ``ec_pv_redistributable`` view.
2. **Serve-time** — no ``/v1`` endpoint that carries a per-row ``source`` ever surfaces a
   row whose source is anything but MIT (or NULL, an honest D005 no-PV gap).

All offline (D028): synthetic frame → real SQLite snapshot, no live Postgres.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.fixtures.api_snapshot import SNAPSHOT_TS, synthetic_ec_pv_frame
from usvote.snapshot import SnapshotError, build_snapshot

# --- build-time guard -------------------------------------------------------


def test_build_refuses_a_non_redistributable_row(tmp_path: Path) -> None:
    """A single ``redistributable=false`` row must fail the build loud, not slip through."""
    frame = synthetic_ec_pv_frame()
    frame.loc[0, "redistributable"] = False
    with pytest.raises(SnapshotError, match="redistributable"):
        build_snapshot(frame, str(tmp_path / "snap.sqlite"), build_timestamp=SNAPSHOT_TS)


def test_build_refuses_a_non_mit_source_row(tmp_path: Path) -> None:
    """A non-MIT ``source`` (e.g. a UCSB row) must fail the build loud (D016/D030)."""
    frame = synthetic_ec_pv_frame()
    frame.loc[0, "source"] = "UCSB"
    with pytest.raises(SnapshotError, match="non-MIT"):
        build_snapshot(frame, str(tmp_path / "snap.sqlite"), build_timestamp=SNAPSHOT_TS)


# --- serve-time guard -------------------------------------------------------


def test_no_endpoint_surfaces_a_non_mit_row(client: TestClient) -> None:
    """Across every row-carrying endpoint, no served row has a non-MIT ``source``.

    Strengthens the original three-path spot-check into a full sweep over each covered
    year / state / candidate in the fixture.
    """
    years = (2016, 2020)
    states = ("TX", "CA")
    slugs = ("cand-a", "cand-b")
    paths = (
        [f"/v1/elections/{y}" for y in years]
        + [f"/v1/states/{s}" for s in states]
        + [f"/v1/candidates/{slug}" for slug in slugs]
    )
    for path in paths:
        body = client.get(path).json()
        for row in body["data"]:
            # ``row["source"]`` (not ``.get``) so a dropped/renamed field fails loud
            # rather than silently matching the allowed ``None``.
            assert row["source"] in (None, "MIT"), f"{path}: {row}"
