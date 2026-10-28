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
import datetime
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


def rec(model, effort="high", usage=None, timestamp=None):
    """Each call is its own API turn: a distinct `message.id`, so a dedupe never
    merges two fixture records that a test means to be two turns."""
    r = {"type": "assistant", "effort": effort, "version": "2.1.280",
         "message": {"id": "x%d" % next(_IDS), "model": model, "content": [],
                     "usage": usage if usage is not None else ONE_M}}
    if timestamp is not None:
        r["timestamp"] = timestamp
    return r


def at(seconds):
    """A transcript timestamp `seconds` after a fixed origin, `Z`-suffixed as
    transcripts write it."""
    when = datetime.datetime(2026, 10, 1) + datetime.timedelta(seconds=seconds)
    return when.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def writes(n, tier="1h"):
    """Usage writing `n` cache tokens on one tier, nothing else."""
    cc = {"ephemeral_5m_input_tokens": n if tier == "5m" else 0,
          "ephemeral_1h_input_tokens": n if tier == "1h" else 0}
    return {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": n, "cache_creation": cc}


READ_ONLY = {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 1000,
             "cache_creation_input_tokens": 0}

#: The hand-checked session of appendix D. It lives outside the repo, so the test
#: that reads it skips where it is absent.
D_SESSION = pathlib.Path(os.path.expanduser(
    "~/.claude/projects/-home-fdpearce-Documents-Projects-git-us-presidential-vote-analysis"
    "/3f30a898-e246-47ff-95aa-0b2ebceb383e.jsonl"))


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


class RewarmTests(unittest.TestCase):
    """The re-warm term (#287): cache writes on a parent turn after an idle gap
    longer than the TTL of the cache an earlier turn wrote."""

    def setUp(self):
        self.root = pathlib.Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def row(self, parent, subs=()):
        (self.root / "p.jsonl").write_text("".join(json.dumps(r) + "\n" for r in parent))
        if subs:
            d = self.root / "p" / "subagents"
            d.mkdir(parents=True)
            for i, recs in enumerate(subs):
                (d / ("a%d.jsonl" % i)).write_text("".join(json.dumps(r) + "\n" for r in recs))
        r = T.price_session(self.root / "p.jsonl")
        self.assertIsNone(r["refused"])
        return r

    def pair(self, gap, first="1h", second="1h", n=1_000_000):
        """A writer at 0 and a second writer `gap` seconds later."""
        return self.row([rec(M55, usage=writes(n, first), timestamp=at(0)),
                         rec(M55, usage=writes(n, second), timestamp=at(gap))])

    def test_a_write_after_a_gap_longer_than_the_ttl_is_a_rewarm(self):
        r = self.pair(3601)
        self.assertEqual(len(r["rewarms"]), 1)
        self.assertAlmostEqual(r["rewarm_usd"], 8.0)        # 1M 1h writes @ 2 x $4
        self.assertEqual(r["rewarms"][0][1:3], (3601, 1_000_000))

    def test_a_gap_equal_to_the_ttl_is_not_a_rewarm(self):
        r = self.pair(3600)
        self.assertEqual((r["rewarms"], r["rewarm_usd"]), ([], 0))

    def test_a_gap_shorter_than_the_ttl_is_not_a_rewarm(self):
        self.assertEqual(self.pair(1800)["rewarms"], [])

    def test_the_first_turn_is_never_a_rewarm(self):
        r = self.row([rec(M55, usage=writes(1000), timestamp=at(0))])
        self.assertEqual((r["rewarms"], r["rewarm_usd"]), ([], 0))

    def test_a_turn_that_writes_no_cache_is_never_a_rewarm(self):
        r = self.row([rec(M55, usage=writes(1000), timestamp=at(0)),
                      rec(M55, usage=READ_ONLY, timestamp=at(7200))])
        self.assertEqual(r["rewarms"], [])

    def test_a_turn_with_no_earlier_writer_has_nothing_to_expire(self):
        r = self.row([rec(M55, usage=READ_ONLY, timestamp=at(0)),
                      rec(M55, usage=writes(1000), timestamp=at(7200))])
        self.assertEqual(r["rewarms"], [])

    def test_the_ttl_is_the_earlier_writers_tier_not_this_turns(self):
        """The entry that expired is the earlier one. A 5-minute writer then a 1-hour
        write 301s later is a re-warm; the reverse is not."""
        r = self.pair(301, first="5m", second="1h")
        self.assertAlmostEqual(r["rewarm_usd"], 8.0)
        self.assertEqual(self.pair(301, first="1h", second="5m")["rewarms"], [])

    def test_only_the_write_tokens_of_a_rewarm_turn_are_priced(self):
        """The re-warm turn also reads, takes fresh input and writes output; none of
        that is in the term, all of it is in the bill."""
        busy = dict(writes(500_000), input_tokens=100_000, output_tokens=100_000,
                    cache_read_input_tokens=100_000)
        r = self.row([rec(M55, usage=writes(1_000_000), timestamp=at(0)),
                      rec(M55, usage=busy, timestamp=at(3601))])
        self.assertAlmostEqual(r["rewarm_usd"], 4.0)        # 500k 1h writes @ 2 x $4
        self.assertAlmostEqual(r["parent_usd"], 8.0 + 4.0 + 0.4 + 2.0 + 0.02)

    def test_a_rewarm_is_priced_on_its_own_model(self):
        r = self.row([rec(M55, usage=writes(1000), timestamp=at(0)),
                      rec(M48, usage=writes(1_000_000), timestamp=at(3601))])
        self.assertAlmostEqual(r["rewarm_usd"], 10.0)      # 1M 1h writes @ 2 x $5

    def test_a_read_only_turn_between_writers_keeps_the_expiring_tier(self):
        """A non-writing turn keeps the earlier writer's tier and still anchors the gap."""
        r = self.row([rec(M55, usage=writes(1000), timestamp=at(0)),
                      rec(M55, usage=READ_ONLY, timestamp=at(10)),
                      rec(M55, usage=writes(1000), timestamp=at(3700))])
        self.assertEqual(len(r["rewarms"]), 1)
        r = self.row([rec(M55, usage=writes(1000), timestamp=at(0)),
                      rec(M55, usage=READ_ONLY, timestamp=at(3000)),
                      rec(M55, usage=writes(1000), timestamp=at(4000))])
        self.assertEqual(r["rewarms"], [])

    def test_a_five_minute_gap_equal_to_the_ttl_is_not_a_rewarm(self):
        self.assertEqual(self.pair(300, first="5m")["rewarms"], [])

    def test_each_tier_is_priced_at_its_own_write_rate(self):
        self.assertAlmostEqual(self.pair(3601, first="1h", second="5m")["rewarm_usd"], 5.0)

    def test_the_ttl_follows_the_most_recent_writer(self):
        """1h writer, then a 5m writer, then a write 400s later: the 5m entry is the
        one that expired."""
        r = self.row([rec(M55, usage=writes(1000, "1h"), timestamp=at(0)),
                      rec(M55, usage=writes(1000, "5m"), timestamp=at(10)),
                      rec(M55, usage=writes(1000, "1h"), timestamp=at(410))])
        self.assertEqual(len(r["rewarms"]), 1)
        r = self.row([rec(M55, usage=writes(1000, "5m"), timestamp=at(0)),
                      rec(M55, usage=writes(1000, "1h"), timestamp=at(10)),
                      rec(M55, usage=writes(1000, "5m"), timestamp=at(410))])
        self.assertEqual(r["rewarms"], [])

    def test_an_unreadable_earlier_tier_makes_the_term_unknown_not_zero(self):
        absent = {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0,
                  "cache_creation_input_tokens": 1000}
        r = self.row([rec(M55, usage=absent, timestamp=at(0)),
                      rec(M55, usage=writes(1000), timestamp=at(600))])
        self.assertIsNone(r["rewarm_usd"])
        self.assertIsNone(r["rewarms"])
        self.assertIn("tier unreadable", r["rewarm_unknown"])
        self.assertIsNotNone(r["parent_usd"])               # the bill still prices

    def test_an_earlier_writer_on_both_tiers_makes_the_term_unknown(self):
        both = dict(writes(2000), cache_creation={"ephemeral_5m_input_tokens": 1000,
                                                  "ephemeral_1h_input_tokens": 1000})
        r = self.row([rec(M55, usage=both, timestamp=at(0)),
                      rec(M55, usage=writes(1000), timestamp=at(600))])
        self.assertIsNone(r["rewarm_usd"])
        self.assertIn("tier unreadable", r["rewarm_unknown"])

    def test_an_unreadable_tier_is_unknown_only_where_the_gap_could_exceed_it(self):
        """No TTL is shorter than five minutes, and a turn that writes nothing is no
        re-warm whatever expired, so neither needs the tier."""
        absent = {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0,
                  "cache_creation_input_tokens": 1000}
        for second, gap in ((writes(1000), 300), (READ_ONLY, 600)):
            with self.subTest(gap=gap):
                r = self.row([rec(M55, usage=absent, timestamp=at(0)),
                              rec(M55, usage=second, timestamp=at(gap))])
                self.assertEqual((r["rewarms"], r["rewarm_unknown"]), ([], None))

    def test_the_gap_runs_from_the_previous_turns_last_record_to_this_turns_first(self):
        """Turn A streams at 0 and 1000; turn B at 4500 and 8000. From A's last
        record to B's first is 3500 -- no re-warm. From A's first (4500), or to B's
        last (7000), would be one."""
        a, b = rec(M55, usage=writes(1000)), rec(M55, usage=writes(1000))
        recs = [dict(a, timestamp=at(0)), dict(a, timestamp=at(1000)),
                dict(b, timestamp=at(4500)), dict(b, timestamp=at(8000))]
        r = self.row(recs)
        self.assertEqual(r["turns"], 2)
        self.assertEqual(r["rewarms"], [])

    def test_an_offset_timestamp_parses_like_a_z_one(self):
        r = self.row([rec(M55, usage=writes(1000), timestamp="2026-10-01T00:00:00+00:00"),
                      rec(M55, usage=writes(1000), timestamp="2026-10-01T01:00:01+00:00")])
        self.assertEqual(len(r["rewarms"]), 1)

    def test_a_missing_or_unparseable_timestamp_makes_the_term_unknown(self):
        for bad in (None, "yesterday", "2026-10-01T00:00:00"):     # the last is naive
            with self.subTest(bad=bad):
                r = self.row([rec(M55, usage=writes(1000), timestamp=at(0)),
                              rec(M55, usage=writes(1000), timestamp=bad)])
                self.assertIsNone(r["rewarm_usd"])
                self.assertIsNone(r["rewarms"])
                self.assertIn("no readable timestamp", r["rewarm_unknown"])

    def test_a_missing_timestamp_on_a_turns_last_record_makes_the_term_unknown(self):
        a = rec(M55, usage=writes(1000))
        r = self.row([dict(a, timestamp=at(0)), dict(a),
                      rec(M55, usage=writes(1000), timestamp=at(7200))])
        self.assertIsNone(r["rewarm_usd"])
        self.assertIn("no readable timestamp", r["rewarm_unknown"])

    def test_a_backwards_timestamp_makes_the_term_unknown(self):
        r = self.row([rec(M55, usage=writes(1000), timestamp=at(100)),
                      rec(M55, usage=writes(1000), timestamp=at(0))])
        self.assertIsNone(r["rewarms"])
        self.assertIn("backwards", r["rewarm_unknown"])

    def test_a_turn_whose_own_records_run_backwards_makes_the_term_unknown(self):
        """Read as A's last record, t=0 would put B 3700s after A instead of 700s."""
        a = rec(M55, usage=writes(1000))
        r = self.row([dict(a, timestamp=at(3000)), dict(a, timestamp=at(0)),
                      rec(M55, usage=writes(1000), timestamp=at(3700))])
        self.assertIsNone(r["rewarms"])
        self.assertIn("backwards", r["rewarm_unknown"])

    def test_equal_timestamps_are_not_backwards(self):
        """Between turns, and between the records of one turn."""
        r = self.row([rec(M55, usage=writes(1000), timestamp=at(0)),
                      rec(M55, usage=writes(1000), timestamp=at(0))])
        self.assertEqual((r["rewarms"], r["rewarm_unknown"]), ([], None))
        a = rec(M55, usage=writes(1000))
        r = self.row([dict(a, timestamp=at(0)), dict(a, timestamp=at(0))])
        self.assertEqual((r["rewarms"], r["rewarm_unknown"]), ([], None))

    def test_a_fraction_of_any_length_parses_the_same_on_every_version(self):
        """Bites only below Python 3.11, whose `fromisoformat` rejects these fractions
        without the normalization; this file is not in CI, so run it on 3.9 by hand."""
        for frac in ("1", "123", "123456", "123456789"):
            with self.subTest(frac=frac):
                r = self.row([rec(M55, usage=writes(1000), timestamp="2026-10-01T00:00:00Z"),
                              rec(M55, usage=writes(1000),
                                  timestamp="2026-10-01T01:00:01.%sZ" % frac)])
                self.assertEqual(len(r["rewarms"]), 1)

    def test_subagent_turns_are_not_counted(self):
        sub = [rec(M55, usage=writes(1000), timestamp=at(0)),
               rec(M55, usage=writes(1000), timestamp=at(7200))]
        r = self.row([rec(M55, usage=writes(1000), timestamp=at(0))], [sub])
        self.assertEqual(r["rewarms"], [])

    def test_the_term_leaves_the_bill_untouched(self):
        r = self.pair(3601)
        self.assertAlmostEqual(r["parent_usd"], T.bill(self.root / "p.jsonl")[0].usd)
        self.assertAlmostEqual(r["parent_usd"], 16.0)      # both writes, re-warm included once

    def test_sessions_mode_prints_unknown_and_excludes_it_from_totals(self):
        self.pair(3601)
        (self.root / "q.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in [rec(M55, usage=writes(1000)),
                                                    rec(M55, usage=writes(1000))]))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            T.main(["--sessions", str(self.root / "p.jsonl"), str(self.root / "q.jsonl")])
        out = buf.getvalue()
        p_line = [ln for ln in out.splitlines() if ln.startswith("p ")][0]
        self.assertEqual(p_line.split()[2::4], ["16.00", "8.00"])  # parent $, re-warm $
        q_line = [ln for ln in out.splitlines() if ln.startswith("q ")][0]
        self.assertIn("unknown", q_line)
        self.assertIn("re-warm unknown, EXCLUDED from re-warm totals q:", out)
        stratum = [ln for ln in out.splitlines() if ln.startswith("# stratum")][0]
        self.assertIn("2 sessions | parent $16.02", stratum)     # the bill keeps q
        self.assertIn("re-warm $8.00 (1 of 2 sessions)", stratum)

    def test_a_stratum_with_no_known_term_prints_unknown_not_zero(self):
        self.row([rec(M55, usage=writes(1000), timestamp=at(0)),
                  rec(M55, usage=writes(1000))])
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            T.main(["--sessions", str(self.root / "p.jsonl")])
        stratum = [ln for ln in buf.getvalue().splitlines() if ln.startswith("# stratum")][0]
        self.assertTrue(stratum.endswith("| re-warm unknown"), stratum)

    @unittest.skipUnless(D_SESSION.is_file(), "appendix D's transcript is not on this machine")
    def test_appendix_d_session_reproduces_seven_rewarms_and_27_80(self):
        r = T.price_session(D_SESSION)
        self.assertIsNone(r["refused"])
        self.assertIsNone(r["rewarm_unknown"])
        self.assertEqual(len(r["rewarms"]), 7)
        self.assertAlmostEqual(r["rewarm_usd"], 27.80, delta=0.05)


if __name__ == "__main__":
    unittest.main(verbosity=2)
