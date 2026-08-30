# A cost model with an identification strategy — design note

**Status:** design note. Not a plan, not a decision, nothing gated. Opened from a brainstorming
session on 2026-08-29.
**Opened:** 2026-08-29
**Question:** Findings 1–12 rank three levers on correlational evidence and say so. Can the analysis
be put on a footing where a lever's effect is *estimated* rather than inferred from a slope — and if
so, what has to be built first?

Companion to [`loop-cost-and-convergence.md`](loop-cost-and-convergence.md), which measured the
problem, and to [`baseline-2026-08-25.md`](baseline-2026-08-25.md), whose P1–P9 are already a
pre-registration in everything but name. This note proposes an estimand, a design, and a build
order.

**The numbers in this note are provisional and were produced by a scouting script
(`tree_cost.py`) that has no fixture tests and has not been hand-checked.** The repo has found six
silent detection bugs in this corpus, every one plausible-looking and wrong. Treat what follows as
an existence check that motivates the build order, never as a finding. Nothing here should be cited
until it has been through the two defences that have actually worked: hand-check a sample of
matches, and sanity-check the distribution against what the system can physically do.

---

## First, the thing that is easy to get wrong

**Modelling `cost` is modelling an accounting identity.** Finding 10 established
`cost ≈ turns × ~33k`, with bill/turn holding at CV 15% across eight sessions. Average context is
squeezed between the compaction ceiling above and the starting footprint below, so it barely varies;
turn count has no ceiling. Regress cost on anything and the fit is dominated by its own arithmetic.

The consequence is not cosmetic. It fixes the dependent variable (DV) — the outcome a model is
fit to predict:

> **The outcome is `turns`, a count.** Poisson or negative-binomial with an offset, not OLS on
> tokens. Cost is then read off the identity, not estimated.

And it demotes a whole class of features. Anything that acts on cost *only* through context size —
engine sharding, read discipline, `- Budget:` hygiene — is competing for the ~15% of the bill that
context variation explains. Anything that acts through turn count is competing for the rest. That
ranking is already Finding 10's, and a model that does not reproduce it is wrong.

---

## The measured gap: the current dependent variable is missing about a quarter of the bill

Finding 11 states that subagent work is unpriced — no `isSidechain` records in the corpus, subagent
transcripts living in `<session>/subagents/` that neither script opens. That is recorded as a
caveat. It is larger than a caveat.

Scouting run over every **delegating** session in each consumer's project directory, pricing parent
and subagent transcripts on the same 1× / 1.25× / 0.1× / 5× schedule the README pins:

| project | delegating sessions | subagent share of bill | per-session median | range |
|---|---:|---:|---:|---:|
| `claude-code-loop` | 40 | **37.7%** | 39.1% | 8.7 – 66.9% |
| `us-presidential-vote-analysis` | 72 | **27.0%** | 21.7% | 4.5 – 78.4% |
| `agentfluent` | 143 | **17.7%** | 23.1% | 1.6 – 82.5% |
| `claude-code-sessions` | 48 | **20.3%** | 17.2% | 0.8 – 52.7% |

*Dated snapshot, 2026-08-29, from an untested script. Regenerate before citing; see the warning
above.*

Three things follow, and the third is the one that reaches an existing finding.

1. **Between roughly a sixth and two fifths of the bill is currently priced at zero.** A model fit
   on the parent-only DV is not fitting cost.
2. **It is not a constant that divides out.** The per-session share spans nearly the whole interval
   in every project. A parent-only DV therefore does not merely understate the level — it injects
   variance that is *correlated with delegation behaviour*, which is exactly the thing several
   candidate levers move.
3. **Finding 4 concluded that the cross-repo gradient is mostly engine era, not deliverable type.**
   That conclusion was drawn on the parent-only DV, and the subagent share differs by about 2×
   across these projects. This does not refute Finding 4 — the shares above are not restricted to
   loop runs — but Finding 4 cannot be considered settled until it is recomputed whole-tree.

**The one threat that would have killed the idea is cleared.** If subagent transcripts were a recent
feature, availability would be confounded with era and the whole corpus would be unusable for a
before/after. Checked in `claude-code-loop`: sessions carrying a subagent directory run 2026-07-28
onward and sessions without run 2026-07-26 onward, with the monthly share flat (27.3% in July,
27.4% in August). Availability is not trending. **Selection into *delegating* is a different matter
and is not cleared** — these are sessions that delegated at least once, which is a behaviour, not a
sample.

