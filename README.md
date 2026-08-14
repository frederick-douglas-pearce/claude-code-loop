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
├── tools/
│   └── mutate_verify.py     # mutation harness the acceptance gate runs by path (stdlib only)
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
surface, contested review findings, unresolved acceptance-gate findings of
either kind, and an unresolved offline-tier finding.
Wherever eligibility is unclear the rule is **default-deny**: fall back to the human.

**By default you approve every plan before any code is written.** The plan gate is a separate
setting from the merge gate — a `plan-gate:` field in the run's ledger header — set to `always` for
a new run under `calibration`, meaning the loop writes a plan, shows it to you, and stops, on
**every** issue. **This arrives with v0.2.0** — the released v0.0.1 has no `plan-gate:` field and
gates the plan only on uncertainty, so this paragraph describes the posture the next release ships
with, stated before it lands rather than after. Set the field to `conditional` and the loop stops
when it hits ambiguous acceptance criteria, risk, agent disagreement, a value story that doesn't
hold, or genuine uncertainty. The two settings are deliberately independent: relaxing how much of
the planning you review never loosens what gets merged without you, and a ledger that doesn't
mention the field at all is read as `always`. Neither setting reaches the loop's other mid-pipeline
stops — such as the architect-rewrite stop below, or a gate finding still there after one fresh
re-check, which stop and ask you regardless of both.

**When its design reviewer rewrites the plan, you see the plan.** One mid-pipeline stop is
unconditional — no mode setting, no `plan-gate:` value, and no route graduation can loosen it: if the architect review
**materially changed** the approach, the loop stops and shows you what changed before writing any
code. A reviewer that decides is treated as a stronger reason to interrupt you than one that hedges,
because the plan you would have approved is no longer the plan being built. The comparison is made
against a copy of the approach frozen before the review ran, so the loop is reading a record rather
than its own memory of what it had intended.

**A gate that did not run is never reported as one that passed.** For every gate the loop
runs — plan, architect, your build commands, code review, security, acceptance, merge — it may
record a pass only with
that gate's own output as evidence: **no verdict means not passed**. A binding you left blank in
`loop.config.md` is not a switch that turns the gate off; it makes the loop fall back to a built-in
equivalent where one exists, and otherwise stop and ask you. A gate that ran and *errored* never
falls back at all — the loop will not substitute a check of its own devising and call it clean; it
escalates. (A gate the route legitimately skips is journalled as *skipped*, which is also not a
pass.)

**A pull request appears before any review has run — that is the order, not a slip.** The loop
implements, then **immediately commits and opens the PR**, and only then runs code review, security,
and the acceptance gate. So an open PR on your repo means "the loop has reached the review gates",
never "the loop is finished with this and wants your merge." Nothing merges without the merge gate
below, and CI is green before review starts. **This arrives with v0.2.0** — the released v0.0.1
opens the PR after acceptance rather than before review, so this paragraph describes the posture the
next release ships with, stated before it lands rather than after.

Two consequences worth knowing. **The acceptance gate now runs last**, immediately before the merge
gate, so the diff it certifies is the diff that merges — under v0.0.1 it ran before review, and
every review round after it silently invalidated its verdict. And **no gate was removed** — the loop stops at the
same set of gates it always did. What changed is which one is last, and therefore what your repo
looks like when a stop happens: an acceptance-gate stop used to find no PR and no CI run, and now
finds a PR already open with CI green.

**The acceptance gate asks whether your tests would notice a regression.** It runs after code review
and security — the last gate before merge. It reports two kinds of
finding, kept separate and never added together: a criterion the change did not meet, and a **guard
that does not guard** — a test that would stay green even if the code it protects broke. The second
is protection you believe you have and do not, so the loop reports it as prominently as a bug. What
that means for your repo:

- **It only applies to `code`-route changes that alter behavior.** A `docs` or `research` route is
  out of scope entirely.
- **If such a change adds no test at all, the loop tells you.** That is read straight off the diff
  and is the one case that needs nothing run against your code at all.
- **Either kind of finding blocks.** It is treated like an unmet acceptance criterion — fixed and
  re-verified — and a row still carrying one is never eligible for auto-merge.
