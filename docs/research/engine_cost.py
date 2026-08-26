#!/usr/bin/env python3
"""Cost of carrying `loop-engine.md` through a whole loop run, not just ingesting it.

`context_profile.py` answers "what entered the parent, and via which tool". That
is an INGESTION metric: it counts each engine read once, at the moment it lands.
It is the right lever-tracking number (it moves iff the file or the read pattern
changes) but it is NOT a cost proxy, because a token that enters at turn 12 of a
90-turn session is re-submitted on all 78 turns that follow.

This script answers the cost question. Three quantities, each labelled:

  * **ingested**   -- what `context_profile.py` reports. Read once per read.
  * **resident-turn tokens** -- sum over parent turns of the engine tokens sitting
    in that turn's input. This is what a no-cache bill would charge for the engine.
  * **billable-equivalent** -- the same, priced. Every turn's input is split by the
    API into fresh / cache-write / cache-read at 1x / 1.25x / 0.1x, so carrying a
    cached prefix is ~10x cheaper per turn than the no-cache model implies. We
    attribute the engine its share of each turn's real billing mix.

Residency needs an eviction model, because compaction drops context. We report all
three: NONE (upper bound, nothing is ever evicted), PROP (context shrank by r, so
assume the engine's resident share shrank by r too), and FULL (lower bound, any
context drop evicts the engine entirely until it is re-read). PROP is the headline;
the spread between NONE and FULL is the honest error bar.

Stdlib only.
"""
import json
import os
import sys

CTX = ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")
CHARS_PER_TOKEN = 4.0

# Relative to one fresh input token. Uniform across current Claude models.
W_FRESH, W_CACHE_WRITE, W_CACHE_READ = 1.0, 1.25, 0.1


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
    msg = rec.get("message") or {}
    c = msg.get("content")
    return c if isinstance(c, list) else []


def is_engine(name, inp, target):
    """Does this tool call pull text out of the engine file?"""
    if not isinstance(inp, dict):
        return False
    if name == "Read":
        return target in str(inp.get("file_path", ""))
    if name == "Bash":
        cmd = str(inp.get("command", ""))
        # a bash call that merely *mentions* the path (wc, ls, git) is not a read
        if target not in cmd:
            return False
        return any(v in cmd for v in ("cat ", "sed ", "head ", "tail ", "awk ", "grep "))
    if name in ("Grep", "Glob"):
        return target in str(inp.get("path", "")) or target in str(inp.get("glob", ""))
    return False


