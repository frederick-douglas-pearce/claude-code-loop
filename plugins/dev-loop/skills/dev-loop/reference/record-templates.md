# Unit `record-templates` — the `progress.md` open and close records

This file is the **`record-templates` unit** of the dev-loop engine, not a standalone document. Core
(`loop-engine.md`) lists it in its phase index and has you read it at step 7, before staging, and at
step 12. Read it in full, under core's load protocol. What holds when it is not loaded is stated in
core (*What holds without each unit loaded*), never here: its absence never makes a gate pass and
never lets one be skipped.

**The open record** — written at step 7:

```markdown
## <ISO8601> — #<N> (<route>) — iteration open
- Issue: #<N> — <title>
- Route: <code|research|docs>
- Branch: <branch name>
- PR: #<pr>
- Status: in-pr
```

Where the work **closes no issue** — a follow-up patching what a prior PR shipped, say — such work is
often not in `queue.md` at all, so do not assume a row key exists: head the record with the PR
(`## <ISO8601> — PR #<pr> (<route>) — iteration open`) and write `- Issue: none (Refs #<M>)`, adding
the row key only if there is one. The branch and PR number are the identity the orphan scan reports
by; omitting the record because there is no issue number is what would break it.

**The close record** — written at step 12:

```markdown
## <ISO8601> — #<N> (research) — iteration complete
- Selected: #<N> (highest-priority unblocked).
- Route: research (probe; no test-coverage gate).
- Plan: issue-<N>.plan.md written.
- Architect: skipped (research scaffolding, no shared-interface impact).
- Plan-gate: n/a: architect skipped (research scaffolding).
- Human gate: plan approved by the human (plan-gate: always).
- Implemented: <path>; recorded findings in <path>.
- Hermetic: n/a: research route.
- PR: #<pr> (chore scope). CI: green.
- Code-review: round 1 (main...9f3c1ab) — 0 findings. Security: n/a: no deps added.
- Editorial: 0 — no EDITORIAL finding returned.
- Restore: n/a: no mutation applied.
- AC-verify: Class A 3/3 acceptance criteria met. Class B: mutation pass not due (research route).
- Budget: subagent-runs=3 · gate-rounds=architect=0,code-review=1(correctness,robustness),ac-verify=1 · ac-findings=0 · mutation-survivors=n/a: research route · wall-clock=18m · tokens=deferred
- Merged: squash #<pr>. Issue #<N> closed.
- Next: #<M> now unblocked.
```

*End of the `record-templates` unit.*
