# Unit `reference` — Initialization and the `queue.md` skeleton

This file is the **`reference` unit** of the dev-loop engine, not a standalone document. Core
(`loop-engine.md`) lists it in its phase index and has you read it at step 0, when there is no
active run and you are about to initialize one. Read it in full, under core's load protocol,
**before creating anything under `LEDGER_ROOT`**. What holds when it is not loaded is stated in core
(*What holds without each unit loaded*), never here: its absence never makes a gate pass and never
lets one be skipped.

## Initialization procedure (new run)
1. Derive `<run-slug>` from `BACKLOG_SOURCE`: milestone → the milestone name; label → the label
   (slugified); `TODO.md` → its basename. `mkdir -p LEDGER_ROOT/<run-slug>`.
2. Enumerate `BACKLOG_SOURCE` (e.g. `gh issue list --milestone <run> --state open --json
   number,title,labels` for a milestone; `--label <name>` for a label/epic source).
3. For each issue: determine route (Router) and dependencies (parse "Depends on"/"blocked by"
   refs in the body; respect epic ordering notes). An epic *tracker* issue is not a work row —
   carry it terminal (`deferred`) if the source enumerates it (the loop does not close epics).
4. Topologically order by dependency, then by `PRIORITY_LABELS` (tiebreak issue-number asc).
   Write `queue.md` with header `mode: calibration` **unless the human has already graduated routes
   for this project** — check the decision log and, if so, init `mode: escalation-only` + the
   graduated `graduated-routes:` instead, so a prior graduation persists across runs rather than
   silently resetting to calibration. Step 11 reads `mode`/`graduated-routes` to gate **the merge
   gate**, per route; it never affects the plan gate. **Set `plan-gate:` on the same branch you just
   took** — `calibration` ⇒ `plan-gate: always`; the prior-graduation branch ⇒
   `plan-gate: conditional` — so the plan gate's posture starts consistent with the trust level the
   project has actually established. Write it explicitly even though an absent field would read as
   `always` (step 5): the human tunes what they can see, and a field that only exists once someone
   needs to loosen it is one they will not know to look for. After init the two are independent —
   a later `mode:` change never rewrites `plan-gate:`. Also set `iteration-cap: none` and
   `subagent-cap: none` (the human sets them when loosening).
5. Append an "init" block to `progress.md`. (Ledger is gitignored — not committed.)

### The `queue.md` skeleton

```markdown
# Loop run: <run-slug>
_mode: calibration_
_graduated-routes: none_
_plan-gate: always_         # always | conditional; absent or unrecognized = always
_iteration-cap: none_       # max issues per run; none = uncapped
_subagent-cap: none_        # max subagent runs per iteration; none = uncapped
_Last updated: <ISO8601 by orchestrator>_

| # | Issue | Route | Status | Depends on | PR | Notes |
|---|-------|-------|--------|-----------|----|----|
| 1 | #<a> precondition fix | code | done | — | #<pr> | precondition |
| 2 | #<b> probe | research | queued | — | — | first in epic #<epic> |
| 3 | #<c> follow-on | research | blocked | #<b> | — | needs #<b> findings |
| 4 | #<d> stub | stub-defer | deferred | — | — | not implementation-ready |
| 5 | #<e> post-release re-measure | code | parked | — | — | awaiting: <external condition> |
```

*End of the `reference` unit.*
