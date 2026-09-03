# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A **Claude Code plugin** (`dev-loop`, distributed via the `claude-code-loop` marketplace) that
packages a supervised dev-loop engine originally built and hardened in
[AgentFluent](https://github.com/frederick-douglas-pearce/agentfluent). The deliverable is almost
entirely **prompt artifacts** (markdown read by an agent at runtime) plus **one Python hook**. There
is no build, no package, and no dependency manifest. CI is a single GitHub Actions workflow that
runs the stdlib test suite — nothing is installed, and nothing should need to be.

Consequence: most "code" here is instructions a future agent will execute. Precision of wording,
internal consistency of cross-references, and the fail-safe posture of each instruction *are* the
correctness properties — review changes to `.md` files as carefully as code.

## Commands

```bash
python3 -m unittest discover -s tests        # full suite (stdlib unittest only; no pytest, no deps)
python3 tests/test_guard_append_only.py      # one module, direct
python3 -m unittest tests.test_guard_append_only.CheckTests.test_blocks_dropping_entries   # one test
```

Stdlib `unittest` only — **never add pytest or any dependency.** The guard hook runs under bare
`python3` in a consumer's environment, so the suite must run there too. CI
(`.github/workflows/test.yml`) runs `discover` on Python **3.9–3.13** for `push` to `main` and every
PR; the aggregate **`test-suite`** job is the stable name for branch protection to require, so the
matrix can change without editing the protection rule. A need for `pip install` in CI means the
stdlib-only constraint was broken — fix the code, not the workflow.

### What is and isn't covered

Three modules, and the split between them matters:

- **`tests/test_guard_append_only.py`** — behavior of the guard hook.
- **`tests/test_mutate_verify.py`** — behavior of `tools/mutate_verify.py`, the mutation harness.
  Added by #60, and the reason it exists is worth keeping: the prose version of this apparatus could
  not converge because **every review round re-derived its correctness by reading** — there was
  nothing to execute. These tests are what make a green suite say something about it. They are
  behavioral: what the harness does to a tree, and what it refuses to do. The harness was inert with
  respect to the engine when it shipped; **#60's second PR wired it in** — `loop-engine.md`'s Part 2
  now names it as the thing a due mutation pass runs, so these tests are the only executable
  evidence behind a gate that edits source code.

  **No claim is made here about these tests being mechanism-shaped rather than outcome-shaped, and
  that absence is deliberate.** Two earlier drafts of this bullet asserted it; both were false when
  written, and the second was a *reword* of the first with a hedge added. Three separate reviews of
  #60 each found an outcome-shaped or vacuous test in this very module — one of them created by the
  commit that fixed the previous one. The discipline is real and is applied per-test where it bites
  (`test_the_only_thing_the_harness_executes_is_the_callers_test_command` walks the AST instead of
  grepping for `git`, because a substring search passes for any implementation that avoids the
  word). But a **file-level** guarantee of it is exactly the enumerable assertion this project keeps
  having to retract, so it is not made. Check the test, not this sentence.
- **`tests/test_repo_consistency.py`** — **mechanical** checks on the markdown/JSON deliverable:
  the shipped example sidecar still loads through the real `load_registry`; the composed
  `plugin@marketplace` identifier still matches every hand-written call site; engine `CAPS` ⊆
  the `/init-loop` skeleton (see the three-layer split below — this is that contract, enforced);
  `PlanGateFrozenBlockTests` — the frozen-approach heading #28's always-on plan-gate stop is looked
  up by appears, normalized, in each of four *located regions* of the engine (see the invariants
  section below for why that string, and only that string, is checkable — and why per-region rather
  than a global count);
  and `PipelineStepOrderTests` — the pipeline's **step *ordering*** agrees across the **five**
  restatements of it, in **three** files: `loop-engine.md`'s `### N.` headings, `SKILL.md`'s numbered
  chain, `plugin.json`'s `description` (published with the plugin), `SKILL.md`'s **frontmatter
  `description`** (`plan→architect→implement→review→merge` — the string the model reads when
  deciding to invoke the skill, so a behavior surface, not prose), and the engine's in-prose
  `step N` cross-references. (`loop-engine.md` ×2, `SKILL.md` ×2, `plugin.json` — which is why five
  restatements live in three files.) The naive grep
  (`grep -oE '[Ss]teps?[ -][0-9]|[Ss]tages?[ -][0-9]' skills/dev-loop/loop-engine.md | wc -l`) does
  **not** find them all: the rest are line-wrapped, which is exactly how they went unguarded until
  review caught it. **No site count is stated here, deliberately** — the figures this sentence used
  to carry went stale where they stood. The assertion is a deliberately loose floor
  (`_MIN_STEP_REFERENCES`), not a measurement, so there is no *maintained* count anywhere to cite:
  the figures in `tests/test_repo_consistency.py`'s docstrings are unmaintained prose and were
  already stale when this sentence was written. `PipelineStepOrderTests` checks numbering and label
  correspondence **only** — never whether a
  step is the *right* thing to do at that point, and never the pipeline's *status* vocabulary (the
  `queued → routed → …` chain lives in the ledger format, not in headings). `plugin.json` and the
  frontmatter chain are both pinned loosely, by ordered subsequence: they may keep omitting internal
  steps, and reorderings are caught only *among the labels each lists* — a swap involving a step one
  omits is invisible there and rests on the `SKILL.md` numbered-chain check. The frontmatter's
  **label count is pinned** (`_EXPECTED_FRONTMATTER_LABELS`) because a *shortened* chain is still a
  valid subsequence and would otherwise pass while checking less.

  **What a renumber still slips past** — the coverage claim is deliberately narrow, and **#31 has
  now run, so read this as a report rather than a warning.** The cross-reference check asserts
  **resolvability only**: every referenced N is a real heading number. It cannot know that `step 8`
  still *means* code review —
  that is semantics, which this module does not do. It fires when a reference goes **out of range** —
  whether edited to a number no heading defines, or left behind when the heading run shrank or was
  rebased off zero. Stated bluntly, because this is the case #31 actually hit: **insert a step
  mid-pipeline, renumber everything after it, and every one of those reference sites points at the
  wrong step with the whole suite green.** Confirmed by mutation (#44), along with the milder shapes — appending a step
  and updating `SKILL.md` passes, as does rewriting a `(step 9)` to `(step 7)`. **A green run is not
  evidence the cross-references were correctly renumbered.** (Those two numbers are #44's mutation as
  it was actually run, against the pre-#31 numbering — a historical record, deliberately not
  re-mapped.) **What #31 confirmed in practice:** it rotated 7–10 across 39 sites and the suite was
  green before a single one had been *read*. **Several** of the sites that changed meaning carried
  **no step number at all** — they reasoned from ordering in prose — so no matcher could have reached
  them. (No count here on purpose: three separate readings each found some and missed others, which
  is the same reason this file states mechanisms rather than tallies.)
  The evidence that a renumber is correct is a site-by-site reading; it is not available from this
  module and never will be. Reference *forms* the regex does not
  match (`steps 3 and 7`, `steps 3, 7`, `step #7`) are invisible too; none is used today, and each
  is excluded deliberately — treating `,`/`and` as separators makes ordinary prose ("step 12 — 40
  lines max") parse as a step range and fail.

**Prompt *semantics* remain validated by review + dogfooding, and that is deliberate** — the
consistency module tests couplings, never whether an instruction is *right*. Do not try to grow it
into a semantic test of the engine.

Two habits it depends on. First: these checks **pass against the tree they were written for**, so a
green run proves nothing by itself — when you change one, mutate the thing it guards and confirm it
actually fails. Second: `CapsVocabularyTests.ALLOWED_NON_BINDINGS` is an escape hatch (currently two
env vars and the meta-term `CAPS`). Adding to it is almost always the wrong fix — a growing
allow-list means the test is being worked around rather than the vocabulary kept in sync.
`PipelineStepOrderTests._STOPWORDS` has the identical property: padding it is the easy way to make a
failing label comparison pass, and it is just as much a worked-around test.

**The ceiling on a prose guard: it can pin a coupling's *identity*, never a proposition's *truth*.**
Established by ruling on #33 (PR #96) after three successive attempts to guard the *polarity* of an
engine claim were each judged outcome-shaped by a fresh checker, and each defeated by a one-word
edit — assert the token appears, and the negation is deleted; match the negation, and the predicate
it attaches to is reworded; enumerate the accepted phrasings, and you have built
`ALLOWED_NON_BINDINGS` again, where the cheap fix for a red run is to append the new wording. Note
what the guards that *do* work here pin: `PlanGateFrozenBlockTests` and `ResumeHandoffPointerTests`
both pin **labels and headings** — arbitrary strings where any change is a real change — and
`CurrencyExemptionAgreementTests` pins two passages **against each other**, so drift in either
direction fails. All three assert that a coupling still exists and still names the same thing. None
asserts that a sentence means what it says, because no regex over prose can.

Two consequences, and the second is the useful one. **Do not "complete" a guard by adding the
polarity assertion back** — that is the displacement loop, not a gap someone forgot. And **when a
claim's polarity is load-bearing, the fix is a product fix, not a test**: word the instruction so
the dangerous reading requires *adding* a claim rather than deleting a word, which moves the
property into structure where a guard can reach it. Failing that, polarity is review's to own, and
saying so in the test's docstring is the honest record.

**When the ceiling does not announce itself — a round cap on a single assertion.** A prose guard
rewritten twice and defeated twice is *at* the ceiling, not two rounds short of clearing it. The
third change may not be another literal or another locus: it must be a different **shape**
(presence → position, prose → parsed structure), a **product fix**, or **deletion with the property
named in the docstring as review's**. Retuning the literal is the displacement loop with a longer
string. Established by #122 (PR #145), where one assertion — that step 8's `guard-efficacy` skip
rendering carries its one legal reason — was rewritten **four** times, each after a fresh checker
defeated the previous version. Every one of them changed the literal and none changed the
assertion's shape, which is why each defeat read as a bad literal rather than as the pattern it was.

**What a guard over prose must survive, and what it must not be asked to.** It must survive **edit**
and **delete** — reword the pinned string, move it, remove it. It is **not** required to survive
**append**: a spare mention beside the real one, a scope clause bolted onto a mandate, a second
member added to a closed enumeration. No containment or position check over prose can stop an
append, and #122 **measured** that rather than asserting it — its battery carries the append case
with `expect: survived`, so the boundary sits where the next reviewer will look. Append-class
hazards are real and they are **review's**, exactly as the ceiling above assigns polarity and scope.
**A reviewer who defeats a prose guard by adding text has demonstrated the documented ceiling, not
found a gap** — that goes on #1, never into another round on the branch.

**The positive prescription the trap above has been missing: a rule about which states are *safe*
must be written default-deny — unknown ⇒ unsafe — never as an enumeration of the safe set.** The
section above governs *guards*; this governs *product prose*, and it is what the enumerable-assertion
trap looks like when the enumeration is user-facing rather than in a test. Established by #34, where
one README rule — which ledger rows are safe to leave before a plugin upgrade — was rewritten
**seven** times. Each of the first six enumerated a safe set or a set of tests and was falsified by a
state it did not enumerate (`park`, then `hold`, then `blocked`, then a PR-column check that was
really a non-empty-cell check, then a gate-errored row with work but no PR, then `planning` rows a
discharge test cleared). The version that held inverted the posture — name the safe statuses, treat
everything else including an unrecognised status as in flight, and close with *"if you cannot tell,
it is in flight."* That is the posture the engine already uses at the merge gate, for an absent
`plan-gate:`, and in #34's own unknown-status stop; the rule was the one thing in that change written
fail-open. **What makes the inverted form safe is not that its list is finally complete — it is that
a state nobody enumerated now resolves in the harmless direction.**

Two corollaries, and the first is the one that cost the most to learn. **Once a rule is default-deny,
its backstop *is* the argument — do not defend it with a completeness proof.** #34's seventh attempt
justified a test three verifiers had failed to falsify with the claim that "the plan file is the
first thing the pipeline writes for a row"; that claim was false five ways, and deleting it cost
nothing, because the fail-safe never needed it. A completeness argument bolted onto a default-deny
rule reintroduces exactly the enumerable assertion the inversion escaped, and it is the hardest
sentence in the passage to make true. **Second: when you invert a rule's posture, carry the inversion
through every sentence in one pass.** Five of #34's nine gate rounds were post-inversion polish, each
finding a leftover coverage claim in a sentence *adjacent* to the one just fixed. That is an
authoring discipline, not a missing gate — the round caps forced escalation every time and worked,
and none of this belongs in `loop-engine.md`, which consumers execute.

## Architecture — the three-layer split

The load-bearing design is a strict separation between **generic engine**, **per-project bindings**,
and **thin entry point**:

1. `skills/dev-loop/SKILL.md` — the entry point Claude loads when the skill is invoked. It is
   deliberately thin: it names the two files to read, then restates a short set of **fail-safe
   invariants** so that a *partial* load over-escalates (safe) rather than under-gates. Sibling
   files are read on demand, not auto-injected, hence the explicit "read both first" instruction.
2. `skills/dev-loop/loop-engine.md` — the whole operating procedure: pipeline steps 0–12, ledger
   format, router, AC-verifier, initialization, resume, convergence/park/hold semantics, budget
   caps. **Project-agnostic — contains no project-specific values, ever.**
3. `${CLAUDE_PROJECT_DIR}/.claude/loop.config.md` (lives in the *consuming* repo, not here) — the
   binding seam. Every `CAPS` name in the engine (`BACKLOG_SOURCE`, `SCOPE_AGENT`,
   `DESIGN_AGENT`, `LINT_CMD`/`TYPE_CMD`/`TEST_CMD`/`HERMETIC_TEST_CMD`, `BRANCH_FMT`,
   `COMMIT_CONV`, `MERGE_METHOD`,
   `RELEASE_SCHEME`, …) resolves here.

   **This was described as "~40-line" until #141, and the figure did the wrong work.** It names the
   `/init-loop` skeleton and a typical fresh port; a long-lived consumer's config is legitimately
   larger, because a `—`-plus-reason value and a delegated routing rule both take room and both are
   read at runtime. The size was never the invariant. **The invariant is what a passage is: a
   passage stays iff the engine reads it at runtime**, so a binding value, a `—`-plus-reason (the
   reason is part of the value, never commentary), and project-specific logic the engine delegates
   all stay — while rationale, history and findings belong to the tracker, where #1 is the only
   copy. This repo's own config reached 350 lines by accreting a findings journal, 44% of the file,
   that nothing dereferenced; #141 moved it. **Trim toward the value, never through it.**

**The contract between layers is the parameter *vocabulary*, never layout.** The engine references
config values by `CAPS` name only; the config's section structure is free to change. Porting a new
project means editing only the config — never the engine. If a change to the engine would require
knowing something project-specific, that is the signal to introduce a new `CAPS` parameter instead.

A fourth file participates: `commands/init-loop.md` embeds a **skeleton of `loop.config.md`**. When
you add or rename a `CAPS` parameter in `loop-engine.md`, the `/init-loop` skeleton (§1 binding
table) and its inference map must be updated in the same change, or newly-onboarded repos will be
missing the binding the engine now reads.

**`CapsVocabularyTests` enforces the half of that a test can reach**: it fails if the engine (or
`SKILL.md`) names a `CAPS` parameter the skeleton does not offer. It cannot check that the
*inference map* gained a row, or that the Notes column makes sense — so a red run means you forgot
the binding table, and a green run does **not** mean the skeleton update is complete. The check is
one-directional by design: skeleton-only names are fine, engine-only names are the bug.

## Engine semantics worth knowing before editing

These are the non-obvious invariants the prose encodes; changes that violate them are regressions
even though nothing will fail loudly:

- **One issue per invocation, then STOP and journal.** State lives in the ledger on disk, not in
  context, so a fresh invocation resumes correctly after `/clear` or compaction.
- **Live git/PR state is the source of truth on resume**; the ledger row status is only a coarse
  stage anchor. The ledger is gitignored in consuming repos, so it can be stale.
- **Route and Status are separate columns.** `blocked`/`parked`/`hold` are Status overlays that
  retain their semantic Route (`code`/`research`/`docs`/`stub-defer`).
- **Gate parameters that name a *procedure* must never be bound to a user-triggered skill.** A skill
  marked `disable-model-invocation` cannot be invoked by the orchestrator, so binding one makes the
  gate **unsatisfiable as bound** — it does not error, it simply never runs on its own terms. Since
  F14 (#21) that is no longer *silent*: the Gate-outcome invariant makes the orchestrator fall back
  to the engine's inline composition where one is defined, record a `- gate-fallback:` line, and
  surface the misbinding. **The rule has no live example, and saying so is the point.** `CODE_REVIEW` was cited as one here from 2026-07-27 until #74 unwound
  it, and the citation was false: `/code-review` **is** model-invocable at any ordinary effort level
  (its `ultra` argument is gated, and degrades silently rather than refusing). What #74 retracts is
  **F7's invocability claim only** — F7's *second half*, that finder angles should be chosen from the
  diff's risk surface rather than a fixed list, is untouched and **already ships** as engine prose
  (`loop-engine.md`, "Pick finder angles from the diff's risk surface", from #10); what remains open
  under [#38](https://github.com/frederick-douglas-pearce/claude-code-loop/issues/38) is only whether
  to formalize it as a `REVIEW_TIERS` matrix.
  The rule stands on its own — F14 (#21) generalizes it to the whole class, where an
  unbound or `TODO(init-loop)` binding never means "skip the gate" — but an invariant illustrated by
  a fictional instance is the exact shape this project keeps having to retract, so do not reach for a
  replacement example unless you have verified one exists. Any new gate binding still gets the same
  scrutiny: name something the orchestrator can actually execute.
- **`HERMETIC_TEST_CMD` is the one gate whose due-ness is knowable only from its own binding**, so
  the Gate-outcome invariant carries an explicit carve-out for it: an absent or `TODO`-valued row is
  **unknown, and unknown is due**, never "the trigger never made it due" — which is the fail-open
  reading the invariant's general wording would otherwise license. The carve-out is scoped to rows
  the gate's own trigger fired on, so a missing binding never makes a gate due that nothing else
  made due. Tidying that invariant without preserving both halves silently turns the gate off.
- **Three resting-state classes** — terminal (`RUN COMPLETE`), resting-non-terminal (`RUN PARKED`,
  awaiting an external event, released only by explicit human un-park), and held/pending (no
  sentinel). `progress.md` is append-only and the **most recent** sentinel wins.
- **Default-deny at the merge gate:** uncertainty about auto-merge eligibility means fall back to
  the human. `mode:` gates the merge gate *only*. **F2 is complete** — #28 shipped the always-on
  condition (a material architect rewrite stops under every mode), and **#29 shipped the
  `plan-gate:` header field**, so the plan gate's posture no longer comes from `mode:` at all:
  - `plan-gate: always` (Initialization's value under `calibration`) stops on **every** issue;
    `plan-gate: conditional` (its value where routes were already graduated) stops on step 5's
    judgment conditions. **Absent or unrecognized reads as `always`** — the over-gating direction.
  - **The two fields are independent after init, deliberately.** A `mode:` change never re-derives
    `plan-gate:` in either direction. Coupling them would mean a project could only escape a
    mandatory plan stop by loosening its *merge* gate, which is the trade the field exists to avoid.
    Do not "simplify" this back into `mode:`.
  - The always-on condition sits under **both** values, and `plan-gate: always` does **not** excuse
    skipping its frozen-vs-live diff or its `- Plan-gate:` line — stricter posture, same record.
  **The posture's restatement sites are not enumerated anywhere, and this bullet does not enumerate
  them either.** The list in the always-on plan-gate bullet below is scoped to a *different*
  invariant (the material-architect-rewrite stop) and does not cover posture sites — #29 changed at
  least five that the always-on bullet's site list below does not cover: step 0.2's header read,
  Initialization step 4, the `queue.md` skeleton fence, Ledger format's `- Human gate:` paragraph,
  and `SKILL.md`'s plan-gate bullet (that list names `SKILL.md`'s fail-safe list for the *other*
  invariant, not this one).
  Do not read that list as the posture's site list. **#35 was to reduce all of this to one canonical
  passage. It was attempted and DEFERRED at its plan gate on 2026-08-18, and the reason changes what
  this instruction means: the restatements have already DRIFTED — they no longer agree with each
  other.** The divergences are catalogued on #1 (F57, F58); do not re-derive or re-count them here.
  **So grep before editing is still necessary and is no longer sufficient: read each site, because
  the sites do not currently say the same thing.** Editing them "together" on the assumption that
  they agree is how one of several variants gets propagated as though it were the invariant. #35
  cannot be executed as chartered until F57/F58 are resolved — its AC1 (state it once) and AC3 (no
  semantic change) are in direct conflict while the drift stands, since collapsing divergent sites
  necessarily picks a winner. It carries `tech-debt` and no milestone.
- **Notes on `parked`/`blocked` rows record the durable curation DECISION, never mutable live
  evidence** — the latter is contradicted by the next re-check and destabilizes resume.
- **The tree-isolation / staging rule is a new multi-site invariant with no test guarding it** (#25).
  "Any agent that must write to the tree gets its own copy", and the explicit-path staging rule that
  backstops it, are now restated across `loop-engine.md` (step 6, step 7, **step 10's own commit
  boundary, added by #31**, Tool surface, the
  `- Restore:` line, the AC-verifier untracked scan, Part 2's envelope, Resume), plus `SKILL.md`'s
  fail-safe list and the README trust model. Nothing checks their agreement, so an edit to one
  desyncs the rest silently — the same shape as the `mode:`-gating restatements above. The scope
  split this bullet used to carry — isolation live, mutation pass dormant — **closed with #60's
  second PR**: the pass now runs the harness, so every one of those sites describes live behavior
  and none of them may be re-fenced as dormant.
- **The always-on plan-gate stop is a second multi-site invariant, only partly guarded** (#28).
  "A material architect rewrite stops for the human, under every mode" is restated at every site in
  the list below. **The list is the claim — there is deliberately no headline number.** Two drafts
  of this bullet carried one and both were wrong (it said "eight" while listing nine; the correction
  to "nine" was then re-derived by two independent reviewers as eleven and as twelve, depending on
  whether adjacent sub-paragraphs count once or separately). That is the same enumerable assertion
  the consistency-module section above declines to make for the engine's step-reference sites, where
  the counts that used to stand went stale where they sat and were replaced by the mechanism,
  and a number nobody can re-derive the same way twice is worse than no number. **Maintain the list;
  do not summarize it.**
  - `loop-engine.md` step 4 — the freeze-invoke-apply ordering, the pre-image, write-once,
    no-back-dating, and the record-it-in-`## Approach` rule
  - step 5 — the condition, the materiality test, the absent-pre-image rule,
    and the architect-pass-by-any-actor definition
  - the Escalation rubric · the `mode:` shared paragraph · the `calibration` bullet · the
    `escalation-only` bullet · step 11's "only gate `mode` changes" aside · the gate table row
  - the `plan-gate:` field paragraph (added by #29) — it restates that the condition fires under
    **both** values and that `always` does not excuse skipping the diff or its `- Plan-gate:` line;
    step 5's always-on block carries the same point at length
  - Ledger format — the `- Plan-gate:` spelling enumeration (the **canonical** one; step 5 points
    at it rather than restating, after a draft where the two lists disagreed) and the `progress.md`
    worked example
  - the `issue-<N>.plan.md` template · Resume's two write-once side effects
  - `SKILL.md`'s fail-safe list · the README trust model

  **`PlanGateFrozenBlockTests` guards one mechanically-checkable part** — that the frozen
  block's heading appears, **normalized**, in each of four *located regions* of the engine: step 4's
  span (which writes it), step 5's span (which diffs against it), the `issue-<N>.plan.md` template
  fence, and the Resume paragraph. That coupling is a *string*, not a meaning, so the check is
  neither fragile nor vacuous: if step 4 writes a heading step 5 no longer looks for, the mechanism
  is dead while every word of the prose still reads correctly. **It asserts that the heading *appears*, normalized, in each region — not byte-identity, and not
  equality** — whitespace is collapsed (one occurrence is line-wrapped, the same hazard that hides
  wrapped references from the naive grep above; no count here either, for the reason given there)
  and the em dash is folded; say no more than that about it. **Per-region, not a global count, and that is the whole value:** the first draft asserted
  `count(...) == 4` over the file and a fresh reviewer walked two mutations straight through it —
  paraphrase Resume's occurrence while adding a spare mention elsewhere, or delete the block from
  the plan template and mention it in the *progress.md* fence instead. Both leave the mechanism dead
  with the suite green. Never replace the region anchors with a total, and never drop a region to
  make it pass.
  **The prose agreement across the sites listed above stays unguarded**, and that half is deliberate: a
  check over it would be the fragile-or-vacuous shape #76 documents for the `~~~markdown` span.
  Three failure modes to watch, each a silent reversal: (1) any site restored to "escalate **only**
  when the agents disagree/punt" re-inverts the logic the change exists to fix, and the Escalation
  rubric is where that wording actually lived; (2) the step-4 freeze losing its **write-once** guard
  makes the step-5 diff come back empty on a resumed row, so the gate passes silently — the
  mechanism failing in the one direction that looks like success; (3) **the subtlest, and the one
  the acceptance gate caught in this very change** — dropping step 4's instruction to write the
  architect's outcome into `## Approach` *before step 5*. Carry the rulings to implement time
  instead and the diff is empty by **literal compliance**, no bad faith required. The materiality
  list is **sufficient, not exhaustive**: extend it, never prune it. Its "if unsure, material"
  catch-all is what makes it the opposite polarity to `ALLOWED_NON_BINDINGS`/`_STOPWORDS` —
  additions can only strengthen it, so it is not the stale-allow-list failure those two flag.

## The append-only guard hook

`hooks/guard_append_only.py` (wired by `hooks/hooks.json` as a `PreToolUse` matcher on `Write`)
blocks full-file `Write`s that would drop entries from a registered append-only log. It is
**config-driven and inert until the consuming project opts in** via
`${CLAUDE_PROJECT_DIR}/.claude/loop.append-guard.json` (see `hooks/loop.append-guard.example.json`).

The **fail posture is a deliberate asymmetry** — preserve it in any change:

| Situation | Behavior |
|---|---|
| Unparseable hook event on stdin | fail **closed** (exit 2) |
| Any unexpected internal exception | fail **closed** (emit `deny`) |
| Read error on an existing protected file | fail **closed** |
| Sidecar absent | fail **open, silent** (an installed plugin must no-op until opted in) |
| Sidecar malformed / bad regex / wrong capture-group count | fail **open, LOUD** on stderr |

Also fixed by design: `id_pattern` must have **exactly one capture group** (0 groups captures whole
heading lines; ≥2 makes `re.findall` return tuples, a latent crash that would fail the guard open).
The guard protects *entry existence*, not body content, and covers `Write` only — `Edit` and `Bash`
redirection are out of scope. Keep it **stdlib-only** (it runs via bare `python3`, no venv). These
bounds and the trust level of `id_pattern` (repo-local committed config, not attacker input) are
also stated in `README.md` → "What the loop can do to your repo" — change both together.

**Tightening `load_registry`'s validation can invalidate the shipped example.**
`hooks/loop.append-guard.example.json` is the template every consuming project copies, and the
loader fails *open* — so a rule that rejects the example produces no error here, just consuming
projects whose guard silently protects nothing. `ExampleSidecarTests` loads the real file through
the real loader and asserts **zero stderr warnings**, which is the assertion that catches this;
"one entry loaded" alone would not.

## Repo conventions

- `.claude-plugin/` holds **only** manifests (`plugin.json`, `marketplace.json`). Skills, hooks,
  commands, and tools live at the repo root in their own directories.
- `tools/` holds **executables meant to be run by path rather than wired to a tool event** —
  currently just `mutate_verify.py`. The distinction from `hooks/` is what invokes them: a hook is
  registered in `hooks/hooks.json` and fired by the harness; a tool is run by whoever needs it.
  `loop-engine.md` (AC-verifier → Part 2) invokes it by path as
  `${CLAUDE_PLUGIN_ROOT}/tools/mutate_verify.py`, which is the whole reason the directory ships in
  the plugin payload. Both directories are reached as `${CLAUDE_PLUGIN_ROOT}/<dir>/<file>` and both are
  **stdlib-only**, for the same reason — they execute under bare `python3` in a consumer's
  environment.
- `${CLAUDE_PLUGIN_ROOT}` (this installed plugin) and `${CLAUDE_PROJECT_DIR}` (the consuming repo)
  are not interchangeable — the engine and hook both depend on the distinction.
- The loop ledger (`queue.md`, `progress.md`, `issue-<N>.plan.md`) lives under the *consuming*
  project's `LEDGER_ROOT` and is gitignored there. **As of 2026-07-28 this repo is also a consumer**
  (see "Dogfooding this repo" below), so a ledger does live here, under `.claude/loop/` and
  gitignored. It is still never committed. `.claude/loop.config.md` — the binding seam — *is*
  committed, like any consumer's.
- Commits follow Conventional Commits (`feat:`, `fix:`, `chore:`).

## Dogfooding this repo

**This repo runs the loop it develops** (onboarded 2026-07-28, milestone `v0.2.0`). Two facts about
that arrangement are easy to forget mid-run and change what the evidence means:

**The loop executes the *installed* plugin, not the working tree.** The engine driving a run comes
from `~/.claude/plugins/cache/claude-code-loop/dev-loop/<version>/`; edits to `skills/` and
`commands/` here do not take effect until the next release's re-install. This is a **safety
property** — a run cannot mutate the engine driving it — but it also means the loop keeps exhibiting
the defects we are fixing until that re-install lands.

**All three consumers moved 0.0.1 → 0.2.0 on 2026-08-21**, so the two instances below are now
history. They are kept because the *shape* recurs at every release, and because reading a journal
written before that date requires knowing which engine produced it: **#19/F15** (in the installed 0.0.1
the AC-verifier is **step 7** and diffs `main...HEAD` *before* the step-8 commit, so an uncommitted
branch certifies an empty diff — **fixed in-tree by #48; the fix reached every consumer at the
2026-08-21 re-install**; note the step numbers in that sentence are 0.0.1's, and **#31 has since rotated the
in-tree pipeline** so that acceptance is step 10 and runs *after* the step-7 commit — when reading a
run's journal, check which numbering the engine driving it used) and
**#21/F14** (an unbound binding skips its gate silently instead of erroring — **fixed in-tree by
the gate-outcome invariant; the fix reached every consumer at the 2026-08-21 re-install**).

**The window between an in-tree fix and a consumer re-install is when new consumers get onboarded
with the old bug.** The test is exact — a defect fixed in-tree **before** an onboarding yet still
live in the installed plugin at that moment — and **two illustrations written here have already
failed it, so check both dates before naming an instance.** F15/#19 and F14/#21 do **not** qualify:
both were filed on the 2026-07-28 onboarding day and fixed in-tree 2026-08-01 and 2026-08-05, *after*
it. This repo inherited them because they were unfixed everywhere, which illustrates the paragraph
above, not this one.

**The instance that does qualify is #10 itself, and it stayed live for three weeks.** Its commits
landed in-tree 2026-07-27 (`1d3ddbc`, `90de201`); this repo onboarded the next day (`c6dea09`,
2026-07-28). #10's engine changes were **absent from the installed 0.0.1** — so every iteration run
here before 2026-08-21 was driven by an engine whose hard-limit list stops before *"never edit
`loop.config.md`"*. The orchestrator honored that rule from the in-tree copy, not from the engine
actually executing. Closed by the 2026-08-21 re-install, like the rest. **The window is the durable
lesson, not the instance** — it reopens at every release, and this one lasted from #10's merge to a
re-install three weeks later.

**What F7 illustrated here is withdrawn.** The history is accurate — the 0.0.1 skeleton did bind
`CODE_REVIEW` to `/code-review`, and #10 did unbind it — but the reading was not: `/code-review`
**is** model-invocable, so that gate would never have been inert. **Only #10's *rebinding* rested on
the false premise; the rest of #10 stands** — finders receive the issue's acceptance criteria
("Give every finder the issue's acceptance criteria alongside the diff"), angles come from the diff's
risk surface, and the orchestrator is forbidden to edit its own `loop.config.md`, which is still
load-bearing. `.claude/loop.config.md` still deviates from the 0.0.1 skeleton, and that deviation is
a **design choice** — the finder fan-out, kept on its own merits — rather than a workaround for a
constraint that was never there. **The config has since been corrected** (2026-08-16): it now
carries the withdrawal explicitly — *"F7's invocability claim — WITHDRAWN 2026-08-16 (#74). Not a
defect."* — and its `CODE_REVIEW` row closes with the same note. **#74/AC4 appears discharged.** This
paragraph tracked that edit as pending for five days after it landed, which is the ordinary way a
cross-file claim goes stale: the correction was human-owned (the engine forbids the orchestrator from
editing `loop.config.md`), so nothing here moved with it. Verify against the file, not this
sentence.

**Why this consumer is worth the overhead:** its deliverable is *markdown an agent executes*, which
neither AgentFluent nor the vote repo produces. That breaks the router's assumption that markdown
implies the `docs` route — so `.claude/loop.config.md` §3 carries a binding override sending
`loop-engine.md`, `SKILL.md`, and `init-loop.md` to the `code` route. Findings unique to this shape
are logged on #1, which is the only copy.

## Branching & PR flow

**Default: work happens on a branch and lands via PR.** (Adopted 2026-07-26; commits before that
date went directly to `main`, so git history predates this rule.) **Enforcement is live** (#3, and
the repo went public 2026-07-28): `main` is protected and requires the aggregate **`test-suite`**
check, strict — branches must be up to date with `main` before merging. Admin enforcement is
deliberately **off**, which is the only reason the documentation exception below still works as a
direct push; it is not an invitation to route anything else around the gate.

**The one exception: simple documentation updates may be pushed straight to `main`.** Scope it
narrowly — the boundary is *what the file does*, not its extension:

| Direct to `main` | Must go through a PR |
|---|---|
| `README.md`, `CLAUDE.md`, `LICENSE` | anything in `skills/`, `commands/`, `hooks/`, `.claude-plugin/`, `tests/`, `.github/`, `.claude/` |
| typo / link / formatting fixes anywhere | any change to runtime behavior |

`.claude/loop.config.md` is on the PR side for the same reason the engine is: it binds the gates the
loop runs in this repo, so editing it is a behavior change. Note the engine separately forbids the
orchestrator from editing its own config mid-run — config changes are human work, landed outside a
loop iteration.

`skills/dev-loop/loop-engine.md`, `skills/dev-loop/SKILL.md`, and `commands/init-loop.md` are
markdown, but they are **the product** — an agent executes them at runtime. Editing them is a
behavior change and takes the PR path, however prose-like the diff looks. When unsure which side a
change falls on, open the PR.

This exception is for ad-hoc human/interactive edits. It does **not** apply to the `dev-loop` skill
working a routed issue: the engine's `docs` route still goes through commit → PR → light review
(step 7/8), and the loop must never bypass its own gates.

## Issue tracking

**All future issue work for the plugin is tracked in *this* repo** (`frederick-douglas-pearce/claude-code-loop`),
not in AgentFluent. The early extraction stories (S2–S4, epic
[#611](https://github.com/frederick-douglas-pearce/agentfluent/issues/611)) were filed in AgentFluent
before this repo existed; those links in `README.md` are history, not the live backlog.

**`public-readiness` — complete, closed out 2026-07-28.** The repo is public, CI runs on PRs with
`test-suite` required on `main` (#3), the mechanical consistency checks ship (#4), the README status
block (#2) and trust-model section (#5) landed, and the clean-machine install smoke test (#6)
certified the public install path end-to-end. Kept here as history; nothing in it is live work.

**`v0.2.0`** — the live milestone, and **not** the `v0.0.2` this file used to name. The batch grew
past a patch bump: it renumbers the pipeline, adds an `in-acceptance` status, rewrites Resume, and
reverses a multi-site invariant, so it is a minor bump.

[#1](https://github.com/frederick-douglas-pearce/claude-code-loop/issues/1) is now the **findings
index, not a work item** — "no PR should ever be opened for #1." Findings surfaced by real
runs (the first external adoption
[us-presidential-vote-analysis](https://github.com/frederick-douglas-pearce/us-presidential-vote-analysis),
the AgentFluent dogfood, #6's smoke test, and — since 2026-07-28 — this repo's own dogfood) are
recorded there with where they surfaced, the gap, a
*generic* fix (removing the AgentFluent-ism rather than special-casing), and a severity; the detail
lives in its comments, which are the only copy. They are scoped into **seven epics and ~21 stories**
under the milestone.

**The index outgrew its own title, so do not read either as a range.** The issue is still *titled*
"F1–F21"; its comments now carry findings **well past that range** — the highest F-number lives on
#1 and nowhere else, and this paragraph deliberately no longer names it (the figure stated here was
stale by seventeen when it was finally checked, which is the trap arriving on schedule). The
overwhelming majority are filed by this repo's dogfood runs rather than by the three original
sources. The title is human-owned and stale —
treat the comments as authoritative and don't infer the count from either the title or this
paragraph. (This is the same enumerable-assertion trap documented twice above; the fix is to state
where the number lives, not to restate the number.)

**#1 closes when the last child does — and that is now known to be after the v0.2.0 release.** #30
was deferred to `v0.3.0` at its plan gate on 2026-08-13, and #30 *is* epic **#15**'s third acceptance
criterion verbatim, so **#15 and #1 both stay open past the bump.** Accepted deliberately: E4's
load-bearing half (F2 — the plan gate, #28 + #29) shipped, and what deferred is the recommendation
half. The epic rows are `deferred` in the ledger, so nothing blocks #36.

**The batching convention was superseded 2026-07-28: batch the *release*, not the PRs.** One version
bump and one consumer re-install, but multiple coherent PRs. The old "never cut per-finding PRs" rule
existed to avoid re-installing per finding — a release cost, not a PR cost.

**`v0.3.0` — the deferral milestone, and it is no longer the two-issue footnote this file described
until 2026-08-13.** It opened as exactly that: `TEST_EFFICACY_AGENT` (#37) and `REVIEW_TIERS` (#38),
"both wait on corpus, not on effort." It has since grown by an order of magnitude — **check the
milestone for the count.** No number is stated here on purpose: the two previous drafts of this
sentence each named one and each went stale within a fortnight, which is the enumerable-assertion
trap this file documents three times above.

**The organizing criterion still holds and is the useful part: work lands here when it waits on
*corpus*, not on effort.** That is what makes it a real milestone rather than a backlog of things we
didn't get to, and it is the test to apply when deciding whether something belongs here. #30 (the
hand-mirrors-a-subsystem architect trigger, F9) is the worked example, deferred 2026-08-13 at its
plan gate: the plan's own corpus pass returned **n=1 and wholly retrospective**, against a falsifier
that only a *prospective* instance can discharge.

**The reason #30 deferred is worth carrying, because it generalizes past #30.** Cheapness did not
save it. Its AC3 would have written the new wording into the `/init-loop` **skeleton**, which copies
into consumer `loop.config.md` files that **no later release touches** — so unvalidated wording there
is *stranded*, not corrected by the next bump. That asymmetry is a general rule: **the evidence bar
for anything landing in the skeleton is higher than for the same wording landing in the engine**,
because the engine's copy is reachable and the skeleton's copy is not. `commands/init-loop.md`'s
maintainer note states the step-number case of it where it bites, above the skeleton it governs.

**A deferral needs a capture mechanism or it is just a delay.** "If it matters it will recur" is only
true if something records recurrences. Nothing did for F9 — the second instance surfaced solely
because #30's plan grepped `progress.md` for it, and F9's own thesis is that nobody writes this
trigger down unprompted, so while it does not exist nobody is looking. The fix was a **recurrence log
on #1** that also separates the *mechanisms* two findings can share (for F9: behavioral-mirror vs.
list-drift), which is what stops a count re-inflating by absorbing a related-but-different failure
mode — exactly how #30's evidence first got overstated as n=2. Do the same for any future corpus
deferral.

### The scope brake, and why the milestone needed one (2026-08-15)

**v0.2.0 was frozen on 2026-08-15 after a scope review.** The measured problem: in the 15-day
execution window 7/31–8/15, **19 issues closed and 31 new ones were filed** — 12 into v0.2.0, 15 into
v0.3.0, 4 left unmilestoned, with the rate showing no decay (four filed in the final two days). The
milestone could not converge because it was also the intake queue.

**The generator is the loop's own gates, working correctly.** The adversarial review and mutation
passes surface real couplings; that is what they are for. The defect was never the finding rate — it
was that **every finding got a milestone automatically**, with no human between "finding generated"
and "scope committed." Three rules now sit in that gap:

1. **Findings default to the index (#1), not to a milestone.** A finding surfaced by a run lands as
   an F-comment on #1 and nowhere else. Moving it into a release milestone is a deliberate human
   triage decision. This is the load-bearing rule — the other two are corollaries.
2. **A frozen release milestone accepts nothing new** except a blocker for one of its remaining ship
   items. Freezing is what makes any ship estimate hold.
3. **A guard on a guard is categorically never in a shipping release.** A finding whose fix is a test
   guarding *test infrastructure* or *doc accuracy* — #62 and #76 are the worked examples — has zero
   consumer impact and goes to `tech-debt`. This is the rule that caps `epic:release-safety`, which
   produced five of the seven issues cut from v0.2.0.

**The `tech-debt` label exists so v0.3.0 keeps meaning something.** Work that waits on *effort*
rather than *corpus* does not belong in the deferral milestone — putting it there would dissolve the
one criterion that makes v0.3.0 a category instead of a junk drawer. #35, #62 and #76 carry the label
and no milestone. Corpus- or evidence-gated work (#49, #61, #71) still goes to v0.3.0 proper. When
deferring, pick the bucket by *what the work waits on*, and never widen v0.3.0's criterion to avoid
the choice.

**The v0.2.0 cut line, for the record:** ship #74 → #40 → #34 → #67 → #36, with #60 closing out as
already-merged (PRs #79/#80) and #57's corrections absorbed into #36/AC3. **As of 2026-08-18 the
first four have all merged and only #36 remains.** *This line reads as originally written and is
again accurate, but it was not accurate throughout — #35 was pulled back in at the 2026-08-16 roster
reconciliation ("eject four, keep #35", placed last before #36, with a second decision releasing its
`blocked` row) and deferred back out at its plan gate on 2026-08-18. Recorded because a line that is
accidentally correct hides a round trip that the ledger and #35's own comments carry in full.*
Two ordering constraints are load-bearing and not arbitrary: **#74 must precede #36**, because #36/AC5 as written propagates a
correction to a *phantom* defect (F7's invocability half is false) into consumer configs no later
release can reach; and
**#74 must precede #40**, or they collide on `commands/init-loop.md`, which #40 rewrites broadly.

### Standing convention: the README status block ships with the version bump

**Any PR that bumps `.claude-plugin/plugin.json` must update the `README.md` status block in the
same PR.** Not just the v0.2.0 release — every bump, permanently. The status block names the current
version, what actually works, where the live backlog is, and which repos have adopted it; all four
rot silently, and the recurring failure mode is that nobody notices until a reader does. Treat it as
part of "done" for a release, not a separate chore.

The README's **trust-model section** ("What the loop can do to your repo") has the same property for
a different trigger: it restates the engine's gating posture and hard limits, so a change to the
merge gate, the mode semantics, the **plan-gate posture**, or the guard hook's scope must update it
in the same PR. **F2 (#28 + #29) was the live example and has now landed** — the trust-model section
gained a paragraph stating that you approve every plan by default, that `plan-gate:` and `mode:` are
independent settings, and that an absent field reads as `always`. It is no longer a pending
re-read. #36 / AC3 carries this for the release, and F5 (#31), F8 (#25) and F16 (#26/#27)
change it too.
