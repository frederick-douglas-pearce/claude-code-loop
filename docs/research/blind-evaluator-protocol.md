# Blind evaluator protocol — paired benchmark (#382)

Two judgments a paired-benchmark run needs that no script can make: whether the work at the stop
meets the issue's criteria, and what kind of stop the replicate ended at. Both are made by an agent
that does not know which arm produced what it reads. This file is the protocol. **Nothing here is
built**: #288 builds the first evaluator, against this text.

A pre-registration written from `preregistration-template.md` inherits this file unchanged and
supplies the fields marked **Registered**.

## When it runs

After the last replicate of the run has ended, and before any outcome is compared between arms
(template section 13). Every replicate is scored in one batch, in shuffled order.

## Blinding

1. **Relabel.** A step the scorer never sees maps each replicate id to an opaque id and copies the
   scorer's inputs under that id. The mapping stays sealed until every score is recorded.
2. **Withhold.** The scorer never receives the ledger, a transcript, `environment.json`,
   `audit.json`, the branch name, or the replicate id. Those name the arm or let it be inferred.
3. **Leak check.** Each input is searched for the **Registered** redaction list: strings only one
   arm can produce. A hit in a diff is reported and that replicate is scored separately as
   **unblinded**. A hit in a stop message is redacted before judging, and the judgment is flagged.
4. **What blinding cannot do** is stated with the result, not hidden: a stop the lever itself adds
   names its arm, and so may a diff the lever shaped. Unblinded scores are reported beside the
   blind ones and never pooled with them.

## Part 1 — scoring the diff at the stop

**Inputs, per replicate:** `stop/diff.patch` (the committed work at the stop, against the fixture's
base); the fixture repo at its base commit, read-only; and the pick's frozen criteria list. Work
left uncommitted at the stop (`stop/uncommitted.patch`) is not scored, and its presence is
reported.

**Scope.** Only a replicate that reached the endpoint has a diff to score. That conditions the
quality outcome on reaching the endpoint, and the pre-registration says so wherever it uses the
score.

**The scorer's instructions carry all of these:**
- the criteria, verbatim, and the diff;
- a verdict on every criterion first, then detail;
- one of `met`, `unmet`, or `cannot tell` per criterion, each with the hunk or file it rests on;
- that `cannot tell` is a valid answer and must be given plainly when it applies;
- each statement marked as reproduced (read in the inputs) or inferred;
- that it reads only: it runs nothing and changes nothing;
- a defect list: anything in the diff that is wrong whatever the criteria say;
- a `removal` tag on any criterion that is unmet because the diff deletes something the base had.

**Registered:** the scorer's model and effort, and the prompt's text. All three are the same for
every replicate in the run.

**Repeats.** Each diff is scored twice, by two fresh spawns that share nothing. Where they disagree
on a criterion, that criterion is `cannot tell`. The agreement rate is reported.

**Score.** A criterion marked undischargeable in the frozen list is left out for both arms.
`cannot tell` counts as unmet. A replicate's score is criteria met ÷ criteria scored.

**How it feeds the quality outcome.** Per pick, each arm's score is the median over its scored
replicates, and the paired difference is control minus treatment. The pre-registration registers
the reading that refutes. Defects and `removal` tags are listed per replicate beside the scores.

## Part 2 — judging the stop type

**Input, per replicate that reached the endpoint:** the final assistant message of its last stream
file (`streams/`), after the leak check. Nothing else.

**Categories** (template section 7): routine merge-gate stop; step-10 escalation; step-11
escalation; `gate-error`; a stop the lever adds; `cannot tell`.

**Rules.**
- A message that names the lever's own stop is classified by rule as that category. It is not sent
  to the judge.
- The judge is told that `cannot tell` is a valid answer, and returns its verdict before its
  reasons.
- Each message is judged twice by fresh spawns. A disagreement is `cannot tell`.
- `cannot tell` counts with the escalations.

**Cross-check.** `quality_outcomes.escalations()` is run over the captured `progress.md`, with the
posture read from the captured `queue.md` header. It is a second reading by fixed rules. Where it
and the judge disagree about a replicate, both readings are reported and the judge's stands. Its
`unclassified` column counts with the escalations.

## What #288 builds

- the relabeling step and the sealed mapping;
- the scorer and judge prompts, from the instruction lists above;
- the leak check, from the registered redaction list;
- the script that turns recorded verdicts into per-pick scores.
