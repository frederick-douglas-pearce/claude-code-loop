# Phase unit `accepting` — step 10 and the AC-verifier

This file is a **phase unit** of the dev-loop engine, not a standalone document. Core
(`loop-engine.md`) lists it in its phase index and has you read it at step 10, and on Resume when
its unfinished-mutation check sends you here. Read it in full, under core's load
protocol. What holds when it is not loaded is stated in core (*What holds without each unit
loaded*), never here: its absence never makes this gate pass and never lets it be skipped.

Core keeps three things this unit relies on, because other steps act on them without it: the
mechanism blockquote (Gates → Fresh-re-check invariant), the rule for a source-changing fix made
at this gate together with its three constraints (core's step 10), and this gate's fail-safe half
(core's preamble).

## Step 10 — the procedure

Run the AC-verifier (below): a fresh check that the diff
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

**These are *result* classes, not the *finding* classes code review emits — two vocabularies, not two
granularities.** Class A and Class B are this gate's own vocabulary; BLOCKING and EDITORIAL are step
8's. The engine calls an item in either a "finding", so **"a Class B finding" carries no finding class
at all** — it is a result of this gate, which emits none. **Neither of this gate's classes may ever be
swept.**

The gate returns **two result classes, and they are never summed into one "findings" count**:
**Class A — AC-satisfaction findings** (a criterion judged not met) and **Class B — mutation
survivors** (a test this change adds or modifies that stays green when the behavior it guards is
broken — or, when the change alters behavior and adds no test at all, that absence).
Class B comes from the **mutation pass**, which is **scoped by risk surface** rather than run
unconditionally: step 10 itself remains due on every issue with acceptance criteria, but the mutation
pass *within* it is conditional (AC-verifier → Part 2). **A clean Class B after a dirty one is a
valid and valuable result** — do not read "no survivors this time" as the gate going soft.

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
   (the Verdict-first invariant). Mark each statement you return as REPRODUCED — you ran it, read it,
   or compared it in the material given to you — or INFERRED, for anything about an artifact you were
   not given; if you did not check it, say so rather than stating it, and never present an inference
   about a file you were not shown at the same weight as something you read (the Relay invariant).
   Return a checklist + overall done/not-done."*
2. For behavior that needs runtime proof, also run `VERIFY` (runs the app).
3. `CODE_REVIEW` (step 8) provides the adversarial bug pass.
Promote to a dedicated `ac-verifier` agent only if the composed approach proves too loose.

**Part 2 — Class B: mutation survivors.** A test that this change adds or modifies, which stays
green when the behavior it guards is broken, is a **survivor** — protection the human believes they
have and does not. A survivor is a finding, **reported as prominently as a bug**. (Step 8's mandatory
`guard-efficacy` lens asks a related question by **reading** and is **not** this pass; the two are
distinguished at that step.)

*Why a checklist cannot find these* — the mechanism, quoted verbatim from the project retrospective
that first made it nameable, is **the mechanism blockquote in core** (Gates → Fresh-re-check
invariant, inside the Class B recipe). It is kept there, not here, because step 8's `guard-efficacy` lens needs it
before this unit is loaded. Core is always loaded, so read it there.

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

**Its first precondition, which often fails: `TEST_CMD` must be green *in the copy*.** A bare copy carries
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

**Its third precondition — attribution: the copy must be a DIFFERENT TREE from the parent, and you
check that rather than assume it.** **Run this one FIRST, whatever its number** — it is numbered
third only so the two above keep the numbers they already had. Until it holds, neither of the others
means anything, because they are then answering questions about the parent's own tree, and
precondition 1 in particular *runs your suite* — on an unattributed copy that means running it in
your own tree, which is the recorded incident below, verbatim. **The check is two commands, and the second runs in the
parent — `git -C` is there so you never need to `cd` into the copy at all:**

```bash
git -C <copy> rev-parse --show-toplevel     # must DIFFER from the parent's
git rev-parse --show-toplevel               # the parent's, for comparison
```

**It is orthogonal to the second precondition, and that is the whole reason it exists.** A copy that
*is* the parent tree contains the change trivially, so precondition 2 passes on it — cleanly,
loudly, with a correct-looking diff. The recorded instance is exactly this: a sequence that created
a worktree, changed into it, and ran the suite, where the **create failed**, the `cd` therefore
failed, and the suite ran in the **main repository** and printed `98 passed`. Read quickly that is a
satisfied precondition. Nothing had been tested in any copy.

**So CHECK each step; do not infer it from the sequence's exit status.** A `;`-separated sequence,
or steps issued separately, keeps going after a failed `cd` and reports the **last** command's
status — so the suite runs in the parent and the whole thing exits 0. An `&&` chain does *not*
produce that shape: it short-circuits, so nothing after the failed `cd` runs at all. **`&&` is the
safer spelling and this engine uses it deliberately elsewhere; the hazard is the unchecked sequence,
not the operator.** What makes either safe is the same thing: create the copy, check that it exists
and that its toplevel differs from yours, and only then run anything in it.

**The verdict, and this is the load-bearing half: a green result from an unattributed copy is
`unproven`, never clean.** It is not a pass you may journal, exactly as a run with no control is not
(the exit table below). Treat it as the same class of answer: the pipeline was not shown to be
capable of reporting what it claims to have looked for. Re-materialize the copy correctly and re-run.

**The harness enforces a path-level form of this rather than trusting you to remember it** — the
tree-level question is still yours, via the two commands above; what the harness can see is paths and
inode identity. `--parent-root` is required,
and `mutate_verify.py` refuses a `--root` that is not isolated from it — the same tree, or the
parent's tree lying inside it — **exit `5`**, before any
target is resolved, any snapshot taken, or any test run, so a refusal costs nothing and leaves
nothing behind. **That refusal is not yours to discharge with `--in-tree-authorized`.** The flag
does technically lift it — that is what it is for — but it is the escalated in-tree rung below, which
is the human's choice for a tree that genuinely cannot be isolated. Reaching for it to quiet a copy
that was *supposed* to be isolated and was not is the one use it must never have.

**If the isolated copy cannot be used — whichever of the three preconditions failed — the
fallback is in-tree mutation with BOTH compensating controls —
explicit-path staging (step 6) **and** the restore journal (below) — and never in-tree mutation
alone.** But **do not take that rung on your own judgement.** It moves a deliberately-destructive
operation onto the tree holding the human's uncommitted work, which is a destructive and
irreversible action, so the Escalation rubric applies: **escalate to the human and let them choose
it.** If they decline, the pass was due and produced no verdict, so emit
`- gate-error: acceptance (Class B) — isolated copy unusable: <TEST_CMD unrunnable | change under
verification not present | copy not attributed as a distinct tree> — <first line of the error>` and
STOP. **One gate-error shape covers all three preconditions**, so widening the ladder never needs a
second spelling.

**Note the ladder for an attribution failure specifically, because it is the one that usually
resolves without escalating.** A refusal means *this* copy was not isolated, which is ordinarily
repaired by re-materializing it — a re-created worktree, or one re-pointed at the right commit.
Re-materialize and re-run first. Only where the tree genuinely **cannot** be isolated does the rung
above apply, and only where the human then declines it is this a `- gate-error:`. **Do not record
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
    --spec <spec.json> --test-cmd "<TEST_CMD>" --root "<the tree being mutated>" \
    --parent-root "$(git rev-parse --show-toplevel)"
```

`--test-cmd` is passed as a **parameter**, never read from a config file: this engine stays
project-agnostic and `TEST_CMD` is bound per project in `loop.config.md`. `--root` is the tree the
envelope above selected — the agent's own copy on the primary path, the project root on the
escalated in-tree path. **`--parent-root` is the tree you are protecting — your own working tree,
holding your uncommitted deliverables — and it is required. Derive it with
`git rev-parse --show-toplevel`, never with `$(pwd)`:** run from a subdirectory, `$(pwd)` names a
path *inside* your tree rather than the tree itself. The two together are what let the
harness refuse a pass whose `--root` is not isolated (the third precondition above); passing your
own root as both is the in-tree path, and on that path the refusal is lifted only by
`--in-tree-authorized`, which a human chooses.

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

**Read the exit status — the six codes are distinct on purpose**, and collapsing any two of them
lets a result read as a different result:

| Exit | Meaning | What you do |
|---|---|---|
| `0` | clean — every real mutation killed, and a control proved the pipeline can report a survivor | `mutation-survivors=0` |
| `1` | the pass worked and found survivors — **a result, not an error** | Class B findings; each blocks |
| `2` | harness error — no match, a no-op mutation, a bad spec, a red baseline, a control that was **killed**, a spec made only of controls, or any other harness failure | `- gate-error:`, STOP |
| `3` | unproven — no control, so the clean verdict is not trustworthy | not a pass; add a control and re-run. If a control cannot be produced, the pass was due and produced no verdict: `- gate-error:` and STOP — **never `=0`**, which would report an unproven pipeline as a clean one, and never `n/a` |
| `4` | restore failed — **a mutation may still be live in the tree** | `- Restore: finding`, and **read the harness's error lines before touching anything** — see below |
| `5` | unattributed — `--root` is not isolated from `--parent-root`: the same tree, or the parent's tree lying inside it. Refused before any target was resolved, any snapshot taken, or any test run | not a pass and **never `=0`**, and never `n/a` — the ladder above owns what this row does not restate. Re-materialize the copy and re-run. `--in-tree-authorized` is **not** your remedy — it is the human's escalated rung for a tree that cannot be isolated at all |

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
the guard (assert the *mechanism*, per the mechanism blockquote, not the outcome) and re-verify, within the
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

*End of the `accepting` unit.*
