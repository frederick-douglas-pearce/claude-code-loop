#!/usr/bin/env python3
"""Synthetic-transcript tests for `review_launches.py` (#393).

NOT part of the shipped suite -- lives under `docs/research/`, not `tests/`, so
`python3 -m unittest discover -s tests` does not pick it up; `TEST_CMD`'s second
half runs it, and CI does not (#286).

Every transcript here is written by the test; nothing reads a real replicate. The
cases pin the mechanism: what a launch is (assistant records only, against
replays and other record types; sidechain records skipped; one per
`tool_use_id`, within and across files; ordered by time across parent files),
each term of the two signatures and the re-check's precedence over the finder,
that an unmatched launch is listed and never dropped, that the fix-agent count
is `null` and "not established" while the hook is unset and never `0`, and that
each shape the docstring lists as unreadable gives `null` with a reason.

    python3 docs/research/test_review_launches.py
"""
import contextlib
import io
import json
import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import replicate  # noqa: E402
import review_launches as RL  # noqa: E402

COMMIT = "44e0c690d0dd09ce1efbdbaa339ba2f6dceb0c31"
PIN = "5391906a8723ba67956750e5e550f16a1779edcd"
SLUG = "proj"

FINDER_P = ("You are a READ-ONLY code-review finder, lens label `correctness`. "
            "Classify each finding BLOCKING or EDITORIAL; if unsure, BLOCKING.")
# rp2-h1's re-check prompt carries the finder's words (the lens label `recheck`
# and both classes); the precedence is what keeps such a prompt a re-check.
RECHECK_P = ("You are a fresh READ-ONLY re-checker (finding-id lens label: `recheck`). "
             "Earlier material carries a verdict and is not re-litigated. "
             "Classify each finding BLOCKING or EDITORIAL.")
AC_P = "You are a fresh, read-only acceptance verifier. State met/not-met per criterion."
FIX_P = "Apply these review fixes in your own worktree copy and report the diff."


