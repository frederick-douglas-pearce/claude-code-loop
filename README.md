# claude-code-loop

A reusable **Claude Code plugin** that packages a battle-tested, supervised
**dev-loop engine** — the loop originally built and hardened in
[AgentFluent](https://github.com/frederick-douglas-pearce/agentfluent) (where it
ran the v0.10.x / v0.11.0 releases). Install it once, drop a small per-project
`loop.config.md` into a target repo, and run your backlog as a loop: one routed
issue per invocation, with human gates on uncertainty and durable ledger state.

> **Status — v0.0.1, working and in use, not yet stable.** All three pieces are in
> place: the `dev-loop` skill (`SKILL.md` + `loop-engine.md`), the `/init-loop`
> onboarding command, and the append-only guard hook. The engine has run beyond the
> repo it was built in — first external adoption is
> [us-presidential-vote-analysis](https://github.com/frederick-douglas-pearce/us-presidential-vote-analysis),
> alongside the ongoing AgentFluent dogfood.
>
> Findings from those real runs are indexed in
> [#1](https://github.com/frederick-douglas-pearce/claude-code-loop/issues/1) (F1–F21) and
> scoped into
> [v0.2.0](https://github.com/frederick-douglas-pearce/claude-code-loop/milestone/1) —
> a hardening release that makes the acceptance gate adversarial, moves it last so it
> certifies the commit that actually merges, and reverses the plan-gate default under
> `calibration`. Expect rough edges in porting to a repo unlike the two above; that is
> exactly what #1 collects.
>
> **Issues for this plugin live in
> [this repo's tracker](https://github.com/frederick-douglas-pearce/claude-code-loop/issues).**
> The AgentFluent links in this README are **provenance, not the live backlog** — the
> extraction stories (S2–S4, under epic
> [#611](https://github.com/frederick-douglas-pearce/agentfluent/issues/611)) were filed
> there before this repo existed.

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
├── commands/
│   └── init-loop.md         # /init-loop onboarding scaffolder
├── tests/                   # stdlib unittest suite (no pytest, no dependencies)
├── .github/workflows/       # CI: the suite on Python 3.9-3.13
├── LICENSE
└── README.md
```

## What the loop can do to your repo

Worth reading before you install. This plugin drives a real development workflow on
your behalf: it creates branches, commits, opens pull requests, runs your project's
lint/type/test commands, merges, and deletes the merged branch. Here is the posture it
takes while doing that.

**The default is human-gated.** The loop runs in `mode: calibration` unless you change
it, and in that mode **the human approves every merge — it never auto-merges.**
Auto-merge exists only under the opt-in `escalation-only` mode, and even there it is
per-route, limited to routes you have explicitly *graduated*, and withheld for feature
or breaking changes, risky or irreversible changes, anything touching a security
surface, and contested review findings. Independently of mode, the loop stops and asks
you mid-pipeline when it hits ambiguous acceptance criteria, risk, agent disagreement,
or genuine uncertainty. Wherever eligibility is unclear the rule is **default-deny**:
fall back to the human.

**A gate that did not run is never reported as one that passed.** For every gate the loop
runs — plan, architect, acceptance, code review, security, merge — it may record a pass only with
that gate's own output as evidence: **no verdict means not passed**. A binding you left blank in
`loop.config.md` is not a switch that turns the gate off; it makes the loop fall back to a built-in
equivalent where one exists, and otherwise stop and ask you. A gate that ran and *errored* never
falls back at all — the loop will not substitute a check of its own devising and call it clean; it
escalates. (A gate the route legitimately skips is journalled as *skipped*, which is also not a
pass.) **Upgrading from an earlier version:** if a previous `/init-loop` told you to *delete* a
binding row that didn't apply to your repo, restore it as `—` plus a reason — an absent row now
reads the same as a blank one, and blanks escalate.

**Hard limits the engine commits to:**

- **One PR at a time** — no stacked PRs.
- **Never force-push.**
- **Never bypass failing CI** — no admin-merge, never merge red.
- **Only `--delete-branch` the PR's own branch.**
- **Never `git add` unrelated pre-existing working-tree changes** in your working tree.
- **Never edit your user-global subagent definitions.**
- **Never edit its own `loop.config.md`** — a binding that looks wrong gets journalled and handed to
  you, so the loop can't quietly rewrite its own gates to match its reading of them.

**The ledger is local and never committed.** Working state (`queue.md`, `progress.md`,
`issue-<N>.plan.md`) is written under `.claude/loop/` in your repo, which `/init-loop`
adds to `.gitignore`. It lives on disk so a fresh invocation resumes correctly after a
`/clear`, and it stays out of your history.

**It runs your commands, not ours.** `LINT_CMD` / `TYPE_CMD` / `TEST_CMD` /
`CI_STATUS_CMD` are whatever your own `loop.config.md` names — the plugin ships no
commands of its own and executes what that file tells it to.

**How the limits are enforced.** Be clear-eyed about this: the human gates and the
append-only guard hook are *enforced backstops*, while the rest of the list above is
**instruction the orchestrating agent is bound by, not a sandbox**. If you want a hard
boundary rather than a diligent one, use Claude Code's own permission settings — the
skill deliberately runs with the full session toolset, because an orchestrator needs
git, `gh`, and subagents to do the job at all.

**The guard hook's trust model.** The bundled hook compiles `id_pattern` from
repo-local, committed config — the same trust level as a Makefile or a git hook, not
attacker-controlled input. Its scope is deliberately bounded: it protects **entry
existence against full-file `Write`s only**. It does not guard `Edit`, and it does not
cover `Bash` redirection (`cat > file`, `tee`, `sed -i`), which an agent with Bash could
still use to clobber a file. It is a durable guard against one specific data-loss mode,
not an any-tool guarantee.

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
  infer, and an explicit `—` plus a reason where a parameter genuinely doesn't
  apply (correctness is yours to confirm at first-run review). A leftover `TODO`
  on a gate binding is not inert: see the gating posture above;
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

## Development

```bash
python3 -m unittest discover -s tests
```

No install step, no virtualenv, no dependencies — the suite is **stdlib `unittest`
only**, because the guard hook runs under bare `python3` in a consumer's
environment and the tests have to run wherever it does. CI runs exactly that
command on Python 3.9–3.13 for every pull request.

Two modules, covering deliberately different things:

- `test_guard_append_only.py` — behavior of the guard hook: drop detection, the
  suffix matcher, the config loader, and each direction of the fail posture.
- `test_repo_consistency.py` — mechanical checks on the shipped artifacts: that
  the example sidecar still loads through the real loader, that the
  `dev-loop@claude-code-loop` identifier still matches the manifests it is
  composed from, and that every `CAPS` parameter the engine reads is offered by
  the `/init-loop` skeleton.

What the suite does **not** test is whether the prompt artifacts say the *right*
thing. The engine is ~600 lines of instructions an agent executes at runtime, and
its correctness properties — precision of wording, internal consistency,
fail-safe posture — are validated by review and by running the loop on real
backlogs. The second module guards couplings between files, not semantics.

## License

MIT © 2026 Frederick Douglas Pearce
