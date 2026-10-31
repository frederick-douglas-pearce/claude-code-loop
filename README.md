# claude-code-loop

A **Claude Code plugin** (`dev-loop`) that works your issue backlog the way a small, disciplined
dev team would: one issue at a time — scoped, planned, design-reviewed, implemented, code-reviewed,
security-reviewed where the change calls for it, acceptance-tested by an agent that did not write
the code, and merged — with **you approving every plan and every merge by default**. Each
invocation handles exactly one routed issue end-to-end and writes everything it did to a ledger on
disk, so the next invocation — after a `/clear`, a compaction, or a crash — picks up where the
last one stopped.

The engine was originally built and hardened in
[AgentFluent](https://github.com/frederick-douglas-pearce/agentfluent) (where it ran the v0.10.x /
v0.11.0 releases) and extracted here. Install it once, generate a per-project `loop.config.md` with
`/init-loop`, and run your backlog as a loop.

> **v0.4.0, not yet stable**: six repos drive it today; see *Status* for what that does and
> doesn't establish.

## Why try it

- **You stay in charge of what matters.** By default the loop stops for your approval on every
  plan before any code is written and on every merge. You can loosen either one, separately, and
  only on purpose — and two stops (a design reviewer that rewrote the plan, and a review finding
  that raises a design question) stay on whatever you loosen.
- **It works like a team, not a single agent.** Scope and priority questions go to your product
  agent, design questions to your architect agent, code review fans out to parallel reviewers that
  are handed the issue's acceptance criteria, and acceptance is judged by a fresh agent that did not
  write the change. A fix for a review or acceptance finding is re-checked by a fresh agent, never
  by its author — editorial wording fixes are the one exception, and the merge gate tells you how
  many there were.
- **The rigor scales to the change.** Each issue is routed by its labels and by path rules in your
  config. A `code` change gets the full pipeline and every gate. `research` gets a lighter plan,
  with the architect optional. `docs` skips the architect and security passes and gets a light
  review. `stub-defer` is journaled and left in the backlog. On any route, a review finding that
  raises a design question still goes to the architect and then to you. If markdown is what your
  project ships, your config can route it as `code`.
- **It asks whether your tests would notice a regression.** On a `code`-route change that alters
  behavior, the acceptance gate deliberately breaks the guarded code in a throwaway copy of your
  tree and reports any test that stays green.
- **It survives `/clear`, compaction and crashes.** State lives in a ledger on disk. On resume the
  loop reconciles each unfinished row against live git and PR state before it starts anything new,
  and stops on an open PR it cannot account for rather than adopting it.
- **It never reports a gate it did not run as passed.** No verdict means not passed, a verdict
  covers only the commit it ran on, and an unset binding falls back to a built-in equivalent or
  stops — it never silently turns the gate off.
- **It runs your project's conventions.** Your lint, type and test commands, branch format, commit
  convention, merge method and PR template live in one per-project config file, which
  `/init-loop` infers for you. The engine itself is never edited per project.
- **Nothing to install beyond Claude Code, git, the `gh` CLI and Python 3.9+.** The engine is
  markdown an agent executes; the guard hook and the mutation harness are standard-library Python.
  It is written around GitHub, using `gh` for issues, pull requests and CI checks.

## How the loop works

This is a **structured, routed loop**, not a graph orchestrator: a single
supervised orchestrator handles **exactly one issue end-to-end per invocation**,
delegates to specialized agents (scope, design, code review, AC-verify), gates on
human judgment when uncertain, and journals everything to a ledger that lives
outside the model's context so a fresh invocation resumes correctly. It is the
kind of well-instrumented loop that "graph engineering" treats as a single node.

### A dev team, in a loop

The pipeline is shaped after the roles on a human team, and each role is a binding you control
in `loop.config.md`. **The plugin ships no agent definitions**: the scope and design roles name
subagents you already have (this repo binds its own `pm` and `architect` agents).

| Team role | What it does in the loop | Bound by |
|---|---|---|
| Product manager | answers scope, priority and requirements questions — including any plan whose value story lacks a credible user or a checkable falsifier — and splits an issue too large for one context | `SCOPE_AGENT` |
| Architect (read-only) | reviews the plan before any code when one of your `ARCHITECT_TRIGGERS` fires or the loop is unsure; gives the scope ruling when a blocking review finding raises a design question; returns a review and never writes to your tree | `DESIGN_AGENT` |
| Developer | the orchestrator itself: writes the plan, implements on a branch, runs your build commands, commits, pushes, opens the PR, applies the fixes the gates ask for | `LINT_CMD` / `TYPE_CMD` / `TEST_CMD` / `HERMETIC_TEST_CMD`, `BRANCH_FMT`, `COMMIT_CONV`, `PR_TEMPLATE` |
| Code reviewers | parallel read-only finder subagents over the diff, each handed the issue's acceptance criteria, with angles picked from the change's risk surface and a guard-efficacy lens as a floor | `CODE_REVIEW` |
| Security reviewer | runs where the route and the touched surface call for it | `SECURITY_REVIEW` |
| QA | a fresh-context acceptance verifier: did the change meet every criterion (Class A), and would its tests notice if it broke (Class B, the mutation pass) | `VERIFY`, plus the bundled mutation harness |
| Owner | you: the final call on scope, design and merges — approve plans, approve merges, settle anything the agents disagree on, punt on, or cannot resolve | the `plan-gate:` and `mode:` fields in the run's ledger |

### The pipeline: one issue per invocation

Steps are numbered 0–12 in the engine. The order changed in v0.2.0, which moved the acceptance gate
to last so that it certifies the commit that actually merges.

| Step | What happens | Comes back to you when |
|---|---|---|
| **0. Load / resume** | Finds the active run, or asks which backlog to run and initializes one. Finishes any interrupted row against live git/PR state before anything new, then scans for open PRs no row covers. | a ledger status it does not recognize; an open PR it cannot attribute |
| **1. Select** | Reconciles the queue against the live backlog source, checks the budget caps, picks the next selectable issue by `PRIORITY_LABELS`, and size-checks it. | an issue joined or left the backlog after the run began (asked once; never auto-applied) |
| **2. Route** | The Router sets the issue's route (`code` / `research` / `docs` / `stub-defer`) and its starting status. | — |
| **3. Plan** | Writes `issue-<N>.plan.md`: acceptance criteria verbatim, a value framing scaled to the route, and any falsifier cheap enough to check before code, checked. | the value story does not hold (it goes to `SCOPE_AGENT` first) |
| **4. Architect** | When a trigger fires or the loop is unsure: freezes the plan's approach, then has `DESIGN_AGENT` review it, then writes the outcome into the plan. | — |
| **5. Plan gate** | Presents the plan with its value framing. | every issue under `plan-gate: always` (the default under `calibration`); under `conditional`, on a failed value story, ambiguity, risk, agent disagreement or a punt, or doubt; **always** if the architect materially changed the plan |
| **6. Implement** | Branch, code, tests and docs. Lint, type and test each pass on their own exit status; the offline tier runs where you bound one. | — |
| **7. Commit + PR** | Stages explicit paths only, pushes the branch, opens the PR from your template, journals an open record, waits for CI to go green. From then on, every commit is pushed as soon as it is made. | — |
| **8. Code review** | Finder fan-out; findings classed blocking or editorial; blocking fixes committed and re-checked once by a fresh checker; editorial ones applied in one contained sweep. | a blocking finding raises a design question; a blocking finding survives the re-check |
| **9. Security** | By route: a local review, or a labeled review path when a sensitive surface is touched. Before labeling, checks that the remote branch matches the local one. | the local and remote branches disagree, or the head check cannot run |
| **10. Acceptance** | A fresh AC-verifier, plus the mutation pass where it is due. The last gate before merge. | a finding of either class survives one re-verify; a fix here changed source no earlier gate saw |
| **11. Merge** | Checks that the remote branch matches the local one, before deciding and again right before merging; then merges through `MERGE_METHOD`, with the PR's own branch deleted. | every merge under `mode: calibration` (the default) and on any route you have not graduated; the local and remote branches disagree, or the head check cannot run |
| **12. Journal + stop** | Appends the close record — including a `- Budget:` line of subagent runs and gate rounds — marks the row `done`, and stops. | — |

Re-invoke for the next issue by hand, running `/clear` first so it does not start on the last
issue's context. Claude Code's `/loop` can drive it instead, but it re-fires in the same session
and cannot `/clear`, so each issue then starts on the last one's context. The optional
`iteration-cap:` and `subagent-cap:` fields in the ledger header halt the driver once a run reaches
them; a manual re-invoke past a cap is warned and journaled, not stopped.

