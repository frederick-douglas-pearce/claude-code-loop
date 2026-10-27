# Cost review — engine, config, backlog, and the testing approach

**Status:** review, not a ruling. Nothing here has been through a gate.
**Date:** 2026-10-26. **Engine:** 0.3.1 (`e7c03d6`), working tree `971f21c`. **Stratum of every transcript figure:** parent `claude-opus-5-5@high`, CLI 2.1.296–2.1.302.
**Question:** after three shipped cost levers and no measurable dent, what would actually cut the cost of a loop iteration without lowering its quality, and is the testing approach able to tell?

Six parallel audits fed this document: the engine core, the units and sharding record, the research corpus and causal design, fresh measurements on 0.3.1 sessions, the backlog and consumer configs, and the current Claude Code feature set. Raw script outputs are in the session scratchpad (`scratchpad/measure/`); every number below names the script and session that produced it or is marked as an estimate. The byte-class splits of the engine are a reader's estimates from a full read; the section sizes are measured.

---

## 1. The one-paragraph answer

The bill is turn-driven (`cost ≈ turns × ~25k` billable-equivalent on 0.3.1; the per-turn figure sits in a narrow band because context is bounded by the compaction ceiling, while turns have no ceiling). Every lever shipped so far — the `Read` protocol (0.2.1), same-file batching (0.3.0), sharding (0.3.1) — acts on context, and the program's own model priced each at 3–5% of a run. "No dent" is what that model predicted. The levers the model rates largest act on **turns**, and specifically on review rounds that exist because the previous round's fix introduced the next round's defects. None has been tried. Meanwhile the engine kept growing: a completed `code` iteration now reads **1.6% more** engine text than before sharding (282KB vs 278KB), because the unit preambles and fail-safe halves were added, not moved. So the recommendation is: **treat turns first (fix application and round ceilings), then make the engine structurally smaller in context (phase isolation and deletion), and change the primary metric to dollars per completed issue with a quality outcome beside it.**

---

## 2. Where the money is today (0.3.1, measured 2026-10-26)

### 2.1 Per iteration

| | loop (n=5 completed) | vote (n=11 admissible) |
|---|---:|---:|
| whole-tree USD per session, median (`tree_cost.py --sessions`) | **$17.61** | **$35.61** (range $13–53) |
| subagent share of the tree bill | 34–38% | 33% |
| parent turns, median | 106 | 185 |
| bill/turn (billable-equivalent), median | 25.0k | 25.1k |
| **peak parent context**, median (max) | **346k** (711k) | **449k** (619k) |
| compactions per session | 0–2 | 0–4 |
| engine share of average context, P2c (PROP model) | 33.9% | 24.4% |
| resident context at the plan-file write, median (`plan_gate_cost.py`) | **186k** | **230k** |

