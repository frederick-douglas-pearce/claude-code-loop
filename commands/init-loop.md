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
root. **If `${CLAUDE_PROJECT_DIR}` was unset, `export CLAUDE_PROJECT_DIR="$TARGET"`** so the
deterministic blocks in Steps 6–7 (which reference `${CLAUDE_PROJECT_DIR}`) resolve to the repo
root rather than `/`. `mkdir -p "$TARGET/.claude"`. Record which of `CONFIG`, `GUARD`, `SETTINGS`,
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
`TODO(init-loop): <what to supply>`.

**Inference map (cross-ecosystem — do not assume Python/GitHub):**

| Parameter | Look here |
|-----------|-----------|
| `TEST_CMD` | pyproject/`tox`, `package.json` scripts (`test`), `Makefile` (`test:`), `Cargo.toml`, CI workflow steps |
| `LINT_CMD` | ruff/flake8/eslint/clippy/golangci config; `lint` script; CI |
| `TYPE_CMD` | mypy/pyright config, `tsc`, `package.json` `typecheck`; set `—` + the reason if the language has no separate type step |
| `CI_STATUS_CMD` | `gh pr checks <PR>` if GitHub host; else the host's equivalent or `TODO(init-loop)` |
| `BRANCH_FMT` | CLAUDE.md / CONTRIBUTING branch rules; else infer from existing `git branch -a` names |
| `COMMIT_CONV` | CONTRIBUTING / CLAUDE.md; detect Conventional Commits from recent `git log` if unstated |
| `PR_TEMPLATE` | `.github/PULL_REQUEST_TEMPLATE.md` (note "must replicate" if present) |
| `MERGE_METHOD` | CONTRIBUTING / repo settings; default `TODO(init-loop)` |
| `BACKLOG_SOURCE` | GitHub milestone/label if a GitHub remote exists; else a local `TODO.md`; else `TODO(init-loop)` |
| `PRIORITY_LABELS` | `gh label list` for `priority:*` labels (GitHub host); else CONTRIBUTING/CLAUDE.md; else `TODO(init-loop)` |
| `RELEASE_SCHEME` | release-please / semantic-release config, `pyproject`/`package.json` version + publish; else "no release cycle" |
| `SCOPE_AGENT` / `DESIGN_AGENT` | user-global subagents — cannot be inferred from the repo; default `TODO(init-loop): name a scope/design subagent` — or an explicit `—` plus a reason if this project has none |

## Step 3 — Detect an append-only file (for the guard)

Best-effort scan for a decision-log / changelog-style markdown whose entries are repeated
`## <ID>` headers (e.g. `docs/decisions.md`, `.claude/specs/decisions.md`, `DECISIONS.md`,
`CHANGELOG.md`). If you find one:
- `suffix` = its repo-relative path.
- `id_pattern` = a regex with **exactly one capture group** for the entry ID, e.g. for `## D001`
  headers: `^##\s+(D\d+(?:-[A-Za-z0-9]+)?)`. In JSON the backslashes double: `"^##\\s+(...)"`.
- Run the pattern against the file and **collect the matched IDs** — you will echo them in the
  summary so the human can confirm the guard actually matches (0 matches ⇒ it protects nothing).

If you find nothing, do **not** invent a sidecar — skip Step 5's write and set `APPEND_ONLY_FILES`
to `—` plus the reason ("no append-only log in this repo"): an explicit negative, per the §1 callout,
not a `TODO`. If you are *unsure* — you saw a candidate but could not confirm its shape — that is a
genuine blank, so leave `TODO(init-loop)` and name the candidate.

## Step 4 — Generate `loop.config.md`

Write `CONFIG` from the skeleton below, substituting inferred values and `TODO(init-loop)`
placeholders. Keep all five sections. §1 is cross-ecosystem — fill it. §3 is lightly inferable
(source layout) — fill what you can. **§2 and §4 are the project-specific porting surface** — emit
them as stubs with the commented AgentFluent example so the human sees the shape. If the host is
**not** GitHub, add a one-line `TODO(init-loop)` note in §4 flagging that every rule there is a
GitHub-ism to be re-specified.

For the `APPEND_ONLY_FILES` row use the **pointer form**, never a duplicated path — the sidecar
JSON is the single source of truth for which files are protected:

~~~markdown
# Loop config — <REPO NAME>

Per-project bindings for the supervised dev loop. `loop-engine.md` (the generic engine, bundled in
the plugin) references every value below **by parameter name**; this file is the only surface a
porting project edits. A non-matching (non-Python / non-`src/` / non-GitHub) project revises **all
four sections** (parameters, architect triggers, source layout, security routing) — never the
engine.

See `${CLAUDE_PLUGIN_ROOT}/skills/dev-loop/loop-engine.md` for the operating procedure and semantics.

> ⚠ **Generated by `/init-loop` — review before the first run.** Values are best-effort inferences;
> every `TODO(init-loop)` is a blank you must fill — or, where the parameter genuinely does not apply
> to this repo, replace with an explicit `—` plus a reason (see the callout under §1; deleting the
> row is not a third option).

---

## 1. Project parameters

The binding table. The engine names each parameter in `CAPS`; the values here are this repo's.

