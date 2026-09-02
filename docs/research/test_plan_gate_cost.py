#!/usr/bin/env python3
"""Behavioral tests for plan_gate_cost.py.

Each test names the mutation it kills. The one that matters most is
`test_cost_comes_from_the_context_delta_not_the_result_size`: it is the executable
statement of decision D010, the payload bug that retired `context_profile.py`.
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import plan_gate_cost as pgc


def assistant(context, output_tokens=0, calls=(), cache_creation=0):
    """One assistant turn. `context` is the input side; cache tiers are split out."""
    return {
        "type": "assistant",
        "message": {
            "usage": {
                "input_tokens": context - cache_creation,
                "cache_read_input_tokens": 0,
                "cache_creation_input_tokens": cache_creation,
                "output_tokens": output_tokens,
            },
            "content": [
                {"type": "tool_use", "id": cid, "name": name, "input": args}
                for cid, name, args in calls
            ],
        },
    }


def results(*pairs):
    return {
        "type": "user",
        "message": {
            "content": [
                {"type": "tool_result", "tool_use_id": cid, "content": "x" * size}
                for cid, size in pairs
            ]
        },
    }


PLAN_WRITE = ("plan", "Write", {"file_path": "/repo/.claude/loop/v0.2.1/issue-42.plan.md"})


def transcript(*entries):
    handle = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False)
    for entry in entries:
        handle.write(json.dumps(entry) + "\n")
    handle.close()
    return handle.name


class ContextTokenTests(unittest.TestCase):
    def test_sums_fresh_input_and_both_cache_tiers(self):
        """Kills: dropping cache_creation, which is where a re-read after eviction lands."""
        usage = {"input_tokens": 10, "cache_read_input_tokens": 100, "cache_creation_input_tokens": 1000}
        self.assertEqual(pgc.context_tokens(usage), 1110)

    def test_absent_usage_is_zero_not_a_crash(self):
        self.assertEqual(pgc.context_tokens(None), 0)


class ClassifyTests(unittest.TestCase):
    def test_installed_engine_outranks_in_tree_engine(self):
        """Kills: reordering _classify_read so an installed-plugin path falls through.

        The distinction is the whole point in the authoring repo, where an in-tree engine
        read is the work under way and the installed read is the loop's own overhead.
        """
        installed = "/home/u/.claude/plugins/cache/claude-code-loop/dev-loop/0.2.1/skills/dev-loop/loop-engine.md"
        self.assertEqual(pgc.classify("Read", {"file_path": installed}), "ENGINE read (installed)")
        self.assertEqual(
            pgc.classify("Read", {"file_path": "/repo/skills/dev-loop/loop-engine.md"}),
            "engine read (in-tree)",
        )

    def test_a_heredoc_to_progress_is_a_write_not_a_ledger_read(self):
        """Kills: classifying journal appends as reads, which double-counts model output.

        The heredoc's bulk is the model's own output and is already in that bucket; counting
        it again as an arriving read is the specific error this separation prevents.
        """
        append = "cat >> .claude/loop/v0.2.1/progress.md <<'EOF'\nentry\nEOF"
        self.assertEqual(pgc.classify("Bash", {"command": append}), "ledger write")
        self.assertEqual(
            pgc.classify("Bash", {"command": "sed -n '1,50p' .claude/loop/v0.2.1/progress.md"}),
            "ledger read",
        )

    def test_gh_issue_and_pr_reads_are_separate_buckets(self):
        self.assertEqual(pgc.classify("Bash", {"command": "gh issue view 42"}), "gh issue read")
        self.assertEqual(pgc.classify("Bash", {"command": "gh pr list"}), "gh pr read")


class AttributionTests(unittest.TestCase):
    def test_cost_comes_from_the_context_delta_not_the_result_size(self):
        """Kills: reintroducing D010 — sizing the tool result instead of the context delta.

        The call below returns 4 characters and costs 40,000 tokens, which is exactly the
        spilled-read shape that over-counted by up to 13x. Any implementation that prices a
        call by its result text fails here.
        """
        path = transcript(
            assistant(1_000, output_tokens=0, calls=[("c1", "Read", {"file_path": "/x/engine.md"})]),
            results(("c1", 4)),
            assistant(41_000, output_tokens=0, calls=[PLAN_WRITE]),
        )
        result = pgc.analyze(path)
        os.unlink(path)
        self.assertEqual(round(result["by_source"]["repo file read"]), 40_000)

    def test_model_output_is_subtracted_from_the_delta(self):
        """Kills: attributing the model's own output to whatever tool ran next."""
        path = transcript(
            assistant(1_000, output_tokens=500, calls=[("c1", "Bash", {"command": "ls"})]),
            results(("c1", 100)),
            assistant(2_000, output_tokens=0, calls=[PLAN_WRITE]),
        )
        result = pgc.analyze(path)
        os.unlink(path)
        self.assertEqual(round(result["by_source"]["search"]), 500)
        self.assertEqual(result["model_output"], 500)

    def test_multi_call_turns_split_by_result_size_and_are_flagged_estimated(self):
        """Result size is legitimate for SPLITTING a shared delta — never for pricing one call."""
        path = transcript(
            assistant(1_000, calls=[("c1", "Bash", {"command": "ls"}),
                                    ("c2", "Bash", {"command": "git log"})]),
            results(("c1", 250), ("c2", 750)),
            assistant(5_000, calls=[PLAN_WRITE]),
        )
        result = pgc.analyze(path)
        os.unlink(path)
        self.assertEqual(round(result["by_source"]["search"]), 1_000)
        self.assertEqual(round(result["by_source"]["git"]), 3_000)
        self.assertEqual(round(result["multi_call_estimated"]), 4_000)

    def test_baseline_is_the_first_turns_context_not_zero(self):
        """The always-loaded floor arrives before any delta exists, so no delta-based
        instrument sees it. Kills: starting the accounting at the first tool call."""
        path = transcript(assistant(55_000, calls=[PLAN_WRITE]))
        result = pgc.analyze(path)
        os.unlink(path)
        self.assertEqual(result["baseline"], 55_000)