### Routes

The Router classifies each issue from its labels and from the path rules in your config's
`SOURCE_LAYOUT`. Markdown is not automatically `docs`: where markdown is what a project ships, the
config can say so — this repo's own config routes the engine's markdown as `code`.

| Route | Pipeline differences |
|---|---|
| `code` | the full pipeline and every gate; the offline test tier when the change adds or modifies a test; the mutation pass when it alters behavior |
| `research` | a lighter plan, no test-coverage gate, architect optional, security only if dependencies are added; work placed outside the package; no mutation pass |
| `docs` | no architect or security pass; a light review; no mutation pass |
| `stub-defer` | not implemented — journaled and left in the backlog |

Whatever the route, a blocking review finding that raises a design question still consults the
architect and stops for you.

### Two human gates, set separately

- **The merge gate follows `mode:`.** Under `calibration` (the default) you approve every merge.
  Under `escalation-only`, a route you have explicitly *graduated* may auto-merge — but never a
  feature or breaking change, a risky or irreversible one, one that touches a security surface,
  one with a contested or unresolved review, acceptance or offline-tier finding, or one that bumps a
  release past patch. If eligibility is unclear, it comes back to you.
- **The plan gate follows `plan-gate:`.** `always` (the default under `calibration`) stops on every issue;
  `conditional` stops only on the engine's judgment conditions. An absent or unrecognized value
  reads as `always`.
- **The two are independent**, so relaxing how much of the planning you review never loosens what
  merges without you. The details, and the stops that neither field reaches, are in *What the loop
  can do to your repo* below.

### State lives in a ledger, not in the context

Each run gets a directory under `.claude/loop/<run-slug>/` (your `LEDGER_ROOT`), gitignored and
never committed:

- **`queue.md`** — the authoritative work list. Route and Status are separate columns; a row moves
  `queued → routed → planning → plan-approved → implementing → in-pr → in-review → in-acceptance →
  done`, may rest at `hold` (you held the merge) or `parked` (waiting on an external event), and
  ends `done`, `deferred` or `blocked`.
- **`progress.md`** — the append-only journal: every gate decision, every fallback or gate error,
  and each iteration's open and close records. Its most recent sentinel says whether the run is
  complete, parked, or resumed.
- **`issue-<N>.plan.md`** — the per-issue plan, including the approach frozen before the architect
  saw it, which is what the plan gate diffs against.

## Design: three layers

The plugin keeps a strict split between what is generic, what is per project, and what loads first:

1. **A thin entry point** — `skills/dev-loop/SKILL.md`. It names the two files to read, then
   restates a short list of fail-safe invariants, so that a partial load **over-escalates** rather
   than under-gates.
2. **A project-agnostic engine** — `skills/dev-loop/loop-engine.md` is the **core**: the pipeline,
   ledger format, router, resume, gate, convergence and budget semantics, and a **phase index**
   naming each on-demand unit. The core is read in full on every invocation; a unit is read at its
   point of use, which the phase index names for each unit. A unit the loop cannot confirm it read
   in full counts as not loaded, and the step that needs it does not pass. Neither the core nor any
   unit contains a project-specific value.
3. **A per-project binding seam** — `.claude/loop.config.md` in *your* repo. Every `CAPS` name the
   engine uses (`BACKLOG_SOURCE`, `SCOPE_AGENT`, `DESIGN_AGENT`, `CODE_REVIEW`, `TEST_CMD`,
   `MERGE_METHOD`, …) resolves there.

**The contract between the layers is the parameter vocabulary, never the layout.** The engine refers
to config values by name only, so the config's sections are yours to arrange, and porting a new
project means editing the config and nothing else. When the engine needs a fact about a project, it
gets a new `CAPS` parameter rather than a special case. `/init-loop` embeds the config's skeleton and
an inference map for filling it in, and the test suite fails if the engine reads a parameter that
skeleton does not offer.

## Status

