#!/usr/bin/env python3
"""Cost of CARRYING `loop-engine.md` through a whole loop run, not just ingesting it.

`context_profile.py` answers "what entered the parent, via which tool". That is an
INGESTION metric: each read counted once, when it lands. It tracks the lever, but
it is not a cost proxy -- a token arriving at turn 12 of a 109-turn session is
re-submitted on the 97 turns that follow.

Quantities, each labelled:

  * **ingested**        -- tokens of engine text that entered the parent.
  * **resident-turn**   -- sum over turns of engine tokens sitting in that turn's
                           input. What a no-cache bill would charge for the engine.
  * **carry/turn**      -- resident-turn / (ingested x turns). Turn-INVARIANT: the
                           mean fraction of the run each engine token is carried
                           for. Prefer this to raw `carry`, which scales with
                           session length and so cannot be compared across runs.
  * **billable-equiv**  -- priced. Input splits into fresh / cache-write /
                           cache-read at 1x / 1.25x / 0.1x; output bills ~5x input.

DETECTION IS THE HARD PART, and it has been wrong three separate ways. Each bug
was silent and each moved the number in a believable direction, so read
`test_engine_cost.py` before trusting a change here:

  1. **Heredoc bodies.** `cat > progress.md <<'EOF' ... EOF` whose body discusses
     the engine is a WRITE. Matching the raw command scored 9 reads in a session
     that had 1.
  2. **Working-tree vs plugin-cache.** Reading `skills/dev-loop/loop-engine.md` is
     an agent EDITING the engine as a work product -- only happens in the repo
     that develops it, and is not a loop cost. Only `/plugins/` paths are loads.
  3. **Spill files.** A `cat` of the engine exceeds the inline limit, so the
     harness writes it to `<session>/tool-results/<id>.txt` and hands the model a
     2KB preview. The recovery reads then target THE SPILL PATH, which contains no
     `loop-engine.md` substring at all. Missing them scored a session that loaded
     the entire engine as having loaded ~10% of it.

Bug 3 also corrupts sizing: on a spilled record `toolUseResult.stdout` holds the
full output while the model only ever received the preview. We size from the
tool_result BLOCK content, which is what actually entered the context window.

Stdlib only.  Self-test: `python3 test_engine_cost.py`
"""
import json
import os
import re
import sys

CTX = ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")

# Relative to one fresh input token.
W_FRESH, W_CACHE_WRITE, W_CACHE_READ, W_OUTPUT = 1.0, 1.25, 0.1, 5.0

_READ_VERB = ("cat ", "sed ", "head ", "tail ", "awk ", "grep ", "less ", "more ")
# Shapes that name a file but return a scalar, not its text.
_NOT_A_READ = re.compile(r"\bwc\b|\bgrep\b[^|;]*\s-[a-zA-Z]*[clL]\b|\bsed\b[^|;]*\s-i\b")
_HEREDOC = re.compile(r"<<-?\s*(['\"]?)(\w+)\1")


def strip_heredocs(cmd):
    """Remove heredoc BODIES, keeping any command that follows the terminator.

    Cutting at the first `<<` (the earlier approach) silently dropped a real read
    chained after a journal write -- `cat >> progress.md <<'EOF' ... EOF; sed -n
    '1,50p' $ENG` -- which the loop does constantly. Every such miss is a false
    negative, the same direction as the other two detection bugs.
    """
    out, pos = [], 0
    for m in _HEREDOC.finditer(cmd):
        if m.start() < pos:
            continue
        out.append(cmd[pos:m.start()])
        end = re.search(r"^\s*%s\s*$" % re.escape(m.group(2)),
                        cmd[m.end():], re.MULTILINE)
        pos = m.end() + (end.end() if end else len(cmd))
    out.append(cmd[pos:])
    return " ".join(out)


