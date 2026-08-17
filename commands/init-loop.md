---
description: Onboard the current repo to the dev-loop — infer and generate loop.config.md, wire the ledger + plugin settings. Best-effort inference; you confirm the result before the first run.
---

# /init-loop — onboard this repo to the dev-loop

You are onboarding the **current target repo** (`${CLAUDE_PROJECT_DIR}`) to the `dev-loop`
plugin. You read the repo's own conventions, generate a pre-filled per-project
`loop.config.md`, and wire up the ledger + plugin settings — so the human never hand-copies the
harness. **Inference is best-effort; the human confirms correctness at first-run review.** Favor
a clearly-marked `TODO(init-loop)` over a wrong guess.

## Fail-safe invariants (hold before you touch anything)

Guards in a prompt are advisory — state them to yourself first so a partial run **over-guards**:

- **Never overwrite an existing `loop.config.md`.** If it exists, STOP the generate path, tell the
  human, and offer a `.init-new` sibling for manual diff. Do not clobber their edits.
- **Every mutation is additive / idempotent.** Re-running must never duplicate a `.gitignore`
  line, reorder `settings.json` keys, or wipe an existing artifact. Check presence before writing.
- **Prefer `TODO(init-loop)` over a guess.** A blank the human must fill beats a plausible-wrong
  value that runs silently.
- **Only ever add `enabledPlugins["dev-loop@claude-code-loop"] = true`** to `settings.json`;
  preserve every other key verbatim. If the file is present but not parseable as a JSON object,
  do **not** edit it — emit the snippet and let the human paste.

Let `TARGET = ${CLAUDE_PROJECT_DIR}` throughout. Artifacts:
- `CONFIG   = $TARGET/.claude/loop.config.md`
- `GUARD    = $TARGET/.claude/loop.append-guard.json`
- `SETTINGS = $TARGET/.claude/settings.json`
- `LEDGER   = $TARGET/.claude/loop/`

---

## Step 0 — Preflight

Resolve `TARGET` (fall back to `git -C . rev-parse --show-toplevel` if `${CLAUDE_PROJECT_DIR}` is
unset). Confirm it is a git repo; if not, STOP and tell the human `/init-loop` expects a git repo
root. **If `${CLAUDE_PROJECT_DIR}` was unset, `export CLAUDE_PROJECT_DIR="$TARGET"`** — but do not
rely on it reaching Steps 6–7: by Step 4's rule 2 their paths were expanded before you read this
file, and shell state does not survive between commands either way. If those blocks came to you with
an empty path, their own guards will refuse to run; **re-issue them with `$TARGET` substituted for the
empty path**, and say at Step 8 that you did. `mkdir -p "$TARGET/.claude"`. Record which of `CONFIG`,
`GUARD`, `SETTINGS`,
`LEDGER`, and `$TARGET/.gitignore` already exist — this drives idempotency below.

## Step 1 — Idempotency gate

If `CONFIG` exists: **do not regenerate it.** Report that the repo already has a `loop.config.md`,
and ask whether to (a) leave it and only run the additive steps (5–7), or (b) write a fresh
inference **only to a `loop.config.md.init-new` sibling — never to `CONFIG` itself** — for the
human to diff and merge by hand. Either way, still run the additive steps (ledger dir,
`.gitignore`, `settings.json`) — they are safe to repeat. Skip the generate path (Steps 2–4)
unless the human opts into the `.init-new` refresh.

## Step 2 — Inference pass (best-effort)

Read whatever exists (skip missing files silently): `CLAUDE.md`, `AGENTS.md`, `CONTRIBUTING.md`,
`pyproject.toml`, `package.json`, `Cargo.toml`, `go.mod`, `Makefile`, `.github/workflows/*.yml`,
`.github/PULL_REQUEST_TEMPLATE.md`. Also run `git remote -v` and `git branch -a` for host + branch
conventions. Infer the §1 parameters below. Put **how you inferred each value** in the Notes
column (e.g. "from pyproject `[tool.pytest]`"); leave anything you cannot infer as
TODO(init-loop): <what to supply> — written bare, per Step 4's rule 4.

**Inference map (cross-ecosystem — do not assume Python/GitHub):**

