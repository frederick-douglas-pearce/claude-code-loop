# Loop cost & convergence — research notes

**Status:** open investigation. Not a plan, not a ruling. Nothing here has been through a gate.
**Opened:** 2026-08-24 · **Last updated:** 2026-08-25 (four ledgers + six profiled sessions + read/engine profile)
**Question:** why does a loop iteration cost what it does, and what would make it cheaper without
making it worse?

This file is a working notebook for that question. It records the measurements, the readings taken
from them, and the candidate levers — so the next session starts from the evidence rather than
re-deriving it. Findings that graduate become issues; this file is not a backlog.

---

## The problem as stated

Three symptoms, reported from live runs:

1. **Iterations run four or five review rounds**, disproportionately on changes whose implementation
   content is minor (test and docs updates).
2. **The parent context finishes far fuller than is healthy** — context rot and lost-in-the-middle
   are the suspected consequences. The target is a loop that completes at **100–200k parent
   context** and not much more.
3. **Scope is routinely split at the review gate**, which is a leading indicator that issues are
   being over-scoped at spec time.

---

## Method

`docs/research/budget_stats.py` parses `- Budget:` lines out of one or more ledgers and reports one
row per issue — the journal entry with the highest `subagent-runs`, the closest thing the ledger has
to a final cost — plus per-ledger aggregates.

```bash
python3 docs/research/budget_stats.py --era \
    ~/Documents/Projects/git/claude-code-loop/.claude/loop \
    ~/Documents/Projects/git/us_presidential_vote_analysis/.claude/loop \
    ~/Documents/Projects/git/agentfluent/.claude/loop \
    ~/Documents/Projects/git/claude-code-sessions/.claude/loop
```

`--era` additionally splits each ledger at the 0.0.1 → 0.2.0 upgrade, by two different detectors,
and flags where they disagree. Finding 1 turns on that disagreement — read it before trusting a
split.

**The numbers below are a dated snapshot and will go stale where they sit.** That is the failure
mode this repo documents repeatedly (`CLAUDE.md` → the enumerable-assertion trap), so the script is
the artifact and the table is an illustration. Regenerate before citing.

Three limits on what the data can carry, and the first is the one that matters most:

- **`subagent-runs` cannot see parent-thread burn.** The engine says so itself: a long implement step
  spawns no subagent yet can be the largest single consumer. So every number here is a proxy for the
  cost being investigated, never a measurement of it. **Nothing in the ledger measures symptom 2 at
  all** — see *Finding 4*.
- **Multi-entry issues were re-entered.** The counts on a later entry are cumulative for that issue.
- **`justification=` is a self-report** written by the orchestrator that spent the budget.

---

## Baseline (snapshot 2026-08-25, pre-#167)

Four ledgers, all consumers of this plugin:

| ledger | what it builds | review binding |
|---|---|---|
| `claude-code-loop` | this plugin — markdown an agent executes | inline finder fan-out |
| `us_presidential_vote_analysis` | Python data analysis (ruff + mypy) | fan-out + `/code-review` |
| `agentfluent` | the Python app the engine was extracted from | fan-out |
| `claude-code-sessions` | Python tooling (sanitizer) | **`/code-review` skill, bound on cost grounds** |

| | `loop` | `vote` | `agentfluent` | `sessions` |
|---|---:|---:|---:|---:|
| issues with a Budget line | 27 | 19 | 13 | 2 |
| subagent-runs — median / max | 7 / 14 | 3 / 9 | 2 / 6 | *see below* |
| gate-rounds — median / max | 5 / 10 | 3 / 7 | 2 / 6 | *see below* |
| journal entries per issue — mean / max | 1.7 / 5 | 1.1 / 2 | 1.7 / 4 | 1.0 / 1 |

`sessions` has **n=2 and no median is quoted on purpose**: its two rows are `#190` at 5 runs / 4
rounds and `#194` at 15 runs / 10 rounds, and #194's figure is a **floor reconstructed at resume
from the journal**, not a count — its own Budget line says so, and rounds 3–5 there were
human-directed. Averaging a reconstructed floor with a real count produces a number that means
nothing.

**In flight, deliberately excluded:** vote `#167` sat at **code-review round 5** on 2026-08-25 with
round 6 being put to the human. No terminal Budget line yet. It is the purest available instance of
symptom 1 — an expensive run against modest implementation content. **Re-run the script once it
lands and add it here.**

---

## What the data says

### Finding 1 — the 0.2.0 engine looks 2–3× more expensive than 0.0.1, and that is the headline

All consumers moved 0.0.1 → 0.2.0 on **2026-08-21**, and the loop executes the *installed* plugin,
so that date splits every ledger into two engine eras.

**Attributing an era is the subtle part, and getting it wrong inverts the result.** Two detectors —
the entry's date, and 0.2.0-only vocabulary in the entry (`in-acceptance`, `post-gate-survivors`,
`mutation-survivors`, `step 10`). They agree on **every row** of `vote`, `agentfluent` and
`sessions`, and disagree on **22 of 27** rows of `claude-code-loop`, all in one direction — because
that repo *writes* the 0.2.0 vocabulary into its ledger while still running the 0.0.1 engine. So
marker is the better detector for an ordinary consumer, and date is the only usable one for the
plugin repo itself. `budget_stats.py --era` prints both and flags the disagreement rather than
picking. The table below uses the right detector per repo:

| repo | engine | n | runs median | rounds median |
|------|--------|--:|------------:|--------------:|
| vote | 0.0.1 | 12 | 2.5 | 3 |
| vote | **0.2.0** | 7 | **6** | **5** |
| agentfluent | 0.0.1 | 12 | 2 | 2 |
| agentfluent | **0.2.0** | 1 | **6** | **6** |
| loop | 0.0.1 | 25 | 7 | 5 |
| loop | 0.2.0 | 2 | 6.5 | 4 |
| sessions | 0.2.0 | 2 | — (see above) | — |