> **Status — v0.4.0; not yet stable.** Four pieces ship: the
> `dev-loop` skill (`SKILL.md`, a core `loop-engine.md`, and the units under `phases/` and
> `reference/` that it reads on demand), the `/init-loop` onboarding
> command, the append-only guard hook, and the mutation harness the acceptance gate
> runs (`plugins/dev-loop/tools/mutate_verify.py`). **Six repos drive it**: the first external adoption
> [us-presidential-vote-analysis](https://github.com/frederick-douglas-pearce/us-presidential-vote-analysis),
> the ongoing AgentFluent dogfood,
> [claude-code-sessions](https://github.com/frederick-douglas-pearce/claude-code-sessions),
> [sportswear-esg-news-classifier](https://github.com/frederick-douglas-pearce/sportswear-esg-news-classifier)
> (since 2026-09-06), `claude-hook-validator` (a private repo, onboarded directly at v0.3.1 on
> 2026-10-09), and (since 2026-07-28) this repo, which runs the loop it develops and
> is the source of most of the findings below. **They sit on different engine versions
> deliberately — and this list is not the authority on which.** Version pinning is
> per-project; read it from `~/.claude/plugins/installed_plugins.json`, never from prose
> here. At the v0.3.0 cut (2026-09-11) three repos took that release — this one,
> `us-presidential-vote-analysis` and `sportswear-esg-news-classifier` — and the same three
> took v0.3.1 on 2026-10-08 and 2026-10-09. AgentFluent and `claude-code-sessions` stay held
> on v0.2.0 as an untreated control for the cost research in [`docs/research/`](docs/research/)
> (see *How the loop gets better*). **111 issues had been carried to `done` by the loop as of
> the v0.3.0 cut**, across the five repos driving it then. That is enough to say the
> plugin/config seam holds and that the hardening works under load; it is not enough to call
> it stable.
>
> **v0.4.0 is a minor bump because it adds stops.** The loop now pushes every commit on the
> PR branch as soon as it makes it, and before it applies a review label or merges it checks
> that the local and remote branches agree. If they don't, or the check can't run, it stops
> for you and runs nothing that moves either branch to make them agree
> ([#107](https://github.com/frederick-douglas-pearce/claude-code-loop/issues/107)). Five
> places where two engine passages disagreed now follow the stricter one
> ([#277](https://github.com/frederick-douglas-pearce/claude-code-loop/issues/277)); the
> visible one is that a repo whose `DESIGN_AGENT` is still `TODO(init-loop)` stops on an
> issue that triggers the architect instead of improvising its own design pass. The rest is
> the first half of the cost work
> ([#271](https://github.com/frederick-douglas-pearce/claude-code-loop/issues/271)), shipped
> unmeasured by decision. The engine core and `SKILL.md`, which every invocation reads, are
> 7.8% smaller in bytes than in v0.3.1: duplicated passages and maintainer history are gone,
> and three rarely-read sections moved into units read on demand (#275, #292, #278). The loop
> also tells you to `/clear` between invocations, and the Install section covers the cache
> setting for API-key users (#287). A smaller footprint is not yet a saving; the epic's
> benchmark is what will measure one.
>
> **v0.3.1 is a patch: it changes how the engine is loaded.** The engine is now a core
> that every invocation reads in full, plus units it reads at their point of use. A unit
> the loop cannot confirm it read in full counts as not loaded, and the step that needs it
> stops for you rather than passing
> ([#128](https://github.com/frederick-douglas-pearce/claude-code-loop/issues/128)). The
> plugin now ships its runtime tree only
> ([#170](https://github.com/frederick-douglas-pearce/claude-code-loop/issues/170)). It is
> also the release the cost research is measuring: the files every invocation reads shrank
> 23.8% in bytes against v0.3.0, clearing the pre-registered ≥20% floor — which is a smaller
> footprint, not yet a saving. Whether a run actually gets cheaper is
> [#133](https://github.com/frederick-douglas-pearce/claude-code-loop/issues/133)'s verdict,
> measured against a frozen v0.3.0 baseline.
>
> **v0.3.0 is a minor bump because it adds a gate.** When code review returns a **blocking**
> finding that raises a design question — whether the approach is right, whether a fix
> belongs in this change at all, whether several findings share one root cause — the loop
> consults its design reviewer for a **scope ruling** and stops for you with that ruling
> attached. It fires on every route, under every mode, at whatever round the finding arose,
> and no config setting reaches it
> ([#114](https://github.com/frederick-douglas-pearce/claude-code-loop/issues/114)).
> The rest of the release is the review gate getting cheaper without getting weaker:
> findings sort into **blocking** and **editorial**, so a prose fix no longer costs a full
> round (#121); the guard-efficacy lens becomes a floor rather than an option (#122); and
> rounds after the first read only the delta since the last reviewed commit, defaulting back
> to a full round whenever that anchor cannot be trusted (#120). Three verification fixes
> ride along — an agent that returns **no verdict** is recorded as not passed rather than
> passed (#119), the mutation harness refuses to break a tree it cannot tell apart from
> yours (#111), and the loop must mark which of its claims it verified and which it merely
> inferred (#115) — and a run whose ledger carries no `plan-gate:` field is now **told once per
> run** that the loop inferred `always`, and what the one-line remedy is, instead of arriving
> there in silence (#108).
>
> Findings from real runs are indexed in
> [#1](https://github.com/frederick-douglas-pearce/claude-code-loop/issues/1) — read
> the comments there for the current set; its title names only the earliest ones.
> **v0.2.0** was the hardening release that came out of them: it makes the acceptance
> gate adversarial, moves it last so it certifies the commit that actually merges, and
> defaults the plan gate to stopping on every issue under `calibration` — alongside
> gate-currency expiry, an orphan-PR scan on resume, an offline-test tier, and a stop
> on any ledger status the engine does not recognize. Expect rough edges in porting to
> a repo unlike the six above; that is exactly what #1 collects.
>
> **Issues for this plugin live in
> [this repo's tracker](https://github.com/frederick-douglas-pearce/claude-code-loop/issues).**
> The AgentFluent links in this README are **provenance, not the live backlog** — the
> extraction stories (S2–S4, under epic
> [#611](https://github.com/frederick-douglas-pearce/agentfluent/issues/611)) were filed
> there before this repo existed.

## Quick start

```
/plugin marketplace add frederick-douglas-pearce/claude-code-loop
/plugin install dev-loop@claude-code-loop
/init-loop
```

1. Read *What the loop can do to your repo* below — it creates branches, commits, pushes, opens
   PRs and merges on your behalf.
2. Review the generated `.claude/loop.config.md` and resolve every `TODO(init-loop)` — in
   particular, bind `SCOPE_AGENT` and `DESIGN_AGENT` to subagents you have, or record that you have
   none the way the generated rows' notes describe.
3. Ask Claude to "run the dev loop" (or invoke the `dev-loop` skill). The first invocation asks
   which milestone, label or `TODO.md` to work, initializes the ledger, and takes the first issue —
   stopping for you at its plan.

## Install

```
/plugin marketplace add frederick-douglas-pearce/claude-code-loop
/plugin install dev-loop@claude-code-loop
```

- `dev-loop` is the plugin id (from `plugin.json` `name`).
- `claude-code-loop` is the marketplace id (from `marketplace.json` `name`).

The plugin ships the engine, the onboarding command, the guard hook and the mutation
harness; it does nothing until the consuming repo supplies the per-project config below. Run
`/init-loop` to generate that config (or write it by hand).

**Requirements: Python 3.9+**, for the append-only guard hook and for the mutation
harness the acceptance gate runs — the engine's own instructions are prompt
artifacts and need nothing installed. Both are launched with bare `python3`, use
the standard library only, and are tested on 3.9 through 3.13 in CI.

**With an API key, a cloud provider, or usage credits, set the prompt cache to one hour.** The
loop stops for you at its plan and merge gates. With any of those, Claude Code caches the main
conversation for five minutes by default, so a gate you answer later than that re-writes the
session's whole context into the cache when the loop resumes. Set `"promptCacheTtl": "1h"` in your
Claude Code settings (v2.1.242 or later; see
[prompt caching](https://code.claude.com/docs/en/prompt-caching)) to keep it for an hour. On Amazon
Bedrock or behind an LLM gateway, check that page first. A
one-hour cache write costs 2× base input against 1.25× for five minutes, so the setting costs more
on work that never idles past five minutes. Re-warms are not small: in one hand-checked run they
were 32% of the parent bill even with a one-hour cache
([appendix D](docs/research/cost-review-2026-10-26/D-handcheck-3f30a898.md)).
On a Claude subscription within your plan's usage, the main conversation already gets one hour.

### Upgrading the plugin

**`/plugin install` does not upgrade.** On a plugin that is already installed it reports
`already installed` and exits successfully without changing the version. A third-party
marketplace like this one also does not auto-update by default. Read *Upgrading with a live
ledger* below first, then run, from inside the consuming repo:

```
claude plugin marketplace update claude-code-loop
claude plugin update dev-loop@claude-code-loop --scope project
```

The first command refreshes the marketplace's copy of this repo. Without it, `update` has
no newer version to find. Pass the `--scope` you installed at; `project` is shown here. The
running session keeps the engine it already loaded, so start a new session (or run
`/reload-plugins`) before the next loop run.

**Confirm the version from the files, never from the command's output.** In
`~/.claude/plugins/installed_plugins.json`, the `dev-loop@claude-code-loop` entry for your
scope (at `project` or `local` scope, the one whose `projectPath` is your repo) must show the
new `version`, and
`~/.claude/plugins/cache/claude-code-loop/dev-loop/<version>/` must exist.
`claude plugin list` is not enough: it prints one entry per repo without saying which repo
each belongs to. If you cannot confirm the new version, you have not upgraded.

### Upgrading with a live ledger

**Finish the in-flight work before you upgrade the plugin. Do not upgrade
mid-iteration.** You are reading `.claude/loop/<run-slug>/queue.md` — the most
recently modified run directory, if there are several; a project that rebound
`LEDGER_ROOT` will have it elsewhere.

**Treat every row as in flight unless its `Status` is one of these four:**

- `queued` or `routed` — never entered the pipeline.
- `done` or `deferred` — finished, or terminal by decision.

Anything else is in flight until you show otherwise, **including a status you do not
recognize**. Do not reason from the status name: a row can rest outside the loop's
resume scan and still hold unfinished work. A `hold` is set at the *merge gate*, and
releasing it restores the row's previous status. A row `blocked` on a repeated gate
error can carry implemented work too — with or without an open PR, depending on which
gate failed.

Letting the loop finish such a row is the ordinary path and the one to prefer; it ends
at `done`, or at `deferred` if you close the row out instead. A row you *cannot*
finish — one waiting on a dependency, a split, a config repair, or an external event —
is discharged only by showing the loop has produced nothing for it: **no
`issue-<N>.plan.md` in the ledger directory, no branch, no uncommitted changes, and no
open pull request** (the `PR` cell keeps its number after a merge, so check the state
with `gh pr view <n>`, not the cell). **If you cannot tell, it is in flight** —
waiting costs you nothing, and this is the same default-deny posture the loop takes at
its own gates.

Finish those rows, or leave them and upgrade later. **Do not park one to get there:**
`parked` is assigned at triage, to work gated on an external event, and moving a
mid-pipeline row into a resting status puts it outside the resume scan — the opposite
of what you want across an upgrade.

The reason any of this matters is that the ledger is local, gitignored state that
**outlives the engine that wrote it**, and a release can change what a row means:

- **Upgrading mid-iteration** hands your in-flight row to a newer engine. If that
  release renumbered the pipeline, the row's status still resolves — it just brackets
  a different gate than it did when it was written, and nothing reports that.
- **Rolling back** hands a row to an older engine that may never have heard of its
  status — v0.2.0 added `in-acceptance`, which v0.0.1 does not define — and it also
  un-does the gating: v0.0.1 has no `plan-gate:` field (plans stop only on
  uncertainty), no gate-currency expiry, and runs the acceptance gate before review
  rather than last.

**As of v0.2.0,** the engine stops and asks you when it meets a row status it does
not recognize, rather than guessing a stage. v0.0.1 has no such check. Where it does
*not* save you: it cannot teach an older installed engine the same manners; it only
catches an *unrecognized* status, so one that still exists but now sits at a different
point in the pipeline looks valid to it; and it runs on the resume path, so a run
resting at `RUN PARKED` — which re-derives its work from `queue.md` without that scan
— is not separately covered.

**A ledger written before v0.2.0 has no `plan-gate:` field — and this is the upgrade
you are most likely to actually make.** v0.2.0 added that field, which sets whether
the plan gate stops on every issue or only on the engine's judgment conditions. A
`queue.md` written before it simply does not carry the line, and there is no second
Initialization to add one. The engine reads an absent field as `always` — it stops for
your approval on every issue — which is the safe direction, and **the engine now says
so once per run**, both in `progress.md` and in its own output, instead of inferring it
in silence.

Two consequences worth knowing before you upgrade. The inference does not consult
`mode:`, so a run sitting at `escalation-only` with graduated routes still stops on
every plan; if your header looks loosened and your plans keep stopping, this is why.
And **the loop will not add the field to an existing run for you** — Initialization
is the only place it ever writes this field, and that already happened for your run.
It is yours to set, and an engine that wrote one now would be freezing a posture you
never chose. The remedy is a one-line hand edit: add `_plan-gate: always_`
(or `_plan-gate: conditional_`) to `queue.md`'s header, beside `mode:`.

The finish-before-you-upgrade rule at the top of this section is a rule, not an
enforcement: nothing in the plugin can stop you upgrading mid-iteration.

## What the loop can do to your repo

**This section describes v0.4.0.** Every engine older than v0.3.0 gates less at nearly
every point below, and the lists here are illustrative, never the set — **assume nothing
in this section is live until you have re-installed.** An installed **v0.2.0** has no
design-question stop, no blocking/editorial split at code review, no guard-efficacy
floor, no delta-scoped re-check, no refusal to mutate a tree it cannot tell apart
from yours, and says nothing when it infers your plan-gate posture. An installed
**v0.0.1** is further back again: no `plan-gate:` field, no rule that a gate without
its own verdict never counts as passed, no gate-currency expiry, no offline test
tier, no mutation pass and no orphan-PR scan, and it runs the acceptance gate before
review rather than last. If you are already running the loop, re-install before
relying on any of this — *Upgrading the plugin* says how — and read "Upgrading with a
live ledger" first.

Worth reading before you install. This plugin drives a real development workflow on
your behalf: it creates branches, commits, pushes branches, opens pull requests, runs your project's
lint/type/test commands, merges, and deletes the merged branch. Here is the posture it
takes while doing that.

**The default is human-gated.** The loop runs in `mode: calibration` unless you change
it, and in that mode **the human approves every merge — it never auto-merges.**
Auto-merge exists only under the opt-in `escalation-only` mode, and even there it is
per-route, limited to routes you have explicitly *graduated*, and withheld for feature
or breaking changes, risky or irreversible changes, anything touching a security
surface, contested review findings, an unresolved blocking review finding,
unresolved acceptance-gate findings of
either kind, and an unresolved offline-tier finding.
Wherever eligibility is unclear the rule is **default-deny**: fall back to the human.

**By default you approve every plan before any code is written.** The plan gate is a separate
setting from the merge gate — a `plan-gate:` field in the run's ledger header — set to `always` for
a new run under `calibration`, meaning the loop writes a plan, shows it to you, and stops, on
**every** issue. Set the field to `conditional` and the loop stops when it hits ambiguous
acceptance criteria, risk, agent disagreement, an agent that punts, a value story that doesn't
hold, or genuine uncertainty. The two settings are deliberately independent: relaxing how much of
the planning you review never loosens what gets merged without you, and a ledger that doesn't
mention the field at all is read as `always`. Neither setting reaches the loop's other mid-pipeline
stops — such as the architect-rewrite stop below, the design-question stop after it, or a blocking
gate finding still there after one fresh re-check, which stop and ask you regardless of both.

**When its design reviewer rewrites the plan, you see the plan.** One mid-pipeline stop is
unconditional — no mode setting, no `plan-gate:` value, and no route graduation can loosen it: if the architect review
**materially changed** the approach, the loop stops and shows you what changed before writing any
code. A reviewer that decides is treated as a stronger reason to interrupt you than one that hedges,
because the plan you would have approved is no longer the plan being built. The comparison is made
against a copy of the approach frozen before the review ran, so the loop is reading a record rather
than its own memory of what it had intended.

**When a review finding raises a design question, you see it.** A second mid-pipeline stop is
unconditional in the same way. If code review returns a **blocking** finding that raises a design
question — whether the approach is right, whether a fix belongs in this change at all, whether
several findings share one root cause — the loop consults its design reviewer for a scope ruling
and **stops for you with that ruling attached**, under every mode, **on every route**, and at
whatever round the finding arose. The ruling can narrow the work; it can never conclude that no
decision of yours is required, and it never clears the finding or passes the gate on your behalf.
If the design-reviewer binding is missing or unset the loop **still stops** — it simply has no
ruling to attach — because the stop belongs to the finding, not to the reviewer. Editorial
findings raised before **the loop's single editorial sweep** — the one pass in which it applies
them without re-review — neither consult nor stop; one raised after that sweep escalates like any
finding, because there is no second sweep left for it to join.

**Code review asks whether your new guards would actually catch anything.** The loop picks review
angles from what the change puts at risk, but one is a floor rather than a choice: on any change
touching a path you have not declared inert, the first round's roster must include a lens that reads
that change's guards and asks whether they pin the **mechanism** that would break or merely an
**outcome** a broken implementation would still produce. Neither the route nor whether the change
appears to carry a guard narrows this — where it carries none, *that* is the lens's answer, and it
is recorded as such; whether that absence is itself a defect is the acceptance gate's question, not
this one. The cost is the same one the blocking/editorial split carries: until you declare some
paths inert, this fires on every change. It decides by reading — it never mutates your code — and
"cannot tell" counts as a finding, not a pass. **This is not the acceptance gate's mutation pass**,
which runs later and separately when it is due, and which actually breaks your code — in a copy, or,
only with your explicit approval, your own tree (below) — to see whether the suite notices. Neither
substitutes for the other, and neither one's result is written into the other's record. The lenses a
round ran are written to the journal, each with what it returned.

**Some review findings are applied without a second review, and the loop tells you how many.**
Code review sorts each finding into **blocking** or **editorial**, and only blocking ones send the
gate round back around. Editorial ones — wording that asserts no proposition about your repository
and changes no behavior — are applied in a single pass at the close of code review and are not
re-reviewed. What that pass writes still goes through acceptance and CI afterwards, and through
security review where the change's route makes that gate due. Four things
bound it, and they are deliberately strict: the **reviewer** assigns the class, never the loop; the
loop may only ever *raise* a finding to blocking, never lower one; a finding that something is
**false, stale, unresolvable, self-contradictory, or misdescribes what it sits on is blocking wherever
it lives** — including in
prose, which is a correctness finding when prose is what your project ships; and the pass may touch
**only** paths your config has positively marked inert — never source, never tests, never a path it
does not explicitly declare docs-or-research, and never a path it declares security-sensitive, which
in most projects leaves it reaching very little. The practical effect is that
this saves less than it may sound like it does, in the safe direction. **At the merge gate you are
told the count**, and it is recorded in the ledger either way — including when it is zero.

**The loop is held to what it asserts — and only one of the surfaces it writes gets read back.**
Every factual assertion it writes is a claim it has to stand behind: a claim that a test or guard
exists elsewhere must name it, and the named thing must exist and say what the claim says. That binds
every surface it writes — the diff, the ledger it keeps, and what it reports to you
among them. **Only the diff is read back, by code
review.** Nothing reads the ledger or a report to you and asks whether an assertion in it is *true*,
so treat both as resting on the loop's own discipline. (Other machinery does check the ledger's
**state** against your repository — a row's stage against live git, a missing record at the merge
gate — but that is state, not the truth of a sentence.) And even the diff is **reviewed, not
enforced**: the reviewer is an agent reading, which by the standard set out further down this section
is instruction the loop is bound by, not a sandbox. The ledger is where this matters most — it is
what the next run reads to pick up where the last one stopped, so a false line there is not a stale
document, it is something a later run treats as having happened. Stated the honest way round on
purpose: naming the one surface that is read, rather than listing the ones that are not, so a surface
nobody has thought of yet counts as unchecked instead of quietly counting as covered.

**A subagent's recommendation is not the same as its finding, and the loop is required to tell them
apart.** The agents it spawns return two kinds of thing: what they actually ran, read, or compared in
the material they were handed, and what they inferred about anything outside it. Those arrive at
identical authority on the page. So the loop asks its agents to mark which is which, and **anything
unmarked counts as unverified**: it either checks the claim itself before that reaches you or the
ledger, or hands it to you explicitly labeled unverified. What it may not do is relay it as fact.
**Coverage of this is partial today** — the rule is stated once and the individual prompts that carry
it are being brought into line one at a time — and it is built so the gap is harmless: a prompt that
never asks the question yields output the loop must treat as unverified. Incomplete coverage costs
you an extra check, never a false fact.

**A gate that did not run is never reported as one that passed.** For every gate the loop
runs — plan, architect, your build commands, the offline tier, code review, security, acceptance,
merge — it may record a pass only with that gate's own output as evidence: **no verdict means not
passed**. A binding you left blank in
`loop.config.md` is not a switch that turns the gate off; it makes the loop fall back to a built-in
equivalent where one exists, and otherwise stop and ask you. A gate that ran and *errored* never
falls back at all — the loop will not substitute a check of its own devising and call it clean; it
escalates. (A gate the route legitimately skips is journaled as *skipped*, which is also not a
pass.)

**A gate's pass covers the exact commit it ran on — and expires when that changes.** If anything
changes the pull request after a gate certified it — a fix the loop made at the acceptance gate, a
fix for CI that went red later, a change you asked for at the merge gate, or bringing the branch up
to date with your main branch —
the loop treats the gates that change re-armed as **not** having passed the new code. It re-runs
them or stops and asks you; it does not merge on the older result. This is the failure mode that
looks most like success, because every gate genuinely did pass — just not on the code you would be
merging.

**The same holds between your machine and the remote.** CI, a label-triggered review, and your own
merge approval all look at the pushed branch, which can differ from the loop's local copy. So from
the PR's first push on, the loop pushes every commit as soon as it makes it, and before it applies a
review label or merges it checks mechanically that the two agree
(`git rev-list --left-right --count @{u}...HEAD` after a fetch, which must report both counts as
`0`). If they disagree it stops and asks you, and it runs
nothing that moves either head to make the check pass.

**A pull request appears before any review has run — that is the order, not a slip.** The loop
implements, then **immediately commits and opens the PR**, and only then runs code review, security,
and the acceptance gate. So an open PR on your repo means "the loop has reached the review gates",
never "the loop is finished with this and wants your merge." Nothing merges without the merge gate
below, and CI is green before review starts.

Two consequences worth knowing. **The acceptance gate runs last**, immediately before the merge
gate, so the code it certifies is the code that merges. And **relative to v0.0.1 no gate was
removed** — the reorder changes only which one is last, and therefore what your repo looks like
when a stop happens: an acceptance-gate stop finds a PR already open with CI green, where under
v0.0.1 it found neither.

**The acceptance gate asks whether your tests would notice a regression.** It runs after code review
and security — the last gate before merge. It reports two kinds of
finding, kept separate and never added together: a criterion the change did not meet, and a **guard
that does not guard** — a test that would stay green even if the code it protects broke. The second
is protection you believe you have and do not, so the loop reports it as prominently as a bug. What
that means for your repo:

- **The mutation half only applies to `code`-route changes that alter behavior.** On `docs` and
  `research` the gate still checks your acceptance criteria independently; it runs no mutation
  pass.
- **If such a change adds no test at all, the loop tells you.** That is read straight off the diff
  and is the one case that needs nothing run against your code at all.
- **Either kind of finding blocks.** It is treated like an unmet acceptance criterion — fixed and
  re-verified — and a row still carrying one is never eligible for auto-merge.
- **To check the rest, the loop breaks your code on purpose — in a copy.** This is the most
  invasive thing the plugin does, so it is worth being exact about. Where the change adds or
  modifies a test, a mutating agent takes a **throwaway copy of your tree**, makes a small edit that
  ought to break something, runs your test suite against it, and reports any test that stayed green.
  Your working tree is not the tree that gets broken — unless you explicitly allow it, which is the
  next point.
- **If the copy cannot run your suite, the loop stops and asks you.** A bare copy has none of your
  installed dependencies, so this is the common case rather than an exotic one. Mutating your *real*
  working tree is the fallback and is **never taken on the loop's own judgment**. If you decline,
  the gate records that it could not run — it never records a clean result, because "we checked and
  found nothing" and "we could not check" must not look alike. On that path every file is restored
  from a snapshot taken before it was touched, **never from git**, which would throw away
  uncommitted work the mutation never touched.
- **The harness now refuses to break a tree it cannot tell apart from yours.** Previously it took
  the path it was handed on trust, so a copy that silently was not a copy — a `git worktree add`
  that failed, with the steps after it still running, in your real tree — got mutated and reported
  green. It is now told which tree is yours, and a pass whose target is that same tree (or contains
  it) stops before it resolves a target, takes a snapshot, or runs anything. That refusal is not a
  clean result and not a finding; it means nothing was checked. Only you can lift it, and lifting it
  is the fallback in the point above.
- **Every pass that mutates anything journals whether it gave the tree back**, and a pass that
  cannot restore reports that as its most severe outcome, ahead of any finding. A pass that ends up
  applying **no** mutation is an error rather than a quiet success — otherwise a check that found
  nothing and a check that did nothing would report the same clean result, which is the exact
  confidence this gate exists to refuse.

**An agent that writes to your tree gets a copy of it, not yours — so the loop may create and remove
git worktrees under your repository.** This is not limited to the mutation testing above: your
working tree holds your uncommitted work, so any subagent that needs to write gets its own
copy. Two things to expect. The copy is typically created **inside your repository** — where your
host puts it is the host's choice, not this plugin's — and while it is there it shows up as an
untracked directory in `git status`. It is not gitignored for you, and if you gitignore it yourself,
be aware the loop then has one fewer way to notice a stray one. And
**the loop is responsible for removing it**: your host only auto-cleans a copy the agent never wrote
to, which is never the case that matters, so removal is an instruction the loop follows rather than a
guarantee something enforces. An iteration that dies partway can leave one behind; `git worktree
list` will show it — and **the loop sweeps for one itself when it resumes**, before it touches the
tree. That sweep is described below, with the one path it does not cover.

**If the loop crashes partway through an iteration and then resumes, it does not quietly absorb
whatever it finds in your tree.** Two mechanisms cover your working tree, they are scoped
differently, and it is worth being exact about which is which.

**Whenever it resumes to work an issue, the loop looks for the marks of a mutation pass that did not
finish** — a stray worktree copy, or a retained snapshot directory. If it finds them it repairs
from its own pre-mutation snapshots, **never from git**, touching only the files it can attribute;
and if those snapshots are gone, it **stops and asks you** rather than improvising a repair. It
keys on those artifacts, not on the row's status, so a mislabeled row cannot carry a live mutation
past it. One path is not covered: a run resting at `RUN PARKED` re-derives its work without
entering the resume procedure, so it short-circuits ahead of this sweep.

**The loop also checks your open PRs whenever it resumes to work an issue**, not only
its own ledger rows —
because that ledger is gitignored and can be absent or stale while the work it described is still
open. **An open PR it can neither tie to one of its own ledger rows nor positively attribute to you
or another tool stops the run and asks you.** It does not adopt such a PR and does not act on it —
it reports it and waits, so a PR of yours sitting open can pause the loop until you say whose it is.
That is the deliberate direction: asking costs a question, and taking over your branch would change
your work.

**The second mechanism: when it resumes a row that was in review or acceptance, a change to your
code it cannot attribute is neither kept nor discarded — it stops and asks you.** That reverses the
older behavior, which kept anything that "looked like it matched the plan" — a bad default once the
loop's own acceptance gate started deliberately breaking code, because a mutation is built to look
like a small, sane edit and "it looks plausible" is precisely the test it is designed to pass. This
is the case most likely to involve your work, so the loop is not permitted to resolve it alone: not
keeping something and destroying it are different actions, and only you choose the second.
**Resuming an interrupted implementation is unchanged** — work in progress that belongs to the plan
is kept, and being half-finished is never on its own a reason to discard it. **The practical
protection is the ordinary one** — commit or stash work you care about before leaving an iteration
mid-flight, since a committed change is attributable by definition.

**If you bind a command for your offline test tier, the loop runs it and treats a failure as a bug.**
Where `HERMETIC_TEST_CMD` names one, any `code`-route change that adds or modifies a test runs that
tier once. A test that passes normally and fails there is reported as a bug rather than as flake —
it was passing for the wrong reason, quietly exercising a live resource instead of your fixture —
and the loop fixes it and re-runs the tier. If instead the **block itself** could not be applied (no
namespace, tool missing), nothing was learned about your tests, so the loop stops and hands you the
failure rather than rewriting a test to satisfy a block that never ran. You supply the blocking mechanism — the loop reads
an exit status and cannot see *how* you blocked, so the requirement that the block be socket-level
(a proxy still resolves DNS) is one you check once when writing the binding, not one the loop
enforces. `/init-loop` may draft the value for you and flag it for confirmation; confirming it is
yours to do. **No such tier? Say so explicitly** — bind `—` plus a reason and the gate records
itself as not applicable. Leaving the row off is not the same thing: on a change that would have run
the gate, the loop cannot tell "no tier" from "a tier I was not told about", so it stops and asks
you rather than assuming.

**A fix is never checked by whoever wrote it.** When the loop fixes what a gate found — the
acceptance gate above, or code review, on any route — a freshly spawned checker decides whether the
fix worked: not the thread that wrote it, and not the checker that raised the finding. Each such
gate gets **one** re-check; if it comes back dirty the loop stops and asks you, rather than
iterating on itself. At code review, "dirty" means a **blocking** finding — an editorial one raised
before that pass has run joins it, and neither re-arms the round nor stops for you. Once the pass has
run there is no second one, so a finding of either kind after that point stops and asks you.

**A re-check reads what no round has read yet, not your whole pull request again.** The first round
reads the entire change; a later one reads the range between the commit the previous round certified
and the current head, together with that round's findings — including the ones it *declined* — and
one narrowed question. Every commit on the branch is still read by whichever round's range contains
it, so no verdict is carried onto code no round ran on, and the round still certifies the head rather
than the range. Where the anchor is missing or cannot be trusted — a resumed iteration, a rebase or
force-push that moved the ground under it, an empty delta, or a repository that has not declared
which of its paths are security-sensitive — the round runs **full**. That is default-deny in the
same direction as the rest: anything unknown about the range costs a round's saving, never a round's
coverage.

**Hard limits the engine commits to:**

- **One PR at a time** — no stacked PRs.
- **Never force-push.**
- **Never bypass failing CI** — no admin-merge, never merge red.
- **Only `--delete-branch` the PR's own branch.**
- **Never blanket-stage** (`git add -A`/`git add .`) and never `git add` unrelated pre-existing
  working-tree changes. It stages explicit paths and reads back what it staged before each commit.
- **Never stage or commit while a subagent's isolated copy of your tree is live** — that window
  closes when the loop removes the copy, not when the agent finishes.
- **Never edit your user-global subagent definitions.**
- **Never edit its own `loop.config.md`** — a binding that looks wrong gets journaled and handed to
  you, so the loop can't quietly rewrite its own gates to match its reading of them.

**The ledger is local and never committed.** Working state (`queue.md`, `progress.md`,
`issue-<N>.plan.md`) is written under `.claude/loop/` in your repo, which `/init-loop`
adds to `.gitignore`. It lives on disk so a fresh invocation resumes correctly after a
`/clear`, and it stays out of your history.

**It runs your commands, not ours.** `LINT_CMD` / `TYPE_CMD` / `TEST_CMD` /
`HERMETIC_TEST_CMD` / `CI_STATUS_CMD` are whatever your own `loop.config.md` names — the
plugin ships no commands of its own and executes what that file tells it to. One of
those deserves singling out: **`HERMETIC_TEST_CMD` is the only binding whose value is
expected to restrict the environment** — it runs your declared offline test tier with
the network cut, so a plausible value wraps your test command in a sandbox or network
namespace (`unshare -rn …`, `firejail --net=none …`, a socket-blocking test plugin).
The loop supplies no blocking mechanism of its own, cannot tell whether the one you
named blocks at socket level, and will run whatever you wrote. Leave the binding as
`—` plus a reason and the gate is simply not run.

**How the limits are enforced.** Be clear-eyed about this: the human gates and the
append-only guard hook are *enforced backstops*, while the rest of the list above is
**instruction the orchestrating agent is bound by, not a sandbox**. If you want a hard
boundary rather than a diligent one, use Claude Code's own permission settings — the
skill deliberately runs with the full session toolset, because an orchestrator needs
git, `gh`, and subagents to do the job at all.

**The guard hook's trust model.** The bundled hook compiles `id_pattern` from
repo-local, committed config — the same trust level as a Makefile or a git hook, not
attacker-controlled input. Its scope is deliberately bounded: it protects **entry
existence against full-file `Write`s only**. It does not guard `Edit`, and it does not
cover `Bash` redirection (`cat > file`, `tee`, `sed -i`), which an agent with Bash could
still use to clobber a file. It is a durable guard against one specific data-loss mode,
not an any-tool guarantee.

## Onboard a repo — `/init-loop`

From inside the target repo, after installing the plugin:

```
/init-loop
```

The command reads the repo's own conventions (`CLAUDE.md`, `pyproject.toml` /
`package.json` / `Cargo.toml` / `Makefile`, the PR template, CI workflows, branch
naming) and:

- generates a pre-filled `${CLAUDE_PROJECT_DIR}/.claude/loop.config.md` — inferred
  values in place, clearly-marked `TODO(init-loop)` blanks for anything it can't
  infer (correctness is yours to confirm at first-run review). A leftover `TODO`
  on a gate binding is not inert: see the gating posture above. **One row is an
  exception worth checking by hand: `HERMETIC_TEST_CMD` fails *open*** — where it
  finds no declared offline tier it writes `—`, not a `TODO`, because a tier can
  be declared in prose the generator never reads, and `—` is read as a clean
  not-applicable and never asked about again;
- if it finds a decision-log-style append-only file, generates a
  `loop.append-guard.json` sidecar (the machine SSOT) and echoes the entry IDs it
  matched so you can confirm the guard is live;
- adds the ledger dir (`.claude/loop/`) to `.gitignore` and creates it;
- wires `enabledPlugins: { "dev-loop@claude-code-loop": true }` into
  `.claude/settings.json` (or prints the snippet to paste if the file isn't a
  plain JSON object).

It is **safe to re-run**: it never overwrites an existing `loop.config.md` without
asking, and the `.gitignore` / `settings.json` / ledger steps are additive.

## Per-project config

Each consuming repo keeps a `${CLAUDE_PROJECT_DIR}/.claude/loop.config.md` — the binding seam
described in *Design: three layers*. It binds the backlog and its priority order
(`BACKLOG_SOURCE`, `PRIORITY_LABELS`), the agents and review procedures that staff the gates
(`SCOPE_AGENT`, `DESIGN_AGENT`, `CODE_REVIEW`, `SECURITY_REVIEW`, `VERIFY`), your build and CI
commands (`LINT_CMD`/`TYPE_CMD`/`TEST_CMD`/`HERMETIC_TEST_CMD`, `CI_STATUS_CMD`), your git and
release conventions (`BRANCH_FMT`, `COMMIT_CONV`, `PR_TEMPLATE`, `MERGE_METHOD`, `RELEASE_SCHEME`),
and the project-specific logic the engine delegates — when to call the architect
(`ARCHITECT_TRIGGERS`) and how to route a change (`SOURCE_LAYOUT`). The `/init-loop` skeleton is the
full list.

A freshly generated config is short; a long-lived one grows, because a `—`-plus-reason value and a
project-specific routing rule both take room and both are read at runtime. What belongs in the file
is whatever the engine reads; rationale and history belong in your tracker. The generic engine is
never edited per project — only the config.

### Optional: `loop.append-guard.json` (append-only protection)

The bundled `guard_append_only.py` hook protects append-only logs (e.g. a
decision log) from full-file `Write`s that would silently drop existing entries.
It is **config-driven and inert until configured**: it reads
`${CLAUDE_PROJECT_DIR}/.claude/loop.append-guard.json`, a JSON array declaring
which files to protect and the regex that identifies each file's entry IDs (see
`hooks/loop.append-guard.example.json`). No sidecar → the hook is a silent no-op;
a malformed sidecar → it allows writes but warns on stderr (so a typo can't
silently disable protection).

## How the loop gets better

**It is developed by running it.** Since 2026-07-28 this repo works its own backlog with the
loop, alongside the other repos named in the status block. A run always executes the *installed*
plugin, never this working tree, so a run cannot edit the engine that is driving it — and a fix
reaches the loop only at the next release and re-install.

**Every finding from a real run lands in one index first.** Gaps the loop surfaces in itself — a
gate that could pass without running, a rule that drifted between two of its restatements, a cost
nobody measured — are recorded as comments on
[#1](https://github.com/frederick-douglas-pearce/claude-code-loop/issues/1), each with where it
surfaced, the gap, a *generic* fix and a severity. Moving a finding into a release is a deliberate
human decision, not a default. That rule exists because the loop's own adversarial gates generate
findings faster than a milestone can absorb them: a release milestone is frozen once scoped, and
work that waits on *evidence* rather than effort goes to the
[`deferred-corpus`](https://github.com/frederick-douglas-pearce/claude-code-loop/milestone/3)
milestone with written decision criteria instead of shipping on a hunch. Wording headed for the
`/init-loop` skeleton is held to a higher bar than the same wording in the engine, because the
engine is replaced at every release while a generated config is never touched again.

**The suite pins the couplings, and review owns the meaning.** The stdlib test suite checks the
mechanical couplings between files — that every parameter the engine reads is in the onboarding
skeleton, that the pipeline's step order agrees wherever it is restated, that the payload holds
only its declared inventory — and its guards are checked by mutation to show they can actually
fail. Whether the instructions say the *right* thing is left to the loop's own review gates and
to running it on real backlogs; see *Development*.

### Measuring what a run costs, and what changes it

[`docs/research/`](docs/research/) is a research notebook on why an iteration costs what it does
and what would make it cheaper without making it worse. It reads Claude Code session transcripts
and the ledgers' `- Budget:` lines with standard-library scripts, prices them against a shared
[cost specification](https://github.com/frederick-douglas-pearce/claude-code-sessions/blob/main/reference/cost-model.md),
and records each finding with its method, its numbers and what would falsify it. The headline
readings, all taken on v0.2.0:

- **A run's cost is driven by its turn count.** Context per turn is bounded by the compaction
  ceiling above and the starting footprint below, so it varies little; the number of turns has no
  ceiling. A lever that saves turns has far more room to move the bill than one that only shrinks
  context.
- **Extra review rounds are mostly fix-induced.** The defects a later round catches are, more often
  than not, ones the previous round's fixes introduced.
- **One extra gate round costs about what loading the whole engine costs.**
- **The orchestrator issued about one tool call per turn**, so independent reads were paying for a
  full turn each.

The levers those readings rank have each been taken since. v0.3.0 took the two ranked highest.
It went after gate rounds: measured round by round on two repos, the review gate consumed most of a
run's tokens and its last rounds routinely found nothing that changed shipped behavior, so
editorial findings stopped costing a round and later rounds read only the delta. And it told the
orchestrator to request a file's remaining pages in one turn
([#135](https://github.com/frederick-douglas-pearce/claude-code-loop/issues/135)). v0.3.1 then
sharded the engine — the lever the notebook ranks lowest of the three — as a single-epic release,
so that its small expected effect could be measured without anything else moving.

**The analysis is set up as causal inference, not trend-reading**, because the obvious regression
misleads here. [`cost-model-design.md`](docs/research/cost-model-design.md) models the outcome as a
turn count, with cost read off it. It draws the causal graph: the difficulty of an issue is an
unmeasured confounder that drives review rounds, turns and defects alike, and review rounds sit on
the causal path from a config choice to its cost. So a config lever's effect is estimated as a
*total* effect, never adjusted for rounds — conditioning on a mediator that is also a collider can
manufacture an effect that is not there. The note then ranks the identification strategies
available, and the favorable fact behind all of them is that the loop's config is set by a human
before each run, so the assignment mechanism is ours:

- **Repeated runs of a single reference issue**, varying one lever at a time — the primary plan.
  It holds issue difficulty fixed by construction and is the only design that yields
  within-config variance. The
  [cost-experiments epic](https://github.com/frederick-douglas-pearce/claude-code-loop/issues/211)
  starts with the replicate harness it needs.
- **Randomized config assignment** for future runs, so the propensity is known rather than assumed.
- **Difference-in-differences on the staggered engine rollout** — free, because the data is
  already on disk. Releases reach consuming repos on different dates, and two of them are
  deliberately held on v0.2.0 as an untreated control.

**The run environment is treated as a treatment too.** When the default model and effort level
changed partway through the v0.3.0 baseline window, every instrument was stratified by
`(model, effort)` so that the change could not be read as an engine effect
([#207](https://github.com/frederick-douglas-pearce/claude-code-loop/issues/207)). The sharding
release's predictions were registered before any after-side data existed, and a before/after that
does not name the engine version on both sides is treated as uninterpretable.

**The notebook is candid about its own failures**, and that is part of why its numbers can be
checked. It lists six transcript-detection bugs, each of which produced a silent, plausible,
wrong result, and the two defenses that caught them: hand-checking a sample of matches, and
checking the output against what the system can physically do. Figures that predate the current
cost arithmetic carry a pointer to their re-run, and each lever in the ranking carries its
confidence — correlational at best — beside it.

## Roadmap

**The live plan is the [milestone list](https://github.com/frederick-douglas-pearce/claude-code-loop/milestones)**,
and each milestone's description says what it is for and whether it is frozen. This section
describes direction; it deliberately does not restate what is in each milestone.

- **Finish measuring v0.3.1.** The sharding milestone stays open until
  [#133](https://github.com/frederick-douglas-pearce/claude-code-loop/issues/133) has enough
  completed v0.3.1 sessions in each treated repo to judge its pre-registered predictions.
- **Cost, turns first.** The cost review
  ([#271](https://github.com/frederick-douglas-pearce/claude-code-loop/issues/271)) found the bill
  is driven by turns, and the largest lever on turns is the review round that exists because the
  previous round's fix introduced a new defect. v0.4.0 shipped the review's safe deletions
  unmeasured. Next come more deletions and a paired benchmark, and then the levers that act on rounds.
- **Cost attribution per iteration.** Recording session IDs in the journal
  ([#234](https://github.com/frederick-douglas-pearce/claude-code-loop/issues/234)) would let an
  iteration's token usage be tied to its PR.
- **Cost experiments** ([#211](https://github.com/frederick-douglas-pearce/claude-code-loop/issues/211),
  designed in [#144](https://github.com/frederick-douglas-pearce/claude-code-loop/issues/144)): an
  isolated replicate harness, then replicated runs that estimate within-config variance and the
  model effect, then an engine × model comparison.
- **Briefs for the people the merge serves.**
  [`pr-brief`](https://github.com/frederick-douglas-pearce/claude-code-loop/issues/231), incubating
  in `incubator/` outside the payload, writes a plain-language brief of one pull request for
  executives and product managers — what it was worth, what it cost, an acceptance walkthrough
  against the spec, and where delivery differs from it — and fact-checks the brief with an
  independent verifier before you see it. It graduates into the plugin only after use across at
  least two consuming repos
  ([#229](https://github.com/frederick-douglas-pearce/claude-code-loop/issues/229)). A planned
  [`epic-brief`](https://github.com/frederick-douglas-pearce/claude-code-loop/issues/245) builds
  on it, aggregating those briefs into one page per epic.
- **Decisions waiting on evidence.** `deferred-corpus` holds design questions that the loop's own
  data has to settle first — for example, whether to formalize review tiers by route and risk
  surface ([#38](https://github.com/frederick-douglas-pearce/claude-code-loop/issues/38)), whether
  to mint a dedicated test-efficacy agent
  ([#37](https://github.com/frederick-douglas-pearce/claude-code-loop/issues/37)), and whether the
  engine gets a semantic eval harness
  ([#69](https://github.com/frederick-douglas-pearce/claude-code-loop/issues/69)).
- **Toward stable.** The status block says why this is not yet called stable, and porting to
  repos unlike the ones above is what surfaces the rough edges — which is where you come in. If you
  try it, findings are welcome in the
  [tracker](https://github.com/frederick-douglas-pearce/claude-code-loop/issues). A slimmer
  consumer-facing README is also deferred (see *Layout*).

## Layout

**`plugins/dev-loop/` is the plugin payload** — the directory `marketplace.json` points
`source` at, and the only thing copied into a consumer's plugin cache. Everything **outside**
it is maintainer-side and does not ship.

```
claude-code-loop/
├── .claude-plugin/
│   └── marketplace.json     # the marketplace index; repo root; does NOT ship
├── plugins/
│   ├── CLAUDE.md            # engine-editing notes; OUTSIDE the payload, so does NOT ship
│   └── dev-loop/            # <- THE PAYLOAD. `source` points here; this is all that ships
│       ├── .claude-plugin/
│       │   └── plugin.json      # the plugin manifest (each .claude-plugin/ holds ONLY manifests)
│       ├── skills/
│       │   └── dev-loop/
│       │       ├── SKILL.md         # thin orchestrator entry point (reads the one below)
│       │       ├── loop-engine.md   # the engine's core: pipeline, semantics, and the phase index
│       │       ├── phases/
│       │       │   ├── accepting.md # phase unit: step 10 + the AC-verifier
│       │       │   └── reviewing.md # phase unit: step 8's code-review procedure
│       │       └── reference/
│       │           ├── initialization.md     # appendix unit: Initialization + the queue.md skeleton
│       │           ├── plan-gate-inferred.md # appendix unit: the run-level posture inference record
│       │           ├── plan-template.md      # appendix unit: the issue-<N>.plan.md template + lifecycle
│       │           └── record-templates.md   # appendix unit: the progress.md open and close records
│       ├── hooks/
│       │   ├── hooks.json           # wires the PreToolUse guard via ${CLAUDE_PLUGIN_ROOT}
│       │   ├── guard_append_only.py # append-only guard (config-driven; stdlib only)
│       │   └── loop.append-guard.example.json  # sample per-project protection registry
│       ├── commands/
│       │   └── init-loop.md         # /init-loop onboarding scaffolder
│       ├── tools/
│       │   └── mutate_verify.py     # mutation harness the acceptance gate runs by path
│       ├── README.md            # a copy of the front-door README -- see below
│       └── LICENSE              # pristine MIT, unlike the root -- see below
├── tests/                   # stdlib unittest suite + its own CLAUDE.md; does NOT ship
├── tooling/                 # maintainer-side root executables; does NOT ship
├── incubator/               # skills in development, not yet in the payload; does NOT ship
├── tools/mutation-specs/    # hand-run harness self-check; does NOT ship
├── docs/research/           # the research notebook; does NOT ship
├── posts/                   # blog series sources + frontmatter contract; does NOT ship
├── .github/workflows/       # CI and repo automation; does NOT ship
├── .claude/                 # this repo's dogfood config, decision log + PRDs; does NOT ship
├── CLAUDE.md                # maintainer instructions for THIS repo; does NOT ship
├── package.json             # Prettier pin for the posts/ gate, maintainer-side; does NOT ship
├── package-lock.json        # its lockfile, what `npm ci` installs in CI; does NOT ship
├── .prettierrc              # the site's formatter options, mirrored; does NOT ship
├── .prettierignore          # ignore-everything-then-unignore posts/; does NOT ship
├── .gitignore               # does NOT ship
├── LICENSE                  # MIT, scoped to exclude the posts/ tree; does NOT ship
├── LICENSE-prose.md         # CC BY 4.0, covering the posts/ tree; does NOT ship
├── AI-DISCLOSURE.md         # how this repo's content was produced; does NOT ship
└── README.md                # this file: the GitHub front door; a copy ships in the payload
```

**Why the tree is shaped this way.** There is no payload-exclusion mechanism for a Claude
Code plugin — no `files`/`exclude`/`ignore` manifest field and no `.pluginignore`. The only
available filter is **positional**: a file is excluded by sitting outside the source
directory. That is why the runtime tree moved rather than the rest being filtered out.

**`.gitignore` is not a payload-selection mechanism** — it cannot keep a **tracked** file out
of the payload, which is the whole reason this restructure was needed. It does keep
*untracked* droppings out, because the cache is copied from a clone of this repo and an
ignored file was never in the clone. Those are two different stages, and collapsing them into
"`.gitignore` has no effect on the cache" is wrong in a way that matters: it is what
`test_bytecode_droppings_cannot_be_committed` relies on.

**A file ships iff a consumer needs it in the cache** — and deliberately with no list of the
qualifying kinds: **if you cannot establish that a consumer needs it in the cache, it does not
ship.** `PayloadContentsTests` pins the payload against a **declared inventory** and fails on any
path outside it; it does not itself decide what belongs there.

**The payload README is a copy of this file, and that is an explicit interim decision.** The
root README is the GitHub front door and the marketplace homepage target;
`plugins/dev-loop/README.md` is a byte-identical copy of it, kept in step by
`test_payload_readme_is_identical_to_the_front_door`. **Neither file silently became both** —
the duplication is stated here and mechanically pinned.

A slimmer consumer-facing README is the better end state, and it is deliberately **deferred**
rather than taken here. Shipping a short README now would
strand two things the engine cross-references inside a consumer's cache — *How the limits are
enforced* and *Upgrading with a live ledger*, both of which live only in this file — and
repairing those references means editing `loop-engine.md`, whose bytes the sharding release
measures. Copying this file keeps every such reference resolving with no engine edit at all.

**The payload carries its own `LICENSE`, and it is not a copy of the root one.** Two
separate reasons, and both hold. It is a **file rather than a symlink** because a symlink whose
target sits outside the plugin directory is *silently skipped* when the plugin is copied into
the cache — not rejected — so a symlinked license would simply be absent, with nothing saying
so. And it is **pristine MIT where the root one is scoped**: the root `LICENSE` excludes the
top-level `posts/` directory and everything under it, which is licensed CC BY 4.0 instead, but the
payload is `plugins/dev-loop/`, which is no part of that tree — so the payload's file has nothing to
scope, and nothing a consumer receives is CC-BY-licensed. **The two files diverge deliberately and
are not out of sync.**

## Development

```bash
python3 -m unittest discover -s tests
```

No install step, no virtualenv, no dependencies — the suite is **stdlib `unittest`
only**, because the guard hook runs under bare `python3` in a consumer's
environment and the tests have to run wherever it does. CI runs that command on
Python 3.9–3.13 for every pull request.

The modules covering the plugin itself, each aimed at a deliberately different thing:

- `test_guard_append_only.py` — behavior of the guard hook: drop detection, the
  suffix matcher, the config loader, and each direction of the fail posture.
- `test_mutate_verify.py` — behavior of `plugins/dev-loop/tools/mutate_verify.py`, the mutation
  harness the acceptance gate runs: what it does to a tree, and what it refuses
  to do. It is the only executable evidence behind a gate that edits source code.
- `test_repo_consistency.py` — mechanical checks on the shipped artifacts: that
  the example sidecar still loads through the real loader, that the
  `dev-loop@claude-code-loop` identifier still matches the manifests it is
  composed from, that every `CAPS` parameter the engine reads is offered by
  the `/init-loop` skeleton, that the pipeline's step order still agrees
  everywhere it is restated, and that the payload under `plugins/dev-loop/`
  holds only its declared inventory with `marketplace.json`'s `source` still
  pointing at it.

The remaining modules cover maintainer-side tooling that never ships — the frontmatter contract
for the blog posts in `posts/`, and the publishing scripts under `tooling/` — and
[`tests/CLAUDE.md`](tests/CLAUDE.md) describes every module, along with the ceiling on what any
test over prose can establish. The cost-research scripts in `docs/research/` carry their own tests,
run separately as that directory's README shows.

What the suite does **not** test is whether the prompt artifacts say the *right*
thing. The engine is a long document of instructions an agent executes at
runtime, and its correctness properties — precision of wording, internal
consistency, fail-safe posture — are validated by review and by running the loop
on real backlogs. `test_repo_consistency.py` guards couplings between files, not
semantics.

## License

**Two licenses, cutting at one directory.** The top-level `posts/` directory and everything under it
is licensed **CC BY 4.0** — see [LICENSE-prose.md](LICENSE-prose.md). Everything else is **MIT** ©
2026 Frederick Douglas Pearce — see [LICENSE](LICENSE), whose scope clause defines *"the Software"*
to exclude the top-level `posts/` directory and everything under it. The two grants meet at that
boundary, so no file in this repository is left unassigned and none is covered by both.

The payload carries its own MIT license file at `plugins/dev-loop/LICENSE`, governing
`plugins/dev-loop/` and nothing outside it — a license outside that directory would not travel into
a consumer's plugin cache. That file is pristine MIT with no scope clause: `plugins/dev-loop/` is no
part of the top-level `posts/` tree, so **nothing a consumer receives is CC-BY-licensed.**

GitHub's license detection matches the root `LICENSE` against known license texts and does not
recognize a scoped one, so a repository whose `LICENSE` carries a scope clause shows **Other** in
the sidebar rather than the license it actually grants. That is the cost of making the boundary
above bind, and it was accepted deliberately.

[AI-DISCLOSURE.md](AI-DISCLOSURE.md) states how this repository's content was produced — the loop
drafts and gates its own development, the `marketer` agent drafts the posts, and a human owns every
published claim.
