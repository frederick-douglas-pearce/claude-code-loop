# Benchmark fixture set — 2026-11-21 (#381)

Seven closed issues, from the three repos that run the loop, for R1's paired benchmark (#288) to
replay. Each pick records its repo, source base SHA, route, historical rounds, the reason it was
chosen, and three feasibility fields: how likely a replay is to halt at `in-review`, what its CI
row must be rebound to, and whether its config can be frozen; and which of its acceptance criteria
the replay's sandbox can discharge. One pick, **vote #82**, is named for
#274's control replay.

This note is the selection and its reasons. It builds no fixture: #274 builds the control-replay
pick, and #288 builds the rest. #288's per-pick `fixture.json` is the machine-readable record, so
nothing here is in a second, machine-readable copy that could drift from it.

**Where the facts come from.** Every SHA, diff size, issue state, workflow and config row below was
read from git and `gh` on 2026-11-21. Rounds and stop histories were read from each repo's loop
ledger (`.claude/loop/<run>/progress.md`). The ledgers are gitignored and exist only on the
maintainer's machine, so this note names the run and the facts, not paths. Where a fact could not
be re-derived it says "not established".

## The repos

| Short name | Repository | Merge shape | Base of a pick |
|---|---|---|---|
| vote | `frederick-douglas-pearce/us-presidential-vote-analysis` | merge commit | `merge-base(M^1, M^2)` |
| esg | `frederick-douglas-pearce/sportswear-esg-news-classifier` | squash | `S^` |
| loop | `frederick-douglas-pearce/claude-code-loop` (this repo) | merge commit until #346, squash since | `merge-base(M^1, M^2)` for a merge commit, `S^` for a squash |

"Source base SHA" below is the commit in the source repo. A built fixture's `base_sha` is a
different SHA, because `replicate.py`'s `build_base` re-commits the copied tree with a fixed
identity and date.

**The derived base is a proxy for the base the historical run worked on, and it is checked.** Where
a run journaled its base (`$BASE`, or the base it named), the two are compared; where it did not,
the branch must root on the derived base with no merge from main in between. Six picks pass. esg
#93 does not: its run planned and reviewed on `a8ca32c`, and its derived base `504810a` differs from
that only in `.claude/loop.config.md` (its section says what follows).

## The selection rule

Applied in this order.

1. **Closed as COMPLETED, one merged PR, and replayable in the sandbox.** This rule is about what
   a replicate can do, not about how the historical run checked its own work. (Read the second way
   it would exclude every ≥ 5-round pick, since each of those runs had a human release the review
   cap mid-run.) It has two parts:
   - **Hard part.** Everything before step 10 — planning, `TEST_CMD` and `HERMETIC_TEST_CMD`, and
     code review — must be able to run in the replicate's sandbox from what is tracked at the base
     plus what the fixture supplies. A pick that fails this is out.
   - **Disclosure part.** Any acceptance criterion that step 10 cannot discharge in the sandbox —
     because it needs a database, a corpus or service outside the repo, a paid API call, or a
     secret — is named in the pick's section, with its consequence. **If you cannot tell, it is
     named.**

   An undischargeable criterion does not move where a replicate halts in review. It fixes the kind
   of step-10 stop the pick reaches, the same in both arms, and raises step-10 cost. It can also
   raise the ac-verify round count, since an unmet criterion sends step 10 to its second round, and
   outcome 1 counts ac-verify rounds. Whether such a pick counts toward any outcome is #382's to
   decide.
2. **No reason to read the dev-loop engine inside the fixture repo.** `replicate.py`'s
   `audit_engine_loads` records a problem for any engine read that `engine_cost.classify` calls
   `'tree'` (an engine file read at a path with no `/.claude/plugins/cache/` segment), and the audit's `pass`
   requires `b_engine_loads` to be empty. So a pick whose diff, tests or acceptance criteria need
   the repo's own `skills/dev-loop/` copy is out, and **if you cannot tell, it is out**. This
   removes every loop-repo issue that edits or guards the engine.
3. **A replay reads the issue body and nothing else.** A fixture carries `issue.body` only. A pick
   whose historical plan relied on an issue comment, or whose body was edited during the run, is out
   unless the note names the body revision the fixture uses and that revision is enough. None of
   the seven bodies was ever edited (`userContentEdits` is empty for all seven); the pre-merge
   comments are listed per pick.
