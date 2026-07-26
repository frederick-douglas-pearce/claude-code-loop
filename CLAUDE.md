# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A **Claude Code plugin** (`dev-loop`, distributed via the `claude-code-loop` marketplace) that
packages a supervised dev-loop engine originally built and hardened in
[AgentFluent](https://github.com/frederick-douglas-pearce/agentfluent). The deliverable is almost
entirely **prompt artifacts** (markdown read by an agent at runtime) plus **one Python hook**. There
is no build, no package, no dependency manifest, and no CI.

Consequence: most "code" here is instructions a future agent will execute. Precision of wording,
internal consistency of cross-references, and the fail-safe posture of each instruction *are* the
correctness properties — review changes to `.md` files as carefully as code.

## Commands

```bash
python3 -m unittest discover -s tests        # full suite (stdlib unittest only; no pytest, no CI)
python3 tests/test_guard_append_only.py      # same suite, direct
python3 -m unittest tests.test_guard_append_only.CheckTests.test_blocks_dropping_entries   # one test
```

Only `hooks/guard_append_only.py` is testable code. The markdown artifacts are validated by
review + dogfooding, not tests.

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

## Engine semantics worth knowing before editing

These are the non-obvious invariants the prose encodes; changes that violate them are regressions
even though nothing will fail loudly:

- **One issue per invocation, then STOP and journal.** State lives in the ledger on disk, not in
  context, so a fresh invocation resumes correctly after `/clear` or compaction.
- **Live git/PR state is the source of truth on resume**; the ledger row status is only a coarse
  stage anchor. The ledger is gitignored in consuming repos, so it can be stale.
- **Route and Status are separate columns.** `blocked`/`parked`/`hold` are Status overlays that
  retain their semantic Route (`code`/`research`/`docs`/`stub-defer`).
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
redirection are out of scope. Keep it **stdlib-only** (it runs via bare `python3`, no venv).

## Repo conventions

- `.claude-plugin/` holds **only** manifests (`plugin.json`, `marketplace.json`). Skills, hooks, and
  commands live at the repo root in their own directories.
- `${CLAUDE_PLUGIN_ROOT}` (this installed plugin) and `${CLAUDE_PROJECT_DIR}` (the consuming repo)
  are not interchangeable — the engine and hook both depend on the distinction.
- The loop ledger (`queue.md`, `progress.md`, `issue-<N>.plan.md`) lives under the *consuming*
  project's `LEDGER_ROOT` and is gitignored there. Nothing ledger-related belongs in this repo.
- Commits follow Conventional Commits (`feat:`, `fix:`, `chore:`).

## Issue tracking

**All future issue work for the plugin is tracked in *this* repo** (`frederick-douglas-pearce/claude-code-loop`),
not in AgentFluent. The early extraction stories (S2–S4, epic
[#611](https://github.com/frederick-douglas-pearce/agentfluent/issues/611)) were filed in AgentFluent
before this repo existed; those links in `README.md` are history, not the live backlog.

Work is split across **two deliberately decoupled milestones** — they move independently, so do not
let one block the other:

**`public-readiness`** — everything required before flipping this repo from private to public, which
is the current priority. Covers CI + branch protection (#3), mechanical consistency checks for the
markdown deliverable (#4), the README status block (#2) and trust-model section (#5), and a
clean-machine install smoke test (#6). #2 and #5 both touch the README front door and will likely
land in one PR, but close independently.

**`v0.0.2`** — the hardening batch, currently
[#1 — Plugin hardening backlog](https://github.com/frederick-douglas-pearce/claude-code-loop/issues/1)
alone. It is an **accumulator issue**: findings surfaced by real loop runs (the first external
adoption [us-presidential-vote-analysis](https://github.com/frederick-douglas-pearce/us-presidential-vote-analysis),
and the AgentFluent dogfood) are appended as checklist items `F1`, `F2`, … Each records where it
surfaced, the gap, a *generic* fix (removing the AgentFluent-ism rather than special-casing), and a
severity. Working convention: **do not cut per-finding PRs — batch them.** Implement the accumulated
findings as one batch, bump `.claude-plugin/plugin.json` to `0.0.2`, then re-install in the consumers
(AgentFluent + the vote repo). This milestone is gated on the AgentFluent v0.12 release and is
**not** a blocker for going public.

When the v0.0.2 batch lands, update the `README.md` status block in the same PR (see #2) rather than
leaving it to rot until someone notices.