def classify(name, inp, target="loop-engine.md", spills=None):
    """-> 'load' (plugin cache), 'tree' (working copy), or None.

    `spills` maps a spill-file path to the kind of the read that produced it, so
    the recovery reads inherit it.
    """
    spills = spills or {}
    if not isinstance(inp, dict):
        return None
    if name == "Read":
        path = str(inp.get("file_path", ""))
    elif name in ("Grep", "Glob"):
        path = str(inp.get("path", "")) + " " + str(inp.get("glob", ""))
    elif name == "Bash":
        path = strip_heredocs(str(inp.get("command", "")))
        if _NOT_A_READ.search(path) or not any(v in path for v in _READ_VERB):
            return None
    else:
        return None
    for sp, kind in spills.items():
        if sp and sp in path:
            return kind
    if target not in path:
        return None
    # `/dev-loop/` matches the working tree too; `/plugins/` is the discriminator.
    return "load" if "/plugins/" in path else "tree"


def _spill_path(rec, block):
    """Where the harness parked an over-large tool result, if it did."""
    tr = rec.get("toolUseResult")
    if isinstance(tr, dict) and tr.get("persistedOutputPath"):
        return str(tr["persistedOutputPath"])
    m = re.search(r"Full output saved to:\s*(\S+)", str(block.get("content") or ""))
    return m.group(1) if m else None


def _received(rec, block):
    """What the model actually got -- NOT toolUseResult, which on a spilled record
    holds the full output the model never saw."""
    c = block.get("content")
    if c is None:
        c = rec.get("toolUseResult")
    try:
        return len(json.dumps(c, default=str))
    except (TypeError, ValueError):
        return len(str(c))


def load(path):
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue


def blocks(rec):
    c = (rec.get("message") or {}).get("content")
    return c if isinstance(c, list) else []


def profile(path, target="loop-engine.md", kinds=("load",)):
    turns, order, tools = {}, [], {}
    pending, arrivals = [], {}
    spills, kind_counts = {}, {}
    compactions = 0

    for rec in load(path):
        if rec.get("isSidechain"):
            continue
        if rec.get("isCompactSummary"):
            compactions += 1
        if rec.get("type") == "assistant":
            msg = rec.get("message") or {}
            mid = msg.get("id")
            if not mid:
                continue
            usage = msg.get("usage") or {}
            if mid not in turns:
                order.append(mid)
            if mid not in turns or usage.get("output_tokens", 0) > turns[mid].get("output_tokens", 0):
                turns[mid] = usage
            for b in blocks(rec):
                if isinstance(b, dict) and b.get("type") == "tool_use":
                    tools[b.get("id")] = (b.get("name", "?"), b.get("input"))
            if pending:
                arrivals[mid] = pending
                pending = []
        elif rec.get("type") == "user":
            for b in blocks(rec):
                if not (isinstance(b, dict) and b.get("type") == "tool_result"):
                    continue
                name, inp = tools.get(b.get("tool_use_id"), ("?", None))
                kind = classify(name, inp, target, spills)
                if kind:
                    kind_counts[kind] = kind_counts.get(kind, 0) + 1
                    sp = _spill_path(rec, b)
                    if sp:
                        spills[sp] = kind
                pending.append((name, _received(rec, b), kind in kinds, kind))

    if not order:
        return None

    ctx = [sum(turns[m].get(f, 0) or 0 for f in CTX) for m in order]
    out = [turns[m].get("output_tokens", 0) or 0 for m in order]
    # Input and output are billed separately AND attributed separately: the
    # engine occupies context, so it takes a share of the INPUT side only. It does
    # not cause output tokens. Folding output into the per-turn weight and then
    # multiplying by the engine's context share silently credited the engine with
    # a slice of the model's own writing, which cancelled the dilution that
    # including output is supposed to produce.
    bill_in = [(turns[m].get("input_tokens", 0) or 0) * W_FRESH
               + (turns[m].get("cache_creation_input_tokens", 0) or 0) * W_CACHE_WRITE
               + (turns[m].get("cache_read_input_tokens", 0) or 0) * W_CACHE_READ
               for m in order]
    bill_out = [(turns[m].get("output_tokens", 0) or 0) * W_OUTPUT for m in order]
    bill_total = sum(bill_in) + sum(bill_out)

    reads, by_tool, per_turn, calib = 0, {}, {}, []
    for i, mid in enumerate(order):
        calls = arrivals.get(mid, [])
        eng = [(n, sz) for n, sz, e, k in calls if e]
        for n, sz in eng:
            reads += 1
            by_tool[n] = by_tool.get(n, 0) + sz
        if not eng or i == 0:
            continue
        added = max(0, ctx[i] - ctx[i - 1] - out[i - 1])
        total = sum(sz for _, sz, _, _ in calls)
        if total:
            per_turn[i] = added * sum(sz for _, sz in eng) / total
        if len(calls) == len(eng) and added > 0:
            calib.append((added, sum(sz for _, sz in eng)))

    ingested = sum(per_turn.values())

    models = {}
    for model in ("NONE", "PROP", "FULL"):
        resident = resident_turns = billable = peak_share = 0.0
        for i, mid in enumerate(order):
            if i > 0 and ctx[i] < ctx[i - 1] and ctx[i - 1] > 0:
                if model == "FULL":
                    resident = 0.0
                elif model == "PROP":
                    resident *= ctx[i] / ctx[i - 1]
            resident += per_turn.get(i, 0.0)
            if ctx[i]:
                resident = min(resident, ctx[i])
                share = resident / ctx[i]
                peak_share = max(peak_share, share)
                billable += share * bill_in[i]
            resident_turns += resident
        models[model] = (resident_turns, billable, peak_share)

    return {
        "path": path, "turns": len(order), "compactions": compactions,
        "reads": reads, "by_tool": by_tool, "kind_counts": kind_counts,
        "ingested": ingested, "calib": calib, "spills": len(spills),
        "peak_ctx": max(ctx), "processed": sum(ctx),
        "billable_total": bill_total, "billable_in": sum(bill_in),
        "billable_out": sum(bill_out), "output_total": sum(out), "models": models,
    }


