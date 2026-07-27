# claude-code-loop

A reusable **Claude Code plugin** that packages a battle-tested, supervised
**dev-loop engine** — the loop originally built and hardened in
[AgentFluent](https://github.com/frederick-douglas-pearce/agentfluent) (where it
ran the v0.10.x / v0.11.0 releases). Install it once, drop a small per-project
`loop.config.md` into a target repo, and run your backlog as a loop: one routed
issue per invocation, with human gates on uncertainty and durable ledger state.

> **Status: engine ported + `/init-loop` scaffolder landed.** The generic engine
> is in place — the `dev-loop` skill (`SKILL.md` + `loop-engine.md`) and the
> append-only guard hook (wired via `hooks/hooks.json`) — ported from AgentFluent
> in [#614](https://github.com/frederick-douglas-pearce/agentfluent/issues/614)
> (S3), and the `/init-loop` onboarding command
> ([#615](https://github.com/frederick-douglas-pearce/agentfluent/issues/615), S4)
> now generates a starter `loop.config.md` for you. Still to come: a real
> dogfood/parity run
> ([#616](https://github.com/frederick-douglas-pearce/agentfluent/issues/616)),
> and the full docs / porting guide
> ([#617](https://github.com/frederick-douglas-pearce/agentfluent/issues/617)).
> Tracked under epic
> [#611](https://github.com/frederick-douglas-pearce/agentfluent/issues/611).

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
├── skills/
│   └── dev-loop/
│       ├── SKILL.md         # thin orchestrator entry point (reads the two below)
│       └── loop-engine.md   # the generic engine: pipeline + all semantics
├── hooks/
│   ├── hooks.json           # wires the PreToolUse guard via ${CLAUDE_PLUGIN_ROOT}
│   ├── guard_append_only.py # append-only guard (config-driven; stdlib only)
│   └── loop.append-guard.example.json  # sample per-project protection registry
├── tests/                   # stdlib unittest for the guard hook
├── commands/
│   └── init-loop.md         # /init-loop onboarding scaffolder (#615)
├── LICENSE
└── README.md
```

## Install

```
/plugin marketplace add frederick-douglas-pearce/claude-code-loop
/plugin install dev-loop@claude-code-loop
```

- `dev-loop` is the plugin id (from `plugin.json` `name`).
- `claude-code-loop` is the marketplace id (from `marketplace.json` `name`).

The plugin ships the engine and the guard hook; it does nothing until the
consuming repo supplies the per-project config below. Run `/init-loop` to
generate that config (or write it by hand).

**Requirements: Python 3.9+**, and only for the optional append-only guard hook
— the engine itself is pure prompt artifacts and needs nothing installed. The
hook is launched with bare `python3`, uses the standard library only, and is
tested on 3.9 through 3.13 in CI.

## Onboard a repo — `/init-loop`

From inside the target repo, after installing the plugin:

```
/init-loop
```

The command reads the repo's own conventions (`CLAUDE.md`, `pyproject.toml` /
`package.json` / `Cargo.toml` / `Makefile`, the PR template, CI workflows, branch
naming) and:

- generates a pre-filled `${CLAUDE_PROJECT_DIR}/.claude/loop.config.md` — inferred
  values in place, clearly-marked `TODO(init-loop)` blanks for anything it can't
  infer (correctness is yours to confirm at first-run review);
- if it finds a decision-log-style append-only file, generates a
  `loop.append-guard.json` sidecar (the machine SSOT) and echoes the entry IDs it
  matched so you can confirm the guard is live;
- adds the ledger dir (`.claude/loop/`) to `.gitignore` and creates it;
- wires `enabledPlugins: { "dev-loop@claude-code-loop": true }` into
  `.claude/settings.json` (or prints the snippet to paste if the file isn't a
  plain JSON object).

It is **safe to re-run**: it never overwrites an existing `loop.config.md` without
asking, and the `.gitignore` / `settings.json` / ledger steps are additive.

## Per-project config

Each consuming repo keeps a small `${CLAUDE_PROJECT_DIR}/.claude/loop.config.md`
(the ~40-line binding seam: `BACKLOG_SOURCE`, `SCOPE_AGENT`, `DESIGN_AGENT`,
`LINT_CMD`/`TYPE_CMD`/`TEST_CMD`, `BRANCH_FMT`, `COMMIT_CONV`, `MERGE_METHOD`, …).
The generic engine is never edited per-project — only the config.

### Optional: `loop.append-guard.json` (append-only protection)

The bundled `guard_append_only.py` hook protects append-only logs (e.g. a
decision log) from full-file `Write`s that would silently drop existing entries.
It is **config-driven and inert until configured**: it reads
`${CLAUDE_PROJECT_DIR}/.claude/loop.append-guard.json`, a JSON array declaring
which files to protect and the regex that identifies each file's entry IDs (see
`hooks/loop.append-guard.example.json`). No sidecar → the hook is a silent no-op;
a malformed sidecar → it allows writes but warns on stderr (so a typo can't
silently disable protection).

## License

MIT © 2026 Frederick Douglas Pearce
