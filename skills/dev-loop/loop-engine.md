# Loop engine — generic operating procedure & semantics

This is the **project-agnostic engine** for the supervised dev loop: control flow, gate /
convergence / resume semantics, the ledger format, the router procedure shape, and the budget
machinery. It contains **no project-specific values**.

Every name in `CAPS` (`BACKLOG_SOURCE`, `LEDGER_ROOT`, `SCOPE_AGENT`, `DESIGN_AGENT`,
`CODE_REVIEW`, `PRIORITY_LABELS`, `ARCHITECT_TRIGGERS`, `SOURCE_LAYOUT`, `LINT_CMD`/`TYPE_CMD`/
`TEST_CMD`/`HERMETIC_TEST_CMD`, `BRANCH_FMT`, `COMMIT_CONV`, `MERGE_METHOD`, `RELEASE_SCHEME`, …)
is bound in the per-project **`loop.config.md`**. **Read that config first** — this engine depends on the
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
   procedure below. Otherwise find the **most recent** run-state sentinel in `progress.md` — the
   last of `{RUN COMPLETE, RUN PARKED, RUN RESUMED}` by append order (the log is append-only, so
   a superseded sentinel still sits above; last one wins) — and act only on it. **Find it by
   searching the file for those three strings and taking the last hit that is a sentinel; never
   bulk-read the journal.** That file grows without bound, a bulk read is capped **silently**,
   and a cap drops the end — which is where last-wins puts the answer, so that failure is
   invisible and always in the wrong direction. The search owes two things a read does not: the
   journal *discusses* sentinels in prose and a discussion is not one; and if you cannot tell
   which hits are sentinels, or cannot confirm the search covered the whole file, **STOP and ask
   the human** — acting on the wrong sentinel either re-enters a terminal run or releases a park
   nothing released. Then:
   - `RUN COMPLETE` (see Convergence) → report done and STOP; do not re-scan (the run is terminal).
   - `RUN PARKED — awaiting <condition>` (see Convergence) — the run finished all *workable* rows
     and rests on an external event:
     - **If this invocation explicitly releases the park** (the human names a met condition — "the
       cut is out, resume"): perform the concrete un-park mutation, **scoped to the released
       condition** — flip back to `routed` (retain Route, clear the `awaiting:` marker) ONLY the
       `parked` rows whose `awaiting:` condition the human named; leave rows still gated on *other*
       conditions `parked` with their markers intact (if which rows a release covers is ambiguous,
       ask — do NOT flip all, that would prematurely release a still-unmet gate). Append a `RUN
       RESUMED` sentinel (now last-wins) and continue to step 0.2; any rows left parked simply
       re-append `RUN PARKED` at the next step-1 pass (last-wins over `RUN RESUMED`), which the
       existing machinery handles. A bare re-fire (e.g. the `/loop` driver) does NOT release the
       park.
     - **Otherwise take the cheap parked path (no full re-scan):** read `queue.md`, take
       `progress.md` by the same searched read (never a bulk one — this is the path that exists to
       be cheap, and the journal is the largest file in the ledger), run the step-1 roster
       reconciliation (the one scan a parked run still owes —
       this is how `BACKLOG_SOURCE` drift is still caught), then **re-derive selectability from
       `queue.md` alone** (no git/PR reconcile). If that produced selectable work (a joiner the
       human pulled in, or an in-run dep that has since cleared) fall through to step 1 **at
       selection** (the reconciliation just ran — do not repeat it); otherwise STOP and report
       "parked — awaiting <condition>" **without** running the step-3 resume or any per-row live
       reconcile — skipping resume is provably safe **for rows** here (a valid PARKED state has every
       non-`parked` row terminal, so no interrupted pipeline row can coexist). It proves nothing about
       state with **no** row, which no row-status argument constrains.
   - `RUN RESUMED` or no sentinel → continue to step 0.2 (a released or never-parked run runs
     normally).
2. Read `queue.md` (note its `mode:` / `graduated-routes:` / `plan-gate:` header and any
   `hold`/`parked` rows) and the tail of `progress.md`.
3. **Resume before selecting (see the Resume procedure below).** **Recognise each issue row's
   Status first, then classify it** — the three Status sets are closed (Ledger format → queue.md),
   and a Status in none of them is unrecognised: **STOP and ask the human** rather than deciding
   what it probably meant. Classify a recognised Status thus: a **pipeline** status other than
   `queued`/`routed` is *interrupted*; `hold`/`parked` rest (below); a terminal status takes no
   resume action. Test
   membership against the vocabulary rather than by excluding a list of statuses that rest — an
   exclusion test silently absorbs anything it has never heard of into *interrupted*, which is the
   guess this ordering exists to prevent. If any row is *interrupted*, a prior iteration was cut off. Reconcile it against
   LIVE git/PR state as the source of truth — branch exists? PR open? already merged? CI
   status? — plus the working tree (status is only a coarse anchor; git wins on conflict),
   then re-enter the pipeline at the matching stage and FINISH that issue BEFORE selecting a
   new one. This is what makes "one PR at a time" hold across `/clear`/compaction. A `hold` or
   `parked` row is NOT an interruption: skip it here — a `hold` stays held until the human
   releases the merge, a `parked` row stays gated until its external condition is released (step
   1); neither blocks working other issues.

   **Then run the orphan scan: look for an open PR that no row covers.** The scan above classifies
   *rows*, and a row is created for every backlogged issue at init — so most interruptions do leave one. External state can
   still exist with no row behind it: work that closes no issue and was never queued, a ledger lost or
   replaced (it is gitignored, so it can be absent or stale while the PRs it described are still
   open), or a PR left open by an earlier run. Enumerate the repo's **open PRs**.

   **Then decide what each one is, default-deny.** These are the only things that are **not** an
   interruption: a PR belonging to **any `queue.md` row the scan above already classified** —
   terminal, resting (`hold`/`parked`), or interrupted, because that scan owns those and this one
   exists only for state no row covers; and work you can **positively** attribute to a human or
   another tool rather than to this loop. **Everything else is an interruption**, and **if you cannot
   tell, it is one.**

   **For every open PR this leaves classified as an interruption, STOP and report it, naming the PR;
   do not select new work until it is resolved.** Any open record in `progress.md` is evidence to
   report alongside it. **This scan detects and halts; it does not reconcile or reconstruct** — live
   state can tell you a PR exists, but it cannot tell you which gates ran on it. Resolving it is the
   human's: they add the row,
   close or merge the PR, or tell you whose it is.

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
  roster (curation)`) so it self-dedups; on "eject", an in-flight leaver (`planning`..`in-acceptance`,
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
`DESIGN_AGENT` with the plan **in the order below** — the freeze comes first; address
`blocking`/`important` concerns before coding. Skip for docs
and trivial research.

**Instruct it verdict-first** (Verdict-first invariant, under Gates): a complete ruling on every
question you put to it, then depth with whatever remains. This agent has no prompt template of its
own — its definition is user-global and you may not edit it (Tool surface) — so this sentence at the
invoke site is the whole of the invariant's reach here, and it is weaker than a template for that
reason.

**Do these three things in this order.** The order is the mechanism, not presentation: freeze, then
invoke, then apply. Executed in any other order the step-5 diff compares a text with itself and the
always-on stop passes silently.

**(a) FIRST, before you invoke `DESIGN_AGENT`, freeze the plan's approach.** Copy `## Approach`
verbatim into a
`## Approach as reviewed (frozen before the design gate) — write-once, do not edit` block in
`issue-<N>.plan.md` (the heading is fixed and must match the template in Ledger format exactly —
step 5 looks for it by name). That block
is the **pre-image** step 5's materiality test diffs against — without it the test has nothing to
compare and degrades to self-assessment, which is what it exists to replace. (The ledger is
gitignored, so there is no git pre-image to recover instead.) The freeze is owed whenever you are
about to consult `DESIGN_AGENT` — here, or at step 5 where that step first consults it; an architect
pass that never happens can rewrite nothing.

**A freeze taken after the agent has returned is not a pre-image.** It copies the already-redirected
text, so treat the block as **absent** — which step 5 reads as material. Never back-date one.

**(b) THEN invoke, and (c) write the outcome into `## Approach` before step 5 — not at implement
time.** "Address the
concerns before coding" is satisfied too late if you carry the architect's rulings in your head to
step 6: `## Approach` would still read exactly as frozen, and step 5's diff would come back **empty
on precisely the run the gate exists to catch** — the always-on condition reporting "no material
change" by *literal compliance*, on the run where the architect rewrote the plan. **This bites under
every `plan-gate:` value, and `always` is not a reprieve from it.** Under `conditional` the row
auto-approves outright; under `always` the human is stopped but shown a diff that says nothing
changed, which is the same failure wearing a stop as a disguise — the gate exists to show them
*what* the architect changed, and an empty diff withholds exactly that. **You** perform this edit, not the agent — `DESIGN_AGENT` returns its review and
**never writes to the tree** (Tool surface); **you** record the outcome wherever this project
records architect decisions (an issue comment, an issue-body marker, or a decision-log entry — see
step 4's write-once note under Resume). So an unedited `## Approach` is the orchestrator's omission
and never evidence that nothing changed. Adopt, adapt, or decline each `blocking`/`important`
finding **in the plan text** first; a declined finding is recorded with its one-line rationale, and
a decline that alters no text is itself the record that the approach stands.

**A ruling that belongs in another section still gets a line in `## Approach`.** Step 5 diffs
`## Approach` and nothing else, so an AC reinterpretation written only under `## Acceptance criteria`
or `## Risks / open questions for human` — and an approach-level redirect on a `research`/`docs` plan
whose `## Approach` is thin — is invisible to the test. Record it where it belongs *and* note it
there, or the one materiality axis this step also flags as an issue-amendment hazard never reaches
the gate.

**The block is write-once: if it already exists, never rewrite it.** Re-running the copy after the
architect has edited `## Approach` would overwrite the pre-image with the post-architect text — the
step-5 diff would then come back empty and the gate would **silently pass**, which is precisely the
failure the test exists to catch. This is the same write-once discipline Resume already applies to
this step's other side effect (the recorded architect outcome, however this project records it);
both are stated there.

### 5. Human gate (posture set by `plan-gate:` — plus one always-on condition)
**Read `plan-gate:` from the `queue.md` header** (Ledger format → queue.md). That field, and never
`mode:`, sets this gate's posture — `mode:` gates the merge gate only (step 11), never this one:
- **`plan-gate: always`** — what Initialization writes under `mode: calibration`. **STOP for plan
  approval on every issue.** Whether to stop is not a judgment call under this value. **What you
  put in front of the human still is** — work through the rest of this step before stopping, and in
  particular evaluate the always-on condition below and prepare its frozen-vs-live diff for
  presentation. Stopping with the plan but without that diff satisfies this bullet and still fails
  the gate.
- **`plan-gate: conditional`** — what Initialization writes for a project with prior route
  graduation. Stop on the judgment conditions below, plus the always-on condition that follows them.

**Read the field, never derive it from `mode:`.** Those are the values Initialization *writes*, not
a rule for computing one — the fields are independent afterwards, so a run may legitimately sit at
`escalation-only` with `plan-gate: always`. The case this distinction exists for is the common one:
a ledger created before this field existed, under either mode, has no `plan-gate:` line at all, and
it reads as `always` by the rule below — never as `conditional` inferred from its `mode:`.

**An absent or unrecognized value reads as `always`.** A ledger written before this field existed,
or a typo (`plan-gate: alway`), gets the **over-gating** reading — never "conditional by
fallthrough". Same default-deny posture as every other gate: the failure that costs you an
unnecessary approval is recoverable, the one that skips it is not.

Under **either** value this gate is **value-first**: present the step-3 value framing (user-story
map / value statement) alongside the approach, and treat a **non-credible value story — no plausible
user, or no checkable falsifier — as itself a reason to STOP**, not just ambiguous ACs.

**Under `plan-gate: conditional`**, present the plan and STOP for approval when: the value story
doesn't hold; acceptance criteria are ambiguous; the change is risky/irreversible; SCOPE/DESIGN
agents disagree or punt; or you are otherwise unsure. Otherwise proceed (note "auto-approved" + why
in the journal). **Under `plan-gate: always` there is no "otherwise"** — every issue stops, and
"auto-approved" is never a legitimate journal entry for this gate. Route scope/value questions to
`SCOPE_AGENT` and design questions to `DESIGN_AGENT` BEFORE escalating to the human — **instructing
either verdict-first** (Verdict-first invariant, under Gates), since a consult that first runs *here*
is an architect pass on this engine's own terms (below) and owes the same instruction step 4 gives.
Under either value — `always` removes the judgment call about *stopping*, never the consultations that inform
what you present. On approval — the human's, or under `conditional` only, an auto-approval —
advance the row to `plan-approved`.

**One stop condition is ALWAYS-ON.** The conditions above are judgment calls; this one is not, and
it fires under **every** mode **and both `plan-gate:` values**. Route graduation cannot reach it —
`escalation-only` loosens the merge gate only, so a graduated route still stops here:

**Under `plan-gate: always` this condition is not moot, and skipping its diff is a silent
regression.** `always` subsumes the **stop decision** — you were stopping anyway — but it subsumes
**nothing about the record**. Take the frozen-vs-live diff and write its `- Plan-gate:` line on
every iteration that reaches this step, whatever the field says. Reasoning "we stop regardless, so
the diff is moot" kills the mechanism below while leaving every word of it in place: the stop still
happens, the prose still reads correctly, the suite stays green, and the evidence this condition's
own falsifier is read against silently stops accruing. **A posture that makes a gate stricter must
never be a reason to record less.**

- **The architect materially changed the plan.** A *decisive* architect that **redirects** the plan
  is a **stronger** reason for a human look than one that punts or disagrees, not a weaker one: the
  plan you would have approved is now a different plan, and nobody has seen it. Read that inversion
  literally — **"the agents agreed and ruled cleanly, so I proceeded" is not a reason to auto-approve,
  it is the trigger.** (The condition above it keys on disagreement; this one keys on the opposite,
  and both stop.)

  **The test is a diff, not a self-assessment.** Compare the frozen `## Approach as reviewed (frozen
  before the design gate) — write-once, do not edit` block (step 4) against the live `## Approach`.
  The change is **material**
  if any of: a step was added, removed, or reordered; the files-to-touch set changed; a different
  fork was chosen; an acceptance criterion was reinterpreted. Pure wording is not material.
  **The list is sufficient, not exhaustive — extend it, never prune it**, and **if you are unsure
  whether an edit is material, it is material** (default-deny, as at every other gate). The
  catch-all is what makes extension safe and pruning a regression.

  **An empty diff is only evidence when both halves are present. Architect ran + block absent ⇒
  material ⇒ STOP.** A missing pre-image is not "nothing changed" — it is a gate with nothing to
  read, and reading it as a pass restores the self-assessment this test removes. It happens for
  ordinary reasons (a crash between invoking the agent and the freeze, a hand-edited plan file, an
  earlier iteration that predates this rule), none of which is evidence about the approach. Where
  the architect was **skipped**, the block is legitimately absent and the condition is not due at
  all — the distinction is whether the gate ran, never whether the artifact is there.

  **"Skipped" means no architect pass ran at all — not merely that step 4 skipped it, and not
  merely that `DESIGN_AGENT` by that name was never invoked.** Two cases the narrow reading loses:
  this step routes design questions to `DESIGN_AGENT` before escalating, so the agent can first run
  *here*, after step 4 declined it; and where the binding is unrunnable, the inline composition you
  run in its place (Gate-outcome invariant) **is** an architect pass in substance. **The freeze is
  owed by either, at step 4 or at step 5**: freeze `## Approach` before consulting, and apply the
  outcome to the plan text before deciding. A consultation at this step that redirects the plan is
  material on the same terms — otherwise the one architect call the freeze rule forgot to name
  becomes the path the whole condition is bypassed through, journalled `n/a: architect skipped`
  while a pass was in fact run and did in fact redirect.

  **A consultation *after* this gate is out of scope here, deliberately.** The pipeline offers no
  path back to step 5 from `plan-approved`, and an approved plan later invalidated by a fresh
  consultation is the plan-currency problem (#89, in the same family as #33), not this
  condition. Do not improvise a stop for it here: with no pre-image to diff, any rule stated at this step would be self-assessment — the very
  thing this condition exists to replace.

  **Present the frozen-vs-final diff at the stop**, not a re-read of the whole plan. The cost of this
  condition is the human's attention, and a diff is what keeps it cheap.

  **Journal what the diff returned, and journal it HERE — when the gate resolves, not at step 12.**
  Write one of the **four** `- Plan-gate:` spellings (enumerated once, in Ledger format →
  `progress.md`; do not re-derive them from this paragraph). The ledger format licenses a block "per
  gate decision", and writing it now is what makes the record survive: a `/clear` between this step
  and step 12 otherwise leaves the resuming orchestrator owing a line with no evidence of what the
  diff returned, and the cheapest compliant line asserts a diff it never took. Absence of the line
  is **not** a record that the diff was clean: a run
  that never took it and a run that took it and found nothing are otherwise identical in the ledger,
  which is the silent-inertness shape the `- Hermetic:` and `- Restore:` lines exist to prevent. It
  is also the only evidence this condition's own falsifier can ever be evaluated against.

  **A narrowing or reduction of an acceptance criterion is never absorbed here.** The gate may adopt
  a rewrite; it may not quietly deliver less than the ACs ask. Reading down an AC's *wording* while
  delivering its intent is interpretive and belongs to the gate; **reducing its intent is an issue
  amendment** — record it on the issue and file the removed scope, or the acceptance gate (step 10)
  will certify an AC that was never met.

### 6. Implement (you, the parent thread)
Advance the row to `implementing`. Create the branch (`BRANCH_FMT`). Implement code + tests +
docs per the plan. TDD where it fits (write failing tests, commit, do not modify tests later).
Run `LINT_CMD`, `TYPE_CMD`, and `TEST_CMD` — they are **independent signals**, and **each command's
exit status is its verdict**: a non-zero exit is not green however the output reads, and one
command's zero is not evidence about the others. Read each output to completion to find *what*
failed — a command can print an early `all checks passed` line *above* a later failure, so no
single line, first or last, is the result. Fix and re-run until each exits zero. Do NOT stage
unrelated pre-existing working-tree changes.

**Stage explicit paths; never blanket-stage.** `git add -A` / `git add .` take whatever the tree
holds at that instant, and from the moment you spawn a subagent until you have cleaned up after it
that includes files you did not write. The window is **not** "while the agent runs" — an isolated
worktree outlives the agent that wrote to it (Tool surface), so the exposure runs until the parent
removes it. So: **name the paths you mean**, and **read `git diff --cached` before every commit**
rather than trusting what you meant to stage. It applies at every commit boundary — step 7, the fix
commits at step 8, **the editorial sweep's own commit at the close of step 8**, **and the acceptance
gate's own fix commits at step 10** — not just the first.
(Step 9 defines no commit of its own; where a security finding needs code, it is fixed and committed
under step 8's rule.)
The last of those is the newest and the most exposed: the acceptance gate's mutation pass takes a
copy of the tree, so a blanket stage there can land a deliberately-broken one.

**Know what you are looking for**, because the worst case does not look like the mess it is. A
blanket `git add` over an isolated worktree nested in the repository does **not** stage its files:
git records a single **gitlink** entry (mode `160000`, a bare commit SHA) and prints an
`adding embedded git repository` warning. So `git diff --cached` shows one `Subproject commit` line,
not the wall of files you might scan for — easy to skim past, and it lands a directory that clones
empty and points at a commit no remote has. Unstaging it is `git rm --cached <path>`, not a file
unstage. Deliberately-broken code and scratch files are the loud version of this failure; the
gitlink is the quiet one.

**`HERMETIC_TEST_CMD` — the declared-offline tier, run with the network actually cut.** A project
that documents a hermetic test tier ("unit tests are offline — no network, no DB") holds an
invariant **no other command checks**: `TEST_CMD` runs with the network up, so a test that quietly
reaches the internet is green, and green *for the wrong reason* — the live resource silently
displaces the fixture the test meant to exercise, changing what is under test without changing
anything that is asserted. A documented invariant nothing enforces is the defect class this engine
exists to name; where a project binds this parameter, the tier gets run for real.

**Due when** the row's Route is `code` **and** the change adds or modifies **at least one test** —
any test, not only one you judge to sit in the tier. Once per issue, not per test run. Deciding
which files the tier covers would mean parsing the bound command, which is the project's business
and not this engine's; over-running costs one command, under-running is the entire defect. Its exit
status is its verdict on the same terms as the three commands above.

**What the binding must do — and what this engine cannot check.** The bound command must block the
network **at socket level**. *A proxy still resolves DNS*, so a proxy-based block can leave a test
looking offline while it is not — that is the specific trap, and it is why "socket level" is the
requirement rather than "somehow offline". This engine reads an exit status and **cannot inspect how
the block was implemented**, so socket-level is a requirement **on the binding's author**, never an
enforcement this engine performs — do not read or restate it as one. Check it once, when writing the
binding, with a **direct-IP** connect (direct IP because DNS is exactly what a proxy still services):

```bash
# under the block: must FAIL. Without it: must connect. If both connect, the block is not socket-level.
<the block> python3 -c "import socket; socket.create_connection(('1.1.1.1', 443), 3)"
```

**A test that passes under `TEST_CMD` and fails under `HERMETIC_TEST_CMD` is a finding, reported as
prominently as a bug** — it is not flake and not an environment problem. It was passing for the
wrong reason, and the gate has just told you which test and what it was really doing. Fix it, and
**preserve what it asserts**: three escapes turn the tier green while destroying the thing the tier
was for, and all three are forbidden —
1. weakening or removing the block;
2. moving the test out of the tier without saying so;
3. **changing what the test asserts** — skipping or xfailing it under the block, or stubbing the
   fetch so it no longer exercises what it did. This is the likeliest escape and the hardest to see,
   because it is the incident in reverse: cutting the network *changes what the test exercises*, so
   a "fix" can green the tier while silently reducing coverage.

**Re-run the tier under the block after the fix** — the exit status is the verdict, not your
reading of it. "Once per issue" bounds the *trigger*, never the re-runs a finding forces.

Whether the fix **preserved what the test asserts** is not an exit status, and you are the one
reader who cannot judge it: you wrote the fix. Send that question to a **fresh instance** — a new
spawn, not you and not whoever wrote the test. **Its prompt carries five things**, and the last
three matter most because they are rules it cannot see from where it sits: the test as it now
stands; the behavior the test covered before; that it must decide by **reading**, never by running
or altering anything; that it must **say plainly when it cannot tell — which is a dirty answer, not
a clean one**; and the **Verdict-first invariant** (Gates) — the complete answer first, depth after.
Withhold your conclusions. An unprompted checker hedges, and a hedge read as agreement is how
this gate goes quietly soft.

This borrows the *shape* of the Fresh-re-check invariant without being governed by it: that
invariant covers the two gates carrying a round cap (step 8 and step 10), and this gate carries none —
it blocks until green, like any other step-6 command. So there is no round to count and no cap to
consume. **If the fresh read comes back dirty, or cannot tell, escalate to the human and STOP** —
do not absorb it, and do not fix-and-re-ask in a loop. A hermetic finding you stop on never reaches
the merge gate; the always-escalate entry at step 11 is there for the other path, where a row somehow
arrives carrying one.

**A test added later re-arms the trigger.** Step 8 and step 10 routinely add tests — the Class B limit
case is fixed by adding one, and review findings often are too. A gate journalled `n/a: no test
change` at step 6 and then handed a new test at step 10 has left the tier unrun on an issue that
*did* add a test, which is precisely what this gate is due on. Re-evaluate the trigger before you
commit the fixes, and let the `- Hermetic:` line record the final state rather than the first
reading.

**Every iteration leaves a record of this gate** — a `- Hermetic:` line in the iteration
block, or, where the gate produced no verdict at all, the `- gate-error:` that carries it instead (Ledger format → progress.md). This gate blocks at this step, so its findings are resolved
before the acceptance gate ever runs: without the line it leaves **no trace at all**, and "reported
as prominently as a bug" would be discharged by the blocking alone. **Never record it in
`mutation-survivors`** — that slot records whether a guard guards, a different question, and its
`n/a` list is closed at two reasons neither of which is about this gate.

**The four config states — and why this gate needs them spelled out.** Every other gate's due-ness
is settled by route and trigger *before* its binding is read. This one is different: **whether a
hermetic tier exists at all is knowable only from the binding**, so a missing row is genuinely
ambiguous, and the fail-safe reading has to be written down rather than inferred.

| `HERMETIC_TEST_CMD` is… | Outcome |
|---|---|
| a command | due when the trigger above fires; **exit status is the verdict** |
| `—` **plus a reason** | `n/a: <that reason>` — a project with no hermetic tier is genuinely not gated, and this is the only clean way to say so |
| `—` with no reason | a blank, not a "not applicable" — the reason is what distinguishes them; on a row the trigger fired on, escalate |
| `TODO`-valued, **or the row is absent** | on a row the trigger fired on, **unknown — which is not the same as not-due**: static "cannot run" (Gate-outcome invariant), no inline composition exists, so **escalate to the human**. On a row it did not, write the trigger's own `n/a` reason |

**"The block would not run" is never a reason to proceed.** A namespace tool refused by a hardened
host, or a blocking plugin that is not installed, produces a non-zero exit — and the tempting
reading, *can't apply the block, so there is nothing to check*, is the silently-skipped gate in new
clothing. **Neither outcome is a pass**, but they are journalled differently, so the discriminator
has to be stated rather than left to judgement. It is **whether any test ran**:
- **The wrapper failed before the tier started** — command not found, permission denied, the
  namespace refused, the plugin missing. No test was executed, so there is no verdict about the
  tier: `- gate-error:` and **escalate** (Gate-outcome invariant). The iteration STOPS.
- **Anything else** — the tier ran and something in it exited non-zero. That **blocks** as a dirty
  tier, and you fix it under the finding rules above.
- **If you cannot tell which you have, treat it as the `- gate-error:`.** That is the fail-safe
  branch: it stops and asks a human, where guessing "dirty tier" would have you rewriting a test to
  satisfy a block that never applied.

**Authoring rule — a claim that a protection exists must name it, and the name must resolve.** A
comment — or, where the deliverable is itself prose an agent executes, any claim the prose makes
about the tree — asserting that a test, guard, or invariant exists **elsewhere** must **name it** —
the test name, `file:line`, or the invariant's own name where this document defines one — and you
must **confirm the named thing exists and asserts what you claim** before writing the comment. An
unnamed claim is worse than no comment: the next reader — human or agent — stops looking, so the
comment *defeats* the reviewer rather than merely failing to help, and it does so most effectively
when it sits directly on top of the gap. A **named** claim that does not resolve is worse still: it
buys that credibility with a citation the reader is now less likely to check. A comment that
misdescribes the code it sits on is the same defect without the citation — write neither. This is
an authoring rule, not a binding; step 8's finders check the diff against it.

**Before you leave this step, walk the acceptance criteria once and name a `file:line` for each.**
For every AC, point at the change that satisfies it. If you cannot point at anything, you have not
implemented it — go back and do so now.

**This is a tripwire, not a gate, and it is explicitly not sufficient.** It exists because of where
the acceptance gate now sits. That gate is step 10, after the PR is open, after CI is green, after
review and after security — so "you did not implement AC-3 at all" is discovered at the most
expensive point in the pipeline available. Under the old ordering it cost one cheap fix loop with no
PR and no CI. This walk is a cheap catch for **gross omission** and buys nothing else:
- it does **not** substitute for step 10, which still runs unconditionally and independently;
- a `file:line` you can name is **not evidence the criterion is met** — only that something was
  written toward it. Judging *met* is the fresh verifier's job, on the diff, not yours on your
  memory;
- **do not journal it as a gate outcome.** It produces no verdict, so it cannot be recorded as one
  (Gate-outcome invariant), and a `- AC-verify:` line may only ever carry step 10's result.

It does not conflict with the rule that the parent cannot self-certify. That rule is about **test
assertions** — whether a guard would notice a regression, which is exactly what you cannot judge
about your own work. *Whether a criterion was implemented at all* is a different question, answerable
by looking, and the one reader who can answer it fastest is the one who just wrote the change.

### 7. Commit + PR
Commit with correct `COMMIT_CONV` scope — **staging explicit paths and reading `git diff --cached`
first** (step 6), since this is a commit boundary like any other and the tree may have gained an
agent's files since you last looked. Open the PR; **replicate `PR_TEMPLATE` fully** in
the body; make the Security-review choice up front. Advance the row to `in-pr` and record the
PR number.

**Then append the iteration's open record to `progress.md`, before you wait for CI.** Write it as
Ledger format → `progress.md` gives it; that template is the one statement of what it carries, so do
not re-derive the fields here.

**Write it now rather than at step 12, for the reason step 5 journals its `- Plan-gate:` line where
that gate resolves.** A `/clear`, a compaction, or a crash between this step and step 12 otherwise
leaves an **open PR with no ledger trace at all**. Step 0.3's orphan scan is the backstop for that
case; this record is what the scan reports alongside the PR, so whoever resolves it has the issue,
the branch and the PR identity on disk rather than a bare stranger. **Do not
read this as making `progress.md` self-sufficient** — the standing contract is `queue.md` +
`progress.md` + **live git/PR state**, which wins on conflict (Resume). This record makes an
iteration *recoverable by the human*, not the ledger *authoritative*.

Then wait for CI; fix until green.

### 8. Code review
Advance the row to `in-review`. Run `CODE_REVIEW` on the diff.

`CODE_REVIEW` names a **procedure you run, not a command you call**. The default — and the pattern
that works in practice — is **parallel finder subagents over `git diff main...HEAD`, plus a pass
that confirms each finding**, journaled under the gate's name. (`main...HEAD` is the right form
*for round 1*: step 7 has committed and opened the PR, so the branch head **is** the change. A round
*after* the first reads a narrower range — see the scoping rule at the end of this step. The
acceptance gate at step 10 deliberately diffs the **working tree** instead, and still does now that
it too runs post-commit — but for a changed reason: it is the gate of record for the merge
candidate, so it must be able to **detect** a fix that is written but not yet committed. Detecting
one is not certifying it; step 10 requires such a fix committed before it certifies. **These bases
differ on purpose — do not "fix" any of them to match another.** There are three, and each answers a
different question: round 1's `main...HEAD` (the whole change), a later round's `<reviewed>..HEAD`
(what no round has read yet), and step 10's working tree (the merge candidate, committed or not).)
Running those finders at once is permitted because they are read-only — the **read-only** form the
Execution policy (Tool surface) allows; see it there for what that permission does and does not
extend to. A review skill marked
`disable-model-invocation` is **user-triggered only and cannot be invoked from here at all**: if
`CODE_REVIEW` is bound to one, the gate is unsatisfiable and silently does nothing. Such a skill is
a *human* escalation, never a binding. On finding one bound here: run the finder procedure for this
issue, journal the misbinding as a `- gate-fallback:` line (Gate-outcome invariant) along with the
rebind you recommend, and surface it to the human — **do not edit `loop.config.md` yourself**
(Tool surface).

**Give every finder the issue's acceptance criteria alongside the diff.** You cannot judge whether
code is *right* without knowing what it was meant to do; a finder holding the ACs catches "this
doesn't actually do AC-3", a class the diff alone cannot reveal. (This does not make step 10
redundant — the acceptance gate still runs independently.)

**Give every finder one standing check in its prompt too, whatever angle it is working: flag any
comment or prose claim in the diff that asserts a test, guard, or invariant exists elsewhere
without naming it, names one that does not resolve, or that misdescribes the code it sits on** (the
step-6 authoring rule; where the deliverable is prose, its claims about the tree are such claims).
This is a property applied *within* whatever finders the surface warrants, **not an angle of its
own**, and is **never written into the `code-review=` lens parenthetical** (progress.md → the
Budget line), which records angles only.

**And give every finder the Verdict-first invariant** (Gates): findings on the whole diff first,
depth on any one of them after. A finder that exhausts itself on the first thing it notices returns
a partial reading of the change, which this gate cannot tell apart from a clean one.

**Pick finder angles from the diff's risk surface, not from a fixed list.** Distinct lenses —
correctness; robustness/IO/network/filesystem; reuse/conventions/integration;
production-readiness — overlap far less than repeated passes of the same one, and single-angle
review misses most of what a diff carries. Scale the count with the surface: one light pass on
`docs`, more when the diff touches a production or public-API path. **Give each finder a distinct
lens label, distinct from every other finder's in the same round** — the label is a component of every
finding ID this gate records (below), so two finders sharing one collide.

**Distinct in question, not only in label — a roster may not carry two lenses that would return the
same findings.** State, when you spawn the round, one thing each lens would find that no other lens
in that roster would; **a lens you cannot state one for is the same lens, so run one of them.** Those
differentials are journalled with the roster (below), and that record is the control rather than a
default. **Doubt subtracts under this rule**, so it needs saying that the
general default-deny below — the one that sends an unknown *range* to a FULL round — does not reach
it: that rule governs how much of the change a round reads, this one governs how many lenses read
it. Inverting this one would make it vacuous, since "keep both when unsure" is what it exists to
stop; the record is what keeps it honest instead. **The floor lens below is never the one dropped:
where another lens duplicates it, the other one goes.**

**No per-round lens *ceiling* is fixed here, deliberately** — only the floor below. The corpus
establishes that lenses **duplicate**; it does not establish a number. **Duplication is what the
evidence shows; a count is what it does not.** Choosing one, or a per-route roster, is the
**review-tier matrix** question, which this step does not answer. **This step
deliberately mints no route-to-lens matrix and no fixed roster.**

**One lens is a floor, not a choice: `guard-efficacy`.** The rule above picks angles from the risk
surface, and that judgment stands — this puts a floor beneath it and **never a ceiling**.

**Due when** the round's delta touches at least one path `SOURCE_LAYOUT` does not positively
declare `docs` or `research`. On a round it is due on, the roster **must carry a lens labelled
`guard-efficacy`**. That is one predicate over the round, not a file-by-file test: a single
unmatched path anywhere in the delta arms it. **If you cannot tell whether a declaration covers a
path, it does not — the path is unmatched and the lens is due.**

**This is a path test. Route does not gate it, and neither does whether the delta carries a
guard.** The unmatched reading is Floor 2a's, for Floor 2a's reason (`code` is the Router's
**default**, Router rule 4) — so a project that declares its `research` route by *label* (Router
rule 3) and declares no research **path** gets the floor on that row too. Route-scoping a lens
*inside* this gate would subtract from a gate the Gate table makes due on **every** route; and
conditioning it on finding a guard would let *"there is no guard here"* — the answer this lens
exists to return — be given by the orchestrator instead of by the lens.

**The cost has Floor 2a's shape, and is stated the same way:** where a project declares no inert
paths, every iteration's round 1 carries this lens whatever its route — on a `docs` round that is
the light pass **plus** the floor, since this is a floor and never a ceiling (above). That holds
until the project declares some. That is the safe direction and it is deliberate.

**The floor is round 1's.** A later round of this gate is one lighter checker rather than a fan-out
(below), so it carries no roster and no floor; round 1 is also the round that reads the whole
change, so the floor reads every guard the change carried when the PR was opened.

**A round that owes this lens and does not carry it has produced no verdict.** Spawn the missing
lens before the round resolves; if you cannot, `- gate-error:` and escalate (Gate-outcome
invariant). It is not a round that passed with a gap.

**What it asks.** *Do this change's guards assert the **mechanism** that would break, or only an
**outcome** a broken implementation would still produce?* That question is the Class B limit-case
re-checker's (Gates → Fresh-re-check invariant), and its answering discipline governs here too: the
lens decides by **reading**, never by running, editing or breaking anything, and **"cannot tell" is
a dirty answer** — at this gate a BLOCKING finding, never a no-verdict. It is BLOCKING whatever
class the finder emitted: EDITORIAL is an affirmative claim, and a finding that cannot say does not
establish it, so **Floor 1** below carries it — as does that floor's *"if you are unsure, it is
BLOCKING"* catch-all. Being a reader, it joins the fan-out under the
Execution policy's read-only form like any other finder. **It never mutates** — improvising a
mutation outside the harness is forbidden (AC-verifier → Part 2), and a mutating finder could not
join a fan-out licensed on being read-only.

**What its prompt must carry**, over and above every finder's standing inputs at this step (the
acceptance criteria, the standing authoring check, the Verdict-first invariant, and the
finding-class rule): **(1) Part 2's blockquote, verbatim** — the worked example is what makes the
distinction operable; **(2) that it must not edit, break or execute anything to decide** — the
prohibition on improvising a mutation does not otherwise reach a finder; and **(3) that it must say
plainly when it cannot tell** — the rule making that a dirty answer lives here, where the finder
cannot see it, so an unprompted finder hedges and the gate reads clean. These are the three the
Class B limit-case re-checker's spawn prompt carries, for the same reasons; the fourth it already
has. **Named by content, never by number** — that recipe's items are numbered in another section.
What does **not** carry over is that recipe's antecedent: it is written for a re-check of an
already-found gap, and this lens has no prior finding and no fix in hand. Its **differential** is
fixed by construction — writing its question as its differential is sufficient, and no round need
invent prose for it.

**A lens may find nothing to apply its question to, and returns exactly that — on a delta that
adds or modifies no guard, that is the ordinary outcome, and it is the lens that says so, not
you.**
`nothing to read` is the rendering for a lens that was **due, spawned, and found nothing to apply
the question to** — never the orchestrator's substitute for spawning it, and never the rendering for
a round the floor was not due on (that one is written as not-due, below). It is not a finding here
and does not re-arm the round. **Whether an absence of guards is itself a defect is the acceptance
gate's question, not this one:** step 10 asks it against the **merge candidate**, under Part 2's own
three questions, where the limit case lives. The two gates read different objects, so neither one's
answer is available to the other.

**This lens is NOT the acceptance gate's Class B pass, and neither stands in for the other.** They
ask different questions at different steps against different objects, and conflating them would let
one be journalled as the other:

| | `guard-efficacy` lens (step 8) | Class B (step 10) |
|---|---|---|
| asks | do the assertions pin the mechanism? | does a real mutant survive the suite? |
| method | **reads** the guard | **runs** the harness against a mutated tree |
| object | the round's delta | the merge candidate |
| due when | the floor above says so | Part 2's three questions say so |
| records to | the round's roster record | `mutation-survivors=`, `- Restore:`, the `- AC-verify:` line |

**A surviving mutant is step 10's and only step 10's.** A read cannot establish one — which is why
this is a floor on *reading* and not a second mutation pass — and **neither gate's verdict discharges
the other's journal slot**: a step-8 `guard-efficacy` finding is never written to
`mutation-survivors=`, whose readings are fixed elsewhere and closed. A `guard-efficacy` finding
asserts a proposition about the tree, so **Floor 1 promotes it to BLOCKING** (it is the *test
efficacy* class named in the finding-class list below), and it never reaches the editorial sweep.

**Record the round's lens roster where that round resolves.** Write it into that round's
gate-decision block (Ledger format → progress.md), on the same write-time discipline as this step's
other per-round records — **when the round resolves, not at step 12**. Each entry carries the lens
label, the differential you stated for it, and what it returned; the outcome is written per lens and
is **never inferred** from which findings carry which ID, because those IDs are recorded for
EDITORIAL findings only (below), so a lens whose findings were all BLOCKING would read as having
found nothing. **The label written here is the same string that round's finding IDs carry**, so the
roster and the IDs join on it.

**Every round-1 roster names `guard-efficacy`** — either as an entry with its differential
and what it returned, or as `guard-efficacy — not due: <reason>`. Those are the only two, and there
is no silence. **The duty presupposes a verdict:** a round that produced none writes
`roster: no verdict` and names no lens (below) — the absence of a roster, not a third way to
satisfy this. **An absent *entry* means the lens did not run, never that it was not due**; a round that
owed the floor and whose roster does not name it produced no verdict (above), not a round excused
from it. The renderings, enumerated for the reason `- Restore:` and `- Hermetic:` enumerate theirs —
a shape whose only legal rendering asserts a full roster is a template that pressures you to record
one:
- **`roster: <lens> (<differential>) — <n> findings; …`** — an ordinary round-1 roster. `<n>` counts
  everything that lens returned, of **either** class. Write `0 findings` where a lens returned none,
  and `nothing to read` where a lens found nothing to apply its question to (above).
- **`… ; guard-efficacy — not due: every path in the delta is declared docs or research`** — the
  floor was not due, written **visibly with its reason**, exactly as `- Hermetic:` writes its
  `n/a:`. **That is the only legal reason, because it is the due-when's only conjunct negated, and
  the list does not re-open.** In particular *"no test or guard in the delta"* is **not** a reason:
  the floor is due on such a round, and its lens returns `nothing to read` (above). **If you could
  not tell, it was due and this rendering is unavailable.**
- **`roster: none (recheck)`** — a round that is one lighter checker rather than a fan-out (the floor
  is round 1's, above).
- **`roster: no verdict`** — the round produced none; a `- gate-fallback:` or `- gate-error:` line
  carries what happened (Gate-outcome invariant). **Never write lens entries beside it, including a
  `not due:` rendering.** This displaces the naming duty above rather than discharging it — and a
  round that landed here *because* it owed the floor and did not carry it (above) is the failure
  that duty exists to catch, not a round excused from it.
- **no roster record at all** — **unknown, and unknown is not "the floor ran".** Absence cannot
  distinguish a round that recorded nothing from one that carried no floor lens, and the second is
  the failure this record exists to catch.

**Keep the floor lens out of any later tier decision, whatever record it is read off** — the roster
record and the `code-review=` parenthetical (progress.md → the Budget line) both list it. A mandated
lens fires on close to every qualifying round by construction, so counting it toward "the same
lenses keep firing" would answer the review-tier question with evidence this floor manufactured.
Read the tier question off the lenses the risk surface *chose*.

**This is deliberately a lowercase `roster:` record inside the gate-decision block, not a `- Name:`
element, and it is not repeated in the close record.** The per-finding ID record and the declines
record below are specified **here rather than in Ledger format** too. **Never the
`- Code-review:` element, and never the `code-review=` parenthetical** on the `- Budget:` line:
that parenthetical is per-iteration and label-only, while this is per-round and carries the
differential and the outcome. Collapsing either into the other loses that.

**Finding classes — every finding carries one, and only one class re-arms a round.**
"The gate returned findings" is not one state. A guard that cannot fail and a changelog line worded
oddly cost the same full round today, and nothing in the ledger records the difference. Two classes:

- **BLOCKING** — correctness, security, test efficacy (a test that cannot fail), acceptance-criteria
  coverage, anything moving a safety boundary. Re-arms exactly as a finding does today.
- **EDITORIAL** — discharged in one contained sweep at the close of this step.

**"Finding class" and "result class" are different vocabularies and never mix.** A *finding class* is
BLOCKING or EDITORIAL, one per finding, and **only this gate's agents emit one** — its finders, and
the fresh re-checker of a later round (Gates → Fresh-re-check invariant). A *result class* is the
acceptance gate's Class A / Class B, one per result (step 10), and nothing there is ever BLOCKING or
EDITORIAL. Step 9 returns clean-or-findings and emits no class at all. **That is what makes every
EDITORIAL finding known by the close of this step** — not a survey of what the later gates happen to
return, but a rule about who may emit the class. The one exception is written out at the sweep below,
where a round re-armed from downstream reopens the question after the sweep has already run.

**The finder emits the class; you never assign or reassign one.** Put it in the finder's prompt
beside the acceptance criteria and the standing authoring check. Inference by the author is the
judgment this gate exists to remove: an orchestrator under budget pressure will want to read a real
finding as EDITORIAL, and the only structural defence is that the class arrives from outside. What
you may do is **raise** it, by any floor below — **promotion only, never the reverse.**

**Floor 1 — content.** EDITORIAL is the **affirmative claim the finder must establish**: this finding
*asserts no proposition about the tree* **and** *has no behavioral consequence*. Everything else is
BLOCKING. In particular, a finding that something is **false, stale, unresolvable,
self-contradictory, or misdescribes what it sits on** is BLOCKING **whatever path it is on** — that
is the step-6 authoring rule's own class, and where the deliverable is prose an agent executes such a
finding *is* a correctness finding.

**That list is sufficient, not exhaustive — extend it, never prune it — and if you are unsure, it is
BLOCKING.** Stated the other way round, *"EDITORIAL is anything not on that list"*, the triggers
become an enumeration of the **safe** set and a shape nobody enumerated ships: an **ambiguous**
instruction carrying two readings, a **misleading-but-not-false** example, a **fragile**
cross-reference. That is the same enumerable-assertion failure one level up from a topic list. The
catch-all is what makes extension safe and pruning a regression.

**"No behavioral consequence" is itself a judgment about an executed artifact, so it defaults to
*assume there is one*.** Where prose is the product, a wrong sentence is a behavior change.

**Floor 2a — code-route path (default-deny on the layout *default*).** A path is code-route **unless
`SOURCE_LAYOUT` positively declares it `docs` or `research`**. Unmatched ⇒ `code` ⇒ **promote to
BLOCKING**, regardless of content and regardless of what the finder returned. The unmatched reading is
`code` because `code` is the Router's **default** route (Router rule 4), not a fallback this floor
invents.

**Floor 2b — sensitive-surface path (default-deny on an *absent* declaration).** Where the project's
security routing (`loop.config.md`, step 9) declares a path sensitive, **promote**. Here a **present,
path-shaped declaration that simply does not cover this diff is a *known* answer** — no sensitive path
was touched, no promotion — exactly as this step's full-round fallback list already reads it. Only a
**missing, `TODO`-valued or non-path-shaped** declaration is unknown, and unknown promotes. **That
list of unknown-making defects is sufficient, not exhaustive, and it is deliberately not a list of the
safe states** — a stale, ambiguous, self-contradictory or unlocatable declaration is unknown too.
**If you cannot tell whether the declaration answers the question for this path, it does not: treat it
as unknown and promote.** (The fallback list this floor models itself on carries the same two clauses,
and dropping them here would have inherited its known-answer reading without its catch-all.)

**The two use opposite unmatched-readings on purpose, and unifying them is a regression.**
`SOURCE_LAYOUT` enumerates the **exceptions** to a `code` default, so an unmentioned path is `code`;
security routing enumerates the sensitive set **positively**, so an unmentioned path is not sensitive.
Reading 2b's known-answer rule into 2a lets a path no declaration mentions survive as EDITORIAL,
which is fail-open on the default route. Reading 2a's rule into 2b sends every finding to BLOCKING in
any project whose sensitive surface is narrow, which is most of them. **Do not merge these into one
floor.**

**What the path floors cost, stated here rather than discovered later.** They are deliberately blunt,
and their reach is the consequence: EDITORIAL survives only on paths a project has **explicitly
declared inert**. Where source is `code`-route, a stale docstring or a wrong comment *inside source*
promotes to BLOCKING. Where a project declares no `docs`/`research` paths at all, everything promotes
and this mechanism is inert until it declares some. That is the safe direction and it is deliberate.
**Do not describe the saving as larger than it is**, here or in a journal, and **do not state a
measured round saving anywhere in this engine** — whether the classes save rounds is a corpus
question this document is not the place to answer.

**Default-deny over every floor:** an unclassified, unrecognised, or ambiguous finding is BLOCKING.
Never *"it is not on the BLOCKING list, so it is editorial."*

**A worked negative example — the case where the floors disagree, and why content must win.**
Take a project whose deliverable is prose an agent executes, and a change confined to a file that
project's own config **positively declares `docs`**: a contributor guide, say, that ships to no
consumer but that every agent working the repo reads as instructions. A finder returns *"this sentence
says the generated artifact is unreachable by any later release — that is false; the generator is
edited every release."* **Neither path floor fires** — the path is declared `docs`, and it is not
security-sensitive. **Floor 1 does** — the finding asserts a proposition about the tree and says it is
false. So the finding is **BLOCKING**. Decided by path alone it would have been swept in without
re-review, and the round that would have caught what the fix broke would never have run at all. **A
finding that says "this is false" is never editorial, wherever it lives.**

**Recording an EDITORIAL finding — when its round resolves, under an ID stable across the fan-out.**
Write each one into that round's gate-decision block (Ledger format → progress.md), beside the
round's declines and on the same write-time discipline: **when the round resolves, not at step 12.**
Accumulating them only in your context loses them to a `/clear`, and the loss then reads as a
measured zero rather than as an absence. The ID is **`r<round>.<lens>.<k>`** — round number, the
finder's lens, and that finder's own item index. **The lens is what makes the ID stable across the
fan-out**: rounds run several finders at once and each numbers its own items from 1, so
`round <n>, item <k>` collides. Where two finders would carry the same lens label, **distinguish the
labels** — distinct labels are what keep two finders' items apart, so do it when you spawn
them. **A round that is one lighter checker rather than a fan-out has no lens**: write
`recheck` in that position, e.g. `r2.recheck.1`. This is a
**new record in the gate-decision block**, not the `code-review=` parenthetical on the `- Budget:`
line, which records **angles only** and carries no per-finding detail.

**The editorial sweep — one pass, contained, at the close of THIS step.** It is specified here,
beside the classes it discharges, but it **runs last** — after the round paragraphs below, including
the round bound. Read the two together rather than in file order.
Run it when this gate resolves with **no unresolved BLOCKING finding**, as its own commit at this
step's commit boundary, under step 6's explicit-path staging rule like any other boundary. **Take the
set to sweep from every round's gate-decision block in `progress.md`, not from memory** — that is what
the per-finding record above is written for, and reading it back is what makes the record load-bearing
rather than decorative. A `/clear` between a round and this sweep is the ordinary case, not the
exceptional one. They are
not re-reviewed: the finder that raised one already said what to write. **Placing it here is what
makes it cheap and safe** — every EDITORIAL finding is already known (the emission rule above), and
whatever still runs after this step — step 9 where its route makes it due, step 10, and CI — sees the
sweep's edits, at no extra round.
**Three rules make it safe, and none is optional:**
1. **Apply only a remedy the finder specified.** A finding whose remedy is not specified precisely
   enough to apply as given is **BLOCKING** by the same default-deny — the licence not to re-review
   rests entirely on the reviewer having said what to write, so where they did not, it is absent.
2. **The sweep may touch only paths that are neither source nor tests, and that no floor above would
   promote.** Every such path is one the currency clause's existing exemption already covers — the
   swept set is a **subset** of the exempt set, never a widening of it (Gates → currency) — so the
   sweep re-arms nothing **by definition**. It is not given an exemption of its own and **must never
   be given one**. Inherit that clause's default-deny with it: **if you
   cannot tell whether a path is source or a test, it is — do not sweep it.** If a sweep edit would
   land anywhere outside that set, **a finding was misclassified: escalate, do not apply.**
3. **Journal what it applied** — the `- Editorial:` line (Ledger format → progress.md), whose
   enumerated spellings include the case where there was nothing to sweep.

**"Once" is literal.** The rule is about *when a round runs*, not about what class a finding
carries:

> **Before the sweep has run**, an EDITORIAL finding joins it: it re-arms nothing and escalates
> nothing. **After the sweep has run, there is no sweep left** — so **every** finding a later round
> returns, of **either** class, **escalates with the re-arm**. There is never a second sweep.

**Stated that way on purpose: as a rule about ordering, not an enumeration of the ways it can
happen.** This gate can be re-armed from *downstream* — a step-9 security fix that commits under this
step's rule, a CI fix, a change the human asked for at the merge gate, a step-10 fix — and that list
is the currency clause's own, which is **sufficient, not exhaustive** (Gates → currency). Naming one
member here and letting the rest fall through to the unqualified bound would be the enumerable-safe-set
trap in its fail-open direction: a round re-armed by something unnamed would sweep again. **Whatever
re-armed it, a round that runs after the sweep does not sweep.** The licence to apply a finding
unreviewed rests on containment inside *this step's* commit boundary, and that containment is gone
once the pipeline has advanced past it — a sweep run then would sit downstream of step 9, which is
exactly the certification the placement above buys.

**Implement viable BLOCKING findings**; decline others with a one-line rationale — **and record each decline,
with that rationale, in the gate-decision block where this round resolves** (Ledger format →
progress.md), exactly as an architect decline is recorded in the plan text. A later round is
*required* to receive the declines (Gates), and a decline is the one outcome that leaves **no trace
in the diff** for that round to recover it from: unrecorded, it is invisible to every subsequent
fresh instance. Then **commit the
BLOCKING fixes** and
**verify recs were applied — by a fresh checker, never by yourself.** If you *delegated* any fix,
that agent wrote to its own copy: collect the diff, apply it, and **remove the copy before you
commit** (Execution policy, Tool surface) — directing a fix is authorship, and it is also the one
spawn at this gate that opens the staging window. This is the Fresh-re-check
invariant's sharpest instance (see Gates): you wrote the fixes, so confirming them yourself is the
author agreeing with himself, not a gate. **Commit before spawning it** — the checker reads a diff
ending at `HEAD`, so an uncommitted fix is invisible to it. Under a scoped round that is worse than
the F15 shape the acceptance gate had to fix, not milder: the checker is handed not the pre-fix code
but an **empty** delta, which reports clean rather than reporting the wrong thing (hence the
empty-delta fallback below). Spawn **one lighter
checker** — its inputs are fixed under Gates (Fresh-re-check invariant → the code-review bullet) and
are not restated here — rather than re-running the full finder fan-out; that recipe carries its
licence to object too. Bounded to 2 rounds (round 1 being the review
itself, that re-check being round 2) — contested findings, and **any BLOCKING finding** the re-check
returns, whether one round 1 raised or one only the fix introduced, escalate to the human, do not
loop. **An EDITORIAL finding raised before the sweep has run does not re-arm and does not escalate** —
it joins that sweep. **A round that runs after the sweep has no sweep to join, so every finding it
returns escalates whatever its class.** The classes change nothing else about this bound: not the
cap, not what counts as a defect, and not the escalation for anything else.

**Round 1 reads the whole change; every round after it reads only what has changed since the last
round read.** What ***this gate's*** re-check requires is a fresh **instance** — it does not
additionally require re-ingesting material a prior round has already reported on. Read that as
scoped to this gate and nowhere else: the acceptance gate's Class A re-check deliberately *does*
re-run its whole recipe from scratch, and Gates forbids relaxing it. A majority of iterations reach
a second round, which is what makes the repeated reading worth removing. Scoping changes **what a
round re-reads**, never **what counts as a defect**: nothing is reclassified and no finding is
suppressed.

- **Round 1 is unscoped.** `main...HEAD`, and the full lens set the risk surface warrants. Nothing
  below narrows it.
- **Record what each round read.** Take `git rev-parse HEAD` when you spawn the round and write it
  to that round's `- Code-review:` element **when that round resolves — not at step 12** (Ledger
  format → progress.md, which fixes the spelling and the write-time, for the reason the
  `- Plan-gate:` line fixes its own). That SHA — **the head the last round ran on** — is this gate's
  anchor. It is deliberately **not** called *certified*: a round that returned findings certified
  nothing, and a later round exists only because an earlier one returned findings.
- **A later round reads `<reviewed>..HEAD`**, plus the previous round's findings **and the ones it
  declined**, and one narrowed question. Its full input recipe is under Gates (Fresh-re-check
  invariant → the code-review bullet); do not restate it here.
- **The anchor is the one you hold, and it is validated before use.** It is the head you recorded
  when you spawned the previous round, in this invocation. **Do not reconstruct it by reading the
  journal back** — the ledger records it for a later *reader*, not for a parser, and a journal
  scanned for "the most recent SHA" yields one that resolves and belongs to another branch. Where
  you do not hold one — a resumed iteration, most often — the round is FULL; that is the whole
  fallback, and it costs a round's saving rather than a round's coverage. Where you do hold one,
  confirm it still describes this history: `git merge-base --is-ancestor <reviewed> HEAD` must
  succeed, or a rebase, amend or force-push has moved the ground under it and the round is FULL.

**The anchor is owed by every round after the first, not only this step's own round 2.** This gate
can be re-armed from *outside* this step. **Which re-arms are owned by step 8's budget and which
escalate instead is the Gate-outcome invariant's currency clause to decide — read it there and do
not paraphrase it from here**; it turns on whether a round is actually left, which this step cannot
see. What *this* step fixes is narrower: wherever a round after the first does run, it needs an
anchor, and one computing its delta from the wrong anchor, or from none, **under-reviews in
silence** — the failure the currency clause exists to prevent. **Where no anchor is available or
trustworthy, the round is FULL.** Default-deny: the anchor buys a saving, and an unavailable saving
is never a reason to review less.

**Fall back to a full round — mechanically, default-deny — when any of these fires.** ("Fall back",
not "escalate": this branch runs the round *unscoped*; it does not hand off to the human.)
1. **A fix touched a path the project's security routing declares sensitive** (`loop.config.md`,
   step 9). This is the **risk** test. **Never read a small delta as a low-risk one** — the defect
   that motivated this rule lived in a 21-line delta that no round had yet seen; size and risk are
   unrelated, which is why no size test appears in this list.
   **Distinguish a declaration that does not match from a declaration that is not there.** A
   present, path-shaped declaration that simply does not cover this diff is a **known** answer — no
   sensitive path was touched, and the round may scope. Only a **missing, `TODO`-valued or
   non-path-shaped** declaration is unknown, and unknown is a full round. Reading a non-match as
   unknown would send every round to full in any project whose sensitive surface is narrow, which is
   most of them.
2. **The delta is empty.** A round handed nothing to read reports nothing and comes back clean —
   a pass manufactured out of an absent input, which is the shape the AC-verifier's Part 1 already
   refuses ("never read an empty diff as 'nothing to object to'"). **Confirm first that the fixes
   were committed** — this step requires that before the round is spawned, and an uncommitted fix is
   the likelier cause. Once they are, an empty delta means nothing was fixed, and the round runs
   **full** rather than certifying an absence. (Like the condition above, this branch runs the
   round unscoped; it does not hand off.)

**Any unknown makes the round FULL. This list is sufficient, not exhaustive, and it is deliberately
not a list of the safe states:** the project's sensitive-path declaration is missing, `TODO`-valued
or not path-shaped; the anchor is missing, untrusted, or not an ancestor of `HEAD`; a range will not
resolve. **An absent declaration is unknown, and unknown is a full round — never "the condition did
not fire"**, which is the fail-open reading the Gate-outcome invariant already refuses for
`HERMETIC_TEST_CMD`. If you are unsure whether some state belongs on this list, it does.

**Currency is preserved, and a scoped round is not a substitute for a full one.** A later round runs
on `HEAD` and certifies `HEAD`, as any round does — **the delta bounds what it re-certifies, never
whether it certifies.** Every commit in `main...HEAD` was read by the round whose range contains it:
round 1 read `main...<reviewed>`, the later round reads `<reviewed>..HEAD`, and a fix that rewrote a
line round 1 read reappears in that second range. So no verdict is carried onto a commit no round
ran on. **What scoping narrows is stated rather than argued away, and there is more than one thing
in that set** — extend it, never prune it: a fix's correctness can turn on earlier-read code that
has not changed since `<reviewed>`, which is outside the delta (hence the recipe's obligation under
Gates to read the definition of any symbol the delta references but does not itself contain); and a
finding round 1 *declined* leaves no trace in the delta at all, which is why the declines travel
with the findings. **A round certifies `HEAD` whatever the delta holds** — carrying a prior verdict
forward *instead of* running a round, on a docs-only delta or any other, is a different proposal and
is not licensed here.

### 9. Security review (by route)
Run `SECURITY_REVIEW` per the routing in `loop.config.md` (the local-skill-vs-label choice and any
host-repo Git incantation are project specifics; this engine only fixes the gate's position and
that findings ≥ the project's confidence bar are addressed):
- A `.claude/`-only (tooling-only) change → the **local** review path.
- Otherwise, if a sensitive surface is touched → the **labeled** review path. Skip for
  docs/no-surface changes.

**This gate is no longer last, so "run it once, at dev-complete" is no longer a safe reading.** Step
10 can produce code — a Class A finding is fixed and committed there — and that code lands
*downstream* of this gate. Re-evaluate this trigger against any acceptance-gate fix before step 11:
if such a fix touches a sensitive surface it has not been security-reviewed, so it **escalates at
the merge gate under the existing "touched security surface" always-escalate condition** (step
11) — the earlier clean verdict does not cover it. This is one instance of the general rule; **which
gates a post-gate change re-arms, and from which sources, is the Gate-outcome invariant's currency
clause** (under Gates).

### 10. Verify done (independent, fresh context)
Advance the row to `in-acceptance`. Run the AC-verifier (below): a fresh check that the diff
satisfies EVERY acceptance
criterion — verify state, not your claim. If gaps, fix and re-verify **once**: round 1 was the
gate's own first run, so that re-verify is **round 2 of this gate's 2-round cap**, and if it comes
back dirty, escalate. **The re-verify is a fresh instance, never the author of the fix**
(Fresh-re-check invariant, under Gates: a new spawn, not you and not the round-1 agent
re-contacted).
**"Gaps" means a finding of either class** — an unmet criterion or a surviving
mutant both send you back to fix and re-verify under the same cap.

**This gate is last, so it owns its own commit boundary — there is no later step that will pick its
fixes up.** Every earlier gate's fixes flowed into a commit downstream of it; nothing sits between
this gate and the merge (step 11) but the merge itself. So **commit the fixes here**, under the
same explicit-path staging rule as every other boundary (step 6), and **before** spawning the fresh
re-verify — an uncommitted fix is not on the PR branch, and a gate that certifies work the merge
candidate does not contain has certified nothing. **Confirm no mutation copy is still live
(`git worktree list`) and remove it before you stage** — Part 2 below creates one, this is the
boundary immediately downstream of it, and the untracked scan cannot see a copy the repo gitignores
(Tool surface).

**A source-changing fix here has no gate downstream of it.** Steps 8 and 9 already ran against a
head that did not contain this code, so a Class A fix that **adds or changes source** — implementing
a missed criterion, not correcting a citation or doc line — has been reviewed by nobody. **Finish
this gate first — commit the fix and run its re-verify — then escalate to the human before step 11.**
Escalating is not a reason to skip your own remaining round, and **do not merge on the earlier
verdicts** — a gate that never saw a change has not passed it (Gate-outcome invariant). A fix that changes **no** source — a citation, a doc line
— re-arms nothing and needs no escalation. (A test-only change is **not** sourceless: it re-arms
step 6's hermetic trigger — see step 6.) **A source-changing fix is not routed back through
review or security: it escalates, and that is the rule, not a fail-safe default awaiting a better
one.** A re-arm would need three things this gate cannot supply:
- **an ordering** — a re-armed step 8 commits its fixes *downstream* of the acceptance verdict,
  re-creating exactly the superseded-commit staleness this gate order exists to remove;
- **a round** — this gate's cap is 2 and round 2 **is** the re-verify, so no round remains to
  certify re-armed work, and a gate round invented to fit is a cap that does not bind;
- **a status** — the row is `in-acceptance` and Resume re-enters *here*, so a re-armed review
  would be skipped in silence by the next `/clear`.
The human is the path because the human is the only actor outside those three constraints.

**These are *result* classes, not the *finding* classes code review emits — two vocabularies, not two
granularities.** Class A and Class B are this gate's own vocabulary; BLOCKING and EDITORIAL are step
8's. The engine calls an item in either a "finding", so **"a Class B finding" carries no finding class
at all** — it is a result of this gate, which emits none. **Neither of this gate's classes may ever be
swept**: "either class blocks" below means exactly that.

The gate returns **two result classes, and they are never summed into one "findings" count**:
**Class A — AC-satisfaction findings** (a criterion judged not met) and **Class B — mutation
survivors** (a test this change adds or modifies that stays green when the behavior it guards is
broken — or, when the change alters behavior and adds no test at all, that absence).
Class B comes from the **mutation pass**, which is **scoped by risk surface** rather than run
unconditionally: step 10 itself remains due on every issue with acceptance criteria, but the mutation
pass *within* it is conditional (AC-verifier → Part 2). **A clean Class B after a dirty one is a
valid and valuable result** — do not read "no survivors this time" as the gate going soft.

### 11. Merge
Read the run `mode` and `graduated-routes` from the `queue.md` header. The merge gate is the
**only** gate `mode` changes (step 5's posture comes from the separate `plan-gate:` field, which
`mode:` never sets after Initialization — plus one always-on condition neither reaches). A row is
**auto-merge-eligible**
only when ALL of these hold:
- `mode: escalation-only`, AND
- the row's Route is listed in the header's `graduated-routes` field, AND
- the change produces **no release-artifact bump**, or ≤ patch where `RELEASE_SCHEME` defines a
  version scheme — a `docs`/`chore` change, or any change in a project with no release cycle,
  produces no bump, which qualifies, AND
- the row is **not** `hold`, AND
- none of the always-escalate conditions apply: a `feat:`/breaking change, a risky/irreversible
  change, a touched security surface, a contested review finding, **an unresolved BLOCKING review
  finding** (step 8 — an EDITORIAL finding raised before that step's sweep is swept there and never
  left unresolved; one raised after it escalates, by step 8's *"Once" is literal* rule), **an
  unresolved Class B mutation survivor from the acceptance gate** (step 10 — a guard that does not guard is
  exactly the defect an auto-merge has no human to catch), or **an unresolved hermetic-tier finding**
  (step 6 — same shape: a declared invariant that is not true, with no human in the path to notice).

**Default-deny:** if route graduation or any always-escalate condition is uncertain, the row is
**not** auto-merge-eligible — fall back to the human merge gate.

If the row is **not** auto-merge-eligible — which includes *every* row under `mode: calibration`
(the default) and any `hold` row — STOP and ask the human before merging; never auto-merge.

**What the stop must state, and it is not optional: how many EDITORIAL findings were applied without
re-review** (step 8's sweep), and on which paths. A count, never a reassurance. Those are findings a
gate raised that no fresh instance ever re-read — a trade the human is the only actor positioned to
price, and absorbed silently it reads as a clean review. **Read the number off the `- Editorial:`
line** (Ledger format → progress.md) rather than from memory: the sweep resolved back at step 8, so on
a resumed iteration the ledger is where it survives. **Write `0` where the line says `0`** —
a measured zero and an absent count are different statements, and this is the one number this
disclosure exists to surface:
- **No `- Editorial:` line on an iteration whose step 8 closed ⇒ unknown, never `0`** (Ledger format
  fixes that reading). Unknown is not a count you may report: say so and **escalate**.
- **A `- Editorial: finding — …` line carries no count** — the sweep hit its containment rule and a
  finding was misclassified. That is a BLOCKING finding standing open; do not merge, and do not report
  it as a count.
- **More than one line can exist for one issue** — a `/clear` on an `in-review` row replays step 8
  (Resume), so read the lines belonging to **this issue's** step-8 blocks and **sum** them. If you
  cannot tell which blocks belong to this iteration, that is unknown: escalate.

Where the row instead **auto-merges** there
is no human to tell, which is why the same count is journalled either way.
**If the human holds the merge (now or in any later invocation),
WRITE the hold to the row before stopping** — set Status `hold` (record the reason in Notes) so
it persists across `/clear`; resume (step 0.3), step 1, and this gate all key on Status `hold` and
honor it until the human clears it (restoring the row's prior status). When the row **is**
auto-merge-eligible (or the human has approved), and CI + security + acceptance are green **on the
commit you are about to merge** — this gate is itself a source of change, and it is the one step
with nothing downstream to catch a stale verdict (Gate-outcome invariant → currency) — AND the row
is not `hold`:
merge via `MERGE_METHOD` with an explicit `--subject` carrying the correct `COMMIT_CONV` scope,
`--delete-branch`. Confirm the issue closed.

### 12. Journal + stop
Append the iteration's **close record** to `progress.md` (Ledger format → progress.md, which carries
its shape). Step 7 writes the open record; if this iteration re-entered *past* step 7 on resume,
there may be none — **do not write one now.** Back-dating it would assert a record of a moment nobody
observed, which is the same bar the architect freeze and the gate lines are under.

The `- Budget:` line is:
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
`DESIGN_AGENT`. Escalate to the HUMAN when those disagree/punt, ACs are unresolvable, an
action is destructive/irreversible, a review finding is contested or is BLOCKING and unresolved
(an EDITORIAL one raised before step 8's sweep escalates nothing — it is swept there; one raised
after that sweep escalates like any other, by step 8's *"Once" is literal* rule), or the same step
failed twice —
**and, always-on, when the architect *decides*: a material redirect of the plan escalates exactly as
a punt does** (step 5). "Only when those disagree/punt" would read a decisive rewrite as a reason to
proceed, which inverts the point of the gate.

**This list is what "unsure" triggers; it is not the whole of when the plan gate stops.** Under
`plan-gate: always` — the shipped default, and what an absent field reads as — step 5 stops on
**every** issue, whether or not anything here fires. Read this rubric as the floor, never as the
condition set: nothing on it needs to be true for the plan gate to be owed.

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
branch; never `git add` unrelated pre-existing working-tree changes; **never stage or commit while a
writing subagent's isolated copy is live** (Execution policy, below — the window closes when *you*
remove the copy, not when the agent exits); never edit the user-global
`SCOPE_AGENT`/`DESIGN_AGENT` definitions; **never edit `loop.config.md`** — a binding
that looks wrong is a finding you journal and hand to the human, because a gate you rebind to match
your own reading entrenches your misreading instead of correcting it. The C1 append-only guard and
the human/merge gates are the enforced backstops; the rest of this list is your contract.

**Paging a file of known extent — ask for the remaining slices in one turn.** Where you are reading
a file in slices and already know how long it is, every slice after the first is an independent
request: issue them together rather than one per turn, since a turn re-submits your whole
accumulated context, and issuing five calls together costs **one** such re-submission instead of
five. The results themselves are not free — only the turn is — so ask for each slice once and do not
pad the ranges against a boundary you are unsure of; widening a slice to be safe is how this rule
starts costing more than it saves. Establish the extent first, from whatever the tool reports —
`Read`'s `totalLines`, or a `wc -l` ahead of shell slices, among others; treat those as examples
rather than the whole list. Read `wc -l` as a **floor, never the extent**: it counts newlines, so a
file whose last line carries no newline is one line longer than it reports, and that line is the one
you would never ask for. **Then confirm what came back is contiguous and covers the whole file, and
re-read anything missing** — asking one at a time made that self-correcting, because each request
started from what the last result actually returned, and asking together gives that up: a hole still
reads like a complete load. **Confirm the extent you received, not merely the range you asked for**:
a tool result is capped independently of the range — a `Read` is bounded by tokens as well as lines,
and a shell slice is bounded by the command-output cap, which truncates **silently** — so a pair of
slices whose *requested* ranges tile the file can still arrive with the middle missing. **If you
cannot confirm the file's extent, it is not known, and you page it one turn at a time.** This governs
*slices of one file you have already sized*; it is **not** a licence to merge independent tool calls
in general, because in general nothing distinguishes a dependent read from an independent one and
merging across a dependency reorders effects. (The engine must still be read with `Read` rather than
shell slices — see the engine-read protocol in `SKILL.md`.)

**The working tree is parent-owned state; any agent that must write to it gets its own copy.** This
governs every agent you spawn, not only a mutating one — the tree holds your uncommitted
deliverables, and a subagent writing to it is writing to your work. Read-only agents need no copy;
any agent that writes gets one, via the host's worktree-isolation option. Three duties follow, and
all three are **yours**, because the agent cannot discharge them from inside its own copy:
- **Never stage its copy.** Where the host materializes the isolated tree inside the repository it
  shows up in your `git status` as untracked, and a blanket `git add` lands it as a gitlink.
  Explicit-path staging (step 6) is the control, and that step describes what the mistake looks like.
- **Collect anything you asked it to produce, then remove the copy.** These are one duty in two
  parts, and skipping the first destroys work: where the agent's writes **are** the deliverable — a
  fix you delegated (Fresh-re-check invariant) — the parent takes the diff out of the copy and
  applies it *before* removing anything. Only a copy whose contents you do not want is discarded
  unread. Hosts that auto-clean an *unchanged* isolated tree will not clean one the agent wrote to,
  which is every case this invariant is about, so removal is always yours.

  **An agent that died or was interrupted still produced something, and it is collected on the same
  terms.** Read this duty as *whatever is in the copy*, never as *what the agent managed to finish*.
  A pass that ended early leaves a partial artifact — a spec it had already written, a half-built
  report, a verdict covering some criteria and not others — and that artifact is the only surviving
  evidence of budget already spent. **Do not discard it** because nothing was formally "delivered":
  that leaves the re-spawn starting from nothing, having paid twice for the same ground. The narrow
  reading is the live hazard, because a dead agent hands you no summary of what it left behind: you
  find that out by **looking in the copy before you remove it**, which is the one order this duty
  fixes. (Where such a copy is *stranded* — nobody holds a handle to it — the paragraph below is how
  you find it at all; that is the same duty reached by a different route, not a second one.)
- **Never let its copy stand in for the change under review.** A file inside an isolated tree is not
  evidence of anything until you have applied it; cite `file:line` in the merge candidate, never in
  a copy.

The concrete path an isolated tree appears at is a **host** fact, not a project one, so this engine
names none. **Get it from `git worktree list`**, which answers whatever the host does or does not
report back, and answers for a copy left behind by an agent that errored or was interrupted — the
case where you have no handle at all and the one where the duty matters most. Do not rely on the
acceptance gate's untracked scan to find a stray copy: it is `git ls-files --others
--exclude-standard`, so a repo that gitignores the isolation path — which is what a maintainer does
after seeing one appear — sees nothing. Its position is no help either: that scan runs in the
acceptance gate's Part 1, *before* Part 2 creates the copy most likely to be stranded.
`git worktree list` has neither blind spot. A host whose isolated trees land *outside*
the repository discharges the first duty for free and still owes the other two.

**Execution policy — the parent owns the tree, and nothing may concurrently mutate it.** Pipeline
steps run one after another — **do not overlap them**; the parent thread owns the working tree
throughout. Ordering is not the whole rule, though: **within a step, subagents may run concurrently
only when they mutate nothing the parent owns** — its working tree first of all, and equally its
index and refs, the ledger, and the PR. That is a predicate rather than a list of blessed fan-out
sites, on purpose: a fan-out added later is then permitted or forbidden on its own merits, instead
of on whether someone remembered to add it to a list. It has two satisfying forms:

- **Read-only.** The step 8 `CODE_REVIEW` finder fan-out is the standing example and is **permitted
  by name**: several finders on distinct angles, running at once, reading the diff and the
  acceptance criteria. Angle diversity is what makes that gate find anything, so nothing *in this
  policy* bounds the fan-out — read-only agents hold no copy and cannot corrupt your tree. The
  converse duty is yours: do not mutate the tree in place while a reader is in flight over it (Part
  2's in-tree rung is the one place you would). Other bounds are unaffected: each finder counts
  separately toward the **next** iteration's `subagent-cap` check (progress.md → the Budget line) —
  retrospective, and advisory on a manual re-invoke — so step 8's own roster rules — scale
  with the risk surface, the `guard-efficacy` floor, and the distinct-question rule — are the bounds
  that act on the fan-out you are about to launch.
- **Isolated.** An agent that writes runs against **its own copy** of the tree, per the isolation
  duty above. **The escape hatch is isolation, not care** — "be careful not to collide" is not an
  available option, because the duties that make writing safe are ones the agent cannot discharge
  from inside its own copy.

There is no third form: an agent that would write to the parent's tree does not get spawned more
carefully, it gets a copy first.

**And there is no binding that loosens any of this.** This policy is deliberately *not*
project-bound: a porting project has nothing to set here, and that is a decision rather than an
oversight — the parameter that once sat here was retired, not left unfilled. The case that looks
like it needs one is a host where isolation is unavailable or ruinously expensive, and it is
precisely the case the predicate already answers: with no satisfying form available, nothing may be
spawned to write concurrently at all. **Note what that settles and what it does not:** who may run
concurrently, not what the parent may then do on its own path. A destructive step there is governed
by the Escalation rubric's destructive/irreversible clause and, at the acceptance gate, by its
safety envelope (AC-verifier → Part 2), which sends you to the human and treats a declined choice as
a gate-error rather than a quiet proceed. Neither is configurable. A binding could only ever restate
what the predicate derives, or license the "be careful" form ruled out just above; the first is
redundant and the second is an off switch for a safety invariant. Nor is the other cost a counterexample — not the cost of copies, already dealt with, but
agent spend. What varies by project there is how much of it you can afford, and that is budgeted
**elsewhere and differently**, by the `subagent-cap` circuit-breaker named in the read-only form
above: a per-run ledger field the human sets, not a project binding, bounding *volume*
retrospectively and unable to tell simultaneity from throughput.

**Your own writes are governed by this policy too — never stage or commit while a writing subagent's
isolated copy is live.** The window opens when you spawn that agent and closes only when **you have
removed the copy**, *not* when the agent exits — an isolated tree outlives the agent that wrote to
it, which is why step 6 fixes the same closing edge. Where the host materializes the copy inside the
repository, a blanket `git add` inside that window lands it as a gitlink rather than as the wall of
files you would scan for; where the host puts it outside, the reason survives anyway — a commit
taken before you have collected the agent's output commits a half-collected change.

Step 6 states this window over **any** subagent, which is the more conservative form and is left
that way deliberately: "read-only" here is a property of the prompt you wrote, not of a tool grant
the host enforces, so a reader that writes a scratch file is a misclassification you want step 6 to
catch. Treat the copy as what makes the window *outlast* the agent, never as what makes it exist.

**This does not retire explicit-path staging — it sequences around it.** The two rules answer
different questions and neither replaces the other: *when* you may reach a commit boundary at all
(here), and *how* you stage once you are at one (step 6, at **every** boundary, which is why it is
called the control both above and in Part 2's envelope). **No commit boundary legitimately falls
inside the window.** Every one the pipeline defines is sequenceable outside it — a fix you delegated
at step 8 is collected, applied, and its copy removed before that step's fix commit, and step 10's
mutation copy is removed before the acceptance gate's own fix commit. Both copies are created and
retired *within* the step that opened them; neither may still be live when the next boundary
arrives. Removing the copy is always available to you, so remove it
first. If you believe a boundary must fall inside the window, that is a finding to journal and hand
to the human, not a case to stage carefully and proceed through.

---

## Ledger format

Create `LEDGER_ROOT/<run-slug>/` (e.g. `.claude/loop/<run-slug>/`) containing three artifacts.
The orchestrator is the only writer except where noted.

### `queue.md` — work list (authoritative status)
Dependency-ordered. One row per issue. **`Route` and `Status` are separate columns** (a row
can be Route `research`, Status `blocked`). **Pipeline statuses** — advanced by the
orchestrator as the issue moves through the pipeline, so an interrupted run leaves a non-terminal
status resume keys on (see Resume): `queued → routed → planning → plan-approved → implementing →
in-pr → in-review → in-acceptance`. **`in-acceptance` brackets the acceptance gate (step 10) and the
merge (step 11)**, and
exists because that gate is now the last one: without it `in-review` would span review, security,
acceptance and merge, so any `/clear` in that span would resume by replaying the entire code-review
fan-out. A crash during **security** still resumes under
`in-review` and replays the review fan-out, which is a residual this status does not close.
It is a **pipeline** status like the seven before it — never a resting one, so it takes no
part in the `hold`/`parked` machinery below. **Terminal statuses** — the run converges when every row is terminal:
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

**The three sets above are CLOSED, and a Status outside them escalates.** A row whose Status is
none of them is **unrecognised**: do not classify it, do not resume it, do not select it — **STOP
and ask the human**, naming the row and quoting the literal string you found. Step 0.3 and Resume
apply this rule; the sets it closes over are the ones enumerated above.

- **Read the `queue.md` Status column only.** Not Notes, and not `progress.md`'s `RUN …` sentinels.
  `awaiting:`, `kept:` and `gate-error:` are **Notes** values, not statuses — a gate-errored row's
  Status is plain `blocked` (Gate-outcome invariant), so a recognizer written as though
  `gate-error:` were a Status token would look for something the engine never emits.
- **Match the whole Status, and accept exactly one compound form: `blocked: too-large`.** Trim
  surrounding whitespace and compare case-insensitively; otherwise match the literal string. **Do
  NOT split on `:` and accept whatever precedes it.** `blocked: too-large` is how this engine has
  extended a status once already, so `<known token>: <qualifier>` is precisely the shape a *future*
  status will arrive in — and a rule that accepts the base token would read `blocked:
  needs-config-repair` as plain `blocked` — terminal, and eligible for step 1 to re-select once it
  reads the dependency test as satisfied. That is this gate's own failure mode reproduced inside
  the recognizer, and it fails **open**. Anything that is
  neither a bare status nor that one compound form is unrecognised, and unrecognised stops the run.
- **Escalate; do not resolve it to a default.** `plan-gate:` can read an unrecognised value as
  `always` because its values are ordered and one of them is stricter. A Status has no such
  ordering — there is no over-gating reading of "unknown stage" — so the fail-safe here is the
  human, not a fallback.
- **What this buys, and where it stops.** A status this engine has not heard of stops the run
  instead of being silently mapped to a stage. It cannot help an engine that predates the rule, it
  cannot see a *recognised* token whose meaning shifted underneath it (the same status at a
  renumbered pipeline position reads as valid), and it runs on the resume path — the step-0.1
  **parked cheap path** re-derives selectability from `queue.md` without that scan. The upgrade rule
  in `README.md` is what addresses the second of those, and nothing here enforces it.

**Curated-subset invariant.** The queue built at init (see Initialization) is the authoritative
work set; `BACKLOG_SOURCE` membership may drift afterward, and that drift is **surfaced to the
human once, never auto-applied** — neither auto-added on join nor auto-ejected on leave (step-1
roster reconciliation). A corollary is a Notes discipline: **write a `parked`/`blocked` row's Notes
as the durable curation DECISION** (`awaiting: <external condition>`, `deliberately out of <run> at
init (curation)`, `kept: out-of-<run> roster (curation)`), **never the mutable live evidence** ("not
in roster", "no PR yet") — the latter is contradicted by a later live re-check and destabilizes
resume.

The header carries a `mode:` field that gates **the merge gate only** — it does
**not** change the plan gate, whose posture comes from the separate **`plan-gate:`** field described
below (step 5) — **plus one always-on condition neither field can reach, a material architect
rewrite of the plan**. The two modes:
- **`calibration`** (default) — the human approves **every** merge; the loop never auto-merges
  (step 11). Initialization pairs it with `plan-gate: always` (step 5) — plus that always-on
  condition.
- **`escalation-only`** — the human loosens the **merge gate per route**: a route the human has
  *graduated* auto-merges when CI + AC-verifier + review are green and the change produces no
  release-artifact bump (or ≤ patch where `RELEASE_SCHEME` defines one — a `docs`/`chore` change,
  or any change with no release cycle, qualifies). *Which* routes are currently graduated is a
  mutable human decision, recorded per-run in the `graduated-routes:` header and in the project
  decision log — never frozen into this mechanism definition (the lesson: graduation *state* is
  evidence, not a rule). The human merge gate is **retained** for every non-graduated route and,
  regardless of route, for any of: a `feat:`/breaking change, a risky/irreversible change, a touched
  security surface, a contested review finding, an unresolved BLOCKING review finding (step 8 — an
  EDITORIAL finding raised before that step's sweep is swept there and never left unresolved; one
  raised after it escalates, by step 8's *"Once" is literal* rule), an unresolved Class B mutation
  survivor from the acceptance gate (step 10),
  an unresolved hermetic-tier finding (step 6), or a `hold` row — **and, by default-deny, whenever
  route graduation or any always-escalate condition is uncertain, fall back to the human merge
  gate.** Initialization pairs it with `plan-gate: conditional` (step 5) — **and neither that
  pairing nor graduating a route loosens the always-on condition**: a material architect rewrite of
  the plan stops for the human on every route, in this mode as in `calibration` (step 5).
  Graduation buys an unattended *merge*, never an unattended change of plan. **Note what the pairing
  is and is not:** it is the value Initialization *writes* for a project that has already graduated
  routes, not a coupling — a run may sit at `escalation-only` with `plan-gate: always`, and
  switching `mode:` later never rewrites the field. Loosening to `escalation-only` presupposes the
  calibration prerequisites are met (these pinned mode semantics, plus per-iteration budget
  journaling — the `- Budget:` record and `iteration-cap:`/`subagent-cap:` fields below); it cannot
  run headless.

The set of graduated routes is recorded in a `graduated-routes:` header field beside `mode:`
(default `none`; e.g. `graduated-routes: docs, research`). Under `mode: calibration` it is inert.
*Which* routes graduate and the criteria for promoting one are out of scope here; this field only
gives the merge gate (step 11) a place to read the human's decision from.

The header also carries **`plan-gate:`**, which sets the plan gate's posture (step 5) exactly as
`mode:` sets the merge gate's. Two values:
- **`always`** — stop for plan approval on **every** issue.
- **`conditional`** — stop on step 5's judgment conditions (ambiguous ACs, risk/irreversibility,
  agent disagreement, a value story that doesn't hold, genuine uncertainty).

Under **both**, step 5's always-on condition still fires and its `- Plan-gate:` line is still
written. **Absent or unrecognized ⇒ `always`**: a ledger predating this field, or a typo, gets the
over-gating reading rather than a silent fallthrough to the looser one.

Initialization writes it per mode — `calibration` ⇒ `always`, a project with prior route graduation
⇒ `conditional`. **After that the two fields are independent, and this is load-bearing rather than
incidental.** Changing `mode:` never re-derives `plan-gate:`, in either direction: flipping to
`escalation-only` does not loosen the plan gate, and flipping back to `calibration` does not
re-tighten it. Were they coupled, a project that found a mandatory plan stop too heavy could only
escape it by loosening its **merge** gate — trading away the protection it actually wanted to keep
in order to adjust the one it did not. Consumers at different trust levels need to set these
independently, which is the whole reason this is a field rather than a property of `mode:`.

**That independence holds *within* a run.** A **new** run's Initialization re-derives the default
from the mode branch, so a `plan-gate:` value a human sets by hand is **not yet carried across runs**
the way a graduated `mode:` is — re-set it after init if the run's posture should differ from the
mode default.

**`plan-gate:` is human-owned.** Initialization writes it once, deriving the default from the mode
branch it already takes (below); every value after that first write is a human decision recorded in
the header, exactly like `mode:`, `graduated-routes:` and the budget caps. **The orchestrator never
rewrites this field after Initialization** — not at step 5, and not on the observation that recent
approvals looked routine. A gate that can switch itself off on its own reading of its own history is
not a gate.

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

### `progress.md` — append-only journal (survives /clear + compaction)
The orchestrator APPENDS one block **per gate decision** and, over an iteration, the two records
below; it is never rewritten. This is the audit trail and the resume anchor.

**The pipeline names the step that writes each record, and each is owed only by an iteration that
reaches that step:**

| Record | Written at | Owed by |
|---|---|---|
| **open record** | **step 7**, as soon as the PR is opened | an iteration that opens a PR |
| **close record** | **step 12** | an iteration that reaches step 12 |

**An iteration that ends before step 7 writes neither** — a plan
gate that stops (under `plan-gate: always`, the shipped default, that is *every* issue until the
human approves), a row deferred or blocked at step 2, a gate that escalates. This is the writes-none
path, enumerated for the same reason `- Hermetic:` and `- Plan-gate:` enumerate theirs: a shape whose
only legal rendering asserts that a record exists is a template that pressures you to invent one.

**Gate-decision blocks are appended wherever the gate resolves — before, between, or after these
two.** Step 5's `- Plan-gate:` line is written *at step 5*, which is **before** the open record, not
between the two. So a single iteration commonly spans several appends; that is the intended shape,
not drift.

**Why the open record is a separate record and not a heading on the close record:** the two are
written at different times *by different invocations of this skill*, and the whole point of the first
is that it survives the loss of the second. A template that only shows the close record demands
outcomes an iteration does not have yet, which pressures the orchestrator to defer the entire
journal to step 12 — the failure this split exists to remove.

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
- Code-review: round 1 (main...9f3c1ab) — 0 findings. Security: n/a (no deps added).
- Editorial: 0 — no EDITORIAL finding returned.
- Restore: n/a: no mutation applied.
- AC-verify: Class A 3/3 acceptance criteria met. Class B: mutation pass not due (research route).
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

The **`- Hermetic:`** line records the declared-offline tier gate (step 6), which is otherwise
invisible: it blocks at implement time, so by the acceptance gate its findings are already fixed and
nothing downstream would ever show that it ran or what it caught. Every iteration writes exactly one
of the first three spellings, or takes the fourth path, which writes none:
- **`- Hermetic: pass`** — the tier ran under the block and exited zero.
- **`- Hermetic: finding — <what failed only under the block, and what it was really doing>`** — a
  test was passing for the wrong reason. This is the line that discharges "reported as prominently
  as a bug"; blocking alone does not, because blocking leaves no record.
- **`- Hermetic: n/a: <reason>`** — not due: `no test change`, or `<route> route` off a non-`code`
  row, or the config's own reason where the binding is `—` (e.g. `n/a: no offline/hermetic tier
  declared`). The first two say the **trigger** never fired and are available whatever the binding
  says; the third says the **project** has no tier, and needs the binding to be `—` with a reason to
  quote.
- **no `- Hermetic:` line at all** — the gate produced no verdict, so a `- gate-error:` carries it
  instead and the iteration stops. Three states reach here, all of them on a row the trigger DID
  fire on: bound but unable to execute; `—` with no reason; and absent or `TODO`-valued.

The **`- Human gate:`** line records how the plan gate resolved. Under `plan-gate: always` (the
shipped default) every issue stops, so the line reads as an approval by the human and
**`plan auto-approved` is never legitimate for this gate** — name the posture, as the worked example
does. Under `plan-gate: conditional` an unstopped issue reads `plan auto-approved (<why>)`, the
`<why>` being the judgment call that let it pass (e.g. route and low ambiguity).

The **`- Plan-gate:`** line records the always-on stop's frozen-vs-live diff (step 5), which is
otherwise invisible for the same reason: it resolves before implementation, so a run that never took
the diff and a run that took it and found nothing leave an identical ledger. It is also the only
evidence this condition's falsifier can ever be evaluated against. **This is the one enumeration of
the spellings; step 5 points here rather than restating them.** Write it **at step 5, when the gate
resolves** — not at step 12. Every iteration **that reaches step 5** writes exactly one; an
iteration that re-enters *past* step 5 (Resume — a `plan-approved` row goes straight to implement)
writes none and carries the decision from the iteration that took it, exactly as `- Hermetic:`
enumerates a writes-none path.
- **`- Plan-gate: material (<what changed>) → STOPPED`** — the diff showed a material change and the
  human was asked. Name the axis (a step added/removed/reordered, the files-to-touch set changed, a
  fork re-chosen, an AC reinterpreted), not just the verdict.
- **`- Plan-gate: no material change (frozen-vs-live diff taken)`** — the diff was taken and came
  back immaterial. The parenthetical is the point: it is what distinguishes this from the line never
  being written.
- **`- Plan-gate: material (pre-image absent, architect ran) → STOPPED`** — the block was missing on
  a row where `DESIGN_AGENT` was consulted. There is nothing to name as "what changed" because the
  evidence is what is missing; that is a stop, never a pass.
- **`- Plan-gate: n/a: architect skipped (<route/reason>)`** — **no architect pass ran at all**: not
  at step 4, not at step 5, and not as the inline composition that substitutes for an unrunnable
  binding. If any pass ran, by any actor, this spelling is unavailable.

**An absent or `TODO`-valued binding is never an `n/a: no offline/hermetic tier declared`** — that
reason quotes a config that did not give one. On a row the trigger fires on it is unknown, unknown
is due, and it takes the fourth path. On a row the trigger never fired on, write the trigger's own
reason (`n/a: no test change`, `n/a: docs route`): a missing binding does not make a gate due that
nothing else made due, and halting a `docs` typo fix over a binding it would never have read is not
fail-safe, just broken.

Never fold this into `mutation-survivors`. That slot's `n/a` list is closed at two reasons, and a
hermetic result is a different question from whether a guard guards.

The **`- Code-review:`** line names **the commit range each round read**, one element per round,
alongside that round's result. It is what lets a later reader tell **what a verdict covers** —
the question the currency clause turns on and the thing a merge gate has to weigh. **It is a record
for a reader, not a store a later step parses**: the orchestrator holds the anchor in context for as
long as it can use it, and a round that no longer holds one runs full (step 8), so nothing reads
this line back and no grammar is imposed on it.

**Write each element when its round resolves — not at step 12**, for the reason the `- Plan-gate:`
line is written at step 5: an append-only journal records what happened when it happened, and a
record reconstructed at the end of an iteration is written by whoever survived it, from memory,
about rounds that may have run before a `/clear`. The iteration appends the element in the
gate-decision block where that round resolves (`progress.md` licenses one block per gate decision),
and the close record carries the accumulated line. Each element takes one of three shapes —
enumerated for the same reason `- Hermetic:` and `- Restore:` enumerate theirs, that a shape whose
only legal rendering asserts a scoped round is a template that pressures you to record one:

- **`round <n> (main...<sha>) — <result>`** — an **unscoped** round: round 1 always, and any later
  round that fell back to full. Where it is a *fallback*, **name the reason** — `round 2
  (main...a18061d) — fell back to full (no sensitive-path declaration), 2 findings` — or the line
  cannot distinguish a scoped round from one that declined to scope, which is the saving silently
  not happening.
- **`round <n> (<sha>..<head>) — <result>`** — a **scoped** round, reading only what the previous
  round did not.
- **`round <n> — no verdict`** — the round produced none; a `- gate-fallback:` or `- gate-error:`
  line carries what happened (Gate-outcome invariant). Never write a range here: there is no verdict
  for one to bound.

Keep the range **off** the `- Budget:` line: that line is one physical line and its
`code-review=<c>(…)` parenthetical records lenses only.

The **`- Editorial:`** line records step 8's editorial sweep — what was applied **without
re-review**, and to what. It exists for the reason `- Hermetic:` and `- Restore:` do: everything the
sweep's containment rules do is *prevention*, and prevention that fails, fails silently. Without this
line an iteration that swept ten findings and one that raised none are identical in the ledger, and
the merge gate's disclosure (step 11) would have nothing behind it to read. **Write it at step 8, when
the sweep resolves — not at step 12**, for the reason the `- Plan-gate:` line fixes its own
write-time: the sweep resolves several steps before the journal, and the merge gate reads this line
back rather than recalling the number. It is **owed by an iteration whose step 8 closes**; an
iteration that escalates at step 8 and stops runs no sweep and writes none, exactly as `- Hermetic:`
enumerates a writes-none path. **The close record carries the line too**, as it carries `- Hermetic:`
and `- Restore:` — written at step 8 when the sweep resolves, and repeated in the close record so one
block holds the iteration's whole outcome. It takes the same **enumerated** forms, for the
same reason — a single
fixed shape whose only legal rendering asserts a clean sweep is a template that pressures you to
assert one:

- **`- Editorial: <count> applied without re-review — <id> (<path>): <what was applied>; …`** — the
  sweep ran. Each `<id>` is the `r<round>.<lens>.<k>` the finding was recorded under (step 8), so a
  reader can trace it back to the round and the lens that raised it.
- **`- Editorial: 0 — <no EDITORIAL finding returned | all promoted by the content floor | all
  promoted by a path floor | all promoted for an unspecified remedy | promoted by a mix of the
  above>`** — nothing to sweep. **These reasons are sufficient, not exhaustive**: name the route that
  actually promoted the findings rather than forcing it into the nearest reason listed here.
  **`0`, not `none`**,
  so this line and the merge gate's count are the same statement; and **which** of those it was
  matters, because "the finders raised none" and "the floors promoted every one" are different facts
  about the change — in a project whose declared-inert set is small the second is the ordinary
  outcome.
- **`- Editorial: finding — <the sweep edit that would have landed outside the swept set>`** — the
  sweep's containment rule 2 fired, so a finding was misclassified. This is a **BLOCKING** finding:
  escalate, do not apply, and do not merge while it stands.
- **no `- Editorial:` line at all** — on an iteration whose step 8 closed, **unknown, and unknown is
  not "0".** Absence cannot distinguish an iteration that swept nothing from one that swept without
  recording it, and the second is the failure this line exists to catch.

The **`- Restore:`** line records that a mutation pass gave the tree back. It gets its own line for
the same reason `- Hermetic:` does — everything else about the pass is *prevention*, and prevention
that fails, fails silently, so without this line a leak waits for a reviewer to notice broken code
in a diff. It takes the same **enumerated** forms, for the same reason: a single fixed shape whose
only legal rendering asserts success is a template that pressures you to assert success.

- **`- Restore: <n> mutations applied, <n> restored, git status clean`** — the pass gave everything
  back. **The two counts describe the tree that was mutated; `git status clean` always describes the
  parent**, which is what lets one line cover both paths. In-tree, the counts are files snapshotted
  and restored from those snapshots. Under isolation they are the agent's own copy, restored by
  discarding it — the parent was never mutated, so its clean status asserts that a tree which should
  never have changed did not. **The clean-status half is the load-bearing half**: it is the only part
  verifiable after the fact, and the only part that catches a leak the counts would report as
  balanced.
- **`- Restore: finding — <what is still in the tree, and where>`** — the two counts disagree, or the
  parent is dirty for a reason that is not a leftover copy. Either way a mutation is still live. This
  is a **blocking finding, reported as prominently as a bug**: repair from the snapshot, re-check,
  and **do not commit while it stands**. If the snapshot itself is what went missing, you have lost
  the safe repair — escalate to the human rather than reaching for `git checkout`/`git restore`,
  which is the move that destroys uncommitted work (AC-verifier → Part 2).
- **`- Restore: n/a: no mutation applied`** — no mutation was applied, so there was nothing to give
  back. This is the **not-due** case (AC-verifier → Part 2, questions 1 and 2) and the **limit case**,
  where no pass runs at all. It is **not** available to a pass that ran: a due pass that applied
  zero mutations is a harness error — its spec matched nothing, which the harness reports as such
  rather than as a clean run — and that takes a `- gate-error:`, never this line. The distinction
  is the whole of AC5: "nothing to give back" and "nothing was broken to begin with" must not share
  a spelling.
- **no `- Restore:` line at all** — **unknown, and unknown is not clean.** Once a producer exists,
  absence cannot distinguish "no mutation ran" from "a pass applied mutations and died before it
  could journal" — and the second is precisely the leak this line exists to catch. That is why the
  not-due case is written visibly as `n/a:` rather than omitted, exactly as the Gate-outcome
  invariant requires of any gate whose absence would otherwise read as a pass. **A missing line on an
  iteration that ran a pass is treated as a possible leak: check `git status` and `git worktree list`
  before doing anything else.**

Two ordering rules, because both are easy to get backwards:
- **Remove the agent's copy before asserting the parent is clean.** Where the host places an isolated
  tree inside the repository the parent is *not* clean while that copy is there, so the assertion
  made in the wrong order either certifies clean against a tree still holding the agent's files or
  reports dirty for a reason that is not a leak. Clean up first (Tool surface), then look.
- **`git status` is not sufficient on its own.** A repo that gitignores the isolation path reports
  clean with a copy still present, so pair it with `git worktree list` (Tool surface).

**A producer now exists** (AC-verifier → Part 2), so on an isolated or in-tree pass the two counts
are read off the harness's report rather than tallied by hand: `applied` counts **mutations whose
substitution actually changed the file's bytes**, and `restored` counts mutations whose file was
verified byte-exact on the way back. They count mutations, not files — three mutations in one file
report `applied: 3` — and neither counts invocations of a helper — that substitution is the specific dishonesty AC5 names, and it is
now settled in code instead of by instruction. Pinning this line's presence or shape with a
consistency check became possible with that producer; whether to do it is **#62's** call, not a
claim this section makes on its behalf.

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
  erases the signal); and defects that escaped the gate and surfaced later — within this iteration
  only at the merge gate, since code review and security now run *before* the acceptance gate; the
  window running from the gate to this journal entry. The larger channel is a later iteration.
  A survivor found in a *later* iteration is recorded on that iteration's line, naming the
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
    **two** reasons: the route scoped it out (`n/a: docs route`), or the change alters no behavior
    (`n/a: no behavior change`). Both are answers to Part 2's questions 1 and 2, and both say the
    pass was never **due**.

    **The list was closed at three until the apparatus landed. The third reason —
    `n/a: apparatus pending` — is RETIRED and must never be written again**: it named a gap that no
    longer exists, since the actor split, the applied-check and interrupted-pass recovery are now
    specified and the harness that performs them ships with the plugin (AC-verifier → Part 2).
    Writing it today would report a missing capability as the reason for not using the capability.

    **No other reason is a legal `n/a`, and the list does not re-open.** Retiring a member is not an
    invitation to add one: a reachable extra reason is an off switch an agent can always reach for,
    which is the failure this slot was designed against. In particular, these look like candidates
    and are not:
    - a change that alters behavior *while adding no test* is the **limit case** — a Class B
      **finding**, written as a count;
    - an unrunnable `TEST_CMD` is a `- gate-error:`;
    - an isolated copy that cannot be made **usable** — the suite will not go green there, or the
      change under verification cannot be materialized in it — where the human then declines the
      in-tree fallback, is **also** a `- gate-error:` (Part 2's fallback ladder) — the pass was due
      and produced no verdict, which is not the same as never being due.

    Writing `n/a` for any of them would erase a finding or excuse a binding that did not work, which
    is the one reading this slot must never permit. The `n/a: <reason>` spelling follows the
    Gate-outcome invariant's not-run vocabulary, and it is deliberately visible.
  - **omitted** — **unknown**. This is what every line written before this slot existed
    carries, and those lines keep exactly that meaning. An omission must **never** be read
    retroactively as "the pass was scoped out": the corpus is append-only and is never rewritten, so
    the only honest reading of a missing slot is that nothing produced it.

  **This slot is not where a step-8 `guard-efficacy` finding goes, at all** — that lens reads, this
  slot records what the acceptance gate's mutation pass found, and the two are distinguished at
  step 8. It is not a legal `n/a` reason; it is not this slot's business.

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

## Approach as reviewed (frozen before the design gate) — write-once, do not edit
<Verbatim copy of `## Approach` taken BEFORE the architect pass was consulted — at step 4, or at
step 5 where that step first consults it. Omit this section ONLY if no architect pass ran at all
(step 4 skipping it is not enough). It is the pre-image step 5 diffs the live
`## Approach` against to decide whether the architect materially changed the plan. Never
regenerated and never back-dated — see Resume.>

## Architect triggers hit
<which ARCHITECT_TRIGGERS fired, or "none">

## Risks / open questions for human
<empty if none>
```

### Lifecycle & commit policy
- **Init:** orchestrator creates the dir + `queue.md` from `BACKLOG_SOURCE` (see Initialization).
- **Per iteration:** update one `queue.md` row through its statuses; append the **open record** at
  step 7 and the **close record** at step 12, each owed only by an iteration that reaches that step,
  plus a block wherever a gate resolves (see `progress.md` above); write/update `issue-<N>.plan.md`.
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
     A third, distinct from those: an **isolated agent tree** the host placed inside the repository
     is neither stray scratch nor AC evidence but an artifact the parent still owes cleanup on
     (Tool surface) — never cite a `file:line` inside one. Its presence here says it was not
     removed; its **absence here says nothing**, since this scan honors `.gitignore` and runs in
     Part 1, before Part 2 below creates its own copy. `git worktree list` is what actually answers
     that question.
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
   reason to call a criterion unmet. Verify the diff actually does this; do not assume. Produce the
   complete verdict on EVERY criterion first, then deepen with whatever budget remains — never let
   deepening stop you returning a verdict; a shallow verdict is useful, no verdict is worthless
   (the Verdict-first invariant). Return a checklist + overall done/not-done."*
2. For behavior that needs runtime proof, also run `VERIFY` (runs the app).
3. `CODE_REVIEW` (step 8) provides the adversarial bug pass.
Promote to a dedicated `ac-verifier` agent only if the composed approach proves too loose.

**Part 2 — Class B: mutation survivors.** A test that this change adds or modifies, which stays
green when the behavior it guards is broken, is a **survivor** — protection the human believes they
have and does not. A survivor is a finding, **reported as prominently as a bug**. (Step 8's mandatory
`guard-efficacy` lens asks a related question by **reading** and is **not** this pass; the two are
distinguished at that step.)

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
   mutation pass is **due and runs**: the safety envelope below fixes *where* it runs, and the
   apparatus after it fixes *how*.

Questions 1 and 2 are the only ways out, and both are recorded visibly. **When any answer is
unclear, treat Class B as due** — the cost of looking is small; the cost of a wrong skip is the
entire class of defect this gate exists to catch.

**The limit case is a finding, not a silent skip — and it needs no mutation to detect.** A change
that alters behavior while adding or modifying **no** test is a Class B finding naming that absence,
never allowed to read as clean. It is read straight off the diff, so it is live from this change
onward. Nothing to mutate is not the same as nothing to worry about; it is the
guard-that-guards-nothing at its extreme.

**The safety envelope — where a mutation runs, and how the tree survives it.** A mutation pass
deliberately breaks working code, so the tree it breaks must not be the one holding your
deliverables. The envelope is specified here and the apparatus below lands *on top of* it rather
than reinventing it. **Both are live**: where question 3 answers yes, this is how the pass runs.

**Primary — the mutating agent gets its own copy of the tree.** Spawn it with the host's
worktree-isolation option, so its mutations are *physically incapable* of reaching the parent's
index. Two duties stay with the **parent**, not the agent:
- **Never stage the agent's copy.** Where the host materializes it inside the repository the parent
  sees it as an untracked directory, and a blanket `git add` lands it — as a **gitlink**, not as its
  files, which is the quiet signature described at step 6. Isolation moves the leak rather than
  closing it; explicit-path staging (step 6) is what actually covers it.
- **Remove the worktree once the agent is done.** A host that auto-cleans an *unchanged* worktree
  will not clean this one — a mutation agent changes it by definition.

**Its precondition, which often fails: `TEST_CMD` must be green *in the copy*.** A bare copy carries
none of the environment a suite needs — installed dependencies, build artifacts, an activated
environment — so a suite that passes in the parent can be unrunnable beside it. Confirm it green in
the copy **before** the mutating run begins.

**Its second precondition, and the one whose failure is silent: the copy must contain the change
under verification — check it, never assume it.** How a host materializes an isolated tree is a
**host** fact this engine deliberately does not know (Tool surface), and step 10 certifies work in
every commit state including **wholly uncommitted** (Part 1). A copy taken from a commit therefore
carries none of the uncommitted remainder. **At this point in the pipeline that remainder is usually
small — and the check matters anyway.** Step 7 committed and opened the PR, and step 8 committed its
fixes, so on most iterations the change is already committed here; the residue is a fix
written but not yet committed, or whatever a crash left behind. That is a **narrower** target than
it once was, not a safer one: a copy missing the one uncommitted fix mutates the code as it stood
*before* that fix, and reports clean. Do not read the shrinking remainder as licence to skip the
check. Confirm with `git -C <copy> diff "$BASE" --stat`, using the **same `$BASE`**
Part 1 resolved: every file the change adds or modifies must appear, and **the added or modified
test above all**, since that guard is the whole object of the pass. **Pair it with `git -C <copy>
ls-files --others --exclude-standard`, for the reason Part 1 pairs them:** a diff never shows an
untracked file, and a brand-new test is both among the commonest forms of AC evidence and the most
likely thing this pass is here to mutate. Checking with the diff alone would miss exactly the case
the gate is most due on — and would miss it *silently*, since a copy lacking the new file simply
mutates the old code instead.

**Both failure shapes are real, and only one of them is loud.** If the spec's `find` strings are
absent from the copy the harness errors — safe, and now rare, since the change is normally committed
by the time this gate runs. **Rarity is what makes it worth naming, not what retires it:** an
escalation that fires on most iterations degrades into a per-iteration click-through, while one that
fires on few is the one nobody has kept in mind when it finally does. The silent shape is the
dangerous one: where the change
edits an **existing** file, the old text still matches, the copy's **old** suite — the one without
the new test — kills the mutant, and the pass exits clean. **The gate then certifies that the new
guard guards, having never seen the new guard.** That is the manufactured confidence this whole part
exists to refuse, and nothing downstream can detect it: the harness has no notion of "the change",
so no exit code distinguishes this from a real clean pass. The check above is the only thing that
does.

**Materialize the change in the copy before mutating** — applying the step-10 working-tree diff into
it is the obvious mechanism. **Do not commit the parent's work merely to create it**: this gate
owns exactly one commit boundary — the one that lands *its own fixes* (step 10) — and committing
the parent's work early, to make a copy convenient, is not that. A gate written to certify work in
any commit state must not require a commit to run. If the
change cannot be materialized in the copy, the copy is unusable for this pass and takes exactly the
rung below.

**If it cannot be made green, the fallback is in-tree mutation with BOTH compensating controls —
explicit-path staging (step 6) **and** the restore journal (below) — and never in-tree mutation
alone.** But **do not take that rung on your own judgement.** It moves a deliberately-destructive
operation onto the tree holding the human's uncommitted work, which is a destructive and
irreversible action, so the Escalation rubric applies: **escalate to the human and let them choose
it.** If they decline, the pass was due and produced no verdict, so emit
`- gate-error: acceptance (Class B) — isolated copy unusable: <TEST_CMD unrunnable | change under
verification not present> — <first line of the error>` and STOP. **One gate-error shape covers both
preconditions**, so widening the ladder never needs a second spelling. **Do not record
`mutation-survivors=n/a`**: that list is closed at two reasons and neither of them is this one
(progress.md → the Budget line). An unrunnable `TEST_CMD` was *already* ruled a `- gate-error:`
everywhere else, and "the copy could not run the tests" as an `n/a` is an off switch that silently
upgrades its own blast radius, the shape Part 2's three questions are deliberately written to
exclude.

**Restore from a pre-mutation copy of the file, never from the index.** On the in-tree path, copy
each file before mutating it and restore from that copy. **Never `git checkout`/`git restore` a file
to undo a mutation** — the index does not know about work in progress, so restoring from it silently
destroys uncommitted work the mutation never touched. This prohibition is scoped to *undoing a
mutation*: Resume's working-tree reconciliation uses `git restore`/stash legitimately, on crash
leftovers no mutation produced. Under isolation the whole question is moot — nothing in the parent
was mutated, so there is nothing to restore.

**Journal the restore, whichever path ran.** Whenever a pass applies **≥1 mutation**, it emits the
`- Restore:` line (Ledger format → progress.md), under isolation as well as in-tree.
This is the **only detection mechanism** in the envelope: everything above is prevention, and
prevention that fails, fails silently — the line is what surfaces a leak instead of waiting for a
reviewer to notice broken code in a diff. It is therefore **not** conditional on isolation having
worked.

**The apparatus — what actually runs the pass.** Three things were deferred here until there was
something to execute: the **actor split**, the **applied-check**, and **interrupted-pass recovery**.
All three are specified below. The applied-check is enforced mechanically by the harness that ships
with the plugin as `${CLAUDE_PLUGIN_ROOT}/tools/mutate_verify.py`; the actor split and recovery are
procedure, and nothing in that script knows about either.

**Use the harness. Do NOT improvise a mutation procedure.** That prohibition has not been lifted —
it has been given something to point at. An improvised pass reporting a clean result is the
manufactured confidence named above, and a hand-rolled one on the in-tree path edits production code
beside your uncommitted deliverables with no restore guarantee, which is the one way this gate can
destroy work rather than protect it. The **judgment** half — choosing a mechanism-preserving
mutation, reading a survivor — is yours and cannot be scripted. The **mechanical** half is not yours
to re-invent:

```
python3 "${CLAUDE_PLUGIN_ROOT}/tools/mutate_verify.py" run \
    --spec <spec.json> --test-cmd "<TEST_CMD>" --root "<the tree being mutated>"
```

`--test-cmd` is passed as a **parameter**, never read from a config file: this engine stays
project-agnostic and `TEST_CMD` is bound per project in `loop.config.md`. `--root` is the tree the
envelope above selected — the agent's own copy on the primary path, the project root on the
escalated in-tree path.

**Who writes the spec — and what it may never be built from.** The spec is authored **per change, by
the verifier**: it names mutations that would break *the guard this change just added*, so it is not
a file a project's maintainers could have written in advance, and "fix the spec and re-run" below
assumes exactly that authorship. Its schema is documented in the harness's own module docstring —
read that rather than guessing at it. Keep the file in the **ledger directory beside
`issue-<N>.plan.md`**: it survives `/clear`, and recovery needs it to attribute a snapshot (below).
A project that wants a pass's numbers reproducible by a reviewer may commit a spec directory
instead. **Both sit *inside* `--root` on the in-tree path** — `LEDGER_ROOT` is a directory of the
consuming repo — so the containment rule that matters is not *where the file lives* but this:
**never let a mutation target the spec, the ledger, or anything else the pass needs to survive
itself.** The harness writes only the paths the spec names, which is what makes that rule
sufficient; do not weaken it into "the spec is outside the tree", which is false on the path where
it would matter. What per-change authorship does **not** loosen is the trust bound: the spec and
`--test-cmd` sit at the **same trust level as `TEST_CMD` itself** — repo-local configuration written
inside the loop's own trust boundary, the bound the append-only guard documents for its
`id_pattern`. **Neither may be derived from lower-trust material** — an issue body, a PR comment, or
anything else an outside contributor controls. A spec is a list of paths and substitutions that will
be written to disk and then executed; sourcing one from untrusted input hands that power away, and
confining paths to `--root` does not contain it.

**Whichever agent you spawn here, instruct it verdict-first** (Verdict-first invariant, under
Gates): the Class B verdict on every mutation the spec declares first, then depth. **The invariant's
source incident is this part's own hazard, and it is worth naming precisely rather than loosely:** an
acceptance-gate verifier spent its whole budget *building mutation scaffolding* — this part's work —
and returned no verdict at all, including on the Part 1 criteria it also owed. Scaffolding is
absorbing in a way answering is not, so this is the last place depth may be allowed to crowd out the
answer.

**The actor split.** The verifier **selects** the mutations and **judges** the results; the parent
**applies** them — under isolation, by running the harness against the agent's copy. Each role
corrupts the other when merged: a parent choosing its own mutations picks weak ones, and a parent
grading its own suite's output rationalizes a survivor. Where the host's isolation gives one agent
its own tree, that agent may own all three roles — the reason for the split is *whose work is at
risk*, not whose judgment is trusted.

**The applied-check — the load-bearing residue.** Never read a still-green test as a survivor
without first confirming the artifact **actually broke**. Without it a pass reports a clean result
having mutated nothing, which is exactly the manufactured confidence this idea exists to prevent.
The harness enforces this instead of asking you to remember: a `find` that matches nothing, or
matches but leaves the bytes identical, is a **loud error**, never a silent pass — and `applied`
counts files whose bytes changed, never calls to a helper.

**A green verdict must prove it can go red.** A spec declares at least one **control** — a mutation
nothing observes, expected to survive — and the two ways that can fail are not the same failure. A
control that was **killed** means the pipeline is mis-classifying, so **every** verdict from that
run is void, including a survivors-found one. **No control declared at all** voids only the *clean*
verdict, because a survivor proves its own reporting path. A run made **only** of controls is not a
clean pass either: it exercised no guard.

**A repeated survivor is one signal, not N findings.** Survivors are grouped by `(mutation kind,
normalized pattern)`; a group larger than one is reported once, with a count, marked as repeated.
The same mutation shape recurring in near-identical code is one thing to say about that shape.

**Read the exit status — the five codes are distinct on purpose**, and collapsing any two of them
lets a result read as a different result:

| Exit | Meaning | What you do |
|---|---|---|
| `0` | clean — every real mutation killed, and a control proved the pipeline can report a survivor | `mutation-survivors=0` |
| `1` | the pass worked and found survivors — **a result, not an error** | Class B findings; each blocks |
| `2` | harness error — no match, a no-op mutation, a bad spec, a red baseline, a control that was **killed**, a spec made only of controls, or any other harness failure | `- gate-error:`, STOP |
| `3` | unproven — no control, so the clean verdict is not trustworthy | not a pass; add a control and re-run. If a control cannot be produced, the pass was due and produced no verdict: `- gate-error:` and STOP — **never `=0`**, which would report an unproven pipeline as a clean one, and never `n/a` |
| `4` | restore failed — **a mutation may still be live in the tree** | `- Restore: finding`, and **read the harness's error lines before touching anything** — see below |

**Exit 4 has two shapes and they take opposite actions, which is why the row above sends you to the
error text first.** Where the harness reports that it **refused** to restore because the file changed
underneath it, the snapshot no longer describes that file: writing it back destroys whatever changed
it, which is the one harm this entire envelope exists to prevent. **Escalate; do not restore.** Where
the restore merely failed, the snapshot still describes "before" and repairing from it is correct.
The general rule, of which the missing-snapshot case (the `- Restore:` line) is the other instance:
**a snapshot is safe repair material only while it still describes the file's pre-mutation state — a
snapshot that has been overtaken is as gone as one that was never taken.**

**Interrupted-pass recovery — keyed on the artifacts, never on the journal.** A later invocation can
land on a tree holding live mutations, or on snapshots with no pass left to own them. Key recovery
on two artifacts that outlive the pass: a **retained snapshot directory**, which self-clears (the harness deletes it
on every path where the tree was restored and verified, so a surviving one means the tree may still
hold a mutation) and a **leftover isolated copy** in `git worktree list`.

**Where the snapshots are, because a procedure that keys on an artifact must say how to find it.**
The harness puts them in a `mutate-verify-*` directory under the **system temp dir**, deliberately
outside the repository — snapshots inside it would be visible to the test command, stageable by a
blanket `git add`, and indistinguishable from the deliverables they exist to protect. The cost of
that choice is the one you must plan for: the directory is invisible to both `git status` and `git
worktree list`, so **neither of the checks you would reach for first will find it** — list the temp
dir. A pass that exits normally prints the retained path; the case that matters most is the one that
does not (below), which is why the location is written here rather than left to the report.

Do **not** key it on an
unclosed `- mutation-pass: started`-style journal line: `progress.md` is append-only and a human
repair never comes back to close the entry, so such a line stays unclosed forever and would license
restoring a stale snapshot over live work. **The journal line is audit, not state.** Restore from
the snapshots, never with `git checkout`/`git restore` (above); if the snapshots are what went
missing, the safe repair is gone — escalate to the human.

**A retained snapshot is a *candidate*, not a verdict — and it is not self-describing.** The
directory self-clears per run, but nothing scopes it to *this* iteration: a pass that died weeks ago
leaves one behind exactly as a pass that died a minute ago does, and developing the harness itself
leaves a drift of them. Worse, snapshots are named by **basename only**, so the directory tells you
*that* a pass may have died and by itself tells you neither which file, nor which run, nor which
**repository** — and every run of every project lands in the same temp dir. A same-named file from
another clone restored over this one by basename inference is a cross-repository data loss, invented
entirely by the recovery step.

So attribute **positively** before any write, and prefer the check that needs no attribution at all:
an in-tree mutation is a deliberate break in a source file, so it is usually visible in the parent's
`git diff` and would fail `TEST_CMD` (usually — not a guarantee, since the mutated file need not be
tracked; the retained directory stays the fail-safe signal that does not depend on it). To attribute,
use the run's report if you still have it, and otherwise **the iteration's spec**, which carries
every target's relative path and its `find`/`replace`. That is what makes the spec's location
matter: **keep it in the ledger directory beside `issue-<N>.plan.md`**, where it survives `/clear`
for the same reason the rest of the ledger does. Attribute by **content** — does the live file differ
from its snapshot by exactly some spec entry's `find`→`replace`? — never by the snapshot's filename
or its ordering, which nothing pins.

**Then treat "different" as a trigger, not an authorization.** Identical is a sound conclusion: the
file is intact and restoring would be a no-op anyway — delete the snapshot and move on. Different has
three causes — a live mutation, a human edit since the snapshot, or both — and the comparison cannot
separate them. Inspect the difference: restore only where it is the mutation and nothing else, and
**escalate wherever anything else is in there**, because that is the overtaken-snapshot case above.
A snapshot you cannot attribute to a specific file **in this repository** is never written anywhere.

**One case the artifacts do not cover, stated plainly because a silent gap here is the whole
hazard:** a pass killed by a signal runs no cleanup and prints nothing, so the mutation stays in the
tree with its snapshots intact and unannounced. That is precisely why recovery keys on the presence
of the snapshot directory rather than on anything the pass said before it died.

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
   gate**, per route; it never affects the plan gate. **Set `plan-gate:` on the same branch you just
   took** — `calibration` ⇒ `plan-gate: always`; the prior-graduation branch ⇒
   `plan-gate: conditional` — so the plan gate's posture starts consistent with the trust level the
   project has actually established. Write it explicitly even though an absent field would read as
   `always` (step 5): the human tunes what they can see, and a field that only exists once someone
   needs to loosen it is one they will not know to look for. After init the two are independent —
   a later `mode:` change never rewrites `plan-gate:`. Also set `iteration-cap: none` and
   `subagent-cap: none` (the human sets them when loosening).
5. Append an "init" block to `progress.md`. (Ledger is gitignored — not committed.)

---

## Resume after `/clear` or compaction
The next invocation's step-0 resume (step 3) reads `queue.md` + tail of `progress.md` and, finding
any *interrupted* row (a **pipeline** status other than `queued`/`routed`), finishes it before
selecting new work. **An interruption need not have left a row**, so that scan is not the whole of
resume: step 0.3 also looks for an open PR that no row covers, and states both the test and its
default-deny close — do not re-derive them here. Such a PR is **reported to the human**, with any
**open record** in `progress.md` (Ledger format → `progress.md`) as evidence; step 7 writes that
record for exactly this case. The scan does not reconcile or reconstruct a missing row.

**A row whose Status is not in the closed vocabulary at all STOPS the run for
the human** — it is not an interrupted row and never enters the live reconcile below (Ledger
format → queue.md, which is where that rule and its limits are stated). A `hold` **or `parked`** row is **excluded** — a `hold` is a deliberate, durable
human merge-hold and a `parked` row is gated on an external event (Ledger format → queue.md),
neither an interruption; leave them (a `hold` until the human clears it at step 11; a `parked` row
until explicit un-park at step 0.1) and neither blocks other work. A run resting under a `RUN
PARKED` sentinel is likewise **not** an interrupted row — step 0 short-circuits it on the cheap
parked path and never enters this resume *row* scan (safe for rows: a valid PARKED state has no
non-terminal pipeline row — it says nothing about state with no row). The on-disk ledger row status
is only a **coarse anchor** (which stage); the **live
git/PR state is the source of truth** for the details (the ledger is uncommitted): for an in-flight
row, check whether its branch exists, whether a PR is open (or already merged), and the PR's CI
status, and resume at the matching pipeline stage — git wins on any conflict with a stale status.
Stages 4/9 need no distinct status because the surrounding statuses bracket them: a
`plan-approved` row re-enters at implement (step 6), so the architect/human gates are NOT re-run.
**The acceptance gate is no longer one of them.** It is now the last gate (step 10), so `in-review`
would otherwise bracket review, security, acceptance *and* merge — and a resume anywhere in that
span would replay the whole code-review fan-out. `in-acceptance` is what stops that: a row resuming
under it re-enters at acceptance, not at review.
The architect pass (step 4, or step 5 where that step first consults `DESIGN_AGENT`) carries **two**
side effects, and on the resume of a `planning` row both
are **write-once** — check for the artifact and skip the action if it is present. **Expect this
resume to be common, not exceptional:** under `plan-gate: always` every issue stops at step 5 with
its row still `planning`, and `planning` is a pipeline status, so step 0.3 classifies it
*interrupted* — meaning any `/clear` between
the plan gate and the human's approval lands here. The write-once guards below are what make that
safe; do not relax them on the assumption that this path is rare.

**A `planning` row is by definition unapproved — it re-enters at step 5, never past it.** The
status vocabulary is the whole record here: step 3 sets `planning`, and step 5 advances to
`plan-approved` *only* on an approval. So a row still reading `planning` did not get one, however
complete its artifacts look. **A `- Plan-gate:` line already in `progress.md` is not evidence of
approval** — it records what the architect's frozen-vs-live diff returned, which resolves *before*
the human answers; finding one means the gate was reached, not that it was passed. Neither does a
recorded architect outcome — however this project records it — a written frozen block, or an updated
`## Approach`. The carry-forward
rule for gates decided in a prior iteration applies to rows that re-enter *past* step 5; this one
has not left it.
1. it records the architect's outcome — check for an existing record, do not double-post.
   **Look wherever *this* project records architect decisions, not only in issue comments.** The
   surfaces in use across real consumers are an **issue comment**, an **issue-body marker** (a line
   in the body itself, e.g. "Architect review complete — approved <date>"), and a **decision-log
   entry** in the repo. A project may use more than one, and some use no comments at all — so
   "no comment found" is **not** evidence the architect never ran, and treating it as such
   re-invokes a gate that already ran and, worse, invites the back-dated freeze that (2) below bars.
   If you cannot establish which surface this project uses, that is a question for the human, not a
   reason to re-invoke.
   **But do not treat the record as the whole of the step:** if a record exists and `## Approach`
   does not yet reflect its `blocking`/`important` outcome, the crash landed between the two, so
   **apply the outcome now** (step 4) before reaching step 5. Skipping the re-invoke while leaving
   the outcome unapplied strands it — the diff comes back empty and the always-on stop passes
   silently, on the one path this guard was added to harden;
2. it freezes `## Approach as reviewed (frozen before the design gate) — write-once, do not edit`
   into `issue-<N>.plan.md`
   **before** invoking the agent — **if that block exists, leave it exactly as it is; and if the
   step-4 pass already ran without one, do not manufacture it now.** (This bars only a *back-dated*
   freeze. Where step 5 is about to consult `DESIGN_AGENT` for the first time, the freeze is owed
   and taken then, as normal.) Both halves matter and they fail in opposite directions: a
   rewrite overwrites the pre-image, while a *late* freeze manufactures one out of the already-
   redirected `## Approach` — either way step 5 diffs a text against itself, gets nothing, and the
   always-on stop passes silently. A block that was never written is the **absent pre-image** case
   (step 5): if the architect ran, that is **material**, and no freeze performed now can turn it back
   into evidence. Re-running
   the copy on resume would capture the *post*-architect approach as the pre-image, so step 5's
   materiality diff would come back empty and the always-on stop would **silently pass**. A resumed
   iteration is the one case where the pre-image and the live text have already diverged, which is
   precisely when the guard matters.

AC-verify (step 10) has **no write-once artifact to double-create** — nothing it does is a side
effect resume must avoid repeating, which is the only property this paragraph turns on. **It is not
side-effect-*free*:** its mutation pass deliberately breaks source, and it commits its own fixes.
That is why the rule below exists in the shape it does — but note what it does **not** license. The
mutation check (a) is deliberately **not** scoped by status, because a crash can leave a status
stale. Only (b)'s default turns on the row's status. Security (step 9) re-labeling is a no-op.

**Working-tree reconciliation — two mechanisms, and collapsing them is the failure mode.** If a
crashed prior attempt left uncommitted changes, inspect them before proceeding. Run (a) first,
always; **if (a) escalates, stop there — (b) is not reached**; otherwise apply (b).

**(a) The unfinished-mutation check, which runs on every resume whatever the row's status.** Before
any other work on the tree, run `git worktree list` and list the system temp dir for a retained
snapshot directory. **If either is present, hand off to AC-verifier → Part 2, *Interrupted-pass
recovery*, which owns the diagnosis, the repair, and when to escalate — do not re-derive it here.**
Two things are worth knowing before you hand off, because they decide whether you hand off at all:
the trigger is the *artifacts*, never the status (a crash can leave a status stale, so keying this
check on one would let a mislabeled row carry a live mutation straight past it), and `git restore`
is exactly what must not repair a mutation (it restores from the index, which does not know about
the surrounding work in progress). Once Part 2's recovery completes **without escalating**, remove
any leftover copy per Part 2 and Tool surface's **collect-then-remove** duty — the copy's contents
are sometimes the deliverable, so that duty governs and this paragraph does not override it.

**(b) What to do with uncommitted changes (a) did not account for — the one place the row's status
sets the default.**
- **On an `in-review` or `in-acceptance` resume: do not keep a production-code delta you cannot
  attribute.** Attributable means you can place it in something specific — a fix this gate's own
  round wrote, or a review finding it answers — and **not** merely that it looks plausible.
  **Plausibility is what a mutation counterfeits:** it is built to be a small, sane-looking edit, so
  "it matches the plan" is the one test it is designed to pass, which is why the plan is not an
  attribution source on these rows. These rows are past implement, so no stage is still legitimately
  producing *unexplained* work in the tree. Where the change **is** this gate's own uncommitted fix,
  that is attributable and **kept** — step 10 mandates a window in which such a fix is written and
  not yet committed, so expect to meet it here.
- **Where you cannot attribute it, STOP and ask the human — do not `git restore` it.** The same
  inability to attribute it is an inability to recover it, and keeping it is equally wrong.
  **Not-keeping and destroying are different actions, and only the human chooses the second.**
- **On any other resume (`implementing` above all): keep and continue where you can place the
  changes in the plan.** An interrupted implement step leaves *legitimate* work in progress, and
  **incomplete is expected here — never on its own a reason to discard.** Use `git restore`/stash
  only where a change belongs to no plan step at all. This is the default only; (a) has already run
  regardless of status.

A resumed `implementing` row is NOT "stuck" (stuck
keys on a repeated error signature, not status re-entry — see Guardrails).

---

## Routing table

| Route | Pipeline differences |
|-------|----------------------|
| `code` | full pipeline, all gates; the declared-offline tier (`HERMETIC_TEST_CMD`) runs at step 6 when the change adds or modifies a test; the acceptance gate's **mutation pass** (Class B) is due when the change alters behavior and adds or modifies a test, and **runs** via the harness (AC-verifier → Part 2); when it alters behavior while adding **none**, that absence is itself a Class B finding, never a silent skip |
| `research` | lighter plan; **no test-coverage gate**; architect optional; security only if deps added; place outside the package source. No test-coverage gate means **nothing to mutate** — no mutation pass, and no hermetic-tier run (`n/a: research route`) |
| `docs` | skip architect + security; light review; `docs:` scope; **no mutation pass**, and no hermetic-tier run (`n/a: docs route`) |
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
| Architect | `DESIGN_AGENT` | `ARCHITECT_TRIGGERS` or unsure | the agent's review, **recorded by you** wherever this project records architect decisions — issue comment, issue-body marker, or decision-log entry (Resume) |
| Human (plan) | user | **every issue under `plan-gate: always`** (the default under `calibration`; absent or unrecognized reads as `always`); under `plan-gate: conditional`, if uncertain/irreversible. Under **both**, **always** when the architect materially changed the plan (step 5's frozen-vs-live diff — decisiveness escalates exactly as a punt does, and neither `mode:`, `plan-gate:`, nor route graduation reaches this one) | approve/redirect |
| Build commands (`LINT_CMD`/`TYPE_CMD`/`TEST_CMD`/`HERMETIC_TEST_CMD`) | orchestrator | step 6, each per its own binding; `HERMETIC_TEST_CMD` additionally requires Route `code` **and** a change that adds or modifies a test, **whatever the binding says** — on such a row an absent or `TODO` binding is unknown, and unknown is due (the gate's four-state table) | **exit status per command**; non-zero blocks |
| Code review | `CODE_REVIEW` (parallel finders you run — step 8); **the fix's re-check a fresh checker, not you** (Fresh-re-check invariant) | every issue; one light pass on `docs` | findings → fixes, each carrying a **finding class**: BLOCKING re-arms; EDITORIAL raised before step 8's sweep is swept there, and anything raised after that sweep escalates |
| Security | `SECURITY_REVIEW` (local or label) | by route (step 9) | clean/findings |
| AC-verify | fresh subagent (+`VERIFY`); **any re-check a fresh instance too** (Fresh-re-check invariant) | every issue with acceptance criteria (step 10 is unconditional; the **mutation pass within it** is scoped — Routing table). **Last gate before merge**, so it certifies the merge candidate and owns the commit boundary for its own fixes | done/not-done + gaps, as **two separate counts**: Class A (AC-satisfaction) and Class B (mutation survivors); **either class blocks** |
| Merge | user (calibration / non-graduated route) → orchestrator (auto: graduated routes) | CI + security + acceptance green | `MERGE_METHOD` |

**Gate-outcome invariant (evidence-bound pass).** Applies to every gate in the table above that
returns a verdict, **on the rows that gate is due on** — due-ness is decided by the gate's **When**
entry in the Gate table above and by the Routing table's per-route column, **both in this file**,
and this invariant does not touch it. (The one gate whose due-ness is knowable only from its
binding is `HERMETIC_TEST_CMD`; its carve-out below states that unknown reads as due.) A gate the
route or its trigger condition never made due was never owed a verdict, so journal it as not run
(`skipped` / `n/a`) with the reason; not-due is not a pass either. An explicit `—` **plus a
reason** in the config is a deliberate "not applicable", journalled `n/a: <that reason>` — **not**
an absent binding; it is the only way a config marks a gate not-due, and it is deliberately
visible.

**The Build commands row is in the table, so this invariant reaches step 6 by rule, not by
analogy.** `LINT_CMD`/`TYPE_CMD`/`TEST_CMD`/`HERMETIC_TEST_CMD` are bindings that return a verdict —
an exit status, the crispest kind — so each is `n/a` only with `—` plus a reason, and an unrunnable
one is a `- gate-error:`. This is what the `mutation-survivors` slot already assumed in ruling that
"an unrunnable `TEST_CMD` is a `- gate-error:`" (progress.md → the Budget line); stating it here puts
the whole class on the rule instead of on that one aside. **Three of the four need no journal slot
of their own:** `LINT_CMD`/`TYPE_CMD`/`TEST_CMD` run on every issue and the iteration cannot reach
step 7 until each exits zero, so *the absence of a `- gate-error:` naming one is the record that it
passed*. **A `—`-plus-a-reason build command is the exception and is written out**, as
`- Lint: n/a: <reason>` (likewise `- Type:`, `- Test:`): the invariant requires a deliberate
not-applicable to be *visible*, and an absence cannot carry a reason. Absence means "it ran and the
iteration got past it"; it never means "it was not due". `HERMETIC_TEST_CMD` gets the `- Hermetic:` line because it is the only one of the four that
is **conditionally due**, so for it "no line" would be ambiguous between ran-clean and never-ran.

**One carve-out, for the one gate whose due-ness is knowable only from its binding.** The paragraph
above says due-ness is settled before this invariant applies — true of every gate except
`HERMETIC_TEST_CMD`, where whether a hermetic tier exists *is* the binding. For that gate an absent
or `TODO`-valued row reads as **unknown, and unknown is due** — never as "the trigger never made it
due", which is the fail-open reading this invariant's own wording would otherwise license. It
applies only where the gate's own trigger fired: a missing binding never makes a gate due that
nothing else made due. Its four config states are tabulated once, at the gate itself; this is the
rule, that is the table. An **unbound** row was never attempted and has no command to quote, so
write the literal `- gate-error: hermetic — HERMETIC_TEST_CMD unbound — no-binding`; the
`no-stderr` convention below is the precedent for naming an absent string rather than inventing one.

For a gate that **is** due: it may be journalled **passed** only with the gate's own verdict as
evidence — it ran and returned clean/met. **No verdict ⇒ not passed**, and there are two ways that
happens. The discriminator is **what you can see without running it**: your own config and toolset
are *inspection*, so a binding naming a skill, agent or command absent from them is **static** —
anything that surfaces only when the thing is actually run is **dynamic**.
- **Cannot run (static)** — by inspection, the binding is absent, `TODO`-valued, or names something
  missing from your toolset or that you are not permitted to invoke. Fall back to the engine's
  inline composition where one is defined, otherwise escalate to the human. Step 8 is this branch's
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

**Currency — a verdict is bound to the commit it ran on.** The two branches above are about a gate
that produced **no** verdict. Another way a gate ends up not having passed, and the one that looks
like success: the gate ran, returned clean, and then **the merge candidate changed
underneath it**. A later commit is a commit no gate ran on, so the earlier verdict does not reach
it. Step 10's "a gate that never saw a change has not passed it" is this clause applied at that
gate. The clause binds every gate above **whose verdict is about a diff or a commit** — the build
commands, code review, security, AC-verify, and the merge gate's own precondition. The plan,
architect and human-plan gates certify an *approach*, not a commit; carrying those across a resume
is Resume's rule, not this one.

**The remedy, before the detail: re-run the re-armed gate, or STOP and escalate to the human. Never
journal or merge on the superseded verdict.** Where the gate's own step states what a re-run costs,
follow it; **where no step states one, escalate — an unowned re-arm is escalated, never absorbed.**
A step-9 fix re-arming code review is *owned*: step 8 states its cost, so it is re-checked under
**step 8's own round budget** by a fresh checker (Fresh-re-check invariant), not escalated. **A
budget already spent does not make it owned anyway** — if step 8 used both rounds, nothing remains
to certify the re-arm, so it becomes an unowned re-arm and **escalates**. Ownership is a live round,
not a step that once had one; a round invented to fit is a cap that does not bind (step 10).
Escalation is for a re-arm no step owns — at the acceptance gate, every source-changing fix, per
step 10's three constraints.
And **commit the change first**, under step 6's explicit-path staging rule: the acceptance gate
reads the working tree, so an uncommitted fix can be **detected** there and still be absent from
what merges — **detecting is not certifying** (step 8).

**It holds whatever produced the change** — the rule is about the *change*, never about its author.
The sources below are the ones this pipeline is known to produce; treat the list as **sufficient,
not exhaustive**, and extend it rather than reading an unlisted source as exempt:
- a fix the **acceptance gate itself** made (step 10) — the one the gate order newly creates;
- a **CI fix** after a gate has run (CI first runs at step 7, but the branch can redden later);
- a change the **human asked for at the merge gate** (step 11);
- **bringing the branch up to date with its base**, where the host requires that before merging.
  This re-arms every gate that reads the **tree** rather than the diff — CI **and** the build
  commands (`LINT_CMD`/`TYPE_CMD`/`TEST_CMD`/`HERMETIC_TEST_CMD`). If you cannot tell what the
  update touched, re-arm.

**Review and security fixes (steps 8 and 9) do not re-arm the *acceptance* gate** — it runs
downstream of them, which is the gate order's payoff, and re-running it for them is the waste this
rule must not create. **They still re-arm gates that ran before them**, and two cases are live: a
test added at step 8 re-arms step 6's hermetic trigger (step 6), and a step-9 security fix commits
under step 8's rule, so it lands after code review certified the head and that verdict does not
reach it.

**Scope it by what the change touches.** A change touching neither source nor tests — a citation, a
doc line — re-arms nothing, the same line step 10 already draws for its own fixes. A **test-only**
change is not in that set, per step 6's trigger above. This exemption is **narrow** — if you cannot
decide whether a change alters source, it does; re-arm.

**When the pipeline cannot re-run a re-armed gate, the human's disposition is what releases the
row — and it is not a pass.** Step 10's three constraints (ordering, round, status) can leave a gate
re-armed with no way to re-run it inside the pipeline. That is an escalation, and the human's answer
on it releases the row. Record it in the row's Notes and in `progress.md` as a **human decision**,
naming the gate and the commit its verdict does not cover — **never on a `- gate-fallback:` line**,
whose fixed shape is for a binding defect and its substitution, and which Guardrails excludes from
the repeat check. **A human deciding to merge is not a gate certifying the code** — the record must
keep those two distinguishable, or the ledger reports a pass that never happened.

**Fresh-re-check invariant (a fix is never checked by its author).** Applies to the two gates that
carry a round cap, and so re-check a fix inside the pipeline under a bounded budget: the
**acceptance gate** (step 10, *both* result classes) and **code review** (step 8). When a gate comes
back dirty
and you fix what it found, the re-check is performed by a **fresh instance**. You wrote the fix, so
you are the one reader who cannot check it: the belief that produced the defect is still present
while the fix is written. **You are an author of every fix made in this iteration, including one you
delegated** — directing a fix is authorship for this rule, so handing the writing to a subagent and
reading it yourself satisfies nothing.

**Read this as a rule about round *two*, and about three clauses in particular** — both gates
already spawn fresh subagents for the first round they actually run today (step 10 Part 1, step 8's
finders), so the parts that actually bind are narrow:
- **Step 8's "verify recs were applied" is the sharpest hole it closes.** Confirming your own
  remediation is not a gate; it is the author agreeing with himself. Spawn a checker for it.
- **A re-check must not collapse into the parent thread** re-reading its own diff — the commonest
  shape, because it is the cheapest.
- **Nor into the round-1 agent re-contacted.** That agent carries its own prior conclusions, which is
  the same contamination one level up. **"Fresh" means a new spawn**, every time.

**What the fresh checker receives — and it differs by gate.** In every case it gets **none of your
conclusions about whether the fix worked**; that is the exclusion Part 1 already draws (it withholds
your *conclusions*, not the instructions the checker needs).
- **Acceptance gate (step 10), Class A — re-run Part 1's recipe unchanged:** the acceptance criteria
  verbatim, the resolved `$BASE`, and the commands under **Verifier runs**, with nothing added. The
  criteria are the yardstick, so a round-2 checker that re-derives met/not-met from scratch is *more*
  independent than one handed a list of claimed repairs. **Do not relax Part 1's `ONLY` here** — a
  claimed-repairs list is a claim, which that list exists to exclude.
- **Acceptance gate, Class B — the limit case needs its own recipe.** Where the
  finding was the *absence* of a guard (behavior altered, no test added — read straight off the
  diff, so it needs no apparatus), the re-checker receives the change as it now stands plus the
  behavior the missing guard was meant to cover, and none of your claims about the test you added.
  Its question is: **do the new test's assertions pin the *mechanism* that would break, or only an
  *outcome* a broken implementation would still produce?** It answers by **reading them** — never by
  running or altering anything — and **if it cannot tell, that is a dirty result, not a clean one.**
  **The spawn prompt must carry four things the checker would otherwise never see**, since it reads
  neither Part 2 nor this section:
  1. the **blockquote** under Part 2 — the `write_bytes`-versus-`mkstemp` passage, not the one-line
     slogan alone — **pasted verbatim**: that is the yardstick, and its worked example is what makes
     the distinction operable;
  2. that it **must not edit, break, or execute code to decide**, since the prohibition on
     improvising a mutation does not otherwise reach it, and a checker that breaks the code to see
     what fails has done the one thing this gate forbids;
  3. that it **must say plainly when it cannot tell** — the rule making that a dirty result lives
     here, where the checker cannot see it, so an unprompted checker hedges and the gate reads
     clean;
  4. the **Verdict-first invariant** (Gates) — answer the question put to it first, then deepen.

  (**This recipe has a second caller.** Step 8's mandatory `guard-efficacy` lens borrows its
  answering discipline and its blockquote, but not this bullet's antecedent — that lens runs with no
  prior finding and no fix in hand. What follows is written for the acceptance gate.)

  **Why a read is a legitimate check here, when Part 2 says only mutation detects a survivor.**
  Two reasons, each from this engine's own text rather than from the cost of mutating: the defect
  is, in the quote's own words, *a property of the assertion* — so it is visible **in the
  assertion**, to a reader who knows which behavior is at risk, and this checker is handed that
  behavior (above); and the fix side already applies this yardstick without mutating anything
  (`Strengthen the guard (assert the *mechanism*, per the quote above, not the outcome)`), so
  reading whether the mechanism *is* asserted is the symmetric operation. "Cannot tell ⇒ dirty"
  keeps it fail-safe where an instruction to be careful never is. None of this substitutes for the
  apparatus — a *surviving mutant* still requires it, and no argument here is offered against
  "only mutation detects it."
  (**A re-check of a *surviving mutant* re-runs the harness on the same spec entry, with its control
  retained** — a lone entry declares no control, so the harness returns *unproven* on exactly the
  outcome the re-check is looking for, a kill (a survivor is self-proving and still reports as one)
  — and after the guard is strengthened the mutation must come back **killed**; a re-read is not
  sufficient there,
  precisely because the survivor was established by running rather than by reading. That re-run is a
  fresh instance too, per the invariant above.)
- **Code review (step 8) — the previous round's findings *and its declines*, the diff since the head
  that round ran on, and one narrowed question.** Review has no fixed yardstick to re-derive from,
  so those lists are what give the checker something to test rather than a blank re-review. Its diff
  input is **`git diff <reviewed>..HEAD`** — what has changed since the head the last round read
  (step 8, which fixes the anchor, validates it, and says when the round is **full** instead). Its
  question is: **are these findings discharged, and does the new delta introduce anything?** **State
  in the prompt that earlier material carries a verdict and is not re-litigated** — a checker handed
  a diff and no such instruction re-reviews the diff it was handed, which is the cost this scoping
  exists to remove. It **reads the change itself and reports what it saw** — a claimed fix is a
  claim, not evidence — and states for each finding whether the code now does it, citing
  `file:line`. **It returns a finding class per finding on the same terms as round 1** (step 8): the
  checker emits it, you may only raise it, and an unclassified finding is BLOCKING. **Where this round
  is running after the sweep already went, the class no longer changes the outcome** — step 8's
  *"Once" is literal* rule escalates either class — but it is still emitted, because the `- Editorial:`
  record and the merge gate's count read it. **One lighter
  checker**, not a re-run of the full finder fan-out. **Anything the
  fixes broke is in scope**: a defect the fix commits introduced is a finding even though no one
  listed it. "Lighter" bounds the fan-out, never the checker's licence to object. It carries the
  **Verdict-first invariant** (Gates) too: a verdict on every claimed fix first, depth after.

  **The declines are not optional, and they are the one input scoping would otherwise delete.** A
  finding round 1 raised and the orchestrator **declined** leaves nothing in the delta — no fix, no
  diff, nothing for a scoped checker to see — so without the declines list a decline would pass
  unexamined by any fresh instance, which the unscoped recipe never allowed. Hand over each declined
  finding **with the one-line rationale given for it** (step 8), and say plainly that the checker may
  **contest a decline**: that is a finding like any other, and it counts against this round.

  **Scoping bounds what must be re-certified, never what the checker may read — and that is an
  instruction to give it, not diligence to hope for.** Tell it to **read the definition of any
  symbol the delta references but does not itself contain.** A fix whose correctness turns on
  earlier-read code unchanged since `<reviewed>` is the other thing the delta genuinely does not
  show; step 8's fallback conditions need not catch it — such a fix need not touch a sensitive
  path, and nothing else in that list keys on it.

**The bound — one fresh re-check, then escalate; there is no ladder.** The fresh re-check **is**
round 2 of the 2-round cap each gate already carries, never a round on top of it. If round 2 comes
back dirty — **whether it is a finding round 1 raised or one only the fix introduced** — escalate to
the human; there is no round 3. **At code review, "dirty" means a BLOCKING finding**: an EDITORIAL one
raised before step 8's sweep joins it, re-arms nothing and escalates nothing. **A round that runs
after that sweep is the exception, and the rule runs the other way** — step 8's *"Once" is literal*
rule governs it, and every finding it returns escalates whatever its class. (Step 8 fixes the classes, the
floors that may raise one, and that ordering rule.) **The acceptance gate has no finding class
at all** — either of its two *result* classes is dirty, and neither may be swept.

**Reaching a cap is a handoff, never a terminal state.** The cap ends the *round* — not the run, not
the issue. **STOP and put the decision to the human**, and do not proceed on your own judgement: an
unanswered or non-committal reply is not a decision, so journal it and stop. The iteration then
continues on what they decide, and the decision is frequently **not** "run another round" —
narrowing the change, splitting it, or diagnosing why the fixes keep landing dirty are all live
answers, and the cap exists to force that question rather than to end anything. **You never open
round 3 on your own;** where a human directs further work it exists because they directed it.
Reaching the cap is also not a verdict: an escalated gate has still returned no pass, so the
Gate-outcome invariant governs what may be journalled. It does not mark the row `blocked` — that
status is for a row waiting on something outside this gate (an unmet in-run dependency, a
`blocked: too-large` split, a recurring `gate-error:`), and a dirty round 2 waits on a human answer
about *this* gate.

Cost: **one extra subagent per dirty class per iteration** — so two
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

**Verdict-first invariant (a verdict before depth).** Applies to every gate that spawns an agent to
produce a verdict. **That agent's prompt instructs it to produce a complete verdict covering every
criterion first, then deepen with whatever budget remains — never letting deepening prevent it from
returning a verdict.**

**Why this is a rule rather than advice about prompting.** Under the Gate-outcome invariant a pass
that returns no verdict is **not passed**. So an agent that spends its budget on depth and stops
before answering has bought nothing **as a verdict**: the gate is still owed one, so nothing that
pass produced can be journalled as a result (whatever it wrote is still *collected* — Tool surface —
but evidence is not a verdict), and the re-spawn pays full price a second time. A shallow verdict is
useful; **no verdict is worthless and costs the same.** The failure is also invisible from inside the
agent — depth feels like progress right up to the point the budget ends — which is why this belongs
in the prompt and not in your judgement about how deep to let it go.

**Two kinds of site carry it, and treating them alike defeats it.**
- **Text handed to the agent verbatim** — the AC-verifier's `Prompt:` block (Part 1) above all.
  That text reaches an agent which reads neither this section nor anything else in this file, so a
  bare reference to this invariant **by name is inert there**. Such sites carry **the sentence
  itself**, tagged with this invariant's name so the coupling stays visible to a later editor.
- **Orchestrator-facing recipes** — the lists telling *you* what a spawn prompt must carry. Those
  name the invariant; you resolve it when you compose the prompt.

**A gate bound to a skill invoked by name is out of reach, and that is recorded, not papered over.**
Where the binding is a skill or workflow this engine invokes by name rather than a prompt it
composes, there is no prompt surface to instruct, so this invariant cannot reach it. `SECURITY_REVIEW`
is the standing case, **but the property belongs to the binding and not to that parameter**:
`CODE_REVIEW` names a *procedure you run* and is normally the finder fan-out this engine composes —
yet the engine itself contemplates it being bound to a skill instead (step 8), and `VERIFY` is
invoked by name too. **Test the binding you actually have, not the parameter's name.** Where a gate
turns out to be out of reach, that is a property of the binding, and it is never a reason to journal
the gate as covered by this invariant — say so, as step 8 says so for its own fallback.

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