**Caveat that bounds all of the above:** these counts are over *all* sessions in each project
directory, most of which are ad-hoc work like the session that produced this note, not loop runs.
The table sizes a measurement gap. It does not report a loop-run cost.

---

## The causal structure, and which node each feature is

The reason to reach for causal language here is not sophistication — it is that the notebook already
hit the identification problem head-on and named it: *"a harder issue plausibly causes both more
rounds and more turns. This join cannot separate them and does not try."* That is the whole game.

```
        issue_difficulty  (U — unmeasured)
              │  │  │
              │  │  └────────────────────────────┐
              │  └──────────────────┐            │
              ▼                     ▼            ▼
  policy ─▶ gate_rounds ─▶ turns ─▶ cost     defect_rate
  (config)      ▲            ▲
                │            │
      round_cap ┘   engine_size ─▶ context/turn ─┘
```

- **Treatment** — anything set before the run and under your control: `plan-gate:`, the review
  binding, finder fan-out width, round caps, `REVIEW_TIERS`, lint-as-hook vs lint-as-turn, engine
  version.
- **Mediator** — `gate_rounds`, and `turns` itself. Both sit *on* the causal path from policy to
  cost.
- **Confounder** — `issue_difficulty`, unmeasured, pointing at rounds, turns and defects alike.
- **Outcome** — `turns` (→ cost by identity), and `defect_rate`, which nothing currently measures.

**The single most consequential modelling rule falls straight out of the diagram: do not adjust for
`gate_rounds` when estimating a policy effect.** The policy-relevant quantity is a *total* effect —
what happens to cost under config A versus config B, rounds included, because moving rounds is how
the config works. Conditioning on rounds returns the direct effect only, and worse, rounds is a
collider on `policy → rounds ← difficulty`, so adjusting for it opens a path and can manufacture an
association where none exists. Finding 11's `rounds → cost` slope is a **mechanism** estimate. It is
a legitimate quantity and it is not the decision-relevant one.

This is also the answer to the collinearity worry that prompted the note. For prediction,
collinearity is harmless; for causal estimation, the enemy is not correlated regressors but a
wrongly-chosen adjustment set. **Classify features by node first; select among them second.**

### The estimands, stated so a result can be checked against one

| # | estimand | why it is the one you want |
|---|---|---|
| **E1** | Total effect of a config lever on whole-tree cost per issue | The decision. Directly comparable to the lever table's rows. |
| **E2** | Total effect of the same lever on a quality outcome | Without it E1 is unsafe — see below. |
| **E3** | Proportion of E1 mediated by `gate_rounds` | Tests Finding 2's mechanism claim. Needs a mediation design, not a covariate. |
| **E4** | Cost per pipeline step | Not causal, and the highest-value descriptive gap. Open question 3. |

---

## E1 worked: what a targeted subagent has to be worth

The estimands above are abstract. This is the first one made concrete, and it is the question that
prompted the note's own extension: **if a subagent removes parent turns, when does it save more than
it costs?**

Under the parent-only DV the question cannot even be asked — a subagent is free by construction, so
"delegate everything" is the answer and it is an artifact of the measurement. Whole-tree accounting
makes the trade real. Scouting run over the same four projects, per assistant record:

| | median bill/record | trend with agent length |
|---|---:|---|
| parent | **~26k** | rises, r = **+0.54** |
| subagent | **~15k** | flat, r = +0.21 |

**The flatness is the load-bearing part, and it refutes the obvious hypothesis.** The natural guess
is that subagents look cheap only because they are short — less accumulated context, lower per-turn
rate — in which case the saving would evaporate the moment one is given real work. That holds for
the parent and does not hold for the subagent:

```
subagent length    n     median bill/record
      1-5        282            4,952
      6-15       228           15,365
     16-30       409           15,542
     31-60       373           15,290
    61-120       136           15,452
      121+         3           16,642
```

Past roughly six turns it is flat at ~15k regardless of length. **Subagent context plateaus; parent
context does not.** So delegation scales — there is no per-turn penalty for handing a subagent a
large job, which is the opposite of the intuition.

