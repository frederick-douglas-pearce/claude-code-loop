# Loop engine — generic operating procedure & semantics

This is the **project-agnostic engine** for the supervised dev loop: control flow, gate /
convergence / resume semantics, the ledger format, the router procedure shape, and the budget
machinery. It contains **no project-specific values**.

Every name in `CAPS` (`BACKLOG_SOURCE`, `LEDGER_ROOT`, `SCOPE_AGENT`, `DESIGN_AGENT`,
`CODE_REVIEW`, `PRIORITY_LABELS`, `ARCHITECT_TRIGGERS`, `SOURCE_LAYOUT`, `LINT_CMD`/`TYPE_CMD`/
`TEST_CMD`, `BRANCH_FMT`, `COMMIT_CONV`, `MERGE_METHOD`, `RELEASE_SCHEME`, …) is bound in the
per-project **`loop.config.md`**. **Read that config first** — this engine depends on the
config's parameter *vocabulary*, never its layout.

Cross-references within this doc are by **named section** (e.g. "the Resume procedure below"),
and pipeline steps are numbered 0–12. The live skill (`SKILL.md`) is the thin entry point that
loads this engine plus the config; the full procedure lives here, once.

---

## The pipeline (ONE issue per invocation)

You are the orchestrator of a supervised dev loop. Each invocation handles exactly ONE issue
end-to-end, journals, and stops. State lives in the ledger, not your context — so a fresh
invocation resumes correctly.

