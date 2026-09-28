#!/usr/bin/env python3
"""Fixture tests for `tree_cost.py`: per-stratum grouping and per-model pricing
summed in US dollars (#207), and the spec's billing arithmetic -- the
`message.id` dedupe and named refusals (#212). The arithmetic itself is pinned in
`test_stratum.py`; this file pins that `tree_cost` routes through it.

NOT part of the shipped suite -- under `docs/research/`, not `tests/`, per the
scope brake. Same rationale as `test_engine_cost.py`.

    python3 docs/research/test_tree_cost.py
"""
import contextlib
import io
import itertools
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


_IDS = itertools.count()


def rec(model, effort="high", usage=None):
    """Each call is its own API turn: a distinct `message.id`, so a dedupe never
    merges two fixture records that a test means to be two turns."""
    return {"type": "assistant", "effort": effort, "version": "2.1.280",
            "message": {"id": "x%d" % next(_IDS), "model": model, "content": [],
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

    def test_a_nonzero_usage_synthetic_subagent_record_refuses_the_session(self):
        syn = {"type": "assistant", "message": {"model": "<synthetic>", "usage": dict(ONE_M)}}
        self.session("aaaaaaaa", [rec(M55)], [[rec(M55), syn]])
        rows, refused = T.survey(self.root)
        self.assertEqual(rows, [])
        self.assertEqual(refused[0][0], "aaaaaaaa")
        self.assertIn("<synthetic>", refused[0][2])

    def test_a_non_numeric_token_field_is_never_priced_as_zero(self):
        """Refused, named, and absent from the rows (#212/AC6) -- not a crash."""
        bad = rec(M55, usage={"input_tokens": "1000000"})
        self.session("aaaaaaaa", [rec(M55), bad], [[rec(M55)]])
        self.session("bbbbbbbb", [rec(M55)], [[rec(M55)]])
        rows, refused = T.survey(self.root)
        self.assertEqual([r[0] for r in rows], ["bbbbbbbb"])
        self.assertEqual(refused[0][0], "aaaaaaaa")
        self.assertIn("input_tokens", refused[0][2])
        self.assertIn("EXCLUDED aaaaaaaa: price refused", self.out())

    def test_a_streamed_subagent_turn_is_priced_once(self):
        """Three lines of one API call, each repeating 1M input: $5, never $15."""
        line = rec(M48, "xhigh")
        streamed = [dict(line, message=dict(line["message"], id="same")) for _ in range(3)]
        self.session("aaaaaaaa", [rec(M55)], [streamed])
        (name, turns, parent_usd, n_subs, sub_usd, _), = T.survey(self.root)[0]
        self.assertAlmostEqual(sub_usd, 5.0)
        priced, _ = T.bill(self.root / "aaaaaaaa" / "subagents" / "a0.jsonl")
        self.assertEqual(len(priced.turns), 1)          # the SUBAGENT's three lines, one turn
        self.assertEqual(priced.counts.lines, 3)

    def test_an_opus_parent_and_a_newly_priced_subagent_sum_in_usd(self):
        """AC10: the parent on claude-opus-5-5 ($4/M input), the subagent on
        claude-sonnet-5 ($2/M input)."""
        self.session("aaaaaaaa", [rec(M55)], [[rec("claude-sonnet-5", "medium")]])
        rows, refused = T.survey(self.root)
        self.assertEqual(refused, [])
        (_, _, parent_usd, _, sub_usd, _), = rows
        self.assertAlmostEqual(parent_usd, 4.0)
        self.assertAlmostEqual(sub_usd, 2.0)
        self.assertIn("33.3%", self.out())

    def test_a_well_formed_unpriced_subagent_model_refuses_the_whole_session(self):
        self.session("aaaaaaaa", [rec(M55)], [[rec("claude-sonnet-9", "medium")]])
        rows, refused = T.survey(self.root)
        self.assertEqual(rows, [])
        self.assertIn("claude-sonnet-9", refused[0][2])

    def test_an_api_error_line_is_not_billed(self):
        err = rec(M55)
        err["isApiErrorMessage"] = True
        self.session("aaaaaaaa", [rec(M55), err], [[rec(M55)]])
        (_, turns, parent_usd, _, _, _), = T.survey(self.root)[0]
        self.assertAlmostEqual(parent_usd, 4.0)
        self.assertEqual(turns, 1)

    def test_no_id_lines_and_ids_in_more_than_one_file_are_counted_and_printed(self):
        noid = rec(M55)
        del noid["message"]["id"]
        shared = rec(M55)
        self.session("aaaaaaaa", [noid, shared], [[dict(shared)]])
        counts = {}
        T.survey(self.root, counts)
        self.assertEqual(counts["aaaaaaaa"]["no_id"], 1)
        self.assertEqual(counts["aaaaaaaa"]["cross_file_ids"], 1)
        out = self.out()
        self.assertIn("no_id=1", out)
        self.assertIn("ids in >1 file=1", out)

    def test_no_id_lines_in_a_subagent_file_count_too(self):
        """The count covers every file of the session, not only the parent's."""
        noid = rec(M55)
        del noid["message"]["id"]
        self.session("aaaaaaaa", [rec(M55)], [[rec(M55), noid], [dict(noid)]])
        counts = {}
        T.survey(self.root, counts)
        self.assertEqual(counts["aaaaaaaa"]["no_id"], 2)

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