4. **Rounds.** Appendix A §4 (`cost-review-2026-10-26/A-design-R1-fix-agent-and-ceiling.md`)
   counts rounds as code-review plus ac-verify (its outcome 1); the issue says "review rounds". The two picks that carry the "≥ 5" slot have
   code-review = 5 on their own, so they qualify under either reading. Every other pick is labeled
   with its two numbers and claims neither threshold. "Clean in two" means code-review = 1 and
   ac-verify = 1.
5. **Prefer picks with no historical round-1 design-question stop.** That stop halts a replicate
   before any fix is applied, in both arms, so it cannot show an R1 effect. The cost to the
   estimand: results hold for issues without such a stop and do not carry over to all issues.
6. **Spread:** at least one pick per repo, and small diffs where there is a choice, to keep the
   replay cost down.

## The picks

| # | Repo | Issue (PR) | Source base SHA | Route | Rounds (code-review / ac-verify) | Ledger run; merged (UTC) | Role in the set |
|---|---|---|---|---|---|---|---|
| 1 | vote | #172 (#202) | `1aa95d07f0721129d64b5c55aefa5f42fa020f73` | code | 5 / 2 | epic-tech-debt; 2026-08-30 | ≥ 5 rounds |
| 2 | esg | #74 (#108) | `0c94ff9ef04455f330dc344b69c2c5298cb74ed7` | code | 5 / 2 | silent-success; 2026-09-09 | ≥ 5 rounds |
| 3 | esg | #93 (#110) | `504810a4f1fe908c2f0bcc90401ed3d58fbc09a6` | code | 4 / 2 | silent-success; 2026-09-12 | high by code-review + ac-verify only |
| 4 | loop | #199 (#205) | `0871430420a73d89a9cd29a13af089221aef1862` | code | 3 / 1 | epic-publishing; 2026-09-26 | middle; the loop pick |
| 5 | esg | #211 (#261) | `3fef3d8d30539df99aaf61900b7ee373f13e4e1d` | code | 3 / 1 | eval-calibration; 2026-11-08 | middle |
| 6 | vote | #392 (#542) | `b8dcb4be0f0056a7de442f5f4e63be812bd2ebca` | code | 2 / 1 | epic-dashboard-ui; 2026-11-16 | low; the working negative |
| 7 | vote | #82 (#115) | `92ce679581a9535406963150af9e0803790b1ede` | code | 1 / 1 | chores; 2026-07-26 | clean in two (by the numbers only); **#274's control replay** |

All seven issues are CLOSED with `stateReason` COMPLETED, and each PR's closing reference is its
issue. No diff touches a `skills/dev-loop/` path. Rounds are the `gate-rounds=` slot of each
iteration's close-record `- Budget:` line (for #199, the corrected line that follows its close
record).

The set meets appendix A §4's mix: #172 and #74 took five code-review rounds each, and #82 was
clean in two by its recorded numbers (1 / 1; its section says why that is weak). Seven picks leaves three of the issue's ten slots for #288.

## Fields every pick shares

**`CI_STATUS_CMD`.** Every base binds `gh pr checks <PR>`. `replicate.py`'s `ci_status_binding`
refuses anything but the Actions-API form (`gh run list|view …` or
`gh api repos/<o>/<r>/actions/…`), because the sandbox token cannot read checks. So **every
fixture rebinds this row**, to the workflow named per pick. Workflows that need a secret or run on
a schedule cannot work in a fixture repo and should be dropped from the copy; the per-pick lists
name them, and also name any other workflow the pick's PR would trigger. A binding of the form
`gh run list --workflow <file>` reads only the named workflow; the others still run in the fixture
repo, but no gate reads them.

**`MODEL_TIERS`** is absent at every base. The 0.6.0 engine reads an absent row as every role
inheriting, so it needs nothing.

**`BACKLOG_SOURCE`** is rebound at every base, to the fixture's label.

**Config call.** "Frozen with named rebinds" means the base's `loop.config.md` with only existing
rows changed. A config that needs a row added is "newly authored". No base config runs under the
0.6.0 engine unchanged.

**Roster.** Every base config binds `SCOPE_AGENT` to `pm` and `DESIGN_AGENT` to `architect`, both
user-global, so every fixture must supply them. vote #392's base also names a `ba` agent.

