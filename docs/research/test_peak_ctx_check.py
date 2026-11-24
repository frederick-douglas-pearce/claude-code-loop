#!/usr/bin/env python3
"""Synthetic-replicate tests for `peak_ctx_check.py` (#394).

NOT part of the shipped suite -- lives under `docs/research/`, not `tests/`, so
`python3 -m unittest discover -s tests` does not pick it up; `TEST_CMD`'s second
half runs it, and CI does not (#286).

Every replicate here is written by the test; nothing reads a real one. The cases
pin the verdict: the two counts agreeing exits 0; a real divergent record (an
`isApiErrorMessage` line, which the independent count includes and `turns()`
excludes) exits 1; an unparseable line exits 1 even when the peaks agree; a second
project dir refuses; and the independent count reads all three context fields.

    python3 docs/research/test_peak_ctx_check.py
"""
import contextlib
import io
import json
import os
import pathlib
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import peak_ctx_check as pc  # noqa: E402


def call(mid, ctx, **extra):
    third = ctx // 3
    rec = {"type": "assistant", "effort": "high", "message": {
        "id": mid, "model": "claude-sonnet-5-5", "usage": {
            "input_tokens": ctx - 2 * third, "cache_read_input_tokens": third,
            "cache_creation_input_tokens": third, "output_tokens": 5},
        "content": [{"type": "text", "text": "."}]}}
    rec.update(extra)
    return rec


class PeakCtxCheckTests(unittest.TestCase):

    def setUp(self):
        self.root = pathlib.Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(str(self.root))

    def replicate(self, name, recs, raw=(), extra_project=False):
        rdir = self.root / name
        proj = rdir / "home" / ".claude" / "projects"
        (proj / "slug").mkdir(parents=True)
        if extra_project:
            (proj / "elsewhere").mkdir()
        (rdir / "environment.json").write_text(json.dumps({"project_slug": "slug"}))
        with open(str(proj / "slug" / "s.jsonl"), "w") as fh:
            for r in recs:
                fh.write(json.dumps(r) + "\n")
            for line in raw:
                fh.write(line + "\n")
        return rdir

    def run_main(self, *rdirs):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = pc.main([str(r) for r in rdirs])
        return rc, out.getvalue()

    def test_agreement_exits_zero(self):
        r = self.replicate("ok", [call("m0", 1000), call("m1", 61_000)])
        rc, out = self.run_main(r)
        self.assertEqual(rc, 0, out)
        self.assertIn("ok\t1\t61000\t61000\t0\tequal", out)

    def test_an_api_error_line_is_a_mismatch(self):
        r = self.replicate("err", [call("m0", 1000),
                                   call("e0", 500_000, isApiErrorMessage=True)])
        rc, out = self.run_main(r)
        self.assertEqual(rc, 1)
        self.assertIn("err\t1\t1000\t500000\t0\tMISMATCH", out)

    def test_an_unparseable_line_fails_even_when_peaks_agree(self):
        r = self.replicate("trunc", [call("m0", 2000)], raw=['{"type": "assist'])
        rc, out = self.run_main(r)
        self.assertEqual(rc, 1)
        self.assertIn("trunc\t1\t2000\t2000\t1\tMISMATCH", out)

    def test_a_second_project_dir_refuses(self):
        r = self.replicate("two", [call("m0", 2000)], extra_project=True)
        rc, out = self.run_main(r)
        self.assertEqual(rc, 1)
        self.assertIn("REFUSED: project_dir:", out)

    def test_one_bad_replicate_fails_the_run(self):
        good = self.replicate("good", [call("m0", 3000)])
        bad = self.replicate("bad", [call("m0", 3000)], raw=["nope"])
        rc, _ = self.run_main(good, bad)
        self.assertEqual(rc, 1)

    def test_the_independent_count_reads_all_three_fields(self):
        path = self.root / "f.jsonl"
        path.write_text(json.dumps(call("m0", 9000)) + "\n"
                        + json.dumps(call("s0", 99_000, isSidechain=True)) + "\n")
        self.assertEqual(pc.independent_peak([path]), (9000, 0))

    def test_no_arguments_prints_usage(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(pc.main([]), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
