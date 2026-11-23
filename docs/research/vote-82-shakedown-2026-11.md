# The vote #82 fixture and its sandbox shakedowns (#392, 2026-11-22)

`replicate-fixtures/vote-82/` is the fixture for #274's control replay (`benchmark-fixture-set.md`,
pick 7). This note records how it was built and what its model-free shakedowns showed. A shakedown
runs one command in the replicate sandbox with no model, no credentials, and no GitHub repos
(`replicate.py shakedown`), so it costs nothing. It is how to learn whether a fixture's gates can
run before a paid replicate does.

## The fixture

- **Source:** `frederick-douglas-pearce/us-presidential-vote-analysis` at
  `92ce679581a9535406963150af9e0803790b1ede`. The source's tracked tree is 156 files; `repo/` holds
  154 of them, less the two `dropped` below. `source-tree.txt` is `git ls-tree -r` at that commit,
  verbatim.
- **Changes from the source:** `fixture.json` records every one with its reason. Its `rebinds` are
  five `loop.config.md` rows (`BACKLOG_SOURCE`, `CI_STATUS_CMD`, `CODE_REVIEW`, `LEDGER_ROOT`, and
  the added `HERMETIC_TEST_CMD`), the config preamble's host path, and one `.gitignore` entry. Its
  `dropped` entries are `deploy.yml` and `.claude/settings.json`. `renamed` stores `CLAUDE.md` as
  `CLAUDE.md.fixture`, which `build_base` restores, so the base carries the source bytes at the
  source path. `Vote82FixtureTests.test_base_differs_from_the_source_tree_exactly_by_the_records`
  checks the built base against `source-tree.txt` by blob and mode, file by file: every changed,
  dropped or added file has a record with a reason. Which rows of `loop.config.md` changed was
  checked by hand against the source (2026-11-22); no test compares rows.
- **Shared with the pilot, byte for byte:** the roster (`pm`, `architect`), the empty memory
  snapshot, and the stop list. The fixtures' roster hashes and stop behavior therefore compare.
- **Source issue:** #82 (`source.issue_url`). The fixture's `issue.body` is the body
  `gh issue view` returned on 2026-11-22, and `source.issue_body_sha256` is its hash.

## What was pinned

