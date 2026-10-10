#!/usr/bin/env python3
"""Whole-tree cost: parent transcript + its subagent transcripts, priced together.

CITABLE since #133 (2026-10-09), through the two defences that have actually worked
in this directory:
  * **A hand-checked sample.** 20 of the 243 transcript files behind the 0.3.0
    before-baseline (seed 133; 2 parents, 18 subagents) were re-priced by a script
    sharing no code with `stratum.py`, from the per-MTok rates on Anthropic's model
    table. Every file agreed to the cent, turn count included
    (`before-side-2026-10-09.md`).
  * **Physical bounds, enforced.** `price_session` refuses any session holding a
    turn whose context or output no single API call could produce (`MAX_CONTEXT`,
    `MAX_OUTPUT`). It is a check on every run, not a one-off.
A change to the arithmetic or the dedupe voids the first: re-run the sample.

Why it exists: Finding 11 notes that subagent work is unpriced -- no `isSidechain`
records in the parent, subagent transcripts living unopened in `<session>/subagents/`.
This sizes that gap. See `cost-model-design.md`.

Every turn is priced by ITS OWN `message.model` (`stratum.PRICING`): a subagent's
model can differ from its parent's. Two models' costs are summed only in US dollars,
never in ratio units, because the models' base prices differ. A turn the spec cannot
price -- a model with no PRICING entry, unreadable usage, a cache split that
disagrees with its total, a pricing lever -- REFUSES to price its whole session,
which is named and excluded.

Turns follow the cost spec (#212, `stratum.price_records`), one transcript file at a
time: one turn per `message.id`, priced once on its max-`output_tokens` line, with
1-hour cache writes at 2x; API-error and ignorable `<synthetic>` lines are excluded.
Lines with no id are counted per session, and so are ids seen in more than one file
of the same session -- 0 on clean data, since an id names one API call, and the
count is what makes that assumption evidence rather than belief.

**Totals and shares are grouped by the parent's stratum** (`stratum.py`) and never
pooled across one; an unstratified session is excluded and named with its reason.
Every session prints its `stratum` line.

Only sessions that delegated at least once are reported -- a non-delegating session
has a subagent share of zero by construction and would deflate the aggregate. That
makes "delegating" a selection on behaviour, which is a real limit on the numbers.

Usage:
    python3 docs/research/tree_cost.py ~/.claude/projects/<slug> [<slug> ...]
    python3 docs/research/tree_cost.py --sessions <session.jsonl> [...]   # named sessions,
        delegating or not: the per-issue bill, parent and subagents shown separately
"""
import json
import os
import pathlib
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stratum import Unpriced, _tok, group_by_stratum, label, price_records, \
    session_strata, stratum_line  # noqa: E402


def _records(path):
    with open(path, errors="replace") as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if isinstance(rec, dict):
                yield rec


def bill(path):
    """-> (PricedRecords, refusal) for one transcript file; PricedRecords is None when
    refused. Only the top-level usage is read: `usage.iterations` restates the same
    tokens per inference iteration, and `toolUseResult.usage` is one turn's snapshot
    with no model -- pricing either would double-count."""
    name = pathlib.Path(path).name
    try:
        return price_records(list(_records(path))), None
    except Unpriced as exc:
        return None, "%s: %s" % (name, exc)
    except OSError as exc:
        return None, "unreadable %s: %s" % (name, exc)


# Physical bounds no API turn can exceed: the widest context window (input + cache
# read + cache write) and the largest `max_tokens` of any model in `stratum.PRICING`
# -- 1M and 128K (Anthropic's model table, as cached 2026-10-06; Haiku 4.5's window
# is 200K, inside both). Deliberately the WIDEST across models: the check catches
# a turn that cannot exist (a dedupe or parse defect summing several calls into
# one), never an unusual but real one. Raise them when a priced model exceeds them.
MAX_CONTEXT = 1_000_000
MAX_OUTPUT = 128_000