**The break-even that follows.** A subagent doing `W` turns costs ~15k×`W`; the same work in the
parent costs ~26k×`W`. It pays for itself if it removes more than **~0.6 parent turns per subagent
turn it consumes**. At a 1:1 transfer, delegation wins by ~40%, and the true margin is larger,
because the parent's rate *rises* with context (r = +0.54) — every turn kept out of the parent also
lowers the rate on all subsequent parent turns.

**The obvious counterweight is already measured and it is small.** A subagent's return enters parent
context permanently, which is lever B — and B is marked *REFUTED*: Finding 6 puts `Agent` returns at
0.9–3.7% of what enters the parent, under 1% of a run on the bill model. The return channel is not
where delegation loses.

**The confound that decides whether any of this transfers.** The ~15k rate reflects what subagents
are used for *today* — largely search and review, which are read-heavy and context-light. A subagent
doing implement-shaped work might not stay flat, because it accumulates file state the way the
parent does. **The rate is a property of the workload, not of subagents**, and nothing here
establishes it for a workload the corpus does not contain.

### The first candidate: a docs-only subagent

Proposed 2026-08-29 from field observation in `us-presidential-vote-analysis`, **recollection not
measurement, recorded so it can be tested rather than relied on**: one to two parent turns per
iteration go to fine-tuning documentation that *earlier turns in the same run over-claimed*.

That is worth stating precisely, because it makes the overhead predictable rather than random.
Those turns are not the cost of writing documentation — they are the cost of **correcting
documentation written mid-run by an actor holding the whole run in context**. It is the same
over-claiming pathology `CLAUDE.md` documents at length in this repo's own prose, arriving as a
*cost* item: a claim is asserted while the work is in flight, and a later turn walks it back.

If that reading is right, the fix is structural rather than behavioural. A docs subagent invoked
once at the **end** of step 6, with a clean context and a scope limited to what the diff actually
shows, cannot over-claim from run history it never saw — so the correction turns have nothing to
correct. It is also close to the ideal shape for the economics above: bounded, terminal,
context-light, and a plausible 1:1 turn transfer.

**This is lever F, arrived at from the other direction.** The notebook already proposes a
documentation subagent at the end of step 6, on the grounds that multi-site consistency propagation
is a good subagent brief and a bad inline parent task. The contribution here is a cost model for it,
a second mechanism (correction turns, above), and a falsifier. **F's two constraints carry over
unchanged, and the second one bounds the economics:**

- **Not after code review.** The currency clause means a commit no gate ran on does not inherit that
  gate's verdict, so landing docs after step 8 re-arms code review every run — a cost *increase*.
  End of step 6, before the commit.
- **A subagent that returns a patch the parent must read saves less than it looks.** That is exactly
  where the 1:1 turn transfer assumed above breaks down: ingestion is cheap (lever B), but *applying*
  a returned patch is parent turns, and they come straight off the saving. F's answer — hand back a
  worktree the parent applies from a path — is also what the tree-isolation invariant already
  requires, so the cheap shape and the safe shape agree here.

**Falsifier.** Count the doc-correcting turns in a run — turns whose only edit is to documentation
already written earlier in the same session. If the rate is well under one per iteration, the lever
is too small to bother with regardless of how good the economics look. Measure before building.
---

## The trap that makes this worth doing carefully

**Every lever on the table reduces cost by doing less work.** Fewer rounds, fewer finders, tighter
review, a lower round cap — each is a genuine cost reduction and each is trivially achievable by
degrading the product. Finding 5 already says it: *nothing measures the thing we are trying to fix.*

So a cost model with no quality term is not merely incomplete, it is **actively misleading**: it
will rank "turn the gates off" first, and on its own objective it will be right. The brief is cost
reduction *at or above current implementation accuracy*, which makes this a constrained problem —
minimise cost subject to quality ≥ baseline — and makes the interesting object the **frontier**, not
a coefficient.

That elevates the quality metric from follow-up to prerequisite. Three candidates, none free:

- **post-merge defect rate** — findings on #1 attributable to an already-merged change. Cleanest
  definition, longest lag.
- **fix-up / revert rate** — commits that repair a merged change. Mechanical, available from git
  now, noisy.
- **fix-induced defect rate** — Finding 2's quantity: defects created by the previous round's fix.
  Already partly characterised at 7 instances across 4 ledgers, and it is the one that speaks
  directly to E3.

