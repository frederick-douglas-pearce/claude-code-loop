#!/usr/bin/env python3
"""Fixture tests for `tree_cost.py`, scoped to what #207 added: per-stratum grouping
and per-record, per-model pricing summed in US dollars.

The billing arithmetic itself (no `message.id` dedupe, 1-hour cache writes) is NOT
covered here; it is #212's.

NOT part of the shipped suite -- under `docs/research/`, not `tests/`, per the
scope brake. Same rationale as `test_engine_cost.py`.

    python3 docs/research/test_tree_cost.py
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
import tree_cost as T  # noqa: E402

M55, M48 = "claude-opus-5-5", "claude-opus-4-8"
ONE_M = {"input_tokens": 1_000_000, "output_tokens": 0,
         "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}


def rec(model, effort="high", usage=None):
    return {"type": "assistant", "effort": effort, "version": "2.1.280",
            "message": {"id": "x", "model": model, "content": [],
                        "usage": usage if usage is not None else ONE_M}}


class TreeCostTests(unittest.TestCase):
    def setUp(self):
        self.root = pathlib.Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def session(self, stem, parent, subs):
        (self.root / (stem + ".jsonl")).write_text("".join(json.dumps(r) + "\n" for r in parent))
        d = self.root / stem / "subagents"
        d.mkdir(parents=True)
        for i, recs in enumerate(subs):
            (d / ("a%d.jsonl" % i)).write_text("".join(json.dumps(r) + "\n" for r in recs))

    def out(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            T.main([str(self.root)])
        return buf.getvalue()

    def test_each_record_is_priced_by_its_own_model_in_usd(self):
        """1M input tokens on each side. Summed in ratio units the two halves are
        equal (50%); in dollars the 4-8 subagent costs $5 against the 5-5 parent's
        $4. Only the second is a cost."""
        self.session("aaaaaaaa", [rec(M55)], [[rec(M48, "xhigh")]])
        rows, refused = T.survey(self.root)
        self.assertEqual(refused, [])
        (name, records, parent_usd, n_subs, sub_usd, _), = rows
        self.assertAlmostEqual(parent_usd, 4.0)
        self.assertAlmostEqual(sub_usd, 5.0)
        self.assertIn("55.6%", self.out())

    def test_totals_are_grouped_per_parent_stratum(self):
        self.session("aaaaaaaa", [rec(M55)], [[rec(M55)]])
        self.session("bbbbbbbb", [rec(M55)], [[rec(M48, "xhigh")]])
        self.session("cccccccc", [rec(M48, "xhigh")], [[rec(M48, "xhigh")]])
        out = self.out()
        sec55 = out.split("### stratum claude-opus-5-5@high")[1].split("### stratum")[0]
        sec48 = out.split("### stratum claude-opus-4-8@xhigh")[1].split("### stratum")[0]
        self.assertIn("2 delegating sessions", sec55)
        self.assertIn("1 delegating sessions", sec48)
        self.assertNotIn("3 delegating sessions", out)

    def test_an_unpriced_model_on_any_record_refuses_the_session_and_names_it(self):
        self.session("aaaaaaaa", [rec(M55)], [[rec(M55), rec("claude-opus-9")]])
        self.session("bbbbbbbb", [rec(M55)], [[rec(M55)]])
        rows, refused = T.survey(self.root)
        self.assertEqual([r[0] for r in rows], ["bbbbbbbb"])
        self.assertEqual(refused[0][0], "aaaaaaaa")
        self.assertIn("claude-opus-9", refused[0][2])
        out = self.out()
        self.assertIn("EXCLUDED aaaaaaaa: price refused", out)
        self.assertIn("1 delegating sessions", out)

    def test_an_unstratified_parent_is_excluded_and_named(self):
        self.session("aaaaaaaa", [rec(M55, "medium"), rec(M55, "high")], [[rec(M55)]])
        out = self.out()
        self.assertRegex(out, r"EXCLUDED aaaaaaaa: UNSTRATIFIED: switched mid-session")
        self.assertNotIn("### stratum", out)

    def test_a_zero_usage_synthetic_record_is_skipped_not_refused(self):
        syn = {"type": "assistant", "message": {"model": "<synthetic>", "usage": {
            "input_tokens": 0, "output_tokens": 0, "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0}}}
        self.session("aaaaaaaa", [rec(M55), syn], [[rec(M55)]])
        rows, refused = T.survey(self.root)
        self.assertEqual(refused, [])
        self.assertEqual(rows[0][1], 1)

    def test_every_session_prints_its_stratum_line(self):
        self.session("aaaaaaaa", [rec(M55)], [[rec(M48, "xhigh")]])
        self.assertIn("stratum  claude-opus-5-5@high", self.out())


if __name__ == "__main__":
    unittest.main(verbosity=2)