- **To check the rest, the loop breaks your code on purpose — in a copy.** This is the most
  invasive thing the plugin does, so it is worth being exact about. Where the change adds or
  modifies a test, a mutating agent takes a **throwaway copy of your tree**, makes a small edit that
  ought to break something, runs your test suite against it, and reports any test that stayed green.
  Your working tree is not the tree that gets broken — unless you explicitly allow it, which is the next point. **This arrives with v0.2.0** — the released
  v0.0.1 has no mutation pass at all, and the paragraph you are reading is the posture the next
  release ships with, stated before it lands rather than after.
- **If the copy cannot run your suite, the loop stops and asks you.** A bare copy has none of your
  installed dependencies, so this is the common case rather than an exotic one. Mutating your *real*
  working tree is the fallback and is **never taken on the loop's own judgement**. If you decline,
  the gate records that it could not run — it never records a clean result, because "we checked and
  found nothing" and "we could not check" must not look alike. On that path every file is restored
  from a snapshot taken before it was touched, **never from git**, which would throw away
  uncommitted work the mutation never touched.
- **Every pass that mutates anything journals whether it gave the tree back**, and a pass that
  cannot restore reports that as its most severe outcome, ahead of any finding. A pass that ends up
  applying **no** mutation is an error rather than a quiet success — otherwise a check that found
  nothing and a check that did nothing would report the same clean result, which is the exact
  confidence this gate exists to refuse.

**An agent that writes to your tree gets a copy of it, not yours — so the loop may create and remove
git worktrees under your repository.** This is live now and is not limited to the mutation testing
above: your working tree holds your uncommitted work, so any subagent that needs to write gets its
own copy. Two things to expect. The copy is typically created **inside your repository** — where your
host puts it is the host's choice, not this plugin's — and while it is there it shows up as an
untracked directory in `git status`. It is not gitignored for you, and if you gitignore it yourself,
be aware the loop then has one fewer way to notice a stray one. And
**the loop is responsible for removing it**: your host only auto-cleans a copy the agent never wrote
to, which is never the case that matters, so removal is an instruction the loop follows rather than a
guarantee something enforces. An iteration that dies partway can leave one behind; `git worktree
list` will show it — and **as of v0.2.0 the loop sweeps for one itself on every resume**, before it
touches the tree.

**If the loop crashes late in an iteration and then resumes, it will no longer silently keep
uncommitted changes in your tree that it cannot account for.** **This arrives with v0.2.0** — the
released v0.0.1 does none of it, so do not read the protection below as live on an installed
v0.0.1. It reverses the older behavior,
which kept anything that "looked like it matched the plan" — a bad default once the loop's own
acceptance gate started deliberately breaking code, because a mutation is built to look like a small,
sane edit and "it looks plausible" is precisely the test it is designed to pass. Two things happen,
and it is worth being exact about which is which.

**On every resume, the loop looks for the marks of a mutation pass that did not finish** — a stray
worktree copy, or a retained snapshot directory. If it finds them it repairs from its own
pre-mutation snapshots, **never from git**, touching only the files it can attribute; and if those
snapshots are gone, it **stops and asks you** rather than improvising a repair.

**Separately, when it resumes a row that was in review or acceptance, a change to your code it cannot
attribute is neither kept nor discarded — it stops and asks you.** This is the case most likely to
involve your work, so the loop is not permitted to resolve it alone: not keeping something and
destroying it are different actions, and only you choose the second. **Resuming an interrupted
implementation is unchanged** — work in progress that belongs to the plan is kept, and being
half-finished is never on its own a reason to discard it. **The practical protection is the ordinary
one** — commit or stash work you care about before leaving an
iteration mid-flight, since a committed change is attributable by definition.

