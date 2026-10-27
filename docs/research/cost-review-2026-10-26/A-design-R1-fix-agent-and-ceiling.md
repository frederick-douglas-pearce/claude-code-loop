# R1 design note — fresh-agent fix application and an iteration round ceiling

**Status:** design, not a ruling. Nothing here has been through a gate. Written 2026-10-26 against
working tree `971f21c` (engine 0.3.1, `loop-engine.md` 2,535 lines). Every line number below is
against that tree; re-derive them before applying if the file has moved.

**What R1 is.** Three engine-side, project-agnostic changes from `docs/research/cost-review-2026-10-26.md`
§3 R1: (a) on a dirty code-review round the fix is written by a fresh agent in an isolated copy under a
deletion-first mandate, and the parent collects the diff by path without reading it; (b) an
iteration-level ceiling on the review re-arm cycle, reached ⇒ stop and escalate with state and options;
(c) F125's constraint carried into engine text — the prose class that costs rounds is the unverified
claim, and the fix that works is deletion.

## 0. Decisions, up front

| question | decision | why (short) |
|---|---|---|
| Ceiling: fixed constant, `CAPS` binding, or ledger header field? | **Fixed engine constant, six.** No `CAPS`, no `/init-loop` change, no header field. | The per-gate cap is already a fixed constant, and the engine's own reasoning for `justification=`'s trigger applies verbatim: *"it is the engine's own shape, not a per-project number, so it needs no binding and cannot drift upward as a run gets more expensive"* (L1679–1681). A binding is an off switch for a stop, and the engine holds that stops are not configurable (Tool surface L1179–1194). A skeleton value is stranded at every consumer (#30's asymmetry), and this constant will be retuned from the paired benchmark, which only the engine's copy can receive. `CapsVocabularyTests` is therefore untouched — the new text names only `CODE_REVIEW`, `DESIGN_AGENT` and backticked `HEAD`, all already in the skeleton (checked by extractor regex over the drafted blocks). |
| Value of the constant | **6** rounds, code review + acceptance, every round counted however it was opened | The two capped gates own 2 rounds each, so 6 is above everything the orchestrator can spend on its own authority (4) and never fires on an iteration the caps already handle. The corpus's self-reported medians are 5–5.5 across all three sub-slots (architect included), i.e. roughly 4–4.5 for the two gates counted here; the tail runs to 10–12. Six interrupts that tail before its second half. It is a guess to be retuned, which is one more reason it is a constant and not a binding. |
| Where the fix agent runs | **In its own copy, spawned by the parent, one per round**, via the host's worktree isolation the Tool surface already specifies | The Execution policy has "no third form": an agent that writes gets a copy. Spawned by the parent *today*; the brief is written to the step's executor ("you"), so under R2 a forked review phase can spawn it unchanged (a subagent can spawn subagents, three layers deep — verified by the coordinator today; parent → forked phase → fix agent is exactly three, which is why the brief says *Spawn nothing*). |
| What the parent reads | **The agent's bounded report and `git diff --cached --name-status`** — never the hunks, never an edit | The parent is an author of every fix it directs (Fresh-re-check invariant); reading the fix buys no gate and invites the rewrite that injects the next round's claim. The path read is what step 6's read exists to catch (a gitlink, a stray file, a test path that re-arms the hermetic trigger). |
| Who applies EDITORIAL findings | **Unchanged — the parent's sweep** | The sweep applies only "a remedy the finder specified"; it composes nothing already. Deliberately left out (§5). |
| Step 10's own fixes | **Unchanged — the parent** | R1 is scoped to code review (the task's (a)). The ceiling counts step 10's rounds; the fix agent does not write them. Deliberately left out (§5). |
| Fix agent returns nothing | **`- gate-error:` and escalate; never write the fix yourself; no automatic re-spawn** | Gate-outcome: an agent that returns nothing produced no result. One stop costs less than a ladder. |
| Stranded copy on `/clear` | **Collect (save the diff beside the ledger), remove, never apply** | Resume's artifact check already finds any leftover worktree (`git worktree list`) and hands it to the collect-then-remove duty; an `in-review` resume replays step 8, so the findings it answered are re-derived and re-fixed. Applying it would land an unattributable delta on a row Resume's (b) says to keep only what it can attribute. |

**Default-deny, listed so the implementer can check each branch lands on the escalating side:** cannot
isolate a writer ⇒ no fix is written, stop; copy base unconfirmed ⇒ `unproven`, not applied; staged path
unattributable to the report ⇒ not committed, ask; no report and empty copy ⇒ gate-error, escalate;
cannot tell whether a finding turns on a claim ⇒ it does (delete, do not compose); cannot tell whether a
claim is load-bearing ⇒ it is (decline); cannot count this iteration's rounds ⇒ at the ceiling, stop;
stranded copy ⇒ never applied.

---

## 1. Engine text, per site

