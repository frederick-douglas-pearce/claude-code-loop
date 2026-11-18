"""Build a per-assistant-turn timeline from a Claude Code session transcript.

Usage: python3 -I timeline.py <transcript.jsonl> <out_dir>
Writes <out_dir>/timeline.txt (full) and prints the three summaries.
"""
import json, sys, os, collections

path, out_dir = sys.argv[1], sys.argv[2]
os.makedirs(out_dir, exist_ok=True)

lines = []
with open(path) as f:
    for raw in f:
        try:
            lines.append(json.loads(raw))
        except Exception:
            pass


def block_text(content):
    """Flatten a message content (str or list of blocks) to text."""
    if content is None:
        return ''
    if isinstance(content, str):
        return content
    out = []
    for b in content:
        if isinstance(b, dict):
            t = b.get('type')
            if t == 'text':
                out.append(b.get('text', ''))
            elif t == 'tool_result':
                out.append(block_text(b.get('content')))
            elif t == 'thinking':
                out.append(b.get('thinking', ''))
            elif t == 'tool_use':
                out.append(json.dumps(b.get('input', {})))
            else:
                out.append(json.dumps(b))
        else:
            out.append(str(b))
    return '\n'.join(out)


def summarize_input(name, inp):
    if not isinstance(inp, dict):
        return str(inp)[:60]
    if name == 'Bash':
        s = inp.get('command', '')
    elif name in ('Read', 'Write', 'Edit', 'NotebookEdit'):
        s = inp.get('file_path', '')
        if name == 'Write':
            s += ' (%d chars)' % len(inp.get('content', ''))
        if name == 'Edit':
            s += ' (old %d/new %d)' % (len(inp.get('old_string', '')), len(inp.get('new_string', '')))
    elif name == 'Agent':
        s = '[%s] %s' % (inp.get('subagent_type', '?'), inp.get('description', ''))
    elif name in ('Grep', 'Glob'):
        s = '%s in %s' % (inp.get('pattern', ''), inp.get('path', ''))
    elif name == 'Skill':
        s = '%s %s' % (inp.get('skill', ''), inp.get('args', ''))
    elif name == 'SendMessage':
        s = '%s: %s' % (inp.get('to', inp.get('recipient', '')), str(inp.get('message', ''))[:50])
    elif name == 'TaskOutput' or name == 'Monitor':
        s = json.dumps(inp)
    else:
        s = json.dumps(inp)
    s = s.replace('\n', ' ')
    return s[:60]


# ---- group assistant blocks into API turns by message.id ----
turns = []  # list of dicts
turn_by_msgid = {}
tool_use_to_turn = {}
for i, o in enumerate(lines):
    if o.get('type') != 'assistant':
        continue
    m = o['message']
    mid = m.get('id') or o.get('requestId')
    if mid not in turn_by_msgid:
        t = {
            'idx': len(turns) + 1,
            'line': i,
            'msgid': mid,
            'ts': o.get('timestamp'),
            'usage': m.get('usage', {}),
            'tools': [],  # (tool_use_id, name, summary, input)
            'text': '',
            'thinking': '',
            'uuid': o.get('uuid'),
            'parentUuid': o.get('parentUuid'),
            'attributionSkill': o.get('attributionSkill'),
            'attributionPlugin': o.get('attributionPlugin'),
            'stop_reason': m.get('stop_reason'),
        }
        turns.append(t)
        turn_by_msgid[mid] = t
    t = turn_by_msgid[mid]
    # usage: keep the max-cumulative (later block lines usually carry the final usage)
    u = m.get('usage', {})
    if u and (u.get('output_tokens', 0) >= t['usage'].get('output_tokens', 0)):
        t['usage'] = u
    for b in m.get('content', []) or []:
        if not isinstance(b, dict):
            continue
        if b['type'] == 'tool_use':
            t['tools'].append((b['id'], b['name'], summarize_input(b['name'], b.get('input')), b.get('input')))
            tool_use_to_turn[b['id']] = t
        elif b['type'] == 'text':
            t['text'] += b.get('text', '')
        elif b['type'] == 'thinking':
            t['thinking'] += b.get('thinking', '')

# ---- tool results ----
results = {}  # tool_use_id -> (chars, preview, line idx, toolUseResult summary)
for i, o in enumerate(lines):
    if o.get('type') != 'user':
        continue
    m = o.get('message', {})
    c = m.get('content')
    if not isinstance(c, list):
        continue
    for b in c:
        if isinstance(b, dict) and b.get('type') == 'tool_result':
            txt = block_text(b.get('content'))
            tur = o.get('toolUseResult')
            tur_len = len(json.dumps(tur)) if tur is not None else 0
            results[b['tool_use_id']] = (len(txt), txt[:120].replace('\n', ' '), i, tur_len, bool(b.get('is_error')))

# ---- human prompts, compactions, system lines ----
human = []
compact = []
for i, o in enumerate(lines):
    if o.get('type') == 'user':
        m = o.get('message', {})
        c = m.get('content')
        is_tool = isinstance(c, list) and any(isinstance(b, dict) and b.get('type') == 'tool_result' for b in c)
        if not is_tool and not o.get('isMeta'):
            human.append((i, o.get('timestamp'), block_text(c)[:200].replace('\n', ' '), o.get('isCompactSummary', False)))
        if o.get('isCompactSummary'):
            compact.append((i, o.get('timestamp'), len(block_text(c))))
    if o.get('type') == 'system' and o.get('compactMetadata'):
        compact.append((i, o.get('timestamp'), 'system:' + json.dumps(o.get('compactMetadata'))[:300]))


