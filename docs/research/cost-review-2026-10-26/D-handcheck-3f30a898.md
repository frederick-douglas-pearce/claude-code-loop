# Appendix D — hand-check of session `3f30a898` (vote, engine 0.3.1)

The most expensive session in the corpus ($128.52 whole-tree, $87.90 parent, 423 parent turns, peak context 959,671). `engine_cost.py` refuses it as "unattributable engine read"; the refusal is correct for a different reason (below). Parsed by script from the transcript on 2026-10-26; the scripts and their outputs (`timeline.py`, `phases.py`, `ledger.py`, `subagents.py`, `cache_writes_out.txt`, …) were left in the session scratchpad and are not committed. Nothing in the repo was edited.

## What it was

One session, **two `/dev-loop` invocations with no `/clear` between them**: #386 (turns 1–246, PR #396) and #389 (turns 247–423, PR #398), plus three user side-requests. Neither invocation resumed a row. Split at the stratum's pricing weights (which reproduce $87.90 to the cent): invocation 1 ≈ $51, invocation 2 ≈ $37. **Active API time 4.5h of a 29h span; 24.6h was the human waiting at gates.**

## Where the dollars went

Cache reads $43.8, cache writes $36.9, output $7.2.

- **Reads:** 423 turns × 529k average context. Invocation 2 started at **723k** because invocation 1's context was never cleared, ran 99 turns at 723k→960k, then auto-compacted (turn 346).
- **Writes: 75% ($27.8) is six re-warms of the whole context after human waits longer than the 1-hour cache TTL** — turn 340 (9h43 at the round-2 cap stop, 947k context, $7.6), and turns 212, 203, 152, 46, 406. A gate stop at 950k costs $7.6 just to resume. No per-turn instrument sees this; it is 32% of the parent bill.

## Where the context went

Engine core (201k chars ≈ 55k tokens) read in full at turns 1–3 and **again in full after compaction** (turns 348–350, 241k chars including `accepting.md`), which is `SKILL.md`'s default-deny load rule working as designed. Project reads at turns 6–16 and 53–65. Tool results 1.42M chars (Read 766k, Bash 621k). The orchestrator's own output, 360k tokens, is retained: thinking plus **123 heredoc whole-file patches (336k chars of command text)** and 33 pytest runs. Agent returns were cheap (1.3k-char acks).

## Turns per phase (share of Σ context)

| phase | invocation 1 | invocation 2 |
|---|---|---|
| plan | 41 turns (4%) | 14 (5%) |
| implement | 88 (17%) | 46 (17%) |
| review | 66 (17%) | 33 (14%) |
| security | — | 5 |
| compaction + re-read | — | 6 |
| acceptance | 24 (7%) | 53 (6%) |
| merge / journal | 20 (6%) | 13 (2%) |

## Rounds

The 2-round cap held. Invocation 1: round 1 20 findings → round 2 "fell back to full" (the fix touched `snapshot.py`, a §4 sensitive path) 4 findings → cap → human → round 3 human-directed, 1 finding → `ba` fix under waiver. Invocation 2: round 1 27 → round 2 fell back to full (fix touched `dashboard/`, §4) 2 findings → cap → human waived. **Every round-2/3 finding was fix-induced prose** (docstring, PR body, glossary wording). The §4 fallback bought a full round and a human stop for 2–4 small findings, twice.

## Compactions

One, automatic, at 960k: 959,671 → 80,653 (−92%), summary 12.1k chars. Re-read afterward: `accepting.md` in full, `loop-engine.md` in full (7 chunks), the `progress.md` tail.

## Agent launches

28 agents (26 plus two `/code-review` forks), 663 subagent turns, Σ context 77M. **The two built-in `Explore` map-the-codebase agents alone were 21M** (68 and 56 turns), on the main model. Launch contexts ran from 180k (turn 13) to 957k (turn 343).

## Ledger lines written

- turn 245: `- Budget: subagent-runs=21 · gate-rounds=architect=1,code-review=3(code-review,guard-efficacy,wording-ba),ac-verify=2 · ac-findings=0 · mutation-survivors=2 · post-gate-survivors=0 · justification=… round 3 owner-authorized … · wall-clock=≈12h · tokens=deferred`
- turn 416: `- Budget: subagent-runs=13 · gate-rounds=architect=1,code-review=2,ac-verify=2 · ac-findings=0 · mutation-survivors=9 (8 real + 1 equivalent; all pinned) · post-gate-survivors=0 · wall-clock=≈26h · tokens=deferred`
- `- Code-review:` turn 145 "round 1 (main...e7c4809) — 20 findings (19 BLOCKING), claims=12"; turn 181 "round 2 (main...6e17e0e) — fell back to full (a fix touched src/usvote/snapshot.py, a §4 sensitive path), 4 findings, claims=4"; turn 193 "round 3 (6e17e0e..3c4fcfc) — 1 finding, claims=1"; turn 315 "round 1 (main...f3c7d13) — 27 findings, claims=11"; turn 338 "round 2 (main...aa80652) — fell back to full (fix touched dashboard/, §4), 2 findings, claims=1".

## Cheap fixes

1. **`/clear` before re-invoking.** Invocation 2's 99 pre-compaction turns would run at ~210k instead of ~850k (−$12.7 reads), no compaction or engine re-read (−$1), and the 9h43 re-warm at ~300k not 947k (−$5): **≈ −$19, 21% of the session**, for a sentence in the stop message.
2. **Count the gate-wait re-warm.** It is 32% of this bill and invisible to every per-turn instrument (and the research README says no long-context tier is modeled, so the real cost may be higher). The lever is smaller context at the stop, which (1) mostly gives, and which the thin-controller design (R2) gives structurally.
3. **The §4 fallback plus fix-induced prose** is R1's case exactly: a fresh fix agent under the deletion rule would have left round 2 with nothing to find.

Sharding the 55k-token core (carried 423 turns, ≈ $5) and delegating step 6 (134 parent turns, 34% of Σ context) are structural levers, not cheap ones.

## Correction (2026-10-27, #287)

**Seven turns, six of them whole-context re-warms.** The $27.8 above is right as the re-warm
term's total, not as the six's sum, and `tree_cost.py --sessions` now reproduces it as that term: seven parent turns write cache after an idle gap longer than the
1-hour TTL — 46, 152, 203, 212, 340, **346** and 406 — summing to $27.80. The list above omits 346
($0.36, 44,942 tokens), the first turn after the auto-compaction: it is the post-compaction
rebuild (35,709 tokens read from cache), not a whole-context re-warm, and the term counts it
because the term is defined by the gap, not by the cause. The six whole-context re-warms sum to
$27.44.