def physical_problems(priced, name=""):
    """-> [str], one per priced turn whose usage no single API call could produce."""
    out = []
    for t in priced.turns:
        ctx = sum(_tok(t.usage, f) for f in
                  ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
        o = _tok(t.usage, "output_tokens")
        if ctx > MAX_CONTEXT or o > MAX_OUTPUT:
            out.append("%s turn %s: context %d, output %d" % (name, t.key, ctx, o))
    return out


def price_session(parent):
    """Price one session: its parent transcript and every subagent transcript.

    -> dict(name, parent_usd, sub_usd, subs, turns, stratum, refused). Unlike
    `survey` this prices a session that delegated nothing (its subagent bill is a
    measured 0, not a selection). A session refuses -- `refused` names why, and both
    bills are None -- when any file will not price under the spec, or any turn is
    outside the physical bounds above: a figure built on an impossible turn is a
    defect, not a cost."""
    parent = pathlib.Path(parent)
    sub_dir = parent.parent / parent.stem / "subagents"
    subs = sorted(sub_dir.glob("*.jsonl")) if sub_dir.is_dir() else []
    row = {"name": parent.stem[:8], "subs": len(subs), "parent_usd": None,
           "sub_usd": None, "turns": None, "refused": None,
           "stratum": session_strata(str(parent))}
    files = []
    for f in [parent] + subs:
        priced, why = bill(f)
        if why:
            row["refused"] = why
            return row
        files.append(priced)
    bad = [p for f, priced in zip([parent] + subs, files)
           for p in physical_problems(priced, f.name)]
    if bad:
        row["refused"] = "physically impossible usage: " + "; ".join(bad[:3])
        return row
    row.update(parent_usd=files[0].usd, sub_usd=sum(f.usd for f in files[1:]),
               turns=len(files[0].turns))
    return row


def report_sessions(paths):
    """`--sessions`: one line per named session, then totals over the priced ones.
    Pools whatever it is given, so pass one repo's sessions of one stratum."""
    rows = [price_session(p) for p in paths]
    print(f"{'session':9} {'turns':>6} {'parent $':>10} {'subs':>5} {'subagent $':>11} "
          f"{'total $':>10}  stratum")
    for r in rows:
        if r["refused"]:
            print(f"{r['name']:9} REFUSED -- {r['refused']}")
            continue
        print(f"{r['name']:9} {r['turns']:6d} {r['parent_usd']:10.2f} {r['subs']:5d} "
              f"{r['sub_usd']:11.2f} {r['parent_usd'] + r['sub_usd']:10.2f}  "
              f"{label(r['stratum'].parent) if r['stratum'].stratified else 'UNSTRATIFIED'}")
    ok = [r for r in rows if not r["refused"]]
    if ok:
        pt, st = sum(r["parent_usd"] for r in ok), sum(r["sub_usd"] for r in ok)
        print(f"# {len(ok)} priced, {len(rows) - len(ok)} refused | parent ${pt:,.2f} | "
              f"subagent ${st:,.2f} | total ${pt + st:,.2f}")
    else:
        print(f"# 0 priced, {len(rows)} refused")
    return rows


def survey(root, counts=None):
    """-> (rows, refused). A row is (name, turns, parent_usd, n_subs, sub_usd,
    stratum), `turns` being the parent's. `refused` is [(name, stratum, reason)] for
    sessions that would not price. Pass a dict as `counts` to collect, per session,
    `no_id` (lines with no id, all files) and `cross_file_ids`."""
    rows, refused = [], []
    for parent in sorted(root.glob("*.jsonl")):
        sub_dir = root / parent.stem / "subagents"
        subs = sorted(sub_dir.glob("*.jsonl")) if sub_dir.is_dir() else []
        if not subs:
            continue
        name = parent.stem[:8]
        stratum = session_strata(str(parent))
        priced, why = bill(parent)
        files = [priced]
        for s in subs:
            if why:
                break
            p, why = bill(s)
            files.append(p)
        if why:
            refused.append((name, stratum, why))
            continue
        if counts is not None:
            seen = {}
            for f in files:
                for key in {t.key for t in f.turns if isinstance(t.key, str)}:
                    seen[key] = seen.get(key, 0) + 1
            counts[name] = {"no_id": sum(f.counts.no_id for f in files),
                            "cross_file_ids": sum(1 for n in seen.values() if n > 1)}
        rows.append((name, len(priced.turns), priced.usd, len(subs),
                     sum(f.usd for f in files[1:]), stratum))
    return sorted(rows, key=lambda r: -(r[2] + r[4])), refused


def report(root, rows, refused=(), counts=None):
    print(f"\n=== {root.name} ===")
    counts = counts or {}
    for r in rows:
        c = counts.get(r[0])
        extra = (f"  (no_id={c['no_id']} ids in >1 file={c['cross_file_ids']})"
                 if c else "")
        print(f"  {r[0]:9} {stratum_line(r[5])}{extra}")
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
    print(f"{'session':9} {'turns':>8} {'parent $':>12} {'subs':>5} {'subagent $':>12} {'sub%':>7}")
    for name, turns, pb, n_sub, sb, _ in rows:
        total = pb + sb
        share = sb / total * 100 if total else 0.0
        print(f"{name:9} {turns:8d} {pb:12,.2f} {n_sub:5d} {sb:12,.2f} {share:6.1f}%")
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
    if argv[0] == "--sessions":
        report_sessions(argv[1:])
        return 0
    for arg in argv:
        root = pathlib.Path(arg).expanduser()
        if not root.is_dir():
            print(f"not a directory: {root}", file=sys.stderr)
            return 2
        counts = {}
        rows, refused = survey(root, counts)
        report(root, rows, refused, counts)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
