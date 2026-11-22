# Loop cost & convergence research

**Not part of the plugin's runtime.** Nothing here is read by an agent at runtime; the `dev-loop`
deliverable is `skills/`, `commands/`, `hooks/`, `tools/`. These are analysis artifacts about how
much a loop run costs and why, kept in-repo so the numbers behind a scoping decision are auditable
rather than remembered.

---

## Start here

| file | what it is |
|---|---|
| **`loop-cost-and-convergence.md`** | The notebook. Findings 1–12, each with method, numbers, and what would falsify it. **The primary document** — everything else supports it. |
| `baseline-2026-10-04.md` | **The sharding epic's before-baseline** (#126): 0.3.0, stratum `claude-opus-5-5`@`high`, per repo. It also states the 0.3.0-relative predictions #133 is judged against. |
| `before-side-2026-10-09.md` | #133's **PR B**: the per-file instrument the sharding release is measured with, frozen at its merge commit; the 0.3.0 before side re-admitted through it; and that side **priced** (parent and subagents, per repo). |
| `baseline-2026-08-25.md` | Frozen **0.2.0** metrics and its P1–P9 sharding predictions (P10 is #135's). Kept as published; superseded as the sharding before-baseline by `baseline-2026-10-04.md`. |
| `context-architecture-refactor.md` | Design note: why shard the engine, compared against `obra/superpowers`. |
| `draft-core.md` | The seven-unit **target** architecture. Not the increment being shipped — do not implement from it. |
| `core-self-sufficiency-audit.md` | Which engine references a shrunken core would break, and the replacement wording. |
| `cost-model-design.md` | Design note: what it would take to *estimate* a lever's effect rather than read it off a slope — estimands, the identification designs available, and the instrumentation that has to land first. |
| **`model-selection-2026-10-31.md`** | **Design: per-role, multi-provider model selection** (2026-10-31, engine 0.4.0, CLI 2.1.314): the `MODEL_TIERS` config table (alias tiers, `inherit` on anything unreadable), the engine never names a provider, the inverted roster, two mechanism alternatives (a routing Mod; a `PreToolUse` hook), the measurement plan, and a draft D018. Builds on the cost review's R4 and #281. Evidence base in `model-selection-2026-10-31/`: five dated research notes (Claude Code's native surfaces, third-party providers and gateways, prior art and evidence, hooks and Mods, this repo's internals) plus the coordinator's `PROGRESS.md`. |
| **`cost-review-2026-10-26.md`** | **The cost review** (2026-10-26, engine 0.3.1): where the bill goes (turns, not context), nine ranked levers R1–R9, what to change in the testing approach, and the `cost: turns first` epic with a model label per issue. Appendices in `cost-review-2026-10-26/`: the R1 design note (A), the #35 drift reconciliations (B1, B2), the 147-row deletion manifest and its generator (C), and the hand-check of the $128 session (D). |
| **`r2-phase-isolation-design.md`** | **Design: R2 phase isolation** (#279, 2026-11-18, engine 0.6.0). It covers:<br>- a thin controller plus three forked phases (`planning`, `reviewing`, `accepting`) under one return contract;<br>- the default-deny rule for where shared invariants live (#35);<br>- the platform constraints re-checked against current docs;<br>- a SCOUTING per-step re-model from `tree_cost.py --by-step`, never pooled;<br>- D001 revisited;<br>- the pre-registered falsifier for the #280 spike;<br>- the decision, ratified as D019.<br>Nothing here is engine text. |
| `replicate-pilot-2026-11.md` | **#208's pilot gate (AC6)** for `replicate.py`, 2026-11-17: two unattended replicates on the `pilot` fixture (`claude-sonnet-5-5` @medium and @high, plugin `v0.6.0`, CLI 2.1.326, harness frozen at `90eeb48`), the three failed attempts that shaped the harness, and the bounds #274 inherits (account-wide event check, the `gh run list` CI binding, the `in-review` stop that always halts under #371). No comparison drawn. |
| `replicate-repilot-2026-11.md` | **#368's re-pilot**, 2026-11-19: certifies harness **`da8b717`** for #274 (same pins as the pilot). Covers five replicates — `rp2-m1` and `rp2-h2` merged unattended; `rp-h1` (at `dd517ab`) halted at `in-review`, which led to #371; `rp2-h1` was cut off by the account spend cap — plus the delayed re-audit of the pilot's m3/h1 that found #369, and the bounds #274 inherits: detection-only account feed, `in-review` halts as censored observations, #373, #374. No comparison drawn. **#373 changed the harness after it, so its certification of `da8b717` does not carry over.** Its 2026-11-20 addendum certifies **`f868f97`** (#376, #377) with one replicate, `rp3-m1`, which ended unmerged at the routine merge gate with `pass: true`. |
| `preregistration-template.md` | **The pre-registration template** for a lever measured on the paired benchmark (#382): arms and pins, the endpoint (the first `in-acceptance` stop), the required outcomes, admissibility, censoring and replacement, the verdict's form, and the stopping rule. Copy it per lever and freeze the copy before the first replicate. |
| `r1-preregistration.md` | **R1's pre-registration (#288), a draft, not frozen.** Appendix A §4 restated for a harness on which nothing merges: the primary outcome is round 2 clean given round 1 dirty, the 15–35% USD size is withdrawn, and the classification rules, verdict conditions, and numeric bounds are open rows in its section 2. No replicate may be spent against it until the owner freezes it. |
| `blind-evaluator-protocol.md` | **The blind evaluator's protocol** (#382): how the diff at the stop is scored against a pick's frozen criteria with the arm hidden, how the stop type is judged, and how both feed a pre-registration's outcomes. Specified only; #388 carries the build. |
| `benchmark-fixture-set.md` | **#381's fixture set** for R1's paired benchmark (#288), 2026-11-21: seven closed issues across vote, loop and esg, each with its source base SHA, route, historical rounds, reason, and three feasibility fields (in-review halt likelihood, the Actions-API `CI_STATUS_CMD` rebind, frozen or newly authored config), and which criteria the sandbox can discharge. Names vote #82 as #274's control replay, and records five observations for #382's pre-registration. Selects only; builds no fixture. |

## Scripts

All stdlib-only, all read Claude Code session transcripts from `~/.claude/projects/<slug>/*.jsonl`.

| script | answers | tests |
|---|---|---|
| `engine_cost.py` | What does carrying the engine — core, on-demand units, and tool reads of `SKILL.md` — cost across a whole run? (P2, P2c, P6, P9, per-unit reads and arrival centroids; `--table` adds the P2c median's order-statistic interval) **Admissibility is per file, in context tokens: every engine file the session read but `SKILL.md` must clear its floor, 98% of one measured complete load for the session's own era on its parent's tokenizer family; an unmeasured file, or a parent model with no family, refuses** — never a chars-per-token constant (F191). | `test_engine_cost.py` |
| `load_levels.py` | Which sessions read each engine file of one era in full, and what did the smallest complete load ingest? The scan behind each era's `LOAD_TOKENS` rows, one section per parent tokenizer family (`engine_cost.TOKENIZER_FAMILY`, by exact model id; a parent with no family is left out, never averaged in), `--prev` takes the minimum over a byte-identical earlier copy, an unread file gets **no** row (default-deny), and the output only *suggests* rows. `--census` then scores every session of the era and names each refusal and skip. Hand-check the session that sets the most rows before committing them. | `test_load_levels.py` |
| `plan_gate_cost.py` | What is the parent carrying when the plan is written, and where did all of it come from? Attributes **everything** before implementation starts — including the two buckets no delta-based instrument sees: the always-loaded baseline and the model's own output. Splits that output by block type (only some of it stays resident) and prices the **selection phase** in resident-turn tokens. | `test_plan_gate_cost.py` |
| `rounds_vs_turns.py` | Do gate rounds predict parent turns and bill? (Finding 11) | `test_rounds_vs_turns.py` |
| `calls_per_turn.py` | How many tool calls per turn, and how many turns could have been merged? (Finding 12) | `test_calls_per_turn.py` |
| ~~`context_profile.py`~~ | **RETIRED 2026-08-26** → `deprecated/`. Kept only to reproduce Findings 6–9; its payload bug over-counts spilled reads by up to 13×, so **P4 and the "~50% of every byte" figure are withdrawn**. | — |
| `budget_stats.py` | Ledger `- Budget:` aggregates by engine era. **`--era` resolves N eras and caps BOTH the date and marker columns at the repo's installed version**, so a held-back control cannot read as treated. An installed version missing from `ERAS` raises rather than silently dropping the cap. | `test_budget_stats.py` |
| `tree_cost.py` | Parent **+ subagent** transcripts priced together, each turn on its own model's weights and summed in USD — sizes the bill Finding 11 leaves unpriced. `--sessions` prices named sessions, delegating or not, parent and subagents apart, totals per stratum. **`--sessions` is citable since #133** (`handcheck_pricing.py` agreed to the cent; impossible usage refuses); directory mode stays scouting. Its `re-warm $` column (#287) prices the parent's cache writes after an idle gap longer than the cache TTL. It is not covered by `handcheck_pricing.py`: it reproduces appendix D's $27.80 (`test_appendix_d_session_reproduces_seven_rewarms_and_27_80`, which skips where the transcript is absent), and prints `unknown`, never 0, whenever it cannot state the term (`rewarms`' docstring names why). **`--sessions … --by-step` (#273) is SCOUTING, n=1:** whole-tree USD, turns and Σ context per pipeline step, with boundaries taken from parent `tool_use` markers (`MARKERS`) and subagents linked to their launch by `agentId`. Each of these prints `DETECTOR FAILURE`, never 0:
- a step with no turns, whether or not its marker fired (so a step a route legitimately skips is flagged too);
- an engine load below one copy, or with no row;
- step entries out of pipeline order;
- more than one iteration in one invocation;
- rows that do not add back up to the session's bill.

It reproduces appendix D's phase table within the tolerance as amended on #273 (step entries; the final exit is not asserted) (`test_appendix_d_phase_table_is_reproduced_within_the_stated_tolerance`; appendix D's scripts are in `cost-review-2026-10-26/handcheck/`). | `test_tree_cost.py`; the spec arithmetic itself in `test_stratum.py`; `handcheck_pricing.py` re-run by hand |
| `handcheck_pricing.py` | Does `tree_cost.bill` price a file the way an independent reading of the spec does? Re-prices a seeded sample of transcript files with **no code shared with `stratum.py`** and compares file by file. The hand-check behind `tree_cost --sessions`' citability; re-run it after any change to the arithmetic or the dedupe. | none, deliberately: a test of the hand-check is a guard on a guard |
| `stratum.py` | Which `(model, effort)` stratum a session ran on, plus its CLI version range — the **one** extractor every transcript script above imports, and the per-model `PRICING` table. Every per-session profile prints its `stratum` line; every aggregate groups by parent stratum and names what it excluded. An unpriced model refuses to price, never falls back. (#207) | `test_stratum.py` |
| `replicate.py` | **Not a reader — a runner.** Runs one unattended dev-loop replicate on a frozen fixture issue (#208) and records it. **Containment:** every `claude` process runs under bubblewrap in its own user, mount, pid, network, ipc and uts namespaces with all capabilities dropped; its filesystem is an allowlist (`/usr`, `/etc` and the merged-usr links read-only, the pinned binary and `docs/research/` read-only, and only the replicate's own `home/`, `work/` and shim log writable), so the human's home, gh login, token files, SSH keys and X11/session sockets do not exist inside it; its network is slirp4netns with host loopback disabled; and its environment is an explicit allowlist whose only GitHub credential is a token owned by the sandbox org. Still reachable: outbound internet, host services on non-loopback interfaces and the LAN, and the shared kernel. The plugin is git-archived at a pinned commit, pushed to a private sandbox-org repo and installed from it over https into the replicate's own config, and the run refuses unless it landed as a git install of that commit in the cache (a local-directory marketplace would run the skill from its source dir, so `engine_cost.classify` would see no load); each replicate gets a throwaway sandbox-org repo with CI live; replies are scripted and keyed on the ledger row's Status. **A fixture may answer only the statuses in `REPLY_STATUSES`** (no queue yet, `planning`), **and may end a replicate only at one in `FINAL_STATUSES`** (`in-acceptance`). Any other status halts, `done` and an unknown one included, and `check_stops` refuses a fixture that scripts one (#371, #373). **The harness never answers the merge gate** (#373), so under `mode: calibration`, the engine's default, no replicate merges: `in-acceptance` brackets step 10 and step 11's merge gate, and nothing the 0.6.0 engine writes, nor git state, tells the routine merge-gate stop from a step-10 escalation, so a `merge` reply could merge unreviewed work. A replicate ends, with nothing sent, at its first `in-acceptance` stop, whatever its final message says. Which kind of stop it was is judged afterwards from the stream, never by the harness, and `unattended` means it reached that stop on scripted replies alone. The harness does not check the PR's state: a run that merged on its own (a mode that auto-merges) reaches `done` and halts. `in-review` is deliberately not in that set: no guard can tell step 8's round-1 design-question stop from a stop after a round 2 that read the same commit (the engine's empty-delta full round), so that stop always halts. **A replicate halted there is a censored observation, not a dropped one.** It is likely among the costlier runs, and the rate can differ by arm and stratum (`rp-h1` @high reached it; `rp-m1` @medium did not), so #274's admissibility rules must account for it. It writes `environment.json` (the fixture's absolute directory and the sha256 of its `fixture.json`, the harness commit and whether `docs/research/` was clean at it (#374), base SHA, plugin commit and cache sha256, CLI version, parent and per-agent `(model, effort)`, memory snapshot id, times, per-turn exit codes, any refusal or error), `result.json` (whole-tree USD and **turns summed across sessions**, via `tree_cost`, or a `refused` reason in place of the figures) and `audit.json` (gh calls, account events, MCP and credential-path mentions, engine loads, strata). **Before teardown it freezes the state at the stop into `stop/`** (#380): `diff.patch` (`base_sha..HEAD`, the committed work at the clone's `HEAD`; the pushed head is not recorded), `uncommitted.patch` (`HEAD` against the worktree), `head.txt`, `branch.txt`, `status.txt` (`git status --porcelain --untracked-files=all`) and `ledger/`, a copy of the ledger root's regular files and directories; `environment.json`'s `stop_capture` names each file and records a hash of `stop/`. It runs on every way a replicate ends once its repos are being made — the final stop, every halt, an external halt (Ctrl-C, SIGTERM or SIGHUP; a SIGKILL runs nothing), an install refusal. Its `git` runs under a narrower sandbox profile — no network, `work/` read-only, no `home/`, shim log, `claude` or token — since the clone's git config is the replicate's to write. That config is still read, and a clean filter it names still runs in that sandbox, so the capture is evidence, not proof. The ledger copy refuses any symlink between the clone and the ledger root, and records any symlink or other non-regular entry inside it as an error rather than copying it, so `stop/` holds nothing a reader could follow to the host. The audit's `d_stop_capture` fails the replicate on a missing, errored or changed capture, including any replicate made before #380. The `gh` shim and the audit are a second line: they read tool inputs, not effects, and the replicate can write the shim log and its transcripts, so a clean audit is evidence, not proof. The only call made with the human's own gh login is a read-only GET of the account event feed, outside the sandbox. **That feed is detection only, never coverage** (#369). GitHub serves it unordered, capped at 300 events and up to 6h late, so `audit.json` records every read under `account_feed` and fails (a) on any foreign event any read saw. It never says the window was covered. Criterion (a) rests on the token boundary, so the run refuses unless `gh-token` hashes to the sha256 in `gh-token.sha256`, recorded after the spike that verified its scope with `tr -d '[:space:]' < gh-token | sha256sum > gh-token.sha256` (`sha256sum gh-token` hashes the newline too and will not match). **A delayed re-audit is owed, and `pass` waits for it**: re-run `audit` at least 6h after `run_end` with the same `--login`. A successful read that late sets `account_feed.delayed_read`, and until then the audit does not pass. A read refuses unless `gh` is signed in as `--login`, since any other user would see only that account's public events. Tokens live in `~/.config/loop-sandbox/` and are never printed. **`--uv-bin <abs path>`** copies a pinned `uv` into the replicate's `bin/`, read-only and first on `PATH` inside the sandbox, and `environment.json` records the copy's `uv_version` and `uv_sha256` (null without it) (#391). **`shakedown`** builds the base and clone as `run` does and runs one `--command` in the same turn sandbox with network, but with no `claude`, no token (it refuses to start while `GH_TOKEN` or `CLAUDE_CODE_OAUTH_TOKEN` is set in the harness environment) and no repo created, then probes which Python the sandbox offers and, with `--uv-bin`, which one `uv` resolves; it writes `shakedown.json` and spends nothing, so it is how to check that a fixture's gates can run before a paid replicate. Fixtures: `replicate-fixtures/<name>/`. `run` spends money and creates GitHub repos, so run it by hand only. | `test_replicate.py` |
| `quality_outcomes.py` | **Not a transcript reader — reads git history, ledgers, and #1's comments.** Does a run's merged work hold up? Per merged loop PR: **fix-up commits** (first-parent commits within 14 days touching the PR's files — the issue's definition, so an upper bound) and **F-comments** attributed to it by the convention below; per **issue**: escalations from the journal. Each journal block is at most one stop, in the first class that matches: `gate-error`, `scope-ruling`, `routine` (the stops `plan-gate: always` and `mode: calibration` owe every issue), `human-option`, `unclassified`. Those columns are disjoint, and **`escalations` = gate-error + scope-ruling + human-option** is the issue's definition (`unclassified` is printed, not summed). `plan-material` and `review-past-cap` are attributes that overlap the partition and are never summed with it. Per-repo and per-run medians written `median (n_known/N)` with the nonzero share. Open windows print `pending(n)`; a PR it cannot locate, a journal without `- Plan-gate:` lines, and a PR merged before the convention print `unknown`, never 0. **Observational only:** on a #274 replicate only the escalation counter (`escalations()`, importable) applies. No network call: pass `--findings` (`gh api repos/frederick-douglas-pearce/claude-code-loop/issues/1/comments --paginate`) and `--prs REPO=FILE` (`gh pr list --state merged --limit 1000 --json number,mergeCommit,mergedAt`). `--prs` is optional, but without it PRs whose squash subject names the issue rather than the PR cannot be located (17 of 80 here); the script prints how many, and **any figure meant for #274/#288 should pass it**. A `--prs` key that matches no REPO argument is an error. (#272) | `test_quality_outcomes.py` |

```bash
SLUG=~/.claude/projects/-home-fdpearce-Documents-Projects-git-us-presidential-vote-analysis
python3 docs/research/engine_cost.py      $SLUG/<session>.jsonl
python3 docs/research/plan_gate_cost.py  $SLUG/*.jsonl
python3 docs/research/rounds_vs_turns.py  $SLUG/*.jsonl
python3 docs/research/calls_per_turn.py   $SLUG/*.jsonl
fail=0; for t in docs/research/test_*.py; do python3 "$t" -q || fail=1; done; [ "$fail" = 0 ]   # each module prints its own count; `|| break; done` exits 0 on a failure
```

**Always record the installed plugin version with any measurement** —
`python3 -c "import json,os;print(json.load(open(os.path.expanduser('~/.claude/plugins/installed_plugins.json')))['plugins']['dev-loop@claude-code-loop'])"`.
A before/after that does not name both engine versions is not interpretable. **Nor is one that does
not name both strata:** a model or effort change is a treatment too (`cost-model-design.md` → *The run
environment is a treatment*), so compare only within one parent `(model, effort)` stratum, as each
script's `stratum` line reports it.

## F-comment attribution convention

**Every comment on #1 from 2026-11-18 on carries at least one `**Attributed-to:**` line** (#272),
on a line of its own:

- `**Attributed-to:** <owner>/<repo>#<PR>` — the **merged PR the finding is about**: the change
  that introduced the defect or the gap, which is usually *not* where it surfaced. Name the repo
  even for this one, because PR numbers collide across repos. Several lines are fine when a
  finding is about several PRs.
- `**Attributed-to:** none (<reason>)` — the comment is about no merged PR (bookkeeping, a
  pointer, a finding about something that predates the loop).
- `**Attributed-to:** unknown` — about a merged change, but you cannot tell which.

`quality_outcomes.py` counts the first form per PR, within 14 days of its merge, taking every
`owner/repo#N` in a marker line (backticks and trailing text are tolerated). A comment with no
marker at all is reported as `unmarked=n`, and a marker that is none of the three forms as
`malformed=n`, so a forgotten or mistyped marker shows up rather than reading as a zero. A PR merged before 2026-11-18 prints `unknown` (or `>=n`), because older comments carry no
marker by construction.

**This measures origin, not where a finding surfaced, and the two are different quantities.**
#234's session IDs would attribute a finding to the run it surfaced in; that is a cost and process
signal, not a quality outcome for the PR that caused it, so it does not replace this convention.
Findings on #1 are about the plugin, so for a consumer repo's own PRs this outcome is close to
structurally zero; the script says so instead of reporting a median of 0 as a result.

## The cost spec is canonical

**The canonical cost arithmetic is
[`claude-code-sessions/reference/cost-model.md`](https://github.com/frederick-douglas-pearce/claude-code-sessions/blob/main/reference/cost-model.md).**
Every script here that prices anything does so through `stratum.py`'s shared path (#212). Where this
directory and the spec disagree, the spec describes the bill.

**When a script refuses a session, it names it in its output** (`REFUSED` or
`EXCLUDED`, with the reason). `stratum.py` holds the exact conditions. Refusals include a cache-write
split that disagrees with its total, unreadable usage, and a non-default pricing lever.

**These departures still produce a price, and nothing in the output flags them:**
- **No long-context tier is modelled.** Every model is priced at its flat rates.
- **A usage key the code does not know is ignored**, so a new lever would price at standard rates.
  The spec says to ignore unknown fields, so this cannot be refused by default.
- **Rates are not date-aware.** The spec prices each record at the rate in effect on its
  `timestamp`; `PRICING` is one snapshot, applied to every session whatever its date.

**A difference from the spec that is not listed here is still a departure.**

---

## What the metrics mean

These were misread once, so they are pinned here rather than left to inference.

| term | definition | what it is **not** |
|---|---|---|
| **engine reads** | count of tool calls returning engine text | *not* complete reads of the file — under 0.2.0 they are overlapping partial slices, ~1.0–1.5× the file in total. Also **filter-dependent**; treat as approximate. |
| **ingested** (P2) | engine tokens that entered the parent, measured from context deltas | *not* the file's size, and *not* `chars/4`. The 0.2.0 corpus ran 3.25–3.82 chars per context token; the 0.3.0 sessions in `baseline-2026-10-04.md` run 2.87–2.89 |
| **resident-turn** (P2c) | Σ over turns of engine tokens sitting in that turn's input | the cost quantity; ingestion counts each read once, this counts every turn it is carried |
| **carry / carry-per-turn** | resident-turn ÷ ingested (÷ turns) | **use carry/turn** — raw carry scales with session length and cannot be compared across runs |
| **% of bill** | engine's share of billable-equivalent input | engine takes a share of the **input** side only; it does not cause output tokens |
| **peak context** | the high-water mark of a **single turn** | *not* a total for the run; compaction *lowers* it |
| **bill/turn** | billable-equivalent per parent turn | near-constant (~28–33k) — that is the point, not a coincidence. *Finding 10, n=8, pooled across `claude-opus-5@xhigh` and `@high`.* ↳ *#212: figures here predate #212's cost arithmetic; see [`cost-arithmetic-rerun-2026-09-28.md`](cost-arithmetic-rerun-2026-09-28.md).* |

**Pricing is per model** (`stratum.PRICING`, from the
[pricing page](https://platform.claude.com/docs/en/about-claude/pricing), checked 2026-09-28). Input
splits fresh / 5-minute cache write / 1-hour cache write / cache read at 1× / 1.25× / 2× / **0.1×**,
except a **0.05×** cache read on `claude-opus-5-5`; output is 5× input on every entry. A model with no
entry refuses to price. 97.6–98.9% of input is cache-read, so **share of context ≈ share of cost** and
cache is a uniform ~8× discount rather than a lever — *Finding 10's n=8 on `claude-opus-5`, pooled
across `@xhigh` and `@high`; re-measure per stratum.*
↳ *#212: figures here predate #212's cost arithmetic; see [`cost-arithmetic-rerun-2026-09-28.md`](cost-arithmetic-rerun-2026-09-28.md).*

**The cost model in one line:** `cost ≈ turns × ~33k` (*Finding 10's n=8 on `claude-opus-5`, pooled
across `@xhigh` and `@high`; re-measure per stratum*). Average context is bounded above by the
compaction ceiling and below by the starting footprint, so it varies little; turn count has no
ceiling. **Turns is the free variable.**
↳ *#212: figures here predate #212's cost arithmetic; see [`cost-arithmetic-rerun-2026-09-28.md`](cost-arithmetic-rerun-2026-09-28.md).*

---

## Read this before trusting any new transcript filter

Six detection bugs were found in this analysis. **Every one produced a silent false result in a
plausible direction**, and pattern-matching caught none of them:

1. **Heredoc bodies** — `cat > progress.md <<'EOF' …` discussing the engine scored as an engine read
   (9 reads in a session that had 1).
2. **Working tree vs plugin cache** — reading `skills/dev-loop/loop-engine.md` is an agent *editing*
   the engine, not the loop loading it. Only happens in this repo; inflated one session ~44%.
   **Recurred after #170** moved the working tree under `plugins/dev-loop/`, so a bare `/plugins/`
   test scored in-repo reads as loads; only `/.claude/plugins/cache/` is a load now (#126).
3. **Spill files** — an over-large `cat` is parked at `<session>/tool-results/<id>.txt` and the model
   gets a 2KB preview; recovery reads target the **spill path**, which contains no `loop-engine.md`
   substring. Scored a full load as ~10% of one, and that was written up as a real finding before it
   was caught.
4. **Payload inversion** — `toolUseResult.stdout` holds the full output on a spilled record; the
   model only received the preview. 13× overstatement. **`context_profile.py` was retired (D010) carrying it.**
5. **Direction** — counting `- Budget:` lines the parent *read back* from `progress.md` as work done
   in that session (one 158-turn session showed 11 issues at 14 turns each).
6. **Line wrapping** — budget lines wrap, so `gate-rounds=` sits on a continuation line; a
   single-line regex dropped 3 of 9 sessions.

Two defences, both cheap, and they are the only things that have worked:

- **Hand-check a sample of matches.** Bugs 1, 2, 4, 5 and 6 were found this way; the architect review
  found 3. None was found by reasoning about the pattern.
- **Sanity-check the output distribution against what the system can physically do.** One issue per
  invocation; engine ingestion ≥ one copy of the engine. `engine_cost.py` enforces the latter as an
  **admissibility precondition** (derived per session from the engine era and the parent's tokenizer family; override the core's with `--floor`) — a session whose parent model has no measured rows is inadmissible, and a session below it is
  *unmeasured*, not cheap, and is refused loudly rather than averaged in.

  *This sentence asserted that behaviour for a day before the code had it: the rule was documented
  as default-deny while the tool was in fact fail-open. Caught in review, not by reading. It is
  implemented and tested now — but the lesson is that a doc claiming a fail-safe is not evidence of
  one, which is the same thing `CLAUDE.md` says about prose guards.*

---

## Status

Findings 1–12 are recorded in the notebook and were **all measured on 0.2.0**.

**Several eras are now on disk, and since 2026-10-31 there is no control group.** The held-back
control repos were re-installed at v0.4.0 and the difference-in-differences design is dropped
(#285): the two control repos had 1 and 2 ledger rows at 0.2.0, no stratum, different review
bindings and no post-period accrual, so the DiD could not be computed, and holding them kept them on
a known-defective engine. The paired benchmark (#274) replaces it. Every consumer is now treated, and
each one's sessions are observational data on its own stratum, never pooled (D007). Read the current split from `~/.claude/plugins/installed_plugins.json` — never from this paragraph,
which is the kind of prose that goes stale between releases:

| era | installed | repos |
|---|---|---|
| 0.2.0 | 2026-08-21 | `agentfluent`, `claude-code-sessions` — held as the untreated control until 2026-10-31, then moved straight to 0.4.0 (#285) |
| 0.2.1 | 2026-08-26 | `claude-code-loop`, `us_presidential_vote_analysis` — **n=10 / n=12** admissible sessions (vote `d53db569` excluded as 0.2.0-era, F170) |
| 0.3.0 | 2026-09-11 (local; `installed_plugins.json` stamps it `2026-09-12T00:39Z`) | `claude-code-loop`, `us_presidential_vote_analysis`, `sportswear-esg-news-classifier` — the sharding epic's before side (`baseline-2026-10-04.md`) |
| **0.3.1** | **2026-10-08** loop and vote (~15:55 local); **2026-10-09** esg (21:40 local) | the three above — **#133-treated**. Also **`claude-hook-validator`**, onboarded at 0.3.1 on 2026-10-09: **baseline-only, not #133-treated** — it has no 0.3.0 before side, and D007 forbids pooling, so its 0.3.1 sessions are its own before-baseline for the next engine-changing release. Also the GitHub Pages repo `frederick-douglas-pearce.github.io`, onboarded at 0.3.1 on 2026-10-26 |
| **0.4.0** | **2026-10-30/31** (UTC stamps `2026-10-30T23:10Z`–`2026-10-31T02:47Z`) | **every consumer**: `claude-code-loop`, the Pages repo, `claude-code-sessions`, `claude-hook-validator`, `sportswear-esg-news-classifier`, `agentfluent`, `us_presidential_vote_analysis`. Shipped unmeasured by decision (#271). `KNOWN_FILE_BYTES`, `ERAS` (boundary 2026-10-31, local) and `LOAD_TOKENS` carry 0.4.0. The `LOAD_TOKENS` rows were measured 2026-11-04 over `claude-opus-5-5` parents. ⚠ `reference/plan-gate-inferred.md` has no row, since no session read it in full, so a 0.4.0 session that reads it still refuses |
| **0.5.0** | **2026-11-04** (local 01:13–02:05 -0800; UTC stamps `2026-11-04T09:13Z`–`10:05Z`) | **every consumer**, the same seven. The second round of unmeasured deletions (#271) plus #109. `KNOWN_FILE_BYTES`, `ERAS` (boundary 2026-11-05, local) and `LOAD_TOKENS` carry 0.5.0. The `LOAD_TOKENS` rows were measured 2026-11-13 (#341) over the `opus-5` family's parents, with a row for every file the era requires |
| **0.6.0** | **2026-11-16** (local; released the same day, release PR #348, `44e0c69`). Staggered: `us_presidential_vote_analysis` 2026-11-15 23:57 -0800 (UTC `2026-11-16T07:57Z`) as the canary, the other six 2026-11-16 19:22–20:06 -0800 (UTC `2026-11-17T03:22Z`–`04:06Z`) | **every consumer**, the same seven. Vote's canary passed (vote #540, PR #549, ran on 0.6.0 throughout). #309's `MODEL_TIERS` vocabulary, behavior-neutral (every role inherits; always-loaded 44,471 → 45,488 tokens, +2.29%). `KNOWN_FILE_BYTES` carries 0.6.0, measured from the tree at `5391906` before install and checked against the 0.6.0 cache on 2026-11-16 (all eight files match). `ERAS` carries 0.6.0, date-only (boundary 2026-11-17, local); vote's 11-16 rows, including the canary, ran 0.6.0 but are filed as 0.5.0. The `LOAD_TOKENS` rows were measured 2026-11-17 (#353) over the `opus-5` family's parents, with a row for every file the era requires. Stratum at the cut: every interactive (`cli`) parent session in this repo and vote started 2026-11-14T00:00Z–2026-11-15T07:48Z ran `claude-opus-5-5@high`, and the `@medium` sessions in that window are `sdk-py` runs, not interactive ones. Compare within one stratum only (D007) |

⚠ **The v0.3.0 release grew the engine 50.8%** (177,529 → 267,647 bytes; always-loaded 45,937 →
69,457 tokens). Two consequences, both of which bit the instruments before anyone measured anything:

- `engine_cost.py`'s admissibility floor was a **hardcoded 0.2.0 constant** and so turned fail-open
  the moment 0.3.0 installed — a session holding 66–99% of its engine scored `ADMISSIBLE`. The floor
  is now derived **per session** from the era in the read path. Do not reintroduce a constant.
- **The floor's unit was wrong too (F191), and #133 fixed it.** It was `bytes / 3.5` chars per token,
  but engine text enters the context at ~0.38 context tokens per byte, so the floor admitted ~75% of
  a 0.3.0 load. It is now **one complete load per file, in context tokens**, measured from sessions
  whose reads cover every line (`LOAD_TOKENS`, which names each row's source). The floor is 98% of
  that load. A required file with **no** measured row refuses; nothing is estimated. Rows are per tokenizer family as well
  as per file: re-measure them before scoring a parent model on a different tokenizer.
- **Every frozen baseline in `baseline-2026-08-25.md` is against a 45,937-token engine.** P1's
  ~30,000 target was a ~35% cut from that; the same cut against 69,457 lands near ~45,100. Anything
  comparing across this boundary must say which engine each side ran.

**`budget_stats.py --era` now resolves N eras, not two**, and caps the date-derived era at the
version a repo actually has installed — without that cap a held-back control reads as treated, which
does not make the DiD noisier, it inverts it. Note 0.2.1 writes no ledger vocabulary of its own, so
marker attribution returns a **bound** (`0.2.0|0.2.1`) rather than a false exact era. 0.3.1 is the
same (`0.3.0|0.3.1`), and its date boundary in `ERAS` is 2026-10-10, the first day no treated repo
could still be on 0.3.0.

The three levers this work ranks, in the same units:

| lever | value | basis | confidence |
|---|---|---|---|
| avoid one gate round | ~561–850k **input+output, per issue** | r=+0.79 + Finding 2's mechanism | correlational |
| batch same-file paging reads | ~176k **input-only, per session** (358k theoretical) | run-length corrected | rough order |
| shard the engine (#128) | ~4–5% of a run | modelled, not measured | low |

↳ *#212: figures here predate #212's cost arithmetic; see [`cost-arithmetic-rerun-2026-09-28.md`](cost-arithmetic-rerun-2026-09-28.md).*

**These are not in the same units and an earlier version of this table said they were.** The gate-round
figure is input+output per *issue*; the batching figure is input-only per *session*. On a common
basis the gate-round lever is ≈714k input-equivalent. The ranking survives the correction; the
"same units" claim did not.
