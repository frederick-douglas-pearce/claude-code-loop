# The sharding release's instrument, and the 0.3.0 side priced — 2026-10-09

**Purpose:** #133's second PR. It builds the instrument the sharding release (v0.3.1) is measured
with, runs the frozen 0.3.0 before side through it, and prices that side. The after side does not
exist yet. Its sessions accrue on the installed 0.3.1, and #133's third PR measures them.

**The instrument is frozen at the merge commit of the PR that adds this page.** #133's third PR, the
measurement, runs `engine_cost.py`, `tree_cost.py` and `stratum.py` unchanged. Any later change to them
re-runs **both** sides, never only the after side.

**Before side:** exactly the 23 sessions `baseline-2026-10-04.md` freezes (0.3.0, parent
`claude-opus-5-5`@`high`). Nothing is added to that list.

---

## The release is installed (#133/AC2, P1)

From `~/.claude/plugins/installed_plugins.json`, read 2026-10-09:

| repo | version | installed (UTC) | arm |
|---|---|---|---|
| `claude-code-loop` | 0.3.1 | 2026-10-08T22:54:37Z | treated |
| `us_presidential_vote_analysis` | 0.3.1 | 2026-10-08T22:56:36Z | treated |
| `sportswear-esg-news-classifier` | 0.3.1 | 2026-10-10T04:40:09Z (21:40 on 10-09, −07:00) | treated |
| `agentfluent`, `claude-code-sessions` | 0.2.0 | unchanged | control |
| `claude-hook-validator` | 0.3.1 | 2026-10-09T03:47:28Z | **baseline-only**: no 0.3.0 side, never pooled (D007) |

**P1, in bytes, on the installed cache** (`dev-loop/0.3.1/`): `SKILL.md` 10,829 + `loop-engine.md`
200,789 = **211,618 B**, against 0.3.0's 277,829 B: **−23.8%**, which clears #128's ≥20% floor
(≤ 222,263 B). The cache's `skills/` is byte-identical to the release tree (`diff -r`).

---

## What the instrument now does

