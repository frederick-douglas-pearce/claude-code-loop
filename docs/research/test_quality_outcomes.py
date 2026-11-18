#!/usr/bin/env python3
"""Fixture tests for `quality_outcomes.py` (#272).

NOT part of the shipped suite -- lives under `docs/research/`, not `tests/`, so
`python3 -m unittest discover -s tests` does not pick it up; `TEST_CMD`'s second
half runs it, and CI does not (#286).

The cases pin MECHANISM, not today's numbers: that a window boundary is
exclusive at the merge and inclusive at day 14, that an open window never reads
as a count, that a merge commit's files come from its first parent, that a
stop's answer is not a second stop, that an unreadable journal is `unknown`
rather than zero, and that a comment's marker is matched on repo AND PR.

The git fixtures are hermetic: a temporary HOME, no system config, and fixed
author/committer identities and dates, so the result does not depend on the
machine's git configuration.

    python3 docs/research/test_quality_outcomes.py
"""
import io
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import quality_outcomes as q  # noqa: E402

DAY = 86400
T0 = q.epoch("2026-06-01T12:00:00+00:00")


class Repo:
    """A throwaway git repo whose commits carry chosen committer dates."""

    def __init__(self, path):
        self.path = path
        self.env = dict(os.environ, HOME=path, GIT_CONFIG_NOSYSTEM="1",
                        GIT_CONFIG_GLOBAL=os.devnull,
                        GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
                        GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com")
        self.git("init", "-q", "-b", "main")

    def git(self, *args, when=None):
        env = dict(self.env)
        if when is not None:
            env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = f"@{when} +0000"
        return subprocess.run(["git", "-C", self.path, *args], env=env, check=True,
                              capture_output=True, text=True).stdout.strip()

    def commit(self, msg, files, when):
        for name in files:
            full = os.path.join(self.path, name)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "a") as f:
                f.write(msg + "\n")
            self.git("add", name)
        self.git("commit", "-q", "-m", msg, when=when)
        return self.git("rev-parse", "HEAD")

    def merge(self, branch, msg, when):
        self.git("merge", "-q", "--no-ff", "-m", msg, branch, when=when)
        return self.git("rev-parse", "HEAD")


class GitCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Repo(self.tmp.name)
        self.repo.commit("root", ["a.py", "b.py"], T0 - 10 * DAY)

    def tearDown(self):
        self.tmp.cleanup()

    def hist(self):
        return q.History(self.tmp.name, "main")


class LocateTests(GitCase):
    def test_squash_subject_is_found(self):
        sha = self.repo.commit("chore: thing (#12)", ["a.py"], T0)
        self.assertEqual(self.hist().locate(12), (sha, T0))

    def test_merge_commit_subject_is_found(self):
        self.repo.git("checkout", "-q", "-b", "feat")
        self.repo.commit("work", ["b.py"], T0 - DAY)
        self.repo.git("checkout", "-q", "main")
        sha = self.repo.merge("feat", "Merge pull request #7 from x/feat", T0)
        self.assertEqual(self.hist().locate(7), (sha, T0))

    def test_ledger_sha_wins_but_only_if_its_message_names_the_pr(self):
        """A SHA from the row is trusted only when the commit names the PR."""
        real = self.repo.commit("fix: real (#30)", ["a.py"], T0)
        other = self.repo.commit("unrelated", ["b.py"], T0 + DAY)
        self.assertEqual(self.hist().locate(30, [real[:7]])[0], real)
        # a row SHA whose commit does not name #30 falls through to the subject
        self.assertEqual(self.hist().locate(30, [other[:7]])[0], real)

    def test_unlocatable_pr_is_none(self):
        self.assertIsNone(self.hist().locate(999))

    def test_pr_number_prefix_does_not_match(self):
        self.repo.commit("chore: x (#123)", ["a.py"], T0)
        self.assertIsNone(self.hist().locate(12))


