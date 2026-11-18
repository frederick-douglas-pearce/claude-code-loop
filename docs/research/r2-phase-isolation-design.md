# R2 — phase isolation: a thin controller plus forked phases

**Status:** design note (#279). Nothing here is engine text, and nothing ships. The proposed decision
at the end is **unratified** until the owner says otherwise.
**Opened:** 2026-11-18, engine 0.6.0 (payload unchanged in-tree since `44e0c69`; payload freeze in
force until R1, #288, branches).
**Question:** can the parent become a thin controller — with each phase between the human gates
running in its own forked context, loading only what it needs, and returning a bounded result —
**without any phase losing its fail-safe half**? And what would that save, once the gate re-warm is
priced in?

Builds on [`context-architecture-refactor.md`](context-architecture-refactor.md) (2026-08-25, the
first controller note and its architect corrections) and on the cost review's
[§3 R2 and R9](cost-review-2026-10-26.md#r2-phase-isolation-each-phase-in-its-own-context-context--turns).
It does not restate either. Feeds three things: the #280 spike (its falsifier is pre-registered
here), #35 (where shared invariants live), and the #271 ordering of R2 against R1.

**What this note can and cannot decide.** Its cost numbers are SCOUTING: one instrument
(`tree_cost.py --by-step`, #273), a handful of sessions, never pooled. They rank phases and size the
falsifier's thresholds. **They never close R2 on cost, and they never decide R2 against R1** — R1's
15–35% is itself modeled. The one "no" this note can return on its own is structural: a phase that
cannot carry its fail-safe half in a return the controller can check. That question is answered in
§3, and the answer is that every phase can, at a price §3 states.

---

## 1. The shape

**The controller** is what the parent keeps:

| keeps | why it cannot move |
|---|---|
| `SKILL.md` and its fail-safe invariants | it is the partial-load backstop; a controller that loaded less would under-gate |
| step 0 (load/resume, orphan scan), step 1 (select), step 2 (route) | they read the whole ledger and decide what runs; a fork is chosen by them |
| the Gate table, the Routing table, the closed status vocabulary | the index of what is owed; due-ness must resolve where the controller can read it (08-25 note, B1) |
| both human gates: step 5's stop, step 11's merge decision | only the main conversation talks to the human (§4, constraint C8) |
| step 5's frozen-vs-live diff and its `- Plan-gate:` line | the always-on condition is a diff the controller takes, never a fork's self-report |
| step 6 implement and step 7 commit/PR | D017 keeps step 6 in core; D018 says no fork can carry an `implement` role; commits stay with the tree's owner |
| the remote head check, `git worktree list` and `git status` **after every phase return**, and the head check before the merge | currency and tree state are checked against live state, which the controller owns. Step 9's head check *before the label* runs in the review fork, which applies the label (§2.5) |
| ledger status transitions in `queue.md` | one writer for the authoritative status file |

**A phase** is the work between two controller decisions, run in a fork:

| phase | engine steps | returns to |
|---|---|---|
| `planning` | 3 plan, 4 architect (plan-informing) | step 5, in the controller |
| `reviewing` | 8 code review (finders, fix agent post-R1, fresh re-check, scope ruling), 9 security (head check, label or local skill) | the controller, before step 10 |
| `accepting` | 10 AC-verify (Part 1, Part 2 mutation) | step 11, in the controller |

Three phases, not seven. Step 6 stays (D017, D018); steps 7, 11 and 12 are controller work, because
each writes something the controller owns (a commit, a merge, the close record). The `reference`
appendix units stay controller-read, at the points the phase index names today.

## 2. The phase contract

Every phase follows one contract. **The controller verifies identity, never judgment.** It can check
that an artifact exists, that a SHA matches the live head, and that a record is present and
well-formed. It cannot check that the procedure ran well. **A phase's procedural fidelity rests
entirely on the fork loading, in full, every passage that phase acts on.** That is what `SKILL.md`'s
engine-read protocol rests on today, one level down. §2.2 says which passages those are, and the
answer is larger than "the unit". The contract does not pretend otherwise.

### 2.1 Inputs are on disk

A fork sees none of the controller's conversation (§4, C6). Everything a phase needs is passed as
paths:
- the ledger directory;
- the issue number;
- the plan file;
- the branch;
- the base SHA;
- for a resumed phase, the gate-decision blocks already written.

Nothing the controller "knows" reaches the fork unless it is on disk or in the skill arguments. That
is the loop's design already: state lives in the ledger so `/clear` survives. So it costs nothing new.

### 2.2 What the fork loads, and why the unit is not enough

**The units do not hold their phases' fail-safe halves. Core does.**
- `phases/reviewing.md` says so in its preamble: "This step's fail-safe half is in core (step 8)."
- `phases/accepting.md` lists what core keeps for it: the mechanism blockquote, the rule for a
  source-changing fix and its three constraints, the Model tiers passage, and the gate's fail-safe
  half.

#166 put them there deliberately, for partial-load safety in a single context. Concretely, core's
step-8 span holds all of these, and none of them appears in `reviewing.md`:
- the `guard-efficacy` floor;
- default-deny BLOCKING;
- the 2-round cap;
- the design-question stop and its scope ruling.

Core also holds step 9 (procedure and head check) and step 10's source-changing-fix escalation.

So a fork that loads its unit and a kernel of general invariants can return a well-formed
`verdict: clean`, at the right SHA, after it has fixed a design-question finding before the human
saw it, or looped past the cap. The controller checks identity, so it accepts that return. **That
would be a silent skip.**

**The rule, therefore:**
- A fork loads `loop.config.md`, its unit, **and every core span that unit relies on**, each in full
  under the engine-read protocol, plus whatever §5's rule requires.
- For `reviewing`, that is core's step-8 and step-9 text and the Tool surface's isolation and staging
  duties.
- For `accepting`, it is step 10's text, the Fresh-re-check invariant with the mechanism blockquote,
  and the Model tiers passage.
- For `planning`, it is steps 3–4, the plan template, and the freeze rule.

**A fork that cannot confirm a complete load returns `load-failure`**, never a partial procedure.
Where those spans *live* under R2 is disputed (§2.8). Which ones the fork must *load* is not.

**The fork does not load `SKILL.md` as-is.** `SKILL.md` tells its reader to read the full
`loop-engine.md` first, and its fail-safe list over-escalates when the engine is not loaded: every
finding is BLOCKING, so no EDITORIAL sweep could ever run. A phase skill's body therefore carries its
own short version of that list, scoped to the phase: what it loads, and what it returns if the load
fails. `SKILL.md` stays the controller's.

### 2.3 The return schema — a closed set of variants

A phase returns exactly one of four variants.

**`verdict`** carries:
- the gate's result (clean, findings, met or not-met);
- **the head SHA it certified**;
- the paths of the records it wrote;
- the evidence for the controller's `- Budget:` line (`subagent-runs`, the phase's `gate-rounds`, and
  `models=`), so those slots are not left unknown.

A `planning` verdict also carries a **required** field, `architect: ran | skipped (<reason>)`. An
absent or unrecognized value reads as `ran`, so the frozen block is required.

The controller then:
- runs the post-return checks (§2.5);
- compares the SHA with the live head;
- confirms the phase's **required record set** (§2.4) exists and is well-formed;
- for `planning`, takes step 5's diff itself;
- then advances the row.

**`stopped-for-human`** carries:
- why: a design-question finding, the round cap reached, a contested finding, or a Class A source fix
  at step 10;
- the state written to disk;
- what is put to the human.

The controller performs the stop itself, presents what the fork wrote, and waits. On the answer, it
re-enters with a **fresh fork** that resumes from disk (§2.6).

**`load-failure`** carries which file could not be confirmed, and the first error line. The
controller writes `- gate-error: <phase> — <unit> not loaded — <first line>` and stops.

**`gate-error`** means a gate inside the phase ran and produced no verdict. The controller checks
that the fork wrote the `- gate-error:` line, **writes it itself if the fork did not**, and stops.

**Anything else is a `gate-error`.** Each of these is "no verdict":
- a return the controller does not recognize;
- a `verdict` whose SHA does not match the live head;
- a missing required record;
- an empty return;
- a fork that died.

By the Gate-outcome invariant, no verdict is not a pass. This is `SKILL.md`'s partial-load rule
stated as a schema rather than as prose. The schema is closed for the same reason the status
vocabulary is.

**A step-5 consult is the controller's.** Where step 5 first consults `DESIGN_AGENT` (engine step 5,
"the freeze is owed at step 4 or at step 5"), the controller does that freeze and that consult. The
`planning` fork owns only the step-4 pass.

### 2.4 One writer per record, and a required set per phase

The evidence for most `progress.md` lines lives inside the fork:
- the review rounds and their ranges (`- Code-review:`);
- the declines;
- the scope ruling;
- `- Editorial:`;
- `- Restore:`;
- the AC-verify counts;
- any `- gate-error:` raised inside the phase.

**So the fork writes its own gate-decision blocks.** The controller writes the records it holds the
evidence for:
- curation;
- the `- Plan-gate:` line;
- the open record at step 7;
- the close record and `- Budget:` at step 12, built from the evidence each verdict carries.

**The controller checks the records a phase owes, never the records a fork names.** A fork that names
fewer records would otherwise pass. Each phase has a **required record set** that the controller
holds, stated default-deny:
- `planning`: the plan file, with verbatim ACs, value framing, and the frozen block whenever
  `architect: ran`.
- `reviewing`: a `- Code-review:` element per round, an `- Editorial:` line, and the security
  outcome.
- `accepting`: `- Restore:` and the Class A and Class B counts.

**A missing required record is a `gate-error`, whatever the return names.** A record whose
requiredness the controller cannot tell is required.

Two writers to an append-only file are not mechanically protected: the append-only guard hook covers
`Write` only, and both writers append. They never write concurrently, though. A phase runs in the
foreground (§4, C5) and the controller waits, so the order is sequential, which is the property
append-only needs.

### 2.5 Who commits, and the checks after every return

| phase | writes to the tree? | who commits |
|---|---|---|
| `planning` | no: the plan file is in the gitignored ledger | — |
| `reviewing` | yes: the R1 fix agent, in its own isolated copy | **the review fork**, after collect-apply-remove and under explicit-path staging, then it pushes. The fork also runs step 9, including the **head check before the label** (engine step 9) and the label itself. The `verdict` carries the resulting head SHA |
| `accepting` | yes: Class A/B fixes and the mutation copy | **the accepting fork**, on the same terms. A source-changing fix returns `stopped-for-human`, as step 10 escalates today |

The 08-25 note found that a controller makes the staging burden **rise**, because collect-then-remove
moves from a rare path to the main path. Forking the phase moves that burden rather than reducing it:
- the fork owns the tree for the length of the phase;
- the controller must not touch the tree while a fork runs.

That is the existing Execution policy (the parent owns the tree, and nothing may concurrently mutate
it), with "parent" read as "whoever holds the tree right now".

**After every return, `gate-error` and a dead fork included, the controller's first act is the same
three checks:**
1. the remote head check;
2. `git worktree list`;
3. `git status`.

A fork that died while a fix agent's isolated copy was live has left the staging window open, and
this is how the controller finds out. It is no longer a step-11-only check.

A labeled security review reports on the remote, asynchronously. The `reviewing` verdict waits for
that result, or it returns `stopped-for-human` with the label applied and the review pending. It
never returns `clean` on a review that has not reported.

### 2.6 Resume — and the one change it makes

A fork cannot be resumed. It returns, and the next fork starts cold. So every phase needs write-once
resume rules: check for the artifact, and never redo the side effect. A `planning` re-entry already
has them (engine Resume, the two write-once side effects).

**For `reviewing`, this is a change to Resume, not an extension of it.** Today an `in-review` resume
**replays** step 8, and step 11 **sums** the `- Editorial:` lines across replays. A review fork
re-entering after `stopped-for-human` would instead **continue**: it reads the round's
gate-decision block and acts on the human's answer. That needs engine text, and it is disputed
(§2.8).

**Whichever way that is decided, the cap cannot reset.** A resumed fork that cannot establish the
round count from the ledger treats the cap as reached, and returns `stopped-for-human`. Unknown lands
on the over-gating side.

The row's Status stays the coarse anchor, and live git/PR state stays the source of truth, exactly as
today.

### 2.7 Per phase: where the fail-safe half is, and how the controller sees it

**`planning`**
- *Fail-safe half:* the freeze before `DESIGN_AGENT` (write-once); ACs copied verbatim; value
  framing; escalate rather than build when there is no credible user.
- *Where it is:* steps 3–4 in core and the `plan-template` unit, both loaded by the fork.
- *What the controller checks:* the required `architect:` field. On `ran` (or absent), the frozen
  block must exist, and if it does not, the result is material ⇒ stop, as today. The controller takes
  step 5's diff itself.

**`reviewing`**
- *Fail-safe half:* the `guard-efficacy` floor; BLOCKING by default-deny; the design-question stop
  **before any fix**; the 2-round cap; the fresh re-check; step 9's head check.
- *Where it is:* **core's step-8 and step-9 text**, not `reviewing.md`. The fork loads both in full,
  plus the unit (§2.2).
- *What the controller checks:* the design-question stop and the cap surface as `stopped-for-human`;
  the required records (§2.4) are checked; the head check and worktree check run on return.

**`accepting`**
- *Fail-safe half:* either class blocks; an unresolvable `$BASE` ⇒ escalate; the restore check; a
  source-changing fix ⇒ escalate.
- *Where it is:* **core's step-10 text**, the Fresh-re-check invariant with its blockquote, and Model
  tiers, plus `accepting.md`, all loaded by the fork.
- *What the controller checks:* it reads `- Restore:` and the Class A/B counts off the fork's records,
  and runs `git worktree list` and `git status` itself before step 11.

**What makes this safe is the same thing that made the 2026-08-25 sharding safe.** That note's
architect review said it plainly: the safety comes from the retained Gate table, the Gate-outcome
invariant, and the load protocol, not from the fail-safe halves as such. Under forking:
- those three stay in the controller;
- the load protocol is repeated inside each fork, over the core spans it needs;
- the return schema closes the one new gap, which is a fork's claim reaching the controller
  unverified.

### 2.8 Disputed: where the core spans live under R2

This is for the owner to decide. It sets the size of every fork's cold load, and so most of §6's
range.
- **(a) Move them into the units.** Step 8's fail-safe half goes into `reviewing.md`, step 10's into
  `accepting.md`. This reverses #166's "fail-safe half in core", which was justified by partial-load
  safety in a *single* context. Under R2 the controller never runs step 8, so core no longer needs it.
  But a single-context fallback (§7, depth limit) would then need the unit loaded before step 8,
  which it already does.
- **(b) Put them in the shared kernel (§5)**, so the controller loads them too. They stay in one
  place, but every fork and the controller pay for spans most of them never act on.

**Recommendation: (a).**
- It puts each span with the only reader that acts on it.
- It shrinks the controller, which is the point of R2.
- Its partial-load story is already the one the units use: a unit that is not loaded makes no gate
  pass.

**The cost:** #166's placement reverses, and a unit's preamble stops saying "this step's fail-safe
half is in core". That is engine text, so it waits for #280 and the payload freeze either way.

## 3. Can every phase carry its fail-safe half? — the structural answer

**Yes, if each fork loads the core spans §2.2 names.** No phase was found whose fail-safe half needs
the controller's conversation, and no stop needs a fork to wait on the human. **The structural null
does not fire.** It would have fired against the draft of this note that loaded the unit alone; that
is §2.2's finding, and the fix is to load more, not to verify more.

The answer comes with three costs, and §6's model must carry them:
1. **Each fork pays its own load.** It loads the config, its unit, its core spans and the kernel
   cold: a cache write, not a cache read, on every invocation. That is the price of "a pointer across
   a unit boundary is never a fail-safe half". It is also why the cost review's 25–40% may not be net
   of anything: that range was modeled before this replication was counted.
2. **A stop for the human doubles a load.** A `stopped-for-human` return ends the fork, and the answer
   starts a new one, which loads everything again. On an issue that stops mid-review, the review
   phase is paid for twice.
3. **Review's Resume semantics change** (§2.6). That is engine text, not a cost in tokens, but it is a
   cost.

## 4. Constraints

Re-checked **2026-11-18** against the current Claude Code docs ([`skills.md`](https://code.claude.com/docs/en/skills.md),
[`sub-agents.md`](https://code.claude.com/docs/en/sub-agents.md),
[`prompt-caching.md`](https://code.claude.com/docs/en/prompt-caching.md),
[`settings-reference.md`](https://code.claude.com/docs/en/settings-reference.md),
[`env-vars.md`](https://code.claude.com/docs/en/env-vars.md)). These claims were first recorded on
2026-10-26 (cost review §3 R2). One of them is now **wrong**: C4. Claude Code changes without notice,
so each row carries its check date.
- **REPRODUCED** means a doc sentence states the claim. C3, C4 and C7's skill-field half were also
  spot-checked by hand.
- **INFERRED** means no doc sentence states it.
- No empirical checks were run. Those are #280's job.

| # | constraint | status (2026-11-18) |
|---|---|---|
| C1 | **A skill with `context: fork` runs its body as a new subagent's prompt.** `agent:` picks the type (default `general-purpose`). The docs: "The subagent doesn't see your conversation history." The result "arrives in your conversation when it completes." | REPRODUCED |
| C2 | **Nesting:** "up to three layers below the main conversation". Set by `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH`: default 3, `1` disables nesting, needs v2.1.217+. | REPRODUCED |
| C3 | **The first filter removes these tools from every subagent, even when listed in its `tools` field:** `Workflow`, `AskUserQuestion`, `EndConversation`, `EnterPlanMode`, `ExitPlanMode` (outside plan mode), `ScheduleWakeup`, `WaitForMcpServers`, and `Agent` at the depth limit. So `Workflow` is controller-only, as recorded. | REPRODUCED |
| C4 | **~~A backgrounded fork loses `Agent`~~ — corrected.** "Apart from `Agent` and `ExitPlanMode`, which follow the first filter's conditions wherever the subagent runs, a background subagent keeps … only these built-in tools: …" A background fork *keeps* `Agent`. It loses most other built-ins. | REPRODUCED; **the 10-26 claim is contradicted** |
| C5 | **`background:` defaults to `true`.** `false` waits "for the forked subagent's result in the turn that invoked the skill". Phases still set `background: false`, now for a different reason than recorded: the controller must wait (§2.4's sequential-writer property depends on it), and a background fork's narrower tool set excludes tools a phase may need. | REPRODUCED (default and behavior); the reason is this note's |
| C6 | **What a fork sees:** its skill body with `$ARGUMENTS` substituted, plus `CLAUDE.md` per its agent type's startup context. Never the parent conversation. Hence §2.1: everything is on disk. | REPRODUCED |
| C7 | **Model and effort.** A skill's frontmatter `model:` and `effort:` are honored under `context: fork`: "the value sets the forked subagent's model instead", and the same for effort. The per-call `effort` on `Agent` is for "a non-fork subagent" only. A per-call `model` *on a fork* is not covered by the docs. Under `CLAUDE_CODE_SUBAGENT_MODEL_FORCE`, a fork runs on the parent's model. | skill-field half REPRODUCED; the per-call model on a fork: docs silent |
| C8 | **A fork cannot ask the human.** `AskUserQuestion` is in C3's removal list, so a phase that needs a human answer must return. That is why `stopped-for-human` exists (§2.3). | removal REPRODUCED; "must return" INFERRED |
| C9 | **Cache TTL.** Main conversation: 1 hour on a subscription within plan usage; 5 minutes on an API key, usage credits, or a cloud provider. Subagents: 5 minutes by default. `promptCacheTtl` and `subagentPromptCacheTtl` (values `"5m"`/`"1h"`, v2.1.242+) and a per-agent `experimental.cacheTtl` (v2.1.248+) set them. A phase that can end in `stopped-for-human` gains nothing from a longer subagent TTL, because the fork has returned before the wait. The controller's `promptCacheTtl: 1h` is what the gate wait needs (R9). | REPRODUCED |
| C10 | **`${CLAUDE_PLUGIN_ROOT}`** is "Substituted only in plugin skills", in the skill's markdown content. A fork's prompt *is* that content, so a phase skill can name its unit by plugin path. The `Skill` tool is available to subagents unless denied. | substitution REPRODUCED; "therefore available in the fork" INFERRED |
| C11 | **Step 6 stays in the parent** (D017). | decision, not a platform fact |

**What C7 does to D018.** D018 (2026-11-12) says "a forked phase ignores both spawn parameters, so no
fork can carry an `implement` role".
- **The per-spawn half is not contradicted, but it is unverified for `model`.** `MODEL_TIERS`
  resolves per spawn, from the consumer's config. A fork takes no per-call effort (REPRODUCED), and
  the docs do not cover a per-call model on one.
- **D018's premise sentence is partly superseded.** It says "a forked phase ignores both spawn
  parameters", but C7 shows that skill frontmatter does set a fork's model and effort. This note
  proposes an erratum on D018 (§11). The conclusion stands; the sentence's reason does not, as
  written.
- **What C7 adds:** a fork *can* be tiered, but only statically, in the phase skill's own frontmatter.
  That frontmatter ships in the payload, and the payload is project-agnostic, so it can hold no
  consumer's tier.

So D018's conclusion stands for `MODEL_TIERS`. A phase skill should leave `model:` and `effort:`
unset (inherit), and **every role spawned *inside* a fork resolves through `MODEL_TIERS` as today.**
Those spawns are ordinary `Agent` calls, and the per-call `model`/`effort` reach them (C7 is silent
only on the fork itself). This needs the fork to load core's Model tiers passage, which §2.2 already
requires for `accepting` and which `reviewing` needs for its re-checker. That last point is **INFERRED** and is the first thing #280 should observe:
record the `models=` slot for spawns inside the fork. It agrees with D017 (step 6 in the parent) and
with D018's reserved `implement` role: neither needs a fork.


## 5. Shared invariants — the rule #35 needs

**Default-deny, not a list of sections:** *an invariant whose fail-safe half any fork needs lives in
text the fork loads in full — the controller-loaded text is not that text, because a fork does not
inherit the controller's context — or is stated in full in the unit. A pointer across a unit boundary
is never a fail-safe half.* If you cannot tell whether a fork needs an invariant's fail-safe half, it
does.

This changes #35's problem. Under a single context, "state it once, point elsewhere" is safe because
the pointer resolves in text already loaded. Under forks, the controller's copy of the Gate-outcome
invariant is not in the review fork, so a review unit that points at it points into nothing. Two
homes satisfy the rule for an invariant several forks need:

- **A small shared kernel** that every fork loads in full, with the controller loading it too: one
  copy, loaded N+1 times. **Its contents are decided by the rule, not by a list here.** Any list
  would be the enumerable-assertion trap, and the first draft of this note fell into it: it listed
  general invariants and missed the phase-specific fail-safe halves §2.2 found in core. The
  Gate-outcome, Fresh-re-check, Relay and Verdict-first invariants, the currency clause and the
  staging rule are *examples* of what the rule pulls in, not its extent. The phase-specific spans go
  wherever §2.8 decides.
- **Restatement inside each unit**, which is the multi-site drift #35 exists to reduce.

*Deviation from the plan, recorded:* the plan's Approach said a fork-needed invariant could live "in
the controller-loaded text". It cannot, because a fork does not inherit the controller's context.
The rule above corrects that.

The kernel is the better answer, and it makes the rest of R3's deletion worth more: **every byte cut
from text a fork must load is cut once per fork per issue**, on a cold cache. Under a single context
a byte of core costs one cache write and then reads; under R2 a byte of the kernel costs a write per
fork. Cutting Gates, Ledger format and Tool surface down to their kernel is therefore worth more under
R2 than under today's engine — the 2026-10-27 note on #279 says this, and the arithmetic agrees.

A kernel is a new multi-site artifact, so it inherits the 08-25 note's B3 lesson: it needs a
mechanical identity guard (every unit that names a kernel invariant loads the kernel; every phase in
the controller's registry resolves to a skill that exists), never a truth check.

## 6. What it would save — re-modeled with the gate re-warm, SCOUTING

**Every figure in this section is SCOUTING.** Source: `tree_cost.py --sessions … --by-step` (#273),
whose docstring says n=1 and "do not cite its figures". There are three sessions, in two strata, and
they are **never pooled**. Step dollars and Σctx are the tool's output (the #273 table was re-run by
hand for this note and matches). Peak and gate-stop contexts come from a scratch pass over the same
transcripts, with the same `message.id` dedupe and turn counts matching the tool, so they are
**INFERRED**, not tool output. Context is prompt tokens: input + cache read + cache write.

### 6.1 Where the parent's money and context go

| session | engine · stratum | parent $ | sub $ | turns | plan-gate ctx | merge-gate ctx | top parent-$ steps |
|---|---|---:|---:|---:|---:|---:|---|
| `3f30a898` (vote, two invocations) | 0.3.1 · opus-5-5@high | 87.90 | 40.62 | 423 | 324k; 783k | 697k; 282k (after compaction) | inv1: acceptance 14.51, review 13.82, implement 13.57 · inv2: review 14.49, implement 9.69 |
| `e628e410` (#272) | 0.6.0 · opus-5-5@medium | 13.01 | 8.55 | 128 | 204k | 405k | review 5.51, implement 2.50, security 1.91 |
| `261e63c5` (#273) | 0.6.0 · opus-5-5@medium | 17.68 | 9.80 | 140 | 211k | 466k | review 8.02, implement 3.02, plan 2.36 |

**A DETECTOR FAILURE is reported, not dropped.** In `e628e410`, the tool printed "step entries out of
pipeline order: … acceptance 7 …": the `accepting.md` marker fired during planning, so turns 7–24
(really steps 3–5) are booked as acceptance. Read that session's plan cost as roughly the
"acceptance" row ($1.45 parent), and its acceptance as unmeasured.

What the three agree on:
- **Review is the largest parent step** in every 0.6.0 session (42% and 45% of parent $) and in
  `3f30a898`'s second invocation. In its first invocation, acceptance narrowly beats review, and
  $10.64 of that acceptance is re-warm. This is §7's reason for designing the review phase first.
- **Implement is second, and it spends nothing on subagents.** §1 keeps it in the parent (D017,
  D018). That is the largest cost R2 leaves untouched by design.
- **Residency only grows.** On 0.6.0 the parent is at about 115–150k after load, 204–211k at the plan
  gate, and 405–466k at the merge gate. Review adds the most (about +110k and +125k). In `3f30a898`
  residency carried across two invocations: the second plan gate opened at 783k. R9's
  one-invocation-per-session rule addresses that carry, not R2.
- **The human stops inside review** (2–3 per 0.6.0 session) sit at 300–410k of parent context.

### 6.2 A step-3 fork (the #280 spike), modeled on the 0.6.0 sessions

The spike forks steps 3–4. The controller still loads full core (§8). The model has three terms.

- **Load cost of the fork** (cold, at the cache-write rate):
  - What it loads: `loop.config.md` (~6.5k, this repo's) + `plan-template` (~0.7k) + core's steps 3–4 text (~2.5k) + a phase-skill body carrying its own partial-load list (§2.2; ~1–3k assumed) + the shared kernel *K* (§5, not yet drafted; 5–20k assumed) + the issue. It does not load `SKILL.md` (§2.2).
  - Measured at 0.6.0 `wc -c ÷ 4`.
  - Total: **~16–33k + the issue**.
  - **This is where the range is net of replicating the fail-safe halves.** *K* is that replication.
- **The plan step's own turns, moved to the fork.** In `261e63c5`, the plan step ran 31 parent turns at a mean of 193k (Σctx 5.98M, $2.36).
  - Run in a fork, the same turns start at ~16–33k and grow by the step's own reads.
  - Modeled mean ≈ 45–80k, so Σctx ≈ 1.4–2.5M.
  - Saving ≈ **3.5–4.6M Σctx**.
- **Downstream residency, the larger term.** The plan step adds 56–65k to the parent: plan-gate context minus load-end peak, which is 204−148k (`e628e410`) and 211−146k (`261e63c5`).
  - Under the fork, most of that stays out of the parent for every later turn. The controller does re-read the plan file to diff and present it, at most ~6k at today's plan sizes.
  - Using `261e63c5`'s own figure (65k − 6k = 59k) over its ~105 later parent turns: ≈ **6.2M Σctx**.
  - **That is an upper bound.** The 65k also holds the step-4 architect return and step-5 work, and in the spike part of that stays in the controller (§2.3, step-5 consults).

At `261e63c5`'s blended parent rate (≈ $0.40 per M Σctx: $17.68 / 44.05M), the total is
**at most ≈ 9.7–10.8M Σctx, ≈ $3.9–4.3 of a $27.49 whole-tree session (≤ ~14–16%)**. Read that as a range on
one session, not a prediction. Two cautions:
- The blended rate mixes cache reads with writes and output.
- The downstream term assumes nothing else re-reads what the plan step read. Step 6 often re-reads the issue and the files the plan names, which would claw part of it back.

**The #280 threshold X is fixed here: X = 40k** of plan-gate parent context, as a median *paired*
reduction. That is the lower observed step-3 growth (56k), minus the controller's plan-file read
(≤ 6k), minus a 10k margin. It is fixed now, before any spike data, and §10 uses it. **Caveat,
disclosed in advance:** because the 56k includes step-4 and step-5 work, X may be high, and that
pushes a real but smaller effect into §10's sub-threshold outcome rather than into go.

### 6.3 The gate re-warm

A re-warm re-writes the parent's whole context to cache after a wait longer than the cache TTL. The one observed instance:
- Appendix D (`3f30a898`): **$7.60 to resume at 947k**, ≈ **$8.0 per M tokens** at the 1-hour TTL's write rate.
- That anchor is 0.3.1@high on one session, and R9 is the source for it.

On an API key, the main-conversation TTL is 5 minutes (R9). Per token, a 5-minute cache write is
cheaper than a 1-hour one (INFERRED from Anthropic's published cache pricing: 1.25× base input
against 2×, so ≈ 0.6 of the anchor). But nearly every human wait outlasts it, so the re-warm is paid
at almost every stop.

| stop | today (0.6.0) | spike controller | full-R2 controller (assumed 40–80k) | re-warm saved per stop, 1h · 5-min |
|---|---:|---:|---:|---|
| plan gate | 204–211k | ~150k | 40–80k | spike: ≈ $0.45 · $0.28 — full: ≈ $1.0–1.4 · $0.6–0.9 |
| a review escalation | 300–410k | unchanged | 40–80k | full: ≈ $1.8–3.0 · $1.1–1.9 |
| merge gate | 405–466k | ~350–410k (less the plan step's 50–60k) | 40–80k | spike: ≈ $0.45 · $0.28 — full: ≈ $2.6–3.4 · $1.6–2.1 |

**The spike's re-warm saving is small**, under $1 per issue at either TTL, because the spike controller
still carries full core and everything after step 4. **The full-R2 figures depend on a controller
nobody has built**: its 40–80k is an assumption (SKILL.md + core minus the forked steps + the kernel +
ledger reads), not a measurement. Per issue on 0.6.0, with one plan gate, 2–3 review stops and one
merge gate all outlasting the TTL, the full-R2 re-warm saving would be ≈ $7–14 at 1h and ≈ $4–9 at
5 minutes, **gross**.
- **Net it of §3's second cost:** each `stopped-for-human` re-entry pays a fresh fork load (~16–33k +
  the core spans + re-reading the diff and the round's block), at the cache-write rate. That is
  roughly $0.2–0.5 per stop at the 1h anchor. It is not subtracted in the table.
- These figures set a modeled saving for an *assumed* controller against a *measured* bill whose
  re-warm content on 0.6.0 is $0 and $2.49 (both short-wait sessions), so they do not compare.
- What they suggest is only that full R2's case would rest on the re-warm, not on the turns, **if**
  human waits are long.

#274's scripted approvals cannot observe that (§10).

### 6.4 What this does and does not say about 25–40%

- **It does not confirm the cost review's 25–40%.** That range was modeled before the fork's own
  cold load (the replicated fail-safe halves, *K*) was counted. §6.2 counts it for one phase.
- **The step-3 fork alone models at no more than about 14–16% on one session.** The review phase would be larger
  (it is 39% of `261e63c5`'s Σctx), but it is designed against post-R1 step 8 (§7), which does not
  exist yet. So no total is modeled here.
- **Whether R2 lands before or after R1 is #271's call**, on #280's and R1's benchmark data, never on
  these numbers.

## 7. The review phase, designed against R1

The turns are in step 8 (cost review §3 R1: about 17 parent turns per round, rounds per issue around
5). So the review phase is where R2 pays most — and it is designed here against **step 8 as R1
(#288) will leave it**, with a fresh fix agent per dirty round and an iteration round ceiling. #288 is
written after #35, which waits on this note, so this section is a target, not a dependency.

Nesting, counted from the main conversation:

```
controller (main conversation)
└─ review fork                      depth 1
   ├─ finders ×N (read-only)         depth 2
   ├─ fix agent (isolated copy)      depth 2
   ├─ fresh re-checker               depth 2
   ├─ DESIGN_AGENT scope ruling      depth 2
   └─ /security-review (skill)       in the fork
```

Every spawn is at depth 2, within the limit in §4 (C2). **If the limit shrinks below 2, the review
phase falls back to running in the controller**, as today, and the note's saving for step 8 goes to
zero; that is the fail-safe direction (more context, no lost gate).

The design-question stop is the case that shows the contract works or does not. A finder returns a
BLOCKING finding raising a design question. The fork consults `DESIGN_AGENT`, writes the round's
gate-decision block with the ruling, and returns `stopped-for-human` **before any fix is applied**.
The controller presents the ruling. On the answer, a fresh review fork reads the block and continues.
No fork ever waits on the human, and no fix lands before the human speaks.

## 8. Why #280 spikes step 3, not step 8

The payoff is in step 8, and the spike is at step 3. That is deliberate, and the reason is the human
gate, not "step 3 is safest":

- **Under `plan-gate: always`, every issue stops at the plan gate.** The parent's context at that stop
  is what a re-warm costs (R9), so shrinking it is a real saving, not a proxy for one. Today the
  parent arrives there carrying the engine plus the issue, the plan reads and the architect's return.
- **Step 3 tests the mechanism with the fewest moving parts**: one fork, no tree writes, no nested
  spawns beyond the architect, one return variant in the common case.

**What a step-3 spike does not measure.** The controller in the spike still loads the full core,
because the controller-side reduction (dropping step 3–4 procedure from core) is engine text the
payload freeze forbids, and #35's kernel does not exist yet. So the spike measures the forking
mechanism plus the removal of step 3's reads from the parent — not R2's total. **A step-3 no-go on
cost does not kill R2**; it says step 3 alone does not pay. A step-3 no-go on a fail-safe artifact
does: the contract failed on its simplest phase.

## 9. D001, revisited on the new ground

D001 kept controller-ification out of the sharding increment as "a convergence lever, not a context
lever", because `Agent` returns are 0.9–3.7% of parent context. That was right about returns. R2's
claim is different: **the phase's reads, and the engine text that drives them, never enter the
parent at all.** The 08-25 note made three corrections, and each needs an answer.

1. **"Controller-ification is not established as a context lever."**
   - That is still true of controller-ification as the 08-25 note framed it, which was delegating
     implementation. §1 keeps implementation in the parent.
   - Forking a *phase* moves reads, not returns, out of the parent. Whether that works as a context
     lever is exactly what #280 measures, and this note does not claim it is established.
2. **"Staging burden rises under a controller."**
   - Confirmed, and not avoided (§2.5). The burden moves into the review and accepting forks, which
     run the existing collect-apply-remove machinery on the main path.
   - The argument for accepting that is the 08-25 note's own: the machinery is hardened, and R2
     exercises it more heavily instead of inventing new invariants.
3. **"Shard first, then controller-ify."**
   - Done: sharding has shipped (`accepting`, `reviewing` and the `reference` units).

**R2 departs from the 08-25 note's framing, and it says so.** That note's sequencing ends with
"controller-ification as a separate change, sold on convergence (Finding 2), **not on context**"
(`context-architecture-refactor.md`, Sequencing item 4). R2 argues on context and on the gate
re-warm. So it is not the change that item anticipated: it is a new claim, and it needs a new
decision rather than a reading of the old one.

**D001 stands for what it decided** (the sharding increment, and its scope). D001 has no sequencing
list of its own; the sequencing above is the 08-25 note's.

## 10. Pre-registered falsifier for #280

This section is written before any data exists. The spike runs on #274's paired benchmark, with
**≥3 fixtures**, each replayed under both arms.

**The arms.** Both arms run on the same base engine version, the same `(model, effort)` stratum and
the same subagent roster.
- **Control:** the base engine.
- **Treatment:** the base engine plus the `planning`-fork diff and nothing else. Steps 3–4 run as a
  forked skill, and the controller is otherwise unchanged (§8).
- **Pinning:** both arms, and the fault-injection variants below, are pinned plugin directories
  **outside the payload**. That is #274's mechanism, and it is why the payload freeze does not block
  the spike. The fault variants are a **third and fourth pinned variant**, which #274's two-arm design
  does not supply, and #280 adds them.

**The primary measure is plan-gate parent context.** It is the prompt tokens (input + cache read +
cache write) of the **last parent turn before the plan-gate stop**, deduplicated by `message.id`.
- This note's §6 figures came from a scratch pass, not from #273's instrument, and #274's outcome is
  *peak* parent context. So **#280 owes a committed script** that computes this measure (or a
  `tree_cost.py` flag that does). It must be committed before the first run.
- Secondary measures, per fixture: turns per issue; whole-tree USD per issue; the #272 quality
  outcome; and the fail-safe checklist below.

**Fail-safe checklist, on every treatment fixture:**
- ACs copied verbatim into the plan;
- value framing present;
- the frozen `## Approach as reviewed` block present whenever the verdict says `architect: ran`;
- a `- Plan-gate:` line written by the controller;
- the plan gate stopped, with the scripted approval recorded.

**Two fault-injection runs,** treatment code only.

| run | what is injected | passes when |
|---|---|---|
| F1 | the fork's return is replaced with a malformed one | the controller writes a `- gate-error:` and stops |
| F2 | the architect runs, and the frozen block is deleted before the return | the controller writes `- Plan-gate: material (pre-image absent, architect ran) → STOPPED` |

Any other outcome of either run is a fail.

**Statistics.** A **paired reduction** is control minus treatment on the same fixture.
- *No reduction* means the median paired reduction is ≤ 0.
- X = 40k (§6.2).

**The outcomes are exhaustive and mutually exclusive.** Test them in this order and take the first
that holds.

1. **No-go (safety).** Any of:
   - a fail-safe item missing on any treatment fixture;
   - F1 or F2 failing;
   - any fork return the controller accepted that should have escalated.
   
   This is a no-go **whatever the cost result**.
2. **No-go (no effect).** The median paired reduction is ≤ 0.
3. **No-go (quality).** Any treatment fixture's #272 score is below the **worst** control fixture's.
4. **Inconclusive.** The paired reductions disagree in sign: at least one fixture has treatment ≥
   control, while the median is > 0.
5. **Not-go (sub-threshold).** Treatment < control on every fixture, but the median paired reduction
   is in (0, X). This is a real effect, too small for step 3 alone. It does not count against R2
   (§8).
6. **Go, or no-go on cost.** Treatment < control on every fixture, and the median paired reduction is
   ≥ X. The USD result then decides:
   - **Go** if median whole-tree USD did not rise;
   - **Go** if USD rose but the modeled plan-gate re-warm saving (§6.3, context reduction ×
     cache-write rate) exceeds the median USD increase **at both TTLs**;
   - **No-go (cost)** otherwise.

**Turns are reported for both arms and gate nothing.**

**A limit, stated in advance.** #274 answers the plan gate with a scripted approval, so no fixture
waits longer than a cache TTL. **The re-warm is therefore modeled, never observed:** parent context
at the stop × the cache-write rate. Appendix D is the one observed instance (n=1, vote, 0.3.1).

## 11. Proposed decision (unratified)

> **D0xx — R2 phase isolation is designed, not adopted; the #280 spike decides whether it proceeds.**
>
> **Decision.** Adopt this note's design as the target R2 shape:
> - a controller holding `SKILL.md`, the Gate and Routing tables, steps 0–2, both human gates, step
>   5's diff, steps 6–7 and 11–12, and the post-return checks;
> - three forked phases (`planning`, `reviewing`, `accepting`), each loading the core spans it acts
>   on;
> - one contract for those phases: a closed return schema, a required record set per phase, a single
>   writer per record, and a SHA-bound verdict.
>
> **No payload change until #280 returns go.** The spike's treatment and fault-injection variants are
> pinned plugin directories outside the payload, and the payload freeze holds until R1 branches,
> regardless of this decision.
>
> **The shared-invariant rule (§5) binds #35 only if #280 returns go.** On a no-go, #35 chooses homes
> for a single-context engine, where "state it once, point elsewhere" is safe because the pointer
> resolves in loaded text.
>
> **Not decided here:**
> - whether R2 proceeds;
> - the kernel's contents;
> - where the core spans live (§2.8);
> - whether the `in-review` Resume changes from replay to continue (§2.6);
> - the order of the review and accepting phases after the spike;
> - whether R2 lands before or after R1. #271 decides that on benchmark data, never on §6's SCOUTING
>   numbers.
>
> **D001** stands for what it decided. R2 is a new claim, argued on context and the re-warm (§9).
>
> **Erratum proposed on D018:** its premise sentence, "a forked phase ignores both spawn parameters",
> is partly superseded. Per current Claude Code docs, skill frontmatter `model:`/`effort:` set a
> fork's model and effort; only per-call parameters are unavailable to a fork. D018's conclusion is
> unchanged (§4, C7).

If ratified, this text is appended to `.claude/specs/decisions.md` as the next D-number, in the PR
that lands this note.

## 12. Open questions, disputes and deviations

**Disputed, for the owner** (this note's AC2 escalations):
1. **Where the core spans live under R2:** in the units, reversing #166, or in the kernel (§2.8).
   Recommendation: the units.
2. **Whether the `in-review` Resume changes from replay to continue** (§2.6).
   - Recommendation: continue, because a replay would re-run round 1 against a human's answer that was
     given to round 2's state.
   - Either way, the cap cannot reset.
3. **Whether §11 binds #35 to the §5 rule before #280 reports.** Recommendation: no, conditional on
   go, as §11 now reads.

**Open questions:**
1. **The shared kernel's size.** §5's rule decides what is in it, and nobody has drafted it. Its
   size, plus §2.8's answer, sets every fork's cold-load cost and so most of §6's range.
2. **Phase skills and the three-layer split.** A phase skill is a new artifact kind in the payload. It
   stays project-agnostic, because each fork reads `loop.config.md` by `CAPS` name, as the engine
   does. What would need to change:
   - a phase registry (in core's phase index, where the units' rows already are, or in `SKILL.md`;
     core is recommended, because the index is already guarded by `PhaseIndexIdentityTests`, which
     would extend to "each registered phase resolves to a skill that exists");
   - `CapsVocabularyTests` extending its scan to phase skills;
   - `/init-loop` needs nothing new unless a phase adds a `CAPS` name, and none here does.
3. **Phase-skill exposure.** A `context: fork` phase skill is a listed skill. A user or the model
   could invoke it outside the controller, which would bypass the SHA, record and currency checks.
   - A phase skill must refuse to run unless it is invoked with the controller's arguments (the
     ledger path, the issue and the base SHA), or another mechanism must stop a stray run.
   - **Not** `disable-model-invocation`: that would stop the controller invoking it too
     (`plugins/CLAUDE.md`).
4. **Compaction inside a fork.** A long review fork can compact. Smaller contexts should make that
   rare, and a fork that compacts re-reads its unit and spans, not the whole engine. Unmeasured.
5. **The `docs` route** (the 08-25 note's open question 5) may need no phases at all. It skips
   architect, security and mutation, so it could stay entirely in the controller.

**Deviations from the issue's scope list, recorded:**
- The issue's constraint "a backgrounded fork loses `Agent`" is **contradicted** by current docs
  (§4, C4). `background: false` is kept, for a different reason (C5).
- The issue's "set `subagentPromptCacheTtl: 1h` for phases that wait on a human" does not apply as
  written. A fork that needs the human returns before the wait (C8), so the wait is the
  controller's, and `promptCacheTtl` is the setting that matters (C9).
- §5 corrects the plan's "lives in the controller-loaded text" (recorded in §5).