**Default-deny applies here as it does at the merge gate: a lever whose quality effect is unmeasured
is not "quality-neutral", it is unevaluated, and unevaluated does not ship.**

---

## What identification is actually available, ranked

The unusual and genuinely favourable fact about this problem: **the assignment mechanism is ours.**
Config is set per run, before the outcome, by a human. That converts a hopeless observational
problem into a design problem.

| design | what it buys | what it costs | verdict |
|---|---|---|---|
| **Repeated runs on a reference issue** — one issue, many replicates, one lever varied | Removes `issue_difficulty` *by construction*, and is the only design that yields **within-config variance** | Many full runs — but see below, the usual cost objection does not apply here | **Decisive, and now the primary plan.** Own section below. |
| **Randomised config assignment going forward** | Known propensity; identifies E1 with no unconfoundedness assumption to defend | Discipline only — the run happens anyway | **Start immediately.** Every unrandomised run is an observation that cannot serve E1. |
| **DiD on the staggered engine rollout** | Uses data already on disk | Free | **Do first — it is free and it is already sitting there.** |
| Regression adjustment on observational rows | Nothing, unless difficulty is measured | Free | Descriptive only. Do not report as an effect. |
| IV via a binding round cap | A cap moves rounds without touching difficulty | Weak instrument, thin | Note and park. |

**The DiD deserves its own paragraph because it already exists and nobody has claimed it.** Versions
0.0.1 → 0.2.0 → 0.2.1 rolled out at *different dates across four projects*, and
`claude-code-sessions` was **deliberately held on 0.2.0**. That is a staggered-adoption design with a
late-treated control, and it fell out of ordinary release practice rather than being designed.
Findings 1 and 4 are already running an informal version of it. Formalising it — project and era
fixed effects, whole-tree DV — is the cheapest available increase in rigour.

**One caution before betting on it:** in `claude-code-loop` the corpus spans 2026-07-26 to
2026-08-29, and 0.2.1 landed 2026-08-26, so the post-period is a few days wide. Check the
post-treatment window in `agentfluent` and the vote repo before designing around it; a DiD with
three days of post data is a picture of a transition, not an effect.

---

## The reference-issue experiment

*Proposed 2026-08-29. This is the paired design from the table above taken to its limit, and it is
the strongest identification available to this project.*

**Shape.** Pick one well-scoped issue. Re-run it many times from an identical starting tree, varying
one config lever at a time. Every replicate is the *same* issue, so `issue_difficulty` — the
unmeasured confounder that Finding 11 correctly refuses to work around — is held fixed by
construction rather than adjusted for. Nothing else on the table does that.

**Why it is feasible here, which is the unusual part.** Repeated-run designs are normally ruled out
on cost. They are not ruled out here: the operator is on a Max subscription that rarely reaches its
weekly ceiling, so replicate runs draw on capacity that otherwise expires unused, and the natural
scheduling window is the end of a billing week. **The binding constraint on the best available
design is therefore close to zero**, which inverts the usual trade and is the reason this design
should be preferred over the observational work rather than held as an aspiration.

**Harness.** The Agent SDK, driving runs unattended against a fixed base commit in a throwaway
worktree. Not the interactive loop — a replicate that a human nudges is not a replicate.

### The first experiment is a replication, not a comparison

**Run the same config `k` times before comparing any two configs.** This is the step most likely to
be skipped and the one that decides whether anything after it means something.

Nothing in the current corpus estimates **within-config variance**. Finding 11 has n=8 sessions with
no repeated measures, so run-to-run noise and lever effects are perfectly confounded: there is no
way to say whether a 20% difference between two configs is a lever or a coin flip. A reference issue
supplies that number directly, and it is a prerequisite for every power calculation, every stopping
rule, and every claim of the form "config A is cheaper than config B."

There is a real chance σ is large enough that the modest levers are unmeasurable at any feasible
`k`. **That is a result worth having early**, because it would redirect the whole programme toward
the two or three levers big enough to clear the noise.

### Validity threats specific to this design

- **The tree must be identical across replicates.** Fixed base commit, fresh worktree, ledger reset,
  and the *installed plugin version pinned and recorded* — the README already insists on the last
  one and it matters more here than anywhere else.
