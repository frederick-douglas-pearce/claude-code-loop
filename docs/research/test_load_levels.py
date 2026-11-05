#!/usr/bin/env python3
"""Fixture tests for `load_levels.py`.

NOT part of the shipped suite -- under `docs/research/`, not `tests/`, per the
scope brake. Same rationale as `test_engine_cost.py`.

    python3 docs/research/test_load_levels.py
"""
import io
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import load_levels as L  # noqa: E402

CORE_NAME = "loop-engine.md"
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


def opus(found, model="claude-opus-5-5"):
    """`{file: [(ingested, tag)]}` -> scan's shape, all on the one measured family."""
    return {"opus-5": {f: [(x, t, model) for x, t in v] for f, v in found.items()}}


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
        out = L.report("0.5.0", opus({"loop-engine.md": [(100, "a/s1")]}), [])
        self.assertIn("reference/never.md: UNMEASURED -- no complete read; no row (default-deny)", out)
        self.assertFalse(any("never.md'): " in line for line in out))

    def test_the_row_is_the_minimum_and_names_its_setter(self):
        out = L.report("0.5.0", opus({"loop-engine.md": [(105, "a/s2"), (100, "a/s1")]}), [])
        self.assertIn("loop-engine.md: row=100  n=2 range=100-105  set by a/s1", out)
        self.assertIn("    suggested for LOAD_TOKENS_BY_FAMILY['opus-5']: ('0.5.0', CORE): 100,", out)

    def test_skill_md_is_never_given_a_row(self):
        out = L.report("0.5.0", opus({"SKILL.md": [(50, "a/s1")]}), [])
        self.assertFalse(any(line.startswith("SKILL.md") for line in out))

    def test_an_identical_file_takes_the_minimum_over_both_eras(self):
        with mock.patch.dict(L.ec.LOAD_TOKENS, {("0.4.0", "reference/same.md"): 90}):
            out = L.report("0.5.0", opus({"reference/same.md": [(95, "a/s1")]}), [], prev="0.4.0")
        self.assertIn("    suggested for LOAD_TOKENS_BY_FAMILY['opus-5']: ('0.5.0', 'reference/same.md'): 90,", out)

    def test_an_identical_file_with_no_read_inherits_the_previous_row(self):
        with mock.patch.dict(L.ec.LOAD_TOKENS, {("0.4.0", "reference/same.md"): 90}):
            out = L.report("0.5.0", opus({}), [], prev="0.4.0")
        self.assertIn("    suggested for LOAD_TOKENS_BY_FAMILY['opus-5']: ('0.5.0', 'reference/same.md'): 90,", out)

    def test_a_changed_file_ignores_the_previous_row(self):
        with mock.patch.dict(L.ec.LOAD_TOKENS, {("0.4.0", "loop-engine.md"): 10}):
            out = L.report("0.5.0", opus({"loop-engine.md": [(100, "a/s1")]}), [], prev="0.4.0")
        self.assertIn("    suggested for LOAD_TOKENS_BY_FAMILY['opus-5']: ('0.5.0', CORE): 100,", out)

    def test_a_row_from_the_previous_era_names_that_era_as_its_setter(self):
        with mock.patch.dict(L.ec.LOAD_TOKENS, {("0.4.0", "reference/same.md"): 90}):
            out = L.report("0.5.0", opus({"reference/same.md": [(95, "a/s1")]}), [], prev="0.4.0")
        line = next(x for x in out if x.startswith("reference/same.md:"))
        self.assertIn("set by 0.4.0's row", line)
        self.assertNotIn("a/s1", line.split("set by")[1])

    def test_a_tie_with_the_previous_row_names_both_setters(self):
        with mock.patch.dict(L.ec.LOAD_TOKENS, {("0.4.0", "reference/same.md"): 90}):
            out = L.report("0.5.0", opus({"reference/same.md": [(90, "a/s1")]}), [], prev="0.4.0")
        self.assertTrue(any("set by a/s1, 0.4.0's row" in x for x in out))

    def test_each_family_gets_its_own_section_and_never_mixes(self):
        found = opus({"loop-engine.md": [(100, "a/s1")]})
        found["other-1"] = {"loop-engine.md": [(80, "b/s2", "claude-other-1")]}
        out = L.report("0.5.0", found, [])
        i, j = out.index("== family opus-5: rows go in LOAD_TOKENS_BY_FAMILY['opus-5']"), out.index(
            "== family other-1: rows go in LOAD_TOKENS_BY_FAMILY['other-1']  (NO TABLE YET: "
            "add it first; never paste these into another family's)")
        opus_part, other_part = out[i:j], out[j:]
        self.assertIn("loop-engine.md: row=100  n=1 range=100-100  set by a/s1", opus_part)
        self.assertIn("loop-engine.md: row=80  n=1 range=80-80  set by b/s2", other_part)
        self.assertIn("    suggested for LOAD_TOKENS_BY_FAMILY['other-1']: ('0.5.0', CORE): 80,",
                      other_part)

    def test_a_family_with_rows_is_reported_even_with_no_reads(self):
        out = L.report("0.5.0", {}, [])
        self.assertIn("== family opus-5: rows go in LOAD_TOKENS_BY_FAMILY['opus-5']", out)
        self.assertIn("loop-engine.md: UNMEASURED -- no complete read; no row (default-deny)", out)

    def test_ids_within_a_family_show_their_own_minima(self):
        found = {"opus-5": {"loop-engine.md": [(100, "a/s1", "claude-opus-5-5"),
                                               (103, "a/s2", "claude-opus-5")]}}
        out = L.report("0.5.0", found, [])
        self.assertIn("    per model: claude-opus-5=103, claude-opus-5-5=100", out)

    def test_left_out_sessions_are_named(self):
        out = L.report("0.5.0", opus({}), [("a/s9", "parent ('claude-fable-5-1', 'xhigh')")])
        self.assertIn("left out: a/s9 -- parent ('claude-fable-5-1', 'xhigh')", out)