| Parameter | Look here |
|-----------|-----------|
| `TEST_CMD` | pyproject/`tox`, `package.json` scripts (`test`), `Makefile` (`test:`), `Cargo.toml`, CI workflow steps |
| `LINT_CMD` | ruff/flake8/eslint/clippy/golangci config; `lint` script; CI. Same rule as `TYPE_CMD` below: if there is none, `—` **plus a reason** |
| `TYPE_CMD` | mypy/pyright config, `tsc`, `package.json` `typecheck`; where the language has no separate type step write `—` **plus the reason** (e.g. `— (no separate type step)`), never a bare dash — the engine reads a reasonless `—` as a blank and escalates on it |
| `HERMETIC_TEST_CMD` | **First, whether an offline/hermetic tier is *declared* at all.** Signals are ecosystem-specific: prose in `CLAUDE.md`/`CONTRIBUTING`/README ("unit tests are offline — no network or DB"); Python — a marker or `addopts` exclusion (`-m 'not integration'`), split `tests/unit` vs `tests/integration`, a tox env; Go — `testing.Short()` with `-short`, or a `//go:build !integration` tag (the canonical Go form); Node — a `test:unit` script, `jest --testPathIgnorePatterns`, `nock.disableNetConnect()`; Rust — `cargo test --lib` vs `tests/`, `#[ignore]`; any ecosystem — a `test-unit`-style `Makefile` target or a CI job named for it. **If none is declared, emit `—` plus the reason "no offline/hermetic tier declared"** — the common case, and see the fail-open note below. If one *is* declared, the value is that tier's command wrapped in a socket-level block: prefer a blocker already in the project (`pytest --disable-socket`); otherwise on a **Linux** host propose `unshare -rn -- sh -c 'ip link set lo up && <the tier's command>'` — a fresh network namespace, which is language-agnostic and needs no test-framework support. **Do not drop the `ip link set lo up`:** a fresh netns has loopback DOWN, so `connect()` to `127.0.0.1` fails and every test using a local server, socket or TCP database breaks — which the engine would then report as a bug rather than an environment fault, the one false positive it is least able to dismiss. Note in the Notes that `ip` is iproute2 (absent from minimal images — `ifconfig lo up` is the fallback), that `-r` runs the tier as **uid 0**, and that the human must confirm the value. If a tier is declared and you can find no workable block, emit TODO(init-loop), **never `—`** |
| `CI_STATUS_CMD` | `gh pr checks <PR>` if GitHub host; else the host's equivalent or TODO(init-loop) |
| `BRANCH_FMT` | CLAUDE.md / CONTRIBUTING branch rules; else infer from existing `git branch -a` names |
| `COMMIT_CONV` | CONTRIBUTING / CLAUDE.md; detect Conventional Commits from recent `git log` if unstated |
| `PR_TEMPLATE` | `.github/PULL_REQUEST_TEMPLATE.md` (note "must replicate" if present) |
| `MERGE_METHOD` | CONTRIBUTING / repo settings; default TODO(init-loop) |
| `BACKLOG_SOURCE` | GitHub milestone/label if a GitHub remote exists; else a local `TODO.md`; else TODO(init-loop) |
| `PRIORITY_LABELS` | `gh label list` for `priority:*` labels (GitHub host); else CONTRIBUTING/CLAUDE.md; else TODO(init-loop) |
| `RELEASE_SCHEME` | release-please / semantic-release config, `pyproject`/`package.json` version + publish; else "no release cycle" |
| `SCOPE_AGENT` / `DESIGN_AGENT` | user-global subagents — cannot be inferred from the repo; default TODO(init-loop): name a scope/design subagent, or remove if none |

> **Backticks in the "Look here" column are this table's notation, not part of any value.** Where a
> row says to emit a `TODO(init-loop)`, write it into `CONFIG` **bare** — Step 4's rule 4, and the
> reason it exists. The defect that rule fixes was built exactly here: a generator composed a cell out
> of two fragments from this column and produced `` `TODO(init-loop): … a local `TODO.md` …` ``, an
> outer code span wrapped around an inner one, which does not nest and rendered as garbage.

> ⚠ **`HERMETIC_TEST_CMD` is the one row where the generator fails *open*, and the human reviewing
> this config is the only thing that catches it.** Emitting `—` says "this project declares no
> hermetic tier", which the engine reads as a clean not-applicable and never asks about again. But
> the generator cannot distinguish *no tier is declared* from *a tier is declared somewhere I did not
> look* — the declaration is prose, and it may sit in a README section, a test docstring, or a
> reviewer's habit rather than in any file listed above. Every other unfillable row escalates; this
> one goes quiet. **So check this row specifically** rather than skimming it: if your project claims
> anywhere that some tests run offline, the `—` is wrong and the gate you want is off.

## Step 3 — Detect an append-only file (for the guard)

Best-effort scan for a decision-log / changelog-style markdown whose entries are repeated
`## <ID>` headers (e.g. `docs/decisions.md`, `.claude/specs/decisions.md`, `DECISIONS.md`,
`CHANGELOG.md`). If you find one:
- `suffix` = its repo-relative path.
- `id_pattern` = a regex with **exactly one capture group** for the entry ID, e.g. for `## D001`
  headers: `^##\s+(D\d+(?:-[A-Za-z0-9]+)?)`. In JSON the backslashes double: `"^##\\s+(...)"`.
