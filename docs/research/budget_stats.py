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

Engine-era attribution (`--era`) is the subtle part, and it is no longer a
two-era problem. The loop executes the INSTALLED plugin, so a ledger is split by
the dates that repo re-installed on. Two ways to detect it, and they disagree:

  * by DATE of the journal entry, against `ERAS` below;
  * by MARKER -- vocabulary that FIRST APPEARS in an era and persists after it,
    so a match is a LOWER BOUND (">=0.2.0"), never an exact era.

They agree exactly on every consumer that does not author the engine. They
disagree on 22 `claude-code-loop` rows, all in one direction, because that repo
WRITES an era's vocabulary in its ledger while still running the previous engine.
So: marker is the better signal for ordinary consumers, date is the only usable
one for the plugin repo itself. `--era` prints both and flags the disagreement
rather than picking for you.

THREE THINGS THAT MAKE THIS EASY TO GET WRONG, all learned the hard way:

  * **Not every release is marker-detectable.** 0.2.1 changed how the engine is
    READ and writes no new ledger vocabulary, so no marker can separate it from
    0.2.0. It is date-only, and the output says so rather than silently folding
    it into 0.2.0.
  * **Date alone over-advances the controls.** `agentfluent` and
    `claude-code-sessions` are deliberately held on 0.2.0 for the DiD in
    `cost-model-design.md`. A pure date rule would march them through 0.2.1 and
    0.3.0 and quietly destroy the control arm -- the untreated group would be
    coded as treated. So the date-derived era is CAPPED at the version that repo
    actually has installed, read from installed_plugins.json.
  * **A hardcoded era list goes stale at every release.** This module read
    `REINSTALL = "2026-08-21"` and knew only 0.0.1 vs 0.2.0, so from 2026-08-26
    every 0.2.1 row and from 2026-09-12 every 0.3.0 row attributed to "0.2.0".
    Adding a release means adding a row to `ERAS` -- if you are reading this
    after a release that is not listed, that is the bug.

    WHY THE DATES ARE NOT DERIVED, since that is the obvious objection.
    `engine_cost.py` derives engine SIZES from the plugin cache and keeps its
    table only as a fallback for evicted versions. The same trick does not work
    here: installed_plugins.json records each repo's CURRENT version and when it
    last changed, not the history of installs, so the boundary dates for eras a
    repo has already moved past are not recoverable from any live source. The
    list is therefore hand-maintained by necessity -- which is why an installed
    version missing from it RAISES rather than degrading quietly. That is the
    one mechanical staleness signal available, so it is loud on purpose.
