# Unit `plan-gate-inferred` — the run-level posture inference record

This file is the **`plan-gate-inferred` unit** of the dev-loop engine, not a standalone document.
Core (`loop-engine.md`) lists it in its phase index and has you read it at step 0, only on a run
that owes the `- Plan-gate-inferred:` record (core states when). Read it in full, under core's load
protocol. What holds when it is not loaded is stated in core (*What holds without each unit
loaded*), never here: its absence never makes a gate pass and never lets one be skipped.

## `- Plan-gate-inferred:` — the run-level posture inference

**Three plan-gate-family lines exist; keep them apart.** `- Human gate:` records how the plan gate
**resolved** on an issue. `- Plan-gate:` records the always-on stop's **frozen-vs-live diff** on an
issue. `- Plan-gate-inferred:` — this line — records that the **run's header stated no posture at
all**, so one was inferred.

**Emit at most once per run — and dedupe on the LINE YOU ARE ABOUT TO WRITE, never on the name
alone.** Search the FULL `progress.md` (never the tail) for that exact line; write the block only if
it is absent. **The two spellings below are two different facts with two different remedies, and the
second commonly follows the first *because the human acted on the first*.** A run that reports the
absent field, gets a hand-edited header with a typo in it, and then suppresses the unrecognized-value
notice on a name match has gone quiet at the exact moment its ledger started asserting a posture —
strictly worse than never having spoken. Keying on the name alone produces that; keying on the line
does not. This still is not a per-issue record: the line can only change when the **header** changes,
which is the property AC-level "once per run" is about.

**Surface first, then journal — the order is load-bearing.** An invocation can stop between the two
(step 0.3 halts on an orphan PR, the driver halts on a budget breach, a `/clear` lands). Journalling
first and stopping suppresses the message permanently while the ledger shows full compliance;
surfacing first and stopping merely re-emits next invocation, which is harmless.

It takes its own dated block, headed `## <ISO8601> — plan-gate inference`. **Keep the literals `RUN
COMPLETE`, `RUN PARKED` and `RUN RESUMED` out of the heading and the body**: step 0.1 greps the whole
journal for those, and a block carrying one risks reading as a run-state sentinel or forcing that
step to stop and ask. **If the unrecognized value you must quote itself contains one of the three,
do not write the block — STOP and ask the human**, rather than choosing between quoting it faithfully
and keeping the journal readable.

The block's shape — a skeleton, because the lines themselves are rendered **once**, below:

```markdown
## <ISO8601> — plan-gate inference

<the applicable line from the two variants below, verbatim — it already carries its `- ` marker>

  <that variant's own remedy paragraph, indented beneath it>
```

**Two variants, and this is the one place either is written out.** Each carries **its own** remedy:
the two are not interchangeable, because they describe opposite states of the header.
- **`- Plan-gate-inferred: no plan-gate: field in this run's header — reading as always.`**
  Remedy: *a human may set the posture by adding `_plan-gate: always_` (or `_plan-gate: conditional_`) to this
  run's `queue.md` header, beside `mode:`. The orchestrator never writes this field outside
  Initialization, which for this run has already happened.*
- **`- Plan-gate-inferred: unrecognized value "<the literal found>" — reading as always.`**
  **Quote what you found**, never a tidied version of it. Remedy: *a human may correct the existing
  value in this run's `queue.md` header — **replace it in place; do not add a second `plan-gate:`
  line**. The orchestrator never writes this field outside Initialization, which for this run has
  already happened.*

**Never hand the absent-field remedy to the unrecognized-value case.** There the field is already
present, so "add it beside `mode:`" yields a header carrying **two** `plan-gate:` lines — a state
this engine has no rule for, reached by an operator doing exactly what they were told.

**Absence of this line is not evidence the header stated a posture.** Every ledger written before
this line existed lacks it whatever its header said, and so does a run that never reached an emit
point. A missing line reads as *unknown*, on the same terms as an omitted `- Budget:` slot — never as
"the posture was stated". **A `- Human gate:` line naming a posture is not that evidence either**: it
names the posture in force, which on an owed run is the inferred one.

*End of the `plan-gate-inferred` unit.*
