# R1 pre-registration — fresh-agent fixes and the round ceiling (#288)

Written from `preregistration-template.md`; section numbers match it, and its **Fixed** text
applies here unrepeated. The judgments in sections 7 and 12 follow `blind-evaluator-protocol.md`.

## 1. Header

- **Lever:** R1 (#288): on a dirty code-review round the fix is written by a fresh agent under a
  deletion-first mandate, and an iteration stops at a ceiling of six review rounds.
- **Source:** `cost-review-2026-10-26/A-design-R1-fix-agent-and-ceiling.md` §4, "The falsifier,
  written for pre-registration". It was written against engine 0.3.1 and merged runs. This file
  restates it for a harness on which every replicate ends unmerged at its first `in-acceptance`
  stop. Section 14 lists what was restated and what was dropped.
- **Status:** `draft`, 2026-11-21 (#382). **Not frozen: no replicate may be spent against it.** The
  owner freezes it under the template's freeze rule once every row of section 2 is closed.

## 2. Fields filled at freeze

| Field | Draft value | Owed by |
|---|---|---|
| Treatment commit and `--version-dir` | open: R1's PR head does not exist yet | #288 |
| Stratum `(model, effort)` | default: the stratum of #274's control replay. Chosen before any treatment replicate, with the reason recorded here. | owner |
| k | 3 per pick per arm | owner |
| Arm schedule | the rule in section 13 | owner |
| Replacement cap | 1 per pick per arm | owner |
| Picks beyond the seven | open: three slots (`benchmark-fixture-set.md`) | #288 |
| Frozen criteria list per pick | open. vote #172 and vote #82 have no acceptance-criteria section, so theirs are written from the issue body. | #288 |
| Environment-fixed set | vote #172 and esg #211. esg #211 leaves only if its criterion 3 is shown dischargeable in the sandbox before freeze. | #288 |
| Redaction list | seed in section 7, outcome 7; checked against the treatment's text | #288 |
| Classification rules (section 9) | as drafted; checked against the treatment's journal text | #288 |
| Treatment-check script (section 6) | does not exist | #288 |
| Peak-context instrument | `engine_cost.profile()`. Not established: whether it reports `peak_ctx` for a replicate transcript in either arm, and which `engine_cost.py` rows that needs for each arm's `--version-dir` and the stratum's model family. | #288 |
| Cost bound (outcome 3) | 25% | owner |
| Compliance floor (section 6) | 90% | owner |
| Balance bound (section 7) | 0.20 | owner |
| Evaluator and judge model, effort, prompts | open | #288 |
| What each verdict does (section 12) | as drafted; the owner confirms | owner |

## 3. Arms and pins

Each arm is installed from the sandbox marketplace the harness builds at the arm's pinned commit.
Appendix A §4 pinned the arms as versioned plugin-cache directories; this replaces that.

- **Control:** the v0.6.0 content, `--plugin-commit 5391906a8723ba67956750e5e550f16a1779edcd`,
  `--version-dir 0.6.0`. It is not 0.3.1, which is what appendix A §4 names (owner decision
  recorded on #288, 2026-11-15).
- **Treatment:** R1's PR head, with its own `--version-dir`. Its base must show no difference from
  the control commit under `plugins/dev-loop/`, other than the v0.6.0 release's own changes to
  `.claude-plugin/plugin.json` and `README.md`. Anything else means the arms differ by more than
  R1, and the instance is not frozen.
- **`MODEL_TIERS`:** every role inherits, in both arms. R1's `fix` role stays `inherit` in the
  treatment arm (#288).

## 4. Fixture set

The seven picks of `benchmark-fixture-set.md`, plus up to three that #288 adds before freeze. That
note gives each pick's base, route, history, and the criteria its sandbox cannot discharge.

## 5. Endpoint

As the template fixes it.

## 6. Treatment check

Counted from each replicate's parent transcript:

- **Treatment arm:** every code-review round that returned a BLOCKING finding is followed by
  exactly one fix-agent spawn before the re-check is spawned, and the parent edits no tracked file
  in between.
- **Control arm:** no fix-agent spawn occurs.

Compliance is the share of the treatment arm's dirty rounds that meet the first line. **Below the
compliance floor, or with any fix-agent spawn in the control arm, the run is void** (section 12).
The script that counts this does not exist. Unlike an outcome's instrument, it cannot be dropped:
without it the instance is not frozen.

## 7. Outcomes

A replicate is **at risk** when its first review round was dirty and did not stop on a design
question; section 9 gives the rule. A pick is **informative** when both arms have at least one
at-risk replicate and their outcome-1 rates differ.

### Outcome 1 — round 2 clean, given round 1 dirty (primary)

- **Instrument:** the section 9 rules, over the captured ledger.
- **Unit:** per pick and arm, the share of at-risk replicates whose round 2 came back clean.
- **Prediction:** higher in the treatment arm on every informative pick.
- **Refuted if:** the median over informative picks of (treatment rate − control rate) is ≤ 0.
- **Selection:** at-risk replicates only. The two balance checks below test whether that set is
  comparable between arms.
- **Secondary reading:** the share of all replicates that reach the endpoint with no review halt.
  Reported; it decides nothing.

### Balance checks

Both events happen before R1 acts, so neither should differ by arm:

- the share of replicates whose round 1 was dirty;
- the share that halt on a round-1 design question.

**Failed if** either share, taken over all picks, differs between arms by more than the balance
bound. A failed check makes the verdict at most "inconclusive".

### Outcome 2 — claim defects in round 2

- **Instrument:** `claims=` on the round-2 `- Code-review:` element in the captured ledger.
- **Unit:** the sum over a pick's at-risk replicates, per arm.
- **Prediction:** lower in the treatment arm, summed over picks.
- **Refuted if:** the treatment arm's sum is not lower.
- **Selection:** as outcome 1. The count is the orchestrator's own, so it is an intent record
  (cost review §5.4).

### Outcome 3 — cost to the endpoint

- **Instrument:** the template's three: `usd`, `turns`, and peak parent context.
- **Unit:** per pick and arm, the median over replicates that reached the endpoint.
- **Prediction:** the treatment arm's USD is not more than the cost bound above the control arm's,
  taking the median over picks of the paired difference. The same reading is reported for turns and
  for peak context, which decide nothing.
- **Refuted if:** this outcome can only pass. Exceeding the bound refutes nothing and makes the
  verdict "inconclusive" (section 12).
- **Selection:** if outcome 1 holds, more treatment replicates reach the endpoint, and the extra
  ones went through a dirty round and a fix. The comparison is therefore biased against the
  treatment, which is why only a pass is read.
- **Sensitivity readings:** the same comparison without the environment-fixed set, whose step-10
  cost the environment inflates in both arms; and USD up to the stop for every admissible
  replicate, whatever the stop.

**The saving is a projection, not a test.** Appendix A predicted 15–35% lower USD on the
five-round issues. That saving came from rounds 3 to 5, and a replicate runs neither. No size is
registered in its place. What is reported instead, labeled as a projection: per pick, the
outcome-1 difference × the code-review rounds the historical run took past the cap of 2
(`benchmark-fixture-set.md`) × USD 4–6 per round (#288's estimate). It assumes those rounds would
recur under 0.6.0 and that a clean round 2 removes all of them. Neither assumption is tested here.

### Outcome 4 — quality at the stop

- **Instrument:** part 1 of `blind-evaluator-protocol.md`.
- **Unit:** per pick, the paired difference in median score.
- **Prediction:** the treatment arm's score is not lower.
- **Refuted if:** on any pick, the treatment arm's median score is below the lowest control
  replicate's score.
- **Selection:** replicates that reached the endpoint.
- **Over-deletion.** Where the treatment's journal tags a finding `over-deletion` (appendix A §4,
  outcome 4), the count is reported per replicate. **Safety no-go if** any tagged finding is still
  open at the stop, or any replicate carries more than one in a round. The evaluator's `removal`
  tags are listed beside it.

### Outcome 5 — the ceiling (safety)

On an unattended path the engine opens at most two rounds per capped gate, and no replicate answers
a stop, so a replicate cannot reach six rounds. A ceiling stop in a replicate therefore means the
orchestrator lost count. **Safety no-go if** any treatment replicate stops at the ceiling. It is
read from the final stop message and the last journal block, not from the `ceiling=` slot, which is
written at step 12. Both the cap and the counting rule are re-read in the treatment's text at
freeze.

### Outcome 6 — halts and hygiene, counted by arm

Counted per arm over the whole run:

- fix agents that returned no report (the `code-review — fix agent` `gate-error` signature);
- every other halt that is neither a review halt nor external;
- turn timeouts and `max_turns` halts.

Every halt is listed with its journal block. **Safety no-go if** the treatment arm has more than
one fix-agent gate-error, or exceeds the control arm's count on either other line by more than
one. These replicates are censored at the endpoint (section 9), and this is where they count.

### Outcome 7 — stop type

- **Instrument:** part 2 of `blind-evaluator-protocol.md`. The lever's own stop is the ceiling
  stop. Redaction list seed, from appendix A's sites: `fix agent`, `ceiling`, `deletion-first`,
  `over-deletion`, and the disposition words `deleted`, `substituted`, `re-wrapped`.
- **Unit:** per arm, the count of stops that are not routine, over picks outside the
  environment-fixed set.
- **Prediction:** not higher in the treatment arm.
- **Refuted if:** the treatment arm's count exceeds the control arm's by two or more.
- **Selection:** replicates that reached the endpoint.
- **Environment-fixed set.** These picks reach the same kind of step-10 stop in both arms. They are
  judged like any other and reported apart, as a check on the judge: it should give both arms the
  same answer.

## 8. Admissibility

As the template fixes it.

## 9. Censoring and replacement

**Classification rules.** Applied in this order to each admissible replicate. "Journal" is
`progress.md` in the captured ledger.

1. **External halt:** `environment.json` records a turn timeout, a `max_turns` halt, an interrupt,
   or a refusal. Replaced under the cap; counted in outcome 6.
2. **Halted before review:** no turn in `environment.json`'s `turns` records the status
   `in-review` or `in-acceptance`. Not at risk; counted in outcome 6.
3. **Step 8 closed:** the journal has an `- Editorial:` line that is not the `finding` form.
4. **Round 2 ran:** the journal has a `- Code-review:` element for round 2.
5. **Outcome 1 reads rules 3 and 4 only:**
   - round 2 ran and step 8 closed → at risk, **clean**;
   - round 2 ran and step 8 did not close → at risk, **not clean**;
   - no round 2 and step 8 closed → not at risk.
6. **No round 2, and step 8 did not close:** a round-1 design-question halt if
   `quality_outcomes.escalations()` counts a `scope-ruling` stop for the issue. Then it is not at
   risk, and it counts in the second balance check.
7. **Anything else is at risk and not clean.** That includes a ceiling stop, a contested finding, a
   gate-error inside step 8, and a journal that cannot be read.

Round 1 was **dirty**, for the first balance check, when the replicate is at risk or falls under
rule 6. A gate-error halt after step 8 closed keeps its outcome-1 reading and is censored for
every endpoint outcome.

**Rates that are outcomes:** a review halt after round 2 is what outcome 1 reads; a round-1
design-question halt is a balance check; gate-error and external halts are outcome 6.

**Replacement cap:** section 2.

## 10. Excluded measures

As the template fixes it. Also excluded: anything the treatment journals that the control cannot,
as a comparison between arms. The fix agent's dispositions and the `ceiling=` slot exist in one
arm only.

## 11. Statistics

- **k:** section 2.
- **Per-pick summary:** a rate (outcomes 1 and 7), a sum (outcome 2), or a median (outcomes 3
  and 4).
- **Paired difference:** treatment minus control for outcome 1; control minus treatment for
  outcomes 3 and 4.
- **Test for outcome 1:** a one-sided sign test over informative picks. Five picks all favoring
  the treatment give p = 1/32; four give 1/16. So "go" needs at least five informative picks, all
  in the treatment's favor, and anything less is "inconclusive" or "no effect".

## 12. Verdict

Tested in this order; the first that holds is the verdict.

1. **Void.** The treatment check fails (section 6).
2. **No-go (safety).** Any safety condition in outcomes 4, 5, or 6.
3. **No-go (quality).** Outcome 4 or outcome 7 is refuted.
4. **No effect.** Outcome 1 is refuted.
5. **Inconclusive.** Any of: fewer than five informative picks; an informative pick that favors
   the control; a failed balance check; outcome 2 refuted; outcome 3's bound exceeded.
6. **Go.** None of the above.

**What each does** (draft; the owner confirms at freeze):

- **Void:** the cause is fixed and the run is repeated under a new freeze. None of its replicates
  is used.
- **No-go (safety) or no-go (quality):** R1 does not ship. #288 returns to its plan gate with the
  failing replicates named.
- **No effect:** R1 does not ship as a cost lever. The question returns to #271.
- **Inconclusive:** no claim is made about R1 from this run. More picks are a new pre-registration,
  not an extension of this one.
- **Go:** #288's third acceptance criterion is met.

## 13. Stopping rule

- **Schedule.** Picks are numbered as in `benchmark-fixture-set.md`, and #288's additions continue
  the numbering. Replicate r of pick p runs the control arm first when p + r is even, and the
  treatment arm first when it is odd. The two replicates of a pair run back to back. Pairs run in
  order of r, then p.
- **Verdict:** posted on #288 and linked from #169, with what the template lists.

## 14. Confounds, and what this design cannot observe

**Confound, kept from appendix A.** The fix agent gets a clean context and a deletion mandate
together. The design cannot separate them; what is tested is the combination. A third arm is #144's.

**Appendix A §4, element by element.**

| §4 element | Here | Why |
|---|---|---|
| Control = 0.3.1; plugin-cache directories | Restated, section 3 | #288's control decision; the harness installs from a sandbox marketplace. |
| Independent variable from transcripts | Kept, section 6 | — |
| Outcome 1, rounds per completed issue | Restated as outcome 1 | A replicate shows at most two rounds. |
| Outcome 2, `claims=` after round 1 | Restated to round 2 | Rounds 3 and later never run. |
| Outcome 3, USD 15–35% lower | Size withdrawn; outcome 3 and the projection | The saving came from rounds neither arm runs. |
| Outcome 4, over-deletion | Restated at the stop | Nothing merges. |
| Outcome 4, blind evaluator on merged diffs | Restated to the diff at the stop | Nothing merges. |
| Outcome 4, fix-up commits within 14 days; F-comments | **Dropped** | Both need a merged PR and a 14-day window, and teardown deletes the sandbox. |
| Outcome 5, the ceiling fires only on five-round issues | Restated as outcome 5 | It cannot fire legitimately in a replicate. |
| Outcome 5, what the human chose at the ceiling | **Dropped** | No replicate answers a stop. |
| Outcome 6, fix-agent diffs touching a path no finding reached; staged-path mismatches | **Dropped** | No instrument reads them from the capture. A staged-path stop still appears, as a halt in outcome 6. |
| Outcome 6, stranded worktrees at step 12 | **Dropped** | Step 12 never runs, and the capture holds no `git worktree list`. |
| Outcome 6, fix agents that returned no report | Kept, outcome 6 | — |
| Verdict posted on #169 | Restated, section 13 | #288 absorbs #169. |

**Not registered:** a prediction that parent turns between the round-1 verdict and the round-2
spawn are lower in the treatment arm. It has no instrument. It may be added before freeze if one
exists by then.

**Population.** The picks were chosen to have no historical round-1 design-question stop
(`benchmark-fixture-set.md`, rule 5), and none edits the engine (rule 2). The result does not
carry to issues of either kind.

## Appendix A's stale line references

#288's comment of 2026-10-28 names one: Site 7's step-12 insert, whose anchor no longer exists.
For this pre-registration:

- **Site 7, step-12 insert: dropped, not re-located.** Step 12 no longer carries its own copy of
  the `- Budget:` specification. The line has one specification, under Ledger format in
  `loop-engine.md`.
- **Site 7, Ledger-format insert:** it goes after the `justification=` bullet of that
  specification. No measurement here reads the slot (outcome 5).
- **Site 7's rows in appendix A's byte table** count two inserts. #288 recomputes them.
- **The fields this file reads** are named, not located: the `- Code-review:` round elements and
  their `claims=`, and the `- Editorial:` line.

Every other site's line numbers are against engine 0.3.1. Re-locating that text is #288's first
acceptance criterion and is not done here.

## 15. Deviations

None.