- Run the pattern against the file and **collect the matched IDs** — you will echo them in the
  summary so the human can confirm the guard actually matches (0 matches ⇒ it protects nothing).

If you find nothing (or are unsure), do **not** invent a sidecar — leave `APPEND_ONLY_FILES` as a
`TODO(init-loop)` in the config and skip Step 5's write.

## Step 4 — Generate `loop.config.md`

Write `CONFIG` from the skeleton below, substituting inferred values and `TODO(init-loop)`
placeholders. Keep all five sections. §1 is cross-ecosystem — fill it. §3 is lightly inferable
(source layout) — fill what you can. **§2 and §4's routing rules are the project-specific porting
surface** — emit them as stubs with the commented AgentFluent example so the human sees the shape.
**§4 additionally carries a live `### ⛔ Precondition` block: it is uncommented, mandatory prose that
must be copied into the generated config as-is. It is not a stub — never comment it out, and never
drop it at generation time.** It is git-specific, not host-specific, so it survives a non-GitHub host;
the block tells the *human* when they may remove it at first-run review, and that decision is theirs,
not yours. If the host is **not** GitHub, add a one-line TODO(init-loop) note (bare, per rule 4) in §4
flagging that every **routing rule** there is a GitHub-ism to be re-specified — the precondition block
is not one of them.

### Four rules about what you write into `CONFIG`

These govern the *text* you emit, independently of any value you inferred in Step 2. Rules 1 and 2
are two halves of one problem and are easiest to read together.

**1. `@@PLUGIN_ROOT@@` is a token you expand yourself.** The skeleton's pointer line reads
`See @@PLUGIN_ROOT@@/skills/dev-loop/loop-engine.md …`. Replace `@@PLUGIN_ROOT@@` — and nothing else
on that line — with a **plugin-root variable reference**, which you compose from four pieces in this
order: a dollar sign, an opening brace, the name `CLAUDE_PLUGIN_ROOT`, a closing brace. It is spelled
out in pieces rather than shown assembled because an assembled one would not have survived the trip
to you — which is rule 2. `@@PLUGIN_ROOT@@` is **not** a `TODO(init-loop)` and **not** a `<…>`
fill-in: do not infer a value for it, do not ask the human about it, and do not leave it in place.

**2. Any absolute path you were handed is an artifact of delivery, not content to copy.** The harness
substitutes environment variables into this command's text **before you read a word of it**,
including inside backtick code spans. So wherever this file writes a project-dir variable, what
arrived in your prompt is already an absolute path — and wherever a plugin-root variable is written,
you would have received something like
`/home/<user>/.claude/plugins/cache/<marketplace>/<plugin>/<version>/skills/…` instead. **Do not
reproduce a plugin-cache path in `CONFIG`; reverse it** to the variable reference of rule 1. (For
project paths, see rule 3: write them repo-relative, never absolute.) Rule 1 is why no *expanded*
plugin-cache path should reach you from this file today — `@@PLUGIN_ROOT@@` cannot be expanded, so the
skeleton's pointer line arrives intact. The rule still binds for any such path you meet elsewhere,
including one you carry forward into a `.init-new` refresh; but **never edit an existing `CONFIG` in
place to fix one** — report it to the human at Step 8 instead (the never-overwrite invariant).

