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
    classify, strip_heredocs, profile, main,
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

    # REMOVED 2026-09-12, both deliberately, and worth saying why rather than
    # leaving a gap someone helpfully refills:
    #
    #   test_a_session_below_one_engine_copy_is_inadmissible built two literals
    #   ({"ingested": 6088, "floor": 50723}) and asserted 6088 < 50723. It called
    #   no production code and would have passed against an empty module.
    #
    #   test_default_floor_is_about_one_engine_copy asserted 45000 < DEFAULT_FLOOR
    #   < 60000 -- i.e. it actively CERTIFIED the 0.2.0 constant whose use in
    #   main() was the fail-open. A test can hold a defect in place.
    #
    # What replaces them is CliFloorTests below, which runs main() end to end.

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
        would rebuild the fail-open this function replaced.

        Asserted as a RELATION, not against `max(KNOWN_ENGINE_BYTES)`: the
        resolver also scans the live plugin cache, so an equality would fail on
        the first machine to install a wider engine -- the single event this
        module exists to survive.
        """
        for v in KNOWN_ENGINE_BYTES:
            self.assertGreaterEqual(floor_for(None), floor_for(v))
        self.assertGreater(floor_for(None), 0)

    def test_an_evicted_version_falls_back_to_the_table_not_to_zero(self):
        """A version no longer in the plugin cache must not size the floor at 0."""
        self.assertEqual(engine_bytes("0.2.0"), KNOWN_ENGINE_BYTES["0.2.0"])

    def test_an_entirely_unknown_version_still_yields_a_usable_floor(self):
        self.assertIsNone(engine_bytes("9.9.9"))
        self.assertGreater(floor_for("9.9.9"), 0)


class CliFloorTests(unittest.TestCase):
    """`main()` must apply the PER-SESSION floor, not a constant.

    REGRESSION, 2026-09-12, and the reason this class exists at all. The floor
    was made version-aware in `floor_for`, a mutation battery killed 3/3 against
    it -- and `main()` still opened with `floor = DEFAULT_FLOOR` and passed it
    straight into `profile`. The fix lived in the library and not in the product,
    and every mutation aimed one layer below the defect.

    It also survived a manual smoke test, because that session was 0.2.1, where
    the stale constant and the derived floor are the SAME NUMBER. So these cases
    use a 0.3.0 fixture on purpose: the eras must disagree for the test to bite.
    """

    ENG = ("/home/u/.claude/plugins/cache/claude-code-loop/dev-loop/"
           "%s/skills/dev-loop/loop-engine.md")

    def _session(self, version, ingest_tokens):
        """A transcript whose single engine read of `version` ingests exactly
        `ingest_tokens`.

        `profile` derives ingestion from the CONTEXT DELTA between turns, not
        from payload size, so the fixture sets the delta directly: turn 1's
        input is turn 0's input + turn 0's output + the tokens to ingest. That
        makes the quantity under test the one the assertion names.
        """
        base_in, base_out = 10, 5
        return [
            {"type": "assistant", "message": {
                "id": "m0",
                "usage": {"input_tokens": base_in, "cache_read_input_tokens": 0,
                          "cache_creation_input_tokens": 0,
                          "output_tokens": base_out},
                "content": [{"type": "tool_use", "id": "t0", "name": "Read",
                             "input": {"file_path": self.ENG % version}}]}},
            {"type": "user", "message": {"content": [
                {"type": "tool_result", "tool_use_id": "t0",
                 "content": "engine text"}]}},
            {"type": "assistant", "message": {
                "id": "m1",
                "usage": {"input_tokens": base_in + base_out + ingest_tokens,
                          "cache_read_input_tokens": 0,
                          "cache_creation_input_tokens": 0,
                          "output_tokens": base_out},
                "content": [{"type": "text", "text": "done"}]}},
        ]

    def _run(self, recs):
        import json as _json
        import tempfile
        import io
        import contextlib
        fh = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False)
        for r in recs:
            fh.write(_json.dumps(r) + "\n")
        fh.close()
        try:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                main(["engine_cost.py", fh.name])
            return buf.getvalue()
        finally:
            os.unlink(fh.name)

    def test_cli_detects_and_prints_the_era(self):
        out = self._run(self._session("0.3.0", 100000))
        self.assertIn("0.3.0", out)

    def test_cli_refuses_a_partial_load_of_the_wider_engine(self):
        """THE REGRESSION. Enough ingestion for a 0.2.0 copy, short of a 0.3.0
        one. Against the stale constant this printed no INADMISSIBLE line."""
        between = int(floor_for("0.2.0") * 1.02)   # clears 0.2.0, short of 0.3.0
        self.assertGreater(between, floor_for("0.2.0"))
        self.assertLess(between, floor_for("0.3.0"))
        out = self._run(self._session("0.3.0", between))
        self.assertIn("INADMISSIBLE", out)

    def test_cli_admits_the_same_volume_when_the_era_is_narrower(self):
        """Same bytes, older engine -> admissible. Proves the refusal above is
        the ERA doing the work, not the payload being small."""
        between = int(floor_for("0.2.0") * 1.02)
        out = self._run(self._session("0.2.0", between))
        self.assertNotIn("INADMISSIBLE", out)

    def test_an_explicit_floor_flag_still_overrides(self):
        between = int(floor_for("0.2.0") * 1.02)
        import json as _json
        import tempfile
        import io
        import contextlib
        fh = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False)
        for r in self._session("0.3.0", between):
            fh.write(_json.dumps(r) + "\n")
        fh.close()
        try:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                main(["engine_cost.py", "--floor", "1", fh.name])
            self.assertNotIn("INADMISSIBLE", buf.getvalue())
        finally:
            os.unlink(fh.name)


if __name__ == "__main__":
    unittest.main(verbosity=2)
