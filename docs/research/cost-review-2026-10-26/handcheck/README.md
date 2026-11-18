# Appendix D's hand-check scripts (recovered)

These are the scripts behind [appendix D](../D-handcheck-3f30a898.md), the hand-check of vote
session `3f30a898`. They were written to a session scratchpad on 2026-10-26 and never committed.
On 2026-11-17 (#273) they were recovered verbatim from the `Write` calls in the subagent transcript
that produced appendix D (`538462a0-…/subagents/agent-a28630ded68385c27.jsonl` under this repo's
`~/.claude/projects/` slug). That transcript has no later `Edit`, `sed -i` or redirect to these
files, so what is here is what ran. Their outputs (`turns.json`, `timeline.txt`,
`cache_writes_out.txt`) were not recovered. `timeline.py` regenerates the first two.

| file | what it does |
|---|---|
| `timeline.py` | per-turn timeline of a transcript; writes `turns.json`, which the others read |
| `phases.py` | keyword first-occurrence scan per invocation, human gates, Bash categories |
| `analysis2.py` | **the per-phase accounting; its `PHASES` list holds appendix D's exact turn ranges** |
| `ledger.py` | ledger lines the session wrote, from tool_use inputs |
| `details.py` | Budget lines, engine read params, post-compaction text, human-wait gaps |
| `subagents.py` | per-subagent summary |
| `probe.py` | record-type survey of a transcript |
| `report.md` | the draft appendix D was edited from |

**How appendix D drew its phase boundaries:** by hand, from `phases.py`'s keyword scan, then fixed
in `analysis2.py`'s `PHASES`. `tree_cost.py --sessions … --by-step` (#273) detects the same
boundaries from `tool_use` markers. `test_tree_cost.py` pins its agreement with these ranges.

These are a historical record. Nothing imports or runs them, so the stdlib-only rule does not bind
them, but they happen to be stdlib-only. Usage is in each file's docstring, e.g.
`python3 -I timeline.py <transcript.jsonl> <out_dir>`.
