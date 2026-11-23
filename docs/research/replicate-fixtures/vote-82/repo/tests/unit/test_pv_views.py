"""Unit tests for the D017 resolution views (``usvote.pv.views``, #68).

Two kinds of check, both offline:

- **SQL structure** — the view builders emit the resolution logic D017 mandates
  (``DISTINCT ON ... ORDER BY precedence_rank`` for ``pv_preferred``; an *independent*
  ``WHERE redistributable`` for ``pv_redistributable``; the literal UCSB filter for the
  control), and every view selects the D018 shared shape.
- **Frame oracles** — ``resolve_preferred`` and the assert helpers on a small,
  fabricated two-source union (no real UCSB bytes — D022): MIT wins the 1976–2024
  overlap, UCSB is kept pre-1976, a MIT-only key stays MIT, an absent key is never
  fabricated (D005), and the provenance-coverage gap raises.

The oracles are the same policy the live views run; the live behavioral check is in
``tests/integration/test_pv_union.py``.
"""

from __future__ import annotations

import pandas as pd
import pytest

from usvote.pv.schema import SHARED_PV_COLUMNS
from usvote.pv.source import SOURCE_MIT, SOURCE_UCSB, build_pv_source_frame
from usvote.pv.views import (
    PV_PREFERRED_VIEW,
    PV_REDISTRIBUTABLE_VIEW,
    PV_UCSB_VIEW,
    PVViewError,
    assert_provenance_coverage,
    assert_single_row_per_key,
    assert_union_grain,
    build_pv_preferred_sql,
    build_pv_redistributable_sql,
    build_pv_ucsb_sql,
    resolve_preferred,
)

# --- SQL structure ----------------------------------------------------------


def test_view_names_are_named_apart_from_the_fact() -> None:
    from usvote.pv.schema import PV_TABLE

    assert {PV_PREFERRED_VIEW, PV_REDISTRIBUTABLE_VIEW, PV_UCSB_VIEW} == {
        "pv_preferred", "pv_redistributable", "pv_ucsb"
    }
    assert PV_TABLE not in {PV_PREFERRED_VIEW, PV_REDISTRIBUTABLE_VIEW, PV_UCSB_VIEW}


def test_preferred_resolves_by_precedence_rank_not_a_hardcoded_source() -> None:
    sql = build_pv_preferred_sql()
    # DISTINCT ON the resolved key, tie-broken by the pv_source precedence_rank join —
    # NOT a hardcoded CASE/source='MIT', so a grant or new source is a data-only edit.
    assert "DISTINCT ON (v.year, v.state, v.candidate)" in sql
    assert "JOIN dwh.pv_source s USING (source)" in sql
    assert sql.rstrip().endswith("ORDER BY v.year, v.state, v.candidate, s.precedence_rank")
    assert "'MIT'" not in sql and "CASE" not in sql


def test_redistributable_is_defined_independently_not_over_preferred() -> None:
    sql = build_pv_redistributable_sql()
    # D017 §4: WHERE redistributable (a pv_source attribute), defined independently so
    # no preference change can leak a UCSB row onto the public surface. It must NOT be
    # a filter over pv_preferred, and must NOT hardcode the source name.
    assert "WHERE s.redistributable" in sql
    assert PV_PREFERRED_VIEW not in sql
    assert "'MIT'" not in sql


def test_redistributable_dedupes_by_precedence_rank() -> None:
    # Forward-compat guard: the public surface must stay one row per key even if a
    # second redistributable source is added, so it deduplicates the same way
    # pv_preferred does (DISTINCT ON key ORDER BY precedence_rank), not by assuming
    # MIT is the only redistributable source.
    sql = build_pv_redistributable_sql()
    assert "DISTINCT ON (v.year, v.state, v.candidate)" in sql
    assert sql.rstrip().endswith(
        "ORDER BY v.year, v.state, v.candidate, s.precedence_rank"
    )


def test_ucsb_control_filters_the_literal_source() -> None:
    sql = build_pv_ucsb_sql()
    # D017 §5: specifically the UCSB single-source control — a literal source filter,
    # deliberately not a generic "WHERE NOT redistributable".
    assert "WHERE v.source = 'UCSB'" in sql
    assert "redistributable" not in sql


def test_all_views_select_the_shared_shape() -> None:
    projected = ", ".join(f"v.{c}" for c in SHARED_PV_COLUMNS)
    for sql in (
        build_pv_preferred_sql(),
        build_pv_redistributable_sql(),
        build_pv_ucsb_sql(),
    ):
        assert projected in sql