One vote session (`3f30a898`, `/dev-loop` on #3xx, 423 turns) cost **$128.52** on its own and peaked at 960k. It is inadmissible to the engine instrument on a detector technicality, which is itself a finding (§6).

**Read the plan-gate row.** The research target of 100–200k parent context is exceeded before implementation begins. At the moment the plan file is written the parent already holds ~77k of engine core, ~61k of baseline (system prompt, tool definitions, CLAUDE.md; #150), the config (23KB here), `queue.md`, the issue, and 14–21 turns of selection and reconciliation. The fixed overhead is ~138k before the loop has done anything an issue needs.

### 2.2 Per issue, from the ledgers (`budget_stats.py --era`; self-reported, unstratified)

| repo | Aug-25 snapshot (runs median / rounds median) | 0.3.1 now |
|---|---|---|
| loop | 7 / 5 (n=27) | **12.5 / 5.5** (n=6) |
| vote | 3 / 3 (n=19) | **13 / 5** (n=17) |

Subagent runs per issue have roughly **doubled** since August in both treated repos; gate rounds are flat at ~5. The 2-round caps are respected per gate and the cycle compounds anyway (F98: "the 2-round cap is a checkpoint, not convergence; 4/4 went past it").

### 2.3 The engine

| file | bytes | lines | context tokens when loaded (`LOAD_TOKENS`) |
|---|---:|---:|---:|
| `loop-engine.md` (core, every invocation) | 200,789 | 2,535 | 76,897 |
| `SKILL.md` (every invocation) | 10,829 | 131 | ~2.8k |
| `phases/reviewing.md` (step 8) | 32,344 | 403 | 11,826 |
| `phases/accepting.md` (step 10) | 38,409 | 493 | 14,042 |
| `reference/initialization.md` | 3,489 | 53 | 1,510 |
| **total** | **285,860** | **3,615** | **~107k** |

The core alone is 13% larger than the *whole* 0.2.0 engine was when the cost research opened (177,529 B). Classified by a full read (estimates):

| class | bytes | share |
|---|---:|---:|
| first-order runtime instruction | ~76.5k | **38%** |
| fail-safe restatement of an invariant stated elsewhere | ~43.9k | 22% |
| extended "why" prose | ~57.4k | 29% |
| maintainer history and rationale ("deliberate", "used to say", "#N shipped", "RETIRED") | ~13.2k | 7% |
| templates and worked examples | ~9.7k | 5% |

Invariants stated at three or more sites, in different words, cover **~117KB (58%)** of the file. Two blocks are near-verbatim duplicates: the `- Budget:` line specification (step 12 and the Ledger section, 13.9KB together) and the merge-eligibility always-escalate list (twice). `SKILL.md` is 65% fail-safe restatement of core by design.

### 2.4 What else enters the parent

The engine mandates several **unbounded** reads: the full config; full `queue.md`; `git diff --cached` in full at every commit boundary; lint, type, test, and hermetic output "to completion"; the issue body; the contents of an isolated copy before removal; and an undefined "tail of `progress.md`" on a journal that is 67–484KB in this repo. The August profile found `cat`/`head`/`sed` + `Read` + `grep` at 56–82% of what enters the parent; nothing since has bounded those reads. The parent still issues **1.01–1.02 tool calls per turn** (`calls_per_turn.py`), so #135's batching has not changed turn structure measurably.

### 2.5 What does not cost what it seemed

- **Subagent returns** are 0.9–3.7% of parent input. Constraining them is not a lever (D010, Finding 6).
- **Lint/type output** is 1.2% of Bash volume. Hooks that replace the fix-until-green loop are not a context lever.
- **Fork subagents**: zero `subagent_type: fork` calls in 55 loop sessions since 2026-10-01 across loop and vote (980 `Agent` calls). Not a hidden cost.
- **CLAUDE.md size**: a 3.4× difference moved nothing (#150).

---

## 3. Recommendations, ranked

Ranked by expected saving × confidence, with quality held fixed. Savings are stated against the whole-tree bill per completed iteration. "Modeled" means derived from the measured cost structure; "measured" means a before/after exists. Nothing in this list is measured; §5 says how each would be.

| rank | lever | acts on | expected saving | confidence | quality risk |
|---|---|---|---|---|---|
| R1 | Fresh-agent fix application + iteration round ceiling | turns | 15–35% | medium | low; likely positive |
| R2 | Phase isolation: run each phase in its own context | context × turns | 25–40% | medium-low (unmeasured; needs a spike) | medium until staged |
| R3 | Engine deletion: duplicates, history, "why" prose | context | 5–10% + fewer compactions | high on bytes, medium on bill | low |
| R4 | Subagent model and effort tiering | subagent bill | 7–15% | medium | low-medium |
| R5 | Baseline overhead: tool definitions and MCP servers | context | 0–10% | unknown; one `/context` reading settles it | none |
| R6 | Hook-enforced read discipline and bounded reads | context, correctness | 3–8% | medium | low; fail-safe gain |
| R7 | Plan-gate scope budget | turns (late splits) | 5–15% on the issues it catches | low-medium | low |
| R8 | Route-aware gate depth and a `test` route | subagent runs | consumer-dependent | medium | low for docs/tests |
| R9 | Context at the human gate: one invocation per session, cache TTL, arrive thin | cache re-warm (invisible to per-turn instruments) | 20–30% on multi-invocation sessions; larger on API keys | high (measured on one session) | none |
| — | Finish the reference appendix (PRD S3) | context | ~1–2% | high | low |
| — | More batching (#184 and the mergeable-read tail) | turns | 1–3% | medium | none |

### R1. Fresh-agent fix application, and a ceiling on the cycle (turns)

**Evidence.** Seven journaled instances across four ledgers say the extra rounds catch defects the *previous round's fix* introduced (Finding 2; F38: 5/5 fix-induced; F131). The lever is fix-application quality: the parent applies N findings in one pass, deep in a 300–500k session. #169 recorded the one direct experiment: a parent rewrite produced 8 + 3 new false claims; a clean deleter produced 0 + 0. The rounds-to-turns join gives ~17 parent turns per round (r = +0.79, n = 8, on a self-reported independent variable; §6). At 25k billable-equivalent per turn plus the round's own finders and re-check, **one round is roughly $4–6 of a $18–36 iteration**. Rounds per issue sit at 5; the caps are 2 per gate.

**Change.** Three parts, all engine-side and project-agnostic:
1. **Apply fixes in a fresh agent, not the parent.** On a dirty round, spawn one agent in the isolated copy the engine already specifies (Tool surface, "writing agent gets its own copy"), with the plan, the finding list, and the diff, under the deletion-first rule F125 identified and #169 charters ("fix prose by deleting, not rewriting"). The parent collects the diff by path and never reads the fix. The fresh re-checker then reviews it as today. This targets the mechanism directly: the agent writing the fix has a clean context.
2. **An iteration-level ceiling on the re-arm cycle** (lever C): total review rounds per iteration, not per gate. Reaching it stops and escalates with state, which is the posture the merge gate already takes. The data to set it exists (`gate-rounds` on every Budget line; median 5, max 10–12).
3. **Carry F125's constraint into the engine text**: the prose class that costs rounds is unverified claims, and the fix that works is deletion. #121's BLOCKING/EDITORIAL split did not reduce rounds (F107, F119) because it could not reach that class.

**Quality.** Expected to improve: fewer fix-induced defects reach the human, and the ceiling converts an open-ended cycle into an escalation with options, which is the current behavior at every other gate. The human still approves every merge.

**Why first.** It is the only lever on the page that the evidence says is large, it is cheap (no new CAPS parameter, no new agent definition, one new engine passage), and #169 is already filed with no comments since 2026-09-14.

### R2. Phase isolation: each phase in its own context (context × turns)

**Evidence.** 71% of all tokens processed are the parent's (Finding 6), and the parent's content is file reads. The engine is carried for 74–91% of a run (Finding 10). Compaction is the only thing that reduces residency and it is the worst mechanism: after compaction any file over 5,000 tokens comes back as a path reference, so the engine is re-read in full at cache-write rates (Claude Code docs, `context-window.md`; F106). Finding 7.3 already concluded "delegate reading, not just work" is the strongest single finding. This lever applies that conclusion to whole phases.

**Change.** The parent becomes a thin controller: `SKILL.md`, the gate table, the routing table, the ledger writes, and the two human gates. Each phase between gates runs in a fresh context that loads only its own unit, does its own reads, and returns a bounded result (verdict, plan path, PR number, gate-decision block). The engine text and the phase's reads never enter the parent; phase turns run at 50–100k context instead of 300–500k; compactions mostly disappear. Claude Code supports this today in two shapes:
- **Skills with `context: fork` and an `agent:`** run the skill body as a subagent's prompt; the parent sees only the result (`skills.md`). Use `background: false` so the parent waits. State is on disk, which is the loop's design already (`/clear` survives), so "cannot see conversation history" costs nothing.
- **The `Workflow` tool** runs a deterministic script of agents (`pipeline`, `parallel`) with intermediate results held in script variables and only the final value returned. It fits the review round exactly: finders in parallel, verify, fix in a worktree, re-check, return a verdict. A skill's instructions may direct the orchestrator to call it.

**Constraints that decide the staging** (verified empirically 2026-10-26 from inside a subagent, and against `sub-agents.md` and `skills.md`):
- **A subagent can spawn subagents**, "up to three layers below the main conversation" (`CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH`; tested: a nested `Agent` launch returned normally). So a forked *review* phase can run the finder fan-out, the fix agent, and the fresh re-check itself and return one verdict. This is the strongest shape for R2, because the review round is where the turns are.
- **`Workflow` is withheld from every subagent** ("removes these tools, even when listed in the `tools` field"). The Workflow option only exists at the parent, so it is the fallback, not the plan.
- **A backgrounded forked skill loses `Agent`** (background subagents keep a fixed built-in set). Phase skills must set `background: false`, which also makes the parent wait, which is what a pipeline wants.
- The `Skill` tool is available inside a subagent, so a phase can load its own unit as a skill rather than reading a file.
- Step 6 (implement) is parent-owned by the engine's isolation rules and D017 ruled `implementing` out of extraction. Leave it in the parent in the first increment.
- Subagent prompt cache defaults to 5 minutes; set `subagentPromptCacheTtl: 1h` or per-agent `experimental.cacheTtl` for phases that wait on a human.
- Every phase must keep the fail-safe posture on *its* side: a phase that returns anything the controller does not recognize is an escalation. That is `SKILL.md`'s existing design, one level down.
- D001 rejected "controller-ification" **as a lever on subagent returns**, which was correct: returns are small. This is a different claim — the gain is the engine text and the phase's reads never entering the parent, and phase turns running at small context. The decision should be revisited on that ground, not overruled.

**Order of work.** First build the per-step cost attribution the research design calls E4 (whole-tree $ by pipeline step; `tree_cost.py` has the pricing, it lacks the step boundaries). It tells which phase to isolate first and gives the before side for free. Then a spike: one phase (step 3 plan drafting is the safest; it reads the issue and writes a file) as a forked skill, measured on the paired benchmark (§5).

**Quality.** Neutral by construction if each phase loads its full unit; the risk is a partial load inside a phase, which is the same hazard `SKILL.md` guards today and needs the same guard per phase.

### R3. Engine deletion (context)

**Evidence.** §2.3. 62% of the core is not first-order instruction; 58% sits inside multi-site restatements; two blocks are verbatim duplicates. The engine is 24–34% of average context on 0.3.1.

**Change.** In order of safety:
1. **Delete verbatim duplicates**, keeping the Ledger copy: the `- Budget:` specification at step 12 (L975–1011 vs L1654–1787, ~7KB) and the merge always-escalate list (L917–937 vs L1298–1312, ~1.5KB).
2. **Move maintainer history to `plugins/CLAUDE.md`**, which does not ship: the ~13KB of "RETIRED", "used to say", "the parameter that once sat here", "placed last deliberately" passages the core audit lists by line, plus the `reviewing.md` floor-polarity warnings (L237–263) and the duplicated `cd`-incident narrative in `accepting.md` (L247–260; core L1123–1134 has it).
3. **Cut extended rationale to one line each** where the rule survives without it (~57KB of "why" prose; the audit quotes L1399–1403, L1559–1565, L2423–2426, L2433–2440, L2472–2477, L637–645, L1338–1345, L2331–2340 as representative). Keep the rule; keep a pointer to the decision log or F-number; delete the argument.
4. **Finish the reference appendix** the sharding PRD planned and #131 left in core: the `progress.md` worked example (L1405–1442), `- Plan-gate-inferred:` (L1789–1878, needed only on a ledger predating the field), the plan template and lifecycle (L1880–1930). ~12KB per invocation.
5. **Replace unit restatements with pointers**, as `reviewing.md` L340–342 already does ("Its full input recipe is under Gates; do not restate it here"): the guard-efficacy prompt list and comparison table in `reviewing.md` (~2.5KB), the `SKILL.md` read protocol (L29–47, keep the three operative sentences).

**Target, now measured rather than estimated (appendix C).** The deletion manifest covers classes 1–3 in 147 rows with the exact surviving text per row: **46,304 bytes net (23.1% of the core)**, generated by a script that asserts every row's anchors against the file, applies them to produce the engine-after text (154,485 bytes), and re-checks the 75 engine-pinned test literals (all still present; five rows need a test edit in the same PR, listed in the manifest). With the #35 collapse (~15KB, appendices B1/B2) and the reference appendix (~12KB), the core lands near **127KB**, a 37% cut, none of it a fail-safe half. Modeled at the measured share, ~8–12% of parent input bill, ~5–8% whole-tree, plus a second-order gain from fewer compactions (each compaction re-reads the engine at 2× a load) and a smaller re-warm at every gate (R9).

**Constraints.** D017: never close a footprint gap by deferring fail-safe halves out of core or by "quietly restating". None of 1–5 touches a fail-safe half. The multi-site *semantic* restatements are **#35**, deferred because the sites had drifted (F57–F59); collapsing them silently picks a winner. **The drift is now reconciled (appendices B1 and B2), and it is smaller than #35 feared.** The currency clause, fresh re-check, and scope-ruling sites have not drifted at all (B2: zero behavior deltas, ~9.1KB of redundancy). The plan-gate posture and gate-outcome sites carry **four behavior-changing deltas** (B1), each with a ruling:
- the `conditional` stop set is 5 items at step 5 but 2 in the gate table (F57): step 5 wins;
- "never *writes* the field outside Initialization" (#108) vs "never *rewrites*" at L1355 and `SKILL.md` L86: the strong form wins, and the `SKILL.md` clause must change;
- Guardrails L1053 "mark blocked, move on" vs Gates L2203 "open PR ⇒ STOP": Gates wins;
- four sites presuppose an "inline architect composition" that nothing defines: escalate, strike the references.
Plus one fail-open read-alone defect in the currency clause at step 9 (L880–883; B2 Δ3.3). **Sequence: one point-fix PR for the five behavior deltas first, then #35 as a true refactor** with the canonical passages B1/B2 draft, ~15KB in total.

**Quality.** Low risk; deletion asserts nothing (the repo's own rule). The one process risk is the same one #23 hit: a prose change costing 9 subagent runs and 7 rounds on *consistency*. Land it as several small PRs, each one deletion class, so each round has one shape of finding.

### R4. Subagent model and effort tiering (subagent bill)

**Evidence.** Subagents are 33–38% of the tree bill. Every subagent in the 0.3.1 corpus runs `claude-opus-5-5` (F198). No finder, reviewer, or verifier agent definition exists; the finders are ad hoc spawns inheriting the parent model. The engine has no vocabulary for a model tier, and the config skeleton has no row for one.

**Change.** Pin a model and effort per role in the agent frontmatter (`model:`, `effort:`), or spawn with an explicit model from the engine for the roles it spawns ad hoc. Tier by whether the output is verified mechanically:
- **Cheaper model, exit-code or diff-verified:** the mutation selector, ledger probes and step 0/1 reconciliation (R2's read-only phases), CI wait, docs propagation, the AC-verifier's mechanical Part 1 checks, the green-up loop if it is ever delegated.
- **Stay on the main model:** finders, the fresh re-checker, pm, architect. The research is explicit: a cheap finder returns plausible noise, and noise costs rounds, which is the expensive axis.
- **Do not use the built-in `Explore` agent as the cheap reader**: on a subscription it runs the main model.

**Expected:** 20–40% of the subagent bill, i.e. 7–15% whole-tree. The engine-side part is one sentence per spawn site plus a CAPS parameter only if the tier should be consumer-bound. **Quality:** low risk on mechanically verified roles; do not tier the judgment roles.

### R5. Baseline overhead (context)

#150 measured ~44k always-on tokens invisible to every instrument, ~32k of it system prompt plus MCP tool definitions, most of which a loop run never calls; `plan_gate_cost.py` puts the baseline at ~61k at the plan write. If tool definitions are eagerly loaded, disabling unneeded MCP servers for loop sessions (per-project `.mcp.json`, or `disabledMcpServers`) is ~10% of input bill for a config change. If they are deferred (this session lists MCP tools by name only and loads schemas through `ToolSearch`), the lever is already taken. **One `/context` reading inside a loop session settles it** (#150's AC1, never run). Do that before anything else on this list; it is an hour.

### R6. Hook-enforced read discipline and bounded reads (context, correctness)

**Evidence.** The read protocol is ~4KB of prose in `SKILL.md` and core, and the truncation hazard it guards is fail-open (Finding 8: a `cat` of the engine returns 18% and nothing requires noticing). `cat`/`head`/`sed` was 56% of Bash volume at ~6k chars per call in August; the mandated unbounded reads (§2.4) are unchanged.

**Change.** A `PreToolUse` hook on `Bash`, config-driven and inert until opted in, in the shape of `guard_append_only.py`:
- block `cat`/`sed -n`/`head` on files above the output cap with a "use `Read`" denial (fail-closed on the engine files specifically);
- rewrite `git diff --cached` to `--stat` plus `--name-status` unless a flag opts into the full diff (`updatedInput`);
- pipe test and lint output through a filter that keeps the summary and the first failures (`updatedInput`, the pattern the hooks docs use as their example).
Then delete the prose the hook replaces. Bounded reads elsewhere: define "tail of `progress.md`" as a `Read` with an offset from `totalLines`; read issue comments through a subagent that returns the ACs and corrections verbatim (the stale-AC hazard the memory records).

**Expected:** 3–8%; the larger value is the fail-safe gain and the deleted prose. **Quality:** improves (the fail-open bootstrap closes).

### R7. Plan-gate scope budget (turns, on the issues it catches)

Symptom 3 says scope is split at the review gate, which means the review gate is doing the scoping; a late split throws away an implementation. The plan gate already stops for a human on every issue; have the plan declare files-to-touch, AC count, and rough diff size, and have the pm's recommendation name a split when over budget. Modeled only; the prevalence of late splits is unmeasured (count `split` outcomes in the journals first; it is one grep). Low risk: the human still decides.

### R8. Route-aware gate depth and a `test` route (subagent runs)

F93: the gate stack is route-blind; a `docs` row costs the same six subagent runs as `code`. There is no `test` route anywhere, so a test-only change draws the full pipeline plus the hermetic tier plus the mutation pass. Only `claude-code-sessions` scales review effort by route (`/code-review high` for code, `low`/`medium` for docs-adjacent) and only `agentfluent` runs graduated routes with `escalation-only`. For this repo the `docs` route is nearly unreachable by design (executed markdown is code), so the gain is in consumers. Check route distribution in the ledgers before building a route; the research's open question 2 was never answered.

### R9. Context at the human gate, and the cache re-warm (added after the `3f30a898` hand-check, appendix D)

**Evidence.** The $128 session was two `/dev-loop` invocations in one session with no `/clear` between them; the second started at 723k context. Of its $87.90 parent bill, cache writes were $36.9, and **75% of that ($27.8) was six re-warms of the entire context after human gate waits longer than the 1-hour cache TTL**: one stop at 947k context cost $7.60 just to resume. Per-turn instruments cannot see this; it is 32% of the parent bill. Active API time was 4.5h of a 29h span; the other 24.6h was the human.

**Why it matters more than the number.** The 1-hour TTL is the *subscription* rate. **On an API key the main-conversation cache TTL is 5 minutes** (`prompt-caching.md`), so a business consumer re-warms the whole context at cache-write rates at nearly every plan gate and merge gate, and the cost of a gate is proportional to the parent's context at the stop. For the adoption goal, this is the first-order problem: the loop stops for a human by design, and the parent is at 200–950k when it does.

**Change.** Three parts, cheapest first:
1. **One invocation per session.** The engine's step-12 stop message, and `SKILL.md`, tell the operator to `/clear` before invoking again (F128: exactly one context boundary, at the issue level). In the hand-checked session this alone is ≈ −$19 (21%).
2. **Set `promptCacheTtl: 1h`** in the consumer's settings for API-key users (documented; cache writes cost more, but a 5-minute TTL across a human gate is the worst case).
3. **Arrive at the gate thin.** This is R2 restated from the gate's side: a controller that holds ~50–100k at the plan and merge gates re-warms at a tenth of today's cost, and the phase that did the work is already gone. R2's expected saving should be re-modeled with the re-warm included; the instruments currently price it at zero.

Also from the hand-check, two smaller items for R4 and R6: the two built-in `Explore` map-the-codebase agents were 21M of the subagent tree's 77M context (on the main model, §3 R4), and the orchestrator's own 123 heredoc whole-file patches (336k chars of command text, retained for the rest of the session) argue for `Edit` over `cat > file` heredocs as a write-discipline rule beside the read one.

### Not recommended now

- **Capping `autoCompactWindow`** at the 200k target. Compaction evicts the engine and re-reads it at cache-write; more compactions cost more until R2/R3 make the engine small. Anti-lever today.
- **`REVIEW_TIERS` (#38) and rebinding `CODE_REVIEW` to `/code-review`.** The one data point (sessions #190) shows parity with the fan-out, not the predicted order of magnitude. Rounds, not finders, are the term.
- **Narrowing the re-check base** to `<pre-fix-sha>...HEAD`. Already rejected: fix-induced regressions are the dominant defect class, and the narrower base cannot see them.
- **Constraining finder returns, or lint/format hooks sold as context savings.** Refuted (§2.5).
- **Vote's `ba` at every plan step and every round 1** adds at least one subagent run per iteration and one per round, and it contaminated 13 of 22 after-side sessions (F198). That is the owner's call, but it should be priced.

---

## 4. What the backlog already holds

| item | state | this review's view |
|---|---|---|
| #169 deletion-first delegated repair | open, unmilestoned, no comments since 09-14 | **R1's core; promote** |
| #56 fix-induced thrash, subtractive step-back | deferred-corpus (n=2) | folds into R1's ceiling |
| #153 claim audit before re-arming | deferred-corpus | superseded by R1 (adds a run per fix; R1 removes the defects instead) |
| #128 / #133 sharding epic and its measurement | open; #133 parked since 10-10 awaiting n≥5 | **data is on disk now** (§6); un-park, post the verdict, close the epic |
| #150 always-on baseline | open, AC1 never run | **R5; one hour** |
| #35 one canonical gate passage | deferred-corpus (drift) | prerequisite for the semantic half of R3; keep deferred, do the drift reconciliation first |
| #211 cost-experiments epic (#208 pilot gate, #209 σ, #210 go/no-go) | unmilestoned | **the test harness §5 needs; promote** |
| #234 session IDs in journal → #235/#236 per-PR tokens | "top candidate after v0.3.2" | the E4 attribution R2 depends on |
| #223 judge v0.2.1's P2 prediction | open | close as "before side inadmissible under the frozen instrument" after one reading |
| #138 per-round cost in the ledger | cut from 0.3.0 | replaced by transcript-recovered rounds (§6.4) |
| #184 batch independent edits | open | small; fold into R6's hook work only if free |
| #38, #37, #69 review tiers, test-efficacy agent, fixture repo | deferred-corpus | #69's fixture repo is the paired benchmark (§5.3); the other two wait on it |
| #85 `CI_STATUS_CMD` bound, never read | v0.3.2 | minor wasted turns; fix with R6 |
| F93 route-blind gate stack, F145 route default catches everything | #1 only | R8 |

Also: `PERMISSION_POSTURE` is dead (#27 retired it 2026-08-12), yet three consumer configs still carry the row. Harmless to cost; worth a cleanup when those configs are next touched.

---

## 5. The testing approach: what to change before testing R1–R8

The research corpus is unusually candid about its instruments, and that candor is the finding. In two months it shipped three levers, pre-registered a prediction for each, and holds a verdict on none. The recommendations below come from the causal-design review and are listed in the order they should land.

### 5.1 Change the primary outcome

P2c (engine share of average context) was chosen because it is *predictable* from engine size, not because it is what is paid. On the cost model, context variation explains ~15% of the bill; turns explain the rest. Three instruments, two baselines, and ~10 PRs were built to detect a 3.6-point P2c effect, while turns had no treatment. Pre-register **three outcomes with units**, and a prediction for each per lever:
1. **Whole-tree USD per completed issue** (primary; `tree_cost.py --sessions` already prices it on each turn's own model).
2. **Peak parent context** (the symptom the research opened with; it has no acceptance criterion anywhere today).
3. **Turns per issue**, parent and subagent.
Keep P2c as a mechanism check for engine-size levers only. Report output tokens (12–18% of the bill, immune to context levers) and post-compaction cache-write reloads explicitly rather than folding them into "share of context ≈ share of cost".

### 5.2 Add a quality outcome, now

Nothing measures whether a cheaper run is a worse run. "Unevaluated does not ship" was the stated rule, and 0.2.1, 0.3.0 (a new gate), and 0.3.1 shipped without a quality reading. Every lever in §3 reduces cost by doing less or doing it elsewhere, so a quality outcome is a precondition, not a nicety. Three that exist in git and the tracker today:
- **Fix-up commits** touching a merged PR's files within 14 days, attributed to the PR (available from `git log` now).
- **F-comments on #1** attributed to a PR (needs #234's session IDs, or a PR number on the comment by convention).
- **Escalations per issue** (gate-error, scope-ruling, and human-option stops), from the journal.
On the paired benchmark (§5.3) add a **blind evaluator**: an agent that scores the two runs' merged diffs against the issue's ACs without knowing which engine produced which.

### 5.3 Use a paired within-issue benchmark, and drop the held-back controls

The staggered rollout DiD was never computed and cannot be: `agentfluent` and `claude-code-sessions` have 1 and 2 ledger rows at 0.2.0, ledger-only (no stratum), different review bindings, and no post-period accrual. Holding them back runs a known-defective engine and buys nothing. **Re-install them and drop the DiD.**

Replace it with the design the plugin cache already supports: **the same issue, run under two engine variants.**
- **Fixture set:** 6–10 closed issues from vote, loop, and esg, each with its base commit, issue text, and ACs frozen (#69's fixture repo). Mix routes and sizes; include at least one that split at review and one that stopped at the plan gate.
- **Replay:** a throwaway worktree at the base commit, the ledger initialized fresh, the plan gate answered by a scripted approval (or a human on a fixed rubric), both variants pinned as versioned plugin-cache directories, the same `(model, effort)` stratum and the same subagent roster for both arms.
- **Order:** interleave arms by issue parity; never run all of one arm first.
- **Replication:** k ≥ 3 runs per issue per arm on one configuration *before* any comparison, to get σ. #209 is this. Until σ exists, declare that only levers predicted at >~25–30% are detectable and stop instrumenting 4% ones.
- **Pre-registration:** the three outcomes, the predicted direction and size per lever, the admissibility rules, and the stopping rule, written before the first run. The corpus has this habit already; keep it.

This design pays for itself on R1 alone: one issue that took 7 rounds, replayed under R1, is a single run's evidence of whether rounds fall.

### 5.4 Recover the independent variable from transcripts

Finding 11's `r = +0.79` uses `gate-rounds` as written by the orchestrator. The adjacent `subagent-runs` field was 2.5× low in the session anchoring the fit, and no ground truth for rounds has been built. Count step-8 round blocks and re-check `Agent` launches from `tool_use` inputs, the way `rounds_vs_turns.py` already does for Budget lines. The same self-report supplies P7, the only quality-shaped guard. Treat every ledger count as an intent record.

### 5.5 Handle compaction consistently

`engine_cost.py`'s `PROP` model scales resident engine tokens proportionally at any context drop; the corpus shows the engine is re-read in full after compaction at 2× a load. `plan_gate_cost.py` excludes compacted sessions; `engine_cost.py` keeps them. The compacting sessions are the expensive ones, so the inconsistency biases P2c down where it matters. Report P9 = 0 sessions separately and price the reload.

### 5.6 Stratify on the roster, not only the parent

F198: `ba` entered vote's roster mid-window and contaminated 13 of 22 after-side sessions. R4 will change rosters on purpose. The stratum must be `(parent model, effort, subagent model set)`, and pinning subagent models in frontmatter is what makes it stable.

### 5.7 Close the open experiments with the data on disk

- **#133 (sharding after side):** vote has 11 admissible 0.3.1 sessions at **P2c 24.4%** (18 of 22 over the full window, 26.2%) against a predicted 25.5%: consistent with the prediction. Loop has 5 completed at 33.9% against 27.4% predicted, interval 17.3–40.1%, unresolvable at n = 5. Post that, and close #128 with the honest reading: the bytes landed, the context share moved where n allows a reading, and the bill did not detectably move because the lever was 4–5% by construction.
- **#223 (v0.2.1 read protocol):** the before side (53–65k ingested) is inadmissible under the frozen `LOAD_TOKENS` floor (68,116). Close it as unjudgeable, with one note: nobody checked whether `Read`'s line-number prefix costs more context tokens per byte than `cat`; the +16–18% move in P2 is consistent with that.
- **P10 (batching):** the 0.3.0 `opus-5@xhigh` sessions exist in the exclusion table of `baseline-2026-10-04.md`. One run of `calls_per_turn.py` on them is the verdict. Today's 1.01–1.02 calls/turn on 0.3.1 says it is "no change".

### 5.8 Instrument hygiene

Six silent detection bugs, each in a plausible direction, and a corpus where most figures exist in two or three versions with pointer notes. The freeze (`52717a4`) was right. Add: a CI job for `docs/research/test_*.py` (tech-debt by the scope brake, but cheap), one canonical table per figure with superseded versions deleted rather than annotated, and the distributional sanity rule the notebook already states (ingestion below one engine copy is a detector failure until proven otherwise) applied to every new script.

---

## 6. Open questions this review could not settle

1. ~~Can a forked skill spawn the finder fan-out?~~ **Settled (§3 R2): yes, to three layers; `Workflow` is parent-only; forked skills need `background: false`.**
2. **Is the ~61k baseline eager or deferred?** `/context` in a loop session. R5 depends on it.
3. **What is the step→turn mapping?** Deferral is worth deletion × (turns after the step ÷ 0.91), and the denominator has never been measured; E4's per-step attribution answers it and orders R2.
4. **How often does a plan split at review?** One grep over the journals; R7 depends on it.
5. ~~Why did `3f30a898` cost $128?~~ **Settled (R9, appendix D): two invocations without `/clear`, and six cache re-warms after gate waits longer than the TTL, worth 32% of the parent bill. The instrument's refusal was correct (two Budget lines, one session); the lesson is that the re-warm cost is invisible to every per-turn instrument and must be added to `tree_cost.py` (cache-write tokens on the first turn after a gap > TTL).**

---

## 7. Proposed epic: `cost: turns first`

The work this review leaves, as issues, with the model each needs. "Fable" marks work where the deliverable is engine prose that must stay consistent with multi-site invariants, or a design whose fail-safe posture has to be argued; that is where weaker runs have cost rounds before (#23: 9 subagent runs and 7 rounds on consistency alone). "Opus 5.5" marks scripts, instruments, config, and PRs that apply a manifest or a design note that already exists.

| # | issue | depends on | model | why |
|---|---|---|---|---|
| 1 | **R1 engine text**: fresh-agent fix application, iteration round ceiling, the deletion rule (absorbs #169, #56; supersedes #153) | design note (appendix A) | Fable for the text; Opus 5.5 for the PR | the passage touches currency, isolation, fresh re-check, and gate-outcome at once |
| 2 | **#133 un-park, post the sharding verdict, close #128** | data on disk (§5.7) | Opus 5.5 | one reading and a comment |
| 3 | **#150 AC1**: three `/context` readings in a loop session; disable unneeded MCP servers if eager | — | Opus 5.5 | an hour |
| 4 | **Quality outcome instrument**: fix-up commits within 14 days per merged PR; escalations per issue from the journal; F-comment attribution convention | — | Opus 5.5 | git and journal parsing |
| 5 | **Per-step cost attribution (E4)** in `tree_cost.py`, with step boundaries recovered from `tool_use` inputs | — | Opus 5.5 | instrument work; the step-marker detector needs the hand-check rule (§5.8) |
| 6 | **Paired benchmark harness**: frozen fixture issues, replay script, scripted plan-gate answer, interleaving, pre-registration template (promotes #211's #208/#209/#210; realizes #69) | 4, 5 | Opus 5.5; Fable for fixture selection and the pre-registration | the predictions per lever are the judgment part |
| 7 | **σ replication** (#209): k ≥ 3 runs per fixture on one configuration | 6 | Opus 5.5 | runs and a table |
| 8 | **R3a deletion PRs** from the manifest (appendix C): class 1 verbatim duplicates (14 rows, 8.0KB net), then class 2 maintainer history to `plugins/CLAUDE.md` (38 rows, 10.2KB) | manifest | Opus 5.5 | the survivor text is written and anchor-checked; one class per PR; five rows carry a named test edit |
| 9 | **R3b class 3 "why"-prose cuts** (95 rows, 28.1KB net) | manifest | Opus 5.5 to apply; Fable to review the survivors once, since each is a rule restated | the manifest already drafted every survivor, so the Fable share is a review pass, not the drafting |
| 10a | **Point-fix PR for the five behavior deltas** the reconciliation found (B1 D1.1, D1.2, D2.1, D2.4; B2 Δ3.3), each with its ruling and reason | appendices B1, B2 | Opus 5.5 | the rulings are made; this is applying them, one site each, with the `SKILL.md` L86 clause change |
| 10b | **#35 collapse** of the five multi-site invariants to the canonical passages B1/B2 draft, with per-region pointer tests | 10a | Fable for the plan-gate and gate-outcome passages (the drifted ones); Opus 5.5 for currency, fresh re-check, and scope ruling (no drift, ~9.1KB of redundancy) | collapsing is where a winner gets picked silently; the rulings in B1 are what make it safe |
| 11 | **R3c finish the reference appendix** (PRD S3): worked example, `- Plan-gate-inferred:`, plan template and lifecycle | — | Opus 5.5 | the PRD already specifies it; `PlanGateFrozenBlockTests` must be re-pointed |
| 12 | **R2 phase-isolation design**: controller + phase skills (`context: fork`, `background: false`), fail-safe posture per phase, the review phase first | 5 (to order phases) | Fable | a new layer in the three-layer split; the posture argument is the deliverable |
| 13 | **R2 spike**: step 3 plan drafting as a forked skill, measured on the benchmark | 6, 12 | Opus 5.5 | implementation of a design |
| 14 | **R4 subagent tiering**: pin `model:`/`effort:` per role; spawn mechanical roles on a cheaper model; roster stratification in the instruments | 4 | Opus 5.5 | frontmatter and a spawn sentence; quality guard from 4 |
| 15 | **R6 read-discipline hook** (`PreToolUse` on Bash, opt-in, fail-open until configured) and the prose it retires | — | Opus 5.5 | same shape as `guard_append_only.py` |
| 16 | **R7 plan-gate scope budget**, after a journal grep for split prevalence | — | Opus 5.5 | small engine passage; the human still decides |
| 17 | **R8 `test` route and route-aware gate depth**, after a route-distribution count | — | Opus 5.5 | config and routing table |
| 18 | **Re-install the control repos** (`agentfluent`, `claude-code-sessions`) and drop the DiD; close #223 | — | Opus 5.5 | a decision and two installs |
| 19 | **Research tests in CI** (`docs/research/test_*.py`) | — | Opus 5.5, `tech-debt` | a workflow file |
| 20 | **R9 gate-wait cost**: step-12 stop message and `SKILL.md` say "one invocation per session, `/clear` before the next"; document `promptCacheTtl: 1h` for API-key consumers in the README; add the re-warm term to `tree_cost.py` | — | Opus 5.5 | two sentences, a README paragraph, one instrument term |

Order: 2, 3, 20 first (hours, and they close open loops). Then 4–7 (the harness; nothing else can be judged without it). Then 1 (the largest modeled lever, and its design note is the appendix). Then 8–11 in parallel with 12–13. 14–17 after the harness exists.

**Milestone.** Nothing here goes into a frozen release milestone by the scope brake; this is a new epic, unmilestoned until the owner triages it, and the deferred-corpus items it absorbs (#56, #153, #35's collapse) move only when their stated conditions are met by the work above.

---

## 8. Appendices

In `cost-review-2026-10-26/`:

- **A** `A-design-R1-fix-agent-and-ceiling.md` — the R1 engine change as replacement blocks per site, with the measured old/new text under `A-blocks/`, the `SKILL.md` bullet, the journal-line changes, and the pre-registered falsifier.
- **B1** `B1-reconcile-plan-gate-and-gate-outcome.md` — every site of the two drifted invariants quoted, seven deltas each, four behavior-changing with rulings, canonical passages and pointers.
- **B2** `B2-reconcile-currency-recheck-scope-ruling.md` — the same for the currency clause, fresh re-check, and scope-ruling stop: no semantic drift, three read-alone defects, ~9.1KB recoverable.
- **C** `C-deletion-manifest.md` and `C-gen_manifest.py` — 147 rows with surviving text, anchor-checked; the generator applies the manifest and re-checks test pins (stdlib; nothing ships or imports it).
- **D** `D-handcheck-3f30a898.md` — the $128 session by phase, round, compaction, and cache re-warm.

## 9. Provenance

Measured 2026-10-26 by the scripts in this directory, unmodified, at `971f21c`: `budget_stats.py --era` on four ledgers; `engine_cost.py` (`--table` and profiles) on 6 loop and 14 vote 0.3.1 sessions (3 refused, listed in the scratchpad); `calls_per_turn.py`, `plan_gate_cost.py`, `tree_cost.py --sessions` on the same sessions. Engine sizes by `wc`. The passage classification of the engine and units is a full-read estimate by line range (the ranges are in the scratchpad as `ranges.py`). Claude Code feature statements are from code.claude.com docs read the same day; items the docs did not confirm are marked in the audit. Backlog state from `gh` the same day. Nothing in the repo was edited by the audits.
