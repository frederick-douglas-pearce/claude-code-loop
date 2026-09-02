# Loop cost & convergence research

**Not part of the plugin's runtime.** Nothing here is read by an agent at runtime; the `dev-loop`
deliverable is `skills/`, `commands/`, `hooks/`, `tools/`. These are analysis artifacts about how
much a loop run costs and why, kept in-repo so the numbers behind a scoping decision are auditable
rather than remembered.

---

## Start here

| file | what it is |
|---|---|
| **`loop-cost-and-convergence.md`** | The notebook. Findings 1–12, each with method, numbers, and what would falsify it. **The primary document** — everything else supports it. |
| `baseline-2026-08-25.md` | Frozen pre-change metrics and the P1–P9 predictions the sharding epic is judged against. |
| `context-architecture-refactor.md` | Design note: why shard the engine, compared against `obra/superpowers`. |
| `draft-core.md` | The seven-unit **target** architecture. Not the increment being shipped — do not implement from it. |
| `core-self-sufficiency-audit.md` | Which engine references a shrunken core would break, and the replacement wording. |
| `cost-model-design.md` | Design note: what it would take to *estimate* a lever's effect rather than read it off a slope — estimands, the identification designs available, and the instrumentation that has to land first. |

## Scripts

All stdlib-only, all read Claude Code session transcripts from `~/.claude/projects/<slug>/*.jsonl`.

| script | answers | tests |
|---|---|---|
| `engine_cost.py` | What does carrying `loop-engine.md` cost across a whole run? (P2, P2c, P8/P9) | `test_engine_cost.py` |
| `plan_gate_cost.py` | What is the parent carrying when the plan is written, and where did all of it come from? Attributes **everything** before implementation starts — including the two buckets no delta-based instrument sees: the always-loaded baseline and the model's own output. | `test_plan_gate_cost.py` |
| `rounds_vs_turns.py` | Do gate rounds predict parent turns and bill? (Finding 11) | `test_rounds_vs_turns.py` |
| `calls_per_turn.py` | How many tool calls per turn, and how many turns could have been merged? (Finding 12) | `test_calls_per_turn.py` |
| ~~`context_profile.py`~~ | **RETIRED 2026-08-26** → `deprecated/`. Kept only to reproduce Findings 6–9; its payload bug over-counts spilled reads by up to 13×, so **P4 and the "~50% of every byte" figure are withdrawn**. | — |
| `budget_stats.py` | Ledger `- Budget:` aggregates by engine era. | none |
| `tree_cost.py` | Parent **+ subagent** transcripts priced together — sizes the bill Finding 11 leaves unpriced. **Scouting only; output is not a finding.** | none |

```bash
SLUG=~/.claude/projects/-home-fdpearce-Documents-Projects-git-us-presidential-vote-analysis
python3 docs/research/engine_cost.py      $SLUG/<session>.jsonl
python3 docs/research/plan_gate_cost.py  $SLUG/*.jsonl
python3 docs/research/rounds_vs_turns.py  $SLUG/*.jsonl
python3 docs/research/calls_per_turn.py   $SLUG/*.jsonl
for t in docs/research/test_*.py; do python3 "$t" -q || break; done   # each module prints its own count
```

**Always record the installed plugin version with any measurement** —
`python3 -c "import json,os;print(json.load(open(os.path.expanduser('~/.claude/plugins/installed_plugins.json')))['plugins']['dev-loop@claude-code-loop'])"`.
A before/after that does not name both engine versions is not interpretable.

---

## What the metrics mean

These were misread once, so they are pinned here rather than left to inference.

| term | definition | what it is **not** |
|---|---|---|
| **engine reads** | count of tool calls returning engine text | *not* complete reads of the file — under 0.2.0 they are overlapping partial slices, ~1.0–1.5× the file in total. Also **filter-dependent**; treat as approximate. |
| **ingested** (P2) | engine tokens that entered the parent, measured from context deltas | *not* the file's size, and *not* `chars/4` — this corpus runs 3.25–3.82 chars per context token |
| **resident-turn** (P2c) | Σ over turns of engine tokens sitting in that turn's input | the cost quantity; ingestion counts each read once, this counts every turn it is carried |
| **carry / carry-per-turn** | resident-turn ÷ ingested (÷ turns) | **use carry/turn** — raw carry scales with session length and cannot be compared across runs |
| **% of bill** | engine's share of billable-equivalent input | engine takes a share of the **input** side only; it does not cause output tokens |
| **peak context** | the high-water mark of a **single turn** | *not* a total for the run; compaction *lowers* it |
| **bill/turn** | billable-equivalent per parent turn | near-constant (~28–33k) — that is the point, not a coincidence |

