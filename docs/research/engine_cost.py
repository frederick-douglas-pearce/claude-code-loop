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

# ADMISSIBILITY FLOOR. A session counts only if measured ingestion clears one copy
# of what should have loaded. Below it, the engine either never fully loaded or the
# detector missed reads -- and in BOTH cases the session is *unmeasured*, not cheap.
# Default-deny: unknown ⇒ inadmissible, excluded loudly, never quietly averaged in.
# Without this, a broken run reads as the cheapest run in the corpus, which is
# exactly how a truncated load got written up as a finding once already.
#
# THE FLOOR IS PER-SESSION, because "one copy of the engine" is not one number.
# It was `177529 / 3.5` -- one 0.2.0 copy -- from the first version of this file
# until 2026-09-12, and the v0.3.0 release grew the engine 50.8% (177,529 ->
# 267,647 bytes) and so turned that constant fail-OPEN: a 0.3.0 session that
# ingested 50,722-76,469 tokens had loaded 66-99% of its engine and was scored
# ADMISSIBLE. That is the precise failure this floor exists to refuse, arriving
# silently and in the reassuring direction. A hardcoded size cannot survive a
# release, so the size is now read off the era the session actually ran.
CHARS_PER_TOKEN = 3.5

# Fallback sizes for engines no longer in the plugin cache. The cache is the
# primary source; this table is only consulted when a version has been evicted.
# Add a row when a version is retired, never instead of reading the payload.
KNOWN_ENGINE_BYTES = {"0.2.0": 177529, "0.2.1": 177529, "0.3.0": 267647}

PLUGIN_CACHE = os.path.expanduser(
    "~/.claude/plugins/cache/claude-code-loop/dev-loop")
# The installed path carries its own version: .../dev-loop/<version>/skills/...
# This is the same path `classify` already requires to contain `/plugins/`, so
# era attribution costs no extra detection surface and inherits its correctness.
VERSION_IN_PATH = re.compile(r"/dev-loop/(\d+\.\d+\.\d+)/")


def engine_bytes(version):
    """One engine copy in bytes for `version`, preferring the payload on disk."""
    if not version:
        return None
    cached = os.path.join(PLUGIN_CACHE, version, "skills", "dev-loop",
                          "loop-engine.md")
    try:
        return os.path.getsize(cached)
    except OSError:
        return KNOWN_ENGINE_BYTES.get(version)


def _widest_known_engine():
    """The largest engine we can see, for use when the era is unknown."""
    sizes = list(KNOWN_ENGINE_BYTES.values())
    try:
        for v in os.listdir(PLUGIN_CACHE):
            b = engine_bytes(v)
            if b:
                sizes.append(b)
    except OSError:
        pass
    return max(sizes)


def floor_for(version):
    """Admissibility floor in tokens for a session that ran engine `version`.

    Default-deny on an unknown era: fall back to the WIDEST engine known, so an
    unattributable session must clear the strictest bar rather than the most
    permissive one. Sizing an unknown era off the smallest engine would recreate
    exactly the fail-open this function replaced.
    """
    return (engine_bytes(version) or _widest_known_engine()) / CHARS_PER_TOKEN


# The 0.2.0 floor, retained ONLY so a caller that imported the name still
# resolves. Nothing in this module consumes it: `--floor` parses its own value
# and `main()` passes None so the floor is derived per session. Do not wire it
# back into a default -- that is precisely the regression this comment records.
DEFAULT_FLOOR = 177529 / CHARS_PER_TOKEN

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


def tool_path(name, inp):
    """The path string `classify` inspects. The single extraction table."""
    if not isinstance(inp, dict):
        return ""
    if name == "Read":
        return str(inp.get("file_path", ""))
    if name in ("Grep", "Glob"):
        return str(inp.get("path", "")) + " " + str(inp.get("glob", ""))
    if name == "Bash":
        return strip_heredocs(str(inp.get("command", "")))
    return ""


def engine_version(name, inp):
    """Engine version this read loaded, from the installed path. None if absent."""
    m = VERSION_IN_PATH.search(tool_path(name, inp))
    return m.group(1) if m else None


