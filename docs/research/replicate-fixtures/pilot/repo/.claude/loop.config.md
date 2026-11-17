# Loop config — greet (replicate-harness pilot fixture)

Frozen with the fixture. Every replicate of this fixture runs against these exact bytes.

## 1. Project parameters

| Parameter | Value | Notes |
|-----------|-------|-------|
| `BACKLOG_SOURCE` | GitHub label **`fixture`** | `gh issue list --label fixture --state open`; run slug `fixture`. Initialize the run if none exists. |
| `SCOPE_AGENT` | the **`pm`** subagent | |
| `DESIGN_AGENT` | the **`architect`** subagent | |
| `CODE_REVIEW` | parallel finder subagents over `git diff main...HEAD` + the issue's acceptance criteria, angles chosen per the diff's risk surface, then a pass confirming each finding | |
| `SECURITY_REVIEW` | `—` (no security surface: a pure string function, no I/O, no dependencies) | |
| `VERIFY` | `—` (no runnable app; `TEST_CMD` is the runtime proof) | |
| `MODEL_TIERS` | `—` (every role inherits — the model and effort each subagent ran on before this row existed) | |
| `PRIORITY_LABELS` | `—` (no priority labels; tiebreak issue number ascending) | |
| `ARCHITECT_TRIGGERS` | see §2 | |
| `SOURCE_LAYOUT` | see §3 | |
| `TEST_CMD` | `python3 -m unittest -q` | stdlib only |
| `LINT_CMD` | `—` (no linter configured in this fixture) | |
| `TYPE_CMD` | `—` (no separate type step in this fixture) | |
| `HERMETIC_TEST_CMD` | `—` (no offline/hermetic tier declared) | |
| `CI_STATUS_CMD` | `gh run list --workflow test.yml --branch <branch> --json headSha,status,conclusion` | green only when the run whose `headSha` is the PR's head commit is `completed` with conclusion `success`; that run's job is the required check `test-suite`. Not `gh pr checks`: the replicate's sandbox token cannot read checks. |
| `BRANCH_FMT` | `<type>/<kebab-slug>` | |
| `COMMIT_CONV` | Conventional Commits (`feat:`, `fix:`, `docs:`, `test:`, `chore:`) | |
| `PR_TEMPLATE` | `—` (none) | |
| `MERGE_METHOD` | `gh pr merge <PR> --squash --subject "<type>(<scope>): <summary> (#<PR>)" --body "" --delete-branch` | |
| `APPEND_ONLY_FILES` | `—` (none in this fixture) | |
| `LEDGER_ROOT` | `.loop-ledger/` | gitignored; outside `.claude/` because headless writes there are refused |
| `RELEASE_SCHEME` | no release cycle | |

## 2. `ARCHITECT_TRIGGERS`

- A public function's signature changes.

## 3. `SOURCE_LAYOUT`

- Package layout: top-level modules (`greet.py`) with `test_*.py` beside them.
- `docs` route: `README.md` only.
- `code` (default): everything else.

## 4. Security routing

No security surface; skip and journal why.
