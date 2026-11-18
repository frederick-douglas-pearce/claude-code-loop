"""Full Budget lines, engine read params, post-compaction text, human-wait gaps.

Usage: python3 -I details.py <turns.json>
"""
import json, sys, re, datetime
turns = json.load(open(sys.argv[1]))

print('=== FULL BUDGET LINES ===')
for t in turns:
    for (tid, name, summ, inp) in t['tools']:
        if name == 'Bash':
            for m in re.finditer(r'^\s*- Budget:.*$', inp.get('command', ''), re.M):
                print('turn %d: %s\n' % (t['idx'], m.group(0).strip()))

print('=== ENGINE READ PARAMS (turn, path tail, offset, limit, result chars) ===')
for t in turns:
    for (tid, name, summ, inp), rc in zip(t['tools'], t['results']):
        if name == 'Read' and 'plugins/cache' in inp.get('file_path', ''):
            p = inp['file_path']
            m = re.search(r'dev-loop/([^/]+)/(.*)$', p)
            print('turn %3d  v=%s  %-45s off=%-6s lim=%-6s -> %d' % (t['idx'], m.group(1) if m else '?', m.group(2) if m else p, inp.get('offset', '-'), inp.get('limit', '-'), rc or 0))

print('\n=== TEXT/THINKING AROUND COMPACTION (turns 346-352) ===')
for t in turns:
    if 346 <= t['idx'] <= 352:
        blob = (t['thinking'] + ' || ' + t['text']).replace('\n', ' ')
        print('turn %d [%s]: %s' % (t['idx'], ','.join(x[1] for x in t['tools']), blob[:700]))
        print()

print('=== TEXT AT TURNS 1-4 (what it read and why) ===')
for t in turns:
    if t['idx'] <= 4:
        blob = (t['thinking'] + ' || ' + t['text']).replace('\n', ' ')
        print('turn %d [%s]: %s' % (t['idx'], ','.join(x[1] + ':' + x[2][:30] for x in t['tools']), blob[:500]))
        print()

print('=== GAPS > 20 min BETWEEN CONSECUTIVE TURNS (human waits / long agents) ===')
def ts(s):
    return datetime.datetime.strptime(s[:19], '%Y-%m-%dT%H:%M:%S')
tot_gap = datetime.timedelta()
for a, b in zip(turns, turns[1:]):
    d = ts(b['ts']) - ts(a['ts'])
    if d.total_seconds() > 1200:
        tot_gap += d
        print('turn %3d -> %3d  %s  (after: %s)' % (a['idx'], b['idx'], d, ','.join(x[1] + ':' + x[2][:30] for x in a['tools'])[:100]))
span = ts(turns[-1]['ts']) - ts(turns[0]['ts'])
print('session span %s ; gaps>20min total %s ; active %s' % (span, tot_gap, span - tot_gap))

print('\n=== IMPLEMENT PHASE inv1 (turns 46-133): tool sequence summary ===')
import collections
seq = collections.Counter()
for t in turns:
    if 46 <= t['idx'] <= 133:
        for (tid, name, summ, inp) in t['tools']:
            c = inp.get('command', '') if name == 'Bash' else ''
            k = name
            if name == 'Bash':
                c2 = re.sub(r'^(cd\s+\S+)\s*(&&|;)\s*', '', c.strip())
                w = c2.split()
                k = 'Bash:' + (w[0] if w else '?')
                if 'pytest' in c: k = 'Bash:pytest'
                elif 'python3 - <<' in c or "python3 -c" in c: k = 'Bash:python-heredoc'
                elif w and w[0] == 'git': k = 'Bash:git ' + (w[1] if len(w) > 1 else '')
            seq[k] += 1
print(dict(seq.most_common(20)))
print('\n=== IMPLEMENT PHASE inv2 (turns 262-307) ===')
seq = collections.Counter()
for t in turns:
    if 262 <= t['idx'] <= 307:
        for (tid, name, summ, inp) in t['tools']:
            c = inp.get('command', '') if name == 'Bash' else ''
            k = name
            if name == 'Bash':
                c2 = re.sub(r'^(cd\s+\S+)\s*(&&|;)\s*', '', c.strip())
                w = c2.split()
                k = 'Bash:' + (w[0] if w else '?')
                if 'pytest' in c: k = 'Bash:pytest'
                elif 'python3 - <<' in c or "python3 -c" in c: k = 'Bash:python-heredoc'
                elif w and w[0] == 'git': k = 'Bash:git ' + (w[1] if len(w) > 1 else '')
            seq[k] += 1
print(dict(seq.most_common(20)))

# how were source edits made in implement phases? count Edit/Write vs python heredoc writes to src/tests
print('\n=== HOW CODE WAS WRITTEN (Edit/Write tool vs python/cat heredoc into src|tests|dashboard|docs) ===')
cnt = collections.Counter()
chars = collections.Counter()
for t in turns:
    for (tid, name, summ, inp) in t['tools']:
        if name in ('Edit', 'Write'):
            cnt[name + ' tool'] += 1
            chars[name + ' tool'] += len(inp.get('content', inp.get('new_string', '')))
        elif name == 'Bash':
            c = inp.get('command', '')
            if ('python3 - <<' in c or 'cat >' in c or 'cat >>' in c) and re.search(r"(src/|tests/|dashboard/|docs/|\.md'|\.py')", c):
                cnt['Bash heredoc write'] += 1
                chars['Bash heredoc write'] += len(c)
print(dict(cnt), dict(chars))
print('total Bash command chars:', sum(len(inp.get('command', '')) for t in turns for (_, n, _, inp) in t['tools'] if n == 'Bash'))
print('total Agent prompt chars:', sum(len(inp.get('prompt', '')) for t in turns for (_, n, _, inp) in t['tools'] if n == 'Agent'))
print('total tool_use input chars:', sum(len(json.dumps(inp)) for t in turns for (_, n, _, inp) in t['tools']))