"""
import glob
import json
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
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# Engine eras in release order: (version, first install date, first-appearing
# vocabulary). A marker persists into later eras, so matching one means "this era
# OR LATER" -- see the docstring. `None` means the release is not
# marker-detectable and can only be separated by date.
ERAS = [
    ("0.0.1", None, None),
    ("0.2.0", "2026-08-21",
     re.compile(r"in-acceptance|post-gate-survivors|mutation-survivors|step 10")),
    # 0.2.1 is the engine-load truncation fix: it changes what the orchestrator
    # READS, and writes nothing new to the journal. Date-only, deliberately.
    ("0.2.1", "2026-08-26", None),
    # 0.3.0: #108's run-level inference record and #122's mandatory review lens.
    # Both are written to progress.md, which is what makes them usable here.
    #
    # NOTE THE DATE IS LOCAL, NOT THE UTC STAMP. installed_plugins.json records
    # 2026-09-12T00:39Z for this install; the machine that ran it was at
    # 2026-09-11 17:38 -0700, and ledger `## ` headers are written in local time.
    # Dating the boundary from the UTC stamp put the first evening of 0.3.0 runs
    # -- the first treated observations in the whole staggered-adoption design --
    # into the 0.2.1 bucket. Take install dates from the LOCAL date of the
    # install, and where a boundary day is genuinely ambiguous prefer the
    # EARLIER era: under-treating biases a DiD toward the null, over-treating
    # manufactures the effect.
    ("0.3.0", "2026-09-11", re.compile(r"Plan-gate-inferred|guard-efficacy")),
]

# `era_by_date` scans ERAS in order and breaks at the first future row, and the
# cap compares list POSITIONS -- two independent ordering contracts that were
# stated only in a comment. Append a backport row out of date order (the natural
# edit when a release is found missing) and the scan breaks at it, silently
# attributing every later row to the era before it. Checked on import instead.
def check_era_order(eras):
    """Raise unless `eras` satisfies both ordering contracts.

    A function rather than a bare module-level assert so the failing case can be
    exercised: an assert over data that is currently valid cannot be shown to
    guard anything, since deleting it changes nothing until someone makes the
    bad edit it exists to catch.
    """
    dates = [s for _, s, _ in eras if s]
    if dates != sorted(dates):
        raise ValueError(
            "ERAS install dates are out of order -- era_by_date scans in list "
            "order and breaks at the first future row")
    return True


check_era_order(ERAS)

INSTALLED_PLUGINS = os.path.expanduser("~/.claude/plugins/installed_plugins.json")



def installed_version(ledger_root):
    """Version this repo actually has installed, or None if it cannot be told.

    This is the cap that keeps a held-back control repo from being coded as
    treated. Returns None rather than guessing -- an uncappable repo is reported
    uncapped, never silently advanced.
    """
    path = os.path.abspath(ledger_root)
    try:
        with open(INSTALLED_PLUGINS, encoding="utf-8") as fh:
            entries = json.load(fh)["plugins"]["dev-loop@claude-code-loop"]
    except (OSError, ValueError, KeyError):
        return None
    best = None
    for e in entries:
        proj = os.path.abspath(e.get("projectPath") or "")
        if not proj:
            continue
        # The ledger lives under the project, so the project path is a prefix --
        # but a RAW prefix test also matches a sibling that merely shares a name
        # (`.../claude-code-loop-EXPERIMENT` inheriting `.../claude-code-loop`),
        # silently capping an unregistered repo at another repo's version. The
        # separator boundary is what makes it a path containment test.
        if path == proj or path.startswith(proj.rstrip(os.sep) + os.sep):
            if best is None or len(proj) > len(best[0]):
                best = (proj, e.get("version"))
    return best[1] if best else None


def era_by_date(date, cap=None):
    """Latest era whose install date has passed, capped at `cap` if given.

    Two default-deny rules, both of which were fail-open on the first cut:

    * An unparseable date resolves to the EARLIEST era. `parse()` writes "?"
      when a `## ` header carries no ISO date, and "?" is 0x3F -- above "2" --
      so `"?" >= "2026-09-12"` is True and the sentinel resolved to the NEWEST
      era. An undated entry was coded as fully treated, which is worse than the
      boolean it replaced (that could only ever mis-file it as 0.2.0).
    * A cap this table does not know is an ERROR, not an absent cap. Swallowing
      it silently dropped the cap while `summarize_era` still printed that
      capping was in effect -- so a repo held on an unlisted version read as
      treated, the exact DiD inversion the cap exists to prevent. It is also
      the one place staleness is mechanically detectable, so it must be loud.
    """
    if not _ISO_DATE.match(date or ""):
        return ERAS[0][0]
    era = ERAS[0][0]
    for version, start, _ in ERAS:
        if start is None or date >= start:
            era = version
        else:
            break
    if cap:
        order = [v for v, _, _ in ERAS]
        if cap not in order:
            raise ValueError(
                "installed version %r is not in ERAS -- add the release (see the "
                "module docstring) rather than measuring with a stale table" % cap)
        if order.index(era) > order.index(cap):
            era = cap
    return era


def cap_span(span, cap):
    """Truncate a marker BOUND at the installed version.

    The cap was applied to the date method only, so the marker column still
    advertised eras a held-back control never installed -- inside the read-out
    built to keep the control arm clean.
    """
    if not cap:
        return span
    order = [v for v, _, _ in ERAS]
    if cap not in order:
        return span
    kept = [v for v in span.split("|") if v in order and order.index(v) <= order.index(cap)]
    return "|".join(kept) if kept else cap


def era_by_marker(block):
    """Lower bound from vocabulary. Returns a label, not an exact era.

    A marker persists into later releases, so the honest read-out is ">=X". Where
    the next release writes no vocabulary of its own, the bound spans both and the
    label says so instead of picking the earlier one.
    """
    idx = 0
    for i, (_, _, marker) in enumerate(ERAS):
        if marker is not None and marker.search(block):
            idx = i
    span = [ERAS[idx][0]]
    for version, _, marker in ERAS[idx + 1:]:
        if marker is None:
            span.append(version)
        else:
            break
    # No conditional here: when idx == 0 and the span is a single entry, that
    # entry IS ERAS[0][0], so the guard this replaced could never change the
    # result -- it only made a future reader reason through a dead branch.
    return "|".join(span)


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
                # `era_marker` replaced a `marker` boolean that matched 0.2.0
                # vocabulary only, so it read False for a 0.3.0 entry. Nothing
                # consumed it; a reader reaching for it as "is this a modern
                # engine" would have got a silently 0.2.0-shaped answer.
                "era_marker": era_by_marker(block),
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
    cap = installed_version(label)
    print(f"\n### {label} — by engine era")
    print(f"  installed now: {cap or 'UNKNOWN (date-derived eras are UNCAPPED)'}"
          + ("   <- date-derived eras capped here; a held-back control must not "
             "read as treated" if cap else ""))

    def bucket(method):
        out = {}
        for r in peak.values():
            key = (cap_span(r["era_marker"], cap) if method == "marker"
                   else era_by_date(r["date"], cap))
            out.setdefault(key, []).append(r)
        return out

    for method in ("marker", "date"):
        for era, sel in sorted(bucket(method).items()):
            runs = [r["runs"] for r in sel]
            rounds = [r["rounds"] for r in sel if r["rounds"]]
            dates = sorted(r["date"] for r in sel)
            print(f"  {method:<6} {era:<13} n={len(runs):<3} "
                  f"runs median={statistics.median(runs):<5} max={max(runs):<4} "
                  f"rounds median={statistics.median(rounds) if rounds else '-':<5} "
                  f"{dates[0]}..{dates[-1]}")

    # A marker is a LOWER BOUND, so only a date era EARLIER than the bound's
    # floor is a disagreement. The first cut flagged any date era outside the
    # span, which flags the consistent direction too: a 0.2.0 marker can never
    # produce a span reaching 0.3.0 (the span stops at the next marker-bearing
    # era), yet ">=0.2.0" is entirely satisfied by 0.3.0. That false direction
    # grows with every 0.3.0 row whose journal happens to carry neither new
    # marker, turning the banner into noise exactly as the corpus fills up.
    order = [v for v, _, _ in ERAS]
    split = []
    for r in peak.values():
        floor_era = cap_span(r["era_marker"], cap).split("|")[0]
        if order.index(era_by_date(r["date"], cap)) < order.index(floor_era):
            split.append(r)
    if split:
        print(f"  !! {len(split)}/{len(peak)} rows classified differently by the two "
              f"methods — see the module docstring before trusting either")
    undetectable = [v for v, _, m in ERAS if m is None and v != ERAS[0][0]]
    if undetectable:
        verb = "writes" if len(undetectable) == 1 else "write"
        print(f"  note: {', '.join(undetectable)} {verb} no ledger vocabulary of its "
              f"own — marker rows spanning it are a bound, not an era")


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
