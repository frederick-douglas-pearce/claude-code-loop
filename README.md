# claude-code-loop

A reusable **Claude Code plugin** that packages a battle-tested, supervised
**dev-loop engine** — the loop originally built and hardened in
[AgentFluent](https://github.com/frederick-douglas-pearce/agentfluent) (where it
ran the v0.10.x / v0.11.0 releases). Install it once, drop a small per-project
`loop.config.md` into a target repo, and run your backlog as a loop: one routed
issue per invocation, with human gates on uncertainty and durable ledger state.

> **Status: scaffold only.** This repo currently contains just the plugin +
> marketplace manifests and the directory layout (issue
> [#613](https://github.com/frederick-douglas-pearce/agentfluent/issues/613), S2).
> The engine (skill + `loop-engine.md` + guard hook), the `/init-loop`
> scaffolder, and full docs are ported/built in
> [#614–#617](https://github.com/frederick-douglas-pearce/agentfluent/issues/611).
> It does nothing useful yet.

## What "loop engineering" means here

This is a **structured, routed loop**, not a graph orchestrator: a single
supervised orchestrator handles **exactly one issue end-to-end per invocation**,
delegates to specialized agents (scope, design, AC-verify, code-review), gates on
human judgement when uncertain, and journals everything to a ledger that lives
outside the model's context so a fresh invocation resumes correctly. It is the
kind of well-instrumented loop that "graph engineering" treats as a single node.

## Layout

```
claude-code-loop/
├── .claude-plugin/
│   ├── plugin.json          # the plugin manifest (this dir holds ONLY manifests)
│   └── marketplace.json     # makes the plugin installable
├── skills/                  # SKILL.md + loop-engine.md land here (#614)
├── hooks/                   # append-only guard hook lands here (#614)
├── commands/                # /init-loop scaffolder lands here (#615)
├── LICENSE
└── README.md
```

## Install (once the engine is ported — not functional yet)

```
/plugin marketplace add frederick-douglas-pearce/claude-code-loop
/plugin install dev-loop@claude-code-loop
```

- `dev-loop` is the plugin id (from `plugin.json` `name`).
- `claude-code-loop` is the marketplace id (from `marketplace.json` `name`).

## Per-project config

Each consuming repo keeps a small `${CLAUDE_PROJECT_DIR}/.claude/loop.config.md`
(the ~40-line binding seam: `BACKLOG_SOURCE`, `SCOPE_AGENT`, `DESIGN_AGENT`,
`LINT_CMD`/`TYPE_CMD`/`TEST_CMD`, `BRANCH_FMT`, `COMMIT_CONV`, `MERGE_METHOD`, …).
The generic engine is never edited per-project — only the config. `/init-loop`
generates that config for a new repo (#615).

## License

MIT © 2026 Frederick Douglas Pearce