def prof(model="claude-opus-5-5", eras=("0.5.0",), ingested=100.0):
    """The fields of `profile`'s result that `scan` reads; the family comes from
    the real lookup, so scan's binning is tested against engine_cost's key."""
    family = L.ec.family_of(model)
    return {"family": family, "parent_models": [model],
            "no_rows": None if family else f"no load rows for parent model {model}",
            "eras_seen": {e: 1 for e in eras},
            "files": {"loop-engine.md": {"ingested": ingested}}}


class ScanTests(unittest.TestCase):
    """`scan`'s exclusions: each one is NAMED in left_out, never silent."""

    def run_scan(self, profile):
        full = [read("loop-engine.md", 1, 10, 10)]
        with mock.patch.object(L.ec, "load", return_value=full), \
                mock.patch.object(L.ec, "profile", side_effect=profile):
            return L.scan(["/p/proj/s1234567.jsonl"], "0.5.0")

    def test_an_opus_parent_sets_a_row(self):
        found, left = self.run_scan(lambda _: prof())
        self.assertEqual(found, {"opus-5": {"loop-engine.md": [
            (100, "proj/s1234567", "claude-opus-5-5")]}})
        self.assertEqual(left, [])

    def test_family_is_by_exact_id_so_a_lookalike_is_left_out(self):
        found, left = self.run_scan(lambda _: prof("claude-opus-5-7"))
        self.assertEqual(dict(found), {})
        self.assertIn("no tokenizer family", left[0][1])

    def test_another_tokenizer_family_is_left_out_not_averaged_in(self):
        found, left = self.run_scan(lambda _: prof("claude-fable-5-1"))
        self.assertEqual(dict(found), {})
        self.assertEqual(left[0][1],
                         "no tokenizer family: no load rows for parent model claude-fable-5-1")

    def test_two_ids_of_one_family_are_labeled_with_both(self):
        p = prof()
        p["parent_models"] = ["claude-opus-5", "claude-opus-5-5"]
        found, _ = self.run_scan(lambda _: p)
        self.assertEqual(found["opus-5"]["loop-engine.md"][0][2],
                         "claude-opus-5+claude-opus-5-5")

    def test_a_mixed_era_session_is_left_out(self):
        found, left = self.run_scan(lambda _: prof(eras=("0.4.0", "0.5.0")))
        self.assertEqual(dict(found), {})
        self.assertIn("mixed eras", left[0][1])

    def test_a_refusal_is_named(self):
        def refuse(_):
            raise L.ec.Unpriced("unknown model")
        found, left = self.run_scan(refuse)
        self.assertEqual(dict(found), {})
        self.assertIn("profile refused: unknown model", left[0][1])

    def test_a_programming_error_is_not_reported_as_a_refusal(self):
        def bug(_):
            raise KeyError("files")
        with self.assertRaises(KeyError):
            self.run_scan(bug)

    def test_no_parent_turns_is_named(self):
        found, left = self.run_scan(lambda _: None)
        self.assertEqual(left, [("proj/s1234567", "profile found no parent turns")])

    def test_zero_credited_ingestion_is_named(self):
        found, left = self.run_scan(lambda _: prof(ingested=0.0))
        self.assertEqual(dict(found), {})
        self.assertIn("credited no ingestion", left[0][1])


class CensusTests(unittest.TestCase):
    def test_a_session_without_rows_names_why(self):
        p = {"eras_seen": {"0.5.0": 1}, "admissible": False, "incomplete": [CORE_NAME],
             "unattributed": [], "no_rows": "no load rows for parent model claude-fable-5-1"}
        with mock.patch.object(L.ec, "profile", return_value=p):
            out = L.census(["/p/proj/s1234567.jsonl"], "0.5.0")
        self.assertTrue(out[0].startswith(
            "INADMISSIBLE proj/s1234567: no load rows for parent model claude-fable-5-1"))
        self.assertEqual(out[-1], "census: admissible 0, inadmissible 1, refused 0, skipped 0")


class MainTests(unittest.TestCase):
    def test_a_malformed_era_is_refused(self):
        for argv in (["x", "0.5"], ["x", "v0.5.0"], ["x", "0.5.0", "--prev", "0.4"]):
            with mock.patch.object(L, "transcripts") as t, \
                    mock.patch("sys.stderr", new_callable=io.StringIO):
                self.assertEqual(L.main(argv), 2, argv)
                t.assert_not_called()


if __name__ == "__main__":
    unittest.main()
