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
markdown file named by its full path under the cached `skills/dev-loop/`, so a unit a later release
adds is counted from its first install. A command that `cd`s into that directory, or names it in a
variable, may name a file relative to it. Such a token counts when the relative path exists in a
payload on disk. That form is only as wide as the payloads seen. `SKILL.md` counts only when a tool
reads it. Arriving as the skill's prompt is not a tool read, and it is counted on neither side.

**Admissibility is per file, in context tokens** (F191), and default-deny. The floor used to be
`bytes / 3.5`. Engine text actually enters the context at about 0.38 context tokens per byte, so
that floor admitted ~75% of a load. Now a session counts only if every engine file it read at all
cleared **its floor: 98% of one measured complete load of that file**. That means the core always,
and every other file except `SKILL.md` once read. Three things refuse a session outright:

- a required file with no measured load, or an unknown era. Nothing sizes it, and the tool does not
  estimate one: small files run denser, so no measured rate bounds the next file's;
- an **unattributable engine read**: a read that names the cached skill directory but resolves to
  no single file, such as a glob, an unresolvable relative name, a recursive grep, or the Grep tool
  on the directory;
- a load of any required file below its floor.

A read naming several files at once (`grep -n x phases/a.md phases/b.md`) makes each of them
required and credits none of them. They must each clear the floor through single-file reads.

**What the tool cannot see.** Whether a unit the session never read was *due* is a fact about the
session's journal. **Pre-registered here
for PR C, before any after-side data is seen:** in a 0.3.1 session, a unit is **due** when the
session's own journal names its step:

- `phases/reviewing.md` is due when the session wrote a step-8 code-review round block or a
  `- Code-review:` line;
- `phases/accepting.md` is due when it wrote an `- AC-verify:` line;
- `reference/initialization.md` is due when it wrote an Initialization block.

**A due unit that shows no load makes the session inadmissible**, whatever the reason. Either the
load was skipped or the detector missed it, and the session is unmeasured either way. PR C applies
this check with the frozen tool's per-unit read counts. It is not tuned after the data is seen.

A read the detector misses lowers P2, and neither this check nor the floors guarantee a refusal for
it. F194 on #1 logs the known shapes, and PR C's duty toward them.

**One complete load, per file, as measured** (`LOAD_TOKENS`). Each row is the **smallest**
ingestion among every session on disk (2026-10-10, `claude-opus-5` and `-5-5` parents) whose `Read`
results cover every line of that file. Coverage is checked as `file.startLine`/`numLines` against
`totalLines`, less the trailing empty line `Read` counts after a final newline:

| era | file | bytes | one complete load (context tokens) | set by |
|---|---|---:|---:|---|
| 0.2.0, 0.2.1 | `loop-engine.md` | 177,529 | 68,116 | vote `ab6d955b`. The two eras' cores are byte-identical (`cmp`). |
| 0.3.0 | `loop-engine.md` | 267,647 | 101,825 | vote `9b13c205` |
| 0.3.1 | `loop-engine.md` | 200,789 | 76,897 | claude-hook-validator `f60e1176` |
| 0.3.1 | `phases/accepting.md` | 38,409 | 14,042 | claude-hook-validator `7b6d7a80` |
| 0.3.1 | `phases/reviewing.md` | 32,344 | 11,826 | vote `76f03bf5`, `a4a60fb7` |
| 0.3.1 | `reference/initialization.md` | 3,489 | 1,510 | claude-hook-validator `f60e1176` |

Single verified loads of one file land up to 1.4% apart: the 0.3.1 core runs 76,897–77,974, and the
0.2.x core 68,116 to about 68,800. Ingestion is a context delta shared out across a turn's tool
results. Since each row is the minimum, the 2% below it is margin for a complete load that measures
lower than any yet seen. A missing page is far larger: 2% of the 0.3.1 core is ~1,540 tokens. A
test pins that band (`TolerancePinTests`): for every row, 95% of a load refuses and a whole load
admits. The rows were measured on one tokenizer family. A parent on another tokenizer needs them
re-measured.

**Two limits.** The floor is a sum, so it catches a short load but not the same partial range read
twice. And `initialization.md`'s row rests on one session.

**Also added:** each unit's **arrival centroid**, the token-weighted turn at which its text
arrived, as a fraction of the session's turns. `baseline-2026-10-04.md` assumed 55% for `reviewing`
and 75% for `accepting`, and PR C measures it. The tool also adds **P6** (`<session>/subagents/*.jsonl`) and
`--table`, which prints one line per session and then the P2c median over the admissible sessions
with its order-statistic interval. It prints the median only when they share one project
directory, era and stratum, and otherwise names the groups. `--all-reads` is gone: admissibility
counts plugin-cache loads only. **P7** stays where it was, read from each session's own
`- Budget:` line (`budget_stats.py` parses it). **P9** is the compaction count it always printed.

