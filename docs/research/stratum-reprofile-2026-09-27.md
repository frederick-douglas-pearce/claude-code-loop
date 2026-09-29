# Stratum re-profile of the published readings — 2026-09-27 (#207/AC9)

The readings #207/AC9 names — the frozen 0.2.0 baselines, the v0.2.1 n=10 / n=13 reading, and any
0.3.0 sessions already harvested — were re-profiled by parent `(model, effort)` stratum with
`stratum.py` **as merged in `9b68f05`** (PR #213; the last commit to touch the extractor is
`3454b4e`). A later change to `stratum.py` invalidates this file until it is re-run.

↳ **Re-run at `43245b5` (#212 changed `stratum.py`):** every session's `stratum` line is unchanged,
so the verdicts below stand. See `cost-arithmetic-rerun-2026-09-28.md`.

**Nothing here is recomputed.** A reading in this file that is not positively single-stratum is
**labelled** in its source doc with a one-line pointer to this file. Its figures stand as published,
and the label tells a reader not to compare them across a stratum. The rule behind this, and why a
model or effort change is a treatment, is in `cost-model-design.md` → *The run environment is a
treatment the harness can change without asking*.

Session IDs and strata only; no transcript content leaves the machine.

## Verdict

**Checked single-stratum:** every session in each of these readings was profiled into one parent
stratum:

| repo | reading | stratum |
|---|---|---|
| `claude-code-loop` | v0.2.1, n=10 | `claude-opus-5@xhigh` |
| `us_presidential_vote_analysis` | v0.2.1, n=13 | `claude-opus-5@xhigh` |
| `us_presidential_vote_analysis` | addendum `c51f20e1` (one session) | `claude-opus-5@xhigh` |

**Every other reading in this file is treated as not stratified, and is labelled in its source
doc.** That includes a reading whose stratum cannot be told:

- **Spans strata:** vote's frozen n=5 baseline.
- **Contains an UNSTRATIFIED session:** loop's second baseline, n=3 (`a587e8e4`).
- **No session set recorded, so it cannot be stratified:** the 0.2.0 Convergence rows (all four
  repos; ledger-sourced).

**Anything not in this file, including a figure elsewhere that quotes or derives from a reading
here, was not re-profiled or labelled; treat it as not stratified.**

## The readings

| reading | source | repo | sessions found / claimed | parent strata | label |
|---|---|---|---|---|---|
| Frozen baseline, n=5 | `baseline-2026-08-25.md` → *Baseline sessions (n=5)* | vote | 5/5 | `opus-5@xhigh` ×3, `opus-5@high` ×2 | **spans** |
| Addendum `c51f20e1` (not folded into n) | same doc | vote | 1/1 | `opus-5@xhigh` | none: single stratum |
| Second per-repo baseline, n=3 | `baseline-2026-08-25.md` → *Second per-repo baseline* | loop | 3/3 | `opus-5@xhigh` ×2, **UNSTRATIFIED** ×1 | **contains UNSTRATIFIED** |
| Convergence, 0.2.0 era only | `baseline-2026-08-25.md` → *Convergence* | all four | **0 / 12: no session set recorded** (these are ledger rows) | unknown | **cannot be stratified** |
| v0.2.1 n=10 | #126 comment (*"AC3's ≥5 precondition is discharged — n=10 and n=13"*) | loop | 10/10 | `opus-5@xhigh` ×10 | none: single stratum |
| v0.2.1 n=13 | same comment | vote | 13/13 | `opus-5@xhigh` ×13 | none: single stratum |
| 0.3.0: none harvested, so no reading exists | #126's body: n=0 as of 2026-09-13 | any | 0 / 0 | — | n/a: no reading to label |

**Where the v0.2.1 list was found.** Searched #126's body and comments, #128, #133, #207, every
`progress.md` under this repo's `.claude/loop/` and the vote repo's, and `docs/research/*.md`. The
per-session list is in the #126 comment named above.

## The `<synthetic>` carve-out, measured

Every `<synthetic>` record in every session in this file has absent or all-zero usage, so D016's
carve-out ignores them all and **changes no verdict in this file**. The literal rule — any
`<synthetic>` record makes a session unstratified — would have shrunk these readings, which is the
selection effect the carve-out exists to prevent:

| reading | n | excluded by the literal rule |
|---|---:|---|
| vote frozen n=5 | 5 | 1 (`d9933e33`) |
| vote addendum `c51f20e1` | 1 | 0 |
| loop second baseline | 3 | 2 (`b40adacf`, `fd687f48`) |
| loop v0.2.1 | 10 | 3 (`d11dabf8`, `c5b66cab`, `eb7ca2dc`) |
| vote v0.2.1 | 13 | 4 (`4b76d973`, `7b903076`, `d3fa3d0a`, `d53db569`) |

## Per-session strata

`id · parent stratum · CLI`. Subagent strata are printed by each script's `stratum` line and are
not a grouping key.

**vote, frozen n=5 + addendum:** `c60c8a44` opus-5@xhigh 2.1.240 · `592ab44d` opus-5@xhigh 2.1.240 ·
`d9933e33` opus-5@xhigh 2.1.240 · `d5ba0ddc` **opus-5@high** 2.1.238 · `f374d191` **opus-5@high**
2.1.238 · addendum `c51f20e1` opus-5@xhigh 2.1.240

**loop, second baseline n=3:** `b40adacf` opus-5@xhigh 2.1.241 · `fd687f48` opus-5@xhigh 2.1.239 ·
`a587e8e4` **UNSTRATIFIED** (switched mid-session: opus-5@high → opus-5@xhigh) 2.1.234–2.1.239

**loop, v0.2.1 n=10:** `fe55fe80`, `d11dabf8`, `c5b66cab`, `5c0e852e`, `7ea2dc1a`, `a0f9e735`,
`ca0a90a3`, `b505937a`, `b257a520`, `eb7ca2dc` — all opus-5@xhigh, CLI 2.1.246–2.1.261.

**vote, v0.2.1 n=13:** `4b76d973`, `e28f07c0`, `098416fc`, `99a1001f`, `7b903076`, `7c7ef722`,
`cd2054d8`, `d3fa3d0a`, `0baee1d7`, `bc7a1681`, `af91d0e3`, `ab6d955b`, `d53db569` — all
opus-5@xhigh, CLI 2.1.246–2.1.266.
