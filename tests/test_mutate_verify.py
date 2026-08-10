"""Behavior of the mutation harness (`tools/mutate_verify.py`).

This module is the point of #60. The prose version of this apparatus could not converge because
every review round re-derived its correctness by reading — there was nothing to execute. These
tests are what make a green suite say something about the harness, so keep them behavioral: assert
what the harness *does* to a tree and what it *refuses* to do, not how it is written.

Stdlib `unittest` only, per `CLAUDE.md` — the harness runs under bare `python3` in a consumer's
environment, so its tests must too.

The scratch project each test builds is deliberately tiny: one source file holding a marker, plus a
"test suite" that is a one-line `python3 -c` command. That gives exact control over which mutations
the suite observes, which is the only thing these tests need to vary.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import mutate_verify  # noqa: E402  (path juggling above is deliberate)
from mutate_verify import (  # noqa: E402
    EXIT_CLEAN,
    EXIT_HARNESS_ERROR,
    EXIT_RESTORE_FAILED,
    EXIT_SURVIVORS,
    EXIT_UNPROVEN,
    Mutation,
    MutationError,
    RestoreError,
    SpecError,
    apply_mutation,
    dedupe_survivors,
    load_spec,
    mutate_text,
    resolve_target,
    restore_file,
    run_pass,
)

# A suite that OBSERVES the marker: mutating GOOD away turns it red.
_OBSERVING_SUITE = (
    "{exe} -c \"import sys; sys.exit(0 if 'GOOD' in open('src.py').read() else 1)\""
)
# A suite that observes nothing: always green, so every mutation survives it.
_BLIND_SUITE = '{exe} -c "import sys; sys.exit(0)"'
# A suite that is red before anything is mutated.
_RED_SUITE = '{exe} -c "import sys; sys.exit(1)"'

_SOURCE = "# marker: GOOD\nvalue = 1\n# spare: SPARE_A\n# spare: SPARE_B\n"


class _Scratch:
    """A throwaway project directory: `src.py` plus a chosen test command."""

    def __init__(self, case: unittest.TestCase, suite: str = _OBSERVING_SUITE) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="mutate-verify-test-"))
        case.addCleanup(self._cleanup)
        self.source = self.root / "src.py"
        self.source.write_text(_SOURCE, encoding="utf-8")
        self.test_cmd = suite.format(exe=sys.executable)

    def _cleanup(self) -> None:
        import shutil

        shutil.rmtree(str(self.root), ignore_errors=True)


def _mutation(**kwargs: object) -> Mutation:
    base = {
        "id": "m",
        "file": "src.py",
        "find": "GOOD",
        "replace": "BAD",
        "kind": "marker",
        "expect": "killed",
    }
    base.update(kwargs)
    return Mutation(**base)  # type: ignore[arg-type]


def _control(**kwargs: object) -> Mutation:
    """A mutation nothing observes — the proof that the pipeline can report `survived`."""
    base = {
        "id": "control",
        "file": "src.py",
        "find": "SPARE_A",
        "replace": "SPARE_A_MUTATED",
        "kind": "control",
        "expect": "survived",
    }
    base.update(kwargs)
    return Mutation(**base)  # type: ignore[arg-type]


class MutateTextTests(unittest.TestCase):
    """AC5, first half: a pattern that finds nothing is an error, never a silent no-op."""

    def test_literal_that_does_not_match_raises(self) -> None:
        with self.assertRaises(MutationError) as ctx:
            mutate_text(_mutation(find="NOT_PRESENT"), _SOURCE)
        self.assertIn("not found", str(ctx.exception))

    def test_regex_that_does_not_match_raises(self) -> None:
        with self.assertRaises(MutationError) as ctx:
            mutate_text(_mutation(find=r"ZZZ\d+", regex=True), _SOURCE)
        self.assertIn("matched nothing", str(ctx.exception))

    def test_literal_replaces_only_the_first_occurrence_by_default(self) -> None:
        text = "A A A"
        self.assertEqual(mutate_text(_mutation(find="A", replace="B"), text), "B A A")

    def test_all_flag_replaces_every_occurrence(self) -> None:
        text = "A A A"
        self.assertEqual(mutate_text(_mutation(find="A", replace="B", all=True), text), "B B B")

    def test_regex_replacement_is_literal_not_a_backreference(self) -> None:
        # A replacement containing a backslash must land as written; the harness does not offer
        # backreferences, and silently interpreting one would mutate something else entirely.
        out = mutate_text(_mutation(find=r"value = \d", replace=r"value = \1", regex=True), _SOURCE)
        self.assertIn(r"value = \1", out)


class ApplyMutationTests(unittest.TestCase):
    """AC5, second half: 'applied' means the bytes actually changed."""

    def setUp(self) -> None:
        self.scratch = _Scratch(self)

    def test_match_that_changes_no_bytes_is_an_error(self) -> None:
        with self.assertRaises(MutationError) as ctx:
            apply_mutation(_mutation(find="GOOD", replace="GOOD"), self.scratch.source)
        self.assertIn("did not change", str(ctx.exception))

    def test_a_failed_no_op_leaves_the_file_untouched(self) -> None:
        try:
            apply_mutation(_mutation(find="GOOD", replace="GOOD"), self.scratch.source)
        except MutationError:
            pass
        self.assertEqual(self.scratch.source.read_text(encoding="utf-8"), _SOURCE)

    def test_apply_returns_the_original_bytes_and_writes_the_mutant(self) -> None:
        original = apply_mutation(_mutation(), self.scratch.source)
        self.assertEqual(original, _SOURCE.encode("utf-8"))
        self.assertIn("BAD", self.scratch.source.read_text(encoding="utf-8"))

    def test_non_utf8_target_is_an_error_not_a_crash(self) -> None:
        binary = self.scratch.root / "blob.bin"
        binary.write_bytes(b"\xff\xfe\x00GOOD")
        with self.assertRaises(MutationError) as ctx:
            apply_mutation(_mutation(file="blob.bin"), binary)
        self.assertIn("not valid UTF-8", str(ctx.exception))


class RestoreTests(unittest.TestCase):
    """The tree must come back byte-exact, and never via git."""

    def setUp(self) -> None:
        self.scratch = _Scratch(self)

    def test_restore_is_byte_exact(self) -> None:
        snapshot = self.scratch.root / "snap"
        original = self.scratch.source.read_bytes()
        snapshot.write_bytes(original)
        apply_mutation(_mutation(), self.scratch.source)
        restore_file(self.scratch.source, snapshot, mutate_verify._sha256(original))
        self.assertEqual(self.scratch.source.read_bytes(), original)

    def test_a_snapshot_that_does_not_match_its_hash_raises(self) -> None:
        snapshot = self.scratch.root / "snap"
        snapshot.write_bytes(b"not the original content")
        with self.assertRaises(RestoreError) as ctx:
            restore_file(self.scratch.source, snapshot, mutate_verify._sha256(b"something else"))
        self.assertIn("not byte-exact", str(ctx.exception))

    def test_the_only_thing_the_harness_executes_is_the_callers_test_command(self) -> None:
        # Restoring from the index destroys uncommitted work the mutation never touched, so the
        # harness must have no git call path at all. A substring search would be an *outcome*
        # assertion and passes for any implementation that avoids the word — including one that
        # builds "g"+"it". Assert the mechanism instead: there is exactly one subprocess call site,
        # and what it runs is the caller's parameter, never a literal this module chose.
        import ast

        tree = ast.parse(Path(mutate_verify.__file__).read_text(encoding="utf-8"))
        call_sites = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                if func.value.id in ("subprocess", "os"):
                    call_sites.append((func.value.id, func.attr, node))

        self.assertEqual(
            [(mod, attr) for mod, attr, _ in call_sites],
            [("subprocess", "run")],
            "the harness must have exactly one process-spawning call site",
        )
        _, _, call = call_sites[0]
        self.assertTrue(call.args, "the subprocess call must take the command as its first argument")
        self.assertIsInstance(
            call.args[0],
            ast.Name,
            "the command must be a passed-in variable, never a literal the harness chose",
        )
        self.assertEqual(call.args[0].id, "test_cmd")


class ResolveTargetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.scratch = _Scratch(self)

    def test_target_inside_root_resolves(self) -> None:
        self.assertEqual(
            resolve_target(self.scratch.root, "src.py"), self.scratch.source.resolve()
        )

    def test_target_escaping_root_is_refused(self) -> None:
        with self.assertRaises(SpecError) as ctx:
            resolve_target(self.scratch.root, "../escape.py")
        self.assertIn("outside --root", str(ctx.exception))

    def test_absolute_path_outside_root_is_refused(self) -> None:
        with self.assertRaises(SpecError):
            resolve_target(self.scratch.root, "/etc/hosts")

    def test_missing_target_is_refused(self) -> None:
        with self.assertRaises(SpecError) as ctx:
            resolve_target(self.scratch.root, "no_such_file.py")
        self.assertIn("does not exist", str(ctx.exception))


class LoadSpecTests(unittest.TestCase):
    """A silently-dropped mutation is a mutation that cannot fail — so every rejection is loud."""

    def setUp(self) -> None:
        self.scratch = _Scratch(self)

    def _write(self, payload: object) -> Path:
        path = self.scratch.root / "spec.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_valid_spec_loads(self) -> None:
        path = self._write(
            {"mutations": [{"id": "a", "file": "src.py", "find": "GOOD", "replace": "BAD"}]}
        )
        mutations = load_spec(path)
        self.assertEqual(len(mutations), 1)
        self.assertEqual(mutations[0].expect, "killed")
        self.assertFalse(mutations[0].regex)

    def test_empty_mutation_list_is_refused(self) -> None:
        with self.assertRaises(SpecError) as ctx:
            load_spec(self._write({"mutations": []}))
        self.assertIn("no mutations", str(ctx.exception))

    def test_invalid_json_is_refused(self) -> None:
        path = self.scratch.root / "spec.json"
        path.write_text("{not json", encoding="utf-8")
        with self.assertRaises(SpecError):
            load_spec(path)

    def test_missing_required_key_is_refused(self) -> None:
        with self.assertRaises(SpecError) as ctx:
            load_spec(self._write({"mutations": [{"id": "a", "file": "src.py", "find": "G"}]}))
        self.assertIn("replace", str(ctx.exception))

    def test_empty_replace_is_allowed_as_a_deletion(self) -> None:
        path = self._write(
            {"mutations": [{"id": "a", "file": "src.py", "find": "GOOD", "replace": ""}]}
        )
        self.assertEqual(load_spec(path)[0].replace, "")

    def test_duplicate_ids_are_refused(self) -> None:
        with self.assertRaises(SpecError) as ctx:
            load_spec(
                self._write(
                    {
                        "mutations": [
                            {"id": "a", "file": "src.py", "find": "G", "replace": "B"},
                            {"id": "a", "file": "src.py", "find": "O", "replace": "X"},
                        ]
                    }
                )
            )
        self.assertIn("duplicate", str(ctx.exception))

    def test_unknown_expect_value_is_refused(self) -> None:
        with self.assertRaises(SpecError) as ctx:
            load_spec(
                self._write(
                    {
                        "mutations": [
                            {
                                "id": "a",
                                "file": "src.py",
                                "find": "G",
                                "replace": "B",
                                "expect": "maybe",
                            }
                        ]
                    }
                )
            )
        self.assertIn("expect", str(ctx.exception))

    def test_invalid_regex_is_refused_at_load_time(self) -> None:
        with self.assertRaises(SpecError) as ctx:
            load_spec(
                self._write(
                    {
                        "mutations": [
                            {
                                "id": "a",
                                "file": "src.py",
                                "find": "([",
                                "replace": "B",
                                "regex": True,
                            }
                        ]
                    }
                )
            )
        self.assertIn("not a valid regex", str(ctx.exception))


class RunPassTests(unittest.TestCase):
    """End-to-end: the verdicts, the exit codes, and the state of the tree afterwards."""

    def test_a_killed_mutation_plus_a_control_is_clean(self) -> None:
        scratch = _Scratch(self)
        report, code = run_pass([_mutation(), _control()], scratch.test_cmd, scratch.root)
        self.assertEqual(code, EXIT_CLEAN, report.errors)
        self.assertEqual(report.applied, 2)
        self.assertEqual(report.killed, 1)
        self.assertEqual(report.survived, 1)  # the control
        self.assertTrue(report.control_proved)
        self.assertEqual(report.survivor_groups, [])

    def test_the_tree_is_byte_identical_after_a_pass(self) -> None:
        scratch = _Scratch(self)
        run_pass([_mutation(), _control()], scratch.test_cmd, scratch.root)
        self.assertEqual(scratch.source.read_text(encoding="utf-8"), _SOURCE)

    def test_a_survivor_is_reported_and_exits_nonzero(self) -> None:
        scratch = _Scratch(self, suite=_BLIND_SUITE)
        report, code = run_pass([_mutation(), _control()], scratch.test_cmd, scratch.root)
        self.assertEqual(code, EXIT_SURVIVORS)
        self.assertEqual(len(report.survivor_groups), 1)
        self.assertEqual(report.survivor_groups[0]["count"], 1)

    def test_a_clean_result_without_a_control_is_unproven_not_clean(self) -> None:
        # AC6: a green verdict must prove it can go red. Everything killed, but nothing showed the
        # pipeline is *able* to report a survivor — so this must not read as clean.
        scratch = _Scratch(self)
        report, code = run_pass([_mutation()], scratch.test_cmd, scratch.root)
        self.assertEqual(code, EXIT_UNPROVEN)
        self.assertEqual(report.killed, 1)
        self.assertFalse(report.control_proved)
        self.assertTrue(any("prove it can go red" in e for e in report.errors))

    def test_a_killed_control_invalidates_the_pass(self) -> None:
        # The control was expected to survive and did not, so the classification cannot be trusted.
        scratch = _Scratch(self)
        killed_control = _control(find="GOOD", replace="BAD", id="bad-control")
        report, code = run_pass([killed_control], scratch.test_cmd, scratch.root)
        self.assertEqual(code, EXIT_HARNESS_ERROR)
        self.assertFalse(report.control_proved)

    def test_a_red_baseline_takes_no_verdicts_at_all(self) -> None:
        scratch = _Scratch(self, suite=_RED_SUITE)
        report, code = run_pass([_mutation(), _control()], scratch.test_cmd, scratch.root)
        self.assertEqual(code, EXIT_HARNESS_ERROR)
        self.assertEqual(report.applied, 0)
        self.assertEqual(report.results, [])
        self.assertTrue(any("baseline is not green" in e for e in report.errors))

    def test_a_pattern_that_does_not_match_aborts_the_pass(self) -> None:
        scratch = _Scratch(self)
        report, code = run_pass(
            [_mutation(find="NOT_PRESENT"), _control()], scratch.test_cmd, scratch.root
        )
        self.assertEqual(code, EXIT_HARNESS_ERROR)
        self.assertEqual(report.applied, 0)
        self.assertEqual(scratch.source.read_text(encoding="utf-8"), _SOURCE)

    def test_applied_counts_real_byte_changes_not_invocations(self) -> None:
        # The no-op mutation raises, so it must not be counted — 'applied' is a count of files that
        # actually changed, which is the difference between a real pass and a vacuous one.
        scratch = _Scratch(self)
        report, _ = run_pass(
            [_mutation(find="GOOD", replace="GOOD")], scratch.test_cmd, scratch.root
        )
        self.assertEqual(report.applied, 0)

    def test_snapshots_are_discarded_when_the_tree_is_known_good(self) -> None:
        scratch = _Scratch(self)
        report, code = run_pass([_mutation(), _control()], scratch.test_cmd, scratch.root)
        self.assertEqual(code, EXIT_CLEAN)
        self.assertIsNone(report.snapshot_dir)

    def test_a_timeout_is_not_recorded_as_a_kill(self) -> None:
        scratch = _Scratch(self)
        slow = '{exe} -c "import time; time.sleep(30)"'.format(exe=sys.executable)
        report, code = run_pass([_mutation()], slow, scratch.root, timeout=1)
        self.assertEqual(code, EXIT_HARNESS_ERROR)
        self.assertEqual(report.killed, 0)
        self.assertTrue(any("timed out" in e for e in report.errors))

    def test_a_bad_target_is_caught_before_anything_is_mutated(self) -> None:
        scratch = _Scratch(self)
        with self.assertRaises(SpecError):
            run_pass(
                [_mutation(), _mutation(id="m2", file="../escape.py")],
                scratch.test_cmd,
                scratch.root,
            )
        self.assertEqual(scratch.source.read_text(encoding="utf-8"), _SOURCE)

    def test_a_failed_restore_retains_the_snapshots_and_says_so(self) -> None:
        # The one case where a retained snapshot directory is the correct outcome: the tree may
        # still hold a live mutation, and the snapshot is the only safe repair.
        scratch = _Scratch(self)
        original_restore = mutate_verify.restore_file

        def exploding_restore(*args: object, **kwargs: object) -> None:
            raise RestoreError("simulated restore failure")

        mutate_verify.restore_file = exploding_restore  # type: ignore[assignment]
        self.addCleanup(lambda: setattr(mutate_verify, "restore_file", original_restore))

        report, code = run_pass([_mutation()], scratch.test_cmd, scratch.root)
        self.assertEqual(code, EXIT_RESTORE_FAILED)
        self.assertIsNotNone(report.snapshot_dir)
        self.assertTrue(Path(report.snapshot_dir).is_dir())
        import shutil

        shutil.rmtree(report.snapshot_dir, ignore_errors=True)


class DedupeTests(unittest.TestCase):
    """AC7: a repeated survivor is one signal about a shape, not N findings."""

    def _survivor(self, mutation: Mutation) -> mutate_verify.Result:
        return mutate_verify.Result(
            mutation=mutation, outcome="survived", applied=True, test_exit=0
        )

    def test_identical_shapes_collapse_into_one_group_with_a_count(self) -> None:
        groups = dedupe_survivors(
            [
                self._survivor(_mutation(id="a", find="return  True", kind="fail-open")),
                self._survivor(_mutation(id="b", find="return True", kind="fail-open")),
            ]
        )
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["count"], 2)
        self.assertTrue(groups[0]["repeated"])
        self.assertEqual(len(groups[0]["locations"]), 2)

    def test_different_kinds_stay_separate(self) -> None:
        groups = dedupe_survivors(
            [
                self._survivor(_mutation(id="a", find="x", kind="fail-open")),
                self._survivor(_mutation(id="b", find="x", kind="off-by-one")),
            ]
        )
        self.assertEqual(len(groups), 2)

    def test_a_single_survivor_is_not_marked_repeated(self) -> None:
        groups = dedupe_survivors([self._survivor(_mutation(id="a"))])
        self.assertEqual(groups[0]["count"], 1)
        self.assertFalse(groups[0]["repeated"])

    def test_a_control_that_survived_is_not_a_finding(self) -> None:
        # The control is *supposed* to survive; counting it would manufacture a Class B finding on
        # every clean pass.
        self.assertEqual(dedupe_survivors([self._survivor(_control())]), [])

    def test_killed_mutations_are_not_grouped(self) -> None:
        killed = mutate_verify.Result(
            mutation=_mutation(), outcome="killed", applied=True, test_exit=1
        )
        self.assertEqual(dedupe_survivors([killed]), [])


class ExitCodeTests(unittest.TestCase):
    def test_every_exit_code_is_distinct(self) -> None:
        # Collapsing any two would let one result read as a different result.
        codes = [
            EXIT_CLEAN,
            EXIT_SURVIVORS,
            EXIT_HARNESS_ERROR,
            EXIT_UNPROVEN,
            EXIT_RESTORE_FAILED,
        ]
        self.assertEqual(len(set(codes)), len(codes))

    def test_only_clean_is_zero(self) -> None:
        self.assertEqual(EXIT_CLEAN, 0)
        for code in (EXIT_SURVIVORS, EXIT_HARNESS_ERROR, EXIT_UNPROVEN, EXIT_RESTORE_FAILED):
            self.assertNotEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
