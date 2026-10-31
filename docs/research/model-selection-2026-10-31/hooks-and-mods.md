# Claude Code hooks and mods: observing, enforcing, or rewriting model and effort selection

Research date: 2026-10-31. Every web source below was fetched on that date. The installed CLI on this
machine is 2.1.314 (the mod type declarations it wrote are headed `// Written by Claude Code 2.1.314.`);
the public CHANGELOG's top entry is 2.1.316. The public mods reference states its entries cover "the
Claude Code CLI and the Desktop app as of v2.1.290, and the VS Code extension as of v2.1.299." Local
sources (the bundled `plugin-authoring` skill and the type declarations it ships) are labeled LOCAL;
everything else is PUBLIC. No files or settings outside the output path were modified; the
`plugin-authoring` skill was invoked read-only and nothing was written under `~/.claude/dev-mods/`.

Source abbreviations used in citations:

- HOOKS = https://code.claude.com/docs/en/hooks (284k chars, read in three chunks)
- HOOKS-GUIDE = https://code.claude.com/docs/en/hooks-guide
- STATUSLINE = https://code.claude.com/docs/en/statusline
- MANIFEST = https://code.claude.com/docs/en/plugins-reference (resolves to the "Plugin manifest reference")
- SUBAGENTS = https://code.claude.com/docs/en/sub-agents
- MODS-OVERVIEW = https://code.claude.com/docs/en/plugins/mods/overview.md
- MODS-CREATE = https://code.claude.com/docs/en/plugins/mods/create
- MODS-REF = https://code.claude.com/docs/en/plugins/mods/reference.md
- MODS-EVENTS = https://code.claude.com/docs/en/plugins/mods/events.md
- MODS-API = https://code.claude.com/docs/en/plugins/mods/api.md
- MODEL-CONFIG = https://code.claude.com/docs/en/model-config.md
- CHANGELOG = https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md (raw copy fetched 2026-10-31; entries carry version numbers, not dates)
- RELEASE-287 = https://github.com/anthropics/claude-code/releases/tag/v2.1.287
- LOCAL-SKILL = the `plugin-authoring` skill text as delivered by the Skill tool on 2026-10-31 (base directory `/tmp/claude-1000/bundled-skills/2.1.314/10daab6fa5ec61cbc098347a37651d3e/plugin-authoring/`; the directory is rewritten per session)
- LOCAL-REF = `/tmp/claude-1000/bundled-skills/2.1.314/10daab6fa5ec61cbc098347a37651d3e/plugin-authoring/reference.md` (276 lines)
- LOCAL-TYPES = `/tmp/claude-1000/bundled-skills/2.1.314/10daab6fa5ec61cbc098347a37651d3e/plugin-authoring/types/claude-code.d.ts` (22,846 lines)
- LOCAL-EXAMPLES = `/tmp/claude-1000/bundled-skills/2.1.314/10daab6fa5ec61cbc098347a37651d3e/plugin-authoring/examples/`

## Key question 1: What is a "mod" in Claude Code, what can it do, and how is it packaged and distributed?

### Takeaway

A mod is an ordinary Claude Code plugin whose `hooks/hooks.json` carries a `modules` key naming one
JavaScript/TypeScript ES module that exports `register(on, options)`; its handlers run inside the
Claude Code process as a middleware chain over engine events (tool calls, prompts, model requests,
subagent spawns, UI rendering). Mods shipped publicly in v2.1.287 (GitHub release dated "01 Oct", year
inferred 2026) and are "early access"; the local skill and the public docs agree on every structural
fact, with the public docs adding the organizational controls and the per-surface drawing table.

### Cited Findings

**Definition and packaging (PUBLIC)**