In both repos with a clean before/after, cost roughly **doubles to triples** across the boundary.
`claude-code-loop` is the exception and the exception is informative: it was *already* at 0.2.0-era
cost under 0.0.1, because its deliverable is multi-site prose either way.

**The mechanism is not mysterious — it is the design.** 0.2.0 added the mutation pass (Class B), the
hermetic tier, the `in-acceptance` status, the currency clause, and made the Fresh-re-check
invariant mandatory. Each adds subagent runs and gate rounds *by construction*. The loop did not
regress; it got more rigorous and the cost followed.

**This reframes the question.** Not *"why is the loop expensive"* but **"which of 0.2.0's additions
earn their cost, and which are being paid on every issue regardless of risk?"**

**Evidence quality — read this before acting on it.** Only vote has a usable post-upgrade sample
(n=7); agentfluent is n=1 and sessions has no pre-upgrade rows at all. The split is confounded with
time and milestone — vote's late rows are the hybrid epic, plausibly harder than its July work — and
nothing controls for issue difficulty. **Suggestive, not established.** The honest status is a
strong hypothesis with one mechanism-consistent explanation, awaiting a prospective test.

### Finding 2 — the extra rounds are mostly *fix-induced* defects, not missed ones

Six of 48 `justification=` lines name it outright, and the three most recent vote iterations all say
some version of *round 2 earned its keep because it caught something round 1's fix introduced*:

