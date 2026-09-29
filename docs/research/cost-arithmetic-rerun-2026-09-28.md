# Cost-arithmetic re-run — 2026-09-28 (#212/AC8)

#212 moved this directory's pricing onto the cost spec's per-turn arithmetic (PR #215): one
record per `message.id`, 1-hour cache writes at 2× instead of 1.25×, API-error lines excluded, each
turn priced on its own model. `engine_cost.py` also stopped crediting a tool result to a later line
of the call that issued it, and `plan_gate_cost.py` gained a `user/other input` row. This file
reports how much that moves each figure.

**Nothing is rewritten.** Published figures stand as published, and their sections carry a one-line
pointer to this file. **A figure computed before #212 that this file does not report as re-run has
not been re-checked; treat it as moved.**

**"Materially" was fixed in PR #215 before any number here existed:** a move of **≥ 5% relative**
for an amount, a ratio or a multiplier, or **≥ 2 percentage points** for a share. Every delta is
reported below, including those under the line.

Session IDs and aggregates only; no transcript content leaves the machine.

## Method

- **Old** is `docs/research/` at `bce5e62` (`main` before PR #215). **New** is `43245b5` (PR #215
  merged). Each was extracted with `git archive <sha> docs/research` and run unchanged.
- **§2 re-runs each figure on the session set it was published on, pooled across strata where the
  published figure was**, except where a row says the script now splits by stratum.
- **Two session sets.** (1) The readings #207/AC9 re-profiled, which AC8 names: the 32 sessions in
  `stratum-reprofile-2026-09-27.md`. (2) The session set behind each published figure AC8 names,
  because **none of those figures was computed over the 32**. Finding 10's n=8 includes `9b188aba`
  and `7bcec8a4`, which are in no re-profiled reading, and `cost-model-design.md`'s subagent share
  was taken over whole project directories.
- `engine_cost.py`, `calls_per_turn.py`, `rounds_vs_turns.py` and `plan_gate_cost.py` were given
  the session files. `tree_cost.py` was given a directory holding only that reading's sessions and
  their subagent directories.
- **Strata did not move.** #212 changed `stratum.py`, and `stratum-reprofile-2026-09-27.md` is
  invalid after such a change until it is re-run. Every one of the 32 sessions prints the same
  `stratum` line under both versions, so its verdicts stand.
- **Engine % of bill and carry/turn are read from `engine_cost.py`'s `PROP` row**, the row P2c and
  Finding 10 use.
- **Cache discount** is `no-cache input basis ÷ billable input`, both printed by `engine_cost.py`.
  That is this file's operationalisation of the README's "~8×"; the README does not state one.

## 1. The readings #207/AC9 re-profiled (32 sessions)

**`engine_cost.py`** — medians over each reading's admissible sessions. `a587e8e4` (loop, n=3) is
inadmissible under both versions, so the loop reading has n=2 in this table.

| reading | n | INGESTED (P2) | P2c | engine % of bill | bill/turn | cache discount |
|---|---:|---|---|---|---|---|
| vote frozen n=5 (spans strata) | 5 | 64,345 → 59,214 (−8.0%) | 24.5 → 24.1% (−0.4 pp) | 20.2 → 20.3% (+0.1 pp) | 34,583 → 37,982 (+9.8%) | 8.27 → 7.43× (−10.2%) |
| vote addendum `c51f20e1` | 1 | 74,591 → 78,733 (+5.6%) | 13.8 → 14.6% (+0.8 pp) | 11.4 → 12.1% (+0.7 pp) | 31,922 → 34,029 (+6.6%) | 8.79 → 8.15× (−7.3%) |
| loop second baseline | 2 | 53,514 → 58,197 (+8.7%) | 18.0 → 21.0% (+3.0 pp) | 14.5 → 17.1% (+2.6 pp) | 32,470 → 35,488 (+9.3%) | 8.40 → 7.63× (−9.2%) |
| loop v0.2.1 | 10 | 75,139 → 68,754 (−8.5%) | 22.5 → 22.2% (−0.2 pp) | 18.6 → 19.0% (+0.4 pp) | 44,071 → 49,557 (+12.4%) | 7.52 → 6.47× (−13.9%) |
| vote v0.2.1 | 13 | 68,799 → 68,771 (−0.0%) | 24.2 → 24.2% (+0.0 pp) | 20.7 → 21.0% (+0.3 pp) | 38,335 → 42,329 (+10.4%) | 7.92 → 6.97× (−11.9%) |

Bill/turn rises and the cache discount falls in every reading. 1-hour cache writes, priced at 1.25×
before #212, now cost 2× base input. INGESTED and P2c move in both directions across sessions.
`engine reads counted` also changes on some sessions (e.g. `b40adacf` 11 → 12).

**`tree_cost.py` (parent + subagents, USD)** — pooled within each stratum, as the script prints it.

