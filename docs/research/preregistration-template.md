# Pre-registration template — paired benchmark (#382)

A lever measured on the paired benchmark gets a pre-registration written from this template and
frozen before the first replicate of either arm. The benchmark replays one closed issue under two
engine variants with `replicate.py`; the design is the cost review's §5.3
(`cost-review-2026-10-26.md`), as changed by #274's comment of
[2026-11-20](https://github.com/frederick-douglas-pearce/claude-code-loop/issues/274#issuecomment-7028409256).

**How to use it.** Copy the section list into `<lever>-preregistration.md`, keep the numbering, and
fill every field. Text under **Fixed** holds for every instance, which cites it and does not repeat
it. Text under **Fill** is the instance's. A field with no valid entry is not left blank: the
instance says what is missing and who owes it. `r1-preregistration.md` is the first instance.

## 1. Header

**Fill:** the lever, its issue, the appendix or note the predictions come from, and the status:
`draft`, or `frozen <date>`.

**Fixed — the freeze rule.** The instance is frozen by a commit that changes its status line and
nothing else. A replicate spent before that commit belongs to no arm of this instance. Once
frozen, the body is never edited: a change is a dated entry under section 15, with its reason, and
the verdict names the freeze commit and every entry.

## 2. Fields filled at freeze

**Fill:** a checklist of every field the draft leaves open, each with its owner. An instance
cannot be frozen while any row is open. Every instance carries at least these rows: both arms'
commits and `--version-dir` values, the harness commit, the Claude Code version, the `uv`
binary's version and sha256 (or none), each pick's `fixture_sha256`, the stratum, k, the arm
schedule, the replacement cap, the frozen criteria list per pick, the redaction list, the
classification rules, every instrument an outcome names, and every numeric bound.

**Fixed.** An outcome the instance adds, whose instrument does not exist at freeze, is dropped in
one line under section 14. It is not registered with an instrument to be written later. The five
outcomes section 7 fixes cannot be dropped: without their instruments the instance is not frozen.

## 3. Arms and pins

**Fill:** control and treatment, each as a full commit SHA for `--plugin-commit` and a
`--version-dir` value, plus what the two commits may differ in.

**Fixed.**
- The plugin reaches a replicate through the sandbox marketplace the harness builds from the pinned
  commit. No arm is a plugin-cache directory on the maintainer's machine, and none is loaded with
  `--plugin-dir`.
- Both arms run the same `MODEL_TIERS` value, the same `(model, effort)` stratum, the same subagent
  roster, the same Claude Code version (`--claude-version`), the same `uv` binary on every pick
  (`--uv-bin`, or none), and the same `fixture.json` per pick.
- Every replicate runs from a checkout whose HEAD is a harness commit the instance registers. A
  certifying record names that commit, as `replicate-pilot-2026-11.md` and
  `replicate-repilot-2026-11.md` do for earlier ones, and its `replicate.py` writes the `stop/`
  capture section 8 reads.
- Both arms run under `mode: calibration`. The harness does not check it, so section 8 does.

## 4. Fixture set

**Fill:** the picks, by reference to the note that selected them, and each pick's role.

**Fixed.** Each pick has a **frozen criteria list**: the acceptance criteria the blind evaluator
scores against, written at freeze from the issue body the fixture carries. It is never taken from a
replay's own plan. A criterion the sandbox cannot discharge is on the list and marked
**undischargeable**, with the reason.

## 5. Endpoint

**Fixed.** The endpoint is the replicate's first `in-acceptance` stop. Nothing is sent there and
nothing merges. Every outcome is measured up to that stop. The close record and its `- Budget:`
line are never written, so nothing an instance registers may read them.

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
| Prediction | A direction and a size. A size the source predicted and the instance withdraws is named under section 14 with its reason. A safety reading states the count at which it is a no-go. A measure that is reported and decides nothing says so. |
| Refuted if | The reading that contradicts the prediction, stated so that it can occur. An outcome that can only pass says so, and says what a fail does. |
| Selection | Which replicates the outcome can be read on, and what that conditions on. |

**Fixed — every instance registers these, and adds its own.**

| Outcome | Instrument |
|---|---|
| USD per issue, to the endpoint | `replicate.py measure` → `usd` |
| Turns per issue, to the endpoint | `replicate.py measure` → `turns`. It counts the parent sessions' turns. Cost review §5.1 also names subagent turns, which `measure` does not report. |
| Peak parent context | `engine_cost.profile()` → `peak_ctx`, over the replicate's parent transcript. `measure` does not report it, so the instance shows at freeze that `profile()` reads a replicate's transcript in both arms. |
| Quality | The blind evaluator's score (`blind-evaluator-protocol.md`), and `quality_outcomes.escalations()` over the captured journal. Of #272's three outcomes these are what a replicate supports: fix-up commits and F-comments need a merged PR and a 14-day window. |
| Stop type | The stop-type judgment in `blind-evaluator-protocol.md`. |

**Fixed — stop type.** The categories are: routine merge-gate stop; step-10 escalation; step-11
escalation; `gate-error`; a stop the lever itself adds, which the instance names; a message that is
not the engine's, such as an API or account error; and `cannot tell`. The stop is judged blind,
from the replicate's stream, after the run; the harness never classifies it. `cannot tell` counts
with the escalations.

## 8. Admissibility

**Fixed — one rule for both arms, default-deny.** A replicate is admissible only when each line
below is shown to hold. If a line cannot be checked, the replicate is inadmissible.

- `environment.json`'s `harness_commit` is a harness commit the instance registers, and
  `harness_tree_clean` is true.
- `plugin_commit`, `version_dir`, `cli_version`, `parent`, `fixture_sha256`, `uv_version`, and
  `uv_sha256` equal the registered pins. A registered none is met only by null fields.
- The `MODEL_TIERS` row in the fixture's `loop.config.md` is the registered value.
  `environment.json`'s `model_tiers` is copied from `fixture.json`, so it does not show this.
- The `queue.md` header in the captured ledger (`stop/ledger/`) reads `mode: calibration`.
- In `audit.json`, `a_tracker`, `a_account_events`, `a_tools`, `b_engine_loads`, `c_strata`, and
  `d_stop_capture` are each present and empty, and `account_feed.delayed_read` is true.
- For the cost outcomes only: `measure` did not refuse. A replicate that fails this line alone is
  admissible for every other outcome and is not replaced.

**Do not use `audit.json`'s `pass` for this.** It also requires `unattended`, which a halted
replicate never has, so it would discard every censored replicate along with the outcomes that
read them.

## 9. Censoring and replacement

**Fixed.** A replicate that halts before the endpoint is **censored**: it stays in the record with
everything known up to the halt, and it is left out of every outcome measured at the endpoint. One
rule covers both arms. A halt takes the first kind below that fits:

| Kind | What it is |
|---|---|
| External halt | An interrupt, a harness refusal, or an API or account error such as a spend cap. `environment.json`'s `error_result` and `outcome_kind` are evidence for the last of these (#389); the instance's classification rules decide. |
| Gate-error halt | A gate produced no verdict and the engine stopped, whatever the row's status. |
| Review halt | The replicate stopped at `in-review`. |
| Other halt | Any halt that is none of the above, a turn timeout and the fixture's `max_turns` included. It is treated as a halt the lever could have caused. |

**Fixed — a gate-error during acceptance is censored too.** #274's comment: "an `in-review` halt
(#371), a `gate-error` partway through acceptance, or an external halt (e.g. the spend cap,
`rp2-h1`) is censored." The harness does not classify the final stop, so it cannot tell that case
from the endpoint. The stop-type judgment identifies it: a replicate whose final stop is judged
`gate-error`, or judged not the engine's, is censored for every endpoint outcome.

**Fixed.** Halts are classified by rules the instance registers, read from `environment.json`, the
captured ledger, and the stream. They are not classified by a blind judge, apart from the final
stop above: a lever can write lines into the ledger that name its arm.

**Fill:** the classification rules, including the rule that says a replicate reached the endpoint;
for each kind, whether its rate is also an outcome and in which section 7 block; the replacement
cap; and where in the schedule a replacement runs.

**Fixed — replacement.** An external halt or an inadmissible replicate is replaced, up to the
registered cap per pick and arm. No other halt is replaced. The decision to replace reads sections
8 and 9 only, never an outcome. Admissibility is not known when a replicate ends: the delayed feed
read comes at least six hours later. The stop-type judgment runs after the last replicate
(section 13), so it never causes a replacement: a replicate it alone censors stays censored and is
not replaced.

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
  compared between arms. A safety reading is a count over the run and is not compared this way.
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
- No outcome is compared between arms before the last replicate ends. The blind evaluator and the
  stop-type judgment run after it. Admissibility and the external-halt rule are checked per
  replicate, since replacement needs both.
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
- The record does not show that both arms ran the same agent prompts. `fixture_sha256` covers
  `fixture.json` only, and no recorded hash covers the roster's prompt text (#390).
  `memory_snapshot` records the memory files per replicate; section 8 does not compare it. Both
  arms are run from one fixture directory, unchanged for the length of the run.
- Nothing pins the tools the sandbox takes from the host. `/usr` and `/etc` are bound read-only, so
  every tool under `/usr`, `python3` included, is the host's, and a host `/etc/uv/uv.toml` applies
  to `uv`. A run without `--uv-bin`, of a fixture whose `requires` does not name `uv` (one that
  does is refused, #384), would execute a host `/usr/bin/uv` while recording `uv_version`
  and `uv_sha256` as null, which section 8 admits as matching a registered none. With `--uv-bin`, a
  host `/usr` Python that satisfies a fixture's `.python-version` is used in preference to the one
  `uv` would download. (The host on 2026-11-22 had no `/usr/bin/uv`, no `/etc/uv/uv.toml`, and no
  Python 3.14 under `/usr`: 3.12 and 3.7 only.)

## 15. Deviations

Empty at freeze. Each later entry carries its date, what changed, why, and whether any replicate
had been spent.
