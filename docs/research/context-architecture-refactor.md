# Context architecture — the case for making the parent a controller

**Status:** design note. Not a plan, not a decision, nothing gated.
**Opened:** 2026-08-25
**Question:** the engine occupies ~46k tokens of every parent context for the whole session. Is that
a necessary cost of the workflow, or an artifact of how the workflow is packaged?

Companion to [`loop-cost-and-convergence.md`](loop-cost-and-convergence.md), which measured the
problem. This one proposes a shape. Prompted by a comparison with
[`obra/superpowers`](https://github.com/obra/superpowers), whose `subagent-driven-development` skill
solves a near-identical problem with a very different footprint.

---

## First, the thing that is easy to get wrong

**Prompt caching is a billing mechanism, not a context mechanism.** From a real session:

```
turn   input   cache_read   cache_create   = context
   0       2       26,254         32,407      58,663
   3       2       66,298         15,067      81,367   ← engine loading
   6       2      110,615         15,098     125,715   ← engine loaded
 135       2      364,651          1,093     365,746
```

`input_tokens` is 2 on every turn; everything else is cache. **And context never shrinks.** Caching
means the engine is re-sent at ~0.1× on each turn — it does **not** mean it stops occupying the
window. The 44k sits there for the whole session, every turn, against a 200k target.

Cache-TTL expiry is likewise a *cost* event, not a context event: the prefix is re-**written** at
1.25–2× rather than re-**read** at 0.1×. Nothing is freed.

**Consequence:** the F105 hotfix removes ~14k of *duplication* from both cost and window. The ~44k
floor is untouched, and no prompting change reaches it.

---

## The measured gap

| | `dev-loop` | `superpowers` |
|---|---:|---:|
| always-loaded bootstrap | `SKILL.md` + `loop-engine.md` = **~46,200 tok** | `using-superpowers` = **~777 tok** |
| entire skill library | (same file) | 14 skills = **~34,600 tok** |
| largest single unit | `loop-engine.md`, ~44,400 tok | `subagent-driven-development`, ~8,100 tok |

**Our always-loaded footprint is 33% larger than their complete skill library, and ~59× their
bootstrap.** Their largest single skill is under a fifth of our engine.

---

## What they do that we do not

Three mechanisms, quoted from `subagent-driven-development`:

1. **The controller never does the work.**
   > *"Controller must never fix code directly — fixes skip review and pollute controller context.
   > Resume the implementer or dispatch a fresh one instead."*

   Our step 6 is titled *"Implement (you, the parent thread)"*, and step 8 has the parent apply
   review fixes. **Our own measurements are the evidence for their rule**: the parent is **71% of
   all tokens processed**, and fix-induced defects are the most consistent signal in the corpus —
   seven documented instances across four ledgers (`loop-cost-and-convergence.md`, Finding 2).

2. **No context inheritance; hand off by file path.**
   > *"Everything you paste into a dispatch prompt stays resident in your context for the rest of
   > the session. Hand over work via file paths instead."*

   Each subagent gets a task brief path, a report file path, prior interfaces, and constraints —
   never session history, never the full plan.

3. **Graduated fix rounds that reuse context.**
   > *"Rounds 1–3 resume the same implementer (context intact). Round 4+ escalates to a more capable
   > model on a fresh implementer with the report file as persistent memory. After round 5, the
   > controller adjudicates."*

**Mechanism 3 is the single best thing available to steal**, and it is nearly free. Resuming the
implementer to fix is *cheaper* (it already holds the context, so nothing is re-read) **and safer**
(the parent never becomes the author). Our Fresh-re-check invariant requires the **re-checker** to be
fresh — it never required the **fixer** to be the parent. We simply built it that way.

## What we do that they do not — stated so this is not read as a rout

Convergent design is validation, not refutation. They independently arrived at a ledger that is *"the
single source of truth after compaction"*, immutable per-task briefs, accumulating report files, git
commits as state, worktree isolation, and fix-round caps with escalation. **That is our
architecture.**

On gate rigor we are ahead: they run spec-compliance plus code-quality review. There is no security
gate, no AC-verifier, no mutation pass, no currency clause, no gate-outcome invariant, no
default-deny merge posture. **The workflow is the asset. The packaging is the defect.**

---

## The two defects

1. **The parent is a worker as well as an orchestrator.** It implements, and it applies review fixes.
   This is the larger defect: it drives the 71% share, it is the origin of the fix-induced defect
   class, and it forces the engine to carry implementation detail the parent would not otherwise
   need.
2. **The operating procedure is one monolith, loaded in full, at every invocation.** Including for
   the **39 of 345 journal entries that stop at the plan gate** having executed perhaps a quarter of
   it.

**These interact, and the direction matters:** fixing (1) shrinks (2), because a controller does not
need step 6's staging rules, the Tool surface's isolation mechanics, or most of step 7. Fixing (2)
first means sharding an engine that still describes work the parent should not be doing.

---

## Target structure

Seven units. Sizes are measured from today's sections, not estimated.

| unit | ~tokens | share | contains |
|---|---:|---:|---|
| **core** (always loaded) | **10,400** | 23.7% | preamble, the pipeline overview, step 0 load/resume, 1 select, 2 route, Escalation rubric, Guardrails, Routing table, **Gates/convergence/resting states** |
| `planning` | 3,900 | 8.9% | steps 3 plan · 4 architect · 5 human gate |
| `implementing` | 5,900 | 13.3% | steps 6 implement · 7 commit/PR · Tool surface |
| `reviewing` | 1,400 | 3.2% | steps 8 code review · 9 security |
| `accepting` | 8,100 | 18.5% | step 10 · the AC-verifier procedure |
| `landing` | 1,500 | 3.3% | steps 11 merge · 12 journal |
| `reference` | 12,800 | 29.1% | ledger format, `queue.md`/`progress.md`/plan templates, Router, Initialization, Resume |

**Always-loaded becomes `core` + `SKILL.md` ≈ 12,250 tokens — 73% below today's ~46,200.**

Two things that structure buys beyond the headline:

- **A plan-gate stop loads `core` + `planning` ≈ 14,300 tokens** instead of 46,200. That is 11.3% of
  journal entries (a floor — 56% of headers do not classify).
- **`implementing` (13.3%) stops being parent context at all** once implementation is delegated. It
  becomes the implementer subagent's brief. Same for much of `accepting`.

`reference` being the largest bucket at 29.1% is the quiet result here: nearly a third of the engine
is format templates and procedures needed at one step or one lifecycle event.

---

## The constraint that decides whether this works

`SKILL.md`'s entire design assumes a **partial load over-escalates**. Sharding creates partial loads
on purpose. So:

**The fail-safe half of every deferred unit must stay in `core`.** Core says *"the acceptance gate is
due on every issue with acceptance criteria, and either class blocks"*; `accepting` says how to run
it. Core keeps the whole Gates table for exactly this reason — it is the index of what is owed, and
it must never be deferred.

**And loading must be explicit, not automatic.** Superpowers' skills *"trigger automatically."* We
cannot rely on that: our posture requires that a gate never *silently* fails to load, which is
precisely the hazard [F105](https://github.com/frederick-douglas-pearce/claude-code-loop/issues/1#issuecomment-5408084091)
documented. Each phase unit is named at its point of use with a read-this-now instruction, and the
same completeness rule F105 established applies to each.

**Get this wrong and the refactor buys 42% of the tokens by recreating the fragment hazard we just
closed.** That is the whole risk, stated once, plainly.

---

## Sequencing

1. **Make the parent a controller.** Delegate implementation; delegate fixes by *resuming the
   implementer*, not by the parent editing. Keep the Fresh-re-check invariant exactly as it is — it
   already says the right thing, and this change makes it cheaper to honor rather than harder.
2. **Then shard.** With implementation delegated, `implementing` and much of `accepting` leave the
   parent's context regardless of file layout, so the sharding is smaller and better understood.
3. **Measure both.** `context_profile.py` makes each step falsifiable on a real session. No stage
   lands without a before/after pair.

---

## Open questions

1. **Does `core` at 10.4k actually hold the fail-safe half of six deferred units,** or does carrying
   every gate's due-ness push it back toward 20k? This is the number that decides the whole design
   and it has not been drafted, only budgeted.
2. **Can a phase unit be re-read after compaction** without re-reading `core`? [F106](https://github.com/frederick-douglas-pearce/claude-code-loop/issues/1#issuecomment-5408090939)
   says the engine can be evicted mid-iteration; sharding changes what recovery costs, possibly for
   the better — smaller units are cheaper to reload.
3. **Does delegating implementation break the tree-isolation invariant**, or simplify it? Today the
   parent is the only mutator by design (`PERMISSION_POSTURE`). A controller model inverts that
   premise and every site restating it (#25's list) is affected.
4. **What happens to `/init-loop`?** The skeleton binds `CAPS` names the engine reads. Sharding does
   not change the vocabulary, but it changes which file names each one — and skeleton copies are
   stranded in consumer repos that no later release reaches.
5. **Is a `docs`-route iteration worth its own reduced path** once phases are separable? It already
   skips architect, security and mutation.
