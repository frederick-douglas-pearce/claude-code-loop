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
    engine_file, file_bytes, load_level, median_interval,
    LOAD_TOKENS, LOAD_TOLERANCE, CORE, ENTRY,
)

CACHE = "/home/u/.claude/plugins/cache/claude-code-loop/dev-loop/0.2.0/skills/dev-loop/loop-engine.md"
TREE = "/home/u/Documents/Projects/git/claude-code-loop/skills/dev-loop/loop-engine.md"
# Since #170 the working tree itself lives under `plugins/dev-loop/`.
TREE_PAYLOAD = ("/home/u/Documents/Projects/git/claude-code-loop/"
                "plugins/dev-loop/skills/dev-loop/loop-engine.md")
# Copies under `~/.claude/` that are still not the engine that runs.
MARKETPLACE = ("/home/u/.claude/plugins/marketplaces/claude-code-loop/"
               "plugins/dev-loop/skills/dev-loop/loop-engine.md")
WORKTREE = ("/home/u/Documents/Projects/git/claude-code-loop/.claude/worktrees/w1/"
            "plugins/dev-loop/skills/dev-loop/loop-engine.md")
# A checkout whose path merely contains "cache" is not the plugin cache either.
CACHE_DIR_CLONE = ("/home/u/.cache/src/claude-code-loop/"
                   "plugins/dev-loop/skills/dev-loop/loop-engine.md")
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

    def test_payload_working_tree_read_is_tree_not_load(self):
        """BUG 2, recurrence (#126). #170 moved the working tree under `plugins/dev-loop/`, so a
        bare `/plugins/` test scored in-repo edits as loads: one 0.3.0 session read
        as 127,654 ingested against 101,828 actually loaded. Only the plugin cache
        is a load."""
        self.assertEqual(classify("Read", {"file_path": TREE_PAYLOAD}), "tree")
        self.assertEqual(bash("sed -n '1,200p' " + TREE_PAYLOAD), "tree")

    def test_non_cache_copies_under_dot_claude_are_not_loads(self):
        """Only the plugin cache runs. The marketplace clone and a worktree both sit
        under `/.claude/`, so a discriminator widened to `/.claude/` would score
        both as loads, and one widened to `/.claude/plugins/` would score the
        marketplace clone; a bare `cache` test would score any checkout under
        `~/.cache/`."""
        for path in (MARKETPLACE, WORKTREE, CACHE_DIR_CLONE):
            self.assertEqual(classify("Read", {"file_path": path}), "tree")
            self.assertEqual(bash("sed -n '1,200p' " + path), "tree")

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

    def test_floor_is_the_measured_load_not_bytes_over_a_constant(self):
        """F191. The floor was `bytes / 3.5`, which admitted ~75% of a 0.3.0 load.
        Mechanism: every measured row IS the floor (less the tolerance), and the
        row is in context tokens, so no chars-per-token constant enters it."""
        for (v, f), tok in LOAD_TOKENS.items():
            self.assertAlmostEqual(floor_for(v, f), tok * LOAD_TOLERANCE)
        self.assertGreater(floor_for("0.3.0"), engine_bytes("0.3.0") / 3.5)

    def test_a_partial_load_of_the_wider_engine_is_inadmissible(self):
        """The exact false-admit: enough for a 0.2.0 copy, short of a 0.3.0 one."""
        partial = load_level("0.2.0")                # a whole 0.2.0 engine
        self.assertGreaterEqual(partial, floor_for("0.2.0"))   # fine as 0.2.0
        self.assertLess(partial, floor_for("0.3.0"))           # short as 0.3.0

    def test_unknown_era_has_no_floor_and_its_session_refuses(self):
        """Default-deny, round-1 ruling on #133 PR B. An unknown era was sized off
        the widest engine known; with no rate to size from, it now has no level,
        and a session that cannot be sized is not measured."""
        self.assertIsNone(floor_for(None))
        recs = transcript([("/home/u/.claude/plugins/cache/claude-code-loop/"
                            "dev-loop/skills/dev-loop/loop-engine.md", 10 ** 6)])
        p = run_profile(recs)
        self.assertIsNone(p["era"])
        self.assertFalse(p["admissible"])
        self.assertEqual(p["incomplete"], [CORE])

    def test_an_evicted_version_falls_back_to_the_table_not_to_zero(self):
        """A version no longer in the plugin cache must not size the floor at 0."""
        self.assertEqual(engine_bytes("0.2.0"), KNOWN_ENGINE_BYTES["0.2.0"])

    def test_an_entirely_unknown_version_has_no_floor(self):
        self.assertIsNone(engine_bytes("9.9.9"))
        self.assertIsNone(floor_for("9.9.9"))


