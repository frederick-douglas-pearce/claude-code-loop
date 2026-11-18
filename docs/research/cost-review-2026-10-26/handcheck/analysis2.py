"""Second pass: fixed Bash categorization, per-phase accounting, context jumps, journal heredocs.

Usage: python3 -I analysis2.py <transcript.jsonl> <turns.json> <out_dir>
"""
import json, sys, re, collections, os
path, turns_path, out_dir = sys.argv[1], sys.argv[2], sys.argv[3]
turns = json.load(open(turns_path))
T = {t['idx']: t for t in turns}

# ---- Bash categorization (strip leading cd / VAR= prefixes) ----
def norm(cmd):
    c = cmd.strip()
    for _ in range(4):
        c2 = re.sub(r'^(cd\s+\S+|[A-Z_]+=\S+)\s*(&&|;|\n)\s*', '', c)
        if c2 == c:
            break
        c = c2
    return c
def cat(cmd):
    c = norm(cmd)
    w = c.split()
    first = w[0] if w else '?'
    tgt = ''
    for k in ('progress.md', 'queue.md', '.plan.md', 'plugins/cache', '/tasks/', 'decisions.md', 'glossary', 'tests/', 'dashboard/', 'loop.config'):
        if k in c:
            tgt = k; break
    if first == 'gh':
        return 'gh ' + ' '.join(w[1:3])
    if first == 'git':
        return 'git ' + (w[1] if len(w) > 1 else '')
    if first in ('sed', 'grep', 'cat', 'head', 'tail', 'awk', 'wc', 'ls', 'find', 'rg', 'diff', 'python3', 'python', 'uv', 'pytest', 'unshare', 'docker', 'curl', 'for', 'echo', 'printf', 'mkdir', 'cp', 'mv', 'rm', 'test', 'true', 'sleep', 'tee', 'sort', 'cut', 'tr', 'xargs', 'jq', 'date', 'nl'):
        if first in ('python3', 'python', 'uv'):
            if 'mutate_verify' in c: return 'mutate_verify'
            if 'pytest' in c or 'unittest' in c: return 'tests (pytest)'
            if 'usvote' in c: return 'uv run usvote'
            return first + ' other'
        if first == 'cat' and ('<<' in c and '>>' in c): return 'cat >> (journal/ledger append) [%s]' % tgt
        return first + (' [%s]' % tgt if tgt else '')
    return first[:20]
rows = collections.defaultdict(lambda: [0, 0, '', 0])
for t in turns:
    for (tid, name, summ, inp), rc in zip(t['tools'], t['results']):
        if name == 'Bash':
            k = cat(inp.get('command', ''))
            rows[k][0] += 1; rows[k][1] += (rc or 0); rows[k][3] += len(inp.get('command', ''))
            if not rows[k][2]: rows[k][2] = norm(inp.get('command', '')).replace('\n', ' ')[:80]
print('=== BASH BY CATEGORY (n, result chars, cmd chars, example) ===')
for k, v in sorted(rows.items(), key=lambda kv: -kv[1][1])[:40]:
    print('%3d  %7d  %6d  %-42s %s' % (v[0], v[1], v[3], k, v[2]))