def test_builders_thread_the_schema() -> None:
    for builder in (
        build_pv_preferred_sql,
        build_pv_redistributable_sql,
        build_pv_ucsb_sql,
    ):
        assert "mart.pv_votes" in builder("mart")


# --- frame oracles: a fabricated two-source union (D022-safe) --------------


def _row(source: str, year: int, state: str, candidate: str, votes: int) -> dict:
    return {
        "source": source, "year": year, "state": state, "candidate": candidate,
        "party": "DEMOCRAT", "candidate_votes": votes,
        "state_total_votes": votes * 2, "reliability": "exact",
    }


def _two_source_union() -> pd.DataFrame:
    """Fabricated union: an overlap key (both sources), a pre-1976 key (UCSB only),
    and a modern MIT-only key. Numbers are invented — no real UCSB data (D022)."""
    return pd.DataFrame(
        [
            _row(SOURCE_MIT, 2016, "Ohio", "A", 100),   # overlap → MIT wins
            _row(SOURCE_UCSB, 2016, "Ohio", "A", 111),  # overlap → loses to MIT
            _row(SOURCE_UCSB, 1900, "Ohio", "B", 50),   # pre-1976 → UCSB kept
            _row(SOURCE_MIT, 2016, "Iowa", "C", 70),    # MIT-only → MIT kept
        ]
    )[list(SHARED_PV_COLUMNS)]


def test_resolve_preferred_picks_mit_on_overlap_ucsb_earlier() -> None:
    resolved = resolve_preferred(_two_source_union(), build_pv_source_frame())
    got = {
        (r.year, r.state, r.candidate): (r.source, r.candidate_votes)
        for r in resolved.itertuples()
    }
    assert got[(2016, "Ohio", "A")] == (SOURCE_MIT, 100)  # MIT wins the overlap
    assert got[(1900, "Ohio", "B")] == (SOURCE_UCSB, 50)  # UCSB supplies pre-1976
    assert got[(2016, "Iowa", "C")] == (SOURCE_MIT, 70)   # MIT-only stays MIT


def test_resolve_preferred_is_single_row_per_key() -> None:
    resolved = resolve_preferred(_two_source_union(), build_pv_source_frame())
    assert len(resolved) == 3
    assert_single_row_per_key(resolved)  # does not raise


def test_resolve_preferred_fabricates_no_absent_key() -> None:
    # A key present in neither source must not appear (D005 — gaps are explicit, never
    # invented). The union has no 1948 row, so the resolved series has none.
    resolved = resolve_preferred(_two_source_union(), build_pv_source_frame())
    assert not (resolved["year"] == 1948).any()


def test_resolve_preferred_output_is_on_the_shared_shape() -> None:
    resolved = resolve_preferred(_two_source_union(), build_pv_source_frame())
    assert list(resolved.columns) == list(SHARED_PV_COLUMNS)


def test_assert_single_row_per_key_rejects_a_duplicate() -> None:
    dup = pd.concat([_two_source_union().iloc[[0]]] * 2, ignore_index=True)
    with pytest.raises(PVViewError, match="row per"):
        assert_single_row_per_key(dup)


def test_assert_union_grain_rejects_a_duplicated_natural_key() -> None:
    bad = pd.concat(
        [_two_source_union(), _two_source_union().iloc[[0]]], ignore_index=True
    )
    with pytest.raises(PVViewError, match="grain violated"):
        assert_union_grain(bad)


def test_assert_union_grain_accepts_both_overlap_rows() -> None:
    # The overlap deliberately keeps BOTH source rows for the same (year, state,
    # candidate) — that is a valid union (source is part of the key), not a grain break.
    assert_union_grain(_two_source_union())  # does not raise


def test_provenance_coverage_raises_on_unknown_source() -> None:
    union = _two_source_union()
    union.loc[0, "source"] = "ICPSR"  # a source with no pv_source row
    with pytest.raises(PVViewError, match="no pv_source row"):
        assert_provenance_coverage(union, build_pv_source_frame())


def test_resolve_preferred_raises_on_unknown_source() -> None:
    # resolve_preferred guards coverage first, so an unknown source raises rather than
    # being silently dropped by the (inner-join) precedence lookup.
    union = _two_source_union()
    union.loc[0, "source"] = "ICPSR"
    with pytest.raises(PVViewError, match="no pv_source row"):
        resolve_preferred(union, build_pv_source_frame())