class FixupTests(GitCase):
    def test_window_is_exclusive_at_merge_and_inclusive_at_day_14(self):
        sha = self.repo.commit("feat (#1)", ["a.py"], T0)
        self.repo.commit("same second", ["a.py"], T0)            # not after merge
        self.repo.commit("day 14", ["a.py"], T0 + 14 * DAY)      # inclusive
        self.repo.commit("day 14 + 1s", ["a.py"], T0 + 14 * DAY + 1)
        n, open_ = self.hist().fixups(sha, T0, now=T0 + 30 * DAY)
        self.assertEqual((n, open_), (1, False))

    def test_unrelated_file_is_not_a_fixup(self):
        sha = self.repo.commit("feat (#1)", ["a.py"], T0)
        self.repo.commit("other file", ["b.py"], T0 + DAY)
        self.assertEqual(self.hist().fixups(sha, T0, now=T0 + 30 * DAY)[0], 0)

    def test_open_window_reports_pending_never_a_bare_count(self):
        sha = self.repo.commit("feat (#1)", ["a.py"], T0)
        self.repo.commit("touch", ["a.py"], T0 + DAY)
        got = q.fmt(self.hist().fixups(sha, T0, now=T0 + 2 * DAY))
        self.assertEqual(got, "pending(1)")

    def test_merge_commit_files_come_from_its_first_parent(self):
        """A merge's own change set is what the branch brought in, nothing else."""
        self.repo.git("checkout", "-q", "-b", "feat")
        self.repo.commit("branch work", ["b.py"], T0 - DAY)
        self.repo.git("checkout", "-q", "main")
        sha = self.repo.merge("feat", "Merge pull request #2 from x/feat", T0)
        self.assertEqual(self.hist().files(sha), {"b.py"})

    def test_a_later_merge_touching_the_files_counts_once(self):
        sha = self.repo.commit("feat (#1)", ["a.py"], T0)
        self.repo.git("checkout", "-q", "-b", "fix")
        self.repo.commit("fix 1", ["a.py"], T0 + DAY)
        self.repo.commit("fix 2", ["a.py"], T0 + DAY)
        self.repo.git("checkout", "-q", "main")
        self.repo.merge("fix", "Merge pull request #3 from x/fix", T0 + 2 * DAY)
        # the branch's own commits are not first-parent, so the merge is one fix-up
        self.assertEqual(self.hist().fixups(sha, T0, now=T0 + 30 * DAY)[0], 1)


QUEUE = """# Loop run: r
_mode: calibration_
_plan-gate: always_

| # | Issue | Route | Status | Depends on | PR | Notes |
|---|-------|-------|--------|-----------|----|----|
| 1 | #10 thing | code | done | — | #20 (merged abc1234) | |
| 2 | #11 other | code | routed | — | — | |
| 3 | #12 split | code | done | — | #21; #22 | merged def5678 |

| PR | label | Status |
|----|-------|--------|
| #106 | tech-debt | done |
"""


class QueueTests(unittest.TestCase):
    def test_columns_are_read_by_header_name(self):
        """The second table has no PR-column-at-position-6; it must not be misread."""
        rows = q.done_rows(QUEUE)
        self.assertEqual([(i, p) for i, p, _ in rows], [(10, [20]), (12, [21, 22]), (None, [106])])
        self.assertIn("abc1234", rows[0][2])
        self.assertIn("def5678", rows[1][2])

    def test_posture_reads_the_header_and_absent_is_none(self):
        self.assertEqual(q.posture(QUEUE), ("calibration", "always"))
        self.assertEqual(q.posture("# Loop run\n_mode: calibration_\n"), ("calibration", None))


JOURNAL = """# Progress journal: r

## 2026-01-01T00:00:00Z — init
- Run initialized. → STOPPED

## 2026-01-01T01:00:00Z — #10 plan gate
- Plan-gate: material (step added) → STOPPED

## 2026-01-01T02:00:00Z — #10 plan gate, human answers
- answered. → STOPPED was the previous block

## 2026-01-01T03:00:00Z — #10 PR #20 code review, round 1 → STOPPED (design-question finding)
- Code-review: round 1 (main...abc) — 3 findings, claims=1

## 2026-01-01T04:00:00Z — #10 PR #20 round-1 stop, human decisions
- fix applied

## 2026-01-01T05:00:00Z — #10 PR #20 code review, round 3 (human-authorized) → STOPPED
- Code-review: round 3 (a..b) — 1 finding, claims=0
- gate-error: security — /security-review — fatal: ambiguous argument

## 2026-01-01T05:30:00Z — #10 acceptance gate
- Merge gate: STOPPED for the owner (mode: calibration).

## 2026-01-01T06:00:00Z — #10 (code) — iteration complete
- Plan-gate: material (step added) → STOPPED
- gate-error: security — /security-review — fatal: ambiguous argument
- Budget: subagent-runs=4 · gate-rounds=architect=1,code-review=3 · wall-clock=1h · tokens=deferred

## 2026-01-01T07:00:00Z — #11 something odd → STOPPED

## 2026-01-01T08:00:00Z — #11 plan gate
- Plan-gate: n/a: architect skipped (docs)

## 2026-01-01T09:00:00Z — #12 plan gate
- no plan-gate line here

## 2026-01-01T10:00:00Z — PR #99 cleanup → STOPPED

## 2026-01-01T11:00:00Z — Post 1 editorial pass (owner-directed)
"""