- **External validity is the price paid for the clean identification.** One issue is n=1 in the
  issue dimension. An effect measured on the reference issue is an effect *on that issue*;
  generalising needs a second reference issue of a different route and shape, and the honest move is
  to treat cross-issue generalisation as a separate question rather than assume it.
- **Reference-issue decay.** The more the issue is studied, the more the engine and config are
  tuned to it. Refresh it periodically, and never let a lever's justification rest solely on the
  issue it was tuned against.

### The quality outcome, which is what makes the experiment safe

The trap above applies with full force: every arm can win on cost by doing less. Three candidate
measures, and they are complements rather than alternatives:

1. **Review-to-exhaustion as the oracle.** Run the review gate on a finished implementation until it
   stops producing new findings, with the round cap lifted. Expensive, and it yields something the
   loop cannot otherwise get: an approximate ground-truth residual defect count for a given diff.
   Run it on a handful of replicates only.
2. **A fixed, blind evaluator agent.** The workhorse. One evaluator prompt, one model, one effort
   level, held constant across every arm and **not told which config produced the diff**. Blinding
   is trivial to arrange and easy to forget, and without it the evaluator can reward the arm it can
   identify.
3. **Quantified fan-out review output.** Cheapest, and the one with a structural hazard:
   **if the treatment is a review-gate config, then review output is endogenous and cannot be the
   outcome.** Tightening review lowers the finding count by construction, which would score as a
   quality *improvement*. Usable only for arms that leave the review gate untouched.

**The sequencing that makes these work together:** use (1) on a few replicates to establish ground
truth, validate (2) against it, then run (2) at scale. An evaluator never checked against an oracle
is a number, not a measurement.

**Falsifier for the design itself.** If the fixed evaluator's scores on repeated runs of one config
have a spread comparable to the differences between configs, the quality axis cannot support the
comparison, and cost results must be reported as cost-only with the quality question stated as
open — never as "quality held constant."
---

## Build order, and the gate on it

Stages 0–2 are instrumentation. **No model is fit until they land** — not conservatism, just that
every stage below changes the DV or the unit, and a model fit before them answers a different
question than the one asked.

- **Stage 0 — whole-tree cost accounting.** Parent + `<session>/subagents/*.jsonl`, one priced
  figure per session. Fixes the DV. `tree_cost.py` is a sketch of this and needs fixture tests and a
  hand-checked sample before its output is trusted.
- **Stage 1 — a per-turn fact table.** One row per turn, parent and subagent: timestamp, model,
  `effort`, the four token fields, tool calls and names, `attributionSkill`, `attributionPlugin`,
  `gitBranch`, `sessionId`, `isSidechain`. Everything downstream is an aggregation of this. The
  transcript already carries the attribution fields, which is most of what Stage 2 needs.
- **Stage 2 — pipeline-step segmentation and the issue↔session join.** The real feature-engineering
  problem, and it clears a known defect: the session↔issue mapping is many-to-many, so Finding 11's
  per-issue figures are within-session averages. **Grain: the turn is the fact, the issue is the
  analysis unit, and the session is a nuisance dimension to be dissolved by attributing turns to
  issues — not by averaging within sessions.**
- **Stage 3 — descriptive decomposition.** Cost by step, by route, by era, whole-tree. Answers E4
  and open question 3. **Plausibly half the total value of this work, and it arrives before any
  model.**
- **Stage 4 — models, kept boring.** NB-GLM on turns, project fixed effects, era fixed effects. With
  N in the dozens and four clusters, gradient boosting would be fitting noise with extra steps.
- **Stage 5 — design.** Randomise one lever; pre-register the prediction in the P1–P9 style, which
  this repo already does well.

**Feature source rule, and it is the one with teeth: every feature derives from the transcript; the
ledger is a validation target, never a data source.** `gate-rounds` — the independent variable of
Finding 11 — is a self-report, demonstrably 2.5× low in the session anchoring the low end of the
fit. Measurement error in an IV is not a rounding problem: if it were classical it would attenuate
the slope, but a self-report that degrades on long runs is correlated with the outcome, and that
biases in either direction. Recovering rounds from transcript evidence is a Stage 2 deliverable, and
until it exists **no rounds coefficient means anything.**

