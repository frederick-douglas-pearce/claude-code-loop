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

Stdlib only.
"""
import json
import os
import re
import sys
from collections import Counter

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


W_FRESH, W_CACHE_WRITE, W_CACHE_READ = 1.0, 1.25, 0.1


def profile_turns(path):
    """-> ordered list of per-turn dicts for the PARENT thread only."""
    turns, order = {}, []
    for rec in load(path):
        if rec.get("isSidechain") or rec.get("type") != "assistant":
            continue
        msg = rec.get("message") or {}
        mid = msg.get("id")
        if not mid:
            continue
        if mid not in turns:
            order.append(mid)
            turns[mid] = {"calls": [], "seen": set(), "bill": 0.0}
        t = turns[mid]
        u = msg.get("usage") or {}
        # A merged-away turn saves ITS OWN input bill, not the corpus average.
        # Paging runs sit early in a session where context is still small, so
        # pricing them at the average materially overstates the saving.
        t["bill"] = max(t["bill"],
                        (u.get("input_tokens", 0) or 0) * W_FRESH
                        + (u.get("cache_creation_input_tokens", 0) or 0) * W_CACHE_WRITE
                        + (u.get("cache_read_input_tokens", 0) or 0) * W_CACHE_READ)
        for b in (msg.get("content") or []):
            if not (isinstance(b, dict) and b.get("type") == "tool_use"):
                continue
            # streaming repeats blocks across snapshots of one logical turn
            if b.get("id") in t["seen"]:
                continue
            t["seen"].add(b.get("id"))
            t["calls"].append((b.get("name", "?"), b.get("input")))
    return [turns[m] for m in order]


def analyse(path):
    ts = profile_turns(path)
    if not ts:
        return None
    hist = Counter(len(t["calls"]) for t in ts)
    total_calls = sum(len(t["calls"]) for t in ts)

    solo_read = [len(t["calls"]) == 1 and is_read_only(*t["calls"][0]) for t in ts]
    mergeable, run, merge_bill, buf = 0, 0, 0.0, []
    for i, flag in enumerate(solo_read + [False]):
        if flag:
            run += 1
            buf.append(ts[i]["bill"])
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
            pbuf.append(t["bill"])
        else:
            if prun >= 2:
                paging += prun - 1
                runlens.append(prun)
                page_bill += sum(sorted(pbuf)[1:])
            prun = 1 if tgt else 0
            pbuf = [t["bill"]] if tgt else []
        prev = tgt
    if prun >= 2:
        paging += prun - 1
        runlens.append(prun)
        page_bill += sum(sorted(pbuf)[1:])
    return {
        "path": path, "turns": len(ts), "calls": total_calls,
        "cpt": total_calls / len(ts), "hist": hist,
        "solo_read": sum(solo_read), "mergeable": mergeable, "paging": paging,
        "merge_bill": merge_bill, "page_bill": page_bill,
        "runlens": runlens, "recoverable": sum(max(0, k - 2) for k in runlens),
        "total_bill": sum(t["bill"] for t in ts),
    }


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("-")]
    if not args:
        print(__doc__)
        return 1
    rows = []
    for p in args:
        a = analyse(p)
        if a:
            rows.append(a)
    if not rows:
        return 1
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
    MB = sum(r["merge_bill"] for r in rows)
    PB = sum(r["page_bill"] for r in rows)
    TB = sum(r["total_bill"] for r in rows)
    n = len(rows)
    print(f"  of which same-file PAGING (high confidence): {P:,} turns ({P/T:.0%} of all turns)")
    print(f"\n  priced at each merged-away turn's OWN input bill, not the corpus average:")
    print(f"    ceiling (all mergeable)  {MB:>12,.0f} tok  = {MB/TB:>5.1%} of input bill"
          f"   ({MB/n:>9,.0f}/session)")
    print(f"    floor   (paging only)    {PB:>12,.0f} tok  = {PB/TB:>5.1%} of input bill"
          f"   ({PB/n:>9,.0f}/session)")
    print(f"    naive avg-priced ceiling {M*33000:>12,.0f} tok  <- overstates by "
          f"{M*33000/MB:.1f}x")
    from collections import Counter
    h = Counter(allruns)
    print(f"\n  paging run lengths: " + ", ".join(f"k={k}x{h[k]}" for k in sorted(h)))
    print(f"  theoretical collapse (k-1): {P:,} turns")
    print(f"  RECOVERABLE under a discovery-read-first protocol (k-2): {REC:,} turns"
          f"  = {REC/P:.0%} of theoretical" if P else "")
    print(f"    -> realistic floor {PB*REC/P:,.0f} tok total, {PB*REC/P/n:,.0f}/session" if P else "")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
