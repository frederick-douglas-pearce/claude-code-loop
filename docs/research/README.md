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
| `baseline-2026-10-04.md` | **The sharding epic's before-baseline** (#126): 0.3.0, stratum `claude-opus-5-5`@`high`, per repo. It also states the 0.3.0-relative predictions #133 is judged against. |
| `before-side-2026-10-09.md` | #133's **PR B**: the per-file instrument the sharding release is measured with, frozen at its merge commit; the 0.3.0 before side re-admitted through it; and that side **priced** (parent and subagents, per repo). |
| `baseline-2026-08-25.md` | Frozen **0.2.0** metrics and its P1–P9 sharding predictions (P10 is #135's). Kept as published; superseded as the sharding before-baseline by `baseline-2026-10-04.md`. |
| `context-architecture-refactor.md` | Design note: why shard the engine, compared against `obra/superpowers`. |
| `draft-core.md` | The seven-unit **target** architecture. Not the increment being shipped — do not implement from it. |
| `core-self-sufficiency-audit.md` | Which engine references a shrunken core would break, and the replacement wording. |
| `cost-model-design.md` | Design note: what it would take to *estimate* a lever's effect rather than read it off a slope — estimands, the identification designs available, and the instrumentation that has to land first. |

## Scripts

All stdlib-only, all read Claude Code session transcripts from `~/.claude/projects/<slug>/*.jsonl`.

| script | answers | tests |
|---|---|---|
| `engine_cost.py` | What does carrying the engine — core, on-demand units, and tool reads of `SKILL.md` — cost across a whole run? (P2, P2c, P6, P9, per-unit reads and arrival centroids; `--table` adds the P2c median's order-statistic interval) **Admissibility is per file, in context tokens: the core and every unit the session read must each clear one complete load of that file, measured for the session's own engine era** — never a chars-per-token constant (F191). | `test_engine_cost.py` |
| `plan_gate_cost.py` | What is the parent carrying when the plan is written, and where did all of it come from? Attributes **everything** before implementation starts — including the two buckets no delta-based instrument sees: the always-loaded baseline and the model's own output. Splits that output by block type (only some of it stays resident) and prices the **selection phase** in resident-turn tokens. | `test_plan_gate_cost.py` |
| `rounds_vs_turns.py` | Do gate rounds predict parent turns and bill? (Finding 11) | `test_rounds_vs_turns.py` |
| `calls_per_turn.py` | How many tool calls per turn, and how many turns could have been merged? (Finding 12) | `test_calls_per_turn.py` |
| ~~`context_profile.py`~~ | **RETIRED 2026-08-26** → `deprecated/`. Kept only to reproduce Findings 6–9; its payload bug over-counts spilled reads by up to 13×, so **P4 and the "~50% of every byte" figure are withdrawn**. | — |
| `budget_stats.py` | Ledger `- Budget:` aggregates by engine era. **`--era` resolves N eras and caps BOTH the date and marker columns at the repo's installed version**, so a held-back control cannot read as treated. An installed version missing from `ERAS` raises rather than silently dropping the cap. | `test_budget_stats.py` |
| `tree_cost.py` | Parent **+ subagent** transcripts priced together, each turn on its own model's weights and summed in USD — sizes the bill Finding 11 leaves unpriced. `--sessions` prices named sessions, delegating or not, parent and subagents apart. **Citable since #133**: a hand-checked sample agreed to the cent, and a turn outside the physical bounds refuses its session. | `test_tree_cost.py`; the spec arithmetic itself in `test_stratum.py` |
| `stratum.py` | Which `(model, effort)` stratum a session ran on, plus its CLI version range — the **one** extractor every transcript script above imports, and the per-model `PRICING` table. Every per-session profile prints its `stratum` line; every aggregate groups by parent stratum and names what it excluded. An unpriced model refuses to price, never falls back. (#207) | `test_stratum.py` |

```bash
SLUG=~/.claude/projects/-home-fdpearce-Documents-Projects-git-us-presidential-vote-analysis
python3 docs/research/engine_cost.py      $SLUG/<session>.jsonl
python3 docs/research/plan_gate_cost.py  $SLUG/*.jsonl
python3 docs/research/rounds_vs_turns.py  $SLUG/*.jsonl
python3 docs/research/calls_per_turn.py   $SLUG/*.jsonl
fail=0; for t in docs/research/test_*.py; do python3 "$t" -q || fail=1; done; [ "$fail" = 0 ]   # each module prints its own count; `|| break; done` exits 0 on a failure
```

**Always record the installed plugin version with any measurement** —
`python3 -c "import json,os;print(json.load(open(os.path.expanduser('~/.claude/plugins/installed_plugins.json')))['plugins']['dev-loop@claude-code-loop'])"`.
A before/after that does not name both engine versions is not interpretable. **Nor is one that does
not name both strata:** a model or effort change is a treatment too (`cost-model-design.md` → *The run
environment is a treatment*), so compare only within one parent `(model, effort)` stratum, as each
script's `stratum` line reports it.

## The cost spec is canonical

**The canonical cost arithmetic is
[`claude-code-sessions/reference/cost-model.md`](https://github.com/frederick-douglas-pearce/claude-code-sessions/blob/main/reference/cost-model.md).**
Every script here that prices anything does so through `stratum.py`'s shared path (#212). Where this
directory and the spec disagree, the spec describes the bill.

**When a script refuses a session, it names it in its output** (`REFUSED` or
`EXCLUDED`, with the reason). `stratum.py` holds the exact conditions. Refusals include a cache-write
split that disagrees with its total, unreadable usage, and a non-default pricing lever.

**These departures still produce a price, and nothing in the output flags them:**
- **No long-context tier is modelled.** Every model is priced at its flat rates.
- **A usage key the code does not know is ignored**, so a new lever would price at standard rates.
  The spec says to ignore unknown fields, so this cannot be refused by default.
- **Rates are not date-aware.** The spec prices each record at the rate in effect on its
  `timestamp`; `PRICING` is one snapshot, applied to every session whatever its date.

**A difference from the spec that is not listed here is still a departure.**

---

## What the metrics mean

These were misread once, so they are pinned here rather than left to inference.

| term | definition | what it is **not** |
|---|---|---|
| **engine reads** | count of tool calls returning engine text | *not* complete reads of the file — under 0.2.0 they are overlapping partial slices, ~1.0–1.5× the file in total. Also **filter-dependent**; treat as approximate. |
| **ingested** (P2) | engine tokens that entered the parent, measured from context deltas | *not* the file's size, and *not* `chars/4`. The 0.2.0 corpus ran 3.25–3.82 chars per context token; the 0.3.0 sessions in `baseline-2026-10-04.md` run 2.87–2.89 |
| **resident-turn** (P2c) | Σ over turns of engine tokens sitting in that turn's input | the cost quantity; ingestion counts each read once, this counts every turn it is carried |
| **carry / carry-per-turn** | resident-turn ÷ ingested (÷ turns) | **use carry/turn** — raw carry scales with session length and cannot be compared across runs |
| **% of bill** | engine's share of billable-equivalent input | engine takes a share of the **input** side only; it does not cause output tokens |
| **peak context** | the high-water mark of a **single turn** | *not* a total for the run; compaction *lowers* it |
| **bill/turn** | billable-equivalent per parent turn | near-constant (~28–33k) — that is the point, not a coincidence. *Finding 10, n=8, pooled across `claude-opus-5@xhigh` and `@high`.* ↳ *#212: figures here predate #212's cost arithmetic; see [`cost-arithmetic-rerun-2026-09-28.md`](cost-arithmetic-rerun-2026-09-28.md).* |

**Pricing is per model** (`stratum.PRICING`, from the
[pricing page](https://platform.claude.com/docs/en/about-claude/pricing), checked 2026-09-28). Input
splits fresh / 5-minute cache write / 1-hour cache write / cache read at 1× / 1.25× / 2× / **0.1×**,
except a **0.05×** cache read on `claude-opus-5-5`; output is 5× input on every entry. A model with no
entry refuses to price. 97.6–98.9% of input is cache-read, so **share of context ≈ share of cost** and
cache is a uniform ~8× discount rather than a lever — *Finding 10's n=8 on `claude-opus-5`, pooled
across `@xhigh` and `@high`; re-measure per stratum.*
↳ *#212: figures here predate #212's cost arithmetic; see [`cost-arithmetic-rerun-2026-09-28.md`](cost-arithmetic-rerun-2026-09-28.md).*

**The cost model in one line:** `cost ≈ turns × ~33k` (*Finding 10's n=8 on `claude-opus-5`, pooled
across `@xhigh` and `@high`; re-measure per stratum*). Average context is bounded above by the
compaction ceiling and below by the starting footprint, so it varies little; turn count has no
ceiling. **Turns is the free variable.**
↳ *#212: figures here predate #212's cost arithmetic; see [`cost-arithmetic-rerun-2026-09-28.md`](cost-arithmetic-rerun-2026-09-28.md).*

---

## Read this before trusting any new transcript filter

Six detection bugs were found in this analysis. **Every one produced a silent false result in a
plausible direction**, and pattern-matching caught none of them:

1. **Heredoc bodies** — `cat > progress.md <<'EOF' …` discussing the engine scored as an engine read
   (9 reads in a session that had 1).
2. **Working tree vs plugin cache** — reading `skills/dev-loop/loop-engine.md` is an agent *editing*
   the engine, not the loop loading it. Only happens in this repo; inflated one session ~44%.
   **Recurred after #170** moved the working tree under `plugins/dev-loop/`, so a bare `/plugins/`
   test scored in-repo reads as loads; only `/.claude/plugins/cache/` is a load now (#126).
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
  **admissibility precondition** (derived per session from the engine era; override with `--floor`) — a session below it is
  *unmeasured*, not cheap, and is refused loudly rather than averaged in.

  *This sentence asserted that behaviour for a day before the code had it: the rule was documented
  as default-deny while the tool was in fact fail-open. Caught in review, not by reading. It is
  implemented and tested now — but the lesson is that a doc claiming a fail-safe is not evidence of
  one, which is the same thing `CLAUDE.md` says about prose guards.*

---

## Status

Findings 1–12 are recorded in the notebook and were **all measured on 0.2.0**.

**Several eras are now on disk, and the rollout is a staggered-adoption design with a live control.**
Read the current split from `~/.claude/plugins/installed_plugins.json` — never from this paragraph,
which is the kind of prose that goes stale between releases:

| era | installed | repos |
|---|---|---|
| 0.2.0 | 2026-08-21 | **held deliberately** on `agentfluent`, `claude-code-sessions` — the untreated control |
| 0.2.1 | 2026-08-26 | `claude-code-loop`, `us_presidential_vote_analysis` — **n=10 / n=12** admissible sessions (vote `d53db569` excluded as 0.2.0-era, F170) |
| 0.3.0 | 2026-09-11 (local; `installed_plugins.json` stamps it `2026-09-12T00:39Z`) | `claude-code-loop`, `us_presidential_vote_analysis`, `sportswear-esg-news-classifier` — the sharding epic's before side (`baseline-2026-10-04.md`) |
| **0.3.1** | **2026-10-08** loop and vote (~15:55 local); **2026-10-09** esg (21:40 local) | the three above — **#133-treated**. Also **`claude-hook-validator`**, onboarded at 0.3.1 on 2026-10-09: **baseline-only, not #133-treated** — it has no 0.3.0 before side, and D007 forbids pooling, so its 0.3.1 sessions are its own before-baseline for the next engine-changing release |

⚠ **The v0.3.0 release grew the engine 50.8%** (177,529 → 267,647 bytes; always-loaded 45,937 →
69,457 tokens). Two consequences, both of which bit the instruments before anyone measured anything:

- `engine_cost.py`'s admissibility floor was a **hardcoded 0.2.0 constant** and so turned fail-open
  the moment 0.3.0 installed — a session holding 66–99% of its engine scored `ADMISSIBLE`. The floor
  is now derived **per session** from the era in the read path, and an unknown era defaults to the
  widest known engine. Do not reintroduce a constant.
- **The floor's unit was wrong too (F191), and #133 fixed it.** It was `bytes / 3.5` chars per token,
  but engine text enters the context at ~0.38 context tokens per byte, so the floor admitted ~75% of
  a 0.3.0 load. It is now **one complete load per file, in context tokens**, measured from sessions
  whose reads cover every line (`LOAD_TOKENS`, which names its sessions). A file with no measured
  row is sized at the **strictest** measured rate, so it can be wrongly refused but never wrongly
  admitted. Rows are per tokenizer family as well as per file: re-measure them before scoring a
  parent model on a different tokenizer.
- **Every frozen baseline in `baseline-2026-08-25.md` is against a 45,937-token engine.** P1's
  ~30,000 target was a ~35% cut from that; the same cut against 69,457 lands near ~45,100. Anything
  comparing across this boundary must say which engine each side ran.

**`budget_stats.py --era` now resolves N eras, not two**, and caps the date-derived era at the
version a repo actually has installed — without that cap a held-back control reads as treated, which
does not make the DiD noisier, it inverts it. Note 0.2.1 writes no ledger vocabulary of its own, so
marker attribution returns a **bound** (`0.2.0|0.2.1`) rather than a false exact era. 0.3.1 is the
same (`0.3.0|0.3.1`), and its date boundary in `ERAS` is 2026-10-10, the first day no treated repo
could still be on 0.3.0.

The three levers this work ranks, in the same units:

| lever | value | basis | confidence |
|---|---|---|---|
| avoid one gate round | ~561–850k **input+output, per issue** | r=+0.79 + Finding 2's mechanism | correlational |
| batch same-file paging reads | ~176k **input-only, per session** (358k theoretical) | run-length corrected | rough order |
| shard the engine (#128) | ~4–5% of a run | modelled, not measured | low |

↳ *#212: figures here predate #212's cost arithmetic; see [`cost-arithmetic-rerun-2026-09-28.md`](cost-arithmetic-rerun-2026-09-28.md).*

**These are not in the same units and an earlier version of this table said they were.** The gate-round
figure is input+output per *issue*; the batching figure is input-only per *session*. On a common
basis the gate-round lever is ≈714k input-equivalent. The ranking survives the correction; the
"same units" claim did not.
