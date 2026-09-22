# Test-suite notes

Read alongside the root `CLAUDE.md`. This file covers what the suite does and does not
guard, and the ceiling on what a test over prose can ever assert. Run it with
`python3 -m unittest discover -s tests` (stdlib only — see the root file's Commands section).

## What is and isn't covered

The modules, and the split between them matters (no count is stated: the figure
that used to sit here went stale the first time a module was added):

- **`tests/test_guard_append_only.py`** — behavior of the guard hook.
- **`tests/test_posts_frontmatter.py`** — the frontmatter contract for `posts/`, the blog
  series sources (`posts/README.md` states it in prose; this makes it a rule). Structural only:
  field presence, value shape, one string equalling another — never whether a post is any good,
  reads human, or is true. Those three are **attested by a frontmatter field** rather than
  checked, which is the same move `CLAUDE.md` prescribes when a claim's truth is beyond a guard's
  reach. Two things about it are load-bearing. The field set is an **exact-set** comparison, not a
  containment check, so a typo'd key (`claims_verifed`) fails instead of silently replacing the
  field it shadows. And `CheckerBatteryTests` exists because **every other assertion in the module
  passes vacuously while `posts/` is empty** — it runs the checker against synthetic posts each
  wrong in one way and asserts the complaint *names that thing*, so a rule that stops firing fails
  there rather than being covered for by a neighbour. Deleting that battery leaves a check that
  cannot fail, which is the defect two entries in this repo's own blog corpus are about.
- **`tests/test_mutate_verify.py`** — behavior of `plugins/dev-loop/tools/mutate_verify.py`, the
  mutation harness.
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
- **`tests/test_publish_to_pages.py`** — behavior of `tooling/publish-to-pages.py`, the Pages
  publisher (#179). **Two tiers, and the split is the point.** Tier 1 drives the namespace guard
  through its `pages_owner` injection seam, pinning the *refusal logic* — three refusals carrying
  three different remedies, each asserted by its own discriminator rather than by a shared
  substring. Tier 2 drives `git_pages_owner` against **real git histories**, because the seam
  bypasses it entirely and that function is where the security-critical parsing lives (`%an%x00%s`
  field order, `%an` not `%cn`, the `-- <path>` pathspec, the walk that stops on an unattributable
  sync). A seam-only suite would assert the outcome while leaving the mechanism untested — the
  exact hole this file is about — and the source repo *measured* that: `%cn` and a dropped pathspec
  each left its whole suite green while restoring a silent cross-publisher overwrite.

  **This module makes a real `git` binary a suite precondition, and it does not skip without
  one.** That is deliberate: skipping would let the security coverage evaporate silently on
  exactly the machine where nobody looks. So "bare `python3` is enough to run this
  suite" is no longer true — `python3` **and** `git`. Still
  stdlib-only; `subprocess` and `tempfile` are not dependencies.

  **What it does not cover, as of #179:** the production wiring (`run()` → the real
  `git_pages_owner`) is untested — every test injects the seam — and nothing ties the workflow's
  `pages-sync[bot]` identity and commit-subject template to the constants that parse them. Both
  are deferred with a capture gate — see **#199**, which carries the gate itself
  (before the first real post, or before the `pages-sync` environment exists).
- **`tests/test_repo_consistency.py`** — **mechanical** checks on the markdown/JSON deliverable:
  the shipped example sidecar still loads through the real `load_registry`; the composed
  `plugin@marketplace` identifier still matches every hand-written call site; engine `CAPS` ⊆
  the `/init-loop` skeleton (see the root `CLAUDE.md`'s three-layer split — this is that
  contract, enforced);
  `PlanGateFrozenBlockTests` — the frozen-approach heading #28's always-on plan-gate stop is looked
  up by appears, normalized, in each of four *located regions* of the engine (see
  `plugins/CLAUDE.md`'s always-on plan-gate bullet for why that string, and only that string, is
  checkable — and why per-region rather than a global count);
  and `PipelineStepOrderTests` — the pipeline's **step *ordering*** agrees across the **five**
  restatements of it, in **three** files: `loop-engine.md`'s `### N.` headings, `SKILL.md`'s numbered
  chain, `plugin.json`'s `description` (published with the plugin), `SKILL.md`'s **frontmatter
  `description`** (`plan→architect→implement→review→merge` — the string the model reads when
  deciding to invoke the skill, so a behavior surface, not prose), and the engine's in-prose
  `step N` cross-references. (`loop-engine.md` ×2, `SKILL.md` ×2, `plugin.json` — which is why five
  restatements live in three files.) The naive grep
  (`grep -oE '[Ss]teps?[ -][0-9]|[Ss]tages?[ -][0-9]' plugins/dev-loop/skills/dev-loop/loop-engine.md | wc -l`) does
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
