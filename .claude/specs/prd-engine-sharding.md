# PRD — Engine sharding: defer `accepting` + a `reference` appendix

> **⚠ SUPERSEDED IN PART — 2026-08-26.** Measurement since this PRD was written has moved its
> numbers and its gate. **`docs/research/loop-cost-and-convergence.md` (Findings 10–12),
> `docs/research/baseline-2026-08-25.md`, and `.claude/specs/decisions.md` (D007–D011) are
> authoritative where they disagree with anything below.** In short:
>
> - **The ~35% figure is a FOOTPRINT cut, not a saving.** Expected effect on a run's bill is
>   **~4–5%** — sharding is *deferral*, not deletion, so in a full iteration the deferred units still
>   load and only the arrival centroid moves. ~7% is a ceiling.
> - **The gate changed.** Accept on **P1** and **P2c as `resident_turns / processed`** only.
>   **P8 is deleted** (circular with P2c) and **P4 is deleted** (its instrument was retired carrying a
>   payload bug — D010). **P9** (compaction count) is observed, never predicted.
> - **The before-baseline freezes against v0.2.2, not v0.2.1** (D008): #135 lowers `resident/processed`
>   on its own by deleting early low-context turns.
> - **The 53,693 P2 figure is retracted** — it came from a filter that counted heredoc writes as
>   engine reads. Per-repo P2c baselines: `claude-code-loop` 18.0%, `us_presidential_vote_analysis`
>   22.8%.
> - **Sharding is the third of three levers**, not the first: one avoided gate round ≈ 561–850k,
>   batching same-file paging ≈ 176k/session (#135), sharding ≈ 4–5% of a run.


**Status:** scoped, pending human ratification. Not filed on GitHub.
**Author:** PM agent · **Date:** 2026-08-25
**Epic (draft):** `epic:engine-sharding` — Shard the loop engine: defer `accepting` + a `reference`
appendix to cut always-loaded context ~35%
**Source research (authoritative — read before implementing):**
- `docs/research/loop-cost-and-convergence.md` (Findings 6–9 motivate this)
- `docs/research/context-architecture-refactor.md` (the "Sequencing" section is what ships)
- `docs/research/core-self-sufficiency-audit.md` (B1 wording verbatim, B3 spec, B2 line ranges)
- `docs/research/baseline-2026-08-25.md` (P1–P7 predictions and the re-freeze note)
- **Not** `docs/research/draft-core.md` — that is the seven-unit *target*, explicitly not what ships.

---

## 1. Problem

The `dev-loop` engine (`skills/dev-loop/loop-engine.md`) is read **in full into the orchestrator's
context on every invocation** — ~44,400 tokens, ~45,937 with `SKILL.md`. Six profiled real sessions
show the cost:

- The engine is **~29% of a 200k context budget, spent before the loop does any work**, on every
  invocation, in every consuming repo — a floor a consumer cannot opt out of or tune.
- The engine is **~50% of every byte the parent reads** in a session. File reading, not subagent
  delegation (0.9–3.7% of parent context), is where parent context goes.
- **~42% of the engine is reference/procedure material needed at exactly one step or lifecycle
  event**: the AC-verifier (16.3%, step 10 only), the `progress.md` worked example (12%,
  journal/init), the `queue.md` skeleton (7%, init only), Initialization (1.1%, new run only).
  Meanwhile ≥11.3% of invocations stop at the plan gate having loaded 100% of the engine to execute
  perhaps a quarter of it.

This applies the plugin's own three-layer split one level down: a leaner always-loaded **core**
(pipeline, gate table, routing, tool surface, fail-safe invariants, a phase index) plus **on-demand
units** that core names at the point of use. This PRD covers **only the increment** — extract the
two largest genuinely-late chunks — targeting **~30k always-loaded** (a ~35% cut).

### The hard constraint

`SKILL.md`'s entire design assumes a partial load **over-escalates** (safe) rather than under-gates.
Sharding creates partial loads on purpose. Get it wrong and we recreate the exact hazard
[#124 / F105/F106](https://github.com/frederick-douglas-pearce/claude-code-loop/issues/1) *just
closed*: a coherent-reading engine that silently ends before a gate. The architect review's reframe
is the design spine — what keeps this safe is the **retained Gates table + Gate-outcome invariant +
explicit load protocol**, not the fail-safe halves alone.

---

## 2. Scope

**In (the increment):**
- Extract **`accepting`** (step 10 detail + the AC-verifier procedure) into an on-demand phase unit
  read at step 10.
- Extract a **`reference` appendix** (`queue.md` skeleton, the `progress.md` *filled worked example*,
  the plan template + lifecycle, Initialization) into on-demand file(s).
- **B1** — reword the Gate-outcome invariant's due-ness clause so it resolves inside core
  (replacement wording verbatim-ready in the audit).
- Add the **phase index** + explicit **load protocol** + the **fail-safe half** of each deferred
  unit to core.
- **B3** — `PhaseIndexIdentityTests` guarding the index (identity/existence, never truth).
- **Release alone and measure** against the frozen baseline predictions P1–P7.

**Out (explicitly, each for a stated reason):**
- **The seven-unit target** (`docs/research/draft-core.md`). Stored for durability; its header says
  it is NOT what ships. Scoping the target instead of the increment is the single most likely way to
  get this wrong.
- **B2's four moves** (status vocabulary, `queue.md` header semantics, Router, Resume into core). The
  increment keeps these in core *by construction*, so moving them is work the increment exists to
  avoid.
- **Controller-ification** (parent stops implementing/applying fixes). Separate change, justified on
  convergence not context — `Agent` returns are only 0.9–3.7% of parent context, so it is not a
  context lever.
- The remaining four units (`planning`, `implementing`, `reviewing`, `landing`). Deferring small
  units may cost more than it saves (78.6% of read volume is re-reads).

---

## 3. Epic acceptance criteria

1. **Always-loaded footprint drops to ~30k tokens** (`SKILL.md` + `loop-engine.md` core), verified by
   `wc -c`, down from 45,937.
2. **Every safety decision still resolves inside core.** No `(step N)` cross-reference in core that
   decides whether a gate is due, whether it passed, whether to stop/proceed, or what may merge,
   resolves against text that now lives in a deferred unit. (B1 closes the one known such reference.)
3. **Each deferred unit's fail-safe half remains in core** and is named in the phase index; each unit
   is loaded by an **explicit read-this-now instruction at its point of use**, and the F105
   completeness rule (an unconfirmed/incomplete load is not loaded ⇒ STOP/escalate) applies per unit,
   extended into `SKILL.md`'s fail-safe posture.
4. **`PhaseIndexIdentityTests` ships** with the assertions and non-assertions specified in the audit,
   and each assertion has been shown to fail against a deliberate mutation of the thing it guards.
5. **The full existing test suite passes on 3.9–3.13**, and every existing consistency guard whose
   anchored content moved (at minimum `PlanGateFrozenBlockTests`' plan-template region) has had its
   region anchors updated and re-mutated.
6. **Falsifiable measurement gate** (§4) — the change is released *alone*, re-measured, and judged
   against P1–P7 with both engine versions recorded.
7. **No consumer-facing behavior, vocabulary, or config change.** No new/renamed `CAPS` parameter (so
   `/init-loop` and `CapsVocabularyTests` are untouched); the pipeline's step numbering and outcomes
   are unchanged.

---

## 4. The falsifiable measurement AC

> **Given** the baseline re-frozen *after* v0.2.1's release (installed version and P1–P7 recorded
> from ≥5 completed, non-live real sessions via `context_profile.py`, plus `budget_stats.py`),
> **When** this epic's shards are released as their own version and re-installed, and P1–P7 are
> re-measured on a comparable set of completed real sessions with the new installed version recorded,
> **Then** the epic is accepted **only if**:
> - **P1** always-loaded ≈ 30,000 (settled by `wc -c`; cannot fail unless the change was not made),
> - **P2** engine-load-per-session falls materially toward ~38k, **P3** plan-gate-stop load toward
>   ~30k, **P4** engine share of file-read volume toward ~45% — the direct metrics move as predicted;
>   **and**
> - **P6** subagent-runs (median 6) and **P7** gate-rounds (median 5) show **no material change**.
>
> **A drop in P6 or P7 is a RED FLAG, not a pass.** Sharding moves where instructions are stored; it
> touches nothing about convergence. If gate-rounds fall, the most likely cause is confounding (which
> issues happened to be worked), and the epic must **not** be credited with the improvement — the
> finding is "investigate the confound," and acceptance is withheld until P6/P7 are explained. The
> before/after numbers (both installed versions named) are posted to the **#1 findings index as a
> comment** (never a PR against #1) and linked from the epic.

**P2 baseline — do not double-count.** The P2 figures are *staged*: #124 alone moves 53,693 → ~46,000
by removing the truncated-`cat` recovery multiplier; sharding then moves ~46,000 → ~38,000. Use the
**post-v0.2.1** number (~46,000) as the sharding baseline, not the pre-#124 53,693. The authoritative
home for this is `docs/research/baseline-2026-08-25.md` → **"⚠ P2's baseline shifts once v0.2.1
releases — do not double-count"** (with the two-stage table). Cite that section; do not restate the
numbers here.

---

## 5. Child stories

Each is sized as a plausible single loop iteration. Repo convention: selection order is a
`**Delivery order:** PR <n>` trailer in the issue body (no `priority:*` labels).

### S1 — Reword the Gate-outcome invariant's due-ness clause to resolve inside core (B1)
**Labels:** `enhancement` · **Delivery order:** PR 1 · **Depends on:** —

Replace the due-ness sentence (currently "due-ness is decided where it always was (**the gate's own
step** and the Routing table)", `loop-engine.md` ~line 2013) with the audit's verbatim replacement,
resolving the predicate against the Gate table's *When* column + the Routing table (both in core).
Load-bearing before `accepting` is deferred: once step 10 leaves core, "the gate's own step" points
at deferred text.

**ACs**
1. Clause replaced with the audit's wording verbatim (`core-self-sufficiency-audit.md`, "B1 —
   replacement wording, ships as-is"), including the `HERMETIC_TEST_CMD` parenthetical.
2. Due-ness predicate resolves entirely against in-core text; no part points at steps 3–12's bodies.
3. No semantic change to due-ness for any gate — relocates *where authority is stated*, not *what is
   due*.
4. Full suite green.

*Note:* independently safe; may be bundled into S2, but if separate it **must precede S2**. This is
the only one of the audit's six failures load-bearing for the increment.

### S2 — Stand up the phase index + load protocol and extract `accepting`
**Labels:** `enhancement` · **Delivery order:** PR 2 · **Depends on:** S1

The heart of the epic. Add the phase index + explicit load protocol to core; extract step 10 detail
+ the AC-verifier into `phases/accepting.md`; keep `accepting`'s fail-safe half (*cannot run ⇒
cannot merge ⇒ human*) in core; extend `SKILL.md`'s fail-safe posture to phase units.

**ACs**
1. Core gains a **phase index** (unit → file → step-to-read) and a **"what holds without each unit
   loaded"** fail-safe section; both cover exactly the extracted set (`accepting`).
2. Step 10 detail + AC-verifier move to `phases/accepting.md`; core's step 10 carries an **explicit
   read-this-now instruction** naming the file, plus the fail-safe half (due-ness in the Gate table's
   *When* column; *cannot run ⇒ cannot merge ⇒ human* in core).
3. **Load protocol in core:** an on-demand unit that cannot be confirmed loaded in full is treated as
   not loaded ⇒ STOP/escalate (the F105 completeness rule, per unit).
4. `SKILL.md`'s fail-safe invariants extended so a partial load omitting a phase unit
   **over-escalates**.
5. Always-loaded footprint measurably drops (toward ~30k; `reference` in S3 completes the cut).
6. No safety reference stranded: core points into `accepting` only from acted-at-step-10 content.
7. Full suite green; any guard anchored on moved content updated in this PR and re-mutated.

*Note:* largest, riskiest iteration ("sharding machinery + first shard"); cannot be cleanly
sub-split (an index entry cannot precede the file it names). `accepting` first is deliberate — safest
deferral (strands no decision), large win (~8.1k).

### S3 — Extract the `reference` appendix and update anchored consistency guards
**Labels:** `enhancement` · **Delivery order:** PR 3 · **Depends on:** S2

Extract the `queue.md` skeleton, the `progress.md` filled worked example, the plan template +
lifecycle, and Initialization into `reference/*.md`; extend the phase index + fail-safe section;
update guards whose anchored content moves.

**ACs**
1. `reference` content moves to `reference/*.md`, each named at its point of use with a read-this-now
   instruction; phase index and fail-safe list grow to include `reference` (set equality maintained).
2. **`progress.md` is split, not moved wholesale** (audit refinement): its **gate-decision line
   vocabulary** — `- gate-error:`/`- gate-fallback:` distinction, the four `- Plan-gate:` spellings
   (canonical enumeration), the `- Budget:` grammar — **stays in core** (the Gate-outcome invariant,
   Guardrails stuck-check and step-1 budget cap resolve against it). Only the *filled example* and
   open/close-record prose defer.
3. **Anchored guards updated in this PR and re-mutated:** at minimum `PlanGateFrozenBlockTests` — its
   plan-template-fence region anchor now lives in `reference/*.md` (re-point it, or keep the
   frozen-block heading in core). Confirm `PipelineStepOrderTests` still resolves (the pipeline
   table-of-contents / step numbering must remain enumerated in core).
4. Always-loaded footprint reaches the ~30k target.
5. Full suite green.

*Note:* trickier than `accepting` (the `progress.md` split and the guard-anchor coupling); "extract
the whole section" would silently break `PlanGateFrozenBlockTests`.

### S4 — Ship `PhaseIndexIdentityTests` (B3)
**Labels:** `enhancement`, `tech-debt` *(see §7)* · **Delivery order:** PR 4 · **Depends on:** S3

Add `PhaseIndexIdentityTests` to `tests/test_repo_consistency.py`, guarding the index by identity and
existence (never truth), covering the full extracted set.

**ACs**
1. Asserts, per the audit: (a) **unit-set identity** — unit names in the index table equal unit names
   in the "what holds without each unit loaded" list (set equality); (b) **file existence** — every
   `phases/*.md` / `reference/*.md` the index names resolves to a real file; (c) **step
   resolvability** — every step number in the "read it at" column is a real pipeline step (reusing
   existing heading-resolution logic); (d) a **vacuity guard**.
2. **RESOLVED 2026-08-25 — vacuity guard carries no floor.** The audit's "≥5 units and `planning`
   among them" was seven-unit-target-shaped. Ruling: **drop the numeric floor**; assert
   `{"accepting", "reference"}` as a **subset** of what the **table** extractor found. A floor's
   value is headroom, and at set size 2 there is none, so `>= N` collapses into "non-empty" — which
   a named member already implies, and more strongly. Subset rather than equality, so additions can
   only satisfy it, never falsify it; it needs no edit as units are added. Full reasoning and the
   two further corrections below live in `docs/research/core-self-sufficiency-audit.md` → "B3 — the
   guard, specified". (D005.)
3. **Two further AC corrections from the same ruling, both load-bearing:**
   - **AC1 as written would be RED ON DAY ONE.** Set equality between the index table and the
     fail-safe list presupposes every unit has a fail-safe half — but `reference` is an *appendix*,
     not a gate. **S2/S3 must write a `reference` fail-safe line** ("needed only at init and
     journal; core over-escalates without them"). Do **not** fix this by teaching the guard to tell
     a phase from an appendix; that hands it semantics it must not own.
   - **AC1(c) step resolvability must be scoped to rows that cite a numbered step.** `accepting` is
     read at step 10, but the `reference` appendix is read at lifecycle *events* (Initialization,
     journal) that are not `### N.` headings.
4. Docstring states the non-assertions verbatim (does not check that a fail-safe half correctly
   states its posture; does not check gate→unit assignment; does not check any posture is right — all
   review-owned). A green run means "the index is internally consistent and its files exist," never
   that the fail-safe halves are correct.
4. Each assertion demonstrated to fail against a deliberate mutation of what it guards.
5. Never red on any intermediate commit (lands after the files it names exist).

*Note:* may instead be authored in S2 scoped to `accepting` and extended in S3 — developer's call.
Landing once after S3 keeps it simplest to mutate-verify.

### S5 — Release alone and measure against the baseline
**Labels:** `enhancement` · **Delivery order:** PR 5 ·
**Depends on:** S4; the **baseline re-freeze follow-up issue** (see §6, filed separately)

Cut the release (bump `.claude-plugin/plugin.json` + update the `README.md` status block in the same
PR, per standing convention), re-install, run the profilers, judge P1–P7. Owns §4's measurement AC.

**ACs**
1. `plugin.json` bumped and the README status block updated in the same PR; the README trust-model
   section reviewed for any load-protocol wording that must move with it.
2. The plugin is re-installed in the consumers and the installed version recorded (the loop executes
   the *installed* plugin, not the tree).
3. §4's falsifiable measurement AC executed and its verdict recorded to the #1 findings index
   (comment, never a PR): P1–P4 hold; **P6/P7 show no material change**, and a drop in either is
   treated as a confounding alarm withholding acceptance, not a success.
4. The before-baseline used is the **post-v0.2.1** freeze owned by the re-freeze follow-up issue (P2
   baseline ~46k, not the pre-#124 53,693), so the refactor's P2 contribution is not double-counted
   against the recovery saving #124 already delivered. Cite
   `baseline-2026-08-25.md` → "⚠ P2's baseline shifts once v0.2.1 releases — do not double-count."
   Both installed versions (before and after) named in the record.
5. This release contains **only** this epic's shards — no v0.2.2 patch-train fix rides along (that
   would make P2 uninterpretable).

---

## 6. Sequencing against the v0.2.1 release

**v0.2.1 has shipped.** PR #124 (F105) and PR #125 (the release: version bump 0.2.0→0.2.1, README
status block, `BACKLOG_SOURCE` repointed v0.2.1→v0.2.2) both merged 2026-08-25; `plugin.json` on
`main` is **0.2.1**. So S5's former external dependency — "#124 released and measured in isolation
first" — is **partly discharged**: the release is cut. What remains:

1. **Re-install in all four consumers** (`claude-code-loop`, `us_presidential_vote_analysis`,
   `agentfluent`, `claude-code-sessions`) so runs execute the 0.2.1 engine.
2. **Re-freeze P2** against 0.2.1 (validates #124's isolated ~46k prediction and sets the sharding
   baseline).

**This re-freeze is a separate follow-up issue, filed on its own**, that owns the post-v0.2.1 P2
measurement. **S5 depends on it rather than absorbing it** — keeping the "measure #124 alone" step a
first-class, separately-owned deliverable preserves the interpretability the baseline method
requires.

**Risks in the ordering (flagged):**
- **Interpretability if not truly isolated.** If any v0.2.2 patch-train fix rides the sharding
  release cut, every direct-metric prediction is muddied. The dedicated milestone (§7) enforces
  isolation (S5/AC5).
- **The measurement — not the green suite — is the real gate.** Consumers run the *installed* plugin,
  so both the benefit and any partial-load regression only appear after re-install. A green suite at
  merge is necessary but not sufficient.
- **Window risk.** Between merge and re-install, any newly onboarded consumer gets the old engine.

---

## 7. Milestone — RATIFIED: `v0.2.3`

**Decision, 2026-08-25: `v0.2.3`, a new dedicated single-epic milestone.** The options below are
kept as the record of what was weighed; the decision is made and D006 logs it. `v0.3.0` was
considered and declined at the stated cost — it is the corpus-gated deferral category and holds 24
open issues, so using it for effort-gated work would have meant dissolving that criterion or
relocating them.

### What was weighed

The v0.2.1 read in the original draft is stale: #106, #108, #109, #111, #112, #114, #115 were
reassigned to **v0.2.2**, which now has **11 open issues** — so v0.2.2 is the busy patch train and is
**not** available as a dedicated single-epic milestone.

The isolation requirement stands: the epic's entire value is a *falsifiable* before/after, and the
baseline method is explicit that "two changes in one release make both uninterpretable." So this must
release **alone**, in a milestone that carries nothing else.

**Options:**

| Option | What it is | Cost / caveat |
|---|---|---|
| **`v0.2.3`** *(recommended)* | A new dedicated single-epic milestone. | Semver-correct — no CAPS change, no config migration, no behavior/vocabulary change; an internal reorganization is a **patch**. Preserves measurement isolation; reorganizes nothing. |
| **`v0.3.0`** | The user's instinct. | v0.3.0 is the **corpus-gated deferral category** and currently holds **24 open issues**. Using it for effort-gated work means **either** dissolving the one criterion that makes it a category rather than a junk drawer (CLAUDE.md is explicit) **or** relocating those 24 to a renamed category milestone. Real cost, stated plainly. |
| **Named milestone** (e.g. `engine-sharding`) | A milestone with no version string until release. | Sidesteps the semver-name collision entirely; the version string is chosen at release time. |

**Ratified: `v0.2.3`** — a new, dedicated, single-epic milestone. It is semver-correct (this is
a patch: internal reorganization with no consumer-facing surface), preserves the measurement
isolation the whole epic depends on, and avoids disturbing the 24 issues sitting in the v0.3.0
category. If you prefer to decouple the name from semver, the **named-milestone** option is the clean
fallback. **`v0.3.0` is not recommended** for the reason above — it is the corpus category, and this
work is effort-gated.

**This is a human decision; the PRD does not settle it.**

---

## 8. Open decisions (blockers before build)

1. **Milestone** (§7) — recommend `v0.2.3`; human to ratify.
2. **B3 vacuity-guard values** (S4/AC2) — floor + named unit for a two-unit index, and whether a
   floor is the right shape at that size. Owned by a separate architect pass; adopt its ruling, do
   not guess.
3. **Confirm the baseline re-freeze follow-up issue** is filed and owns the post-v0.2.1 P2
   measurement, so S5 can depend on it.

---

## 9. Risks

1. **The partial-load hazard (central risk).** Sharding deliberately creates the shape #124/F105/F106
   just fixed: an engine that reads as complete but silently ends before a gate. Mitigations, all
   in-scope: fail-safe half of each deferred unit stays in core; the Gates table + Gate-outcome
   invariant + explicit load protocol remain in core (the architect reframe: *these*, not the
   fail-safe halves alone, make it safe); each unit loaded by explicit read-this-now with the F105
   completeness rule per unit; `SKILL.md`'s over-escalation posture extends to phase units.
2. **B3 spec was written for the target, not the increment** (see §8.2). The vacuity guard's
   target-shaped values must be re-derived to the two-unit reality — an open decision, not a guess.
3. **Cross-test coupling breakage.** Extracting the plan template moves content
   `PlanGateFrozenBlockTests` anchors on; content near step headings could disturb
   `PipelineStepOrderTests`. These fail *silently correct* — prose still reads fine while the
   mechanism dies. S3 must update anchors in the same PR and re-mutate.
4. **Scope creep into the target.** The audit's B2 line ranges and `draft-core.md` are seductive;
   moving status vocabulary / Router / Resume into core is unnecessary for the increment and actively
   out of scope.
5. **Measurement over-claiming.** P5–P7 are confounded at n≈5; a favorable move is weak evidence and
   a P6/P7 *drop* is a confounding alarm. §4 withholds acceptance on a P6/P7 drop rather than banking
   it.
6. **Window risk.** Between merge and re-install, newly onboarded consumers get the old engine; a
   partial-load regression only manifests post-re-install.

*On S4's `tech-debt` label:* the scope brake's rule 3 ("a guard on a guard never ships in a release")
does **not** apply — B3 guards a *runtime deliverable shipping in this very release*, not test
infrastructure or doc accuracy. Keep it in the milestone; the label is advisory, human to confirm.