**3. A generated `loop.config.md` contains no absolute path into the plugin cache.** The plugin's
install location is a fact about *this machine and this version*: it moves at every upgrade and
differs for every user. `CONFIG` is a project-scoped file that gets committed. A cache path written
into it is wrong the moment the plugin is upgraded, and wrong immediately for anyone else who clones
the repo. **Relative** paths into the consuming project (`src/`, `.claude/loop/`) are fine — that is
what the skeleton uses; absolute ones are machine-specific for the same reason and are not, and paths
into the plugin are never.

**4. A `TODO(init-loop)` value is never written inside a code span.** Write it bare, with no
surrounding backticks. The explanatory text that follows one routinely names a file or a command
(`a local TODO.md`, `gh label list`) — and markdown code spans **do not nest**, so an outer span
wrapped around an inner one terminates early and the remainder of the cell renders as garbage. The
human reviewing `CONFIG` before the first run is the only control on every blank in it, so a `TODO`
that renders as garbage is a blank that never gets filled. This rule is about a `TODO(init-loop)`
written as a parameter's **value**; naming the marker in prose, as this sentence does, is not a value
and needs no change.

> **Maintainers of this file** (not part of an onboarding run): write any pipeline cross-reference
> in the skeleton as **`engine step N`**, including the literal word "engine" — the `CODE_REVIEW`
> row uses it today. A bare `step N` is indistinguishable from this file's own numbered onboarding
> headings, which resolve to real engine step numbers too, so nothing would catch a stale one. Add
> references freely in that form, bumping `_EXPECTED_INIT_LOOP_STEP_REFERENCES` in
> `tests/test_repo_consistency.py` in the same change; write `N` rather than a digit in any
> illustrative example, which the same count would otherwise pick up. A reference you add **inside**
> the skeleton bumps `_EXPECTED_SKELETON_STEP_REFERENCES` as well; one in surrounding prose bumps
> only the total. **At least one reference must
> stay inside the `~~~markdown` skeleton** — that block is the only part of this file copied into a
> consuming repo, so a reference that drifts out into surrounding prose stops guarding anything that
> ships, and a check enforces it.
>
> Second, **never write an environment-variable reference into the skeleton** — not the plugin-root
> one, not the project-dir one — because the harness expands them before the generating agent reads
> this file, so the agent copies the expansion into the config it writes. For the plugin-root variable
> that means an absolute, version-pinned cache path that stops resolving at the next plugin upgrade;
> for the project-dir one it means an absolute path that is wrong for every other clone of the repo.
> This is not hypothetical: it is what produced
> [F20](https://github.com/frederick-douglas-pearce/claude-code-loop/issues/1), and a config already
> in the field carries such a path today. Use an `@@…@@` token instead and give it an expansion rule
> in Step 4's rule 1, which is what `@@PLUGIN_ROOT@@` is. **Nothing checks this one** — unlike the
> step-reference rule above, it rests on you reading this note.

For the `APPEND_ONLY_FILES` row use the **pointer form**, never a duplicated path — the sidecar
JSON is the single source of truth for which files are protected:

~~~markdown
# Loop config — <REPO NAME>

Per-project bindings for the supervised dev loop. `loop-engine.md` (the generic engine, bundled in
the plugin) references every value below **by parameter name**; this file is the only surface a
porting project edits. A non-matching (non-Python / non-`src/` / non-GitHub) project revises **all
four sections** (parameters, architect triggers, source layout, security routing) — never the
engine.

See `@@PLUGIN_ROOT@@/skills/dev-loop/loop-engine.md` for the operating procedure and semantics.

> ⚠ **Generated by `/init-loop` — review before the first run.** Values are best-effort inferences;
> every `TODO(init-loop)` is a blank you must fill (or delete if it does not apply to this repo).

---

## 1. Project parameters

The binding table. The engine names each parameter in `CAPS`; the values here are this repo's.

> ⚠ **A `TODO(init-loop)` is a blank that escalates — not a switch that turns its gate off.** The
> engine journals a gate as passed only with the gate's own verdict as evidence (**no verdict ⇒ not
> passed**), so an unfilled binding does not quietly skip the gate: it falls back to the engine's
> inline composition where one is defined, and otherwise **stops the run and asks you**. That is the
> rule for the rows naming a **gate**; the rest of the table is read where it is used, so a `TODO`
> there fails later, at the command that needed it. Where a parameter genuinely does not **apply**,
> write `—` plus the reason — a deliberate "not applicable", which is not the same as a blank.

