#!/usr/bin/env python3
"""Does gate-round count predict parent turns?

This is the load-bearing join the cost analysis rests on. `cost ~ turns x ~33k`,
and Finding 2 claims extra review rounds -- mostly fix-induced -- are the dominant
driver of turns. **If rounds do not predict turns, that ranking is wrong and
sharding outranks convergence after all.**

Method: `- Budget:` lines are written by the parent into `progress.md`, so they
also appear in the session transcript that produced them. For each session we
take the DISTINCT budget lines it wrote, sum `gate-rounds=...` across them, and
divide parent turns by the number of issues closed in that session.

Known weakness, stated because it bounds every number below: **the session-issue
mapping is many-to-many.** A session can close several issues and an issue can
span sessions. Per-issue figures are therefore averages within a session, and a
session that closed zero issues is excluded rather than counted as zero.

Stdlib only.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from engine_cost import profile  # noqa: E402

# Budget lines are LINE-WRAPPED in the ledger, so `gate-rounds=` routinely sits on
# a continuation line. A single-line regex captures the prefix, finds no rounds,
# and silently drops the row -- which cost three of nine sessions on the first
# run. This is the same wrapped-text hazard CLAUDE.md documents for the engine's
# step references. Capture to a blank line or the next top-level bullet.
BUDGET = re.compile(r"- Budget:.*?(?=\n\s*\n|\n- [A-Z]|\nEOF|$)", re.S)
GATE = re.compile(r"(architect|code-review|ac-verify|security)=(\d+)")
RUNS = re.compile(r"subagent-runs[=≈](\d+)")
ISSUE = re.compile(r"#(\d+)")


def budgets(path):
    """Distinct `- Budget:` lines this session WROTE.

    Direction matters, and getting it wrong is the same bug class that broke the
    engine-read filter three times: a budget line the parent *read back* out of
    `progress.md` is history, not work done here. Counting those gave one
    158-turn session 11 issues at 14 turns each, against an engine whose rule is
    one issue per invocation. So we only look inside **assistant tool_use
    inputs** -- the heredoc the parent is appending to the ledger -- and never
    inside tool results or user turns.
    """
    seen, out = set(), []
    with open(path, encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            try:
                rec = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if rec.get("isSidechain") or rec.get("type") != "assistant":
                continue
            content = (rec.get("message") or {}).get("content")
            if not isinstance(content, list):
                continue
            written = []
            for b in content:
                if not (isinstance(b, dict) and b.get("type") == "tool_use"):
                    continue
                inp = b.get("input")
                if isinstance(inp, dict):
                    # the UNESCAPED values -- json.dumps would turn every newline
                    # into a literal backslash-n and defeat the line regex
                    written.extend(str(v) for v in inp.values())
            line = "\n".join(written)
            for m in BUDGET.finditer(line):
                t = m.group(0)
                t = re.sub(r"\s+", " ", t)
                key = t[:300]
                if key in seen:
                    continue
                seen.add(key)
                rounds = {k: int(v) for k, v in GATE.findall(t)}
                if not rounds:
                    continue
                r = RUNS.search(t)
                out.append({"rounds": sum(rounds.values()), "detail": rounds,
                            "runs": int(r.group(1)) if r else None})
    return out


def fit(xs, ys):
    """Least-squares slope/intercept. The slope is the whole point: it prices one
    extra gate round in turns, and turns are the unit cost is denominated in."""
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    den = sum((x - mx) ** 2 for x in xs)
    if not den:
        return None, None
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den
    return b, my - b * mx


def pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = sum((x - mx) ** 2 for x in xs) ** 0.5
    dy = sum((y - my) ** 2 for y in ys) ** 0.5
    return num / (dx * dy) if dx and dy else None


def main(argv):
    paths = [a for a in argv[1:] if not a.startswith("-")]
    rows = []
    for p in paths:
        prof = profile(p)
        if not prof:
            continue
        bs = budgets(p)
        if not bs:
            continue
        issues = len(bs)
        rounds = sum(b["rounds"] for b in bs)
        runs = sum(b["runs"] or 0 for b in bs)
        rows.append({
            "s": os.path.basename(p)[:8], "turns": prof["turns"], "issues": issues,
            "rounds": rounds, "runs": runs,
            "tpi": prof["turns"] / issues, "rpi": rounds / issues,
            "bill": prof["billable_total"], "bpi": prof["billable_total"] / issues,
        })
    if not rows:
        print("no sessions with parseable Budget lines")
        return 1
    rows.sort(key=lambda r: r["rpi"])
    print(f"{'session':<10}{'turns':>6}{'issues':>7}{'rounds':>7}{'runs':>6}"
          f"{'turns/issue':>12}{'rounds/issue':>13}{'bill/issue':>12}")
    for r in rows:
        print(f"{r['s']:<10}{r['turns']:>6}{r['issues']:>7}{r['rounds']:>7}{r['runs']:>6}"
              f"{r['tpi']:>12.0f}{r['rpi']:>13.1f}{r['bpi']:>12,.0f}")
    for xa, ya, lbl in (("rpi", "tpi", "rounds/issue -> turns/issue"),
                        ("rpi", "bpi", "rounds/issue -> bill/issue"),
                        ("rounds", "turns", "total rounds -> total turns"),
                        ("runs", "turns", "subagent-runs -> total turns")):
        r = pearson([x[xa] for x in rows], [x[ya] for x in rows])
        print(f"  pearson  {lbl:<32} r = {r:+.2f}" if r is not None else
              f"  pearson  {lbl:<32} n/a")
    for ya, unit in (("tpi", "turns"), ("bpi", "billable-equiv")):
        b, a = fit([r["rpi"] for r in rows], [r[ya] for r in rows])
        if b is not None:
            print(f"  fit      {ya:<32} = {a:,.0f} + {b:,.0f} x rounds  ({unit})")
    print(f"\n  n = {len(rows)} sessions, {sum(r['issues'] for r in rows)} issues")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