Eleven sites. Sites 1–7 are payload prose (engine core, the `reviewing` unit, `SKILL.md`); 8–9 are the
README and its byte-identical payload mirror; 10–11 are maintainer files. Every block is the full
replacement text; "insert" means the surrounding lines are untouched.

### Site 1 — `plugins/dev-loop/skills/dev-loop/loop-engine.md`, step 8, **replace L749–770**

L770 currently reads `licence to object too. Bounded to 2 rounds (round 1 being the review` and
continues on L771. The block below ends with that same tail **on one line** — `FindingClassAgreementTests`
anchors step 8's bound region on the literal `" rounds (round 1 being the review"` (leading space), so
the tail must not be re-wrapped. L771 onward is byte-identical.

```markdown
**Implement viable BLOCKING findings** — **except one raising a design question, which stops for
the human before any fix for it is applied (below)** — act on that stop before acting on this
sentence. Decline any **other** finding you do
not implement, with a one-line rationale; the exception above is a stop, never a decline — **and
record each decline, with that rationale, in the gate-decision block where this round resolves**
(Ledger format → progress.md), exactly as an architect decline is recorded in the plan text. A
later round is *required* to receive the declines (Gates), and a decline is the one outcome that
leaves **no trace in the diff** for that round to recover it from: unrecorded, it is invisible to
every subsequent fresh instance.

**"Implement" means a fresh agent writes every fix, in its own copy of the tree — never you, and
never in your tree.** The belief that wrote the text under review is still yours while you would
write its fix, and a fix written under it is the next round's finding. Spawn **one fix agent per
round** — not one per finding, never beside another writer — under Tool surface's isolation duties,
with the brief the `reviewing` unit fixes (*The fix agent*); it carries the deletion-first mandate,
which is not restated here. **If you cannot give it its own copy there is no fix to write: do not
write one yourself — STOP and ask.** On its return, **collect the diff by path and apply it, remove
the copy, and only then stage** (Tool surface — the window closes when *you* remove the copy).
**You never read the fix's hunks and never edit them.** Your read at this boundary is `git diff
--cached --name-status`: every staged path must be one the agent's report names — a test path there
re-arms step 6's hermetic trigger, as step 6 says — and **a staged path you cannot attribute to the
report is not committed: unstage it and ask.** A fix that looks wrong to you is a question for the
re-check, never an edit for you. **An agent that returns no report and leaves nothing in its copy
has fixed nothing:** journal `- gate-error: code-review — fix agent — <first line of the error>`
(`no-stderr` where there was none), escalate, and never write the fix yourself. A partial copy is
collected on Tool surface's terms and the re-check judges it. Record the agent's per-finding
dispositions in the gate-decision block (Ledger format → progress.md) before you spawn the re-check.

Then **commit the BLOCKING fixes** and **verify recs were applied — by a fresh checker, never by
yourself and never by the fix agent.** Directing a fix is authorship, and the fix agent is this
gate's one writing spawn, so its copy is what opens the staging window. This is the Fresh-re-check
invariant's sharpest instance (see Gates): you directed the fixes, so confirming them yourself is
the author agreeing with himself, not a gate. **Commit before spawning it** — the checker reads a
diff ending at `HEAD`, so an uncommitted fix is invisible to it. Under a scoped round that is worse
than the F15 shape the acceptance gate had to fix, not milder: the checker is handed not the pre-fix
code but an **empty** delta, which reports clean rather than reporting the wrong thing (hence the
empty-delta fallback in the `reviewing` unit). Spawn **one lighter checker** — its inputs are fixed
under Gates (Fresh-re-check invariant → the code-review bullet) and are not restated here — rather
than re-running the full finder fan-out; that recipe carries its licence to object too. Bounded to 2 rounds (round 1 being the review
```

What this preserves, deliberately: the design-question stop still precedes any fix (the fix agent is
spawned only after that check — "act on that stop before acting on this sentence" is the first clause);
the decline rule and its gate-decision record; "commit before spawning the re-check"; the empty-delta
fallback; the one-lighter-checker recipe pointer; the `Bounded to 2 rounds` sentence and everything after
it. What it changes: *who writes*, *what the parent reads*, and the two new failure branches (cannot
isolate; agent returned nothing). The old "If you *delegated* any fix" sentence is subsumed, since every
fix is now delegated.

### Site 2 — `plugins/dev-loop/skills/dev-loop/phases/reviewing.md`, **insert before L323**

L323 begins `**Round 1 reads the whole change; every round after it reads only what has changed since
the last round read.**`. Insert the block below (with its trailing blank line) between the sweep's
closing paragraph (ends L321) and that line. The unit's fail-safe half is unchanged: core already says
no round runs without the unit loaded, so the fix agent is never spawned without this brief.