def classify(name, inp, target="loop-engine.md", spills=None):
    """-> 'load' (plugin cache), 'tree' (working copy), or None.

    `spills` maps a spill-file path to the kind of the read that produced it, so
    the recovery reads inherit it.
    """
    spills = spills or {}
    if not isinstance(inp, dict):
        return None
    if name not in ("Read", "Grep", "Glob", "Bash"):
        return None
    # One extraction table, shared with `engine_version` below. Two copies drift
    # silently, and a drifted copy costs era detection -- which now sizes the
    # admissibility floor, so the failure is a corpus-wide one.
    path = tool_path(name, inp)
    if name == "Bash":
        if _NOT_A_READ.search(path) or not any(v in path for v in _READ_VERB):
            return None
    for sp, kind in spills.items():
        if sp and sp in path:
            # A spill path carries no version, so it contributes no era evidence.
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


def profile(path, target="loop-engine.md", kinds=("load",), floor=None):
    """`floor=None` derives the admissibility floor from the engine version this
    session actually loaded. Pass a number to override (the `--floor` flag)."""
    turns, order, tools = {}, [], {}
    pending, arrivals = [], {}
    spills, kind_counts = {}, {}
    versions = {}
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
                    if kind == "load":
                        v = engine_version(name, inp)
                        if v:
                            versions[v] = versions.get(v, 0) + 1
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

    # An era mixed within one session (a re-install mid-run) is scored against
    # the WIDEST engine seen, never the average: a session that straddles a
    # release did not fully load either engine, and averaging would admit it.
    era = max(versions, key=lambda v: (engine_bytes(v) or 0)) if versions else None
    if floor is None:
        floor = floor_for(era)

    return {
        "path": path, "turns": len(order), "compactions": compactions,
        "era": era, "eras_seen": dict(versions),
        "floor": floor, "admissible": ingested >= floor,
        "reads": reads, "by_tool": by_tool, "kind_counts": kind_counts,
        "ingested": ingested, "calib": calib, "spills": len(spills),
        "peak_ctx": max(ctx), "processed": sum(ctx),
        "billable_total": bill_total, "billable_in": sum(bill_in),
        "billable_out": sum(bill_out), "output_total": sum(out), "models": models,
    }


def render(p):
    n, ing, proc = p["turns"], p["ingested"], p["processed"]
    mixed = " MIXED:%s" % ",".join(sorted(p["eras_seen"])) if len(p["eras_seen"]) > 1 else ""
    print(f"\n=== {os.path.basename(p['path'])[:8]}   {n} parent turns, "
          f"{p['compactions']} compaction(s), {p['spills']} spill file(s)")
    # Printed unconditionally: the directory's standing rule is that a before/after
    # naming no engine version is not interpretable.
    print(f"  engine era              {(p['era'] or 'UNKNOWN -- floor defaults to the widest known engine'):>12}{mixed}")
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
    if not p["admissible"]:
        print(f"  !! INADMISSIBLE -- {ing:,.0f} tokens is below the floor of "
              f"{p['floor']:,.0f} (one engine copy).")
        print("  !! This is an UNMEASURED run, not a cheap one: either the engine did not "
              "fully load")
        print("  !! or the detector missed reads. EXCLUDE it -- do not average it in.")
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
    rt = p["models"]["PROP"][0]
    # P2c, turn-invariant. THE primary acceptance metric for the sharding epic --
    # it had no read-out here at all and was being hand-derived from two other
    # printed figures, which is how a wrong value reached the baseline document.
    print(f"  P2c  resident/processed {rt/proc:>12.1%}   <- turn-invariant; "
          f"the metric to accept on")


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("-")]
    kinds = ("load", "tree") if "--all-reads" in argv else ("load",)
    # None => profile() derives the floor from the era each session actually ran.
    # This read `DEFAULT_FLOOR` until 2026-09-12 and that made the per-session
    # floor unreachable from the CLI -- the only documented way to run the tool --
    # so the fix for the fail-open existed in the library and not in the product.
    # It survived a mutation battery because every mutation targeted `floor_for`,
    # and it survived a smoke test because that session was 0.2.1, where the old
    # constant and the derived floor are the same number. Keep it None.
    floor = None
    if "--floor" in argv:
        try:
            floor = float(argv[argv.index("--floor") + 1])
            args = [a for a in args if a != str(floor) and a != str(int(floor))]
        except (IndexError, ValueError):
            pass
    if not args:
        print(__doc__)
        return 1
    for path in args:
        p = profile(path, kinds=kinds, floor=floor)
        if p is None:
            print(f"\n=== {os.path.basename(path)}: no parent turns")
        else:
            render(p)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
