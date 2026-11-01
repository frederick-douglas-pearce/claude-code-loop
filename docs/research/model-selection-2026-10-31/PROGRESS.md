# Model-selection design research — progress log

**Started:** 2026-10-31. **Owner session:** Claude Code (Fable 5.1), interactive with Fred.
**Status: COMPLETE, uncommitted (2026-10-31).** The design doc is at
`docs/research/model-selection-2026-10-31.md` (424 unwrapped lines, 12 sections, draft D018 in
§7.10) with all 14 architect findings applied and spot-checked; the `docs/research/README.md`
index row is added. Awaiting Fred's review; lands via branch + PR when he asks. The three
load-bearing claims are verified and folded into §10/§11; the architect review returned 14 findings (2 BLOCKING: the default-deny clause
made a false "exactly as today" claim — fix is "the engine passes neither `model` nor `effort`";
and `inherit` is safe only as *today's behavior*, not for quality — the inverted-roster case,
a cheaper session with judgment roles tiered **up**, breaks "unknown ⇒ main model"). All 14
accepted and being applied by a reviser: rename journal slot `roster=`→`models=` (roster is
the step-8 lens term), role keys `verify`→`ac-verify`, drop `security`, defer the route
qualifier to phase 2, reserve `fix` only (forks ignore model params so R2's path cannot feed
`implement`), add the inverted roster as option 13 (reaches the parent's ~2/3 of the bill in
v1 with no new mechanism), `CLAUDE_CODE_EFFORT_LEVEL=max` in provider guides defeats `@effort`,
provider profile goes in `settings.local.json` not the committed file, stratify on transcript
model IDs not the alias journal, pre-register rounds/issue non-inferiority + decision rule +
power, keep the economy table out of phase 1, split #281 into vocabulary + tiering issues.
Remaining: spot-check §1/§7.1/§6 after the reviser, add the `docs/research/README.md` index
line, present to Fred, open the PR when asked. Nothing committed; the
tree is on `main` at `3287e97` with only this directory untracked.

Resume from here if the session that started this work is gone.

## The request (Fred, 2026-10-31, before scoping v0.5.0)

Research and design **per-task model selection for the dev loop** — e.g. a cheap model (Haiku) for
implementing/reviewing docs, Sonnet for test development/review — with the harder requirement that
models from **other providers** (GPT-4o / GPT-5, DeepSeek V3, Qwen, Grok, …) be usable too. Three
goals, in Fred's order of emphasis: save significant cost, possibly cut loop runtime, and (most
important) make the loop more marketable to new users. Open questions he named: configured in
the existing `loop.config.md`, a new config, or something else? Implemented via Claude Code's new
Mods feature, hooks, or a better option? Constraint: relatively easy to configure within the dev
loop. Deliverable: a well-researched **design document** with the favored approach **and the top
two alternatives**, documented so it can be re-used as the landscape changes.

## Deliverable and where it lives

- Design document: `docs/research/model-selection-2026-10-31.md` (not yet written) — follows the
  `cost-review-2026-10-26.md` + same-named folder precedent. Could move to `.claude/specs/` as a
  PRD once it becomes an epic; decide with Fred.
- Research notes (this folder), one per researcher. Each has Takeaway / Cited Findings /
  Inferences / Gaps sections and dated citations.
- Landing path: a branch + PR (new design doc is not a "simple documentation update"), and the
  `docs/research/README.md` index gets a line. **Do not commit or push without Fred asking.**

## Research notes — status