Port the existing extractors rather than re-deriving them. The heredoc, working-tree-vs-plugin-cache,
spill-file, direction and line-wrap lessons encoded in `engine_cost.py` and `rounds_vs_turns.py` are
the most valuable artifacts in this directory, and each was bought with a wrong published number.

---

## Where the work should live

**A separate repo, consuming sanitized derived tables.** Three reasons, in order of force:

1. This repo is **stdlib-only on Python 3.9–3.13 by hard constraint**, because the guard hook runs
   under bare `python3` in a consumer's environment. The analysis wants pandas, statsmodels,
   numpy, matplotlib. Those do not reconcile, and stdlib-only regression is masochism.
2. Different deliverable, different audience, different lifecycle. `docs/research/` holds artifacts
   *about* the plugin; a cost model is its own product.
3. Transcripts contain everything. `claude-code-sessions` is already a sanitizer and
   `claude-code-data-collective` already has a schema and attestation story — so the sanitization
   problem is solved elsewhere and should not be re-solved here. **Raw transcripts should not leave
   the machine.**

Notebook to start: yes, with one discipline carried over from this directory — **notebook for
exploration, extractors as tested `.py` modules from day one.** The parsers had six silent bugs and
now carry 46 fixture tests; the plots need none. That split is the lesson, and it transfers exactly.

On the extractors: copy initially and accept drift; if they stabilise, move them to the new repo and
leave `docs/research/` a frozen record with a pointer. Do not build sharing infrastructure before
the shape is known.

---

## Falsifiers

Stated per the directory's convention, so each claim above can die cleanly.

- **The DV claim** dies if whole-tree accounting restricted to *loop runs* shows a subagent share
  that is both small and low-variance. The table above is over all delegating sessions; the
  restriction is the test.
- **The identity claim** (`model turns, not cost`) dies if whole-tree bill/turn turns out far more
  variable than the parent-only CV of 15% — plausible, since subagent context profiles differ from
  the parent's, and it would restore context as a first-class term.
- **The DiD** dies if the post-0.2.1 window is too thin in every project, or if era coincides with
  an unmodelled change in issue mix.
- **The mediation story (E3)** dies if transcript-recovered rounds correlate poorly with journaled
  rounds *and* the recovered version shows no rounds→turns relationship.
- **The whole enterprise** is not worth it if Stage 3's descriptive decomposition shows cost
  concentrated in a step no config lever reaches — in which case the answer is engineering, not
  estimation, and the modelling should stop there.
- **The delegation economics** die if the ~15k subagent rate is a property of today's read-heavy
  subagent mix rather than of subagents. An implement- or docs-shaped subagent that accumulates file
  state could land near the parent's rate, at which point the break-even moves and the lever with
  it.
- **The docs-subagent case** dies if doc-correcting turns are rare — well under one per iteration —
  in which case the economics are irrelevant because there is nothing to recover.
- **The reference-issue experiment** dies if within-config variance turns out comparable to the
  between-config differences being chased. That is not a reason to skip it; it is the first thing it
  measures, and learning it early redirects the programme toward the few levers large enough to
  clear the noise.

---

## Open questions

1. **What is the loop-run-only subagent share?** Everything in the gap section is over all
   delegating sessions. This is Stage 0's first real output and it decides how much the DV fix
   matters.
2. **Can `gate_rounds` be recovered from transcripts at all?** If not, Finding 11's IV stays a
   self-report permanently and E3 is unreachable.
3. **Which quality metric is cheap enough to collect every run?** Fix-up rate is the only candidate
   available without new instrumentation, and it is the noisiest.
4. **Does issue difficulty admit a pre-treatment proxy** — spec length, AC count, files touched at
   plan time? A weak one would still support blocking, which is worth more than adjustment.
5. **Is per-issue randomisation acceptable in a repo whose loop is doing real work?** Assigning a
   worse config to a real issue has a real cost, and that is a judgement call, not a statistical
   one. *The reference-issue design largely dissolves this* — a throwaway worktree on a
   fixed base commit is not real work — which is a further reason to prefer it.
6. **What is `σ` for a loop run?** Unknown, unestimated, and a prerequisite for every comparison in
   this note. The reference issue's first output.
7. **Which issue should be the reference?** It needs to be well-scoped, representative of the `code`
   route, and cheap enough to run many times — and those pull against each other.
