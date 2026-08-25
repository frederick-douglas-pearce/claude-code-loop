#!/usr/bin/env python3
"""Aggregate `- Budget:` lines from one or more dev-loop ledgers.

Usage:
    python3 docs/research/budget_stats.py <LEDGER_ROOT> [<LEDGER_ROOT> ...]

where each LEDGER_ROOT is a directory containing per-run subdirectories with a
`progress.md` (e.g. `~/proj/.claude/loop`). Prints one row per issue -- the
journal entry with the highest `subagent-runs`, which is the closest thing the
ledger has to a final cost -- plus per-ledger aggregates.

Stdlib only, deliberately: it runs wherever the guard hook runs.

Caveats, because the numbers are softer than they look:
  * `subagent-runs` is self-reported by the orchestrator and its blind spot is
    parent-thread burn (loop-engine.md -> progress.md -> the Budget line).
  * An issue with several journal entries was re-entered; the last entry's
    counts are cumulative for that issue, not per-entry.
  * Rows still in flight have no terminal Budget line and are absent here.

Engine-era attribution (`--era`) is the subtle part. All consumers moved 0.0.1 ->
0.2.0 on 2026-08-21, and the loop executes the INSTALLED plugin, so that date
splits a ledger in two. Two ways to detect it, and they disagree:

  * by DATE of the journal entry;
  * by MARKER -- 0.2.0-only vocabulary (`in-acceptance`, `post-gate-survivors`,
    `mutation-survivors`, `step 10`) appearing in the entry.

They agree exactly on every consumer that does not author the engine. They
disagree on 22 `claude-code-loop` rows, all in one direction, because that repo
WRITES the 0.2.0 vocabulary in its ledger while still running the 0.0.1 engine.
So: marker is the better signal for ordinary consumers, date is the only usable
one for the plugin repo itself. `--era` prints both and flags the disagreement
rather than picking for you.
"""
import glob
import os
import re
import statistics
import sys

BUDGET = re.compile(r"^- Budget:", re.M)
ISSUE = re.compile(r"#(\d+)")
ROUTE = re.compile(r"\((code|docs|research|stub-defer)\)")
RUNS = re.compile(r"subagent-runs[=≈](\d+)")
GATE = re.compile(r"(architect|code-review|ac-verify)=(\d+)")
SURVIVORS = re.compile(r"post-gate-survivors=([~\d]+)")
DATE = re.compile(r"(\d{4}-\d{2}-\d{2})")
# 0.2.0-only vocabulary: the step reorder, the in-acceptance status, the Class B
# mutation pass and its post-gate slot. See the module docstring on why this is
# unreliable in the repo that authors the engine.
MARKER = re.compile(r"in-acceptance|post-gate-survivors|mutation-survivors|step 10")
REINSTALL = "2026-08-21"


def parse(ledger_root):
    """Yield one dict per `- Budget:` line found under ledger_root."""
    pattern = os.path.join(ledger_root, "*", "progress.md")
    for path in sorted(glob.glob(pattern)):
        run = os.path.basename(os.path.dirname(path))
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().split("\n")
        # Split into iteration blocks on `## ` headers so a marker is scoped to
        # the iteration that wrote it, not to the whole file.
        bounds = [i for i, l in enumerate(lines) if l.startswith("## ")] + [len(lines)]
        for a, b in zip(bounds, bounds[1:]):
            block = "\n".join(lines[a:b])
            if not BUDGET.search(block):
                continue
            header = lines[a]
            issue = ISSUE.search(header)
            route = ROUTE.search(header)
            date = DATE.search(header)
            runs = RUNS.search(block)
            gates = {k: int(v) for k, v in GATE.findall(block)}
            surv = SURVIVORS.search(block)
            yield {
                "run": run,
                "issue": issue.group(1) if issue else "?",
                "route": route.group(1) if route else "?",
                "date": date.group(1) if date else "?",
                "runs": int(runs.group(1)) if runs else None,
                "gates": gates,
                "rounds": sum(gates.values()) if gates else None,
                "survivors": surv.group(1) if surv else "",
                "marker": bool(MARKER.search(block)),
            }


def summarize(label, rows):
    entries = {}
    peak = {}
    for row in rows:
        entries[row["issue"]] = entries.get(row["issue"], 0) + 1
        if row["runs"] is None:
            continue
        if row["issue"] not in peak or row["runs"] > peak[row["issue"]]["runs"]:
            peak[row["issue"]] = row
    if not peak:
        print(f"{label}: no Budget lines found")
        return
    print(f"\n### {label}")
    print(f"{'issue':>6} {'route':<9} {'runs':>4} {'arch':>4} {'rev':>4} "
          f"{'ac':>3} {'rounds':>6} {'surv':>5} {'entries':>7}")
    for issue in sorted(peak, key=lambda k: -peak[k]["runs"]):
        r = peak[issue]
        g = r["gates"]
        print(f"{issue:>6} {r['route']:<9} {r['runs']:>4} "
              f"{g.get('architect', '-'):>4} {g.get('code-review', '-'):>4} "
              f"{g.get('ac-verify', '-'):>3} "
              f"{r['rounds'] if r['rounds'] is not None else '-':>6} "
              f"{r['survivors'] or '-':>5} {entries[issue]:>7}")
    runs = [r["runs"] for r in peak.values()]
    rounds = [r["rounds"] for r in peak.values() if r["rounds"]]
    ent = [entries[i] for i in peak]
    print(f"  n={len(runs)}  subagent-runs median={statistics.median(runs)} "
          f"mean={sum(runs) / len(runs):.1f} max={max(runs)}")
    print(f"  gate-rounds median={statistics.median(rounds)} max={max(rounds)}  "
          f"journal-entries/issue mean={sum(ent) / len(ent):.1f} max={max(ent)}")


def summarize_era(label, rows):
    """Split one ledger by engine era, both ways, and flag the disagreement."""
    peak = {}
    for row in rows:
        if row["runs"] is None:
            continue
        if row["issue"] not in peak or row["runs"] > peak[row["issue"]]["runs"]:
            peak[row["issue"]] = row
    if not peak:
        return
    print(f"\n### {label} — by engine era")
    for method in ("marker", "date"):
        for era in (False, True):
            sel = [r for r in peak.values()
                   if (r["marker"] if method == "marker"
                       else r["date"] >= REINSTALL) == era]
            if not sel:
                continue
            runs = [r["runs"] for r in sel]
            rounds = [r["rounds"] for r in sel if r["rounds"]]
            dates = sorted(r["date"] for r in sel)
            print(f"  {method:<6} {'0.2.0' if era else '0.0.1'}  n={len(runs):<3} "
                  f"runs median={statistics.median(runs):<5} max={max(runs):<4} "
                  f"rounds median={statistics.median(rounds) if rounds else '-':<5} "
                  f"{dates[0]}..{dates[-1]}")
    split = [r for r in peak.values()
             if r["marker"] != (r["date"] >= REINSTALL)]
    if split:
        print(f"  !! {len(split)}/{len(peak)} rows classified differently by the two "
              f"methods — see the module docstring before trusting either")


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("-")]
    era = "--era" in argv
    if not args:
        print(__doc__)
        return 1
    for root in args:
        rows = list(parse(root))
        summarize(root, rows)
        if era:
            summarize_era(root, rows)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
