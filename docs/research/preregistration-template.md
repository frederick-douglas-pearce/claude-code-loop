# Pre-registration template — paired benchmark (#382)

A lever measured on the paired benchmark gets a pre-registration written from this template and
frozen before the first replicate of either arm. The benchmark replays one closed issue under two
engine variants with `replicate.py`; the design is the cost review's §5.3
(`cost-review-2026-10-26.md`), as changed by #274's comment of
[2026-11-20](https://github.com/frederick-douglas-pearce/claude-code-loop/issues/274#issuecomment-7028409256).

**How to use it.** Copy the section list into `<lever>-preregistration.md`, keep the numbering, and
fill every field. Text under **Fixed** holds for every instance and is copied unchanged. Text under
**Fill** is the instance's. A field with no valid entry is not left blank: the instance says what
is missing and who owes it. `r1-preregistration.md` is the first instance.

## 1. Header

**Fill:** the lever, its issue, the appendix or note the predictions come from, and the status:
`draft`, or `frozen <date> at <commit>` where the commit is this file's own.

**Fixed — the freeze rule.** The instance is frozen by a commit that changes its status line and
nothing else. A replicate spent before that commit belongs to no arm of this instance. Once the
first replicate of either arm is spent, the body is never edited: a change is a dated entry under
section 15, with its reason, and the verdict names every entry.

## 2. Fields filled at freeze

**Fill:** a checklist of every field the draft leaves open, each with its owner. An instance
cannot be frozen while any row is open. Every instance carries at least these rows: both arms'
commits and `--version-dir` values, the stratum, k, the arm schedule, the replacement cap, the
frozen criteria list per pick, the redaction list, every instrument an outcome names, and every
numeric bound.

**Fixed.** An outcome whose instrument does not exist at freeze is dropped in one line under
section 14. It is not registered with an instrument to be written later.

## 3. Arms and pins

**Fill:** control and treatment, each as a full commit SHA for `--plugin-commit` and a
`--version-dir` value, plus what the two commits may differ in.

**Fixed.**
- The plugin reaches a replicate through the sandbox marketplace the harness builds from the pinned
  commit. No arm is a plugin-cache directory on the maintainer's machine, and none is loaded with
  `--plugin-dir`.
- Both arms run the same `MODEL_TIERS` value, the same `(model, effort)` stratum, the same subagent
  roster, the same Claude Code version (`--claude-version`), the same `fixture.json` per pick, and
  the same harness commit. That commit is the one the latest certifying record names
  (`replicate-repilot-2026-11.md` and its addenda).
- Both arms run under `mode: calibration`. The harness does not check it, so section 8 does.

## 4. Fixture set

**Fill:** the picks, by reference to the note that selected them, and each pick's role.

**Fixed.** Each pick has a **frozen criteria list**: the acceptance criteria the blind evaluator
scores against, written at freeze from the issue body the fixture carries. It is never taken from a
replay's own plan. A criterion the sandbox cannot discharge is on the list and marked
**undischargeable**, with the reason.

## 5. Endpoint

**Fixed.** The endpoint is the replicate's first `in-acceptance` stop. Nothing is sent there and
nothing merges. Every outcome is measured up to that stop. Steps 11 and 12 never run, so nothing an
instance registers may read the close record or its `- Budget:` line.

## 6. Treatment check

**Fill:** what shows, per replicate, that the treatment ran in the treatment arm and did not run in
the control arm; the script that counts it; and the compliance level below which the run is void.

**Fixed.** The check reads transcripts, not the journal (cost review §5.4). Every replicate is
analyzed in the arm it was assigned to, and compliance is reported beside the verdict.

## 7. Outcomes

**Fill:** one block per outcome, each with these five fields.

| Field | A valid entry |
|---|---|
| Instrument | A script or a rule that exists at freeze, and the file it reads. |
| Unit | What one observation is: a replicate, or a pick. |
| Prediction | A direction and a size. "Lower" with no size is not an entry. |
| Refuted if | The reading that contradicts the prediction, stated so that it can occur. An outcome that can only pass says so, and says what a fail does. |
| Selection | Which replicates the outcome can be read on, and what that conditions on. |

**Fixed — every instance registers these, and adds its own.**

| Outcome | Instrument |
|---|---|
| USD per issue, to the endpoint | `replicate.py measure` → `usd` |
| Parent turns per issue, to the endpoint | `replicate.py measure` → `turns` |
| Peak parent context | `engine_cost.profile()` → `peak_ctx`, over the replicate's parent transcript. `measure` does not report it, so the instance shows at freeze that `profile()` reads a replicate's transcript in both arms. |
| Quality | The blind evaluator's score (`blind-evaluator-protocol.md`), and `quality_outcomes.escalations()` over the captured journal. Of #272's three outcomes these are what a replicate supports: fix-up commits and F-comments need a merged PR and a 14-day window. |
| Stop type | The stop-type judgment in `blind-evaluator-protocol.md`. |

**Fixed — stop type.** The categories are: routine merge-gate stop; step-10 escalation; step-11
escalation; `gate-error`; a stop the lever itself adds, which the instance names; and
`cannot tell`. The stop is judged blind, from the replicate's stream, after the run; the harness
never classifies it. `cannot tell` counts with the escalations.

## 8. Admissibility

**Fixed — one rule for both arms, default-deny.** A replicate is admissible only when each line
below is shown to hold. If a line cannot be checked, the replicate is inadmissible.

- `environment.json`'s `harness_commit` is the certified commit and `harness_tree_clean` is true.
- `plugin_commit`, `cli_version`, `parent`, and `fixture_sha256` equal the registered pins.
- The `MODEL_TIERS` row in the fixture's `loop.config.md` is the registered value.
  `environment.json`'s `model_tiers` is copied from `fixture.json`, so it does not show this.
- The `queue.md` header in the captured ledger (`stop/ledger/`) reads `mode: calibration`.
- In `audit.json`, `a_tracker`, `a_account_events`, `a_tools`, `b_engine_loads`, `c_strata`, and
  `d_stop_capture` are each empty, and `account_feed.delayed_read` is true.
- For the cost outcomes only: `measure` did not refuse.

**Do not use `audit.json`'s `pass` for this.** It also requires `unattended`, which a halted
replicate never has, so it would discard every censored replicate along with the outcomes that
read them.

## 9. Censoring and replacement

**Fixed.** A replicate that halts before the endpoint is **censored**: it stays in the record with
everything known up to the halt, and it is left out of every outcome measured at the endpoint. One
rule covers both arms. Halts come in three kinds:

| Kind | What it is |
|---|---|
| Review halt | The replicate stopped at `in-review`. |
| Gate-error halt | A gate produced no verdict and the engine stopped before the endpoint. |
| External halt | A turn timeout, the fixture's `max_turns`, an interrupt, an account spend cap, or a harness refusal. |

**Fixed.** Halts are classified by rules the instance registers, read from the captured ledger and
`environment.json`. They are not classified by a blind judge: a lever can write lines into the
ledger that name its arm.

**Fill:** the classification rules; for each kind, whether its rate is also an outcome and in which
section 7 block; and the replacement cap.

**Fixed — replacement.** A halt the lever could have caused is never replaced. An external halt or
an inadmissible replicate is replaced, in the same schedule slot, up to the registered cap per pick
and arm. The decision to replace reads sections 8 and 9 only, never an outcome.

## 10. Excluded measures

**Fixed.**
- The journal's `wall-clock` slot and its block timestamps are not outcomes. They are estimates the
  orchestrator writes without reading a clock
  ([F229](https://github.com/frederick-douglas-pearce/claude-code-loop/issues/1#issuecomment-6934861954)).
- The plan gate is answered by the fixture's scripted reply, so no replicate waits on a human. The
  cost of re-warming the cache after a gate wait is therefore never observed. An instance that needs
  it models it and says so.

**Fill:** anything else the lever makes unusable.

## 11. Statistics

**Fill:** k, the per-pick summary of an arm's k replicates, the paired difference and its sign
convention, and the test.

**Fixed.**
- The unit of analysis is the pick. Replicates within a pick are summarized first; picks are then
  compared between arms.
- No decision rule depends on σ. It has not been measured (#209). The control arm's within-pick
  spread is reported with the verdict and handed to #209.
- Every numeric bound is fixed at freeze. No bound is derived from the run's own data.

## 12. Verdict

**Fill:** the possible verdicts, in the order they are tested, and what each one does.

**Fixed.** The verdicts are exhaustive and mutually exclusive. They are tested in the registered
order and the first that holds is the verdict, as in `r2-phase-isolation-design.md` §10. A safety
verdict is tested before any cost or effect verdict. Every verdict routes somewhere: none leaves the
lever's issue waiting.

## 13. Stopping rule

**Fill:** the arm schedule, as a rule that fixes the order of every replicate before the first one
runs, and where the verdict is posted.

**Fixed.**
- k replicates per pick per arm, plus replacements under section 9, and then the run ends. No
  replicate is added because of a result.
- No outcome is compared between arms before the last replicate ends. The blind evaluator, the
  stop-type judgment, and the classification rules all run after it. Admissibility is checked per
  replicate, since replacement needs it.
- The verdict is posted with the paired table, the control arm's spread, both arms' commits, the
  harness commit, and every section 15 entry.

## 14. Confounds, and what this design cannot observe

**Fill:** what the treatment bundles that the design cannot separate; every outcome of the source
note that was dropped, with one line of reason each; and the population the result holds for.

**Fixed — true of every instance on this harness.**
- A replicate shows at most two code-review rounds. A third round exists only when a human
  authorizes it, and no reply is sent at an `in-review` stop.
- Nothing merges, so nothing that needs a merged PR is observable.
- The result holds for the registered stratum and the picked issues.

## 15. Deviations

Empty at freeze. Each later entry carries its date, what changed, why, and whether any replicate
had been spent.