| File | Scope | Status |
|---|---|---|
| `dev-loop-internals.md` | every spawn point in the engine, where the money goes (cost review R4/R9/§5.6), CAPS touch points, maintainer constraints, issues #281/#38/#71/#27/#150/#272/#274, F198 | **done** (351 lines) |
| `prior-art-and-evidence.md` | aider/OpenCode/Codex/Continue/Roo/Cline/Cursor/Copilot/Gemini CLI config shapes; Anthropic's measured effort-vs-model guidance; RouteLLM/FrugalGPT; SE sub-task evidence by role | **done** (222 lines) |
| `claude-code-native-surfaces.md` | settings `model`, `ANTHROPIC_MODEL`, `CLAUDE_CODE_SUBAGENT_MODEL`, `ANTHROPIC_DEFAULT_*_MODEL`, subagent `model:`/`effort:` frontmatter, Agent-tool `model`/`effort` params, skills/commands `model`, Bedrock/Vertex alias mapping, caching, subscription | **done** (317 lines) |
| `third-party-providers-and-gateways.md` | `ANTHROPIC_BASE_URL` providers (DeepSeek, Kimi, GLM, MiniMax, Qwen, xAI, OpenRouter, Ollama), LiteLLM, claude-code-router (`<CCR-SUBAGENT-MODEL>`), per-subagent provider switching, fidelity problems, ToS, pricing snapshot | **done** (327 lines) |
| `hooks-and-mods.md` | what a Mod is (from the local `plugin-authoring` skill + public docs), `PreToolUse` `updatedInput` on the Agent tool, `SubagentStart/Stop`, `SessionStart` env injection, status-line JSON, plugin packaging of `agents/`, hook fail posture | **done** |

If an in-flight file is missing when you resume, re-run that research with the scope above.

## Findings so far that shape the design

From `dev-loop-internals.md`:
- The payload has **zero model/effort vocabulary** today. Nine spawn roles exist (SCOPE_AGENT at
  steps 1/3/5; DESIGN_AGENT at 4/5 and the step-8 scope ruling; hermetic checker at 6; finders,
  fresh re-checker, optional fix agent at 8; SECURITY_REVIEW/VERIFY at 9/10; AC-verifier Part 1
  and mutation selector at 10; Class B re-checker).
- **Step 6 (implement) runs in the parent thread** (`loop-engine.md:451`; D017; cost review R2).
  The parent's (model, effort) is the harness's — there is **no engine lever to re-model the
  implementer** short of a writing subagent in an isolated copy (R1's fix agent is the first
  increment of that).
- Subagents are 33–38% of the whole-tree bill; every one runs `claude-opus-5-5` (F198). R4 of the
  cost review already proposes tiering and #281 is the issue — but #281 has two internal
  contradictions: it tiers roles that are parent turns, and it would pin `model:` in the
  user-global `pm`/`architect` frontmatter, which is outside all three layers and the engine is
  forbidden to edit.
- `CapsVocabularyTests` scans core + units + SKILL.md for ALLCAPS tokens and requires each to
  appear somewhere in `init-loop.md`. `_PAYLOAD_INVENTORY` has no `agents/` dir — shipping agent
  definitions or a new hook means updating the inventory; a new hook must be
  `${CLAUDE_PLUGIN_ROOT}`-relative; README edits land in both copies.
- Default-deny prose rule ⇒ the only compliant posture is **unknown/unset tier ⇒ main model**,
  with no completeness argument.
- Stratum must become `(parent model, effort, subagent model set)` (§5.6); `stratum.py` records
  subagent strata but does not group by them.
- Decision log format `## D0NN — date — title`, latest D017.

From `prior-art-and-evidence.md`:
- Every surviving tool: **global default + per-role override**, same value syntax
  (`provider/model`), secondary roles default to *inherit*. Named presets (Cursor Auto,
  Copilot Auto, `opusplan`, community quality/balanced/budget profiles) sit **above** that layer.
- Anthropic, measured: "Tuning effort is often a better lever than switching models"; sweep
  effort on one model first; Haiku subagents under Opus cut cost/attempt ~32% at ~4 pts pass
  rate — "an alternative to lowering effort, not better"; "Upgrade the model" can be up to 87%
  cheaper per *solved* task. Claude Code docs: `model: haiku` for "simple subagent tasks",
  Explore→haiku is the one concrete example.
