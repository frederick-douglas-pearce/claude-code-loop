# Blind evaluator protocol — paired benchmark (#382)

Two judgments a paired-benchmark run needs that no script can make: whether the work at the stop
meets the issue's criteria, and what kind of stop the replicate ended at. Both are made by an agent
that does not know which arm produced what it reads. This file is the protocol. **Nothing here is
built**; #388 carries the build.

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
3. **Leak check.** The relabeling step searches each input for the **Registered** redaction list:
   strings only one arm can produce. A hit in a diff is reported and that replicate is scored
   separately as **unblinded**. A hit in a stop message is handled as part 2 says.
4. **What blinding cannot do** is stated with the result, not hidden: a stop the lever itself adds
   names its arm, and so may a diff the lever shaped. Unblinded scores are reported beside the
   blind ones and never pooled with them.

## Part 1 — scoring the diff at the stop

**Inputs, per replicate:** `stop/diff.patch` (the committed work at the stop, against the fixture's
base); the fixture repo at its base commit, read-only; and the pick's frozen criteria list. Work
left uncommitted at the stop (`stop/uncommitted.patch`) is not scored, and its presence is
reported.

**Scope.** Only a replicate that reached the endpoint is scored. A halted replicate has a
`stop/diff.patch` too, and it is not scored. That conditions the quality outcome on reaching the
endpoint, and the pre-registration says so wherever it uses the score.

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
`cannot tell` counts as unmet. A replicate's score is criteria met ÷ criteria scored. A replicate
with no criterion scored has no score, and that is reported.

**How it feeds the quality outcome.** Per pick, each arm's score is the median over its scored
replicates, and the paired difference is taken between the arms' medians. The pre-registration
registers the reading that refutes. Defects and `removal` tags are listed per replicate beside the
scores.

## Part 2 — judging the stop type

**Input, per replicate:** the final assistant message of its last stream file (`streams/`).
Nothing else. Rule 1 runs on every replicate. The judge sees only a replicate whose row was
`in-acceptance` at its last stop.

**Categories** (template section 7): routine merge-gate stop; step-10 escalation; step-11
escalation; `gate-error`; a stop the lever adds; a message that is not the engine's, such as an API
or account error; `cannot tell`.

**Registered:** the judge's model and effort, the prompt's text, and the lever-stop pattern.

**Rules, in this order.**
1. The relabeling step reads the unredacted message. One that matches the lever-stop pattern is
   classified by rule as the lever's stop and is not sent to the judge.
2. Any other hit on the redaction list is redacted, and the judgment is flagged.
3. The judge is told that `cannot tell` is a valid answer, and returns its verdict before its
   reasons.
4. Each message is judged twice by fresh spawns. A disagreement is `cannot tell`.
5. `cannot tell` counts with the escalations.

**What the judgment decides besides the outcome.** A replicate whose final stop is judged
`gate-error`, or judged not the engine's, is censored for every endpoint outcome (template
section 9).

**Reported beside it.** `quality_outcomes.escalations()` is run over the captured `progress.md`,
with the posture read from the captured `queue.md` header, and its counts are listed per
replicate. It counts stops over the whole journal and names no final stop, so nothing is compared
with the judgment.

## What the build covers (#388)

- the relabeling step and the sealed mapping;
- the scorer and judge prompts, from the instruction lists above;
- the leak check, from the registered redaction list and lever-stop pattern;
- the script that turns recorded verdicts into per-pick scores.
