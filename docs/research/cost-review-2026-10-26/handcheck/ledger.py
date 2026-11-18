"""Quote ledger lines written via tool_use inputs (Write content, Edit new_string, Bash heredocs).

Usage: python3 -I ledger.py <turns.json>
"""
import json, sys, re
turns = json.load(open(sys.argv[1]))
PAT = re.compile(r'^\s*- (Budget|Code-review|Status|Acceptance|Plan-gate|Review|Rounds|Mutation|AC-verifier|Gate|PR|Merged|Outcome)[^\n]*', re.M)
seen = set()
for t in turns:
    for (tid, name, summ, inp) in t['tools']:
        if name == 'Write':
            src = inp.get('content', '')
            where = 'Write ' + inp.get('file_path', '')
        elif name == 'Edit':
            src = inp.get('new_string', '')
            where = 'Edit ' + inp.get('file_path', '')
        elif name == 'Bash':
            src = inp.get('command', '')
            where = 'Bash'
        else:
            continue
        for m in PAT.finditer(src):
            line = m.group(0).strip()
            if line.startswith('- Budget:') or line.startswith('- Code-review:') or line.startswith('- Status:') or line.startswith('- Acceptance') or line.startswith('- Plan-gate') or line.startswith('- Mutation') or line.startswith('- AC'):
                key = (t['idx'], line)
                if key in seen:
                    continue
                seen.add(key)
                print('turn %3d  %-60s %s' % (t['idx'], where[-60:], line[:400]))

# Also: queue.md / progress.md writes - list which files were Written/Edited and sizes
print('\n=== LEDGER FILE WRITES/EDITS (turn, tool, path, size) ===')
for t in turns:
    for (tid, name, summ, inp) in t['tools']:
        if name in ('Write', 'Edit') and ('.claude/loop' in inp.get('file_path', '') or 'plan.md' in inp.get('file_path', '')):
            print('turn %3d %-5s %s  %d' % (t['idx'], name, inp.get('file_path', ''), len(inp.get('content', inp.get('new_string', '')))))
        if name == 'Bash' and ('progress.md' in inp.get('command', '') or 'queue.md' in inp.get('command', '')) and ('>>' in inp.get('command', '') or 'EOF' in inp.get('command', '') or 'python3' in inp.get('command', '')):
            print('turn %3d Bash  %s' % (t['idx'], inp.get('command', '').replace('\n', ' ')[:140]))

# Rows resumed? look for 'resume' / 'in flight' / 'interrupted' in text/thinking for first 20 turns and after inv2 start
print('\n=== RESUME SIGNALS (turn, snippet) ===')
rx = re.compile(r'(resum\w+|interrupted|in[- ]flight|unfinished|Resume)', re.I)
for t in turns:
    blob = t['text'] + '\n' + t['thinking']
    if t['idx'] <= 12 or 247 <= t['idx'] <= 260 or 346 <= t['idx'] <= 360:
        for m in rx.finditer(blob):
            s = max(0, m.start() - 100); e = min(len(blob), m.end() + 120)
            print('turn %3d: ...%s...' % (t['idx'], blob[s:e].replace('\n', ' ')))
            break
