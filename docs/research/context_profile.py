#!/usr/bin/env python3
"""Profile PARENT-THREAD context growth across a Claude Code session transcript.

Usage:
    python3 docs/research/context_profile.py <session.jsonl> [<session.jsonl> ...]
    python3 docs/research/context_profile.py --top 12 <session.jsonl>

Answers: how full was the parent context when the session ended, what was it
carrying, and which tool put it there.

Field semantics follow `claude-code-sessions/reference/data-dictionary.md`. Three
of its warnings are load-bearing here and each is handled below:

  * **Streaming emits several `assistant` lines per logical turn**, sharing one
    `message.id`, each a running snapshot rather than an increment. Summing them
    double-counts (~2x on real corpora). We group by `message.id` and keep the
    record with the greatest `output_tokens`, taking all four usage fields from
    THAT record -- never a per-field max across records.
  * **Context size and tokens-processed are different quantities.** A single
    turn's usage gives context size; summing across turns gives what you were
    billed for, because each turn re-reads the accumulated prefix. Both are
    reported, separately and labelled.
  * **`isSidechain: true` marks subagent turns.** They have their own context
    windows and must not be mixed into the parent's. We report the parent only,
    and count sidechain turns separately.

Attribution method: context(i) - context(i-1) is the exact number of tokens that
entered the parent between two turns. Subtract the previous turn's own
`output_tokens` and the remainder is what the tool results added. Where a turn
called several tools, the remainder is split across them in proportion to their
serialized result length. So per-tool figures are exact in aggregate and
approximate per call -- which is the right way round for "where does it go".

Stdlib only.
"""
import json
import os
import sys
from collections import defaultdict

CTX_FIELDS = ("input_tokens", "cache_read_input_tokens",
              "cache_creation_input_tokens")


def load(path):
    """Yield parsed records, skipping unparseable lines."""
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def blocks(rec):
    msg = rec.get("message") or {}
    content = msg.get("content")
    return content if isinstance(content, list) else []


def profile(path):
    turns = {}          # message.id -> best assistant record
    order = []          # message.id in first-seen order
    tool_names = {}     # tool_use_id -> tool name
    results = defaultdict(list)   # message.id of NEXT turn -> [(tool, chars)]
    pending = []        # tool results seen since the last assistant turn
    sidechain = 0

    for rec in load(path):
        if rec.get("isSidechain"):
            if rec.get("type") == "assistant":
                sidechain += 1
            continue
        rtype = rec.get("type")
        if rtype == "assistant":
            msg = rec.get("message") or {}
            mid = msg.get("id")
            if not mid:
                continue
            usage = msg.get("usage") or {}
            prev = turns.get(mid)
            if prev is None:
                order.append(mid)
            # Keep the most complete snapshot of this logical turn.
            if prev is None or usage.get("output_tokens", 0) > prev["usage"].get("output_tokens", 0):
                turns[mid] = {"usage": usage, "ts": rec.get("timestamp", "")}
            for b in blocks(rec):
                if isinstance(b, dict) and b.get("type") == "tool_use":
                    tool_names[b.get("id")] = b.get("name", "?")
            if pending:
                results[mid] = pending
                pending = []
        elif rtype == "user":
            for b in blocks(rec):
                if isinstance(b, dict) and b.get("type") == "tool_result":
                    name = tool_names.get(b.get("tool_use_id"), "?")
                    payload = rec.get("toolUseResult", b.get("content"))
                    try:
                        size = len(json.dumps(payload, default=str))
                    except (TypeError, ValueError):
                        size = len(str(payload))
                    pending.append((name, size))

    if not order:
        return None

    ctx = [sum(turns[m]["usage"].get(f, 0) or 0 for f in CTX_FIELDS) for m in order]
    out = [turns[m]["usage"].get("output_tokens", 0) or 0 for m in order]

    attribution = defaultdict(int)
    unattributed = 0
    for i in range(1, len(order)):
        delta = ctx[i] - ctx[i - 1]
        if delta <= 0:
            continue          # compaction, or a cache boundary; not growth
        added = max(0, delta - out[i - 1])
        calls = results.get(order[i], [])
        total = sum(sz for _, sz in calls)
        if not calls or total == 0:
            unattributed += added
            continue
        for name, sz in calls:
            attribution[name] += int(added * sz / total)

    processed = sum(
        sum(turns[m]["usage"].get(f, 0) or 0 for f in CTX_FIELDS + ("output_tokens",))
        for m in order
    )
    return {
        "path": path,
        "turns": len(order),
        "sidechain_turns": sidechain,
        "final_ctx": ctx[-1],
        "peak_ctx": max(ctx),
        "processed": processed,
        "attribution": dict(attribution),
        "unattributed": unattributed,
        "output_total": sum(out),
    }


def render(p, top):
    print(f"\n=== {os.path.basename(p['path'])}")
    print(f"  parent turns        {p['turns']}   (+{p['sidechain_turns']} subagent turns, separate windows)")
    print(f"  context at end      {p['final_ctx']:>9,}")
    print(f"  peak context        {p['peak_ctx']:>9,}")
    print(f"  tokens processed    {p['processed']:>9,}   (billing basis; re-reads the prefix each turn)")
    print(f"  own output          {p['output_total']:>9,}")
    items = sorted(p["attribution"].items(), key=lambda kv: -kv[1])
    grand = sum(p["attribution"].values()) + p["unattributed"]
    if grand:
        print(f"  --- what entered the parent, by source ({grand:,} tokens) ---")
        for name, tok in items[:top]:
            print(f"    {name:<28}{tok:>9,}  {tok / grand:>5.1%}")
        rest = sum(t for _, t in items[top:])
        if rest:
            print(f"    {'(' + str(len(items) - top) + ' more)':<28}{rest:>9,}  {rest / grand:>5.1%}")
        if p["unattributed"]:
            print(f"    {'(unattributed)':<28}{p['unattributed']:>9,}  {p['unattributed'] / grand:>5.1%}")


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("-")]
    top = 10
    if "--top" in argv:
        try:
            top = int(argv[argv.index("--top") + 1])
            args = [a for a in args if a != str(top)]
        except (IndexError, ValueError):
            pass
    if not args:
        print(__doc__)
        return 1
    for path in args:
        p = profile(path)
        if p is None:
            print(f"\n=== {os.path.basename(path)}: no parent assistant turns")
            continue
        render(p, top)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