def render(p):
    n, ing, proc = p["turns"], p["ingested"], p["processed"]
    print(f"\n=== {os.path.basename(p['path'])[:8]}   {n} parent turns, "
          f"{p['compactions']} compaction(s), {p['spills']} spill file(s)")
    print(f"  peak context            {p['peak_ctx']:>12,}")
    print(f"  no-cache input basis    {proc:>12,}")
    print(f"  billable-equiv          {p['billable_total']:>12,.0f}   "
          f"(input {p['billable_in']:,.0f} @1/1.25/0.1x + output {p['billable_out']:,.0f} @5x)")
    kc = ", ".join(f"{k}:{v}" for k, v in sorted(p["kind_counts"].items())) or "none"
    print(f"  engine reads counted    {p['reads']:>12}   [all matches: {kc}]")
    if not ing:
        print("  !! no engine tokens detected -- check the filter before believing this")
        return
    print(f"  INGESTED (P2)           {ing:>12,.0f}")
    if p["calib"]:
        ex = sum(a for a, _ in p["calib"]); ch = sum(b for _, b in p["calib"])
        print(f"  chars/context-token     {ch/ex:>12.2f}   (n={len(p['calib'])}; pipeline "
              f"constant, NOT the tokenizer ratio)")
    print(f"  {'model':<7}{'resident-turn':>15}{'carry':>8}{'carry/turn':>12}"
          f"{'eng bill':>12}{'% of bill':>11}{'peak share':>12}")
    for m in ("NONE", "PROP", "FULL"):
        rt, bl, ps = p["models"][m]
        print(f"  {m:<7}{rt:>15,.0f}{rt/ing:>7.0f}x{rt/(ing*n):>12.2f}"
              f"{bl:>12,.0f}{bl/p['billable_total']:>11.1%}{ps:>12.1%}")


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("-")]
    kinds = ("load", "tree") if "--all-reads" in argv else ("load",)
    if not args:
        print(__doc__)
        return 1
    for path in args:
        p = profile(path, kinds=kinds)
        if p is None:
            print(f"\n=== {os.path.basename(path)}: no parent turns")
        else:
            render(p)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