**If you bind a command for your offline test tier, the loop runs it and treats a failure as a bug.**
Where `HERMETIC_TEST_CMD` names one, any `code`-route change that adds or modifies a test runs that
tier once. A test that passes normally and fails there is reported as a bug rather than as flake —
it was passing for the wrong reason, quietly exercising a live resource instead of your fixture —
and the loop fixes it and re-runs the tier. If instead the **block itself** could not be applied (no
namespace, tool missing), nothing was learned about your tests, so the loop stops and hands you the
failure rather than rewriting a test to satisfy a block that never ran. You supply the blocking mechanism — the loop reads
an exit status and cannot see *how* you blocked, so the requirement that the block be socket-level
(a proxy still resolves DNS) is one you check once when writing the binding, not one the loop
enforces. `/init-loop` may draft the value for you and flag it for confirmation; confirming it is
yours to do. **No such tier? Say so explicitly** — bind `—` plus a reason and the gate records
itself as not applicable. Leaving the row off is not the same thing: on a change that would have run
the gate, the loop cannot tell "no tier" from "a tier I was not told about", so it stops and asks
you rather than assuming.

**A fix is never checked by whoever wrote it.** When the loop fixes what a gate found — the
acceptance gate above, or code review, on any route — a freshly spawned checker decides whether the
fix worked: not the thread that wrote it, and not the checker that raised the finding. Each such
gate gets **one** re-check; if it comes back dirty the loop stops and asks you, rather than
iterating on itself.

**Hard limits the engine commits to:**

- **One PR at a time** — no stacked PRs.
- **Never force-push.**
- **Never bypass failing CI** — no admin-merge, never merge red.
- **Only `--delete-branch` the PR's own branch.**
- **Never blanket-stage** (`git add -A`/`git add .`) and never `git add` unrelated pre-existing
  working-tree changes. It stages explicit paths and reads back what it staged before each commit.
- **Never stage or commit while a subagent's isolated copy of your tree is live** — that window
  closes when the loop removes the copy, not when the agent finishes.
- **Never edit your user-global subagent definitions.**
- **Never edit its own `loop.config.md`** — a binding that looks wrong gets journalled and handed to
  you, so the loop can't quietly rewrite its own gates to match its reading of them.

**The ledger is local and never committed.** Working state (`queue.md`, `progress.md`,
`issue-<N>.plan.md`) is written under `.claude/loop/` in your repo, which `/init-loop`
adds to `.gitignore`. It lives on disk so a fresh invocation resumes correctly after a
`/clear`, and it stays out of your history.

**It runs your commands, not ours.** `LINT_CMD` / `TYPE_CMD` / `TEST_CMD` /
`HERMETIC_TEST_CMD` / `CI_STATUS_CMD` are whatever your own `loop.config.md` names — the
plugin ships no commands of its own and executes what that file tells it to. One of
those deserves singling out: **`HERMETIC_TEST_CMD` is the only binding whose value is
expected to restrict the environment** — it runs your declared offline test tier with
the network cut, so a plausible value wraps your test command in a sandbox or network
namespace (`unshare -rn …`, `firejail --net=none …`, a socket-blocking test plugin).
The loop supplies no blocking mechanism of its own, cannot tell whether the one you
named blocks at socket level, and will run whatever you wrote. Leave the binding as
`—` plus a reason and the gate is simply not run.

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
  infer (correctness is yours to confirm at first-run review). A leftover `TODO`
  on a gate binding is not inert: see the gating posture above. **One row is an
  exception worth checking by hand: `HERMETIC_TEST_CMD` fails *open*** — where it
  finds no declared offline tier it writes `—`, not a `TODO`, because a tier can
  be declared in prose the generator never reads, and `—` is read as a clean
  not-applicable and never asked about again;
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
`LINT_CMD`/`TYPE_CMD`/`TEST_CMD`/`HERMETIC_TEST_CMD`, `BRANCH_FMT`, `COMMIT_CONV`,
`MERGE_METHOD`, …).
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
  composed from, that every `CAPS` parameter the engine reads is offered by
  the `/init-loop` skeleton, and that the pipeline's step order still agrees
  across the six places it is restated.

What the suite does **not** test is whether the prompt artifacts say the *right*
thing. The engine is ~600 lines of instructions an agent executes at runtime, and
its correctness properties — precision of wording, internal consistency,
fail-safe posture — are validated by review and by running the loop on real
backlogs. The second module guards couplings between files, not semantics.

## License

MIT © 2026 Frederick Douglas Pearce