| Parameter | Value | Notes |
|-----------|-------|-------|
| `BACKLOG_SOURCE` | <inferred / TODO(init-loop)> | GitHub milestone/label, or a local `TODO.md` |
| `SCOPE_AGENT` | <TODO(init-loop): user-global subagent, or remove if none> | answers scope/priority/requirements questions |
| `DESIGN_AGENT` | <TODO(init-loop): user-global subagent, or remove if none> | reviews plans pre-implementation |
| `CODE_REVIEW` | parallel finder subagents over `git diff main...HEAD` **+ the issue's acceptance criteria**, angles chosen per the diff's risk surface (engine step 8), then a pass confirming each finding | the orchestrator runs this itself — the finder fan-out is the engine's inline default and the binding this repo keeps. A porting project may bind a different review procedure here, but only one the orchestrator can actually invoke: a skill marked `disable-model-invocation` is user-triggered only, so keep such skills as a human escalation, never a binding. A gate bound to something it cannot invoke is never journalled passed — the orchestrator falls back to the inline fan-out, records a `- gate-fallback:` line, and surfaces the misbinding to you (engine Gate-outcome invariant) |
| `SECURITY_REVIEW` | <TODO(init-loop): local `/security-review` and/or a labeled workflow> | see §4 |
| `VERIFY` | `/verify` (built-in) | runtime behavior check when an AC needs proof-by-running |
| `PRIORITY_LABELS` | <inferred / TODO(init-loop)> | drives selection order; e.g. `priority:high > medium > low`, tiebreak issue number asc |
| `ARCHITECT_TRIGGERS` | see §2 | **project-specific — edit when porting** |
| `SOURCE_LAYOUT` | see §3 | router uses this; **edit when porting** |
| `TEST_CMD` | <inferred / TODO(init-loop)> | |
| `LINT_CMD` | <inferred / — + reason if none> | a bare `—` with no reason is a blank, not a "not applicable" |
| `TYPE_CMD` | <inferred / — + reason if none, e.g. `— (no separate type step)`> | a bare `—` with no reason is a blank, not a "not applicable" |
| `HERMETIC_TEST_CMD` | <the declared offline tier wrapped in a socket-level block / `—` + "no offline/hermetic tier declared"> | runs at engine step 6 on a `code`-route change that adds or modifies a test. **If this says `—`, confirm it** — the generator writes `—` whenever it found no declared offline tier, and it only read the files the onboarding run listed; if anything in this repo claims some tests run offline, the `—` is wrong and the gate is off. **Never delete this row:** an absent row reads as unknown and stops the run — write `—` plus a reason instead. **The block must be socket-level — a proxy still resolves DNS.** Verify once: for a wrapper-style block run `<the block> python3 -c "import socket; socket.create_connection(('1.1.1.1',443),3)"` and require it to fail (and to connect without the block); for an in-process blocker, add a throwaway test doing that connect and confirm it fails inside the tier and passes outside it. A bare `—` with no reason, or a `TODO`, escalates — neither is read as "no tier" |
| `CI_STATUS_CMD` | <inferred / TODO(init-loop)> | |
| `BRANCH_FMT` | <inferred / TODO(init-loop)> | |
| `COMMIT_CONV` | <inferred / TODO(init-loop)> | |
| `PR_TEMPLATE` | <inferred / — if none> | replicate in the PR body if the repo enforces it |
| `MERGE_METHOD` | <inferred / TODO(init-loop)> | e.g. squash, `--delete-branch`, explicit `--subject` scope |
| `APPEND_ONLY_FILES` | protected files are declared for the guard hook in `.claude/loop.append-guard.json` (the machine SSOT); TODO(init-loop) if this repo protects none | do **not** restate paths here — the sidecar is authoritative |
| `LEDGER_ROOT` | `.claude/loop/` | **gitignored** — local working state, never committed |
| `RELEASE_SCHEME` | <inferred / "no release cycle"> | merge gate reads "≤ patch bump or no bump" |

## 2. `ARCHITECT_TRIGGERS`

<!-- TODO(init-loop): list this project's "needs design review" conditions. AgentFluent example: -->
<!-- Fire DESIGN_AGENT when the plan touches shared models, changes a cross-module interface, adds -->
<!-- a new rule/pipeline, OR the orchestrator is unsure. Bias toward calling it. Skip for docs. -->

