# Replicate harness pilot — 2026-11-17 (#208, AC6)

The pilot gate for `replicate.py`: throwaway replicates on the `pilot` fixture, **no comparison
drawn**. It exists to show the harness holds the stratum fixed and contains the run before #274 or
#209 spends a replicate. Two passing replicates, one per effort level, plus the failed attempts that
shaped the harness.

## What was pinned

| Factor | Value |
|---|---|
| Harness commit (frozen) | **`90eeb48`** — any runtime-changing change after it forces a re-pilot (#357's freeze rule) |
| Plugin | tag `v0.6.0` = `44e0c690d0dd09ce1efbdbaa339ba2f6dceb0c31` (engine content = R1's control, `5391906`); version dir `0.6.0`; marketplace commit `1401f4314c8a`; installed cache sha256 `2f742197f6dc…` |
| CLI | `2.1.326 (Claude Code)`, pinned binary `~/.local/share/claude/versions/2.1.326`, autoupdate off |
| Fixture base | `7c311b7cfe3b594c54c7c6279977e764163c2439` (re-frozen after the CI rebind below) |
| Stratum | `claude-sonnet-5-5` @`medium` (m3) and @`high` (h1); roster (`pm`, `architect`) rendered to the same pair; `MODEL_TIERS` every role inherits; `CLAUDE_CODE_*EFFORT*`/`*SUBAGENT_MODEL*` unset in the harness |
| Memory snapshot | `1dff0d1844d4fc8bf0eba1b3ea0ed3fccee816ce67faacbf37f3d02bb4f79731` |
| Settings | `{}`, sha256 `ca3d163bab05…` as written before install (the install then records the replicate's own plugin repo in it) |
| Replies | scripted, keyed on the ledger row's Status, sent with `--resume`; gate latency 0 |

**`gh-token` permissions, as the human recorded them at the plan gate (2026-11-17):** a
fine-grained token whose resource owner is the sandbox org `frederick-douglas-pearce-loop-sandbox`,
with Contents, Pull requests and Issues read/write, Actions and Commit statuses read-only, and no
administration. The harness's `harness-token` (Administration/Contents/Issues/Workflows) is used
only outside the sandbox, for setup and teardown. The A0 spike checked the boundary from the outside:
`gh-token` was refused creating a personal repo, creating a ref on `claude-code-loop`, and deleting
an org repo.

## Built-in agents

Two sandboxed spikes on the pinned CLI, before the pilot ($0.20 together): built-ins spawned with no
`model`/`effort` run on the parent's stratum — at medium Explore, general-purpose and Plan; at high
those and `claude`. The fixture's `builtin_agents` map carries all four as `"parent"`; any other
built-in fails AC6c by default-deny.

## Attempts

| Replicate | Harness | Outcome | Cost |
|---|---|---|---|
| p1-med | `7cbd00b` | **Refused at preflight**: `--plugin-commit` was an abbreviated SHA, which does not equal the resolved one. Nothing installed, no repo created. | $0 |
| m1 | `7cbd00b` | Halted at `in-pr`. Two defects: **(1)** a *directory*-source marketplace makes Claude Code run the skill from the source dir, not the cache, so every engine read missed `cache/` and the audit counted 0 loads; **(2)** the fixture bound `CI_STATUS_CMD` to `gh pr checks`, which a fine-grained token cannot read (`statusCheckRollup`: "Resource not accessible by personal access token"; the check-runs API likewise). | $0.57 |
| m2 | `22b4f83` | (a)(b)(c) clean, halted at `in-review`: the replicate's loop stopped at step 8 on a design-question finding with an architect scope ruling — correct engine behavior — and the fixture had no scripted reply for it. | $0.83 |
| **m3** | `90eeb48` | **Unattended end to end** (plan gate → acceptance → merge, 3 invocations). | $1.05 |
| **h1** | `90eeb48` | **Unattended end to end, audit `pass: true`.** | $1.48 |

Fixes between attempts: the plugin is pushed to a private per-replicate
sandbox-org repo and installed from it over https (the CLI rejects `file://` sources, and a git
source declared in `settings.json` did not register headless), and the run refuses unless
`known_marketplaces.json` records a git source at that URL and `installed_plugins.json` records the
marketplace commit at the cache path (offline: `InstallCheckTests`); the fixture's `CI_STATUS_CMD`
became `gh run list --workflow test.yml`, keyed on the PR's head SHA (no test pins the binding); and
the fixture gained an `in-review` reply — *follow the architect's scope ruling* — chosen by the
human. That reply goes to **any** `in-review` stop whose final message matches
`scope ruling|design question`, a dirty round-2 escalation that names a ruling included
(`test_review_stop_follows_the_scope_ruling` covers only a message naming neither). No pilot
replicate reached it: m3 and h1 never stopped at `in-review`, so there is no live evidence for it.

## AC6

| | Verdict | Evidence |
|---|---|---|
| **(a)** zero writes to the real tracker | **met, h1 clean; m3 by hand adjudication** | Both: every shim-logged `gh` call targeted the sandbox (m3 9, h1 15), no unshimmed `gh` in any transcript, no MCP, no credential-path mention. h1's account-event audit is empty. m3's flagged four `IssuesEvent`s on the human's personal repos `claude-hook-validator` and `claude-code-sessions`. The replicate's only GitHub credential is `gh-token`, whose resource owner is the sandbox org, and the A0 spike showed it refused a write to a personal repo; no transcript, stream, shim log or work-tree file names either repo. They were the human's concurrent activity. Met **within the window bounds stated below**; the delayed re-audit the plan owes has not been done. |
| **(b)** exactly the pinned plugin executed | **met** | Every engine read classified as a load (m3 16, h1 18) is under the replicate's own `home/.claude/plugins/cache/claude-code-loop/dev-loop/0.6.0/`; none under the real `~/.claude`; none from a non-cache copy. The user-installed plugin does not exist inside the sandbox. |
| **(c)** every record carries the pinned `(model, effort)` | **met** | m3: parent 63 and Explore 6 records, all `claude-sonnet-5-5@medium`. h1: parent 97 and Explore 12, all `@high`. No record lacks an effort. The roster's `architect` ran in m2 (the scope ruling, 3 records `@medium`), also clean; `pm` never ran, and neither passing replicate spawned a roster agent. |
| **(d)** the instrument refuses an unknown model | **met** | Live: an h1 transcript copy with its model rewritten to `claude-sonnet-9-9` → `measure` returns `refused: … no PRICING entry for model 'claude-sonnet-9-9'` and no figures. Also pinned offline (`test_unknown_model_refuses`). |
| **(e)** auto-approval with no human; identical snapshot on a second run | **met** | Both passing replicates answered every stop from the script (`unattended: true`) and merged. m3 and h1 start from the same memory snapshot id, settings hash, marketplace commit, cache hash and base SHA. |

**AC1** (unattended end-to-end from a fixed base in a fresh clone, refusal from a non-baseline
state, ledger reset per replicate): m3 and h1, each in a fresh clone with no ledger at start. The
non-baseline refusals are shown offline (`test_refuses_non_baseline_head`,
`test_refuses_dirty_and_untracked`, `test_refuses_existing_ledger`); p1-med is a live refusal of an
operator input (an abbreviated plugin SHA), not of a tree. **AC5**: `result.json` from `tree_cost` — m3 31 turns, $1.05;
h1 45 turns, $1.48 — and the unknown-model refusal above.

## Bounds and deviations, stated

- **The account-event check is account-wide.** It flags any activity on the account during a run,
  the human's own included, which is what m3 shows. A clean (a) needs either a quiet account during
  the run or a hand adjudication like m3's. It reads the public+private events feed, which can lag,
  and only its first page (100 events).
- **The account-event window starts late.** `run_start` is stamped when the sandbox repo is created,
  after the plugin repo is created and pushed and after both sandboxed `claude plugin` runs (m3
  13:29:23 → 13:29:36, h1 13:33:27 → 13:33:42), so the audit does not cover the install.
- **The plugin repo is an in-org write target for the whole run**, reachable by `git push` (which the
  shim does not see), and `foreign_events` ignores in-org repos. Checked after the fact: no stream or
  transcript names `pilot-m3-plugin` or `pilot-h1-plugin`, and both runs' caches still hash to the
  recorded `2f742197f6dc…`. The harness does not re-hash the cache at the end of a run.
- **The marketplace commit's tree equals the pin's** (`16e01f2` = `44e0c69^{tree}`), checked by hand;
  the harness does not assert it.
- Fixing these bounds is #357's, and changing the harness ends this pilot's coverage: one re-pilot is
  owed after the last such change and before #274 spends a replicate.
- **`CI_STATUS_CMD` differs from a consumer's** (`gh run list`, not `gh pr checks`) because the
  sandbox credential is a fine-grained token. Every #274 fixture must apply the same rewrite for it
  to be a fixed factor across arms; nothing enforces that yet. It is a confound for any comparison of replicate cost against
  consumer transcripts; the human confirmed no #274/R1 analysis makes that comparison and no arm
  treats the CI gate.
- **The review design-question reply is protocol, and not yet safe to inherit.** As written it can
  answer a dirty round 2 with *accept as non-blocking*. The human ruled that only the design-question
  stop gets a scripted reply, with a discriminator that halts when unsure; that is #357's, before any
  #274 fixture carries an `in-review` reply.
- **m1's audit flagged a `printf`** whose string contained "gh pr checks" as an unshimmed call.
  A false positive, adjudicated by hand; narrowing the pattern is #357's.
- Two replicates are a pilot, not a sample: no figure here estimates anything.

## Falsifier

The plan's falsifier was that the harness could not hold the stratum fixed — that subagent effort
would not be recoverable. It is not falsified: every subagent record in both passing replicates
carries an effort, and it is the pinned one.
