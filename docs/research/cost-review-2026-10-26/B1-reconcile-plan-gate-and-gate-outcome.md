# Reconciliation A — the two drifted invariants behind #35

Line numbers are against `main` at `971f21c` (2026-10-26), working tree clean except an untracked
research note. Files: `E` = `plugins/dev-loop/skills/dev-loop/loop-engine.md` (2535 lines,
200,789 bytes); `S` = `…/SKILL.md`; `I` = `…/reference/initialization.md`; `A` =
`…/phases/accepting.md`; `R` = `…/phases/reviewing.md`. Nothing was edited.

**What this is for.** #35 (one canonical mode/gate passage) was deferred 2026-08-18 because its AC1
(state once) and AC3 (no semantic change) conflict while the restatement sites disagree (F57/F58 on
#1). The precondition for re-opening it, per the architect and the deferral comment, is: *resolve
F57 and F58 first, as separate decisions*. This document is those decisions, proposed, for the two
invariants named in the brief — with the drift that has accrued **since** F57/F58 were filed, which
turned out to be the larger part.

**Standing design work carried over, not re-derived** (architect-affirmed on #35): three classes of
site — *definitional* (becomes canonical), *operative* (reduce to one fail-safe line + pointer, never
a bare pointer), *citing* (the rule is a premise inside an argument about something else — **never
reduce**); P5 (the always-on architect-rewrite stop) is out of scope and its site list in
`plugins/CLAUDE.md` is maintained, not summarized; `SKILL.md`'s restatements stay (AC2).

---

## Invariant 1 — plan-gate posture

Propositions (from the #35 plan): **P1** `mode:` gates the merge gate only; **P2** `always` ⇒ stop
every issue, `conditional` ⇒ stop on step 5's judgment conditions; **P3** absent or unrecognized ⇒
`always`; **P4** the two fields are independent after Initialization; **W** who writes the field and
when (Initialization once; human-owned after; the orchestrator never writes it outside
Initialization).

### 1.1 Sites, verbatim (trimmed to the operative sentences)

| # | Where | Class | Operative text |
|---|---|---|---|
| S1.1 | E L97–101 (step 0.1, parked path) | operative, pointer | "emit the plan-gate inference record if it is owed (Ledger format → `progress.md` → `- Plan-gate-inferred:`, which states when it is owed and how it dedupes)" |
| S1.2 | E L114–121 (step 0.2) | operative, pointer | "note its `mode:` / `graduated-routes:` / `plan-gate:` header … Then emit the plan-gate inference record if it is owed … **Do not write the field: it is the human's.**" |
| S1.3 | E L309–312 (step 4c) | citing (P5) | "This bites under **every** `plan-gate:` value, and `always` is not a reprieve from it. Under `conditional` the row auto-approves outright; under `always` the human is stopped but shown a diff that says nothing changed" |
| S1.4 | E L335 | heading | `### 5. Human gate (posture set by `plan-gate:` — plus one always-on condition)` |
| S1.5 | E L336–356 (step 5 opening, 21 lines) | **operative — REDUCE** | L336–337: "**Read `plan-gate:` from the `queue.md` header** (Ledger format → queue.md). That field, and never `mode:`, sets this gate's posture — `mode:` gates the merge gate only (step 11), never this one". L338–339: "`plan-gate: always` — what Initialization writes under `mode: calibration`. **STOP for plan approval on every issue.**" L339–343: "Whether to stop is not a judgment call under this value. **What you put in front of the human still is** — … prepare its frozen-vs-live diff for presentation. Stopping with the plan but without that diff satisfies this bullet and still fails the gate." L344–345: "`plan-gate: conditional` — what Initialization writes for a project with prior route graduation. Stop on the judgment conditions below, plus the always-on condition". L347–351: "**Read the field, never derive it from `mode:`.** … the fields are independent afterwards, so a run may legitimately sit at `escalation-only` with `plan-gate: always`. … a ledger created before this field existed … has no `plan-gate:` line at all, and it reads as `always` by the rule below — never as `conditional` inferred from its `mode:`." L353–356: "**An absent or unrecognized value reads as `always`.** … gets the **over-gating** reading — never 'conditional by fallthrough'. Same default-deny posture as every other gate" |
| S1.6 | E L358–360 | gate content | value-first under either value (not posture) |
| S1.7 | E L362–372 (conditional list) | **operative — canonical for P2's list** | L362–364: "**Under `plan-gate: conditional`**, present the plan and STOP for approval when: the value story doesn't hold; acceptance criteria are ambiguous; the change is risky/irreversible; SCOPE/DESIGN agents disagree or punt; or you are otherwise unsure. Otherwise proceed (note 'auto-approved' + why in the journal)." L365–366: "**Under `plan-gate: always` there is no 'otherwise'** — every issue stops, and 'auto-approved' is never a legitimate journal entry for this gate." L371–372: "On approval — the human's, or under `conditional` only, an auto-approval — advance the row to `plan-approved`." |
| S1.8 | E L374–376 | P5 | "it fires under **every** mode **and both `plan-gate:` values**. Route graduation cannot reach it" |
| S1.9 | E L378–385 | P5 (write duty, imperative) | "Take the frozen-vs-live diff and write its `- Plan-gate:` line on every iteration that reaches this step, whatever the field says." |
| S1.10 | E L914–916 (step 11) | operative at the merge gate | "The merge gate is the **only** gate `mode` changes (step 5's posture comes from the separate `plan-gate:` field, which `mode:` never sets after Initialization — plus one always-on condition neither reaches)." |
| S1.11 | E L1036–1039 (Escalation rubric) | operative floor | "**This list is what 'unsure' triggers; it is not the whole of when the plan gate stops.** Under `plan-gate: always` — the shipped default, and what an absent field reads as — step 5 stops on **every** issue, whether or not anything here fires." |
| S1.12 | E L1271–1274 (Status recognizer) | **citing — never reduce** | "`plan-gate:` can read an unrecognised value as `always` because its values are ordered and one of them is stricter. A Status has no such ordering … so the fail-safe here is the human, not a fallback." |
| S1.13 | E L1291–1297 (`mode:` paragraph + `calibration` bullet) | operative (P1) + P5 | "The header carries a `mode:` field that gates **the merge gate only** — it does **not** change the plan gate, whose posture comes from the separate **`plan-gate:`** field described below (step 5) — **plus one always-on condition neither field can reach** … `calibration` (default) — the human approves **every** merge … Initialization pairs it with `plan-gate: always` (step 5) — plus that always-on condition." |
| S1.14 | E L1312–1318 (`escalation-only` bullet) | P5 + operative (P4) | "Initialization pairs it with `plan-gate: conditional` (step 5) — **and neither that pairing nor graduating a route loosens the always-on condition** … **Note what the pairing is and is not:** it is the value Initialization *writes* for a project that has already graduated routes, not a coupling — a run may sit at `escalation-only` with `plan-gate: always`, and switching `mode:` later never rewrites the field." |
| S1.15 | E L1328–1357 (the `plan-gate:` field paragraph, 30 lines) | **definitional — becomes canonical** | L1328–1332: "The header also carries **`plan-gate:`**, which sets the plan gate's posture (step 5) exactly as `mode:` sets the merge gate's. Two values: `always` — stop for plan approval on **every** issue. `conditional` — stop on step 5's judgment conditions (ambiguous ACs, risk/irreversibility, agent disagreement, a value story that doesn't hold, genuine uncertainty)." L1334–1336: "Under **both**, step 5's always-on condition still fires and its `- Plan-gate:` line is still written. **Absent or unrecognized ⇒ `always`**: a ledger predating this field, or a typo, gets the over-gating reading rather than a silent fallthrough to the looser one." L1338–1345: "Initialization writes it per mode — `calibration` ⇒ `always`, a project with prior route graduation ⇒ `conditional`. **After that the two fields are independent, and this is load-bearing** … Changing `mode:` never re-derives `plan-gate:`, in either direction … Were they coupled, a project that found a mandatory plan stop too heavy could only escape it by loosening its **merge** gate". L1347–1350: "**That independence holds *within* a run.** A **new** run's Initialization re-derives the default from the mode branch, so a `plan-gate:` value a human sets by hand is **not yet carried across runs** … re-set it after init". L1352–1357: "**`plan-gate:` is human-owned.** Initialization writes it once … **The orchestrator never rewrites this field after Initialization** — not at step 5, and not on the observation that recent approvals looked routine. A gate that can switch itself off on its own reading of its own history is not a gate." |
| S1.16 | E L1388–1390 (writes-none path) | citing | "a plan gate that stops (under `plan-gate: always`, the shipped default, that is *every* issue until the human approves)" |
| S1.17 | E L1395 | P5 | "Step 5's `- Plan-gate:` line is written *at step 5*" |
| S1.18 | E L1430–1431 (worked example) | P5 list | `- Plan-gate: n/a: architect skipped (research scaffolding).` / `- Human gate: plan approved by the human (plan-gate: always).` |
| S1.19 | E L1470–1474 (`- Human gate:` definition) | definitional for the line | "Under `plan-gate: always` (the shipped default) every issue stops, so the line reads as an approval by the human and **`plan auto-approved` is never legitimate for this gate** — name the posture, as the worked example does. Under `plan-gate: conditional` an unstopped issue reads `plan auto-approved (<why>)`" |
| S1.20 | E L1476–1500 | P5 canonical (`- Plan-gate:` spellings) | "This is the one enumeration of the spellings; step 5 points here rather than restating them." |
| S1.21 | E L1795–1814 (`- Plan-gate-inferred:`) | operative (trigger, canonical for it) | L1800: "**Step 5 states the rule; this line does not restate it — it reports that the rule fired.**" L1807–1808: "the orchestrator never writes the field outside Initialization". L1812–1814: "It is owed when the run's `queue.md` header carries **no `plan-gate:` field, or a value step 5 does not recognise**." |
| S1.22 | E L1850–1858 (the two remedies) | surfaced text | each ends "*The orchestrator never writes this field outside Initialization, which for this run has already happened.*" |
| S1.23 | E L1874–1878 | operative (W) — REDUCE | "**The orchestrator never writes the `plan-gate:` field outside Initialization.** Read that as written and do not weaken it to 'never rewrites it': on a ledger that never had the field there is nothing to rewrite, and an orchestrator reasoning from the weaker form can talk itself into adding one — freezing a posture the human never chose … This line is a message, never an edit" |
| S1.24 | E L1988–1989 (Resume) | citing | "under `plan-gate: always` every issue stops at step 5 with its row still `planning`" |
| S1.25 | E L2119 (gate table, `Human (plan)` row) | **operative lookup — REWRITE** | "**every issue under `plan-gate: always`** (the default under `calibration`; absent or unrecognized reads as `always`); under `plan-gate: conditional`, if uncertain/irreversible. Under **both**, **always** when the architect materially changed the plan (… neither `mode:`, `plan-gate:`, nor route graduation reaches this one)" |
| S1.26 | E L2122 (Scope ruling row) | citing | "nor by `mode:`, `plan-gate:`, or route graduation" |
| S1.27 | S L80–86 | **stays by design (AC2)** | "**The plan gate stops on every issue unless the ledger says otherwise.** The `queue.md` header's `plan-gate:` field sets this gate's posture, and **an absent or unrecognized value means stop** … Only an explicit `plan-gate: conditional` narrows it, and only to the engine's judgment conditions — so **if you are reading this without `loop-engine.md` loaded, treat the gate as `always` whatever the field says** … `mode:` never narrows this gate in either direction, and the field is the human's — you never rewrite it after Initialization." |
| S1.28 | I L19–30 (Initialization step 4) | operative — this IS the write | "Step 11 reads `mode`/`graduated-routes` to gate **the merge gate**, per route; it never affects the plan gate. **Set `plan-gate:` on the same branch you just took** — `calibration` ⇒ `plan-gate: always`; the prior-graduation branch ⇒ `plan-gate: conditional` … Write it explicitly even though an absent field would read as `always` (step 5): the human tunes what they can see … After init the two are independent — a later `mode:` change never rewrites `plan-gate:`." |
| S1.29 | I L39 (skeleton) | artifact | `_plan-gate: always_         # always | conditional; absent or unrecognized = always` |

Adjacent, outside the brief's file set but restating under the README standing convention:
`README.md` L90 ("under `conditional`, on ambiguity, risk, disagreement or doubt"), L126–128,
L413–420 ("ambiguous acceptance criteria, risk, agent disagreement, a value story that doesn't hold,
or genuine uncertainty … a ledger that doesn't mention the field at all is read as `always`").
`plugins/CLAUDE.md` L48–79 (maintainer notes; not product).

**Tests.** No test pins any posture sentence (`grep -n plan-gate tests/` hits only
`PlanGateFrozenBlockTests`). Two tests bound what an edit may do: `PlanGateFrozenBlockTests`
(`tests/test_repo_consistency.py` L1654–1790) locates the step-5 span by `### 5. Human gate` →
`### 6. Implement` and asserts the frozen heading (E L394–395) appears in it — so S1.5 may shrink
but the `### 5. Human gate` heading must stay the first occurrence and L394–395 untouched;
`PipelineStepOrderTests.test_skill_labels_match_their_engine_headings` (L1254–1296) matches S's
`5 human gate` label to the heading's words by overlap, so keep "Human gate" in the heading.
`PhaseIndexIdentityTests` does not reach any of these.

### 1.2 Semantic deltas

| Δ | Sites | What differs | Behavior changes? | Pinned by |
|---|---|---|---|---|
| **D1.1** (= F57) | S1.7 L362–364 vs S1.15 L1331–1332 vs S1.25 L2119 (+ README L90, L416–418) | The `conditional` stop set: step 5 = 5 items incl. "disagree **or punt**"; Ledger format = 5, punt dropped, "genuine uncertainty"; gate table = **2** ("if uncertain/irreversible"); README L90 = 4 (no value story, no punt); README L416 = 5, no punt. | **YES.** Under `conditional`, an orchestrator consulting the gate table proceeds on ambiguous ACs, a failed value story, disagreement, or a punt. Narrowing = fail-open. | none |
| **D1.2** (new since F58) | Strong: S1.2 L120–121, S1.21 L1807, S1.22 L1853/1857, S1.23 L1874–1878. Weak: S1.15 L1354–1355 "never **rewrites** this field after Initialization"; S1.27 (S L86) "you never **rewrite** it after Initialization". | The write rule. The weak form forbids editing an existing value; the strong form also forbids **adding** the field to a ledger that lacks it. | **YES.** On a pre-field ledger (the common case L349–351 names) the weak form lets the orchestrator add `_plan-gate: always_`, which freezes a posture the human never chose and permanently silences the `- Plan-gate-inferred:` notice (its trigger is "no field"). The canonical home and `SKILL.md` both carry the weak form. | none |
| **D1.3** (= F58 #3) | "the shipped default": S1.11 L1037, S1.16 L1389, S1.19 L1471. "the default under `calibration`" / what Init writes under calibration: S1.5 L338, S1.25 L2119, `plugins/CLAUDE.md` L52. Source of truth: S1.28 (I L23–25) — the default is per mode branch. | Which value is "the default". | No — descriptive parentheticals; the orchestrator reads the field. A reader may wrongly expect a fresh init to always write `always`. | none |
| **D1.4** (= F58 #4) | Absent-only: S1.11 L1037, S1.28 I L26–27, README L419. Unrecognized-only: S1.12 L1271 (citing). Both: S1.5 L353, S1.15 L1335, S1.21 L1813, S1.25 L2119, S L81, I L39. | P3 stated in halves. | No — no site asserts the opposite for the missing half; partial site + full rule compose. | none |
| **D1.5** (= F58 #1) | Qualified: S1.15 L1347–1350 (holds *within* a run; a new run re-derives). Unqualified: S1.5 L347–349, S1.10 L915, S1.14 L1316–1318, S1.15 L1339–1341, S1.28 I L28–29, S L85–86, README L128. | Whether independence is a cross-run promise. | No — every unqualified site is a claim about a `mode:` *change*, true within a run; what the orchestrator does at a new init is unambiguous in I L23–25. Hazard is a human's prediction, not an orchestrator action. | none |
| **D1.6** (= F58 #2) | Imperative: S1.9 L380–381 ("write its `- Plan-gate:` line … whatever the field says"); S1.20 L1480–1481. Passive: S1.15 L1334–1335 ("its `- Plan-gate:` line is still written"). | Actor and scope of the write duty. | No — the orchestrator is the only writer (L1226) and "Under **both**" supplies the scope. It is the #29 round-1 near-miss shape. Both sites are on the P5 list, so neither is removed; the fix is wording. | none |
| **D1.7** (spelling) | S1.7 L364 'note "auto-approved" + why' vs S1.19 L1473 `plan auto-approved (<why>)` vs S1.18 L1431. | Journal spelling of the conditional auto-approval. | Journal only; nothing parses `- Human gate:`. Ledger format is the line's one definition. | none |

Checked and **not** drifted (no delta): P1 at L337, L915, L1291, I L22–23, S L85, README L121 (six
agreeing sites — the most-restated proposition); the init pairing (`calibration` ⇒ `always`,
prior-graduation ⇒ `conditional`) at L338, L344, L1296, L1312, L1338, I L23–25; the
`- Plan-gate-inferred:` trigger (L1813) vs step 5's rule (L353) — both halves, same reading; the
underscore-italic header form (`_plan-gate: always_`) is the skeleton's wrapper for every header line,
not a second spelling.

### 1.3 Rulings

- **D1.1 → step 5's five-item list wins, including "punt".** (a) Step 5 is where the gate executes.
  (b) The would-be canonical passage's own words are "stop on **step 5's** judgment conditions"
  (L1331) — it already delegates; its parenthetical is a paraphrase, and paraphrase is what drifted.
  (c) The widest set is the over-gating direction (unknown ⇒ unsafe). (d) "punt" is load-bearing:
  the Escalation rubric (L1020) still escalates to the human when agents "disagree/punt", and the
  plan-gate list descends from it. Dating: the gate-table clause is the oldest text in play
  (`066ac35`, 2026-07-23, "only if uncertain/irreversible" — written before the field existed); #29
  (`840e6f1`) rewrote the row and carried the two-item clause unchanged; the Ledger paraphrase is
  #29's. The most recent *deliberate* statement of the set is still step 5's.
- **D1.2 → the strong form wins everywhere: "never writes the field outside Initialization."**
  Most recent deliberate change: #108 (`906b2a3` + `59807ad`, 2026-09-05) added it with the reason
  spelled out and the instruction "do not weaken it to 'never rewrites it'" — and did not update
  L1355 or S L86. Fail-safe: an engine that may add the field can silence its own notice. This one
  **must touch `SKILL.md`** (one clause, L86), which #35's AC2 forbids — so it belongs to the
  F58-resolution PR, before #35, not to #35.
- **D1.3 → "the default under `calibration`" (or no parenthetical at all).** Accurate per the
  `reference` unit, which is where the default is actually chosen. All three "shipped default"
  sites and the gate table's "under `calibration`" were born in the same commit (`840e6f1`), so
  there is no later deliberate change to defer to; accuracy decides.
- **D1.4 → the canonical passage carries both halves; operative partial sites gain the other half
  or a pointer; citing sites untouched.** No winner needed — nothing is wrong, only partial.
- **D1.5 → the qualified form is canonical.** It is the later deliberate addition (`7b82d61`,
  #29 round 2) and it is true. Unqualified *operative* sites reduce to "`mode:` never sets this
  gate" + pointer, so none can be read as a cross-run promise; I L28–29 is self-consistent in situ
  (it is the init) and may stay or point.
- **D1.6 → imperative.** Same actor, same scope, stated the way the executing section states it.
- **D1.7 → Ledger format's spelling;** step 5 names the line and points.

### 1.4 The canonical passage (replaces E L1328–1357; 25 lines)

Home: Ledger format → `queue.md`, promoted to a pointable heading so every other site can name one
stable string (the `GatePosturePointerTests` the architect ruled legitimate pins that string,
per region, never a count).

```markdown
#### Gate posture — `mode:` and `plan-gate:`

The header carries two posture fields, and each sets exactly one gate:
- **`mode:`** sets the **merge gate** (step 11) and nothing else — `calibration` (default), the
  human approves every merge; `escalation-only`, graduated routes may auto-merge, subject to the
  always-escalate list and the default-deny close at step 11 (the bullets above).
- **`plan-gate:`** sets the **plan gate** (step 5) and nothing else — `always`, STOP for plan
  approval on every issue; `conditional`, STOP on step 5's judgment conditions, enumerated there
  once (do not re-derive them here). **Absent or unrecognized ⇒ `always`**: a ledger predating the
  field, or a typo, gets the over-gating reading, never a fallthrough to the looser one.
- Under both values step 5's always-on condition still fires: you still take its frozen-vs-live
  diff and write its `- Plan-gate:` line, whatever the field says (step 5).
- **Initialization writes both, once, on the same branch** (the `reference` unit) — `calibration`
  ⇒ `always`; prior route graduation ⇒ `escalation-only` + `conditional`. That pairing is a written
  default, not a coupling: **within a run the fields are independent** — a `mode:` change never
  re-derives `plan-gate:` in either direction, and a run may sit at `escalation-only` with
  `plan-gate: always`. A hand-set value is not carried across runs — a new run's Initialization
  re-derives the default from its mode branch — so re-set it after init. (Coupled, a project could
  escape a mandatory plan stop only by loosening its merge gate, which is the trade the field exists
  to avoid.)
- **Both fields are human-owned after Initialization. The orchestrator never writes `plan-gate:`
  outside Initialization** — not a rewrite at step 5 on the observation that approvals looked
  routine, and not an addition to a ledger that lacks it: there is nothing to rewrite on such a
  ledger, which is exactly the write a weaker "never rewrites" form licenses, and it would freeze a
  posture the human never chose and silence `- Plan-gate-inferred:` (progress.md) for good.
```

(The `mode:` bullets at L1295–1321 — merge-gate semantics and the always-escalate restatement — are
a *third* invariant, the merge-gate list #35's first comment counted at six sites; untouched here.)

### 1.5 Every other site — pointer or keep

| Site | Disposition | Replacement text / reason |
|---|---|---|
| S1.5 E L336–356 | reduce 21 → ~6 lines | "**Read `plan-gate:` from the `queue.md` header. Absent or unrecognized ⇒ `always` ⇒ STOP for plan approval; `always` and `conditional` are its only values; `mode:` never sets this gate, and you never write the field.** Its full semantics — both values, what Initialization writes, the independence from `mode:`, why the default is `always` — are in **Gate posture — `mode:` and `plan-gate:`** (Ledger format → queue.md); do not re-derive them here. Under `always`, whether to stop is not a judgment call; **what you put in front of the human still is** — work through the rest of this step and prepare the always-on condition's frozen-vs-live diff: stopping with the plan but without that diff fails the gate." |
| S1.7 L362–372 | keep; one spelling fix | becomes the one statement of the `conditional` list (D1.1). L364 → 'journal `- Human gate: plan auto-approved (<why>)` (Ledger format → progress.md)'. |
| S1.10 L914–916 | keep, trim the P4 clause | "(step 5's posture comes from `plan-gate:`, which `mode:` never sets — **Gate posture**, Ledger format → queue.md — plus one always-on condition neither reaches)". The always-on aside stays: it is on the P5 list. |
| S1.11 L1036–1039 | keep operative; fix parenthetical | "Under `plan-gate: always` — and under an absent or unrecognized field, which read as `always` (**Gate posture**) — step 5 stops on **every** issue …" |
| S1.12 L1271–1274 | **keep as is** | citing: P3 is the premise of the argument that a Status has no over-gating reading. Reduce it and the argument evaporates. |
| S1.13 L1291–1294 | trim P1 clause to pointer | "The header carries a `mode:` field that gates **the merge gate only** (**Gate posture**, below) — **plus one always-on condition neither field can reach, a material architect rewrite of the plan**. The two modes:" (P5 clause kept; the pairing sentence L1296–1297 kept — on the P5 list). |
| S1.14 L1315–1318 | trim to pointer | "(That pairing is Initialization's written default, not a coupling — **Gate posture**, below.)" The always-on half L1312–1315 stays (P5 list). |
| S1.15 L1328–1357 | **becomes canonical** | §1.4 |
| S1.16 L1389 | keep; drop "the shipped default" | "(under `plan-gate: always`, that is *every* issue until the human approves)" |
| S1.19 L1470–1474 | keep (the line's definition); drop "(the shipped default)" | "Under `plan-gate: always` every issue stops, so …" |
| S1.21/S1.22 L1795–1858 | **keep as is** | a different line (`- Plan-gate-inferred:`); already points ("Step 5 states the rule; this line does not restate it"); the remedy paragraphs are text surfaced to the human. |
| S1.23 L1874–1878 | reduce 5 → 2 lines | "**The orchestrator never writes the `plan-gate:` field outside Initialization** (**Gate posture**, queue.md — which says why the weaker 'never rewrites' reading licenses exactly the write this forbids). This line is a message, never an edit — not here, and not at any later invocation." |
| S1.25 L2119 | rewrite the `conditional` clause | "**every issue under `plan-gate: always`** (the default under `calibration`; absent or unrecognized reads as `always`); under `plan-gate: conditional`, on **step 5's judgment conditions — enumerated there, not here**. Under **both** …" (rest unchanged — the always-on clause is on the P5 list). |
| S1.3, S1.8, S1.9, S1.17, S1.18, S1.20, S1.24, S1.26 | **keep as is** | P5 sites (maintain the list) or citing. |
| S1.27 S L80–86 | **keep by design** (AC2); one clause corrected under D1.2 in the F58 PR | L86 → "and the field is the human's — you never write it outside Initialization." A partial load over-escalates without `loop-engine.md` only because this bullet is complete on its own; a pointer there would be a bare pointer. |
| S1.28 I L22–30 | keep the write instruction and its reason; trim P1/P4 to a pointer | L22–23 "it never affects the plan gate" → keep (one clause). L26–27 → "even though an absent or unrecognized field reads as `always`". L28–29 → "After init the two are independent (**Gate posture**, Ledger format → queue.md)." The `reference` unit is read without the rest of the engine in view at init time? No — core is read in full first, so a pointer resolves. |
| S1.29 I L39 | **keep as is** | the comment travels inside the artifact the human edits; it is the fail-safe line in the ledger itself. |
| README L90, L416–418 | out of #35's scope; flag | D1.1 makes these restatements narrower than the engine (no punt; L90 also no value story). The standing convention says a plan-gate posture change updates the README in the same PR; a fix to F57 is such a change. Decision for the human. |

### 1.6 Bytes (invariant 1)

Measured (`sed -n | wc -c`): S1.5 1,740 → ≈640 (−1,100); S1.13 P1 clause ≈ −110; S1.14 P4 sentence
≈ −240; S1.15 2,245 → ≈2,300 (+55, it absorbs the strong write rule and its reason); S1.23 478 →
≈230 (−250); S1.11/S1.16/S1.19 parentheticals ≈ −30; S1.25 ≈ +20; S1.7 spelling +40; I L26–29 ≈ −40.
**≈ 1.65 KB removed from the engine (≈ 17 lines of 2,535), `SKILL.md` ±0.** The plan's "~150 lines"
counted P2/P3 deletions that the citing-site rule and the P5 list forbid; this is the honest number.

---

## Invariant 2 — gate-outcome

Properties in the brief: no verdict ≠ pass; the `- gate-error:` / `- gate-fallback:` shapes and when
each applies; a missing journal line is unknown — never `0`, never a pass. The currency clause
(E L2208–2262) is part of the same invariant but a separate property, partly guarded
(`CurrencyExemptionAgreementTests`), and is touched here only where a delta reaches it.

### 2.1 Sites, verbatim (trimmed)

| # | Where | Class | Operative text |
|---|---|---|---|
| S2.1 | E L42–55 (*What holds without each unit loaded*) | **fail-safe halves — keep by design** (D001/PRD: "the fail-safe half of each deferred unit stays in core") | "`accepting` — the acceptance gate (step 10) cannot run without the unit, so it has no verdict and the row cannot merge: journal a `- gate-error:` and escalate to the human (Gate-outcome invariant)." "`reviewing` — … every one is BLOCKING … Journal a `- gate-error:`, escalate to the human, and do not merge." "`reference` — … STOP and tell the human." |
| S2.2 | E L414–415 (step 5) | citing | "where the binding is unrunnable, the inline composition you run in its place (Gate-outcome invariant) **is** an architect pass in substance" |
| S2.3 | E L466–470 (step 6) | operative | "**each command's exit status is its verdict**: a non-zero exit is not green however the output reads" |
| S2.4 | E L562–567 | operative + pointer | "**Every iteration leaves a record of this gate** — a `- Hermetic:` line … or, where the gate produced no verdict at all, the `- gate-error:` that carries it instead" |
| S2.5 | E L569–579 (four config states) | **canonical for the four states** (L2163: "tabulated once, at the gate itself; this is the rule, that is the table") | L578: "`—` with no reason → a blank … on a row the trigger fired on, escalate". L579: "`TODO`-valued, **or the row is absent** → on a row the trigger fired on, **unknown — which is not the same as not-due**: static 'cannot run' (Gate-outcome invariant), no inline composition exists, so **escalate to the human**. On a row it did not, write the trigger's own `n/a` reason" |
| S2.6 | E L581–593 | operative, gate-specific | "**Neither outcome is a pass** … **The wrapper failed before the tier started** … No test was executed, so there is no verdict about the tier: `- gate-error:` and **escalate** … **Anything else** — the tier ran … **blocks** … **If you cannot tell which you have, treat it as the `- gate-error:`.**" |
| S2.7 | E L660–661 | citing | "**do not journal it as a gate outcome.** It produces no verdict, so it cannot be recorded as one (Gate-outcome invariant)" |
| S2.8 | E L694–700 (step 8 not loaded) | operative literal + pointer | "Journal `- gate-error: code-review — phases/reviewing.md not loaded — <first line of the error>` (or `no-stderr` where the read raised none), escalate to the human, and do not merge" |
| S2.9 | E L728–730 | operative | "**A round that owes this lens and does not carry it has produced no verdict.** … if you cannot, `- gate-error:` and escalate (Gate-outcome invariant). It is not a round that passed with a gap." |
| S2.10 | E L815–836 (scope ruling, binding states) | operative, gate-specific | "**No state of the binding excuses the stop.** … **No inline composition substitutes here, and that is scoped per *use*, not per binding:** the plan gate's inline architect composition (step 5) does not reach this consult … This use therefore defines no fallback, which puts it on the Gate-outcome invariant's **stopped-and-escalated** branch … **static**ally unusable … write `- gate-error: scope-ruling — DESIGN_AGENT <unbound | TODO-valued | uninvocable> — no-binding` … **Where the agent ran and failed** … `- gate-error: scope-ruling — DESIGN_AGENT — <first line of the error>`, or `no-stderr` … **Never `no-binding` for a binding that was fine** … And **never `- gate-fallback:`**, which Guardrails excludes from the repeat check" |
| S2.11 | E L844–851 | operative (an exception to the invariant) | "**There is deliberately no dedicated `- Scope-ruling:` *disposition* line, and none is owed when this gate is not due** — the Gate-outcome invariant's not-run journalling does not reach this row, because a not-due spelling would be a claim in its own right … **The `- gate-error:` line above is untouched by this** … *if you cannot tell whether this gate was due, it was — consult and stop.*" |
| S2.12 | E L878–885 (step 9) | pointer | "**which gates a post-gate change re-arms, and from which sources, is the Gate-outcome invariant's currency clause**" |
| S2.13 | E L891–893 (step 10 not loaded) | operative literal + pointer | "`- gate-error: acceptance — phases/accepting.md not loaded — <first line of the error>` (or `no-stderr` …), escalate to the human, and do not merge" |
| S2.14 | E L895–911 | operative (currency applied) | "**do not merge on the earlier verdicts** — a gate that never saw a change has not passed it (Gate-outcome invariant). A fix that changes **no** source — a citation, a doc line — re-arms nothing" |
| S2.15 | E L942–954 (merge gate, `- Editorial:` read) | operative | "**No `- Editorial:` line on an iteration whose step 8 closed ⇒ unknown, never `0`** … Unknown is not a count you may report: say so and **escalate**." |
| S2.16 | E L962–964 | operative | "green **on the commit you are about to merge** … (Gate-outcome invariant → currency)" |
| S2.17 | E L1041–1044 (Escalation rubric) | **pure pointer — the model** | "**A gate that produced no verdict does not get reasoned about here.** … apply the **Gate-outcome invariant (evidence-bound pass)** under Gates … Do not paraphrase those branches from memory; they differ, and the difference is the rule." |
| S2.18 | E L1047–1056 (Guardrails) | operative | "**Stuck = the same error SIGNATURE recurs** … **A `- gate-fallback:` line is likewise not a stuck signature** … `- gate-error:` lines *are* in scope. On a genuine repeat: stop, escalate, mark `blocked`, move on." |
| S2.19 | E L1188 | citing | "treats a declined choice as a gate-error rather than a quiet proceed. Neither is configurable." |
| S2.20 | E L1241–1243 | definitional (Status) | "`blocked` (an unmet in-run dependency; `blocked: too-large` …; or a recurring `gate-error:` awaiting a config repair — see the Gate-outcome invariant)" |
| S2.21 | E L1259–1261 | operative (recognizer) | "`gate-error:` are **Notes** values, not statuses — a gate-errored row's Status is plain `blocked` (Gate-outcome invariant)" |
| S2.22 | E L1444–1451 (the two fixed-shape lines) | definitional for the shapes | "Two further fixed-shape lines are appended **only when a gate produced no verdict** (Gate-outcome invariant — that section defines when each applies and what follows): `- gate-fallback: <gate> — <the binding defect> → ran <what you substituted>` … Guardrails excludes it from the repeat check … `- gate-error: <gate> — <failing tool or command> — <first line of the error>` — … the iteration STOPPED. This one **is** a stuck signature … elide volatile arguments (PR numbers, SHAs, paths)." |
| S2.23 | E L1453–1468 (`- Hermetic:` spellings) | definitional for the line | L1466–1468: "**no `- Hermetic:` line at all** — the gate produced no verdict, so a `- gate-error:` carries it instead and the iteration stops. Three states reach here, all of them on a row the trigger DID fire on: bound but unable to execute; `—` with no reason; and absent or `TODO`-valued." |
| S2.24 | E L1502–1507 | operative (the carve-out where the spelling is chosen) | "**An absent or `TODO`-valued binding is never an `n/a: no offline/hermetic tier declared`** … On a row the trigger fires on it is unknown, unknown is due, and it takes the fourth path. On a row the trigger never fired on, write the trigger's own reason … a missing binding does not make a gate due that nothing else made due" |
| S2.25 | E L1535–1537 | definitional (line) | "**`round <n> — no verdict`** — the round produced none; a `- gate-fallback:` or `- gate-error:` line carries what happened (Gate-outcome invariant). Never write a range here" |
| S2.26 | E L1598–1600 | definitional (line) | "**no `- Editorial:` line at all** — on an iteration whose step 8 closed, **unknown, and unknown is not '0'.**" |
| S2.27 | E L1622–1635 | definitional (line) + citing | "a due pass that applied zero mutations is a harness error … that takes a `- gate-error:`, never this line" / "**no `- Restore:` line at all** — **unknown, and unknown is not clean.** … exactly as the Gate-outcome invariant requires of any gate whose absence would otherwise read as a pass" |
| S2.28 | E L1707–1733 (`mutation-survivors` `n/a` list) | operative + citing | "an unrunnable `TEST_CMD` is a `- gate-error:`; … [a declined in-tree fallback] is **also** a `- gate-error:` … the pass was due and produced no verdict, which is not the same as never being due. … The `n/a: <reason>` spelling follows the Gate-outcome invariant's not-run vocabulary" |
| S2.29 | E L1734–1737 | definitional (slot) | "**omitted** — **unknown** … must **never** be read retroactively as 'the pass was scoped out'" |
| S2.30 | E L1781–1787 | definitional (slots, general) | "**an absent slot does not mean zero** … Where a slot's procedure exists but was **not due** on this row … write `n/a: <reason>` rather than omitting … So three states stay distinguishable: a value, a visible not-due, and an omission that means only 'unknown'." |
| S2.31 | E L2120 (gate table, Build commands row) | operative lookup | "`HERMETIC_TEST_CMD` additionally requires Route `code` **and** a change that adds or modifies a test, **whatever the binding says** — on such a row an absent or `TODO` binding is unknown, and unknown is due (the gate's four-state table) \| **exit status per command**; non-zero blocks" |
| S2.32 | E L2127–2141 | **canonical (scope, due-ness, not-due)** | "Applies to every gate in the table above that returns a verdict **or a ruling** — the scope ruling returns the latter and certifies nothing, and it is inside this invariant for its journalling forms, never as a gate that may be recorded as passed — **on the rows that gate is due on** — due-ness is decided by the gate's **When** entry … and … the Routing table's per-route column, **both in this file** … A gate the route or its trigger condition never made due was never owed a verdict, so journal it as not run (`skipped` / `n/a`) with the reason; not-due is not a pass either. An explicit `—` **plus a reason** in the config is a deliberate 'not applicable', journalled `n/a: <that reason>` — **not** an absent binding; it is the only way a config marks a gate not-due" |
| S2.33 | E L2143–2155 | canonical (build commands) | "each is `n/a` only with `—` plus a reason, and an unrunnable one is a `- gate-error:` … `LINT_CMD`/`TYPE_CMD`/`TEST_CMD` run on every issue and the iteration cannot reach step 7 until each exits zero, so *the absence of a `- gate-error:` naming one is the record that it passed*. **A `—`-plus-a-reason build command is the exception and is written out**, as `- Lint: n/a: <reason>` (likewise `- Type:`, `- Test:`) … Absence means 'it ran and the iteration got past it'; it never means 'it was not due'." |
| S2.34 | E L2157–2166 | canonical (carve-out, both halves) | "For that gate an absent or `TODO`-valued row reads as **unknown, and unknown is due** — never as 'the trigger never made it due' … It applies only where the gate's own trigger fired: a missing binding never makes a gate due that nothing else made due. Its four config states are tabulated once, at the gate itself … An **unbound** row … write the literal `- gate-error: hermetic — HERMETIC_TEST_CMD unbound — no-binding`" |
| S2.35 | E L2168–2184 | canonical (no verdict; static/dynamic) | "**No verdict ⇒ not passed** … The discriminator is **what you can see without running it** … **Cannot run (static)** … Fall back to the engine's inline composition where one is defined, otherwise escalate to the human. Step 8 is this branch's worked instance … **Ran and errored (dynamic)** … Do **not** substitute a home-composed check, and do **not** journal it as passed. **Escalate to the human.**" |
| S2.36 | E L2186–2204 | canonical (journal forms, stuck, row status) | "**Fell back and continued** (static, an inline composition exists) → append `- gate-fallback: …` … a **substitution record, not a stuck signature** … **Stopped and escalated** (dynamic, or static with no fallback defined) → append `- gate-error: …`, **before** you stop … **elide volatile arguments** … Write `no-stderr` where the failure emitted none. A **first** failure leaves the row at its current pipeline status, taking **no** terminal … **and no resting** … status … A **recurring** signature is *stuck* (Guardrails) → mark the row `blocked` with Notes `gate-error: <gate>` … step 1 never re-selects it … **If that row already has an open PR, do not 'move on' to another row** — one PR at a time still binds; report and STOP." |
| S2.37 | E L2206 | canonical (one-liner) | "**A gate that did not run — static or dynamic — is never recorded as a gate that passed.**" |
| S2.38 | E L2208–2262 | currency clause | untouched here except as D-rows reach it; `CurrencyExemptionAgreementTests` pins L2250–2251 against L900–901. |
| S2.39 | E L2353 | citing | "(… the `reviewing` unit; not loaded ⇒ no verdict)" |
| S2.40 | E L2408–2412 | citing | "Reaching the cap is also not a verdict: an escalated gate has still returned no pass, so the Gate-outcome invariant governs what may be journalled. It does not mark the row `blocked`" |
| S2.41 | E L2433–2438 | citing | "Under the Gate-outcome invariant a pass that returns no verdict is **not passed** … **no verdict is worthless and costs the same.**" |
| S2.42 | S L106–116 | **stays by design** | "**A gate that did not run is never recorded as one that passed.** Journal a gate as passed only with its own verdict as evidence — **no verdict ⇒ not passed.** An unbound, `TODO`-valued, or uninvocable binding is not permission to skip the gate: fall back to the engine's inline composition where it defines one, otherwise escalate. A gate that ran and *errored* never falls back — escalate, and never journal it as clean. **A verdict is bound to the commit it ran on** … Never merge on a verdict describing an earlier tree." |
| S2.43–48 | A L78–83, L284–296, L407–408; R L28–34, L152–176, L382–387 | unit operative literals | `$BASE` empty → gate-error, no round consumed; `- gate-error: acceptance (Class B) — isolated copy unusable: <…> — <first line of the error>`; exit 2 → gate-error STOP, exit 3 → "never `=0` … never `n/a`"; a `disable-model-invocation` `CODE_REVIEW` → run the finder procedure, `- gate-fallback:`; `roster: no verdict`; "An absent declaration is unknown, and unknown is a full round — never 'the condition did not fire', which is the fail-open reading the Gate-outcome invariant already refuses for `HERMETIC_TEST_CMD`." |

Adjacent: README L43–45, L504–510 (consistent); `init-loop.md` L235, L246–247 (consistent — and
the `DESIGN_AGENT` row states the per-use `—` rule: not-applicable at the architect gate, never an
off switch for the scope ruling); `plugins/CLAUDE.md` L21–44.

**Tests.** `PhaseIndexIdentityTests` (L1791–1941) pins S2.1's **unit set** against the phase-index
table (marker `**What holds without each unit loaded.**`, bullets `^- \`unit\``) — never its posture.
`CurrencyExemptionAgreementTests` (L2722–2852) pins S2.14's exemption list against S2.38's.
`MutationNaReasonTests` (L1444–1653) reaches S2.28's `n/a` list. `DeltaScopedRoundNotationTests`'
`_LEDGER_REGION` (L2603) pins the `- Code-review:` paragraph around S2.25. Nothing pins the
`- gate-error:`/`- gate-fallback:` shapes, the static/dynamic branches, the carve-out, or any
absent-line rule (`grep -n 'gate-error\|gate-fallback\|no verdict' tests/` → two docstring mentions
only).

### 2.2 Semantic deltas

| Δ | Sites | What differs | Behavior changes? | Pinned by |
|---|---|---|---|---|
| **D2.1** | S2.18 L1053–1054 "On a genuine repeat: stop, escalate, mark `blocked`, **move on**." vs S2.36 L2203–2204 "**If that row already has an open PR, do not 'move on' to another row** — one PR at a time still binds; report and STOP." | What follows a recurring `gate-error:` on a row with an open PR. | **YES.** Guardrails sends the orchestrator to select the next row — a second PR, i.e. the stacked PR its own first sentence forbids. Gates says STOP. | none |
| **D2.2** | S2.34 L2164–2165 (a literal for **unbound** only) vs S2.5 L579, S2.23 L1468, S2.34 L2159–2160 (absent **or `TODO`-valued**, and `—` with no reason, all take the same path) vs S2.10 L827 (the scope-ruling analogue enumerates `<unbound \| TODO-valued \| uninvocable> — no-binding`). | The `- gate-error: hermetic` spelling for a `TODO`-valued row or a bare `—`. Unstated. | Journal spelling — but Guardrails greps signatures across rows, so an invented spelling for the `TODO` case may never read as recurring and the config defect is re-surfaced as fresh each time. | none |
| **D2.3** | S2.32 L2128–2130 "inside this invariant for its journalling forms" + L2137–2138 "journal it as not run (`skipped` / `n/a`) with the reason" vs S2.11 L844–846 "none is owed when this gate is not due — the Gate-outcome invariant's not-run journalling does not reach this row". | Whether a not-due scope ruling writes an `n/a` line. | Journal spelling: the invariant read alone yields a `- Scope-ruling: n/a` line on every round with no design-question finding — the line #114 (`bf15770`, `1bd4938`, 2026-09-10) deliberately cut and then settled as "none owed". | none |
| **D2.4** | S2.35 L2174–2175 "Fall back to the engine's inline composition **where one is defined**, otherwise escalate" (the only defined composition is step 8's finder fan-out: L2175–2177, R L28–34) vs S2.2 L414–415, S2.10 L821–822 "the plan gate's inline architect composition (step 5)", S2.28-adjacent L1496 "the inline composition that substitutes for an unrunnable binding" — plus S L93 "counting any inline substitute for an unrunnable binding" — four sites that presuppose an inline **architect** composition exists; none defines one, step 4 (L276–277) says the agent "has no prompt template of its own", and `init-loop.md` L247 names the finder fan-out as "the engine's inline default" — the only one (swept: core, both units, `reference`, `SKILL.md`, README, `init-loop.md`). | What the plan-informing architect gate does when `DESIGN_AGENT` is unbound or `TODO`-valued (not `—` + reason, which is not-due). | **YES.** Following the three references, the orchestrator composes an architect pass itself, journals `- gate-fallback:`, and continues. Following the invariant strictly, nothing is "defined", so it escalates. The two readings differ on every triggered issue of a fresh consumer whose `DESIGN_AGENT` is still `TODO(init-loop)`. | none |
| **D2.5** | S2.22 L1446, L1449 vs S2.36 L2189, L2194 — the two shape strings, stated verbatim twice; volatile-argument examples differ (L1451 "PR numbers, SHAs, paths" vs L2196 "PR/issue numbers, SHAs, branch names, temp paths"); `no-stderr` stated only at L2198. | Nothing today — identical strings. | No — but it is exactly the unguarded coupling `CurrencyExemptionAgreementTests` was written for one section over, and the examples have already drifted. | none |
| **D2.6** | "Absent ⇒ unknown, never `0`, never a pass" is stated per line — S2.15/S2.26 (`- Editorial:`), S2.27 (`- Restore:`), S2.29/S2.30 (Budget slots), S1.21 L1868–1872 (`- Plan-gate-inferred:`), E L451–455 and L1997–1999 (`- Plan-gate:`) — and **never once generally**; S2.33 L2150–2153 states the one exception (`LINT`/`TYPE`/`TEST`: absence of a `- gate-error:` naming one **is** the record it passed). | No two sites disagree about the same line. | No, today. Append-class hazard: the next journal line someone adds inherits no absence semantics unless its author restates them; and the one exception is reasoned at its site but not named as an exception anywhere general. | none |
| **D2.7** | S1.18 L1435 `Security: n/a (no deps added)` vs the rule's `n/a: <reason>` (S2.32 L2139–2140, L1433 `- Hermetic: n/a: research route`, L1461, S2.30 L1785). | `n/a` spelling in the worked example. | No — nothing parses `Security:`. But the worked example is what gets copied. | none |

Checked and **not** drifted: S L107–110 vs L2173–2182 (static → fallback-where-defined else
escalate; dynamic → never falls back) — same; S L110–116 vs L2235–2238 (the four re-arm sources) —
same; "unit not loaded" is dynamic (an attempted read) and its literals carry `<first line of the
error>` / `no-stderr` accordingly (L697, L892) — consistent with L2178–2182; the row-status rules
(first failure → stays; recurring → `blocked`, Notes `gate-error:`; never re-selected) at L191,
L1241–1243, L1259–1261, L2198–2204 — consistent; `—` + reason semantics at L577, L1461–1465,
L2139–2141, `init-loop.md` L246 (per use) — consistent; A L285's gate token `acceptance (Class B)` vs
L892's `acceptance` name different failures of the same gate and both conform to the shape.

### 2.3 Rulings

- **D2.1 → Gates wins.** Later deliberate change (`3a9772f`, 2026-08-05, #21's own review round
  added the open-PR clause); the Guardrails sentence is `066ac35` port text that predates the
  invariant; and Guardrails' *first* sentence is "One PR at a time", which "move on" violates. Fix
  L1053–1054: "On a genuine repeat: stop, escalate, mark `blocked` with Notes `gate-error: <gate>`
  — and move on only if the row has no open PR (Gate-outcome invariant); otherwise report and STOP."
- **D2.2 → generalize the literal to the scope-ruling idiom**, the more recent (`#114`) and
  default-deny form: `- gate-error: hermetic — HERMETIC_TEST_CMD <unbound | TODO-valued | — with no
  reason> — no-binding`. One spelling per static state, grep-stable, nothing invented.
- **D2.3 → step 8 wins; the invariant names the exception.** #114 is the most recent deliberate
  change and its commit titles say what it decided ("cut the scope-ruling ledger line"; "settle what
  a not-due scope ruling records"). The invariant's "inside … for its journalling forms" is amended
  to "for its `- gate-error:` form; it owes no not-due line (step 8)".
- **D2.4 → escalate; strike the three references to an undefined composition.** The invariant's
  rule is right as written and default-deny: a composition nobody can point to does not exist. The
  alternative — define an inline architect composition — is a product decision (it would need a
  freeze, a verdict-first self-review against `ARCHITECT_TRIGGERS`, a recorded outcome, and a
  `- gate-fallback:`), and the engine's own argument at L822–824 (an orchestrator composing its own
  ruling is the self-assessment the gate exists to remove) cuts against it as hard at step 4 as at
  step 8. Dating does not rescue the references: #114 (`919bae0`/`dda837c`) wrote two of them
  *while contrasting* the scope ruling with a step-5 composition it assumed rather than checked.
  Rewrites: L414–415 → "where the binding is unrunnable there is no inline substitute at this gate
  — escalate (Gate-outcome invariant)"; L821–822 → drop the parenthetical contrast; L1496 → drop
  "and not as the inline composition that substitutes for an unrunnable binding"; S L93 → "counting
  an inline substitute, if this engine ever defines one" (a `SKILL.md` clause, so — like D1.2 — it
  belongs to the F58 PR, not to #35). **Flag for the human**: this is the one ruling that changes what a `TODO(init-loop)` consumer experiences on day
  one (a stop instead of a self-composed review), which is the F14 posture and the safe one.
- **D2.5 → Ledger format holds the shapes; the invariant owns the semantics and points for the
  shape.** This is the engine's idiom for every other line ("the one enumeration of the spellings;
  step 5 points here"). Move `no-stderr` and the volatile-argument examples next to the shapes
  (one list), and let the invariant say "in the fixed shapes Ledger format → progress.md
  enumerates". Alternatively pin the two against each other with a test; the idiom is cheaper.
- **D2.6 → state the reader's rule once, in the canonical passage, with its one exception named
  as an exception.** Per-line sites keep their operative sentence (each is where the line is
  defined) and may point.
- **D2.7 → `Security: n/a: no deps added`.** The rule's spelling; the example is on the P5 list,
  but this line is not P5 content.

### 2.4 The canonical passage (replaces E L2127–2207; 25 lines)

Everything below is a rule carried over from L2127–2207. Dropped: three worked instances (step 8's
misbinding — already at R L28–34; the AC-verifier's `$BASE` — already at A L78–83; "the
host-specific instance lives in `loop.config.md`, do not copy a host's error string into this
engine" — a maintainer instruction, which belongs in `plugins/CLAUDE.md`), the `mutation-survivors`
aside (citing), and the two shape strings (D2.5). Relocated: `- Lint: n/a: <reason>` (likewise
`- Type:`, `- Test:`) to Ledger format → progress.md beside `- Hermetic:`; the hermetic literal
(D2.2) to the `- Hermetic:` no-line bullet (L1466–1468). The currency clause (L2208–2262) stays as
its own clause, unchanged.

```markdown
**Gate-outcome invariant (evidence-bound pass).** Binds every gate in the table above, the scope
ruling included (a ruling is never a verdict), on the rows it is due on. **Due-ness** is the gate's
own **When** cell plus, where that column speaks to the gate, the Routing table's per-route column —
both in this file; a row may fix its own due-ness outright and says so (Scope ruling). One carve-out:
`HERMETIC_TEST_CMD`'s due-ness is knowable only from its binding, so on a row its trigger fired an
absent or `TODO`-valued row is **unknown, and unknown is due** — never "the trigger never made it
due"; a missing binding never makes a gate due that nothing else made due (four states: step 6).
- **Not due ⇒ not a pass.** Journal it as not run (`skipped` / `n/a`) with the reason. A config
  marks a gate not-due in exactly one way — `—` **plus a reason**, journalled `n/a: <that reason>` —
  and that is never an absent binding. The scope ruling owes no not-due line at all (step 8).
- **Due ⇒ passed only on the gate's own verdict.** No verdict ⇒ not passed, by one of two routes,
  discriminated by what you can see **without running it**: **static** — by inspection the binding
  is absent, `TODO`-valued, or names something your toolset lacks or you may not invoke → run the
  inline composition this engine defines for that gate (step 8 defines its finder fan-out; one no
  step defines does not exist), else escalate; **dynamic** — attempted, no verdict (a non-zero exit,
  a tool error, a missing precondition) → no home-composed substitute, never journalled passed: escalate.
- **Journal either way, in the two fixed shapes Ledger format → progress.md enumerates.** Fell back
  and continued → `- gate-fallback:`, a substitution record excluded from the repeat check; surface
  the config defect every time. Stopped and escalated → `- gate-error:` **before** you stop, a stuck
  signature: a first failure leaves the row at its pipeline status (no terminal, no resting status,
  so Resume re-enters it); a recurring one (Guardrails) → `blocked`, Notes `gate-error: <gate>`,
  never re-selected; a row with an open PR is reported and STOPPED on, never moved past.
- **An absent line or slot reads as unknown — never `0`, never a pass** — with one reasoned
  exception: `LINT_CMD`/`TYPE_CMD`/`TEST_CMD` run on every issue and the iteration cannot pass step
  6 until each exits zero, so absence of a `- gate-error:` naming one is the record it passed.
```

### 2.5 Every other site — pointer or keep

| Site | Disposition | Replacement text / reason |
|---|---|---|
| S2.1 L42–55 | **keep by design** | the fail-safe half of each unit, in core (D001; PRD S2/S3; `PhaseIndexIdentityTests` pins the unit set). A unit's absence must resolve without the Gates section being re-derived. |
| S2.5, S2.6 L569–593 | **keep** | the four-state table is canonical by the invariant's own words; the wrapper-vs-tier discriminator is gate-specific and operative. |
| S2.8, S2.9, S2.13 | **keep as is** | already operative literal + pointer — the target shape. |
| S2.10 L832–836 | trim 5 → ~3 lines | "**Never `no-binding` for a binding that was fine, and never `- gate-fallback:`** — Guardrails reads these signatures across rows and excludes fallbacks from the repeat check (Gate-outcome invariant), so either misspelling sends the human to repair a healthy config or lets a `TODO(init-loop)` default read as handled forever." L821–822 loses its contrast per D2.4. |
| S2.11 L844–847 | keep; first sentence points | "**There is deliberately no `- Scope-ruling:` disposition line, and none is owed when this gate is not due** — the one gate the Gate-outcome invariant's not-run journalling names as owing none. Two consequences …" (L847–851 unchanged). |
| S2.17 L1041–1044 | **keep as is** | the model pointer; it already refuses to paraphrase. |
| S2.18 L1047–1056 | keep; fix D2.1 | wording in §2.3. |
| S2.22 L1444–1451 | **keep; becomes the one statement of the shapes** | add after L1451: "Write `no-stderr` where the failure emitted none; a `no-binding` third slot names a binding that was never attempted (the hermetic and scope-ruling literals)." |
| S2.23 L1466–1468 | keep; add the literal | append: "— spelled `- gate-error: hermetic — HERMETIC_TEST_CMD <unbound \| TODO-valued \| — with no reason> — no-binding` for the static states, and with the wrapper's first error line for a bound command that could not execute." |
| S2.24 L1502–1507 | **keep as is** | both halves of the carve-out where the spelling is chosen; `plugins/CLAUDE.md` L39–44 forbids tidying either half away. |
| S2.30 L1781–1787 | keep; may point | "(the Gate-outcome invariant states the general reading once)". |
| S2.31 L2120 | **keep as is** | lookup surface; already operative + pointer. |
| S2.32–S2.37 L2127–2207 | **becomes canonical** | §2.4 |
| S2.38 L2208–2262 | **keep as is** | currency; separately pinned. |
| S2.2, S2.7, S2.19, S2.20, S2.21, S2.27, S2.28, S2.29, S2.39, S2.40, S2.41 | **keep as is** | citing or per-line definitional; never reduce. (S2.2 and L1496 change only under D2.4.) |
| S2.42 S L106–116 | **keep by design** | fail-safe list; complete on its own. No clause needs correcting (unlike invariant 1's L86). |
| Units S2.43–48 | **keep as is** | read at the point of use with core loaded; each carries its gate-specific literal. |
| `plugins/CLAUDE.md` | gains one line | the "do not copy a host's error string into this engine" maintainer caution, relocated. |

### 2.6 Bytes (invariant 2)

Measured: L2127–2207 = 7,233 bytes (81 lines). Canonical ≈ 2,450 (24 lines); relocations +≈250
(`- Lint: n/a:` spelling and the hermetic literal into Ledger format) and +≈200 into
`plugins/CLAUDE.md` (does not ship). S2.10 ≈ −200; S2.11 ≈ −80; D2.1 fix +≈60; S2.22 additions
+≈200; D2.4 strikes ≈ −150. **≈ 4.6 KB removed from the engine (≈ 48 lines).**

**Conservative variant.** If the human prefers to keep L2127–2207 at its current length (it is the
highest-blast-radius prose in the product and the 81→24 compression is the one edit here whose
"no semantic change" can only be certified by reading), apply only D2.1–D2.7 as point fixes:
**≈ 0.3 KB net**, no deletion.

---

## Totals and sequencing

| | Deltas | Behavior-changing | Bytes recoverable |
|---|---|---|---|
| Invariant 1 | 7 (D1.1–D1.7) | **2** — D1.1 (F57: the gate table's two-item `conditional` set) and D1.2 (the weak "never rewrites" form at the canonical home and in `SKILL.md`, post-dating F58) | ≈ 1.65 KB |
| Invariant 2 | 7 (D2.1–D2.7) | **2** — D2.1 (Guardrails "move on" past an open PR) and D2.4 (an inline architect composition three sites cite and none defines) | ≈ 4.6 KB (≈ 0.3 KB conservative) |
| Both | 14 | 4 | **≈ 6.2 KB of 200,789 (≈ 3.1%)**, or ≈ 2 KB conservative |

Of the five F57/F58 items, four are confirmed as filed (D1.1, D1.3, D1.4, D1.5, D1.6 — F58's four
plus F57); the behavior-changing ones were not among them except F57. The four new ones (D1.2, D2.1,
D2.3, D2.4) all post-date or were missed by the 2026-08-18 survey; D1.2 and D2.3 were *created* by
later deliberate changes (#108, #114) that updated some sites and not others — F59's mechanism,
observed twice more.

**Order of work, per the deferral comment's precondition.** (1) One PR resolving the four
behavior-changing deltas as point fixes — D1.1 (gate table + Ledger parenthetical → pointers at
step 5), D1.2 (L1355 and S L86 → strong form), D2.1 (Guardrails), D2.4 (strike three references) —
plus the spelling/voice fixes D1.3, D1.6, D1.7, D2.2, D2.3, D2.7; README L90/L416 under the
standing convention. Every site then says the same thing. (2) #35 proper, as the refactor its charter
promises: promote §1.4 and §2.4, reduce the operative sites to the pointers in §1.5/§2.5, add
`GatePosturePointerTests` anchored per region on the string `Gate posture — \`mode:\` and
\`plan-gate:\`` in the step-5 span, the step-11 span, the queue.md section, the
`- Plan-gate-inferred:` subsection, the gate table, and `initialization.md` — and, for invariant 2,
on `Ledger format → progress.md` inside the invariant's journal bullet. Neither test pins a
fail-safe operative line; that stays review's, as the architect said.
