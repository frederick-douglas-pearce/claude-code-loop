# Context architecture — the case for making the parent a controller

**Status:** design note. Not a plan, not a decision, nothing gated. Core drafted and measured, then architect-reviewed, 2026-08-25.
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
   It is the origin of the fix-induced defect class (Finding 2, seven instances across four
   ledgers).

   **Correction, 2026-08-25 (architect review).** This bullet originally read "it drives the 71%
   share", which **conflates doing work with reading files**. Finding 6 says the parent's 71% is
   dominated by *file reads*, and that `Agent` returns are **0.9–3.7%** of what enters the parent.
   Delegation removes the *implementer's reading* from parent context, which is real — but
   controller-ification is **not established as a context lever**. It is well-evidenced as a
   **convergence and quality** lever, on Finding 2, and that is how it should be argued.
2. **The operating procedure is one monolith, loaded in full, at every invocation.** Including for
   the **39 of 345 journal entries that stop at the plan gate** having executed perhaps a quarter of
   it.

**Correction, 2026-08-25 (architect review): this paragraph was wrong, and self-contradictory.** It
argued controller-first on the grounds that "a controller does not need step 6's staging rules, the
Tool surface's isolation mechanics" — but drafting the core moved Tool surface *into* core precisely
**because delegation makes staging more central**, since every phase then delegates to a writing
agent. Both cannot be true.

Under a controller model the parent's staging burden **rises**: it still owns commits and merge
(`PERMISSION_POSTURE`), and must now run collect-then-remove against a writing subagent's isolated
copy on *every* issue rather than only on delegated-fix issues — so the gitlink hazard and the
"skipping collect destroys work" duty move from rare to main-path. The better safety argument is the
opposite one: that machinery already exists and is hardened, so this exercises tested machinery more
heavily rather than requiring new invariants.

**Revised sequencing: shard first, then controller-ify** — see below.

---

## Target structure

Seven units. Sizes are measured from today's sections, not estimated.

| unit | ~tokens | share | contains |
|---|---:|---:|---|
| **core** (always loaded) | **13,360** | 30.4% | preamble, pipeline overview, step 0 load/resume, 1 select, 2 route, Escalation rubric, Guardrails, **Tool surface**, Routing table, **Gates/convergence/resting**, + a hand-written phase index |
| `planning` | 3,900 | 8.9% | steps 3 plan · 4 architect · 5 human gate |
| `implementing` | 3,570 | 8.1% | steps 6 implement · 7 commit/PR |
| `reviewing` | 1,400 | 3.2% | steps 8 code review · 9 security |
| `accepting` | 8,100 | 18.5% | step 10 · the AC-verifier procedure |
| `landing` | 1,500 | 3.3% | steps 11 merge · 12 journal |
| `reference` | 12,800 | 29.1% | ledger format, `queue.md`/`progress.md`/plan templates, Router, Initialization, Resume |

**Always-loaded becomes `core` + `SKILL.md` ≈ 15,180 tokens — 67% below today's ~46,200.**
*(Drafted and measured, not budgeted — `docs/research/draft-core.md`. The first estimate said 10,400
and 73%; assembling it moved Tool surface into core and added a phase index, costing ~2,900 tokens.)*

Two things that structure buys beyond the headline:

- **A plan-gate stop loads `core` + `planning` ≈ 17,300 tokens** instead of 46,200. That is 11.3% of
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

## Sequencing — revised after architect review

The original order (controller first) was argued from a claim that turned out to be backwards; see
the correction above. Revised:

