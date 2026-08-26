#!/usr/bin/env python3
"""Fixture tests for `calls_per_turn.py`.

NOT part of the shipped suite -- under `docs/research/`, not `tests/`, per the
scope brake. Same rationale as `test_engine_cost.py`.

    python3 docs/research/test_calls_per_turn.py
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import calls_per_turn as C  # noqa: E402


def bash(cmd):
    return C.is_read_only("Bash", {"command": cmd})


def turn(mid, calls, ctx=100000, sidechain=False):
    """calls: list of (id, name, input)"""
    return {"type": "assistant", "isSidechain": sidechain,
            "message": {"id": mid,
                        "usage": {"cache_read_input_tokens": ctx},
                        "content": [{"type": "tool_use", "id": i, "name": n, "input": p}
                                    for i, n, p in calls]}}


def read(path):
    return ("Read", {"file_path": path})


def write_jsonl(records):
    fh = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False)
    for r in records:
        fh.write(json.dumps(r) + "\n")
    fh.close()
    return fh.name


class ReadOnlyTests(unittest.TestCase):
    def test_grep_and_sed_slices_are_reads(self):
        self.assertTrue(bash("grep -n foo src/x.py"))
        self.assertTrue(bash("sed -n '1,90p' tests/t.py"))
        self.assertTrue(bash("ls tests/ && grep -n class tests/t.py"))

    def test_python_heredoc_calling_write_text_is_a_WRITE(self):
        """BUG: a `python3 - <<'PY' ... p.write_text(s) PY` heredoc mutates the tree
        while the command line shows no redirect at all, so a shell-shape-only test
        called it read-only and merged across a write. Found by hand-checking a run
        this script had already reported as mergeable. Moved the estimate 23%->18%."""
        self.assertFalse(bash("python3 - <<PY\nimport pathlib\n"
                              "pathlib.Path('q.md').write_text(s)\nPY"))

    def test_python_heredoc_opening_for_write_is_a_WRITE(self):
        self.assertFalse(bash("python3 - <<PY\nopen('f','w').write(x)\nPY"))

    def test_redirects_and_git_mutations_are_writes(self):
        self.assertFalse(bash("cat > f.md <<EOF\nx\nEOF"))
        self.assertFalse(bash("git commit -m x"))
        self.assertFalse(bash("sed -i 's/a/b/' f.md"))
        self.assertFalse(bash("rm -f f.md"))

    def test_read_tool_is_always_read_only(self):
        self.assertTrue(C.is_read_only("Read", {"file_path": "/a/b.py"}))

    def test_unknown_tool_is_not_assumed_read_only(self):
        self.assertFalse(C.is_read_only("Write", {"file_path": "/a/b.py"}))


class TurnTests(unittest.TestCase):
    def tearDown(self):
        for p in getattr(self, "_paths", []):
            os.unlink(p)

    def analyse(self, records):
        p = write_jsonl(records)
        self._paths = [p]
        return C.analyse(p)

    def test_streaming_snapshots_of_one_turn_are_one_turn_one_call(self):
        r = self.analyse([turn("m1", [("t1", "Read", {"file_path": "/a.py"})]),
                          turn("m1", [("t1", "Read", {"file_path": "/a.py"})])])
        self.assertEqual((r["turns"], r["calls"]), (1, 1))

    def test_sidechain_turns_are_excluded(self):
        r = self.analyse([turn("m1", [("t1", "Read", {"file_path": "/a.py"})]),
                          turn("m2", [("t2", "Read", {"file_path": "/b.py"})],
                               sidechain=True)])
        self.assertEqual(r["turns"], 1)

    def test_three_consecutive_solo_reads_of_one_file_are_two_mergeable_paging(self):
        recs = [turn(f"m{i}", [(f"t{i}", "Read", {"file_path": "/eng.md"})])
                for i in range(3)]
        r = self.analyse(recs)
        self.assertEqual(r["mergeable"], 2)
        self.assertEqual(r["paging"], 2)

    def test_reads_of_DIFFERENT_files_are_mergeable_but_not_paging(self):
        recs = [turn(f"m{i}", [(f"t{i}", "Read", {"file_path": f"/f{i}.py"})])
                for i in range(3)]
        r = self.analyse(recs)
        self.assertEqual(r["mergeable"], 2)
        self.assertEqual(r["paging"], 0)

    def test_a_write_breaks_the_run(self):
        recs = [turn("m0", [("t0", "Read", {"file_path": "/a.py"})]),
                turn("m1", [("t1", "Bash", {"command": "git commit -m x"})]),
                turn("m2", [("t2", "Read", {"file_path": "/a.py"})])]
        self.assertEqual(self.analyse(recs)["mergeable"], 0)

    def test_a_turn_already_batching_two_calls_is_not_mergeable(self):
        recs = [turn("m0", [("t0", "Read", {"file_path": "/a.py"}),
                            ("t1", "Read", {"file_path": "/b.py"})]),
                turn("m1", [("t2", "Read", {"file_path": "/c.py"})])]
        r = self.analyse(recs)
        self.assertEqual(r["mergeable"], 0)
        self.assertAlmostEqual(r["cpt"], 1.5)

    def test_the_surviving_turn_is_the_FIRST_one_not_the_priciest(self):
        """Two separate propositions, and an earlier test conflated them.

        (a) merged-away turns are priced at their own bill, not the corpus average;
        (b) the survivor is the turn the run STARTED at -- the merge happens there --
        so the saving is every turn AFTER the first. The old code dropped the
        largest bill instead of the smallest, i.e. it kept the priciest turn as the
        survivor, which understates the saving. Context is ascending within a run,
        so the two models diverge sharply: here 3,000 vs 32,000."""
        recs = [turn("m0", [("t0", "Read", {"file_path": "/e.md"})], ctx=10000),
                turn("m1", [("t1", "Read", {"file_path": "/e.md"})], ctx=20000),
                turn("m2", [("t2", "Read", {"file_path": "/e.md"})], ctx=300000)]
        r = self.analyse(recs)
        self.assertAlmostEqual(r["page_bill"], (20000 + 300000) * C.W_CACHE_READ)

    def test_run_length_is_recorded_and_k2_runs_recover_nothing(self):
        """A k=2 run contributes 1 to the theoretical collapse and 0 to what a
        discovery-read-first protocol can reach. 47 of 74 runs in the corpus are
        k=2, so conflating the two overstates the lever by ~2x."""
        recs = [turn("m0", [("t0", "Read", {"file_path": "/e.md"})]),
                turn("m1", [("t1", "Read", {"file_path": "/e.md"})])]
        r = self.analyse(recs)
        self.assertEqual(r["runlens"], [2])
        self.assertEqual(r["paging"], 1)
        self.assertEqual(r["recoverable"], 0)

    def test_a_k6_run_recovers_four_turns(self):
        recs = [turn(f"m{i}", [(f"t{i}", "Read", {"file_path": "/e.md"})])
                for i in range(6)]
        r = self.analyse(recs)
        self.assertEqual((r["runlens"], r["paging"], r["recoverable"]), ([6], 5, 4))

    def test_empty_transcript_returns_none(self):
        self.assertIsNone(self.analyse([]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
