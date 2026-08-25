# Core self-sufficiency audit

**Date:** 2026-08-25 · **Subject:** `docs/research/draft-core.md` · **Method:** architect pass,
every cross-reference in the drafted core that resolves a **safety decision**, checked for whether
its referent is inside core.

A reference "resolves a safety decision" if the orchestrator must follow it to decide whether a gate
is due, whether a gate passed, whether to stop or proceed, whether something may merge, what a
status means, or what a hard limit forbids. Informational pointers are out of scope.

---

## Verdict

**27 safety-resolving references. 6 genuine failures, all clustering on B1 and B2. No others.**

Self-sufficient in core today, needing nothing: the Escalation rubric, Guardrails, **the entire Tool
surface and Execution policy** (hard limits, isolation duties, the staging window), the **currency
clause**, the **convergence/resting classifier**, the **merge-gate posture**, the **always-on
plan-gate stop**, and every gate's due-ness in the Gate table's *When* column.

The failures:

| # | reference | referent | decision at risk |
|---|---|---|---|
| 3 | "Resume before selecting (see the Resume procedure below)" | Resume | how to reconcile an interrupted row — what makes one-PR-at-a-time hold across `/clear` |
| 4, 5, 8 | "the three Status sets are closed", the classification rule, "Route and Status are distinct" | status vocabulary | what a status *means* and which are recognised — **the language the fail-safe invariants are written in** |
| 7, 18 | "Run the Router (below)", "returns to selection when its dependency closes" | Router | route assignment → which gates are due |
| 20 | Architect row: "recorded wherever this project records architect decisions (Resume)" | Resume | where the architect verdict lives — load-bearing for the plan-gate diff on resume |
| 21 | "due-ness is decided where it always was (**the gate's own step** and the Routing table)" | steps 3–12 | **the Gate-outcome invariant's central predicate**, resolving against deferred text |
| 27 | phase-index `reference` row naming `reference/resume.md`, `reference/router.md` | — | mechanical consequence: those filenames stop existing once B2 lands |

Two AMBIGUOUS, neither requiring repair: Initialization (#1 — its fail-safe, *absent `plan-gate` ⇒
`always`*, is in core, so an unloaded Initialization **over**-gates) and the `- Budget:` grammar
(#6 — see the refinement below).

---

## The finding that changes the near-term plan

**`draft-core.md` audits the seven-unit *target*. The revised increment is a different core.**

Deferring only `accepting` plus a `reference` appendix keeps the status vocabulary, `queue.md`
header semantics, Router and Resume in core **by construction**. So:

> **For the increment, B2's four moves are unnecessary — those sections never leave core. Only B1's
> reword and the B3 guard are load-bearing on day one.**

**Decide which core is shipping before doing B2's moves, or you will move text the increment was
going to keep.**

And the increment's one deferral is the safest available: **`accepting` strands no decision.** Its
due-ness is in the Gate table; its fail-safe — *cannot run ⇒ cannot merge ⇒ human* — is in the phase
index. Core points deep into `accepting` only from the Fresh-re-check invariant's Class B recipe,
which is acted on at step 10, when `accepting` is loaded.

---

## B2 — the boundary, if the seven-unit target ever ships

Move into core (`loop-engine.md` line ranges):

| content | lines | why it cannot defer |
|---|---|---|
| status vocabulary — three closed sets + "unrecognised ⇒ STOP" | **906–958** | steps 0.3 and 2 and Resume classify against it |
| `queue.md` header semantics — `mode:`, `graduated-routes:`, `plan-gate:`, budget caps | **969–1046** | sets plan-gate and merge-gate posture; `plan-gate:` is cross-cutting |
| Router | **1432–1451** | route decides which gates are due |
| Resume | **1852–1975** | makes one-PR-at-a-time hold across compaction |

**Refinement — `progress.md` is not monolithic.** Its **gate-decision line vocabulary** — the
`- gate-error:` / `- gate-fallback:` distinction, the four `- Plan-gate:` spellings, and the
`- Budget:` grammar — is cross-cutting invariant vocabulary that core's Gate-outcome invariant, the
Guardrails stuck-check and the step-1 budget cap all resolve against. **Those formats stay in core;
only the filled worked example and the open/close-record prose defer.**

Genuinely deferrable: the `queue.md` skeleton (1048–1064), the `progress.md` worked example (within
1066–1378), the plan template + lifecycle (1379–1431), Initialization (1827–1849). The AC-verifier
(1455–1826) is `accepting`, not `reference`.

---

## B1 — replacement wording, ships as-is

Current, in the Gate-outcome invariant:

> …**on the rows that gate is due on** — due-ness is decided where it always was (the gate's own step
> and the Routing table) and this invariant does not touch it.

Replacement:

> …**on the rows that gate is due on** — due-ness is decided by the gate's **When** entry in the Gate
> table above and by the Routing table's per-route column, both in this core, and this invariant does
> not touch it. (The one gate whose due-ness is knowable only from its binding is
> `HERMETIC_TEST_CMD`; its carve-out below states that unknown reads as due.)

This resolves the predicate entirely inside core: the *When* column carries every gate's condition,
the Routing table carries the route-scoped ones, and the HERMETIC carve-out is already in core.

---

## B3 — the guard, specified

`PhaseIndexIdentityTests` in `tests/test_repo_consistency.py`, shaped like `CapsVocabularyTests`
(one-directional, vacuity-guarded) and `PlanGateFrozenBlockTests` (string identity, never truth).

**Correction to B3 as originally stated.** "Every gate has exactly one phase-index entry" **cannot be
a bijection**: eight gates, six units — `planning` owns Plan + Architect + Human, `reviewing` owns
Code review + Security. The gate→unit mapping is semantic, and encoding it rebuilds
`ALLOWED_NON_BINDINGS`. **The guard pins units and files, not gates.**

Asserts — all identity or existence, arbitrary-string couplings where any change is a real change:

1. **Unit-set identity.** The set of unit names in the phase-index *table* equals the set in the
   *"what holds without each unit loaded"* list. Set equality, not a count. Catches a deferred unit
   shipped with no fail-safe half, or an orphaned fail-safe half.
2. **File existence.** Every `phases/*.md` and `reference/*.md` the index names resolves to a file
   that exists. (Ship with the PR that creates the shards, or scope to units actually extracted, so
   it is never red on an intermediate commit.)
3. **Step resolvability.** Every step number in the *read it at* column is a real pipeline step —
   resolvability only, reusing the existing heading-resolution logic.
4. **Vacuity guard.** The extractor finds ≥5 units and `planning` is among them, so a broken regex
   fails here rather than passing on an empty set.

Must **not** assert: that a fail-safe half's text correctly states its unit's posture (truth over
prose — the enumerable-assertion trap, defeated by one reword); that a gate is assigned to the
*correct* unit; or whether any posture is right. Those stay review-owned, and the docstring says so:
a green run means **the index is internally consistent and its files exist**, never that the
fail-safe halves are correct.

**On the #35 opportunity:** the guard makes the phase index a *checked* canonical home for identity
and existence. Whether the units then stop re-asserting posture — the actual reduction in
restatement sites — is authoring discipline no guard can see, for the same reason it cannot check a
fail-safe half's truth.
