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
    ERAS, era_by_date, era_by_marker, installed_version,
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

    def test_an_unknown_cap_is_ignored_rather_than_crashing(self):
        late = ERAS[-1][1]
        self.assertEqual(era_by_date(late, cap="9.9.9"), era_by_date(late))

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
