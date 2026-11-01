# Scoping proposal — v0.5.0, model selection, backlog order (pm, 2026-10-31)

Status: **decided and filed 2026-11-01.** Fred's answers: (1) v1.0.0 is a stability and
marketability commitment; (2) MT-1 ships in its own v0.6.0; (3) the skeleton gets a placeholder
row, with the role keys listed in the README; (4) phase 3 runs a **Kimi** profile (Moonshot
endpoint, LiteLLM, or Hugging Face) on a **$10–20** budget; (5) pr-brief (#229) goes to v1.0.0.
Filed: epic #308; MT1 #309 (v0.6.0); MT2 #310; MT3 = #281 rewritten; MT4 #311 (v1.0.0).
Milestones v0.6.0 and v1.0.0 created; #229 and #112 moved to v1.0.0; #306 moved to
`deferred-corpus`. Cross-reference comments posted on #288, #38, #284, #298, and #271.
Closes and merges in §4 (2026-11-01): #138 closed as superseded. #211 **kept open**, against the proposal: the cost review (§4) says to promote it, and its unique children #208 and #210 are not in #271. #128 + v0.3.1 still need the sharding verdict written up first.
Load-bearing claims checked by the coordinator against GitHub on 2026-10-31: v0.5.0 milestone
(created 2026-10-31, theme "the rationale cuts": #276, #290, #109); #276 body line 21 ("a separate
release makes any regression traceable"); #288 body ("Benchmark control arm: the release that
contains the deletions"; "Don't land #281 between the two arms"); #133 closed 2026-10-27 while #128
is still open in v0.3.1; 65 open issues unmilestoned.

## 1. v0.5.0 — go, unchanged

Order: #276 PR 1 → #276 PR 2(/3) → #290 items 1–3 → #109 (after #276 so its step-1 edit cannot
break a manifest anchor) — **cut line** — #290 item 4 (`SKILL.md` read protocol; slips to v0.6.0
if it hits the round cap). Nothing added: model-selection phase 1 stays out (new failure mode —
e.g. passing `inherit` literally to the Agent tool — in the release #276 wants attributable).

## 2. Model selection — milestones (v1.0.0-as-feature-milestone rejected)

- **v0.6.0:** MT-1 (phase 1, behavior-neutral vocabulary).
- **Unmilestoned under the epic:** MT-2 (instruments), MT-3 (measured tiering, gated like #288).
- **v1.0.0 = stability + marketability commitment:** vocabulary frozen, R1 measured, R2 decided,
  measured $/issue headline, MT-4 (bring your own models, a profile actually run), onboarding
  (#112), maybe pr-brief graduation (#229).
- **Phase 4 (routing Mod):** no issue; a re-check log row.

Coordinator note: MT-1 lands between R1's arms (v0.5.0 control, R1 treatment). It is
behavior-neutral by intent only, so either land it before the control arm is frozen, or treat
v0.6.0 as the control. Decide at #288's plan gate.

### Epic `epic:model-tiers` — "Per-role model tiers and bring-your-own-models" (cross-link #271)

**MT-1 — `MODEL_TIERS` vocabulary, behavior-neutral** (v0.6.0; supersedes #281 scope bullets 1–3).
Canonical core passage (grammar, exact-key resolution, default-deny clause §7.1, journal rule);
one pointer sentence per §7.2 spawn site; `models=` Budget slot; skeleton + inference-map rows
(§7.3); key-identity test (§7.4); README trust-model + "Per-role model tiers" (both copies); D018.
- AC1 plan records the two pre-phase-1 §11 re-checks (`CLAUDE_CODE_SUBAGENT_EFFORT` in docs;
  `/tasks` reading after an `effort` spawn).
- AC2 no `ANTHROPIC_*`/`CLAUDE_CODE_*` token in core/units/`SKILL.md`; CapsVocabularyTests + key
  test green.
- AC3 smoke run in a scratch consumer: zero `Agent` calls carrying `model`/`effort`; `models=`
  reads `inherit` for every spawned role.
- AC4 README names `_FORCE`, `CLAUDE_CODE_EFFORT_LEVEL`, family-alias quirk, inverted roster; no
  subscription-usage claim.
- AC5 research Budget-line parsers tolerate the slot (test in `docs/research/test_*.py`).

**MT-2 — stratify instruments by subagent roster** (unmilestoned; #281 AC2 split out).
`stratum.py` groups by resolved (parent model, effort, subagent model+effort set) from transcripts.
- AC1 test: same parent stratum, different subagent models → different groups.
- AC2 `PRICING` covers every model a tier resolves to on the Anthropic API (D016).
- AC3 answer, with evidence: is subagent effort readable from the session JSONL?

**MT-3 — measured tiering presets (= #281 rewritten in place)** (unmilestoned; depends #272,
#273, #274, #209, MT-1 installed, MT-2). Candidate rows `explore: haiku`, `mutation: sonnet@medium`,
`finder: inherit@medium`, **plus the inverted roster as its own arm**.
- AC1 pre-registration states X (saving), Y (rounds/issue non-inferiority margin), n — before arm 1.
- AC2 promotion only by the §7.9 rule; failures recorded.
- AC3 skeleton default stays `inherit`; promoted rows go to the README only.
- AC4 `role.route` qualifier lands only with the first promoted row that needs it.

**MT-4 — bring your own models: a provider profile Fred has run** (v1.0.0; depends MT-1).
- AC1 README section with profile, fidelity caveats (§7.6, Q5), Anthropic's "doesn't support
  routing … non-Claude models" sentence.
- AC2 evidence from one real run (session ID, engine version, provider, outcome, cost).
- AC3 §11 "before phase 3" rows re-checked and dated.
- AC4 profile pins all four aliases.

**Existing issues:** #281 → rewritten as MT-3. #288 gains an AC: when the fix-agent spawn lands,
`fix` becomes a live key. #38 and #284: cross-reference — any route/risk model choice resolves
through `MODEL_TIERS`, not a second vocabulary. #298 gains this repo's `MODEL_TIERS` entry.

## 3. Capture items that are not issues

- §11 re-check table → carried in the epic body with "last checked" per row; "each minor release"
  rows checked in every version-bump PR (one line beside the README status-block convention in
  root `CLAUDE.md`).
- §9 PreToolUse enforcement hook → recurrence log: each transcript/`models=` disagreement is an
  F-comment on #1; revisit at n≥3.
- Corrections to cost review R4 (three roles are parent turns; Part 1 is judgment; the Explore
  caution is half true) → dated correction note in `cost-review-2026-10-26.md` R4.

## 4. Backlog order

**Now:** #128 close (+ close v0.3.1 milestone) · #150 AC1 (`/context` reading) · #276, #290,
#109 · #272 · #273 · #279 (R2 design note, Fable) · #298 · #195 (branch-protection setting).
**Next:** #274 (time-boxed) · #209 · MT-1 · MT-2 · #306 (move to `deferred-corpus`) · #234.
**Later:** #288 · MT-3/#281 · #280 · #282 (absorb #85) · #283, #284 (count first) · MT-4 · #229 ·
pr-brief/epic-brief children · #184, #185 · #177, #198, #269.
**Defer/merge/close:** close #138 (superseded); fold #211 into #271; #144 likely superseded by
#274 (unverified); #210 likely moot after #133 (unverified); #169/#56/#153 decided at #288's plan
gate; tech-debt items stay; #222 stays unless hit; triage #89/#104/#86; #250 is an index; label
#306/#298/#185/#184/#104.

## 5. Open questions for Fred

1. What does v1.0.0 mean — stability/marketability commitment or model-selection feature release?
2. MT-1 in its own v0.6.0, or v0.5.0's last item below the cut line?
3. Skeleton lists the 8 role keys all `inherit`, or a `—`-plus-reason row with keys only in README?
4. Which provider profile will you actually run for phase 3, and on what budget?
5. Does pr-brief (#229) join v1.0.0's bundle or ship earlier on its own?
