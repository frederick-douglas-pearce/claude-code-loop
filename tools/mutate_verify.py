#!/usr/bin/env python3
"""Mutation harness for the dev-loop acceptance gate (Class B).

The gate asks one question: *would we notice if this broke?* A test that stays green when the
behavior it guards is broken is a **survivor** — protection the human believes they have and does
not. This script is the mechanical half of finding them. The judgment half (choosing a
mechanism-preserving mutation, reading a survivor) stays with the agent that calls it.

Why this is a script and not prose: every review round of the prose version re-derived correctness
by reading, because there was nothing to execute. Precedent: ``hooks/guard_append_only.py``.

Stdlib only. It runs under bare ``python3`` in a consumer's environment, so it must not import
anything that is not in the standard library.

The fail posture is a deliberate asymmetry — preserve it in any change
--------------------------------------------------------------------
``exit 0`` means *clean and trustworthy*, and it is reachable only when ALL of these hold:

* the spec declared **at least one real mutation** (``"expect": "killed"``) — a pass made only of
  controls exercises no guard, so a clean verdict from it would certify nothing;
* the baseline suite was **green before any mutation** (a red baseline invalidates every verdict);
* every mutation **actually altered the file's bytes** (a pattern that does not match, or matches
  but changes nothing, is a loud error — never a silent pass);
* every file was **restored byte-exact** from its pre-mutation snapshot;
* every real mutation was **killed**, and every **control** mutation (``"expect": "survived"``)
  survived — the control is what proves the pipeline can report a survivor at all, so a green
  verdict proves it can go red;
* nothing raised unexpectedly along the way.

Anything else exits non-zero. There is no flag that produces ``exit 0`` without that proof.

**An unexpected exception fails closed**, mirroring ``hooks/guard_append_only.py``: it is reported
as a harness error (exit 2), never allowed to surface as the process exit 1 that means "survivors
found". A crash is not a result.

Two things this script must never do:

* **Never run ``git``.** Restoring a mutation from the index destroys uncommitted work the mutation
  never touched. Restores come from the snapshot copy, never from ``git checkout``/``git restore``.
* **Never mutate outside ``--root``.** A target whose *resolved path* leaves the root is a spec
  error, which covers ``..`` traversal, absolute paths and symlinks. It does **not** cover a hard
  link, which is indistinguishable from an ordinary file by path — that residual case rests on the
  trusted-spec bound stated below rather than on this check.

Snapshots live **outside the repository** (system temp) and are deleted on every path where the
tree was restored and verified. A surviving snapshot directory therefore means one of exactly two
things: a restore failed, or the pass was killed mid-run — which is what interrupted-pass recovery
keys on. **Whenever snapshots are retained, their path is printed**; when the tree is known good
they are gone, and there is nothing to announce.

Trust level of the spec and of ``--test-cmd``: repo-local, committed configuration written by the
project's maintainers — the same bound ``hooks/guard_append_only.py`` documents for ``id_pattern``,
and the same one ``README.md`` states. Neither is attacker input, and ``--test-cmd`` is run through
the shell so that real bindings (``unshare -rn -- sh -c '...'``) work unchanged.

Spec format (JSON)::

    {
      "mutations": [
        {
          "id": "fail-open-on-read-error",
          "file": "hooks/guard_append_only.py",
          "find": "return _deny(",
          "replace": "return _allow(",
          "kind": "fail-open",
          "expect": "killed"
        },
        {
          "id": "control-comment",
          "file": "hooks/guard_append_only.py",
          "find": "# noqa-control",
          "replace": "# noqa-control-mutated",
          "kind": "control",
          "expect": "survived"
        }
      ]
    }

Optional per-mutation keys: ``regex`` (bool, default false — ``find`` is a literal), ``all`` (bool,
default false — replace the first occurrence only), ``kind`` (string, default ``"unspecified"``),
``expect`` (``"killed"`` | ``"survived"``, default ``"killed"``).

Usage::

    python3 tools/mutate_verify.py run --spec mutations.json \\
        --test-cmd "python3 -m unittest discover -s tests" --root .

``--test-cmd`` is a **parameter**, never read from a config file: the engine that calls this stays
project-agnostic, and ``TEST_CMD`` is bound per project in ``loop.config.md``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

# Exit codes. Distinct on purpose: the caller acts differently on each, and collapsing any two of
# them would let a result read as a different result.
EXIT_CLEAN = 0  # every mutation killed as expected, control proved the pipeline can report survived
EXIT_SURVIVORS = 1  # the pass worked and found Class B findings — a result, not an error
EXIT_HARNESS_ERROR = 2  # no match / no-op / bad spec / red baseline / test-run error
EXIT_UNPROVEN = 3  # no control mutation, so a clean verdict is not trustworthy
EXIT_RESTORE_FAILED = 4  # a mutation may still be live in the tree — the most severe outcome

_VALID_EXPECT = ("killed", "survived")
_DEFAULT_TIMEOUT = 1800


class SpecError(Exception):
    """The spec is malformed, or names a target the harness refuses to touch."""


class MutationError(Exception):
    """A mutation could not be applied as specified — the AC5 loud failure."""


class RestoreError(Exception):
    """A file could not be given back byte-exact. The tree may still hold a mutation."""


@dataclass(frozen=True)
class Mutation:
    """One mutation, as declared in the spec."""

    id: str
    file: str
    find: str
    replace: str
    kind: str = "unspecified"
    expect: str = "killed"
    regex: bool = False
    all: bool = False


@dataclass
class Result:
    """What happened to one mutation."""

    mutation: Mutation
    outcome: str  # "killed" | "survived"
    applied: bool
    test_exit: int

    @property
    def as_expected(self) -> bool:
        return self.outcome == self.mutation.expect


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _normalize(text: str) -> str:
    """Collapse whitespace so near-identical mutations group together (AC7).

    Deliberately crude. The key is a *de-duplication signal*, not a similarity engine — a repeated
    survivor is worth saying once, and anything cleverer here would be pinned by nothing and drift.
    """
    return " ".join(text.split())


def load_spec(spec_path: Path) -> List[Mutation]:
    """Parse and validate a spec. Every rejection is loud — a silently-dropped mutation is a
    mutation that cannot fail, which is the defect this whole gate exists to catch."""
    try:
        raw = json.loads(spec_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise SpecError("cannot read spec {}: {}".format(spec_path, exc)) from exc
    except ValueError as exc:
        raise SpecError("spec {} is not valid JSON: {}".format(spec_path, exc)) from exc

    if not isinstance(raw, dict):
        raise SpecError("spec must be a JSON object with a 'mutations' key")
    entries = raw.get("mutations")
    if not isinstance(entries, list):
        raise SpecError("spec key 'mutations' must be a list")
    if not entries:
        raise SpecError("spec declares no mutations — nothing to verify")

    mutations: List[Mutation] = []
    seen_ids = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise SpecError("mutations[{}] must be an object".format(index))
        for key in ("id", "file", "find", "replace"):
            if not isinstance(entry.get(key), str) or not entry.get(key):
                # 'replace' may legitimately be empty (a deletion), so it is checked separately.
                if key == "replace" and isinstance(entry.get(key), str):
                    continue
                raise SpecError(
                    "mutations[{}] needs a non-empty string '{}'".format(index, key)
                )
        mutation_id = entry["id"]
        if mutation_id in seen_ids:
            raise SpecError("duplicate mutation id {!r}".format(mutation_id))
        seen_ids.add(mutation_id)

        expect = entry.get("expect", "killed")
        if expect not in _VALID_EXPECT:
            raise SpecError(
                "mutations[{}] 'expect' must be one of {}, got {!r}".format(
                    index, _VALID_EXPECT, expect
                )
            )
        for flag in ("regex", "all"):
            if flag in entry and not isinstance(entry[flag], bool):
                raise SpecError("mutations[{}] '{}' must be a boolean".format(index, flag))
        if entry.get("regex"):
            try:
                re.compile(entry["find"])
            except re.error as exc:
                raise SpecError(
                    "mutations[{}] 'find' is not a valid regex: {}".format(index, exc)
                ) from exc

        mutations.append(
            Mutation(
                id=mutation_id,
                file=entry["file"],
                find=entry["find"],
                replace=entry["replace"],
                kind=entry.get("kind", "unspecified"),
                expect=expect,
                regex=bool(entry.get("regex", False)),
                all=bool(entry.get("all", False)),
            )
        )
    return mutations


def resolve_target(root: Path, relative: str) -> Path:
    """Resolve a spec's target inside the root, refusing anything that escapes it."""
    root_resolved = root.resolve()
    target = (root_resolved / relative).resolve()
    try:
        target.relative_to(root_resolved)
    except ValueError:
        raise SpecError(
            "refusing to mutate {!r}: resolves outside --root {}".format(relative, root_resolved)
        ) from None
    if not target.is_file():
        raise SpecError("mutation target does not exist or is not a file: {}".format(target))
    return target


