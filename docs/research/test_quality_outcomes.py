#!/usr/bin/env python3
"""Fixture tests for `quality_outcomes.py` (#272).

NOT part of the shipped suite -- lives under `docs/research/`, not `tests/`, so
`python3 -m unittest discover -s tests` does not pick it up; `TEST_CMD`'s second
half runs it, and CI does not (#286).

The cases pin MECHANISM, not today's numbers: that a fix-up window is exclusive
at the merge and inclusive at day 14, that an open window never reads as a
count, that a stop's answer is not a second stop, that the escalation partition
gives one stop per block, that a journal with no `- Plan-gate:` line, a run
with no `plan-gate:` header, or a run with no journal is `unknown` rather than
zero, and that `fcount` matches a marker on repo AND PR.

The fixture commits do not depend on the machine's git config files or on
inherited `GIT_*` variables: a temporary HOME, no system or global config, and
fixed identities and dates.

    python3 docs/research/test_quality_outcomes.py
"""
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import quality_outcomes as q  # noqa: E402

DAY = 86400
T0 = q.epoch("2026-06-01T12:00:00+00:00")


class Repo:
    """A throwaway git repo whose commits carry chosen committer dates."""

    def __init__(self, path):
        self.path = path
        base = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        self.env = dict(base, HOME=path, GIT_CONFIG_NOSYSTEM="1",
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

    def test_an_inherited_git_dir_does_not_redirect_the_read(self):
        """Inside a git hook GIT_DIR names the hook's repo; the script must read REPO."""
        sha = self.repo.commit("chore: thing (#12)", ["a.py"], T0)
        other = tempfile.TemporaryDirectory()
        self.addCleanup(other.cleanup)
        Repo(other.name).commit("elsewhere (#99)", ["z.py"], T0)
        with mock.patch.dict(os.environ, {"GIT_DIR": os.path.join(other.name, ".git")}):
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
- Code-review: round 1 (a..b) — 1 finding, claims=0
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

    def test_attributes(self):
        c = self.per[10]
        self.assertEqual(c["plan-material"], 1, "the summary's restatement is not a second stop")
        self.assertEqual(c["review-past-cap"], 1, "the Budget line's code-review=3 is one past 2")

    def test_partition_gives_one_stop_per_block(self):
        c = self.per[10]
        # round 3's block carries a gate-error line AND a stop word: gate-error only
        self.assertEqual(c["gate-error"], 1, "per block; the summary's restatement is not a second")
        self.assertEqual(c["human-option"], 0, "round 3 went to gate-error, not here as well")
        self.assertEqual(c["scope-ruling"], 1)
        self.assertEqual(c["routine"], 2, "the plan-gate stop and the calibration merge stop")
        self.assertEqual(self.per[11]["unclassified"], 1)

    def test_escalations_total_is_the_issues_definition(self):
        c = self.per[10]
        self.assertEqual(c["escalations"], c["gate-error"] + c["scope-ruling"] + c["human-option"])
        self.assertEqual(c["escalations"], 2)
        self.assertEqual(self.per[11]["escalations"], 0, "unclassified is not summed")

    def test_one_block_with_every_signal_adds_exactly_one(self):
        j = ("## t — #5 plan gate\n- Plan-gate: n/a: architect skipped\n\n"
             "## t — #5 code review round 1 → STOPPED (design-question finding)\n"
             "- gate-error: x — y — z\n- Plan-gate: material (a) → STOPPED\n")
        per, _ = q.escalations(j, "calibration", "always")
        self.assertEqual(per[5]["escalations"], 1)
        self.assertEqual(per[5]["gate-error"], 1)
        self.assertEqual(per[5]["scope-ruling"], 0)

    def test_routine_needs_the_posture_that_owes_it(self):
        per, _ = q.escalations(JOURNAL, "escalation-only", "conditional")
        self.assertEqual(per[10]["routine"], 0)
        self.assertEqual(per[10]["human-option"], 2, "the plan and merge stops move here")

    def test_rounds_take_the_larger_of_budget_and_prose(self):
        """A Budget line alone counts; one written at the cap does not cap the count."""
        j = ("## t — #7 plan gate\n- Plan-gate: n/a: x\n\n"
             "## t — #7 (code) — iteration complete\n- Budget: gate-rounds=code-review=4 · x\n")
        per, _ = q.escalations(j, "calibration", "always")
        self.assertEqual(per[7]["review-past-cap"], 2)
        j += "\n## t — #7 code review resolved\n- Code-review: RESOLVED after 5 rounds\n"
        per, _ = q.escalations(j, "calibration", "always")
        self.assertEqual(per[7]["review-past-cap"], 3)

    def test_rounds_from_prose_shaped_like_113(self):
        """No Budget count: "N rounds" counts, "no round 3" does not, and case is ignored."""
        j = ("## t — #8 plan gate\n- Plan-gate: n/a: x\n\n"
             "## t — #8 code review\n- Code-review: 2 rounds, cap reached, no round 3 opened\n"
             "- Code-review: RESOLVED after 4 rounds\n\n"
             "## t — #9 plan gate\n- Plan-gate: n/a: x\n\n"
             "## t — #9 code review\n- Code-review: rounds 1-5 total\n"
             "- Awaiting human: fix (round 7) or decline\n\n"
             "## t — #6 plan gate\n- Plan-gate: n/a: x\n\n"
             "## t — #6 code review\n- Code-review: Round 4 human-authorized\n")
        per, _ = q.escalations(j, "calibration", "always")
        self.assertEqual(per[8]["review-past-cap"], 2)
        self.assertEqual(per[9]["review-past-cap"], 3, "a hypothetical round outside the Code-review line does not count")
        self.assertEqual(per[6]["review-past-cap"], 2, "a capitalized 'Round 4' is the only evidence here")
        only_negated = j.split("- Code-review: RESOLVED")[0]
        per, _ = q.escalations(only_negated, "calibration", "always")
        self.assertEqual(per[8]["review-past-cap"], 0, "'no round 3' is not round 3")

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
        marked = [f[2] for f in self.found()]
        self.assertEqual(marked, [True, True, True, True, False, True])

    def test_every_ref_in_a_marker_counts_and_malformed_is_reported(self):
        found = q.findings([
            comment("2026-12-02T00:00:00Z", "## F1\n**Attributed-to:** `owner/repo#5` (review gate)"),
            comment("2026-12-02T00:00:00Z", "## F2\n**Attributed-to:** owner/repo#7, owner/repo#5"),
            comment("2026-12-02T00:00:00Z", "## F3\n**Attributed-to:** PR 5 in repo"),
            comment("2026-12-02T00:00:00Z", "## F4\n**Attributed-to:** unknown"),
            comment("2026-12-02T00:00:00Z", "## F5\n**Attributed-to:** owner/repo#50"),
            comment("2026-12-02T00:00:00Z",
                    "## F6\n**Attributed-to:** none (a pointer to the finding on owner/repo#5)"),
            comment("2026-12-02T00:00:00Z", "## F7\n**Attributed-to:** Unknown — maybe owner/repo#5."),
            comment("2026-12-02T00:00:00Z", "## F8\n**Attributed-to:** Unknown."),
        ])
        now = self.MERGE + 60 * DAY
        self.assertEqual(q.fcount(found, "owner/repo", 5, self.MERGE, now), 2,
                         "a ref inside a none(...) or unknown marker attributes nothing")
        self.assertEqual(q.fcount(found, "owner/repo", 7, self.MERGE, now), 1)
        self.assertEqual([f[3] for f in found], [0, 0, 1, 0, 0, 0, 0, 0])


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
        self.assertIn("3 of 4 PRs not located; pass --prs", text)
        self.assertTrue(sha)

    def test_a_run_without_a_journal_reports_its_issues_unknown(self):
        run = os.path.join(self.tmp.name, ".claude", "loop", "r")
        os.makedirs(run)
        with open(os.path.join(run, "queue.md"), "w") as f:
            f.write(QUEUE)
        out = io.StringIO()
        q.report(self.tmp.name, "main", T0, None, None, out=out)
        for issue in (10, 12):
            self.assertIn(f"r | #{issue} | " + " | ".join(["unknown"] * len(q.COLUMNS)),
                          out.getvalue())


class MainTests(GitCase):
    def run_main(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        old = sys.stdout, sys.stderr
        sys.stdout, sys.stderr = out, err
        try:
            code = q.main(list(argv))
        finally:
            sys.stdout, sys.stderr = old
        return code, out.getvalue(), err.getvalue()

    def test_unmatched_prs_key_fails_loudly(self):
        path = os.path.join(self.tmp.name, "prs.json")
        with open(path, "w") as f:
            f.write("[]")
        code, _, err = self.run_main(self.tmp.name, "--prs", "/no/such/repo=" + path)
        self.assertEqual(code, 2)
        self.assertIn("matches no REPO", err)

    def test_prs_key_matches_through_a_symlink(self):
        sha = self.repo.commit("unrelated subject", ["a.py"], T0)
        run = os.path.join(self.tmp.name, ".claude", "loop", "r")
        os.makedirs(run)
        with open(os.path.join(run, "queue.md"), "w") as f:
            f.write(QUEUE)
        path = os.path.join(self.tmp.name, "prs.json")
        with open(path, "w") as f:
            f.write('[{"number": 20, "mergeCommit": {"oid": "%s"}}]' % sha)
        link = self.tmp.name + "-link"
        os.symlink(self.tmp.name, link)
        self.addCleanup(os.remove, link)
        code, out, _ = self.run_main(self.tmp.name, "--prs", link + "=" + path,
                                     "--now", "2026-07-30")
        self.assertEqual(code, 0)
        self.assertIn("r | 20 | 10 | 2026-06-01 |", out)

    def test_unmarked_and_malformed_count_only_since_adoption(self):
        before = q.utc(q.epoch(q.ADOPTION) - DAY).isoformat()
        after = q.utc(q.epoch(q.ADOPTION) + DAY).isoformat()
        path = os.path.join(self.tmp.name, "f.json")
        with open(path, "w") as f:
            json.dump([comment(before, "## F1 none"), comment(after, "## F2 none"),
                       comment(after, "## F3\n**Attributed-to:** garbage")], f)
        code, out, _ = self.run_main(self.tmp.name, "--findings", path)
        self.assertEqual(code, 0)
        self.assertIn("unmarked=1 malformed=1", out)


if __name__ == "__main__":
    unittest.main()
