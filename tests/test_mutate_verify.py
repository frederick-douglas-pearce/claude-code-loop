#!/usr/bin/env python3
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

Run with: python3 -m unittest discover -s tests
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

# Load the harness by path, as `test_guard_append_only.py` and `test_repo_consistency.py` both do.
# Deliberately NOT `sys.path.insert`: `discover` runs all three modules in one process, so a
# permanent entry would leave `tools/` on the path for the whole session and shadow any stdlib
# module sharing a filename with something added there later.
_MUTATE_VERIFY_PATH = Path(__file__).resolve().parents[1] / "tools" / "mutate_verify.py"
_spec = importlib.util.spec_from_file_location("mutate_verify", _MUTATE_VERIFY_PATH)
assert _spec and _spec.loader
mutate_verify = importlib.util.module_from_spec(_spec)
# Registered BEFORE exec: `dataclasses` resolves a field's type by looking its module up in
# `sys.modules`, so a module executed while absent from it raises during class creation.
sys.modules["mutate_verify"] = mutate_verify
_spec.loader.exec_module(mutate_verify)

from mutate_verify import (  # noqa: E402  # type: ignore[import-not-found]
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
# A red baseline that prints something a human would need in order to understand why.
_NOISY_RED_SUITE = '{exe} -c "print(\'DIAGNOSTIC-MARKER: assertion failed\'); raise SystemExit(1)"'
# A suite that observes ONLY the control's marker — so the control dies and the real mutation lives.
_CONTROL_OBSERVING_SUITE = (
    "{exe} -c \"import sys; sys.exit(0 if 'SPARE_A' in open('src.py').read() else 1)\""
)

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

        # First close the alias hole: `from subprocess import call as _c` would make every
        # attribute-based check below blind, so no process-spawning name may be imported directly.
        spawning = {"subprocess", "os", "runpy", "multiprocessing", "pty", "commands"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertIn(
                        alias.name.split(".")[0],
                        spawning | {"argparse", "hashlib", "json", "re", "shutil", "sys",
                                    "tempfile", "dataclasses", "pathlib", "typing", "__future__"},
                        "unexpected import {!r}".format(alias.name),
                    )
                    self.assertIsNone(alias.asname, "aliased import hides the call site")
            elif isinstance(node, ast.ImportFrom):
                self.assertNotIn(
                    node.module,
                    spawning,
                    "importing names out of {!r} bypasses the call-site check".format(node.module),
                )

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

    def test_a_backreference_shaped_replacement_is_refused(self) -> None:
        # Replacements are inserted literally, so `\\1` would land as those two characters. That
        # changes bytes (clearing the no-op check) and usually breaks the file, which the suite
        # reports as a KILL — a false negative wearing a pass. Refuse the shape instead.
        for bad in ("return \\1", "x = \\g<0>"):
            with self.assertRaises(SpecError) as ctx:
                load_spec(
                    self._write(
                        {
                            "mutations": [
                                {
                                    "id": "a",
                                    "file": "src.py",
                                    "find": "value = (.)",
                                    "replace": bad,
                                    "regex": True,
                                }
                            ]
                        }
                    )
                )
            self.assertIn("backreference", str(ctx.exception))

    def test_a_literal_replacement_may_contain_a_backslash_digit(self) -> None:
        # The refusal is scoped to `regex: true`; a literal replacement is inserted verbatim and
        # has no backreference semantics to be confused about.
        path = self._write(
            {"mutations": [{"id": "a", "file": "src.py", "find": "GOOD", "replace": "x\\1"}]}
        )
        self.assertEqual(load_spec(path)[0].replace, "x\\1")

    def test_kind_must_be_a_string_because_it_becomes_a_grouping_key(self) -> None:
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
                                "kind": 123,
                            }
                        ]
                    }
                )
            )
        self.assertIn("kind", str(ctx.exception))

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
        #
        # The spec MUST pair a real mutation with the killed control. An earlier version passed only
        # the control, which made the spec control-only — so `run_pass` refused it up front and this
        # test went green without ever reaching the branch it names. Four paths return
        # EXIT_HARNESS_ERROR, so the error text is asserted to tell this one from those.
        scratch = _Scratch(self)
        killed_control = _control(find="GOOD", replace="BAD", id="bad-control")
        report, code = run_pass([_mutation(), killed_control], scratch.test_cmd, scratch.root)
        self.assertEqual(code, EXIT_HARNESS_ERROR)
        self.assertFalse(report.control_proved)
        self.assertTrue(
            any("classification cannot be trusted" in e for e in report.errors),
            "reached a different EXIT_HARNESS_ERROR path than the one this test names",
        )

    def test_a_killed_control_outranks_a_survivor_finding(self) -> None:
        # The pipeline mis-classified (the control died), so "survivors found" from it would be an
        # authoritative-sounding verdict with nothing behind it. Integrity gates every verdict.
        scratch = _Scratch(self, suite=_CONTROL_OBSERVING_SUITE)
        report, code = run_pass(
            [_mutation(), _control(replace="SPARE_Z")], scratch.test_cmd, scratch.root
        )
        # The real mutation survived (this suite ignores GOOD) AND the control was killed.
        self.assertEqual(report.survived, 1)
        self.assertEqual(report.killed, 1)
        self.assertNotEqual(code, EXIT_SURVIVORS)
        self.assertEqual(code, EXIT_HARNESS_ERROR)
        self.assertTrue(any("classification cannot be trusted" in e for e in report.errors))

    def test_a_survivor_is_reported_even_without_a_control(self) -> None:
        # The mirror of the rule above: a survivor is self-proving. The pipeline just demonstrated
        # the capability a control exists to establish, so a missing control must not downgrade a
        # real finding to "unproven".
        scratch = _Scratch(self, suite=_BLIND_SUITE)
        _, code = run_pass([_mutation()], scratch.test_cmd, scratch.root)
        self.assertEqual(code, EXIT_SURVIVORS)

    def _explode(self, name: str, exc: Exception) -> None:
        original = getattr(mutate_verify, name)

        def boom(*args: object, **kwargs: object) -> object:
            raise exc

        setattr(mutate_verify, name, boom)
        self.addCleanup(lambda: setattr(mutate_verify, name, original))

    def test_a_doubled_failure_with_a_dirty_tree_reports_restore_failed(self) -> None:
        # The worst state the design defines: the mutation landed, then the harness errored, then
        # the restore failed too. A mutation is live, so it must exit EXIT_RESTORE_FAILED.
        scratch = _Scratch(self)
        original_run = mutate_verify.run_tests
        calls = {"n": 0}

        def green_baseline_then_explode(*args: object, **kwargs: object) -> object:
            calls["n"] += 1
            if calls["n"] == 1:
                return original_run(*args, **kwargs)  # the baseline must pass, or nothing is tried
            raise OSError("simulated failure while running the suite")

        mutate_verify.run_tests = green_baseline_then_explode  # type: ignore[assignment]
        self.addCleanup(lambda: setattr(mutate_verify, "run_tests", original_run))
        self._explode("restore_file", RestoreError("simulated failure while restoring"))

        report, code = run_pass([_mutation()], scratch.test_cmd, scratch.root)
        self.assertEqual(code, EXIT_RESTORE_FAILED)
        self.assertTrue(any("restore also failed" in e for e in report.errors))
        self.assertIn("BAD", scratch.source.read_text(encoding="utf-8"))  # the mutation IS live
        # The DISK, not `report.snapshot_dir` — the field is the report's own claim, and asserting
        # it passes for an implementation that keeps the field and deletes the files, which would
        # destroy the only safe repair for the most severe outcome this tool has.
        self.assertIsNotNone(report.snapshot_dir)
        self.assertTrue(Path(report.snapshot_dir).is_dir(), "the safe repair was deleted")
        import shutil

        shutil.rmtree(report.snapshot_dir, ignore_errors=True)

    def test_a_doubled_failure_with_an_intact_tree_is_only_a_harness_error(self) -> None:
        # Same doubled failure, but the mutation never landed — an unwritable target, say. Nothing
        # is live, so code 4 would be crying wolf, and a severity that fires on the most benign
        # cause there is stops being read.
        scratch = _Scratch(self)
        self._explode("apply_mutation", OSError("simulated read-only target"))
        self._explode("restore_file", RestoreError("simulated failure while restoring"))

        report, code = run_pass([_mutation()], scratch.test_cmd, scratch.root)
        self.assertEqual(code, EXIT_HARNESS_ERROR)
        self.assertTrue(any("tree is intact" in e for e in report.errors))
        self.assertEqual(scratch.source.read_text(encoding="utf-8"), _SOURCE)

    def test_a_write_during_the_test_run_is_never_overwritten(self) -> None:
        # THE defect this design exists to prevent, reached by a door that is not `git restore`.
        # A developer saves an edit while the suite runs under a live mutant. The snapshot no longer
        # describes "before", so copying it back would destroy their work — and the pass would
        # report exit 0, clean and trustworthy, having done it.
        scratch = _Scratch(self)
        writer = scratch.root / "writer.py"
        writer.write_text(
            "import sys\n"
            "c = open('src.py').read()\n"
            "if 'BAD' in c and 'DEVWORK' not in c:\n"
            "    open('src.py', 'a').write('DEVWORK = 1\\n')\n"
            "sys.exit(0 if 'GOOD' in open('src.py').read() else 1)\n",
            encoding="utf-8",
        )
        cmd = "{} {}".format(sys.executable, writer)

        report, code = run_pass([_mutation(), _control()], cmd, scratch.root)
        self.assertEqual(code, EXIT_RESTORE_FAILED)
        self.assertNotEqual(code, EXIT_CLEAN)
        self.assertIn("DEVWORK", scratch.source.read_text(encoding="utf-8"))
        self.assertTrue(any("refusing to restore" in e for e in report.errors))
        self.assertIsNotNone(report.snapshot_dir)
        self.assertTrue(Path(report.snapshot_dir).is_dir(), "the safe repair was deleted")
        import shutil

        shutil.rmtree(report.snapshot_dir, ignore_errors=True)

    def test_a_change_between_snapshot_and_mutation_is_also_refused(self) -> None:
        # The narrower window, same rule: if the file is not what we snapshotted, the snapshot is
        # already stale and writing it back would erase whatever changed it.
        scratch = _Scratch(self)
        original_apply = mutate_verify.apply_mutation

        def apply_then_report_different_original(mutation: object, target: Path) -> bytes:
            original_apply(mutation, target)
            return b"not what was snapshotted"

        mutate_verify.apply_mutation = apply_then_report_different_original  # type: ignore
        self.addCleanup(lambda: setattr(mutate_verify, "apply_mutation", original_apply))

        report, code = run_pass([_mutation()], scratch.test_cmd, scratch.root)
        self.assertEqual(code, EXIT_RESTORE_FAILED)
        self.assertTrue(any("between the snapshot and the mutation" in e for e in report.errors))
        self.assertTrue(Path(report.snapshot_dir).is_dir(), "the safe repair was deleted")
        import shutil

        shutil.rmtree(report.snapshot_dir, ignore_errors=True)

    def test_a_failed_cleanup_does_not_claim_the_snapshots_are_gone(self) -> None:
        # `ignore_errors=True` swallows a real removal failure. Clearing the field anyway would
        # invert the signal: the directory survives while the report says it is gone, so recovery
        # reads a clean tree as dirty.
        import shutil as _shutil

        scratch = _Scratch(self)
        original_rmtree = _shutil.rmtree

        def silently_failing_rmtree(*args: object, **kwargs: object) -> None:
            # Exactly what `ignore_errors=True` does when removal genuinely fails: nothing, quietly.
            return None

        _shutil.rmtree = silently_failing_rmtree  # type: ignore[assignment]
        self.addCleanup(lambda: setattr(_shutil, "rmtree", original_rmtree))

        report, code = run_pass([_mutation(), _control()], scratch.test_cmd, scratch.root)
        self.assertEqual(code, EXIT_CLEAN)
        self.assertIsNotNone(report.snapshot_dir, "cleared the field while the directory survived")
        self.assertTrue(any("stale, not evidence" in e for e in report.errors))

        _shutil.rmtree = original_rmtree  # type: ignore[assignment]
        original_rmtree(report.snapshot_dir, ignore_errors=True)

    def test_restored_is_counted_because_the_ledger_line_names_it(self) -> None:
        scratch = _Scratch(self)
        report, code = run_pass([_mutation(), _control()], scratch.test_cmd, scratch.root)
        self.assertEqual(code, EXIT_CLEAN)
        self.assertEqual(report.restored, report.applied)
        self.assertEqual(report.restored, 2)

    def test_a_red_baseline_carries_the_output_that_explains_it(self) -> None:
        scratch = _Scratch(self, suite=_NOISY_RED_SUITE)
        report, _ = run_pass([_mutation()], scratch.test_cmd, scratch.root)
        self.assertTrue(any("DIAGNOSTIC-MARKER" in e for e in report.errors))

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

    def test_snapshots_really_leave_the_disk_when_the_tree_is_known_good(self) -> None:
        # Assert the directory is GONE, not merely that the report says so. Asserting
        # `report.snapshot_dir is None` is an outcome assertion: it passes for an implementation
        # that nulls the field and leaves the files, which is exactly the leak this cleanup exists
        # to prevent. Capture the path first, then look at the filesystem.
        scratch = _Scratch(self)
        seen: list = []
        original_mkdtemp = mutate_verify.tempfile.mkdtemp

        def spy(*args: object, **kwargs: object) -> str:
            path = original_mkdtemp(*args, **kwargs)
            seen.append(path)
            return path

        mutate_verify.tempfile.mkdtemp = spy  # type: ignore[assignment]
        self.addCleanup(lambda: setattr(mutate_verify.tempfile, "mkdtemp", original_mkdtemp))

        report, code = run_pass([_mutation(), _control()], scratch.test_cmd, scratch.root)
        self.assertEqual(code, EXIT_CLEAN)
        self.assertEqual(len(seen), 1)
        self.assertFalse(Path(seen[0]).exists(), "snapshot directory was left on disk")
        self.assertIsNone(report.snapshot_dir)

    def test_a_spec_of_only_controls_is_refused(self) -> None:
        # Every other condition for a clean verdict would hold, and the pass would report
        # `killed: 0` as clean — certifying that nothing was tested.
        scratch = _Scratch(self)
        report, code = run_pass([_control()], scratch.test_cmd, scratch.root)
        self.assertEqual(code, EXIT_HARNESS_ERROR)
        self.assertEqual(report.applied, 0)
        self.assertTrue(any("no real mutation" in e for e in report.errors))

    def test_an_unexpected_exception_fails_closed_rather_than_reading_as_survivors(self) -> None:
        # An OSError escaping to the interpreter exits 1 — which is EXIT_SURVIVORS. A crash must
        # never be readable as "the pass found survivors".
        scratch = _Scratch(self)
        original_apply = mutate_verify.apply_mutation

        def exploding_apply(*args: object, **kwargs: object) -> bytes:
            raise OSError("simulated read-only filesystem")

        mutate_verify.apply_mutation = exploding_apply  # type: ignore[assignment]
        self.addCleanup(lambda: setattr(mutate_verify, "apply_mutation", original_apply))

        report, code = run_pass([_mutation(), _control()], scratch.test_cmd, scratch.root)
        self.assertNotEqual(code, EXIT_SURVIVORS)
        self.assertEqual(code, EXIT_HARNESS_ERROR)
        self.assertTrue(any("OSError" in e for e in report.errors))
        self.assertEqual(scratch.source.read_text(encoding="utf-8"), _SOURCE)

    def test_a_timeout_is_not_recorded_as_a_kill(self) -> None:
        # The suite must be fast at BASELINE and hang only once the mutant is live. An earlier
        # version timed out on the baseline, so `applied` was 0 and `killed == 0` was trivially
        # true — the assertion held without the code path it names ever running, and the case that
        # matters (a timeout with a mutation live in the tree, needing a restore) was uncovered.
        scratch = _Scratch(self)
        hangs_only_when_mutated = (
            "{exe} -c \"import sys,time; c=open('src.py').read(); "
            "sys.exit(0) if 'GOOD' in c else time.sleep(30)\""
        ).format(exe=sys.executable)

        report, code = run_pass([_mutation()], hangs_only_when_mutated, scratch.root, timeout=2)
        self.assertEqual(code, EXIT_HARNESS_ERROR)
        self.assertEqual(report.baseline_exit, 0, "the baseline must have completed, not timed out")
        self.assertEqual(report.applied, 1, "the timeout must happen with a mutation live")
        self.assertEqual(report.killed, 0)
        self.assertTrue(any("timed out" in e for e in report.errors))
        # And the tree still comes back.
        self.assertEqual(scratch.source.read_text(encoding="utf-8"), _SOURCE)

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