def ts(sec):
    return "2026-11-19T10:%02d:%02d.000Z" % (sec // 60, sec % 60)


def launch(tid, prompt, desc="d", name="Agent", sub="general-purpose"):
    inp = {"description": desc, "subagent_type": sub}
    if prompt is not None:
        inp["prompt"] = prompt
    return {"type": "tool_use", "id": tid, "name": name, "input": inp}


def rec(sec, *blocks, rtype="assistant"):
    r = {"type": rtype, "message": {"role": "assistant", "content": list(blocks)}}
    if sec is not None:
        r["timestamp"] = ts(sec)
    return r


class Fixture(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.rdir = pathlib.Path(self._tmp.name) / "rp-x"
        self.pdir = self.rdir / "home" / ".claude" / "projects" / SLUG
        self.pdir.mkdir(parents=True)
        self.env(COMMIT)

    def tearDown(self):
        self._tmp.cleanup()

    def env(self, commit):
        env = {"project_slug": SLUG}
        if commit is not None:
            env["plugin_commit"] = commit
        (self.rdir / "environment.json").write_text(json.dumps(env))

    def write(self, records, name="aaaa.jsonl", raw_lines=()):
        lines = [json.dumps(r) for r in records] + list(raw_lines)
        (self.pdir / name).write_text("\n".join(lines) + "\n")

    def report(self):
        return RL.count(self.rdir)

    def control(self):
        """Two finders, a re-check, an acceptance verifier: the 0.6.0 control shape."""
        return [rec(1, launch("f1", FINDER_P, "Review: correctness lens"),
                    launch("f2", FINDER_P.replace("correctness", "guard-efficacy"))),
                rec(30, launch("r1", RECHECK_P, "Review round 2 re-check")),
                rec(60, launch("a1", AC_P, "AC verifier (Class A)"))]


class Counting(Fixture):
    def test_control_shape(self):
        self.write(self.control())
        r = self.report()
        self.assertEqual((r["launches"], r["finder"], r["recheck"], r["unclassified"]), (4, 2, 1, 1))
        self.assertEqual(r["review_rounds"], 2)
        self.assertIsNone(r["review_rounds_reason"])
        self.assertEqual([c["tool_use_id"] for c in r["classified_launches"]], ["f1", "f2", "r1"])

    def test_recheck_takes_precedence_over_finder(self):
        self.assertTrue(RL.is_recheck({"prompt": RECHECK_P}))
        for word in ("lens", "BLOCKING", "EDITORIAL"):
            self.assertIn(word, RECHECK_P)  # rp2-h1's shape: it carries the finder's words
        self.assertEqual(RL.classify({"prompt": RECHECK_P}), ("recheck", ["recheck"]))
        self.assertEqual(RL.classify({"prompt": FINDER_P}), ("finder", ["finder"]))

    def test_unclassified_is_listed_never_dropped(self):
        self.write(self.control())
        r = self.report()
        (u,) = r["unclassified_launches"]
        self.assertEqual(u["tool_use_id"], "a1")
        self.assertEqual(u["description"], "AC verifier (Class A)")
        self.assertEqual(u["subagent_type"], "general-purpose")
        self.assertEqual(r["launches"], r["finder"] + r["recheck"] + r["unclassified"])

    def test_prompt_head_is_cut_at_120_characters(self):
        long_p = "x" * 100 + "0123456789abcdefghijKLMNOP"
        self.write([rec(1, launch("a1", long_p))])
        (u,) = self.report()["unclassified_launches"]
        self.assertEqual(u["prompt_head"], "x" * 100 + "0123456789abcdefghij")

    def test_two_signatures_is_unclassified(self):
        # The realistic #288 shape: a fix-agent signature that also matches a
        # finder prompt. Neither count may take it.
        with mock.patch.object(RL, "FIX_AGENT", lambda inp: "BLOCKING" in (inp.get("prompt") or "")):
            self.write([rec(1, launch("f1", FINDER_P))])
            r = self.report()
        self.assertEqual((r["finder"], r["fix_agent"], r["unclassified"]), (0, 0, 1))
        self.assertEqual(r["unclassified_launches"][0]["matches"], ["finder", "fix_agent"])

    def test_task_is_a_launch(self):
        self.write([rec(1, launch("f1", FINDER_P, name="Task"))])
        self.assertEqual(self.report()["finder"], 1)

    def test_only_assistant_records_hold_launches(self):
        self.write([rec(1, launch("f1", FINDER_P)),
                    rec(2, launch("f9", FINDER_P), rtype="api-request-blob"),
                    rec(3, launch("f8", FINDER_P), rtype="user"),
                    rec(4, launch("f7", FINDER_P), rtype="progress")])
        r = self.report()
        self.assertEqual((r["launches"], r["finder"]), (1, 1))

    def test_sidechain_records_are_skipped(self):
        side = rec(2, launch("s1", FINDER_P))
        side["isSidechain"] = True
        self.write([rec(1, launch("f1", FINDER_P)), side])
        self.assertEqual(self.report()["launches"], 1)

    def test_duplicate_tool_use_id_counted_once(self):
        self.write([rec(1, launch("f1", FINDER_P)), rec(1, launch("f1", FINDER_P))])
        self.assertEqual(self.report()["launches"], 1)

    def test_duplicate_tool_use_id_across_files_counted_once(self):
        self.write([rec(1, launch("f1", FINDER_P))], name="aaaa.jsonl")
        self.write([rec(1, launch("f1", FINDER_P))], name="bbbb.jsonl")
        r = self.report()
        self.assertEqual((r["parent_transcripts"], r["launches"]), (2, 1))

    def test_case_rules(self):
        self.assertTrue(RL.is_recheck({"prompt": "Earlier material is not to be Re-Litigated."}))
        self.assertTrue(RL.is_finder({"prompt": "LENS label x. Classes: BLOCKING, EDITORIAL."}))
        # The classes are matched as the engine spells them.
        self.assertFalse(RL.is_finder({"prompt": "lens label x. classes: blocking, editorial."}))
        self.assertFalse(RL.is_finder({"prompt": "lens label x. BLOCKING only."}))
        # Each term is required on its own, and each class is matched in its own case.
        self.assertFalse(RL.is_finder({"prompt": "Classes: BLOCKING, EDITORIAL."}))
        self.assertFalse(RL.is_finder({"prompt": "lens x. EDITORIAL only."}))
        self.assertFalse(RL.is_finder({"prompt": "lens x. blocking, EDITORIAL."}))
        self.assertFalse(RL.is_finder({"prompt": "lens x. BLOCKING, editorial."}))

    def test_missing_or_non_string_prompt_is_unclassified(self):
        self.write([rec(1, launch("n1", None), launch("n2", 123), launch("n3", ["x"]))])
        r = self.report()
        self.assertEqual((r["launches"], r["unclassified"]), (3, 3))
        self.assertEqual([u["prompt_head"] for u in r["unclassified_launches"]], [None, None, None])

    def test_subagent_transcripts_are_not_counted(self):
        self.write(self.control())
        sub = self.pdir / "aaaa" / "subagents"
        sub.mkdir(parents=True)
        (sub / "agent-x.jsonl").write_text(json.dumps(rec(5, launch("s1", FINDER_P))) + "\n")
        self.assertEqual(self.report()["launches"], 4)

    def test_launches_ordered_by_time_across_parent_files(self):
        # aaaa.jsonl sorts first but holds the LATER launch.
        self.write([rec(90, launch("r1", RECHECK_P))], name="aaaa.jsonl")
        self.write([rec(1, launch("f1", FINDER_P)), rec(2, launch("f2", FINDER_P))], name="bbbb.jsonl")
        r = self.report()
        self.assertEqual(r["parent_transcripts"], 2)
        self.assertEqual(r["review_rounds"], 2)

    def test_send_message_listed(self):
        self.write([rec(1, {"type": "tool_use", "id": "s1", "name": "SendMessage",
                            "input": {"to": "abc", "summary": "continue"}})])
        r = self.report()
        self.assertEqual(r["send_message"], 1)
        self.assertEqual(r["send_messages"][0]["to"], "abc")
        self.assertEqual(r["launches"], 0)

    def test_unparseable_lines_are_counted(self):
        self.write(self.control(), raw_lines=['{"type": "assistant", "mess', "[1, 2]"])
        self.assertEqual(self.report()["unparseable_lines"], 2)

    def test_malformed_record_fields_do_not_crash(self):
        bad_msg = {"type": "assistant", "timestamp": ts(2), "message": "x"}
        bad_ts = rec(3, launch("f2", FINDER_P))
        bad_ts["timestamp"] = 5
        self.write([rec(1, launch("f1", FINDER_P)), bad_msg, bad_ts])
        r = self.report()
        self.assertEqual(r["launches"], 2)
        self.assertIsNone(r["review_rounds"])
        self.assertIn("timestamp", r["review_rounds_reason"])


class FixAgent(Fixture):
    def test_unset_hook_is_null_never_zero(self):
        for records in ([], self.control()):
            with self.subTest(launches=len(records)):
                self.write(records)
                r = self.report()
                self.assertIsNone(r["fix_agent"])
                self.assertNotEqual(r["fix_agent"], 0)
                self.assertEqual(r["fix_agent_label"], "not established")

    def test_json_carries_null_and_the_label(self):
        self.write(self.control())
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(RL.main([str(self.rdir), "--json"]), 0)
        (rep,) = json.loads(out.getvalue())
        self.assertIn("fix_agent", rep)
        self.assertIsNone(rep["fix_agent"])
        self.assertEqual(rep["fix_agent_label"], "not established")

    def test_text_never_prints_zero(self):
        self.write(self.control())
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            RL.main([str(self.rdir)])
        (line,) = [l for l in out.getvalue().splitlines() if "fix-agent" in l]
        self.assertEqual(line.strip(), "fix-agent spawns: not established (null)")

    def test_set_hook_reports_a_true_zero(self):
        with mock.patch.object(RL, "FIX_AGENT", lambda inp: False):
            self.write(self.control())
            r = self.report()
        self.assertEqual(r["fix_agent"], 0)
        self.assertEqual(r["fix_agent_label"], "counted by FIX_AGENT")

    def test_set_hook_counts_and_may_sit_between_rounds(self):
        with mock.patch.object(RL, "FIX_AGENT", lambda inp: "review fixes" in (inp.get("prompt") or "")):
            self.write([rec(1, launch("f1", FINDER_P)), rec(10, launch("x1", FIX_P)),
                        rec(30, launch("r1", RECHECK_P))])
            r = self.report()
        self.assertEqual((r["fix_agent"], r["review_rounds"], r["unclassified"]), (1, 2, 0))
        self.assertNotEqual(r["fix_agent_label"], "not established")


class NullRounds(Fixture):
    def rounds(self, records):
        self.write(records)
        r = self.report()
        return r["review_rounds"], r["review_rounds_reason"]

    def assertNull(self, records, needle):
        rounds, reason = self.rounds(records)
        self.assertIsNone(rounds)
        self.assertIn(needle, reason)

    def test_only_the_hand_counted_commit_is_validated(self):
        self.assertEqual(set(RL.VALIDATED_COMMITS), {COMMIT})
        self.assertEqual(self.rounds(self.control()), (2, None))
        # R1's control pin fails closed until a replicate that ran it is hand-counted.
        self.env(PIN)
        self.assertNull(self.control(), "not validated against " + PIN)

    def test_unvalidated_commit_nulls_every_signature_count(self):
        self.env("0" * 40)
        self.assertNull(self.control(), "not validated against " + "0" * 40)
        r = self.report()
        self.assertEqual((r["finder"], r["recheck"], r["fix_agent"]), (None, None, None))
        self.assertEqual(r["fix_agent_label"], "not validated for this plugin_commit")
        # The launches are still listed, with the kind each signature gave.
        self.assertEqual(r["launches"], 4)
        self.assertEqual([c["kind"] for c in r["classified_launches"]],
                         ["finder", "finder", "recheck"])
        self.assertEqual(r["unclassified"], 1)

    def test_unparseable_line_nulls_rounds(self):
        self.write(self.control(), raw_lines=['{"type": "assistant", "mess'])
        r = self.report()
        self.assertIsNone(r["review_rounds"])
        self.assertIn("1 unparseable", r["review_rounds_reason"])

    def test_send_message_nulls_rounds(self):
        self.assertNull(self.control() + [rec(70, {"type": "tool_use", "id": "s1",
                                                    "name": "SendMessage", "input": {"to": "a"}})],
                        "SendMessage")

    def test_parent_tool_between_finders_nulls_rounds(self):
        # A second fan-out separated only by the parent's own fix and commit.
        for tool in ("Edit", "Write", "Bash", "SomeNewTool"):
            with self.subTest(tool=tool):
                self.assertNull([rec(1, launch("f1", FINDER_P)),
                                 rec(10, {"type": "tool_use", "id": "t1", "name": tool, "input": {}}),
                                 rec(20, launch("f2", FINDER_P))],
                                "between the first and last finder launch")

    def test_read_only_tools_between_finders_are_allowed(self):
        self.assertEqual(self.rounds(
            [rec(1, launch("f1", FINDER_P))]
            + [rec(2 + i, {"type": "tool_use", "id": "t%d" % i, "name": t, "input": {}})
               for i, t in enumerate(("Read", "Grep", "Glob"))]
            + [rec(20, launch("f2", FINDER_P))]), (1, None))

    def test_fixes_after_round_one_are_the_control_shape(self):
        # The parent's fix and commit sit after the last finder and before the re-check.
        self.assertEqual(self.rounds(
            [rec(1, launch("f1", FINDER_P)), rec(2, launch("f2", FINDER_P)),
             rec(10, {"type": "tool_use", "id": "e1", "name": "Edit", "input": {}}),
             rec(11, {"type": "tool_use", "id": "b1", "name": "Bash", "input": {}}),
             rec(30, launch("r1", RECHECK_P))]), (2, None))

    def test_unrecorded_commit(self):
        self.env(None)
        self.assertNull(self.control(), "not validated")

    def test_launch_without_timestamp(self):
        self.assertNull([rec(1, launch("f1", FINDER_P)), rec(None, launch("r1", RECHECK_P))],
                        "timestamp")

    def test_two_rechecks_exceed_the_cap(self):
        self.assertNull([rec(1, launch("f1", FINDER_P)), rec(30, launch("r1", RECHECK_P)),
                         rec(60, launch("r2", RECHECK_P))], "two-round cap")

    def test_recheck_with_no_finder_before_it(self):
        self.assertNull([rec(1, launch("r1", RECHECK_P)), rec(30, launch("f1", FINDER_P))],
                        "no finder launch before it")

    def test_finder_after_recheck(self):
        self.assertNull([rec(1, launch("f1", FINDER_P)), rec(30, launch("r1", RECHECK_P)),
                         rec(60, launch("f2", FINDER_P))], "after a re-check")

    def test_downstream_rearm_or_delegated_fix(self):
        self.assertNull([rec(1, launch("f1", FINDER_P)), rec(20, launch("a1", AC_P)),
                         rec(30, launch("r1", RECHECK_P))], "a downstream re-arm, or a delegated fix")

    def test_split_finders(self):
        self.assertNull([rec(1, launch("f1", FINDER_P)), rec(20, launch("a1", AC_P)),
                         rec(30, launch("f2", FINDER_P))], "split")

    def test_round_one_only_and_none(self):
        self.assertEqual(self.rounds([rec(1, launch("f1", FINDER_P)), rec(20, launch("a1", AC_P))]),
                         (1, None))
        self.assertEqual(self.rounds([rec(20, launch("a1", AC_P))]), (0, None))


class Errors(unittest.TestCase):
    def test_refused_and_empty_replicates_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = pathlib.Path(tmp) / "rp-missing"
            missing.mkdir()
            empty = pathlib.Path(tmp) / "rp-empty"
            (empty / "home" / ".claude" / "projects" / SLUG).mkdir(parents=True)
            (empty / "environment.json").write_text(json.dumps({"project_slug": SLUG}))
            with self.assertRaises(replicate.Refused):
                RL.count(empty)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = RL.main([str(missing), str(empty), "--json"])
            self.assertEqual(code, 1)
            reps = json.loads(out.getvalue())
            self.assertEqual([("error" in r) for r in reps], [True, True])
            self.assertFalse(any("review_rounds" in r for r in reps))

    def test_malformed_environment_is_an_error_row_and_the_batch_continues(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows = []
            for name, env in (("rp-good", json.dumps({"project_slug": SLUG, "plugin_commit": COMMIT})),
                              ("rp-torn", "{"),
                              ("rp-list", json.dumps({"project_slug": SLUG, "plugin_commit": ["x"]})),
                              ("rp-array", "[1]")):
                rdir = pathlib.Path(tmp) / name
                pdir = rdir / "home" / ".claude" / "projects" / SLUG
                pdir.mkdir(parents=True)
                (pdir / "a.jsonl").write_text(json.dumps(rec(1, launch("f1", FINDER_P))) + "\n")
                (rdir / "environment.json").write_text(env)
                rows.append(str(rdir))
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = RL.main(rows + ["--json"])
            self.assertEqual(code, 1)
            reps = json.loads(out.getvalue())
            self.assertEqual([("error" in r) for r in reps], [False, True, True, True])
            self.assertEqual(reps[0]["finder"], 1)


if __name__ == "__main__":
    unittest.main()