```markdown
**The fix agent — one fresh writer per dirty round, under a deletion-first mandate.** Core (step 8)
fixes that every BLOCKING fix is written by a fresh agent in its own copy and that you never read
or edit its hunks; this is the brief. The agent is a new spawn — not a finder of this round, not the
re-checker, not anything that has read your reasoning — isolated per Tool surface and counted in
`subagent-runs`. Its copy need not start at this branch's head: **the brief's first instruction is
to check out the round's anchor** — the head the round ran on — **detached, and print `git rev-parse
HEAD`**; before you apply anything, confirm the copy's HEAD is that SHA and its `git rev-parse
--show-toplevel` differs from yours. **A diff whose base you cannot confirm is `unproven` and is not
applied.** The agent commits nothing: its working tree against that base is the whole deliverable,
so collection is one `git diff`.

**What the brief carries** — as text, since the agent reads nothing in this engine:
1. **the finding list, verbatim** — every BLOCKING finding you are implementing, each with its
   `file:line` and the finder's own words — and nothing of yours: not why you think each defect
   happened, not a draft fix, not a commit message, not what the fix should say;
2. **the base** — the anchor SHA, with the checkout-and-confirm instruction above;
3. **the plan** (`issue-<N>.plan.md`, which holds the acceptance criteria verbatim) and the round's
   diff range, to read in the copy;
4. **the mandate, verbatim:** *A finding that turns on a claim — false, stale, unresolvable,
   self-contradictory, or misdescribing what it sits on — is fixed by deleting the smallest clause
   that carries the claim, by substituting a value you reproduced in this tree, or by a mechanical
   re-wrap; if you cannot tell whether a finding turns on a claim, it does. Compose no new
   sentence: a new sentence is a new claim and enters review unverified. A claim you cannot verify
   in the tree is deleted, not reworded; a hedge is not a defect, and is never resolved into an
   assertion. Fix a stale term at every site repo-wide — enumerate them first — not at the one site
   a finding names. Where a claim is load-bearing and cannot be deleted, or the finding is wrong
   because the claim is true, DECLINE and say what you reproduced; if you cannot tell whether a
   claim is load-bearing, it is. A behavior defect is fixed in code, with no new prose claim beside
   it and never by weakening a test. Grep for inbound references before deleting. Touch nothing no
   finding reaches. Commit nothing. Spawn nothing.*
5. **what it returns, verdict-first** (Verdict-first invariant): one line per finding — `fixed:
   deleted | substituted | re-wrapped | code — <paths>` or `declined — <reason>` — before any
   explanation; and the Relay invariant's sentence verbatim: *mark each statement you return as
   REPRODUCED — you ran it, read it, or compared it in the material given to you — or INFERRED,
   for anything about an artifact you were not given.*

**What you do with the return.** A `declined` finding is a decline for every purpose core's decline
rule fixes: record it with the agent's reason beside your own declines in the gate-decision block,
so the re-check receives it and may contest it. Its `file:line` cite the copy, never the merge
candidate — record dispositions, not lines. **A copy stranded by a `/clear` is collected on Tool
surface's terms — save its diff beside the ledger, then remove it — and never applied:** a resumed
`in-review` row replays this step, so the findings it answered are re-derived and re-fixed by a
fresh spawn.

```