> `round 1's fixes introduced six defects` (#45)
> `each remediation introduced fresh defects, which is what drove the split` (#22)
> `it found only defects the round-1 fixes had introduced` (#117)
> `it caught a false claim about a guard's behaviour introduced by the commit that was fixing false
> claims about guards` (#166)
> `round 2 then found a second false measurement introduced by the fix commit` (sessions #190)

Seven instances now, across all four ledgers and both review bindings — the single most consistent
signal in the corpus.

Consequences:

- **More or better finders in round 1 cannot help.** Those defects do not exist when round 1 runs.
- **The fresh re-check is the highest-yield agent in the loop** and is the last thing to cut. It is
  also, per Finding 1, one of the additions that made 0.2.0 more expensive — so it is the clearest
  case of a cost that earns itself.
- **The lever is fix-application quality** — the parent thread, applying N findings in one pass,
  deep into a long session, under exactly the context pressure symptom 2 describes.

Symptoms 1 and 2 are plausibly the **same defect**: a degraded parent writes worse fixes, which buys
another round, which degrades the parent further. **Hypothesis, not a measured causal claim** —
nothing records parent context, so the correlation cannot be computed. See *Finding 5*.

### Finding 3 — re-entry is a symptom, not an independent driver *(corrected 2026-08-25)*

The two-repo reading was that `journal-entries/issue` tracks cost. **Adding agentfluent falsifies
that as stated**: agentfluent's mean entries/issue is **1.7 — identical to `claude-code-loop`** — on
a median of 2 subagent runs against loop's 7. Re-entry is common and cheap there. `sessions` is the
other end: 1.0 entries per issue and the highest per-issue cost in the corpus.

What actually differs is **runs *per* entry**. #31 turned 5 entries into 13 runs; agentfluent's #112
turned 4 entries into 4. So re-entry multiplies whatever a gate cycle already costs, and does not
generate cost on its own.

The underlying observation survives intact, and it is the one that matters: **per-gate caps are 2,
were respected throughout, and cost compounded anyway**, because the currency clause re-arms an
upstream gate whenever a downstream one produces a fix. #167's own journal is the live instance —
*"Round 5's verdict no longer binds — the candidate moved."* **There is a cap on each gate and no
ceiling on the cycle.**

### Finding 4 — the cross-repo gradient is mostly engine era, not deliverable type *(corrected 2026-08-25)*

On two ledgers it looked like prose-as-product was intrinsically ~2× more expensive. With
agentfluent and sessions added and the engine split applied, **most of that gap is the 0.0.1/0.2.0
boundary**: 25 of loop's 27 rows are pre-upgrade, and so are 12 of vote's 19 and 12 of
agentfluent's 13. `sessions` — Python tooling, not prose — is post-upgrade only and is the most
expensive per issue of the four, which is the wrong direction for a deliverable-type explanation.

A residual repo effect is still plausible — loop is the only ledger whose 0.0.1 rows already sit at
0.2.0-era cost — but it is now a **smaller** term than the engine version, and the earlier reading
overstated it.

One observation is unaffected and still worth checking: **there is no `test` route.** A test-only
change lands on `code` and draws the full pipeline *plus* the hermetic tier *plus* the mutation
pass.

### Finding 5 — nothing measures the thing we are trying to fix

`tokens=deferred` on every one of the 48 Budget lines. The target is 100–200k parent context; there
is no record of parent context anywhere in any of the three ledgers, so the target is currently
unfalsifiable and no lever below can be evaluated against it. `tokens` is already a **reserved,
named slot**, so the seam exists.

**This is the prerequisite, not a lever.** Everything below was a guess until it landed — and it has now landed for the parent thread, from the session transcripts rather than the ledger. See **Finding 6**, which refutes two of the levers this file proposed. The ledger slot is still `deferred` and still worth filling, so the loop records its own cost without an external parse.

---

### Finding 6 — measured at last: the parent carries 313–534k, and it is file reads, not agents

*(added 2026-08-25; supersedes the guesswork in Findings 1–5's framing of where the money goes)*

`context_profile.py` reads the parent thread's own token accounting out of the session transcripts
(`~/.claude/projects/<slug>/*.jsonl`), so *Finding 5's* "nothing measures this" is now false. Six
vote-repo loop sessions, all confirmed genuine iterations (engine reads + ledger writes + 6–15
subagent traces each):

| session | parent turns | context at end | **peak context** | parent processed | subagents | subagent processed |
|---|---:|---:|---:|---:|---:|---:|
| c51f20e1 | 357 | 236k | **463k** | 86.6M | 15 | 42.9M |
| c60c8a44 | 109 | 313k | **313k** | 23.7M | 7 | 12.3M |
| 592ab44d | 136 | 366k | **366k** | 33.9M | 6 | 10.4M |
| d9933e33 | 161 | 92k | **409k** | 37.6M | 9 | 17.7M |
| d5ba0ddc | 224 | 88k | **534k** | 75.1M | 9 | 23.9M |
| f374d191 | 152 | 70k | **379k** | 34.4M | 7 | 13.7M |

**Every session peaks at 313–534k against a 100–200k target — 1.6× to 2.7× over.** Read *peak*, not
*context at end*: the three sessions ending at 70–92k got there by compacting, which is a cost, not
a success.

**The parent thread is 71% of all tokens processed**; subagents are 29%. Delegation is not where the
money goes.

**What actually enters the parent**, by source (share of attributed growth, across the six):

| source | share |
|---|---|
| `Bash` | 36–82% |
| `Read` | 1–37% |
| **`Agent` (subagent returns)** | **0.9–3.7%** |
| everything else | <1% each |

And within `Bash`, across five sessions (1.98M chars):

| class | calls | share | avg chars |
|---|---:|---:|---:|
| `cat`/`head`/`sed` | 187 | **56.3%** | 5,975 |
| `grep` | 130 | 11.0% | 1,679 |
| `ls`/`find` | 32 | 6.0% | 3,745 |
| **test runs** | **175** | **5.6%** | **639** |
| `git diff` | 10 | 2.7% | 5,320 |
| **lint/type** | **62** | **1.2%** | **375** |

**Reading files is the whole story.** `cat`/`head`/`sed` + `Read` + `grep` dominates every session.
The single largest repeated read is the orchestrator loading **`loop-engine.md` itself**. This
document first recorded that as "31,126 chars, ~8k tokens, once per invocation … unavoidable and
arguably well spent." **That was wrong in both halves** — the 31,126-char result was a *truncated*
18% of the file, and the true figure is ~4× larger. See **Finding 8**.

**Two of this document's own levers are refuted by this table, and one is reframed:**

- **Lever B (constrain finder returns) — largely refuted.** `Agent` returns are **0.9–3.7%** of what
  enters the parent. Eliminating them entirely would not move the number. The fan-out still costs,
  but on the **subagent** side (29% of total), never in parent context. The lever was aimed at the
  wrong quantity.
- **Lever H (format/lint hooks) — refuted *as a context lever*.** lint/type output is **1.2%** of
  Bash volume at **375 chars per call**, and test output is 5.6% at 639. The fix-until-green loop is
  not what fills the parent. The hook may still be worth building for wall-clock, round-trips and
  determinism — but it must not be sold as a context saving.
- **The cost model is multiplicative: `cost ≈ context × turns`.** Every turn re-reads the
  accumulated prefix at cache-read rates, which is why 357 turns at ~242k average context bills 86.6M.
  So **a gate round late in an iteration costs far more than the same round early**, because it
  processes the whole accumulated prefix each turn. This is the quantified link between symptom 1
  and symptom 2 that *Finding 2* could only hypothesize: rounds are expensive **because** context is
  large, and context is large **by the time rounds happen**.

**The prescription that follows is "fail earlier", not "fewer gates".** A defect caught at step 5
costs a fraction of the same defect caught at step 10 round 3 — not because the gate is cheaper, but
because the prefix it re-reads is smaller. That is an argument for *moving* rigor earlier, which is
the same conclusion **Lever E** (scope budget at the plan gate) reaches from a different direction.

### Finding 7 — the new dominant lever is read discipline, and it did not appear anywhere above

Nothing in the original lever list addresses file reading, because nobody had measured it. Concrete
candidates, in the order the data supports:

1. **The parent re-reads the same large files.** Now measured, and the answer is emphatic:
   **78.6% of all file-read volume sits in files read more than once**, and `loop-engine.md` alone
   is **50%** of everything read. Only **2.1%** is a byte-identical re-read, so the pattern is
   paging and recovery, not naive duplication — see **Finding 8**.
2. **`sed -n` slices average ~6k chars.** Several exceed 30k. Bounded-window reads with an explicit
   cap would cut the tail without changing behavior.
3. **Delegate reading, not just work.** The one thing the data says is cheap is a subagent return
   (~1–4%). An agent that reads five files and returns a 500-token answer is close to free in parent
   context. This inverts the usual advice and is the strongest single finding here.


### Finding 8 — loading the engine costs ~58k tokens a session: half of all file reading

*(2026-08-25; corrects Finding 6's engine figure, which was measured off a truncated read)*

`loop-engine.md` is **177,529 bytes / 2,271 lines ≈ 44,400 tokens.** `cat`-ing it does not put it in
context: the harness caps Bash output at ~31k chars — **18% of the file** — and spills the remaining
177KB to `<session>/tool-results/<id>.txt`, recording `persistedOutputSize` in the result envelope.
**All six sessions spilled it.** The orchestrator then recovers the rest one of two ways, and both
were observed:

- a **five-part `Read` sweep** (`offset` 0/500/1000/1500/2000, 183k chars) — 3 sessions;
- **paging the spill file back** in 6–8 `sed`/`cat` slices (165–184k chars) — 3 sessions.

Either path lands the whole engine, so **the first, truncated `cat` is pure waste** — and where a
`sed -n '1,400p'` was tried in between, that is wasted too.

| session | engine reads | engine chars | ~tokens | all file reads | engine share |
|---|---:|---:|---:|---:|---:|
| c51f20e1 | 13 | 270,061 | 67,515 | 762,155 | 35% |
| c60c8a44 | 8 | 213,131 | 53,282 | 363,288 | **59%** |
| 592ab44d | 7 | 245,540 | 61,385 | 355,172 | **69%** |
| d9933e33 | 9 | 214,773 | 53,693 | 351,152 | **61%** |
| d5ba0ddc | 7 | 245,639 | 61,409 | 524,301 | 47% |
| f374d191 | 8 | 211,110 | 52,777 | 434,520 | 49% |
| **total** | | **1,400,254** | **350,063** | 2,790,588 | **50%** |

**The engine is 50% of every byte the parent reads, and ~58k tokens per session** against a 200k
target — **29% of the budget, spent before the loop does any work.** Of that, ~44k is irreducible
(the file's own size) and **~14k is the truncated-`cat` dance.**

Three consequences, in increasing order of importance:

1. **~14k tokens a session is recoverable for one sentence.** `SKILL.md` tells the orchestrator to
   read the engine; it does not say *how*. Saying "use `Read`; the file exceeds the Bash output cap"
   deletes the wasted `cat` and any `sed` follow-up. (`Read` itself is efficient — ~80 chars per
   line against the file's own 78 bytes per line, ~3% overhead.)
2. **The 44k floor is a product problem, not a prompting one.** No instruction makes a 2,271-line
   monolith smaller. The only lever is structural: let an invocation load the part of the pipeline
   it is actually at, rather than all twelve steps plus the ledger format, router, AC-verifier,
   Resume and gate table. That is a real design change with real risks — `SKILL.md`'s fail-safe
   posture exists *because* partial loads are dangerous (below) — and it is not proposed here, only
   measured.
3. **The truncation is a correctness hazard and it is fail-open.** A session that `cat`s the engine
   and does not notice gets **lines 1–400 of 2,271** — steps 0–5 and nothing else. No implement, no
   commit/PR, no review, no security, no acceptance, no merge, no journal; no ledger format, router,
   AC-verifier, Resume, or gate table. All six sessions here happened to recover, but **nothing in
   the engine or `SKILL.md` requires it** — the truncation is advertised only as a
   `persistedOutputSize` field the model may or may not act on. By this project's own default-deny
   rule, *an engine read that cannot be shown to be complete should be treated as incomplete.*
   That is the same posture the merge gate and the `plan-gate:` field already take, and it is the
   one place the loop's own bootstrap does not take it.

**This is the strongest single finding in this document**, and it is the one most likely to be
worth an issue: item 1 is nearly free, item 3 is a fail-safe gap in the bootstrap, and item 2 sizes
the ceiling on everything else here.


### Finding 9 — where the engine's 178KB actually is, and why "define once, reuse" recovers ~1%

*(2026-08-25, in response to the compression question)*

**The twelve pipeline steps are only ~32% of the file.** The bulk is reference material:

| section | lines | share |
|---|---:|---:|
| AC-verifier | 372 | **16.3%** |
| Gates, convergence & resting states | 276 | **13.4%** |
| `progress.md` worked example | 264 | **12.0%** |
| 6. Implement | 163 | 7.3% |
| `queue.md` format | 160 | 7.0% |
| Resume | 125 | 5.8% |
| Tool surface | 111 | 5.2% |
| 5. Human gate | 111 | 5.0% |
| *(all other steps 0–4, 7–12)* | | *~19%* |

**Literal repetition is not the lever.** Shingling the file on 12-word windows: **64** repeated
windows, **1.0%** of the file inside a repeat beyond first occurrence. A macro or include mechanism
would recover about one percent. The multi-site invariants `CLAUDE.md` warns about are real, but
they are restated **in different words at each site** — which is exactly why they *drift*, and
exactly why no mechanical dedup reaches them.

**And the semantic version of that idea is already chartered and already blocked.** Collapsing the
restatements to one canonical passage is **#35**, deferred at its plan gate 2026-08-18 because the
sites *have* diverged (F57/F58 on #1): its AC1 (state it once) and AC3 (no semantic change) are in
direct conflict while the drift stands, since collapsing divergent sites silently picks a winner.
**Do not re-derive this as a compression idea** — it is a correctness problem wearing a compression
costume.

**Maintainer rationale is a real but modest term.** Sentences carrying a rationale or history marker
("deliberate", "do not tidy", "for the record", "#N shipped", "used to say") are **7.1% / ~3.1k
tokens per invocation.** Treat that as a **floor**: marker detection cannot see rationale woven into
an instruction's own clause, and much of this file's is. Splitting runtime instruction from
maintainer commentary is worth doing on its own merits — the engine is the one artifact where every
maintainer-facing sentence is billed to every consumer, forever — but on this measurement it is not
the headline.

**The lever the data actually supports is load-on-demand sectioning: ~42% is deferrable.**

| deferrable section | share | needed when |
|---|---:|---|
| AC-verifier | 16.3% | step 10 only (Part 2 is further route-scoped) |
| `progress.md` worked example | 12.0% | step 12 / init |
| `queue.md` format | 7.0% | init only |
| Resume | 5.8% | only when step 0 finds a mid-pipeline row |
| Initialization | 1.1% | new run only |

And a large share of invocations never reach most of it: **39 of 345 journal entries across the four
ledgers stopped at the plan gate** — step 5 — having loaded 100% of the engine to execute perhaps a
quarter of it. That 11.3% is a **floor**; header-based classification leaves 56% unclassified.

**The shape this suggests** is the plugin's own three-layer split applied one level down: a core
`loop-engine.md` carrying the pipeline, the gate table, the routing table, the Tool surface and the
fail-safe invariants; and `procedures/*.md` — AC-verifier, ledger format, Resume, Initialization —
that the core **names at the point of use** with an explicit "read this now before proceeding".

**The constraint that makes or breaks it, stated before anyone builds it:** `SKILL.md`'s entire
design assumes a partial load **over-escalates**. So the core must keep the *fail-safe half* of
every deferred section even when the procedure moves out — the core says "the acceptance gate is due
on every issue with acceptance criteria and either class blocks"; the procedure says how to run it.
Get that wrong and this trades ~42% of the tokens for the exact failure mode **Finding 8** just
documented: a coherent-reading engine that silently ends before a gate.

**Why this is a product issue, not a personal cost issue.** At ~44k tokens the engine consumes 29%
of a 200k budget before the loop does any work, on every invocation, in every consuming repo. That
is a floor a consumer cannot opt out of and cannot tune, and it scales with nothing they control.

**Whatever is attempted, it is now falsifiable.** `context_profile.py` measures the before and the
after on a real session. No engine-size change should land without that pair of numbers.

---

### Finding 10 — ingestion is not cost: the engine is carried for ~91% of a run

*(added 2026-08-26. **Rewritten twice the same day**, each time because the measuring instrument was
wrong — see "Three detection bugs" below. Every number is a frozen snapshot, not a maintained
figure. Reproduce with `engine_cost.py`; its detection is pinned by `test_engine_cost.py`.)*

Findings 6–9 measure **ingestion**: engine tokens counted once, when they land. That tracks the
lever, but it is not a cost proxy — a token arriving at turn 12 of a 109-turn session is
re-submitted on the 97 turns that follow.

| repo | session | turns | cmp | ingested | carry | **carry/turn** | **% of bill** | bill/turn | |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| loop | `b40adacf` | 109 | 0 | 54,221 | 98× | 0.90 | 18.3% | 33,035 | |
| loop | `fd687f48` | 231 | 1 | 52,808 | 134× | 0.58 | 10.7% | 31,905 | |
| loop | `a587e8e4` | 422 | 3 | 21,589 | 146× | 0.35 | 3.3% | 27,715 | **excluded** |
| vote | `d9933e33` | 161 | 1 | 62,014 | 77× | 0.48 | 10.8% | 36,041 | |
| vote | `d5ba0ddc` | 224 | 1 | 75,183 | 206× | 0.92 | 18.4% | 41,715 | |
| vote | `9b188aba` | 158 | 0 | 69,077 | 145× | 0.92 | 20.8% | 35,774 | |
| vote | `592ab44d` | 136 | 0 | 65,868 | 132× | 0.97 | 22.2% | 34,583 | |
| vote | `7bcec8a4` | 92 | 0 | 69,077 | 84× | 0.91 | 27.7% | 25,969 | |
| | **median (admissible, n=7)** | | | **65,868** | | **0.91** | **18.4%** | | |

**The engine is ~18% of a run's bill and is carried for ~91% of every run it enters.**

**Use `carry/turn`, never raw `carry`.** Raw carry scales with session length, so a median of it
across runs spanning 92–422 turns describes the sample, not the system. `carry/turn` —
resident-turn ÷ (ingested × turns) — is the turn-invariant form: the mean fraction of the run each
engine token is carried for. It is the number that generalises.

**Admissibility is a precondition, not a filter.** A session enters the sample only if its measured
ingestion clears **one copy of the engine** (~50.7k tokens). Below that floor the engine either
never fully loaded or the detector missed reads — and in both cases the session is **not a cheap
run, it is an unmeasured run**. `a587e8e4` is excluded on this rule. Stating it as default-deny
matters: the earlier draft of this finding read a below-floor session as a *result* and built a
narrative on it (see below). Unknown ⇒ inadmissible, never quietly averaged in.

**1. Turn count, not context size, drives the variance.** Across the eight sessions turns span
**4.6×** while billable-equivalent *per turn* stays in a narrow band (mean 33,342, sd 4,972,
**CV 15%**).

> **cost ≈ turns × ~33k**

The CV is a consistency check, not the argument. **The argument is structural: average context per
turn is bounded above by the compaction ceiling and below by the session's starting footprint, so it
lives in a narrow band by construction, while turn count has no ceiling at all.** That is why this
does not rest on n=8. *Falsifier: a session that never approaches the ceiling and whose bill/turn
still falls outside the band.* This puts **Finding 2 — extra rounds are mostly *fix-induced*
defects — back as the dominant cost lever**, ahead of engine size.

**2. Cache is a uniform ~8× discount, not a lever.** 97.6–98.9% of input tokens are `cache_read` at
0.1×. Because the discount covers essentially the whole prefix, **share of context ≈ share of
cost**. That single fact carries the conclusion; the "two models agree within 15%" corroboration
this document previously offered has been **deleted as circular** — with `cache_read ≈ 0.98 × ctx`,
the positional model reduces to `0.1 × resident_turns`, so the two functions cannot disagree.
**P8 and P2c are one measurement reported twice** (`P8 ≈ P2c/processed`, scaled), and #128 must not
carry both as independent acceptance criteria.

**3. Output tokens are ~13–19% of the bill and are now included.** They bill ~5× input against a
~8×-discounted input side. They are attributed to the *model*, not to the engine — the engine takes
a share of the input side only. Note the direction: **including them cuts against this document's
own preferred conclusion**, since output is purely turn-proportional and wholly immune to sharding,
so excluding it was under-rating the convergence lever relative to sharding.

**4. Compaction is currently the only thing that reduces engine residency, and it is the worst
possible mechanism** — the parent then re-reads the engine at cache-*write* rates (1.25×), 12.5×
the cache-read rate it was being carried at. Every zero-compaction session sits at **0.90–0.97**
carry/turn; the compacted ones range **0.35–0.92**. So compaction is *necessary but not sufficient*
to reduce carry — `d5ba0ddc` compacted once and still carried 0.92. **This is a directional
relationship on n=8, not the clean split it first appeared to be**, and it should not be quoted as
one. It does suggest sharding's second-order benefit — fewer compactions — may exceed its
first-order one, which is worth a metric (P9, compaction count) before the epic closes.

**What this means for sharding.**

- **Expect ~4–5% of a run, not ~7%.** The 46k→30k figure is **P1, the file on disk**, and applying
  it proportionally to residency repeats the exact ingestion/cost conflation this finding exists to
  correct. Sharding is *deferral*, not deletion: in a full iteration the deferred units still load,
  and only the arrival centroid moves. ~7% is the ceiling, reached only where deferred units are
  never loaded at all (plan-gate stops, and the reference appendix).
- **"When" is worth a substantial fraction of "how much" — and the fraction is unmeasured.**
  Deferring a unit to step 10 of 12 is worth deletion × (turns after step 10 ÷ 0.91). **That
  denominator is a step→turn mapping nobody has measured**, and it is not linear: steps 8–10 are
  where the review rounds live, which is where Finding 2 says the turns go. The plausible range is
  **44–78%** of deletion's value. Measure it from the transcripts before quoting a figure.
- **P2c's acceptance criterion must be turn-invariant.** Raw resident-turn tokens scale with turn
  count — the most confounded quantity in this corpus — so a post-sharding run on a hard issue would
  show P2c *up*. Use **`resident_turns / processed`** (engine share of average context), which is
  dimensionless and direct. Keep raw P2c as a reported quantity only.
- **The named falsifier for P2c is re-load after compaction**, not just truncation: a deferred unit
  re-loaded post-compaction bills at 1.25× rather than 0.1×.

#### Three detection bugs, and the pattern they form

This finding was published twice with wrong numbers before this version. All three bugs were in
detection — a pure function of `(tool name, tool input)` — and **all three were silent**:

1. **Heredoc bodies counted as reads.** `cat > progress.md <<'EOF' …` whose body discusses the
   engine scored as an engine load. One vote session showed 9 reads where 1 was real. *This
   over-counted, producing a high engine share — which supported sharding.*
2. **Working-tree reads counted as loads.** Reading `skills/dev-loop/loop-engine.md` is an agent
   *editing the engine as a work product*; only `/plugins/` paths are loop costs. `a587e8e4` carried
   20 tree reads against 18 loads.
3. **Spill-file recovery reads were invisible.** A `cat` of the engine exceeds the inline limit, so
   the harness parks it at `<session>/tool-results/<id>.txt` and hands the model a 2KB preview; the
   recovery reads then target **the spill path**, which contains no `loop-engine.md` substring.
   `d9933e33` measured **6,088** tokens against a true **62,014**. *This under-counted — and the
   result was immediately written up here as "the F105 truncation caught in the act", a claim that
   was **false** and has been withdrawn in full, along with its "low engine load is not by itself
   good news" generalisation.*

Bug 3 also corrupted sizing: on a spilled record `toolUseResult.stdout` holds the full output while
the model received only the preview — 29,752 chars against 2,246, a **13× overstatement**. Sizing
now comes from the tool_result *block* content, which is what actually entered the window.
`context_profile.py` has the same inversion and has not been corrected.

**The pattern is the finding.** Bug 1 moved the number *up* and was accepted because it supported
the case for sharding. Bug 3 moved it *down* and was accepted because it looked like a known defect
being caught. **Both were believed because they pointed where the reader was already looking** —
which is Finding 2's fix-induced-defect mechanism reproducing inside the measurement apparatus, one
round later.

Two durable defences, both now in place:

- **A distributional sanity rule beats a narrative.** Admissible sessions cluster at 52.8k–75.2k
  ingested — 1.0–1.5× the engine's own token count, the truncated-`cat`-plus-sweep dance. 6,088 is
  not a member of that distribution. *Any session measuring below one copy of the engine is a
  detector failure until proven otherwise.* That is checkable; "caught in the act" is not.
- **The instrument has fixture tests** (`test_engine_cost.py`, 20 cases), each pinning a real
  transcript shape, with the three bugs above named in the cases that catch them. Deliberately under
  `docs/research/` and **not** `tests/`, so it stays out of the shipped suite — the scope brake puts
  a guard on analysis infrastructure in `tech-debt`, never in a release.

**Remaining caveats.** `chars/context-token` (3.25–3.82) is a **pipeline constant** for this read
pattern, not the tokenizer's ratio; a real `count_tokens` call would settle it exactly and remove
the estimate every other figure rests on. Residency needs an eviction model; `NONE`/`PROP`/`FULL`
bracket it and `PROP` is quoted (`NONE` is "nothing evicted except what the context ceiling forces",
not "nothing evicted"). The subagent *bill* is still unpriced, which matters because two proposed
levers move work into subagents. All eight sessions are 0.2.0; **there is no v0.2.1 measurement
yet.**

### Finding 11 — the join: one extra gate round costs about what loading the engine costs

*(added 2026-08-26. This is the test the cost ranking rested on: if gate rounds did not predict
turns, Finding 10's ranking of convergence above sharding was wrong. Reproduce with
`rounds_vs_turns.py`.)*

`- Budget:` lines are written by the parent into `progress.md`, so the session that produced one
also contains it. Joining those to parent turn counts, across eight sessions in two repos:

| session | turns | issues | rounds | subagent-runs | turns/issue | **rounds/issue** | bill/issue |
|---|---:|---:|---:|---:|---:|---:|---:|
| `fd687f48` | 231 | 2 | 4 | 6 | 116 | 2.0 | 3,685,064 |
| `7bcec8a4` | 92 | 1 | 3 | 4 | 92 | 3.0 | 2,389,110 |
| `592ab44d` | 136 | 1 | 4 | 6 | 136 | 4.0 | 4,703,345 |
| `b40adacf` | 109 | 1 | 5 | 8 | 109 | 5.0 | 3,600,805 |
| `d9933e33` | 161 | 1 | 5 | 9 | 161 | 5.0 | 5,802,670 |
| `9b188aba` | 158 | 1 | 7 | 6 | 158 | 7.0 | 5,652,370 |
| `d53db569` | 178 | 1 | 7 | 7 | 178 | 7.0 | 6,318,506 |
| `d5ba0ddc` | 224 | 1 | 7 | 6 | 224 | 7.0 | 9,344,236 |

    rounds/issue -> turns/issue     r = +0.79      turns/issue ≈  59 + 17 x rounds
    rounds/issue -> bill/issue      r = +0.77       bill/issue ≈ 938k + 850k x rounds
    subagent-runs -> turns          r = +0.10

**One extra gate round costs ~17 turns ≈ 850k billable-equivalent tokens.** For scale, the engine's
*entire* contribution to a typical run is ~1.0M (Finding 10). So:

> **Avoiding one gate round is worth roughly as much as not loading the engine at all — and about
> 3–4× what the whole sharding epic is projected to save.**

**Subagent count does not predict turns (r = +0.10).** That is a useful negative: the cost is not in
*how many* agents run, it is in *how many times the pipeline goes round*. It argues against
"fewer/cheaper subagents" as a cost lever and against reading the `subagent-runs` figure in the
ledger as a cost proxy — it is a fan-out measure, not a budget one.

**The intercept is the floor and it is not small.** ~59 turns per issue before any gate round —
roughly 2M billable-equivalent. A perfectly converging issue still costs that, and no convergence
work touches it. That floor is where sharding and read discipline apply.

**Correlation is not causation here, and the confound is obvious: a harder issue plausibly causes
both more rounds and more turns.** This join cannot separate them and does not try. What makes the
causal reading credible is **Finding 2's separate, mechanism-level evidence that most extra rounds
are *fix-induced*** — defects created by the previous round's fix rather than inherent to the issue
— across 7 instances in 4 ledgers. The join establishes that rounds are *expensive*; Finding 2
establishes that many of them are *avoidable*. Neither claim carries the other, and quoting the
`+0.79` alone would overstate it.

**Caveats.** n=8 sessions / 9 issues. The session↔issue mapping is many-to-many, so per-issue
figures are within-session averages. `a587e8e4` is excluded and the exclusion was checked by hand:
its twelve `- Budget:` matches are all *prose about* budget lines in plan files, not ledger entries,
so it journaled none in that session.

**Two detection bugs were found and fixed while building this**, both the same shape as Finding 10's
three, which is now a pattern worth naming rather than a coincidence:

1. **Direction.** Counting every `- Budget:` occurrence in a transcript counts lines the parent
   *read back out of* `progress.md` as work done in that session. It gave one 158-turn session
   **11 issues at 14 turns each**, against an engine whose rule is one issue per invocation. Only
   `tool_use` **inputs** count.
2. **Line wrapping.** Budget lines wrap, so `gate-rounds=` routinely sits on a continuation line. A
   single-line regex captured the prefix, found no rounds, and dropped the row — losing three of
   nine sessions silently. This is the same wrapped-text hazard `CLAUDE.md` documents for the
   engine's step references.

**Every one of these five bugs was a silent false result in a plausible direction.** The defence
that keeps working is not a better pattern — it is **checking a sample of matches by hand, and
sanity-checking the output distribution against what the system can physically do** (one issue per
invocation; ingestion ≥ one engine copy). Do both before believing any transcript-derived number.

## Candidate levers

Ranked by (expected saving × confidence), with the reasoning that places them. None is a decision.

### A. Record parent context at step 12 — *prerequisite*
Even a coarse self-report fills the reserved `tokens` slot and makes symptom 2 measurable, the
Finding-1 hypothesis testable, and every lever below evaluable. Cheapest thing on the page and it
gates the value of the rest.

### B. Constrain what finders return — *REFUTED; header corrected 2026-08-26*

> This header read *"high saving, high confidence, small edit"* until 2026-08-26, while
> Finding 6 above already recorded the lever as largely refuted (`Agent` returns are
> 0.9–3.7% of what enters the parent; under 1% of a run on the bill model). Two
> restatements of one claim, drifted, in the same file — the pathology `CLAUDE.md`
> documents at length, occurring in the research notebook itself. Fixed in place rather
> than guarded.
Step 8 says nothing about return shape. Finders should return a bounded structured list —
`file:line`, one-sentence claim, failure scenario, severity, hard cap ~5 — with **no narrative and
no restating the diff**. The parent needs verdicts, not reasoning. `loop.config.md` prices this gate
at **≈15–25 subagent runs on a hard issue**; every one of those returns prose into the parent.

### C. A ceiling on the re-arm cycle — *directly targets Finding 2*
`- Budget:` already records `gate-rounds` per gate, so the data exists. An iteration-level total
that stops and escalates with state, rather than a per-gate cap the cycle re-arms. Note this is a
**stop**, not a merge — it routes to the human, which is the posture the merge gate already takes.

### D. Apply the scope brake's rule 1 *inside* the review gate — *directly targets Finding 1's tail*
Findings default to the #1 index, not to a round. A finding that is not a correctness or behavior
defect **in this diff** becomes an F-comment, never another pass. The tail rounds are
disproportionately polish. Not fail-open by this repo's standard: the human still approves every
merge, so the backstop is intact.

### E. A declared scope budget at the plan gate — *targets symptom 3*
Splitting at review means **the review gate is currently doing the scoping**. The plan gate already
stops for a human on every issue under `plan-gate: always` — the right gate is already there, it is
just not being asked the right question. Have the plan declare files-to-touch, AC count, and rough
diff size; over budget ⇒ split before implement. Converts an expensive late split into a free early
one. This repo has the milestone-level version of the rule already (the scope brake); this is its
per-issue form.

### F. A documentation subagent at the **end of step 6** — *targets Finding 1's cause*
Step 6 says exactly one thing about docs: *"Implement code + tests + docs per the plan."* In this
repo that expands to a multi-site consistency propagation, which is a good subagent brief (diff +
site list + rule → returns a patch) and a bad inline parent task.

**But not *after* code review, and this is the trap.** The currency clause means a commit no gate
ran on does not inherit that gate's verdict. Landing docs after step 8 re-arms code review on
**every** run, permanently — a cost *increase*. The win is the agent, not the reordering. Put it at
the end of step 6, before the commit.

Second-order caveat: a subagent that returns a patch the parent must *read* saves less than it
looks. Prefer a worktree the parent applies from a path.

### G. Pull #38 (`REVIEW_TIERS`) forward — *the order-of-magnitude lever*
`v0.3.0`'s criterion is *waits on corpus, not effort.* #38 was deferred because the corpus did not
exist. The corpus in this file is the argument that it now does. Worth an explicit re-test of the
deferral criterion rather than letting it sit by inertia.

**One caution, and it cuts against the obvious version of this lever.** `claude-code-sessions` binds
`CODE_REVIEW` to the `/code-review` skill rather than the fan-out, **explicitly on cost grounds** —
its config cites the same ≈15–25-runs-vs-one-invocation figure. Its clean row (`#190`) came in at
**5 subagent runs / 4 gate-rounds**, against vote's 0.2.0 fan-out median of 6 / 5. That is rough
parity, **not the order of magnitude the arithmetic predicts.** n=1, so it settles nothing — but it
is the only direct evidence on the binding that exists, and it does not support the saving. The
plausible reading is that the fan-out is not the dominant term; rounds are, and the skill does not
reduce rounds. **Do not cite the ≈15–25 figure as an expected saving without testing it.**

### H. Mechanize the mundane: format/lint/type as a hook, not a model turn
`LINT_CMD`/`TYPE_CMD` at step 6 are a **fix-until-green loop in the parent thread**: run → read
output into context → edit → re-run, with zero design content. Three tiers, cheapest first:

1. **Deterministic rewriters need no model at all.** `ruff format`, import sorting and friends are
   pure functions of the file. A hook on `Write`/`Edit` — or pre-commit — that runs them silently is
   zero tokens and zero rounds. The plumbing already exists: `guard_append_only.py` is a
   `PreToolUse` hook with a config-driven, **fail-open-until-opted-in** posture, and an autoformat
   template would follow the same shape (`hooks/loop.autoformat.json` naming commands per glob).
   *The vote repo runs ruff + mypy today, so it is the natural first consumer.*

   **One asymmetry to get right:** `ruff format` is semantics-preserving and safe to apply silently.
   `ruff check --fix` is **not** uniformly safe — some fixes are behavior-adjacent. Format-only in
   the hook; lint-fix stays in the visible loop. A hook that silently rewrites semantics is a new
   defect source, which is the opposite of the goal.

2. **A "green-up" agent on a cheap model** for what is left: mypy errors, judgment-requiring lint
   rules, obvious test breaks. Tight brief, **verified by exit code** — so a weak model cannot fake
   success, which is what makes this delegation safe where others are not. Needs a worktree
   (`PERMISSION_POSTURE` keeps subagents read-only), and the parent should apply from a path rather
   than read the patch.

3. **Model tiering generally.** The loop runs everything at one tier today and the engine has no
   vocabulary for it. Candidates, ranked by saving × safety: **green-up** (best — exit-code
   verified), **docs agent** (good — verifiable against the diff), **mutation-selector**
   (mechanical). **Not finders, and not the fresh re-checker.** Their whole value is judgment on a
   risk surface; a cheap finder returns plausible noise, and noise costs **rounds** — the expensive
   axis. Downgrading the re-checker specifically contradicts Finding 1.

### Considered and set aside

- **A dedicated tester agent.** Context overlap with implementation is near-total and tests are
  written with the code. The mutation harness already occupies the one test-shaped niche that
  delegates cleanly.
- **Narrowing step 8's re-check base** from `main...HEAD` to `<pre-fix-sha>...HEAD`. Cheaper and
  more focused, and the engine's stated reason for `main...HEAD` is fix *visibility*, which the
  narrower base preserves. **But** it gives up regression detection outside the fix — and Finding 1
  says fix-induced regressions are the dominant defect class, so this is probably backwards. Left
  here as a recorded rejection.

---

## Open questions

1. **Is Finding 1's loop real?** Does degraded parent context actually correlate with fix-induced
   defect rate? Unanswerable until lever A lands.
2. **Does a `test` route pay for itself,** or is test-only work rare enough not to matter? Check
   route distribution before building anything.
3. **What is the actual parent-context profile of an iteration** — where does it go? Finder returns
   and inline lint/type output are the two suspects; neither is measured.
4. **Would B alone hit 100–200k,** or is the parent's own file reading the dominant term?
5. **Does #167 fit Finding 1,** or is it a different shape? It is the best single test case available
   and it has not landed yet.

## Provenance

Opened from a brainstorming session on 2026-08-24, extended 2026-08-25. Measurements from four
ledgers: `claude-code-loop` (`v0.2.0`, `v0.2.1`), `us_presidential_vote_analysis` (`chores`,
`epic-hybrid`, `epic-internal-api`, `epic-publishing`), `agentfluent` (`v0.10.0`–`v0.12.0`) and
`claude-code-sessions` (`epic-sanitizer`). Ledgers are gitignored local state
and are **not** reproducible from this repo alone — the script needs a live ledger to read.
