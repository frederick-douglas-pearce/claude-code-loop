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

---

## D012 — 2026-09-11 — The release is `0.3.0`; milestone names shift to follow it

**Context.** #161 chartered the bump as `v0.2.2` but flagged the number itself as an open maintainer
decision: 115 commits past `be29a79`, **+7,236 lines**, `loop-engine.md` alone **+1,317** — and #114
adds a **whole new gate** (the `DESIGN_AGENT` scope ruling, with its own row in the Gate table),
confirmed absent from the installed 0.2.1 payload. The repo's own precedent is explicit: v0.2.0 "grew
past a patch bump … which is why it was a minor bump" (`CLAUDE.md`), and that release was smaller
than this one.

**Decision.** **`0.3.0`.** A new always-on gate is a feature, and a patch number would have
misdescribed the release to every consumer deciding whether to take it. Four milestone renames
follow, so the tracker and the version agree:

| was | now | what it is |
|---|---|---|
| `v0.3.0` | **`deferred-corpus`** | the corpus-gated deferral category — never a release |
| `v0.2.2` | **`v0.3.0`** | this release |
| `v0.2.3` | **`v0.3.1`** | the engine-sharding epic (#128), still a patch by D006's reasoning |
| `v0.2.4` | **`v0.3.2`** | the next patch train |

**What this supersedes, precisely.** D006 ratified `v0.2.3` for the sharding epic and declined
`v0.3.0`, on the grounds that using the corpus category for effort-gated work would either dissolve
its defining criterion or force relocating 24 issues. **That ratification stands** — the epic still
gets a dedicated single-epic milestone, and its criterion is untouched; only its *name* changes,
which is the one thing D006 was not deciding. What is superseded is D006's cost argument in its
narrow form: it weighed the rename against a *milestone* choice, where the cheaper option was
available and free. Here the trigger is the **version number**, where the alternative is not a
cheaper name but an inaccurate one. **The category never should have been a version string** —
`CLAUDE.md` had already been calling it "a category rather than a junk drawer" while numbering it
like a release, and this collision is what that mismatch was always going to produce.

**D008 re-labelled, not changed.** "The sharding baseline freezes against v0.2.2" means the release
installed immediately before the sharding cut; that release is now **0.3.0**. Same object, same
double-count hazard, new number.

**Cost paid, stated plainly.** 48 issues across four milestones carry a renamed milestone. Every
issue body, PR description, journal entry and ledger row written before 2026-09-11 uses the old
names, and none of them is being rewritten — `CLAUDE.md`'s `deferred-corpus` paragraph carries the
mapping, and that is the only copy.

**What was NOT done, deliberately.** The ledger run directory `.claude/loop/v0.2.1/` keeps its name.
It is a label, resume scans the ledger root, and renaming a live run directory is the larger risk —
the same reasoning its own header already records for the v0.2.1→v0.2.2 move.

---

## D013 — 2026-09-20 — The prose licence binds at the `posts/` directory, and the two `LICENSE` files diverge deliberately

**Context.** #189 is the fourth attempt at a CC-BY-4.0 licence for `posts/`; three prior drafts were
rejected on PR #188, each fixing the previous round's defects and producing new ones of the same
class — an inversion applied to some sentences and not others. The issue named two decisions that
had to be settled *before* drafting, because both prior attempts drafted first. They are settled
here.

### 1. The scope clause goes in the root `LICENSE`, and the GitHub label changes

**Measured first, not assumed.** GitHub's licence detection reads the root `LICENSE` and matches it
against templates under a confidence threshold, so any operative scoping text drops it below:

| repo | root `LICENSE` | `gh api repos/.../license` |
|---|---|---|
| `claude-code-loop` (before this change) | pristine MIT | `mit` / MIT License |
| `claude-code-sessions` | MIT + trailing `**Scope:**` block | `other` / NOASSERTION |
| `us-presidential-vote-analysis` | MIT + trailing `**Scope:**` block | `other` / NOASSERTION |

**Decision: accept it.** The root `LICENSE` carries the scope clause and this repository's sidebar
label becomes **`Other`/`NOASSERTION`**, knowingly.

**Where the clause sits and how it is worded, recorded because both are load-bearing.** It is a
**preamble preceding the MIT text**, headed `SCOPE OF THIS LICENCE`, and it is worded as a
**definition of the term `"the Software"`** that the MIT grant below then uses — not as a separate
reservation sitting alongside the grant. That is what makes it narrow the grant rather than comment
on it: MIT permits dealing "in the Software", so redefining that term is the only edit that reaches
the permission. **The table above does not evidence this placement** — both sibling repos carry
*trailing* `**Scope:**` blocks — so the leading preamble was measured separately, on the branch:
`gh api repos/.../license?ref=docs/prose-licence-for-posts` returns `other`/`NOASSERTION`, while the
same call against `main` still returns `mit`. A leading preamble costs the label exactly as a
trailing block does. **Measured, not inferred** — and see §4 both on why it was measurable at all
and on what the measurement is bound to.

**Why the alternative under-protects, which is the whole of the argument.** Leaving `LICENSE`
pristine does not merely state the boundary less prominently — it leaves the MIT grant *covering*
`posts/`. MIT grants unrestricted rights over "the Software and associated documentation files", so
a recipient of a post could take the MIT grant and owe **no attribution at all**; a CC-BY file
elsewhere adds a second, *more permissive* escape rather than removing the first. Attribution is the
instrument's only purpose, so the alternative makes it optional. Binding requires the MIT grant
itself to exclude `posts/`, and that is the edit that costs the label.

**The cost, stated plainly.** `Other`/`NOASSERTION` is sidebar metadata. The files are unchanged in
force either way, `LICENSE` still reads as standard MIT to a human, and the change is **reversible**
— delete the clause and the label returns. The considered counter-argument is that this repo is a
plugin marketplace front door and an adopter may read `Other` as licensing risk; it was weighed and
the binding grant was judged worth more. Both sibling repos already sit at `Other` **without having
chosen it**, which is worth telling them regardless.

### 2. All of `posts/` is covered, with no exception — on the PATH axis, token `posts/`

**Decision: the CC-BY grant covers everything in the `posts/` directory, whatever its format,
including `posts/README.md`. There is no exception.**

**The boundary token is fixed here so downstream wording cannot drift from it.** The MIT carve-out
and the CC-BY grant both cut on the **path axis at the literal token `posts/`** — "everything in the
top-level `posts/` directory and everything under it" against "everything except" the same. **No
sentence in either file describes the boundary by content type** — not "prose", not "essays", not
"the blog series". That is what makes the partition provable by reading the two files against each
other instead of asserted in either one, and it is exactly how attempt 3 died: `LICENSE` carved out *"the blog-series **prose**
under `posts/`"* while `LICENSE-prose.md` granted *"everything committed under `posts/`, whatever its
format"*. #180 will put og-cards and images under `posts/`, so a content-type cut leaks immediately.

**The rule: each instrument states its extent once and refers to it by name thereafter.** Stated as
a rule for whoever edits these files next, not as a claim about what they currently say — a rule
survives being violated, where a claim about current state is simply false the moment someone adds a
sentence. The term in `LICENSE-prose.md` is **the Licensed Material**, defined in its opening grant
and taken from CC BY 4.0's own §1(f); in root `LICENSE` it is `"the Software"`, defined in the scope
preamble and used by the MIT permission clause below it. **A sentence that does not restate the
extent cannot misstate it.**

**Why a rule and not a fixed literal, which is what this entry said first.** The first attempt at
this paragraph mandated one string — *"the top-level `posts/` directory and everything under it"* —
everywhere, and asserted every sentence already used it. Security review falsified that in the same
commit: five sentences in `LICENSE-prose.md` dropped the `top-level` anchor, and the primary grant
interposed *"of this repository"*, so the `grep` the rule was justified by could not have matched the
one sentence that mattered most. **That is the completeness proof bolted onto a rule that root
`CLAUDE.md` warns about, arriving inside the entry written to prevent it.** Six documented misses of
this class on #190 — three prior attempts, two review rounds, and that one — every one of them a
sentence *restating* the boundary near a sentence that stated it correctly. The defined term removes
the restatements, so there is nothing left to drift. The README copies sit outside both instruments
and cannot use a term defined in one, so they spell the boundary out; that is the one place the
literal still applies.

**Why no exception, and note that decision 1 forces it.** Both prior attempts excluded
`posts/README.md` and neither could say it operatively; round 2 then found that *"everything under
`posts/` except `posts/README.md`"* is a sweeping grant minus an exclusion, which rots when a second
non-series file lands there. **The exception is the defect.** And under decision 1 the root MIT is
itself scoped to *"everything except `posts/`"* — so an exception on the CC-BY side would leave
`posts/README.md` assigned to **neither licence**, an outright partition gap rather than merely rot.

**The honest cost:** this is *over*-inclusion, and the attempt-1 architect ruling held that
over-inclusion is the dangerous direction for a grant because CC-BY-ing MIT material is hard to claw
back. It does not bite here for reasons specific to this file rather than general:
`posts/README.md` is licensor-authored, is not code, never ships, and CC-BY over it costs a copier
one attribution line. Scoping by filename convention (`posts/YYYY-MM-DD-*.md`) was considered and
rejected — also exception-free, but keyed to `.md`, so it under-covers the assets #180 introduces.

### 3. `plugin.json` stays `MIT`, and that is a conclusion rather than an omission

`plugins/dev-loop/.claude-plugin/plugin.json`'s `"license": "MIT"` is **unchanged, deliberately**:
the payload is `plugins/dev-loop/`, which is no part of the top-level `posts/` tree, so it is
genuinely all-MIT. `.claude-plugin/marketplace.json` carries no `license` field. Recorded because
the point of this exercise is that no licence assertion goes unexamined.

### 4. Forward notes

- **When the slim consumer README lands** and `plugins/dev-loop/README.md` stops mirroring the front
  door, the payload copy must **not** inherit the root's `posts/` scope prose. The payload has no
  `posts/` to scope.
- **AC5's second half is discharged, and the deferral that stood here was built on a false
  premise.** This bullet previously read *"unobservable before merge, since detection reads the
  default branch"* and deferred the check past the merge gate. **That is wrong**: the endpoint takes
  a `?ref=`, so `gh api repos/frederick-douglas-pearce/claude-code-loop/license?ref=<branch>` reads
  any ref. Measured on `docs/prose-licence-for-posts` at `3f747ac`: `other` / `NOASSERTION`, `path`
  `LICENSE`, `sha` `009d5505b1d3053a905ffef28248c9f2374e1778`, which `git rev-parse HEAD:LICENSE`
  matches byte for byte; `main` returns `mit`. So the check was run rather than assumed, before merge
  rather than after, and `README.md`'s licence-detection paragraph and its payload copy are **true**.
  **The measurement is bound to that blob, not to the branch.** An earlier draft of this bullet cited
  blob `e208f69` — and the very commit that wrote the citation also edited `LICENSE`, so the sentence
  was false the moment it was written, and the acceptance gate caught it. A recorded measurement
  naming a hash the same change can move is a falsifier discharged against the wrong object. If
  `LICENSE` is edited again before merge, re-run the call; the result is expected to hold, because
  what costs the label is the presence of a scope preamble rather than its wording.
  **The lesson generalises past this entry**: the deferral was not created by a limit of the tool, it
  was created by not reading the tool's parameters. A capture mechanism is the right response to
  something genuinely unobservable now; reaching for one first is how an observable fact becomes a
  post-merge TODO. Re-running after merge is still worth doing once, since the default branch is what
  a reader's sidebar reflects — but nothing in this change now waits on it.
- **E2's future guard must never be written as byte-identity.** Nothing pins the two `LICENSE` files
  today, so this divergence breaks nothing now. If such a guard is ever added it has to encode a
  **relationship** — payload `LICENSE` == root `LICENSE` minus the scope preamble — because equality
  is now false by design.

---

## D014 — 2026-09-22 — OG cards live at `posts/images/<slug>/`, and D013's forward premise held

**Appending, not amending.** This log is append-only, so D013's two forward references to #180
stay exactly as written — they were accurate when written and are now simply settled. This entry
is what a reader arriving at them should find next.

### The decision

**An OG card lives at `posts/images/<slug>/og-card.png`, committed**, where `<slug>` is the post's
filename minus the date prefix and the `.md`. Settled at #180's plan gate, approved by the human
2026-09-22. Written into `posts/README.md` → *Where an OG card lives*, which is the copy an author
reads; this entry records **why**, which that section states only in summary.

### D013's premise is confirmed, not merely unfalsified

D013 §2 cuts the CC-BY grant on the **path axis** at the literal token `posts/` and gave as one
reason: *"#180 will put og-cards and images under `posts/`, so a content-type cut leaks
immediately."* It also **rejected** a `posts/YYYY-MM-DD-*.md` scoping as *"keyed to `.md`, so it
under-covers the assets #180 introduces."*

**Both were forward-looking claims about a decision nobody had taken yet.** This change takes
that decision: the first non-`.md` file under `posts/` will be an OG card, which a `.md`-keyed
grant would not have covered. **No card lands in this change** — `posts/` still holds only
`posts/README.md`, and the guard ported here exits 0 until a dated post exists. D013's path-axis
cut needs no revision.

**This ran the other way round, and it is worth recording which direction the reasoning went.**
The fork was argued first on other grounds — boundary preservation and the silent failure mode of
a negated-ignore idiom — by two agents, both of which reached `posts/`. D013 was found afterwards,
by a `git grep -n '#180'` the architect demanded for an unrelated reason, and it turned a
preference into a constraint: the alternative would have put a **published card on the MIT side of
a grant whose post is CC-BY**, re-opening the partition gap D013 §2 spent three attempts closing.
**A recorded decision reasoning about unfinished work is a constraint on that work, and nothing
searches for it on your behalf.** Grep the decision log for the issue number before settling
anything a prior entry may have assumed.

### The cost, stated rather than buried

**This diverges from both sibling repos**, which keep cards at
`social/images/<date>-linkedin-<slug>/`. They reach them differently, and the difference matters
to the argument below: `us-presidential-vote-analysis` carves `social/images/` out of an otherwise
ignored `social/` (`/social/*` plus `!/social/images/`), while `claude-code-sessions` ignores only
`social/drafts/` and tracks the rest. This repo's `social/` stays wholly gitignored. The divergence was accepted twice: once on its merits,
and once again after the orchestrator corrected a mistaken belief that `posts/images/` matched the
siblings — it matches neither, and neither sibling has any non-`.md` file under `posts/`.

Two things follow for whoever edits this next. **`posts/` will stop being markdown-only** when the
first card lands, so a rule written as "every file in `posts/`" must say what it means about
assets — `posts/README.md`'s Prettier paragraph was corrected in this change for that reason,
ahead of the card rather than after it. And **do not "tidy" the
card path back to match the siblings**; it would falsify this entry and D013 together.

### Forward note

`tooling/check-og-cards.py` (#180) now runs the publisher's `build_plan` on PRs, so an
unresolvable card fails the PR rather than the `main` sync. It is **not** a required status check —
branch protection requires the aggregate `test-suite` job only, and no file in this repo can assert
a protection setting. While `posts/` holds no dated post the guard exits 0 either way; it becomes
load-bearing at the first dated post. Making it required is the same open question as #195 asks for
`prettier`.

## D015 — 2026-09-23 — The stdlib-only rule binds by reach, not by directory; the card renderer takes Pillow

**Appending, not amending.** D014's forward note stands as written. This entry settles the one
architectural decision epic #177 said this pipeline would force, taken at #181's plan gate and
approved by the human on 2026-09-23.

### The decision

**`tooling/render-og-card.py` is ported, with Pillow, Inkscape and `tomllib`.** The dependency is
maintainer-side: it does not ship in the payload, CI never runs the renderer, and the test suite is
forbidden to reach it. **`CLAUDE.md`'s stdlib-only rule is re-scoped to say so by predicate rather
than by directory:** a file is bound iff it **ships to a consumer** or **the suite imports or runs
it**, and if you cannot establish it reaches neither, it is bound.

### Why the rule needed re-scoping at all, which is the part worth keeping

The preamble already stated the predicate correctly — *"anything that reaches a consumer's
environment, or that `TEST_CMD` runs, is stdlib-only"*. The `tooling/` bullet restated it as
*"the stdlib-only rule binds `tooling/`"*, keyed to the **directory**. That was true of the two
files in there and false of the directory, and the drift had already been paid for once: a
forward-looking exception for this very issue was bolted onto the end of the bullet, which is the
shape an enumerated exception list starts as. **The fix is not a better list.** A second
dependency-taking file would rot any list on arrival; a predicate classifies it with no edit.

**A guard backs the common case.** `SuiteImportClosureTests` parses the `tests/` modules plus
every repo `.py` file they **name as a `/`-joined path-literal chain**, and fails on any import that does
not resolve to the standard library. An **unknown** dependency fails too, which is what makes it
default-deny rather than a blocklist. It follows path *literals*, not loads, so it is a backstop
for the predicate and never a substitute for it; `tests/CLAUDE.md` states what it reaches and what
it misses, which is that file's to state rather than this one's.

**That guard was itself the third attempt, and the first two are worth recording.** The plan
proposed *"assert no test imports the renderer"* — a forbidden-name check over an open domain,
whose cheap fix for a red run is to append the new name. The architect rejected it against
`tests/CLAUDE.md`'s own `ALLOWED_NON_BINDINGS` trap: it asserts an **outcome** (one name is absent)
rather than the **mechanism** (the closure is stdlib-only). The first implementation of the
inverted form then resolved path literals **by basename anywhere in the repo**, which pulled in
files named only in a *docstring* and went red on a clean tree. A guard that fails on a clean tree
is not a strict guard, it is a broken one. The shipped form follows `/`-joined path literals, which
is how this suite actually names a script.

**A third attempt failed in CI for a different reason, and it is the most instructive of the
three.** The inverted `RemedyTests` check probed every path the remedy cites by stripping at the
placeholder — so `posts/images/<slug>/` became `posts/images/`, which **does not exist until the
first card is committed**. It passed locally only because an earlier step in the same session had
left that directory behind, empty; git does not track empty directories, so CI had no such path and
went red on all five interpreters. **The guard was reading local dirt.** The fix distinguishes a
*concrete* citation, which must resolve, from a *template* the author fills, which must not be
asserted to exist — and pins the card-directory convention against `posts/README.md`, the document
that defines it, rather than against the filesystem. Worth recording because the failure mode is
not "the guard was wrong": it is that a guard can be **green for an environmental reason**, and
only a clean checkout says so.

**The guard then killed a regression of its own author's, during the review fixes, and that is the
cleanest evidence it works.** The walker shipped with a second branch that treated any whole string
literal ending in `.py` as a load. Code review called it *"one keystroke from red"* — and the very
next fix wrote `tooling/render-og-card.py` into a test assertion, so the renderer entered the
closure and the guard failed on a correct tree. (The prediction was right about the outcome and
loose about the mechanism: a docstring merely *containing* the path would not have fired, since the
branch tested the whole literal.) The branch
was **deleted** rather than special-cased: it detected no real load in this suite, which names
every script it loads as a `/`-joined chain, and its only live effect was the false red. **A
mention is not a load** — the same sentence the basename attempt was rejected on, arriving a second
time in a different shape. The guard caught a regression its own author introduced, which is the
property the whole class exists for.

### What was rejected, and why

1. **Don't port it.** Rejected on value: every post needs a card it cannot produce here. Two
   separate mechanisms sit behind that, and **this entry deliberately does not state how they
   relate** — `tests/test_posts_frontmatter.py:203-205` records that a claim about exactly that
   relation was drafted twice and was false both times, and a third draft of it stood in this
   entry until code review caught it. What each one does, separately: the required `test-suite`
   check enforces that `og_card_source` is *present* and well-formed; the non-required
   `og-card-guard` workflow fails closed when the card does not *resolve*. This option would also
   leave the documented remedy having to point at a script in *another repo* — the
   unresolvable-citation shape #180 deleted from the ported guard on purpose.
2. **Consolidate one renderer into a shared home.** Not wrong, and **not closed** — see below. It
   was rejected *for this issue* because it stands up a fourth repo or adopts Python tooling into a
   Jekyll site, and drags two out-of-scope repos into an epic whose own priority note says this work
   is not high priority. Option 1 forecloses none of it.

### Two premises this decision was nearly taken on, both false

- **`claude-code-sessions` does not render cards by hand.** #181 and #177 both said so — #177's
  comparison table is captioned *"checked, not assumed"* and that row was neither. It has a
  **272-line `render.py`** running the same `tomllib` + Inkscape + Pillow pipeline as the vote
  repo's 274-line copy. So the delta between the two repos is **location and specimen frame**, not
  script-vs-hand, and the "don't port" option's stated fallback never existed. Both bodies were
  corrected on 2026-09-23.
- **The README trust-model section does not state a dependency posture.** The plan claimed it did
  and that it had to move in this change. It does not: that section covers enforcement and the
  guard hook's scope, and the dependency claims live in **Requirements** (whose "Both" is the guard
  hook and the mutation harness) and in the run-the-suite line. Option 1 falsifies none of them, so
  **no README line is part of this change.**

### Three placement calls, each with a consequence

- **The chassis template is `tooling/og-card-template.svg` — MIT, not CC-BY.** It is machinery: it
  is never published (only the 1x PNG reaches the site) and it is shared across series. D013 §2
  records that **over-inclusion is the dangerous direction for a grant**, so unpublished
  scaffolding does not go on the CC-BY side. The brief **does** go under `posts/` with its card,
  because a brief is per-post authored content. The line is **content CC-BY, machinery MIT**, which
  is the boundary D013 already draws.
- **Only `og-card.png` is committed.** `og-card.svg` and `og-card@2x.png` are reproducible
  intermediates that nothing resolves; they are gitignored. They are written *beside the brief*,
  which under this layout is a committed directory, so without those rules a wide `git add` sweeps
  them in.
- **`uv` is the invocation, via a PEP-723 header rather than a repo manifest.** `uv run` had nothing
  to resolve Pillow from here — the vote repo's works off its `pyproject.toml` + `uv.lock`, and
  neither sibling uses PEP-723. Declaring the dependency inside the one file that has it keeps
  *"the payload carries no dependency manifest"* and *"nothing the suite imports gains a
  dependency"* trivially true. Whether to graduate to a full `pyproject.toml` + lockfile is a
  separate issue.

### A gotcha was inherited wrong, and the port fixes it

Both source repos document *"Inkscape is snap-confined to `$HOME`. Absolute resolved paths only; a
brief outside `$HOME` fails fast rather than silently no-opping."* **Measured 2026-09-23: it does
not.** Snap's `home` interface grants access to **non-hidden** paths only, so a brief in a
dot-directory sits under `$HOME`, passes the source's guard, and Inkscape then prints
`ink_file_open: … cannot be opened!`, **exits 0**, and writes nothing — `check=True` passes and the
failure surfaces several steps later as a missing-file error from Pillow. The port adds both a
named fast-path for the dot-directory case and, load-bearing, an **assertion that the export
actually produced a non-empty file**, which catches any silent no-op whatever its cause. The
enumerated check is the message; the artifact check is the guard.

### The cost, stated rather than buried

**CI does not guard the renderer's pixel pipeline, and cannot without breaking the suite.** The
byte-identical reproduction measured at plan time is a one-time observation, not a standing
guarantee. This is the honest form of attesting what cannot be checked, and it is the reason
"add testing for the renderer" is filed rather than assumed.

### Forward notes

Four follow-ups were identified at the plan gate and are the human's to file: this series'
**specimen frame** (split out of #181's AC3); **renderer consolidation** across the three copies,
which should carry a recurrence trigger — *the next substantive behavioural change to any copy, not
a specimen swap, consolidates instead of editing three* — and should record this port's
snap-guard fix as the first such divergence, since it is the first thing that ought to propagate;
**dependency-management artifacts** (`pyproject.toml`/lockfile/a repo-wide Python floor — this
repo declares none today, so `tomllib` puts a 3.11 floor on one file, declared in that file's
PEP-723 header and nowhere else); and **testing for the renderer**, per the cost above.