Notes for the implementer. The mandate is item 4 *as text* because the Verdict-first and Relay
sections both rule that a reference by name is inert in a prompt the agent reads verbatim; the same
rule is why item 5 carries the Relay sentence itself rather than its name. The claim vocabulary in the
mandate is the `claims=` count's own (Ledger format L1542–1544) and the content floor's (unit L205–206),
per #169/AC2 — do not mint a third. The "need not start at this branch's head" sentence encodes a
host fact (an isolated worktree is commonly created from the default branch) without naming the host;
#169/AC4 established the base-commit input "the hard way", and the memory file on isolated worktrees
records the same hazard. The decline licence (item 4's DECLINE clause) is #169/AC3 and AC5 — the two
#178 declines are why it is load-bearing; a bare "delete it" mandate would have deleted a true
statement.

### Site 3 — `loop-engine.md`, Gates, **insert after L2412 and replace L2414–2416**

L2401–2412 is the paragraph `**Reaching a cap is a handoff, never a terminal state.** … about *this*
gate.` L2414–2416 is the `Cost:` paragraph. Insert the ceiling paragraph after L2412 (keeping the blank
L2413), then replace the `Cost:` paragraph with the amended one. The `FindingClassAgreementTests`
span for the Gates bound ends at `**Reaching a cap is a handoff` and the `CurrencyExemptionAgreementTests`
span ends at `**Fresh-re-check invariant`, so both sit before this insert; the Verdict-first and Relay
regions start at L2428 and L2460, after it.

```markdown
**The ceiling — six rounds across code review and acceptance in one iteration, every round
counted however it was opened.** The caps bound each gate and nothing bounds the cycle: a fix at
one gate re-arms another, so an iteration can spend a round at every stop and never trip a cap.
Keep the running total — every round this iteration has run at either gate, each `- Code-review:`
element and each acceptance verify or re-verify, re-arm re-checks and human-directed rounds
included; **if you cannot tell which rounds are this iteration's, the total is unknown, and unknown
is at the ceiling.** Before spawning any round of either gate, add one: **a total that would exceed
six is a round you do not spawn.** STOP and put it to the human with the state — the total and its
split, each round's `claims=`, and where the last round's findings sit: in the previous fix's
hunks, in one acceptance-criteria cluster, in prose rather than code — and the options that end a
cycle: revert the hunk the findings cluster in; split the change along that seam; a subtractive
scope ruling from `DESIGN_AGENT`; ship what is clean, with the residuals named for the human to
file; abandon. Another round is the option this stop exists to interrupt — list it last. **A
direction given before this stop does not carry past it:** "keep going until clean" is spent at the
ceiling, and **past it no re-arm is owned** — a round that would exceed six is spawned under no
step's budget; it escalates (Currency). The human remains the budget authority: a round they direct
*at* this stop runs, counts, and stops again if dirty. It is a handoff on the cap's terms above —
not a verdict, not `blocked`. Record `ceiling=reached` on the `- Budget:` line (progress.md → the
Budget line), and the human's answer as a human decision, never as a gate passing (Currency).

Cost: **one extra subagent per dirty class per iteration, plus one fix agent per dirty code-review
round (step 8)** — so two re-checkers at the acceptance gate when Class A and Class B are both
dirty, since their inputs differ and cannot be merged into one checker. Bounded either way, and it
cannot grow into an unbounded ladder.
```

What the ceiling adds to the engine as written, stated honestly: the orchestrator's *own* authority to
open rounds is already ≤2 per gate (a re-arm is owned only while a round is left — L2221–2225), so on an
unattended path the per-gate caps already stop everything. The ceiling binds three things the caps do
not: (1) a **total across gates** that the human sees, where today each stop presents "round 2 of this
gate"; (2) **standing human directions** — today nothing says whether "keep going until clean" licenses
round after round, and the corpus (F131) shows every round past 2 was a human release; (3) the
**content** of the stop — the diagnostic (findings by hunk, AC-cluster, prose-vs-code, the memory
files' three cheapest tests) and the subtractive menu, which is what #56, #88 and five memory entries
describe as the thing that actually ends a cycle. It is written as a stop, not a ruling on merit, which
is why it cannot produce the false positive #56's own falsifier warns about (#123, #234: rounds "reached
on merit") — the worst case is one extra human stop with a better menu.

### Site 4 — `loop-engine.md` Gate table, **replace L2121**

```markdown
| Code review | `CODE_REVIEW` (parallel finders you run — step 8); **the fix a fresh agent in its own copy, its re-check another fresh checker — neither you** (Fresh-re-check invariant) | every issue; one light pass on `docs` | findings → fixes, each carrying a **finding class**: BLOCKING re-arms; EDITORIAL raised before step 8's sweep is swept there, and anything raised after that sweep escalates |
```

### Site 5 — `loop-engine.md` Escalation rubric, **replace L1020–1024**

```markdown
`DESIGN_AGENT`. Escalate to the HUMAN when those disagree/punt, ACs are unresolvable, an
action is destructive/irreversible, a review finding is contested or is BLOCKING and unresolved
(an EDITORIAL one raised before step 8's sweep escalates nothing — it is swept there; one raised
after that sweep escalates like any other, by step 8's *"Once" is literal* rule), the same step
failed twice, or the round ceiling is reached (Gates) —
```

(L1025 `**and, always-on, when the architect *decides*…` follows unchanged.)

### Site 6 — `loop-engine.md` Ledger format, `- Code-review:` paragraph, **insert after L1565**

L1565 ends `…a slot written only when it looks interesting measures nothing.`; L1567 begins
`The **`- Editorial:`** line records`. Insert between them. This sits inside
`DeltaScopedRoundNotationTests._LEDGER_REGION` (`The **`- Code-review:`** line names` → `The **`- Restore:`**
line records`), which only requires the `<sha>..<head>` spelling to remain and the start anchor to stay
unique — the block repeats neither.

```markdown

**With each dirty round, record the fix agent's dispositions** — one per BLOCKING finding, in the
agent's own vocabulary (`fixed: deleted | substituted | re-wrapped | code` or `declined —
<reason>`; the `reviewing` unit, *The fix agent*), written when the fix resolves and before the
re-check is spawned, beside the round's declines. A disposition held only in your context is lost
to the `/clear` that most often sits between a fix and its re-check, and the re-check is owed the
declines among them.
```

### Site 7 — the `ceiling=` Budget slot, two sites (the line is specified twice today)

**Step 12, insert after L1007** (the `post-gate-survivors` sub-bullet ends there; L1009 begins `**Two
constraints that keep the line parseable.**`):

```markdown
- **`ceiling=reached` where the round ceiling stopped this iteration (Gates), `ceiling=not-reached`
  otherwise.** Omitted means unknown, as for every optional slot — never "not reached".
```

**Ledger format Fields list, insert after L1681** (the `justification=` bullet ends there):

```markdown
- **`ceiling=reached | not-reached`** — whether the round ceiling (Gates) stopped this iteration.
  Recorded separately from `gate-rounds` because a total can sit at six without the stop having
  fired, and only the stop is what a later reader is measuring.
```

Both are optional slots under the forward-stability rule (L1774–1787): `name=value`, no `·`, absent =
unknown. The worked example line at L1439 need not change.

### Site 8 — `plugins/dev-loop/skills/dev-loop/SKILL.md`, **replace L123–126** (see §2)

### Site 9 — `README.md` and `plugins/dev-loop/README.md` (byte-identical; edit both in one commit)

Three edits, same text in both copies. **Trust model**, replace the paragraph at L636–642 (`**A fix is
never checked by whoever wrote it.** …`):

```markdown
**A fix is never written by the thread that wrote the change, and never checked by whoever wrote
the fix.** When code review finds something, a freshly spawned agent writes the fix in a throwaway
copy of your tree, under one rule: a wrong claim in prose or a comment is cut or replaced with
something it verified in your tree, never reworded into a new claim, and a claim it cannot verify is
deleted. The loop applies that diff by path, without reading or editing it, and commits it; then
another fresh checker — not the thread, and not the agent that wrote the fix — decides whether it
worked. The acceptance gate's own fixes are re-checked the same way. Each such gate gets **one**
re-check; if it comes back dirty the loop stops and asks you, rather than iterating on itself. At
code review, "dirty" means a **blocking** finding — an editorial one raised before that pass has run
joins it, and neither re-arms the round nor stops for you. Once the pass has run there is no second
one, so a finding of either kind after that point stops and asks you.

**Six gate rounds in one issue is the ceiling.** Across code review and acceptance, counting every
round you release, the loop will not open a seventh: it stops, shows you where the findings cluster
— in the last fix, in one acceptance criterion, in prose rather than code — and the options that end
a cycle (revert that hunk, split the change, narrow it, ship the clean part), and lists another
round last. You decide; a round you direct there runs and stops again if dirty.
```

**"How the loop works" table**, row 8 (L93) `Comes back to you when` cell: append `; the issue's sixth
gate round across review and acceptance`. Row 10 (L95): append the same clause. (The root `CLAUDE.md`
requires both the trust-model section and this table to move with any change to what stops for the
human; `PipelineStepOrderTests` never reads the README, so nothing fails if this is forgotten.)

### Site 10 — `plugins/CLAUDE.md`, tree-isolation bullet (L82–91), maintainer-side

Add to the site list: `step 8's fix-agent paragraph (R1) and the \`reviewing\` unit's *The fix agent*
brief`. One line; no other change. Does not ship.

### Site 11 — `tests/test_repo_consistency.py`, optional, maintainer-side

`VerdictFirstInvariantTests` and `RelayInvariantTests` enumerate the orchestrator-facing recipes that
must name each invariant. The fix-agent brief is a new recipe of that kind; add one region to each,
anchored `("**What the brief carries**", "**What you do with the return.**")`. It is a coupling-identity
pin (the invariant's name appears in a located region), the shape `tests/CLAUDE.md` permits. Not
required for the engine change to be correct; recommended so the brief cannot silently drop either
name later.

### Invariant checklist — each multi-site invariant, and where the new text keeps it

| invariant | kept how |
|---|---|
| **Currency** — the fix commit re-arms the gates it must | The fix commit is still step 8's boundary; the path read names a test path, and the block says in so many words that a test path re-arms step 6's hermetic trigger. Step 9/10/CI re-arms are untouched; past the ceiling an owned re-arm becomes unowned and escalates, which is the currency clause's own posture for an unowned re-arm. |
| **Gate-outcome** — an agent that returns nothing is not a pass | No report and an empty copy ⇒ `- gate-error: code-review — fix agent — …`, escalate. The spelling elides volatile arguments so Guardrails' repeat check reads one signature. A partial copy is evidence, not a verdict: collected, then judged by the re-check. |
| **Isolation** — never stage while a writing agent's copy is live; the parent discharges all four duties | The sequence is spelled: return → attribute the copy (toplevel differs, HEAD = anchor) → collect by path → apply → remove → then stage. One writer per round (F40). The stranded-copy case routes through Tool surface's collect-then-remove duty, which Resume already invokes. |
| **Attribution** — `file:line` in the merge candidate, never the copy | The brief's `file:line` are declared copy citations and are recorded as dispositions; the re-checker, reading `<reviewed>..HEAD`, is still the one that cites the merge candidate. |
| **Fresh-re-check** — a fix is never checked by its author | Strengthened: the re-checker is "never you and never the fix agent"; "directing a fix is authorship" is kept verbatim. |
| **Verdict-first / Relay** — recipes name them; verbatim prompts carry the sentence | The brief names both and carries the Relay sentence itself. |
| **Explicit-path staging** (step 6, every boundary) | Unchanged at step 6. Step 8's read is `git diff --cached --name-status`, which is still "read back what you staged" (the README's wording) and still catches the gitlink and the stray path. |
| **Design-question stop before any fix** | The first clause of Site 1 is unchanged; the fix agent is spawned after it. |
| **Default-deny** | Every unknown in the new text lands on stop/escalate/not-applied — the list in §0. |

---

## 2. `SKILL.md` fail-safe bullet — replace L123–126

```markdown
- **A code-review fix is written by a fresh agent in its own copy of the tree, never by you, and
  re-checked by another fresh instance, never by its author.** If you cannot isolate a writer, do
  not write the fix yourself — stop and ask. After any gate's fix, the re-check is a **new spawn** —
  not you re-reading the diff, and not the round-1 agent re-contacted. If the fresh re-check is
  still dirty, **escalate to the human** rather than iterating — and **never spawn a round that
  would take this iteration past six across code review and acceptance**, whatever you were told
  earlier; if you cannot count them, you are at the ceiling: stop and ask.
```

Partial-load posture: an orchestrator holding `SKILL.md` without the engine over-escalates — it writes
no fix itself (stop), and it stops at six rounds or on an uncountable total. Neither sentence can be
satisfied by doing less than the engine asks.

---

## 3. Journal lines, and what pins them

| record | change | pinned by |
|---|---|---|
| `- Code-review:` round elements | **None.** The three element shapes (unscoped / scoped / no verdict) and `claims=` are unchanged. | `DeltaScopedRoundNotationTests` pins the paragraph region for `<sha>..<head>` and the unique start anchor; the Site 6 insert keeps both. |
| gate-decision block | **New record:** the fix agent's per-finding dispositions, beside the declines, written when the fix resolves. Same write-time discipline as the roster record and the EDITORIAL IDs. | Nothing in `tests/` reads gate-decision blocks. |
| `- Budget:` | **One optional slot**, `ceiling=reached \| not-reached`. The four required slots, `justification=`'s trigger, and the one-physical-line rule are unchanged. | **Nothing.** `grep -rn -E "Budget:\|gate-rounds" tests/` returns no match; the Budget line is specified in prose only, at two near-duplicate sites (step 12 and Ledger format), both edited here. |
| `- gate-error:` | **New signature:** `code-review — fix agent — <first line>`; distinct from the existing `code-review — phases/reviewing.md not loaded — …`. | Guardrails greps the full journal for repeats; the fixed shape is what makes a second occurrence read as the same defect. |
| `subagent-runs` | The fix agent is one invocation, so it increments; unchanged rule, stated in the brief. | — |
| append-only guard | **No interaction.** This repo's `.claude/loop.append-guard.json` registers only `.claude/specs/decisions.md`; `progress.md` is gitignored and never full-file-written by the engine. Everything here is an append. | `test_guard_append_only.py` is about the hook, not these lines. |
| ledger directory | A stranded fix copy's diff is saved beside the ledger (`LEDGER_ROOT/<run>/`), the precedent being the mutation spec kept beside `issue-<N>.plan.md`. Gitignored like the rest. | — |

Other pins checked against the drafted blocks (extractor regexes and `grep -F` over the new text):
`CapsVocabularyTests` finds only `CODE_REVIEW`, `DESIGN_AGENT` and backticked `HEAD`, all in
`init-loop.md` already (no `/init-loop` change, no inference-map row); the seven anchors
`" rounds (round 1 being the review"`, `"- **Round 1 is unscoped.**"`, `"**These bases"`,
`"The **`- Code-review:`** line names"`, `"**The bound — one fresh re-check"`, `"**Reaching a cap is a
handoff"` and `"**A BLOCKING finding that raises a design question consults"` each occur **zero** times in
the new text, so no start anchor is duplicated and no span is widened; the step-8 bound span still names
both class tokens; `PipelineStepOrderTests`' cross-reference floor only rises (the new text cites steps
6, 8, 10 by resolvable number); the README mirror test requires both copies in one commit.

---

## 4. The falsifier, written for pre-registration

**Design.** The paired within-issue benchmark of §5.3: the same closed issue replayed at its base
commit under two engine variants pinned as versioned plugin-cache directories — control = 0.3.1,
treatment = 0.3.1 + R1 — same `(parent model, effort, subagent roster)` stratum, arms interleaved by
issue parity, k ≥ 3 replicates per issue per arm, plan gate answered by the same scripted approval.
Fixture: 6–10 issues from vote, loop and esg, including at least two that took ≥ 5 rounds under the
installed engine (the ledger's `gate-rounds` picks them; `us-presidential-vote-analysis` #157, #172,
#181, #234 and this repo's #28, #60 are the obvious candidates) and at least one that was clean in two
rounds (a true negative for the ceiling). Independent variable recovered from transcripts, not the
self-report (§5.4): count step-8/step-10 round blocks and re-check `Agent` launches from `tool_use`
inputs; count fix-agent spawns the same way.

**Outcomes, with the direction and the size predicted, and the reading that refutes R1:**

1. **Rounds per completed issue** (c + v, transcript-counted). Prediction: treatment median lower on
   the ≥5-round issues by at least one round, and not higher on the clean issues. **Refuted** if a paired
   sign test over issues shows no reduction, or the treatment arm is higher on any clean issue.
2. **Fix-induced claim defects** — the `claims=` count of every round after round 1, treatment vs
   control (#169's own falsifier; the instrument is live). Prediction: falls toward zero on the
   prose-heavy issues (#178 measured 8 → 3 → 0 → 0 by actor and mode). **Refuted** if the post-round-1
   `claims=` sum does not fall. This is the mechanism check; outcome 1 is the cost check, and R1 can
   pass one and fail the other.
3. **Whole-tree USD per completed issue** (`tree_cost.py --sessions`, each turn priced on its own
   model). Prediction: 15–35% lower on the ≥5-round issues, within noise on the clean ones (the fix agent
   costs one cold-cache spawn per dirty round). **Refuted** if the treatment arm is not lower on the
   ≥5-round issues once σ from #209 is known; until σ exists, only a reduction above ~25–30% is
   claimable.
4. **Quality — three readings, all pre-registered as "must not rise":**
   - **Over-deletion.** A new defect class R1 can create: the fix agent deletes a true or
     load-bearing statement. Tag it in advance: any re-check or AC-verifier finding of the form "a
     claim the finding did not dispute is gone" or "a criterion is now unmet because text was removed"
     is logged as `over-deletion` in the round's gate-decision block. **Refuted** if the treatment arm
     logs any over-deletion that reaches the merge candidate, or more than one per issue at any round.
   - **Blind evaluator** (§5.2): an agent scores each arm's merged diff against the issue's ACs
     without knowing which engine produced it. **Refuted** if the treatment arm scores lower on the
     paired issues.
   - **Fix-up commits** touching the merged PR's files within 14 days, and F-comments on #1
     attributed to the PR. **Refuted** if either is higher in the treatment arm.
5. **The ceiling.** Count issues reaching it, and what the human chose. Prediction: it fires on the
   ≥5-round issues only, and the human's choice is a subtractive option at least as often as "another
   round". **Refuted** if it fires on any clean issue (an unknown-total stop counts), or if, over the
   fixture, every ceiling stop is answered "another round" and those rounds come back clean — which would
   mean the menu is not the lever and the constant is too low.
6. **Blast radius and hygiene** (new defect classes to watch, pass/fail by count): fix-agent diffs
   touching a path no finding reached; staged-path mismatches at the commit boundary; stranded
   worktrees per iteration (`git worktree list` at step 12); fix agents that returned no report.
   **Refuted** as a safe change if any of these exceeds one per fixture run.

**Confound stated up front.** #178's experiment, and this design, give the fix agent both treatments at
once — a clean context *and* a deletion mandate — and cannot separate them. What ships is the combined
treatment. The third arm (clean context, rewriting permitted) belongs to #144's reference-issue design
and is not required for a verdict on R1 as a lever; it is required before anyone claims which half is
the active ingredient.

**Stopping rule.** Run the fixture once per arm per replicate; no interim look at the outcomes; the
verdict is posted on #169 with the paired table, the σ from #209, and the engine SHAs of both arms.

---

## 5. Risks, and what is deliberately left out

**Risks.**

- **Over-deletion is the one defect class R1 can create.** The decline licence and "if you cannot tell
  whether a claim is load-bearing, it is" are the mitigation; the falsifier's outcome 4 is the
  measurement. The acceptance gate (which reads the ACs verbatim) is the structural backstop — a deleted
  load-bearing claim that the ACs depended on is a Class A finding there.
- **The parent's path read is weaker than its old content read.** A fix agent that writes something
  deliberately broken is caught by the re-check, CI and acceptance, not by the parent. That is the trade:
  the parent's content read never certified anything (the Fresh-re-check invariant says so) and is what
  produced the rewrite. Accepted; the gitlink and stray-path hazards, which are the ones step 6's read
  was written for, are visible by path.
- **The isolated copy's starting commit.** Hosts create worktrees from the default branch, so a brief
  without the checkout-and-confirm instruction fixes the wrong tree and reports success. Both the brief
  (first instruction) and the parent (HEAD = anchor before apply) check it; this is #169/AC4's "base
  commit" and the memory entry on isolated worktrees.
- **One more subagent per dirty round, cold cache.** R1 pays for itself only if rounds fall; on an issue
  whose rounds are "on merit" (#123) it is pure cost. Outcome 3 measures this.
- **The constant is a guess.** Six is derived from the owned budget (4) and the corpus tail, not from a
  measurement of where the diagnostic stop pays. It is a constant precisely so that it can be retuned in
  the engine without touching any consumer config.
- **Multi-site drift.** The isolation invariant gains two sites (Site 1, Site 2) and the round bound
  gains one (the ceiling); `plugins/CLAUDE.md` records that nothing checks their agreement. Site 10 adds
  the new sites to its list; Site 11 is the one mechanical pin available.
- **`in-review` resume still replays step 8 from round 1** (L1236–1238's residual). A `/clear` between
  the fix and its re-check now also strands a copy; the stranded-copy rule costs the fix (it is redone),
  never the tree.
- **The fix agent cannot see the parent's reasoning, by design** — so a behavior defect whose fix needs
  context the plan and the diff do not carry will be fixed worse, and the re-check will say so. That is a
  round, not a silent failure; the alternative (the parent writes it) is the mechanism under treatment.

**Deliberately left out, with the reason each would need to come back.**

- **The editorial sweep stays with the parent.** It applies finder-specified remedies and composes
  nothing; routing it through the fix agent would add a spawn to the common clean path for no measured
  defect. Revisit if `- Editorial:` lines start carrying fix-induced claims.
- **Step 10's own fixes stay with the parent.** R1 is scoped to code review; the acceptance gate's
  commit boundary and Class B fix path are untouched. The ceiling *counts* step 10's rounds. Extending
  the fix agent to step 10 is a separate change with its own falsifier (`ac-findings` in round 2).
- **No `CAPS` binding and no header field for the ceiling.** A per-run override in the `queue.md`
  header (beside `subagent-cap:`) is the one form that would not strand a value in consumer configs; it
  is omitted because a raisable ceiling is an off switch for a stop, and the human can already direct a
  round at the stop. Reconsider only if the falsifier's outcome 5 shows the stop firing on clean issues
  at a rate the menu does not justify.
- **No automatic re-spawn when the fix agent returns nothing.** One human stop; no ladder.
- **No provenance detector (#56), no claim audit (#153), no severity floor (F38), no "doc-only ⇒
  stop" rule (F131 says why).** The ceiling's menu lists #56's subtractive step-back as an option the
  human picks; it does not run it. #153 is superseded for the reason the cost review gives: a repair that
  may not introduce a claim leaves an audit little to check.
- **No change to `CODE_REVIEW`'s binding, to the finder fan-out, or to `init-loop.md`.** The skeleton
  is untouched, which is the whole point of the fixed constant and the no-binding fix agent.
- **The third experimental arm.** #144's.
- **Prompt-cache tuning for the fix agent.** It is a short-lived spawn; `subagentPromptCacheTtl` is R2's
  concern for phases that wait on a human.

**R2 compatibility, since the coordinator confirmed subagents can spawn subagents (three layers).**
Every sentence in Sites 1–2 addresses "you", the executor of step 8, and every duty the fix agent's
spawner owes (attribute, collect, remove, then stage) is one the Tool surface already assigns to whoever
owns the tree during that step. Under R2 a forked review phase becomes that executor and spawns the fix
agent as its own child — parent → phase → fix agent is three layers, which is why the brief ends
*Spawn nothing*. No wording here needs to change for that; what R2 must settle is tree ownership during
a forked phase, which is its problem and not this note's.

---

## 6. Byte count

Measured with `wc -c` on the drafted blocks against the lines they replace (files under
`scratchpad/old/` and `scratchpad/new/` beside this note).

| site | old bytes | new bytes | delta |
|---|---:|---:|---:|
| 1. step 8 (L749–770) | 2,007 | 3,581 | **+1,574** |
| 3. Gates ceiling + amended Cost (L2414–2416 replaced) | 264 | 2,186 | **+1,922** |
| 4. Gate table row (L2121) | 363 | 409 | +46 |
| 5. Escalation rubric (L1020–1024) | 400 | 438 | +38 |
| 6. Ledger dispositions record (insert) | 0 | 506 | +506 |
| 7. `ceiling=` slot, step 12 (insert) | 0 | 190 | +190 |
| 7. `ceiling=` slot, Ledger fields (insert) | 0 | 260 | +260 |
| **engine core subtotal** | | | **+4,536** |
| 2. `reviewing` unit, *The fix agent* (insert) | 0 | 3,703 | **+3,703** |
| 8. `SKILL.md` bullet (L123–126) | 323 | 666 | +343 |
| **payload prose total** | | | **+8,582** |

Against the measured sizes in the cost review: core 200,789 → ~205,325 (+2.3%, ~1.7k tokens on every
invocation); `reviewing` unit 32,344 → ~36,047 (+11%, ~1.4k tokens, read at step 8 only); `SKILL.md`
10,829 → ~11,172. README deltas are not counted (two copies, ~1.3 KB each; the payload copy ships but is
not read by the engine). Where to cut if the gate wants it smaller: the ceiling paragraph's menu can
lose ~250 bytes by naming the options without the tally clause, and Site 2's opener can lose ~300 by
dropping the "need not start at this branch's head" rationale and keeping only the instruction. Neither
cut touches a fail-safe branch.