ENG31 = "/home/u/.claude/plugins/cache/claude-code-loop/dev-loop/0.3.1/skills/dev-loop/%s"
TREE31 = "/home/u/Documents/Projects/git/claude-code-loop/plugins/dev-loop/skills/dev-loop/%s"


def transcript(steps):
    """Records for a session whose parent takes one turn per step, plus a final one.

    A step is `(path, tokens)` -- a Read of `path` whose result raises the next
    turn's input by exactly `tokens` -- `("Bash", command, tokens)`, `("Grep",
    path, tokens)`, or "idle". A read at step k ARRIVES at turn
    k + 1, so its arrival fraction is (k + 1) / (len(steps) + 1). Ingestion is set
    through the context delta because that is what `profile` measures."""
    recs, ctx, out = [], 10, 5
    for k, step in enumerate(list(steps) + ["idle"]):
        use = None if step == "idle" else step
        if use and use[0] in ("Bash", "Grep"):
            tool, inp = use[0], ({"command": use[1]} if use[0] == "Bash"
                                 else {"pattern": "step", "path": use[1]})
            use = (None, use[2])
        elif use:
            tool, inp = "Read", {"file_path": use[0]}
        content = ([{"type": "tool_use", "id": "t%d" % k, "name": tool,
                     "input": inp}] if use
                   else [{"type": "text", "text": "."}])
        recs.append({"type": "assistant", "message": {"id": "m%d" % k, "usage": {
            "input_tokens": ctx, "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0, "output_tokens": out},
            "content": content}})
        if use:
            recs.append({"type": "user", "message": {"content": [
                {"type": "tool_result", "tool_use_id": "t%d" % k,
                 "content": "engine text"}]}})
        ctx += out + (use[1] if use else 0)
    return recs


def run_profile(recs, **kw):
    import json as _json
    import tempfile
    fh = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False)
    for r in recs:
        fh.write(_json.dumps(r) + "\n")
    fh.close()
    try:
        return profile(fh.name, **kw)
    finally:
        os.unlink(fh.name)


def full(version, f):
    return load_level(version, f)


