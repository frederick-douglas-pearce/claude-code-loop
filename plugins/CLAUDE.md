# Engine semantics worth knowing before editing

Read alongside the root `CLAUDE.md`, which carries the three-layer split this file assumes.

**This file lives at `plugins/`, not inside `plugins/dev-loop/`, and that is deliberate.**
`marketplace.json`'s `source` names `./plugins/dev-loop`, and Claude Code copies that directory
and nothing outside it into every consumer's plugin cache. A `CLAUDE.md` one level up is loaded
when you open anything under `plugins/` and ships to nobody;
`PayloadContentsTests.test_no_maintainer_path_appears_in_the_payload` fails if one ever appears
inside the payload.

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
  `tests/CLAUDE.md` declines to make for the engine's step-reference sites, where
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
  wrapped references from the naive grep `tests/CLAUDE.md` quotes; no count here either, for the
  reason given there)
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
