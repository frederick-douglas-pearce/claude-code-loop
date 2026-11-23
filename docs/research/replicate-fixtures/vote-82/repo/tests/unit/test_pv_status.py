"""Unit tests for :mod:`usvote.pv.status` — the shared PV-absence roster contract (#36).

Source-neutral, mirroring ``test_pv_load.py``'s treatment of :mod:`usvote.pv.schema`.
These lock the parts #37 (the ``dwh.pv_state_status`` DDL), #38 (which re-runs the
two-way assert after narrowing candidates) and E6 (the MIT roster backfill) all depend
on — in particular that the assert is scoped by an explicit ``source`` and ``years``
rather than by whatever happens to be in the frame.
"""

from __future__ import annotations

import pandas as pd
import pytest

from usvote.pv.status import (
    PV_ABSENCE_STATUSES,
    PV_STATUS_LEGISLATURE_CHOSEN,
    PV_STATUS_NOT_PARTICIPATING,
    PV_STATUS_POPULAR_VOTE,
    PV_STATUS_VALUES,
    ROSTER_COLUMNS,
    ROSTER_TABLE,
    PVRosterError,
    assert_roster_covers_facts,
    assert_roster_shape,
    assert_unique_roster_grain,
    build_status_column_defs,
)


def _roster(*rows: tuple[str, int, str | None, str, str | None]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            dict(zip(ROSTER_COLUMNS, row, strict=True))
            for row in rows
        ]
    )


def _facts(*rows: tuple[str, int, str]) -> pd.DataFrame:
    return pd.DataFrame(
        [{"source": s, "year": y, "state": st} for s, y, st in rows]
    )


class TestEnum:
    def test_exactly_three_statuses(self) -> None:
        """D024 §4 admits three and no ``unknown``/``unparsed`` bucket."""
        assert PV_STATUS_VALUES == (
            PV_STATUS_POPULAR_VOTE,
            PV_STATUS_LEGISLATURE_CHOSEN,
            PV_STATUS_NOT_PARTICIPATING,
        )

    def test_absence_statuses_are_the_two_non_popular_vote_values(self) -> None:
        assert {
            PV_STATUS_LEGISLATURE_CHOSEN,
            PV_STATUS_NOT_PARTICIPATING,
        } == PV_ABSENCE_STATUSES

    def test_parser_status_string_matches_the_shared_enum(self) -> None:
        """The parser emits its own literal; a drift would split the roster in two."""
        from usvote.ucsb.parse import STATUS_LEGISLATURE_CHOSEN

        assert STATUS_LEGISLATURE_CHOSEN == PV_STATUS_LEGISLATURE_CHOSEN


class TestDDL:
    def test_check_constraint_is_built_from_the_enum(self) -> None:
        defs = build_status_column_defs()
        status = next(c for c in defs if c[0] == "pv_status")
        for value in PV_STATUS_VALUES:
            assert f"'{value}'" in status[-1]

    def test_natural_key_is_unique_and_state_has_an_fk(self) -> None:
        defs = build_status_column_defs("dwh")
        assert ("CONSTRAINT", f"{ROSTER_TABLE}_natural_key", "UNIQUE",
                "(source, year, state)") in defs
        state = next(c for c in defs if c[0] == "state")
        assert "REFERENCES dwh.state" in state

    def test_note_is_nullable(self) -> None:
        """Null on every ordinary row by design; only absence rows carry prose."""
        note = next(c for c in build_status_column_defs() if c[0] == "note")
        assert "not null" not in " ".join(note).lower()


class TestShape:
    def test_valid_roster_passes(self) -> None:
        assert_roster_shape(
            _roster(("UCSB", 1900, "Ohio", PV_STATUS_POPULAR_VOTE, None))
        )

    def test_unknown_status_raises(self) -> None:
        with pytest.raises(PVRosterError, match="unknown pv_status"):
            assert_roster_shape(_roster(("UCSB", 1900, "Ohio", "unparsed", None)))

    def test_null_key_raises(self) -> None:
        with pytest.raises(PVRosterError, match="null value"):
            assert_roster_shape(_roster(("UCSB", 1900, None, PV_STATUS_POPULAR_VOTE, None)))

    def test_wrong_column_order_raises(self) -> None:
        frame = _roster(("UCSB", 1900, "Ohio", PV_STATUS_POPULAR_VOTE, None))
        with pytest.raises(PVRosterError, match="!= roster shape"):
            assert_roster_shape(frame[list(reversed(ROSTER_COLUMNS))])

    def test_duplicate_grain_raises(self) -> None:
        frame = _roster(
            ("UCSB", 1900, "Ohio", PV_STATUS_POPULAR_VOTE, None),
            ("UCSB", 1900, "Ohio", PV_STATUS_NOT_PARTICIPATING, "x"),
        )
        with pytest.raises(PVRosterError, match="grain violated"):
            assert_unique_roster_grain(frame)

    def test_same_state_and_year_across_sources_is_not_a_duplicate(self) -> None:
        """``source`` is part of the key — both sources keep their own roster (D021)."""
        assert_unique_roster_grain(
            _roster(
                ("UCSB", 1900, "Ohio", PV_STATUS_POPULAR_VOTE, None),
                ("MIT", 1900, "Ohio", PV_STATUS_POPULAR_VOTE, None),
            )
        )