class UnitDetectionTests(unittest.TestCase):
    """#133/AC4: P2 is core plus units, so a unit read must count as engine text."""

    def test_a_unit_in_the_cache_is_a_load_and_names_its_file(self):
        for f in ("phases/reviewing.md", "phases/accepting.md",
                  "reference/initialization.md"):
            self.assertEqual(classify("Read", {"file_path": ENG31 % f}), "load")
            self.assertEqual(engine_file("Read", {"file_path": ENG31 % f}), f)

    def test_a_unit_no_release_has_shipped_yet_is_still_counted(self):
        """The set is a path pattern, never a list of names: a list would miss the
        next unit and understate P2 in exactly the release that added it."""
        f = "phases/zz-never-shipped-133.md"
        self.assertEqual(classify("Read", {"file_path": ENG31 % f}), "load")
        self.assertEqual(engine_file("Read", {"file_path": ENG31 % f}), f)

    def test_a_tool_read_of_skill_md_counts(self):
        self.assertEqual(classify("Read", {"file_path": ENG31 % ENTRY}), "load")

    def test_a_working_tree_unit_is_tree_not_load(self):
        self.assertEqual(classify("Read", {"file_path": TREE31 % "phases/reviewing.md"}),
                         "tree")

    def test_a_unit_named_relative_to_a_cd_into_the_skill_dir_is_found(self):
        """#130's sessions read units this way; the full-path pattern alone
        missed them."""
        d = (ENG31 % "x").rsplit("/", 1)[0]
        cmd = "cd %s; head -16 phases/accepting.md; tail -4 phases/accepting.md" % d
        self.assertEqual(classify("Bash", {"command": cmd}), "load")
        self.assertEqual(engine_file("Bash", {"command": cmd}), "phases/accepting.md")
        self.assertEqual(engine_version("Bash", {"command": cmd}), "0.3.1")

    def test_a_file_named_through_a_directory_variable_is_found(self):
        d = (TREE31 % "x").rsplit("/", 1)[0]
        cmd = "D=%s; sed -n 1739,1741p $D/loop-engine.md" % d
        self.assertEqual(classify("Bash", {"command": cmd}), "tree")
        self.assertEqual(engine_file("Bash", {"command": cmd}), CORE)

    def test_a_relative_md_that_is_not_in_the_payload_is_not_engine(self):
        d = (TREE31 % "x").rsplit("/", 1)[0]
        cmd = "cd %s; sed -n 1,20p README.md" % d
        self.assertIsNone(engine_file("Bash", {"command": cmd}))
        self.assertIsNone(classify("Bash", {"command": cmd}))

    def test_an_engine_name_without_the_skill_dir_is_not_a_read_of_it(self):
        """The old substring test scored this as a tree read of the engine."""
        cmd = "grep -v '^loop-engine.md' /tmp/s/ac5-groups.txt"
        self.assertIsNone(classify("Bash", {"command": cmd}))

    def test_a_command_naming_two_files_is_one_unattributable_key(self):
        cmd = "cat %s %s" % (ENG31 % "phases/reviewing.md", ENG31 % "phases/accepting.md")
        self.assertEqual(engine_file("Bash", {"command": cmd}),
                         "phases/accepting.md+phases/reviewing.md")

    def test_a_spill_recovery_read_inherits_the_unit(self):
        """BUG 3 again, per file: the spill path names no engine file."""
        sp = "/home/u/.claude/projects/-s/abc/tool-results/x.txt"
        recs = transcript([(ENG31 % CORE, full("0.3.1", CORE))])
        recs += [
            {"type": "assistant", "message": {"id": "u0", "usage": {
                "input_tokens": 10 ** 6, "output_tokens": 5}, "content": [
                {"type": "tool_use", "id": "s0", "name": "Bash",
                 "input": {"command": "cat " + ENG31 % "phases/reviewing.md"}}]}},
            {"type": "user", "toolUseResult": {"persistedOutputPath": sp},
             "message": {"content": [{"type": "tool_result", "tool_use_id": "s0",
                                      "content": "preview"}]}},
            {"type": "assistant", "message": {"id": "u1", "usage": {
                "input_tokens": 10 ** 6 + 10, "output_tokens": 5}, "content": [
                {"type": "tool_use", "id": "s1", "name": "Bash",
                 "input": {"command": "sed -n '1,400p' " + sp}}]}},
            {"type": "user", "message": {"content": [
                {"type": "tool_result", "tool_use_id": "s1", "content": "body"}]}},
            {"type": "assistant", "message": {"id": "u2", "usage": {
                "input_tokens": 10 ** 6 + 20 + 500, "output_tokens": 5},
                "content": [{"type": "text", "text": "."}]}},
        ]
        p = run_profile(recs)
        self.assertEqual(p["files"]["phases/reviewing.md"]["reads"], 2)