| reading | stratum | sessions | subagent share | total USD |
|---|---|---:|---|---|
| vote frozen n=5 | opus-5@xhigh | 3 | 38.6 → 38.8% (+0.2 pp) | $253 → $128 (−49%) |
| | opus-5@high | 2 | 34.9 → 34.5% (−0.4 pp) | $206 → $112 (−46%) |
| vote addendum | opus-5@xhigh | 1 | 43.1 → 40.6% (−2.5 pp) | $219 → $113 (−48%) |
| loop second baseline | opus-5@xhigh | 2 | 38.4 → 39.3% (+0.9 pp) | $207 → $97 (−53%) |
| loop v0.2.1 | opus-5@xhigh | 10 | 36.0 → 35.6% (−0.4 pp) | $1,469 → $685 (−53%) |
| vote v0.2.1 | opus-5@xhigh | 13 | 34.6 → 32.7% (−1.9 pp) | $1,333 → $675 (−49%) |

The totals roughly halve, mainly because the old `tree_cost.py` summed every streamed line of a response
rather than one record per `message.id`.

**`calls_per_turn.py` (Finding 12's lever)** — per-session means within each stratum, as the script prints them.

| reading | stratum | ceiling (all mergeable) | floor (paging only) | realistic floor |
|---|---|---|---|---|
| vote frozen n=5 | opus-5@xhigh | 448,212 → 510,832 (+14.0%); 11.2 → 11.3% of input | 245,619 → 295,982 (+20.5%); 6.2 → 6.5% | 138,160 → 166,490 (+20.5%) |
| | opus-5@high | 1,048,074 → 1,148,160 (+9.5%); 17.4 → 18.0% | 423,247 → 485,613 (+14.7%); 7.0 → 7.6% | 193,484 → 221,994 (+14.7%) |
| vote addendum | opus-5@xhigh | 1,891,691 → 2,127,875 (+12.5%); 17.9 → 18.7% | 656,438 → 731,745 (+11.5%); 6.2 → 6.4% | 218,813 → 243,915 (+11.5%) |
| loop second baseline | opus-5@xhigh | 430,756 → 503,187 (+16.8%); 9.7 → 10.3% | 240,738 → 294,852 (+22.5%); 5.4 → 6.0% | 178,324 → 218,409 (+22.5%) |
| loop v0.2.1 | opus-5@xhigh | 520,132 → 624,418 (+20.0%); 8.0 → 8.3% | 305,181 → 382,446 (+25.3%); 4.7 → 5.1% | 108,993 → 136,588 (+25.3%) |
| vote v0.2.1 | opus-5@xhigh | 646,269 → 734,058 (+13.6%); 11.8 → 11.9% | 262,544 → 310,383 (+18.2%); 4.8 → 5.0% | 97,322 → 115,056 (+18.2%) |

Token amounts rise 9–25%. The shares of input bill move by 0.8 pp or less.

**`rounds_vs_turns.py` (Finding 11's fit, opus-5@xhigh)** — least-squares fits, as the script prints them.

| reading | r (rounds/issue → bill/issue) | fit, bill/issue |
|---|---|---|
| vote frozen n=5 | +0.86 → +0.88 | −2,616,484 + 1,683,831 × rounds → −3,287,458 + 1,962,569 × rounds (slope +16.6%) |
| loop second baseline | n/a (both) | 3,741,237 − 28,086 × rounds → 3,829,848 + 34,717 × rounds |
| loop v0.2.1 | +0.89 → +0.89 | −215,521 + 1,131,406 × rounds → −282,336 + 1,296,573 × rounds (slope +14.6%) |
| vote v0.2.1 | +0.57 → +0.59 | 2,384,988 + 649,091 × rounds → 2,769,266 + 697,252 × rounds (slope +7.4%) |

The addendum is one session and yields no fit. The loop second-baseline fit rests on two sessions,
and its slope changes sign.

**`plan_gate_cost.py` (token counts, not prices)** — medians over every session in the reading. The script does not split by stratum, so the vote n=5 row spans strata and the loop row includes `a587e8e4`.

| reading | n | cumulative arrivals | model output | pre-plan turns | selection-phase share | over-attribution |
|---|---:|---|---|---|---|---|
| vote frozen n=5 | 5 | 183,797 → 177,677 (−3.3%) | 19,508 → 17,383 (−10.9%) | 36 → 30 | 35 → 33% | 255…8,184 → 0 |
| vote addendum | 1 | 199,783 → 197,147 (−1.3%) | 20,394 → 17,758 (−12.9%) | 30 → 25 | 42 → 37% | 2,636 → 0 |
| loop second baseline | 3 | 173,049 → 166,267 (−3.9%) | 22,279 → 16,930 (−24.0%) | 36 → 29 | 48 → 44% | 1,265…6,782 → 0 |
| loop v0.2.1 | 10 | 181,235 → 177,953 (−1.8%) | 16,215 → 14,980 (−7.6%) | 24 → 22 | 40 → 36% | −14,031…7,038 → 0 |
| vote v0.2.1 | 13 | 189,735 → 189,735 (0.0%) | 20,684 → 20,118 (−2.7%) | 32 → 31 | 31 → 30% | 0…7,903 → 0…4 |

"Resident at plan-file write" is unchanged in every session.
Tokens also move between source buckets. In `d9933e33`, 5,136 tokens move from `ENGINE read` to
`loop.config.md`. No published figure comes from this script, so nothing here is labelled.

## 2. The published figures, re-run on their own session sets

| figure | set | old → new | verdict |
|---|---|---|---|
| bill/turn "~33k", "~28–33k", "mean 33,342 … CV 15%" | Finding 10's n=8 | median 35,179 → 38,381 (**+9.1%**); mean 34,363 → 37,579 (**+9.4%**); CV 13.0 → 12.9% | **material** |
| cache "~8× discount" | n=8 | median 8.44 → 7.66× (**−9.2%**); range 7.69–9.20 → 6.69–8.74× | **material** |
| P2c, loop 18.0% (n=2) | `b40adacf`, `fd687f48` | 18.0 → 21.0% (**+3.0 pp**) | **material** |
| P2c, vote 22.8% (n=6) | Finding 10's six vote sessions | 22.8 → 22.8% (+0.05 pp) | not material |
| INGESTED median, loop 53,514 / vote 67,472 | n=2 / n=6 | 53,514 → 58,197 (**+8.7%**) / 67,472 → 69,077 (+2.4%) | loop **material** |
| carry/turn median, loop 0.74 / vote 0.91 | n=2 / n=6 | 0.74 → 0.80 (**+8.1%**) / 0.915 → 0.915 | loop **material** |
| engine % of bill median, loop 14.5% / vote 19.6% | n=2 / n=6 | 14.5 → 17.1% (**+2.6 pp**) / 19.6 → 19.25% (−0.35 pp) | loop **material** |
| output "~13–19% of the bill" | n=8 | 12.9–19.1 → 11.9–18.1% (≤ 1.8 pp per session) | not material |
| rounds → bill fit, "850k × rounds" | Finding 11's n=8 | published fit is pooled, and both versions stratify, so the pooled fit cannot be re-run. Within opus-5@xhigh (n=6): slope 680,134 → 755,734 (**+11.1%**), r +0.77 → +0.78 | **material** |
| batching: ceiling ~783k, floor ~358k, recoverable ~176k per session | Finding 12's nine | published figures are pooled and both versions stratify. opus-5@xhigh: 564,333 → 638,160 (**+13.1%**), 271,448 → 323,612 (**+19.2%**), 150,397 → 179,298 (**+19.2%**). opus-5@high: 990,496 → 1,092,375 (**+10.3%**), 454,416 → 516,283 (**+13.6%**), 213,843 → 242,957 (**+13.6%**). Shares of input bill move ≤ 0.5 pp | amounts **material**, shares not |
| subagent share 37.7 / 27.0 / 17.7 / 20.3% | every delegating session in each of the four project directories (published n = 40 / 72 / 143 / 48) | pooled over the sessions both versions price: loop 35.5 → 33.9% (−1.6 pp, n=65), vote 31.2 → 29.0% (**−2.2 pp**, n=68), agentfluent 27.3 → 24.7% (**−2.6 pp**, n=9), claude-code-sessions 24.0 → 22.4% (−1.6 pp, n=14) | **material** (two of four) |
| median bill/record ~26k / ~15k, and the length table | four projects, per record | **not re-run**: no script in this directory produces it | labelled, unmeasured |
| P10 "123,343 tok/session" | loop 0.2.1, ≥50 turns, n=6 | **not re-run**: the session list was not recorded | labelled, unmeasured |
| "shard the engine ~4–5% of a run" | n=8 | **not re-run**: its derivation is not stated | labelled, unmeasured |

**Notes on the table.**

- **Unmeasured is labelled, not skipped.** A figure this file could not re-run has not been shown to
  be stable, so it takes the same pointer as one that moved.
- **Finding 10's published mean and CV do not match its own rows.** Its eight bill/turn cells
  average 34,363 with a CV of 13.0%, the old script's figures, not the 33,342 and 15% its text
  states. The deltas above compare old script to new script and leave that discrepancy as published.
- **The subagent-share comparison uses only the sessions both versions price.** The new version also
  prices the four models #212 added to `PRICING`, so the two versions' full sets differ. The
  published table dates from 2026-08-29 and an earlier `tree_cost.py`. This re-run isolates #212's change and does not reproduce that table.
