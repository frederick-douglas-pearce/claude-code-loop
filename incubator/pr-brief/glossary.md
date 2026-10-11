# Glossary — dev-loop and development terms in PR briefs

What the dev loop's terms, and the general development terms a brief uses, mean for readers who
are not engineers, and for the agent writing to them. Maintained by the `ba` agent; the owner
settles anything marked `proposed`.

**Which glossary wins.** A briefed repo's own glossary (the file its `CLAUDE.md` names, otherwise
`docs/glossary.md`) wins for **every term it defines**, including one this file also defines: that
repo's owner settled it for that repo's readers. This file covers **dev-loop terms** and the
**general development terms** below. Technology terms (hosting, caches, libraries, services) are in
neither unless the repo's glossary has them: explain those in the brief's Technology table.

**How the drafter uses this file.** Each **Plain** line is written to be quoted into a brief as it
stands, including the executive summary. **Precise** is for a technical lead and for checking that
a term really applies. **Not** names the distinction the reader needs; keep it in the brief when
the PR is on the wrong side of it (a review closed with findings open is not a clean pass). This
file records meaning. The brief's own section and row names live in `SKILL.md` → *Write the
brief*; **Shown as** points there.

**Which engine.** Definitions follow the engine this file ships with. A journal written by an
older engine may use a term differently (an engine before v0.3.0 has no blocking/editorial split,
for example). When a journal and this file disagree, report what the journal says, and do not
apply a definition the journal's engine did not have.

**Audiences.** Executives and product managers reading PR briefs (and later, one-page epic
briefs); they oversee several projects and come to each PR cold. Technical leads who use a brief
to talk with them. The `pr-brief` drafter and verifier, who quote and check the Plain lines.
Plain definitions are written for the executive; Precise definitions must hold up to someone who
knows the engine.

**Sources.** Engine paths are relative to the plugin root (`plugins/dev-loop/` in the source
repo): `skills/dev-loop/loop-engine.md` (core), `skills/dev-loop/phases/reviewing.md`,
`skills/dev-loop/phases/accepting.md`, `skills/dev-loop/reference/initialization.md`. `README.md`
is the plugin's front-door README.

---

## Terms

### Acceptance check
- **Plain:** A final check, by an AI agent that did not build the change, that every acceptance criterion in the issue is met by the code about to merge.
- **Precise:** The engine's acceptance gate (step 10, "Verify done", also `AC-verify`). A fresh subagent receives only the issue's acceptance criteria verbatim and runs its own read commands, so it reports what it saw, not what the builder claimed. It returns two result classes, never summed: unmet criteria (Class A, counted in `ac-findings`) and, for `code`-route changes that alter behavior, tests that would not notice a break (Class B, from the mutation pass). Either class blocks the merge. It runs last, after code review and security, so it certifies the merge candidate. At most two rounds (round cap); a fix it makes that changes source has been reviewed by nobody, so the loop escalates to a person before merge.
- **Shown as:** `SKILL.md` → Cost, *Review effort* ("the acceptance check ran twice"). Journal: `- AC-verify:` line; `ac-verify=` inside `gate-rounds=`.
- **Source:** `loop-engine.md` → "10. Verify done (independent, fresh context)"; `phases/accepting.md` → "Step 10 — the procedure" and "AC-verifier"; `README.md` → "What the loop can do to your repo" ("The acceptance gate asks whether your tests would notice a regression").
- **Not:** Not CI, and not code review: it asks whether the work does what the issue asked, not whether the code is well written. README calls it the "acceptance gate"; briefs say "acceptance check", the wording `SKILL.md` already uses.
- **Status:** settled

### Acceptance criteria
- **Plain:** The checklist in the issue that says what "done" means for this work.
- **Precise:** The criteria written in the issue. The loop copies them verbatim into the plan, every code reviewer receives them, and the acceptance check tests each one. Criteria are often numbered AC1, AC2 and so on; a correction posted as an issue comment does not change the criteria text.
- **Shown as:** `SKILL.md` → Acceptance walkthrough ("checks <criterion or user story>") and Spec vs. delivery.
- **Source:** `loop-engine.md` → "3. Plan" (copied verbatim) and "Ledger format" → `issue-<N>.plan.md` ("Acceptance criteria (verbatim from issue)"); `phases/accepting.md` → "AC-verifier", Part 1.
- **Not:** Not tests. Never show a bare "AC2" in a brief: name what the criterion asks ("the second criterion, migrating the adapter").
- **Status:** settled

### ac-findings
- **Plain:** How many of the issue's acceptance criteria the acceptance check found unmet, counted across all its rounds.
- **Precise:** `ac-findings=<n>` on the journal's `- Budget:` line: Class A results, counted cumulatively across every round of the acceptance gate, not the final round's residue (which is 0 on every iteration that merged). An absent slot means unknown, never zero; only `ac-findings=0` says none.
- **Shown as:** not shown as a slot; summarized in `SKILL.md` → Cost, *Review effort*.
- **Source:** `loop-engine.md` → "12. Journal + stop" and "Ledger format" → `progress.md` → the Budget line field list (`ac-findings` / `post-gate-survivors`).
- **Not:** Not a count of every problem the check raised: it counts unmet criteria only. Not `post-gate-survivors` (what the check missed) and not `mutation-survivors` (tests that would not notice a break).
- **Status:** settled

### Auto-merge
- **Plain:** The loop merged the change itself, without asking a person, because the project has opted in for that kind of work and nothing risky was involved.
- **Precise:** Possible only under `mode: escalation-only`, for a route the person has graduated, with no release bump beyond a patch, no hold, and none of the always-escalate conditions: a feature or breaking change, a risky or irreversible change, a touched security surface, a contested or unresolved blocking review finding, an unresolved mutation survivor, or an unresolved offline-test finding. If any of that is uncertain, a person approves the merge.
- **Shown as:** not shown; when it happened, `SKILL.md` → Cost, *Human involvement* has no merge approval to count.
- **Source:** `loop-engine.md` → "11. Merge"; "Ledger format" → `queue.md` (the `escalation-only` mode); `README.md` → "What the loop can do to your repo" ("The default is human-gated").
- **Not:** Not the default: under `mode: calibration` a person approves every merge. Never write "the owner approved the merge" for an auto-merged PR.
- **Status:** settled