| Pin | Value |
|---|---|
| Harness commit | `0463017` (this PR's last fixture edit; `harness_tree_clean: true` on every run) |
| Fixture base | `4eacda1053018d345f3c66a755661e6a5561e2d7` |
| `fixture_sha256` | `66361f5ecc3288b5ca8dd9d96a3457360ac5731259863b836eac4901f533d7ad` |
| `uv` | `--uv-bin ~/.local/bin/uv`, `uv 0.9.5`, sha256 `d3dc3ca8e29337dd602a9a4df9e6edb15ebc52aed91461debeedb96939dc4ce0` |
| Python | `Python 3.14.0 (main, Oct 14 2025, 21:27:55) [Clang 20.1.4 ]`: `cpython-3.14.0-linux-x86_64-gnu`, downloaded by `uv` inside the sandbox on each run (33.0 MiB). The host's `python3` is 3.12.3. |

## The runs

All seven are in `replicate-fixtures/vote-82/shakedowns.sh` and were run at `0463017` on
2026-11-22, each in a fresh replicate directory with its own `HOME`, so its own `uv` cache. They
were first run at `0059048`, before review fixes changed `fixture.json`'s bytes but not `repo/`,
with the same results. At `0463017`, `lint-type`'s command exited 0, then the harness refused the
probe sandbox after it with `slirp4netns did not report ready` and recorded no probes. A re-run
under a new id (`lint-type-2`) was clean, and the table shows it. That message can also mask a
bubblewrap setup failure (a diagnostic gap first noted in #208's review).

| Run | Command | Exit | Result |
|---|---|---|---|
| `test-hermetic` | `uv run pytest && unshare -rn -- sh -c 'ip link set lo up && uv run --offline pytest'` | 0 | Both halves ran. The hermetic run: 698 passed, 12 skipped, 10 deselected. |
| `socket-open` | `python3 -c "import socket; socket.create_connection((\"1.1.1.1\", 443), 3)"` | 0 | Control: the probe connects from the sandbox. |
| `socket-blocked` | the same probe inside `unshare -rn -- sh -c 'ip link set lo up && …'` | 1 | `OSError: [Errno 101] Network is unreachable`. The block is at socket level. |
| `lint-type` | `uv run ruff check && uv run mypy` | 0 | `All checks passed!`; `Success: no issues found in 100 source files` |
| `locked` | `uv run --locked pytest` | 0 | 698 passed, 12 skipped, 10 deselected |
| `python-a` | `uv run python -VV` | 0 | `Python 3.14.0 (main, Oct 14 2025, 21:27:55) [Clang 20.1.4 ]` |
| `python-b` | `uv run python -VV` | 0 | the same build |

**AC4 (#392).** `shakedown` runs the config's `TEST_CMD` and `HERMETIC_TEST_CMD` inside the
sandbox, and both exit 0. The `unshare -rn` form runs under bubblewrap, so the row is the command,
not `—`. The command strings in `shakedowns.sh` are the config rows, byte for byte. `TEST_CMD`'s
cell carries three spans; the one counted is `uv run pytest`. The
`integration` marker's 10 tests are deselected, as at the source. The 12 skips are the real-corpus
tests in `tests/unit/test_ucsb_parse.py` and `test_ucsb_transform.py`, which skip unless
`USVOTE_UCSB_HTML_DIR` is set; the sandbox does not set it.

**#391's deferred item 2.**
- **Python:** with one `uv` binary, two runs that each downloaded Python into an empty cache got the
  same build string. That is consistent with `uv_sha256` pinning which Python `uv` downloads,
  because `uv` embeds its download metadata. It is n=2 on one day, so it does not prove that the
  build stays fixed over time.
- **Wheels:** `uv run --locked` passes, so `uv.lock` matches `pyproject.toml` at the base, and
  `uv run` installs from it. The lock records hashes, so the wheels are pinned by it rather than by
  the live index.

Item 1, the unpinned host tools, is named in `preregistration-template.md` §14.

## Bounds

- **Every replicate downloads Python 3.14 and its 126 packages.** The sandbox's network is used for
  this, and a run with no network access to `python-build-standalone` or PyPI cannot pass
  `TEST_CMD`.
- **The sandbox org's Actions policy is untested.** Vote's `ci.yml` uses `astral-sh/setup-uv@v6`, a
  `postgres:16` service, and `docker build`. The pilot used only `actions/checkout`. No shakedown
  reaches GitHub Actions, so this has to be checked by hand before #274's replay.
- **The memory snapshot is empty.** The source run had project memories that its config cites
  (`working-conventions` in §1's `SCOPE_AGENT` row and `local-api-testdrive` in §5 of the fixture's
  `loop.config.md`); the replay has none.
- **A replicate of this fixture must pass `--uv-bin`** with `uv 0.9.5`, sha256 `d3dc3ca8…4ce0`.
  `run` does not require the flag, and without it the sandbox has no `uv`, so `TEST_CMD` cannot
  run and the replicate stops at step 6. A refusal in the harness is a candidate for #384.
- **`/security-review` and `/verify` have not been exercised in the sandbox.** This is the first
  fixture whose `SECURITY_REVIEW` and `VERIFY` rows are skills invoked by name (the pilot binds both
  `—`). `builtin_agents` covers only the four agent types the pilot's spikes saw, so a sub-agent of
  any other type that `/security-review` spawns fails the strata audit, and `/verify`'s headless
  behavior is not established. The historical fix (`92ce679..c534650`) touched `usvote/pv/`, the
  MIT and UCSB transforms, `ucsb/reconcile.py`, tests and `CLAUDE.md`, none of config §4's
  sensitive surfaces, so step 9 most likely does not fire.
- **`CODE_REVIEW` is the pilot's inline finder fan-out**, not the `/code-review` the source bound.
  The historical run used `/review 115`, so neither arm replays the reviewer the source used.
- A shakedown's `output_tail` keeps the last 4000 characters, so a chained command shows only its
  last summary. Both halves of `test-hermetic` ran, as its exit code shows (`&&`).
