# Pointing Claude Code at non-Anthropic models: providers, gateways, per-subagent routing

Research notes, as of **2026-10-31**. Every source was fetched on that date unless the entry says otherwise; "(stale?)" marks a source older than six months (published before ~2026-05-01). Verified facts carry a link; inferences and rumors are labeled. Claude pricing is deliberately out of scope.

One orientation note before the questions: the model names in the brief (GPT-5 / GPT-5-mini, DeepSeek V3.x / R1, Qwen3-Coder / Qwen3 Max, Grok 4 / Grok Code Fast, Kimi K2, GLM-4.6, Gemini 2.5) are one to three generations behind the live catalogs on 2026-10-31. The provider guides now name DeepSeek V4.1-Flash / V4-Pro, Kimi K3, GLM-5.3, MiniMax-M3.1-Flash, Qwen 3.7/3.8, Grok 4.7, Gemini 3.8/4, and GPT-6.x. I report the current successors and the legacy prices where a provider still lists them.

## Q1. Which providers expose an Anthropic Messages-compatible endpoint and document using Claude Code with it?

### Takeaway
Six providers officially document `ANTHROPIC_BASE_URL` + `ANTHROPIC_AUTH_TOKEN` for Claude Code with their own models (DeepSeek, Moonshot/Kimi, Z.ai/GLM, MiniMax, Alibaba Model Studio/Qwen, Ollama), and OpenRouter and Vercel AI Gateway expose a native `/v1/messages` that reaches many providers' models. xAI has deprecated its Anthropic-compatible endpoint; Google Gemini and OpenAI have none. The provider guides converge on one recipe: set `ANTHROPIC_DEFAULT_{OPUS,SONNET,HAIKU}_MODEL` (and increasingly `ANTHROPIC_DEFAULT_FABLE_MODEL` and `CLAUDE_CODE_SUBAGENT_MODEL`) to the provider's own model IDs, often with a `[1m]` suffix.

### Cited Findings