### Backlog ruling
- **Plain:** A person's decision about which issues the loop works on, in what order, or whether an issue is split or set aside.
- **Precise:** The loop works a curated list fixed when the run starts. An issue that joins or leaves the backlog afterward is put to the person once and never added or removed automatically ("curation"). An issue too large for one iteration is marked `blocked: too-large` and sent to the scope reviewer to split. Scope and priority questions go to the scope reviewer (`SCOPE_AGENT`, an AI agent) before a person; the person's answer is the ruling.
- **Shown as:** `SKILL.md` → Cost, *Human involvement* ("scope or backlog rulings").
- **Source:** `loop-engine.md` → "1. Select" (Roster reconciliation; Size guard), "Ledger format" → `queue.md` (Curated-subset invariant), and "Escalation rubric (when unsure)".
- **Not:** Not a plan approval or a merge approval; count it as a separate human decision only when the journal attributes it to the person.
- **Status:** settled

### Blocked
- **Plain:** Waiting on something outside this issue: another issue finishing, a split into smaller issues, or a repair to the loop's setup.
- **Precise:** A ledger status. Three causes: an unmet dependency on another issue in the run (returns to the queue when that issue is done); `blocked: too-large`, awaiting a split; or a repeated gate error, awaiting a person's repair of the project's loop configuration. The last two wait on a person. It counts as finished for the run's bookkeeping, and the issue stays open.
- **Shown as:** not shown as a status; describe the cause.
- **Source:** `loop-engine.md` → "Ledger format" → `queue.md` (Terminal statuses); "Gates, convergence & resting states" (Gate-outcome invariant).
- **Not:** Not `hold` (a person paused a merge) and not `parked` (waiting on an outside event such as a release).
- **Status:** settled

### Blocking finding
- **Plain:** A review finding that had to be fixed and checked again before the change could merge.
- **Precise:** One of code review's two finding classes (`BLOCKING`): correctness, security, a test that cannot fail, acceptance-criteria coverage, anything that moves a safety boundary, and any finding that something is false, stale or misdescribed, wherever it sits. The reviewer assigns the class; the loop may raise a finding to blocking, never lower it, and an unclassified or ambiguous finding is blocking. A blocking finding still open after the second round, or one raising a design question, stops for a person.
- **Shown as:** `SKILL.md` → Cost, *Review effort*; write it in lowercase ("12 blocking findings").
- **Source:** `loop-engine.md` → "8. Code review" (Finding classes); `phases/reviewing.md` → "Step 8 — the procedure" (Floor 1 — content); `README.md` → "What the loop can do to your repo" ("Some review findings are applied without a second review").
- **Not:** Not the acceptance check's Class A or Class B, which carry no finding class. Engines before v0.3.0 have no blocking/editorial split: there, every finding was handled as blocking.
- **Status:** settled

### Budget line
- **Plain:** The journal's one-line cost record for an issue: how many AI helpers ran, how many review rounds each check took and why, and the elapsed time.
- **Precise:** `- Budget:`, written in the close record at step 12 as one line of `name=value` slots separated by `·`. Required: `subagent-runs`, `gate-rounds`, `wall-clock`, `tokens`. Optional: `justification`, `ac-findings`, `mutation-survivors`, `post-gate-survivors`, and notes in parentheses after any value. An absent optional slot means unknown, never zero. An iteration that stops before step 12 has no Budget line.
- **Shown as:** `SKILL.md` → Cost (*Elapsed time*, *Review effort*, *Compute (tokens)*).
- **Source:** `loop-engine.md` → "12. Journal + stop" and "Ledger format" → `progress.md` → the Budget line field list.
- **Not:** Not a measure of money or compute: tokens are not yet recorded (`tokens=deferred`).
- **Status:** settled

### CI (checks)
- **Plain:** Automated tests the code host runs on every change; "passing" means they all succeeded.
- **Precise:** Continuous integration: the project's own check workflows, run by the code host on each push and pull request. The loop waits for them after opening the PR and fixes failures until they pass; a merge needs them passing on the exact commit being merged, and the loop never merges with them failing.
- **Shown as:** not shown as a row; in prose, say "automated checks passed" rather than "CI green".
- **Source:** `loop-engine.md` → "7. Commit + PR" ("wait for CI; fix until green") and "11. Merge"; `README.md` → "What the loop can do to your repo" (Hard limits: "Never bypass failing CI").
- **Not:** Not code review and not the acceptance check: passing checks say the tests ran clean, not that anyone read the change or that it does what the issue asked.
- **Status:** settled

### Code review
- **Plain:** AI reviewers read the change and report problems, which are fixed and re-checked; it is not a person's approval on GitHub.
- **Precise:** Step 8. Several reviewer subagents ("finders") read the whole change in parallel, each from a different angle (lens) and each given the issue's acceptance criteria, and a further pass confirms each finding. Each finding is classed blocking or editorial. Blocking fixes are committed and re-checked by a fresh checker in round 2; anything still blocking after that, and any blocking finding that raises a design question, stops for a person. A `docs` change gets one light pass.
- **Shown as:** `SKILL.md` → Cost, *Review effort* ("passed code review on the third round"). Journal: `- Code-review:` line; `code-review=` inside `gate-rounds=`.
- **Source:** `loop-engine.md` → "8. Code review"; `phases/reviewing.md` → "Step 8 — the procedure"; `README.md` → "What the loop can do to your repo".
- **Not:** Not a GitHub approval review by a person; a PR can pass code review with no human review recorded on GitHub. Not the acceptance check.
- **Status:** settled

### Commit
- **Plain:** One saved set of changes to the code, with a short message saying what changed.
- **Precise:** A git commit. A pull request usually holds several; a squash merge combines them into one new commit on the main branch. The loop commits before every review round so the reviewer reads what will merge.
- **Shown as:** not shown; say "the PR's final state" rather than a commit ID where possible.
- **Source:** `loop-engine.md` → "7. Commit + PR"; "Gates, convergence & resting states" (Currency).
- **Not:** Not a merge: a commit on a branch has not joined the main line of code.
- **Status:** settled

