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

Two modules, and the split between them matters:

- **`tests/test_guard_append_only.py`** — behavior of the one piece of executable code.
- **`tests/test_repo_consistency.py`** — **mechanical** checks on the markdown/JSON deliverable:
  the shipped example sidecar still loads through the real `load_registry`; the composed
  `plugin@marketplace` identifier still matches every hand-written call site; and engine `CAPS` ⊆
  the `/init-loop` skeleton (see the three-layer split below — this is that contract, enforced).

**Prompt *semantics* remain validated by review + dogfooding, and that is deliberate** — the
consistency module tests couplings, never whether an instruction is *right*. Do not try to grow it
into a semantic test of the engine.

Two habits it depends on. First: these checks **pass against the tree they were written for**, so a
green run proves nothing by itself — when you change one, mutate the thing it guards and confirm it
actually fails. Second: `CapsVocabularyTests.ALLOWED_NON_BINDINGS` is an escape hatch (currently two
env vars and the meta-term `CAPS`). Adding to it is almost always the wrong fix — a growing
allow-list means the test is being worked around rather than the vocabulary kept in sync.

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
   ~40-line binding seam. Every `CAPS` name in the engine (`BACKLOG_SOURCE`, `SCOPE_AGENT`,
   `DESIGN_AGENT`, `LINT_CMD`/`TYPE_CMD`/`TEST_CMD`, `BRANCH_FMT`, `COMMIT_CONV`, `MERGE_METHOD`,
   `RELEASE_SCHEME`, …) resolves here.

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
- **Gate parameters that name a *procedure* must never be bound to a user-triggered skill.**
  `CODE_REVIEW` is the live example: a skill marked `disable-model-invocation` cannot be invoked by
  the orchestrator, so binding one makes the gate **silently inert** — it does not error, it just
  never runs. The shipped `/init-loop` skeleton bound `/code-review` that way for the whole of
  v0.0.1 (F7, fixed in #10; consumer configs still carry it, see #36 / AC5). Any new gate binding
  gets the same scrutiny: name something the orchestrator can actually execute. F14 (#21) generalizes
  this to the whole class — an unbound or `TODO(init-loop)` binding never means "skip the gate."
- **Three resting-state classes** — terminal (`RUN COMPLETE`), resting-non-terminal (`RUN PARKED`,
  awaiting an external event, released only by explicit human un-park), and held/pending (no
  sentinel). `progress.md` is append-only and the **most recent** sentinel wins.
- **Default-deny at the merge gate:** uncertainty about auto-merge eligibility means fall back to
  the human. `mode:` currently gates the merge gate *only* — the plan gate is conditional in every
  mode, and the engine restates this in ~5 places (step 5, step 11, both `queue.md` header mode
  descriptions, the gate table) plus `SKILL.md`. **Issue #1 / F2 reverses this** (calibration will
  make the plan gate unconditional); when implementing it, every restatement must change together.
- **Notes on `parked`/`blocked` rows record the durable curation DECISION, never mutable live
  evidence** — the latter is contradicted by the next re-check and destabilizes resume.

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

- `.claude-plugin/` holds **only** manifests (`plugin.json`, `marketplace.json`). Skills, hooks, and
  commands live at the repo root in their own directories.
- `${CLAUDE_PLUGIN_ROOT}` (this installed plugin) and `${CLAUDE_PROJECT_DIR}` (the consuming repo)
  are not interchangeable — the engine and hook both depend on the distinction.
- The loop ledger (`queue.md`, `progress.md`, `issue-<N>.plan.md`) lives under the *consuming*
  project's `LEDGER_ROOT` and is gitignored there. Nothing ledger-related belongs in this repo.
- Commits follow Conventional Commits (`feat:`, `fix:`, `chore:`).

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
| `README.md`, `CLAUDE.md`, `LICENSE` | anything in `skills/`, `commands/`, `hooks/`, `.claude-plugin/`, `tests/`, `.github/` |
| typo / link / formatting fixes anywhere | any change to runtime behavior |

`skills/dev-loop/loop-engine.md`, `skills/dev-loop/SKILL.md`, and `commands/init-loop.md` are
markdown, but they are **the product** — an agent executes them at runtime. Editing them is a
behavior change and takes the PR path, however prose-like the diff looks. When unsure which side a
change falls on, open the PR.

This exception is for ad-hoc human/interactive edits. It does **not** apply to the `dev-loop` skill
working a routed issue: the engine's `docs` route still goes through commit → PR → light review
(step 8/9), and the loop must never bypass its own gates.

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
index (F1–F21), not a work item** — "no PR should ever be opened for #1." Findings surfaced by real
runs (the first external adoption
[us-presidential-vote-analysis](https://github.com/frederick-douglas-pearce/us-presidential-vote-analysis),
the AgentFluent dogfood, and #6's smoke test) are recorded there with where they surfaced, the gap, a
*generic* fix (removing the AgentFluent-ism rather than special-casing), and a severity; the detail
lives in its comments, which are the only copy. They are scoped into **seven epics and ~21 stories**
under the milestone, and #1 closes when the last child does.

**The batching convention was superseded 2026-07-28: batch the *release*, not the PRs.** One version
bump and one consumer re-install, but multiple coherent PRs. The old "never cut per-finding PRs" rule
existed to avoid re-installing per finding — a release cost, not a PR cost.

**`v0.3.0`** — two deferrals scoped out of v0.2.0 rather than dropped: the `TEST_EFFICACY_AGENT`
binding (#37) and `REVIEW_TIERS` (#38). Both wait on corpus, not on effort.

### Standing convention: the README status block ships with the version bump

**Any PR that bumps `.claude-plugin/plugin.json` must update the `README.md` status block in the
same PR.** Not just the v0.2.0 release — every bump, permanently. The status block names the current
version, what actually works, where the live backlog is, and which repos have adopted it; all four
rot silently, and the recurring failure mode is that nobody notices until a reader does. Treat it as
part of "done" for a release, not a separate chore.

The README's **trust-model section** ("What the loop can do to your repo") has the same property for
a different trigger: it restates the engine's gating posture and hard limits, so a change to the
merge gate, the mode semantics, or the guard hook's scope must update it in the same PR. **F2 (#28 +
#29) is the live example** — making the plan gate unconditional under `calibration` changes what that
section says about mid-pipeline stops. The section is worded to survive that change, but re-read it
when F2 lands. #36 / AC3 carries this for the release, and F5 (#31), F8 (#25) and F16 (#26/#27)
change it too.
