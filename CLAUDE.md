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

**What the suite does and does not guard — including the ceiling on any test over prose — lives
in `tests/CLAUDE.md`**, loaded when you open anything under `tests/`. Do not restate it here.

## Writing product prose: default-deny, never enumeration

**The positive prescription the enumerable-assertion trap has been missing: a rule about which
states are *safe* must be written default-deny — unknown ⇒ unsafe — never as an enumeration of the
safe set.** The prose-guard ceiling in `tests/CLAUDE.md` governs *guards*; this governs *product
prose*, and it is what that trap looks like when the enumeration is user-facing rather than in a
test. Established by #34, where
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

1. `plugins/dev-loop/skills/dev-loop/SKILL.md` — the entry point Claude loads when the skill is
   invoked. It is deliberately thin: it names the two files to read, then restates a short set of
   **fail-safe invariants** so that a *partial* load over-escalates (safe) rather than under-gates.
   Sibling files are read on demand, not auto-injected, hence the explicit "read both first"
   instruction.
2. `plugins/dev-loop/skills/dev-loop/loop-engine.md` — the whole operating procedure: pipeline
   steps 0–12, ledger format, router, AC-verifier, initialization, resume, convergence/park/hold
   semantics, budget caps. **Project-agnostic — contains no project-specific values, ever.**
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

A fourth file participates: `plugins/dev-loop/commands/init-loop.md` embeds a **skeleton of
`loop.config.md`**. When you add or rename a `CAPS` parameter in `loop-engine.md`, the `/init-loop`
skeleton (§1 binding table) and its inference map must be updated in the same change, or
newly-onboarded repos will be missing the binding the engine now reads.

**`CapsVocabularyTests` enforces the half of that a test can reach**: it fails if the engine (or
`SKILL.md`) names a `CAPS` parameter the skeleton does not offer. It cannot check that the
*inference map* gained a row, or that the Notes column makes sense — so a red run means you forgot
the binding table, and a green run does **not** mean the skeleton update is complete. The check is
one-directional by design: skeleton-only names are fine, engine-only names are the bug.

## Editing the engine

**The engine's non-obvious invariants live in `plugins/CLAUDE.md`**, loaded when you open anything
under `plugins/`. It sits outside the payload deliberately; see its own preamble.

## The append-only guard hook

`plugins/dev-loop/hooks/guard_append_only.py` (wired by `plugins/dev-loop/hooks/hooks.json` as a
`PreToolUse` matcher on `Write`) blocks full-file `Write`s that would drop entries from a registered
append-only log. It is **config-driven and inert until the consuming project opts in** via
`${CLAUDE_PROJECT_DIR}/.claude/loop.append-guard.json` (see
`plugins/dev-loop/hooks/loop.append-guard.example.json`).

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
`plugins/dev-loop/hooks/loop.append-guard.example.json` is the template every consuming project
copies, and the loader fails *open* — so a rule that rejects the example produces no error here,
just consuming projects whose guard silently protects nothing. `ExampleSidecarTests` loads the real file through
the real loader and asserts **zero stderr warnings**, which is the assertion that catches this;
"one entry loaded" alone would not.

## Repo conventions