> ⚠ **A `TODO(init-loop)` is a blank that escalates — not a switch that turns its gate off.** The
> engine journals a gate as passed only with the gate's own verdict as evidence (**no verdict ⇒ not
> passed**), so an unfilled binding does not quietly skip the gate: it falls back to the engine's
> inline composition where one is defined, and otherwise **stops the run and asks you**. Every
> `TODO` left here costs an escalation every iteration it is read.
>
> **Deleting the row does not help** — the engine treats an absent binding exactly as it treats a
> `TODO`-valued one. There are only two resolutions: **fill it**, or **state the negative
> explicitly** — set the Value to `—` and give the reason in Notes (`— (no type checker; stdlib-only
> project, deliberate)`). An explicit negative *is* a filled binding: it tells the engine the
> parameter has no value here and tells the next reader a decision was made. A blank tells them
> neither.

| Parameter | Value | Notes |
|-----------|-------|-------|
| `BACKLOG_SOURCE` | <inferred / TODO(init-loop)> | GitHub milestone/label, or a local `TODO.md` |
| `SCOPE_AGENT` | <TODO(init-loop): user-global subagent, or `—` + a reason if none> | answers scope/priority/requirements questions |
| `DESIGN_AGENT` | <TODO(init-loop): user-global subagent, or `—` + a reason if none> | reviews plans pre-implementation |
| `CODE_REVIEW` | parallel finder subagents over `git diff main...HEAD` **+ the issue's acceptance criteria**, angles chosen per the diff's risk surface (engine step 9), then a pass confirming each finding | the orchestrator runs this itself. Do **not** bind a `disable-model-invocation` skill (e.g. `/code-review`) — those are user-triggered only, so the gate would silently do nothing; keep them as a human escalation |
| `SECURITY_REVIEW` | <TODO(init-loop): local `/security-review` and/or a labeled workflow> | see §4 |
| `VERIFY` | `/verify` (built-in) | runtime behavior check when an AC needs proof-by-running |
| `PRIORITY_LABELS` | <inferred / TODO(init-loop)> | drives selection order; e.g. `priority:high > medium > low`, tiebreak issue number asc |
| `ARCHITECT_TRIGGERS` | see §2 | **project-specific — edit when porting** |
| `SOURCE_LAYOUT` | see §3 | router uses this; **edit when porting** |
| `TEST_CMD` | <inferred / TODO(init-loop)> | |
| `LINT_CMD` | <inferred / TODO(init-loop)> | |
| `TYPE_CMD` | <inferred / — if none> | |
| `CI_STATUS_CMD` | <inferred / TODO(init-loop)> | |
| `BRANCH_FMT` | <inferred / TODO(init-loop)> | |
| `COMMIT_CONV` | <inferred / TODO(init-loop)> | |
| `PR_TEMPLATE` | <inferred / — if none> | replicate in the PR body if the repo enforces it |
| `MERGE_METHOD` | <inferred / TODO(init-loop)> | e.g. squash, `--delete-branch`, explicit `--subject` scope |
| `APPEND_ONLY_FILES` | protected files are declared for the guard hook in `.claude/loop.append-guard.json` (the machine SSOT); `—` + reason if this repo protects none | do **not** restate paths here — the sidecar is authoritative |
| `PERMISSION_POSTURE` | <TODO(init-loop): e.g. background agents validate-only → parent implements> | shapes fan-out |
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
If Step 3 found nothing, skip this step entirely (leave any existing `GUARD` untouched; the config's
`APPEND_ONLY_FILES` row carries the explicit `—` + reason set in Step 3, not a `TODO`).

## Step 6 — Ledger dir + `.gitignore` (deterministic)

Run these exact, idempotent commands:

```bash
mkdir -p "${CLAUDE_PROJECT_DIR}/.claude/loop"
grep -qxF '.claude/loop/' "${CLAUDE_PROJECT_DIR}/.gitignore" 2>/dev/null \
  || printf '\n# dev-loop ledger (local working state, never committed)\n.claude/loop/\n' \
       >> "${CLAUDE_PROJECT_DIR}/.gitignore"
```

## Step 7 — Wire `enabledPlugins` in `settings.json` (deterministic, safe fallback)

Merge the plugin key without disturbing existing settings. Run:

```bash
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
```

If the script prints a `SKIP:` line, relay the snippet to the human instead of editing the file.

## Step 8 — Summary

Report, concisely:
- **Artifacts:** which of `CONFIG` / `GUARD` / `SETTINGS` / `.gitignore` / `LEDGER` were created,
  updated, or already present (skipped).
- **Inferred parameters:** the values you filled and their provenance (mirror the Notes column).
- **`TODO(init-loop)` blanks:** the list the human must resolve before the first run — `grep -n
  'TODO(init-loop)' "$CONFIG"`.
- **Append-guard:** if a sidecar was written, the file protected and the **matched entry IDs**
  (e.g. "matched D001…D060 — guard is live"; "0 matches — the regex protects nothing, fix
  `id_pattern`"). If none, say the guard is inert (no sidecar).
- **Next steps:** review `CONFIG` (resolve TODOs), then run the `dev-loop` skill to work the first
  issue. Note that an unresolved blank does **not** disable its gate — the loop escalates to the
  human every time it reads one, so the first run will be noisier the more `TODO`s remain.