**Pricing.** Input splits fresh / cache-write / cache-read at 1× / 1.25× / 0.1×; output ≈ 5× input.
97.6–98.9% of input is cache-read, so **share of context ≈ share of cost** and cache is a uniform
~8× discount rather than a lever.

**The cost model in one line:** `cost ≈ turns × ~33k`. Average context is bounded above by the
compaction ceiling and below by the starting footprint, so it varies little; turn count has no
ceiling. **Turns is the free variable.**

---

## Read this before trusting any new transcript filter

Six detection bugs were found in this analysis. **Every one produced a silent false result in a
plausible direction**, and pattern-matching caught none of them:

1. **Heredoc bodies** — `cat > progress.md <<'EOF' …` discussing the engine scored as an engine read
   (9 reads in a session that had 1).
2. **Working tree vs plugin cache** — reading `skills/dev-loop/loop-engine.md` is an agent *editing*
   the engine, not the loop loading it. Only happens in this repo; inflated one session ~44%.
3. **Spill files** — an over-large `cat` is parked at `<session>/tool-results/<id>.txt` and the model
   gets a 2KB preview; recovery reads target the **spill path**, which contains no `loop-engine.md`
   substring. Scored a full load as ~10% of one, and that was written up as a real finding before it
   was caught.
4. **Payload inversion** — `toolUseResult.stdout` holds the full output on a spilled record; the
   model only received the preview. 13× overstatement. **`context_profile.py` was retired (D010) carrying it.**
5. **Direction** — counting `- Budget:` lines the parent *read back* from `progress.md` as work done
   in that session (one 158-turn session showed 11 issues at 14 turns each).
6. **Line wrapping** — budget lines wrap, so `gate-rounds=` sits on a continuation line; a
   single-line regex dropped 3 of 9 sessions.

Two defences, both cheap, and they are the only things that have worked:

- **Hand-check a sample of matches.** Bugs 1, 2, 4, 5 and 6 were found this way; the architect review
  found 3. None was found by reasoning about the pattern.
- **Sanity-check the output distribution against what the system can physically do.** One issue per
  invocation; engine ingestion ≥ one copy of the engine. `engine_cost.py` enforces the latter as an
  **admissibility precondition** (`DEFAULT_FLOOR`, override with `--floor`) — a session below it is
  *unmeasured*, not cheap, and is refused loudly rather than averaged in.

  *This sentence asserted that behaviour for a day before the code had it: the rule was documented
  as default-deny while the tool was in fact fail-open. Caught in review, not by reading. It is
  implemented and tested now — but the lesson is that a doc claiming a fail-safe is not evidence of
  one, which is the same thing `CLAUDE.md` says about prose guards.*

---

## Status

Findings 1–12 are recorded in the notebook. **All measured sessions are 0.2.0**; `claude-code-loop`
and `us_presidential_vote_analysis` moved to 0.2.1 on 2026-08-26, so the next fresh session in either
is the first post-fix reading. `claude-code-sessions` remains on 0.2.0 deliberately.

The three levers this work ranks, in the same units:

| lever | value | basis | confidence |
|---|---|---|---|
| avoid one gate round | ~561–850k **input+output, per issue** | r=+0.79 + Finding 2's mechanism | correlational |
| batch same-file paging reads | ~176k **input-only, per session** (358k theoretical) | run-length corrected | rough order |
| shard the engine (#128) | ~4–5% of a run | modelled, not measured | low |

**These are not in the same units and an earlier version of this table said they were.** The gate-round
figure is input+output per *issue*; the batching figure is input-only per *session*. On a common
basis the gate-round lever is ≈714k input-equivalent. The ranking survives the correction; the
"same units" claim did not.