def mutate_text(mutation: Mutation, text: str) -> str:
    """Return the mutated text, or raise MutationError when the pattern does not match.

    AC5's first half lives here: a pattern that finds nothing is an **error**, never a no-op that
    reports success.
    """
    count = 0 if mutation.all else 1
    if mutation.regex:
        pattern = re.compile(mutation.find)
        if pattern.search(text) is None:
            raise MutationError(
                "mutation {!r}: regex {!r} matched nothing in {}".format(
                    mutation.id, mutation.find, mutation.file
                )
            )
        return pattern.sub(mutation.replace.replace("\\", "\\\\"), text, count=count)
    if mutation.find not in text:
        raise MutationError(
            "mutation {!r}: literal {!r} not found in {}".format(
                mutation.id, mutation.find, mutation.file
            )
        )
    return text.replace(mutation.find, mutation.replace, count if count else -1)


def apply_mutation(mutation: Mutation, target: Path) -> bytes:
    """Apply one mutation in place. Returns the original bytes.

    AC5's second half: the file's bytes must **actually change**. A substitution that matches but
    leaves the content identical (``find`` == ``replace``) is as useless as one that never matched,
    and is refused just as loudly — this is what makes "N mutations applied" a count of real
    changes rather than of helper invocations.
    """
    original = target.read_bytes()
    try:
        text = original.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise MutationError(
            "mutation {!r}: {} is not valid UTF-8".format(mutation.id, mutation.file)
        ) from exc

    mutated = mutate_text(mutation, text)
    mutated_bytes = mutated.encode("utf-8")
    if mutated_bytes == original:
        raise MutationError(
            "mutation {!r}: pattern matched but the bytes of {} did not change — "
            "a no-op mutation is an error, never a silent pass".format(mutation.id, mutation.file)
        )
    target.write_bytes(mutated_bytes)
    return original


