# Decision log

Append-only. Never rewrite a prior entry; if a decision is superseded, add a new entry that says so
and links back. Newest entries at the bottom.

---

## D001 — 2026-08-25 — Engine sharding scoped as the increment, not the seven-unit target

**Context.** The `dev-loop` engine is loaded in full (~46k tokens) into the orchestrator's context on
every invocation; ~42% is reference/procedure material needed at one step or lifecycle event
(`docs/research/loop-cost-and-convergence.md`, Findings 6–9). A seven-unit target design exists
(`docs/research/draft-core.md`) but is explicitly marked not-for-ship.

**Decision.** Scope an epic that ships **only the increment**: extract `accepting` (step 10 +
AC-verifier) and a `reference` appendix (`queue.md` skeleton, `progress.md` worked example, plan
template + lifecycle, Initialization) into on-demand units; add a phase index + load protocol + the
fail-safe half of each deferred unit to core; reword the Gate-outcome invariant's due-ness clause
(B1) so it resolves inside core; add `PhaseIndexIdentityTests` (B3). Target ~30k always-loaded.

**Out of scope, with reasons.** The seven-unit target (not shippable by its own header); B2's four
moves (increment keeps that content in core by construction); controller-ification (a convergence
lever, not a context lever — `Agent` returns are 0.9–3.7% of parent context); the four small units
`planning`/`implementing`/`reviewing`/`landing` (deferring small units may cost more than it saves —
78.6% of read volume is re-reads).

