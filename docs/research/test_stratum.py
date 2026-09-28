#!/usr/bin/env python3
"""Fixture tests for `stratum.py` and for how each cost script is wired to it (#207).

NOT part of the shipped suite -- under `docs/research/`, not `tests/`, per the
scope brake. Same rationale as `test_engine_cost.py`.

The cases pin MECHANISM: a switched session is asserted by its presence in the
named-exclusion list with its reason, never only by a smaller n. Each pricing
weight is asserted by the literal bill one field produces (`PricingTests`), and the
cache-read weight also on a fixture where two models' weights disagree.

    python3 docs/research/test_stratum.py
"""
import contextlib
import io
import itertools
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stratum as S  # noqa: E402

M55, M5, M48 = "claude-opus-5-5", "claude-opus-5", "claude-opus-4-8"
UNPRICED = "claude-opus-9"     # well-formed, no PRICING entry

# A counter, never `id(object())`: CPython reuses a discarded object's id, so that
# default gave distinct records one `message.id`, which a dedupe then merges.
_IDS = itertools.count()


def arec(model=M55, effort="high", version="2.1.280", mid=None, usage=None,
         sidechain=False, ts=None, content=None):
    """One assistant record. `model=None` / `effort=None` omit the field."""
    msg = {"id": mid or "m%d" % next(_IDS), "content": content or []}
    if model is not None:
        msg["model"] = model
    if usage is not False:          # usage=False omits the field entirely
        msg["usage"] = usage if usage is not None else {
            "input_tokens": 10, "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0, "output_tokens": 5}
    r = {"type": "assistant", "isSidechain": sidechain, "message": msg}
    if effort is not None:
        r["effort"] = effort
    if version is not None:
        r["version"] = version
    if ts is not None:
        r["timestamp"] = ts
    return r


def synthetic(usage=None):
    r = {"type": "assistant", "isSidechain": False, "version": "2.1.280",
         "message": {"id": "syn", "model": S.SYNTHETIC, "content": []}}
    if usage is not False:
        r["message"]["usage"] = usage if usage is not None else {
            "input_tokens": 0, "output_tokens": 0,
            "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
    return r


class Sessions:
    """Temp project dir: `<root>/<stem>.jsonl` + `<root>/<stem>/subagents/*.jsonl`."""

    def setUp(self):
        self.root = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def session(self, stem, parent, subagents=None):
        path = os.path.join(self.root, stem + ".jsonl")
        with open(path, "w") as fh:
            for r in parent:
                fh.write(json.dumps(r) + "\n")
        for i, recs in enumerate(subagents or []):
            d = os.path.join(self.root, stem, "subagents")
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, "agent-%d.jsonl" % i), "w") as fh:
                for r in recs:
                    fh.write(json.dumps(r) + "\n")
        return path


def run(fn, *args):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fn(*args)
    return buf.getvalue()


class ExtractorTests(Sessions, unittest.TestCase):
    def test_a_single_stratum_resolves_to_its_exact_key(self):
        s = S.session_strata(self.session("one", [arec(), arec(), arec()]))
        self.assertEqual(s.parent, (M55, "high"))
        self.assertIsNone(s.reason)
        self.assertEqual(s.parent_records, 3)

    def test_a_mid_session_model_switch_is_unstratified_and_names_both_keys(self):
        s = S.session_strata(self.session("sw", [arec(M5, "xhigh"), arec(M55, "medium")]))
        self.assertIsNone(s.parent)
        self.assertIn("switched mid-session", s.reason)
        self.assertIn("claude-opus-5@xhigh", s.reason)
        self.assertIn("claude-opus-5-5@medium", s.reason)

    def test_a_model_change_alone_is_a_switch(self):
        s = S.session_strata(self.session("mo", [arec(M5, "high"), arec(M55, "high")]))
        self.assertIsNone(s.parent)
        self.assertIn("switched mid-session", s.reason)
        self.assertIn("claude-opus-5@high", s.reason)
        self.assertIn("claude-opus-5-5@high", s.reason)

    def test_an_effort_change_alone_is_a_switch(self):
        s = S.session_strata(self.session("ef", [arec(M55, "medium"), arec(M55, "high")]))
        self.assertIn("switched mid-session", s.reason)

    def test_a_record_with_no_effort_is_unstratified_never_defaulted(self):
        s = S.session_strata(self.session("ne", [arec(), arec(effort=None)]))
        self.assertIsNone(s.parent)
        self.assertIn("missing effort", s.reason)

    def test_a_record_with_no_model_is_unstratified(self):
        s = S.session_strata(self.session("nm", [arec(model=None)]))
        self.assertIn("missing model", s.reason)

    def test_an_unpriced_well_formed_model_forms_its_own_stratum(self):
        """Recognition never consults PRICING. An allowlist gate would make this
        session -- and every future model release -- unstratified."""
        s = S.session_strata(self.session("new", [arec(UNPRICED)]))
        self.assertEqual(s.parent, (UNPRICED, "high"))
        with self.assertRaises(S.UnknownModel):
            S.weights_for(UNPRICED)

    def test_an_unpriced_model_never_pools_with_a_priced_one(self):
        a = S.session_strata(self.session("a", [arec(UNPRICED)]))
        b = S.session_strata(self.session("b", [arec(M55)]))
        groups, excluded = S.group_by_stratum([a, b], key=lambda s: s)
        self.assertEqual(groups, {(UNPRICED, "high"): [a], (M55, "high"): [b]})
        self.assertEqual(excluded, [])

    def test_a_malformed_model_value_is_unstratified(self):
        for bad in ("Claude Opus!", "unknown", "", 5):
            with self.subTest(bad=bad):
                s = S.session_strata(self.session("bad", [arec(model=bad)]))
                self.assertIsNone(s.parent)

    def test_parent_stratum_stands_and_subagent_strata_are_recorded_not_grouped(self):
        p = self.session("mix", [arec(M55, "high")],
                         subagents=[[arec(M48, "xhigh"), arec(M48, "xhigh")],
                                    [arec(M55, "high")]])
        s = S.session_strata(p)
        self.assertEqual(s.parent, (M55, "high"))
        self.assertEqual(dict(s.subagents), {(M48, "xhigh"): 2, (M55, "high"): 1})
        other = S.session_strata(self.session("plain", [arec(M55, "high")]))
        groups, _ = S.group_by_stratum([s, other], key=lambda x: x)
        self.assertEqual(list(groups), [(M55, "high")])
        self.assertEqual(groups[(M55, "high")], [s, other])

    def test_subagent_strata_are_never_collapsed_in_the_line(self):
        p = self.session("mix", [arec(M55)],
                         subagents=[[arec(M48, "xhigh")] * 2, [arec(M55, "high")]])
        line = S.stratum_line(S.session_strata(p))
        self.assertIn("claude-opus-4-8@xhigh×2 rec", line)
        self.assertIn("claude-opus-5-5@high×1 rec", line)

    def test_a_sidechain_record_in_the_parent_is_not_a_parent_record(self):
        s = S.session_strata(self.session("sc", [arec(M55), arec(M48, "xhigh", sidechain=True)]))
        self.assertEqual(s.parent, (M55, "high"))
        self.assertEqual(s.parent_records, 1)