# ---- phase boundaries (hand-set from markers/gates) ----
PHASES = [
    (1, 3, 'inv1 engine load (SKILL+core+units)'),
    (4, 44, 'inv1 steps 0-5 select/route/plan/scope/architect'),
    (45, 45, 'inv1 plan gate (AskUser)'),
    (46, 133, 'inv1 step 6-7 implement+commit+PR'),
    (134, 199, 'inv1 step 8 code review r1-r3 (+human at 151,182,194)'),
    (200, 202, 'inv1 step 9 security'),
    (203, 226, 'inv1 step 10 acceptance (ClassA+B, recheck)'),
    (227, 246, 'inv1 merge gate+merge+deploy+journal'),
    (247, 260, 'inv2 steps 0-5 select/plan/scope/architect'),
    (261, 261, 'inv2 plan gate (AskUser)'),
    (262, 307, 'inv2 step 6-7 implement+commit+PR'),
    (308, 340, 'inv2 step 8 code review r1-r2 (+human at 318,339)'),
    (341, 345, 'inv2 step 9 security (to 960k)'),
    (346, 351, 'inv2 COMPACTION + engine re-read'),
    (352, 404, 'inv2 step 10 acceptance (ClassA+B, recheck)'),
    (405, 417, 'inv2 merge gate+merge+deploy+journal'),
    (418, 423, 'user follow-up (comment edit)'),
]
print('\n=== PER-PHASE ACCOUNTING (turns, sum ctx Mtok, cache_create k, out k, ctx start->end, tool-result kchars) ===')
tot = sum(t['ctx'] for t in turns)
for lo, hi, label in PHASES:
    sel = [t for t in turns if lo <= t['idx'] <= hi]
    cs = sum(t['ctx'] for t in sel)
    cc = sum(t['usage'].get('cache_creation_input_tokens', 0) for t in sel)
    ou = sum(t['usage'].get('output_tokens', 0) for t in sel)
    rc = sum((r or 0) for t in sel for r in t['results'])
    print('%-58s n=%3d  %6.1fM (%4.1f%%)  cc=%5dk  out=%4dk  %6dk->%6dk  res=%4dk' % (
        label, len(sel), cs / 1e6, 100 * cs / tot, cc // 1000, ou // 1000, sel[0]['ctx'] // 1000, sel[-1]['ctx'] // 1000, rc // 1000))

# ---- context jumps ----
print('\n=== TOP 25 CONTEXT JUMPS (turn, delta, prev-turn out tok, prev-turn result chars, prev-turn tools) ===')
jumps = []
for t in turns:
    p = T.get(t['idx'] - 1)
    if not p: continue
    d = t['ctx'] - p['ctx']
    jumps.append((d, t['idx'], p['usage'].get('output_tokens', 0), sum((r or 0) for r in p['results']), [x[1] + '(' + x[2][:40] + ')' for x in p['tools']][:4]))
jumps.sort(reverse=True)
for d, idx, po, pr, tools in jumps[:25]:
    print('turn %3d  +%6d  prev_out=%5d prev_res=%6d  %s' % (idx, d, po, pr, '; '.join(tools)))
pos = sum(d for d, *_ in jumps if d > 0)
print('sum of positive deltas: %d  (turn1 ctx %d)' % (pos, turns[0]['ctx']))
# attribution: how much of growth is explained by output tokens vs tool results
sum_out = sum(t['usage'].get('output_tokens', 0) for t in turns)
sum_res = sum((r or 0) for t in turns for r in t['results'])
print('sum output tokens %d ; sum tool-result chars %d (~%d tok at 3.6c/t)' % (sum_out, sum_res, sum_res // 3.6))

# ---- task output-file reads by the parent ----
print('\n=== PARENT READS OF AGENT OUTPUT FILES (turn, tool, chars) ===')
tot_task = 0
for t in turns:
    for (tid, name, summ, inp), rc in zip(t['tools'], t['results']):
        s = json.dumps(inp)
        if '/tasks/' in s:
            tot_task += (rc or 0)
            print('turn %3d %-5s %6d  %s' % (t['idx'], name, rc or 0, summ))
print('total:', tot_task)

# ---- engine reads (plugin cache) ----
print('\n=== ENGINE/PLUGIN READS (turn, chars, path tail) ===')
eng = 0
for t in turns:
    for (tid, name, summ, inp), rc in zip(t['tools'], t['results']):
        if name == 'Read' and 'plugins/cache' in inp.get('file_path', ''):
            eng += rc or 0
            print('turn %3d %6d  %s' % (t['idx'], rc or 0, inp['file_path'].split('dev-loop/')[-1]))
print('total engine read chars:', eng)

# ---- journal heredocs: dump and grep for round/budget lines ----
jp = os.path.join(out_dir, 'journal_heredocs.txt')
with open(jp, 'w') as f:
    for t in turns:
        for (tid, name, summ, inp) in t['tools']:
            if name == 'Bash' and 'progress.md' in inp.get('command', '') and '<<' in inp.get('command', ''):
                f.write('\n##### turn %d\n%s\n' % (t['idx'], inp['command']))
            if name in ('Write', 'Edit') and ('progress.md' in inp.get('file_path', '') or 'queue.md' in inp.get('file_path', '')):
                f.write('\n##### turn %d %s %s\n%s\n' % (t['idx'], name, inp['file_path'], inp.get('content', inp.get('new_string', ''))))
print('wrote', jp)
print('\n=== JOURNAL LINES: round / Budget / Code-review / fix-induced / cap / recheck ===')
rx = re.compile(r'^.*(round|Budget:|Code-review:|fix-induced|the cap|re-?check|Rounds|waiver|Status:).*$', re.I | re.M)
for line in open(jp):
    if rx.match(line.rstrip('\n')) and not line.startswith('#####'):
        print('  ' + line.rstrip('\n')[:220])
    elif line.startswith('#####'):
        print(line.rstrip('\n'))

# ---- which tool result was persisted to tool-results/ (1.7MB) ----
print('\n=== PERSISTED TOOL RESULT REFERENCES ===')
for i, raw in enumerate(open(path)):
    for key in ('bq80ue8kx', 'bsoqmahpa', 'belhdt7i6', 'bn0f2kunk', 'bnmrhwr3u', 'bzk1zzhm1'):
        if key in raw:
            o = json.loads(raw)
            print(i, key, o.get('type'), (json.dumps(o)[:0]), re.search(r'.{0,120}' + key + r'.{0,120}', raw).group(0).replace('\\n', ' ')[:260])