def ctx(u):
    return (u.get('input_tokens', 0) or 0) + (u.get('cache_read_input_tokens', 0) or 0) + (u.get('cache_creation_input_tokens', 0) or 0)


# map line index -> nearest turn index (for human prompts)
def turn_after_line(li):
    for t in turns:
        if t['line'] > li:
            return t['idx']
    return None


# ---- write full timeline ----
tl = os.path.join(out_dir, 'timeline.txt')
with open(tl, 'w') as f:
    f.write('idx\tts\tcontext\tin\tcache_read\tcache_create\tout\ttools -> result_chars\n')
    prev = None
    for t in turns:
        u = t['usage']
        c = ctx(u)
        tools_s = []
        for (tid, name, summ, inp) in t['tools']:
            r = results.get(tid)
            rc = r[0] if r else -1
            err = ' ERR' if (r and r[4]) else ''
            tools_s.append('%s(%s) -> %d%s' % (name, summ, rc, err))
        drop = ''
        if prev and prev > 0 and c < prev * 0.7:
            drop = '  <<< DROP %.0f%%' % (100 * (1 - c / prev))
        f.write('%d\t%s\t%d\t%d\t%d\t%d\t%d\t%s%s\n' % (
            t['idx'], t['ts'], c, u.get('input_tokens', 0), u.get('cache_read_input_tokens', 0),
            u.get('cache_creation_input_tokens', 0), u.get('output_tokens', 0),
            ' | '.join(tools_s) if tools_s else ('[text %d chars] ' % len(t['text'])) + t['text'][:80].replace('\n', ' '),
            drop))
        prev = c
    f.write('\n\n=== HUMAN PROMPTS (line, ts, before turn, text) ===\n')
    for (li, ts, txt, cs) in human:
        f.write('%d\t%s\tbefore turn %s\t%s%s\n' % (li, ts, turn_after_line(li), '[COMPACT SUMMARY] ' if cs else '', txt))

print('turns:', len(turns), ' tool_uses:', len(tool_use_to_turn), ' results:', len(results))
print('first/last ts:', turns[0]['ts'], turns[-1]['ts'])
tot_in = sum(t['usage'].get('input_tokens', 0) for t in turns)
tot_cr = sum(t['usage'].get('cache_read_input_tokens', 0) for t in turns)
tot_cc = sum(t['usage'].get('cache_creation_input_tokens', 0) for t in turns)
tot_out = sum(t['usage'].get('output_tokens', 0) for t in turns)
print('totals: input=%d cache_read=%d cache_create=%d output=%d  sum_ctx=%d' % (tot_in, tot_cr, tot_cc, tot_out, tot_in + tot_cr + tot_cc))
print('peak ctx: %d at turn %d' % max((ctx(t['usage']), t['idx']) for t in turns))
print('wrote', tl)

# ---- (a) 25 largest tool results ----
print('\n=== (a) 25 LARGEST TOOL RESULTS (chars, turn, tool, input, tur_json_len) ===')
rows = []
for tid, (n, prev_, li, turlen, err) in results.items():
    t = tool_use_to_turn.get(tid)
    name = summ = '?'
    if t:
        for (xid, xn, xs, xi) in t['tools']:
            if xid == tid:
                name, summ = xn, xs
    rows.append((n, t['idx'] if t else -1, name, summ, turlen, err))
rows.sort(reverse=True)
for r in rows[:25]:
    print('%8d  turn %3d  %-12s %-60s tur=%d%s' % (r[0], r[1], r[2], r[3], r[4], ' ERR' if r[5] else ''))
print('total tool result chars: %d' % sum(r[0] for r in rows))
by_tool = collections.Counter()
cnt_tool = collections.Counter()
for r in rows:
    by_tool[r[2]] += r[0]
    cnt_tool[r[2]] += 1
print('result chars by tool:', ', '.join('%s=%d(n=%d)' % (k, v, cnt_tool[k]) for k, v in by_tool.most_common()))

# ---- (b) context drops >30% ----
print('\n=== (b) CONTEXT DROPS >30% ===')
prev = None
for t in turns:
    c = ctx(t['usage'])
    if prev and prev > 0 and c < prev * 0.7:
        print('turn %d  %s  %d -> %d (-%.0f%%)  tools=%s' % (t['idx'], t['ts'], prev, c, 100 * (1 - c / prev), [x[1] for x in t['tools']]))
    prev = c
print('compaction markers:', compact)

# ---- (c) Agent launches ----
print('\n=== (c) AGENT LAUNCHES (turn, subagent_type, description, prompt_chars, return_chars) ===')
for t in turns:
    for (tid, name, summ, inp) in t['tools']:
        if name == 'Agent':
            r = results.get(tid)
            print('turn %3d  ctx=%7d  [%s] %-45s prompt=%6d  return=%s%s' % (
                t['idx'], ctx(t['usage']), inp.get('subagent_type', '?'), inp.get('description', '')[:45],
                len(inp.get('prompt', '')), r[0] if r else 'none', (' isolation=' + inp['isolation']) if inp.get('isolation') else ''))

# ---- tool counts ----
print('\n=== TOOL USE COUNTS ===')
tc = collections.Counter(name for t in turns for (_, name, _, _) in t['tools'])
print(dict(tc.most_common()))

# dump structures for other scripts
with open(os.path.join(out_dir, 'turns.json'), 'w') as f:
    json.dump([{'idx': t['idx'], 'line': t['line'], 'ts': t['ts'], 'ctx': ctx(t['usage']), 'usage': t['usage'],
                'tools': [(a, b, c, d) for (a, b, c, d) in t['tools']], 'text': t['text'], 'thinking': t['thinking'],
                'results': [results.get(a, (None,))[0] for (a, b, c, d) in t['tools']]} for t in turns], f)