- "A mod is a plugin that changes how Claude Code looks and behaves. It's made of JavaScript or TypeScript event handlers: Claude Code calls one when an event happens, such as a tool call, a submitted prompt, or a part of the interface being drawn, and the handler can watch the event, change it, or take it over." — [MODS-OVERVIEW](https://code.claude.com/docs/en/plugins/mods/overview.md)
- Terminology: "Claude Code calls both kinds hooks: on these pages, 'hook' means a mod's handler, and the settings-file kind is a 'settings hook'." — [MODS-OVERVIEW](https://code.claude.com/docs/en/plugins/mods/overview.md)
- Files table: `.claude-plugin/plugin.json` (required; "Mods add no required fields"); `hooks/hooks.json` (required; "`modules`: an array with one path, relative to this file, to the hooks module, as in `"modules": ["./register.js"]`. Can also hold settings hooks under `hooks`."); the hooks module ("Exports `register(on, options)`. Named `.js`, `.mjs`, `.cjs`, `.jsx`, `.ts`, `.mts`, `.cts`, or `.tsx`. An ES module."); `types/index.d.ts` ("When the mod uses `$.state` or adds a namespace to the mods API"; omitting `types` from the manifest needs v2.1.299+); `*.test.ts` files for `claude plugin test`. — [MODS-REF](https://code.claude.com/docs/en/plugins/mods/reference.md)
- "The `modules` key in that file gives the path to your code, and having it is what makes the plugin a mod." — [MODS-CREATE](https://code.claude.com/docs/en/plugins/mods/create)
- "You don't need Node.js, a bundler, or a build step, because Claude Code loads `.js` and `.ts` files directly." — [MODS-CREATE](https://code.claude.com/docs/en/plugins/mods/create)
- The manifest reference lists a `types` field: "A `.d.ts` file that declares the `$.state` values and `$` nouns of a mod". — [MANIFEST](https://code.claude.com/docs/en/plugins-reference)
- Runtime: "The hooks module itself has no Node.js APIs, no timer globals such as `setTimeout`, and no network or file access of its own. Standard JavaScript and web APIs such as `URL`, `TextEncoder`, `AbortController`, and `crypto.subtle` are available." All outside access goes through the `$` mods API. — [MODS-API](https://code.claude.com/docs/en/plugins/mods/api.md)
- Hook shape: `on(eventName, matcher?, hook)`; every hook is `($, e, next)`; "`e`: The event's input, as deeply frozen plain data. To change it, pass a copy to `next`."; "`next(e)`: The next handler, as in middleware. Runs the hooks after this one, then Claude Code's behavior. Resolves to the event's result." `on` returns a registration with `.catch(handler)`. — [MODS-REF](https://code.claude.com/docs/en/plugins/mods/reference.md)
- Three things a hook can do: Observe (return `next(e)`), Rewrite (`next({ ...e, text })`), Answer (return a result without calling `next`, which short-circuits later mods and Claude Code's own behavior). — [MODS-EVENTS](https://code.claude.com/docs/en/plugins/mods/events.md)

**Definition and packaging (LOCAL)**

- The skill's trigger description: "Make a mod: a change to Claude's own interface or behaviour, such as a panel or pane that stays beside the chat and updates, a band, status line, toast, slash command, or hook on tool calls." — LOCAL-SKILL (as listed in the session's skill index)
- "Write each mod in its own child folder, `/home/fdpearce/.claude/dev-mods/e4a4629a-…/<mod-name>/`, three files written directly: `.claude-plugin/plugin.json` …; `hooks/hooks.json`: `{ "modules": ["./register.tsx"] }`, one path, relative to that file; `hooks/register.tsx` (or `.ts`): the hooks module, `export const register: Register = (on, options) => { ... }`, the type imported from `'claude-code'`." A fourth file, `types/index.d.ts`, declares `$.state` values under `interface PluginState`, named in `plugin.json` as `"types": "./types/index.d.ts"`. — LOCAL-SKILL
- "A mod is three files written directly: `claude plugin init` scaffolds another kind of plugin, one of command hooks under `~/.claude/skills`." — LOCAL-REF, "What a plugin of function hooks is"
- "The module has no DOM or Node: `$` reaches everything outside it. JSX compiles against the global `h`, and the elements come from the drawing surface's own table, `const { Box, Text, Button } = $.ui.resolve(e)`, where `e.surface` is `terminal`, `desktop`, `vscode` or `mobile`." — LOCAL-SKILL
- The type declaration header: "EARLY ACCESS: this surface may change between releases without notice. Written by the engine each time it loads a mod from a folder the person owns, beside that mod as `.claude-plugin/types/claude-code/index.d.ts`". — LOCAL-TYPES lines 1-12
- Hot-reload consent: "The first file written under it makes the engine ask the person, once, right then, while the turn goes on: 'Turn on the mods Claude writes in this session?' … That question is the switch, and the person alone answers it: no permission mode, rule or hook does." Declined mods "load the next time this session starts"; "off, with the reason (nobody could be asked, as under `claude -p`; the question got no pick three times; an organization's policy; an untrusted workspace)." — LOCAL-SKILL
- State across reloads: "A reload runs `register` and `session.start` again. `$.state` (the session's) and `$.store` (across sessions) stay; the module's own variables start over." — LOCAL-SKILL
- The example modules on disk: `tool-call.ts` (a `tool.call` guard on `Edit` that returns `{ deny }` for `.env` paths, with a `.catch` that fails closed; and a `Bash` hook that rewrites `command` via `next({ ...e, command: e.command.trim() })`), `pane.tsx` (a pane fed by `atom`/`update`), `band.tsx` (an `AbovePrompt` band with a `Button`). — LOCAL-EXAMPLES

**UI surfaces and state (both)**

- Local table: pane via `$.ui.open({ id, title })` + a `ui.render` hook on `{ component: 'Pane' }`; band via `ui.render` on `{ component: 'AbovePrompt' }`; status line entry via `$.ui.status(text)`; toast via `$.ui.toast(text)`; slash command via `$.command.register` + `command.run`; system prompt via `prompt.compose`; sound via `$.audio.play`. — LOCAL-SKILL
- Public render sites: `Pane`, `AbovePrompt`, `UserMessage`, `AssistantMessage`, `ToolUse`/`ToolResult`/`ToolGroup`, `CommandOutput`, `AskUserQuestion`, `ToolProgress`, `Spinner`, `TurnDuration`, `InfoNotice`, `SessionMode`, `PromptHint`; each row says which of Terminal/Desktop/VS Code renders it. — [MODS-REF](https://code.claude.com/docs/en/plugins/mods/reference.md)
- Public `$` namespaces: `$.plugin`, `$.ui`, `$.command`, `$.tool`, `$.agent` (`register`, `spawn`, `list`), `$.model` (`complete`, `fork`, `classify`), `$.prompt`, `$.turn`, `$.session` (incl. `model`, `usage`), `$.config`, `$.settings`, `$.env` (`get`, `set`), `$.fs`, `$.store`, `$.state`, `$.clock`, `$.http`, `$.process`, `$.mcp`, `$.audio`, `$.telemetry`. — [MODS-REF](https://code.claude.com/docs/en/plugins/mods/reference.md)

**Where mods run**

- "Mods work in the Claude Code CLI, the Code tab of the Claude Desktop app, and the VS Code extension." Table: `claude -p` and the Agent SDK — hooks run: Yes; what the mod draws appears: No. Remote Control from claude.ai/mobile — hooks run "in the session on your machine", drawing "In the terminal on your machine". Cloud session — hooks run "for a plugin that reaches the cloud session", drawing: No. WSL session in Desktop — No/No. — [MODS-OVERVIEW](https://code.claude.com/docs/en/plugins/mods/overview.md)
- "A mod's hooks run in every kind of session that loads the plugin, whichever provider serves the model, including Amazon Bedrock, Google Cloud's Agent Platform, and Microsoft Foundry." — [MODS-OVERVIEW](https://code.claude.com/docs/en/plugins/mods/overview.md)

**Distribution**

- "A mod installs as a plugin, from a marketplace." `/plugin install token-chart@your-org` or `claude plugin install token-chart@your-org`; all plugin install/scope/update mechanics "apply to a plugin that contains a mod without changes." — [MODS-OVERVIEW](https://code.claude.com/docs/en/plugins/mods/overview.md)
- Sharing options: send the directory or a `.zip`; your own marketplace; organization-wide via managed settings; public marketplace or Anthropic's directory. "Keep developing against the directory with `--plugin-dir`, not against an installed copy. Claude Code caches an installed plugin by version, so your edits don't reach the installed copy until you increment the version and install again." — [MODS-CREATE](https://code.claude.com/docs/en/plugins/mods/create)
- Local skill's "GitHub road": a one-file marketplace (`.claude-plugin/marketplace.json` with `"plugins": [{ "name": "<mod>", "source": "./" }]`) beside `plugin.json`, installed by `/plugin install <mod> --marketplace <owner>/<repo>`; a mandatory secrets scan (`mcp__plugin-authoring__scan_secrets`) before any push; a chat/Cowork variant packages a `<mod>.plugin` zip. — LOCAL-REF, "Sharing a mod" and "Packaging a mod in a chat"
- "A plugin can hold all of them, so a mod can ship in the same plugin as a skill and an MCP server." — [MODS-OVERVIEW](https://code.claude.com/docs/en/plugins/mods/overview.md), comparison section
- Anthropic's own: built-in mods `cc-plugin-agents-md`, `cc-plugin-diff`, `cc-plugin-plugin-authoring` ("It holds a skill and no mod code"), `cc-plugin-sec-default`, `cc-plugin-telemetry`, `cc-plugin-you-should-know`; sources in https://github.com/anthropics/claude-code/tree/main/mods; sample mods (`token-weather`, `blast-radius`, `replay-theater`) in https://github.com/anthropics/claude-code-playground/tree/main/claude-code/mods. — [MODS-OVERVIEW](https://code.claude.com/docs/en/plugins/mods/overview.md)

**Public status and date**

- CHANGELOG 2.1.287: "Added Claude Mods: plugins may now modify deeper behavior" and "Added You should know, a built-in mod …". — [CHANGELOG](https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md)
- The v2.1.287 GitHub release page shows "released this 01 Oct 18:00" (no year on the page). — [RELEASE-287](https://github.com/anthropics/claude-code/releases/tag/v2.1.287)
- "Mods are on by default. In the terminal, use Claude Code v2.1.287 or later. … mods work there [Desktop] from v2.1.286." and "If you set `CLAUDE_CODE_ENABLE_FUNCTION_HOOKS` during early access, remove it. Claude Code v2.1.287 and later ignores it". — [MODS-OVERVIEW](https://code.claude.com/docs/en/plugins/mods/overview.md)
- Third-party coverage exists (a dev.to walkthrough, Korean and Japanese explainers, one of which dates the launch to 2026-10-01 at v2.1.287) but these are aggregators; the official pages above are the primary source. — [WebSearch results, 2026-10-31](https://dev.to/nakadadev/how-to-make-a-claude-code-mod-with-three-files-that-work-in-the-desktop-app-26mm); [daleseo](https://daleseo.com/claude-code-mods/); [ai-souken](https://www.ai-souken.com/article/what-is-claude-code-mods)
- Comparison table (what each can change): Mod — "Tool calls, prompts, commands, turns, and what the interface draws"; Settings hook — "Whether a tool call or prompt goes ahead, a tool call's arguments and result, and context added for Claude"; Skill — "What Claude knows and does"; MCP server — "Which tools Claude has". Only a mod can draw in the interface. — [MODS-OVERVIEW](https://code.claude.com/docs/en/plugins/mods/overview.md)

### Inferences

- The local skill and the public docs describe the same artifact and agree on every structural fact checked (three files, `modules` key, `register(on, options)`, `$`/`e`/`next`, hot reload, validate/test). The only divergence found: the local skill names `mobile` as a possible `e.surface`, while the public "Where mods run" table shows mobile reaching a session only through Remote Control, drawing "In the terminal on your machine". Treat `mobile` as a declared-but-not-publicly-documented surface value.
- The 2.1.287 release year is inferred as 2026 from context (today is 2026-10-31; current version 2.1.316; the docs' "as of v2.1.290"); the release page itself omits the year.
- A mod is therefore a plugin component, not a parallel distribution channel: anything this repo's plugin ships in `plugins/dev-loop/hooks/hooks.json` could gain a `modules` entry and be installed by the same `/plugin install` path consumers already use.

### Gaps

- No official page states the exact calendar date of the public launch; the only dated artifact is the GitHub release page ("01 Oct 18:00", year not shown).
- The `~/.claude/dev-mods/` directory exists on this machine but was not inspected (read-only brief; the skill warns that the first file written under it triggers the hot-reload consent prompt, and listing it was not needed). No installed third-party mod was found in `~/.claude/plugins/installed_plugins.json` (entries: `security-guidance`, `context7`, `skill-creator`, `dev-loop`).

## Key question 2: Can a mod implement model routing or a model-profile switcher for subagents and for the session?

### Takeaway

Yes for subagents and yes per request: a mod's `agent.spawn` hook can set a subagent's `model` (alias or full ID) or deny the spawn, and its `turn.step` hook can rewrite `model` or `effort` on every model request, main loop and subagent loops alike. The hard limits are that `agent.spawn` cannot set a subagent's `effort` (only `tool.call` on the Agent tool could, by rewriting the tool's `effort` argument), `CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1` outranks a hook's choice, `$.session.model()` is read-only, and nothing in `turn.step` lets a hook change the base URL or provider.

### Cited Findings

**`agent.spawn` (subagent model)**

- Reference table: `agent.spawn` — "A subagent or an agent team teammate is about to start. For a teammate, `e.isTeammate` is `true`." A hook can return "`next({ ...e, model })` to choose its model, or `{ deny: reason }`". — [MODS-REF](https://code.claude.com/docs/en/plugins/mods/reference.md)
- "When Claude resumes a subagent with the `SendMessage` tool, your `agent.spawn` hook doesn't run again. To refuse the `SendMessage` calls that resume a subagent, match that tool in a `tool.call` hook." — [MODS-REF](https://code.claude.com/docs/en/plugins/mods/reference.md)
- The subagents page, in its model-resolution order, says of the per-invocation `model` parameter: "An installed mod's `agent.spawn` hook can replace it. `CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1` causes Claude Code to ignore it." — [SUBAGENTS](https://code.claude.com/docs/en/sub-agents)
- LOCAL-TYPES `AgentSpawnInput` doc: "A hook rewrites content (prompt, description, subagentType, model, background, cwd) unless `resume` fixes it, or `workflow` all but two; every other key is pinned." Field `model?: string`: "The Agent tool's `model` parameter as given, an alias (`haiku`) or a full id; undefined lets the agent's own model, then the parent's, decide. Ignored for forks, which always inherit. A hook sets this to pick the subagent's model; where the session forces one model on every subagent, that outranks a workflow agent's, a hook's included." Field `parentModel: string`: "The parent's effective model, what `inherit` resolves to. Pinned". Other pinned fields: `tool_use_id`, `provider`, `parentAgentId`, `permissionMode`, `fork`, `isTeammate`, `workflow`, `resume`, `name`. — LOCAL-TYPES lines ~261-420
- `AgentSpawnResult`: "the started subagent's `{ model, agentId }`, or `{ deny: reason }`"; `model`: "What the subagent runs on: from core the resolved id; from a hook an alias (`haiku`) or an id." — LOCAL-TYPES lines ~422-470
- The event doc comment: "Fires when the Agent tool, or a workflow script's `agent()` (`e.workflow`), is about to start an agent, its model not yet resolved. `next(e)` resolves to `{ model }`. Return it, `next({ ...e, model })`, `{ model }` of your own (an alias resolves like the tool's parameter), or `{ deny: reason }`. @remarks A guard that fails is skipped and the subagent starts, so give it `.catch(($, e, next) => next.called ? next(e) : { deny: "no" })`." — LOCAL-TYPES line ~4225-4240
- There is no `effort` field on `AgentSpawnInput` (the full type was read; fields are `tool_use_id`, `prompt`, `description`, `subagentType`, `provider`, `model`, `parentModel`, `parentAgentId`, `permissionMode`, `background`, `fork`, `isTeammate`, `workflow`, `resume`, `name`, `cwd`). — LOCAL-TYPES lines ~261-420
- CHANGELOG: 2.1.289 "Added `agent.spawn` for teammates, one agent id across plugin hook events, and idle and waiting states in `$.agent.list()`"; 2.1.292 "Added workflow agents to the `agent.spawn` mod hook …"; 2.1.299 "Fixed the `agent.spawn` mod hook not running when a finished subagent or a killed teammate is resumed: the hook's event now carries `resume`, and a mod can refuse it"; 2.1.300 "Added support for rewriting a workflow agent's `prompt` and `model` in the `agent.spawn` mod hook, which could only refuse workflow agents before". — [CHANGELOG](https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md)
- `$.agent.spawn(input)` takes `AgentSpawnArgs = Pick<AgentSpawnInput, 'prompt'> & Partial<Pick<AgentSpawnInput, 'description' | 'subagentType' | 'model' | 'name' | 'cwd'>>` — again no `effort`. — LOCAL-TYPES line ~280
- `$.agent.register` takes an `AgentSpec` "spelled as an agent definition in settings JSON is … Every field an agent file or `--agents` entry may carry is here", including `effort?: string | number` ("The agent's effort: a level (`low`, `medium`, `high`, `xhigh`, `max`)"). — LOCAL-TYPES lines ~480-500

**`turn.step` (per-request model and effort, main session included)**

- Reference table: `turn.step` — "One request is about to go to the model"; a hook can return "`yield* next(e)`, or `next({ ...e, model })`, `next({ ...e, effort })`". — [MODS-REF](https://code.claude.com/docs/en/plugins/mods/reference.md)
- Events guide: "`turn.step` … Claude Code is about to send one request to the model. A turn with tool calls has several. `e.agentId` is set for a subagent's request. | Read each request's token usage, send it to a different model with `next({ ...e, model })`, or answer without calling the model". "To send a request to a different model, pass `next` the event with `model` changed, as in `yield* next({ ...e, model: 'haiku' })`." Caveat: "If a `turn.step` request fails with a model error when `model` is an alias such as `haiku`, update to Claude Code v2.1.309 or later, or use a full model id. Before v2.1.309, an alias went out as written." — [MODS-EVENTS](https://code.claude.com/docs/en/plugins/mods/events.md)
- LOCAL-TYPES `TurnStepInput`: "A hook rewrites `model` or `effort` going down; the rest is pinned." `model: string` — "Which model the request names, as the engine resolved it for this step (the session's, a fallback's). `next({ ...e, model })` names another, by an alias (`haiku`) or a full id." `effort?: 'low' | 'medium' | 'high' | 'xhigh' | 'max' | number` — "the session's setting or the model's default, absent for a model without effort; rewritable. On a model that takes effort per message a level stands from one message with input to the next: a change waits through steps whose new input is tool results, and one made on a step with input stays for the tool steps after it. A number goes out at once." `agentId?: string` — "The loop the request is made in … absent on main. Pinned … A subagent a hook spawned through `$.agent.spawn` steps past that hook, as its tool calls do; every other hook sees its steps." — LOCAL-TYPES lines ~14500-14535
- Overview: a mod can "Step into a tool call or a request: for example, hold a tool call while you ask the user a question, answer it without running the tool, or send one request to a different model." — [MODS-OVERVIEW](https://code.claude.com/docs/en/plugins/mods/overview.md)

**Session model: read-only to mods**

- `$.session.model: () => Promise<string>` — "Returns the main loop's model, as `/model` shows it." No setter exists in the `session` namespace (methods: `messages`, `cwd`, `root`, `model`, `turns`, `id`, `repo`, `surfaces`, `surface`, `usage`, `version`, `compact`, `send`, `append`, `authorize`). — LOCAL-TYPES lines ~2835-2925; [MODS-REF](https://code.claude.com/docs/en/plugins/mods/reference.md)

**`$.model.complete` (a mod's own model calls)**

- "`$.model.complete` sends your prompt on its own, and `$.model.fork({ prompt })` sends the current conversation with your prompt at the end." Model: "The `model` you pass" vs "The session's model". "Both calls use the session's credentials, so they bill to the user's plan, API key, or cloud provider." Options include `effort`. — [MODS-API](https://code.claude.com/docs/en/plugins/mods/api.md)
- LOCAL-TYPES: `await $.model.complete({ model: "haiku", prompt, effort: "low" })`; "A model that takes no effort setting is sent none, whatever is asked." — LOCAL-TYPES lines ~6417-6540

**Env from a mod**

- `$.env` — "The environment of this process, the one every Bash child, MCP server and `$.process.run` command started after inherits." `set`: "Sets the variable for this process and everything it starts after, or unsets it when `value` is `undefined`." Names must be string literals so `claude plugin validate` can list `env reads:`/`env writes:`. `EnvSetResult.deny`: "In a session that takes its settings from its organization, the engine holds a write a plugin that is not built in stands behind where a person's own settings file could not set the variable there." — LOCAL-TYPES, `env` namespace and `EnvSetResult`
- MODS-API confirms: "`$.env` | `get` and `set` environment variables. Write the name as a string literal." — [MODS-API](https://code.claude.com/docs/en/plugins/mods/api.md)

**Precedence facts that bound a router**

- Subagent model resolution order: "1. The per-invocation `model` parameter 2. The definition's `model` frontmatter (`inherit` selects the main conversation's model) 3. `CLAUDE_CODE_SUBAGENT_MODEL`, if set to an alias or model ID 4. The main conversation's model". "Before v2.1.251, `CLAUDE_CODE_SUBAGENT_MODEL` came first in this order and overrode both." `CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1` (v2.1.257+) forces it onto every subagent. — [SUBAGENTS](https://code.claude.com/docs/en/sub-agents); CHANGELOG 2.1.251 and 2.1.257 entries — [CHANGELOG](https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md)
- Agent tool `model` parameter: "that parameter takes a model alias: `sonnet`, `opus`, `haiku`, or `fable`. Claude can't pass a full model ID or `inherit` on that call." — [SUBAGENTS](https://code.claude.com/docs/en/sub-agents); LOCAL-TYPES `BuiltinToolInputs.Agent.model?: "sonnet" | "opus" | "haiku" | "fable"`.
- Agent tool `effort` parameter (v2.1.292+): "it can also pass an `effort` parameter for that invocation. The parameter overrides the `effort` field and stays in effect when the subagent is resumed." "The `CLAUDE_CODE_EFFORT_LEVEL` environment variable takes precedence over both." — [SUBAGENTS](https://code.claude.com/docs/en/sub-agents); CHANGELOG 2.1.292 "Added an `effort` parameter to the Agent tool" — [CHANGELOG](https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md)
- Main-session model precedence: `/model` > `--model` > `ANTHROPIC_MODEL` > settings `model` > `ANTHROPIC_DEFAULT_MODEL`; "The `--model` flag and `ANTHROPIC_MODEL` environment variable apply only to the session you launch with them." Effort order: `CLAUDE_CODE_EFFORT_LEVEL` > a level picked in session > `--effort` > settings > model default. — [MODEL-CONFIG](https://code.claude.com/docs/en/model-config.md)
- "`ANTHROPIC_BASE_URL` changes where requests are sent, not which model answers them." — [MODEL-CONFIG](https://code.claude.com/docs/en/model-config.md)

### Inferences

- A mod is the only documented mechanism that can *rewrite* a subagent's model after the orchestrator chose it; settings hooks can only observe (SubagentStart carries no model) or, speculatively, rewrite the Agent tool's input (see Q3).
- `turn.step` makes a per-request, mid-turn model and effort router possible for the main session, which no settings hook can do (PreModelSwitch only vetoes user-initiated switches, and `/effort` changes start "the next message you send" per MODEL-CONFIG). This is the one place where "change the main-session model mid-turn" is a yes, and it is a mod-only yes.
- Subagent `effort` is not rewritable at `agent.spawn` (field absent, "every other key is pinned"). Two indirect routes exist, both inferred rather than documented: (a) a `tool.call` hook on `{ tool: 'Agent' }` rewriting `e.effort`, since "Change the call: pass changed arguments to `next`" is generic and the Agent tool input declares `effort`; (b) a `turn.step` hook keyed on `e.agentId` rewriting `effort` on each of that subagent's requests. Route (b) is documented as rewritable; route (a) is plausible but no example exists.
- `CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1` is a consumer-side kill switch that overrides any mod-based router (LOCAL-TYPES: the forced model "outranks a workflow agent's, a hook's included").
- `$.env.set` writes into the Claude Code process environment, so a mod *can* set `ANTHROPIC_MODEL`/`ANTHROPIC_BASE_URL` in-process; whether the API client re-reads those variables after startup is undocumented, and MODEL-CONFIG's "apply only to the session you launch with them" suggests not. Do not rely on it.
- The alias-vs-ID caveat (fixed in v2.1.309) means a router that sets `model: 'haiku'` at `turn.step` should pin a minimum CLI version or send full IDs.

### Gaps

- No official documentation of a "model profile switcher" pattern or sample mod; the capability is assembled from `agent.spawn`, `turn.step`, `$.config`, and `$.command.register`.
- Whether `$.env.set("ANTHROPIC_BASE_URL", …)` affects subsequent API requests of the running session is not stated anywhere read; the `turn.step` input has no URL/provider field, so per-subagent base URL routing is unsupported as far as the docs go.
- Whether `tool.call` on the Agent tool can rewrite `effort` is not shown by any example; only the generic "pass changed arguments to `next`" rule and the declared `effort` input field support it.

## Key question 3: Exactly what can settings hooks do about model selection?

### Takeaway

Settings hooks can observe effort (an `effort.level` field and `$CLAUDE_EFFORT` on tool-context events) and, on PreToolUse, replace the Agent tool's whole input via `updatedInput` (validated since v2.1.300, so an invalid `model`/`effort` denies the call); they cannot see a subagent's resolved model (SubagentStart/Stop carry only `agent_id`/`agent_type`), cannot change the session model (PreModelSwitch only allows/denies/asks), and only SessionStart sometimes carries a `model` field. The Agent tool is matched as `Agent`.

### Cited Findings

**Event inventory (33 events)**

- SessionStart, Setup, UserPromptSubmit, UserPromptExpansion, PreToolUse, PermissionRequest, PermissionDenied, PostToolUse, PostToolUseFailure, PostToolBatch, Notification, MessageDisplay, SubagentStart, SubagentStop, TaskCreated, TaskCompleted, Stop, StopFailure, TeammateIdle, InstructionsLoaded, ConfigChange, CwdChanged, DirectoryAdded, FileChanged, WorktreeCreate, WorktreeRemove, PreCompact, PostCompact, PreModelSwitch, PostModelSwitch, Elicitation, ElicitationResult, SessionEnd. — [HOOKS](https://code.claude.com/docs/en/hooks), lifecycle table
- Hook types: `command`, `http`, `mcp_tool`, `prompt`, `agent` ("experimental and may change"). Common fields `type`, `if`, `timeout`, `statusMessage`, `once` ("honored only in skill frontmatter"); command fields `command`, `args`, `async`, `asyncRewake`, `shell`, `onFailure`; prompt/agent fields `prompt`, `model`. — [HOOKS](https://code.claude.com/docs/en/hooks)

**Common input and the effort/model fields**

- Common PreToolUse input example: `session_id`, `prompt_id`, `transcript_path`, `cwd`, `scratchpad_dir`, `permission_mode`, `hook_event_name`, `tool_name`, `tool_input`, `tool_use_id`. — [HOOKS](https://code.claude.com/docs/en/hooks)
- `effort`: "Object whose `level` is the effort level setting when the hook runs … `low`, `medium`, `high`, `xhigh`, or `max`. Present for `PreToolUse`, `PostToolUse`, `Stop`, `SubagentStop`, and other events with a tool-use context." `$CLAUDE_EFFORT` env var holds the same. — [HOOKS](https://code.claude.com/docs/en/hooks)
- LOCAL-TYPES (the settings-hook stdin shape, `BaseHookInput.effort`): "Active effort level for the current turn (e.g., 'low', 'medium', 'high', 'xhigh', 'max'), after any silent downgrade for the selected model. Also exposed to hook commands and Bash as the CLAUDE_EFFORT env var." — LOCAL-TYPES lines ~871-875
- "Only `SessionStart` hooks can receive a `model` field … and Claude Code doesn't always include it." SessionStart `model`: "The active model identifier. It can be omitted, for example after `/clear` or when a session is restored through conversation recovery, so check for the field before reading it". "There is no `$CLAUDE_MODEL` environment variable." — [HOOKS](https://code.claude.com/docs/en/hooks)
- Token usage or cost: not present in any hook input except the SessionStart resume/fork extras (`seconds_since_last_response`, `context_tokens`, `prompt_cache_likely_expired`, `estimated_cache_write_usd`, v2.1.251+) and PreModelSwitch's cost fields (below). — [HOOKS](https://code.claude.com/docs/en/hooks)

**PreToolUse decision control and `updatedInput`**

- `hookSpecificOutput` fields: `permissionDecision` (`allow`/`deny`/`ask`/`defer`), `permissionDecisionReason`, `updatedInput`, `additionalContext`. — [HOOKS](https://code.claude.com/docs/en/hooks)
- `updatedInput`: "Modifies the tool's input parameters before execution. Replaces the entire input object, so include unchanged fields alongside modified ones. Claude Code evaluates permission rules and a Bash command's auto-background eligibility against the input your hook returns, not the input Claude sent. Combine with `"allow"` to auto-approve, or `"ask"` to show the modified input to the user. For `"defer"`, ignored". — [HOOKS](https://code.claude.com/docs/en/hooks)
- Overview sentence: "`PreToolUse`: `updatedInput` directly under `hookSpecificOutput` replaces a tool's arguments before it runs." No per-tool restriction is stated. — [HOOKS](https://code.claude.com/docs/en/hooks)
- CHANGELOG 2.1.300: "Changed hooks: `updatedInput` from PreToolUse and PermissionRequest hooks is now validated like Claude's own input: unknown keys are dropped, and input the tool rejects denies the call". Earlier: 2.1.110 PermissionRequest `updatedInput` re-checked against `permissions.deny`; an older entry "Fixed PreToolUse hooks to allow `updatedInput` when returning `ask`"; "PreToolUse hooks can now satisfy `AskUserQuestion` by returning `updatedInput` alongside `permissionDecision: "allow"`". — [CHANGELOG](https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md)
- "When multiple `PreToolUse` hooks return `updatedInput` to rewrite a tool's input, Claude Code doesn't merge the rewrites or guarantee which rewrite the tool runs with. Avoid having more than one hook rewrite the same tool's input." — [HOOKS-GUIDE](https://code.claude.com/docs/en/hooks-guide)
- Precedence across hooks: "the most restrictive answer applies, in the order `deny`, `defer`, `ask`, `allow`." — [HOOKS-GUIDE](https://code.claude.com/docs/en/hooks-guide)
- Agent tool `tool_input` as documented on the hooks page: `prompt`, `description`, `subagent_type`, `model` ("sonnet", optional). — [HOOKS](https://code.claude.com/docs/en/hooks)
- The full Agent tool input schema this build declares: `description`, `prompt`, `subagent_type?`, `model?: "sonnet" | "opus" | "haiku" | "fable"`, `effort?: "low" | "medium" | "high" | "xhigh" | "max"`, `name?`, deprecated `team_name?` and `mode?`, `isolation?: "worktree" | "remote"`. — LOCAL-TYPES `BuiltinToolInputs.Agent`, lines ~17170-17190

**Matcher syntax and the Agent tool's name**

- "Only letters, digits, `_`, `-`, spaces, `,`, and `|`" → "Exact string, or list of exact strings separated by `|` or `,`"; "Contains any other character" → "JavaScript regular expression, unanchored". Examples `Bash`, `Edit|Write`, `mcp__memory__.*`. — [HOOKS](https://code.claude.com/docs/en/hooks)
- The subagent tool is documented as `Agent` (listed among built-in tools and as the `##### Agent` input section); `Task` appears only in the `TaskCreate`/`TaskCompleted` context. — [HOOKS](https://code.claude.com/docs/en/hooks)
- The `if` field filters by tool name and arguments; "Because the filter is best-effort, use the permission system rather than a hook to enforce a hard allow or deny." — [HOOKS-GUIDE](https://code.claude.com/docs/en/hooks-guide)

**SubagentStart / SubagentStop**

- SubagentStart input: `agent_id`, `agent_type` (plus common fields); example `{ "hook_event_name": "SubagentStart", "agent_id": "agent-abc123", "agent_type": "Explore" }`. Output: `additionalContext` only; "It can't block subagent creation." — [HOOKS](https://code.claude.com/docs/en/hooks)
- SubagentStop input: `stop_hook_active`, `agent_id`, `agent_type`, `agent_transcript_path`, `last_assistant_message`, `background_tasks`, `session_crons`. Output: Stop format; "Returning `decision: "block"` with a `reason` keeps the subagent running and delivers `reason` to the subagent as its next instruction." Exit 2 "Prevents the subagent from stopping." — [HOOKS](https://code.claude.com/docs/en/hooks)
- Neither event carries a `model` field (see "Only `SessionStart` hooks can receive a `model` field"). — [HOOKS](https://code.claude.com/docs/en/hooks)
- `SubagentStart` and `SubagentStop` are "configured in `settings.json` as project-level hooks, matched by agent name." — [SUBAGENTS](https://code.claude.com/docs/en/sub-agents)
- Hook environment: `agent_id` "Unique identifier for the subagent or in-process teammate the hook fires in"; `agent_type` "Agent name (for example, `"Explore"` or `"security-reviewer"`)". — [HOOKS](https://code.claude.com/docs/en/hooks)

**PreModelSwitch / PostModelSwitch (v2.1.251+)**

- PreModelSwitch runs for `/model`, the picker, the `/config` Model setting, fast mode, and SDK `set_model`/`apply_flag_settings`; not for automatic fallback or resume restore. Input: `from_model`, `to_model`, `requested_model`, `source` (`command`/`picker`/`sdk`), `context_tokens`, `prompt_cache_warm`, `cache_ttl`, `estimated_cache_write_usd`, `pricing`. Decision: exit 2 or `decision: "block"` cancels; `hookSpecificOutput.permissionDecision` accepts `allow`/`deny`/`ask`; "It doesn't accept `"defer"`, `updatedInput`, or `additionalContext`." Precedence `deny` > `ask` > `allow`. "A PreModelSwitch hook that doesn't respond before its timeout blocks the switch. The default timeout for this event is 30 seconds." — [HOOKS](https://code.claude.com/docs/en/hooks)
- PostModelSwitch "can't block, because the model has already changed"; runs after requested switches, automatic fallback, `opusplan` mode changes, and resume restores; not for one-turn fallback-chain substitutions. — [HOOKS](https://code.claude.com/docs/en/hooks)
- Matchers for both compare "the canonical name of the model the session switches to", e.g. `claude-opus-5`, `claude-opus-4-6|claude-opus-5`, `.*opus.*`. — [HOOKS-GUIDE](https://code.claude.com/docs/en/hooks-guide)
- CHANGELOG 2.1.251: "Added `PreModelSwitch` and `PostModelSwitch` hook events (block, confirm, or annotate a model switch)". — [CHANGELOG](https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md)

**Other outputs of note**

- UserPromptSubmit "can't replace the prompt; it only injects `additionalContext` alongside it"; output fields `decision`, `reason`, `additionalContext`, `sessionTitle`, `suppressOriginalPrompt`. — [HOOKS](https://code.claude.com/docs/en/hooks)
- PostToolUse output: `decision`, `reason`, `additionalContext`, `classifierContext`, `updatedToolOutput` ("only changes what Claude sees"), `updatedMCPToolOutput`. PostToolUseFailure input adds `error`, `is_interrupt`, `duration_ms`. — [HOOKS](https://code.claude.com/docs/en/hooks)
- Hooks "can't trigger `/` commands or tool calls. Text returned via `additionalContext` is injected as a system reminder". — [HOOKS-GUIDE](https://code.claude.com/docs/en/hooks-guide)

### Inferences

- Rewriting the Agent tool's `model` or `effort` through PreToolUse `updatedInput` is *mechanically* supported (the field replaces the whole input object, there is no per-tool restriction, and since v2.1.300 the rewritten input is validated against the tool's schema, so `model` must be one of the four aliases and `effort` one of the five levels or the call is denied). It is *not documented as a use case*: no example on any page rewrites `Agent` input, and the only `Agent`-specific statement about overriding the per-call model names a mod's `agent.spawn`, not a hook. Treat it as plausible and testable, not as supported.
- Because `updatedInput` on the Agent tool replaces the input "before execution", and the subagent resolution order puts the per-invocation `model` first, a hook-rewritten `model` would become the per-invocation parameter and win over frontmatter and `CLAUDE_CODE_SUBAGENT_MODEL` (unless `_FORCE=1`). This follows from the two documented rules; it is not stated directly.
- Settings hooks are the wrong layer for *observing* a subagent's resolved model: SubagentStart carries `agent_type` but no model, and there is no `$CLAUDE_MODEL`. Only a mod (`agent.spawn`'s result `model`, `turn.step`'s `e.model`, `turn.step` result `usage.model`) or the status line (`model.id`) sees the resolved model.

### Gaps

- The date or version at which the subagent tool was renamed from `Task` to `Agent` was not found in the CHANGELOG grep or the docs read; every current page uses `Agent`.
- No example anywhere rewrites the Agent tool's input with `updatedInput`; whether a rewritten `effort` is honored identically to a model-supplied one (e.g., persistence across SendMessage resumes) is untested and undocumented.

## Key question 4: Env injection, session-model changes, and per-subagent hook scoping

### Takeaway

`CLAUDE_ENV_FILE` (available to SessionStart, Setup, CwdChanged, FileChanged) persists shell variables for the Bash tool only — the file's contents run as a preamble before each Bash command — so writing `ANTHROPIC_MODEL` or `ANTHROPIC_BASE_URL` there cannot change Claude Code's own API client, which reads those at launch. Hooks can be scoped to a subagent via `hooks:` frontmatter (all events; removed when the subagent finishes; `Stop` becomes `SubagentStop`), but plugin-shipped subagents ignore the `hooks` field.

### Cited Findings

- "SessionStart hooks have access to the `CLAUDE_ENV_FILE` environment variable, which provides a file path where you can persist environment variables for the shell commands Claude runs later in the session." Example: `echo 'export NODE_ENV=production' >> "$CLAUDE_ENV_FILE"`. "Each Bash command runs the file's contents as shell code before the command itself." PowerShell reads only plain assignments (v2.1.296+); sandboxed PowerShell receives none. Events with access: SessionStart, Setup, CwdChanged, FileChanged. — [HOOKS](https://code.claude.com/docs/en/hooks)
- "Both write to `CLAUDE_ENV_FILE`, which Claude Code runs as a script preamble before each Bash command." — [HOOKS-GUIDE](https://code.claude.com/docs/en/hooks-guide)
- CwdChanged/FileChanged: variables written there "persist into subsequent Bash commands until the next CwdChanged event, when Claude Code clears them." — [HOOKS](https://code.claude.com/docs/en/hooks)
- CHANGELOG history: 2.1.111 "Windows: `CLAUDE_ENV_FILE` and SessionStart hook environment files now apply (previously a no-op)"; 2.1.136 "Fixed env vars from `CLAUDE_ENV_FILE` SessionStart hooks going stale after `/resume` or `/clear`"; 2.1.295 "Fixed variables a SessionStart hook writes to `CLAUDE_ENV_FILE` not reaching the Bash tool after an in-app `/resume` or `/branch`". — [CHANGELOG](https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md)
- "The `--model` flag and `ANTHROPIC_MODEL` environment variable apply only to the session you launch with them." With `ANTHROPIC_MODEL` set, "Claude Code returns to that variable's model on the next launch, whatever you saved with `/model`." — [MODEL-CONFIG](https://code.claude.com/docs/en/model-config.md)
- A `/model` switch "also reaches subagents that inherit the main conversation's model, because Claude Code resolves their model from the one your session is using when Claude starts them." — [MODEL-CONFIG](https://code.claude.com/docs/en/model-config.md)
- New effort levels take effect on "the next message you send" (after the turn, or queued while Claude works). — [MODEL-CONFIG](https://code.claude.com/docs/en/model-config.md), "When a new effort level starts"
- Hooks in frontmatter: "hooks can be defined directly in skills and subagents using frontmatter." Subagent hooks "are removed when the subagent finishes, and a `Stop` hook there is converted to `SubagentStop`. Skill hooks persist for the session." — [HOOKS](https://code.claude.com/docs/en/hooks)
- Subagent `hooks` field: "Lifecycle hooks scoped to this subagent. Ignored for plugin subagents". "All hook events are supported." "These hooks only run while that specific subagent is active and are cleaned up when it finishes." "Project-level agent hooks run only after you accept the workspace trust dialog." — [SUBAGENTS](https://code.claude.com/docs/en/sub-agents)
- Hook locations table: `~/.claude/settings.json`, `.claude/settings.json`, `.claude/settings.local.json`, managed policy settings, plugin `hooks/hooks.json`, skill frontmatter ("The rest of the session once the skill is invoked"), subagent frontmatter ("While that subagent is running"). — [HOOKS-GUIDE](https://code.claude.com/docs/en/hooks-guide)
- Hook process environment from a plugin: `CLAUDE_PLUGIN_ROOT`, `CLAUDE_PLUGIN_DATA`, `CLAUDE_PROJECT_DIR`, `CLAUDE_PLUGIN_OPTION_<KEY>`; "The variables aren't present in the environment of commands Claude runs through the Bash tool, in the main session or in a subagent." — [MANIFEST](https://code.claude.com/docs/en/plugins-reference)
- Subagent frontmatter `model`: "`sonnet`, `opus`, `haiku`, `fable`, a full model ID such as `claude-opus-5-5`, or `inherit`"; `effort`: "`low`, `medium`, `high`, `xhigh`, `max` … Overrides the session effort level, but not the `CLAUDE_CODE_EFFORT_LEVEL` environment variable." — [SUBAGENTS](https://code.claude.com/docs/en/sub-agents)

### Inferences

- No settings hook can change the main session's model or effort: SessionStart/UserPromptSubmit return only context, PreModelSwitch returns only a permission decision (explicitly no `updatedInput`), and `CLAUDE_ENV_FILE` reaches only the Bash tool. A hook that writes `export ANTHROPIC_MODEL=…` there affects `claude` *child* invocations the model might run from Bash, not the running session.
- Per-subagent hook scoping exists but is unavailable to *plugin-shipped* agents, which matters for this repo: a plugin that ships `agents/*.md` cannot attach `hooks:` to them; the plugin's `hooks/hooks.json` with `SubagentStart`/`SubagentStop` matchers on the agent name is the available substitute.

### Gaps

- The hooks reference was read in three chunks; the exact "Persist environment variables" subsection heading was quoted via the SessionStart section, and whether subagent Bash commands also run the preamble is not stated in the text read.
- No source states that any hook or mod can change `ANTHROPIC_BASE_URL` for a running session or for one subagent.

## Key question 5: Cost and usage visibility for hooks, the status line, and mods

### Takeaway

Settings hooks receive no token or cost data except two narrow cases (SessionStart on resume/fork, and PreModelSwitch's re-cache estimate). The status line receives a rich per-session JSON (`model.id`, `cost.total_cost_usd` cumulative and client-estimated, `context_window.*`, `effort.level`, `rate_limits`, `prompt_cache`, `agent.name`). Mods see the most: per-request `usage` on `turn.step` results, per-turn `e.usage` on `turn.complete`, and `$.session.usage()` with `cost`, `context`, and `rateLimits`.

### Cited Findings

**Settings hooks**

- No hook input carries token usage or cost in general. — [HOOKS](https://code.claude.com/docs/en/hooks) (first-chunk extraction: "Token usage or cost: Not found in any hook input")
- Exceptions: SessionStart on `resume`/`fork` gets `seconds_since_last_response`, `context_tokens`, `prompt_cache_likely_expired`, `estimated_cache_write_usd` (v2.1.251+); PreModelSwitch gets `context_tokens`, `prompt_cache_warm`, `cache_ttl`, `estimated_cache_write_usd`, `pricing` (`configured`/`catalog`/`default`). — [HOOKS](https://code.claude.com/docs/en/hooks)
- OpenTelemetry (not hooks): since 2.1.117 `cost.usage`, `token.usage`, `api_request`, `api_error` events "include an `effort` attribute when the model supports effort levels". — [CHANGELOG](https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md)

**Status line JSON (full schema)**

- Configuration: `"statusLine": { "type": "command", "command": …, "padding", "refreshInterval" }`; "The optional `refreshInterval` field re-runs your command every N seconds in addition to the event-driven updates. The minimum is `1`." "Claude Code debounces updates at 300ms". — [STATUSLINE](https://code.claude.com/docs/en/statusline)
- The documented example JSON (verbatim field set): `cwd`, `session_id`, `session_name`, `prompt_id`, `transcript_path`, `model: { id: "claude-opus-5-5", display_name: "Opus" }`, `workspace: { current_dir, project_dir, added_dirs, git_worktree, repo: { host, owner, name } }`, `version`, `output_style: { name }`, `cost: { total_cost_usd: 0.01234, total_duration_ms: 45000, total_api_duration_ms: 2300, total_lines_added: 156, total_lines_removed: 23 }`, `context_window: { total_input_tokens: 15500, total_output_tokens: 1200, context_window_size: 200000, used_percentage: 8, remaining_percentage: 92, current_usage: { input_tokens: 8500, output_tokens: 1200, cache_creation_input_tokens: 5000, cache_read_input_tokens: 2000 } }`, `exceeds_200k_tokens: false`, `prompt_cache: { warm, caching_observed, ttl, expires_at, requests, misses, expected_rebuilds, hit_ratio, cache_write_tokens, miss_recache_tokens, last_miss_at, last_miss_cause: { causes, tools_added, tools_removed }, miss_causes, recache_tokens_if_cold }`, `fast_mode: false`, `effort: { level: "high" }`, `thinking: { enabled: true }`, `rate_limits: { five_hour: { used_percentage, resets_at }, seven_day: {…}, spend_limit: { used_percentage, resets_at, used_usd, limit_usd, period } }`, `vim: { mode }`, `agent: { name: "security-reviewer" }`, `pr: { number, url, review_state }`, `worktree: { name, path, branch, original_cwd, original_branch }`. — [STATUSLINE](https://code.claude.com/docs/en/statusline), "Full JSON schema" accordion
- `cost.total_cost_usd`: "Estimated session cost in USD, computed client-side at list price unless a `modelPricing` table is in effect. May differ from your actual bill. Resets to $0 when `/clear` starts a new session". "The `cost.total_cost_usd` field accumulates the estimated cost of all API calls in the current session." — [STATUSLINE](https://code.claude.com/docs/en/statusline)
- `effort.level`: "Reasoning effort level set for the session (`low`, `medium`, `high`, `xhigh`, or `max`), not one that a skill, a subagent, or `ultrathink` set. … Absent when the current model does not support the effort parameter". — [STATUSLINE](https://code.claude.com/docs/en/statusline)
- `context_window.total_input_tokens`/`total_output_tokens`: "Token counts currently in the context window, from the most recent API response. Input includes cache reads and writes". `current_usage` is "`null` before the first API call in a session, and again after `/compact`". — [STATUSLINE](https://code.claude.com/docs/en/statusline)
- `rate_limits` "appears only for claude.ai Pro, Max, and Ultra subscribers, or behind a Claude apps gateway that sets a spend limit for you … only after the first API response". — [STATUSLINE](https://code.claude.com/docs/en/statusline)
- `agent.name`: "Agent name when running with the `--agent` flag or agent settings configured". — [STATUSLINE](https://code.claude.com/docs/en/statusline)
- Subagent status lines: `subagentStatusLine` renders a row per subagent; task fields include `effort` ("Reasoning effort set for the subagent in its definition frontmatter or on the individual invocation … This is the configured value, and the effort Claude Code applies can differ when the model doesn't support that level. Omitted when no effort is set"). Plugins can ship a default `subagentStatusLine` in `settings.json`. — [STATUSLINE](https://code.claude.com/docs/en/statusline)

**Mods**

- `turn.step` result `usage`: "holds the token counts the Claude API reports for a request, plus the `model` that answered: `input_tokens`, `output_tokens`, `cache_read_input_tokens`, and `cache_creation_input_tokens`. The hook runs for subagents' requests too, so check `e.agentId` when you want only the main conversation." — [MODS-EVENTS](https://code.claude.com/docs/en/plugins/mods/events.md)
- `turn.complete`: "`e.usage` the turn's token totals. A subagent's turn fires it with `e.agentId` set." — [MODS-EVENTS](https://code.claude.com/docs/en/plugins/mods/events.md)
- `$.session.usage()` "returns `{ startedAt, context, rateLimits, cost }`: `context` has `tokens`, `window`, and `percent`, and `rateLimits` is a list of `{ kind, percentUsed, resetsAt }`." — [MODS-REF](https://code.claude.com/docs/en/plugins/mods/reference.md); LOCAL-TYPES `SessionUsage.cost?: SessionCost` — "What the session has cost so far, as /cost totals it; absent only where the host keeps no cost ledger (the CLI always has one)."
- `session.measure` fires "After each turn, and when a plan limit's percent used changes". — [MODS-REF](https://code.claude.com/docs/en/plugins/mods/reference.md)
- `$.model.complete` results carry `usage` with cache fields. — [MODS-API](https://code.claude.com/docs/en/plugins/mods/api.md)
- Overview: a mod can "read each request's token usage while another charts it in a pane" and can "Spend your usage: call a model on your plan or API key". — [MODS-OVERVIEW](https://code.claude.com/docs/en/plugins/mods/overview.md)

### Inferences

- The status line is the only *settings-level* surface that exposes both the current model and cumulative cost, but it is display-only (its script's stdout is rendered, not fed back to Claude or to hooks), and `cost.total_cost_usd` is a client-side list-price estimate that excludes nothing per subagent — it is one session-wide number.
- For per-subagent cost attribution, mods are the only in-process source (`turn.step` usage keyed by `e.agentId`, with `usage.model` naming the model that actually answered).

### Gaps

- The exact shape of `SessionCost` and `SessionContextUsage` in LOCAL-TYPES was not expanded (only the `SessionUsage` wrapper was read).
- Whether `cost.total_cost_usd` includes subagent requests is not stated explicitly on STATUSLINE (the wording "all API calls in the current session" suggests yes).

## Key question 6: Plugin packaging — what a plugin can ship, mods inside plugins, and pre-tiered agent roles

### Takeaway

A plugin ships `skills/`, `commands/`, `agents/`, `hooks/hooks.json`, `.mcp.json`, `.lsp.json`, `output-styles/`, `workflows/`, `themes/`, `monitors/`, `bin/`, `settings.json`, and — via `hooks/hooks.json`'s `modules` key plus an optional `types` manifest field — a mod. Plugin agents support `model:` and `effort:` frontmatter, so a consumer gets pre-tiered roles on install, but plugin agents ignore `hooks`, `mcpServers`, and `permissionMode`.

### Cited Findings

- Standard layout table: Manifest `.claude-plugin/plugin.json` (optional); Skills `skills/`; Commands `commands/`; Agents `agents/` ("Subfolders are part of the agent name"); Hooks `hooks/hooks.json`; MCP `.mcp.json`; LSP `.lsp.json`; Output styles; Workflows `workflows/`; Themes; Monitors `monitors/monitors.json`; Executables `bin/` ("on the Bash tool's `PATH` while the plugin is enabled"); Settings `settings.json` ("`agent` and `subagentStatusLine` defaults"). — [MANIFEST](https://code.claude.com/docs/en/plugins-reference)
- Manifest fields include `hooks` ("`.json` hook files or inline hook config. Loaded together with `hooks/hooks.json`"), `agents` ("Agent `.md` files. Directories aren't accepted. Replaces the default `agents/` scan"), `types` (mod state contract), `dependencies`, `userConfig`, `settings` ("Only `agent` and `subagentStatusLine` take effect"). — [MANIFEST](https://code.claude.com/docs/en/plugins-reference)
- `hooks/hooks.json` for a mod: "`modules`: an array with one path … Can also hold settings hooks under `hooks`." — [MODS-REF](https://code.claude.com/docs/en/plugins/mods/reference.md)
- "A plugin can hold all of them, so a mod can ship in the same plugin as a skill and an MCP server." — [MODS-OVERVIEW](https://code.claude.com/docs/en/plugins/mods/overview.md)
- Plugin subagents: "Plugin subagents come from plugins you've installed. They load automatically alongside your custom subagents and appear in the @-mention typeahead under their scoped name." Scoped as `<plugin>:<agent>`, recursive (`agents/review/security.md` → `my-plugin:review:security`); lowest priority (5). "plugin subagents don't support the `hooks`, `mcpServers`, or `permissionMode` frontmatter fields. These fields are ignored when loading agents from a plugin." — [SUBAGENTS](https://code.claude.com/docs/en/sub-agents)
- Frontmatter `model` and `effort` fields (quoted under Q4) carry no plugin exclusion, unlike `hooks`/`mcpServers`/`permissionMode`/`initialPrompt`, which are each marked "Ignored for plugin subagents". — [SUBAGENTS](https://code.claude.com/docs/en/sub-agents)
- Plugin command map entries accept a `model` field ("Default model for the command"). — [MANIFEST](https://code.claude.com/docs/en/plugins-reference)
- Plugin hooks' `${user_config.KEY}` substitution works in exec-form `args`, and every option is exported to hook processes as `CLAUDE_PLUGIN_OPTION_<KEY>`; shell-form hook commands reject `${user_config.*}`. — [MANIFEST](https://code.claude.com/docs/en/plugins-reference)
- Disabling: "`disableAllHooks` and your organization's `allowManagedModsOnly` stop a mod and leave the rest of its plugin in place: the plugin stays installed, and its skills, commands, agents, and MCP servers load." — [MODS-OVERVIEW](https://code.claude.com/docs/en/plugins/mods/overview.md)
- `claude plugin validate` reports a mod's `hooks:`, `calls:`, `env reads:`/`env writes:`, `state reads:`/`state writes:` lines and "gating hook without .catch: tool.call" notes; validation rules: `$` calls written in full, event names as string literals, imports only from inside the plugin by relative path, ES modules only. — [MODS-CREATE](https://code.claude.com/docs/en/plugins/mods/create)
- Name check: `claude plugin validate` errors on names starting with `claude-`, `anthropic-`, `cc-plugin-`, etc. — [MANIFEST](https://code.claude.com/docs/en/plugins-reference)

### Inferences

- For this repo: shipping tiered roles is a one-line-per-agent change (`model:`/`effort:` in `plugins/dev-loop/agents/*.md`), and shipping a router is a `hooks/hooks.json` `modules` entry plus one TypeScript file — but the mod would break the repo's "stdlib-only, runs under bare python3" posture only in the sense that it is JavaScript executed by Claude Code itself; it needs no Node, npm, or build step, so no dependency manifest is introduced. That reading is mine, not the docs'.
- `claude plugin validate` listing `env writes:` means a router that touches `ANTHROPIC_*` variables is visible to consumers before install, which fits the trust posture the README already documents for the guard hook.

### Gaps

- The subagents page remainder (characters 100,000-116,219) was not read; it may hold further plugin-agent restrictions.
- No official statement that marketplace-installed mods work on claude.ai/Cowork beyond the "`bin/` directory blocks install there" note.

## Key question 7: Safety and fail posture of hooks and mods

### Takeaway

Settings hooks fail open by default: non-zero exits other than 2, timeouts, and malformed JSON let the action proceed (except PreModelSwitch, where a timeout blocks the switch), and `onFailure: "block"` (v2.1.295+) flips a hook to fail closed. Mods also fail open by default — a hook that throws, times out (10 s), or returns the wrong shape is skipped and the action goes ahead — unless the registration carries a `.catch` handler that answers with the refusal; `claude plugin validate` flags gating hooks without one.

### Cited Findings

**Settings hooks**

- Exit codes: "Exit 0: Success"; stdout counts as JSON only if it is one JSON object. "Exit 2: Blocking error. The message that comes with the block is your hook's stderr." "Other exit codes: Non-blocking error. The action goes ahead." "Exit code 1 without valid JSON output is a non-blocking error." — [HOOKS](https://code.claude.com/docs/en/hooks)
- Malformed output: "When your hook exits 0 but prints JSON that can't be parsed or fails schema validation, the action goes ahead unless the hook is one whose failure blocks the action." `"onFailure": "block"` (v2.1.295+) "blocks the action on failure, timeout, or invalid output." — [HOOKS](https://code.claude.com/docs/en/hooks)
- Timeouts: "Defaults: 600 for `command`, `http`, and `mcp_tool`; 30 for `prompt`; 60 for `agent`." Lowered to 30 on UserPromptSubmit, PreModelSwitch, PostModelSwitch, and 10 on MessageDisplay; SessionEnd hooks share a 1.5-second budget. "On `PreToolUse`, a timed-out `command`, `http`, or `mcp_tool` hook doesn't block the tool call, except for hooks whose failure blocks the action." Async hooks: "Claude Code doesn't enforce `timeout` on async command hooks." — [HOOKS](https://code.claude.com/docs/en/hooks)
- Exception: "A PreModelSwitch hook that doesn't respond before its timeout blocks the switch." — [HOOKS](https://code.claude.com/docs/en/hooks)
- Misplaced fields: `permissionDecision`/`additionalContext` at the top level instead of inside `hookSpecificOutput` are "silently ignore[d] … without reporting an error"; see `claude --debug` for `Hook JSON output had unrecognized keys`. — [HOOKS-GUIDE](https://code.claude.com/docs/en/hooks-guide)
- Workspace trust: "Claude Code holds back hooks from every settings file, including your own `~/.claude/settings.json`, until you accept the workspace trust dialog"; "`-p` or SDK session: Claude Code never shows the dialog and treats the folder as trusted, so hooks committed in a repository's `.claude/settings.json` run in a folder you've never trusted". Mitigations: `--bare`, `--settings '{"disableAllHooks": true}'`. — [HOOKS](https://code.claude.com/docs/en/hooks)
- `disableAllHooks` and `allowManagedHooksOnly`: managed hooks still run unless `disableAllHooks` is set in managed settings. — [HOOKS-GUIDE](https://code.claude.com/docs/en/hooks-guide); [MODS-REF](https://code.claude.com/docs/en/plugins/mods/reference.md)

**Mods**

- "A hook that fails doesn't break the session … When a hook with no `.catch` handler throws, times out, or returns a result of the wrong shape … It failed before calling `next`: Claude Code skips it, and the next handler runs in its place. It failed after `next` resolved: that result stands, and nothing runs a second time." Fail-closed pattern: `on('tool.call', { tool: 'Bash' }, guard).catch(async ($, e, next) => { if (next.called) return next(e); return { deny: … + next.error.kind } })`. "If the handler itself throws or times out, Claude Code skips the hook as if it had no handler." — [MODS-EVENTS](https://code.claude.com/docs/en/plugins/mods/events.md)
- Limits: a hook's own execution time "10 seconds, or 50 milliseconds for a `prompt.edit` hook"; `.catch` handler "1 second"; "Claude Code skips a hook that exceeds a time limit." — [MODS-REF](https://code.claude.com/docs/en/plugins/mods/reference.md)
- `agent.spawn` specifically: "A guard that fails is skipped and the subagent starts, so give it `.catch(($, e, next) => next.called ? next(e) : { deny: "no" })`." — LOCAL-TYPES event doc; `tool.check` and `plugin.register` refusals "returned after `next` resolved still hold". — [MODS-EVENTS](https://code.claude.com/docs/en/plugins/mods/events.md)
- Validation surfaces the gap: "`gating hook without .catch: tool.call`"; CHANGELOG 2.1.290 "each hook a mod registers at a gating site is listed with whether it has a `.catch`". — [MODS-CREATE](https://code.claude.com/docs/en/plugins/mods/create); [CHANGELOG](https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md)
- Failure reporting: in a hot-reloading session "the transcript carries one dim line naming the plugin, the event and the reason when a hook fails"; elsewhere "those lines go to the debug log alone". — LOCAL-SKILL; [MODS-EVENTS](https://code.claude.com/docs/en/plugins/mods/events.md)
- Order and override: managed-settings `PreToolUse` hooks run before any mod's `tool.call`; other settings/plugin `PreToolUse` hooks "run after the last mod calls `next`, as part of Claude Code's own behavior. A mod that answers `tool.call` without calling `next` keeps them from running". With managed settings or a Team/Enterprise `/login`, "by default a mod's approval doesn't get a call past your `ask` rules or `PreToolUse` hooks. Without either, a mod can approve a call that an `ask` rule would prompt for, or that your `PreToolUse` hook blocked." — [MODS-EVENTS](https://code.claude.com/docs/en/plugins/mods/events.md); [MODS-OVERVIEW](https://code.claude.com/docs/en/plugins/mods/overview.md)
- Trust: "A mod is code that runs with your permissions. It can read and write your files, start processes, and make network requests." "Mods aren't sandboxed." "A mod can restyle much of Claude Code's interface, but not the permission prompt." — [MODS-OVERVIEW](https://code.claude.com/docs/en/plugins/mods/overview.md)
- Enterprise controls: `prependPlugins`/`appendPlugins`, `allowManagedModsOnly`, `allowModsToOverrideDenyRules`, `allowManagedHooksOnly`, `disableAllHooks`, `disableSideloadFlags`; the built-in guard `sec-default@builtin` loads first on managed machines. — [MODS-REF](https://code.claude.com/docs/en/plugins/mods/reference.md)
- Claude-written mods cannot load when "Nobody is there to approve" (`claude -p`, `dontAsk`), in an untrusted workspace, or when mods are disabled (`--safe-mode`, `--bare`, `disableAllHooks`, managed settings). — [MODS-CREATE](https://code.claude.com/docs/en/plugins/mods/create)

### Inferences

- A routing hook written as a settings `command` hook has the same default posture as this plugin's existing guard: missing config or a crash lets the Agent call proceed with Claude's own `model`/`effort`, which is the harmless direction for routing (the orchestrator's choice stands). Opting into `onFailure: "block"` would invert that and stall every subagent spawn on a hook bug.
- A mod-based router has an identical default (skipped on failure, subagent starts with the engine's own resolution) and an explicit opt-in to fail closed via `.catch`; for routing, fail-open is the correct choice and matches the engine's "unknown ⇒ proceed as before" semantics, whereas for *enforcement* (deny an expensive model) `.catch` returning `{ deny }` is the correct choice.
- Mods carry a materially broader trust surface than a Python hook (unsandboxed, full user permissions, can approve calls a PreToolUse hook blocked on unmanaged machines); a README trust-model paragraph would need to say so if this plugin ever ships one.

### Gaps

- The hooks reference's "Block the action when a hook fails" section was located only by cross-reference; its full text (which events honor `onFailure`) was not read verbatim.
- Whether `onFailure: "block"` applies to plugin-shipped `hooks/hooks.json` hooks identically to settings-file hooks is not stated in the text read.

## Key question 8: Consolidated limits — what hooks and mods cannot do

### Takeaway

Neither hooks nor mods can change `ANTHROPIC_BASE_URL` per subagent, and settings hooks cannot change any model or effort mid-session; mods can change model and effort per request but cannot set a subagent's effort at spawn, cannot bypass `CLAUDE_CODE_SUBAGENT_MODEL_FORCE`, cannot write `$.session.model`, and cannot restyle the permission prompt.

### Cited Findings

- Settings hooks: no `model` outside SessionStart; no token/cost fields outside the two cases above; `UserPromptSubmit` cannot replace the prompt; `PreModelSwitch` accepts no `updatedInput`; `SubagentStart` cannot block creation; hooks cannot invoke tools or slash commands. — [HOOKS](https://code.claude.com/docs/en/hooks); [HOOKS-GUIDE](https://code.claude.com/docs/en/hooks-guide)
- `CLAUDE_ENV_FILE` reaches only Bash commands (and plain-assignment PowerShell). — [HOOKS](https://code.claude.com/docs/en/hooks)
- Mods: `turn.step` rewrites only `model` and `effort` ("the rest is pinned"); `agent.spawn` rewrites only prompt/description/subagentType/model/background/cwd; the forced subagent model "outranks … a hook's"; `$.session.model()` is a getter; `$.ui` cannot change the permission prompt; drawing is absent under `claude -p`, SDK, and cloud sessions. — LOCAL-TYPES; [MODS-OVERVIEW](https://code.claude.com/docs/en/plugins/mods/overview.md)
- `$.env.set` can be held in managed sessions ("the engine holds a write a plugin that is not built in stands behind where a person's own settings file could not set the variable there"). — LOCAL-TYPES `EnvSetResult`
- Mods are "early access" and "the events and methods can change between releases, so trust these files over any page". — [MODS-CREATE](https://code.claude.com/docs/en/plugins/mods/create); LOCAL-TYPES header

### Inferences

- Per-subagent base URL routing would require a request-level field that does not exist in `turn.step`; the only documented knob is the process-wide `ANTHROPIC_BASE_URL` (plus a gateway), so provider routing per role is out of scope for both mechanisms today.
- A pragmatic split for a model-profile feature: ship tiered `model:`/`effort:` in plugin agents (zero runtime risk, works everywhere), use `CLAUDE_CODE_SUBAGENT_MODEL`/`_FORCE` as the consumer-side override, and treat a mod router as an optional, interactive-only enhancement whose absence changes nothing.

### Gaps

- No source was found that states whether Claude Code re-reads `ANTHROPIC_*` variables mid-session after `$.env.set`.
- The pre-2026 history of the `updatedInput` field (when it first shipped) is not dated in the CHANGELOG; the earliest entries found are the `ask`-compatibility fix and the `AskUserQuestion` support, both undated.
