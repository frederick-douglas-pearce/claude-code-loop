#!/usr/bin/env python3
"""Fixture tests for `load_levels.py`.

NOT part of the shipped suite -- under `docs/research/`, not `tests/`, per the
scope brake. Same rationale as `test_engine_cost.py`.

    python3 docs/research/test_load_levels.py
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import load_levels as L  # noqa: E402

CACHE = "/home/u/.claude/plugins/cache/claude-code-loop/dev-loop"


def read(f, start, n, total, era="0.5.0", sidechain=False, root=CACHE):
    return {"type": "user", "isSidechain": sidechain,
            "toolUseResult": {"type": "text", "file": {
                "filePath": f"{root}/{era}/skills/dev-loop/{f}",
                "startLine": start, "numLines": n, "totalLines": total}}}


class CompleteReadsTests(unittest.TestCase):
    def test_contiguous_pages_cover_the_file(self):
        recs = [read("loop-engine.md", 1, 760, 2280), read("loop-engine.md", 761, 500, 2280),
                read("loop-engine.md", 1261, 1020, 2280)]
        self.assertEqual(L.complete_reads(recs, "0.5.0"), ["loop-engine.md"])

    def test_the_trailing_line_after_a_final_newline_may_be_missing(self):
        recs = [read("phases/accepting.md", 1, 494, 495)]
        self.assertEqual(L.complete_reads(recs, "0.5.0"), ["phases/accepting.md"])

    def test_a_gap_is_not_complete(self):
        recs = [read("loop-engine.md", 1, 700, 2280), read("loop-engine.md", 761, 1520, 2280)]
        self.assertEqual(L.complete_reads(recs, "0.5.0"), [])

    def test_missing_the_last_two_lines_is_not_complete(self):
        self.assertEqual(L.complete_reads([read("SKILL.md", 1, 98, 100)], "0.5.0"), [])

    def test_a_subagent_read_does_not_count(self):
        recs = [read("loop-engine.md", 1, 2280, 2280, sidechain=True)]
        self.assertEqual(L.complete_reads(recs, "0.5.0"), [])

    def test_another_era_does_not_count(self):
        recs = [read("loop-engine.md", 1, 2280, 2280, era="0.4.0")]
        self.assertEqual(L.complete_reads(recs, "0.5.0"), [])

    def test_a_working_tree_read_is_not_a_load(self):
        recs = [read("loop-engine.md", 1, 2280, 2280,
                     root="/home/u/git/claude-code-loop/plugins/dev-loop-x/dev-loop")]
        self.assertEqual(L.complete_reads(recs, "0.5.0"), [])

    def test_malformed_records_are_ignored(self):
        recs = ["x", {"toolUseResult": "text"}, {"toolUseResult": {"file": None}},
                read("loop-engine.md", 1, 10, 10)]
        self.assertEqual(L.complete_reads(recs, "0.5.0"), ["loop-engine.md"])


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for era, body in (("0.5.0", "new"), ("0.4.0", "old")):
            d = os.path.join(self.tmp.name, era, "skills", "dev-loop", "reference")
            os.makedirs(d)
            for f, text in (("loop-engine.md", body), ("SKILL.md", body),
                            ("reference/same.md", "same"), ("reference/never.md", body)):
                with open(os.path.join(self.tmp.name, era, "skills", "dev-loop", f), "w") as fh:
                    fh.write(text)
        p = mock.patch.object(L.ec, "PLUGIN_CACHE", self.tmp.name)
        p.start()
        self.addCleanup(p.stop)

    def test_an_unread_file_gets_no_row(self):
        out = L.report("0.5.0", {"loop-engine.md": [(100, "a/s1")]}, [])
        self.assertIn("reference/never.md: UNMEASURED -- no complete read; no row (default-deny)", out)
        self.assertFalse(any("never.md'): " in line for line in out))

    def test_the_row_is_the_minimum_and_names_its_setter(self):
        out = L.report("0.5.0", {"loop-engine.md": [(105, "a/s2"), (100, "a/s1")]}, [])
        self.assertIn("loop-engine.md: row=100  n=2 range=100-105  set by a/s1", out)
        self.assertIn("    suggested: ('0.5.0', CORE): 100,", out)

    def test_skill_md_is_never_given_a_row(self):
        out = L.report("0.5.0", {"SKILL.md": [(50, "a/s1")]}, [])
        self.assertFalse(any(line.startswith("SKILL.md") for line in out))

    def test_an_identical_file_takes_the_minimum_over_both_eras(self):
        with mock.patch.dict(L.ec.LOAD_TOKENS, {("0.4.0", "reference/same.md"): 90}):
            out = L.report("0.5.0", {"reference/same.md": [(95, "a/s1")]}, [], prev="0.4.0")
        self.assertIn("    suggested: ('0.5.0', 'reference/same.md'): 90,", out)

    def test_an_identical_file_with_no_read_inherits_the_previous_row(self):
        with mock.patch.dict(L.ec.LOAD_TOKENS, {("0.4.0", "reference/same.md"): 90}):
            out = L.report("0.5.0", {}, [], prev="0.4.0")
        self.assertIn("    suggested: ('0.5.0', 'reference/same.md'): 90,", out)

    def test_a_changed_file_ignores_the_previous_row(self):
        with mock.patch.dict(L.ec.LOAD_TOKENS, {("0.4.0", "loop-engine.md"): 10}):
            out = L.report("0.5.0", {"loop-engine.md": [(100, "a/s1")]}, [], prev="0.4.0")
        self.assertIn("    suggested: ('0.5.0', CORE): 100,", out)

    def test_left_out_sessions_are_named(self):
        out = L.report("0.5.0", {}, [("a/s9", "parent ('claude-fable-5-1', 'xhigh')")])
        self.assertIn("left out: a/s9 -- parent ('claude-fable-5-1', 'xhigh')", out)


if __name__ == "__main__":
    unittest.main()
