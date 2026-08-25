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

## Candidate levers

Ranked by (expected saving × confidence), with the reasoning that places them. None is a decision.

### A. Record parent context at step 12 — *prerequisite*
Even a coarse self-report fills the reserved `tokens` slot and makes symptom 2 measurable, the
Finding-1 hypothesis testable, and every lever below evaluable. Cheapest thing on the page and it
gates the value of the rest.

### B. Constrain what finders return — *high saving, high confidence, small edit*
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
