#!/usr/bin/env python3
"""How many tool calls does the parent issue per turn, and how many turns could
have been merged?

Cost is `turns x ~33k` (Finding 10), and a turn issuing five parallel tool calls
bills the same as one issuing a single call. So batching is the only lever that
reduces turns without touching a gate, a verdict, or any pipeline semantics.

Two numbers matter:

  * **calls/turn** -- the current batching rate.
  * **mergeable turns** -- an UPPER BOUND on what batching could recover. We count
    maximal runs of >=2 consecutive turns that each issue exactly one READ-ONLY
    tool call. A run of k such turns could in principle have been 1 turn, saving
    k-1. It is an upper bound and not a target: consecutive reads are often
    genuinely dependent (read a file, then grep for what it named), and nothing
    here can tell a dependent read from an independent one. Treat it as "the
    ceiling is worth chasing" evidence, never as a forecast.

Read-only is decided conservatively: a Bash command containing any write, move,
commit or in-place-edit shape counts as a WRITE and breaks the run, because
merging across a mutation would reorder effects.

Every session prints its `stratum` line, and **corpus totals are grouped by the
parent's stratum** (`stratum.py`), never pooled across one; an unstratified session
is excluded and named. Each turn's input bill uses its OWN model's weights
(`stratum.PRICING`, #212/AC5), in ratio units -- so a session whose turns carry more
than one model refuses to price, since ratio units are one unit only on one model. A
session that refuses to price is excluded from the WEIGHTED totals only, named, and
still counted in the turn and call totals.

Turns follow the cost spec (#212, `stratum.turns`): one turn per `message.id`, billed
on the max-`output_tokens` line, its calls collected from EVERY line; a line with no
id is its own turn and is counted. A session whose usage cannot be read at all is
excluded outright and named.

Stdlib only.
"""
import json
import os
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stratum import Unpriced, group_by_stratum, input_equiv, label, one_model, \
    session_strata, stratum_line, turns, weights_for  # noqa: E402

READ_TOOLS = {"Read", "Grep", "Glob", "NotebookRead", "WebFetch", "WebSearch"}
# Any of these in a Bash command makes it a mutation for our purposes.
# NOTE the last alternation group. A `python3 - <<'PY' ... p.write_text(s) PY`
# heredoc mutates the tree while the command line shows no redirect at all, so a
# shell-shape-only test classifies it read-only. Found by hand-checking a run that
# this script had called mergeable -- it contained two such writes, and merging
# across them would have reordered effects. Sixth detection bug of this family.
WRITE_SHAPE = re.compile(
    r">>?[^&|]|\btee\b|\bsed\b[^|;]*-i\b|\bgit\s+(commit|add|push|merge|checkout|rm|mv|reset)"
    r"|\brm\b|\bmv\b|\bcp\b|\bmkdir\b|\btouch\b|\bgh\s+(issue|pr)\s+(create|edit|comment|close|merge)"
    r"|write_text|\.write\(|\bopen\([^)]*['\"][wa]|json\.dump|shutil\.|os\.(rename|remove|replace)"
    r"|\.unlink\(|\bWrite\b|Path\([^)]*\)\s*\.\s*write"
)


def is_read_only(name, inp):
    if name in READ_TOOLS:
        return True
    if name != "Bash" or not isinstance(inp, dict):
        return False
    return not WRITE_SHAPE.search(str(inp.get("command", "")))


_PATH = re.compile(r"[\w./~${}-]*\.(md|py|txt|json|toml|ya?ml|ipynb|sql|cfg)\b")


def _target(turn):
    """The single file a solo read is aimed at, if one is identifiable."""
    name, inp = turn["calls"][0]
    if not isinstance(inp, dict):
        return None
    fp = inp.get("file_path")
    if fp:
        return os.path.basename(str(fp))
    m = _PATH.search(str(inp.get("command", "")))
    return os.path.basename(m.group(0)) if m else None


def load(path):
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue


def profile_turns(path):
    """-> (per-turn dicts for the PARENT thread only, stratum.TurnCounts).

    Each turn's `bill` is its input side on its own model's weights, or None with
    `refused` naming why. Raises `Unpriced` if a line's usage cannot be read."""
    records = [r for r in load(path) if isinstance(r, dict) and not r.get("isSidechain")]
    ts, counts = turns(records)
    out = []
    for t in ts:
        # A merged-away turn saves ITS OWN input bill, not the corpus average.
        # Paging runs sit early in a session where context is still small, so
        # pricing them at the average materially overstates the saving.
        try:
            bill, refused = input_equiv(t.usage, weights_for(t.model)), None
        except Unpriced as exc:
            bill, refused = None, "turn %s: %s" % (t.key, exc)
        calls, seen = [], set()
        for rec in t.records:
            for b in ((rec.get("message") or {}).get("content") or []):
                if not (isinstance(b, dict) and b.get("type") == "tool_use"):
                    continue
                # streaming repeats blocks across snapshots of one logical turn
                if b.get("id") in seen:
                    continue
                seen.add(b.get("id"))
                calls.append((b.get("name", "?"), b.get("input")))
        out.append({"calls": calls, "bill": bill, "refused": refused,
                    "model": t.model, "turn": t})
    return out, counts


def analyse(path):
    """Raises `Unpriced` when a line's usage cannot be read at all."""
    stratum = session_strata(path)
    ts, counts = profile_turns(path)
    if not ts:
        return None
    refused = None
    if not stratum.stratified:
        refused = "unstratified: %s" % stratum.reason
    else:
        refused = next((t["refused"] for t in ts if t["refused"]), None)
        if refused is None:
            try:
                one_model([t["turn"] for t in ts])
            except Unpriced as exc:
                refused = str(exc)
    priced = refused is None
    hist = Counter(len(t["calls"]) for t in ts)
    total_calls = sum(len(t["calls"]) for t in ts)

    solo_read = [len(t["calls"]) == 1 and is_read_only(*t["calls"][0]) for t in ts]
    mergeable, run, merge_bill, buf = 0, 0, 0.0, []
    for i, flag in enumerate(solo_read + [False]):
        if flag:
            run += 1
            buf.append(ts[i]["bill"] or 0.0)
        else:
            if run >= 2:
                mergeable += run - 1
                merge_bill += sum(sorted(buf)[1:])   # survivor is the FIRST turn (cheapest)
            run, buf = 0, []

    # High-confidence subset: consecutive solo reads whose target FILE is the same.
    # That is paging -- the agent walking one known file in slices -- and the
    # slices are unambiguously independent of each other, so batching them cannot
    # reorder anything. The rest of `mergeable` includes reads that may genuinely
    # depend on what the previous read returned, which nothing here can detect.
    # `paging` is the THEORETICAL collapse (k turns -> 1). `recoverable` is what a
    # discovery-read-first protocol can actually reach: #135/AC1 keeps the first
    # read as its own turn (it is what reports the extent), so a k-run saves k-2,
    # and a k=2 run saves NOTHING. The run-length histogram is what makes the
    # difference legible -- without it, a corpus of 2-runs and a corpus of 6-runs
    # report the same `paging` and have completely different real savings.
    runlens = []
    paging, prun, prev, page_bill, pbuf = 0, 0, None, 0.0, []
    for i, t in enumerate(ts):
        tgt = _target(t) if solo_read[i] else None
        if tgt and tgt == prev:
            prun += 1
            pbuf.append(t["bill"] or 0.0)
        else:
            if prun >= 2:
                paging += prun - 1
                runlens.append(prun)
                page_bill += sum(sorted(pbuf)[1:])
            prun = 1 if tgt else 0
            pbuf = [t["bill"] or 0.0] if tgt else []
        prev = tgt
    if prun >= 2:
        paging += prun - 1
        runlens.append(prun)
        page_bill += sum(sorted(pbuf)[1:])
    return {
        "path": path, "turns": len(ts), "calls": total_calls,
        "cpt": total_calls / len(ts), "hist": hist,
        "solo_read": sum(solo_read), "mergeable": mergeable, "paging": paging,
        "merge_bill": merge_bill if priced else None,
        "page_bill": page_bill if priced else None,
        "runlens": runlens, "recoverable": sum(max(0, k - 2) for k in runlens),
        "total_bill": sum(t["bill"] for t in ts) if priced else None,
        "stratum": stratum, "price_refused": refused,
        "no_id": counts.no_id, "api_error": counts.api_error,
    }


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("-")]
    if not args:
        print(__doc__)
        return 1
    rows, refused = [], []
    for p in args:
        try:
            a = analyse(p)
        except Unpriced as exc:
            refused.append((p, exc))
            continue
        if a:
            rows.append(a)
    for p, exc in refused:
        print(f"  EXCLUDED {os.path.basename(p)[:8]}: refused -- {exc}")
    if not rows:
        return 1
    for r in rows:
        print(f"{os.path.basename(r['path'])[:8]:<10}{stratum_line(r['stratum'])}"
              f"  (no_id={r['no_id']} api_error={r['api_error']})")
    groups, excluded = group_by_stratum(rows, key=lambda r: r["stratum"])
    for r, why in excluded:
        print(f"  EXCLUDED {os.path.basename(r['path'])[:8]}: {why}")
    for key, grp in groups.items():
        report_stratum(key, grp)
    return 0