class EscalationTests(unittest.TestCase):
    def setUp(self):
        self.per, self.unattributed = q.escalations(JOURNAL, "calibration", "always")

    def test_structured_columns(self):
        c = self.per[10]
        self.assertEqual(c["gate-error"], 1, "the summary's restatement is not a second error")
        self.assertEqual(c["plan-material"], 1, "the summary's restatement is not a second stop")
        self.assertEqual(c["review-past-cap"], 1, "round 3 is one round past the cap of 2")

    def test_stop_split(self):
        c = self.per[10]
        self.assertEqual(c["scope-ruling"], 1)
        self.assertEqual(c["human-option"], 1, "round 3; answers and summaries are not stops")
        self.assertEqual(c["routine"], 2, "the plan-gate stop and the calibration merge stop")
        self.assertEqual(self.per[11]["unclassified"], 1)

    def test_routine_needs_the_posture_that_owes_it(self):
        per, _ = q.escalations(JOURNAL, "escalation-only", "conditional")
        self.assertEqual(per[10]["routine"], 0)
        self.assertEqual(per[10]["human-option"], 3)

    def test_issue_without_a_plan_gate_line_is_unknown(self):
        self.assertIsNone(self.per[12])

    def test_run_without_a_plan_gate_header_is_unknown(self):
        per, _ = q.escalations(JOURNAL, "calibration", None)
        self.assertTrue(all(v is None for v in per.values()))

    def test_pr_reference_is_not_an_issue_and_run_level_blocks_are_skipped(self):
        self.assertNotIn(99, self.per)
        self.assertEqual(self.unattributed, 2, "the PR-only block and the post block")


def comment(when, body):
    return {"created_at": when, "body": body}


class FindingTests(unittest.TestCase):
    MERGE = q.epoch("2026-12-01T00:00:00Z")

    def found(self):
        return q.findings([
            comment("2026-12-02T00:00:00Z",
                    "## F300 — x\n**Attributed-to:** owner/repo#5\n**Attributed-to:** owner/other#6"),
            comment("2026-12-03T00:00:00Z", "## F301\n**Attributed-to:** OWNER/Repo#5"),
            comment("2026-12-04T00:00:00Z", "## F302\n**Attributed-to:** owner/other#5"),
            comment("2026-12-05T00:00:00Z", "## F303\n**Attributed-to:** none (bookkeeping)"),
            comment("2026-12-06T00:00:00Z", "## F304 no marker at all"),
            comment("2026-12-30T00:00:00Z", "## F305\n**Attributed-to:** owner/repo#5"),
        ])

    def test_marker_matches_repo_and_pr_case_insensitively_within_the_window(self):
        got = q.fcount(self.found(), "owner/repo", 5, self.MERGE, now=self.MERGE + 60 * DAY)
        self.assertEqual(got, 2, "F302 names another repo; F305 is past day 14")

    def test_open_window_is_pending(self):
        got = q.fcount(self.found(), "owner/repo", 5, self.MERGE, now=self.MERGE + 3 * DAY)
        self.assertEqual(got, "pending(2)")

    def test_pre_adoption_pr_is_unknown_or_a_lower_bound(self):
        early = q.epoch(q.ADOPTION) - 5 * DAY
        self.assertEqual(q.fcount([], "owner/repo", 5, early, now=early + 60 * DAY), "unknown")
        late_hit = [(early + DAY, ["owner/repo#5"], True)]
        self.assertEqual(q.fcount(late_hit, "owner/repo", 5, early, now=early + 60 * DAY), ">=1")

    def test_unmarked_comments_are_visible(self):
        marked = [m for _, _, m in self.found()]
        self.assertEqual(marked, [True, True, True, True, False, True])


class MedianTests(unittest.TestCase):
    def test_unknowns_are_counted_in_the_denominator_not_the_median(self):
        self.assertEqual(q.median_line([0, 2, 4, "unknown", "pending(1)"]),
                         "2 (3/5 known), nonzero 2/3")

    def test_nothing_known(self):
        self.assertEqual(q.median_line(["unknown"]), "n/a (0/1 known)")


class ReportTests(GitCase):
    def test_end_to_end_on_a_fixture_ledger(self):
        sha = self.repo.commit("feat: x (#20)", ["a.py"], T0)
        self.repo.commit("follow-up", ["a.py"], T0 + DAY)
        run = os.path.join(self.tmp.name, ".claude", "loop", "r")
        os.makedirs(run)
        with open(os.path.join(run, "queue.md"), "w") as f:
            f.write(QUEUE)
        with open(os.path.join(run, "progress.md"), "w") as f:
            f.write(JOURNAL)
        out = io.StringIO()
        q.report(self.tmp.name, "main", T0 + 30 * DAY, None, None, out=out)
        text = out.getvalue()
        self.assertIn(f"r | 20 | 10 | 2026-06-01 | 1 | unknown", text)
        self.assertIn("r | 21 | 12 | unknown | unknown | unknown", text)
        self.assertIn("r | #12 | " + " | ".join(["unknown"] * len(q.COLUMNS)), text)
        self.assertIn("every F-comment cell is unknown", text)
        self.assertTrue(sha)


if __name__ == "__main__":
    unittest.main()