class PerFileAdmissibilityTests(unittest.TestCase):
    """The core always, and each unit the session read, must clear one complete
    load of that file (#133/AC4, F191). A partial unit load understates P2c in
    exactly the direction the sharding release predicts, so it must refuse."""

    def test_complete_core_and_no_unit_is_admissible(self):
        p = run_profile(transcript([(ENG31 % CORE, full("0.3.1", CORE))]))
        self.assertTrue(p["admissible"])
        self.assertEqual(p["era"], "0.3.1")

    def test_a_partial_unit_refuses_and_is_named(self):
        f = "phases/reviewing.md"
        p = run_profile(transcript([(ENG31 % CORE, full("0.3.1", CORE)),
                                    (ENG31 % f, int(full("0.3.1", f) * 0.7))]))
        self.assertFalse(p["admissible"])
        self.assertEqual(p["incomplete"], [f])

    def test_complete_core_and_unit_is_admissible_and_both_are_in_p2(self):
        f = "phases/accepting.md"
        core, unit = full("0.3.1", CORE), full("0.3.1", f)
        p = run_profile(transcript([(ENG31 % CORE, core), (ENG31 % f, unit)]))
        self.assertTrue(p["admissible"])
        self.assertAlmostEqual(p["ingested"], core + unit)

    def test_f191_a_three_quarter_core_load_refuses(self):
        """F191's case: ~75% of a load cleared `bytes / 3.5`. It must not now."""
        old_floor = engine_bytes("0.3.1") / 3.5
        p = run_profile(transcript([(ENG31 % CORE, int(old_floor * 1.01))]))
        self.assertFalse(p["admissible"])
        self.assertEqual(p["incomplete"], [CORE])

    def test_a_session_that_never_read_the_core_refuses(self):
        f = "phases/reviewing.md"
        p = run_profile(transcript([(ENG31 % f, full("0.3.1", f))]))
        self.assertFalse(p["admissible"])
        self.assertIn(CORE, p["incomplete"])

    def test_a_unit_nothing_can_size_refuses(self):
        """Default-deny: no measured row and no bytes means not complete."""
        f = "phases/zz-never-shipped-133.md"
        self.assertIsNone(file_bytes("0.3.1", f))
        p = run_profile(transcript([(ENG31 % CORE, full("0.3.1", CORE)),
                                    (ENG31 % f, 10 ** 6)]))
        self.assertFalse(p["admissible"])
        self.assertEqual(p["incomplete"], [f])

    def test_skill_md_counts_in_p2_but_is_never_required(self):
        p = run_profile(transcript([(ENG31 % CORE, full("0.3.1", CORE)),
                                    (ENG31 % ENTRY, 50)]))
        self.assertTrue(p["admissible"])
        self.assertAlmostEqual(p["ingested"], full("0.3.1", CORE) + 50)

    def test_the_floor_flag_overrides_the_core_only(self):
        f = "phases/reviewing.md"
        p = run_profile(transcript([(ENG31 % CORE, 100),
                                    (ENG31 % f, int(full("0.3.1", f) * 0.5))]), floor=1)
        self.assertNotIn(CORE, p["incomplete"])
        self.assertEqual(p["incomplete"], [f])

    def test_an_unmeasured_required_file_refuses(self):
        """Round-1 ruling: no rate sizing. 0.3.0's SKILL.md has bytes and no row,
        and a unit with bytes and no row must refuse rather than be estimated --
        the densest rate measured is not a bound on the next file's."""
        f = "phases/zz-never-shipped-133.md"
        self.assertIsNone(load_level("0.3.1", f))
        p = run_profile(transcript([(ENG31 % CORE, full("0.3.1", CORE)),
                                    (ENG31 % f, 10 ** 6)]))
        self.assertFalse(p["admissible"])
        self.assertIn(f, p["incomplete"])

    def test_a_partial_core_is_not_rescued_by_a_complete_unit(self):
        """ge.1. The pre-#133 check compared the AGGREGATE against the core floor.
        80% of the core plus a whole accepting unit clears that aggregate, so only
        a per-file core check refuses this session."""
        core, unit = full("0.3.1", CORE), full("0.3.1", "phases/accepting.md")
        partial = int(core * 0.8)
        self.assertGreater(partial + unit, floor_for("0.3.1"))    # the trap is live
        p = run_profile(transcript([(ENG31 % CORE, partial),
                                    (ENG31 % "phases/accepting.md", unit)]))
        self.assertFalse(p["admissible"])
        self.assertEqual(p["incomplete"], [CORE])

    def test_a_top_level_unit_is_required_too(self):
        """mc.3. Required was decided by a `/` in the path; a unit a release adds
        beside the core must still be checked, and with no row it refuses."""
        f = "zz-top-level-unit-133.md"
        p = run_profile(transcript([(ENG31 % CORE, full("0.3.1", CORE)),
                                    (ENG31 % f, 10 ** 6)]))
        self.assertIn(f, p["files"])
        self.assertFalse(p["admissible"])