**DeepSeek** (official)
- Base URL `https://api.deepseek.com/anthropic`, endpoint `POST /anthropic/v1/messages`, auth via `x-api-key` or `Authorization: Bearer`. Models `deepseek-flash` (served by DeepSeek-V4.1-Flash-1017) and `deepseek-v4-pro`. Server-side name mapping: `claude-opus*` → `deepseek-v4-pro`; `claude-haiku*` / `claude-sonnet*` / other `claude*` → `deepseek-flash`; non-`claude` unsupported names return 400 — [DeepSeek Anthropic API guide](https://api-docs.deepseek.com/guides/anthropic_api) (no date on page; © 2026)
- Claude Code guide sets `ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic`, `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_MODEL=deepseek-flash[1m]`, `ANTHROPIC_DEFAULT_OPUS_MODEL=deepseek-flash[1m]`, `ANTHROPIC_DEFAULT_SONNET_MODEL=deepseek-flash[1m]`, `ANTHROPIC_DEFAULT_HAIKU_MODEL=deepseek-flash`, `CLAUDE_CODE_SUBAGENT_MODEL=deepseek-flash`, `CLAUDE_CODE_EFFORT_LEVEL=max`, `CLAUDE_CODE_AUTO_COMPACT_WINDOW=786432`; notes the `claude-opus` mapping bills at V4 Pro price — [DeepSeek: Integrate with Claude Code](https://api-docs.deepseek.com/quick_start/agent_integrations/claude_code) (no date)
- Feature support on the Anthropic endpoint: `system`, `stream`, `stop_sequences`, `temperature`, `thinking` (`adaptive` treated as `enabled`; `budget_tokens` ignored), `output_config.effort`, client tools, `tool_choice` (`any` → `auto`; `tool` only in non-thinking mode, else 400), server-side web search. **Ignored**: `cache_control` (caching is automatic; `cache_read_input_tokens` reported, `cache_creation_input_tokens` always 0), `top_k`, `service_tier`, `anthropic-version` header, `disable_parallel_tool_use`. **Unsupported**: `document`, `redacted_thinking`, MCP blocks, `custom` tool type (422). Images: `deepseek-flash` accepts them in user messages and `tool_result`; `deepseek-v4-pro` replaces them with "[Unsupported Image]" — [DeepSeek Anthropic API guide](https://api-docs.deepseek.com/guides/anthropic_api)

**Moonshot / Kimi** (official)
- Docs moved: `platform.moonshot.ai` 301-redirects to `platform.kimi.ai`. Base URL `https://api.moonshot.ai/anthropic`. Guide sets `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_MODEL=kimi-k3[1m]`, `ANTHROPIC_DEFAULT_OPUS_MODEL`/`SONNET`/`FABLE` = `kimi-k3[1m]`, `ANTHROPIC_DEFAULT_HAIKU_MODEL=kimi-k2.7-code`, `CLAUDE_CODE_SUBAGENT_MODEL=kimi-k3[1m]`, `CLAUDE_CODE_AUTO_COMPACT_WINDOW=1000000`, `CLAUDE_CODE_EFFORT_LEVEL=max`. `kimi-k2.7-code` has thinking forced on (400 if thinking is off); `kimi-k2.6` suggested for latency-sensitive tasks. The page's curl example uses `kimi-k3.1-pro`, which its model table does not list — [Kimi: Claude Code guide](https://platform.kimi.ai/docs/guide/claude-code-kimi.md) (no date)
- K2-series models are unavailable to newly registered users from 2026-10-31 and planned for retirement by end of December 2026 — [Kimi pricing page](https://platform.kimi.ai/docs/pricing/chat)

**Z.ai / Zhipu GLM** (official)
- Base URL `https://api.z.ai/api/anthropic`; settings.json `env`: `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_BASE_URL`, `API_TIMEOUT_MS=3000000`; model switch by setting `ANTHROPIC_DEFAULT_OPUS_MODEL` / `ANTHROPIC_DEFAULT_SONNET_MODEL` to `glm-4.7`. Page states it was verified with Claude Code **2.0.14** (an ~October 2025 build), so the page itself is (stale?) relative to the current model lineup — [Z.ai: Claude Code](https://docs.z.ai/scenario-example/develop-tools/claude)
- GLM Coding Plan: Lite "starting at 18 USD per month"; credits 2,000 / 12,000 / 28,000 per 5 hours and 10,000 / 60,000 / 140,000 per week for Lite / Pro / Max; all plans include GLM-5.3 and GLM-5.3-Flash, with GLM-4.7 requests routed to GLM-5.3-Flash; off-peak usage charged at 50% of the credit rate; Claude Code listed as a supported tool — [Z.ai devpack overview](https://docs.z.ai/devpack/overview) (no date)

**MiniMax** (official)
- Base URL `https://api.minimax.io/anthropic`; `ANTHROPIC_AUTH_TOKEN` = M Plan key; `CLAUDE_CODE_AUTO_COMPACT_WINDOW=524288`; `CLAUDE_CODE_EFFORT_LEVEL=max`; `ANTHROPIC_MODEL` and all three `ANTHROPIC_DEFAULT_*_MODEL` set to `MiniMax-M3.1-Flash[1m]`; thinking always on; setup wizard `npx -y mmx-cli@latest agent setup`; "Some Claude Code versions send `xhigh` as `high`" — [MiniMax: Claude Code](https://platform.minimax.io/docs/coding-plan/claude-code) (no date)

**Alibaba Cloud Model Studio / Qwen** (official, last updated Oct 11, 2026)
- Anthropic-compatible endpoints under `/apps/anthropic`: pay-as-you-go `https://{WorkspaceId}.ap-southeast-1.maas.aliyuncs.com/apps/anthropic` (regions cn-beijing, ap-southeast-1, us-east-1; key must match region), Token Plan `https://token-plan.ap-southeast-1.maas.aliyuncs.com/apps/anthropic`, Coding Plan `https://coding-intl.dashscope.aliyuncs.com/apps/anthropic`. Env: `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_BASE_URL`, `ANTHROPIC_MODEL`, `ANTHROPIC_DEFAULT_HAIKU/SONNET/OPUS_MODEL`, `CLAUDE_CODE_SUBAGENT_MODEL`, `CLAUDE_CODE_MAX_CONTEXT_TOKENS`. Role maps: Token Plan → `auto` main/subagent, `qwen3.6-flash` (Haiku), `qwen3.8-flash` (Sonnet), `qwen3.8-max` (Opus); Coding Plan → `qwen3.7-plus` for all roles; PAYG → `qwen3.7-max` for main/Sonnet/Opus/subagent and `qwen3.6-flash` for Haiku. Context is 200K by default, 1M via `CLAUDE_CODE_MAX_CONTEXT_TOKENS=1000000` or a `[1m]` suffix — [Model Studio: Claude Code](https://www.alibabacloud.com/help/en/model-studio/claude-code)
- An older community guide uses `https://dashscope-intl.aliyuncs.com/apps/anthropic` — [Alorse/cc-compatible-models](https://github.com/Alorse/cc-compatible-models) (content references April 2026; stale?)

**Ollama** (official)
- Ollama v0.14.0+ is "compatible with the Anthropic Messages API"; Claude Code setup: `ANTHROPIC_BASE_URL=http://localhost:11434`, `ANTHROPIC_AUTH_TOKEN=ollama`, then `claude --model gpt-oss:20b`; recommended local `gpt-oss:20b`, `qwen3-coder`; cloud `glm-4.7:cloud`, `minimax-m2.1:cloud`; at least 32K context recommended — [Ollama blog: Claude Code](https://ollama.com/blog/claude) (Jan 16, 2026; stale?)
- Supported: messages, streaming, system, tools, thinking, vision (base64 only). **Unsupported**: `tool_choice`, `metadata`, `/v1/messages/count_tokens`, batches, **prompt caching (`cache_control`)**, citations/PDF `document`, streaming `error` events; `budget_tokens` accepted but not enforced; the local server does not validate keys; direct cloud requires `Authorization: Bearer` and "tool-choice controls, deferred tools, and hosted web search are not fully supported" — [Ollama: Anthropic compatibility](https://docs.ollama.com/api/anthropic-compatibility) (no date)
- Ollama v0.15 adds `ollama launch`, which sets `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_BASE_URL`, and `ANTHROPIC_API_KEY` automatically — [Classmethod write-up](https://dev.classmethod.jp/en/articles/claude-code-ollama-local/) (secondary)

**OpenRouter** (official)
- `ANTHROPIC_BASE_URL=https://openrouter.ai/api`, `ANTHROPIC_AUTH_TOKEN=<sk-or-...>`, `ANTHROPIC_API_KEY=""` ("Explicitly blank out `ANTHROPIC_API_KEY` to prevent conflicts"). "Claude Code with OpenRouter is only guaranteed to work with the Anthropic first-party provider." "Claude Code is optimized for Anthropic models and may not work correctly with other providers." Lists `ANTHROPIC_DEFAULT_FABLE/OPUS/SONNET/HAIKU_MODEL` and `CLAUDE_CODE_SUBAGENT_MODEL` as the mapping variables — [OpenRouter: Claude Code integration](https://openrouter.ai/docs/guides/coding-agents/claude-code-integration) (no date)
- The `/api/v1/messages` URL I tried for the API reference returned 404; the integration guide above is the authoritative page — [404 observed at openrouter.ai/docs/api-reference/messages](https://openrouter.ai/docs/api-reference/messages)

**Vercel AI Gateway** (official, last updated 2026-09-18)
- `ANTHROPIC_BASE_URL=https://ai-gateway.vercel.sh`, `ANTHROPIC_AUTH_TOKEN=<AI Gateway key>`, `ANTHROPIC_API_KEY=""`; "Use any model available through the gateway"; model IDs are `provider/model` (e.g. `anthropic/claude-opus-5`); `/v1/messages` and `/v1/messages/count_tokens` supported; `cache_control` is passed through only to Anthropic, Vertex-Anthropic, and Bedrock-Anthropic models ("Other providers or models with implicit caching work automatically"); `CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS` and `CLAUDE_CODE_EXTRA_BODY` documented for provider options — [Vercel: Anthropic Messages API with AI Gateway](https://vercel.com/docs/ai-gateway/sdks-and-apis/anthropic-messages-api)

**xAI** — deprecated
- The `/v1/messages` and `/v1/complete` endpoints sit under "Legacy & Deprecated" with the warning "**Deprecated**: The Anthropic SDK compatibility is fully deprecated"; no removal date; migration target is the Responses API or gRPC — [xAI REST API reference: legacy](https://docs.x.ai/developers/rest-api-reference/inference/legacy)
- The older integrations page (examples use `grok-beta`) still claims Anthropic SDK compatibility — [xAI integrations](https://docs.x.ai/api/integrations) (stale?)

**Google Gemini** — none found
- A third-party compatibility review states the Gemini docs "do not mention an Anthropic-compatible endpoint"; Google documents OpenAI-library compatibility only — [DevelopersDigest: Google API compatibility](https://www.developersdigest.tech/reference/api-compatibility/google); Gemini is reached from Claude Code via gateways (Kong, Bifrost, LiteLLM, Vercel, CCR) or the `gemini-for-claude-code` proxy — [Kong guide](https://developer.konghq.com/ai-gateway/use-claude-code-with-ai-gateway-gemini/); [gemini-for-claude-code](https://github.com/coffeegrind123/gemini-for-claude-code)

**OpenAI** — none found
- Searches returned only the reverse direction (Anthropic's OpenAI-SDK compatibility layer) and third-party gateways; nothing from OpenAI documents an Anthropic-format endpoint — [Anthropic: OpenAI SDK compatibility](https://platform.claude.com/docs/en/api/openai-sdk)

**Community index**: a GitHub repo catalogs Anthropic-compatible providers with base URLs and plan prices (DeepSeek, MiniMax incl. China `api.minimaxi.com/anthropic`, Moonshot, Z.ai, Xiaomi MiMo `https://api.xiaomimimo.com`, StepFun `https://api.stepfun.ai/`, SiliconFlow, OpenRouter, Ollama) — [Alorse/cc-compatible-models](https://github.com/Alorse/cc-compatible-models) (32 stars; prices there predate the current catalogs; stale?)

### Inferences
- The `ANTHROPIC_DEFAULT_*_MODEL` remap is the de-facto portable interface: every official guide uses it, so a plugin that writes those four variables (plus `CLAUDE_CODE_SUBAGENT_MODEL`) covers DeepSeek, Kimi, GLM, MiniMax, Qwen, Ollama, OpenRouter and Vercel without provider-specific logic.
- Providers that do not document `ANTHROPIC_DEFAULT_HAIKU_MODEL` (Z.ai) will see Claude Code send the alias default (a `claude-haiku-*` name) for background tasks; whether that works depends on server-side name mapping (DeepSeek does it; Z.ai's behavior is unverified).

### Gaps
- No official Kimi, Qwen 3.8-max, or MiniMax Coding Plan price tables rendered in my fetches (tables are loaded client-side); see Q7 for the aggregator figures and their status.
- I did not verify whether Z.ai's endpoint maps `claude-*` names server-side the way DeepSeek does.

## Q2. Gateways: which can route by model name per request, and which per subagent?

### Takeaway
Every gateway routes by the `model` string; a few (Bifrost, CCR, LiteLLM via config) can also condition on headers. Only claude-code-router (CCR) has a subagent-specific mechanism, and it works by a prompt tag. Anthropic's own position, stated on the gateway page, is that it "doesn't support routing Claude Code to non-Claude models through any gateway."

### Cited Findings

**Anthropic's gateway documentation (code.claude.com)**
- "Any gateway that exposes a supported API format works. Anthropic doesn't endorse, maintain, or audit third-party gateway products, and doesn't support routing Claude Code to non-Claude models through any gateway." — [Other LLM gateways](https://code.claude.com/docs/en/llm-gateway)
- The gateway docs are now split across five pages: overview ([gateways](https://code.claude.com/docs/en/gateways)), [llm-gateway](https://code.claude.com/docs/en/llm-gateway), [llm-gateway-connect](https://code.claude.com/docs/en/llm-gateway-connect), [llm-gateway-rollout](https://code.claude.com/docs/en/llm-gateway-rollout), and the operator-facing [gateway compatibility guide](https://code.claude.com/docs/en/llm-gateway-protocol). Anthropic also ships its own self-hosted [Claude apps gateway](https://code.claude.com/docs/en/claude-apps-gateway) (Claude-only, SSO sign-in).
- Supported API formats a gateway may expose: **Anthropic Messages** (`ANTHROPIC_BASE_URL`; `/v1/messages`, optional `/v1/messages/count_tokens`), **Bedrock InvokeModel** (`ANTHROPIC_BEDROCK_BASE_URL` + `CLAUDE_CODE_USE_BEDROCK=1`), **Agent Platform rawPredict** (`ANTHROPIC_VERTEX_BASE_URL` + `CLAUDE_CODE_USE_VERTEX=1`). No OpenAI-format option exists; a gateway must translate — [gateway compatibility guide](https://code.claude.com/docs/en/llm-gateway-protocol)
- Behind `ANTHROPIC_BASE_URL`, "Claude Code treats the gateway as the Claude API and can't tell which upstream you forward to" — [gateway compatibility guide](https://code.claude.com/docs/en/llm-gateway-protocol)
- Model discovery: with `CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY=1`, Claude Code calls `GET /v1/models?limit=1000` (3 s timeout) and adds entries to `/model`, but **keeps only IDs containing `claude` or `anthropic`**, so `openai/gpt-5.5` never appears via discovery (it can still be selected with `--model`, `ANTHROPIC_MODEL`, or `ANTHROPIC_CUSTOM_MODEL_OPTION`) — [gateway compatibility guide → Model discovery](https://code.claude.com/docs/en/llm-gateway-protocol#model-discovery)
- `ANTHROPIC_CUSTOM_MODEL_OPTION`: "Claude Code skips validation for the model ID set in `ANTHROPIC_CUSTOM_MODEL_OPTION`, so you can use any string your API endpoint accepts" — [Model configuration](https://code.claude.com/docs/en/model-config)
- Admin lock: `allowedProviders: ["customEndpoint"]` pins a fleet to one `ANTHROPIC_BASE_URL` (v2.1.285+) — [Other LLM gateways](https://code.claude.com/docs/en/llm-gateway)

**LiteLLM** (official)
- "Use Claude Code with Non-Anthropic Models": `config.yaml` `model_list` maps a `model_name` to `openai/gpt-6.1-sol`, `gemini/gemini-3.8-flash`, `vertex_ai/...`, `azure/...`; Claude Code points at `ANTHROPIC_BASE_URL=http://0.0.0.0:4000` with `ANTHROPIC_AUTH_TOKEN=<LITELLM_MASTER_KEY>`; LiteLLM receives at `/v1/messages`, translates to the provider format, and translates the response back; minimum Claude Code v2.1.129, verified v2.1.247; caveat that `max_input_tokens` in `model_info` does not change the client's compaction window — [LiteLLM tutorial](https://docs.litellm.ai/docs/tutorials/claude_non_anthropic_models) (no date)
- Routing is by name: "Requests fail unless the model ID Claude Code sends exists as a `model_name` on the gateway" — [LiteLLM client setup: Claude Code](https://docs.litellm.ai/docs/proxy/client_setup/claude_code.md)
- LiteLLM auto-injects `cache_control` only for `anthropic/` routes — [LiteLLM prompt caching](https://litellm.docs.miniasp.com/en/docs/tutorials/prompt_caching) (mirror; secondary); a sticky "prompt cache routing" tutorial exists for load-balanced deployments — [LiteLLM: Claude Code prompt cache routing](https://docs.litellm.ai/docs/tutorials/claude_code_prompt_cache_routing)

**claude-code-router (CCR, musistudio)**
- v3.1.3 released 2026-10-09; 37.9k stars; MIT; Node 22+; desktop app plus `ccr ui`; gateway at `http://127.0.0.1:3456`, UI at `:3458`; v3 is a rewrite branded "One local control plane for every AI agent" with docs at ccrdesk.top (Chinese) — [GitHub README](https://github.com/musistudio/claude-code-router); [Releases](https://github.com/musistudio/claude-code-router/releases)
- v3 routing model: ordered **conditional rules** reading `request.header` or `request.body` (operators `==`, `!=`, `>`, `starts with`, `contains`, `contains deep`, `not contains`) with rewrites (`set`, `delete`, array ops) — "the most common routing pattern is setting `request.body.model` to the target provider and model"; **Node.js script rules** (2 s default timeout, fail-open, circuit breaker after 3 failures/60 s); Claude Code profile has a default model plus optional per-tier **Fable / Opus / Sonnet / Haiku** overrides as `provider/model`; `/model` inside the CLI lists CCR models — [CCR: routing](https://ccrdesk.top/routing/); [CCR: Claude Code agent config](https://ccrdesk.top/configuration/agents/claude-code/)
- **Subagent routing** (the only per-subagent mechanism I found in any gateway): "`<CCR-SUBAGENT-MODEL>供应商/模型</CCR-SUBAGENT-MODEL>`" — (1) if at least one model has a Description, CCR injects the model list into the Agent/Task tool descriptions; (2) Claude Code writes the tag on the first line of the derived agent's prompt; (3) CCR extracts and removes the tag from the system message or the first two user messages and routes to that model. "Headers such as `x-claude-code-agent-id` are for observation only"; "model selection follows the tag"; "it only works when models have Descriptions configured" — [CCR: routing → subagent](https://ccrdesk.top/routing/)
- The v1-era `Router` block (`default` / `background` / `think` / `longContext` / `longContextThreshold` / `webSearch` / `image`), `CUSTOM_ROUTER_PATH`, and the named transformers (`deepseek`, `gemini`, `openrouter`, `maxtoken`, `tooluse`, `reasoning`, …) do **not** appear in the v3 docs or README I fetched — [CCR README](https://raw.githubusercontent.com/musistudio/claude-code-router/main/README.md); [CCR configuration overview](https://ccrdesk.top/configuration/overview/)

**Bifrost (Maxim)** (official)
- `ANTHROPIC_BASE_URL=https://bifrost.example.com/anthropic`; `ANTHROPIC_AUTH_TOKEN=sk-bf-*` (virtual key), or keep the claude.ai login and send the key as `x-bf-vk` in `ANTHROPIC_CUSTOM_HEADERS`; model IDs `provider/model` (`openai/gpt-5.5`, `vertex/gemini-3.1-pro`, `bedrock/global.anthropic.claude-sonnet-4-6`, `azure/claude-sonnet-4-6`); `/model openai/gpt-5.5` mid-session; aliases `sonnet`/`opus`/`haiku` map via `ANTHROPIC_DEFAULT_*_MODEL`; **alias routing rules** map a label to any configured model with conditions on the model name and a `user-agent` starting `claude-cli`, "scoped per header or other request attributes"; session affinity keyed on `x-claude-code-session-id`; tested up to Claude Code 2.1.212 (2026-07-17); caveats: "OpenRouter was reported to stream empty function-call arguments", non-Claude models "might not implement Claude-specific server-side tools such as computer use", "Anthropic does not support routing Claude Code to non-Claude models", auto-mode classifier wants recognizable Claude model names — [Bifrost: Claude Code](https://docs.getbifrost.ai/cli-agents/claude-code.md)

**Portkey** (official)
- `ANTHROPIC_BASE_URL=https://aigw.portkey.ai`, `ANTHROPIC_AUTH_TOKEN=<Portkey key>`, `ANTHROPIC_CUSTOM_HEADERS` carrying `x-portkey-provider: @<slug>`; the provider slug selects the backend and the model ID goes in `ANTHROPIC_MODEL` / `ANTHROPIC_DEFAULT_*_MODEL`; "any model available through the gateway" (GPT-5.2, Grok, Kimi) by changing slug and model ID; Codex models unsupported pending a Responses adapter; fallback configs; `forward_headers` should include `anthropic-beta` — [Portkey AI Gateway: Claude Code](https://portkey.ai/docs/aigw/integrations/libraries/claude-code.md) (no date)

**Cloudflare AI Gateway** (official, last updated Aug 17, 2026)
- `ANTHROPIC_BASE_URL=https://gateway.ai.cloudflare.com/v1/<ACCOUNT_ID>/<GATEWAY_ID>/anthropic`; `cf-aig-authorization: Bearer <token>` via `ANTHROPIC_CUSTOM_HEADERS`; BYOK or Unified Billing; Bedrock/Vertex via `CLAUDE_CODE_USE_BEDROCK` / `CLAUDE_CODE_USE_VERTEX` with skip-auth; the page covers Anthropic, Bedrock, and Vertex only and says nothing about non-Anthropic models — [Cloudflare: Claude Code](https://developers.cloudflare.com/ai-gateway/integrations/coding-agents/claude-code/index.md)

**Kong AI Gateway** (official)
- AI Model entity with `formats: [type: anthropic]` exposing `/v1/messages`; routes by `config.route.model` (`body_param: model`, `values: [my-claude-gemini]`) to `gemini-2.5-flash`; client runs `claude --model "my-claude-gemini"` with `ANTHROPIC_BASE_URL=http://localhost:8000/`, `CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS=1`, `CLAUDE_CODE_DISABLE_UNKNOWN_MODEL_WINDOW_ENFORCEMENT=1`; a `request-transformer-advanced` policy strips `anthropic-beta`, `authorization`, `x-api-key`, the `beta` query param, and body fields `output_config`, `context_management`, `mcp_servers`, `container`, `service_tier`, `reasoning_effort`; "beta behavior varies by Claude Code version"; requires ai-gateway 2.0, kongctl ≥ 1.21.0 — [Kong: Claude CLI through AI Gateway and Gemini](https://developer.konghq.com/ai-gateway/use-claude-code-with-ai-gateway-gemini/) (no date)

### Inferences
- Per-request routing capability, ranked: CCR (rules on any header/body field + scripts + subagent tag) > Bifrost (rules on model name and headers) > LiteLLM / Kong / Portkey / Vercel / Cloudflare (by model string, with provider chosen by config or header set once per session).
- Gateway-side per-subagent routing without CCR's tag is possible only through the request headers Claude Code emits (see Q3), and those identify the subagent *type*, not its name.

### Gaps
- I could not fetch Portkey's or Bifrost's conditional-routing reference pages, so "per header" is as specific as the evidence gets for them.
- No gateway documents a tested matrix of Claude Code tool-use fidelity per non-Claude model.

## Q3. The crux: can different subagents in one session use different providers, and by what mechanisms?

### Takeaway
Confirmed: one session has one `ANTHROPIC_BASE_URL`, and the client cannot address two backends. Per-subagent provider switching therefore happens either (a) by the model string Claude Code sends, which a gateway or provider maps to another backend, or (b) by a gateway reading a prompt tag (CCR). I found two further client-side levers the brief did not list: (c) a Claude Code **mod** can set the model in an `agent.spawn` hook (and per request in `turn.step`), and (d) Claude Code emits per-request **hint headers** that classify the request as `main` / `subagent` / `compaction` / `auxiliary` and name built-in agent types, which a gateway can route on. All of them still terminate at the single gateway.

### Cited Findings
- Single destination: `ANTHROPIC_BASE_URL` "changes where requests are sent, not which model answers them. Route through a gateway with `ANTHROPIC_BASE_URL`, and the model still comes from the settings above" — [Model configuration](https://code.claude.com/docs/en/model-config)
- Subagent `model` frontmatter accepts "`sonnet`, `opus`, `haiku`, `fable`, a full model ID such as `claude-opus-5-5`, or `inherit`"; a full model ID "Accepts the same values as the `--model` flag"; resolution order (v2.1.251+): 1 per-invocation `model` parameter, 2 definition frontmatter (`inherit` = main model), 3 `CLAUDE_CODE_SUBAGENT_MODEL`, 4 main conversation's model; "If an installed mod sets a model in its `agent.spawn` hook, Claude Code uses that model in place of the per-invocation parameter" — [Create custom subagents](https://code.claude.com/docs/en/sub-agents)
- The Agent tool's per-invocation `model` parameter "takes a model alias: `sonnet`, `opus`, `haiku`, or `fable`. Claude can't pass a full model ID or `inherit` on that call" — [Create custom subagents](https://code.claude.com/docs/en/sub-agents)
- `--model`, `ANTHROPIC_MODEL`, and the `model` setting are not validated up front: "A mistyped value produces an error on the first request" — [Model configuration](https://code.claude.com/docs/en/model-config)
- `CLAUDE_CODE_SUBAGENT_MODEL` "Accepts an alias such as `haiku` or a full model name"; `CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1` (v2.1.257+) makes it override definitions' `model` fields — [Model configuration → Environment variables](https://code.claude.com/docs/en/model-config)
- The four alias tiers each resolve through their own variable (`ANTHROPIC_DEFAULT_FABLE/OPUS/SONNET/HAIKU_MODEL`), and `ANTHROPIC_DEFAULT_HAIKU_MODEL` also drives "background functionality"; `ANTHROPIC_SMALL_FAST_MODEL` is deprecated in favor of it — [Model configuration](https://code.claude.com/docs/en/model-config)
- Provider guides set these variables to **non-Claude strings** (DeepSeek `deepseek-flash[1m]`, Kimi `kimi-k3[1m]`, Qwen `qwen3.8-max`, MiniMax `MiniMax-M3.1-Flash[1m]`) including `CLAUDE_CODE_SUBAGENT_MODEL`, which demonstrates that arbitrary strings pass through unchanged — [DeepSeek guide](https://api-docs.deepseek.com/quick_start/agent_integrations/claude_code); [Kimi guide](https://platform.kimi.ai/docs/guide/claude-code-kimi.md); [Model Studio guide](https://www.alibabacloud.com/help/en/model-studio/claude-code)
- **Mod hooks** (new mechanism): `agent.spawn` fires when "A subagent or an agent team teammate is about to start"; a hook can return "`next({ ...e, model })` to choose its model, or `{ deny: reason }`"; it does not re-run when a subagent is resumed via `SendMessage`. `turn.step` fires when "One request is about to go to the model" and a hook can return `next({ ...e, model })` or `next({ ...e, effort })` — [Mods reference](https://code.claude.com/docs/en/plugins/mods/reference) (reference current as of v2.1.290)
- A mod is "an ordinary Claude Code plugin with one extra file, called the hooks module" and Mods shipped in Claude Code 2.1.287 — [Digital Applied: Claude Code mods explained](https://www.digitalapplied.com/blog/claude-code-mods-function-hooks-explained) (Oct 1, 2026; secondary); one plugin README says `agent.spawn` is dispatched from 2.1.275+ — [aitmpl mods listing](https://www.aitmpl.com/component/mods/integrations/pi-agent-for-claude) (secondary)
- **Request headers a gateway can route on**: `x-claude-code-session-id` (every request), `x-claude-code-agent-id` ("present only on requests from an agent Claude Code spawned inside the session"), `x-claude-code-parent-agent-id`; **gateway hint headers** (v2.1.273+; sent by default to api.anthropic.com, **off by default behind a custom base URL**, enabled with `CLAUDE_CODE_GATEWAY_HINT_HEADERS=1`): `x-claude-code-request-class` ∈ {`main`, `subagent`, `workflow`, `compaction`, `auxiliary`}, `x-claude-code-agent-type` (built-in names such as `Explore`, `Plan`, `general-purpose`, or `custom`, `teammate`, `fork`; "A user-chosen agent name is never sent"), `x-claude-code-prompt-id` (v2.1.283+), `x-claude-code-compaction`, `x-claude-code-prev-tool-durations` — [gateway compatibility guide → Request headers](https://code.claude.com/docs/en/llm-gateway-protocol#request-headers)
- CCR's tag mechanism (see Q2) is the only gateway-side per-subagent feature I found, and CCR explicitly says the agent-id header is "for observation only" — [CCR: routing](https://ccrdesk.top/routing/)
- Provider-side name mapping: DeepSeek maps `claude-opus*` → `deepseek-v4-pro` and `claude-sonnet*`/`claude-haiku*` → `deepseek-flash` server-side, so even unmodified alias names route to two different models — [DeepSeek Anthropic API guide](https://api-docs.deepseek.com/guides/anthropic_api)
- Background tasks: behind an Anthropic-format gateway, side requests use "The main model, or the default Haiku model when `ANTHROPIC_API_KEY` or `apiKeyHelper` supplies an Anthropic Console key and `ANTHROPIC_AUTH_TOKEN` is unset" — [gateway compatibility guide](https://code.claude.com/docs/en/llm-gateway-protocol)

### Inferences
- For a plugin wanting "cheap for docs, mid for tests, strong for implementation/review", the lowest-friction design is **(a) model strings**: give each role's subagent definition a `model:` that is either an alias tier (so the consumer remaps the tier once via `ANTHROPIC_DEFAULT_*_MODEL`) or a gateway-qualified ID (`openai/gpt-6-luna`, `deepseek-flash`), and let the single gateway fan out. This needs no gateway-specific feature beyond name-based routing, which every gateway in Q2 has.
- The alias route gives exactly four provider slots (fable/opus/sonnet/haiku) that the orchestrator can also choose dynamically at Agent-call time; arbitrary strings give unlimited slots but only statically, in definitions (the Agent tool's `model` parameter cannot carry them).
- **(c) is the strongest plugin-owned option**: an `agent.spawn` hook can map agent name/type → model string inside the plugin, overriding even the per-invocation parameter, with no gateway cooperation; `turn.step` could in principle swap models per request (e.g. compaction on a cheap model). I did not find documentation of whether the hook's `model` may be an arbitrary gateway alias rather than an alias/known ID; given `--model` is not validated, it is likely but unverified.
- Gateway routing by `x-claude-code-agent-type` can separate built-in `Explore`/`Plan` from `custom` agents and separate `compaction`/`auxiliary` traffic, but cannot tell two custom agents apart; the model string remains the only per-custom-agent discriminator on the wire (other than CCR's tag).
- I found no mechanism for two base URLs in one session, and no provider or gateway claims one; treat the single-destination constraint as confirmed by absence as well as by the docs' wording.

### Gaps
- Whether `agent.spawn` / `turn.step` accept gateway aliases that Claude Code does not recognize is undocumented.
- No published example combines hint headers with a gateway rule; the capability is documented on both sides (headers emitted; Bifrost/CCR rules read headers) but not demonstrated end to end.

## Q4. Native cloud providers: exact variable names, model-ID formats, and the remap pattern

### Takeaway
`CLAUDE_CODE_USE_BEDROCK`, `CLAUDE_CODE_USE_VERTEX`, and `CLAUDE_CODE_USE_FOUNDRY` are confirmed, with two newer siblings (`CLAUDE_CODE_USE_ANTHROPIC_AWS` for Claude Platform on AWS and `CLAUDE_CODE_USE_MANTLE`). All are Claude-only; model IDs are provider-form strings pinned through the same `ANTHROPIC_DEFAULT_*_MODEL` variables or a `modelOverrides` map.

### Cited Findings
- Deployment options: Anthropic Console, Amazon Bedrock, Claude Platform on AWS, Google Cloud's Agent Platform (formerly Vertex AI; variables keep `VERTEX`), Microsoft Foundry; gateway variables `ANTHROPIC_BASE_URL`, `ANTHROPIC_BEDROCK_BASE_URL`, `ANTHROPIC_AWS_BASE_URL`, `ANTHROPIC_VERTEX_BASE_URL`, `ANTHROPIC_FOUNDRY_BASE_URL`; "Pin model versions for cloud providers" using `ANTHROPIC_DEFAULT_FABLE_MODEL`, `ANTHROPIC_DEFAULT_OPUS_MODEL`, `ANTHROPIC_DEFAULT_SONNET_MODEL`, and `ANTHROPIC_DEFAULT_HAIKU_MODEL` — [Enterprise deployment overview](https://code.claude.com/docs/en/third-party-integrations)
- Gateway blocks: Bedrock `ANTHROPIC_BEDROCK_BASE_URL` + `CLAUDE_CODE_SKIP_BEDROCK_AUTH=1` + `CLAUDE_CODE_USE_BEDROCK=1`; Vertex `ANTHROPIC_VERTEX_BASE_URL` + `ANTHROPIC_VERTEX_PROJECT_ID` + `CLAUDE_CODE_SKIP_VERTEX_AUTH=1` + `CLAUDE_CODE_USE_VERTEX=1` + `CLOUD_ML_REGION`; Foundry `ANTHROPIC_FOUNDRY_BASE_URL` + `ANTHROPIC_FOUNDRY_API_KEY` (or `ANTHROPIC_FOUNDRY_AUTH_TOKEN`, v2.1.203+) + `CLAUDE_CODE_USE_FOUNDRY=1` (+ `CLAUDE_CODE_SKIP_FOUNDRY_AUTH=1`); Claude Platform on AWS `ANTHROPIC_AWS_BASE_URL` + `ANTHROPIC_AWS_WORKSPACE_ID` + `CLAUDE_CODE_SKIP_ANTHROPIC_AWS_AUTH=1` + `CLAUDE_CODE_USE_ANTHROPIC_AWS=1` — [Connect Claude Code to an LLM gateway](https://code.claude.com/docs/en/llm-gateway-connect)
- Model-ID formats: "Amazon Bedrock: inference profile ARNs. Model IDs that start with `anthropic.` are Mantle model IDs… Microsoft Foundry: deployment names. Google Cloud's Agent Platform: version names"; pin examples `ANTHROPIC_DEFAULT_OPUS_MODEL='us.anthropic.claude-opus-4-8'` (Bedrock) and `'claude-opus-4-8'` (Agent Platform / Foundry); alias resolution differs per provider (Anthropic API: Opus 5.5 / Sonnet 5.5 / Haiku 5.5; Bedrock and Agent Platform: Opus 5.5 / Sonnet 4.5 / Haiku 4.5; Foundry: Opus 4.6 / Sonnet 4.5 / Haiku 4.5) — [Model configuration](https://code.claude.com/docs/en/model-config)
- `modelOverrides` maps Anthropic model IDs to provider strings (ARNs, deployment names) and "Claude Code passes values that are already provider-native … to the provider as-is"; `ANTHROPIC_DEFAULT_*_MODEL_SUPPORTED_CAPABILITIES` (`effort`, `xhigh_effort`, `max_effort`, `thinking`, `adaptive_thinking`, `interleaved_thinking`) declares what a pinned ID supports, but "They have no effect behind an `ANTHROPIC_BASE_URL` gateway" — [Model configuration](https://code.claude.com/docs/en/model-config); [gateway compatibility guide](https://code.claude.com/docs/en/llm-gateway-protocol)
- On the Bedrock/Vertex formats Claude Code "sends only the subset of its full capability set that those providers accept"; on the Anthropic Messages format it "sends the full set, even if your gateway forwards to an Amazon Bedrock or Google Cloud's Agent Platform upstream" — [gateway compatibility guide → Format mismatch](https://code.claude.com/docs/en/llm-gateway-protocol)
- Authentication precedence puts cloud-provider credentials first "when `CLAUDE_CODE_USE_BEDROCK`, `CLAUDE_CODE_USE_VERTEX`, or `CLAUDE_CODE_USE_FOUNDRY` is set", then `ANTHROPIC_AUTH_TOKEN`, then `ANTHROPIC_API_KEY`, then `apiKeyHelper`, then `CLAUDE_CODE_OAUTH_TOKEN`, then profiles, then subscription OAuth — [Authentication](https://code.claude.com/docs/en/authentication)

### Inferences
- The `ANTHROPIC_DEFAULT_*_MODEL` remap is the same vocabulary for cloud providers and for third-party endpoints, so a plugin's config surface can be identical across both; only the capability-declaration variables differ (they are honored under `CLAUDE_CODE_USE_*` and ignored behind `ANTHROPIC_BASE_URL`).

### Gaps
- None material for the plugin design; the cloud pages themselves (`amazon-bedrock`, `google-vertex-ai`, `microsoft-foundry`) were not fetched because the gateway and model-config pages carried the variable names.

## Q5. Fidelity problems when a non-Claude model is driven through the Messages API / tool-use protocol

### Takeaway
Anthropic's own compatibility guide enumerates the failure modes (adaptive-thinking 400s, `context_management` and beta tool-field 400s, `role: "system"` mid-conversation entries, silently lost prompt caching, assumed 200K windows), and the gateway/provider issue trackers show the recurring one in practice is **reasoning-state round-tripping on tool calls** (DeepSeek `reasoning_content`, Gemini `thought_signature`), which stayed open in CCR for months. Prompt caching is the main cost-side loss: it is silent, and several non-Anthropic paths drop or ignore `cache_control`.

### Cited Findings

**Anthropic's documented breakage list** ([gateway compatibility guide → Feature pass-through](https://code.claude.com/docs/en/llm-gateway-protocol#feature-pass-through)):
- Adaptive reasoning: "Claude Code sends `thinking: {"type": "adaptive"}` for Claude Opus 4.6, … and later models, and **treats model names it doesn't recognize, such as gateway aliases, as current models that receive the field**"; symptom "`400` naming the `thinking` field or the `adaptive` tag"
- Context management: `context_management` body field + beta header → "`400` with `Extra inputs are not permitted`"; v2.1.304+ retries without the pair
- Beta tool fields `strict` and `defer_loading` → 400 naming the field; fix `CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS=1`
- `output_config` (effort, structured outputs, task budget) → 400 on Bedrock/Vertex-style upstreams
- Mid-conversation `role: "system"` entries are sent "for Claude Opus 4.8, models released after it, **and unrecognized model IDs**" → "`400` such as `Unexpected role "system"`"; Claude Code retries once without them
- Prompt caching: "No error: the conversation bills as uncached input on every turn, visible as high `input_tokens` with little or no cache activity in `usage`"
- Thinking signatures: on a 400 saying a block is "`bound to a different conversation`", Claude Code strips earlier thinking blocks and retries
- Token counting falls back to a character estimate when `count_tokens` is absent
- Most retry logic "matches on the upstream's error wording, so forward error response bodies unmodified"
- Unrecognized IDs: "Claude Code assumes 200K, or 1M when the ID carries `[1m]`"; a gateway that rewrites context-limit errors defeats auto-compaction; `CLAUDE_CODE_AUTO_COMPACT_WINDOW` clamps to ≥100,000 — [Connect … → Troubleshoot](https://code.claude.com/docs/en/llm-gateway-connect#troubleshoot-gateway-errors); [Model configuration → Correct the window](https://code.claude.com/docs/en/model-config#correct-the-window-for-a-gateway-or-custom-model-id)
- Version-specific schema breakage: Artifact tool regex with `\p{…}` on v2.1.265–2.1.267 rejected by gateways validating `pattern`; advisor tool type `advisor_20260301` on v2.1.275 rejected by upstreams validating tool types — [Connect … → Troubleshoot](https://code.claude.com/docs/en/llm-gateway-connect#troubleshoot-gateway-errors)
- System-prompt attribution block: stripped only by `api.anthropic.com`; stable per conversation behind a custom base URL since v2.1.181 (before that it changed per request and broke gateway-side caches) — [gateway compatibility guide → Attribution block](https://code.claude.com/docs/en/llm-gateway-protocol#system-prompt-attribution-block)

**Reasoning round-trip failures on tool calls**
- CCR #1378 (opened 2026-05-05, still open at last comment 2026-08-17): DeepSeek V4 Pro/Flash in thinking mode with tool calls returns 400 "The `reasoning_content` in the thinking mode must be passed back to the API" (Anthropic-endpoint variant: "The `content[].thinking` in the thinking mode must be passed back to the API"); no merged fix; community transformers as workarounds — [musistudio/claude-code-router#1378](https://github.com/musistudio/claude-code-router/issues/1378)
- CCR #1057 (opened 2025-12-07, open): Gemini 3 via OpenRouter returns 400 "function call `default_api:TodoWrite` … is missing a `thought_signature`" because CCR drops `reasoning_details` on both response and request paths; workaround is to not route tool-heavy paths to Gemini 3 — [musistudio/claude-code-router#1057](https://github.com/musistudio/claude-code-router/issues/1057) (stale?)
- CCR #1041 (2025-12-01): "API Error 400: Missing `reasoning_content` field when using DeepSeek Reasoner/V3.2 models"; CCR #1238 (2026-02-27): OpenRouter models with mandatory reasoning reject `reasoning:{enabled:false}` — [#1041](https://github.com/musistudio/claude-code-router/issues/1041); [#1238](https://github.com/musistudio/claude-code-router/issues/1238) (both stale?)
- LiteLLM #14194 (2025-09-03): Bedrock thinking model with tools fails "Expected `thinking` or `redacted_thinking`, but found `tool_use`" — [BerriAI/litellm#14194](https://github.com/BerriAI/litellm/issues/14194) (stale?)

**Tool-call translation failures**
- LiteLLM #32214 (2026-07-06): "`sanitize_tool_use_ids_in_anthropic_messages` breaks multi-turn tool-use on vLLM/Kimi K2.7 pass-through (v1.91.0 regression)" — [BerriAI/litellm#32214](https://github.com/BerriAI/litellm/issues/32214)
- LiteLLM #36540 (2026-08-11): "Anthropic /v1/messages → Responses API transform drops `tool_result` blocks containing `tool_reference`" — [BerriAI/litellm#36540](https://github.com/BerriAI/litellm/issues/36540)
- LiteLLM #38223 (2026-08-25): "Gemini/Vertex rejects tool results containing JSON Schema `$ref`/`$defs`" — [BerriAI/litellm#38223](https://github.com/BerriAI/litellm/issues/38223)
- LiteLLM #30043 (2026-06-09): "No stable LiteLLM path for Claude Code → vLLM" — [BerriAI/litellm#30043](https://github.com/BerriAI/litellm/issues/30043)
- Bifrost docs: "OpenRouter was reported to stream empty function-call arguments" — [Bifrost: Claude Code](https://docs.getbifrost.ai/cli-agents/claude-code.md)
- Ollama #14493 (2026-02-27): "Qwen 3.5 27B: Tool calling completely non-functional" (local model-template issue, not Claude Code specific) — [ollama/ollama#14493](https://github.com/ollama/ollama/issues/14493) (stale?)
- Kong's guide strips `output_config`, `context_management`, `mcp_servers`, `container`, `service_tier`, `reasoning_effort` and the `anthropic-beta` header for Gemini, and warns new fields appear with Claude Code versions — [Kong guide](https://developer.konghq.com/ai-gateway/use-claude-code-with-ai-gateway-gemini/)

**Prompt caching loss (cost side)**
- DeepSeek ignores `cache_control` but caches automatically and reports `cache_read_input_tokens` — [DeepSeek Anthropic API guide](https://api-docs.deepseek.com/guides/anthropic_api)
- Ollama's Anthropic-compatible API lists prompt caching as unsupported — [Ollama: Anthropic compatibility](https://docs.ollama.com/api/anthropic-compatibility); Ollama Cloud users reported zero cache metrics across endpoints ("we're paying 10 times more than necessary"; a 50,000-token repeated prompt showing no cache usage on three endpoints, Sept 7, 2026) until the issue closed 2026-09-15 with "Cloud now reports cache metrics"; a sibling issue #17130 concerns `cache_control` being dropped — [ollama/ollama#16714](https://github.com/ollama/ollama/issues/16714)
- LiteLLM injects `cache_control` automatically only for `anthropic/` routes — [LiteLLM prompt caching](https://litellm.docs.miniasp.com/en/docs/tutorials/prompt_caching) (mirror); a v1.91.0/1.91.1 regression "quietly stopped caching for Claude Code sessions routed through Amazon Bedrock's Invoke API" — [LiteLLM incident report](https://docs.litellm.ai/blog/tags/claude-code)
- Vercel passes `cache_control` only to Anthropic-family providers; others rely on implicit caching — [Vercel AI Gateway](https://vercel.com/docs/ai-gateway/sdks-and-apis/anthropic-messages-api)
- Magnitude (Claude, secondary, unverified): one tracker claims a 170-turn Opus session would cost $168 uncached versus $21 cached — [claudecodecamp: prompt caching](https://www.claudecodecamp.com/p/how-prompt-caching-actually-works-in-claude-code)
- A real non-Claude session reached a 72% cache rate (GLM-5.2 via OpenRouter) — [Lenny's Newsletter, Jun 29 2026](https://www.lennysnewsletter.com/p/how-i-ai-glm-52-review-and-how-gusto)

**Context window / `[1m]`**
- Provider guides either append `[1m]` (DeepSeek, Kimi, MiniMax) or set `CLAUDE_CODE_MAX_CONTEXT_TOKENS=1000000` (Qwen) and raise `CLAUDE_CODE_AUTO_COMPACT_WINDOW` (786432 / 1000000 / 524288) — see Q1 sources
- Local Ollama fails with context-overflow errors unless the model is run with a larger context (e.g. 65536) — [The Agentic Review, Jun 2 2026](https://theagenticreview.substack.com/p/how-to-run-claude-code-against-kimi)

**Images, thinking controls, server-side tools, auth**
- Images: DeepSeek V4-Pro replaces image blocks with "[Unsupported Image]"; Ollama rejects URL images — Q1 sources
- Kimi `kimi-k2.7-code` returns 400 if thinking is off; MiniMax M3.1-Flash thinking cannot be disabled — Q1 sources
- Hosted web search: supported by DeepSeek's endpoint (`server_tool_use`), "not fully supported" on Ollama Cloud; an HN commenter: "search tool does not work" with local models — [Ollama compat](https://docs.ollama.com/api/anthropic-compatibility); [HN thread](https://news.ycombinator.com/item?id=47986970)
- Fast mode, Remote Control, voice dictation, claude.ai connectors and `/schedule` are unavailable or degraded behind a gateway credential or non-Anthropic base URL — [Connect Claude Code to an LLM gateway](https://code.claude.com/docs/en/llm-gateway-connect)
- Rate limits: Ollama Cloud "Frequent 503 errors" (#15419, 2026-04-08) and "95% failure rate across all cloud models" (#15453, 2026-04-09) — [ollama/ollama#15419](https://github.com/ollama/ollama/issues/15419); [#15453](https://github.com/ollama/ollama/issues/15453) (stale?)

### Inferences
- The recurring structural defect is that Claude Code's agentic loop round-trips assistant `thinking` blocks and tool-use IDs verbatim; any translation layer that does not preserve provider-specific reasoning state (`reasoning_content`, `thought_signature`, `reasoning_details`) breaks on the *second* tool turn, which is why these bugs surface only in agentic use and persist.
- Because an unrecognized model ID is treated as a *current Claude* model (adaptive thinking, system-role messages, effort), a non-Claude backend sees the most demanding request shape; `CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS=1` removes some but not all of it (adaptive `thinking` and `role: "system"` entries stay).
- Cost impact of losing caching scales with turn count, not tokens per turn; agentic sessions are the worst case. No source quantifies it for a non-Claude backend under Claude Code specifically.

### Gaps
- I found no report on system-prompt length limits for non-Claude backends.
- No independent, dated measurement of tool-call success rate per non-Claude model under the Claude Code harness exists in what I found.

## Q6. Terms of service and legal posture

### Takeaway
Anthropic's Claude Code legal page restricts *credentials* (subscription OAuth is for Claude Code and native Anthropic apps; API keys for developers), not *backends*. Nothing I found prohibits pointing the unmodified Claude Code client at a third-party endpoint with that provider's credential; Anthropic's gateway page frames non-Claude routing as unsupported rather than forbidden. The separate third-party-client crackdown ran January–April 2026 (not 2025) and targeted subscription OAuth use in other clients.

### Cited Findings
- License: "Your use of Claude Code is subject to: Commercial Terms of Service — for Team, Enterprise, and Claude API users; Consumer Terms of Service — for Free, Pro, Max, and Ultra users." — [Legal and compliance](https://code.claude.com/docs/en/legal-and-compliance)
- "Whether you're using the Claude API directly (1P) or accessing it through Amazon Bedrock or Google Cloud's Agent Platform (3P), your existing commercial agreement will apply to Claude Code usage, unless we've mutually agreed otherwise." — [Legal and compliance](https://code.claude.com/docs/en/legal-and-compliance)
- Credential rules: "OAuth authentication is intended exclusively for purchasers of Claude Free, Pro, Max, Ultra, Team, and Enterprise subscription plans and is designed to support ordinary use of Claude Code and other native Anthropic applications." "Anthropic does not permit third-party developers to offer Claude.ai login into their own applications, or to route requests through Free, Pro, Max, or Ultra plan credentials on behalf of their users." "This does not restrict how customers provision and manage their own API keys or third-party inference provider credentials … provided the resulting usage is billed to the key owner under their agreement with Anthropic (or the applicable provider)." "Anthropic reserves the right to take measures to enforce these restrictions and may do so without prior notice." — [Legal and compliance](https://code.claude.com/docs/en/legal-and-compliance)
- For hosting Claude Code in a product: "The Claude Code binary must not be modified" and "Each end user must authenticate with their own Anthropic API key, Claude subscription plan credentials, or 3P inference provider credential (Amazon Bedrock, Google Cloud's Agent Platform, Microsoft Foundry)" — [Legal and compliance](https://code.claude.com/docs/en/legal-and-compliance)
- Support posture: "Anthropic … doesn't support routing Claude Code to non-Claude models through any gateway" — [Other LLM gateways](https://code.claude.com/docs/en/llm-gateway)
- Subscription traffic through a gateway: setting only `ANTHROPIC_BASE_URL` keeps the claude.ai login active and the gateway "must forward the OAuth capability in `anthropic-beta`"; a gateway credential variable replaces the subscription and bills per token to the credential owner — [Other LLM gateways → Subscriptions and gateways](https://code.claude.com/docs/en/llm-gateway)
- HIPAA: "Claude Code routed through a third-party cloud provider or a gateway aren't covered" under the HIPAA configuration — [Legal and compliance](https://code.claude.com/docs/en/legal-and-compliance)
- Third-party client crackdown timeline (secondary press, all > 6 months old, stale?): server-side block of subscription OAuth outside Claude Code around Jan 9, 2026; doc update Feb 19, 2026 stating Free/Pro/Max tokens cannot be used in third-party tools or the Agent SDK; legal demand to OpenCode in March 2026, which removed Anthropic OAuth; subscriptions stopped covering third-party tools from April 4, 2026 — [VentureBeat](https://venturebeat.com/ai/anthropic-cracks-down-on-unauthorized-claude-usage-by-third-party-harnesses/); [Winbuzzer, Feb 19 2026](https://winbuzzer.com/2026/02/19/anthropic-bans-claude-subscription-oauth-in-third-party-apps-xcxwbn/); [falcao.org](https://falcao.org/posts/anthropic-claude-access-crackdown-ecosystem-fallout/); [implicator.ai](https://www.implicator.ai/anthropic-cuts-openclaw-from-claude-subscriptions-citing-unsustainable-compute-costs/)
- Provider side: OpenRouter's guide says non-Anthropic providers "may not work correctly"; Bifrost's docs repeat "Anthropic does not support routing Claude Code to non-Claude models" — Q1/Q2 sources
- Data note: a Cloudflare community page says claude.ai web traffic cannot be routed through AI Gateway — [claudepluginhub: Cloudflare AI Gateway skill](https://www.claudepluginhub.com/skills/nsheaps-cloudflare-plugins-cloudflare/ai-gateway) (secondary)

### Inferences
- The relevant legal distinction is: (1) subscription OAuth in a non-Anthropic client → prohibited and technically blocked; (2) unmodified Claude Code + your own third-party credential + a non-Anthropic backend → not addressed by any prohibition I found, explicitly unsupported, and outside HIPAA/BAA coverage. A plugin that only writes env vars does not modify the binary.
- I found no explicit statement from Anthropic that says using the Claude Code client against third-party backends is permitted either; the legal page's "third-party inference provider credential" examples name only Bedrock, Agent Platform, and Foundry.

### Gaps
- The Consumer/Commercial Terms themselves were not fetched; the Claude Code legal page is the primary source used. If the brief needs the terms' own wording on client use, that remains to be read.

## Q7. Pricing snapshot (USD per 1M tokens; input / cached input / output; context)

### Takeaway
As of 2026-10-31 the cheap tier is DeepSeek Flash, GLM-5.3-Flash, MiniMax-M3.1-Flash, Qwen-Flash, and GPT-6-Luna (all ≤ $0.20 input, ≤ $0.60 output); mid tier is Qwen-Plus, GLM-5.3, DeepSeek V4-Pro, GPT-6.1-Terra, Grok 4.3; strong non-Claude tier is GPT-6.1-Sol / GPT-5.5, Gemini 3.1 Pro / Gemini 4 Argon, Kimi K3, Qwen 3.8-Max. OpenRouter adds no inference markup but takes 5.5% on credit purchases.

### Cited Findings

**OpenAI** — [developers.openai.com pricing](https://developers.openai.com/api/docs/pricing) (no page date; short context ≤ 272K, long context higher)
- gpt-6-astra $10.00 / $1.00 / $50.00; gpt-6.1-sol $2.00 / $0.10 / $10.00; gpt-6.1-terra $1.00 / $0.05 / $5.00; gpt-6-sol $2.00 / $0.20 / $10.00; gpt-6-luna $0.10 / $0.01 / $0.50
- gpt-5.6-sol $4.00 / $0.40 / $20.00 (promo "at least through November 21, 2026"); gpt-5.6-terra $2.00 / $0.20 / $12.00; gpt-5.6-luna $0.20 / $0.02 / $1.20; gpt-5.5 $5.00 / $0.50 / $30.00 (long context $10 / $45); gpt-5.4 $2.50 / $0.25 / $15.00; gpt-5.4-mini $0.75 / $0.075 / $4.50; gpt-5.4-nano $0.20 / $0.02 / $1.25; gpt-5 $1.25 / $0.125 / $10.00; gpt-5-mini $0.25 / $0.025 / $2.00; gpt-5-nano $0.05 / $0.005 / $0.40; gpt-5.3-codex $1.75 / $0.175 / $14.00; gpt-4o-mini $0.15 / $0.075 / $0.60
- Context windows are not on the pricing page (gap)

**DeepSeek** — [DeepSeek pricing](https://api-docs.deepseek.com/quick_start/pricing) (no date; off-peak = half of peak; peak = 01:00–04:00 and 06:00–10:00 UTC Mon–Fri excluding Chinese holidays)
- deepseek-flash (V4.1-Flash-1017): cache miss $0.30 peak / $0.15 off-peak; cache hit $0.006 / $0.003; output $1.20 / $0.60; 1M context; 384K max output
- deepseek-v4-pro (V4-Pro-0813): cache miss $1.32 / $0.66; cache hit $0.044 / $0.022; output $3.96 / $1.98; 1M context
- Legacy `deepseek-v4-flash` names still accepted but served by Flash; V3.x / R1 no longer listed; web search/fetch free "through DeepSeek Harness, Claude Code, and Codex" until per-request billing starts 2026-11-01 00:00 Beijing

**Alibaba Qwen (Singapore / international)** — official per-model pages, last updated Oct 11, 2026
- qwen-plus (1M context): $0.40 / $0.08 implicit-cache ($0.04 explicit read) / $1.20 for ≤256K input; $1.20 / $0.24 / $3.60 for 256K–1M; thinking-mode output $4.00 (≤256K) — [qwen-plus](https://www.alibabacloud.com/help/en/model-studio/qwen-plus)
- qwen-flash (1M context): $0.05 / $0.01 / $0.40 ≤256K; $0.25 / $0.05 / $2.00 256K–1M — [qwen-flash](https://www.alibabacloud.com/help/en/model-studio/qwen-flash)
- qwen-max (legacy, 32K): $1.60 / $0.32 / $6.40 — [qwen-max](https://www.alibabacloud.com/help/en/model-studio/qwen-max)
- qwen3.8-max: official page not found (404); aggregators converge on $2.00 / $0.25 cached / $6.00, 1M context, "a cut from the $2.50/$7.50 the preview generation charged" — [anotherwrapper](https://anotherwrapper.com/llm-pricing/qwen3.8-max); [cloudprice](https://cloudprice.net/models/Qwen/Qwen3.8-Max) (secondary, unverified)
- qwen3.7-plus: aggregators disagree ($0.32 / $1.28 vs list $0.40 / $1.60) — [requesty](https://www.requesty.ai/models/compare/alibaba--qwen3.7-plus/alibaba--qwen3.8-max) (secondary, unverified)

**xAI** — [xAI models](https://docs.x.ai/docs/models) (no date; "≥200k" rows apply at 200K prompt tokens)
- grok-4.7: $2.00 / $0.50 / $6.00 (<200k), $4.00 / $1.00 / $12.00 (≥200k); 500K context; knowledge cutoff May 2026
- grok-4.6: same as 4.7; grok-4.5: $2.00 / $0.30 / $6.00; grok-4.3: $1.25 / $0.20 / $2.50 (1M); grok-4.20-0309 (reasoning / non-reasoning / multi-agent): $1.25 / $0.20 / $2.50 (1M); grok-build-0.1: $1.00 / $0.20 / $2.00 (256K)
- grok-4, grok-4-fast, grok-code-fast-1 are no longer listed

**Moonshot Kimi** — official tables did not render in two fetch attempts ([pricing page](https://platform.kimi.ai/docs/pricing/chat); [help page](https://www.kimi.ai/help/kimi-api/api-pricing)); the pages do state kimi-k3 and kimi-k3.1-pro have a 1,048,576-token context, batch at 60% of standard, cache writes billed by TTL, and the K2 retirement dates above
- kimi-k3 aggregator consensus: $3.00 / $0.30 cache hit / $15.00; one aggregator lists $2.50 / $14.00 (third-party provider pricing) — [eesel](https://www.eesel.ai/blog/kimi-k3-pricing); [anotherwrapper](https://anotherwrapper.com/llm-pricing/kimi-k3); [pricepertoken](https://pricepertoken.com/pricing-page/model/moonshotai-kimi-k3) (secondary, unverified)
- kimi-k2.6: $0.60 / $3.00 per the Agentic Review walkthrough — [The Agentic Review, Jun 2 2026](https://theagenticreview.substack.com/p/how-to-run-claude-code-against-kimi) (secondary)

**Z.ai GLM** — [Z.ai pricing](https://docs.z.ai/guides/overview/pricing) (no date; cached-input storage "Limited-time Free")
- GLM-5.3 $1.40 / $0.26 / $4.40; GLM-5.3-Flash $0.15 / $0.03 / $0.50; GLM-5.3-FlashX $0.37 / $0.075 / $1.25; GLM-5.2 and GLM-5.1 $1.40 / $0.26 / $4.40; GLM-5 $1.00 / $0.20 / $3.20; GLM-4.7 and GLM-4.6 $0.60 / $0.11 / $2.20; GLM-4.7-FlashX $0.07 / $0.01 / $0.40; GLM-4.5-Air $0.20 / $0.03 / $1.10; GLM-4.7-Flash and GLM-4.5-Flash free; context windows not stated
- Coding Plan: Lite from $18/month (official); Pro/Max monthly list price conflicts between secondary sources ($72 / $160 captured from z.ai/subscribe in July 2026 vs $80 / $168 elsewhere) — [usagepricing capture](https://www.usagepricing.com/blueprint/activity/zhipu-ai-2026-07-22-glm-coding-plan-reprice); [Novita](https://blogs.novita.ai/z-ai-coding-plan-pricing/) (secondary)

**MiniMax** — [MiniMax pricing](https://platform.minimax.io/docs/pricing)
- MiniMax-M3.1-Flash $0.15 / $0.015 / $0.60; MiniMax-M3 ≤512K $0.30 / $0.06 / $1.20 ("Permanent 50% off" from $0.60 / $0.12 / $2.40), >512K $0.60 / $0.12 / $2.40; Priority tier 1.5×; context not stated on the page (1M per secondary sources); M3.1-Flash launched 2026-10-19 — [techenclave](https://techenclave.com/news/items/minimax-releases-m3-1-flash-at-us-0-15-input-and-us-0-60-output-per-million-tokens) (secondary)

**Google Gemini (Developer API, Standard tier)** — [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing) (page updated 2026-10-30)
- Gemini 4 Argon $2.00 / $0.10 / $10.00, rising to $4.00 / $0.20 / $20.00 on Dec 1, 2026 (not on Free tier)
- Gemini 3.8 Flash and 3.6 Flash $0.75 / $0.075 / $3.75, rising to $1.50 / $0.15 / $7.50 on Jan 1, 2027
- Gemini 3.1 Pro Preview $2.00 / $0.20 / $12.00 (≤200K), $4.00 / $0.40 / $18.00 (>200K); Gemini 3.5 Flash-Lite $0.30 / $0.03 / $2.50; Gemini 3.1 Flash-Lite $0.25 / $0.025 / $1.50; Gemini 3 Flash Preview $0.50 / $0.05 / $3.00
- Gemini 2.5 Pro $1.25 / $0.125 / $10.00 (≤200K), $2.50 / $0.25 / $15.00 (>200K); 2.5 Flash $0.30 / $0.03 / $2.50 (1M); 2.5 Flash-Lite $0.10 / $0.01 / $0.40; context windows otherwise not on the pricing page

**OpenRouter markup** — [OpenRouter pricing](https://openrouter.ai/pricing)
- Platform fee on credit purchases: 5.5% Standard, 8% Business; "Inference is billed at the provider's list price on every plan"; BYOK free for the first $25,000/month of list-price inference, then 5%; secondary sources add a $0.80 minimum per non-crypto purchase and 5.0% flat for crypto — [apicostcalc](https://apicostcalc.com/blog/openrouter-credit-fee-is-5-5-not-5-percent.html) (secondary)

**Vercel AI Gateway markup** — not stated on the page fetched (gap)

### Inferences
- With cached-input rates at 5–10% of input on most providers, the cost ranking of "cheap model, no cache" versus "mid model, cached" can invert for long agentic sessions; the Q5 caching findings matter more than the headline rates for a loop that runs many turns.

### Gaps
- Primary-source prices for Kimi K3 and Qwen 3.8-max/3.7-plus could not be read (client-rendered tables / 404); figures above are aggregator consensus and should be re-checked before use.
- Context windows for OpenAI and most Gemini models are not on the pricing pages.

## Q8. Evidence of cost or quality outcomes from mixed-provider Claude Code setups

### Takeaway
First-hand reports are few and anecdotal: a documented GLM-5.2-via-OpenRouter session ran a 45-minute autonomous MCP-driven bug hunt for $3.36 (72% cache rate) but struggled with TypeScript compilation; a Kimi K2.6 hybrid setup claims 60–80% savings with "genuinely close" quality for routine work and Opus still better for novel multi-file reasoning; a small HN thread splits between "surprisingly easy" and "does not work very well. CC really needs the Anthropic model special sauce." No independent benchmark of the Claude Code harness driving non-Claude models exists in what I found.

### Cited Findings
- GLM-5.2 in Claude Code via OpenRouter (episode published Jun 29, 2026): "$3.36 for about 6 million tokens, including the full 45-minute session"; "A 72% cache rate helped"; the task pulled 72 hours of Sentry/Vercel logs through MCP tool calls and produced 14 planned fixes including two P0s; weaknesses: "struggled with TypeScript compilation errors before producing clean React output"; recommendation "put GLM-5.2 in rotation, not in the spotlight" — [Lenny's Newsletter: How I AI](https://www.lennysnewsletter.com/p/how-i-ai-glm-52-review-and-how-gusto)
- Kimi K2.6 and local Qwen via Ollama (Jun 2, 2026): Kimi "Tool calls, file edits, and terminal commands work the same way"; Kimi session ≈ $0.40–0.80 vs $4–6 on Opus; hybrid day ≈ $7–13 vs $30–50 all-Opus (author's claim of 60–80% savings); "Opus is described as still better for novel reasoning, complex multi-file debugging, and design-heavy problems"; local Qwen ~3 s on a 4090 vs ~30 s on an M2 Air; local context must be raised or Claude Code overflows; author's caveat that Anthropic does not officially support the setup — [The Agentic Review](https://theagenticreview.substack.com/p/how-to-run-claude-code-against-kimi)
- "Ask HN: Do people configure Claude Code to use other models" (≈6 months old, 6 comments): Tomte "A few environment variables and Claude Code uses DeepSeek. I was actually surprised how easy that is."; jonahbenton "it does not work very well. CC really needs the Anthropic model special sauce."; perrygeo "recent open weight models (Qwen, Gemini) are pretty solid on quality" but "roughly 10x slower on my M3 mac"; verdverm "search tool does not work" with local models; ilia-a finds a second model useful as a reviewer — [HN 47986970](https://news.ycombinator.com/item?id=47986970) (stale?)
- Other HN comments: a user reports Kimi-K2 on Moonshot "with no issues"; another says local/cheap routing "can be done … but IME it does not work very well" — [HN search results](https://news.ycombinator.com/item?id=45148478) (2025; stale?)
- Cost comparisons without harness data: DevTk.AI lists GLM-5.3-Flash at $0.15/$0.50 as the cheapest route vs Opus 5.5 at $4/$20; particula.tech and andrew.ooo put open models within 5–7 points of Opus 4.7 on SWE-Bench Pro at 5–15% of the cost (model-level benchmarks, not Claude Code harness results) — [DevTk.AI](https://devtk.ai/en/blog/ai-coding-agent-cost-comparison-2026/); [particula](https://particula.tech/blog/deepseek-v4-vs-kimi-k2-6-vs-glm-5-1-open-weight-coding); [andrew.ooo](https://andrew.ooo/answers/kimi-k2-6-vs-glm-5-1-vs-deepseek-v4-pro-may-2026/) (secondary)
- CCR issue threads are dominated by breakage reports rather than outcome data (Q5); the one positive thread, "I got the Router working with Gemini" (2025-11-20, 17 comments), predates the thought-signature regression — [musistudio/claude-code-router#1018](https://github.com/musistudio/claude-code-router/issues/1018) (stale?)

### Inferences
- The pattern across reports is consistent with the Q5 mechanics: setup is trivial, single-turn quality is fine, and the failures cluster in long agentic runs (compilation loops, tool-state round-trips, missing server-side tools). For a per-role design, that argues for keeping the strong model on the roles with the longest tool loops (implementation, review) and moving docs/test roles first.
- Cost claims of 8–10× are model-price arithmetic; realized savings depend on cache behavior (Q5) and on how many retries the weaker model needs, which no source measured.

### Gaps
- No controlled, dated comparison of task success or cost per completed task for Claude Code with mixed providers was found; the evidence is vendor content, two practitioner write-ups, and short forum threads.
