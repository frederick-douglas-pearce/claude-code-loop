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
       RESUMED` sentinel (now last-wins) and continue to step 0.2; any rows left parked simply
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

### Escalation rubric (when unsure)
Scope/priority/requirements — including any plan whose value story lacks a credible user or a
checkable falsifier (step 3) — → `SCOPE_AGENT`, before implementing. Design/implementation →
`DESIGN_AGENT`. Escalate to the HUMAN when those disagree/punt, ACs are unresolvable, an
action is destructive/irreversible, a review finding is contested, or the same step failed twice —
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
  retrospective, and advisory on a manual re-invoke — so step 8's scale-with-risk-surface rule is
  the only bound that acts on the fan-out you are about to launch.
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
| Code review | `CODE_REVIEW` (parallel finders you run — step 8); **the fix's re-check a fresh checker, not you** (Fresh-re-check invariant) | every issue; one light pass on `docs` | findings → fixes |
| Security | `SECURITY_REVIEW` (local or label) | by route (step 9) | clean/findings |
| AC-verify | fresh subagent (+`VERIFY`); **any re-check a fresh instance too** (Fresh-re-check invariant) | every issue with acceptance criteria (step 10 is unconditional; the **mutation pass within it** is scoped — Routing table). **Last gate before merge**, so it certifies the merge candidate and owns the commit boundary for its own fixes | done/not-done + gaps, as **two separate counts**: Class A (AC-satisfaction) and Class B (mutation survivors); **either class blocks** |
| Merge | user (calibration / non-graduated route) → orchestrator (auto: graduated routes) | CI + security + acceptance green | `MERGE_METHOD` |

**Gate-outcome invariant (evidence-bound pass).** Applies to every gate in the table above that
returns a verdict, **on the rows that gate is due on** — due-ness is decided where it always was (the
gate's own step and the Routing table) and this invariant does not touch it. A gate the route or its
trigger condition never made due was never owed a verdict, so journal it as not run (`skipped` /
`n/a`) with the reason; not-due is not a pass either. An explicit `—` **plus a reason** in the config
is a deliberate "not applicable", journalled `n/a: <that reason>` — **not** an absent binding; it is
the only way a config marks a gate not-due, and it is deliberately visible.

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
  **The spawn prompt must carry three things the checker would otherwise never see**, since it reads
  neither Part 2 nor this section:
  1. the **blockquote** under Part 2 — the `write_bytes`-versus-`mkstemp` passage, not the one-line
     slogan alone — **pasted verbatim**: that is the yardstick, and its worked example is what makes
     the distinction operable;
  2. that it **must not edit, break, or execute code to decide**, since the prohibition on
     improvising a mutation does not otherwise reach it, and a checker that breaks the code to see
     what fails has done the one thing this gate forbids;
  3. that it **must say plainly when it cannot tell** — the rule making that a dirty result lives
     here, where the checker cannot see it, so an unprompted checker hedges and the gate reads
     clean.
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
- **Code review (step 8) — the change as it now stands, plus the list of what you claimed to fix.**
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
the human; there is no round 3.

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

---

## Phase units — what to load, when, and what holds if you do not

The steps above are the whole pipeline. The **procedures** for steps 3–12 live in sibling files you
read **at the step that needs them**, not up front. This section is the index, and it is the part
that must never be deferred: it states what each unit owes so that a unit which fails to load
**over-escalates** rather than silently doing nothing.

**Load protocol — identical for every unit.** Read it with `Read`, page by `offset` until you reach
the last line the file reports, and treat a read you cannot confirm complete as **not loaded**. A
procedure you could not load never means "skip the step": it means stop and escalate, exactly as an
unbound gate binding does (Gate-outcome invariant). Confirm the load *before* acting on it.

| unit | file | read it at | what it owns |
|---|---|---|---|
| `planning` | `phases/planning.md` | step 3 | plan authoring, architect gate, human plan gate |
| `implementing` | `phases/implementing.md` | step 6 | implementation, build commands, commit + PR |
| `reviewing` | `phases/reviewing.md` | step 8 | code review procedure, security routing |
| `accepting` | `phases/accepting.md` | step 10 | AC-verifier, Class A and Class B |
| `landing` | `phases/landing.md` | step 11 | merge mechanics, journal + stop |
| `reference` | `reference/*.md` | as named below | ledger formats, router, initialization, resume |

**What holds without each unit loaded.** These are the fail-safe halves. They are stated here, in
full, so that the gate table above is enforceable on its own:

- **`planning`** — the plan gate stops on **every** issue unless `queue.md`'s header says
  `plan-gate: conditional`, and **absent or unrecognized reads as `always`**. A material architect
  rewrite stops for the human under **every** mode and every posture. You cannot apply narrowing
  conditions you have not read: without this unit, the gate is `always`.
- **`implementing`** — `LINT_CMD`, `TYPE_CMD` and `TEST_CMD` each block on a non-zero exit, and
  each command's exit status is its own verdict. `HERMETIC_TEST_CMD` is additionally due on a
  `code`-route change that adds or modifies a test, and an absent or `TODO` binding there is
  **unknown, and unknown is due**. Never blanket-stage (Tool surface, above — that section is core
  and always applies).
- **`reviewing`** — code review is due on **every** issue; security review is due by route. Neither
  may be journalled passed without its own verdict. A binding you cannot invoke is not permission
  to skip: fall back or escalate.
- **`accepting`** — the acceptance gate is due on **every** issue carrying acceptance criteria, it
  is the **last** gate before merge, it certifies the merge candidate, and it owns the commit
  boundary for its own fixes. **Two counts, and either blocks**: Class A (unmet criteria) and
  Class B (surviving mutants). Without this unit you cannot run it — so you cannot merge.
- **`landing`** — default-deny at the merge gate: uncertainty about auto-merge eligibility means
  the human decides. Never merge red CI, never force-push, never admin-merge. The iteration is not
  finished until it has journalled.
- **`reference`** — the ledger is the state, not your context. `progress.md` is append-only and the
  most recent sentinel wins. Read `reference/ledger-format.md` before writing any ledger row or
  journal entry; `reference/resume.md` when step 0 finds a mid-pipeline row;
  `reference/initialization.md` on a new run; `reference/router.md` when step 2 must classify.

**One rule covering all six.** A phase unit is a *procedure*, never a *permission*. Nothing in a
deferred file can loosen a limit stated in this core — not the Tool surface policy, not the
Gate-outcome invariant, not the merge posture. Where a unit appears to, this file wins and the
conflict is a defect to surface.