class AttributionRefusalTests(unittest.TestCase):
    """Round-1 ruling on #133 PR B: a read that cannot be attributed to one file
    refuses or requires, never vanishes (mc.1, mc.2, ge.3, ge.4)."""

    DIR = (ENG31 % "x").rsplit("/", 1)[0]

    def test_a_multi_file_read_requires_each_member_and_credits_none(self):
        a, b = "phases/accepting.md", "phases/reviewing.md"
        both = full("0.3.1", a) + full("0.3.1", b)
        cmd = "cat %s %s" % (ENG31 % a, ENG31 % b)
        p = run_profile(transcript([(ENG31 % CORE, full("0.3.1", CORE)),
                                    ("Bash", cmd, both)]))
        self.assertFalse(p["admissible"])
        self.assertEqual(sorted(p["incomplete"]), [a, b])
        self.assertAlmostEqual(p["ingested"], full("0.3.1", CORE) + both)

    def test_a_multi_file_grep_after_full_single_reads_admits(self):
        a, b = "phases/accepting.md", "phases/reviewing.md"
        cmd = "grep -n step %s %s" % (ENG31 % a, ENG31 % b)
        p = run_profile(transcript([(ENG31 % CORE, full("0.3.1", CORE)),
                                    (ENG31 % a, full("0.3.1", a)),
                                    (ENG31 % b, full("0.3.1", b)),
                                    ("Bash", cmd, 200)]))
        self.assertTrue(p["admissible"])

    def test_a_glob_over_the_units_refuses(self):
        cmd = "head -40 %s/phases/*.md" % self.DIR
        p = run_profile(transcript([(ENG31 % CORE, full("0.3.1", CORE)),
                                    ("Bash", cmd, 3000)]))
        self.assertFalse(p["admissible"])
        self.assertTrue(p["unattributed"])

    def test_an_unresolvable_relative_read_refuses(self):
        cmd = "cd %s && cat ./phases/accepting.md" % self.DIR
        p = run_profile(transcript([(ENG31 % CORE, full("0.3.1", CORE)),
                                    ("Bash", cmd, 3000)]))
        self.assertFalse(p["admissible"])
        self.assertEqual(len(p["unattributed"]), 1)

    def test_the_grep_tool_on_the_skill_directory_refuses(self):
        p = run_profile(transcript([(ENG31 % CORE, full("0.3.1", CORE)),
                                    ("Grep", self.DIR, 500)]))
        self.assertFalse(p["admissible"])
        self.assertTrue(p["unattributed"])

    def test_a_working_tree_read_of_the_directory_is_not_unattributable(self):
        """Only the CACHED directory is the engine that runs; tree reads stay out."""
        tree_dir = (TREE31 % "x").rsplit("/", 1)[0]
        p = run_profile(transcript([(ENG31 % CORE, full("0.3.1", CORE)),
                                    ("Bash", "grep -rn step %s" % tree_dir, 500)]))
        self.assertTrue(p["admissible"])


class TolerancePinTests(unittest.TestCase):
    """ge.2. F191's second door: `LOAD_TOLERANCE` lowered toward 0.75 re-admits a
    three-quarter load with the 3.5 constant gone. Pin the band through the
    product path: for every measured row, 95% of a load refuses and a whole one
    admits -- so 0.95 < tolerance <= 1.0."""

    ENG = "/home/u/.claude/plugins/cache/claude-code-loop/dev-loop/%s/skills/dev-loop/%s"

    def _session(self, v, f, frac):
        steps = [] if f == CORE else [(self.ENG % (v, CORE), full(v, CORE))]
        if f == CORE:
            steps = [(self.ENG % (v, CORE), int(full(v, CORE) * frac))]
        else:
            steps.append((self.ENG % (v, f), int(full(v, f) * frac)))
        return run_profile(transcript(steps))

    def test_95_percent_of_any_measured_load_refuses(self):
        for v, f in LOAD_TOKENS:
            with self.subTest(v=v, f=f):
                p = self._session(v, f, 0.95)
                self.assertFalse(p["admissible"])
                self.assertEqual(p["incomplete"], [f])

    def test_a_whole_measured_load_admits(self):
        for v, f in LOAD_TOKENS:
            with self.subTest(v=v, f=f):
                self.assertTrue(self._session(v, f, 1.0)["admissible"])