- Routing research (RouteLLM etc.) is single-turn QA; the one agentic measurement
  (Arize/Fireworks, 2026-07) shows cost-per-successful-task diverging from token price and a
  cheap-first escalation ladder beating the best single model.
- Review/judging is the weakest case for cheapening (LLM reviewers over-reject; single-model
  judges uneven). Bookkeeping roles are universally cheap-tiered by vendors without measurement.
- Goose's lead/worker env-var feature was removed within a year — a caution about env-var-shaped
  routing surfaces.

From `claude-code-native-surfaces.md` (CLI 2.1.314 running; 2.1.316 installed; docs fetched 2026-10-31):
- **Agent-tool per-call `model` is alias-only** (`sonnet|opus|haiku|fable`; no full ID, no
  `inherit`); definition frontmatter `model:` takes alias, full ID, or `inherit`. Subagent
  resolution order: per-call param > definition frontmatter > `CLAUDE_CODE_SUBAGENT_MODEL` >
  main model. `CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1` overrides the first two. Forks always use the
  parent model and ignore both params.
- Effort: `CLAUDE_CODE_EFFORT_LEVEL` > in-session > `--effort` > settings > model default
  (`medium` on the 5.5 models). Subagent: Agent-tool `effort` param (v2.1.292+) > frontmatter
  `effort:` > session. New in 2.1.316 (CHANGELOG only): `CLAUDE_CODE_SUBAGENT_EFFORT`.
- `ANTHROPIC_DEFAULT_{FABLE,OPUS,SONNET,HAIKU}_MODEL` pin what each alias resolves to, and
  subagent aliases follow those pins — **so an alias is a portable "tier" name**: the config can
  bind roles to tiers, and the consumer's environment (or gateway) decides what a tier is.
  `ANTHROPIC_SMALL_FAST_MODEL` is deprecated in favor of `ANTHROPIC_DEFAULT_HAIKU_MODEL`.
- Quirk: a family alias (`opus`) resolves to the main model's exact ID when the main model is
  already in that family.
- Plugin `agents/*.md` honor `model:` and `effort:` (plus `maxTurns`, `tools`, `background`,
  `isolation: worktree`, `experimental.cacheTtl`); they ignore `hooks`, `mcpServers`,
  `permissionMode`. A plugin `settings.json` **cannot ship environment variables**; a consumer's
  `.claude/settings.json` can.
- Built-in `Explore` now inherits the main model (2.1.198 superseded the old "Haiku" note); a
  custom agent named `Explore` with `model: haiku` overrides the built-in.
- Caching: a non-fork subagent has its own prefix and cache (parent unaffected); forks share.
  `/model` switch = full re-read. **Subagent requests get a 5-minute cache TTL even on a
  subscription** (`CLAUDE_CODE_SUBAGENT_PROMPT_CACHE_TTL` / `experimental.cacheTtl` raise it).
- `SKILL.md` `model:` on the orchestrator's own skill = cache miss every invocation; never do it.
- Subscription: subagent requests count toward the same usage limits; **no official per-model
  consumption rate** — "haiku subagents cost less of my Max limit" is unverified.

From `hooks-and-mods.md`:
- **A Mod is a plugin whose `hooks/hooks.json` names `"modules": ["./register.js"]`**, an ES module
  exporting `register(on, options)`; handlers are an in-process middleware chain over engine
  events. Shipped v2.1.287 (early access). Distributed via the normal marketplace; can ship in the
  same plugin as skills. Unsandboxed, full user permissions.
- **Mods can route models**: `agent.spawn` can replace a subagent's `model` (alias or full ID)
  or deny the spawn; `turn.step` can rewrite `model`/`effort` on **every model request, main loop
  included** — the only mechanism that could re-model the parent-thread implementer per step
  (at the price of a cache re-read on each switch). `AgentSpawnInput` has no `effort` field;
  `FORCE` outranks a hook; nothing exposes base URL/provider; whether the process environment's
  `ANTHROPIC_MODEL`/`ANTHROPIC_BASE_URL` are re-read mid-session is undocumented.
