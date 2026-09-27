# Stratum re-profile of the published readings — 2026-09-27 (#207/AC9)

Every published per-repo reading in this directory was re-profiled by parent `(model, effort)`
stratum with `stratum.py` **as of commit `28f1de5`**, the last commit to touch the extractor. (The
first run, at `cb6a91b`, gave the same strata, CLI ranges and counts; `28f1de5` folds subagent
versions into the CLI range, and no range moved.) A later change to `stratum.py` invalidates this
file until it is re-run.

**Nothing here is recomputed.** A reading that is not positively single-stratum is **labelled** in
its source doc with a one-line pointer to this file. Its figures stand as published, and the label
tells a reader not to compare them across a stratum. The rule behind this, and why a model or effort
change is a treatment, is in `cost-model-design.md` → *The run environment is a treatment the
harness can change without asking*.

Session IDs and strata only; no transcript content leaves the machine.

## Verdict

**Checked single-stratum:** these readings have a recorded session set, and every session in it
was profiled into one parent stratum:

| repo | reading | stratum |
|---|---|---|
| `claude-code-loop` | P2c, n=2 | `claude-opus-5@xhigh` |
| `claude-code-loop` | P10, n=6 (membership reconstructed, below) | `claude-opus-5@xhigh` |
| `claude-code-loop` | v0.2.1, n=10 | `claude-opus-5@xhigh` |
| `us_presidential_vote_analysis` | v0.2.1, n=13 | `claude-opus-5@xhigh` |
| `us_presidential_vote_analysis` | addendum `c51f20e1` (one session) | `claude-opus-5@xhigh` |

**Every other reading is treated as not stratified, and is labelled in its source doc.** That
includes a reading whose stratum cannot be told:

- **Spans strata:** vote's frozen n=5 baseline; vote's P2c n=6; Finding 10's pooled n=8 fit
  (loop + vote), which is where `cost ≈ turns × ~33k` and the ~8× cache discount come from.
- **Contains an UNSTRATIFIED session:** loop's second baseline, n=3 (`a587e8e4`).
- **No session set recorded, so it cannot be stratified:** the 0.2.0 Convergence rows (all four
  repos; ledger-sourced).

Two comparisons follow from the table rather than from any one reading:
- **A vote 0.2.0 → 0.2.1 before/after crosses an effort change:** its 0.2.0 sets include
  `@high`, and its v0.2.1 set is all `@xhigh`.
- **No 0.3.0 reading exists yet.** None is recorded as harvested (#126's body: n=0 as of
  2026-09-13).

## The readings

| reading | source | repo | sessions found / claimed | parent strata | label |
|---|---|---|---|---|---|
| Frozen baseline, n=5 (also feeds its P2, P3, P4 and P5 rows) | `baseline-2026-08-25.md` → *Baseline sessions (n=5)* | vote | 5/5 | `opus-5@xhigh` ×3, `opus-5@high` ×2 | **spans** |
| Addendum `c51f20e1` (not folded into n) | same doc | vote | 1/1 | `opus-5@xhigh` | none: single stratum |
| P2c | `baseline-2026-08-25.md` P2c row; session list in `loop-cost-and-convergence.md` → Finding 10 | loop | 2/2 | `opus-5@xhigh` ×2 | none: single stratum |
| P2c | same | vote | 6/6 | `opus-5@xhigh` ×4, `opus-5@high` ×2 | **spans** |
| Finding 10's pooled fit, n=8 (`cost ≈ turns × ~33k`, CV 15%, the ~8× discount) | `loop-cost-and-convergence.md` → Finding 10 | loop + vote | 8/8 (the two P2c sets) | `opus-5@xhigh` ×6, `opus-5@high` ×2 | **spans**: labelled there, and where the README and `cost-model-design.md` quote it |
| P10, `claude-code-loop` ≥50-turn baseline, n=6 | `baseline-2026-08-25.md` → P10 | loop | 6/6, **membership reconstructed** (below) | `opus-5@xhigh` ×6 | none: single stratum |
| Second per-repo baseline, n=3 | `baseline-2026-08-25.md` → *Second per-repo baseline* | loop | 3/3 | `opus-5@xhigh` ×2, **UNSTRATIFIED** ×1 | **contains UNSTRATIFIED** |
| Convergence, 0.2.0 era only (feeds P6/P7) | `baseline-2026-08-25.md` → *Convergence* | all four | **0 / 12: no session set recorded** (these are ledger rows) | unknown | **cannot be stratified** |
| v0.2.1 n=10 | #126 comment (*"AC3's ≥5 precondition is discharged — n=10 and n=13"*) | loop | 10/10 | `opus-5@xhigh` ×10 | none: single stratum |
| v0.2.1 n=13 | same comment | vote | 13/13 | `opus-5@xhigh` ×13 | none: single stratum |
| Earlier v0.2.1 harvest, n=9 / 11 / 4 | #126 comment of 2026-09-09 | loop / vote / sportswear | 0 listed (loop, vote); 1 of 4 (sportswear, `6dcfc632`) | unknown | none: superseded by n=10 / n=13, and published only in that comment, not in this directory |
| 0.3.0 | — | any | none recorded | — | n/a |

**Where the v0.2.1 list was found.** Searched #126's body and comments, #128, #133, #207, every
`progress.md` under this repo's `.claude/loop/` and the vote repo's, and `docs/research/*.md`. The
per-session list is in the #126 comment named above and nowhere else; the ledgers and the README
cite n=10 / n=13 without IDs.