class AnchorTests(unittest.TestCase):
    def test_anchor_is_the_first_plan_write_not_a_later_one(self):
        """Kills: anchoring on the last plan write, which would sweep in review-round context."""
        path = transcript(
            assistant(1_000, calls=[PLAN_WRITE]),
            results(("plan", 10)),
            assistant(99_000, calls=[PLAN_WRITE]),
        )
        result = pgc.analyze(path)
        os.unlink(path)
        self.assertEqual(result["resident_at_plan_gate"], 1_000)

    def test_a_session_that_never_writes_a_plan_returns_none(self):
        path = transcript(assistant(1_000, calls=[("c1", "Bash", {"command": "ls"})]))
        result = pgc.analyze(path)
        os.unlink(path)
        self.assertIsNone(result)


class CompactionTests(unittest.TestCase):
    def test_a_compaction_before_the_anchor_is_detected_and_reported(self):
        """Kills: silently summing growth across an eviction, which counts bytes twice.

        Without this the session still prints a plausible number, so the failure is invisible
        — which is why detection is reported rather than left to the reader.
        """
        path = transcript(
            assistant(100_000, calls=[("c1", "Bash", {"command": "ls"})]),
            results(("c1", 10)),
            assistant(20_000, calls=[("c2", "Bash", {"command": "ls"})]),
            results(("c2", 10)),
            assistant(60_000, calls=[PLAN_WRITE]),
        )
        result = pgc.analyze(path)
        os.unlink(path)
        self.assertEqual(len(result["compactions"]), 1)
        self.assertEqual(result["compactions"][0], 80_000)

    def test_ordinary_jitter_is_not_a_compaction(self):
        path = transcript(
            assistant(100_000, calls=[("c1", "Bash", {"command": "ls"})]),
            results(("c1", 10)),
            assistant(99_000, calls=[PLAN_WRITE]),
        )
        result = pgc.analyze(path)
        os.unlink(path)
        self.assertEqual(result["compactions"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