**In-review halt.** Every `in-review` stop halts a replicate (`REPLY_STATUSES = {None,
"planning"}` in `replicate.py`, #371), and every replicate ends unmerged at its first
`in-acceptance` stop (`FINAL_STATUSES`). Each pick's call is split in two:

- **(a) a halt at a round-1 design-question stop.** This is censoring in the plain sense: it
  happens before R1 acts, and both arms should halt there at the same rate.
- **(b) a halt at the round-2 cap.** The harness records it as a halt, but on a high-round pick
  reaching the cap is the thing R1 is meant to reduce. Whether (b) counts as censoring or as an
  outcome is #382's to pre-register; this note records the split and does not decide it.

The only measured base rate is the pilot fixture, a trivial issue: 1 of 3 replicates @high halted
at `in-review` and none @medium did (`replicate-repilot-2026-11.md:87`). Every call below is a
judgment from one history, made under whatever engine ran it.

**What the sandbox can discharge.** Each pick has a **Sandbox** line under rule 1: whether the hard
part holds, and which acceptance criteria step 10 cannot discharge in the sandbox, or that it can
discharge them all. Where nobody walked a criterion, the line says "not established".

**Engine era** comes from `README.md` → Status, which dates each install, and from root `CLAUDE.md`
→ Dogfooding this repo for anything before 0.2.0, which that table does not cover. Where neither
settles a pick, it says "not established".

## Per pick

### 1. vote #172 — unit-tier `bool(x) is False` shapes (≥ 5 rounds)

- **Diff:** 6 files, +302/−25, all under `tests/`: `tests/_helpers.py`, four unit-test modules,
  and `tests/integration/test_snapshot_build.py` (+16/−4), a live-Postgres integration test.
- **Why it is here:** five code-review rounds and no design-question stop. Round 1 found two
  correctness defects; rounds 2–4 each found new false claims inside the previous round's fix text
  (8 false claims across all five rounds), and round 5 was clean. That is the pattern R1's fix agent
  is meant to change, and appendix A §4 names this issue as a candidate. With the loop repo's
  engine-prose issues ruled out by rule 2, R1's outcome 2 (the claims count) rests mostly on this
  pick.
- **Stops in review:** three: round 2 dirty at the cap, then rounds 3 and 4 dirty, each after a
  human release of the cap. Engine 0.2.1.
- **In-review halt:** high overall. (a) low; (b) high.
- **Sandbox:** the hard part holds, because `TEST_CMD` deselects the integration tier
  (`addopts` in `pyproject.toml` at the base includes `-m 'not integration'`). Not dischargeable: the issue
  has no acceptance-criteria section, and the run's plan wrote an AC-8 — `uv run pytest -m
  integration` green locally against a throwaway `postgres:16` — that its architect made a merge
  precondition. That run also needs the three local corpora. A replay's step 10 cannot do it, so
  this pick's step-10 stop kind is fixed by the environment. #288 must also make sure a replicate
  cannot reach a Postgres that happens to be running on the host, or the replay depends on host
  state.
- **CI:** `ci.yml` (jobs `checks`, `integration` and `docker-build`; `integration` runs a
  `postgres:16` service container, and `docker-build` builds the Docker image; no secret). Drop `api-canary.yml` (schedule, secret), `deploy.yml` (secrets),
  `pages-sync.yml` (secret). `prettier.yml` runs on every PR; `og-card-guard.yml` is path-filtered
  and this diff does not trigger it.
- **Config:** frozen with named rebinds. `HERMETIC_TEST_CMD` is
  `unshare -rn -- sh -c 'ip link set lo up && uv run pytest'`. Whether that runs inside the
  harness's bubblewrap is untested; if it cannot, a row that changes a test (this one does) gets a
  `gate-error`, so #288 must check it before the pick is built. `CODE_REVIEW` binds the
  `/code-review` skill.
- **Auto-loaded at base:** root `CLAUDE.md`, 56,101 bytes; no nested `CLAUDE.md`;
  `.claude/settings.json` enables the dev-loop plugin only; no tracked agents or hooks.
- **Tests need:** `uv sync --locked --dev` (third-party wheels). Tracked tree 209 files, 5.6 MB.
- **Pre-merge comments:** one, the run's own architect review (2026-08-29), which a replay
  regenerates.

### 2. esg #74 — explicit unknown/check_failed state (≥ 5 rounds)

- **Diff:** 9 files, +1459/−81: `src/agent/health.py`, `src/agent/workflows/base.py`,
  `src/agent/workflows/drift_monitoring.py`, two test modules, and four docs files
  (`CLAUDE.md`, `docs/AGENT.md`, `docs/CHANGELOG.md`, `.claude/specs/decisions.md`). Offline tests.
- **Why it is here:** ordinary code with five code-review rounds. It is the largest pick; it is kept
  because the planning pass found no smaller ≥ 5 issue in esg without a round-1 design-question stop
  or an outside dependency. That search used rule 1's earlier wording, under which a dependency
  needed only at acceptance excluded a candidate, and it was not re-run under the amended rule.
- **Sandbox:** the hard part holds (offline tests). Every criterion can be discharged in the
  sandbox: AC4 ("reading an archived YAML written before this change still loads") by a tracked
  fixture YAML in the pre-verdict shape, which the run wrote. Fidelity: the historical verifier also
  loaded all 1,461 real archives in `~/.esg-agent/history` and the live `state.yaml`, which a replay
  cannot.
- **Stops in review:** three: round 2 dirty at the cap, then rounds 3 and 4 dirty, both
  human-authorized. No round-1 design-question stop. After round 2 the human directed an architect
  consult on three of its findings that had a design component, and the architect ruled one of them a
  live design defect (recorded in esg's D010). The engine that ran it had no scope-ruling stop; under
  0.6.0 such a finding would raise one, but at round 2, where the cap already halts, so it changes no
  halt location.
- **Engine era:** not established. The Status table first lists esg at 0.3.0 (2026-09-11), two days
  after this merge.
- **In-review halt:** high overall. (a) low; (b) high.
- **CI:** `ci.yml` (one job, no secret, no service; `uv sync --frozen --extra dev`, which installs
  `torch` through `sentence-transformers`). Drop `deploy.yml` and `monitoring.yml` (secrets;
  `monitoring.yml` also scheduled).
- **Config:** frozen with named rebinds. `HERMETIC_TEST_CMD` is `—` plus a reason.
- **Auto-loaded at base:** root `CLAUDE.md`, 30,614 bytes; `.claude/settings.json` wires
  `PreToolUse` and `PostToolUse` hooks (`.claude/hooks/block_secret_reads.py`,
  `.claude/hooks/detect_secrets_in_output.py`); four project skills under `.claude/skills/`.
- **Tests need:** uv and the full dependency set. Tracked tree 364 files, 134 MB.
- **Pre-merge comments:** one, an architect review posted 2026-09-05, four days before the run. Its
  decision (the verdict is not a `WorkflowStatus` member) is also in the tree at the base, in esg's
  D008, and the plan cites D008, not the comment. The body (never edited) plus the tracked decision
  log is enough.

### 3. esg #93 — `check_container` collapses three Docker states (high by c + v)

- **Diff:** 6 files, +1267/−16: `scripts/backup_db.sh`, `tests/test_backup_db_script.py`, and
  four docs files. The tests put a fake `docker` on `PATH`.
- **Why it is here:** six rounds by code-review + ac-verify (4 / 2), and two in-review stops with no
  design question. It does not carry the "≥ 5" slot.
- **Stops in review:** two: round 2 dirty at the cap, then round 3 (human-authorized) with sound
  code and dirty prose. A fourth round deleted the prose.
- **Engine era:** not established. The iteration's journal blocks span 2026-09-11 to 2026-09-12,
  across the day 0.3.0 was installed.
- **In-review halt:** high overall. (a) low; (b) high.
- **Sandbox:** the hard part holds. Criteria 1–6 are checkable through the fake-`docker` harness
  the tests use, and criterion 7 is a decision. Fidelity: the historical review measured one gap
  against a live PostgreSQL 16.11 server, which a replay's review cannot reach.
- **CI:** as esg #74.
- **Config:** frozen with named rebinds, from the derived base `504810a`. It is not #74's config
  (`git diff 0c94ff9 504810a -- .claude/loop.config.md`). Among the differences: a §6, "Claim
  authoring — the class this project does not assert", a rule against writing the kind of claim
  R1's outcome 2 counts, which #74's base lacks; and a `DESIGN_AGENT` row and §2 preamble that add
  the step-8 scope ruling. The run itself planned and reviewed on `a8ca32c`, which already had §6
  but not the `DESIGN_AGENT` and §2 changes, so the fixture freezes a config the historical run did
  not have. That part matters only if a design-question finding arises, and #93 had none.
- **Auto-loaded at base:** as esg #74, with root `CLAUDE.md` at 30,911 bytes.
- **Tests need:** as esg #74. Tracked tree 365 files, 134 MB.
- **Pre-merge comments:** one (2026-09-07), correcting the body's SIGPIPE framing: the inversion is
  a race, not a buffer-size threshold. The plan does not cite it, its approach removes the pipe
  altogether, and no acceptance criterion turns on the mechanism. The body (never edited) is
  enough.

### 4. loop #199 — publisher: pin the production wiring (the loop pick)

- **Diff:** 3 files, +247/−17: `tests/test_publish_to_pages.py`, `tooling/publish-to-pages.py`,
  `tests/CLAUDE.md`. Stdlib suite.
- **Why it is here:** the one loop pick. Rule 2 rules out every loop issue that touches the engine,
  and every non-engine loop candidate the planning pass examined (eleven) had a round-1
  design-question stop, so this slot is filled against rule 5.
- **Stops in review:** two: a round-1 stop on three design questions (scope ruling, then the human),
  and round 2 dirty at the cap. Round 3, human-authorized, was clean. Engine 0.3.0.
- **In-review halt:** high overall. (a) high; (b) high.
- **Audit risk no other pick has:** the base's root `CLAUDE.md` describes the engine and names its
  path, and the base tree contains `plugins/dev-loop/skills/dev-loop/`. One tool read of that copy
  fails the replicate's audit.
- **CI:** `test.yml` (no secret, no service). Drop `pages-sync.yml` (secret). This diff touches
  `tooling/publish-to-pages.py`, which is in the path filters of `humanizer-guard.yml` and
  `og-card-guard.yml`, so both would run on the PR; `prettier.yml` runs on every PR.
- **Config:** frozen with named rebinds. `HERMETIC_TEST_CMD` is `—` plus a reason.
- **Auto-loaded at base:** root `CLAUDE.md`, 38,773 bytes; `tests/CLAUDE.md`, 17,805 bytes, loads
  when the diff's test file is opened; `plugins/CLAUDE.md` (12,444 bytes) loads if anything under
  `plugins/` is opened. Only a read of an engine file under `skills/dev-loop/` fails the audit.
  `.claude/settings.json` enables the dev-loop plugin only.
- **Sandbox:** the hard part holds, and all four criteria can be discharged in the sandbox: the
  tests run on the stdlib against a temporary git fixture, and AC3's mutation check runs through
  the plugin's own harness.
- **Tests need:** `python3` only. Tracked tree 67 files, 1.5 MB.
- **Pre-merge comments:** none.

### 5. esg #211 — agent processes import the whole labeling package (middle)

- **Diff:** 7 files, +241/−45: `src/agent/llm.py`, `src/labeling/__init__.py`,
  `src/labeling/config.py`, two test modules, `CLAUDE.md`, `docs/CHANGELOG.md`. Offline tests.
- **Why it is here:** a recent engine, a config close to current, and one in-review stop with no
  design question.
- **Stops in review:** one, round 2 dirty at the cap (round 1 recorded "Design-question findings:
  none"). Round 3 was human-directed. Engine 0.5.0.
- **In-review halt:** medium overall. (a) low; (b) medium.
- **Sandbox:** the hard part holds (offline tests). Criteria 1 and 2 (the import isolation and its
  pinning test) are discharged by tracked tests. Criterion 3 ("`scripts/label_articles.py` and the
  labeling cron behave as before") was discharged by running `label_articles.py --stats`, which
  initializes the database, and a `--dry-run`. Whether `--stats` needs a live database is not
  established, so under rule 1 that half is named as not dischargeable, and this pick's step-10
  stop kind may be fixed by the environment.
- **CI:** as esg #74.
- **Config:** frozen with named rebinds. It is not #74's config
  (`git diff 0c94ff9 3fef3d8 -- .claude/loop.config.md`). Among the differences, it carries the same
  §6 "Claim authoring" rule as #93's base, which #74's base lacks, and a `DESIGN_AGENT` row that adds
  the step-8 scope ruling.
- **Auto-loaded at base:** root `CLAUDE.md`, 61,060 bytes; same hooks and skills as esg #74.
- **Tests need:** as esg #74. Tracked tree 408 files, 91 MB.
- **Pre-merge comments:** one owner comment (2026-11-04) on placement and the overlap with #252.
  The plan's one reference to #252 is a test name in the tree. The body (never edited) is enough.

### 6. vote #392 — filter sentence and glossary on the election and state pages (the working negative)

- **Diff:** 4 files, +217/−71: `dashboard/explore/pages/state.py`,
  `tests/unit/test_dashboard_state.py`, `docs/glossary.md`, `dashboard/CLAUDE.md`. Unit tier only.
- **Why it is here:** the low-round pick from a recent engine. It is not clean in two and it breaks
  rule 5; the planning pass found no code-route vote issue closed since 2026-11-01 that passed
  review with no stop.
- **Stops in review:** one, a round-1 stop on three design-question findings (scope ruling, then
  the owner). Round 2 closed with one EDITORIAL finding, swept. Engine 0.5.0: it merged
  at 04:25Z on 2026-11-16, before the vote repo's 0.6.0 install at 07:57Z.
- **In-review halt:** medium overall. (a) medium; (b) low.
- **CI:** `ci.yml` (as vote #172). Drop `api-canary.yml`, `deploy.yml` and `pages-sync.yml`
  (secrets or schedule). `deploy-dashboard.yml` is dispatch-only. This diff touches `dashboard/`,
  so `e2e.yml` (Playwright, path-filtered) runs on the PR; `prettier.yml` runs on every PR;
  `humanizer-guard.yml` and `og-card-guard.yml` are path-filtered and not triggered.
- **Config:** frozen with named rebinds; `HERMETIC_TEST_CMD` as vote #172, with the same bubblewrap
  question. `CODE_REVIEW` binds the `/code-review` skill. Two of the issue's acceptance criteria defer
  wording to the `ba` agent, which the fixture must supply.
- **Auto-loaded at base:** root `CLAUDE.md`, 19,626 bytes; `dashboard/CLAUDE.md`, 92,416 bytes,
  loads as soon as the diff's page module is opened. Five more nested `CLAUDE.md` files load only
  if their directories are opened. `.claude/settings.json` enables the dev-loop plugin only.
- **Sandbox:** the hard part holds, and all three criteria (page code, its unit test, and glossary
  entries) can be discharged in the sandbox, provided the fixture supplies the `ba` agent.
- **Tests need:** `uv sync --locked --dev`. Tracked tree 391 files, 14 MB.
- **Pre-merge comments:** none.

### 7. vote #82 — consolidate PV validators (clean in two; #274's control replay)

- **Diff:** 8 files, +358/−53: `src/usvote/pv/validate.py` (new), `src/usvote/pv/__init__.py`,
  three transform/reconcile modules, two unit test modules, `CLAUDE.md`. Unit tier.
- **Why it is here:** it fills the "clean in two" slot by the numbers only. Its review gate was
  discharged with `/review 115` rather than the bound `/code-review` (the run's own correction note
  says so), review and AC-verify are journaled together in one block at the merge gate, and it ran
  under engine 0.0.1, which put AC-verify before code review. (0.0.1 is not in the Status table;
  every consumer ran it until the 2026-08-21 re-install, per root `CLAUDE.md`.)
- **Stops in review:** none recorded.
- **In-review halt:** low to medium overall, on thin evidence. (a) and (b) both low to medium.
- **CI:** `ci.yml` (as vote #172). Drop `deploy.yml` (secrets). No other workflow at the base.
- **Config:** newly authored. The base config has every row the 0.6.0 engine reads except
  `HERMETIC_TEST_CMD` and `MODEL_TIERS`. An absent `HERMETIC_TEST_CMD` on a code row that changes a
  test is a `gate-error`, so the row must be added; and the rest of the file was written for engine
  0.0.1.
- **Auto-loaded at base:** root `CLAUDE.md`, 24,726 bytes; `.claude/settings.json` enables the
  dev-loop plugin only.
- **Sandbox:** the hard part holds. The issue has no acceptance-criteria section; the run's plan
  took three from its body (one shared grain check and one shared totals check under `usvote/pv/`,
  called by both sources). They are refactor criteria checked by unit tests, and all can be
  discharged in the sandbox.
- **Tests need:** `uv sync --locked --dev`. Tracked tree 156 files, 3.0 MB.
- **Pre-merge comments:** one, the run's own architect review, which a replay regenerates.

## #274's control replay: vote #82

#274 needs one control-arm replicate that reaches its first `in-acceptance` stop, and draws no
comparison. So the right pick is the one least likely to halt in review and cheapest to build; how
weak #82 is as a historical true negative does not matter there. On the evidence there is, #82 has
the lowest halt likelihood of the seven, and it is a 3 MB tree with no `torch`.

What it costs: its config is newly authored (a `HERMETIC_TEST_CMD` row has to be written), and it
will be the first fixture to need `uv sync` and third-party wheels inside the sandbox, which the
pilot never exercised. The two alternatives considered were loop #199 (the cheapest build, but two
historical in-review stops and the audit risk above) and esg #211 (a recent engine, but a
historical cap stop, a 91 MB tree and a `torch` install). The plan recommended #82, and the human's
approval at the plan gate named no other pick.

## Considered and not picked

- **loop, rule 2 (the issue reads or edits the engine):** #44, #121, #28, #120, #23, #29, #31, #60,
  #113, #166, #170.
- **loop, other:** #366 and #380 (the harness itself); #133, #126, #73 and #207 (not replayable);
  #261 (one stop, but no test the suite runs, and a human hand check); #226, #238, #239, #180,
  #178, #183, #212, #272 and #273 (outside data, workflow files, or mid-run amendments).
- **vote:** #157 (its guard reads the sibling Pages repo's history); #181 and #234 (census corpus
  outside the repo, and round-1 design-question stops); #167 (Postgres warehouse; 15 files); #191
  (figures verified against the live API and a local corpus); #486 (needs a live Actions cache);
  #423 and #440 (an owner approval; the deployed site); #558 and #559 (Playwright; two PRs or an
  in-run comment).
- **esg:** #75 (five in-review stops, one a design question); #239 (a design-question stop); #259
  (no stops, but every touched test needs Postgres); #154, #155 and #248 (open).

These reasons are the planning pass's reads and were not re-derived here. They were also applied
under rule 1's earlier wording, which excluded a pick for how its criteria were historically
checked. Under the amended rule, a candidate excluded only for that reason (needing outside data or
a live service at acceptance, not before it) would be disclosed rather than excluded. None was
re-examined, so #288 should re-check any it wants for the three open slots.

## Observations for #382

Facts with their evidence. None decides anything; each is #382's to use or not.

1. **A replicate can show at most two review rounds.** Since the two-round cap, a third round
   exists only because a human authorized it, so every issue that took five code-review rounds
   stopped in review at least once, and on replay each such stop halts (`REPLY_STATUSES`). Appendix
   A §4's outcome 1 ("lower by at least one round") can be read only as a censored comparison: a
   replicate that needs a third round halts at the cap. Outcome 2 beyond round 2, outcome 5's "what
   the human chose", and outcome 4's 14-day fix-up commits (nothing merges) cannot be observed as
   written.
2. **A round-1 design-question stop halts before R1 acts.** The planning pass counted it in 29 of
   37 esg rows, in all eleven non-engine loop candidates, and in 32 of 37 low-round vote rows since
   2026-11-01. Those are the planning pass's counts and were not re-counted here. Halts of that kind
   should not differ between arms, which makes them a candidate negative control.
3. **"Clean in two" exists only under engine 0.0.1.** Across every line carrying a `gate-rounds=` slot in
   the three repos' ledgers (134 loop, 161 vote, 38 esg), code-review = 1 with ac-verify = 1 is on
   13 lines,
   and the latest are vote #152 and #132 on 2026-08-12; none is in esg. The planning pass also found
   no code-route vote issue since 2026-11-01 that passed review with no stop. A definition of
   "clean" that the control arm sets for itself (it reaches `in-acceptance` within two rounds in
   every replicate) is one way to fill the slot.
4. **Loop-repo issues that edit or guard the engine cannot be fixtures** while the audit rejects
   in-tree engine reads (rule 2).
5. **Some picks reach a step-10 stop whose kind the environment fixes.** vote #172 has a criterion
   the sandbox cannot discharge, and esg #211 may (rule 1's disclosure part; their sections). Such a
   pick reaches the same kind of step-10 stop in both arms, possibly after a second ac-verify round.
   Whether it counts toward an outcome is #382's to decide (rule 1).

## Scope

This note selects and records. Building a fixture directory is #274's job for vote #82 and #288's
for the others.