- **The runtime tree lives under `plugins/dev-loop/`, and that directory IS the payload**
  (#170). `.claude-plugin/marketplace.json` declares `"source": "./plugins/dev-loop"`, and Claude
  Code copies that directory — and nothing outside it — into every consumer's plugin cache. There
  is no payload-exclusion mechanism: no `files`/`exclude`/`ignore` manifest field and no
  `.pluginignore`. The only filter is **positional**, which is why the source directory must hold
  runtime only.

  **`.gitignore` is not a payload-selection mechanism, and the precise form matters.** It cannot
  keep a **tracked** file out of the payload — that is the defect this restructure fixes. It
  *does* keep **untracked** droppings out, because the cache is copied from a clone and an ignored
  file was never in the clone. Do not compress this into *"`.gitignore` has no effect on what is
  cached"*: that is false, and `test_bytecode_droppings_cannot_be_committed` reasons from the
  true version.

  **The rule: a file ships iff a consumer needs it in the cache.** Stated with no list of the
  qualifying kinds, deliberately — **if you cannot establish that a consumer needs it in the
  cache, it does not ship.** Two earlier drafts of this rule enumerated instead, and each was
  falsified by an entry the inventory already required: *"iff the engine reads it at runtime"* by
  `LICENSE` and `README.md`, and the enumeration that replaced it by
  `hooks/loop.append-guard.example.json`, a template a consumer copies that nothing reads. That is
  the enumerable-assertion trap this file documents, so the fix is the default-deny posture rather
  than a third list. **`PayloadContentsTests` pins the payload against a declared inventory** and
  fails on any path outside it; it does not itself decide what belongs there.
- `.claude-plugin/` holds **only** manifests — in **each** of its two locations, which is the part
  that is easy to get wrong: `marketplace.json` sits at the repo root (it is the marketplace
  index, and it does **not** ship), while `plugin.json` sits inside the payload at
  `plugins/dev-loop/.claude-plugin/plugin.json` (it must, or the directory `source` names is not
  an installable plugin). Skills, hooks, commands and the mutation harness live under
  `plugins/dev-loop/` in their own directories; `tests/`, `docs/`, `.github/`, `.claude/`,
  and `CLAUDE.md` stay at the repo root and stop shipping. The front-door `README.md` also stays
  at the repo root, but its **content does ship**, as the byte-identical payload copy above.
- **`plugins/dev-loop/tools/` holds executables meant to be run by path rather than wired to a
  tool event** — currently `mutate_verify.py`, which ships because `loop-engine.md` (AC-verifier →
  Part 2) invokes it at runtime as `${CLAUDE_PLUGIN_ROOT}/tools/mutate_verify.py`. **The root
  `tools/` holds only *inputs* to it** — currently `mutation-specs/self-check.json`, the hand-run
  self-check that keeps #60's mutation numbers reproducible — and does **not** ship, because
  nothing reads it at runtime. It holds no executables, so do not read this bullet as licensing a
  new one there: an executable at the repo root would not ship. The distinction from
  `plugins/dev-loop/hooks/` is what invokes them: a hook is registered in
  `plugins/dev-loop/hooks/hooks.json` and fired by the harness; a tool is run by whoever needs
  it. Both shipped directories are reached as `${CLAUDE_PLUGIN_ROOT}/<dir>/<file>` and both
  are **stdlib-only**, for the same reason — they execute under bare `python3` in a consumer's
  environment.
- **`posts/` holds the blog series sources and does not ship.** Markdown for the
  `claude-code-loop` series, published to the Pages site that two sibling repos already publish
  into. The boundary with `social/` is what matters: `social/` is **gitignored working state** —
  the candidate ledger, the scout, the series outline, the research evidence base, drafts — while
  `posts/` is committed deliverable. A file crosses over when it is ready to be reviewed as
  publishable. **`social/README.md` indexes that working state, and it is the thing to read first
  when picking the series back up**: gitignored files leave no trace in git history, so nothing
  else will tell you they exist or which one is authoritative for what.
  `posts/README.md` is the frontmatter contract and `tests/test_posts_frontmatter.py` enforces it,
  so a post is gated by the same CI run as the plugin. Three frontmatter fields attest to manual
  steps (Claude Code version verified, humanizer pass, claims verified); each guard checks that an
  attestation was **made**, never that the work behind it was done well — the distinction
  `CLAUDE.md` draws everywhere else between a coupling's identity and a proposition's truth.
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
from `~/.claude/plugins/cache/claude-code-loop/dev-loop/<version>/`; edits to `plugins/dev-loop/`
here do not take effect until the next release's re-install. This is a **safety property** — a run
cannot mutate the engine driving it — but it also means the loop keeps exhibiting
the defects we are fixing until that re-install lands.

**All three consumers moved 0.0.1 → 0.2.0 on 2026-08-21**, which is what makes the two instances
below history. **They have moved again since, and this sentence is not where to learn the current
version** — `ls ~/.claude/plugins/cache/claude-code-loop/dev-loop/` is, and the highest version
there is the engine that drove the most recent run. A version pinned in this file rots at every
release; this one did, and it is the first thing you need when reading a journal. They are kept because the *shape* recurs at every release, and because reading a journal
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
| the three maintainer `CLAUDE.md` files (root, `tests/`, `plugins/`) | **`README.md`** (see below), anything in `plugins/dev-loop/` (the whole payload — skills, commands, hooks, tools, `plugin.json`, **and the payload's own `README.md` and `LICENSE`**), `tests/` (its code, not its `CLAUDE.md`), `posts/`, `.github/`, `.claude/`, `.claude-plugin/`, **the root `LICENSE` and `LICENSE-prose.md`** |
| typo / link / formatting fixes anywhere **except** `README.md` and `plugins/dev-loop/` | any change to runtime behavior |

**The maintainer notes are split across three files and none of them ships.** The root `CLAUDE.md`
is the orientation every session loads; `tests/CLAUDE.md` covers what the suite guards and the
ceiling on any test over prose; `plugins/CLAUDE.md` carries the engine's invariants and sits one
level *above* the payload so it stays out of every consumer's cache. Each is loaded when you open
something in its directory, which is why the engine's invariants are not restated at the root.

**`README.md` is on the PR side while the payload mirrors it, and that is not a style rule.**
`plugins/dev-loop/README.md` is a byte-identical copy (#170/AC6), pinned by
`test_payload_readme_is_identical_to_the_front_door`, so **an edit to one file without the other
fails the suite** — and CI runs on pushes to `main`, so taking the direct-push exception for a
README typo red-lines `main`. Edit both copies in the same commit, on a branch, through a PR. When
the slim consumer README lands the mirror goes away and this row can be revisited. This sentence
exists because the duty was previously stated *only* in that test's failure message, which a
maintainer reads after the breakage rather than before it.

`.claude/loop.config.md` is on the PR side for the same reason the engine is: it binds the gates the
loop runs in this repo, so editing it is a behavior change. Note the engine separately forbids the
orchestrator from editing its own config mid-run — config changes are human work, landed outside a
loop iteration.

`plugins/dev-loop/skills/dev-loop/loop-engine.md`,
`plugins/dev-loop/skills/dev-loop/SKILL.md`, and `plugins/dev-loop/commands/init-loop.md` are
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

**`v0.2.0` shipped 2026-08-20** (`1e54d3c`). It grew past a patch bump — it renumbers the pipeline,
adds an `in-acceptance` status, rewrites Resume, and reverses a multi-site invariant — which is why
it was a minor bump and not the `v0.0.2` this file once named.

**Which milestone is live is deliberately NOT stated here.** It lives in two places that cannot
drift from the work: `loop.config.md`'s `BACKLOG_SOURCE` binding, and the milestone list itself.
This paragraph used to name one — and went on naming `v0.2.0` through two later releases, including
one where that milestone had already drained. That is the enumerable-assertion trap these files
document repeatedly, arriving on schedule in the paragraph least likely to be re-read. **Read the
binding, not this file.**

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
paragraph. (This is the same enumerable-assertion trap; the fix is to state where the number
lives, not to restate the number.)

**#1 closes when the last child does — and that is now known to be after the v0.2.0 release.** #30
was deferred to `deferred-corpus` at its plan gate on 2026-08-13, and #30 *is* epic **#15**'s third
acceptance criterion verbatim, so **#15 and #1 both stay open past the bump.** Accepted
deliberately: E4's load-bearing half (F2 — the plan gate, #28 + #29) shipped, and what deferred is
the recommendation half. The epic rows are `deferred` in the ledger, so nothing blocks #36.

**The batching convention was superseded 2026-07-28: batch the *release*, not the PRs.** One version
bump and one consumer re-install, but multiple coherent PRs. The old "never cut per-finding PRs" rule
existed to avoid re-installing per finding — a release cost, not a PR cost.

**`deferred-corpus` — the deferral milestone, and it is no longer the two-issue footnote this file
described until 2026-08-13.** **It was named `v0.3.0` until the 2026-09-11 release took that
number** (D012); issues, PRs and journal entries written before that date call it `v0.3.0`, and it
is the same milestone. It opened as exactly that: `TEST_EFFICACY_AGENT` (#37) and `REVIEW_TIERS`
(#38), "both wait on corpus, not on effort." It has since grown by an order of magnitude — **check
the milestone for the count.** No number is stated here on purpose: the two previous drafts of this
sentence each named one and each went stale within a fortnight, which is the enumerable-assertion
trap these files document repeatedly.

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
because the engine's copy is reachable and the skeleton's copy is not.
`plugins/dev-loop/commands/init-loop.md`'s maintainer note states the step-number case of it where
it bites, above the skeleton it governs.

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
execution window 7/31–8/15, **19 issues closed and 31 new ones were filed** — 12 into v0.2.0, 15
into `deferred-corpus`, 4 left unmilestoned, with the rate showing no decay (four filed in the final
two days). The milestone could not converge because it was also the intake queue.

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

**The `tech-debt` label exists so `deferred-corpus` keeps meaning something.** Work that waits on
*effort* rather than *corpus* does not belong in the deferral milestone — putting it there would
dissolve the one criterion that makes `deferred-corpus` a category instead of a junk drawer. #35,
#62 and #76 carry the label and no milestone. Corpus- or evidence-gated work (#49, #61, #71) still
goes to `deferred-corpus` proper. When deferring, pick the bucket by *what the work waits on*, and
never widen `deferred-corpus`'s criterion to avoid the choice.

### Standing convention: the README status block ships with the version bump

**Any PR that bumps `plugins/dev-loop/.claude-plugin/plugin.json` must update the `README.md` status block in the
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
