# Unit `plan-template` — the `issue-<N>.plan.md` template and the ledger lifecycle

This file is the **`plan-template` unit** of the dev-loop engine, not a standalone document. Core
(`loop-engine.md`) lists it in its phase index and has you read it at step 3, before setting the row
to `planning`. Read it in full, under core's load protocol. What holds when it is not loaded is
stated in core (*What holds without each unit loaded*), never here: its absence never makes a gate
pass and never lets one be skipped.

### `issue-<N>.plan.md` — per-issue plan (architect-reviewed, human-approved)
```markdown
# Plan: #<N> — <title>
**Route:** <code|research|docs>  **Branch:** <BRANCH_FMT>

## Value framing (route-scaled — see step 3)
<feat: backbone activity + 1–3 `as a … I want … so that …`, each with who-benefits +
prevalence + a falsifier ("what observation would show this is misdirected?"); discharge cheap
falsifiers here (run the grep/corpus pass) rather than only stating them.
fix: who hits it / how often / what breaks. docs: who reads it / what it unblocks.
research: question + downstream decision + what a null result means.
chore:/refactor: what internal tooling/quality it serves + why now.
Add a source-fidelity note if the rationale leans on any externally-cited source.>

## Acceptance criteria (verbatim from issue)
- [ ] ...

## Approach
<steps, files to touch, tests to add>

## Approach as reviewed (frozen before the design gate) — write-once, do not edit
<Verbatim copy of `## Approach` taken BEFORE the architect pass was consulted — at step 4, or at
step 5 where that step first consults it. Omit this section ONLY if no plan-informing architect pass
ran at all (step 4 skipping it is not enough; step 8's scope ruling is not one). It is the pre-image
step 5 diffs the live `## Approach` against to decide whether the architect materially changed the
plan. Never regenerated and never back-dated — see Resume.>

## Architect triggers hit
<which ARCHITECT_TRIGGERS fired, or "none">

## Risks / open questions for human
<empty if none>
```

### Lifecycle & commit policy
- **Init:** orchestrator creates the dir + `queue.md` from `BACKLOG_SOURCE`.
- **Per iteration:** update one `queue.md` row through its statuses; append the **open record** at
  step 7 and the **close record** at step 12, each owed only by an iteration that reaches that step,
  plus a block wherever a gate resolves (Ledger format → `progress.md`, in core); write/update `issue-<N>.plan.md`.
- **Commit policy — gitignore the ledger** (`LEDGER_ROOT/` is added to `.gitignore`). It is
  local working state: it survives `/clear`/compaction on disk, but is **never committed**.

*End of the `plan-template` unit.*
