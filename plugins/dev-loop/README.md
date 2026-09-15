# dev-loop

A supervised dev-loop engine for Claude Code. It works **one routed backlog issue per
invocation** — select → route → plan → architect → human gate → implement → commit/PR →
review → security → AC-verify → merge → journal — stopping by default for human approval of
every plan and every merge, and journalling to a durable ledger on disk so a fresh
invocation resumes correctly after `/clear` or compaction.

## Install

```
/plugin marketplace add frederick-douglas-pearce/claude-code-loop
/plugin install dev-loop@claude-code-loop
```

- `dev-loop` is the plugin id (from `plugin.json` `name`).
- `claude-code-loop` is the marketplace id (from `marketplace.json` `name`).

Then run `/init-loop` in the repo you want to onboard. The plugin does nothing until that
repo supplies a per-project config (`.claude/loop.config.md`) binding the gates to your
project's own commands, agents and backlog.

**Requires Python 3.9+** — for the append-only guard hook and the mutation harness the
acceptance gate runs. Both launch with bare `python3` and use only the standard library.
The engine itself is a prompt artifact and needs nothing installed.

## What it can do to your repo

This plugin can create branches, commit, open pull requests, and merge on your behalf.
**Read the full trust model — what is gated, what is enforced, and what the loop will never
do — in the repository README:**

<https://github.com/frederick-douglas-pearce/claude-code-loop#what-the-loop-can-do-to-your-repo>

That section is the single source of truth for the gating posture. It is deliberately not
restated here, so there is no second copy to go stale in your plugin cache.

## Documentation

Everything else — the architecture, the per-project config reference, the ledger format and
the test suite — lives in the repository:

<https://github.com/frederick-douglas-pearce/claude-code-loop>

## License

MIT — see `LICENSE`.
