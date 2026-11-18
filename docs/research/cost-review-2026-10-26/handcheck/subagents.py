"""Per-subagent summary: description, assistant turns, sum ctx, peak ctx, output tokens, largest tool result.

Usage: python3 -I subagents.py <subagents_dir>
"""
import json, sys, os, glob
d = sys.argv[1]
rows = []
for jp in sorted(glob.glob(os.path.join(d, 'agent-*.jsonl'))):
    aid = os.path.basename(jp)[6:-6]
    meta = {}
    mp = os.path.join(d, 'agent-%s.meta.json' % aid)
    if os.path.exists(mp):
        meta = json.load(open(mp))
    turns = {}
    maxres = (0, '')
    nres = 0
    for raw in open(jp):
        try:
            o = json.loads(raw)
        except Exception:
            continue
        if o.get('type') == 'assistant':
            m = o['message']; mid = m.get('id')
            u = m.get('usage', {})
            c = (u.get('input_tokens', 0) or 0) + (u.get('cache_read_input_tokens', 0) or 0) + (u.get('cache_creation_input_tokens', 0) or 0)
            if mid not in turns or u.get('output_tokens', 0) >= turns[mid][1]:
                turns[mid] = (c, u.get('output_tokens', 0), u.get('cache_creation_input_tokens', 0))
        elif o.get('type') == 'user':
            cc = o.get('message', {}).get('content')
            if isinstance(cc, list):
                for b in cc:
                    if isinstance(b, dict) and b.get('type') == 'tool_result':
                        x = b.get('content')
                        n = len(x) if isinstance(x, str) else sum(len(y.get('text', '')) for y in x if isinstance(y, dict)) if isinstance(x, list) else 0
                        nres += 1
                        if n > maxres[0]:
                            maxres = (n, '')
    ctxs = [v[0] for v in turns.values()]
    rows.append((sum(ctxs), aid, meta.get('agentType', '?'), meta.get('description', os.path.basename(jp)), len(turns), max(ctxs) if ctxs else 0,
                 sum(v[1] for v in turns.values()), sum(v[2] for v in turns.values()), nres, maxres[0], os.path.getsize(jp)))
rows.sort(reverse=True)
print('%-10s %-17s %-16s %-40s %5s %8s %8s %7s %7s %5s %8s %8s' % ('sum_ctx', 'id', 'type', 'description', 'turns', 'peak', 'out', 'cc', 'nres', '', 'maxres', 'bytes'))
tot = 0
for r in rows:
    tot += r[0]
    print('%9.1fM %-17s %-16s %-40s %5d %8d %8d %7d %7d %5s %8d %8d' % (r[0] / 1e6, r[1], r[2], r[3][:40], r[4], r[5], r[6], r[7], r[8], '', r[9], r[10]))
print('subagents: %d  total sum_ctx: %.1fM  total turns: %d  total out: %d' % (len(rows), tot / 1e6, sum(r[4] for r in rows), sum(r[6] for r in rows)))
