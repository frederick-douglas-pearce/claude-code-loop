#!/usr/bin/env python3
"""Whole-tree cost: parent transcript + its subagent transcripts, priced together.

SCOUTING SCRIPT — no hand-checked sample. `test_tree_cost.py` covers only the
stratification and per-model pricing added by #207, not the billing arithmetic.
Every other script in this directory earned its tests by publishing a wrong number
first (see the README's six detection bugs). Output here motivates a build order; it
is not a finding, and nothing from it should be cited until it has been through the
two defences that have actually worked: hand-check a sample of matches, and
sanity-check the distribution against what the system can physically do.

Why it exists: Finding 11 notes that subagent work is unpriced -- no `isSidechain`
records in the parent, subagent transcripts living unopened in `<session>/subagents/`.
This sizes that gap. See `cost-model-design.md`.

Every record is priced by ITS OWN `message.model` (`stratum.PRICING`): a subagent's
model can differ from its parent's. Two models' costs are summed only in US dollars,
never in ratio units, because the models' base prices differ. A record whose model
has no PRICING entry REFUSES to price its whole session, which is named and excluded.
Zero-usage `<synthetic>` records are skipped, per `stratum.py`'s carve-out.

**Totals and shares are grouped by the parent's stratum** (`stratum.py`) and never
pooled across one; an unstratified session is excluded and named with its reason.
Every session prints its `stratum` line.

Known and NOT fixed here: this sums every record's usage with no `message.id`
dedupe, and prices 1-hour cache writes at the 5-minute rate. Both are #212's.

Only sessions that delegated at least once are reported -- a non-delegating session
has a subagent share of zero by construction and would deflate the aggregate. That
makes "delegating" a selection on behaviour, which is a real limit on the numbers.

Usage:
    python3 docs/research/tree_cost.py ~/.claude/projects/<slug> [<slug> ...]
"""
import json
import os
import pathlib
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stratum import UnknownModel, group_by_stratum, is_ignorable_synthetic, \
    label, session_strata, stratum_line, usd, weights_for  # noqa: E402


def bill(path):
    """-> (usd, records, refusal) for one transcript. `usd` is None when refused.

    Reads only the top-level usage fields. `usage.iterations` restates the same
    tokens per inference iteration; summing both would double-count.
    """
    total, records = 0.0, 0
    try:
        with open(path, errors="replace") as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(rec, dict):
                    continue
                msg = rec.get("message") or {}
                usage = msg.get("usage")
                if not usage or is_ignorable_synthetic(rec):
                    continue
                records += 1
                try:
                    total += usd(usage, weights_for(msg.get("model")))
                except UnknownModel as exc:
                    return None, records, "%s: %s" % (pathlib.Path(path).name, exc)
    except OSError as exc:
        return None, records, "unreadable %s: %s" % (pathlib.Path(path).name, exc)
    return total, records, None


def survey(root):
    """-> (rows, refused). A row is (name, records, parent_usd, n_subs, sub_usd,
    stratum). `refused` is [(name, stratum, reason)] for sessions that would not
    price."""
    rows, refused = [], []
    for parent in sorted(root.glob("*.jsonl")):
        sub_dir = root / parent.stem / "subagents"
        subs = sorted(sub_dir.glob("*.jsonl")) if sub_dir.is_dir() else []
        if not subs:
            continue
        stratum = session_strata(str(parent))
        parent_usd, parent_records, why = bill(parent)
        sub_usd = 0.0
        for s in subs:
            if why:
                break
            u, _, why = bill(s)
            sub_usd += u or 0.0
        if why:
            refused.append((parent.stem[:8], stratum, why))
            continue
        rows.append((parent.stem[:8], parent_records, parent_usd, len(subs), sub_usd,
                     stratum))
    return sorted(rows, key=lambda r: -(r[2] + r[4])), refused


def report(root, rows, refused=()):
    print(f"\n=== {root.name} ===")
    for r in rows:
        print(f"  {r[0]:9} {stratum_line(r[5])}")
    for name, stratum, why in refused:
        print(f"  {name:9} {stratum_line(stratum)}")
        print(f"  EXCLUDED {name}: price refused -- {why}")
    if not rows:
        print("  no priced delegating sessions")
        return
    groups, excluded = group_by_stratum(rows, key=lambda r: r[5])
    for r, why in excluded:
        print(f"  EXCLUDED {r[0]}: {why}")
    for key, grp in groups.items():
        report_stratum(key, grp)


def report_stratum(key, rows):
    """Totals and shares within ONE parent stratum. Units: US dollars."""
    print(f"\n### stratum {label(key)}")
    print(f"{'session':9} {'records':>8} {'parent $':>12} {'subs':>5} {'subagent $':>12} {'sub%':>7}")
    for name, records, pb, n_sub, sb, _ in rows:
        total = pb + sb
        share = sb / total * 100 if total else 0.0
        print(f"{name:9} {records:8d} {pb:12,.2f} {n_sub:5d} {sb:12,.2f} {share:6.1f}%")
    parent_total = sum(r[2] for r in rows)
    sub_total = sum(r[4] for r in rows)
    grand = parent_total + sub_total
    shares = sorted((r[4] / (r[2] + r[4])) for r in rows if r[2] + r[4])
    print(
        f"\n{len(rows)} delegating sessions | parent ${parent_total:,.2f} | "
        f"subagent ${sub_total:,.2f} | subagent share "
        + (f"{sub_total / grand * 100:.1f}%" if grand else "n/a")
    )
    if shares:
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
        report(root, *survey(root))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
