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

