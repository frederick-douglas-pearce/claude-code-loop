#!/usr/bin/env python3
"""Fixture tests for `budget_stats.py`'s engine-era attribution.

NOT part of the shipped suite -- lives under `docs/research/`, not `tests/`, so
`python3 -m unittest discover -s tests` does not pick it up, per the scope
brake's rule that a guard on analysis infrastructure is `tech-debt` and never
ships in a release.

WHY THIS MODULE EXISTS. `budget_stats.py` had no tests, and era attribution was
a single boolean against one hardcoded date (`REINSTALL = "2026-08-21"`). That
was correct in a two-era world and silently wrong from the moment a third
release landed: every 0.2.1 row and then every 0.3.0 row attributed to "0.2.0".
Era is what the DiD in `cost-model-design.md` identifies on, so a wrong era is
not a cosmetic defect -- it is the independent variable.

The cases below pin MECHANISM, not today's numbers: that a later date resolves
to a later era, that the cap binds, that a marker is a bound rather than an era.
A test asserting `era_by_date("2026-09-12") == "0.3.0"` would pass for an
implementation hardcoded to 0.3.0 and go stale at the next release in exactly
the way this module exists to prevent.

    python3 docs/research/test_budget_stats.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from budget_stats import (  # noqa: E402
    ERAS, era_by_date, era_by_marker, installed_version, cap_span,
    check_era_order,
)

VERSIONS = [v for v, _, _ in ERAS]


class EraByDateTests(unittest.TestCase):
    def test_every_release_is_reachable(self):
        """REGRESSION: the old boolean could only ever return two of these."""
        reached = {era_by_date(start) for _, start, _ in ERAS if start}
        reached.add(era_by_date("1970-01-01"))
        self.assertEqual(reached, set(VERSIONS))

    def test_eras_advance_monotonically_with_date(self):
        dates = [s for _, s, _ in ERAS if s]
        seen = [VERSIONS.index(era_by_date(d)) for d in sorted(dates)]
        self.assertEqual(seen, sorted(seen))
        self.assertEqual(len(set(seen)), len(seen))   # no two dates collapse

    def test_a_date_before_any_release_is_the_earliest_era(self):
        self.assertEqual(era_by_date("1970-01-01"), ERAS[0][0])

    def test_the_day_of_a_release_counts_as_that_release(self):
        for version, start, _ in ERAS:
            if start:
                self.assertEqual(era_by_date(start), version)


class InstalledCapTests(unittest.TestCase):
    """The cap is what keeps a held-back control repo out of the treated arm.

    `agentfluent` and `claude-code-sessions` are deliberately pinned to 0.2.0.
    A pure date rule marches them through every later release, coding the
    untreated group as treated -- which does not make the DiD noisier, it
    inverts it.
    """

    def test_cap_holds_a_late_row_at_the_installed_version(self):
        late = ERAS[-1][1]
        self.assertEqual(era_by_date(late), ERAS[-1][0])          # uncapped
        self.assertEqual(era_by_date(late, cap="0.2.0"), "0.2.0")  # capped

    def test_cap_never_advances_a_row_it_should_not(self):
        """A cap is a ceiling, never a floor: it must not promote an early row."""
        early = "1970-01-01"
        self.assertEqual(era_by_date(early, cap=ERAS[-1][0]), ERAS[0][0])

    def test_an_unknown_cap_raises_rather_than_being_silently_dropped(self):
        """INVERTED 2026-09-12. This case previously asserted the opposite, and
        asserting the opposite is what made it a bug-preserving test.

        A cap the table does not know is the ONE point where this module can
        mechanically detect the staleness its own docstring warns about. Dropping
        it silently left `summarize_era` printing "capped here" while no cap was
        applied -- so a repo held on an unlisted version read as treated, which
        is the DiD inversion the cap exists to prevent. Loud is the only safe
        direction, and a released version missing from ERAS is a real defect.
        """
        with self.assertRaises(ValueError):
            era_by_date(ERAS[-1][1], cap="9.9.9")

    def test_an_unparseable_date_resolves_to_the_earliest_era(self):
        """`parse()` writes "?" for a header with no ISO date. "?" is 0x3F, above
        "2", so a naive `>=` put the sentinel in the NEWEST era -- coding an
        undated entry as fully treated, worse than the boolean it replaced."""
        for bad in ("?", "", "n/a", "2026-9-1"):
            self.assertEqual(era_by_date(bad), ERAS[0][0])
            self.assertEqual(era_by_date(bad, cap=ERAS[-1][0]), ERAS[0][0])


class EraTableIntegrityTests(unittest.TestCase):
    """`era_by_date` scans in list order and breaks at the first future row, so
    a row appended out of date order silently mis-files every later entry. The
    docstring tells maintainers to add a row at every release, so the edit that
    triggers this is the one the module invites."""

    def test_the_shipped_table_is_ordered(self):
        self.assertTrue(check_era_order(ERAS))

    def test_an_out_of_order_row_is_rejected(self):
        scrambled = list(ERAS)
        scrambled.insert(1, ("9.9.9", "2099-01-01", None))
        with self.assertRaises(ValueError):
            check_era_order(scrambled)

    def test_a_backported_row_appended_at_the_end_is_rejected(self):
        """The realistic edit: a release discovered missing and tacked on."""
        with self.assertRaises(ValueError):
            check_era_order(list(ERAS) + [("0.2.2", "2026-08-30", None)])

    # NOT COVERED, and named here rather than left to be discovered: these cases
    # exercise `check_era_order` as a function. Deleting its call at import is a
    # surviving mutation -- nothing fails, because the shipped table is valid, so
    # there is no bad data for the missing call to have caught. Pinning the call
    # would mean asserting on module source, which is a worse test than none.
    # The import-time invocation is belt-and-braces over the function above; the
    # function is what these guard.


class InstalledVersionPathTests(unittest.TestCase):
    """`projectPath` matching needs a separator boundary, not a raw prefix."""

    def test_a_sibling_sharing_a_path_prefix_does_not_inherit_the_cap(self):
        """A repo absent from installed_plugins.json must resolve to None, not
        to a neighbour's version -- which would cap it at an era it never ran
        while the read-out reported that version as "installed now" for it."""
        registered = "/home/fdpearce/Documents/Projects/git/claude-code-loop"
        if installed_version(registered + "/.claude/loop") is None:
            self.skipTest("fixture assumes this repo is registered")
        self.assertIsNone(
            installed_version(registered + "-EXPERIMENT/.claude/loop"))

    def test_the_registered_repo_itself_still_resolves(self):
        registered = "/home/fdpearce/Documents/Projects/git/claude-code-loop"
        if installed_version(registered + "/.claude/loop") is None:
            self.skipTest("fixture assumes this repo is registered")
        self.assertIsNotNone(installed_version(registered + "/.claude/loop"))


class CapSpanTests(unittest.TestCase):
    """The cap must reach the marker column too, not only the date column."""

    def test_a_span_is_truncated_at_the_installed_version(self):
        span = "|".join(v for v, _, _ in ERAS[:3])
        self.assertEqual(cap_span(span, ERAS[1][0]), "|".join(v for v, _, _ in ERAS[:2]))

    def test_a_control_never_advertises_an_era_it_never_installed(self):
        """The regression: the marker bucket ran uncapped, so a repo pinned to an
        early release still displayed a span naming later ones."""
        span = "|".join(v for v, _, _ in ERAS)
        capped = cap_span(span, ERAS[1][0]).split("|")
        for v, _, _ in ERAS[2:]:
            self.assertNotIn(v, capped)

    def test_no_cap_leaves_the_span_alone(self):
        span = "|".join(v for v, _, _ in ERAS[:2])
        self.assertEqual(cap_span(span, None), span)

    def test_an_unknown_cap_leaves_the_span_rather_than_emptying_it(self):
        span = "|".join(v for v, _, _ in ERAS[:2])
        self.assertEqual(cap_span(span, "9.9.9"), span)

    def test_no_cap_means_no_capping(self):
        late = ERAS[-1][1]
        self.assertEqual(era_by_date(late, cap=None), ERAS[-1][0])

    def test_installed_version_returns_none_off_a_path_it_cannot_resolve(self):
        """Default to reporting UNKNOWN, never to guessing a version."""
        self.assertIsNone(installed_version("/nonexistent/path/xyzzy/.claude/loop"))


class EraByMarkerTests(unittest.TestCase):
    def test_no_vocabulary_reads_as_the_earliest_era(self):
        self.assertEqual(era_by_marker("- Budget: subagent-runs=3"), ERAS[0][0])

    def test_a_marker_resolves_to_at_least_its_own_era(self):
        for version, _, marker in ERAS:
            if marker is None:
                continue
            sample = marker.pattern.split("|")[0]
            self.assertIn(version, era_by_marker("- Budget: " + sample).split("|"))

    def test_an_undetectable_release_widens_the_bound_rather_than_vanishing(self):
        """0.2.1 writes no vocabulary. It must appear in a span, not be dropped.

        The failure this refuses is the tempting one: silently attributing a
        marker-less release to the previous era, which is a false exact answer
        where the honest answer is a range.
        """
        undetectable = [i for i, (_, _, m) in enumerate(ERAS) if m is None and i]
        self.assertTrue(undetectable, "fixture assumes at least one such release")
        for i in undetectable:
            prev = ERAS[i - 1]
            if prev[2] is None:
                continue
            sample = prev[2].pattern.split("|")[0]
            span = era_by_marker("- Budget: " + sample).split("|")
            self.assertIn(ERAS[i][0], span)
            self.assertIn(prev[0], span)

    def test_a_later_marker_outranks_an_earlier_one_in_the_same_entry(self):
        """The plugin repo writes new vocabulary while running the old engine, so
        entries carrying both must resolve to the later bound, not the earlier."""
        early = ERAS[1][2].pattern.split("|")[0]
        late = ERAS[-1][2].pattern.split("|")[0]
        both = era_by_marker("- Budget: %s and %s" % (early, late))
        self.assertIn(ERAS[-1][0], both.split("|"))
        self.assertNotIn(ERAS[1][0], both.split("|"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
