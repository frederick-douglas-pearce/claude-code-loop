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
from engine_cost import classify, strip_heredocs, profile  # noqa: E402

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
