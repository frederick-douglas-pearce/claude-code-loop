#!/usr/bin/env python3
"""Whole-tree cost: parent transcript + its subagent transcripts, priced together.

SCOUTING SCRIPT — no fixture tests, no hand-checked sample. Every other script in
this directory earned its tests by publishing a wrong number first (see the README's
six detection bugs). Output here motivates a build order; it is not a finding, and
nothing from it should be cited until it has been through the two defences that have
actually worked: hand-check a sample of matches, and sanity-check the distribution
against what the system can physically do.

Why it exists: Finding 11 notes that subagent work is unpriced -- no `isSidechain`
records in the parent, subagent transcripts living unopened in `<session>/subagents/`.
This sizes that gap. See `cost-model-design.md`.

Billing follows the README's pinned schedule: fresh 1x, cache-write 1.25x,
cache-read 0.1x, output 5x.

Only sessions that delegated at least once are reported -- a non-delegating session
has a subagent share of zero by construction and would deflate the aggregate. That
makes "delegating" a selection on behaviour, which is a real limit on the numbers.

Usage:
    python3 docs/research/tree_cost.py ~/.claude/projects/<slug> [<slug> ...]
"""
import json
import pathlib
import sys

FRESH, CACHE_WRITE, CACHE_READ, OUTPUT = 1.0, 1.25, 0.1, 5.0


def bill(path):
    """Billable-equivalent tokens and assistant-record count for one transcript.

    Reads only the top-level usage fields. `usage.iterations` restates the same
    tokens per inference iteration; summing both would double-count.
    """
    totals = {"fresh": 0, "write": 0, "read": 0, "out": 0}
    records = 0
    try:
        with open(path, errors="replace") as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                usage = (rec.get("message") or {}).get("usage")
                if not usage:
                    continue
                records += 1
                totals["fresh"] += usage.get("input_tokens", 0)
                totals["write"] += usage.get("cache_creation_input_tokens", 0)
                totals["read"] += usage.get("cache_read_input_tokens", 0)
                totals["out"] += usage.get("output_tokens", 0)
    except OSError as exc:
        print(f"  ! unreadable, skipped: {path.name}: {exc}", file=sys.stderr)
        return 0.0, 0
    return (
        FRESH * totals["fresh"]
        + CACHE_WRITE * totals["write"]
        + CACHE_READ * totals["read"]
        + OUTPUT * totals["out"]
    ), records


def survey(root):
    rows = []
    for parent in sorted(root.glob("*.jsonl")):
        sub_dir = root / parent.stem / "subagents"
        subs = sorted(sub_dir.glob("*.jsonl")) if sub_dir.is_dir() else []
        if not subs:
            continue
        parent_bill, parent_records = bill(parent)
        sub_bill = sum(bill(s)[0] for s in subs)
        rows.append((parent.stem[:8], parent_records, parent_bill, len(subs), sub_bill))
    return sorted(rows, key=lambda r: -(r[2] + r[4]))


def report(root, rows):
    print(f"\n=== {root.name} ===")
    if not rows:
        print("  no delegating sessions")
        return
    print(f"{'session':9} {'records':>8} {'parent':>14} {'subs':>5} {'subagent':>14} {'sub%':>7}")
    for name, records, pb, n_sub, sb in rows:
        total = pb + sb
        share = sb / total * 100 if total else 0.0
        print(f"{name:9} {records:8d} {pb:14,.0f} {n_sub:5d} {sb:14,.0f} {share:6.1f}%")
    parent_total = sum(r[2] for r in rows)
    sub_total = sum(r[4] for r in rows)
    grand = parent_total + sub_total
    shares = sorted((r[4] / (r[2] + r[4])) for r in rows if r[2] + r[4])
    print(
        f"\n{len(rows)} delegating sessions | parent {parent_total:,.0f} | "
        f"subagent {sub_total:,.0f} | subagent share {sub_total / grand * 100:.1f}%"
    )
    print(
        f"per-session subagent share: median {shares[len(shares) // 2] * 100:.1f}%  "
        f"min {shares[0] * 100:.1f}%  max {shares[-1] * 100:.1f}%"
    )


def main(argv):
    if not argv:
        print(__doc__, file=sys.stderr)
        return 2
    for arg in argv:
        root = pathlib.Path(arg).expanduser()
        if not root.is_dir():
            print(f"not a directory: {root}", file=sys.stderr)
            return 2
        report(root, survey(root))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
