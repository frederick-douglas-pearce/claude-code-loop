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

* ``--root`` was **attributed** as a tree distinct from ``--parent-root`` — an unisolated pass
  breaks the caller's own working tree, and a green verdict from one is unproven, not clean;
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

**Attribution — the interlock on ``--root``.** ``--parent-root`` is required, and a ``--root`` that
resolves to the same tree is refused with ``exit 5`` **before** anything is resolved, snapshotted or
run. Until this existed ``--root`` was taken entirely on faith: a failed ``git worktree add`` (or a
``cd`` that failed after it in an ``&&`` chain) leaves the pass running in the caller's own tree,
mutating working code beside uncommitted deliverables and reporting green. ``--in-tree-authorized``
is the sole way past it — the engine's escalated in-tree rung, chosen by a human, recorded in the
report and on stderr so it can never be journalled as an ordinary pass.

The comparison is resolved-path **equality**, deliberately not containment: a worktree the host
materializes *inside* the repository is a genuinely separate working tree, and refusing it would
push every pass onto the escape hatch. The bound this leaves — a ``--root`` pointing at a plain
subdirectory of the parent, which shares its toplevel — is real and is not covered here, because
deciding it needs git and this script may not ask.

Two things this script must never do:

* **Never run ``git``.** Restoring a mutation from the index destroys uncommitted work the mutation
  never touched. Restores come from the snapshot copy, never from ``git checkout``/``git restore``.
  This is why attribution above is a path comparison rather than the ``rev-parse --show-toplevel``
  the calling agent runs: the check the *agent* performs and the interlock the *harness* enforces
  are deliberately different mechanisms answering the same question.
* **Never mutate outside ``--root``.** A target whose *resolved path* leaves the root is a spec
  error, which covers ``..`` traversal, absolute paths and symlinks. It does **not** cover a hard
  link, which is indistinguishable from an ordinary file by path — that residual case rests on the
  trusted-spec bound stated below rather than on this check.

Snapshots live **outside the repository** (system temp) and are deleted on every path where the
tree was restored and verified, so a surviving snapshot directory means the tree may still hold a
live mutation. That directory is the durable input to interrupted-pass recovery.

Note what this deliberately does **not** promise: that the path is always announced. A pass killed
by a signal — Ctrl-C is the likeliest way a long pass ends early — runs no handler here, so the
mutation stays in the tree and nothing is printed. That case is real, and recovering from it is a
separate mechanism this script does not carry. Finding the snapshots is what recovery is *for*.

Trust level of the spec and of ``--test-cmd``: repo-local configuration written inside the calling
loop's own trust boundary — by the project's maintainers, or per change by the acceptance gate's
verifier, which is the normal case, since a spec targets the guard a change has just added and so
cannot be written in advance. The *level* is the same either way, and it is the bound
``hooks/guard_append_only.py`` documents for ``id_pattern`` and ``README.md`` states. Neither is
attacker input, neither may be derived from lower-trust material (an issue body, a PR comment), and
``--test-cmd`` is run through the shell so that real bindings (``unshare -rn -- sh -c '...'``) work
unchanged.

