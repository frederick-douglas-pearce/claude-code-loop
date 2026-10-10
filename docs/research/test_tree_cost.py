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

    def sessions_out(self, *stems):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            T.main(["--sessions"] + [str(self.root / (s + ".jsonl")) for s in stems])
        return buf.getvalue()

    def test_sessions_mode_prices_a_session_that_never_delegated(self):
        """`survey` skips these by design; a per-issue bill must not. Its
        subagent bill is a measured 0."""
        (self.root / "solo.jsonl").write_text(json.dumps(rec(M55)) + "\n")
        r = T.price_session(self.root / "solo.jsonl")
        self.assertIsNone(r["refused"])
        self.assertEqual((r["subs"], r["sub_usd"]), (0, 0))
        self.assertAlmostEqual(r["parent_usd"], 4.0)          # 1M fresh input @ $4

    def test_sessions_mode_keeps_parent_and_subagents_separate(self):
        self.session("s1", [rec(M55)], [[rec(M48)]])
        r = T.price_session(self.root / "s1.jsonl")
        self.assertAlmostEqual(r["parent_usd"], 4.0)
        self.assertAlmostEqual(r["sub_usd"], 5.0)
        self.assertIn("parent $4.00 | subagent $5.00 | total $9.00",
                      self.sessions_out("s1"))

    def test_context_counts_cache_writes_toward_the_bound(self):
        """Class B survivor T5: an impossible context held in cache WRITES must
        refuse as surely as one held in fresh input or cache reads."""
        wide = {"input_tokens": 1, "output_tokens": 0, "cache_read_input_tokens": 0,
                "cache_creation_input_tokens": T.MAX_CONTEXT}
        (self.root / "cw.jsonl").write_text(json.dumps(rec(M55, usage=wide)) + "\n")
        self.assertIn("physically impossible",
                      T.price_session(self.root / "cw.jsonl")["refused"])

    def test_a_turn_wider_than_any_context_window_refuses_the_session(self):
        """A dedupe that merged several calls into one would produce exactly this."""
        wide = dict(ONE_M, cache_read_input_tokens=T.MAX_CONTEXT)
        self.session("w", [rec(M55)], [[rec(M55, usage=wide)]])
        r = T.price_session(self.root / "w.jsonl")
        self.assertIn("physically impossible", r["refused"])
        self.assertIsNone(r["parent_usd"])
        self.assertIn("REFUSED", self.sessions_out("w"))

    def test_output_beyond_the_largest_max_tokens_refuses(self):
        big = dict(ONE_M, input_tokens=10, output_tokens=T.MAX_OUTPUT + 1)
        (self.root / "o.jsonl").write_text(json.dumps(rec(M55, usage=big)) + "\n")
        self.assertIn("physically impossible",
                      T.price_session(self.root / "o.jsonl")["refused"])

    def test_a_turn_at_the_bounds_is_priced(self):
        edge = {"input_tokens": T.MAX_CONTEXT, "output_tokens": T.MAX_OUTPUT,
                "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
        (self.root / "e.jsonl").write_text(json.dumps(rec(M55, usage=edge)) + "\n")
        self.assertIsNone(T.price_session(self.root / "e.jsonl")["refused"])

    def test_an_unpriced_subagent_refuses_the_named_session(self):
        self.session("u", [rec(M55)], [[rec("claude-unpriced-9")]])
        self.assertIn("REFUSED", self.sessions_out("u"))

    def test_a_message_id_priced_in_two_files_refuses_the_session(self):
        """mc.8: an id names one API call; in two files it is a turn priced twice."""
        r0 = rec(M55)
        twin = json.loads(json.dumps(r0))
        self.session("d", [r0], [[twin]])
        r = T.price_session(self.root / "d.jsonl")
        self.assertIn("more than one file", r["refused"])
        self.assertIsNone(r["parent_usd"])

    def test_sessions_totals_never_pool_across_strata(self):
        self.session("hi", [rec(M55, "high")], [[rec(M55, "high")]])
        self.session("md", [rec(M55, "medium")], [[rec(M55, "medium")]])
        out = self.sessions_out("hi", "md")
        self.assertIn("# stratum claude-opus-5-5@high: 1 sessions", out)
        self.assertIn("# stratum claude-opus-5-5@medium: 1 sessions", out)
        self.assertNotIn("total $16.00", out)

    def test_an_unstratified_session_is_excluded_from_totals_and_named(self):
        bad = rec(M55)
        del bad["effort"]
        self.session("un", [bad], [[rec(M55)]])
        out = self.sessions_out("un")
        self.assertIn("EXCLUDED from totals un", out)
        self.assertNotIn("# stratum", out)

    def test_every_session_prints_its_stratum_line(self):
        self.session("aaaaaaaa", [rec(M55)], [[rec(M48, "xhigh")]])
        self.assertIn("stratum  claude-opus-5-5@high", self.out())


if __name__ == "__main__":
    unittest.main(verbosity=2)