def report_stratum(key, rows):
    """Corpus totals within ONE parent stratum."""
    print(f"\n### stratum {label(key)}")
    print(f"{'session':<10}{'turns':>6}{'calls':>7}{'calls/turn':>11}"
          f"{'0-call':>8}{'1-call':>8}{'2+':>6}{'solo-read':>10}{'mergeable':>10}{'-turns':>8}{'paging':>8}")
    for r in rows:
        h = r["hist"]
        two_plus = sum(v for k, v in h.items() if k >= 2)
        print(f"{os.path.basename(r['path'])[:8]:<10}{r['turns']:>6}{r['calls']:>7}"
              f"{r['cpt']:>11.2f}{h.get(0,0):>8}{h.get(1,0):>8}{two_plus:>6}"
              f"{r['solo_read']:>10}{r['mergeable']:>10}{r['mergeable']/r['turns']:>7.0%}"
              f"{r['paging']:>8}")
    T = sum(r["turns"] for r in rows)
    C = sum(r["calls"] for r in rows)
    M = sum(r["mergeable"] for r in rows)
    print(f"\n  corpus: {T:,} turns, {C:,} calls, {C/T:.2f} calls/turn")
    print(f"  upper-bound mergeable: {M:,} turns ({M/T:.0%} of all turns)")
    P = sum(r["paging"] for r in rows)
    REC = sum(r["recoverable"] for r in rows)
    allruns = [k for r in rows for k in r["runlens"]]
    print(f"  of which same-file PAGING (high confidence): {P:,} turns ({P/T:.0%} of all turns)")
    priced = [r for r in rows if r["total_bill"] is not None]
    for r in rows:
        if r["total_bill"] is None:
            print(f"  EXCLUDED from the weighted totals only "
                  f"{os.path.basename(r['path'])[:8]}: {r['price_refused']}")
    MB = sum(r["merge_bill"] for r in priced)
    PB = sum(r["page_bill"] for r in priced)
    TB = sum(r["total_bill"] for r in priced)
    Mp = sum(r["mergeable"] for r in priced)
    n = len(priced)
    if priced and TB:
        print(f"\n  priced at each merged-away turn's OWN input bill, not the corpus average"
              f" ({n} priced sessions):")
        print(f"    ceiling (all mergeable)  {MB:>12,.0f} tok  = {MB/TB:>5.1%} of input bill"
              f"   ({MB/n:>9,.0f}/session)")
        print(f"    floor   (paging only)    {PB:>12,.0f} tok  = {PB/TB:>5.1%} of input bill"
              f"   ({PB/n:>9,.0f}/session)")
        # ~33k/turn is Finding 10's figure: claude-opus-5, n=8, pooled across
        # @xhigh x6 and @high x2 -- so it spans an effort stratum itself.
        print(f"    naive avg-priced ceiling {Mp*33000:>12,.0f} tok  (33k/turn: Finding 10, "
              f"claude-opus-5 @xhigh+@high, n=8; spans a stratum -- re-measure per stratum)"
              + (f"  <- overstates by {Mp*33000/MB:.1f}x" if MB else ""))
    h = Counter(allruns)
    print(f"\n  paging run lengths: " + ", ".join(f"k={k}x{h[k]}" for k in sorted(h)))
    print(f"  theoretical collapse (k-1): {P:,} turns")
    print(f"  RECOVERABLE under a discovery-read-first protocol (k-2): {REC:,} turns"
          f"  = {REC/P:.0%} of theoretical" if P else "")
    PP = sum(r["paging"] for r in priced)
    RP = sum(r["recoverable"] for r in priced)
    print(f"    -> realistic floor {PB*RP/PP:,.0f} tok total, {PB*RP/PP/n:,.0f}/session"
          if priced and PP else "")


if __name__ == "__main__":
    sys.exit(main(sys.argv))