**Trade-off.** Smaller cut (~35% vs. the target's ~67%) in exchange for far lower risk on the central
hazard: sharding creates partial loads, and `SKILL.md`'s design assumes a partial load
over-escalates. The increment defers only the safest chunk (`accepting` strands no decision) plus a
reference appendix.

**Full spec:** `.claude/specs/prd-engine-sharding.md`.

---

## D002 — 2026-08-25 — Milestone left as an OPEN DECISION; PM recommends `v0.2.3`

**Context.** v0.2.1 shipped today (PR #124 + #125; `plugin.json` on `main` = 0.2.1). The seven
behavior-fix findings previously read as v0.2.1 have moved to **v0.2.2**, now an 11-issue patch
train — so v0.2.2 is not available as a dedicated single-epic milestone. v0.3.0 is the corpus-gated
deferral category (24 open issues). The refactor is **effort-gated**, and its value is a *falsifiable*
before/after that requires releasing **alone**.

**Decision.** Do not settle the milestone in the PRD; record three options — `v0.2.3` (new dedicated
milestone, semver-correct patch), `v0.3.0` (the user's instinct, but costs either the category's
defining criterion or a 24-issue relocation), or a named milestone (`engine-sharding`, no version
until release). **PM recommendation: `v0.2.3`.** Human to ratify.

**Why not v0.3.0.** It is the corpus category; using it for effort-gated work dissolves the one
criterion (CLAUDE.md is explicit) or forces relocating 24 issues.

---

## D003 — 2026-08-25 — B3 vacuity-guard values deferred to a separate architect ruling

**Context.** The B3 spec in `core-self-sufficiency-audit.md` ("≥5 units and `planning` among them")
was written for the seven-unit target. The increment extracts only `accepting` + `reference`, so the
phase index is a **two-unit** index and the target-shaped floor does not apply.

**Decision.** Leave S4/AC2 as an explicit open decision. A separate architect pass is ruling on the
floor and the named unit for a two-unit index — and on whether a floor is even the right shape at
that size. Adopt that ruling; **do not guess values.** This avoids rebuilding the enumerable-assertion
trap the repo documents at length.

---

## D004 — 2026-08-25 — Baseline re-freeze split into its own follow-up issue; S5 depends on it

**Context.** The P2 metric is staged: #124 alone moves 53,693 → ~46,000; sharding then moves
~46,000 → ~38,000 (`baseline-2026-08-25.md` → "⚠ P2's baseline shifts once v0.2.1 releases — do not
double-count"). Using the pre-#124 number as the sharding baseline would double-count the recovery
saving #124 already delivered.

**Decision.** Keep "measure #124 alone, post-v0.2.1" as a first-class, **separately-owned** follow-up
issue that re-installs the four consumers and re-freezes P2. S5 **depends on** it rather than
absorbing it, preserving the interpretability the baseline method requires. S5/AC4 cites the baseline
doc's section as the single home for those numbers rather than restating them.

---

## D005 — 2026-08-25 — B3's vacuity guard carries no floor; two further AC corrections

**Context.** D003 deferred the B3 vacuity-guard values to an architect ruling. That ruling landed,
and it re-derived three of the four assertions rather than just the fourth.

**Decision.**
- **Assertion 4:** no numeric floor. Assert `{"accepting", "reference"}` ⊆ the **table** extractor's
  units. A floor's value is headroom; at set size 2 there is none, so `>= N` degenerates to
  "non-empty", which a named member implies more strongly (a count proves *some* row matched; a
  named member proves *that* row parsed). Exact set equality was **rejected** — it duplicates
  assertion 1 while adding an enumeration whose red-run cheap fix is "append the name", which is the
  `ALLOWED_NON_BINDINGS` failure mode. Subset escapes it by polarity and needs no edit as units grow.
- **Assertion 1** presupposes every unit has a fail-safe half. `reference` is an appendix, not a
  gate, so **without a written `reference` fail-safe line the guard is red on day one.** Fix by
  writing the line, never by teaching the guard to classify phase-vs-appendix.
- **Assertion 3** must be scoped to rows citing a numbered step; the appendix is read at lifecycle
  events, not `### N.` headings.

**Supersedes** D003's "values pending". Full reasoning: `docs/research/core-self-sufficiency-audit.md`
→ "B3 — the guard, specified".

---

## D006 — 2026-08-25 — Milestone ratified: `v0.2.3`

**Context.** D002 left the milestone open with three options. The instinct in the room was `v0.3.0`.

**Decision.** **`v0.2.3`**, a new dedicated single-epic milestone carrying this epic and nothing
else.

**Why not `v0.3.0`.** It is the **corpus-gated deferral category** — work lands there when it waits
on *corpus*, not effort — and it currently holds 24 open issues. This work is effort-gated: the
corpus already exists. Using `v0.3.0` would have meant either dissolving the one criterion that makes
it a category rather than a junk drawer, or relocating 24 issues to a renamed category. Neither cost
was worth paying for a version string.

**Why `v0.2.3` is semver-correct.** The change introduces no new or renamed `CAPS` parameter, no
config migration, and no behavior or vocabulary change — the pipeline's step numbering and outcomes
are unchanged. It reorganizes where the engine's own text lives. That is a patch.

**Why dedicated.** The epic's entire value is a falsifiable before/after, and two changes in one
release make both uninterpretable (`docs/research/baseline-2026-08-25.md`). `v0.2.2` is the 11-issue
patch train and cannot provide that isolation.

**Supersedes** D002's "open".


---

## D007 — 2026-08-26 — There is no "measurement site" to choose

**Context.** #126 designates the vote repo as the site for the v0.2.1 before/after. Vote's
`epic-hybrid` run is exhausted, so it accrues no sessions; the v0.2.1 window closes at the v0.2.2
re-install. This was framed as a choice: initialize a vote run, or re-designate `claude-code-loop`.

**Decision.** **Neither. The framing was wrong.** The standing rule is already *report per repo,
never take a median across repos* — so there is nothing to designate. **Measure whatever admissible
sessions exist in each repo, report them separately, and never pool.** Both `claude-code-loop` and
`us_presidential_vote_analysis` run v0.2.1 as of 2026-08-26.

**Consequence, accepted deliberately.** If neither repo reaches n≥5 admissible sessions before the
v0.2.2 re-install, **the v0.2.1 reading ships labelled underpowered, and v0.2.2 is not held for it.**
v0.2.1's prediction is narrow (remove the truncated-`cat` recovery multiplier) and is the least
valuable of the three levers; delaying a release to power it would cost more than the reading is
worth.

**What is load-bearing instead:** the freeze against **v0.2.2**, because #135 moves the sharding
epic's own primary metric (P2c) on its own — batching deletes early, low-context turns, which are
exactly where the engine's share of context is highest. See D008.

## D008 — 2026-08-26 — The sharding baseline freezes against v0.2.2, not v0.2.1

**Decision.** #128's before-baseline is the freeze taken against **the release installed immediately
before the sharding cut — v0.2.2** — never v0.2.1 and never the pre-#124 figures.

**Why.** #124 (v0.2.1) removed the truncation-recovery multiplier and #135 (v0.2.2) removes paging
turns. **#135 lowers `resident/processed` by itself**, so a pre-v0.2.2 before-window credits sharding
with #135's saving. Same double-count hazard already caught for #124/P2, one release later.

## D009 — 2026-08-26 — P2c is the acceptance metric, expressed turn-invariantly; P4 and P8 leave the gate

**Decision.** #128 accepts on **P1** (`wc -c`, settled at merge) and **P2c as
`resident_turns / processed`** only. P2, P3, **P9 (compaction count)** and per-unit arrival centroid
are reported, never gating. **P8 is deleted** (it and P2c are one measurement reported twice).
**P4 is deleted** (its only instrument was retired — see D010).

**Why turn-invariant.** Raw resident-turn tokens scale with turn count, the most confounded quantity
in this corpus, so a post-sharding run on a hard issue reads *up*.

**Baselines, per repo, computed not transcribed:** `claude-code-loop` **18.0%** (n=2 admissible),
`us_presidential_vote_analysis` **22.8%** (n=6). The previously recorded 20.8%/n=7 was wrong twice —
a single session's share-of-bill cell, and pooled across repos.

## D010 — 2026-08-26 — `context_profile.py` is retired, not fixed

**Decision.** Moved to `docs/research/deprecated/`. Not deleted: Findings 6–9 were measured with it
and must stay reproducible.

**Why.** It prefers `toolUseResult` over the tool_result block the model actually received, so on a
spilled record it sizes the full output rather than the 2KB preview — up to 13× over, and engine
reads are exactly what spills. It is the third instrument measuring what `engine_cost.py` measures
better. **P4 (engine share of file-read volume) and the "~50% of every byte the parent reads" figure
rest on it and are withdrawn** rather than re-derived.

## D011 — 2026-08-26 — Expected value of the three levers, after correction

**Decision.** Record these so no downstream scoping re-inflates them.

| lever | value | basis |
|---|---|---|
| avoid one gate round | ~561–850k, input+output, per issue | r=+0.79 + Finding 2's mechanism |
| batch same-file paging (#135) | **~176k/session** recoverable (358k theoretical) | run-length corrected |
| shard the engine (#128) | ~4–5% of a run | modelled, not measured |

**Two retractions folded in.** *"Subagent count does not predict turns"* is **withdrawn** — it rested
on the ledger's self-reported `subagent-runs`, which is 2.5× low in the leverage session; ground
truth gives r=+0.62 to +0.74, better than gate rounds on totals. And #135's value is **half** what was
first filed: a batching protocol keeps the first read as its own turn, so a k-run saves k−2, and 47
of 74 runs in the corpus are k=2.

**Standing stop rule for #128:** budget it at normal round caps and treat an overrun as a *park*
signal. One extra gate round costs ~561–850k; the epic buys ~225k per run. **Each round overrun
costs 2–4 runs of the saving it is buying.**