ZERO = {"input_tokens": 0, "output_tokens": 0,
        "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}


class SyntheticCarveOutTests(Sessions, unittest.TestCase):
    def test_a_zero_usage_record_from_a_real_model_is_counted_not_ignored(self):
        """The carve-out needs BOTH halves: model == <synthetic> AND zero usage.
        A real model's zero- or no-usage record is a real record -- here it is the
        record that switches, so ignoring it would hide the switch."""
        for usage in (ZERO, False):
            with self.subTest(usage=usage):
                s = S.session_strata(self.session("zr", [arec(M55), arec(M5, "xhigh", usage=usage)]))
                self.assertIsNone(s.parent)
                self.assertIn("switched mid-session", s.reason)
                self.assertEqual(s.synthetic_ignored, 0)
                self.assertEqual(s.parent_records, 2)

    def test_every_usage_field_counts_toward_nonzero(self):
        # A literal list, never S.USAGE_FIELDS: iterating the constant would let a
        # field dropped from it pass unnoticed.
        for field in ("input_tokens", "output_tokens",
                      "cache_creation_input_tokens", "cache_read_input_tokens"):
            with self.subTest(field=field):
                s = S.session_strata(self.session("f", [arec(), synthetic(dict(ZERO, **{field: 1}))]))
                self.assertIsNone(s.parent)
                self.assertEqual(s.synthetic_ignored, 0)

    def test_a_bool_usage_field_is_not_ignorable(self):
        """Pins the synthetic side of the one shared well-formedness predicate: a
        bool is malformed here exactly as it is in pricing."""
        s = S.session_strata(self.session("bo", [arec(), synthetic(dict(ZERO, output_tokens=False))]))
        self.assertIsNone(s.parent)
        self.assertEqual(s.synthetic_ignored, 0)

    def test_a_malformed_usage_field_is_not_ignorable_and_says_so(self):
        s = S.session_strata(self.session("mf", [arec(), synthetic(dict(ZERO, cache_read_input_tokens=None))]))
        self.assertIsNone(s.parent)
        self.assertIn("nonzero or malformed usage", s.reason)

    def test_a_nonzero_synthetic_SUBAGENT_record_is_recorded_not_unstratifying(self):
        """Ruling (2026-09-27): the parent key stands; the record is a subagent
        stratum, which is never a grouping key. Whole-tree pricing refuses it
        (test_tree_cost.py)."""
        s = S.session_strata(self.session("sn", [arec()], subagents=[[synthetic(dict(ZERO, output_tokens=7))]]))
        self.assertEqual(s.parent, (M55, "high"))
        self.assertEqual(dict(s.subagents), {(S.SYNTHETIC, None): 1})
        self.assertIn("<synthetic>@?×1 rec", S.stratum_line(s))

    def test_a_zero_usage_synthetic_record_is_ignored_and_counted(self):
        s = S.session_strata(self.session("z", [arec(), synthetic(), arec()]))
        self.assertEqual(s.parent, (M55, "high"))
        self.assertEqual(s.synthetic_ignored, 1)
        self.assertEqual(s.parent_records, 2)
        self.assertIn("1 synthetic ignored", S.stratum_line(s))

    def test_a_synthetic_record_with_no_usage_at_all_is_ignored(self):
        s = S.session_strata(self.session("z", [arec(), synthetic(usage=False)]))
        self.assertEqual((s.parent, s.synthetic_ignored), ((M55, "high"), 1))

    def test_a_synthetic_record_with_nonzero_usage_is_unstratified(self):
        s = S.session_strata(self.session("nz", [arec(), synthetic(
            {"input_tokens": 3, "output_tokens": 0,
             "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0})]))
        self.assertIsNone(s.parent)
        self.assertIn("<synthetic>", s.reason)

    def test_an_all_synthetic_session_is_unstratified(self):
        s = S.session_strata(self.session("all", [synthetic(), synthetic()]))
        self.assertIsNone(s.parent)
        self.assertIn("only <synthetic> parent records", s.reason)

    def test_the_only_synthetic_reason_counts_parent_records_alone(self):
        """A parent with no assistant record and a synthetic SUBAGENT record: the
        reason must not claim the parent's records were synthetic."""
        user = {"type": "user", "timestamp": "2026-09-27T08:00:00Z", "message": {}}
        s = S.session_strata(self.session("np", [user], subagents=[[synthetic()]]))
        self.assertEqual(s.reason, "no parent assistant record")
        self.assertEqual((s.synthetic_ignored, s.parent_synthetic_ignored), (1, 0))
        self.assertIn("1 synthetic ignored (0 parent)", S.stratum_line(s))

    def test_the_carve_out_applies_to_subagent_records(self):
        s = S.session_strata(self.session("sub", [arec()], subagents=[[synthetic(), arec(M48, "xhigh")]]))
        self.assertEqual(dict(s.subagents), {(M48, "xhigh"): 1})
        self.assertEqual(s.synthetic_ignored, 1)


class VersionAndStartTests(Sessions, unittest.TestCase):
    def test_versions_order_numerically_not_as_strings(self):
        s = S.session_strata(self.session("v", [arec(version="2.1.280"), arec(version="2.1.99"),
                                                arec(version="2.1.283")]))
        self.assertEqual((s.version_min, s.version_max), ("2.1.99", "2.1.283"))
        self.assertIn("cli 2.1.99–2.1.283", S.stratum_line(s))

    def test_subagent_versions_enter_the_cli_range(self):
        s = S.session_strata(self.session("sv", [arec(version="2.1.280")],
                                          subagents=[[arec(version="2.1.300"), arec(version=None)]]))
        self.assertEqual((s.version_min, s.version_max), ("2.1.280", "2.1.300"))
        self.assertEqual(s.missing_version, 1)

    def test_a_record_with_no_version_is_counted_not_dropped(self):
        s = S.session_strata(self.session("nv", [arec(), arec(version=None)]))
        self.assertEqual(s.parent_records, 2)
        self.assertEqual(s.missing_version, 1)
        self.assertIn("(+1 without version)", S.stratum_line(s))

    def test_start_is_the_first_parent_record_of_any_type(self):
        first = {"type": "user", "timestamp": "2026-09-27T08:01:12.345Z", "message": {}}
        side = {"type": "user", "isSidechain": True, "timestamp": "2026-09-20T00:00:00Z"}
        s = S.session_strata(self.session("t", [side, first, arec(ts="2026-09-27T09:00:00Z")]))
        self.assertEqual(s.started, "2026-09-27T08:01:12.345Z")
        self.assertIn("started 2026-09-27T08:01Z", S.stratum_line(s))


class GroupingTests(Sessions, unittest.TestCase):
    def test_every_exclusion_is_named_with_its_reason(self):
        ok = S.session_strata(self.session("ok", [arec()]))
        sw = S.session_strata(self.session("sw", [arec(M5, "xhigh"), arec(M55, "high")]))
        groups, excluded = S.group_by_stratum([("ok", ok), ("sw", sw)], key=lambda t: t[1])
        self.assertEqual(groups, {(M55, "high"): [("ok", ok)]})
        self.assertEqual(len(excluded), 1)
        (item, why), = excluded
        self.assertEqual(item[0], "sw")
        self.assertIn("UNSTRATIFIED", why)
        self.assertIn("switched mid-session", why)


class PricingTests(unittest.TestCase):
    def test_cache_read_is_per_model(self):
        self.assertEqual(S.weights_for(M5).cache_read, 0.1)
        self.assertEqual(S.weights_for(M55).cache_read, 0.05)

    def test_the_other_ratios_hold_on_both_models(self):
        for m in (M5, M55):
            w = S.weights_for(m)
            self.assertEqual((w.fresh, w.cache_write_5m, w.output), (1.0, 1.25, 5.0))

    def test_an_unknown_model_refuses_and_never_falls_back(self):
        for m in (UNPRICED, None, S.SYNTHETIC, "claude-sonnet-4-5"):
            with self.subTest(m=m):
                with self.assertRaises(S.UnknownModel):
                    S.weights_for(m)

    def test_a_present_malformed_token_field_never_prices_as_zero(self):
        """An absent field is 0, but a usage carrying NO token field (`{}`), a present
        malformed value -- null, a bool, a string -- or a non-dict usage refuses by
        name (#212/AC6). None of them is a $0 turn."""
        w = S.weights_for(M5)
        for bad in ({}, {"input_tokens": None}, {"cache_creation_input_tokens": True},
                    {"output_tokens": "1000000"}, [1, 2]):
            with self.subTest(bad=bad):
                with self.assertRaises(S.Unpriceable):
                    S.usd(bad, w)

    def test_tok_itself_still_raises_on_a_malformed_field(self):
        """`_tok` stays the backstop under the named refusal: a caller that reaches it
        directly still gets a loud TypeError, never a 0."""
        for bad in ({"input_tokens": None}, {"input_tokens": "1"}, [1]):
            with self.subTest(bad=bad):
                with self.assertRaises(TypeError):
                    S._tok(bad, "input_tokens")

    def test_each_field_is_priced_at_its_own_weight(self):
        """1M tokens of one field alone, as a literal dollar figure per field, so a
        dropped term or a wrong weight changes a number."""
        cases = [(M5, "input_tokens", 5.00), (M5, "cache_creation_input_tokens", 6.25),
                 (M5, "cache_read_input_tokens", 0.50), (M5, "output_tokens", 25.00),
                 (M55, "input_tokens", 4.00), (M55, "cache_creation_input_tokens", 5.00),
                 (M55, "cache_read_input_tokens", 0.20), (M55, "output_tokens", 20.00)]
        for model, field, dollars in cases:
            with self.subTest(model=model, field=field):
                self.assertAlmostEqual(S.usd({field: 1_000_000}, S.weights_for(model)), dollars)

    def test_usd_uses_the_models_own_base_price(self):
        one_m = {"input_tokens": 1_000_000}
        self.assertAlmostEqual(S.usd(one_m, S.weights_for(M55)), 4.0)
        self.assertAlmostEqual(S.usd(one_m, S.weights_for(M5)), 5.0)


# ------------------------------------------------ #212: the spec's per-turn arithmetic

ONE_M_IN = {"input_tokens": 1_000_000, "output_tokens": 0,
            "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}


def line(mid, usage, model=M5, **extra):
    """One transcript line of an assistant turn. `mid=None` omits `message.id`."""
    msg = {"model": model, "content": [], "usage": usage}
    if mid is not None:
        msg["id"] = mid
    r = {"type": "assistant", "effort": "high", "message": msg}
    r.update(extra)
    return r


class DedupeTests(unittest.TestCase):
    """AC2: group by `message.id`; the max-`output_tokens` record wins, first on a tie;
    every field comes from that one record."""

    def test_a_streamed_turn_split_across_three_lines_is_one_turn_priced_once(self):
        recs = [line("t", dict(ONE_M_IN, output_tokens=1)),
                line("t", dict(ONE_M_IN, output_tokens=9)),
                line("t", dict(ONE_M_IN, output_tokens=3))]
        ts, counts = S.turns(recs)
        self.assertEqual(len(ts), 1)
        self.assertIs(ts[0].winner, recs[1])
        self.assertEqual(ts[0].records, recs)
        self.assertEqual(counts.lines, 3)
        # Priced once: 1M input + 9 output on claude-opus-5, never 3M input.
        self.assertAlmostEqual(S.price_records(recs).usd, 5.0 + 9 * 25 / 1e6)

    def test_a_tie_on_output_keeps_the_first_record(self):
        a = line("t", dict(ONE_M_IN, output_tokens=5))
        b = line("t", dict(ONE_M_IN, input_tokens=7, output_tokens=5))
        (t,), _ = S.turns([a, b])
        self.assertIs(t.winner, a)

    def test_usage_is_taken_whole_from_the_winner_never_a_per_field_max(self):
        """A per-field max would take b's 1M input and a's 10 output."""
        a = line("t", {"input_tokens": 1, "output_tokens": 10})
        b = line("t", {"input_tokens": 1_000_000, "output_tokens": 2})
        (t,), _ = S.turns([a, b])
        self.assertIs(t.winner, a)
        self.assertAlmostEqual(S.price_records([a, b]).usd, (1 + 10 * 5) * 5.0 / 1e6)

    def test_the_merge_is_global_not_adjacent(self):
        a1, b, a2 = (line("a", dict(ONE_M_IN, output_tokens=1)), line("b", ONE_M_IN),
                     line("a", dict(ONE_M_IN, output_tokens=4)))
        ts, _ = S.turns([a1, b, a2])
        self.assertEqual([t.key for t in ts], ["a", "b"])
        self.assertEqual((ts[0].first_index, ts[0].records, ts[0].winner), (0, [a1, a2], a2))

    def test_a_record_with_no_id_is_its_own_turn_and_counted(self):
        recs = [line(None, ONE_M_IN), line(None, ONE_M_IN), line("t", ONE_M_IN)]
        ts, counts = S.turns(recs)
        self.assertEqual(len(ts), 3)
        self.assertEqual(counts.no_id, 2)
        self.assertNotEqual(ts[0].key, ts[1].key)
        self.assertAlmostEqual(S.price_records(recs).usd, 15.0)

    def test_non_assistant_records_are_not_turns(self):
        user = {"type": "user", "message": {"id": "t", "usage": ONE_M_IN, "content": []}}
        ts, counts = S.turns([user, line("t", ONE_M_IN)])
        self.assertEqual(len(ts), 1)
        self.assertEqual(ts[0].first_index, 1)
        self.assertEqual(counts.lines, 1)


class ExclusionTests(unittest.TestCase):
    """AC4."""

    def test_an_api_error_line_is_excluded_and_counted_even_with_usage(self):
        err = line("e", ONE_M_IN, isApiErrorMessage=True)
        ts, counts = S.turns([err, line("t", ONE_M_IN)])
        self.assertEqual([t.key for t in ts], ["t"])
        self.assertEqual(counts.api_error, 1)
        self.assertAlmostEqual(S.price_records([err, line("t", ONE_M_IN)]).usd, 5.0)

    def test_an_ignorable_synthetic_is_excluded_and_counted(self):
        ts, counts = S.turns([synthetic(), line("t", ONE_M_IN)])
        self.assertEqual(len(ts), 1)
        self.assertEqual(counts.synthetic, 1)

    def test_a_nonzero_synthetic_is_a_turn_and_refuses_to_price(self):
        syn = synthetic(dict(ONE_M_IN))
        ts, _ = S.turns([syn])
        self.assertEqual(len(ts), 1)
        with self.assertRaises(S.UnknownModel):
            S.price_records([syn])

    def test_tool_use_result_usage_and_iterations_are_never_priced(self):
        r = line("t", dict(ONE_M_IN, iterations=[dict(ONE_M_IN, input_tokens=999_000_000)]),
                 toolUseResult={"usage": dict(ONE_M_IN, input_tokens=999_000_000)})
        self.assertAlmostEqual(S.price_records([r]).usd, 5.0)


class CacheWriteSplitTests(unittest.TestCase):
    """AC3: 5-minute writes at 1.25x, 1-hour at 2x; an absent breakdown is all 5m."""

    def cc(self, m5, h1, total=None, model=M5):
        u = {"cache_creation_input_tokens": m5 + h1 if total is None else total,
             "cache_creation": {"ephemeral_5m_input_tokens": m5,
                                "ephemeral_1h_input_tokens": h1}}
        return S.usd(u, S.weights_for(model))

    def test_each_tier_is_priced_at_its_own_weight(self):
        self.assertAlmostEqual(self.cc(1_000_000, 0), 6.25)
        self.assertAlmostEqual(self.cc(0, 1_000_000), 10.0)
        self.assertAlmostEqual(self.cc(0, 1_000_000, model=M55), 8.0)
        self.assertAlmostEqual(self.cc(1_000_000, 1_000_000), 16.25)

    def test_an_absent_breakdown_is_all_five_minute(self):
        u = {"cache_creation_input_tokens": 1_000_000}
        self.assertAlmostEqual(S.usd(u, S.weights_for(M5)), 6.25)

    def test_a_split_that_disagrees_with_the_total_refuses_and_says_so(self):
        for m5, h1, total in ((600_000, 300_000, 1_000_000), (0, 0, 5), (10, 10, 5)):
            with self.subTest(m5=m5, h1=h1, total=total):
                with self.assertRaisesRegex(S.Unpriceable, "cache split"):
                    self.cc(m5, h1, total)

    def test_a_malformed_breakdown_refuses(self):
        for cc in ([1], {"ephemeral_1h_input_tokens": None}, {"ephemeral_5m_input_tokens": "5"}):
            with self.subTest(cc=cc):
                with self.assertRaises(S.Unpriceable):
                    S.usd({"cache_creation_input_tokens": 5, "cache_creation": cc},
                          S.weights_for(M5))


class LeverTests(unittest.TestCase):
    """AC6: no lever occurs in the corpus (plan-time census), so none is priced; a
    non-default value refuses rather than pricing at standard rates."""

    def test_a_non_default_lever_refuses(self):
        for extra in ({"speed": "fast"}, {"service_tier": "batch"},
                      {"service_tier": "priority"}, {"inference_geo": "us"},
                      {"server_tool_use": {"web_search_requests": 1}},
                      {"server_tool_use": {"web_fetch_requests": 2}},
                      {"server_tool_use": {"web_search_requests": None}},
                      {"server_tool_use": [1]}):
            with self.subTest(extra=extra):
                with self.assertRaises(S.Unpriceable):
                    S.usd(dict(ONE_M_IN, **extra), S.weights_for(M5))

    def test_the_default_values_price_at_standard_rates(self):
        for extra in ({"speed": "standard"}, {"service_tier": "standard"},
                      {"inference_geo": ""}, {"inference_geo": "not_available"},
                      {"inference_geo": "global"},
                      {"server_tool_use": {"web_search_requests": 0, "web_fetch_requests": 0}}):
            with self.subTest(extra=extra):
                self.assertAlmostEqual(S.usd(dict(ONE_M_IN, **extra), S.weights_for(M5)), 5.0)


class UsageShapeTests(unittest.TestCase):
    """#212/AC6: a usage that is not a well-formed dict refuses its session by name,
    checked on EVERY line of a turn -- never only the winner."""

    def test_a_non_dict_or_absent_usage_refuses(self):
        for bad in (None, [], 0, False, "x", [1]):
            with self.subTest(bad=bad):
                with self.assertRaises(S.Unpriceable):
                    S.turns([line("t", bad)])
        r = line("t", ONE_M_IN)
        del r["message"]["usage"]
        with self.assertRaises(S.Unpriceable):
            S.turns([r])

    def test_a_malformed_losing_line_still_refuses(self):
        good = line("t", dict(ONE_M_IN, output_tokens=9))
        bad = line("t", {"input_tokens": "1000000", "output_tokens": 1})
        with self.assertRaisesRegex(S.Unpriceable, "input_tokens"):
            S.turns([good, bad])

    def test_an_empty_usage_refuses_at_pricing_not_as_zero(self):
        ts, _ = S.turns([line("t", {})])
        self.assertEqual(len(ts), 1)
        with self.assertRaises(S.Unpriceable):
            S.price_records([line("t", {})])

    def test_every_refusal_is_one_family(self):
        self.assertTrue(issubclass(S.UnknownModel, S.Unpriced))
        self.assertTrue(issubclass(S.Unpriceable, S.Unpriced))


class PerTurnModelTests(unittest.TestCase):
    """AC5 / AC10: each turn on its own `message.model`; cross-model sums in USD."""

    def test_two_models_are_summed_in_usd_per_model(self):
        p = S.price_records([line("a", ONE_M_IN, model=M5),
                             line("b", ONE_M_IN, model="claude-sonnet-5")])
        self.assertAlmostEqual(p.usd, 7.0)
        self.assertEqual(set(p.by_model), {M5, "claude-sonnet-5"})
        self.assertAlmostEqual(p.by_model["claude-sonnet-5"], 2.0)

    def test_the_census_models_are_priced_at_the_pricing_page_rates(self):
        """Every field as a literal dollar figure, 1M tokens each (pricing page,
        2026-09-28). The 1h column is the one #212 adds."""
        rows = {"claude-opus-4-6": (5, 6.25, 10, 0.5, 25),
                "claude-sonnet-4-6": (3, 3.75, 6, 0.3, 15),
                "claude-sonnet-5": (2, 2.5, 4, 0.2, 10),
                "claude-haiku-4-5-20251001": (1, 1.25, 2, 0.1, 5),
                M55: (4, 5, 8, 0.2, 20), M5: (5, 6.25, 10, 0.5, 25),
                M48: (5, 6.25, 10, 0.5, 25), "claude-opus-4-7": (5, 6.25, 10, 0.5, 25)}
        one = 1_000_000
        for model, (inp, w5, w1, rd, out) in rows.items():
            w = S.weights_for(model)
            with self.subTest(model=model):
                self.assertAlmostEqual(S.usd({"input_tokens": one}, w), inp)
                self.assertAlmostEqual(S.usd({"cache_creation_input_tokens": one}, w), w5)
                self.assertAlmostEqual(S.usd({"cache_creation_input_tokens": one,
                                              "cache_creation": {"ephemeral_1h_input_tokens": one}},
                                             w), w1)
                self.assertAlmostEqual(S.usd({"cache_read_input_tokens": one}, w), rd)
                self.assertAlmostEqual(S.usd({"output_tokens": one}, w), out)

    def test_lookup_stays_exact_match(self):
        for m in ("claude-haiku-4-5", "claude-haiku-4-5-20251002", "claude-sonnet-5-0"):
            with self.subTest(m=m):
                with self.assertRaises(S.UnknownModel):
                    S.weights_for(m)

    def test_the_label_names_the_one_hour_weight(self):
        self.assertIn("2x 1h", S.weights_for(M5).label())

    def test_one_model_refuses_a_mix(self):
        ts, _ = S.turns([line("a", ONE_M_IN, model=M5), line("b", ONE_M_IN, model=M48)])
        with self.assertRaisesRegex(S.Unpriceable, "more than one model"):
            S.one_model(ts)
        self.assertEqual(S.one_model(ts[:1]), M5)


# ----------------------------------------------------------------- script wiring

ENG = "/home/u/.claude/plugins/cache/claude-code-loop/dev-loop/0.3.0/skills/dev-loop/loop-engine.md"


def engine_session(model, effort="high"):
    """An engine load followed by a turn. Both turns carry 1,000 cache-read tokens,
    so a cache-read weight of 0.05 and one of 0.1 produce different bills."""
    u0 = {"input_tokens": 10, "cache_read_input_tokens": 1000,
          "cache_creation_input_tokens": 0, "output_tokens": 5}
    u1 = dict(u0, input_tokens=10 + 5 + 100_000)
    return [
        arec(model, effort, mid="e0", usage=u0,
             content=[{"type": "tool_use", "id": "t0", "name": "Read",
                       "input": {"file_path": ENG}}]),
        {"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "t0", "content": "engine"}]}},
        arec(model, effort, mid="e1", usage=u1),
    ]


class EngineCostWiringTests(Sessions, unittest.TestCase):
    def setUp(self):
        super().setUp()
        import engine_cost
        self.E = engine_cost

    def test_the_bill_uses_the_parent_models_weights(self):
        # input side: (10 + 100_015) fresh + 2_000 cache-read x w; output 10 x 5
        p55 = self.E.profile(self.session("a", engine_session(M55)))
        p5 = self.E.profile(self.session("b", engine_session(M5)))
        self.assertAlmostEqual(p55["billable_total"], 100_025 + 2_000 * 0.05 + 50)
        self.assertAlmostEqual(p5["billable_total"], 100_025 + 2_000 * 0.1 + 50)

    def test_the_printed_ratio_label_is_the_weights_used(self):
        out55 = run(self.E.main, ["engine_cost.py", self.session("a", engine_session(M55))])
        out5 = run(self.E.main, ["engine_cost.py", self.session("b", engine_session(M5))])
        self.assertIn("@" + S.weights_for(M55).label(), out55)
        self.assertIn("0.05x in", out55)
        self.assertIn("0.1x in", out5)
        self.assertNotIn("0.1x in", out55)

    def test_the_stratum_line_sits_under_the_era_line(self):
        out = run(self.E.main, ["engine_cost.py", self.session("a", engine_session(M55))])
        lines = out.splitlines()
        i = next(k for k, l in enumerate(lines) if "engine era" in l)
        self.assertTrue(lines[i + 1].strip().startswith("stratum  claude-opus-5-5@high"))

    def test_a_refused_price_prints_refused_and_still_prints_p2c(self):
        out = run(self.E.main, ["engine_cost.py", self.session("n", engine_session(UNPRICED))])
        self.assertRegex(out, r"billable-equiv\s+REFUSED")
        self.assertIn("no PRICING entry", out)
        self.assertIn("REFUSED", out.split("eng bill")[1])
        self.assertIn("P2c  resident/processed", out)
        self.assertIn("stratum  claude-opus-9@high", out)

    def test_an_unstratified_session_refuses_to_price(self):
        recs = engine_session(M55)
        recs[-1] = arec(M5, "xhigh", mid="e1", usage=recs[-1]["message"]["usage"])
        p = self.E.profile(self.session("sw", recs))
        self.assertIsNone(p["billable_total"])
        self.assertIn("switched mid-session", p["price_refused"])


class EngineCostSpecTests(Sessions, unittest.TestCase):
    """#212: engine_cost routes through the shared dedupe and refusal family."""

    def setUp(self):
        super().setUp()
        import engine_cost
        self.E = engine_cost

    def test_a_streamed_turn_is_billed_on_its_max_output_line(self):
        recs = engine_session(M5)
        last = recs[-1]
        low = json.loads(json.dumps(last))
        low["message"]["usage"]["output_tokens"] = 1
        recs[-1:] = [low, last]                # same id "e1": output 1, then 5
        p = self.E.profile(self.session("s", recs))
        self.assertEqual(p["turns"], 2)
        self.assertAlmostEqual(p["billable_total"], 100_025 + 2_000 * 0.1 + 50)

    def test_a_no_id_line_is_its_own_turn_and_is_counted(self):
        recs = engine_session(M55)
        extra = arec(M55, "high")
        del extra["message"]["id"]
        p = self.E.profile(self.session("n", recs + [extra]))
        self.assertEqual((p["turns"], p["no_id"]), (3, 1))
        self.assertIn("no_id=1", run(self.E.render, p))

    def test_an_api_error_line_is_not_a_turn(self):
        err = arec(M55, "high", mid="err")
        err["isApiErrorMessage"] = True
        p = self.E.profile(self.session("e", engine_session(M55) + [err]))
        self.assertEqual((p["turns"], p["api_error"]), (2, 1))

    def test_usd_is_printed_beside_the_ratio(self):
        p = self.E.profile(self.session("u", engine_session(M5)))
        self.assertAlmostEqual(p["billable_usd"], (100_025 + 2_000 * 0.1 + 50) * 5.0 / 1e6)
        self.assertIn("$%.4f" % p["billable_usd"], run(self.E.render, p))

    def test_malformed_usage_refuses_the_session_by_name(self):
        recs = engine_session(M55)
        recs[-1]["message"]["usage"]["input_tokens"] = None
        path = self.session("bad", recs)
        with self.assertRaises(S.Unpriced):
            self.E.profile(path)
        out = run(self.E.main, ["engine_cost.py", path])
        self.assertIn("REFUSED", out)
        self.assertIn("input_tokens", out)

    def test_rounds_vs_turns_names_a_refused_session_and_keeps_the_rest(self):
        import rounds_vs_turns
        good = self.session("goodgood", budget_session(M55, "high", 1, 3))
        recs = budget_session(M55, "high", 1, 3)
        recs[1]["message"]["usage"] = [1]
        bad = self.session("badbadba", recs)       # 8 chars: the script prints [:8]
        out = run(rounds_vs_turns.main, ["r", good, bad])
        self.assertIn("EXCLUDED badbadba: refused", out)
        self.assertIn("n = 1 sessions (1 priced)", out)


def budget_session(model, effort, rounds, turns):
    line = ("- Budget: subagent-runs=2 · gate-rounds=architect=%d,code-review=1,"
            "ac-verify=1 · x=1\n" % rounds)
    recs = [arec(model, effort, mid="w",
                 content=[{"type": "tool_use", "id": "t1", "name": "Bash",
                           "input": {"command": "cat >> progress.md <<'EOF'\n" + line + "EOF"}}])]
    recs += [arec(model, effort, mid="x%d" % i) for i in range(turns)]
    return recs


class RoundsVsTurnsWiringTests(Sessions, unittest.TestCase):
    def setUp(self):
        super().setUp()
        import rounds_vs_turns
        self.R = rounds_vs_turns

    def test_statistics_run_per_stratum_and_unstratified_is_named(self):
        paths = [self.session("p55-%d" % i, budget_session(M55, "high", i, 3 + 2 * i))
                 for i in range(3)]
        paths += [self.session("p5-%d" % i, budget_session(M5, "xhigh", i, 4 + i))
                  for i in range(3)]
        paths.append(self.session("noeffort", budget_session(M55, None, 1, 3)))
        out = run(self.R.main, ["r"] + paths)
        self.assertIn("### stratum claude-opus-5-5@high", out)
        self.assertIn("### stratum claude-opus-5@xhigh", out)
        self.assertRegex(out, r"EXCLUDED noeffort: UNSTRATIFIED: missing effort")
        self.assertEqual(out.count("n = 3 sessions (3 priced)"), 2)

    def test_a_price_refused_session_stays_in_the_turns_fit_only(self):
        paths = [self.session("unp-%d" % i, budget_session(UNPRICED, "high", i, 3 + 2 * i))
                 for i in range(3)]
        out = run(self.R.main, ["r"] + paths)
        for i in range(3):
            self.assertIn("EXCLUDED from bill-based statistics only unp-%d" % i, out)
        self.assertIn("n = 3 sessions (0 priced)", out)
        self.assertRegex(out, r"rounds/issue -> turns/issue\s+r = \+1\.00")
        self.assertRegex(out, r"rounds/issue -> bill/issue\s+n/a")
        self.assertIn("fit      tpi", out)
        self.assertNotIn("fit      bpi", out)

    def test_every_session_prints_its_stratum_line(self):
        p = self.session("one", budget_session(M55, "high", 1, 3))
        self.assertIn("stratum  claude-opus-5-5@high", run(self.R.main, ["r", p]))


class CallsPerTurnWiringTests(Sessions, unittest.TestCase):
    def setUp(self):
        super().setUp()
        import calls_per_turn
        self.C = calls_per_turn

    def turns(self, model, effort, n):
        return [arec(model, effort, mid="c%d" % i,
                     content=[{"type": "tool_use", "id": "u%d" % i, "name": "Read",
                               "input": {"file_path": "/f.md"}}]) for i in range(n)]

    def test_the_input_bill_uses_the_parent_models_weights(self):
        def paging(model):
            return [arec(model, "high", mid="c%d" % i, usage={"cache_read_input_tokens": ctx},
                         content=[{"type": "tool_use", "id": "u%d" % i, "name": "Read",
                                   "input": {"file_path": "/e.md"}}])
                    for i, ctx in enumerate((10000, 20000, 300000))]
        r55 = self.C.analyse(self.session("a", paging(M55)))
        r5 = self.C.analyse(self.session("b", paging(M5)))
        self.assertAlmostEqual(r55["page_bill"], 16000.0)    # (20k + 300k) x 0.05
        self.assertAlmostEqual(r5["page_bill"], 32000.0)     # (20k + 300k) x 0.1

    def test_every_session_prints_its_full_stratum_line(self):
        a = self.session("aaaaaaaa", self.turns(M55, "high", 3),
                         subagents=[[arec(M48, "xhigh")]])
        c = self.session("cccccccc", self.turns(M55, None, 2))
        out = run(self.C.main, ["c", a, c])
        for p in (a, c):
            self.assertIn(S.stratum_line(S.session_strata(p)), out)

    def test_non_numeric_usage_is_not_priced_as_zero(self):
        """Refused, named, and absent from the corpus totals (#212/AC6)."""
        recs = self.turns(M55, "high", 2)
        recs[1]["message"]["usage"] = {"cache_read_input_tokens": "9000"}
        bad = self.session("badbadba", recs)
        with self.assertRaises(S.Unpriced):
            self.C.analyse(bad)
        good = self.session("aaaaaaaa", self.turns(M55, "high", 3))
        out = run(self.C.main, ["c", good, bad])
        self.assertIn("EXCLUDED badbadba: refused", out)
        self.assertIn("cache_read_input_tokens", out)
        self.assertIn("corpus: 3 turns", out)

    def test_corpus_totals_are_per_stratum(self):
        a = self.session("aaaaaaaa", self.turns(M55, "high", 3))
        b = self.session("bbbbbbbb", self.turns(M5, "xhigh", 2))
        c = self.session("cccccccc", self.turns(M55, None, 4))
        out = run(self.C.main, ["c", a, b, c])
        sec55 = out.split("### stratum claude-opus-5-5@high")[1].split("### stratum")[0]
        sec5 = out.split("### stratum claude-opus-5@xhigh")[1].split("### stratum")[0]
        self.assertIn("corpus: 3 turns", sec55)
        self.assertIn("corpus: 2 turns", sec5)
        self.assertIn("EXCLUDED cccccccc: UNSTRATIFIED: missing effort", out)
        self.assertNotIn("corpus: 9 turns", out)

    def test_a_price_refused_session_leaves_the_weighted_totals_only(self):
        a = self.session("aaaaaaaa", self.turns(UNPRICED, "high", 3))
        out = run(self.C.main, ["c", a])
        self.assertIn("corpus: 3 turns", out)
        self.assertIn("EXCLUDED from the weighted totals only aaaaaaaa", out)
        self.assertNotIn("of input bill", out)

    def test_the_naive_figure_names_the_model_it_was_fitted_on(self):
        a = self.session("aaaaaaaa", self.turns(M55, "high", 3))
        self.assertIn("Finding 10, claude-opus-5 @xhigh+@high, n=8; spans a stratum",
                      run(self.C.main, ["c", a]))


class PlanGateCostWiringTests(Sessions, unittest.TestCase):
    def test_the_report_prints_the_stratum_line(self):
        import plan_gate_cost as pgc
        plan = {"type": "tool_use", "id": "p", "name": "Write",
                "input": {"file_path": "/repo/.claude/loop/v0.3.1/issue-42.plan.md"}}
        p = self.session("pg", [arec(M55, "high", mid="g0"),
                                arec(M55, "high", mid="g1", content=[plan])])
        result = pgc.analyze(p)
        self.assertIsNotNone(result)
        out = run(pgc._report, result)
        self.assertIn("stratum  claude-opus-5-5@high", out)


class BudgetStatsBannerTests(unittest.TestCase):
    def test_output_states_it_cannot_stratify(self):
        import budget_stats
        root = tempfile.mkdtemp()
        try:
            out = run(budget_stats.main, ["b", root])
        finally:
            shutil.rmtree(root)
        self.assertIn("NOT STRATIFIED", out)
        self.assertIn("no model or effort", out)
        self.assertTrue(out.startswith(budget_stats.STRATUM_BANNER))


if __name__ == "__main__":
    unittest.main(verbosity=2)
