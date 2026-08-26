#!/usr/bin/env python3
"""Fixture tests for `rounds_vs_turns.py`'s budget-line parsing.

NOT part of the shipped suite -- under `docs/research/`, not `tests/`, per the
scope brake (a guard on analysis infrastructure is `tech-debt`, never a release
item). Same rationale as `test_engine_cost.py`.

Both bugs this parser has had are pinned below by the case that caught them.

    python3 docs/research/test_rounds_vs_turns.py
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rounds_vs_turns as R  # noqa: E402

WRAPPED = (
    "- Budget: subagent-runs=6 (architect x2, code-review, fresh re-check) ·\n"
    "  gate-rounds=architect=2(the second by human direction after the round-2 re-check\n"
    "  came back dirty),code-review=3,ac-verify=2 · ac-findings=3 · tokens=deferred\n"
)
FLAT = "- Budget: subagent-runs=3 · gate-rounds=architect=1,code-review=1,ac-verify=1 · x=1\n"


def write(records):
    fh = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False)
    for r in records:
        fh.write(json.dumps(r) + "\n")
    fh.close()
    return fh.name


def assistant_writing(text, mid="m1", sidechain=False):
    return {"type": "assistant", "isSidechain": sidechain,
            "message": {"id": mid, "usage": {},
                        "content": [{"type": "tool_use", "id": "t1", "name": "Bash",
                                     "input": {"command": "cat >> progress.md <<'EOF'\n"
                                                          + text + "EOF"}}]}}


def user_reading(text):
    return {"type": "user",
            "message": {"content": [{"type": "tool_result", "tool_use_id": "t9",
                                     "content": text}]},
            "toolUseResult": {"stdout": text}}


class BudgetParsingTests(unittest.TestCase):
    def tearDown(self):
        for p in getattr(self, "_paths", []):
            os.unlink(p)

    def parse(self, records):
        p = write(records)
        self._paths = [p]
        return R.budgets(p)

    def test_line_wrapped_gate_rounds_are_found(self):
        """BUG: `gate-rounds=` routinely sits on a continuation line. A single-line
        regex captured the prefix, found no rounds, and dropped 3 of 9 sessions."""
        got = self.parse([assistant_writing(WRAPPED)])
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["rounds"], 7)          # 2 + 3 + 2
        self.assertEqual(got[0]["runs"], 6)

    def test_flat_budget_line_is_found(self):
        got = self.parse([assistant_writing(FLAT)])
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["rounds"], 3)

    def test_budget_line_only_READ_BACK_is_not_counted(self):
        """BUG (direction): counting every occurrence counts lines the parent read
        out of progress.md as work done in this session. It gave one 158-turn
        session 11 issues at 14 turns each, against one-issue-per-invocation."""
        self.assertEqual(self.parse([user_reading(WRAPPED)]), [])

    def test_read_back_alongside_a_real_write_counts_once(self):
        got = self.parse([user_reading(WRAPPED), assistant_writing(FLAT)])
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["rounds"], 3)

    def test_streaming_duplicates_of_one_turn_count_once(self):
        got = self.parse([assistant_writing(FLAT, mid="m1"),
                          assistant_writing(FLAT, mid="m1")])
        self.assertEqual(len(got), 1)

    def test_sidechain_writes_are_ignored(self):
        self.assertEqual(self.parse([assistant_writing(FLAT, sidechain=True)]), [])

    def test_budget_line_without_gate_rounds_is_skipped(self):
        txt = "- Budget: subagent-runs=2 · wall-clock=~35m · tokens=deferred\n"
        self.assertEqual(self.parse([assistant_writing(txt)]), [])

    def test_two_distinct_issues_in_one_session_both_count(self):
        other = FLAT.replace("subagent-runs=3", "subagent-runs=9").replace(
            "architect=1", "architect=2")
        got = self.parse([assistant_writing(FLAT, mid="m1"),
                          assistant_writing(other, mid="m2")])
        self.assertEqual(len(got), 2)
        self.assertEqual(sorted(g["rounds"] for g in got), [3, 4])


class StatsTests(unittest.TestCase):
    def test_fit_recovers_a_known_line(self):
        b, a = R.fit([1, 2, 3, 4], [13, 23, 33, 43])
        self.assertAlmostEqual(b, 10.0)
        self.assertAlmostEqual(a, 3.0)

    def test_pearson_is_one_for_a_perfect_line(self):
        self.assertAlmostEqual(R.pearson([1, 2, 3], [2, 4, 6]), 1.0)

    def test_pearson_needs_three_points(self):
        self.assertIsNone(R.pearson([1, 2], [1, 2]))

    def test_fit_on_a_vertical_input_does_not_raise(self):
        self.assertEqual(R.fit([2, 2, 2], [1, 2, 3]), (None, None))


if __name__ == "__main__":
    unittest.main(verbosity=2)