### Deferred
- **Plain:** Not worked on in this run: the issue was not ready to build, or a person took it out of the run; it stays open for later.
- **Precise:** A ledger status that counts as finished for the run. Reached three ways: the issue says it is not ready to implement (route `stub-defer`); a person ejected it at curation; or it is an epic's tracking issue, which the loop never works. The loop does not close the issue.
- **Shown as:** not shown as a status; say which of the three happened.
- **Source:** `loop-engine.md` → "Ledger format" → `queue.md` (Terminal statuses), "1. Select" (Roster reconciliation), "Routing table" (`stub-defer`); `reference/initialization.md` → "Initialization procedure (new run)", step 3.
- **Not:** Not "postponed" in the backlog sense (an issue's priority lowered, or moved to a later milestone): briefs use "deferred" for that too, which is a second meaning (see Open decisions). Not `tokens=deferred`, which means "not yet measured".
- **Status:** proposed (whether briefs reserve "deferred" for this ledger meaning and say "postponed" for the backlog meaning)

### Deploy
- **Plain:** Putting a version live on a running service, such as a website; a merged change is live only after a successful deploy that ran after it merged.
- **Precise:** For a project that serves something (a site, an API), deploying is a separate step from merging and from releasing, often a workflow run. One deploy can make several earlier merged changes live at once.
- **Shown as:** `SKILL.md` → Executive summary, *Status* (for example "merged, not yet deployed").
- **Source:** `SKILL.md` (pr-brief) → "Gather evidence", step 5 ("Since merge"). The dev-loop engine does not define it.
- **Not:** Not a merge and not a release. A project that ships a package or plugin is released, not deployed.
- **Status:** settled

### Design review
- **Plain:** A review of the planned approach by the loop's design reviewer, an AI agent, before any code is written.
- **Precise:** The architect gate (step 4): the project's `DESIGN_AGENT` (an agent a journal may call "architect") reviews the plan when the project's architect triggers fire or the loop is unsure; skipped for `docs` and trivial `research` work. The plan's approach is frozen first, and if the review materially changes it, a person sees the change before work continues, whatever the run's settings. Rounds count in `gate-rounds=architect=`.
- **Shown as:** `SKILL.md` → Cost, *Review effort* ("design review once; it overturned the plan's central design").
- **Source:** `loop-engine.md` → "4. Architect gate (conditional)" and "5. Human gate" (the always-on condition); `README.md` → "What the loop can do to your repo" ("When its design reviewer rewrites the plan, you see the plan").
- **Not:** Not a person ("the architect" is an AI agent). Not the scope ruling, which is the same agent consulted later on a code-review finding and is not counted as a design-review round.
- **Status:** settled

### Editorial finding
- **Plain:** A wording-only review finding the loop applied once without a second review; the merge approval states how many.
- **Precise:** Code review's second finding class (`EDITORIAL`): the reviewer must establish that it asserts nothing about the code or docs being true or false and changes no behavior. Editorial findings are applied in one sweep at the close of code review, only to paths the project declares documentation or research, never to source, tests or security-sensitive paths, and only as the reviewer specified. The sweep's edits still pass through the acceptance check and CI. The count is recorded on the journal's `- Editorial:` line and must be stated at the merge gate, including zero. A finding raised after the sweep has run is handled like any other and stops for a person.
- **Shown as:** `SKILL.md` → Cost, *Review effort*; write it in lowercase.
- **Source:** `loop-engine.md` → "8. Code review" (Finding classes) and "11. Merge" (what the stop must state); `phases/reviewing.md` → "Step 8 — the procedure" (the sweep; "Once" is literal); `README.md` → "What the loop can do to your repo".
- **Not:** Not "minor" or "optional": an editorial finding was applied, just not re-reviewed. Not available in engines before v0.3.0.
- **Status:** settled

### Epic
- **Plain:** A group of related issues that together deliver a larger goal.
- **Precise:** Usually a tracking issue or a label that links several work issues. The loop can take an epic's label as its backlog, but it never works or closes the tracking issue itself.
- **Shown as:** `SKILL.md` → Value delivered, *Moves forward* ("the larger goal, epic, or milestone").
- **Source:** `reference/initialization.md` → "Initialization procedure (new run)", steps 2–3.
- **Not:** Not a milestone, which groups issues by release or time rather than by goal.
- **Status:** settled

### Escalation
- **Plain:** The loop stopped and asked a person to decide before going on.
- **Precise:** Escalating "to the human" happens when the AI reviewers disagree or cannot decide, criteria cannot be resolved, an action is destructive or irreversible, a review finding is contested or still blocking after its rounds, a gate errored, the same step failed twice, the design review materially changed the plan, or a blocking finding raised a design question. Reaching a round cap is an escalation, not a verdict. Each escalation is one human decision; how long the person took is not recorded.
- **Shown as:** `SKILL.md` → Cost, *Human involvement* ("escalations").
- **Source:** `loop-engine.md` → "Escalation rubric (when unsure)"; "Gates, convergence & resting states" ("Reaching a cap is a handoff, never a terminal state").
- **Not:** The engine also says "escalate to `SCOPE_AGENT`" for handing a question to an AI agent. In a brief, "escalation" means a person was asked; call the other "consulted the scope reviewer".
- **Status:** settled

### Finding
- **Plain:** A problem a reviewer reported; each one is fixed, declined with a stated reason, or put to a person.
- **Precise:** An item returned by a review gate. Code-review findings carry a class (blocking or editorial); the acceptance check's results are Class A (unmet criterion) or Class B (mutation survivor) and carry none. A declined finding is recorded with its reason in the journal.
- **Shown as:** `SKILL.md` → Cost, *Review effort* (counts, and how review ended).
- **Source:** `loop-engine.md` → "8. Code review"; `phases/accepting.md` → "Step 10 — the procedure" (result classes vs finding classes).
- **Not:** Not necessarily a defect in what users see: many findings are about tests, wording or edge cases. Never show a finding number (such as "F57") without saying what it is.
- **Status:** settled

### Fresh re-check
- **Plain:** A newly started checker, not the one that wrote the fix, confirmed whether the fix worked.
- **Precise:** The Fresh-re-check invariant: after code review or the acceptance check comes back with findings, the fixes are re-checked by a new subagent, never by the thread that wrote them and never by the round-1 reviewer contacted again. The re-check is round 2 of that gate's two-round cap; if it comes back dirty, the loop stops for a person.
- **Shown as:** `SKILL.md` → Cost, *Review effort*.
- **Source:** `loop-engine.md` → "Gates, convergence & resting states" (Fresh-re-check invariant); `README.md` → "What the loop can do to your repo" ("A fix is never checked by whoever wrote it").
- **Not:** Not a second full review: later rounds read only what changed since the last reviewed commit, unless the loop cannot trust that anchor.
- **Status:** settled

### Gate
- **Plain:** A checkpoint the work has to clear before it moves on, such as plan approval, a review, or the merge approval.
- **Precise:** The engine's gates: plan, design review (architect), build commands, code review, scope ruling, security review, acceptance check, merge. A gate may be recorded as passed only with its own verdict as evidence; a gate that did not run, errored, or was skipped as not due is never a pass.
- **Shown as:** not shown as a word; name the specific check.
- **Source:** `loop-engine.md` → "Gates, convergence & resting states" (Gate table; Gate-outcome invariant); `README.md` → "What the loop can do to your repo" ("A gate that did not run is never reported as one that passed").
- **Not:** "Skipped" (not due for this kind of work) is not "passed".
- **Status:** settled

### Gate currency
- **Plain:** A check's pass covers only the code it read; any change after it is unchecked until checked again.
- **Precise:** The Currency clause: a verdict is bound to the commit it ran on. A later fix (at the acceptance check, for CI, or asked for at the merge gate) or updating the branch from main re-arms the checks that read it; the loop re-runs them or stops for a person, and never merges on the older verdict. When a person decides to merge anyway, the journal records a human decision, not a pass.
- **Shown as:** `SKILL.md` → Cost, *Review effort*, and the "never gets cut" rule ("anything merged without review or past an unresolved finding").
- **Source:** `loop-engine.md` → "Gates, convergence & resting states" (Currency — a verdict is bound to the commit it ran on); `README.md` → "What the loop can do to your repo" ("A gate's pass covers the exact commit it ran on — and expires when that changes").
- **Not:** "The owner approved merging the last fixes without another review" is not "the review passed": say the final commit was read by no review.
- **Status:** settled

### gate-rounds
- **Plain:** How many rounds each review step took on this issue: design review, code review, and the acceptance check.
- **Precise:** `gate-rounds=architect=<a>,code-review=<c>,ac-verify=<v>` on the Budget line. A value above 1 means that gate had to run again; it is the only slot that signals repeated review. The code-review count may carry the lenses in parentheses (`code-review=2(correctness,robustness)`). The scope ruling is never counted here.
- **Shown as:** `SKILL.md` → Cost, *Review effort* ("passed code review on the third round").
- **Source:** `loop-engine.md` → "12. Journal + stop" and "Ledger format" → `progress.md` → the Budget line field list.
- **Not:** Not the number of AI agents (`subagent-runs`): one round can use several agents.
- **Status:** settled

### Hold
- **Plain:** A person paused the merge; the pull request waits until they release it.
- **Precise:** Ledger status `hold`, set when a person holds the merge at the merge gate; it survives a restart, blocks auto-merge, and is cleared only by the person. While any row is held, the run is not complete.
- **Shown as:** `SKILL.md` → Cost, *Human involvement* ("holds").
- **Source:** `loop-engine.md` → "11. Merge"; "Ledger format" → `queue.md` (non-terminal, resting statuses).
- **Not:** Not `parked` (waiting on an outside event) and not `blocked` (waiting on another issue or a repair).
- **Status:** settled

### Human gate (journal line)
- **Plain:** The journal's record of how the plan was approved: by a person, or automatically by the loop.
- **Precise:** The `- Human gate:` line records the plan gate only. Under `plan-gate: always` it records approval by the person. Under `plan-gate: conditional` it may read `plan auto-approved (<why>)`, which is not a human decision. Merge approvals, holds, escalations and backlog rulings are recorded elsewhere in the journal.
- **Shown as:** `SKILL.md` → Cost, *Human involvement* (counted from "`- Human gate:` lines" and other journal entries).
- **Source:** `loop-engine.md` → "Ledger format" → `progress.md` (the `- Human gate:` line); "5. Human gate".
- **Not:** Not a count of all human decisions, and an auto-approval is not one.
- **Status:** settled

### Issue
- **Plain:** A tracked request for work, such as a bug, a feature or a question; its text is the spec the work is checked against.
- **Precise:** An item in the project's issue tracker. Its problem statement says why the work matters; its acceptance criteria say what was intended; its comments may correct either. The loop works one issue per iteration, and the issue usually closes automatically when its pull request merges.
- **Shown as:** `SKILL.md` → Gather evidence, step 2.
- **Source:** `loop-engine.md` → "The pipeline (ONE issue per invocation)" and "3. Plan".
- **Not:** A closed issue is not a solved problem: an issue closes when its PR merges even if part of its scope was split to another issue.
- **Status:** settled

### Iteration
- **Plain:** The loop's work on one issue, from picking it up to merging it.
- **Precise:** In this engine one iteration is one issue. It can span several sessions, because the loop stops at each human gate and resumes from its ledger.
- **Shown as:** not shown; say "the work on this issue".
- **Source:** `loop-engine.md` → "Ledger format" → `queue.md` (budget caps: "in this engine one 'iteration' = one issue").
- **Not:** Not a review round, and not a run.
- **Status:** settled

### Journal
- **Plain:** The loop's running log of what happened on each issue and what each person decided, written by the loop itself.
- **Precise:** `progress.md` in the ledger: append-only, one block per gate decision, plus an open record when the PR opens and a close record (with the Budget line) at the end. It is the loop's own account: machinery checks the ledger's state against git, but nothing checks whether its sentences are true.
- **Shown as:** `SKILL.md` → Gather evidence, step 3, and the Sources line.
- **Source:** `loop-engine.md` → "Ledger format" → `progress.md`; `README.md` → "What the loop can do to your repo" ("The loop is held to what it asserts").
- **Not:** Not an independent record: cite it as "the loop's journal records…", not as fact.
- **Status:** settled

### justification
- **Plain:** The loop's own short reason why an issue needed more than one round of some review.
- **Precise:** `justification=<short reason>` on the Budget line; expected whenever any `gate-rounds` value exceeds 1, allowed on any line. It lets a reader tell justified high-stakes work from repeated rework.
- **Shown as:** `SKILL.md` → Cost, *Review effort* ("The `gate-rounds=` and `justification=` slots say how many and why").
- **Source:** `loop-engine.md` → "12. Journal + stop" ("Say why, not just how much") and "Ledger format" → `progress.md` → the Budget line field list.
- **Not:** Not a person's approval of the cost: it is the loop's self-report.
- **Status:** settled

### Ledger
- **Plain:** The loop's working records for a run: its work list, its journal, and a plan for each issue, kept on the machine and not published with the code.
- **Precise:** `LEDGER_ROOT/<run>/` holding `queue.md` (the work list and each issue's status), `progress.md` (the journal) and `issue-<N>.plan.md` (one plan per issue). Gitignored, never committed. Live git and pull-request state win over it when they disagree.
- **Shown as:** `SKILL.md` → Gather evidence, step 3, and the Sources line ("ledger files").
- **Source:** `loop-engine.md` → "Ledger format" and "7. Commit + PR" (live git/PR state wins on conflict); `README.md` → "What the loop can do to your repo" ("The ledger is local and never committed").
- **Not:** Not in the repository's history, so a reader without the machine cannot see it.
- **Status:** settled

### Lens
- **Plain:** The angle a code reviewer reads the change from, such as correctness or security.
- **Precise:** Each finder in a code-review round gets a distinct lens, chosen from what the change puts at risk. On any change to a path not declared documentation or research, round 1 must include the `guard-efficacy` lens, which asks whether the change's tests would catch the failure they are meant to. The lenses that ran appear in parentheses on `code-review=` in the Budget line.
- **Shown as:** not shown; say "review angle" if needed.
- **Source:** `loop-engine.md` → "8. Code review" (`guard-efficacy` floor); `phases/reviewing.md` → "Step 8 — the procedure" ("Pick finder angles from the diff's risk surface"); `README.md` → "What the loop can do to your repo" ("Code review asks whether your new guards would actually catch anything").
- **Not:** Not a separate review: several lenses make one round.
- **Status:** settled

### Main branch
- **Plain:** The project's main line of code, which approved changes join when they merge.
- **Precise:** The base branch pull requests merge into (usually `main`). Code on main is not necessarily released or live.
- **Shown as:** not shown; say "the main line of code".
- **Source:** `loop-engine.md` → "11. Merge"; `phases/accepting.md` → "AC-verifier", Part 1 (`main` as the assumed base branch).
- **Not:** Not what users have: that needs a release or a deploy.
- **Status:** settled

### Merge
- **Plain:** The change joined the project's main line of code; merged is not the same as released or live.
- **Precise:** Folding a pull request into the main branch, using the project's merge method. The loop deletes the PR's branch after merging and confirms the issue closed.
- **Shown as:** `SKILL.md` → Executive summary, *Status* ("merged, not yet released").
- **Source:** `loop-engine.md` → "11. Merge".
- **Not:** Not a release and not a deploy.
- **Status:** settled

### Merge gate
- **Plain:** The final approval to merge; by default a person gives it for every pull request.
- **Precise:** Step 11. Under `mode: calibration` (the default) a person approves every merge; under `escalation-only` some routes may auto-merge. The merge needs CI, security and the acceptance check passing on the exact commit being merged. When the loop stops here it must state how many editorial findings were applied without re-review. A person may hold the merge.
- **Shown as:** `SKILL.md` → Cost, *Human involvement* ("merge approval").
- **Source:** `loop-engine.md` → "11. Merge"; `README.md` → "What the loop can do to your repo" ("The default is human-gated").
- **Not:** A person's merge approval is a decision, not a review: it does not certify code no check has read (see Gate currency).
- **Status:** settled

### Milestone
- **Plain:** A named group of issues, usually the work planned for one release.
- **Precise:** A milestone in the issue tracker. A loop run often takes one milestone as its backlog and is named after it.
- **Shown as:** `SKILL.md` → Value delivered, *Moves forward*.
- **Source:** `reference/initialization.md` → "Initialization procedure (new run)", step 1 (run named after the milestone).
- **Not:** Not an epic, which groups issues by goal.
- **Status:** settled

### Mode
- **Plain:** The run's setting for merges: either a person approves every merge, or some kinds of work may merge without asking.
- **Precise:** The `mode:` field in the work list's header. `calibration` (default): a person approves every merge. `escalation-only`: routes the person has graduated may auto-merge. Mode governs the merge gate only. Plan approval has its own setting, `plan-gate:`, and changing one never changes the other.
- **Shown as:** not shown; describe what it meant for this PR.
- **Source:** `loop-engine.md` → "Ledger format" → `queue.md` (the `mode:` field); `README.md` → "What the loop can do to your repo".
- **Not:** Not the plan-approval setting.
- **Status:** settled

### Mutation pass
- **Plain:** The acceptance check deliberately breaks the code, in a throwaway copy, to see whether the tests notice.
- **Precise:** Part 2 of the acceptance gate. Due only for `code`-route changes that alter behavior; if such a change adds or modifies tests, a harness applies small breaking edits in an isolated copy and runs the test suite; if it adds no test, that absence is itself the finding. Mutating the person's real working copy happens only with their explicit approval. A pass that applies no mutation is an error, not a clean result.
- **Shown as:** `SKILL.md` → Cost, *Review effort*.
- **Source:** `phases/accepting.md` → "AC-verifier", Part 2 — Class B: mutation survivors; `loop-engine.md` → "Routing table"; `README.md` → "What the loop can do to your repo" ("To check the rest, the loop breaks your code on purpose — in a copy").
- **Not:** Not the `guard-efficacy` lens in code review, which reads the tests and never breaks anything.
- **Status:** settled

### Mutation survivor
- **Plain:** A test that kept passing when the code it protects was deliberately broken, so it would not catch that failure.
- **Precise:** A Class B result of the acceptance check, recorded as `mutation-survivors=<n>`. It also covers a behavior change with no test added (`mutation-survivors=1 (no guard added)`). It blocks the merge like an unmet criterion. Three readings stay distinct: a number (`0` means checked and clean), `n/a: <reason>` (not due: docs route or no behavior change), and an absent slot (unknown).
- **Shown as:** `SKILL.md` → Cost, *Review effort*.
- **Source:** `loop-engine.md` → "Ledger format" → `progress.md` → the Budget line field list (`mutation-survivors`); `phases/accepting.md` → "Step 10 — the procedure".
- **Not:** Not `post-gate-survivors`, which counts defects the check missed. Not zero when the slot is absent.
- **Status:** settled

### Parked
- **Plain:** Set aside until an outside event happens, such as a release; only a person can bring it back.
- **Precise:** Ledger status `parked`, with the awaited event in the row's notes (`awaiting: <condition>`). It keeps its route, does not stop other work, and returns to the queue only when the person releases that condition. A run whose remaining work is all parked rests at `RUN PARKED`, not complete.
- **Shown as:** not shown as a status; name what it is waiting for.
- **Source:** `loop-engine.md` → "Ledger format" → `queue.md` (non-terminal, resting statuses); "Gates, convergence & resting states" (Convergence & the resting states).
- **Not:** Not `hold` (a paused merge), not `blocked` (waiting on another issue or a repair), not `deferred` (taken out of the run).
- **Status:** settled

### Plan
- **Plain:** The loop's written plan for one issue: who benefits, the issue's acceptance criteria, and how it intends to do the work.
- **Precise:** `issue-<N>.plan.md` in the ledger: value framing (user stories, or one line for a fix), acceptance criteria copied verbatim, the approach, a frozen copy of the approach taken before design review, the architect triggers that fired, and open questions for the person.
- **Shown as:** `SKILL.md` → Gather evidence, step 3 (the plan's `## Value framing`).
- **Source:** `loop-engine.md` → "3. Plan" and "Ledger format" → `issue-<N>.plan.md`.
- **Not:** Not published: it lives in the ledger, not the repository.
- **Status:** settled

### Plan gate
- **Plain:** The point where a person approves the loop's plan before any code is written.
- **Precise:** Step 5. Its posture comes from the `plan-gate:` field: `always` (the default, and how an absent or unrecognized value reads) stops on every issue; `conditional` stops on ambiguous criteria, risk, disagreement between the AI reviewers, a value story that does not hold, or uncertainty, and otherwise auto-approves. Under both, a material change by the design review always stops for the person. Reducing what a criterion asks for cannot be approved here; it must be recorded on the issue (see Scope split).
- **Shown as:** `SKILL.md` → Cost, *Human involvement* ("plan approval").
- **Source:** `loop-engine.md` → "5. Human gate (posture set by `plan-gate:` — plus one always-on condition)"; `README.md` → "What the loop can do to your repo" ("By default you approve every plan before any code is written").
- **Not:** An auto-approved plan is not a human decision. Not the merge gate.
- **Status:** settled

### post-gate-survivors
- **Plain:** Defects the acceptance check missed that came to light later.
- **Precise:** `post-gate-survivors=<n>` on the Budget line: defects that escaped the acceptance gate and surfaced afterward, within the iteration only at the merge gate. One found in a later iteration is recorded on that later line, naming the iteration it escaped; earlier lines are never rewritten.
- **Shown as:** not shown as a slot.
- **Source:** `loop-engine.md` → "12. Journal + stop" and "Ledger format" → `progress.md` → the Budget line field list.
- **Not:** Not `mutation-survivors` (what the check found) and not `ac-findings`.
- **Status:** settled

### Pull request
- **Plain:** A proposed change to the code, opened so it can be checked before it joins the main line.
- **Precise:** A pull request (PR) on the code host: a branch's commits, a description, and the checks and reviews run on them. The loop opens the PR right after implementing and before any review, so an open PR means the review steps have started, not that the work is ready to merge.
- **Shown as:** `SKILL.md` → title line and Status.
- **Source:** `loop-engine.md` → "7. Commit + PR"; `README.md` → "What the loop can do to your repo" ("A pull request appears before any review has run").
- **Not:** Open is not approved, and merged is not released.
- **Status:** settled

### Reinterpreted criterion
- **Plain:** An acceptance criterion was read differently from its wording while still delivering what it was for, and a person confirmed this when approving the plan.
- **Precise:** At the plan gate the loop may read down a criterion's wording while delivering its intent; a reinterpreted criterion makes the plan change material, so a person sees it. Delivering less than a criterion intends is a different thing: it must be recorded on the issue and the removed work filed (see Scope split); otherwise the acceptance check would certify a criterion that was never met.
- **Shown as:** `SKILL.md` → Spec vs. delivery ("criteria narrowed, dropped, or superseded").
- **Source:** `loop-engine.md` → "5. Human gate" (materiality test; "A narrowing or reduction of an acceptance criterion is never absorbed here").
- **Not:** Not a narrowed criterion. If a brief says "narrowed", check that the issue records the reduction; if it does not, that is a gap to report.
- **Status:** settled

### Release
- **Plain:** A numbered version published for users, such as v1.2.0; a merged change reaches users of a released product only in the next release.
- **Precise:** A tagged version under the project's release scheme. A version bump (major, minor, patch) is itself a change that is merged. Auto-merge is barred for any change that bumps the release beyond a patch.
- **Shown as:** `SKILL.md` → Executive summary, *Status* ("released in vX").
- **Source:** `loop-engine.md` → "11. Merge" (release-artifact bump, `RELEASE_SCHEME`); `SKILL.md` (pr-brief) → "Gather evidence", step 5.
- **Not:** Not a merge, and not a deploy. A project with no tags or releases has no release status to report: say so.
- **Status:** settled

### Review round
- **Plain:** One pass of a review over the change; a second round checks the fixes made after the first.
- **Precise:** A pass of a reviewing gate: code review, the acceptance check, or design review. Round 1 of code review reads the whole change; a later round reads what changed since the last reviewed commit, unless it cannot trust that anchor. Rounds are counted per gate in `gate-rounds`. The scope ruling is not a round.
- **Shown as:** `SKILL.md` → Cost, *Review effort* ("three code-review rounds").
- **Source:** `loop-engine.md` → "8. Code review"; "Gates, convergence & resting states" (Fresh-re-check invariant); `phases/reviewing.md` → "Step 8 — the procedure".
- **Not:** Always say which review the rounds belong to.
- **Status:** settled

### Round cap
- **Plain:** Code review and the acceptance check each get at most two rounds; after that the loop must stop and ask a person, who may direct more work.
- **Precise:** Round 1 is the review; round 2 is the fresh re-check of its fixes. If round 2 is still dirty, the loop escalates; it never opens round 3 itself. A third round exists only because a person directed it. Reaching the cap is not a verdict, and the person's answer is often to narrow or split the change rather than run another round. Design review carries no round cap.
- **Shown as:** `SKILL.md` → Cost, *Review effort* ("authorized round 3 past the usual cap").
- **Source:** `loop-engine.md` → "8. Code review" ("Bounded to 2 rounds"); "Gates, convergence & resting states" ("The bound — one fresh re-check, then escalate"; "Reaching a cap is a handoff, never a terminal state"); `phases/accepting.md` → "Step 10 — the procedure".
- **Not:** A round past the cap is a person's decision, not the loop's.
- **Status:** settled

### Route
- **Plain:** The kind of work, which sets which checks the loop runs: code, documentation, research, or not ready to build.
- **Precise:** Set from the issue's labels and contents. `code`: full pipeline, all checks. `docs`: no design review, no security review, a light code review, no mutation pass. `research`: lighter plan, no test-coverage check, design review optional. `stub-defer`: not implemented; status `deferred`. A route is separate from status.
- **Shown as:** not shown; describe the effect (for example "as a documentation change, it skipped security review").
- **Source:** `loop-engine.md` → "Router — classification procedure" and "Routing table".
- **Not:** Not a status.
- **Status:** settled

### Run
- **Plain:** A batch of issues the loop works through together, usually one milestone or label, with its own records.
- **Precise:** One ledger directory (`LEDGER_ROOT/<run-slug>/`), named after its backlog source. It ends `RUN COMPLETE` when every issue is finished, or rests at `RUN PARKED` when only parked work remains.
- **Shown as:** not shown.
- **Source:** `reference/initialization.md` → "Initialization procedure (new run)"; `loop-engine.md` → "Gates, convergence & resting states" (Convergence & the resting states).
- **Not:** Not an iteration (one issue), and not a CI or workflow run.
- **Status:** settled

### Scope ruling
- **Plain:** When a review finding questioned the approach itself, the loop's design reviewer recommended what to fix now and what to set aside, and the loop stopped for a person to decide.
- **Precise:** Step 8: a blocking finding that raises a design question (whether the approach is right, whether a fix belongs in this change, whether several findings share one cause) triggers a `DESIGN_AGENT` consult and a stop for the person, on every route and under every setting. The ruling may narrow the work but never clears a finding or passes the gate. If no ruling comes back, the loop still stops. It is not a review round and is not counted in `gate-rounds`.
- **Shown as:** `SKILL.md` → Cost, *Human involvement* (an escalation) and *Review effort*.
- **Source:** `loop-engine.md` → "8. Code review" (the design-question trigger); "Gates, convergence & resting states" (Gate table, Scope ruling row); `README.md` → "What the loop can do to your repo" ("When a review finding raises a design question, you see it").
- **Not:** Not a design review of the plan, and not a decision: the person decides. Not available in engines before v0.3.0.
- **Status:** settled

### Scope split
- **Plain:** Part of the issue's requested work was moved to a new issue, with a person's approval, so this pull request delivers less than the issue first asked for.
- **Precise:** Reducing what an acceptance criterion intends is an issue amendment: recorded on the issue, with the removed work filed as its own issue, so the acceptance check measures the reduced criteria. The original issue usually closes when this PR merges.
- **Shown as:** `SKILL.md` → Spec vs. delivery and *Not in this PR*.
- **Source:** `loop-engine.md` → "5. Human gate" ("reducing its intent is an issue amendment — record it on the issue and file the removed scope").
- **Not:** Not a reinterpretation, which delivers the full intent. A brief must say the split-off work is not done, even though the issue is closed.
- **Status:** settled

### Security review
- **Plain:** A check of the change for security problems, run when the change touches areas the project marks as security-sensitive.
- **Precise:** Step 9, the project's `SECURITY_REVIEW`, routed by its configuration: skipped for documentation and changes touching no sensitive surface. Findings at or above the project's confidence bar are addressed. A later fix that touches a sensitive surface is not covered by an earlier clean result and goes to a person at the merge gate.
- **Shown as:** `SKILL.md` → Cost, *Review effort* ("security review skipped by the project's rule…").
- **Source:** `loop-engine.md` → "9. Security review (by route)".
- **Not:** "Skipped" is not "passed": say why it was not due.
- **Status:** settled

### Squash merge
- **Plain:** A merge that combines all of a pull request's commits into one new commit on the main line of code.
- **Precise:** A merge method a project can bind (`MERGE_METHOD`); the engine's journal example and its commit-subject rule assume it. The new commit has the content of the PR's final state but a new identity, so no review ever read "the merged commit" as such.
- **Shown as:** `SKILL.md` → Cost, *Review effort* ("Describe what was reviewed as 'the PR's final state'").
- **Source:** `loop-engine.md` → "Routing table" (squash `--subject` discipline) and "11. Merge" (`MERGE_METHOD`); `SKILL.md` (pr-brief) → "Cost".
- **Not:** Say a review certified "the PR's final state", never "the merged commit".
- **Status:** settled

### Story (user story)
- **Plain:** A short statement of who wants something and why: "as a …, I want …, so that …".
- **Precise:** In the loop's plan, a new feature's value framing is one to three user stories, each with who benefits, how often they hit it, and the single observation that would show the feature is misdirected. A plan with no credible user stops for a person.
- **Shown as:** `SKILL.md` → Acceptance walkthrough ("checks <criterion or user story>").
- **Source:** `loop-engine.md` → "3. Plan" (Value framing).
- **Not:** Not an acceptance criterion: a story says why, a criterion says what counts as done. Some projects also call a small issue a "story".
- **Status:** settled

### Subagent
- **Plain:** An AI helper the loop starts for one task, such as reviewing the change or checking the criteria.
- **Precise:** A separate agent invocation. The loop's reviewers (finders, design reviewer, scope reviewer, acceptance checker, fresh re-checkers) are all subagents, configured per project. Each run counts once in `subagent-runs`.
- **Shown as:** not shown as a word; say "AI reviewer" or "AI helper".
- **Source:** `loop-engine.md` → "Ledger format" → `progress.md` → the Budget line field list (`subagent-runs`); `README.md` → "What 'loop engineering' means here".
- **Not:** Not a person. The design and scope reviewers are subagents even when a journal calls them by a role name such as "architect" or "pm".
- **Status:** settled

### subagent-runs
- **Plain:** How many AI helpers the loop started for this issue, a rough stand-in for computing cost but not a measure of it.
- **Precise:** `subagent-runs=<n>` on the Budget line; one run is one subagent invocation, so N reviewers in parallel count as N. It cannot see the main thread's own work, which can be the largest consumer; token cost is not yet recorded.
- **Shown as:** `SKILL.md` → Cost, *Compute (tokens)* ("Not yet measured"); may be given as a proxy.
- **Source:** `loop-engine.md` → "Ledger format" → `progress.md` → the Budget line field list (`subagent-runs`).
- **Not:** Not review rounds (`gate-rounds`), and not compute or dollar cost.
- **Status:** settled

### wall-clock
- **Plain:** Elapsed time on the issue, including time spent waiting for a person, so it is not hours of work.
- **Precise:** `wall-clock=<elapsed>` on the Budget line; defined as elapsed time including the wait for human gates, and not used as a cost limit ("an iteration that waited overnight for approval is not 'expensive'"). The engine does not fix when the clock starts. Some recorded lines note `excl. gate-wait`; when the line carries such a note, report what the note says.
- **Shown as:** `SKILL.md` → Cost, *Elapsed time* ("which *includes time spent waiting for a human*; say so").
- **Source:** `loop-engine.md` → "12. Journal + stop" and "Ledger format" → `progress.md` → the Budget line field list (`wall-clock`).
- **Not:** Not effort, and not calendar time from the issue being filed to the merge (that is longer and is the fallback when there is no journal).
- **Status:** settled (see Open decisions: recorded lines disagree with the definition)

---

## Say instead

Words that reach readers too often without help, and what to say instead.

| Avoid | Say instead | Why |
|---|---|---|
| orchestrator | the loop | The reader does not need the agent's role name. |
| finder | AI reviewer | Engine jargon for one code-review subagent. |
| architect, pm (as actors) | the loop's design reviewer / scope reviewer, an AI agent | Read as people otherwise. |
| `tokens=deferred` | Not yet measured | "Deferred" here means no measurement exists, not a postponed decision. |
| deferred (backlog sense: priority lowered, moved later) | postponed | The ledger's `deferred` means "taken out of this run"; see Open decisions. |
| AC1, AC2 (bare) | the first criterion (what it asks) | A bare ID tells the reader nothing. |
| F57, D071, other bare IDs | a recorded finding / a recorded design decision (ID) | `SKILL.md` forbids an internal ID without a plain gloss. |
| BLOCKING / EDITORIAL (caps) | blocking / editorial | Caps read as alarm; the meaning is in the glossary. |
| Class A / Class B | unmet criteria / tests that would not notice a break | Engine-internal labels. |
| CI green / red | automated checks passed / failed | Color shorthand. |
| clean pass (when a person closed the review with findings open) | closed by the owner with findings unresolved | Not a pass; the distinction must survive. |
| the merged commit (as what was reviewed) | the PR's final state | A squash merge makes a new commit no review read. |
| re-armed | needs checking again | Engine jargon for a check whose earlier pass no longer covers the code. |
| gate-wait | waiting for a person | Plain. |
| thrash | repeated review rounds | Plain, and not pejorative. |
| auto-approved (as a human decision) | approved automatically by the loop | It is not a person's decision; do not count it as one. |
| worktree, isolated copy | a temporary copy of the code | Mechanism, not meaning. |
| HEAD, SHA | the latest commit / the commit (short ID only if needed) | Git internals. |
| consumers (of a plugin or library) | projects that use it | Insider term. |
| installed plugin, re-install | the version each project has installed | A change reaches a project's runs only when that project installs the new version. |
| the engine, engine file | the loop's instructions | Insider term for the markdown the loop follows. |
| version bump | the change that sets the new version number | Jargon. |
| `priority:low` and other labels | low priority | Label syntax. |
| decision log, decision-log entry | the project's record of design decisions | Unknown term; pair with the plain gloss of any ID. |
| dogfood | using the tool on its own project | Insider term. |
| stub-defer | not ready to build | Route name. |
| calibration / escalation-only | a person approves every merge / some work may merge without asking | Mode names mean nothing to the reader. |
| walking skeleton | a thin first version that connects every part end to end | Common in planning, unknown to most executives. |
| canary | an automated check that runs on a schedule to confirm the live service works | Jargon. |
| rollback | returning to the previous version | Jargon. |
| runbook | the operations guide | Jargon. |
| pin, lockfile | fixed the exact version of a library | Jargon. |
| upstream | the library's own maintainers | Ambiguous direction word. |

## Open decisions

Terms whose meaning no source settles yet. Each line names the decision and who makes it.

- deferred: reserve "deferred" in briefs for the ledger meaning (taken out of this run) and say "postponed" for the backlog meaning (priority lowered, moved later), or settle another pair of terms (owner).
- wall-clock: the engine defines it as including waits for a person, but some recorded lines say `excl. gate-wait`; claude-code-loop#53 is open on which rule wins, and until it is settled briefs report what each line says (owner).
- escalation: the engine uses "escalate" for asking a person and for handing a question to an AI agent; confirm briefs keep "escalation" for asking a person only (owner).
- Scope: confirm technology terms (caches, hosting, libraries) stay out of this file and go in the Technology table or the briefed repo's glossary (owner).