**P2 is all engine text: core plus units** (#133/AC4). `engine_cost.py` counts a read of any
markdown file under the cached `skills/dev-loop/`. The set is a path pattern, not a list, so a unit
a later release adds is counted from its first install. A command that `cd`s into that directory, or
names it in a variable, may name a file relative to it. Such a token counts when the relative path
exists in a known payload. `SKILL.md` counts only when a tool reads it. Arriving as the skill's
prompt is not a tool read, and it is counted on neither side.

**Admissibility is per file, in context tokens** (F191). A session counts only if the core and each
unit it read **at all** each cleared one complete load of that file. The floor used to be
`bytes / 3.5`. Engine text actually enters the context at about 0.38 context tokens per byte, so
that floor admitted ~75% of a load. A unit the session never read is not required. Whether it was
due is a fact about the session's journal, which this tool does not read. The per-unit read counts
are printed so PR C can check them against each session's class.

**One complete load, per file, as measured.** Each row is the smallest ingestion among sessions
whose `Read` results cover every line of that file (`file.startLine`/`numLines` against
`totalLines`):

| era | file | bytes | one complete load (context tokens) | from |
|---|---|---:|---:|---|
| 0.2.0, 0.2.1 | `loop-engine.md` | 177,529 | 68,770 | vote `0baee1d7`, `098416fc`. The two eras' cores are byte-identical (`cmp`). |
| 0.3.0 | `loop-engine.md` | 267,647 | 101,828 | `baseline-2026-10-04.md` |
| 0.3.1 | `loop-engine.md` | 200,789 | 77,289 | claude-hook-validator `7b6d7a80`; vote `76f03bf5`, `a4a60fb7` at 77,509 |
| 0.3.1 | `phases/accepting.md` | 38,409 | 14,042 | `7b6d7a80`; `76f03bf5`, `a4a60fb7` at 14,080 and 14,130 |
| 0.3.1 | `phases/reviewing.md` | 32,344 | 11,826 | `76f03bf5`, `a4a60fb7`; `7b6d7a80` at 11,924 |
| 0.3.1 | `reference/initialization.md` | 3,489 | 1,510 | claude-hook-validator `f60e1176`, the only one |

The floor is 98% of the row. Hand-checked complete loads of the same file land up to 0.9% apart, because
ingestion is a context delta shared out across a turn's tool results. A file with no row is sized
at the **highest** measured tokens-per-byte, so it can be refused wrongly but never admitted wrongly.
The rows were measured on one tokenizer family, the `claude-opus-5` and `-5-5` parents. A parent on
another tokenizer needs them re-measured.

**Two limits.** The floor is a sum, so it catches a short load but not the same partial range read
twice. And `initialization.md`'s row rests on one session.

**Also added:** each unit's **arrival centroid**, the token-weighted turn at which its text
arrived, as a fraction of the session's turns. `baseline-2026-10-04.md` assumed 55% for `reviewing`
and 75% for `accepting`, and PR C measures it. The tool also adds **P6** (`<session>/subagents/*.jsonl`) and
`--table`, which prints one line per session and then the P2c median over the admissible sessions
with its order-statistic interval. **P7** stays where it was, read from each session's own
`- Budget:` line (`budget_stats.py` parses it). **P9** is the compaction count it always printed.

**Era registration.** `KNOWN_FILE_BYTES` holds 0.3.1's per-file sizes. `budget_stats.ERAS` has a
date-only 0.3.1 row: 0.3.1 writes no routine journal vocabulary of its own. Its boundary is
2026-10-10, the first day on which no treated repo could still be running 0.3.0.

---

## Re-admission: the frozen before side through the new check

Re-admission can only remove sessions. **It removed none.** All 23 clear the per-file check. P2,
P2c, P5, P6 and P9 reproduce `baseline-2026-10-04.md` for every session, at the precision it
publishes. Every completed-
iteration n stays at or above #126/AC3's bar of 5.

| | loop | vote | esg |
|---|---|---|---|
| n completed (all) | 8 (9) | 6 (7) | 5 (7) |
| **P2c, completed: median, interval** | **31.0%**, 27.2–36.4% (order stats 2, 7; 93.0%) | **29.0%**, 23.2–31.0% (1, 6; 96.9%) | **33.1%**, 30.0–35.1% (1, 5; 93.8%) |
| P2c, all | 31.2%, 27.2–38.1% (2, 8; 96.1%) | 29.0%, 23.2–40.5% (1, 7; 98.4%) | 34.9%, 30.0–48.2% (1, 7; 98.4%) |

The interval is the narrowest symmetric pair of order statistics covering the median with ≥90%
probability. At n=5 and n=6 that is the full range.

**One column moved, and on purpose:** `tree`, the working-tree engine reads, which sit in processed
context but never in P2. `b5129651` reads 13, not 11. Its two extra are working-tree reads of
`phases/accepting.md` and `reference/initialization.md`, which the 0.3.0 tool, counting only
`loop-engine.md`, could not see. The other three loop sessions with tree reads are unchanged, at 8,
11 and 3.

---

## The before side, priced (#133/AC3)

`tree_cost.py --sessions`, on the #212 cost-spec arithmetic in `stratum.py`: one turn per
`message.id`, priced once on its max-output line, each turn on its own model's weights, with 1-hour
cache writes at 2×. Prices are `stratum.PRICING_SOURCE`
(<https://platform.claude.com/docs/en/about-claude/pricing>, checked 2026-09-28). `claude-opus-5-5`
is $4 input and $20 output per MTok.

**No session refused to price, in any repo. The priced set is the admissible set.**

| | loop | vote | esg |
|---|---|---|---|
| **total per completed iteration, median** (interval) | **$28.38** ($16.82–33.42; 2, 7; 93.0%) | **$31.77** ($21.82–86.38; 1, 6; 96.9%) | **$23.45** ($20.33–30.21; 1, 5; 93.8%) |
| parent, median · subagents, median | $17.02 · $10.87 | $23.20 · $9.54 | $16.14 · $8.80 |
| completed iterations, summed: parent + subagents = total | $138.59 + $79.67 = $218.26 | $180.78 + $80.63 = $261.41 | $80.38 + $42.90 = $123.29 |
| subagent share of the summed bill | 36.5% | 30.8% | 34.8% |
| all qualifying sessions, summed | $226.98 | $271.97 | $131.26 |

The parent and subagent medians are separate medians. They do not sum to the total's median. Per
session:

| repo | session | class | parent $ | subagents | subagent $ | total $ |
|---|---|---|---:|---:|---:|---:|
| loop | `65894cf5` | plan stop | 6.06 | 3 | 2.66 | 8.72 |
| loop | `680e0a04` | completed | 27.50 | 12 | 10.87 | 38.37 |
| loop | `ac1dea98` | completed | 11.45 | 8 | 5.38 | 16.82 |
| loop | `1b66dd78` | completed | 21.31 | 14 | 12.10 | 33.42 |
| loop | `50fe6a39` | completed | 16.62 | 9 | 10.63 | 27.25 |
| loop | `7be48522` | completed | 19.50 | 12 | 13.24 | 32.75 |
| loop | `b5129651` | completed | 16.33 | 12 | 10.87 | 27.19 |
| loop | `de7e4367` | completed | 17.42 | 12 | 12.09 | 29.51 |
| loop | `22736589` | completed | 8.46 | 7 | 4.50 | 12.96 |
| vote | `601b5cdd` | other | 6.99 | 2 | 3.57 | 10.56 |
| vote | `93ac7d2a` | completed | 53.11 | 19 | 33.27 | 86.38 |
| vote | `82282b79` | completed | 23.99 | 10 | 7.76 | 31.75 |
| vote | `74df7f22` | completed | 46.99 | 14 | 13.44 | 60.43 |
| vote | `a24f0e20` | completed | 14.73 | 12 | 7.09 | 21.82 |
| vote | `956a112a` | completed | 22.42 | 12 | 9.38 | 31.80 |
| vote | `1f8431a9` | completed | 19.54 | 11 | 9.70 | 29.24 |
| esg | `9829c65c` | other | 2.50 | 0 | 0.00 | 2.50 |
| esg | `53a3d0e7` | completed | 16.14 | 9 | 7.30 | 23.45 |
| esg | `eb04dfe5` | completed | 19.90 | 11 | 10.31 | 30.21 |
| esg | `f2d07d41` | other | 3.57 | 2 | 1.90 | 5.47 |
| esg | `a1a6f18a` | completed | 15.93 | 9 | 5.98 | 21.90 |
| esg | `3e68d1dd` | completed | 16.88 | 10 | 10.51 | 27.40 |
| esg | `829df034` | completed | 11.53 | 10 | 8.80 | 20.33 |

Each session's parent bill agrees with `engine_cost.py`'s `billable_usd` for the same session, to
the cent. Both tools price through `stratum.turn_usd`, so this checks their record handling only. The
arithmetic is checked by the hand-check below.

### Why these figures may be cited

`tree_cost.py` was a scouting script whose output was not to be cited until it had passed two
checks. It has now passed both:

- **A hand-checked sample.** 20 of the 243 transcript files behind these sessions (seed 133; 2
  parents, 18 subagents) were re-priced by a separate script that shares no code with `stratum.py`.
  That script did its own `message.id` dedupe, from raw JSONL, at the per-MTok rates on Anthropic's
  model table. It agreed on every file to the cent, and on every turn count.
- **Physical bounds, enforced on every run.** A session refuses to price if any turn has context or
  output that no single API call could produce: more than 1M context tokens, or more than 128K
  output. Those are the widest window and the largest `max_tokens` of any priced model. A turn past
  them is a defect, typically a dedupe that merged several calls. None of these 243 files has one.

---

## How to reproduce

```bash
D=docs/research
L=~/.claude/projects/-home-fdpearce-Documents-Projects-git-claude-code-loop
s() { for id in "$@"; do ls $L/$id*.jsonl; done; }
python3 $D/engine_cost.py --table $(s 680e0a04 ac1dea98 1b66dd78 50fe6a39 7be48522 b5129651 de7e4367 22736589)
python3 $D/tree_cost.py --sessions $(s 680e0a04 ac1dea98 1b66dd78 50fe6a39 7be48522 b5129651 de7e4367 22736589)
```

Use the same commands for vote and esg, with their slugs and session lists from
`baseline-2026-10-04.md`. **Pass one repo's sessions of one class per call.** Both tools pool
whatever they are given, and neither can tell repos or classes apart itself.
