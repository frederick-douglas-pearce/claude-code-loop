# Reconciliation B — invariants 3, 4, 5

Repo: `claude-code-loop`, read at `971f21c` (2026-10-26).
Files: `E` = `plugins/dev-loop/skills/dev-loop/loop-engine.md` (2535 lines, 200,789 B);
`S` = `.../SKILL.md`; `R` = `.../phases/reviewing.md`; `A` = `.../phases/accepting.md`.
Nothing was edited.

**Headline.** Unlike the plan-gate posture (F57/F58, which blocked #35), **these three invariants
have not drifted semantically.** Every site that states a trigger, a diff base, a spawn rule, a
cap, a journal spelling or an escalation target agrees with the canonical site. What the audit
found is (a) heavy redundancy — rationale restated at each site, and (b) **two sites that are
fail-open if read alone** and **one false cross-attribution**, all in invariant 3. Two couplings
are already pinned by tests (`CurrencyExemptionAgreementTests`, `FindingClassAgreementTests`,
`DeltaScopedRoundNotationTests`); the proposals below keep every anchor those tests use.

History, for the "most recent deliberate change" rulings (`git log -S`, whole-repo paths):

| phrase | introduced / last changed |
|---|---|
| `Currency — a verdict is bound to the commit it ran on` | `09a8478` 2026-08-14 (#33); carve-out polarity `bc42d3a` 2026-08-15 |
| `A source-changing fix here has no gate downstream` | `42769d9` 2026-08-13 (#31: cut the step-10 re-arm rule, default to escalation) |
| step 9's `This gate is no longer last` | `cd54bb2` 2026-08-13 (#31), pointer retained by `42769d9` |
| `Fresh-re-check invariant (a fix is never checked by its author)` | `8213294` 2026-08-07; findings closed `3653553` 2026-08-07 |
| step 6's `This borrows the *shape*` | `43a6cb4` 2026-08-09 |
| `there is no ladder` / BLOCKING-only "dirty" | `013ecd2` 2026-08-28 (#121) |
| `"Once" is literal` | `194dc68`→`fdeab62`→`07ce599` 2026-08-28/29; moved to the unit `fcb127a` 2026-09-30 (#166) |
| `A BLOCKING finding that raises a design question consults` | `919bae0` 2026-09-10 (#114); apparatus subtracted `dda837c`; ledger line cut `bf15770`; not-due settled `1bd4938` (all 2026-09-10) |
| `<reviewed>..HEAD` scoping | `6cbebc3` 2026-08-27 (#120) |

Decision log: D012 (the scope ruling is the new gate that made 0.3.0 a minor bump); D017 (the
≥20% core-footprint floor — every byte below is in addition to it). No decision entry governs
currency, fresh re-check or rounds directly; the rulings below rest on commits, tests and the
fail-safe posture.

---

## Invariant 3 — the currency clause

### 3.1 Sites, verbatim (trimmed to the operative sentences)

**E L878–886 (step 9)**
> L878 **This gate is no longer last, so "run it once, at dev-complete" is no longer a safe reading.** Step 10 can produce code … and that code lands *downstream* of this gate.
> L880 Re-evaluate this trigger against any acceptance-gate fix before step 11: if such a fix touches a sensitive surface it has not been security-reviewed, so it **escalates at the merge gate under the existing "touched security surface" always-escalate condition** (step 11) — the earlier clean verdict does not cover it.
> L883 This is one instance of the general rule; **which gates a post-gate change re-arms, and from which sources, is the Gate-outcome invariant's currency clause** (under Gates).

**E L895–911 (step 10)**
> L895 **A source-changing fix here has no gate downstream of it.** Steps 8 and 9 already ran against a head that did not contain this code, so a Class A fix that **adds or changes source** … has been reviewed by nobody. **Finish this gate first — commit the fix and run its re-verify — then escalate to the human before step 11.**
> L899 … **do not merge on the earlier verdicts** — a gate that never saw a change has not passed it (Gate-outcome invariant). A fix that changes **no** source — a citation, a doc line — re-arms nothing and needs no escalation. (A test-only change is **not** sourceless: it re-arms step 6's hermetic trigger — see step 6.)
> L902 **A source-changing fix is not routed back through review or security: it escalates, and that is the rule, not a fail-safe default awaiting a better one.** A re-arm would need three things this gate cannot supply: [ordering / round / status bullets, L905–910]. L911 The human is the path because the human is the only actor outside those three constraints.

**E L961–965 (step 11)**
> L961 … and CI + security + acceptance are green **on the commit you are about to merge** — this gate is itself a source of change, and it is the one step with nothing downstream to catch a stale verdict (Gate-outcome invariant → currency) — AND the row is not `hold`:

**E L1512–1517 (Ledger format, `- Code-review:`)**
> L1512 The **`- Code-review:`** line names **the commit range each round read**, one element per round … It is what lets a later reader tell **what a verdict covers** — the question the currency clause turns on and the thing a merge gate has to weigh. **It is a record for a reader, not a store a later step parses** … a round that no longer holds one runs full (step 8), so nothing reads this line back.

**E L2208–2262 (Gates — the canonical clause)**
> L2208 **Currency — a verdict is bound to the commit it ran on.** … the gate ran, returned clean, and then **the merge candidate changed underneath it**. A later commit is a commit no gate ran on, so the earlier verdict does not reach it. … The clause binds every gate above **whose verdict is about a diff or a commit** — the build commands, code review, security, AC-verify, and the merge gate's own precondition. The plan, architect and human-plan gates certify an *approach*, not a commit; carrying those across a resume is Resume's rule, not this one.
> L2218 **The remedy, before the detail: re-run the re-armed gate, or STOP and escalate to the human. Never journal or merge on the superseded verdict.** Where the gate's own step states what a re-run costs, follow it; **where no step states one, escalate — an unowned re-arm is escalated, never absorbed.** A step-9 fix re-arming code review is *owned*: step 8 states its cost, so it is re-checked under **step 8's own round budget** by a fresh checker … **A budget already spent does not make it owned anyway** … Ownership is a live round, not a step that once had one … Escalation is for a re-arm no step owns — at the acceptance gate, every source-changing fix, per step 10's three constraints. And **commit the change first** … **detecting is not certifying** (step 8).
> L2232 **It holds whatever produced the change** … treat the list as **sufficient, not exhaustive** … : a fix the **acceptance gate itself** made (step 10); a **CI fix** after a gate has run; a change the **human asked for at the merge gate** (step 11); **bringing the branch up to date with its base** … re-arms every gate that reads the **tree** rather than the diff — CI **and** the build commands … If you cannot tell what the update touched, re-arm.
> L2243 **Review and security fixes (steps 8 and 9) do not re-arm the *acceptance* gate** … **They still re-arm gates that ran before them**, and two cases are live: a test added at step 8 re-arms step 6's hermetic trigger, and a step-9 security fix commits under step 8's rule, so it lands after code review certified the head.
> L2250 **Scope it by what the change touches.** A change touching neither source nor tests — a citation, a doc line — re-arms nothing, the same line step 10 already draws for its own fixes. A **test-only** change is not in that set … **if you cannot decide whether a change alters source, it does; re-arm.**
> L2255 **When the pipeline cannot re-run a re-armed gate, the human's disposition is what releases the row — and it is not a pass.** … Record it in the row's Notes and in `progress.md` as a **human decision**, naming the gate and the commit its verdict does not cover — **never on a `- gate-fallback:` line** … **A human deciding to merge is not a gate certifying the code.**

**S L110–116 (SKILL.md fail-safe bullet)**
> L110 **A verdict is bound to the commit it ran on:** if the merge candidate changed after a gate certified it — a fix at the acceptance gate, a CI fix, a change asked for at the merge gate, or bringing the branch up to date — that gate has not passed the candidate. **Escalate, or re-run what the engine says that change re-armed** — and if you cannot determine which gates it re-armed, which you cannot without `loop-engine.md` loaded, that is the escalate branch, never the nothing-was-re-armed branch. Never merge on a verdict describing an earlier tree.

**R L389–401 (reviewing unit, scoping passage)**
> L389 **Currency is preserved, and a scoped round is not a substitute for a full one.** A later round runs on `HEAD` and certifies `HEAD` … **the delta bounds what it re-certifies, never whether it certifies.** Every commit in `main...HEAD` was read by the round whose range contains it … So no verdict is carried onto a commit no round ran on. **What scoping narrows is stated** … a fix's correctness can turn on earlier-read code … and a finding round 1 *declined* leaves no trace in the delta … **A round certifies `HEAD` whatever the delta holds** — carrying a prior verdict forward *instead of* running a round, **on a docs-only delta or any other**, is a different proposal and is not licensed here.

Secondary sites that cite the clause rather than restate it (keep, all pointers): R L295–301 (the
sweep's touched set is a *subset* of the clause's exemption); R L313–318 (*"Once" is literal* —
see Δ3.1 below, this one is a false attribution); R L352–360 (which re-arms are owned "is the
currency clause to decide — read it there and do not paraphrase"); README L514–521 (trust model,
by its own standing rule in root `CLAUDE.md`).

### 3.2 Semantic deltas

| # | Sites | Axis | What differs | Would the orchestrator act differently? | Test pinning it |
|---|---|---|---|---|---|
| Δ3.1 | R L313–315 vs E L2235–2241 | re-arm **sources** | R lists {step-9 fix, CI fix, human-asked change, step-10 fix} and calls it *"the currency clause's own"*; E's bullet list is {step-10 fix, CI fix, human-asked change, **branch update**}, with the step-9 fix in the *next* paragraph as a code-review re-arm | **No** — both are default-deny ("sufficient, not exhaustive"), so an unlisted source re-arms under either. But the attribution is false as written: R names a list E does not contain | none |
| Δ3.2 | S L110 vs E L2213–2216 | **which gates** the clause binds | E: only gates whose verdict is about a diff/commit (plan, architect, human-plan excluded — Resume's rule); S: "that gate" — any | Only under partial load, and in the over-gating direction (a plan gate would be treated as re-armed). Safe by SKILL.md's design | none |
| Δ3.3 | E L880–883 (step 9) vs E L895–911 (step 10) / E L2226 | **trigger and escalation locus** for a step-10 fix | step 9: *sensitive-surface* fix → "escalates **at the merge gate** under step 11's touched-security-surface condition"; step 10 / clause: **every** source-changing fix → "escalate to the human **before step 11**" | **Not in execution** — step 10 runs before 11 and fires first. **Read alone, step 9 is fail-open**: a non-sensitive source-changing step-10 fix would reach step 11 with no always-escalate condition and, under `escalation-only` on a graduated route, auto-merge. Step 9's "one instance of the general rule" sentence is what keeps it subordinate | none |
| Δ3.4 | E L900–902 (step 10) vs E L2252–2253 | the exemption's **catch-all** | clause: "if you cannot decide whether a change alters source, it does; re-arm"; step 10: no catch-all | **Read alone, step 10 is fail-open** on an undecidable fix (e.g. a generated file, a fixture). In practice the clause is in the same file and step 10 cites the Gate-outcome invariant | `CurrencyExemptionAgreementTests` pins the *list* (`a citation, a doc line`) in both regions and that neither names a test — not the catch-all (docstring: polarity is review's) |
| Δ3.5 | R L399–401 vs E L2250–2251 | **docs-only change after review** | E: a doc-line change re-arms nothing (no round owed); R: carrying a verdict forward "on a docs-only delta or any other … is not licensed **here**" | No conflict once *here* is read as "the scoping rule": R denies that *scoping* grants the exemption, E grants it on its own terms. But a reader of R alone would run a round E says is not owed — over-gating, one wasted round | `DeltaScopedRoundNotationTests` names this paragraph only as a hazard to its region boundary (comment L2578–2584); it does not pin its content |
| Δ3.6 | E L2221–2225 vs R L352–356 | **owned vs unowned** re-arm | identical: owned iff the step states a cost *and a round is live*; R defers explicitly | No | none |
| Δ3.7 | E L961–965, S L116, README L514 | merge precondition | all: never merge on a verdict for an earlier tree | No | none |
| Δ3.8 | E L2255–2262 vs step 10, S, R | **journal line** for a human-disposed re-arm | only the clause states one, and loosely ("Notes and `progress.md` as a human decision, naming the gate and the commit … never `- gate-fallback:`") | No — no competing spelling exists. (Observation: there is no fixed spelling at all; not a drift) | none |

Observation, not a delta: no site says what a **post-step-10 CI fix** re-arms at the acceptance
gate. The clause's default ("no step states a cost ⇒ escalate") covers it; worth one clause in the
canonical ("a change after the acceptance verdict is unowned").

### 3.3 Rulings

- **Δ3.1 — E wins.** `09a8478` wrote the clause's list and its *sufficient, not exhaustive* posture;
  R's sentence (`fcb127a`, the #166 extraction) paraphrased it and mis-attributed. Fix: R points at
  the clause instead of naming members. No behavior change.
- **Δ3.2 — keep S as is.** SKILL.md's bullets exist to over-gate under partial load (root
  `CLAUDE.md`, "a partial load over-escalates"). The over-coverage is the design.
- **Δ3.3 — step 10 / clause win.** `42769d9` (#31) made "escalate, it is the rule" the step-10
  posture and retained step 9's text only as a pointer to step 11's *real* condition; `09a8478`
  (#33) then subordinated it ("one instance of the general rule"). Step 9's locus wording
  ("escalates at the merge gate") predates both. Fail-safe posture also decides it: step 10's
  rule covers every source-changing fix; step 9's covers a subset. Keep one operative instruction
  from step 9 — *re-evaluate this gate's trigger against a step-10 fix so the escalation names the
  gate it re-armed* — because the clause's human-decision record requires "naming the gate".
- **Δ3.4 — clause wins.** `bc42d3a` (#33, 2026-08-15) is the most recent deliberate change and
  its subject is literally "pin the carve-out's polarity"; unknown ⇒ unsafe. Carry the catch-all
  into step 10 as one clause (the test region tolerates it: `_LIST_RE` extracts only the list).
- **Δ3.5 — clause wins.** The exemption is the clause's (R L296–297 itself says the sweep's set is
  a *subset* of "the currency clause's existing exemption"). Delete R's example phrase "on a
  docs-only delta or any other"; keep the sentence's point (scoping licenses no carry-forward).
- Δ3.6–3.8 — no ruling needed.

### 3.4 Canonical passage (E, Gates → Gate-outcome invariant; replaces L2208–2262) — 25 lines

```
**Currency — a verdict is bound to the commit it ran on.** A gate that ran clean and then saw the
merge candidate change underneath it has not passed the candidate: a later commit is a commit no
gate ran on. It binds every gate above whose verdict is about a diff or a commit — the build
commands, code review, security, AC-verify, and the merge gate's own precondition; the plan,
architect and human-plan gates certify an *approach*, and carrying those across a resume is
Resume's rule. **Remedy: re-run the re-armed gate, or STOP and escalate. Never journal or merge on
the superseded verdict.** A re-arm is *owned* only where the gate's step states a re-run's cost
**and a round is still live** — a step-9 fix re-arming code review is owned by step 8's budget
(round 2, a fresh checker; Fresh-re-check invariant below) while a round remains, and unowned once
both are spent. **An unowned re-arm escalates, never absorbs**: every source-changing fix at the
acceptance gate (step 10's three constraints), and any change after the acceptance verdict. Commit
the change first (step 6's staging rule): detecting an uncommitted fix is not certifying it.
**It holds whatever produced the change.** Known sources — **sufficient, not exhaustive**; an
unlisted source is not exempt: a fix the acceptance gate made (step 10); a CI fix after a gate ran;
a change the human asked for at the merge gate (step 11); bringing the branch up to date with its
base, which re-arms every gate that reads the **tree** — CI and the build commands — and, if you
cannot tell what it touched, everything. Review and security fixes (steps 8, 9) do not re-arm the
acceptance gate, which runs downstream of them; they do re-arm gates that ran before them — a test
added at step 8 re-arms step 6's hermetic trigger, and a step-9 fix lands after code review
certified the head. **Scope a re-arm by what the change touches.** A change touching neither source
nor tests — a citation, a doc line — re-arms nothing, the same line step 10 already draws for its
own fixes; a test-only change is not in that set (step 6); **if you cannot decide whether a change
alters source, it does — re-arm.** Where the pipeline cannot re-run a re-armed gate, the human's
disposition releases the row **and is not a pass**: record it in Notes and `progress.md` as a human
decision naming the gate and the commit its verdict does not cover — never on `- gate-fallback:`.
```

Test constraints honored: start anchor `**Currency — a verdict is bound to the commit it ran on.**`
unchanged; the region must still end at the literal `**Fresh-re-check invariant` (the canonical
writes "Fresh-re-check invariant below" *without* a leading `**`); `_LIST_RE` still extracts
`a citation, a doc line` as the first `— a … — re-arms nothing` match (no earlier `— a …` run in the
passage is followed by `— re-arms nothing`).

### 3.5 Other sites — pointer or keep

| Site | Disposition | Replacement / reason |
|---|---|---|
| E L878–886 (step 9) | **pointer** | `**This gate is no longer last.** A step-10 fix lands downstream of it; which gates such a fix re-arms is the currency clause (Gates), and step 10 escalates every source-changing one. Re-evaluate this gate's trigger against that fix so the escalation names the gate it re-armed.` |
| E L895–911 (step 10) | **keep, trimmed** | The three constraints are *cited* by the clause and by R, so they stay here. Cut L899–900 ("do not merge on the earlier verdicts … (Gate-outcome invariant)") and L902–904's "and that is the rule, not a fail-safe default awaiting a better one" — both restate the clause. **Add** after the parenthetical at L902: `If you cannot decide whether a fix alters source, it does (Gates → currency).` The list `a citation, a doc line` must stay byte-identical to the clause's (test). |
| E L961–965 (step 11) | **keep** | It is the merge gate's own precondition, one clause, and the one site with nothing downstream. |
| E L1512–1517 (ledger) | **keep** | Format spec; the cross-reference is one phrase. `DeltaScopedRoundNotationTests` anchors this paragraph. |
| S L110–116 | **keep** | By design (partial-load fail-safe). Already a faithful abbreviation. |
| R L389–401 | **keep, trimmed** | Keep L389–393 (the per-round certification argument is the scoping rule's own, not a restatement) and L394–398 (the two things scoping narrows — cited by the Gates recipe). Replace L399–401 with: `Carrying a prior verdict forward instead of running a round is the currency clause's question (Gates), never this rule's.` |
| R L313–315 | **pointer** | Replace "a step-9 security fix … a step-10 fix — and that list is the currency clause's own, which is **sufficient, not exhaustive** (Gates → currency)" with `— from any source the currency clause names, and from any it does not (Gates → currency: sufficient, not exhaustive)`. |

### 3.6 Bytes

| Site | now | after | saved |
|---|---|---|---|
| E L2208–2262 → canonical | 4,468 | ~2,600 | ~1,850 |
| E L878–886 → pointer | 716 | ~330 | ~390 |
| E L895–911 trim + catch-all | 1,615 | ~1,250 | ~365 |
| R L389–401 trim | 1,223 | ~650 | ~570 |
| R L313–315 pointer | (of 1,353) | | ~150 |
| **Invariant 3** | | | **≈ 3,300 B** |

---

## Invariant 4 — the fresh re-check

### 4.1 Sites, verbatim (trimmed)

**E L537–554 (step 6, hermetic fix read-check)**
> L537 Whether the fix **preserved what the test asserts** is not an exit status, and you are the one reader who cannot judge it: you wrote the fix. Send that question to a **fresh instance** — a new spawn, not you and not whoever wrote the test. **Its prompt carries five things** … the test as it now stands; the behavior the test covered before; that it must decide by **reading**, never by running or altering anything; that it must **say plainly when it cannot tell — which is a dirty answer, not a clean one**; and the **Verdict-first invariant** … Withhold your conclusions.
> L547 This borrows the *shape* of the Fresh-re-check invariant without being governed by it: that invariant covers the two gates carrying a round cap (step 8 and step 10), and this gate carries none — it blocks until green … So there is no round to count and no cap to consume. **If the fresh read comes back dirty, or cannot tell, escalate to the human and STOP** — do not absorb it, and do not fix-and-re-ask in a loop.

**E L757–772 (step 8)**
> L757 Then **commit the BLOCKING fixes** and **verify recs were applied — by a fresh checker, never by yourself.** If you *delegated* any fix, that agent wrote to its own copy … directing a fix is authorship … This is the Fresh-re-check invariant's sharpest instance (see Gates): you wrote the fixes, so confirming them yourself is the author agreeing with himself, not a gate. **Commit before spawning it** — the checker reads a diff ending at `HEAD`, so an uncommitted fix is invisible to it. … Spawn **one lighter checker** — its inputs are fixed under Gates (Fresh-re-check invariant → the code-review bullet) and are not restated here … Bounded to 2 rounds (round 1 being the review itself, that re-check being round 2) — contested findings, and **any BLOCKING finding** the re-check returns, whether one round 1 raised or one only the fix introduced, escalate to the human, do not loop.

**E L1672–1674 (Budget line, `gate-rounds`)**
> a round can consume zero subagents (a review done in the parent thread — never a capped gate's round 2, which the Fresh-re-check invariant requires be a spawn) …

**E L2121 / L2124 (Gate table rows)**
> Code review | … **the fix's re-check a fresh checker, not you** (Fresh-re-check invariant) …
> AC-verify | fresh subagent (+`VERIFY`); **any re-check a fresh instance too** (Fresh-re-check invariant) …

**E L2264–2283 (Gates — the invariant's headline)**
> L2264 **Fresh-re-check invariant (a fix is never checked by its author).** Applies to the two gates that carry a round cap … the **acceptance gate** (step 10, *both* result classes) and **code review** (step 8). When a gate comes back dirty and you fix what it found, the re-check is performed by a **fresh instance**. You wrote the fix, so you are the one reader who cannot check it … **You are an author of every fix made in this iteration, including one you delegated** …
> L2274 **Read this as a rule about round *two*, and about three clauses** … **Step 8's "verify recs were applied" is the sharpest hole it closes** … **A re-check must not collapse into the parent thread** … **Nor into the round-1 agent re-contacted.** … **"Fresh" means a new spawn**, every time.

**E L2284–2382 (What the fresh checker receives — per-gate recipes; the only copy)**
> L2284 In every case it gets **none of your conclusions about whether the fix worked** … Class A — re-run Part 1's recipe unchanged … Class B — … **do the new test's assertions pin the *mechanism*** … **if it cannot tell, that is a dirty result** … five things [blockquote verbatim; no edit/break/execute; say when cannot tell; Verdict-first; Relay] … (a surviving-mutant re-check re-runs the harness; that re-run is a fresh instance too) … Code review — the previous round's findings *and its declines*, **`git diff <reviewed>..HEAD`**, one narrowed question … **One lighter checker** … the checker may **contest a decline**.

**E L2383–2392 (the bound)**
> L2383 **The bound — one fresh re-check, then escalate; there is no ladder.** The fresh re-check **is** round 2 of the 2-round cap each gate already carries, never a round on top of it. If round 2 comes back dirty — **whether it is a finding round 1 raised or one only the fix introduced** — escalate to the human; there is no round 3. **At code review, "dirty" means a BLOCKING finding**: an EDITORIAL one raised before step 8's sweep joins it … **A round that runs after that sweep** … every finding it returns escalates whatever its class. … **The acceptance gate has no finding class at all** — either of its two *result* classes is dirty, and neither may be swept.

**E L2418–2426 (journalling, rationale)**
> L2418 A fresh re-check is a distinct subagent invocation, so it increments `subagent-runs` … **A journal recording a re-check while `subagent-runs` did not move records a re-check that did not happen** … L2423 **Why "be more careful" is not the remedy.** … The belief that produced it is what writes the fix. Vigilance is not a control.

**S L123–126**
> **A fix for a gate finding is re-checked by a fresh instance, never by its author.** After you fix what a gate found, the re-check is a **new spawn** — not you re-reading your own diff, and not the round-1 agent re-contacted. If the fresh re-check is still dirty, **escalate to the human** rather than iterating.

**R L305–321 (*"Once" is literal*)**
> L308 > **Before the sweep has run**, an EDITORIAL finding joins it: it re-arms nothing and escalates nothing. **After the sweep has run, there is no sweep left** — so **every** finding a later round returns, of **either** class, **escalates with the re-arm**. There is never a second sweep.
> L317 **Whatever re-armed it, a round that runs after the sweep does not sweep.**

**R L87–142 (`guard-efficacy` lens — borrows the Class B discipline)**
> L88 That question is the Class B limit-case re-checker's (Gates → Fresh-re-check invariant), and its answering discipline governs here too: the lens decides by **reading** … and **"cannot tell" is a dirty answer** — at this gate a BLOCKING finding, never a no-verdict. … L99 **What its prompt must carry** … **(1) Part 2's blockquote, verbatim** … **(2) that it must not edit, break or execute anything** … **(3) that it must say plainly when it cannot tell** … **Named by content, never by number** … L109 What does **not** carry over is that recipe's antecedent … this lens has no prior finding and no fix in hand.

**R L323–360 (scoping)**
> L323 **Round 1 reads the whole change; every round after it reads only what has changed since the last round read.** What ***this gate's*** re-check requires is a fresh **instance** — it does not additionally require re-ingesting material a prior round has already reported on. … the acceptance gate's Class A re-check deliberately *does* re-run its whole recipe from scratch, and Gates forbids relaxing it. … L340 **A later round reads `<reviewed>..HEAD`**, plus the previous round's findings **and the ones it declined**, and one narrowed question. Its full input recipe is under Gates … **do not restate it here.** … L359 **Where no anchor is available or trustworthy, the round is FULL.**

**A L16–24 (step 10 procedure)**
> If gaps, fix and re-verify **once**: round 1 was the gate's own first run, so that re-verify is **round 2 of this gate's 2-round cap**, and if it comes back dirty, escalate. **The re-verify is a fresh instance, never the author of the fix** (Fresh-re-check invariant, under Gates: a new spawn, not you and not the round-1 agent re-contacted). **"Gaps" means a finding of either class**.

**A L479–491 (Class B)**
> **A Class B finding is not merely recorded — it blocks** … Strengthen the guard … and re-verify, within the same 2-round cap; past that, escalate. **That re-verify is a fresh instance, never the author of the strengthened guard** (Fresh-re-check invariant, under Gates) — this leg needs saying separately because it is the one place a *guard* is what got fixed …

### 4.2 Semantic deltas

| # | Sites | Axis | What differs | Would the orchestrator act differently? | Test pinning it |
|---|---|---|---|---|---|
| Δ4.1 | E L2264–2266 & L547–549 vs S L123 | **scope** of the invariant | Gates: "the two gates that carry a round cap"; step 6: "borrows the *shape* … without being governed by it"; S: "a gate finding" — any gate | **No.** Step 6 re-implements every operative clause itself (new spawn, withhold conclusions, cannot-tell ⇒ dirty, dirty ⇒ escalate + STOP, no loop). S's wider form over-gates only where a gate returns a *judgment* — exactly steps 6, 8, 10. The sole content of "not governed" is *no round to count, no cap to consume* | none |
| Δ4.2 | E L2279–2282 / S L124 / A L21 vs E L538 vs A L481 | **who is excluded** | "not you, not the round-1 agent re-contacted" vs "not you and not whoever wrote the test" (step 6) vs "never the author of the strengthened guard" (Class B) | **No** — "fresh means a new spawn" subsumes all three. The lists differ because the gates have different prior actors | none |
| Δ4.3 | E L542, L2298, R L90 vs E L2287–2291 (Class A), L2348–2367 (code review) | **cannot tell ⇒ dirty** | stated at step 6, Class B, and the lens; not stated for the Class A re-check or the code-review checker | **No concrete divergence**: code review has "unclassified, unrecognised, or ambiguous ⇒ BLOCKING" (E L746, L2360); Class A re-runs Part 1 "unchanged", whose verdict is met-only-with-`file:line` (A L118). Worth stating once, gate-agnostically | none |
| Δ4.4 | E L770–772 vs E L2383–2386 | **"contested" findings** | step 8 lists "contested findings, and any BLOCKING finding" as escalating; the bound names only BLOCKING | No — E L2373–2374: a contested decline "is a finding like any other, and it counts against this round" | `FindingClassAgreementTests` (class tokens in both regions must agree — they do) |
| Δ4.5 | E L2351, R L340, E L763 | **diff base** for the code-review re-check | `git diff <reviewed>..HEAD` (Gates, unit); "a diff ending at `HEAD`" (step 8) | No | `DeltaScopedRoundNotationTests` (three engine regions + ledger spelling `<sha>..<head>`) |
| Δ4.6 | A L18, A L481, E L770, E L2384, S L125, README L639 | **cap** | 2 everywhere ("once" / "no ladder" / "one re-check") | No. Cap numeral deliberately unpinned (`FindingClassAgreementTests` docstring, #114 note) | — |
| Δ4.7 | E L1672–1674 | zero-subagent round | "a review done in the parent thread" is allowed as *a* round, "never a capped gate's round 2" | No — step 8's round 1 is spawned finders by procedure; this is the counter's semantics | none |
| Δ4.8 | E L2287–2291 vs R L323–330 | **Class A re-check scope** | Class A re-runs Part 1 unchanged; code review re-reads only the delta; R states the asymmetry and that Gates forbids relaxing it | No — deliberate asymmetry, stated at both | none |
| Δ4.9 | E L2418–2421 vs others | **journalling** | only Gates states "increments `subagent-runs`"; step 8 writes a `- Code-review:` element per round; step 10 its own line and slots | No competing spelling | none |

Observation (outside this invariant's three): a round 2 that falls back to FULL (R L359, L362–380)
is still "one lighter checker" (E L724–726, L2363) and carries no `guard-efficacy` floor — so a
full round 2 reads the whole diff with no lens roster. Not a drift between restatements; noted for
the parent.

### 4.3 Rulings

- **Δ4.1 — state the principle once, gate-agnostically, with the round accounting as a sub-clause.**
  The rationale ("you wrote the fix, so you are the one reader who cannot check it", `8213294`) is
  true at any gate and is already applied at three. `43a6cb4`'s "not governed" carved step 6 out
  only to avoid counting a round there; the canonical below keeps that carve-out as a sentence
  ("step 6's check carries no round and no cap"). Zero behavior change. Fallback if the parent
  prefers not to touch `43a6cb4`'s wording: keep step 6 outside and keep its pointer — the savings
  drop by ~450 B, nothing else moves.
- **Δ4.2 — name the union once** ("not you; not the round-1 agent or the finding's raiser; not any
  agent that wrote or directed the fix or the test"). Each site's partial list becomes a pointer.
- **Δ4.3 — generalize "cannot tell ⇒ dirty" in the canonical.** Unknown ⇒ unsafe; it is already the
  rule at every site that states one, and the two silent sites reach the same answer by another
  route. No behavior change; closes a read-alone gap in the Class A and code-review bullets.
- Δ4.4–4.9 — no ruling needed.

### 4.4 Canonical passage (E, Gates; replaces L2264–2283 + L2383–2392 + L2418–2426) — 25 lines

The per-gate recipes (L2284–2382) stay between the two halves, unchanged: `DeltaScopedRoundNotationTests`
anchors the code-review recipe's end at `**The bound — one fresh re-check`, and
`FindingClassAgreementTests` anchors the bound's region from that string to `**Reaching a cap is a handoff`.

```
**Fresh-re-check invariant (a fix is never checked by its author).** Wherever this engine re-checks
a fix by *reading* rather than by exit status — code review (step 8), the acceptance gate (step 10,
both result classes), and step 6's hermetic read-check — the re-check is a **fresh instance: a new
spawn, every time.** Not you re-reading your own diff; not the round-1 agent, or the finding's
raiser, re-contacted; not any agent that wrote or directed the fix or the test. You are an author
of every fix made in this iteration, including one you delegated — directing a fix is authorship,
so handing the writing to a subagent and reading it yourself satisfies nothing. The belief that
produced the defect is still present while the fix is written; the remedy is a different checker,
never a more careful one. **Inputs:** the checker gets **none of your conclusions about whether the
fix worked**; what else it gets is fixed per gate below (step 6 fixes its own). Commit the fix
before spawning — a checker reads a diff ending at `HEAD`, so an uncommitted fix is invisible to
it. **A checker that cannot tell has returned dirty, not clean** — write that into its prompt,
where it cannot otherwise see it; an unprompted checker hedges, and a hedge read as agreement is
how this gate goes soft.
[… per-gate recipes, unchanged …]
**The bound — one fresh re-check, then escalate; there is no ladder.** At steps 8 and 10 the
re-check **is** round 2 of the gate's 2-round cap, never a round on top of it; step 6's check
carries no round and no cap — it blocks, so a dirty read escalates and STOPs. If round 2 comes back
dirty — a finding round 1 raised or one only the fix introduced — escalate to the human; there is
no round 3. **At code review, "dirty" means a BLOCKING finding**: an EDITORIAL one raised before
step 8's sweep joins it, re-arms nothing and escalates nothing; a round that runs after the sweep
escalates every finding whatever its class (step 8's *"Once" is literal* rule). **The acceptance
gate has no finding class** — either result class is dirty, and neither may be swept. A fresh
re-check is a subagent invocation and increments `subagent-runs`; a journal recording a re-check
while `subagent-runs` did not move records one that did not happen. Cost: one extra subagent per
dirty class per iteration — two at step 10 when both classes are dirty.
```

(Two blocks of 14 + 11 lines around the unchanged recipes.) The scope-ruling paragraph (L2393–2399)
and *Reaching a cap is a handoff* (L2401–2412) follow as today.

### 4.5 Other sites — pointer or keep

| Site | Disposition | Replacement / reason |
|---|---|---|
| E L537–546 (step 6, the five inputs) | **keep** | Only copy of this check's inputs. |
| E L547–553 (step 6, "borrows the shape") | **pointer** | `Governed by the Fresh-re-check invariant (Gates) in its no-round form: dirty or cannot-tell ⇒ escalate to the human and STOP; never fix-and-re-ask.` Keep L555–559 (the re-arm paragraph; `MutationNaReasonTests`/step-6 tests anchor `**A test added later re-arms the trigger.**`). |
| E L757–772 (step 8) | **keep, trimmed** | Keep: commit-before-spawn, delegated-fix staging (tree-isolation's), "one lighter checker — inputs under Gates", the bound sentence (`FindingClassAgreementTests` start anchor ` rounds (round 1 being the review` and its class tokens must stay). Cut L761–763 "This is the Fresh-re-check invariant's sharpest instance … not a gate" (restated at the canonical) and L764–767's F15 comparison down to `(hence the empty-delta fallback in the reviewing unit)`. |
| E L1672–1674 | **keep** | Budget-counter semantics; one parenthetical. |
| E L2121, L2124 | **keep** | Gate-table rows; already pointers. |
| S L123–126 | **keep** | By design. |
| R L305–321 | **keep** | This is the *canonical* post-sweep ordering rule (`fdeab62`: "state the post-sweep rule once, and point at it the same way everywhere"); six sites point here. Only the attribution sentence changes (Inv 3, Δ3.1). |
| R L87–142 | **keep** | Lens spec; borrows by content, as its "named by content, never by number" sentence requires. Not a restatement. |
| R L323–360 | **keep** | Scoping rule, pinned by `DeltaScopedRoundNotationTests`; it already defers the recipe ("do not restate it here" — the model pointer). |
| A L16–24 | **keep, trimmed** | Replace the parenthetical at L20–22 with `(Fresh-re-check invariant, Gates)`. |
| A L479–491 | **keep, trimmed** | Replace L481–484 ("That re-verify is a fresh instance … precisely the defect Class B exists to catch") with `That re-verify is a fresh instance (Fresh-re-check invariant, Gates); the strengthened guard's author is the one reader it excludes.` |

### 4.6 Bytes

| Site | now | after | saved |
|---|---|---|---|
| E L2264–2283 + L2383–2392 + L2418–2426 → canonical | 3,130 | ~2,450 | ~680 |
| E L547–553 → pointer | ~700 | ~250 | ~450 |
| E L757–772 trim | 1,478 | ~1,100 | ~380 |
| A L16–24 trim | 619 | ~520 | ~100 |
| A L479–491 trim | 1,034 | ~750 | ~280 |
| **Invariant 4** | | | **≈ 1,900 B** |

---

## Invariant 5 — the scope-ruling stop

### 5.1 Sites, verbatim (trimmed)

**E L749–751 (step 8, the implement sentence)**
> **Implement viable BLOCKING findings** — **except one raising a design question, which stops for the human before any fix for it is applied (below)** — act on that stop before acting on this sentence.

**E L778–837 (step 8 — canonical)**
> L778 **A BLOCKING finding that raises a design question consults `DESIGN_AGENT` and carries its own stop.** Those are one trigger, not two.
> L783 **Trigger.** A **BLOCKING** finding raising a design question — whether the approach is right, whether a fix belongs in this change at all, or whether several findings share one root cause. **Default-deny: if you cannot tell whether a finding raises a design question, it does.**
> L786 **Effect, both halves together.** Consult `DESIGN_AGENT` for a **scope ruling** *and* **STOP for the human with it**, under every `mode:` value, **on every route**, **at whatever round the finding arises**. It is **not gated on the cap** … Route graduation does not reach it either.
> L791 **The moment is when the finding is returned** — *before* any fix for it is applied, before the fix commit, and before the next round is spawned.
> L797 **What the ruling returns**, verdict-first — state this at the invoke site …: the findings classified by severity, a **minimal fix set** that would clear the gate, and every deferral named with its reason. L800 **What it may never return** … it may **narrow** the work and may **never** conclude that no human decision is required. It cannot clear a finding and it cannot certify the gate.
> L803 **A deferral is never silent, and it is not a new disposition.** A finding the ruling defers **is a decline** … record it in the round's gate-decision block **as deferred by the ruling** … Where a deferral outlives the iteration it is **surfaced to the human at the stop, named, as work to file** …
> L812 **An EDITORIAL design-question finding raised before the sweep neither consults nor stops** …
> L815 **No state of the binding excuses the stop.** `DESIGN_AGENT` unbound, `TODO`-valued or uninvocable are the named instances; **any state in which no usable ruling comes back** is covered … the iteration **still stops** … **No inline composition substitutes here** … Where the binding is **static**ally unusable … write `- gate-error: scope-ruling — DESIGN_AGENT <unbound | TODO-valued | uninvocable> — no-binding` … **Where the agent ran and failed** … `- gate-error: scope-ruling — DESIGN_AGENT — <first line of the error>`, or `no-stderr` … **Never `no-binding` for a binding that was fine** … And **never `- gate-fallback:`**.

**E L838–869 (step 8 — record, not-a-round, cost)**
> L838 **Record the ruling where this round resolves** — in the gate-decision block … It needs no line format of its own. L844 **There is deliberately no dedicated `- Scope-ruling:` *disposition* line, and none is owed when this gate is not due** … *if you cannot tell whether this gate was due, it was — consult and stop.* L853 **The scope ruling is not a review round** … 1. **It certifies nothing.** … 2. **It reduces no review coverage.** L863 **Cost and locus:** one `DESIGN_AGENT` invocation … counted in **`subagent-runs` only** and **never in `gate-rounds=architect=`**.

**E L1029–1034 (Escalation rubric)**
> **And, always-on again, when a BLOCKING review finding raises a design question: consult `DESIGN_AGENT` for a scope ruling and STOP with it, at the moment the finding is returned** (step 8). The same inversion is available here … a finding that is *ruled on cleanly and then fixed in round 1* is neither "contested" nor "BLOCKING and unresolved" …

**E L2095–2098 (Routing table note)**
> **The `architect` in the `docs` and `research` cells above is the *plan-informing* Architect gate only.** Step 8's scope ruling is a separate gate (Gates → gate table) whose due-ness this column does not reach: a BLOCKING design-question finding consults and stops **on every route**, `docs` included …

**E L2122 (Gate table row)**
> | Scope ruling | `DESIGN_AGENT` | step 8, whenever a **BLOCKING** finding raises a design question — **on every route, `docs` included**, at whatever round it arises. **Its due-ness is fixed in this row alone and is NOT governed by the Routing table's per-route column** … nor by `mode:`, `plan-gate:`, or route graduation | the ruling, presented **with** the stop it carries — never a verdict on the change, and never a review *round* |

**E L2393–2399 (Fresh-re-check bound)**
> **One code-review escalation is not gated on this cap at all: a BLOCKING design-question finding escalates with its scope ruling at whatever round it arises** (step 8). The cap is unchanged by it — it opens no round 3 and renames no round … The scope is **code review only**: the acceptance gate's two *result* classes are not review findings and it runs no sweep …

**S L99–105**
> **A BLOCKING review finding that raises a design question stops for the human.** It is its own gate …: consult `DESIGN_AGENT` for a scope ruling **and** stop with that ruling attached, **before any fix for it is applied** — under every mode, **on every route**, at whatever round the finding arises, and **not** gated on the round cap. **No state of the binding excuses the stop**: unbound, `TODO`-valued or uninvocable means you stop with no ruling attached, never that you proceed. If you cannot tell whether a finding raises a design question, it does.

Cross-references that *exclude* the ruling from the plan-gate freeze rather than restate it (keep,
all): E L52–53 and L694–696 (unit-not-loaded: "a design-question finding still stops"), E L295,
L422–428, L435–440, L1492, L1498, L1903, L1985; S L94–98; README L116, L212–216, L432–440.

### 5.2 Semantic deltas

| # | Sites | Axis | What differs | Would the orchestrator act differently? | Test pinning it |
|---|---|---|---|---|---|
| Δ5.1 | E L815–819 vs S L102–104 | **binding states** that still stop | step 8: static trio *plus* "any state in which no usable ruling comes back" (errored, empty, forbidden conclusion); S: the static trio only | **No** — S's neighbor bullet (L109) already says "a gate that ran and *errored* never falls back — escalate", so a dynamic failure stops under SKILL.md alone | none |
| Δ5.2 | E L791 vs L749, L1030, L2122, L2394, S L101 | **moment** | step 8: before any fix, before the fix commit, before the next round; the others abbreviate to one of those | No — each is a subset of L791 and none contradicts it | none |
| Δ5.3 | E L826–836 vs every other site | **journal spelling** | only step 8 states the two `- gate-error: scope-ruling — …` forms and the never-`gate-fallback:` rule; no other site states any | No competing spelling. Residual check: `- Scope-ruling:` appears only at E L844, as the *negative* ("deliberately no dedicated … line") — `bf15770`'s cut is complete; no `asked:` field survives | none |
| Δ5.4 | E L2397 vs E L786, L2122 | **scope** | "code review only" vs "step 8" | No — same gate | none |
| Δ5.5 | E L853–861 vs L2122, L2394–2395 | **not a round** | step 8 states the two-conjunct test; the table row and the bound say "never a review round" / "opens no round 3" | No | `FindingClassAgreementTests` uses `**A BLOCKING finding that raises a design question consults` as the step-8 bound region's *end* anchor (must stay verbatim) |
| Δ5.6 | E L797–802 vs README L436–438 | **ruling content** | identical (narrow yes; no-human-needed never; clears nothing) | No | none |
| Δ5.7 | E L783 vs E L746 (default-deny over floors) | **trigger class** | the stop keys on BLOCKING; an EDITORIAL design-question finding *after* the sweep escalates (*"Once" is literal*) without a consult | Corner, not a drift: by Floor 1 (R L203–205) a finding that raises a design question asserts a proposition and is BLOCKING by default-deny, so the corner is empty in practice | none |

### 5.3 Rulings

All seven: **no ruling needed** — the pointer sites agree with step 8, which is the canonical site
by history (`919bae0` → `dda837c` → `bf15770` → `1bd4938`, one day, each subtracting rather than
adding). D012 recorded this as the gate that justified a minor bump; its wording is the most
deliberately reviewed passage in the file. What can be cut is rationale: the "why decoupling is
dangerous" sentences (L779–781, L792–796, L806–808, L819–825, L832–836, L865–868) restate at length
what the operative sentences already fix.

### 5.4 Canonical passage (E, step 8; replaces L778–869) — 25 lines

```
**A BLOCKING finding that raises a design question consults `DESIGN_AGENT` and carries its own
stop — one trigger, never two.**
- **Trigger.** A **BLOCKING** finding raising a design question: whether the approach is right,
  whether a fix belongs in this change at all, or whether several findings share one root cause.
  **If you cannot tell whether a finding raises a design question, it does.** An EDITORIAL one
  raised before the sweep neither consults nor stops — it joins the sweep.
- **Effect.** Consult `DESIGN_AGENT` for a **scope ruling** *and* **STOP for the human with it** —
  under every `mode:`, on **every route** (`docs` included), at whatever round the finding arises,
  **not** gated on the round cap, unreached by route graduation. Code review only. **The moment is
  when the finding is returned** — before any fix for it, before the round's fix commit, before the
  next round is spawned; the implement → commit → re-check sequence above runs *after* this stop.
- **The ruling**, verdict-first, stated at the invoke site: findings classified by severity, a
  minimal fix set that would clear the gate, every deferral with its reason. It may **narrow** the
  work; it may **never** conclude no human decision is required, clear a finding, or certify the
  gate. It is not a round — it certifies nothing and reduces no coverage — and is counted in
  `subagent-runs` only, never in `gate-rounds=architect=`.
- **No state of the binding excuses the stop.** No usable ruling — unbound, `TODO`-valued,
  uninvocable, errored, empty, or the forbidden conclusion — means you stop with no ruling attached;
  no inline composition substitutes. Journal the state you found: static ⇒
  `- gate-error: scope-ruling — DESIGN_AGENT <unbound | TODO-valued | uninvocable> — no-binding`;
  dynamic ⇒ `- gate-error: scope-ruling — DESIGN_AGENT — <first line of the error>` (`no-stderr`
  where none). Never `- gate-fallback:`; never `no-binding` for a binding that was fine.
- **Record** the ruling in the round's gate-decision block (Ledger format → progress.md); it has no
  line of its own and none is owed when not due — **if you cannot tell whether it was due, it was.**
  A deferral **is a decline**: record it there *as deferred by the ruling*, with its reason, so a
  later round receives it; one outliving the iteration is named to the human at the stop as work
  to file (you have no write path to `BACKLOG_SOURCE`).
```

(27 lines as drafted; two of the bullet continuations fold to reach 25 at the parent's discretion.)
`FindingClassAgreementTests`' end anchor is the first line, verbatim.

### 5.5 Other sites — pointer or keep

| Site | Disposition | Replacement / reason |
|---|---|---|
| E L749–751 | **keep** | The ordering instruction at the implement sentence is load-bearing ("act on that stop before acting on this sentence"). |
| E L1029–1034 (rubric) | **keep, trimmed** | `**And, always-on again: a BLOCKING review finding that raises a design question consults \`DESIGN_AGENT\` and STOPs when it is returned (step 8)** — a finding ruled on and fixed in round 1 is neither "contested" nor "unresolved", so this list is not the whole of when step 8 escalates.` |
| E L2095–2098 (routing note) | **keep** | `dda837c` root 1: the routing column must say from its side that it does not reach this gate. |
| E L2122 (table row) | **keep** | The row *is* the due-ness statement (Gate-outcome invariant L2132–2135 relies on it). |
| E L2393–2399 (bound) | **keep, trimmed** | `**One code-review escalation is not gated on this cap: a BLOCKING design-question finding escalates with its scope ruling at whatever round it arises** (step 8). It opens no round 3; the acceptance gate's result classes are not review findings, so nothing there keys on it.` |
| S L99–105 | **keep** | By design; it already carries the default-deny and the no-binding stop. |

### 5.6 Bytes

| Site | now | after | saved |
|---|---|---|---|
| E L778–869 → canonical | 7,970 | ~4,600 | ~3,370 (rationale) |
| E L1029–1034 trim | 569 | ~300 | ~270 |
| E L2393–2399 trim | 624 | ~330 | ~290 |
| **Invariant 5** | | | **≈ 3,900 B** (≈ 560 B if step 8's rationale is kept) |

---

## Totals and caveats

| | behavior-changing deltas | read-alone fail-opens | false cross-attributions | bytes recoverable |
|---|---|---|---|---|
| Inv 3 currency | 0 | 2 (step 9 alone; step 10 alone) | 1 (R L313–315) | ≈ 3,300 |
| Inv 4 fresh re-check | 0 | 0 | 0 | ≈ 1,900 |
| Inv 5 scope ruling | 0 | 0 | 0 | ≈ 3,900 (≈ 560 firm) |
| **Total** | **0** | **2** | **1** | **≈ 9,100 B ≈ 2,300 tokens** (≈ 5,800 B without the step-8 rationale cut) |

Against core's 200,789 B that is ~4.5%, in addition to D017's ≥20% floor (already discharged by
#166). Core-only savings ≈ 7,900 B; the rest is in the `reviewing` and `accepting` units.

**Caveats the parent should weigh before acting:**
1. The two fail-opens are *read-alone* defects. In the shipped file the governing sentence is in
   the same step or the same section, so no run has exhibited them; they are worth the two clauses
   because root `CLAUDE.md`'s rule is that a state nobody enumerated must resolve harmlessly.
2. Δ4.1 (naming step 6 inside the invariant) touches `43a6cb4`'s deliberate "not governed"
   wording. The behavior is byte-for-byte the same; the alternative that leaves it untouched is in
   §4.3 and costs ~450 B of the estimate.
3. Three tests anchor these passages by literal strings — listed under each canonical. Any
   rewrite must keep: `**Currency — a verdict is bound to the commit it ran on.**`,
   `**Fresh-re-check invariant` (as an *end* anchor — the canonical currency text must not contain
   it with a leading `**`), `- **Code review (step 8) — the previous round's findings`,
   `**The bound — one fresh re-check`, `**Reaching a cap is a handoff`,
   ` rounds (round 1 being the review`, `**A BLOCKING finding that raises a design question consults`,
   the exemption list `a citation, a doc line` in both regions, and `<reviewed>..HEAD` in all three
   scoping regions. Run `python3 -m unittest tests.test_repo_consistency` after the edit and
   mutate one anchor to confirm the guard still fires (`tests/CLAUDE.md`).
4. `README.md` restates all three (L116, L212–216, L432–440, L514–521, L636–642) under its own
   standing rule (root `CLAUDE.md`: trust-model and "How the loop works" sections change in the
   same PR as the gate). It is outside this reconciliation's scope and was not found to disagree.
5. `plugins/CLAUDE.md` currently says #35 "cannot be executed as chartered until F57/F58 are
   resolved" because the *plan-gate* sites drifted. That finding does not extend to these three
   invariants: here AC1 (state once) and AC3 (no semantic change) are compatible, which is the
   useful result of this pass.