## 3. `SOURCE_LAYOUT` — router signals

<!-- Fill what you can infer; TODO(init-loop) the rest. AgentFluent example shape: -->
- **Package layout:** <where source lives> / <where tests live>; throwaway scaffolding outside the package, no runtime-dep leakage.
- **`docs` label / path:** <label + confined path>.
- **`research` label / path:** <label or naming convention; no test-coverage gate>.
- **`stub-defer` marker:** <how a tracking-only issue is marked>.
- **`code` (default):** bug/enhancement touching source → full pipeline.

## 4. Security routing

<!-- TODO(init-loop): these are GitHub/host-specific. Re-specify for this repo's host if not GitHub. -->
<!-- AgentFluent example: .claude/-only change → run local /security-review (labeled workflow -->
<!-- excludes .claude/); otherwise sensitive surface → apply `needs-security-review` label ONLY when -->
<!-- dev-complete (workflow triggers on [labeled], not push). Skip for docs/no-surface changes. -->

### ⛔ Precondition — `origin/HEAD` must be set, or the local review gate dies before it runs

**Git-specific, not host-specific** — unlike §4's routing rules above, this needs only git and a
remote named `origin`, and applies on any git host. *You*, reviewing this config, may delete it if
this project does not use git, names its remote something else, or binds `SECURITY_REVIEW` to
something that does not diff against `origin/HEAD`.

`/security-review` opens by diffing against `origin/HEAD`. When that ref does not resolve, the gate
exits with `fatal: ambiguous argument 'origin/HEAD...'` and reviews nothing.

**When it is absent — the rule, not a list of cases.** The ref is set only if the remote's own default
branch was among the refs your clone actually fetched. An ordinary full clone fetches it. It is
**absent** after a `--single-branch` or `--depth` clone of some *other* branch or a tag (the usual CI
checkout), a `--bare`/`--mirror` clone, a `git init` + `git remote add` + `git fetch`, or a clone of a
then-empty repo. It can instead be **dangling** — present but pointing at a branch the upstream has
renamed or deleted — which fails the same way. The check below tests that the ref *resolves*, so it
covers both.

**Repair.** These commands act on **the current directory**, so confirm where you are first — run
from the repo root:

```bash
git rev-parse --show-toplevel
GIT_TERMINAL_PROMPT=0 git remote set-head origin -a
git rev-parse --verify -q refs/remotes/origin/HEAD || echo "still unresolved -- see below"
```

`set-head -a` makes a **network call**: it can hang on an unreachable remote (interrupt it), and
`GIT_TERMINAL_PROMPT=0` suppresses git's own credential prompt but not `ssh`'s. If it reports
`Not a valid ref` or `Cannot determine remote HEAD`, your clone never fetched the remote's default
branch — fetch that branch first, then repeat:

```bash
git fetch origin '<default-branch>:refs/remotes/origin/<default-branch>'
```

**An erroring gate is not a passing gate.** Treat `fatal: ambiguous argument` from this gate as a
missing ref, not as a clean review: repair it and re-run. Never journal it as clean.

## 5. Project examples referenced by the engine's guidance

