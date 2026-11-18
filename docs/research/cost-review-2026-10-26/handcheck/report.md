# Hand-check: session 3f30a898 (us-presidential-vote-analysis), engine 0.3.1

## Diagnosis

**What it was.** One session, **two `/dev-loop` invocations with no `/clear` between**: #386 (turns 1–246, PR #396, new /v1 party fields + snapshot schema bump) and #389 (turns 247–423, PR #398, party column in four dashboard tables), plus three user side-requests (dotenv question, #397 filed, a comment edit). Neither resumed a row (turn 10 "Resume/orphan scan clean… Selected #386"; turn 249 "No interrupted rows, no open PRs"). The refusal is right: two `- Budget:` lines, one compaction, side work. Split at the stratum's weights (which reproduce $87.90 exactly): inv1 ≈ $51, inv2 ≈ $37. Active API time 4.5h of a 29h span; 24.6h was human waiting at gates.

**Where the dollars went.** Cache reads $43.8, cache writes $36.9, output $7.2.
- Reads: 423 turns × 529k average context. inv2 started at 723k because inv1's context was never cleared, ran 99 turns at 723k→960k, then auto-compacted (turn 346).
- Writes: **75% ($27.8) is six re-warms of the whole context after human waits longer than the 1h TTL** — turn 340 (9h43 at the round-2 cap stop, 947k ctx, $7.6), 212, 203, 152, 46, 406. A gate stop at 950k costs $7.6 just to resume.

**Where the context went.** Engine core (201k chars ≈ 55k tok) read in full at turns 1–3 and again in full after compaction (turns 348–350, 241k chars with accepting.md) — SKILL.md's default-deny load rule working as designed. Project reads at 6–16, 53–65 (ba spec, glossary, tests). Tool results 1.42M chars (Read 766k, Bash 621k). The orchestrator's own output, 360k tokens, is retained: thinking plus 123 heredoc patches (336k chars of command text) and 33 pytest runs. Agent returns were cheap (1.3k-char acks).

**Turns per phase (Σctx share).** inv1: plan 41 (4%), implement 88 (17%), review 66 (17%), acceptance 24 (7%), merge/journal 20 (6%). inv2: plan 14 (5%), implement 46 (17%), review 33 (14%), security 5, compaction+re-read 6, acceptance 53 (6%), merge 13 (2%).

**Rounds.** The 2-round cap held. inv1: r1 20 findings → r2 "fell back to full" (fix touched snapshot.py, §4) 4 findings → cap → human → r3 human-directed 1 finding → ba fix under waiver. inv2: r1 27 → r2 fell back to full (dashboard/, §4) 2 findings → cap → human waived. Every round-2/3 finding was fix-induced prose (docstring, PR body, glossary wording): the §4 fallback bought a full round and a human stop for 2–4 small findings, twice.

**Compactions.** One (auto, 960k). Re-read after: accepting.md in full, loop-engine.md in full (7 chunks), progress.md tail.

**Cheap fixes.** (1) **`/clear` before re-invoking.** inv2's 99 pre-compaction turns would run at ~210k instead of ~850k (−$12.7 reads), no compaction or engine re-read (−$1), and the 9h43 re-warm at ~300k not 947k (−$5): ≈ −$19, 21%. (2) **Count the gate-wait re-warm.** It is 32% of this bill and invisible to a per-turn instrument; the lever is smaller context at the stop, which (1) mostly gives. Sharding the 55k-token core (carried all 423 turns, ≈ $5) and delegating step 6 (134 parent turns, 34% of Σctx) are the structural levers, not cheap ones.

## (a) 25 largest tool results (all `Read`, chars)
Engine, turn 3: loop-engine.md in 9 chunks of 16–28k (211k total). Engine after compaction: turn 348 accepting.md 40.0k; turns 349–350 loop-engine.md 7 chunks of 28–32k (211k). Project: turn 1 38.1k, turn 15 35.7k + 20.2k, turn 64 28.8k, turn 63 22.8k, turn 53 21.0k, turn 6 18.4k; Bash: turn 77 19.5k (pytest), turn 353 17.0k (`sed` progress.md 3562–3640). Totals by tool: Read 766k (n=35), Bash 621k (n=335), Agent 28k (n=26).

## (b) Context drops >30%
Turn 346 (2026-10-20T01:20Z): 959,671 → 80,653 (−92%), auto-compaction, preTokens 960,335, summary 12.1k chars.

## (c) Agent launches (turn, ctx, type, description → return)
Every return is a 1,093-char background ack; results arrived as task-notifications (~1.3k) with output files. 13 ctx180k Explore map party flow · 30 270k ba spec #386 · 35 286k architect #386 · 139 541k general guard-efficacy r1 + ba wording r1 · 145 561k architect scope ruling · 179 604k r2 checker · 184 616k ba glossary fix · 191 623k r3 checker · 196 631k ba clause · 200 644k security finder · 207 667k Class A verifier + Class B mutation · 218 688k Class B recheck · 251 728k Explore dashboard · 255 750k ba spec #389 + architect #389 · 310 878k guard-efficacy + ba wording · 315 897k scope ruling · 320 912k ba texts · 336 938k r2 checker · 343 957k security finder · 357 194k Class A + Class B · 386 254k Class B recheck. Subagent tree: 28 agents, 663 turns, Σctx 77M; the two Explore maps alone 21M.

## Ledger lines written
- turn 245 `- Budget: subagent-runs=21 … gate-rounds=architect=1,code-review=3(…),ac-verify=2 · mutation-survivors=2 … wall-clock=≈12h … tokens=deferred`
- turn 416 `- Budget: subagent-runs=13 … gate-rounds=architect=1,code-review=2(…),ac-verify=2 · mutation-survivors=9 … wall-clock=≈26h … tokens=deferred`
- turns 145/181/193 and 315/338: the `- Code-review:` round lines quoted in ledger_out.txt.
