# R1 pre-registration — fresh-agent fixes and the round ceiling (#288)

Written from `preregistration-template.md`. Section numbers match it, and its **Fixed** text
applies here. Outcomes 4 and 7 use the judgments in `blind-evaluator-protocol.md`.

## 1. Header

- **Lever:** R1 (#288): on a dirty code-review round the fix is written by a fresh agent under a
  deletion-first mandate, and an iteration stops at a ceiling of six rounds across code review and
  acceptance.
- **Source:** `cost-review-2026-10-26/A-design-R1-fix-agent-and-ceiling.md` §4, "The falsifier,
  written for pre-registration". It was written against engine 0.3.1 and merged runs. This file
  restates it for a harness on which every replicate ends unmerged at its first `in-acceptance`
  stop.
- **Status:** `draft`, 2026-11-21 (#382). **Not frozen: no replicate may be spent against it.**

**What this draft holds.** It restates each of §4's outcomes in words: what is measured, the
direction predicted, and the reading that refutes.

## 2. Fields filled at freeze

Every row is open. The draft cannot be frozen while one is.

| Field | Owed by |
|---|---|
| Treatment commit and `--version-dir` | #288 |
| Harness commit, certified and with the `stop/` capture. The last certified commit, `f868f97`, predates the capture. | #274's re-certification |
| Claude Code version | owner |
| `fixture_sha256` and `fixture_tree_sha256` per pick | #274 for vote #82; #288 for the rest |
| Stratum `(model, effort)` | owner |
| k (appendix A: at least 3) | owner |
| Replacement cap, and where in the schedule a replacement runs | owner |
| Picks beyond the seven | #288 |
| Frozen criteria list per pick | #288 |
| Environment-fixed set: its members | #288 |
| Classification rules (section 9), including the rule that a replicate reached the endpoint, and which halts each of outcome 6's counts takes | #288 |
| The transcript script for outcome 1 and the treatment check | #288 |
| Compliance: what a compliant round is, and the floor below which the run is void | owner |
| Peak-context instrument: that `engine_cost.profile()` reads a replicate's transcript in both arms | #288 |
| Where R1's text writes the `over-deletion` tag (outcome 4) | #288 |
| Redaction list and lever-stop pattern (outcomes 5 and 7) | #288 |
| The blind evaluator and the stop-type judge: the build, and their model, effort, and prompts | #388 |
| Size, outcomes 1 and 2 | owner |
| Every numeric bound: the cost bound, the balance bound, the quality margin, the stop-type bound, the safety counts | owner |
| The projection's inputs (outcome 3) | owner |
| Verdict order and the conditions for each (section 12) | owner |
| How picks combine into one reading for outcomes 3, 4, and 7, and outcome 2's reading on a pick where an arm has no round-2 verdict | owner |
| Whether a flagged stop-type judgment (protocol part 2, rule 2) enters outcome 7's share | owner |
| Confirmation of section 13's arm schedule and section 12's routes | owner |

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
note gives each pick's role, base, route, history, and the criteria its sandbox cannot discharge.

## 5. Endpoint

As the template fixes it.

## 6. Treatment check

Counted from each replicate's parent transcript, from `Agent` launches, as appendix A §4 counts
them: fix-agent spawns per dirty code-review round in the treatment arm, and any fix-agent spawn in
the control arm. Compliance is reported by assigned arm. What makes a round compliant, the floor
below which the run is void, and the script are section 2 rows.

## 7. Outcomes

A replicate is **at risk** when its first review round returned a BLOCKING finding and did not
stop on a design question. Its **round 2 is clean** when the re-check returned no BLOCKING finding.
A pick is **informative** when both arms have at least one at-risk replicate.

### Outcome 1 — round 2 clean, given round 1 dirty (primary)

- **Instrument:** review rounds and re-check launches counted from the transcript (section 2: the
  script is not written). Not the journal: the engine writes its `- Code-review:` line for a
  reader, not for a parser.
- **Unit:** per pick and arm, the share of at-risk replicates whose round 2 is clean.
- **Prediction:** higher in the treatment arm. The size is a section 2 row.
- **Refuted if:** the median over informative picks of the paired difference is zero or below.
- **Selection:** at-risk replicates only. The balance checks test whether that set is comparable
  between arms.
- **Secondary reading:** the share of all replicates that reach the endpoint. Reported; it decides
  nothing.

### Balance checks

Two events happen before R1 acts, so neither should differ by arm: a dirty round 1, and a halt on
a round-1 design question. Each is reported as a share per arm. The bound past which a check fails
is a section 2 row.

### Outcome 2 — claim defects in round 2

- **Instrument:** `claims=` on the round-2 `- Code-review:` element in the captured ledger, which
  is appendix A's instrument. The count is the orchestrator's own, so it is an intent record (cost
  review §5.4).
- **Unit:** per pick and arm, claims per at-risk replicate whose round 2 returned a verdict.
- **Prediction:** lower in the treatment arm. The size is a section 2 row.
- **Refuted if:** the median over informative picks of the paired difference is above zero. Where
  the control arm's count is zero on every informative pick, the outcome cannot be read, and the
  verdict says so.
- **Selection:** as outcome 1.

### Outcome 3 — cost to the endpoint

- **Instrument:** the template's three: `usd`, `turns`, and peak parent context.
- **Unit:** per pick and arm, the median over replicates that reached the endpoint.
- **Prediction:** the treatment arm's USD is not above the control arm's by more than the cost
  bound (section 2). Turns and peak context are reported and decide nothing.
- **Refuted if:** this outcome can only pass. Exceeding the bound refutes nothing; what it does to
  the verdict is part of the section 2 row on verdict conditions.
- **Selection:** if outcome 1 holds, more treatment replicates reach the endpoint, and the extra
  ones went through a dirty round and a fix. The comparison is therefore biased against the
  treatment, which is why only a pass is read.
- **Sensitivity readings:** the same comparison without the environment-fixed set, whose step-10
  cost the environment raises in both arms; and USD up to the stop for every admissible replicate,
  whatever the stop.

**No size is registered for the saving.** Appendix A predicted 15–35% lower USD on issues that took
five or more rounds. A replicate runs at most two review rounds, so that prediction cannot be read
here, and it is withdrawn. What is reported instead is a projection, labeled as one and not a test:
the outcome-1 difference × the review rounds the historical run took past the cap × a cost per
round. Its inputs are a section 2 row.

### Outcome 4 — quality at the stop

- **Instrument:** part 1 of `blind-evaluator-protocol.md`, and `quality_outcomes.escalations()`
  over the captured journal, with its `unclassified` column counted in.
- **Unit:** per pick and arm, the median blind score; and the escalation count per replicate.
- **Prediction:** neither is worse in the treatment arm.
- **Refuted if:** the treatment arm's score is below the control arm's by more than the quality
  margin (section 2). The escalation count is reported and decides nothing.
- **Selection:** replicates that reached the endpoint, blind scores only. Unblinded scores are
  reported and decide nothing.
- **Over-deletion.** Appendix A §4 has the treatment's journal tag a finding `over-deletion`. None
  of appendix A's sites writes that tag (section 2). If R1's text does, a tagged finding in a
  replicate that reached the endpoint is a safety reading, with its count a section 2 bound. If it
  does not, this reading is dropped.

### Outcome 5 — the ceiling (safety)

- **Instrument:** the lever-stop rule in part 2 of `blind-evaluator-protocol.md`; the pattern is a
  section 2 row.
- **Unit:** a treatment-arm replicate. The ceiling exists in one arm only.
- **Prediction:** no ceiling stop; one is a no-go. On an unattended path the engine opens at most
  two rounds per capped gate, and no replicate answers a stop after the plan gate, so a replicate
  cannot reach six rounds. A ceiling stop therefore means the orchestrator lost count.
- **Refuted if:** one ceiling stop in any treatment replicate.
- **Selection:** every treatment replicate, halted or not. Both the cap and the counting rule are
  re-read in the treatment's text at freeze.

### Outcome 6 — halts, counted by arm (safety)

- **Instrument:** the section 9 classification.
- **Unit:** counts per arm over the whole run, of: fix agents that returned no report (the
  `code-review — fix agent` `gate-error` signature of appendix A §3); other gate-error halts
  after round 1's verdict; and other halts, turn timeouts and `max_turns` included.
- **Prediction:** each count stays below its no-go count, a section 2 bound. Halts before review
  are reported apart: they precede R1.
- **Refuted if:** a count reaches its no-go count.
- **Selection:** every admissible replicate. These replicates are censored at the endpoint, and
  this is where they count. Every halt is listed with its journal block.

### Outcome 7 — stop type

- **Instrument:** part 2 of `blind-evaluator-protocol.md`. The lever's own stop is the ceiling stop.
- **Unit:** per pick and arm, the share of endpoint replicates whose stop is not routine, over
  picks outside the environment-fixed set.
- **Prediction:** not higher in the treatment arm, within the stop-type bound (section 2).
- **Refuted if:** it is higher by more than that bound.
- **Selection:** replicates that reached the endpoint. As in outcome 3, the treatment arm's extra
  endpoint replicates went through a dirty round and a fix.
- **Environment-fixed set.** `benchmark-fixture-set.md` names vote #172 and, unless shown
  otherwise, esg #211: picks that reach the same kind of step-10 stop in both arms. They are judged
  like any other and reported apart, as a check on the judge.

## 8. Admissibility

As the template fixes it.

## 9. Censoring and replacement

The kinds, and the censoring of a gate-error during acceptance, are the template's. The rules that
classify a replicate are a section 2 row. One part is fixed now: **a review halt not positively
shown to be a round-1 design-question halt counts as at risk and not clean.**

**Rates that are outcomes:** a review halt after round 2 is what outcome 1 reads; a round-1
design-question halt is a balance check.

## 10. Excluded measures

As the template fixes it. Also excluded, as a comparison between arms: anything the treatment
journals that the control cannot. The fix agent's dispositions and the `ceiling=` slot exist in
one arm only.

## 11. Statistics

- **k:** section 2.
- **Per-pick summary:** a share (outcomes 1 and 7), a rate (outcome 2), or a median (outcomes 3
  and 4). Outcomes 5 and 6 are safety counts over the run.
- **Paired difference:** treatment minus control. For outcome 3 it is taken as a fraction of the
  control arm's median, per pick with an endpoint replicate in both arms.
- **Test for outcome 1:** a one-sided sign test over informative picks. Five picks all favoring
  the treatment give p = 1/32; four give 1/16.

## 12. Verdict

Six verdicts. The order they are tested in and the conditions for each are a section 2 row.

- **Void:** the treatment did not run as assigned. The cause is fixed and the run is repeated under
  a new freeze. None of its replicates is used.
- **No-go (safety)** or **no-go (quality):** R1 does not ship. #288 returns to its plan gate with
  the failing replicates named.
- **No effect:** R1 does not ship as a cost lever. The question returns to #271.
- **Inconclusive:** no claim is made about R1 from this run. More picks are a new pre-registration,
  not an extension of this one.
- **Go:** R1 may ship.

Whichever it is, the posted verdict is what #288's third acceptance criterion asks for: R1
measured against a pre-registered falsifier before it ships. The owner confirms these routes at
freeze.

## 13. Stopping rule

- **Schedule.** Picks are numbered as in `benchmark-fixture-set.md`, and #288's additions continue
  the numbering. Replicate r of pick p runs the control arm first when p + r is even, and the
  treatment arm first when it is odd. Pairs run in order of r, then p.
- **Verdict:** posted on #288 and linked from #169, with what the template lists.

## 14. Confounds, and what this design cannot observe

**Confound, kept from appendix A.** The fix agent gets a clean context and a deletion mandate
together. The design cannot separate them; what is tested is the combination. A third arm is #144's.

**Appendix A §4, element by element.**

| §4 element | Here | Why |
|---|---|---|
| Paired replay of one closed issue at its base under two variants | Kept | — |
| Variants pinned as versioned plugin-cache directories | Restated, section 3 | The harness installs from a sandbox marketplace at a pinned commit. |
| Control = 0.3.1, treatment = 0.3.1 + R1 | Restated, section 3 | #288's control decision. |
| Same `(parent model, effort, subagent roster)` stratum | Kept | — |
| Arms interleaved by issue parity | Restated, section 13 | The order now alternates within each pick's pairs as well. |
| k ≥ 3 replicates per issue per arm | Open, section 2 | — |
| Plan gate answered by the same scripted approval | Kept | — |
| Fixture: 6–10 issues, at least two of ≥ 5 rounds, at least one clean in two | Kept by reference, section 4 | `benchmark-fixture-set.md` made the selection. |
| The candidate issues §4 names | Superseded | The fixture note picked vote #172 and none of the others. |
| Round blocks, re-check launches, and fix-agent spawns counted from transcripts | Kept for code review, sections 6 and 7 | Acceptance rounds are no longer counted: outcome 1 reads review round 2 only. |
| Outcome 1: rounds per completed issue, lower by at least one round | Restated as outcome 1; **appendix A's size is withdrawn, and a new one is open** | A replicate shows at most two review rounds, so a round count cannot fall by one. |
| Outcome 1: not higher on the clean issues | Restated as the first balance check | R1 acts after round 1, so it cannot change whether round 1 is dirty. |
| Outcome 2: `claims=` after round 1 falls toward zero | Restated to round 2; **the size is open** | Rounds 3 and later never run. |
| Outcome 2: refuted if the sum does not fall | Restated: refuted if higher | A control count of zero cannot fall. |
| "R1 can pass one and fail the other" | Kept | The verdict conditions are a section 2 row. |
| Outcome 3: USD per completed issue, from `tree_cost.py --sessions` | Restated: USD to the endpoint, from `replicate.py measure` | Nothing merges. |
| Outcome 3: 15–35% lower on the ≥ 5-round issues | **Withdrawn**; a projection is reported | A replicate runs at most two review rounds. |
| Outcome 3: within noise on the clean issues | Restated as the cost bound, over every pick | — |
| Outcome 3: σ from #209, and the 25–30% floor until it exists | **Dropped** | No rule here depends on σ (template section 11). The control arm's spread is reported. |
| Outcome 4: over-deletion that reaches the merge candidate | Restated at the stop; open | Nothing merges, and no site writes the tag yet. |
| Outcome 4: the blind evaluator scores merged diffs | Restated to the diff at the stop | Nothing merges. |
| Outcome 4: refuted if the treatment scores lower | Restated: lower by more than a margin | Two scorers disagreeing on one criterion would otherwise refute. |
| Outcome 4: fix-up commits within 14 days; F-comments | **Dropped** | Both need a merged PR and a 14-day window, and teardown deletes the sandbox. |
| Outcome 5: the ceiling fires on the ≥ 5-round issues only | **Dropped** | It cannot fire in a replicate unless the count is lost. |
| Outcome 5: refuted if it fires on a clean issue | Restated as outcome 5, for every pick | — |
| Outcome 5: what the human chose at the ceiling | **Dropped** | No replicate answers a stop after the plan gate. |
| Outcome 6: fix-agent diffs touching a path no finding reached; staged-path mismatches | **Dropped** | No instrument reads them from the capture. |
| Outcome 6: stranded worktrees at step 12 | **Dropped** | Step 12 never runs, and the capture holds no `git worktree list`. |
| Outcome 6: fix agents that returned no report | Kept, outcome 6 | — |
| Outcome 6: more than one per fixture run refutes | Restated: the counts are section 2 bounds | — |
| The confound | Kept | — |
| Stopping rule: once per arm per replicate, no interim look | Kept | — |
| Verdict posted on #169, with the σ from #209 | Restated, section 13 | #288 absorbs #169's core; σ is replaced by the control arm's spread. |

**Not registered:** a prediction that parent turns between the round-1 verdict and the round-2
spawn are lower in the treatment arm. It has no instrument. It may be added before freeze if one
exists by then.

**Population.** Rule 5 of `benchmark-fixture-set.md` prefers picks with no historical round-1
design-question stop. Five of the seven have none recorded; loop #199 and vote #392 each had one.
None of the seven edits the engine (rule 2), so the result does not carry to issues that do.

## Appendix A's stale line references

#288's comment of 2026-10-28 names one: Site 7's step-12 insert, whose anchor no longer exists.
For this pre-registration:

- **Site 7, step-12 insert: dropped, not re-located.** Step 12 no longer carries its own copy of
  the `- Budget:` specification. The line has one specification, under Ledger format in
  `loop-engine.md`.
- **Site 7, Ledger-format insert:** it goes after the `justification=` bullet of that
  specification. No measurement here reads the slot (section 10).
- **Site 7's rows in appendix A's byte table** count two inserts. #288 recomputes them.

Every other site's line numbers are against engine 0.3.1. Re-locating that text is #288's first
acceptance criterion and is not done here.

## 15. Deviations

None.