**Era registration.** `KNOWN_FILE_BYTES` holds 0.3.1's per-file sizes. `budget_stats.ERAS` has a
date-only 0.3.1 row: 0.3.1 writes no routine journal vocabulary of its own. Its boundary is
2026-10-10, the first day on which no treated repo could still be running 0.3.0.

---

## Re-admission: the frozen before side through the new check

Re-admission can only remove sessions. **It removed none**, run after the last edit to the
instrument (2026-10-10). All 23 clear the per-file check, and none holds an unattributable read.
P2, P2c, P5, P6 and P9 reproduce `baseline-2026-10-04.md` for every session, at the precision it
publishes. Every completed-iteration n stays at or above #126/AC3's bar of 5.

The same run admits each of the six 0.3.1 loop sessions this PR's calibration found:
claude-hook-validator `f60e1176`, `09b8f45f`, `7b6d7a80`; vote `76f03bf5`, `a4a60fb7`,
`0bec1f40`. None refuses as
unattributable, so the default-deny rules cost no n so far.

| | loop | vote | esg |
|---|---|---|---|
| n completed (all) | 8 (9) | 6 (7) | 5 (7) |
| **P2c, completed: median, interval** | **31.0%**, 27.2–36.4% (order stats 2, 7; 93.0%) | **29.0%**, 23.2–31.0% (1, 6; 96.9%) | **33.1%**, 30.0–35.1% (1, 5; 93.8%) |
| P2c, all | 31.2%, 27.2–38.1% (2, 8; 96.1%) | 29.0%, 23.2–40.5% (1, 7; 98.4%) | 34.9%, 30.0–48.2% (1, 7; 98.4%) |

The interval is the narrowest symmetric pair of order statistics covering the median with ≥90%
probability. At n=5 and n=6 that is the full range.

**One column moved:** `tree`, the working-tree engine reads, which sit in processed context but
never in P2. Its counts come from the new detector and do not compare with the 0.3.0 tool's.

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

`tree_cost.py` was a scouting script whose output was not to be cited until it passed two checks.
**Its `--sessions` mode now passes both. Directory mode does not and stays scouting.**

- **A hand-checked sample**, by `handcheck_pricing.py`. The script shares no pricing or dedupe code
  with `stratum.py`. It reads raw JSONL, does its own `message.id` dedupe, and prices from its own
  rate table, typed from Anthropic's model table. Run with `--seed 133 --sample 20` over the 23
  sessions in this page's order, it drew 2 parents and 18 subagents from 243 files. Every file
  agreed to the cent, and so did every turn count. The 20 files: parents `22736589`, `eb04dfe5`;
  subagents `agent-a2cabb03788d6f078`, `a0919388e185e34d2`, `a51a629f83f10e3b9`,
  `ad4149c9dbba698b8`, `acdda09dd1d00356e`, `a14c320ac976b7d47`, `aa9a09385f873765b`,
  `a3573bf2f5b68f930`, `aa4ecc51eac81478d`, `a442dc86ff5b40c41`, `ae2c55ab48de26ad8`,
  `a1766a07ab8c1f6c1`, `ad9d8f6881eaa9be1`, `a17799db4b3f95eec`, `a493691463534cab1`,
  `a4741b2534f060b85`, `a7d9b53878655e6cf`, `a8ed156415b2ffc3c`. A change to the arithmetic or the
  dedupe voids this check; re-run the script.
- **Impossible usage refuses, on every `--sessions` run.** A session refuses to price if any turn
  has context or output no single API call could produce: more than 1M context tokens, or more than
  128K output. Those are the widest window and the largest `max_tokens` of any priced model. It also
  refuses if a `message.id` is priced in more than one of its files. Either is a defect, typically a
  dedupe that merged or repeated calls. None of these 243 files has either.

`--sessions` totals only within one parent stratum, and all 23 sessions here share one.

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
`baseline-2026-10-04.md`. **Pass one repo's sessions of one class per call.** `engine_cost.py
--table` refuses to pool across project, era or stratum. `tree_cost.py --sessions` totals per
stratum only. Neither can see session class, which is yours to apply.

For the hand-check, pass all 23 sessions in this page's per-session order (loop, then vote, then
esg) to `python3 $D/handcheck_pricing.py --seed 133 --sample 20`.
