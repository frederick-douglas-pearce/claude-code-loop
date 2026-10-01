# Phase unit `reviewing` — step 8's procedure

This file is a **phase unit** of the dev-loop engine, not a standalone document. Core
(`loop-engine.md`) lists it in its phase index and has you read it at step 8, and before any
code-review round, whenever it runs. Read it in full, under core's load protocol. What holds when
it is not loaded is stated in core (*What holds without each unit loaded*), never here: its absence
never makes this gate pass and never lets it be skipped. This step's fail-safe half is in core
(step 8).

## Step 8 — the procedure

Run `CODE_REVIEW` on the diff.

`CODE_REVIEW` names a **procedure you run, not a command you call**. The default — and the pattern
that works in practice — is **parallel finder subagents over `git diff main...HEAD`, plus a pass
that confirms each finding**, journaled under the gate's name. (`main...HEAD` is the right form
*for round 1*: step 7 has committed and opened the PR, so the branch head **is** the change. A round
*after* the first reads a narrower range — see the scoping rule at the end of this unit. The
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

**The diff scope here is a limit on the finder, not the extent of the rule.** A finder reads a diff,
so a diff is all this check can reach; the authoring rule it enforces binds every surface you write
(step 6). Do not read a clean round as evidence about the ledger or the report — nothing read them.

**And give every finder the Verdict-first invariant** (Gates): findings on the whole diff first,
depth on any one of them after. A finder that exhausts itself on the first thing it notices returns
a partial reading of the change, which this gate cannot tell apart from a clean one.

**And the Relay invariant** (Gates): a finder must mark what it reproduced against what it inferred,
and you treat anything unmarked as unverified. A finder reasoning past the diff it was handed — about
a config, a test, or a file it was never shown — is making a claim, not reporting a finding, and it
reads identically on the page unless the prompt asked.

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
stop; the record is what keeps it honest instead. **The floor lens (core, step 8) is never the one dropped:
where another lens duplicates it, the other one goes.**

**No per-round lens *ceiling* is fixed here, deliberately** — only the floor (core, step 8). The corpus
establishes that lenses **duplicate**; it does not establish a number. **Duplication is what the
evidence shows; a count is what it does not.** Choosing one, or a per-route roster, is the
**review-tier matrix** question, which this step does not answer. **This step
deliberately mints no route-to-lens matrix and no fixed roster.**

**What the `guard-efficacy` lens asks.** *Do this change's guards assert the **mechanism** that would break, or only an
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
acceptance criteria, the standing authoring check, the Verdict-first invariant, the Relay invariant,
and the finding-class rule): **(1) Part 2's blockquote, verbatim** (kept in core: Gates →
Fresh-re-check invariant → *the mechanism blockquote*; no unit to load) — the worked example is
what makes the distinction operable; **(2) that it must not edit, break or execute anything to decide** — the
prohibition on improvising a mutation does not otherwise reach a finder; and **(3) that it must say
plainly when it cannot tell** — the rule making that a dirty answer lives here, where the finder
cannot see it, so an unprompted finder hedges and the gate reads clean. The Class B limit-case
re-checker's spawn prompt carries these for the same reasons. **Named by content, never by number**
— that recipe's items are numbered in another section.
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
| due when | the floor (core, step 8) says so | Part 2's three questions say so |
| records to | the round's roster record | `mutation-survivors=`, `- Restore:`, the `- AC-verify:` line |

**A surviving mutant is step 10's and only step 10's.** A read cannot establish one — which is why
this is a floor on *reading* and not a second mutation pass — and **neither gate's verdict discharges
the other's journal slot**: a step-8 `guard-efficacy` finding is never written to
`mutation-survivors=`, whose readings are fixed elsewhere and closed. A `guard-efficacy` finding
asserts a proposition about the tree, so **Floor 1 promotes it to BLOCKING** (it is the *test
efficacy* class named in the finding-class list in core, step 8), and it never reaches the editorial sweep.

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
owed the floor and whose roster does not name it produced no verdict (core, step 8), not a round excused
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
  is round 1's — core, step 8).
- **`roster: no verdict`** — the round produced none; a `- gate-fallback:` or `- gate-error:` line
  carries what happened (Gate-outcome invariant). **Never write lens entries beside it, including a
  `not due:` rendering.** This displaces the naming duty above rather than discharging it — and a
  round that landed here *because* it owed the floor and did not carry it (core, step 8) is the failure
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
element, and it is not repeated in the close record.** **Never the
`- Code-review:` element, and never the `code-review=` parenthetical** on the `- Budget:` line:
that parenthetical is per-iteration and label-only, while this is per-round and carries the
differential and the outcome. Collapsing either into the other loses that.

**"Finding class" and "result class" are different vocabularies and never mix.** A *finding class* is
BLOCKING or EDITORIAL, one per finding, and **only this gate's agents emit one** — its finders, and
the fresh re-checker of a later round (Gates → Fresh-re-check invariant). A *result class* is the
acceptance gate's Class A / Class B, one per result (step 10), and nothing there is ever BLOCKING or
EDITORIAL. Step 9 returns clean-or-findings and emits no class at all. **That is what makes every
EDITORIAL finding known by the close of this step** — not a survey of what the later gates happen to
return, but a rule about who may emit the class. The one exception is written out at the sweep below,
where a round re-armed from downstream reopens the question after the sweep has already run.

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

**The editorial sweep — one pass, contained, at the close of THIS step.** It **runs last** — after the round paragraphs and the round
bound in core (step 8).
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

*End of the `reviewing` unit.*
