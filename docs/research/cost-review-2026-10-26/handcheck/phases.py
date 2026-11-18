"""Phase markers, human gates, Bash categorization, agent returns, cost-state.

Usage: python3 -I phases.py <transcript.jsonl> <turns.json>
"""
import json, sys, re, collections

path, turns_path = sys.argv[1], sys.argv[2]
turns = json.load(open(turns_path))
lines = [json.loads(l) for l in open(path)]

# ---- cost-state ----
for o in lines:
    if o.get('type') == 'cost-state':
        print('=== COST-STATE ===')
        print(json.dumps({k: v for k, v in o.items() if k != 'modelUsage'}, indent=None)[:600])
        print('modelUsage:', json.dumps(o.get('modelUsage'))[:800])

# ---- compaction summary head ----
for o in lines:
    if o.get('type') == 'user' and o.get('isCompactSummary'):
        c = o['message']['content']
        txt = c if isinstance(c, str) else ''.join(b.get('text', '') for b in c if isinstance(b, dict))
        print('\n=== COMPACT SUMMARY (len %d) head ===' % len(txt))
        print(txt[:1800])

# ---- attachments: what kinds, and task-notification returns ----
print('\n=== ATTACHMENT KINDS ===')
kinds = collections.Counter()
for o in lines:
    if o.get('type') == 'attachment':
        a = o.get('attachment', {})
        kinds[a.get('type')] += 1
print(dict(kinds))

# ---- agent returns: user lines containing <task-notification>, and attachments ----
print('\n=== AGENT RETURNS (task-notification lines: line, ts, task-id, chars of text, status) ===')
def text_of(o):
    m = o.get('message', {})
    c = m.get('content')
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return '\n'.join(b.get('text', '') if isinstance(b, dict) and b.get('type') == 'text' else '' for b in c)
    return ''
tn_total = 0
for i, o in enumerate(lines):
    if o.get('type') in ('user', 'attachment'):
        if o.get('type') == 'attachment':
            a = o.get('attachment', {})
            txt = json.dumps(a)
        else:
            txt = text_of(o)
        if '<task-notification>' in txt or 'task-notification' in txt:
            tid = re.search(r'<task-id>([^<]+)</task-id>', txt)
            st = re.search(r'<status>([^<]+)</status>', txt)
            summ = re.search(r'<summary>(.{0,80})', txt, re.S)
            tn_total += len(txt)
            print('%5d %s %s %-20s %6d chars status=%s  %s' % (i, o.get('type'), o.get('timestamp'), tid.group(1) if tid else '?', len(txt), st.group(1) if st else '?', (summ.group(1).replace('\n', ' ') if summ else '')[:80]))
print('task-notification total chars:', tn_total)

# ---- attachment sizes by type (what the model actually saw) ----
print('\n=== ATTACHMENT CHARS BY TYPE ===')
asz = collections.Counter()
for o in lines:
    if o.get('type') == 'attachment':
        a = o.get('attachment', {})
        asz[a.get('type')] += len(json.dumps(a))
print(dict(asz.most_common()))

# ---- human gates: AskUserQuestion ----
print('\n=== ASKUSERQUESTION (turn, ctx, question head) ===')
for t in turns:
    for (tid, name, summ, inp) in t['tools']:
        if name == 'AskUserQuestion':
            qs = inp.get('questions', [])
            for q in qs:
                print('turn %3d ctx=%7d  %s' % (t['idx'], t['ctx'], q.get('question', '')[:200].replace('\n', ' ')))

# ---- phase markers: first occurrence per pattern, split by invocation ----
PATTERNS = [
    ('step 0', r'\bstep 0\b'), ('step 1', r'\bstep 1\b'), ('step 2', r'\bstep 2\b'), ('step 3', r'\bstep 3\b'),
    ('step 4', r'\bstep 4\b'), ('step 5', r'\bstep 5\b'), ('plan gate', r'plan[- ]gate'), ('step 6', r'\bstep 6\b'),
    ('step 7', r'\bstep 7\b'), ('step 8', r'\bstep 8\b'), ('code review', r'code[- ]review'),
    ('round 1', r'\bround[- ]1\b'), ('round 2', r'\bround[- ]2\b'), ('round 3', r'\bround[- ]3\b'), ('round 4', r'\bround[- ]4\b'),
    ('step 9', r'\bstep 9\b'), ('step 10', r'\bstep 10\b'), ('acceptance', r'acceptance'), ('AC-verifier', r'AC[- ]verifier'),
    ('mutation', r'mutation'), ('step 11', r'\bstep 11\b'), ('merge gate', r'merge[- ]gate'), ('merge', r'\bmerge\b'),
    ('step 12', r'\bstep 12\b'), ('Budget:', r'- Budget:'), ('in-acceptance', r'in-acceptance'), ('gh pr merge', r'gh pr merge'),
    ('gh pr create', r'gh pr create'), ('git commit', r'git commit'), ('git push', r'git push'),
    ('CI', r'gh run|gh pr checks|workflow'), ('F-finding', r'\bF\d{2,3}\b'),
]
def turn_blob(t):
    return t['text'] + '\n' + t['thinking'] + '\n' + '\n'.join(json.dumps(x[3]) for x in t['tools'])