- Settings hooks: `PreToolUse` `updatedInput` exists (replaces the whole input; validated since
  2.1.300, unknown keys dropped); the subagent tool is matched as `Agent`; rewriting its
  `model`/`effort` is mechanically plausible, **documented nowhere as a use case**. Multiple
  rewrites are not merged; winner undefined. `SubagentStart/Stop` carry no model. `PreModelSwitch`
  can only allow/deny a user switch. The SessionStart env-file mechanism only prefixes Bash
  commands; it cannot change the API client.
- Cost visibility: status line JSON has `model.id`, `cost.total_cost_usd`, `effort.level`,
  `rate_limits`; mods see per-request `usage` incl. the model that answered.
- Fail posture: settings hooks fail **open** by default (`onFailure: "block"` opts into closed,
  v2.1.295+); mods fail open too unless a `.catch` returns the refusal.

From `third-party-providers-and-gateways.md`:
- **Every provider guide uses the same recipe**: `ANTHROPIC_BASE_URL` + the provider's key +
  `ANTHROPIC_DEFAULT_{FABLE,OPUS,SONNET,HAIKU}_MODEL` (+ `CLAUDE_CODE_SUBAGENT_MODEL`) set to the
  provider's own IDs. Documented for DeepSeek, Kimi, Z.ai/GLM, MiniMax, Alibaba Model Studio,
  Ollama (v0.14+), OpenRouter ("only guaranteed with the Anthropic first-party provider"), Vercel
  AI Gateway. xAI's `/v1/messages` is deprecated; OpenAI and Gemini have none (gateway needed).
  **So the four alias tiers are already the de facto cross-provider contract.**
- Anthropic (llm-gateway page, 2026-10-31): "doesn't support routing Claude Code to non-Claude
  models through any gateway" — unsupported, not prohibited; the legal page restricts
  credentials (no subscription OAuth through third parties), not backends.
