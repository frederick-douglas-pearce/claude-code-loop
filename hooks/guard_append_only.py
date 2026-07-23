#!/usr/bin/env python3
"""PreToolUse hook: protect append-only logs from entry-dropping full-file Writes.

Part of the `dev-loop` Claude Code plugin. Receives the PreToolUse event JSON on
stdin. For a `Write` targeting a file the *consuming project* has registered as
append-only, it compares the set of entry IDs already on disk against the set in
the proposed `content`. If the write would drop any existing entry, the call is
denied.

Background: an append-only log (e.g. a decision log) can be clobbered by an agent
whose `Write` tool does full-file replacement -- an agent intending to append one
entry replaces the entire file, silently dropping every prior entry. This hook is
a durable, agent-agnostic guard against that specific data-loss mode.

## Per-project configuration (the seam)

Which files are protected -- and the regex that identifies each file's entry IDs
-- is NOT hardcoded here; it is read from a per-project sidecar:

    ${CLAUDE_PROJECT_DIR}/.claude/loop.append-guard.json

a JSON array of objects, each:

    [
      {
        "suffix": ".claude/specs/decisions.md",
        "id_pattern": "^##\\s+(D\\d+(?:-[A-Za-z0-9]+)?)"
      }
    ]

- `suffix`     -- path suffix, matched on a path-component boundary so an
                  unrelated file that merely ends in the same string is not
                  caught.
- `id_pattern` -- an anchored, MULTILINE regex whose first capture group is the
                  entry ID whose *existence* must survive a write. Body edits
                  that keep every ID are allowed; only dropping an ID is denied.
                  Note JSON escaping: a `\\s` in the regex is written `\\\\s` in
                  the JSON string.

The `dev-loop` `/init-loop` command generates this sidecar; see the plugin docs.
The `id_pattern` is compiled from repo-local, trusted config (same trust level as
a Makefile or a git hook) -- it is not attacker-controlled, so the compile is not
sandboxed; a bad pattern degrades to no-protection-with-a-warning, never a crash.

## Fail posture (deliberate asymmetry)

- An unparseable *hook event* on stdin fails CLOSED (deny, exit 2): we cannot
  confirm the write is safe.
- A *missing* project sidecar fails OPEN and SILENT: an installed plugin must be
  a no-op until the consuming project opts in.
- A *malformed* sidecar (bad JSON / bad shape / uncompilable regex) fails OPEN
  but LOUD (warns on stderr): a project that tried to configure protection and
  typo'd should not silently get zero protection.

## Scope and bypass surface (deliberately bounded)

- Guards the `Write` tool only. `Edit` is surgical (it cannot easily drop the
  whole file) and simulating its result to detect drops is fragile, so it is not
  guarded.
- It does NOT cover `Bash` redirection (`cat > file`, `tee`, `sed -i`), which an
  agent with Bash could use to clobber the file. This hook therefore protects
  *entry existence against full-file Writes*, not body content, and is not an
  absolute "any tool" guarantee.

Emits a JSON decision on stdout and exits 0 (the modern pattern); exit 2 + stderr
is the fail-closed fallback for an unparseable event.

The hook logic is stdlib-only with no shell dependencies. Note the manifest
(`hooks/hooks.json`) launches it via `python3`, which assumes a POSIX
environment where that name is on PATH (the loop is a bash/git/`gh` workflow);
on Windows the launcher, not this script, is the portability limit.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path, PurePath
from typing import Any

# Where each consuming project declares which files to protect (relative to
# ${CLAUDE_PROJECT_DIR}). Kept out of the gitignored ledger dir so it is a
# committed, reviewable part of the repo's config.
SIDECAR_RELPATH = ".claude/loop.append-guard.json"

DENY_REASON = (
    "Blocked by the dev-loop append-only guard hook. "
    "This Write would drop one or more existing entries from an append-only "
    "log, which is a data-loss risk. The guard protects entry existence (the "
    "heading IDs), not body text -- editing the body of an existing entry is "
    "fine as long as no entry heading is removed. To add an entry, append to "
    "the file (read the current content and write it back with the new entry "
    "appended, or use Edit), preserving every existing entry heading."
)


def normalize(path_str: str) -> str:
    """Return a forward-slash path string for suffix matching."""
    return PurePath(path_str).as_posix()


def warn(message: str) -> None:
    """Emit a non-fatal warning to stderr (the fail-open-but-loud path)."""
    print(f"guard_append_only: {message}", file=sys.stderr)


def load_registry(project_dir: str | None) -> list[tuple[str, re.Pattern[str]]]:
    """Load the per-project append-only registry from the sidecar.

    Returns a list of (normalized-suffix, compiled-pattern). Fail-open:
    - ``project_dir`` unset/empty or sidecar absent -> ``[]`` (silent: an
      unconfigured project is a deliberate no-op).
    - sidecar present but malformed (unreadable / bad JSON / not a list / an
      entry with no valid ``suffix``/``id_pattern`` / an uncompilable regex) ->
      the offending entry is skipped with a stderr warning, so a typo'd config
      never silently disables protection without a signal.
    """
    if not project_dir:
        return []
    sidecar = Path(project_dir) / SIDECAR_RELPATH
    try:
        raw = sidecar.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []  # unconfigured project: silent no-op
    except (OSError, UnicodeDecodeError) as e:
        warn(f"could not read {sidecar}: {e}; allowing writes (no protection)")
        return []

    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError) as e:
        warn(f"invalid JSON in {sidecar}: {e}; allowing writes (no protection)")
        return []

    if not isinstance(data, list):
        warn(f"{sidecar} must be a JSON array; allowing writes (no protection)")
        return []

    registry: list[tuple[str, re.Pattern[str]]] = []
    for i, entry in enumerate(data):
        if not isinstance(entry, dict):
            warn(f"{sidecar} entry {i} is not an object; skipping")
            continue
        suffix = entry.get("suffix")
        pattern_src = entry.get("id_pattern")
        if not isinstance(suffix, str) or not suffix:
            warn(f"{sidecar} entry {i} has no valid 'suffix'; skipping")
            continue
        if not isinstance(pattern_src, str) or not pattern_src:
            warn(f"{sidecar} entry {i} has no valid 'id_pattern'; skipping")
            continue
        try:
            pattern = re.compile(pattern_src, re.MULTILINE)
        except re.error as e:
            warn(f"{sidecar} entry {i} id_pattern is not a valid regex: {e}; skipping")
            continue
        # The contract is "the first capture group is the entry ID". Enforce it:
        # a 0-group pattern would capture whole heading lines (ID + prose); a
        # >=2-group pattern makes re.findall return tuples, which downstream ID
        # comparison cannot join -- a latent crash that, uncaught, would fail the
        # guard OPEN. Reject anything but exactly one group, warn-and-skip.
        if pattern.groups != 1:
            warn(
                f"{sidecar} entry {i} id_pattern must have exactly one capture "
                f"group (the entry ID); found {pattern.groups}; skipping"
            )
            continue
        registry.append((normalize(suffix), pattern))
    return registry


def match_registered_file(
    path_str: str, registry: list[tuple[str, re.Pattern[str]]]
) -> re.Pattern[str] | None:
    """Return the ID pattern for a registered append-only file, else None."""
    if not path_str:
        return None
    normalized = normalize(path_str)
    for suffix, pattern in registry:
        # Require a path-component boundary so an unrelated file whose tail
        # merely ends in the suffix string (e.g. `.../vendor.claude/specs/
        # decisions.md`) is not mistaken for the protected log.
        if normalized == suffix or normalized.endswith("/" + suffix):
            return pattern
    return None


def extract_ids(text: str, pattern: re.Pattern[str]) -> set[str]:
    """Extract the set of entry IDs from text using the registered pattern."""
    return set(pattern.findall(text))


def evaluate(
    existing_content: str, proposed_content: str, pattern: re.Pattern[str]
) -> tuple[bool, str]:
    """Decide whether a write should be blocked. Pure (no I/O).

    Returns (blocked, reason). Blocks when any ID present in the existing
    content is absent from the proposed content.
    """
    existing_ids = extract_ids(existing_content, pattern)
    if not existing_ids:
        # Nothing to protect yet (file exists but has no recognized entries).
        return False, ""
    proposed_ids = extract_ids(proposed_content, pattern)
    missing = sorted(existing_ids - proposed_ids)
    if missing:
        return True, f"{DENY_REASON} (would drop: {', '.join(missing)})"
    return False, ""


def check(
    event: dict[str, Any],
    registry: list[tuple[str, re.Pattern[str]]] | None = None,
) -> tuple[bool, str]:
    """Inspect a PreToolUse event; return (blocked, reason).

    ``registry`` is injectable for testing; in production it is loaded from the
    per-project sidecar located via ``$CLAUDE_PROJECT_DIR``.
    """
    if event.get("tool_name", "") != "Write":
        return False, ""

    if registry is None:
        registry = load_registry(os.environ.get("CLAUDE_PROJECT_DIR"))
    if not registry:
        return False, ""

    tool_input = event.get("tool_input") or {}
    path = tool_input.get("file_path") or ""
    pattern = match_registered_file(path, registry)
    if pattern is None:
        return False, ""

    proposed_content = tool_input.get("content") or ""

    try:
        existing_content = Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        # New file: there is nothing to drop.
        return False, ""
    except (OSError, UnicodeDecodeError) as e:
        # A real read error on an existing protected file means we cannot
        # verify the write is safe. Fail closed -- deny rather than risk a
        # silent clobber. (Such errors on a local file are vanishingly rare.)
        return True, (
            f"{DENY_REASON} (could not read the existing file to verify no "
            f"entries are dropped: {e})"
        )

    return evaluate(existing_content, proposed_content, pattern)


def emit_decision(decision: str, reason: str) -> None:
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": reason,
        }
    }
    sys.stdout.write(json.dumps(payload))


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError) as e:
        # Fail closed: if we can't parse the event we can't confirm the write
        # is safe, so deny rather than allow through a malformed event.
        print(
            f"guard_append_only: failed to parse hook event JSON, "
            f"denying by default: {e}",
            file=sys.stderr,
        )
        return 2

    try:
        blocked, reason = check(event)
    except Exception as e:  # noqa: BLE001 -- fail closed on ANY unexpected error
        # A guard against data loss must never let an internal error silently
        # allow the write. Deny with the generic reason so the user sees a
        # deliberate block rather than a non-blocking hook crash (exit 1).
        print(
            f"guard_append_only: internal error while evaluating the write, "
            f"denying by default: {e}",
            file=sys.stderr,
        )
        emit_decision("deny", DENY_REASON)
        return 0

    if blocked:
        emit_decision("deny", reason)
    return 0


if __name__ == "__main__":
    sys.exit(main())