<!-- Optional. The engine states its principles generically; add this repo's concrete instances -->
<!-- here as they emerge (worked examples the engine's journal/plan/triage steps can point at). -->
~~~

## Step 5 — Write the append-guard sidecar (only if Step 3 found a file)

`GUARD` is a JSON array of `{ "suffix", "id_pattern" }` entries — the SSOT the config's
`APPEND_ONLY_FILES` row points at:

~~~json
[
  { "suffix": "<repo-relative path>", "id_pattern": "<one-capture-group regex, backslashes doubled>" }
]
~~~

**Do not blindly overwrite an existing `GUARD`** (it may protect files this run didn't detect):
- If `GUARD` does **not** exist → write it with the single entry from Step 3.
- If `GUARD` **already exists** → read it, and **merge** the Step 3 entry in, de-duplicated on
  `suffix` (keep every existing entry; add the new one only if its `suffix` isn't already present).
  Report what you kept vs. added; never drop an existing entry.

Do not also write the path into `loop.config.md` — the pointer row already references this file.
If Step 3 found nothing, skip this step entirely (leave any existing `GUARD` untouched; the config
keeps its `TODO(init-loop)` row).

## Step 6 — Ledger dir, `.gitignore`, and `origin/HEAD` (deterministic)

Run these exact, idempotent commands:

```bash
# Refuse to run at all on an empty path. NEITHER half of this block fails safely without this
# guard: `git -C ""` is a no-op (it acts on whatever repo you are standing in, including the
# network write), and `/.claude` is writable in a container, devcontainer or CI runner, so the
# filesystem half creates `/.claude/loop` and `/.gitignore` and reports success.
if [ -z "${CLAUDE_PROJECT_DIR}" ]; then
  echo "STOP: CLAUDE_PROJECT_DIR arrived empty -- Steps 6-7 NOT run; nothing created or changed."
  echo "Re-run them with the repo root (\$TARGET) in place of the empty path, and say so at Step 8."
else
  mkdir -p "${CLAUDE_PROJECT_DIR}/.claude/loop"
  grep -qxF '.claude/loop/' "${CLAUDE_PROJECT_DIR}/.gitignore" 2>/dev/null \
    || printf '\n# dev-loop ledger (local working state, never committed)\n.claude/loop/\n' \
         >> "${CLAUDE_PROJECT_DIR}/.gitignore"

  # Set origin/HEAD if a remote named `origin` exists and the ref does not resolve. Without it the
  # local /security-review dies on `fatal: ambiguous argument 'origin/HEAD...'` and reviews nothing.
  # `set-head -a` is a NETWORK call: bound it, and re-probe rather than trusting its exit status.
  export GIT_TERMINAL_PROMPT=0
  command -v timeout >/dev/null 2>&1 && TMO="timeout 20" || TMO=""
  if git -C "${CLAUDE_PROJECT_DIR}" remote get-url origin >/dev/null 2>&1 \
     && ! git -C "${CLAUDE_PROJECT_DIR}" rev-parse --verify -q refs/remotes/origin/HEAD >/dev/null 2>&1; then
    $TMO git -C "${CLAUDE_PROJECT_DIR}" remote set-head origin -a >/dev/null 2>&1 || true
  fi
  if git -C "${CLAUDE_PROJECT_DIR}" rev-parse --verify -q refs/remotes/origin/HEAD >/dev/null 2>&1; then
    echo "origin/HEAD: resolves (the local /security-review gate can diff against it)"
  else
    echo "origin/HEAD: does not resolve"
  fi
fi
```

Four things this block is deliberate about, all of which look like fussiness and are not:

- **`git remote get-url origin`, not `git remote`, as the existence test.** `git remote` exits **0**
  in a repo with no remotes at all, so it does not gate anything.
- **`rev-parse --verify`, not `symbolic-ref`, as the presence test.** `symbolic-ref` succeeds on a
  **dangling** ref — one pointing at a branch the upstream has renamed or deleted — which fails at
  use exactly like a missing one. Testing that the ref *resolves* covers both states.
- **The empty-path guard.** `git -C ""` is a **no-op, not an error** — it leaves the working directory
  unchanged. So without the guard, an empty `CLAUDE_PROJECT_DIR` does not make these commands fail; it
  makes them act on whatever repo you are standing in, perform the network write there, and report a
  verdict about it. That is the one failure mode here that is both silent and optimistic.
- **A bound on the network call.** `GIT_TERMINAL_PROMPT=0` stops *git's own* credential prompt — it
  does **not** cover `ssh`'s host-key or passphrase prompts, and it does nothing for a connect that
  hangs. `timeout` supplies the missing bound where it exists (it is not present on every host, hence
  the `command -v` probe).

The closing probe **reports what it measured — whether the ref resolves — and deliberately names no
cause.** A non-zero from `git remote get-url origin` has several (no remote, not a git repo, a remote
under another name), and an earlier version of this block picked one and stated it as fact, which is
the failure this whole command exists to stop. Relay the line it printed; do not add a diagnosis.

This block and the `origin/HEAD` precondition in the generated §4 share **the presence test
(`rev-parse --verify`) and the repair (`remote set-head origin -a`)** — change one and change the
other. They are deliberately **not** the same script otherwise, and the difference is not cosmetic:
this one runs unattended, so it is anchored with `-C`, guarded, bounded and silent. §4's is **pasted
by a human into an unknown shell and an unknown directory**, so it anchors by *showing* them where
they are rather than by assuming, sets no environment variable that would outlive the paste, and uses
no shell construct that depends on word-splitting (zsh does not split unquoted variables, and it is
what a consumer is most likely to paste into). Do not "unify" them by copying this block into §4.

## Step 7 — Wire `enabledPlugins` in `settings.json` (deterministic, safe fallback)

Merge the plugin key without disturbing existing settings. Run:

```bash
if [ -z "${CLAUDE_PROJECT_DIR}" ]; then
  echo "STOP: CLAUDE_PROJECT_DIR arrived empty -- Step 7 NOT run (same reason as Step 6)."
else
python3 - "${CLAUDE_PROJECT_DIR}/.claude/settings.json" <<'PY'
import json, sys, pathlib
p = pathlib.Path(sys.argv[1])
key = "dev-loop@claude-code-loop"
if not p.exists():
    p.write_text(json.dumps({"enabledPlugins": {key: True}}, indent=2) + "\n")
    print("created settings.json with enabledPlugins")
    sys.exit(0)
try:
    data = json.loads(p.read_text())
    assert isinstance(data, dict)
except Exception:
    print("SKIP: settings.json is not a plain JSON object -- add this manually:")
    print(json.dumps({"enabledPlugins": {key: True}}, indent=2))
    sys.exit(0)
ep = data.get("enabledPlugins")
if ep is None:
    data["enabledPlugins"] = {key: True}
elif isinstance(ep, dict):
    if ep.get(key) is True:
        print("already enabled -- no change"); sys.exit(0)
    ep[key] = True
else:
    print("SKIP: enabledPlugins is not an object -- add this manually:")
    print(json.dumps({key: True}, indent=2)); sys.exit(0)
p.write_text(json.dumps(data, indent=2) + "\n")
print("enabled dev-loop@claude-code-loop")
PY
fi
```

If the script prints a `SKIP:` line, relay the snippet to the human instead of editing the file.

## Step 8 — Summary

Report, concisely:
- **Artifacts:** which of `CONFIG` / `GUARD` / `SETTINGS` / `.gitignore` / `LEDGER` were created,
  updated, or already present (skipped).
- **`origin/HEAD`:** report exactly the `origin/HEAD:` line Step 6 printed, verbatim and **without
  adding a cause**. If it says the ref does not resolve **and Step 2 found a remote named `origin`**,
  list it as an action item — the local review gate will fail until it is set. If Step 6 did not run,
  say so and why.
- **Unexpanded tokens:** run

  ```bash
  for f in "$TARGET/.claude/loop.config.md" "$TARGET/.claude/loop.config.md.init-new"; do
    [ -e "$f" ] && { echo "checked $f"; grep -n '@@' "$f"; }
  done
  ```

  covering **both**, since Step 1(b) writes the refresh to the `.init-new` sibling and that file
  carries the same pointer line. **Write the paths out** — `$CONFIG` is this document's notation, not
  a shell variable, and a `grep` against an unset one prints nothing and exits non-zero, which is
  indistinguishable from a clean file. The `checked` line is the proof it ran at all; a silent result
  counts only if you saw one. Any hit means a `@@…@@` token was copied
  through instead of expanded (rule 1) — fix it before reporting done. This is the one check that
  catches it: such a token is **not** a `TODO(init-loop)`, so the grep below will not see it, and the
  pointer line reads plausibly enough that a human reviewer may not either.
- **Inferred parameters:** the values you filled and their provenance (mirror the Notes column).
- **`TODO(init-loop)` blanks:** the list the human must resolve before the first run — `grep -n
  'TODO(init-loop)' "$CONFIG"`.
- **Append-guard:** if a sidecar was written, the file protected and the **matched entry IDs**
  (e.g. "matched D001…D060 — guard is live"; "0 matches — the regex protects nothing, fix
  `id_pattern`"). If none, say the guard is inert (no sidecar).
- **Next steps:** review `CONFIG` (resolve TODOs), then run the `dev-loop` skill to work the first
  issue. Note that an unresolved **gate** binding does not disable its gate — the loop falls back to
  a built-in equivalent where it has one (code review) and otherwise stops and asks you. Non-gate
  blanks fail later, at whatever step needed the value.