class TableTests(unittest.TestCase):
    """ge.9 and the pooling rule: `--table` is the one place this script pools, so
    the product path is what these run, not the library underneath it."""

    def _write(self, d, name, recs):
        import json as _json
        path = os.path.join(d, name)
        with open(path, "w") as fh:
            for r in recs:
                fh.write(_json.dumps(r) + "\n")
        return path

    def _table(self, paths):
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            main(["engine_cost.py", "--table"] + paths)
        return buf.getvalue()

    def setUp(self):
        import tempfile
        self.root = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.root)

    def test_the_median_pools_only_admissible_sessions_and_names_its_statistics(self):
        d = os.path.join(self.root, "repo")
        os.makedirs(d)
        good = self._write(d, "good.jsonl", transcript([(ENG31 % CORE, full("0.3.1", CORE))]))
        short = self._write(d, "short.jsonl",
                            transcript([(ENG31 % CORE, int(full("0.3.1", CORE) * 0.5))]))
        out = self._table([good, short])
        self.assertIn("P2c over 1 admissible", out)
        self.assertIn("order statistics 1 and 1", out)

    def test_sessions_from_two_projects_are_not_pooled(self):
        paths = []
        for repo in ("repo-a", "repo-b"):
            d = os.path.join(self.root, repo)
            os.makedirs(d)
            paths.append(self._write(d, "s.jsonl",
                                     transcript([(ENG31 % CORE, full("0.3.1", CORE))])))
        out = self._table(paths)
        self.assertIn("NOT POOLED", out)
        self.assertNotIn("median", out.split("NOT POOLED")[1])


class CentroidTests(unittest.TestCase):
    """Arrival centroid: where in the session (0 = first turn, 1 = past the last)
    a file's text arrived, weighted by tokens. #133 measures what the baseline's
    predictions assumed (reviewing at 55%, accepting at 75%)."""

    def test_a_unit_read_once_arrives_at_its_turn_fraction(self):
        f = "phases/reviewing.md"
        steps = [(ENG31 % CORE, full("0.3.1", CORE))] + ["idle"] * 4 + \
                [(ENG31 % f, full("0.3.1", f))] + ["idle"] * 3
        p = run_profile(transcript(steps))
        n = len(steps) + 1
        self.assertAlmostEqual(p["files"][f]["centroid"], 6 / n)
        self.assertAlmostEqual(p["files"][CORE]["centroid"], 1 / n)

    def test_two_equal_reads_average_their_arrivals(self):
        f = "phases/reviewing.md"
        whole = full("0.3.1", f)
        steps = [(ENG31 % CORE, full("0.3.1", CORE)), (ENG31 % f, whole),
                 "idle", (ENG31 % f, whole)]
        p = run_profile(transcript(steps))
        self.assertAlmostEqual(p["files"][f]["centroid"], ((2 + 4) / 2) / 5)
        self.assertEqual(p["files"][f]["reads"], 2)


class MedianIntervalTests(unittest.TestCase):
    """Order-statistic interval for a median. The baseline quotes n=8 as order
    statistics 2 and 7 at ~93%; the helper must reproduce that."""

    def test_n8_is_order_statistics_2_and_7(self):
        """ge.8: values that differ from their ranks, so returning positions or the
        rank median cannot pass."""
        iv = median_interval([80, 10, 70, 20, 60, 30, 50, 40])
        self.assertEqual(iv["order"], (2, 7))
        self.assertEqual((iv["lo"], iv["hi"]), (20, 70))
        self.assertAlmostEqual(iv["coverage"], 1 - 2 * 9 / 256)
        self.assertEqual(iv["median"], 45)

    def test_n5_needs_the_full_range(self):
        iv = median_interval([5, 4, 3, 2, 1])
        self.assertEqual(iv["order"], (1, 5))
        self.assertTrue(iv["met"])

    def test_n4_cannot_reach_90_and_says_so(self):
        iv = median_interval([1, 2, 3, 4])
        self.assertEqual(iv["order"], (1, 4))
        self.assertFalse(iv["met"])
        self.assertAlmostEqual(iv["coverage"], 0.875)

    def test_empty_is_none(self):
        self.assertIsNone(median_interval([]))


class SubagentCountTests(unittest.TestCase):
    def test_p6_counts_transcripts_beside_the_session(self):
        import tempfile
        d = tempfile.mkdtemp()
        path = os.path.join(d, "s1.jsonl")
        recs = transcript([(ENG31 % CORE, full("0.3.1", CORE))])
        with open(path, "w") as fh:
            import json as _json
            for r in recs:
                fh.write(_json.dumps(r) + "\n")
        os.makedirs(os.path.join(d, "s1", "subagents"))
        for name in ("a.jsonl", "b.jsonl", "a.meta.json"):
            open(os.path.join(d, "s1", "subagents", name), "w").close()
        try:
            self.assertEqual(profile(path)["subagents"], 2)
        finally:
            import shutil
            shutil.rmtree(d)


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