- One session = one base URL, confirmed. Per-subagent provider switching: (a) model string the
  gateway routes on (frontmatter takes any full ID; per-call param = four aliases); (b) CCR's
  `<CCR-SUBAGENT-MODEL>` tag; (c) a mod's `agent.spawn`; (d) gateway hint headers (v2.1.273+,
  opt-in `CLAUDE_CODE_GATEWAY_HINT_HEADERS=1`): `x-claude-code-request-class`
  (main/subagent/compaction/auxiliary), `x-claude-code-agent-type` (Explore/Plan/general-purpose
  or "custom" — **a custom agent's name is never sent**), `x-claude-code-agent-id`.
- Gateways: LiteLLM (name → upstream map), CCR v3.1.3 (2026-10-09, rewritten as a desktop control
  plane; the v1 Router categories are gone from v3 docs), Bifrost (alias rules on model name +
  headers), Portkey, Vercel, Kong, Cloudflare (Claude backends only).
- Fidelity: the persistent real-world defect is **reasoning-state round-tripping on tool calls**
  (CCR #1378 DeepSeek V4 open since 2026-05; CCR #1057 Gemini thought_signature; LiteLLM Kimi
  multi-turn regressions); silent prompt-cache loss; `thinking: adaptive` 400s on unrecognized
  IDs; assumed 200K window. ⇒ non-Claude models are riskiest exactly on the tool-heavy roles.
- Outcomes are anecdotal only (GLM-5.2 ~$3.36/6M tokens; Kimi hybrid 60–80% claimed savings; "CC
  really needs the Anthropic special sauce"). No independent benchmark of the harness with
  non-Claude models.
- Pricing snapshot in the note (USD/1M in/out): gpt-6.1-sol 2/10, gpt-6-luna 0.10/0.50,
  deepseek-flash 0.30/1.20, deepseek-v4-pro 1.32/3.96, qwen-plus 0.40/1.20, grok-4.7 2/6,
  GLM-5.3 1.40/4.40, MiniMax-M3.1-Flash 0.15/0.60, Gemini 4 Argon 2/10; Claude Haiku 5.5
  0.10/0.50, Sonnet 5.5 2/10, Opus 5.5 4/20, Fable 5.1 10/50. **Haiku 5.5 is already in the
  cheap-third-party price band**, which weakens the cost case for cross-provider routing.

## Decisions taken 2026-10-31 (coordinator, after all five notes)

**Favored: tiers in the config, aliases as the contract, provider at the edge.**
- One new CAPS parameter, `MODEL_TIERS`, in `loop.config.md`: a role → `tier[@effort]` table.
  Tier ∈ `inherit|haiku|sonnet|opus|fable`; effort ∈ `low|medium|high|xhigh|max`. Keys are the
  engine's spawn roles (scope, design, explore, finder, recheck, verify, mutation, security,
  hermetic; `fix`/`implement` reserved for R1/R2), with an optional route qualifier
  (`finder.docs`) resolved most-specific-first. **Absent, unknown key, unknown tier, or
  unparseable ⇒ `inherit`** (default-deny: a tier the engine cannot read never cheapens a role).
- Engine: one spawn sentence per site passing `model`/`effort` on the Agent call from the table;
  journal the resolved roster on the `- Budget:` line for the stratum. No shipped `agents/`
  definitions in v1 (per-call param wins over frontmatter anyway; keeps the payload inventory).
- Provider dimension lives **outside the engine**: a "provider profile" = the consumer's
  committed `.claude/settings.json` env (`ANTHROPIC_BASE_URL`, key, `ANTHROPIC_DEFAULT_*_MODEL`)
  — the exact recipe every provider documents; mixed providers in one session need a
  name-routing gateway mapping the four tiers to upstreams. Engine never names a provider.
- Skeleton ships every role `inherit` (behavior-neutral release); an "economy" table is README
  guidance labeled unmeasured until #274's benchmark; the parent-thread implementer is **not**
  addressable in v1 (session model via `/model`/`/effort`), becomes a role when R1/R2 land.
- Phasing: (1) vocabulary + spawn sentences + skeleton row + README trust-model, all inherit;
  (2) measured economy preset; (3) provider-profile docs with fidelity caveats; (4) optional
  mod for parent-thread routing and per-role cost attribution once mods leave early access.

**Alternative A — routing Mod** (`agent.spawn` + `turn.step`): reaches the main loop and sees
per-request usage; early access, unsandboxed JS in the payload, fails open, no effort at spawn.
**Alternative B — `PreToolUse` routing hook** (stdlib Python, sidecar JSON, `updatedInput` on
`Agent`): enforcement independent of the orchestrator's prose compliance; undocumented use case,
role identification by convention, second config file.
**Complementary, not alternatives:** gateways (how providers are reached). **Rejected:** a second
config file for tiers; `/model` switching per step (cache re-read, parent-thread implement);
external agent CLIs via Bash; an Agent-SDK orchestrator; per-role CAPS names instead of one table.

**Load-bearing claims, verified 2026-10-31 in this session (CLI 2.1.314, Max subscription,
parent Fable 5.1):**
1. Per-call `model: haiku` on a built-in `Explore` spawn **is honored** — the subagent reported
   "You are powered by the model named Haiku 5.5. The exact model ID is claude-haiku-5-5."
   (This is the R4 "Explore runs the main model on a subscription" caveat resolved: the
   per-call parameter moves it; the env var alone does not.)
2. `CapsVocabularyTests` extracts `MODEL_TIERS` with its `_UNDERSCORED` regex
   (`tests/test_repo_consistency.py`, class at ~593) and only requires the literal to appear
   anywhere in `init-loop.md`.
3. Per-call `model: sonnet` on a general-purpose spawn is honored (`claude-sonnet-5-5`). The
   `effort: low` parameter was accepted by the tool schema, but effort is not visible from
   inside the subagent's prompt, so its effect is **accepted, not observed** — verify via
   `/tasks` (v2.1.242+) or the transcript's request parameters.

## Emerging shape of the recommendation (superseded by the Decisions section above; kept for history)

1. **Config seam:** per-role `*_MODEL` / `*_EFFORT` style CAPS bindings in `loop.config.md`
   (the existing seam; no new config file). **Values are tier aliases**
   (`haiku|sonnet|opus|fable|inherit`) because the Agent tool's per-call `model` is alias-only
   and aliases are what `ANTHROPIC_DEFAULT_*_MODEL` / a gateway remap — that is how one config
   stays portable across providers. **Default `inherit`** for every role. A named profile
   (`economy`/`balanced`/`quality`) only as an `/init-loop` convenience that fills the matrix.
2. **Engine side:** one "spawn sentence" per spawn site passing the bound model/effort to the
   Agent call; unknown or unbound ⇒ inherit (default-deny). Effort first, model second, per
   Anthropic's measured guidance. Judgment roles (architect, finders, re-checker, AC-verifier)
   stay on the main tier by default.
3. **Provider dimension:** handled **outside the engine**, at the gateway layer
   (`ANTHROPIC_BASE_URL` → LiteLLM / claude-code-router / provider's Anthropic-compatible
   endpoint) with the config's model *names* being what the gateway routes on. The engine stays
   provider-agnostic. Whether per-subagent provider switching is possible at all inside one
   session hinges on the providers/gateways note (expected: only via gateway name-mapping or
   CCR's subagent tag).
4. Hooks/Mods: expected role is enforcement/observability (a PreToolUse hook could pin or audit
   `model` on Agent calls; a Mod could show the tier in the status line), not the primary config
   surface — pending `hooks-and-mods.md`.
5. **Measurement before defaults:** ties to #272/#274/#281 — any default tier change ships only
   with the paired benchmark and quality outcome; stratum by roster.

Top-2 alternatives to write up (provisional): (A) hook-enforced routing table (a stdlib hook
rewrites `model` on Agent calls from a sidecar JSON, like the append-guard) and (B) gateway-only
routing (claude-code-router categories / LiteLLM aliases, zero engine change). Also to be
documented as considered-and-rejected: a second config file, running steps via external agent
CLIs (aider/codex/opencode) from Bash, an Agent-SDK orchestrator, and session-level `/model`
switching per step (cache invalidation + parent-thread implement).

## Next steps

1. Wait for the three in-flight notes; read their hand-back summaries (not the transcripts).
2. Spawn the writer: produce `docs/research/model-selection-2026-10-31.md` from the five notes
   with the outline below; cite the notes and primary sources; American English; date-stamp
   every landscape claim.
3. Architect review of the favored option (premise validity, fail-safe posture, three-layer fit);
   verify the load-bearing claims yourself (Agent tool accepted `model` values, hook
   `updatedInput`, gateway per-subagent routing) before finalizing.
4. Present to Fred; offer the PR; add the `docs/research/README.md` index line in the same PR.

### Design-doc outline

1. One-paragraph answer. 2. Goals and constraints (cost, runtime, marketability; three-layer
split, project-agnostic engine, fail-safe, stdlib-only, installed-vs-tree). 3. Where the loop
spends and which roles exist (table from internals). 4. Mechanism inventory (native surfaces,
hooks, Mods, gateways, providers) with verification status. 5. Prior art and evidence.
6. Options considered (wide) with an evaluation matrix. 7. Recommended design (config vocabulary,
engine changes, provider layer, defaults, migration/phasing, tests, README/trust-model updates).
8. Alternative A and B in the same depth. 9. Risks and open questions. 10. What to re-check as
the landscape moves (dated). 11. Sources.