class TestTwoWayAssert:
    def test_consistent_pair_passes(self) -> None:
        assert_roster_covers_facts(
            _facts(("UCSB", 1900, "Ohio")),
            _roster(
                ("UCSB", 1900, "Ohio", PV_STATUS_POPULAR_VOTE, None),
                ("UCSB", 1900, "Iowa", PV_STATUS_LEGISLATURE_CHOSEN, "prose"),
            ),
            source="UCSB",
            years={1900},
        )

    def test_popular_vote_state_with_no_facts_raises(self) -> None:
        with pytest.raises(PVRosterError, match="have no vote rows"):
            assert_roster_covers_facts(
                _facts(("UCSB", 1900, "Ohio")),
                _roster(
                    ("UCSB", 1900, "Ohio", PV_STATUS_POPULAR_VOTE, None),
                    ("UCSB", 1900, "Iowa", PV_STATUS_POPULAR_VOTE, None),
                ),
                source="UCSB",
                years={1900},
            )

    def test_absence_state_with_facts_raises(self) -> None:
        with pytest.raises(PVRosterError, match="nevertheless have vote rows"):
            assert_roster_covers_facts(
                _facts(("UCSB", 1900, "Ohio")),
                _roster(("UCSB", 1900, "Ohio", PV_STATUS_LEGISLATURE_CHOSEN, "prose")),
                source="UCSB",
                years={1900},
            )

    def test_phantom_fact_state_raises(self) -> None:
        """The check a sum validator cannot replace."""
        with pytest.raises(PVRosterError, match="absent from"):
            assert_roster_covers_facts(
                _facts(("UCSB", 1900, "Ohio"), ("UCSB", 1900, "Atlantis")),
                _roster(("UCSB", 1900, "Ohio", PV_STATUS_POPULAR_VOTE, None)),
                source="UCSB",
                years={1900},
            )

    def test_empty_roster_for_an_in_scope_year_uses_its_own_error_class(self) -> None:
        class Distinct(RuntimeError):
            pass

        with pytest.raises(Distinct, match="pipeline-sequencing"):
            assert_roster_covers_facts(
                _facts(("UCSB", 1900, "Ohio")),
                _roster(("UCSB", 1896, "Ohio", PV_STATUS_POPULAR_VOTE, None)),
                source="UCSB",
                years={1900},
                empty_roster_error_cls=Distinct,
            )

    def test_scoping_is_by_parameter_not_inferred_from_the_frames(self) -> None:
        """Both sources' rows share the table (D021); a partial run must not indict."""
        facts = _facts(("UCSB", 1900, "Ohio"), ("MIT", 1976, "Ohio"))
        roster = _roster(
            ("UCSB", 1900, "Ohio", PV_STATUS_POPULAR_VOTE, None),
            ("UCSB", 1904, "Iowa", PV_STATUS_POPULAR_VOTE, None),
        )
        # MIT's 1976 row is out of source scope; UCSB's 1904 roster row is out of
        # year scope. Neither is a violation of the 1900 UCSB run.
        assert_roster_covers_facts(facts, roster, source="UCSB", years={1900})

    def test_error_class_is_overridable_so_sources_raise_their_own_type(self) -> None:
        from usvote.ucsb.transform import UCSBRosterError

        with pytest.raises(UCSBRosterError):
            assert_roster_covers_facts(
                _facts(("UCSB", 1900, "Atlantis")),
                _roster(("UCSB", 1900, "Ohio", PV_STATUS_POPULAR_VOTE, None)),
                source="UCSB",
                years={1900},
                error_cls=UCSBRosterError,
            )
