#!/usr/bin/env python3
"""Fixture tests for `engine_cost.py`'s detection.

NOT part of the shipped suite -- lives under `docs/research/`, not `tests/`, so
`python3 -m unittest discover -s tests` does not pick it up. The scope brake says
a guard on analysis infrastructure is `tech-debt` and never ships in a release;
this respects that while still making the instrument executable rather than
re-derived by reading, which is exactly the failure `tests/test_mutate_verify.py`
exists to prevent.

Every case below is a real shape taken from a transcript, and each of the three
detection bugs is pinned by the case that caught it.

    python3 docs/research/test_engine_cost.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from engine_cost import (  # noqa: E402
    classify, strip_heredocs, profile,
    engine_version, engine_bytes, floor_for, KNOWN_ENGINE_BYTES,
)

CACHE = "/home/u/.claude/plugins/cache/claude-code-loop/dev-loop/0.2.0/skills/dev-loop/loop-engine.md"
TREE = "/home/u/Documents/Projects/git/claude-code-loop/skills/dev-loop/loop-engine.md"
SPILL = "/home/u/.claude/projects/-slug/abc123/tool-results/bz0uty70f.txt"


def bash(cmd):
    return classify("Bash", {"command": cmd})


class ClassifyTests(unittest.TestCase):
    def test_plain_cat_of_plugin_engine_is_a_load(self):
        self.assertEqual(bash("cat " + CACHE), "load")

    def test_sed_slice_via_shell_variable_is_a_load(self):
        self.assertEqual(bash("ENG=%s; sed -n '1,140p' $ENG" % CACHE), "load")

    def test_read_tool_on_plugin_path_is_a_load(self):
        self.assertEqual(classify("Read", {"file_path": CACHE}), "load")

    def test_working_tree_read_is_tree_not_load(self):
        """BUG 2. This repo develops the engine, so it reads the in-tree copy as a
        work product. Counting it as a loop cost inflated one session by ~44%."""
        self.assertEqual(classify("Read", {"file_path": TREE}), "tree")

    def test_heredoc_write_mentioning_engine_is_not_a_read(self):
        """BUG 1. Scored 9 reads in a session that had 1."""
        self.assertIsNone(bash(
            "cat > .claude/loop/progress.md <<'EOF'\nsee loop-engine.md step 4\nEOF"))

    def test_python_heredoc_editing_a_doc_is_not_a_read(self):
        self.assertIsNone(bash(
            "python3 - <<'PY'\np='skills/dev-loop/loop-engine.md'\nPY"))

    def test_real_read_after_a_heredoc_write_is_still_found(self):
        """Cutting at the first `<<` lost this shape, which the loop uses often."""
        self.assertEqual(
            bash("cat >> progress.md <<'EOF'\nnote\nEOF\nsed -n '1,50p' " + CACHE),
            "load")

    def test_spill_recovery_read_inherits_the_original_kind(self):
        """BUG 3. The spill path holds no `loop-engine.md` substring, so these
        eight reads vanished and a full engine load measured as ~10% of one."""
        self.assertEqual(
            classify("Bash", {"command": "sed -n '1,250p' " + SPILL},
                     spills={SPILL: "load"}),
            "load")

    def test_spill_path_is_not_an_engine_read_without_the_registry(self):
        self.assertIsNone(bash("sed -n '1,250p' " + SPILL))

    def test_wc_returns_a_scalar_not_the_file(self):
        self.assertIsNone(bash("wc -c " + CACHE))

    def test_grep_counting_flag_is_not_a_read(self):
        self.assertIsNone(bash("grep -c 'step 4' " + CACHE))

    def test_grep_piped_to_wc_is_not_a_read(self):
        self.assertIsNone(bash("grep -oE 'step [0-9]' " + CACHE + " | wc -l"))

    def test_grep_returning_lines_is_a_read(self):
        self.assertEqual(bash("grep -n 'Gate-outcome' " + CACHE), "load")

    def test_sed_in_place_edits_rather_than_reads(self):
        self.assertIsNone(bash("sed -i 's/a/b/' " + TREE))

    def test_unrelated_command_is_not_a_read(self):
        self.assertIsNone(bash("git status"))

    def test_non_dict_input_does_not_raise(self):
        self.assertIsNone(classify("Bash", None))


class StripHeredocTests(unittest.TestCase):
    def test_body_removed_terminator_survives(self):
        self.assertNotIn("SECRET", strip_heredocs("cat > f <<'EOF'\nSECRET\nEOF\nls"))
        self.assertIn("ls", strip_heredocs("cat > f <<'EOF'\nSECRET\nEOF\nls"))

    def test_unterminated_heredoc_drops_the_rest(self):
        self.assertNotIn("SECRET", strip_heredocs("cat > f <<'EOF'\nSECRET"))

    def test_command_without_heredoc_is_unchanged(self):
        self.assertEqual(strip_heredocs("sed -n '1,5p' x").strip(), "sed -n '1,5p' x")


class ProfileTests(unittest.TestCase):
    def test_empty_transcript_returns_none_rather_than_raising(self):
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_empty.jsonl")
        open(p, "w").close()
        try:
            self.assertIsNone(profile(p))
        finally:
            os.unlink(p)




class AdmissibilityTests(unittest.TestCase):
    """The floor is a PRECONDITION of measurement, not a filter.

    The README asserted this behaviour before the code had it -- a documented
    default-deny rule that was in fact fail-open, which is the exact shape
    CLAUDE.md warns about. These pin the implementation.
    """

    def test_a_session_below_one_engine_copy_is_inadmissible(self):
        p = {"ingested": 6088, "floor": 50723}
        self.assertLess(p["ingested"], p["floor"])

    def test_default_floor_is_about_one_engine_copy(self):
        from engine_cost import DEFAULT_FLOOR
        self.assertGreater(DEFAULT_FLOOR, 45000)
        self.assertLess(DEFAULT_FLOOR, 60000)

    def test_profile_reports_admissibility_on_a_real_shaped_transcript(self):
        import json as _json
        import tempfile
        recs = [{"type": "assistant", "message": {"id": "m0", "usage":
                 {"cache_read_input_tokens": 1000}, "content": [
                     {"type": "tool_use", "id": "t0", "name": "Bash",
                      "input": {"command": "cat " + CACHE}}]}},
                {"type": "user", "message": {"content": [
                    {"type": "tool_result", "tool_use_id": "t0", "content": "x" * 500}]}},
                {"type": "assistant", "message": {"id": "m1", "usage":
                 {"cache_read_input_tokens": 3000}, "content": []}}]
        fh = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False)
        for r in recs:
            fh.write(_json.dumps(r) + "\n")
        fh.close()
        try:
            p = profile(fh.name)
            self.assertIn("admissible", p)
            self.assertFalse(p["admissible"])   # tiny fixture is far below the floor
        finally:
            os.unlink(fh.name)


class EraFloorTests(unittest.TestCase):
    """The admissibility floor must track the engine that actually ran.

    REGRESSION, 2026-09-12. The floor was the constant `177529 / 3.5` -- one
    0.2.0 engine -- and v0.3.0 grew the engine to 267,647 bytes. That turned a
    default-DENY guard fail-OPEN: a 0.3.0 session holding 66-99% of its engine
    cleared a 0.2.0-sized bar and was scored admissible. These cases pin the
    mechanism (the floor is a function of the era) rather than the outcome (some
    particular number), because a test asserting `floor == 76470` would pass for
    an implementation that hardcoded 0.3.0 and go stale at the next release in
    exactly the same way.
    """

    _ENG = "/home/u/.claude/plugins/cache/claude-code-loop/dev-loop/%s/skills/dev-loop/loop-engine.md"

    def test_version_is_read_off_the_installed_path(self):
        for v in ("0.2.0", "0.2.1", "0.3.0"):
            self.assertEqual(engine_version("Read", {"file_path": self._ENG % v}), v)

    def test_working_tree_read_carries_no_version(self):
        """The in-tree copy has no version segment, so it yields no era."""
        self.assertIsNone(
            engine_version("Read", {"file_path": "/repo/skills/dev-loop/loop-engine.md"}))

    def test_a_bash_slice_still_yields_its_version(self):
        cmd = "sed -n '1,400p' " + self._ENG % "0.3.0"
        self.assertEqual(engine_version("Bash", {"command": cmd}), "0.3.0")

    def test_a_larger_engine_raises_the_floor(self):
        """THE REGRESSION. A wider engine must demand more before admitting."""
        self.assertGreater(floor_for("0.3.0"), floor_for("0.2.1"))

    def test_floor_tracks_engine_size_rather_than_a_constant(self):
        """Mechanism, not magnitude: floor is proportional to the era's bytes."""
        for a, b in (("0.2.0", "0.3.0"), ("0.2.1", "0.3.0")):
            ratio_bytes = engine_bytes(b) / engine_bytes(a)
            ratio_floor = floor_for(b) / floor_for(a)
            self.assertAlmostEqual(ratio_bytes, ratio_floor, places=6)

    def test_a_partial_load_of_the_wider_engine_is_inadmissible(self):
        """The exact false-admit: enough for a 0.2.0 copy, short of a 0.3.0 one."""
        partial = engine_bytes("0.2.0") / 3.5        # a whole 0.2.0 engine
        self.assertGreaterEqual(partial, floor_for("0.2.0"))   # fine as 0.2.0
        self.assertLess(partial, floor_for("0.3.0"))           # short as 0.3.0

    def test_unknown_era_defaults_to_the_widest_engine_not_the_narrowest(self):
        """Default-deny. Sizing an unattributable session off the SMALLEST engine
        would rebuild the fail-open this function replaced."""
        widest = max(KNOWN_ENGINE_BYTES.values())
        self.assertAlmostEqual(floor_for(None), widest / 3.5, places=6)
        for v in KNOWN_ENGINE_BYTES:
            self.assertGreaterEqual(floor_for(None), floor_for(v))

    def test_an_evicted_version_falls_back_to_the_table_not_to_zero(self):
        """A version no longer in the plugin cache must not size the floor at 0."""
        self.assertEqual(engine_bytes("0.2.0"), KNOWN_ENGINE_BYTES["0.2.0"])

    def test_an_entirely_unknown_version_still_yields_a_usable_floor(self):
        self.assertIsNone(engine_bytes("9.9.9"))
        self.assertGreater(floor_for("9.9.9"), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