class CliTests(unittest.TestCase):
    """The surface the orchestrator actually reads: the process exit code and what is printed.

    Everything below `run_pass` was unguarded in the first draft of this module — a mutation pass
    over it produced six survivors, including deletion of the `SNAPSHOTS RETAINED` warning, which is
    the interrupted-pass signal. The verdict is only as trustworthy as its delivery.
    """

    def _spec(self, scratch: _Scratch, mutations: list) -> Path:
        path = scratch.root / "spec.json"
        path.write_text(json.dumps({"mutations": mutations}), encoding="utf-8")
        return path

    @staticmethod
    def _invoke(argv: list) -> tuple:
        """Run the CLI and RETURN what it printed, rather than discarding it.

        An earlier version redirected stdout and stderr into throwaway buffers, which meant no test
        observed anything `main()` printed — deleting the `print` outright, or ignoring `--json`,
        left the suite green. A class whose docstring says it covers "what is printed" must
        actually look at it.
        """
        import contextlib
        import io

        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = mutate_verify.main(argv)
        return code, out.getvalue(), err.getvalue()

    def _quiet(self, argv: list) -> int:
        return self._invoke(argv)[0]

    def _clean_spec(self, scratch: _Scratch) -> Path:
        """A real mutation plus a control — the shape that can reach EXIT_CLEAN."""
        return self._spec(
            scratch,
            [
                {"id": "m", "file": "src.py", "find": "GOOD", "replace": "BAD"},
                {
                    "id": "c",
                    "file": "src.py",
                    "find": "SPARE_A",
                    "replace": "SPARE_Z",
                    "expect": "survived",
                },
            ],
        )

    @staticmethod
    def _argv(scratch: _Scratch, spec: Path) -> list:
        return [
            "run",
            "--spec",
            str(spec),
            "--test-cmd",
            scratch.test_cmd,
            "--root",
            str(scratch.root),
        ]

    def _run(self, scratch: _Scratch, mutations: list, extra: list = None) -> int:
        spec = self._spec(scratch, mutations)
        argv = [
            "run",
            "--spec",
            str(spec),
            "--test-cmd",
            scratch.test_cmd,
            "--root",
            str(scratch.root),
        ]
        return self._quiet(argv + (extra or []))

    def test_main_propagates_clean(self) -> None:
        scratch = _Scratch(self)
        code = self._run(
            scratch,
            [
                {"id": "m", "file": "src.py", "find": "GOOD", "replace": "BAD"},
                {
                    "id": "c",
                    "file": "src.py",
                    "find": "SPARE_A",
                    "replace": "SPARE_A2",
                    "expect": "survived",
                },
            ],
        )
        self.assertEqual(code, EXIT_CLEAN)

    def test_main_propagates_a_nonzero_verdict_rather_than_always_returning_zero(self) -> None:
        # The property AC6 is about, at the boundary the engine reads. `return 0` here would make
        # every pass look clean no matter what `run_pass` decided.
        scratch = _Scratch(self, suite=_BLIND_SUITE)
        code = self._run(
            scratch,
            [
                {"id": "m", "file": "src.py", "find": "GOOD", "replace": "BAD"},
                {
                    "id": "c",
                    "file": "src.py",
                    "find": "SPARE_A",
                    "replace": "SPARE_A2",
                    "expect": "survived",
                },
            ],
        )
        self.assertEqual(code, EXIT_SURVIVORS)

    def test_main_returns_harness_error_on_a_bad_spec(self) -> None:
        scratch = _Scratch(self)
        spec = scratch.root / "spec.json"
        spec.write_text("{not json", encoding="utf-8")
        code = self._quiet(
            ["run", "--spec", str(spec), "--test-cmd", scratch.test_cmd, "--root", str(scratch.root)]
        )
        self.assertEqual(code, EXIT_HARNESS_ERROR)

    def test_an_unexpected_exception_in_main_never_exits_as_survivors(self) -> None:
        scratch = _Scratch(self)
        original = mutate_verify.run_pass

        def exploding(*args: object, **kwargs: object) -> None:
            raise RuntimeError("simulated internal defect")

        mutate_verify.run_pass = exploding  # type: ignore[assignment]
        self.addCleanup(lambda: setattr(mutate_verify, "run_pass", original))

        code = self._run(scratch, [{"id": "m", "file": "src.py", "find": "GOOD", "replace": "BAD"}])
        self.assertEqual(code, EXIT_HARNESS_ERROR)
        self.assertNotEqual(code, EXIT_SURVIVORS)

    def test_the_cli_actually_prints_the_report(self) -> None:
        # Deleting the `print` in `main()` must not leave the suite green: a tool whose entire
        # product is a verdict that nobody prints has produced nothing.
        scratch = _Scratch(self)
        code, out, _ = self._invoke(self._argv(scratch, self._clean_spec(scratch)))
        self.assertEqual(code, EXIT_CLEAN)
        self.assertIn("applied:", out)
        self.assertIn("killed:", out)
        self.assertIn("baseline:", out)
        self.assertIn("control proved", out)
        self.assertIn("exit 0", out)

    def test_json_flag_produces_parseable_json_not_the_rendered_report(self) -> None:
        scratch = _Scratch(self)
        code, out, _ = self._invoke(self._argv(scratch, self._clean_spec(scratch)) + ["--json"])
        self.assertEqual(code, EXIT_CLEAN)
        payload = json.loads(out)  # would raise if `--json` were ignored
        self.assertEqual(payload["applied"], 2)
        self.assertEqual(payload["restored"], 2)
        self.assertNotIn("baseline: exit", out)

    def test_a_survivor_is_named_in_what_the_cli_prints(self) -> None:
        scratch = _Scratch(self, suite=_BLIND_SUITE)
        code, out, _ = self._invoke(self._argv(scratch, self._clean_spec(scratch)))
        self.assertEqual(code, EXIT_SURVIVORS)
        self.assertIn("SURVIVOR", out)

    def test_the_timeout_flag_reaches_the_pass(self) -> None:
        # `--timeout` is plumbing, and unplumbed plumbing is invisible: without this, dropping the
        # argument would silently restore the 1800s default on every run.
        scratch = _Scratch(self)
        spec = self._spec(scratch, [{"id": "m", "file": "src.py", "find": "GOOD", "replace": "BAD"}])
        argv = [
            "run", "--spec", str(spec),
            "--test-cmd", '{} -c "import time; time.sleep(30)"'.format(sys.executable),
            "--root", str(scratch.root), "--timeout", "1",
        ]
        code, out, _ = self._invoke(argv)
        self.assertEqual(code, EXIT_HARNESS_ERROR)
        self.assertIn("timed out after 1s", out)

    def test_spec_is_required(self) -> None:
        with self.assertRaises(SystemExit):
            self._invoke(["run", "--test-cmd", "true"])

    def test_render_announces_a_survivor_and_marks_a_repeat(self) -> None:
        report = mutate_verify.Report(baseline_exit=0)
        report.survivor_groups = [
            {"kind": "fail-open", "pattern": "x", "count": 2, "repeated": True, "locations": []}
        ]
        rendered = mutate_verify._render(report, EXIT_SURVIVORS)
        self.assertIn("SURVIVOR", rendered)
        self.assertIn("fail-open", rendered)
        self.assertIn("de-duplication signal", rendered)

    def test_render_announces_retained_snapshots(self) -> None:
        # The only durable pointer to a tree that may still hold a live mutation.
        report = mutate_verify.Report(baseline_exit=0, snapshot_dir="/tmp/example-snapshots")
        rendered = mutate_verify._render(report, EXIT_RESTORE_FAILED)
        self.assertIn("SNAPSHOTS RETAINED", rendered)
        self.assertIn("/tmp/example-snapshots", rendered)

    def test_render_does_not_announce_snapshots_when_the_tree_is_good(self) -> None:
        report = mutate_verify.Report(baseline_exit=0)
        self.assertNotIn("SNAPSHOTS RETAINED", mutate_verify._render(report, EXIT_CLEAN))

    def test_render_reports_errors(self) -> None:
        report = mutate_verify.Report(baseline_exit=1)
        report.errors.append("baseline is not green")
        self.assertIn("ERROR: baseline is not green", mutate_verify._render(report, 2))

    def test_json_report_carries_the_fields_a_caller_journals(self) -> None:
        scratch = _Scratch(self)
        report, _ = run_pass([_mutation(), _control()], scratch.test_cmd, scratch.root)
        payload = json.loads(report.to_json())
        for key in (
            "applied",
            "killed",
            "survived",
            "control_proved",
            "survivor_groups",
            "results",
            "errors",
            "baseline_exit",
            "snapshot_dir",
        ):
            self.assertIn(key, payload)
        self.assertEqual(payload["applied"], 2)
        self.assertEqual(payload["killed"], 1)
        self.assertTrue(payload["control_proved"])
        self.assertEqual(len(payload["results"]), 2)


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
