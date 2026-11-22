"""Unit tests for the ``pv_source`` reference contract (``usvote.pv.source``, #68).

Crafted units over the D017 reference table: its DDL, its seed data (the single source
of truth for per-source ``precedence_rank``/``redistributable``/``license``), and the
shape guard. All offline — the live seed into Postgres lives in
``tests/integration/test_pv_union.py``.
"""

from __future__ import annotations

import pandas as pd
import pytest

from usvote.pv.schema import PV_SCHEMA
from usvote.pv.source import (
    PV_SOURCE_COLUMNS,
    PV_SOURCE_SCHEMA,
    PV_SOURCE_TABLE,
    SOURCE_MIT,
    SOURCE_UCSB,
    PVSourceError,
    assert_pv_source_shape,
    build_pv_source_column_defs,
    build_pv_source_frame,
)

# --- the SSOT source-name literals -----------------------------------------


def test_source_literals_are_the_canonical_tags() -> None:
    # The strings both source transforms stamp on their rows. pv_source keys on these,
    # so they and the row tags cannot disagree (the reason they moved here in #68).
    assert SOURCE_MIT == "MIT"
    assert SOURCE_UCSB == "UCSB"


def test_transforms_import_the_literals_from_here() -> None:
    # The refactor's whole point: "MIT"/"UCSB" defined once. The transform modules
    # re-export the same object, so a caller of usvote.mit.transform.SOURCE_MIT is
    # unaffected while the definition lives in usvote.pv.source.
    from usvote.mit import transform as mit_transform
    from usvote.ucsb import transform as ucsb_transform

    assert mit_transform.SOURCE_MIT is SOURCE_MIT
    assert ucsb_transform.SOURCE_UCSB is SOURCE_UCSB


# --- DDL --------------------------------------------------------------------


def test_column_defs_shape() -> None:
    defs = {col[0]: col for col in build_pv_source_column_defs()}
    assert defs["source"] == ("source", "varchar", "primary key")
    # precedence_rank UNIQUE is what makes pv_preferred's DISTINCT ON tie-break
    # deterministic — two sources sharing a rank would resolve arbitrarily.
    assert "not null" in defs["precedence_rank"] and "unique" in defs["precedence_rank"]
    assert "not null" in defs["redistributable"]
    assert "not null" in defs["license"]


def test_column_defs_have_no_foreign_key() -> None:
    # pv_source is the reference side pv_votes joins *to*; it embeds no schema and has
    # no FK (which is why build_pv_source_column_defs takes no schema arg).
    for col in build_pv_source_column_defs():
        assert not any("REFERENCES" in part for part in col)


def test_column_defs_cover_exactly_the_columns() -> None:
    names = [col[0] for col in build_pv_source_column_defs()]
    assert names == list(PV_SOURCE_COLUMNS)


# --- seed data (the D017 single source of truth) ---------------------------


def test_seed_frame_is_on_the_column_shape() -> None:
    frame = build_pv_source_frame()
    assert list(frame.columns) == list(PV_SOURCE_COLUMNS)
    assert len(frame) == 2


def test_seed_encodes_mit_preferred_and_redistributable() -> None:
    frame = build_pv_source_frame().set_index("source")
    # MIT wins the overlap (lower rank) and is the only redistributable source (D016).
    assert frame.loc[SOURCE_MIT, "precedence_rank"] == 1
    assert bool(frame.loc[SOURCE_MIT, "redistributable"]) is True
    # UCSB supplies pre-1976 and loses the overlap; analysis-only pending a grant (D022).
    assert frame.loc[SOURCE_UCSB, "precedence_rank"] == 2
    assert bool(frame.loc[SOURCE_UCSB, "redistributable"]) is False


def test_seed_ranks_are_unique() -> None:
    frame = build_pv_source_frame()
    assert frame["precedence_rank"].is_unique


def test_seed_licenses_are_present_and_distinct() -> None:
    frame = build_pv_source_frame().set_index("source")
    assert frame.loc[SOURCE_MIT, "license"]
    assert frame.loc[SOURCE_UCSB, "license"]
    assert frame.loc[SOURCE_MIT, "license"] != frame.loc[SOURCE_UCSB, "license"]


# --- assert_pv_source_shape (boundary guard) -------------------------------


def test_shape_guard_accepts_the_seed() -> None:
    assert_pv_source_shape(build_pv_source_frame())  # does not raise


def test_shape_guard_rejects_wrong_columns() -> None:
    bad = build_pv_source_frame().drop(columns=["license"])
    with pytest.raises(PVSourceError, match="pv_source columns"):
        assert_pv_source_shape(bad)


def test_shape_guard_rejects_null_attribute() -> None:
    bad = build_pv_source_frame()
    bad.loc[bad["source"] == SOURCE_UCSB, "license"] = None
    with pytest.raises(PVSourceError, match="null"):
        assert_pv_source_shape(bad)


def test_shape_guard_rejects_duplicate_precedence_rank() -> None:
    # A duplicated rank would make pv_preferred's tie-break non-deterministic — the
    # guard fails before any DDL rather than leaving the DB UNIQUE to catch it later.
    bad = pd.DataFrame(
        [
            {"source": "MIT", "precedence_rank": 1, "redistributable": True,
             "license": "a"},
            {"source": "UCSB", "precedence_rank": 1, "redistributable": False,
             "license": "b"},
        ]
    )[list(PV_SOURCE_COLUMNS)]
    with pytest.raises(PVSourceError, match="precedence_rank must be unique"):
        assert_pv_source_shape(bad)


def test_table_name_is_named_apart_from_the_fact() -> None:
    # The reference table must not be confused with the raw-union fact table.
    from usvote.pv.schema import PV_TABLE

    assert PV_SOURCE_TABLE == "pv_source"
    assert PV_SOURCE_TABLE != PV_TABLE


def test_source_schema_aliases_the_one_pv_schema() -> None:
    # pv_source co-locates with pv_votes; PV_SOURCE_SCHEMA is the SAME object as
    # PV_SCHEMA, not a second "dwh" literal — so the view's JOIN and this loader's
    # target can never drift to different schemas.
    assert PV_SOURCE_SCHEMA == PV_SCHEMA