### 0. Load or initialize state
1. Identify the active run (most recent `LEDGER_ROOT/<run>/`). If none exists, ask the user which
   `BACKLOG_SOURCE` (milestone/label/`TODO.md`) to run, then INITIALIZE per the Initialization
   procedure below. Otherwise scan the FULL `progress.md` for the **most recent** run-state
   sentinel — the last of `{RUN COMPLETE, RUN PARKED, RUN RESUMED}` by append order (the log is
   append-only, so a superseded sentinel still sits above; last one wins) — and act only on it:
   - `RUN COMPLETE` (see Convergence) → report done and STOP; do not re-scan (the run is terminal).
   - `RUN PARKED — awaiting <condition>` (see Convergence) — the run finished all *workable* rows
     and rests on an external event:
     - **If this invocation explicitly releases the park** (the human names a met condition — "the
       cut is out, resume"): perform the concrete un-park mutation, **scoped to the released
       condition** — flip back to `routed` (retain Route, clear the `awaiting:` marker) ONLY the
       `parked` rows whose `awaiting:` condition the human named; leave rows still gated on *other*
       conditions `parked` with their markers intact (if which rows a release covers is ambiguous,
       ask — do NOT flip all, that would prematurely release a still-unmet gate). Append a `RUN
       RESUMED` sentinel (now last-wins) and continue to step 2; any rows left parked simply
       re-append `RUN PARKED` at the next step-1 pass (last-wins over `RUN RESUMED`), which the
       existing machinery handles. A bare re-fire (e.g. the `/loop` driver) does NOT release the
       park.
     - **Otherwise take the cheap parked path (no full re-scan):** read `queue.md` + the FULL
       `progress.md`, run the step-1 roster reconciliation (the one scan a parked run still owes —
       this is how `BACKLOG_SOURCE` drift is still caught), then **re-derive selectability from
       `queue.md` alone** (no git/PR reconcile). If that produced selectable work (a joiner the
       human pulled in, or an in-run dep that has since cleared) fall through to step 1 **at
       selection** (the reconciliation just ran — do not repeat it); otherwise STOP and report
       "parked — awaiting <condition>" **without** running the step-3 resume or any per-row live
       reconcile — skipping resume is provably safe here (a valid PARKED state has every non-`parked`
       row terminal, so no interrupted pipeline row can coexist).
   - `RUN RESUMED` or no sentinel → continue to step 2 (a released or never-parked run runs
     normally).
2. Read `queue.md` (note its `mode:` / `graduated-routes:` header and any `hold`/`parked` rows) and the tail of `progress.md`.
3. **Resume before selecting (see the Resume procedure below).** If any row sits in an *interrupted*
   status — non-terminal and NOT `queued`/`routed`/`hold`/`parked` (i.e. `planning`/`plan-approved`/
   `implementing`/`in-pr`/`in-review`) — a prior iteration was cut off. Reconcile it against
   LIVE git/PR state as the source of truth — branch exists? PR open? already merged? CI
   status? — plus the working tree (status is only a coarse anchor; git wins on conflict),
   then re-enter the pipeline at the matching stage and FINISH that issue BEFORE selecting a
   new one. This is what makes "one PR at a time" hold across `/clear`/compaction. A `hold` or
   `parked` row is NOT an interruption: skip it here — a `hold` stays held until the human
   releases the merge, a `parked` row stays gated until its external condition is released (step
   1); neither blocks working other issues.

### 1. Select
**Budget cap (iteration start, retrospective).** Read `iteration-cap:` / `subagent-cap:` from the
`queue.md` header (both default `none` = uncapped). Cumulative iterations = the count of **distinct
issues at a terminal status** (`done`/`deferred`/`blocked`) in `queue.md` — never count
`progress.md` blocks (a `/clear`-resume re-enters an iteration and double-counts). Breach = that
count ≥ `iteration-cap`, OR the **prior** iteration's journaled `- Budget:` line (step 12) shows
`subagent-runs` ≥ `subagent-cap`. On breach: **manual re-invoke is advisory** — journal + surface
it and proceed (the human who invoked is the budget authority); **the driver halts.** Inert while
both caps are `none`.

**Roster reconciliation (iteration start).** The queue built at init (see Initialization) is the
authoritative work set — the *curated subset*; `BACKLOG_SOURCE` membership may drift afterward, and
drift is **surfaced to the human once, never auto-applied** — neither auto-added on join nor
auto-ejected on leave. Compute the delta between the live `BACKLOG_SOURCE` roster (one enumeration,
e.g. `gh issue list --milestone <run> --state open` for a milestone source) and `queue.md`,
deduping against prior curation records via a FULL-file scan of `progress.md` (not the tail) for
exact `- surfaced-join:` / `- surfaced-leave:` lines:
- **Joined** (in the `BACKLOG_SOURCE` roster, no `queue.md` row, not already surfaced) → surface
  once: "#N joined <run> after init — pull in, or leave out? (never auto-added)." Record `-
  surfaced-join: #N` in a `## <ISO8601> — curation` block. Only on the human's "pull in" add a
  `queued` row; a bare surface never adds one.
- **Left** (a non-terminal `queue.md` row whose issue is no longer in the roster, not already
  recorded) → surface once: "#N left <run> — eject, or keep? (never auto-ejected)." Record
  `- surfaced-leave: #N`. On "keep", write the decision to the row's Notes (`kept: out-of-<run>
  roster (curation)`) so it self-dedups; on "eject", an in-flight leaver (`planning`..`in-review`,
  open PR) is **finish-then-reconsider**, not a bare eject (only a pre-pipeline row ejects cleanly —
  close/clean its PR+branch first), then set the row `deferred` with a curation Notes reason.
This paragraph is the sub-unit the step-0.1 parked path invokes standalone.

A row is **selectable** if its status is `queued`/`routed`, OR it is `blocked` on an unmet
dependency that has SINCE cleared (all its `Depends on` issues are now `done` — re-route it via
step 2; this does NOT apply to a `blocked: too-large` park, which waits on a split, nor to a
`gate-error:` block, which waits on a config repair). A `parked` row
is never selectable here — it is released only by explicit human un-park (step 0.1). Among
selectable rows pick by `PRIORITY_LABELS` order, tiebreak issue-number ascending. If none are
selectable, determine the resting state from the remaining non-terminal rows (test in this order):
- Any `hold` row present → report "<n> held — awaiting human merge-release" and STOP **without** a
  sentinel (a held row needs the human now; the run is neither complete nor cleanly parked).
- Else if ≥1 `parked` row is present AND every non-`parked` row is `done`/`deferred` → append the
  `RUN PARKED — awaiting <condition(s)>` sentinel (see Convergence) to `progress.md` (name the
  awaited condition(s) + the parked rows) and STOP. This is a **resting, non-terminal** state: the
  next invocation short-circuits on it (step 0.1) instead of re-reconciling. (Tested BEFORE COMPLETE
  so a release-gated row is not swallowed as terminal; it requires truly-terminal peers — a plain
  in-run-`blocked` row present routes to pending below, not to a false park.)
- Else if EVERY row is terminal (`done`/`deferred`/`blocked`) → append the `RUN COMPLETE —
  <run-slug>` sentinel (see Convergence) to `progress.md` (counts + any blocked/deferred items) and
  STOP (convergence).
- Else (rows still `blocked` on an open in-run dependency, or `blocked: too-large` awaiting a split)
  → report what's pending and STOP without a sentinel.
**Size guard:** before entering the pipeline, estimate scope from the issue body — if it
plausibly touches many files or spans multiple unrelated acceptance-criteria clusters (won't
fit one context window), mark it `blocked: too-large`, escalate to `SCOPE_AGENT` to split, and
go back to select. Aggressively offload reading/analysis to subagents (`DESIGN_AGENT`,
AC-verifier) within an iteration to conserve the parent's context.

### 2. Triage / route (if not already routed)
Run the Router (below) to set the row's **Route** (`code`/`research`/`docs`/`stub-defer`) and its
**initial Status** (Route and Status are distinct — see Ledger format → queue.md): `stub-defer` →
Status `deferred` (terminal); an unmet in-run dependency → Status `blocked` (record the dep, or
`too-large`, in Notes — the Route is retained so the row resumes as that route when the dependency
clears, step 1); a row whose work is gated on an **external event** (a release cut, a dogfood
window — not an in-run issue) → Status `parked` with Notes `awaiting: <condition>` (non-terminal,
resting; released only by explicit human un-park, step 0.1); otherwise → Status `routed`. If the
Status is `deferred`/`blocked`/`parked`, journal why and go back to step 1 — do not implement.

**Write parked/blocked Notes as the curation DECISION, never the mutable evidence.** The durable
*why* (`awaiting: <external condition>`, `deliberately out of <run> at init (curation)`, `kept:
out-of-<run> roster (curation)`) survives a later live re-check; the mutable live evidence ("not in
roster", "no PR yet") is contradicted by the next re-check and destabilizes resume.

### 3. Plan
Set the row status to `planning`. Fetch the issue (`gh issue view <N>`). Write
`issue-<N>.plan.md` (template in Ledger format → issue-<N>.plan.md), copying acceptance criteria
verbatim. Lighter for research/docs.

**Value framing (opens the plan, route-scaled).** State *why this should exist* in
user terms — the question the architect/AC-verifier/code-review gates never ask (they check we
build the thing right, not that it's the right thing). You write it inline; it is not extra
ceremony. Scale it to the route:
- **`feat:`** — a compact user-story map: one backbone activity + 1–3 `as a <user>, I want
  <capability>, so that <outcome>` stories. Each carries **who benefits**, its **prevalence**
  (how often real configs/corpora actually hit it), and a **falsifier** — *what single
  observation would show this feature is misdirected?* (e.g. "~0 matching instances in any real
  corpus"). A story with no credible user, or no checkable falsifier, is a red flag.
- **`fix:`** — one line: who hits the bug, how often, what breaks without the fix.
- **`docs:`** — who reads it and what it unblocks.
- **`research:`** — the question, the downstream decision it informs, and what a **null result**
  would mean (a null that changes nothing is a sign the question isn't worth asking).
- **`chore:` / `refactor:`** — one line: what internal tooling or quality this serves and why
  now; no user-facing story required (state "internal tooling, no release-visible change" if so).

**Discharge cheap falsifiers at plan time — don't just state them.** If a story's falsifier is
checkable *before* code (a grep / corpus / prevalence pass), RUN it now, or escalate; a
stated-but-unrun falsifier is not sufficient. This is the load-bearing step: a cheap corpus pass
has caught a misdirected feature in this project's history — but only post-hoc, which is exactly the
argument for discharging it now. Defer discharge only when the check genuinely requires the built
feature.

**Source-fidelity check (any externally-cited justification).** If the issue's rationale leans on
an external source — an automated research-scout candidate feed, a linked article, a postmortem —
confirm the source actually supports the generalization the issue makes: **locus** (does the
incident occur on the surface this feature inspects?), **evidence base** (n, scope, whether the
source itself generalizes), and **current relevance** (already fixed upstream? version-specific?).
An issue that extrapolates past what its source establishes is misdirected regardless of
implementation quality — escalate rather than build.

**When you can't articulate it, escalate — don't build.** If you cannot state a credible user
*and* a checkable falsifier, route the issue to `SCOPE_AGENT` BEFORE implementing; do not
proceed on a plan whose value story doesn't hold.

### 4. Architect gate (conditional)
If any `ARCHITECT_TRIGGERS` condition fires OR you are unsure about the design, invoke the
`DESIGN_AGENT` with the plan; address `blocking`/`important` concerns before coding. Skip for docs
and trivial research.

### 5. Human gate (conditional — every mode)
The plan gate is **conditional in every mode** — `mode:` gates the merge gate only (step 11), never
this one. It is **value-first**: present the step-3 value framing (user-story map / value statement)
alongside the approach, and treat a **non-credible value story — no plausible user, or no
checkable falsifier — as itself a reason to STOP**, not just ambiguous ACs. Present the plan and
STOP for approval when: the value story doesn't hold; acceptance criteria are ambiguous; the
change is risky/irreversible; SCOPE/DESIGN agents disagree or punt; or you are otherwise unsure.
Otherwise proceed (note "auto-approved" + why in the journal). Route scope/value questions to
`SCOPE_AGENT` and design questions to `DESIGN_AGENT` BEFORE escalating to the human. On approval
(human or auto), advance the row to `plan-approved`.

### 6. Implement (you, the parent thread)
Advance the row to `implementing`. Create the branch (`BRANCH_FMT`). Implement code + tests +
docs per the plan. TDD where it fits (write failing tests, commit, do not modify tests later).
Run `LINT_CMD`, `TYPE_CMD`, `TEST_CMD` until green. Do NOT stage unrelated pre-existing
working-tree changes.

### 7. Verify done (independent, fresh context)
Run the AC-verifier (below): a fresh check that the diff satisfies EVERY acceptance
criterion — verify state, not your claim. If gaps, fix and re-verify **once**: round 1 was the
gate's own first run, so that re-verify is **round 2 of this gate's 2-round cap**, and if it comes
back dirty, escalate. **The re-verify is a fresh instance, never the author of the fix**
(Fresh-re-check invariant, under Gates: a new spawn, not you and not the round-1 agent
re-contacted).
**"Gaps" means a finding of either class** — an unmet criterion or a surviving
mutant both send you back to fix and re-verify under the same cap.

The gate returns **two result classes, and they are never summed into one "findings" count**:
**Class A — AC-satisfaction findings** (a criterion judged not met) and **Class B — mutation
survivors** (a test this change adds or modifies that stays green when the behavior it guards is
broken — or, when the change alters behavior and adds no test at all, that absence).
Class B comes from the **mutation pass**, which is **scoped by risk surface** rather than run
unconditionally: step 7 itself remains due on every issue with acceptance criteria, but the mutation
pass *within* it is conditional (AC-verifier → Part 2). **A clean Class B after a dirty one is a
valid and valuable result** — do not read "no survivors this time" as the gate going soft.

### 8. Commit + PR
Commit with correct `COMMIT_CONV` scope. Open the PR; **replicate `PR_TEMPLATE` fully** in
the body; make the Security-review choice up front. Advance the row to `in-pr` and record the
PR number. Wait for CI; fix until green.

### 9. Code review
Advance the row to `in-review`. Run `CODE_REVIEW` on the diff.

`CODE_REVIEW` names a **procedure you run, not a command you call**. The default — and the pattern
that works in practice — is **parallel finder subagents over `git diff main...HEAD`, plus a pass
that confirms each finding**, journaled under the gate's name. (`main...HEAD` is the right form
*here*: the commit has already happened by this gate. The acceptance gate deliberately diffs the
working tree instead, because it runs before the commit — do not "fix" one to match the other.) A review skill marked
`disable-model-invocation` is **user-triggered only and cannot be invoked from here at all**: if
`CODE_REVIEW` is bound to one, the gate is unsatisfiable and silently does nothing. Such a skill is
a *human* escalation, never a binding. On finding one bound here: run the finder procedure for this
issue, journal the misbinding as a `- gate-fallback:` line (Gate-outcome invariant) along with the
rebind you recommend, and surface it to the human — **do not edit `loop.config.md` yourself**
(Tool surface).

**Give every finder the issue's acceptance criteria alongside the diff.** You cannot judge whether
code is *right* without knowing what it was meant to do; a finder holding the ACs catches "this
doesn't actually do AC-3", a class the diff alone cannot reveal. (This does not make step 7
redundant — the acceptance gate still runs independently.)

**Pick finder angles from the diff's risk surface, not from a fixed list.** Distinct lenses —
correctness; robustness/IO/network/filesystem; reuse/conventions/integration;
production-readiness — overlap far less than repeated passes of the same one, and single-angle
review misses most of what a diff carries. Scale the count with the surface: one light pass on
`docs`, more when the diff touches a production or public-API path.

Implement viable findings; decline others with a one-line rationale; then **commit the fixes** and
**verify recs were applied — by a fresh checker, never by yourself.** This is the Fresh-re-check
invariant's sharpest instance (see Gates): you wrote the fixes, so confirming them yourself is the
author agreeing with himself, not a gate. **Commit before spawning it** — the checker reads
`main...HEAD` like the rest of this gate, so an uncommitted fix is invisible to it and the re-check
would certify the pre-fix code (the F15 shape the acceptance gate had to fix). Spawn **one lighter
checker** — the change as it now stands plus the list of what you claimed to fix, and none of your
conclusions about whether it worked — rather than re-running the full finder fan-out; the input
recipe and its licence to object are under Gates. Bounded to 2 rounds (round 1 being the review
itself, that re-check being round 2) — contested findings, and **any** finding the re-check returns,
whether one round 1 raised or one only the fix introduced, escalate to the human, do not loop.

### 10. Security review (by route)
Run `SECURITY_REVIEW` per the routing in `loop.config.md` (the local-skill-vs-label choice and any
host-repo Git incantation are project specifics; this engine only fixes the gate's position and
that findings ≥ the project's confidence bar are addressed):
- A `.claude/`-only (tooling-only) change → the **local** review path.
- Otherwise, if a sensitive surface is touched → the **labeled** review path, applied ONLY now
  (dev-complete). Skip for docs/no-surface changes.

### 11. Merge
Read the run `mode` and `graduated-routes` from the `queue.md` header. The merge gate is the
**only** gate `mode` changes (step 5 is conditional in every mode). A row is **auto-merge-eligible**
only when ALL of these hold:
- `mode: escalation-only`, AND
- the row's Route is listed in the header's `graduated-routes` field, AND
- the change produces **no release-artifact bump**, or ≤ patch where `RELEASE_SCHEME` defines a
  version scheme — a `docs`/`chore` change, or any change in a project with no release cycle,
  produces no bump, which qualifies, AND
- the row is **not** `hold`, AND
- none of the always-escalate conditions apply: a `feat:`/breaking change, a risky/irreversible
  change, a touched security surface, a contested review finding, or **an unresolved Class B
  mutation survivor from the acceptance gate** (step 7 — a guard that does not guard is exactly the
  defect an auto-merge has no human to catch).

**Default-deny:** if route graduation or any always-escalate condition is uncertain, the row is
**not** auto-merge-eligible — fall back to the human merge gate.

If the row is **not** auto-merge-eligible — which includes *every* row under `mode: calibration`
(the default) and any `hold` row — STOP and ask the human before merging; never auto-merge.
**If the human holds the merge (now or in any later invocation),
WRITE the hold to the row before stopping** — set Status `hold` (record the reason in Notes) so
it persists across `/clear`; resume (step 0.3), step 1, and this gate all key on Status `hold` and
honor it until the human clears it (restoring the row's prior status). When the row **is**
auto-merge-eligible (or the human has approved), and CI + security are green AND the row is not
`hold`:
merge via `MERGE_METHOD` with an explicit `--subject` carrying the correct `COMMIT_CONV` scope,
`--delete-branch`. Confirm the issue closed.

### 12. Journal + stop
Append the iteration block to `progress.md`, including a `- Budget:` line (Ledger format →
progress.md):
`subagent-runs=<n>` · `gate-rounds=architect=<a>,code-review=<c>,ac-verify=<v>` ·
`wall-clock=<elapsed, includes gate-wait — not a cap input>` · `tokens=deferred` (computed
post-hoc from the loop's own JSONL by an out-of-band analyzer, not inside the skill; the named
slot keeps the line forward-stable) — **plus any of the optional slots below**. Those four are
**required**; write the whole thing as **one physical line, never wrapped** (every reader of this
line is line-based, so a wrap strands whichever slots fall past the break).

**Say why, not just how much.** Counts alone cannot tell a justified high-stakes iteration from
review thrash, which is the distinction the human needs when deciding whether to loosen a gate. So:
- **Note any slot** by putting a short free-text parenthetical **after** its value —
  `subagent-runs=4 (Explore map + architect + 2 finders)`,
  `gate-rounds=architect=0(discharged by a pre-existing review)`. A space before the `(` is optional.
  On `gate-rounds` a note attaches to the **immediately preceding sub-slot**, never to the slot as a
  whole — to annotate the whole iteration, use `justification=`.
- **On the code-review count, the parenthetical records the lenses that fired** —
  `code-review=2(correctness,robustness)`. Instrumenting which angles actually catch things is what
  lets a review-tier matrix later be chosen from corpus rather than intuition.
- **Add `justification=<short reason>` whenever any `gate-rounds` value exceeds 1** — the single-pass
  baseline. It is *permitted* on any line; write it whenever the spend would otherwise look
  unexplained.
- **Record the acceptance gate's two result classes separately — and its escape count separately
  again.** Three distinct numbers; collapsing any two of them loses the distinction between a gate
  that found nothing and a gate that missed something:
  - `ac-findings=<n>` — **Class A**, criteria the gate found unmet, **counted cumulatively across
    all of that gate's rounds, not as the final round's residue** (a final-round count is 0 on every
    iteration that merged, which erases the signal).
  - `mutation-survivors=<n>` — **Class B**, guards whose test survived its own mutation
    (AC-verifier → Part 2).
  - `post-gate-survivors=<n>` — **not a gate output at all**: defects that escaped the gate and
    surfaced later in this iteration. Class A and Class B are what the gate *found*;
    `post-gate-survivors` is what it *missed*. Keep the three names straight — Class B is
    `mutation-survivors`, never `post-gate-survivors`.

**Two constraints that keep the line parseable.** No slot value and no note may contain the `·`
separator, and notes must keep their parentheses balanced — a reader splits `gate-rounds` on commas
**outside** parentheses, so the lens list above stays one sub-slot rather than three.

Set the `queue.md` row to `done` (or `blocked`/`deferred` with reason); note newly-unblocked
issues. The ledger is gitignored — do NOT commit it (Ledger format → lifecycle). STOP. (Driver
re-invokes with fresh context for the next issue.)

### Escalation rubric (when unsure)
Scope/priority/requirements — including any plan whose value story lacks a credible user or a
checkable falsifier (step 3) — → `SCOPE_AGENT`, before implementing. Design/implementation →
`DESIGN_AGENT`. Escalate to the HUMAN only when those disagree/punt, ACs are unresolvable, an
action is destructive/irreversible, a review finding is contested, or the same step failed twice.

**A gate that produced no verdict does not get reasoned about here.** Do not weigh whether its
absence "matters" — apply the **Gate-outcome invariant (evidence-bound pass)** under Gates,
convergence & resting states, which decides it — including which failures fall back and which
escalate. Do not paraphrase those branches from memory; they differ, and the difference is the rule.

### Guardrails
One PR at a time (no stacked PRs). **Stuck = the same error SIGNATURE recurs** — grep the FULL
`progress.md` (not just the tail) for the signature: an identical CI failure, or the same
tool+args failing again — NOT merely re-entering a status (a legitimate `/clear`-resume
re-enters `implementing` and must not be flagged). **A `- gate-fallback:` line is likewise not a stuck
signature** — a standing misbinding recurs by design until the human repairs the config (Gate-outcome
invariant), so exclude those lines from the repeat check and re-surface the config defect instead;
`- gate-error:` lines *are* in scope. On a genuine repeat: stop, escalate, mark
`blocked`, move on. Respect any iteration/budget cap (`iteration-cap:`/`subagent-cap:` in the
`queue.md` header): checked at iteration start (step 1) against the ledger — **advisory in manual
re-invoke (journaled + surfaced, not gating), halted by the driver**.

### Tool surface — and what you must NOT do
This skill intentionally runs with the full session toolset (no `allowed-tools` restriction):
an orchestrator needs Write/Edit, Bash(git+gh+tests), Agent (`SCOPE_AGENT`/`DESIGN_AGENT`/
AC-verifier), and the built-in review skills. With that power come hard limits — never force-push;
never bypass failing CI (no admin-merge, never merge red); only `--delete-branch` the PR's own
branch; never `git add` unrelated pre-existing working-tree changes; never edit the
user-global `SCOPE_AGENT`/`DESIGN_AGENT` definitions; **never edit `loop.config.md`** — a binding
that looks wrong is a finding you journal and hand to the human, because a gate you rebind to match
your own reading entrenches your misreading instead of correcting it. The C1 append-only guard and
the human/merge gates are the enforced backstops; the rest of this list is your contract.

---

## Ledger format

Create `LEDGER_ROOT/<run-slug>/` (e.g. `.claude/loop/<run-slug>/`) containing three artifacts.
The orchestrator is the only writer except where noted.

### `queue.md` — work list (authoritative status)
Dependency-ordered. One row per issue. **`Route` and `Status` are separate columns** (a row
can be Route `research`, Status `blocked`). **Pipeline statuses** — advanced by the
orchestrator as the issue moves through the pipeline, so an interrupted run leaves a non-terminal
status resume keys on (see Resume): `queued → routed → planning → plan-approved → implementing →
in-pr → in-review`. **Terminal statuses** — the run converges when every row is terminal:
`done`; `deferred` (Route `stub-defer`); `blocked` (an unmet in-run dependency; `blocked:
too-large` awaiting a split; or a recurring `gate-error:` awaiting a config repair — see the
Gate-outcome invariant). The last two wait on a human, not on another row. **Two non-terminal, resting statuses** sit outside both
the pipeline and the terminal set: **`hold`** — a durable, human-set merge-hold that survives
`/clear`; and **`parked`** — a row whose work is gated on an **external event** (a release cut, a
dogfood window — *not* an in-run dependency), with the awaited condition in Notes as
`awaiting: <condition>`. Both retain their Route and are released only by the human (a `hold` by
clearing the hold at the merge gate; a `parked` row by explicit un-park, step 0.1 — which
flips it back to `routed`). While any `hold` **or `parked`** row remains the run is NOT complete
(Convergence distinguishes the resting `RUN PARKED` state from terminal `RUN COMPLETE`), but neither
blocks selecting other queued work (steps 0–1).

**Curated-subset invariant.** The queue built at init (see Initialization) is the authoritative
work set; `BACKLOG_SOURCE` membership may drift afterward, and that drift is **surfaced to the
human once, never auto-applied** — neither auto-added on join nor auto-ejected on leave (step-1
roster reconciliation). A corollary is a Notes discipline: **write a `parked`/`blocked` row's Notes
as the durable curation DECISION** (`awaiting: <external condition>`, `deliberately out of <run> at
init (curation)`, `kept: out-of-<run> roster (curation)`), **never the mutable live evidence** ("not
in roster", "no PR yet") — the latter is contradicted by a later live re-check and destabilizes
resume.

The header carries a `mode:` field that gates **the merge gate only** — it does
**not** change the plan gate, which is conditional in *every* mode (step 5: the
plan gate stops only on ambiguous ACs, risk/irreversibility, agent disagreement, or genuine
uncertainty — never merely because of `mode:`). The two modes:
- **`calibration`** (default) — the human approves **every** merge; the loop never auto-merges
  (step 11). Plan gate conditional.
- **`escalation-only`** — the human loosens the **merge gate per route**: a route the human has
  *graduated* auto-merges when CI + AC-verifier + review are green and the change produces no
  release-artifact bump (or ≤ patch where `RELEASE_SCHEME` defines one — a `docs`/`chore` change,
  or any change with no release cycle, qualifies). *Which* routes are currently graduated is a
  mutable human decision, recorded per-run in the `graduated-routes:` header and in the project
  decision log — never frozen into this mechanism definition (the lesson: graduation *state* is
  evidence, not a rule). The human merge gate is **retained** for every non-graduated route and,
  regardless of route, for any of: a `feat:`/breaking change, a risky/irreversible change, a touched
  security surface, a contested review finding, an unresolved Class B mutation survivor (step 7),
  or a `hold` row — **and, by default-deny, whenever
  route graduation or any always-escalate condition is uncertain, fall back to the human merge
  gate.** Plan gate conditional (unchanged). Loosening to `escalation-only` presupposes the
  calibration prerequisites are met (these pinned mode semantics, plus per-iteration budget
  journaling — the `- Budget:` record and `iteration-cap:`/`subagent-cap:` fields below); it cannot
  run headless.

The set of graduated routes is recorded in a `graduated-routes:` header field beside `mode:`
(default `none`; e.g. `graduated-routes: docs, research`). Under `mode: calibration` it is inert.
*Which* routes graduate and the criteria for promoting one are out of scope here; this field only
gives the merge gate (step 11) a place to read the human's decision from.

The header also carries two **budget caps** (both default `none` = uncapped):
`iteration-cap:` (max **issues per run** — in this engine one "iteration" = one issue) and
`subagent-cap:` (max **subagent runs per iteration**). The orchestrator checks them at iteration
start (step 1) as a **retrospective circuit-breaker** against the ledger — it does not watch
its own spend mid-turn (that is why token/cost is deferred, below). Cumulative iterations are
counted as the **distinct issues at a terminal status** (`done`/`deferred`/`blocked`) in
`queue.md` — the authoritative status file — never by counting `progress.md` blocks, since a
`/clear`-resume re-enters an iteration and would double-count. `subagent-cap` is enforced by
reading the **prior** iteration's journaled `- Budget:` line: if it breached, halt before
starting the next. On breach the behavior is **advisory in manual re-invoke** (journal + surface
it and proceed — the human who invoked is the budget authority) and **halting under the driver**
(see Convergence). The caps bound `escalation-only`'s runaway-consumption risk; bad-merge risk is
already covered by the default-deny/always-escalate machinery above.

```markdown
# Loop run: <run-slug>
_mode: calibration_
_graduated-routes: none_
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

### `progress.md` — append-only journal (survives /clear + compaction)
The orchestrator APPENDS one block per iteration (and per gate decision). Never rewritten.
This is the audit trail and the resume anchor.

```markdown
## <ISO8601> — #<N> (research) — iteration start
- Selected: #<N> (highest-priority unblocked).
- Route: research (probe; no test-coverage gate).
- Plan: issue-<N>.plan.md written.
- Architect: skipped (research scaffolding, no shared-interface impact).
- Human gate: plan auto-approved (route=research, low ambiguity).
- Implemented: <path>; recorded findings in <path>.
- AC-verify: Class A 3/3 acceptance criteria met. Class B: mutation pass not due (research route).
- PR: #<pr> (chore scope). CI: green.
- Code-review: 0 findings. Security: n/a (no deps added).
- Budget: subagent-runs=3 · gate-rounds=architect=0,code-review=1(correctness,robustness),ac-verify=1 · ac-findings=0 · mutation-survivors=n/a: research route · wall-clock=18m · tokens=deferred
- Merged: squash #<pr>. Issue #<N> closed.
- Next: #<M> now unblocked.
```

Two further fixed-shape lines are appended **only when a gate produced no verdict** (Gate-outcome
invariant — that section defines when each applies and what follows):
- `- gate-fallback: <gate> — <the binding defect> → ran <what you substituted>` — the gate could not
  run, an inline composition stood in, the iteration continued. A **substitution record**; Guardrails
  excludes it from the repeat check, so a standing misbinding never reads as *stuck*.
- `- gate-error: <gate> — <failing tool or command> — <first line of the error>` — the gate was
  attempted, produced no verdict, and the iteration STOPPED. This one **is** a stuck signature:
  Guardrails greps for it across rows, so elide volatile arguments (PR numbers, SHAs, paths).

The `- Budget:` line is the per-iteration cost record: a `·`-separated list of `name=value` **slots**.

It carries three different kinds of thing, and mixing them up is the standing confusion — **a count
of how many times something ran** (`gate-rounds`), **a count of what was found** (the result-class
slots), and **a free-text note** annotating either. Only `gate-rounds` nests; a gate's *rounds* live
inside it, while a gate's *results* are their own top-level slots, because `post-gate-survivors`
belongs to no round at all.

Fields:
- **`subagent-runs`** — the proxy cost signal the orchestrator can count for free. **One run = one
  subagent invocation**, so N parallel finders count as N, not as the one gate round they serve
  (the `subagent-cap` check above reads this number, so an under-count silently loosens
  the cap; it reads the leading integer and ignores any parenthetical). Its blind
  spot: parent-thread token burn (a long implement step spawns no subagent yet can be the largest
  consumer) is invisible to run-count — which is precisely what the deferred `tokens` field
  eventually fixes.
- **`gate-rounds`** — architect / code-review / ac-verify round counts (feeds review-thrash
  detection downstream). **A different axis from `subagent-runs`, and neither implies the other:** a
  round can consume zero subagents (a review done in the parent thread — never a capped gate's
  round 2, which the Fresh-re-check invariant requires be a spawn) or several (parallel finders
  plus a confirmation pass), and a subagent can serve no gate at all (recon during implement). Only
  this slot signals *thrash* — having to run a gate again.
- **`justification=<short reason>`** — why the spend was warranted. Counts alone cannot separate a
  justified high-stakes iteration from review thrash, which is exactly the distinction the human
  needs when deciding whether to loosen a gate. **Expected whenever any `gate-rounds` value exceeds
  1** — the single-pass baseline — and *permitted* on any line. The trigger is deliberately the one
  thing decidable from the same line: it is the engine's own shape, not a per-project number, so it
  needs no binding and cannot drift upward as a run gets more expensive.
- **`ac-findings` / `post-gate-survivors`** — what the acceptance gate **found** in Class A, and
  what **escaped** it, recorded **separately** (Class B is its own slot, `mutation-survivors`,
  below — the gate's two *result classes* are `ac-findings` and `mutation-survivors`; this pairing
  is findings-vs-escapes, which is a different axis): criteria the gate found unmet, **counted
  cumulatively across all of that gate's
  rounds** (the final round's count is 0 on every iteration that merged, so a final-round reading
  erases the signal); and defects that escaped the gate and surfaced later in the same iteration —
  in code review, security, or at the merge gate, the window running from the gate to this journal
  entry. A survivor found in a *later* iteration is recorded on that iteration's line, naming the
  one it escaped; this journal is append-only and is never rewritten to add it. Collapsed into one
  number these cancel out — a gate that found nothing and a gate that missed something read
  identically, and two stories measuring opposite signals off this line would each think they were
  confirmed. They are top-level slots, not nested in `gate-rounds`, because they count **outcomes
  rather than runs**.
- **`mutation-survivors`** — **Class B**: a guard the change added that does not guard — a test
  that stayed green when the code it protects was broken, or, where no test was added at all, that
  absence (AC-verifier → Part 2). **Writable as of this change** — it was reserved-and-unwritable
  before, and the promised addition has landed as an addition rather than a format change. It takes **three distinct readings, and the difference between them
  is the point**:
  - **`mutation-survivors=<n>`** — `n` Class B findings, and **`0` is meaningful and is written**:
    Class B was due and came back clean. The **limit case** (behavior altered, no test added or
    modified) lands here too — the absence *is* the single finding, so write
    `mutation-survivors=1 (no guard added)` using the ordinary note syntax. Recording it as a count
    is what stops it reading as clean; the note is what stops it reading as a surviving mutant.
  - **`mutation-survivors=n/a: <reason>`** — Class B was **not assessed**, for one of exactly
    three reasons: the route scoped it out
    (`n/a: docs route`), the change alters no behavior (`n/a: no behavior change`), or the mutation
    apparatus is not yet specified (`n/a: apparatus pending` — see AC-verifier → Part 2). **No other
    reason is a legal `n/a`.** In particular: a change that alters behavior *while adding no test*
    is the limit case — a Class B **finding**, written as a count; and an unrunnable `TEST_CMD` is a
    `- gate-error:`. Writing `n/a` for either would erase a finding or excuse an unbound binding,
    which is the one reading this slot must never permit. The `n/a: <reason>` spelling follows the
    Gate-outcome invariant's not-run vocabulary, and it is deliberately visible.
  - **omitted** — **unknown**. This is what every line written before this slot existed
    carries, and those lines keep exactly that meaning. An omission must **never** be read
    retroactively as "the pass was scoped out": the corpus is append-only and is never rewritten, so
    the only honest reading of a missing slot is that nothing produced it.

  The three readings exist because collapsing them onto one absent/zero axis would make it
  impossible to tell a clean pass from a skipped one from a nonexistent one — and the first stories
  to measure this gate's efficacy read exactly that distinction off this slot.
- **`wall-clock`** — elapsed time including human gate-wait; recorded for the dogfood corpus, **not
  a cap input** (an iteration that waited overnight for approval is not "expensive").
- **`tokens=deferred`** — a reserved, named slot. Per-iteration token/cost is computed **post-hoc
  from the loop's own JSONL by an out-of-band analyzer** (the loop JSONL is a first-class corpus),
  not inside the skill (the orchestrator can't cleanly slice its live session mid-turn). A future
  SDK driver backfills it via usage callbacks — keeping the slot named now makes that a backfill,
  not a format change.

**Notes on any slot.** A short free-text parenthetical may follow **any** slot's value —
`subagent-runs=4 (Explore map + architect + 2 finders)`,
`gate-rounds=architect=0(discharged by a pre-existing review)`; the space before `(` is optional. It
goes *after* the value so the value stays machine-readable. On `gate-rounds`, a note attaches to the
**immediately preceding sub-slot**, never to the slot as a whole — annotate the whole iteration with
`justification=` instead. On the **code-review** count the parenthetical specifically records **the
lenses that fired** (`code-review=2(correctness,robustness)`) — instrumenting which angles actually
catch things is what lets a review-tier matrix later be chosen from corpus rather than from
intuition. A note annotates; it never replaces a slot.

**Writing it so it can be read back.** The line is **one physical line, never wrapped** — this
repo's own step-order references went unguarded for a release precisely because two of them were
line-wrapped, and every reader of this line is line-based. **No slot value and no note may contain
the `·` separator**, and a note's parentheses must be balanced: a reader splits `gate-rounds` on
commas **outside** parentheses, which is what keeps `code-review=2(correctness,robustness)` one
sub-slot rather than three. A slot is split from its value on the **first** `=`, never on a later
one — `gate-rounds=architect=0` depends on this, and so does any note containing an `=`. Every slot
uses `=`, including where prose would reach for something softer: write
`wall-clock=≈2h`, never `wall-clock≈2h`, or the slot parses as a nameless fragment and is lost.

**Forward stability.** The four slots in the chain the journal step prescribes (`subagent-runs`,
`gate-rounds`, `wall-clock`, `tokens`) are **required**: `subagent-runs` because the `subagent-cap`
check reads it and an absent one leaves that check undefined and silently inert, and the other three
because every line in the existing corpus carries them — a reader comparing iterations needs the
same spine on each. Every slot beyond those four is
**optional**, order-insignificant, and a reader ignores names it does not recognise — the
`tokens=deferred` precedent generalised from one reserved name to a rule, so a later release adds
slots without invalidating existing lines. One constraint on reading them: **an absent slot does not
mean zero.** A missing `ac-findings` says nothing about how many findings there were; only
`ac-findings=0` does — which is why a slot with no producing procedure is omitted rather than zeroed.
Where a slot's procedure exists but was **not due** on this row, that is its own reading — write
`n/a: <reason>` rather than omitting (`mutation-survivors` above is the worked instance; the
spelling follows the Gate-outcome invariant's not-run vocabulary). So three states stay
distinguishable: a value, a visible not-due, and an omission that means only "unknown".

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

## Architect triggers hit
<which ARCHITECT_TRIGGERS fired, or "none">

## Risks / open questions for human
<empty if none>
```

### Lifecycle & commit policy
- **Init:** orchestrator creates the dir + `queue.md` from `BACKLOG_SOURCE` (see Initialization).
- **Per iteration:** update one `queue.md` row through its statuses; append `progress.md`;
  write/update `issue-<N>.plan.md`.
- **Commit policy — gitignore the ledger** (`LEDGER_ROOT/` is added to `.gitignore`). It is
  local working state: it survives `/clear`/compaction on disk, but is **never committed**.
  This is deliberate — committing it has no legal landing spot under a `main`-is-PR-only,
  no-stacked-PRs repo (folding ledger commits into an issue's squash-merged PR would pollute that
  PR's scope). Resolves the branch-protection collision.
- **Dogfood corpus harvest:** read the JSONL + `progress.md` from the working tree directly; if a
  versioned audit trail is later wanted, snapshot the ledger into a dedicated `docs:` PR on demand
  — do not stream per-iteration ledger commits.
- **No git/ledger divergence:** because the ledger is uncommitted, resume (see Resume) reconciles
  the on-disk ledger against *live* git/PR state (branch exists? PR open? CI status?), which
  is the source of truth — not a possibly-stale commit.

---

## Router — classification procedure
Set the row's **Route** (the semantic kind) and its **initial Status** *separately* — they are
distinct columns (Ledger format → queue.md), so a dependency-blocked research issue is Route
`research` / Status `blocked`, not Route `blocked`.

**Route**, from labels + body signals per `SOURCE_LAYOUT`, in order:
1. Issue body says explicitly "NOT implementation-ready" / is a stub (per `SOURCE_LAYOUT`'s
   stub-defer marker) → `stub-defer`.
2. The project's docs label + change confined to docs/markdown (per `SOURCE_LAYOUT`) → `docs`.
3. The project's research label or a `*-discovery` epic, throwaway scaffolding, "artifact under
   study is data" (per `SOURCE_LAYOUT`) → `research` (no test-coverage gate; placement outside the
   package; no runtime-dep leakage into the package).
4. Otherwise (a bug/enhancement touching the package source) → `code` (full pipeline).

**Initial Status:** Route `stub-defer` → `deferred` (terminal). Else if the row's work is gated on
an **external event** (a release cut, a dogfood window — not an in-run issue) → `parked` with Notes
`awaiting: <condition>` (non-terminal, resting; released only by explicit human un-park, step 0/1).
Else if any `Depends on` issue is not `done` → `blocked` (record the dep in Notes; the semantic
Route is retained so the row resumes as that route once the dependency clears, step 1). Else →
`routed`.

---

## AC-verifier
Default: **compose existing tools**, don't mint an agent.

The gate has **two parts** and returns **two result classes**: **Class A — AC-satisfaction
findings** from Part 1, and **Class B — mutation survivors** from Part 2. They are reported as
**two counts and never merged into one**. Collapsed, a gate that found nothing reads identically to
a gate that missed something — and the two classes answer different questions. Class A asks *did we
build what was asked?*; Class B asks *would we notice if it broke?* A change can pass either while
failing the other.

**Part 1 — Class A: AC-satisfaction findings.**
1. After implementation, spawn a fresh subagent with ONLY: the issue's acceptance criteria
   (verbatim) + the `$BASE` SHA resolved below + the commands under **Verifier runs** — and nothing
   from your own plan, narrative, or claims (the "ONLY" excludes your *conclusions*, not the
   instructions it needs). The verifier **runs the read commands itself** so it reports what it saw
   rather than what it was handed. Define its input **without assuming a commit exists** — this
   gate must certify the same work whether or not the branch has been committed yet.

   **Orchestrator, before spawning — resolve the fork point.** Run it as ONE command and **quote**
   the result: shell variables do not survive between tool calls, and an *unquoted* empty `$BASE`
   makes `git diff` silently degrade to **unstaged-only** — a plausible-but-wrong input rather than
   a visible failure. Quoted, the same mistake fails loudly instead.
   ```bash
   BASE=$(git merge-base main HEAD) && git diff "$BASE" --stat
   ```
   (`main` is the assumed base branch; a project whose trunk is named otherwise adjusts it here —
   parameterizing it is a pending change.) **If `$BASE` is empty** — the base ref does not resolve,
   or the histories are unrelated, which exits non-zero with *no* stderr at all — STOP and escalate
   **to the human**. That is an environment fault, not an AC gap, so it does **not** consume one of this
   gate's two rounds; journal the failing command as a `- gate-error:` line (Gate-outcome invariant)
   and do NOT run the diff.

   **Verifier runs** (from the repo root — prefix with `git -C "$(git rev-parse --show-toplevel)"`
   if the working directory may be elsewhere):
   - **`git diff "$BASE"`**, plus `--stat` for the file and insertion counts it is asked to report
     — merge-base → **working tree**, covering all three commit states in one command: **fully
     committed** (equivalent to the old `main...HEAD`, though only on an otherwise-clean tree),
     **partially committed** (the still-uncommitted remainder is included, staged and unstaged
     alike), and **wholly uncommitted** (the entire branch's work is included — the case where
     `main...HEAD` yields an EMPTY diff and the gate certifies nothing).
     **Over-inclusion is the price of that coverage, and it is a real failure mode:** the working
     tree also carries any *unrelated* pre-existing edits, which the implement step forbids staging
     but not merely having — so they will never merge. The verifier must name them separately and
     must never accept them as AC evidence; a `file:line` citation has to land in the merge
     candidate. (Under-inclusion certifies nothing; over-inclusion certifies the wrong thing.)
   - **`git ls-files --others --exclude-standard`** — **untracked files, which no diff ever shows.**
     A brand-new file is among the commonest forms of AC evidence; read the contents of those the
     acceptance criteria implicate and list the rest by path only. Two traps: the command is scoped
     to the **current directory**, so from a subdirectory it silently omits everything above it; and
     it lists stray scratch files belonging to no branch, which must not be mistaken for the work.
   If the diff plus that content will not fit one context window, report `input-too-large` and
   not-done rather than silently reading a truncated subset.

   Prompt: *"Run the commands above yourself against base `<SHA>`; do not rely on anything I tell
   you the input contains. State the input you retrieved — base commit, file count, insertions, and
   any untracked files — BEFORE answering, and name separately anything that looks unrelated to
   these acceptance criteria. If the input is empty or absent — no diff, AND no untracked file that
   plausibly IS the work these criteria describe — that is a FINDING: report not-done and say so;
   never read an empty diff as 'nothing to object to'. Then, for each acceptance criterion, state
   met/not-met with the file:line or test that satisfies it, citing only work that belongs to THIS
   change and never an unrelated pre-existing edit. Uncommitted work that implements a criterion IS
   valid evidence — diffing the working tree is the whole point; 'not yet committed' is never a
   reason to call a criterion unmet. Verify the diff actually does this; do not assume. Return a
   checklist + overall done/not-done."*
2. For behavior that needs runtime proof, also run `VERIFY` (runs the app).
3. `CODE_REVIEW` (step 9) provides the adversarial bug pass.
Promote to a dedicated `ac-verifier` agent only if the composed approach proves too loose.

**Part 2 — Class B: mutation survivors.** A test that this change adds or modifies, which stays
green when the behavior it guards is broken, is a **survivor** — protection the human believes they
have and does not. A survivor is a finding, **reported as prominently as a bug**.

*Why a checklist cannot find these* — the mechanism, quoted verbatim from the project retrospective
that first made it nameable:

> **The mechanism, stated precisely** (round 4 made it nameable): *asserting the outcome is not
> asserting the mechanism.* A test written from the outcome ("the file is correct afterwards")
> passes for **every** implementation that reaches that outcome — including the broken one you are
> guarding against. The atomic-write test is the clean example: `write_bytes` and
> `mkstemp`+`fsync`+`replace` produce an identical final file, so only a test that observes *which
> writer runs* can tell them apart. This is a property of the assertion, not of the author's care —
> which is why it recurs and why only mutation detects it.

"A property of the assertion, not of the author's care" is the whole argument: the answer is a
mechanical pass, never an instruction to be more careful.

**When Class B is due — scoped by risk surface, not unconditional.** Cost is this gate's real risk.
Ask these **three** questions in order; do not invent a fourth, and note that "is this test
important enough?" is deliberately **not** among them, because a judgment about a test's worth is an
off switch an agent can always reach for:

1. **Is the row's Route `code`?** If not, Class B is **not due** — a `docs` route runs no mutation
   pass, and `research` carries no test-coverage gate, so it has nothing to mutate. Record
   `mutation-survivors=n/a: <route> route`.
2. **Does the change alter behavior** — any executable or agent-executed artifact, as
   `SOURCE_LAYOUT` defines that for this project? **A change that only adds or edits tests answers
   YES**: the guard is new, so whether it guards anything is exactly what is untested. Answer no
   only when nothing executable moved at all, and record `mutation-survivors=n/a: no behavior
   change`.
3. **Does it add or modify at least one test?** If **no**, see the limit case below. If **yes**, the
   mutation apparatus applies — see the deferral immediately below.

Questions 1 and 2 are the only ways out, and both are recorded visibly. **When any answer is
unclear, treat Class B as due** — the cost of looking is small; the cost of a wrong skip is the
entire class of defect this gate exists to catch.

**The limit case is a finding, not a silent skip — and it needs no mutation to detect.** A change
that alters behavior while adding or modifying **no** test is a Class B finding naming that absence,
never allowed to read as clean. It is read straight off the diff, so it is live from this change
onward. Nothing to mutate is not the same as nothing to worry about; it is the
guard-that-guards-nothing at its extreme.

**⚠ The mutation apparatus itself is deliberately NOT specified here.** Actually breaking production
code and restoring it safely — the actor split, the backup and byte-exact restore, the
applied-check, and the interrupted-pass recovery — is specified separately, on top of the isolation
work that removes most of its hazards. **Until that lands, this gate does not mutate the working
tree**: where question 3 answers yes, record `mutation-survivors=n/a: apparatus pending` and say so.
**Do NOT improvise a mutation procedure.** A hand-rolled one edits production code beside your
uncommitted deliverables with no restore guarantee, which is the one way this gate can destroy work
rather than protect it — and an improvised pass that reports a clean result is precisely the
manufactured confidence the whole idea exists to prevent. An honest `n/a` is the fail-safe reading;
an invented pass is not.

**Reporting, and what a survivor actually does.** Class A and Class B counts are stated separately
and land in separate `- Budget:` slots (`ac-findings` and `mutation-survivors` — see progress.md →
the Budget line). Say explicitly whether Class B was due, and if not, why.

**A Class B finding is not merely recorded — it blocks, exactly as a Class A gap does.** Strengthen
the guard (assert the *mechanism*, per the quote above, not the outcome) and re-verify, within the
same 2-round cap; past that, escalate. **That re-verify is a fresh instance, never the author of the
strengthened guard** (Fresh-re-check invariant, under Gates) — this leg needs saying separately
because it is the one place a *guard* is what got fixed, and a guard confirmed by the person who
just wrote it is precisely the defect Class B exists to catch. Recording a finding and proceeding is
not compliance — a finding "reported as prominently as a bug" that no step acts on is a bug report
filed into a drawer.
**An unresolved Class B finding at the merge gate is an always-escalate condition (step 11), so a
row carrying one is never auto-merge-eligible** however graduated its route.

**A clean Class B after a dirty one is a valid and valuable result** — do not read "nothing this
time" as the gate going soft.

---

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
   gate**, per route; it never affects the plan gate. Also set `iteration-cap: none` and
   `subagent-cap: none` (the human sets them when loosening).
5. Append an "init" block to `progress.md`. (Ledger is gitignored — not committed.)

---

## Resume after `/clear` or compaction
The next invocation's step-0 resume (step 3) reads `queue.md` + tail of `progress.md` and, finding
any *interrupted* row (non-terminal and NOT `queued`/`routed`/`hold`/`parked`), finishes it before
selecting new work. A `hold` **or `parked`** row is **excluded** — a `hold` is a deliberate, durable
human merge-hold and a `parked` row is gated on an external event (Ledger format → queue.md),
neither an interruption; leave them (a `hold` until the human clears it at step 11; a `parked` row
until explicit un-park at step 0.1) and neither blocks other work. A run resting under a `RUN
PARKED` sentinel is likewise **not** an interrupted row — step 0 short-circuits it on the cheap
parked path and never enters this resume scan (safe: a valid PARKED state has no non-terminal
pipeline row). The on-disk ledger row status is only a **coarse anchor** (which stage); the **live
git/PR state is the source of truth** for the details (the ledger is uncommitted): for an in-flight
row, check whether its branch exists, whether a PR is open (or already merged), and the PR's CI
status, and resume at the matching pipeline stage — git wins on any conflict with a stale status.
Stages 4/7/10 need no distinct status because the surrounding statuses bracket them: a
`plan-approved` row re-enters at implement (step 6), so the architect/human gates are NOT re-run.
The one external-side-effect stage is the architect (step 4) — it posts a comment to the issue —
so on the rare resume of a `planning` row, check for an existing architect comment and skip
re-invoking if present (do not double-post). AC-verify (step 7) is side-effect-free; security (step
10) re-labeling is a no-op. Security (step 10) re-labeling is a no-op. **Working-tree reconciliation:** if a crashed prior
attempt left uncommitted changes, inspect them before proceeding — keep and continue if they
match the plan, or `git restore`/stash if they're partial/unrelated. A resumed `implementing` row is NOT "stuck" (stuck
keys on a repeated error signature, not status re-entry — see Guardrails).

---

## Routing table

| Route | Pipeline differences |
|-------|----------------------|
| `code` | full pipeline, all gates; the acceptance gate's **mutation pass** (Class B) runs when the change alters behavior and adds or modifies a test — and when it alters behavior while adding **none**, that absence is itself a Class B finding, never a silent skip |
| `research` | lighter plan; **no test-coverage gate**; architect optional; security only if deps added; place outside the package source. No test-coverage gate means **nothing to mutate** — no mutation pass |
| `docs` | skip architect + security; light review; `docs:` scope; **no mutation pass** |
| `stub-defer` | do NOT implement; journal why; leave in backlog (Status `deferred`) |

`blocked` and `parked` are **Status overlays, not Routes**: a row keeps its semantic Route (`code`/
`research`/`docs`) while resting on an unmet in-run dependency (`blocked`) or an external event
(`parked`). Skip it; a `blocked` row returns to selection when its dependency closes (steps 1 /
Router), a `parked` row when the human un-parks it (step 0.1).

**Generic mechanical discipline:** set the squash `--subject` scope **explicitly** (per
`COMMIT_CONV`), never inherited from the PR title. (Host-repo mechanical specifics — e.g. the
`.claude/`-only security path and the `origin/HEAD` incantation — live in `loop.config.md`.)

---

## Gates, convergence & resting states

Gate table:

| Gate | Who | When | Output |
|------|-----|------|--------|
| Plan | orchestrator | every issue | `issue-<N>.plan.md` |
| Architect | `DESIGN_AGENT` | `ARCHITECT_TRIGGERS` or unsure | issue comment |
| Human (plan) | user | only if uncertain/irreversible | approve/redirect |
| AC-verify | fresh subagent (+`VERIFY`); **any re-check a fresh instance too** (Fresh-re-check invariant) | every issue with acceptance criteria (step 7 is unconditional; the **mutation pass within it** is scoped — Routing table) | done/not-done + gaps, as **two separate counts**: Class A (AC-satisfaction) and Class B (mutation survivors); **either class blocks** |
| Code review | `CODE_REVIEW` (parallel finders you run — step 9); **the fix's re-check a fresh checker, not you** (Fresh-re-check invariant) | every issue; one light pass on `docs` | findings → fixes |
| Security | `SECURITY_REVIEW` (local or label) | by route | clean/findings |
| Merge | user (calibration / non-graduated route) → orchestrator (auto: graduated routes) | CI+security green | `MERGE_METHOD` |

**Gate-outcome invariant (evidence-bound pass).** Applies to every gate in the table above that
returns a verdict, **on the rows that gate is due on** — due-ness is decided where it always was (the
gate's own step and the Routing table) and this invariant does not touch it. A gate the route or its
trigger condition never made due was never owed a verdict, so journal it as not run (`skipped` /
`n/a`) with the reason; not-due is not a pass either. An explicit `—` **plus a reason** in the config
is a deliberate "not applicable", journalled `n/a: <that reason>` — **not** an absent binding; it is
the only way a config marks a gate not-due, and it is deliberately visible.

For a gate that **is** due: it may be journalled **passed** only with the gate's own verdict as
evidence — it ran and returned clean/met. **No verdict ⇒ not passed**, and there are two ways that
happens. The discriminator is **what you can see without running it**: your own config and toolset
are *inspection*, so a binding naming a skill, agent or command absent from them is **static** —
anything that surfaces only when the thing is actually run is **dynamic**.
- **Cannot run (static)** — by inspection, the binding is absent, `TODO`-valued, or names something
  missing from your toolset or that you are not permitted to invoke. Fall back to the engine's
  inline composition where one is defined, otherwise escalate to the human. Step 9 is this branch's
  worked instance: a `CODE_REVIEW` bound to a `disable-model-invocation` skill is unsatisfiable, so
  the orchestrator runs the finder procedure itself, journals the misbinding, and surfaces it.
- **Ran and errored (dynamic)** — the gate was **attempted** — invoked, or its required inputs
  resolved — and produced no verdict: a non-zero exit, a tool error, a missing precondition. (The
  host-specific instance this was drawn from lives in `loop.config.md`, per the Routing table's
  mechanical-discipline note; do not copy a host's error string into this engine.) Do **not**
  substitute a home-composed check, and do **not** journal it as passed. **Escalate to the human.**
  The AC-verifier procedure's unresolvable-`$BASE` rule is this branch's worked instance: an
  environment fault is not an AC gap, so it escalates and does not consume a gate round.

**Either way, journal it** — but the two cases take **different, deliberately distinguishable**
forms, because only one of them is a recurrence signal:
- **Fell back and continued** (static, an inline composition exists) → append
  `- gate-fallback: <gate> — <the binding defect> → ran <what you substituted>`. There is no error
  string to quote; nothing ran. This is a **substitution record, not a stuck signature**: a standing
  misbinding recurs *by design* on every iteration until the human repairs the config, so it must
  never trip the repeat check or mark the row `blocked`. Surface it as a config defect each time.
- **Stopped and escalated** (dynamic, or static with no fallback defined) → append
  `- gate-error: <gate> — <failing tool or command> — <first line of the error>`, **before** you
  stop. The fixed shape is the point: Guardrails greps the FULL journal — **across rows, not within
  one** — so **elide volatile arguments** (PR/issue numbers, SHAs, branch names, temp paths) or the
  same standing defect signs differently on the next issue and never reads as recurring. Write
  `no-stderr` where the failure emitted none. A **first** failure leaves the row at its current
  pipeline status, taking **no** terminal (`done`/`deferred`/`blocked`) **and no resting**
  (`hold`/`parked`) status — both would put it outside the resume scan, and the point is that Resume
  re-enters it (the step-5 plan-gate pattern). A **recurring** signature is *stuck* (Guardrails) →
  mark the row `blocked` with Notes `gate-error: <gate>`. Like `blocked: too-large`, this is **not**
  a dependency block: step 1 never re-selects it, and it waits on the human. **If that row already
  has an open PR, do not "move on" to another row** — one PR at a time still binds; report and STOP.

**A gate that did not run — static or dynamic — is never recorded as a gate that passed.**

**Fresh-re-check invariant (a fix is never checked by its author).** Applies to the two gates that
carry a round cap, and so re-check a fix inside the pipeline under a bounded budget: the
**acceptance gate** (step 7, *both* result classes) and **code review** (step 9). When a gate comes
back dirty
and you fix what it found, the re-check is performed by a **fresh instance**. You wrote the fix, so
you are the one reader who cannot check it: the belief that produced the defect is still present
while the fix is written. **You are an author of every fix made in this iteration, including one you
delegated** — directing a fix is authorship for this rule, so handing the writing to a subagent and
reading it yourself satisfies nothing.

**Read this as a rule about round *two*, and about three clauses in particular** — both gates
already spawn fresh subagents for the first round they actually run today (step 7 Part 1, step 9's
finders), so the parts that actually bind are narrow:
- **Step 9's "verify recs were applied" is the sharpest hole it closes.** Confirming your own
  remediation is not a gate; it is the author agreeing with himself. Spawn a checker for it.
- **A re-check must not collapse into the parent thread** re-reading its own diff — the commonest
  shape, because it is the cheapest.
- **Nor into the round-1 agent re-contacted.** That agent carries its own prior conclusions, which is
  the same contamination one level up. **"Fresh" means a new spawn**, every time.

**What the fresh checker receives — and it differs by gate.** In every case it gets **none of your
conclusions about whether the fix worked**; that is the exclusion Part 1 already draws (it withholds
your *conclusions*, not the instructions the checker needs).
- **Acceptance gate (step 7), Class A — re-run Part 1's recipe unchanged:** the acceptance criteria
  verbatim, the resolved `$BASE`, and the commands under **Verifier runs**, with nothing added. The
  criteria are the yardstick, so a round-2 checker that re-derives met/not-met from scratch is *more*
  independent than one handed a list of claimed repairs. **Do not relax Part 1's `ONLY` here** — a
  claimed-repairs list is a claim, which that list exists to exclude.
- **Acceptance gate, Class B — the limit case is live today and needs its own recipe.** Where the
  finding was the *absence* of a guard (behavior altered, no test added — read straight off the
  diff, so it needs no apparatus), the re-checker receives the change as it now stands plus the
  behavior the missing guard was meant to cover, and none of your claims about the test you added.
  It answers **by reading the new test's assertions**: do they pin the *mechanism* that would
  break, or only an *outcome* a broken implementation would still produce? **If it cannot tell,
  that is a dirty result, not a clean one.**
  **The spawn prompt must carry two things the checker would otherwise never see**, since it does
  not read Part 2: the *asserting the outcome is not asserting the mechanism* distinction **quoted
  verbatim** — that is the yardstick, and without it the checker has the question but no criterion —
  and that it **must not edit, break, or execute code to decide**, since the prohibition on
  improvising a mutation does not otherwise reach it, and a checker that breaks the code to see what
  fails has done the one thing this gate forbids.
  Part 2's "only mutation detects it" is **not** in tension with this: that is about *hunting*
  survivors across a whole suite, where the at-risk behavior is unknown. Here the finding **named
  the behavior in advance**, so the read is one named behavior against one assertion — bounded, and
  it does not reopen the deferred apparatus.
  (What a re-check of a *surviving mutant* receives is specified with the mutation apparatus, not
  here; only that it, too, is a fresh instance is fixed above.)
- **Code review (step 9) — the change as it now stands, plus the list of what you claimed to fix.**
  Review has no fixed yardstick to re-derive from, so that list is what gives the checker something
  to test rather than a blank re-review. It **reads the change itself and reports what it saw** — a
  claimed fix is a claim, not evidence — and states for each whether the code now does it, citing
  `file:line`. **One lighter checker**, not a re-run of the full finder fan-out. But it reviews the
  change *as it now stands*, so **anything the fixes broke is in scope**: a defect the fix commits
  introduced is a finding even though no one listed it. "Lighter" bounds the fan-out, never the
  checker's licence to object.

**The bound — one fresh re-check, then escalate; there is no ladder.** The fresh re-check **is**
round 2 of the 2-round cap each gate already carries, never a round on top of it. If round 2 comes
back dirty — **whether it is a finding round 1 raised or one only the fix introduced** — escalate to
the human; there is no round 3. Cost: **one extra subagent per dirty class per iteration** — so two
at the acceptance gate when Class A and Class B are both dirty, since their inputs differ and cannot
be merged into one checker. Bounded either way, and it cannot grow into an unbounded ladder.

**Journalling it.** A fresh re-check is a distinct subagent invocation, so it increments
`subagent-runs` (one run = one subagent invocation — progress.md → the Budget line).
**A journal recording a re-check while `subagent-runs` did not move
records a re-check that did not happen** — the parent re-read its own work and narrated otherwise.

**Why "be more careful" is not the remedy.** This defect survives authors who have just read the
finding and are actively fixing it — sharpest where one survived inside a commit **whose own subject
line named the defect class**. The belief that produced it is what writes the fix. Vigilance is not
a control, which is why the answer is a different checker rather than a more careful one.

**Convergence & the resting states.** When nothing is selectable, step 1 classifies the run
into one of four outcomes (tested in order: hold → parked → complete → pending) and appends a
`progress.md` **run-state sentinel**; step 0 reads the **most recent** sentinel by append
order (last-wins, since the log is append-only) and acts only on it:
- **`RUN COMPLETE — <run-slug>`** (terminal) — every row is terminal (`done`/`deferred`/`blocked`).
  Summarizes counts + any blocked/deferred items; the orchestrator stops and reports, and a later
  re-invocation short-circuits without re-scanning.
- **`RUN PARKED — awaiting <condition>`** (resting, **non-terminal**) — all *workable* rows are
  terminal but ≥1 `parked` row awaits an external event (a release cut, a dogfood window). A
  re-invocation short-circuits (step 0): it runs only the cheap roster reconciliation
  + a `queue.md` selectability re-derivation, then re-reports parked **without** the expensive
  per-row live reconcile / resume — until the human explicitly releases a **named** condition
  (which flips only the `parked` rows awaiting *that* condition back to `routed`, appends a
  superseding `RUN RESUMED` sentinel, and leaves rows gated on other conditions parked) or a
  pulled-in joiner / cleared dep makes work selectable again. This is what stops a release-gated run
  from re-reaching a *new* conclusion on every re-fire (the "converged-pending-release"
  instability). Distinct from an *interrupted* row needing resume (see Resume): a valid PARKED state
  has no non-terminal pipeline row, so resume is safely skipped.
- **held / pending** (no sentinel) — a `hold` row needs the human now, or a row is still `blocked`
  on an open in-run dependency; the orchestrator reports and stops without a sentinel (the run is
  not complete and not cleanly parked).

**Guardrails:** iteration/budget caps live in the `queue.md` header (`iteration-cap:`/
`subagent-cap:`) and are checked at iteration start against the ledger — **advisory in manual
re-invoke (journaled + surfaced, not gating — the human who invoked is the budget authority),
halted by the driver**; one PR at a time; stuck-detection (repeated error signature) → escalate.
The C1 append-only guard hook protects append-only logs once the loop commits its own work.