def restore_file(target: Path, snapshot: Path, expected_sha: str) -> None:
    """Restore from the pre-mutation snapshot and verify the result is byte-exact.

    Never ``git checkout``/``git restore``: the index does not know about the surrounding work in
    progress, so restoring from it silently destroys uncommitted work the mutation never touched.
    """
    try:
        shutil.copyfile(str(snapshot), str(target))
        restored = target.read_bytes()
    except OSError as exc:
        raise RestoreError("could not restore {} from {}: {}".format(target, snapshot, exc)) from exc
    actual = _sha256(restored)
    if actual != expected_sha:
        raise RestoreError(
            "restore of {} is not byte-exact (expected sha256 {}, got {})".format(
                target, expected_sha, actual
            )
        )


def run_tests(test_cmd: str, root: Path, timeout: int) -> int:
    """Run the project's test command and return its exit status.

    A timeout is **not** silently counted as a kill. A mutation that hangs the suite is ambiguous,
    and claiming a kill we did not observe is the manufactured confidence this gate exists to
    prevent — so it is raised as a harness error for a human to read.
    """
    try:
        completed = subprocess.run(  # noqa: S602 - repo-local committed config, see module docstring
            test_cmd,
            shell=True,
            cwd=str(root),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise MutationError(
            "test command timed out after {}s — refusing to record an unobserved kill".format(
                timeout
            )
        ) from exc
    except OSError as exc:
        raise MutationError("could not run test command {!r}: {}".format(test_cmd, exc)) from exc
    return completed.returncode


def dedupe_survivors(results: Sequence[Result]) -> List[Dict[str, object]]:
    """Group survivors so a repeated one is said once, with a count (AC7).

    The key is ``(kind, normalized find-string)`` — the same mutation shape recurring in
    near-identical code is one signal about that shape, not N findings.
    """
    groups: Dict[Tuple[str, str], List[Result]] = {}
    order: List[Tuple[str, str]] = []
    for result in results:
        if result.outcome != "survived" or result.mutation.expect == "survived":
            continue
        key = (result.mutation.kind, _normalize(result.mutation.find))
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(result)

    grouped: List[Dict[str, object]] = []
    for key in order:
        members = groups[key]
        grouped.append(
            {
                "kind": key[0],
                "pattern": key[1],
                "count": len(members),
                "repeated": len(members) > 1,
                "locations": [
                    {"id": m.mutation.id, "file": m.mutation.file} for m in members
                ],
            }
        )
    return grouped


@dataclass
class Report:
    """Everything the caller needs to journal the pass, and nothing it has to infer."""

    baseline_exit: int
    applied: int = 0
    killed: int = 0
    survived: int = 0
    results: List[Result] = field(default_factory=list)
    survivor_groups: List[Dict[str, object]] = field(default_factory=list)
    control_proved: bool = False
    errors: List[str] = field(default_factory=list)
    snapshot_dir: Optional[str] = None

    def to_json(self) -> str:
        return json.dumps(
            {
                "baseline_exit": self.baseline_exit,
                "applied": self.applied,
                "killed": self.killed,
                "survived": self.survived,
                "control_proved": self.control_proved,
                "survivor_groups": self.survivor_groups,
                "results": [
                    {
                        "id": r.mutation.id,
                        "file": r.mutation.file,
                        "kind": r.mutation.kind,
                        "expect": r.mutation.expect,
                        "outcome": r.outcome,
                        "as_expected": r.as_expected,
                        "test_exit": r.test_exit,
                    }
                    for r in self.results
                ],
                "errors": self.errors,
                "snapshot_dir": self.snapshot_dir,
            },
            indent=2,
            sort_keys=True,
        )


def run_pass(
    mutations: Sequence[Mutation],
    test_cmd: str,
    root: Path,
    timeout: int = _DEFAULT_TIMEOUT,
    snapshot_root: Optional[Path] = None,
) -> Tuple[Report, int]:
    """Run a whole mutation pass. Returns the report and the exit code.

    One mutation is live at a time: apply, run, restore, then move on. Snapshots are taken **before**
    each mutation and deleted only when the whole pass completes cleanly.
    """
    # Resolve every target before touching anything, so a bad spec cannot leave a half-mutated tree.
    targets = {m.id: resolve_target(root, m.file) for m in mutations}

    # A pass built only of controls exercises no guard at all. It would satisfy every other
    # condition below and report `killed: 0` as clean, which is the vacuous-pass shape AC5 exists to
    # rule out — so it is refused before the baseline is even run.
    if not any(m.expect == "killed" for m in mutations):
        report = Report(baseline_exit=-1)
        report.errors.append(
            "spec declares no real mutation (every entry is a control) — such a pass exercises no "
            "guard, so a clean verdict from it would certify nothing"
        )
        return report, EXIT_HARNESS_ERROR

    snapshot_dir = Path(
        tempfile.mkdtemp(prefix="mutate-verify-", dir=str(snapshot_root) if snapshot_root else None)
    )
    report = Report(baseline_exit=-1, snapshot_dir=str(snapshot_dir))

    def discard_snapshots() -> None:
        """Drop the snapshots once the tree is known-good.

        Retention is a *signal*, not bookkeeping: a retained directory means "a mutation may still
        be live". So it is cleared on every path this function controls where the tree was restored
        and verified, and kept only when a restore actually failed. A pass killed mid-run never
        reaches any of these paths, which is exactly the interrupted case recovery must catch.
        """
        shutil.rmtree(str(snapshot_dir), ignore_errors=True)
        report.snapshot_dir = None

    try:
        report.baseline_exit = run_tests(test_cmd, root, timeout)
    except MutationError as exc:
        report.errors.append(str(exc))
        discard_snapshots()
        return report, EXIT_HARNESS_ERROR
    if report.baseline_exit != 0:
        report.errors.append(
            "baseline is not green (exit {}) — every verdict below it would be meaningless, "
            "so none was taken".format(report.baseline_exit)
        )
        discard_snapshots()
        return report, EXIT_HARNESS_ERROR

    for index, mutation in enumerate(mutations):
        target = targets[mutation.id]
        snapshot = snapshot_dir / "{:03d}-{}".format(index, target.name)
        try:
            original = target.read_bytes()
            snapshot.write_bytes(original)
        except OSError as exc:
            report.errors.append("could not snapshot {}: {}".format(target, exc))
            discard_snapshots()
            return report, EXIT_HARNESS_ERROR
        expected_sha = _sha256(original)

        # One handler for the whole mutate-run-restore body, catching **any** exception rather than
        # only the ones this module raises. An unexpected OSError (a read-only target, a full disk)
        # escaping to the process would surface as exit 1 — which means "survivors found" — so a
        # crash would read as a result. Fail closed instead, mirroring `hooks/guard_append_only.py`.
        try:
            apply_mutation(mutation, target)
            report.applied += 1
            test_exit = run_tests(test_cmd, root, timeout)
            outcome = "killed" if test_exit != 0 else "survived"
            if outcome == "killed":
                report.killed += 1
            else:
                report.survived += 1
            report.results.append(
                Result(mutation=mutation, outcome=outcome, applied=True, test_exit=test_exit)
            )
        except RestoreError as exc:  # only reachable if a helper is changed to raise it here
            report.errors.append(str(exc))
            return report, EXIT_RESTORE_FAILED
        except Exception as exc:  # noqa: BLE001 - deliberate: see the comment above
            report.errors.append("{}: {}".format(type(exc).__name__, exc))
            # Restore before reporting, and never trust "nothing was written" as a reason to skip
            # it — being wrong about that means leaving a mutation live in the tree.
            try:
                restore_file(target, snapshot, expected_sha)
            except Exception as restore_exc:  # noqa: BLE001 - the tree may now be dirty
                report.errors.append(
                    "restore also failed: {}: {}".format(
                        type(restore_exc).__name__, restore_exc
                    )
                )
                return report, EXIT_RESTORE_FAILED
            discard_snapshots()
            return report, EXIT_HARNESS_ERROR

        try:
            restore_file(target, snapshot, expected_sha)
        except Exception as exc:  # noqa: BLE001 - the tree may still hold this mutation
            report.errors.append("{}: {}".format(type(exc).__name__, exc))
            return report, EXIT_RESTORE_FAILED

    report.survivor_groups = dedupe_survivors(report.results)

    controls = [r for r in report.results if r.mutation.expect == "survived"]
    report.control_proved = bool(controls) and all(r.as_expected for r in controls)

    real_survivors = sum(int(g["count"]) for g in report.survivor_groups)

    # The whole tree was given back and every restore verified, so the snapshots have done their job.
    discard_snapshots()

    if real_survivors:
        return report, EXIT_SURVIVORS
    if not controls:
        report.errors.append(
            "no control mutation (expect=survived) was declared, so nothing proved this pass can "
            "report a survivor at all — a green verdict must prove it can go red"
        )
        return report, EXIT_UNPROVEN
    if not report.control_proved:
        report.errors.append(
            "a control mutation (expect=survived) was killed — the pipeline's classification cannot "
            "be trusted, so no verdict was taken from this pass"
        )
        return report, EXIT_HARNESS_ERROR
    # Every outcome now matches its expectation, and that is a consequence of the two branches
    # above rather than a further check: a real mutation that survived left the pass at
    # EXIT_SURVIVORS, and a control that was killed left it at the branch immediately above. An
    # explicit `if unexpected:` here would be unreachable, and an unreachable guard reads as
    # protection that is not there.
    return report, EXIT_CLEAN


def _render(report: Report, code: int) -> str:
    lines = [
        "baseline: exit {}".format(report.baseline_exit),
        "applied: {} (mutations that actually altered a file)".format(report.applied),
        "killed: {}  survived: {}".format(report.killed, report.survived),
        "control proved the pipeline can report a survivor: {}".format(
            "yes" if report.control_proved else "NO"
        ),
    ]
    for group in report.survivor_groups:
        lines.append(
            "SURVIVOR [{}] {!r} x{}{}".format(
                group["kind"],
                group["pattern"],
                group["count"],
                "  (repeated — de-duplication signal)" if group["repeated"] else "",
            )
        )
    for error in report.errors:
        lines.append("ERROR: {}".format(error))
    if report.snapshot_dir:
        lines.append(
            "SNAPSHOTS RETAINED: {} — an unfinished pass. Restore from these, never with git.".format(
                report.snapshot_dir
            )
        )
    lines.append("exit {}".format(code))
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="mutate_verify.py", description="Run a mutation pass for the dev-loop acceptance gate."
    )
    sub = parser.add_subparsers(dest="command", required=True)
    run_parser = sub.add_parser("run", help="run a mutation pass from a spec")
    run_parser.add_argument("--spec", required=True, type=Path, help="path to the JSON spec")
    run_parser.add_argument(
        "--test-cmd",
        required=True,
        help="the project's TEST_CMD, passed as a parameter (never read from config)",
    )
    run_parser.add_argument("--root", default=Path("."), type=Path, help="repository root")
    run_parser.add_argument("--timeout", default=_DEFAULT_TIMEOUT, type=int, help="per-run seconds")
    run_parser.add_argument("--json", action="store_true", help="emit the report as JSON")

    args = parser.parse_args(argv)

    try:
        mutations = load_spec(args.spec)
        report, code = run_pass(mutations, args.test_cmd, args.root, timeout=args.timeout)
    except (SpecError, MutationError) as exc:
        print("mutate_verify: {}".format(exc), file=sys.stderr)
        return EXIT_HARNESS_ERROR
    except Exception as exc:  # noqa: BLE001 - fail closed; a crash must never read as a result
        # Without this the exception would reach the interpreter, which exits 1 — and 1 is
        # EXIT_SURVIVORS. A traceback would silently become "the pass found survivors".
        print("mutate_verify: unexpected {}: {}".format(type(exc).__name__, exc), file=sys.stderr)
        return EXIT_HARNESS_ERROR

    print(report.to_json() if args.json else _render(report, code))
    return code


if __name__ == "__main__":
    sys.exit(main())