def profile(path, target="loop-engine.md"):
    turns, order = {}, []
    tools = {}                 # tool_use_id -> (name, input)
    pending = []               # results seen since last assistant turn
    arrivals = {}              # message.id -> [(name, chars, engine?)]

    for rec in load(path):
        if rec.get("isSidechain"):
            continue
        if rec.get("type") == "assistant":
            msg = rec.get("message") or {}
            mid = msg.get("id")
            if not mid:
                continue
            usage = msg.get("usage") or {}
            prev = turns.get(mid)
            if prev is None:
                order.append(mid)
            if prev is None or usage.get("output_tokens", 0) > prev.get("output_tokens", 0):
                turns[mid] = usage
            for b in blocks(rec):
                if isinstance(b, dict) and b.get("type") == "tool_use":
                    tools[b.get("id")] = (b.get("name", "?"), b.get("input"))
            if pending:
                arrivals[mid] = pending
                pending = []
        elif rec.get("type") == "user":
            for b in blocks(rec):
                if isinstance(b, dict) and b.get("type") == "tool_result":
                    name, inp = tools.get(b.get("tool_use_id"), ("?", None))
                    payload = rec.get("toolUseResult", b.get("content"))
                    try:
                        size = len(json.dumps(payload, default=str))
                    except (TypeError, ValueError):
                        size = len(str(payload))
                    pending.append((name, size, is_engine(name, inp, target)))

    if not order:
        return None

    ctx = [sum(turns[m].get(f, 0) or 0 for f in CTX) for m in order]
    out = [turns[m].get("output_tokens", 0) or 0 for m in order]

    # per-turn billable weight of the input side
    bill = [(turns[m].get("input_tokens", 0) or 0) * W_FRESH
            + (turns[m].get("cache_creation_input_tokens", 0) or 0) * W_CACHE_WRITE
            + (turns[m].get("cache_read_input_tokens", 0) or 0) * W_CACHE_READ
            for m in order]

    # ---- engine ingestion, measured from context deltas, not estimated ----
    #
    # chars/4 is an ESTIMATE and it is wrong for this corpus (markdown with heavy
    # punctuation tokenises nearer 3.3-3.8 chars/token, so /4 understates by
    # 5-20%). The transcript carries the true figure: ctx[i]-ctx[i-1]-out[i-1] is
    # exactly what the tool results of turn i added. Where a turn returned engine
    # text alongside other results, that delta is split by serialised length --
    # exact in aggregate, approximate per call, which is the right way round.
    reads, ingested_chars, calib = 0, 0, []
    by_tool = {}
    per_turn_engine_tok = {}       # index -> engine tokens that landed at that turn
    for i, mid in enumerate(order):
        calls = arrivals.get(mid, [])
        eng = [(n, sz) for n, sz, e in calls if e]
        for n, sz in eng:
            reads += 1
            ingested_chars += sz
            by_tool[n] = by_tool.get(n, 0) + sz
        if not eng or i == 0:
            continue
        added = max(0, ctx[i] - ctx[i - 1] - out[i - 1])
        total = sum(sz for _, sz, _ in calls)
        eng_chars = sum(sz for _, sz in eng)
        if total:
            per_turn_engine_tok[i] = added * eng_chars / total
        if len(calls) == len(eng) and added > 0:
            calib.append((added, eng_chars))

    ingested_tok = sum(per_turn_engine_tok.values())
    ingested_est = ingested_chars / CHARS_PER_TOKEN

    # ---- residency, under three eviction models ----
    models = {}
    for model in ("NONE", "PROP", "FULL"):
        resident = 0.0
        resident_turns = 0.0
        billable = 0.0
        peak_share = 0.0
        positional = 0.0
        for i, mid in enumerate(order):
            if i > 0 and ctx[i] < ctx[i - 1] and ctx[i - 1] > 0:
                if model == "FULL":
                    resident = 0.0
                elif model == "PROP":
                    resident *= ctx[i] / ctx[i - 1]
            # engine text that arrived before this turn is in this turn's input
            resident += per_turn_engine_tok.get(i, 0.0)
            resident = min(resident, ctx[i]) if ctx[i] else resident
            resident_turns += resident
            if ctx[i]:
                share = resident / ctx[i]
                peak_share = max(peak_share, share)
                billable += share * bill[i]
                # Positional check: the engine lands early and then sits in the
                # stable cached prefix, so after its arrival turn it is charged at
                # the cache-read rate rather than at the turn's blended rate.
                cr = turns[order[i]].get("cache_read_input_tokens", 0) or 0
                cheap = min(resident, cr)
                positional += cheap * W_CACHE_READ + (resident - cheap) * W_CACHE_WRITE
        models[model] = (resident_turns, billable, peak_share, positional)

    return {
        "path": path, "turns": len(order),
        "reads": reads, "by_tool": by_tool,
        "ingested_tok": ingested_tok, "ingested_est": ingested_est, "calib": calib,
        "peak_ctx": max(ctx), "final_ctx": ctx[-1],
        "processed": sum(ctx), "billable_total": sum(bill),
        "output_total": sum(out), "models": models,
    }


def render(p):
    print(f"\n=== {os.path.basename(p['path'])[:8]}   {p['turns']} parent turns")
    print(f"  peak context            {p['peak_ctx']:>12,}")
    print(f"  no-cache input basis    {p['processed']:>12,}   (sum of every turn's context)")
    print(f"  billable-equiv input    {p['billable_total']:>12,.0f}   (cache-priced: 1x / 1.25x / 0.1x)")
    print(f"  cache leverage          {p['processed'] / p['billable_total']:>12.1f}x")
    print(f"  --- engine ---")
    tl = ", ".join(f"{k}:{v:,}ch" for k, v in sorted(p["by_tool"].items()))
    print(f"  reads                   {p['reads']:>12}   ({tl})")
    print(f"  INGESTED, measured      {p['ingested_tok']:>12,.0f}   <- from context deltas")
    print(f"  INGESTED, chars/4 est   {p['ingested_est']:>12,.0f}   "
          f"({p['ingested_est']/p['ingested_tok']-1:+.0%} vs measured)")
    if p["calib"]:
        ex = sum(a for a, _ in p["calib"]); ch = sum(b for _, b in p["calib"])
        print(f"  chars/token, observed   {ch/ex:>12.2f}   (n={len(p['calib'])} single-source turns)")
    print(f"  cost per ingested token {sum(p['models']['PROP'][3:4])/p['ingested_tok']:>12.1f}x"
          f"   (billable-equiv carried over the run)")
    print(f"  {'model':<8}{'resident-turn tok':>20}{'carry x':>10}{'blended-bill':>15}"
          f"{'positional':>13}{'% of bill':>11}{'peak share':>12}")
    for m in ("NONE", "PROP", "FULL"):
        rt, bl, ps, po = p["models"][m]
        print(f"  {m:<8}{rt:>20,.0f}{rt/p['ingested_tok']:>10.0f}x{bl:>15,.0f}"
              f"{po:>13,.0f}{po/p['billable_total']:>11.1%}{ps:>12.1%}")


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("-")]
    if not args:
        print(__doc__)
        return 1
    for path in args:
        p = profile(path)
        if p is None:
            print(f"\n=== {os.path.basename(path)}: no parent turns")
            continue
        render(p)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