0. **Ship the two near-free wins independently, first.** The `SKILL.md` read-discipline sentence and
   the F105 dedup (PR #124) depend on none of this and de-risk the measurement baseline.
1. **Shard the big, genuinely-late buckets only.** `accepting` (~8.1k, needed at step 10, clean
   fail-safe: cannot run ⇒ cannot merge ⇒ human) and a `reference` **appendix** (Initialization,
   templates, the `progress.md` worked example, ~6–7k, needed at init/journal). That lands
   always-loaded near **~30k — a ~35% cut at a fraction of the risk** of the full seven-unit split.
2. **Measure with `context_profile.py`.** Before/after on a real session, as a hard gate on landing.
3. **Only then defer the small early units**, and only if the parent still overshoots 200k *and* the
   fail-safe halves have proven sound in practice. Deferring a 1.4k unit trades 1.4k of
   always-loaded for a read round-trip that **78.6% re-read rates** say may recur — a worse trade,
   and the most fail-safe surface per token saved.
4. **Controller-ification as a separate change**, sold on convergence (Finding 2), not on context.

---

## Architect review outcome (2026-08-25)

**Verdict: proceed-with-changes on the sharding; reconsider the sequencing.** The central finding
reframes what makes this safe:

> **The fail-safe halves are not what makes this safe.** The retained **Gates table**, the
> **Gate-outcome invariant** (no verdict ⇒ not passed) and the **load protocol** (an unconfirmed
> load is not loaded ⇒ escalate) are. A gate-by-gate walk found **no gate that silently fails to run
> and produces a false pass**; residual risk under a silent partial load is a *weaker improvised
> procedure*, not a *skipped gate*.

Three blockers, all structural rather than directional:

- **B1 — the Gate-outcome invariant's due-ness source points at deferred content.** It says due-ness
  "is decided where it always was (the gate's own step and the Routing table)", and steps 3–12 are
  now deferred. The enforcement mechanism resolves its central property against text `core` does not
  contain. `core` must become the authoritative, self-contained source of every gate's due-ness, and
  every `(step N)` cross-reference in `core` that resolves a *safety* decision must resolve inside
  `core`.
- **B2 — `reference` is mis-drawn, and `core` is not self-sufficient without it.** Step 0.2/0.3
  classifies rows against the **closed status vocabulary**, and step 2 runs the **Router** — both
  assigned to `reference`. So `core` depends on it on every resume and every route. The status
  vocabulary is *the language the fail-safe invariants are written in*. **Cross-cutting invariant
  vocabulary does not defer**: pull status vocabulary, `queue.md` header semantics, Router and
  Resume into `core`; defer only Initialization, templates and the worked example.
- **B3 — the phase index is a new unguarded multi-site restatement**, which is precisely the shape
  this project keeps getting burned by. It needs a mechanical **identity** guard shipped with it —
  every gate in the Gates table has exactly one phase-index entry; every unit and `reference/*.md`
  the index names resolves to a file that exists. **Not** a truth check: whether a fail-safe half
  *agrees with* its step is the enumerable-assertion trap and stays review-owned.

**And an opportunity worth designing for rather than leaving to chance.** If the discipline becomes
*"`core` states each invariant once, in the Gates table plus the phase index; units state only how to
run it and never re-assert the posture"*, the phase index can become the canonical "what is owed"
home that **#35** has been looking for — **reducing** restatement sites rather than adding another.
Left implicit, B3's drift risk is realized instead.

**Audited 2026-08-25** — `core-self-sufficiency-audit.md` walks all 27 safety-resolving references
in the drafted core: **6 genuine failures, all on B1/B2, none elsewhere.** The Tool surface, currency
clause, convergence classifier, merge posture and every gate's due-ness in the Gate table already
resolve in core. **And the increment is a different core than the one audited:** deferring only
`accepting` plus a reference appendix keeps the status vocabulary, header semantics, Router and
Resume in core *by construction*, so **B2's moves are unnecessary for the increment — only B1's
reword and the B3 guard are load-bearing on day one.** `accepting` strands no decision: due-ness in
the Gate table, fail-safe *cannot run ⇒ cannot merge ⇒ human* in the phase index.

Two smaller structural items: `core` must carry a compact **0–12 pipeline table of contents** (steps
4, 5, 7, 9 and 12 are currently never enumerated in `core`), and `implementing` **splits across
actors** under a controller model — step 6 becomes the implementer's brief, step 7 stays with the
parent.

## Open questions

1. ~~**Does `core` at 10.4k hold the fail-safe half of six deferred units?**~~ **Answered by
   drafting** (`draft-core.md`): it holds at **13,360 tokens**, not 20k, and always-loaded lands at
   **~15,180 / 67% below today**. Two corrections the draft forced, both of which a budget would
   have missed: **Tool surface must be core, not `implementing`** — its tree-isolation and
   staging limits bind at steps 4, 8 and 10, and under a controller model they become *more*
   central, since every phase delegates to a writing agent; and the phase index costs ~970 tokens,
   which is cheap for what it does. **What remains unvalidated is whether the fail-safe halves are
   correct**, not whether they fit.
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