blobs = [(t['idx'], turn_blob(t)) for t in turns]
for (lo, hi, label) in [(1, 246, 'INVOCATION 1 (#386)'), (247, 423, 'INVOCATION 2 (#389)')]:
    print('\n=== PHASE MARKERS %s: first turn, count of turns mentioning ===' % label)
    for name, pat in PATTERNS:
        rx = re.compile(pat, re.I)
        hits = [idx for idx, b in blobs if lo <= idx <= hi and rx.search(b)]
        if hits:
            print('  %-14s first=%3d  last=%3d  n=%d' % (name, hits[0], hits[-1], len(hits)))

# ---- Bash categorization ----
print('\n=== BASH COMMANDS BY CATEGORY (count, total result chars, example) ===')
def cat(cmd):
    c = cmd.strip()
    c1 = re.sub(r'^cd\s+\S+\s*&&\s*', '', c)
    first = c1.split()[0] if c1.split() else '?'
    if first == 'gh':
        return 'gh ' + ' '.join(c1.split()[1:3])
    if first == 'git':
        return 'git ' + c1.split()[1] if len(c1.split()) > 1 else 'git'
    if first in ('sed', 'grep', 'cat', 'head', 'tail', 'awk', 'wc', 'ls', 'find', 'rg'):
        tgt = 'progress.md' if 'progress.md' in c else ('queue.md' if 'queue.md' in c else ('plan.md' if '.plan.md' in c else ('plugin' if 'plugins/cache' in c else 'other')))
        return first + ' [' + tgt + ']'
    if first == 'python3' or first == 'python' or 'uv run' in c1[:20]:
        if 'mutate_verify' in c: return 'python mutate_verify'
        if 'pytest' in c or 'unittest' in c: return 'tests'
        return 'python other'
    if first in ('uv', 'pytest', 'ruff', 'mypy', 'npm', 'npx'):
        return first + ' ' + (c1.split()[1] if len(c1.split()) > 1 else '')
    return first
rows = collections.defaultdict(lambda: [0, 0, ''])
for t in turns:
    for (tid, name, summ, inp), rc in zip(t['tools'], t['results']):
        if name == 'Bash':
            k = cat(inp.get('command', ''))
            rows[k][0] += 1
            rows[k][1] += (rc or 0)
            if not rows[k][2]:
                rows[k][2] = inp.get('command', '').replace('\n', ' ')[:70]
for k, v in sorted(rows.items(), key=lambda kv: -kv[1][1]):
    print('%3d  %7d  %-28s %s' % (v[0], v[1], k, v[2]))

# ---- per-invocation turn/time/ctx accounting ----
print('\n=== PER-TURN-RANGE ACCOUNTING ===')
def acct(lo, hi, label):
    sel = [t for t in turns if lo <= t['idx'] <= hi]
    ctx_sum = sum(t['ctx'] for t in sel)
    out = sum(t['usage'].get('output_tokens', 0) for t in sel)
    cc = sum(t['usage'].get('cache_creation_input_tokens', 0) for t in sel)
    print('%-32s turns=%3d  ctx_sum=%11d  cache_create=%9d  out=%7d  ctx %7d -> %7d  %s .. %s' % (
        label, len(sel), ctx_sum, cc, out, sel[0]['ctx'], sel[-1]['ctx'], sel[0]['ts'][5:16], sel[-1]['ts'][5:16]))
acct(1, 423, 'ALL')
acct(1, 246, 'inv1 #386')
acct(247, 423, 'inv2 #389')