Spec format (JSON)::

    {
      "mutations": [
        {
          "id": "fail-open-on-read-error",
          "file": "src/yourpackage/module.py",
          "find": "return _deny(",
          "replace": "return _allow(",
          "kind": "fail-open",
          "expect": "killed"
        },
        {
          "id": "control-comment",
          "file": "src/yourpackage/module.py",
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

    python3 "${CLAUDE_PLUGIN_ROOT}/tools/mutate_verify.py" run \\
        --spec <spec.json> --test-cmd "<TEST_CMD>" --root "${CLAUDE_PROJECT_DIR}"

**The two paths are two different trees, and conflating them is the standing hazard here.** The
script lives in the installed plugin (``${CLAUDE_PLUGIN_ROOT}``); the tree it mutates is the
consuming repository (``${CLAUDE_PROJECT_DIR}``). Running it as ``python3 tools/mutate_verify.py
... --root .`` is correct only when developing this plugin itself, where the two coincide.

``--test-cmd`` is a **parameter**, never read from a config file: the engine that calls this stays
project-agnostic, and ``TEST_CMD`` is bound per project in ``loop.config.md``. ``--root`` likewise
comes from the caller.

``run_pass(..., snapshot_root=...)`` exists for tests. A caller must never point it inside the
repository being mutated: snapshots there would be visible to the test command, stageable by a
blanket ``git add``, and indistinguishable from the deliverables they exist to protect.

Platform note: ``--test-cmd`` is run through the shell, so a POSIX shell is assumed; the
``unshare`` example above is Linux-specific. These are the only platform assumptions in the file.
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
EXIT_UNATTRIBUTED = 5  # `--root` was not attributed as a tree distinct from `--parent-root`

_VALID_EXPECT = ("killed", "survived")
_DEFAULT_TIMEOUT = 1800
_OUTPUT_TAIL_CHARS = 4000  # enough to see a failure summary, not a whole verbose run
_BACKREFERENCE = re.compile(r"\\(?:\d|g<)")  # `\1`, `\g<name>` — see load_spec


class SpecError(Exception):
    """The spec is malformed, or names a target the harness refuses to touch."""


class MutationError(Exception):
    """A mutation could not be applied as specified — the AC5 loud failure."""


class RestoreError(Exception):
    """A file could not be given back byte-exact. The tree may still hold a mutation."""


class AttributionError(Exception):
    """`--parent-root` is unusable, so attribution cannot be decided at all.

    Its own class because it must fail **closed** and loudly rather than resolving to either
    verdict. A path that is not there is the specific trap: ``Path.resolve()`` does not raise on
    one, so a mistyped or missing ``--parent-root`` would resolve to something that never equals
    ``--root``, pass the comparison, and license a mutation pass over the parent's tree.
    """


class ConcurrentModification(Exception):
    """Someone else wrote to a target while it was mutated.

    Its own class because it is the one failure whose correct handling is to do **less**: the
    snapshot no longer describes the file, so restoring it would destroy work the harness never
    touched. Every other failure path restores; this one must not.
    """


def _target_is_intact(target: Path, expected_sha: str) -> bool:
    """True when the target still holds its pre-mutation bytes, so nothing is live."""
    try:
        return _sha256(target.read_bytes()) == expected_sha
    except OSError:
        return False


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
    output_tail: str = ""  # evidence for the verdict; a survivor with no output is hard to act on

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
        if "kind" in entry and not isinstance(entry["kind"], str):
            raise SpecError(
                "mutations[{}] 'kind' must be a string (it becomes a de-duplication key)".format(
                    index
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
            # The replacement is inserted literally (see `mutate_text`), so a backreference would
            # land as the characters `\1` rather than the captured text. That still changes bytes,
            # so it clears the no-op check, and it almost always breaks the file — which the suite
            # then reports as a KILL. A kill certified by a syntax error is a false negative
            # wearing a pass, so refuse the shape rather than let it be discovered as a mystery.
            if _BACKREFERENCE.search(entry["replace"]):
                raise SpecError(
                    "mutations[{}] 'replace' looks like a backreference ({!r}), but replacements "
                    "are inserted literally — it would land as those characters, not as the "
                    "captured text".format(index, entry["replace"])
                )

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


def restore_file(
    target: Path, snapshot: Path, expected_sha: str, mode: Optional[int] = None
) -> None:
    """Restore from the pre-mutation snapshot and verify the result is byte-exact.

    Never ``git checkout``/``git restore``: the index does not know about the surrounding work in
    progress, so restoring from it silently destroys uncommitted work the mutation never touched.
    """
    try:
        shutil.copyfile(str(snapshot), str(target))
        restored = target.read_bytes()
    except OSError as exc:
        raise RestoreError("could not restore {} from {}: {}".format(target, snapshot, exc)) from exc
    if mode is not None:
        # Only matters when the test command deleted the file: `copyfile` then creates a new inode
        # with default permissions, silently dropping +x from an executable target.
        try:
            target.chmod(mode)
        except OSError:
            pass
    actual = _sha256(restored)
    if actual != expected_sha:
        raise RestoreError(
            "restore of {} is not byte-exact (expected sha256 {}, got {})".format(
                target, expected_sha, actual
            )
        )


def run_tests(test_cmd: str, root: Path, timeout: int) -> Tuple[int, str]:
    """Run the project's test command; return its exit status and the tail of its output.

    A timeout is **not** silently counted as a kill. A mutation that hangs the suite is ambiguous,
    and claiming a kill we did not observe is the manufactured confidence this gate exists to
    prevent — so it is raised as a harness error for a human to read.

    The output tail is kept rather than discarded: this tool's entire product is a verdict, and a
    verdict with no evidence attached sends the reader off to re-run the suite by hand. Only the
    tail, because a verbose suite's full output is megabytes of nothing.

    `stdin` is closed. A test command that stops to prompt would otherwise inherit the harness's
    stdin and hang until the timeout, with a mutation live in the tree the whole while.
    """
    try:
        completed = subprocess.run(  # noqa: S602 - repo-local committed config, see module docstring
            test_cmd,
            shell=True,
            cwd=str(root),
            stdin=subprocess.DEVNULL,
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
    output = (completed.stdout or b"").decode("utf-8", "replace")
    return completed.returncode, output[-_OUTPUT_TAIL_CHARS:]


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
    restored: int = 0  # the engine's `- Restore:` ledger line names this number explicitly
    killed: int = 0
    survived: int = 0
    results: List[Result] = field(default_factory=list)
    survivor_groups: List[Dict[str, object]] = field(default_factory=list)
    control_proved: bool = False
    errors: List[str] = field(default_factory=list)
    snapshot_dir: Optional[str] = None
    # Carried so a pass that ran on the parent's own tree cannot be journalled as an ordinary one.
    # The flag is the only thing separating an authorized in-tree pass from the failure this
    # harness now refuses, so it travels with the verdict rather than being left to the caller.
    in_tree_authorized: bool = False

    def to_json(self) -> str:
        return json.dumps(
            {
                "baseline_exit": self.baseline_exit,
                "applied": self.applied,
                "restored": self.restored,
                "killed": self.killed,
                "survived": self.survived,
                "control_proved": self.control_proved,
                "in_tree_authorized": self.in_tree_authorized,
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
                        "output_tail": r.output_tail,
                    }
                    for r in self.results
                ],
                "errors": self.errors,
                "snapshot_dir": self.snapshot_dir,
            },
            indent=2,
            sort_keys=True,
        )


def attribution_refusal(
    root: Path,
    parent_root: Optional[Path],
    in_tree_authorized: bool = False,
) -> Optional[str]:
    """Return a refusal string when `root` is the parent's own tree, else ``None``.

    The interlock this harness was missing. A mutation pass is destructive by design, and until now
    ``--root`` was taken entirely on faith: nothing checked that the tree about to be broken was the
    throwaway copy rather than the tree holding the caller's uncommitted work.

    **Why the comparison is resolved-path equality and not containment.** A worktree the host
    materializes *inside* the repository — the layout the engine documents as typical — is a
    genuinely separate working tree whose ``git rev-parse --show-toplevel`` differs from the
    parent's. Containment would refuse it, and a guard that refuses the primary path would push
    every pass onto the in-tree escape, which is worse than no guard.

    **Known bound, stated rather than claimed away:** a ``--root`` pointing at a plain
    *subdirectory* of the parent shares the parent's toplevel and is **not** refused here.
    ``Path.resolve()`` cannot compute "is a distinct git working tree" from a path relationship, and
    this harness may not ask git (see the module docstring). That residual rests on the same
    trusted-caller bound as the spec itself.

    Raises `AttributionError` when the question cannot be decided — which fails closed, never open.
    """
    if parent_root is None:
        raise AttributionError(
            "--parent-root is required: with nothing to attribute --root against, an isolated copy "
            "cannot be told apart from the parent's own tree"
        )
    parent = Path(parent_root)
    if not parent.is_dir():
        raise AttributionError(
            "--parent-root {!r} is not an existing directory. Path.resolve() does not raise on a "
            "path that is not there, so a mistyped one would resolve to something that never "
            "equals --root and would pass this check silently. Refused instead.".format(
                str(parent_root)
            )
        )
    if not Path(root).is_dir():
        raise AttributionError("--root {!r} is not an existing directory".format(str(root)))
    if Path(root).resolve() != parent.resolve():
        return None
    if in_tree_authorized:
        return None
    return (
        "--root and --parent-root resolve to the SAME tree ({}), so nothing here is isolated. "
        "No mutation was applied and no test was run. A pass over the parent's tree breaks working "
        "code beside its uncommitted deliverables, and a green verdict from it would be UNPROVEN "
        "rather than clean. Re-materialize the isolated copy and re-run. If the tree genuinely "
        "cannot be isolated, that is the engine's escalated in-tree rung, which is the human's "
        "choice to make and not this harness's default.".format(Path(root).resolve())
    )


def run_pass(
    mutations: Sequence[Mutation],
    test_cmd: str,
    root: Path,
    parent_root: Optional[Path] = None,
    timeout: int = _DEFAULT_TIMEOUT,
    snapshot_root: Optional[Path] = None,
    in_tree_authorized: bool = False,
) -> Tuple[Report, int]:
    """Run a whole mutation pass. Returns the report and the exit code.

    One mutation is live at a time: apply, run, restore, then move on. Snapshots are taken **before**
    each mutation and deleted only when the whole pass completes cleanly.
    """
    # ATTRIBUTION FIRST — ahead of target resolution, ahead of the snapshot directory, ahead of the
    # baseline. A refusal that arrives after any of those has already touched something, and the
    # whole point of this interlock is that a pass over the parent's tree costs nothing because it
    # never starts. `attribution_refusal` raises when the question cannot be decided, which reaches
    # `main` as a harness error (exit 2) rather than resolving to either verdict.
    refusal = attribution_refusal(root, parent_root, in_tree_authorized)
    if refusal is not None:
        report = Report(baseline_exit=-1)
        report.errors.append(refusal)
        return report, EXIT_UNATTRIBUTED

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
    report = Report(
        baseline_exit=-1, snapshot_dir=str(snapshot_dir), in_tree_authorized=in_tree_authorized
    )

    def discard_snapshots() -> None:
        """Drop the snapshots once the tree is known-good.

        Retention is a *signal*, not bookkeeping: a retained directory means "a mutation may still
        be live". So it is cleared on every path this function controls where the tree was restored
        and verified, and kept only when a restore actually failed. A pass killed mid-run never
        reaches any of these paths, which is exactly the interrupted case recovery must catch.
        """
        shutil.rmtree(str(snapshot_dir), ignore_errors=True)
        if snapshot_dir.exists():
            # `ignore_errors` swallowed a real failure (a full or read-only TMPDIR, an NFS
            # silly-rename). Clearing the field anyway would invert the retention signal: the
            # directory survives on disk while the report says it is gone, so recovery would read a
            # clean tree as dirty. Keep the field and say so instead.
            report.errors.append(
                "could not remove the snapshot directory {} — it is stale, not evidence of a live "
                "mutation".format(snapshot_dir)
            )
            return
        report.snapshot_dir = None

    try:
        report.baseline_exit, baseline_output = run_tests(test_cmd, root, timeout)
    except MutationError as exc:
        report.errors.append(str(exc))
        discard_snapshots()
        return report, EXIT_HARNESS_ERROR
    if report.baseline_exit != 0:
        report.errors.append(
            "baseline is not green (exit {}) — every verdict below it would be meaningless, "
            "so none was taken. Tail of its output:\n{}".format(
                report.baseline_exit, baseline_output.strip() or "(no output)"
            )
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
        try:
            original_mode = target.stat().st_mode
        except OSError:
            original_mode = None

        # One handler for the whole mutate-run-restore body, catching **any** exception rather than
        # only the ones this module raises. An unexpected OSError (a read-only target, a full disk)
        # escaping to the process would surface as exit 1 — which means "survivors found" — so a
        # crash would read as a result. Fail closed instead, mirroring `hooks/guard_append_only.py`.
        try:
            original_seen = apply_mutation(mutation, target)
            # The file must be what we snapshotted a moment ago. If it is not, someone wrote to it
            # in between and the snapshot is already stale — restoring it would erase their work.
            if _sha256(original_seen) != expected_sha:
                raise ConcurrentModification(
                    "{} changed between the snapshot and the mutation".format(mutation.file)
                )
            report.applied += 1
            mutated_bytes = target.read_bytes()
            test_exit, test_output = run_tests(test_cmd, root, timeout)
            # The window that actually matters: a whole test run, minutes long, on a file in a live
            # working tree. If the bytes are no longer the ones we wrote, a developer (or the suite)
            # edited the file underneath us — so the snapshot no longer describes "before", and
            # copying it back would silently destroy uncommitted work. That is the exact outcome
            # this design refuses to reach via `git restore`; it must not reach it this way either.
            if target.read_bytes() != mutated_bytes:
                raise ConcurrentModification(
                    "{} was modified while the test command was running".format(mutation.file)
                )
            outcome = "killed" if test_exit != 0 else "survived"
            if outcome == "killed":
                report.killed += 1
            else:
                report.survived += 1
            report.results.append(
                Result(
                    mutation=mutation,
                    outcome=outcome,
                    applied=True,
                    test_exit=test_exit,
                    output_tail=test_output,
                )
            )
        except ConcurrentModification as exc:
            # Deliberately NOT restored: the tree holds both a live mutation and someone else's
            # edit, and only a human can separate them. Retain the snapshot — it is the safe repair
            # material — and say plainly what is where.
            report.errors.append(
                "{} — refusing to restore, because the snapshot no longer describes this file and "
                "writing it back would destroy that change. The mutation ({!r}: {!r} -> {!r}) is "
                "still live in the tree.".format(
                    exc, mutation.id, mutation.find, mutation.replace
                )
            )
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
                # A failed restore does not always mean a dirty tree. If the target still hashes to
                # its pre-mutation content — an unwritable file, say, where the mutation never
                # landed — then nothing is live and this is an ordinary harness error. Reserving
                # code 4 for a genuinely dirty tree is what keeps it worth reacting to.
                if _target_is_intact(target, expected_sha):
                    report.errors.append(
                        "the tree is intact: {} still matches its pre-mutation content".format(
                            target
                        )
                    )
                    discard_snapshots()
                    return report, EXIT_HARNESS_ERROR
                return report, EXIT_RESTORE_FAILED
            discard_snapshots()
            return report, EXIT_HARNESS_ERROR

        try:
            restore_file(target, snapshot, expected_sha, mode=original_mode)
            report.restored += 1
        except Exception as exc:  # noqa: BLE001 - the tree may still hold this mutation
            report.errors.append("{}: {}".format(type(exc).__name__, exc))
            return report, EXIT_RESTORE_FAILED

    # The whole tree was given back and every restore verified, so the snapshots have done their
    # job. Discarded HERE, immediately after the loop, rather than after the bookkeeping below: an
    # unexpected defect in that bookkeeping would otherwise leave a snapshot directory on disk with
    # a clean tree, which recovery would read as a restore failure that never happened.
    discard_snapshots()

    report.survivor_groups = dedupe_survivors(report.results)
    controls = [r for r in report.results if r.mutation.expect == "survived"]
    report.control_proved = bool(controls) and all(r.as_expected for r in controls)
    real_survivors = sum(int(g["count"]) for g in report.survivor_groups)

    # Order matters here, and two different questions about the controls are deliberately split.
    #
    # INTEGRITY first, because it gates every verdict including EXIT_SURVIVORS. A control that was
    # killed means the pipeline mis-classifies, and "survivors found" from a pipeline already shown
    # to mis-classify is an authoritative-sounding verdict with nothing behind it.
    if controls and not report.control_proved:
        report.errors.append(
            "a control mutation (expect=survived) was killed — the pipeline's classification cannot "
            "be trusted, so no verdict was taken from this pass"
        )
        return report, EXIT_HARNESS_ERROR
    # Then survivors. A survivor is self-proving: the pipeline just demonstrated it can report one,
    # which is the very capability a control exists to establish. So PRESENCE of a control gates
    # only the clean verdict below, never this one.
    if real_survivors:
        return report, EXIT_SURVIVORS
    if not controls:
        report.errors.append(
            "no control mutation (expect=survived) was declared, so nothing proved this pass can "
            "report a survivor at all — a green verdict must prove it can go red"
        )
        return report, EXIT_UNPROVEN
    # Every outcome now matches its expectation, as a consequence of the branches above rather than
    # of a further check. An explicit `if unexpected:` here would be unreachable, and an unreachable
    # guard reads as protection that is not there.
    return report, EXIT_CLEAN


def _render(report: Report, code: int) -> str:
    lines = [
        "baseline: exit {}".format(report.baseline_exit),
        "applied: {} (mutations that actually altered a file), restored: {}".format(
            report.applied, report.restored
        ),
        "killed: {}  survived: {}".format(report.killed, report.survived),
        "control proved the pipeline can report a survivor: {}".format(
            "yes" if report.control_proved else "NO"
        ),
    ]
    if report.in_tree_authorized:
        lines.append(
            "IN-TREE PASS, AUTHORIZED: --root was NOT isolated from --parent-root and ran anyway "
            "on --in-tree-authorized. That is the human's escalated rung, never this harness's "
            "default, and it is recorded here so the ledger cannot describe it as an ordinary pass."
        )
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
    run_parser.add_argument(
        "--parent-root",
        required=True,
        type=Path,
        help="the tree being PROTECTED — the orchestrator's own working tree. Required: a "
        "destructive pass must not take its blast radius on trust. Refused (exit 5) when it "
        "resolves to the same tree as --root.",
    )
    run_parser.add_argument(
        "--in-tree-authorized",
        action="store_true",
        help="proceed even though --root IS --parent-root. The engine's escalated in-tree rung, "
        "which a human chooses; it is never the remedy for an attribution refusal.",
    )
    run_parser.add_argument("--timeout", default=_DEFAULT_TIMEOUT, type=int, help="per-run seconds")
    run_parser.add_argument("--json", action="store_true", help="emit the report as JSON")

    args = parser.parse_args(argv)

    try:
        mutations = load_spec(args.spec)
        report, code = run_pass(
            mutations,
            args.test_cmd,
            args.root,
            parent_root=args.parent_root,
            timeout=args.timeout,
            in_tree_authorized=args.in_tree_authorized,
        )
    except (SpecError, MutationError, AttributionError) as exc:
        print("mutate_verify: {}".format(exc), file=sys.stderr)
        return EXIT_HARNESS_ERROR
    except Exception as exc:  # noqa: BLE001 - fail closed; a crash must never read as a result
        # Without this the exception would reach the interpreter, which exits 1 — and 1 is
        # EXIT_SURVIVORS. A traceback would silently become "the pass found survivors".
        print("mutate_verify: unexpected {}: {}".format(type(exc).__name__, exc), file=sys.stderr)
        return EXIT_HARNESS_ERROR

    if report.in_tree_authorized:
        # Also on stderr, because stdout is routinely piped or read as `--json`, and this is the one
        # line whose absence would let an in-tree pass be read as an ordinary isolated one.
        print(
            "mutate_verify: IN-TREE PASS — --root was not isolated from --parent-root and ran on "
            "--in-tree-authorized. Journal it as the escalated rung, not as an ordinary pass.",
            file=sys.stderr,
        )

    # Reporting is guarded too, and separately, because it fails for ordinary reasons: stdout piped
    # into `head` (BrokenPipeError), or an ASCII stdout encoding meeting a `find` string copied out
    # of a file full of em dashes — which is the *normal* case when the targets are prose. An
    # exception here would escape to the interpreter and exit 1, i.e. EXIT_SURVIVORS, turning a
    # printing failure into a verdict. The verdict `run_pass` reached is what gets returned, so a
    # dirty tree still reports 4 rather than being downgraded.
    try:
        print(report.to_json() if args.json else _render(report, code))
    except Exception as exc:  # noqa: BLE001 - the verdict survives a failure to announce it
        try:
            sys.stderr.buffer.write(
                "mutate_verify: could not write the report ({}: {}); the verdict below still "
                "stands.\n".format(type(exc).__name__, exc).encode("utf-8", "backslashreplace")
            )
            if report.snapshot_dir:
                # The one thing that must reach the operator even when reporting is broken.
                sys.stderr.buffer.write(
                    "mutate_verify: SNAPSHOTS RETAINED: {}\n".format(report.snapshot_dir).encode(
                        "utf-8", "backslashreplace"
                    )
                )
            sys.stderr.buffer.flush()
        except Exception:  # noqa: BLE001 - stderr is gone too; the exit code is all that is left
            pass
    return code


if __name__ == "__main__":
    sys.exit(main())