**P10's membership is reconstructed, not recorded.** The doc records a rule (`claude-code-loop`,
≥50 turns, started on or after 2026-08-25, authoring session excluded) and the run's totals, not the
IDs. Nine sessions from 2026-08-25 to 2026-09-02 pass the turn filter; exactly one six-session subset
reproduces the recorded run-length totals, and that is the set counted above. The verdict does not
depend on it: all nine candidates are `claude-opus-5@xhigh`.

## The `<synthetic>` carve-out, measured

Every `<synthetic>` record in every session above has absent or all-zero usage, so D016's carve-out
ignores them all and **changes no verdict in this file**. The literal rule — any `<synthetic>` record
makes a session unstratified — would have shrunk these readings, which is the selection effect the
carve-out exists to prevent:

| reading | n | excluded by the literal rule |
|---|---:|---|
| vote frozen n=5 | 5 | 1 (`d9933e33`) |
| loop P2c | 2 | **2** (`b40adacf`, `fd687f48`) — n=0 |
| vote P2c | 6 | 3 (`d9933e33`, `9b188aba`, `d53db569`) |
| loop P10 | 6 | 2 (`d11dabf8`, `c3124e3c`) |
| loop second baseline | 3 | 2 (`b40adacf`, `fd687f48`) |
| loop v0.2.1 | 10 | 3 (`d11dabf8`, `c5b66cab`, `eb7ca2dc`) |
| vote v0.2.1 | 13 | 4 (`4b76d973`, `7b903076`, `d3fa3d0a`, `d53db569`) |

## Per-session strata

`id · parent stratum · started (UTC, 2026) · CLI`. Subagent strata are printed by each script's
`stratum` line and are not a grouping key.

**vote, frozen n=5 + addendum:** `c60c8a44` opus-5@xhigh 08-24 2.1.240 · `592ab44d` opus-5@xhigh
08-24 2.1.240 · `d9933e33` opus-5@xhigh 08-22 2.1.240 · `d5ba0ddc` **opus-5@high** 08-22 2.1.238 ·
`f374d191` **opus-5@high** 08-22 2.1.238 · addendum `c51f20e1` opus-5@xhigh 08-24 2.1.240

**vote, P2c n=6:** `d9933e33`, `592ab44d`, `d5ba0ddc` as above · `9b188aba` **opus-5@high** 08-20
2.1.238 · `7bcec8a4` opus-5@xhigh 08-23 2.1.240 · `d53db569` opus-5@xhigh 08-26 2.1.246

**loop, P2c n=2 and second baseline n=3:** `b40adacf` opus-5@xhigh 08-23 2.1.241 · `fd687f48`
opus-5@xhigh 08-22 2.1.239 · `a587e8e4` **UNSTRATIFIED** (switched mid-session: opus-5@high →
opus-5@xhigh) 08-19 2.1.234–2.1.239 — excluded from P2c by the admissibility floor, included in the
n=3 P2 median.

**loop, P10 n=6 (reconstructed):** `5c0e852e`, `b505937a`, `ca0a90a3`, `b257a520`, `d11dabf8`,
`c3124e3c` — all opus-5@xhigh.

**loop, v0.2.1 n=10:** `fe55fe80`, `d11dabf8`, `c5b66cab`, `5c0e852e`, `7ea2dc1a`, `a0f9e735`,
`ca0a90a3`, `b505937a`, `b257a520`, `eb7ca2dc` — all opus-5@xhigh, 08-27 → 09-10, CLI 2.1.246–2.1.261.

**vote, v0.2.1 n=13:** `4b76d973`, `e28f07c0`, `098416fc`, `99a1001f`, `7b903076`, `7c7ef722`,
`cd2054d8`, `d3fa3d0a`, `0baee1d7`, `bc7a1681`, `af91d0e3`, `ab6d955b`, `d53db569` — all
opus-5@xhigh, 08-26 → 09-09, CLI 2.1.246–2.1.266.

## Side findings, not stratum findings

- **`d53db569` appears in two eras' readings** — the 0.2.0 P2c set and the v0.2.1 n=13 set. It
  started 2026-08-26T04:39Z, seven minutes before the vote repo's 0.2.1 install, and its transcript
  reads both the `0.2.0` and the `0.2.1` engine paths. Its engine era cannot be told from the date
  filter #126 used.
- **`baseline-2026-08-25.md`'s P2c section says "seven admissible 0.2.0 sessions"; the Finding 10
  table it cites has eight** (two loop, six vote).

## Looking ahead: 0.3.0 will span strata unless restricted by date

A census of parent transcripts started on or after 2026-09-11 that read an installed `dev-loop` path
(a proxy for a loop session, not an admissibility test) finds, dated by **session start** (a
session's first record, which can precede its first reply by a day), in `claude-code-loop`:
`opus-5@xhigh` ×15 (to 09-23), `opus-5-5@medium` ×3 (09-24 → 09-27), `opus-5-5@high` ×2 (09-27, one
of them the session that wrote this file), `opus-4-7@xhigh` ×2; in the vote repo: `opus-5@xhigh` ×13
(09-12 → 09-21), `opus-5-5@medium` ×7 (09-22 → 09-26), one UNSTRATIFIED (`183b7d0d`, switched
`@medium` → `@high` on 09-26), `opus-5-5@high` ×1 (09-27). That is why #126's before-baseline is the
`claude-opus-5-5@high` stratum counted from 2026-09-27 (#207/AC8).
