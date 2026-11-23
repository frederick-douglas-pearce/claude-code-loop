# US Presidential Vote Analysis — MVP Backlog

> **Status: DRAFT / TENTATIVE — pending Fred's review.** This backlog expands **E1, E2,
> E3, and the new UCSB epic E4** from [`../docs/ROADMAP.md`](../docs/ROADMAP.md). E1–E3
> are already filed as GitHub issues; E4 is filed in this round. Decisions referenced as
> D0NN live in [`decisions.md`](decisions.md).

Each section below is a GitHub issue body ready for creation. E1–E2 are M1 work; E3 is an
M1 spike; E4 (UCSB historical PV) is M2 work but **un-deferred** (see D014).

**Deferred / not-yet-scoped (named in the roadmap, expanded in a later round):** E5 (MIT
PV ingestion), E6 (canonical key + cross-source join), E7 (hybrid computation), E8
(internal API), E9 (explorer data mart). Per **D014** the former "E4 PV ingestion" is
split into the scoped **UCSB** epic (E4, below) and the named **MIT PV ingestion** epic
(E5). E5 depends on E3's MIT licensing finding; E6 depends on both PV sources landing. E4
does **not** wait on E3 — UCSB is the only source reaching ~1824 (D009).

**Package name:** `usvote` (fixed per D013), used throughout as `src/usvote/`.

---

**Label conventions:**
- Epic labels: `epic:scaffolding`, `epic:ec-ingestion`, `epic:pv-source-research`, `epic:ucsb-ingestion`
- Type labels: `enhancement`, `documentation`, `testing`, `infrastructure`, `research`
- Priority labels: `priority:high`, `priority:medium`, `priority:low`

**Create labels first:**
```bash
gh label create "epic:scaffolding" --color "0E8A16" --description "E1: src/ package scaffolding and infrastructure"
gh label create "epic:ec-ingestion" --color "1D76DB" --description "E2: Electoral College ingestion refactor + coverage extension"
gh label create "epic:pv-source-research" --color "5319E7" --description "E3: Popular-vote source determination spike"
gh label create "epic:ucsb-ingestion" --color "B60205" --description "E4: UCSB historical popular-vote scrape + ingest"
gh label create "enhancement" --color "A2EEEF" --description "New feature or request"
gh label create "documentation" --color "0075CA" --description "Documentation improvements"
gh label create "testing" --color "D4C5F9" --description "Test coverage and infrastructure"
gh label create "infrastructure" --color "E4E669" --description "CI/CD, tooling, project setup"
gh label create "research" --color "C2E0C6" --description "Research spike / written recommendation deliverable"
gh label create "priority:high" --color "B60205" --description "Must have for MVP"
gh label create "priority:medium" --color "FBCA04" --description "Should have for MVP"
gh label create "priority:low" --color "0E8A16" --description "Nice to have"
```

---

## E1: `src/` Package Scaffolding

**Issue title:** Epic: `src/` package scaffolding and infrastructure
**Labels:** `epic:scaffolding`, `infrastructure`

**Body:**

### Summary

Stand up the Python project structure, dependency management, testing infrastructure,
and CI that the EC ingestion refactor (E2) and everything downstream builds on. Today
the repo is a single monolithic notebook (`step1_electoral_college_data.ipynb`) plus a
thin psycopg2 wrapper (`db_tools.py`) with no package, no tests, no lockfile, and no CI.
This epic creates the `src/usvote/` package skeleton and the tooling around it, mirroring
the sibling agentfluent project's conventions (uv, pytest, ruff, mypy/pyright, GitHub
Actions). See D003 (adopt a tested `src/` package + reproducible pipeline) and D012
(mirror agentfluent conventions).

### Success Criteria

- [ ] Python package `usvote` (fixed per D013) with `pyproject.toml` managed by uv
- [ ] `uv sync` on a fresh clone installs all deps and creates the venv
- [ ] `src/usvote/` package layout exists with the module boundaries E2 will fill (scrape / parse / transform / load / db)
- [ ] pytest runs with coverage over `usvote`; `tests/unit`, `tests/integration`, `tests/fixtures` exist
- [ ] ruff (lint) and mypy or pyright (types) configured and passing on the skeleton
- [ ] GitHub Actions CI runs lint + types + unit tests on every PR to `main`
- [ ] CLAUDE.md updated to describe the new `src/` layout and uv/pytest tooling alongside the (still-present) notebook

### Stories

- [ ] #N — Initialize `usvote` package with uv and pyproject.toml (decide package name)
- [ ] #N — Define the `src/usvote/` module layout (scrape/parse/transform/load/db skeleton)
- [ ] #N — Port `db_tools.DBC` into `usvote.db` with unit tests
- [ ] #N — Set up pytest infrastructure with fixtures directory
- [ ] #N — Configure ruff + mypy/pyright
- [ ] #N — Configure GitHub Actions CI pipeline
- [ ] #N — Update CLAUDE.md and README for the `src/` layout

---

### E1-S1: Initialize `usvote` package with uv and pyproject.toml

**Issue title:** Initialize the Python package with uv and pyproject.toml
**Labels:** `epic:scaffolding`, `infrastructure`, `priority:high`

**Body:**

### Summary

Initialize the project as an installable Python package using `uv`, replacing the
implicit "notebook + loose `db_tools.py`" structure. **First: pin the package name** —
proposed `usvote`, alternatives `uspv` / `elections`. This is an open decision; resolving
it is part of this story and unblocks every other module path.

### Acceptance Criteria

- Given a fresh clone, when `uv sync` is run, then all dependencies install and a venv is created
- The package name is decided and recorded (default assumption in this backlog: `usvote`)
- `pyproject.toml` defines:
  - Package name (the decided name)
  - Python version (>=3.11; the seed's ">3.6" floor is obsolete)
  - Runtime deps carried over from the notebook: `beautifulsoup4`, `requests`, `pandas`, `geopandas`, `psycopg2` (or `psycopg2-binary`), `matplotlib`
  - Dev deps: `pytest`, `pytest-cov`, `ruff`, `mypy` (or `pyright`), `jupyterlab` (notebook remains runnable during incremental migration)
- `.python-version`, `uv.lock`, and `src/usvote/__init__.py` are committed
- `README.md` install section updated: `uv sync` replaces the manual pip/pipenv steps (the seed README references Pipfiles that were never committed)

### Implementation Notes

- Use `uv init` targeting a `src/` layout
- Keep the notebook and `db_tools.py` in place for now — D003 mandates *incremental*
  replacement, not a big-bang rewrite
- Connection params and the shapefile path are currently hardcoded in the notebook;
  configuration handling is not in this story (E2 addresses it), but leave a `usvote/config`
  placeholder if convenient

### Dependencies

None — this is the first story.

---

### E1-S2: Define the `src/usvote/` module layout

**Issue title:** Define the src/usvote/ module layout (scrape/parse/transform/load/db skeleton)
**Labels:** `epic:scaffolding`, `infrastructure`, `priority:high`

**Body:**

### Summary

Create the empty module skeleton that mirrors the notebook's actual pipeline shape
(Scrape → Parse → Transform/Validate → Load) so E2 can port each stage into a home that
already exists. This makes the E2 refactor a series of focused moves rather than an
architecture exercise.

### Acceptance Criteria

- Given the package exists, the following modules exist under `src/usvote/` (empty or
  stub, with docstrings naming their responsibility):
  - `scrape.py` — Archives link + raw-table scraping (`scrape_election_links`, `scrape_raw_election_tables`)
  - `parse.py` — HTML table parsing (`parse_election_years` and the `parse_table1` / `parse_table2` family)
  - `transform.py` — build + validate the `candidate`, `state`, `votes` DataFrames
  - `load.py` — orchestrate DataFrame → Postgres load (wraps `db`)
  - `db.py` — the `DBC` wrapper (filled by E1-S3)
  - `pipeline.py` — top-level orchestration (scrape → parse → transform → load)
- A module-boundary note is added to CLAUDE.md (or a `docs/` design note) mapping each
  notebook section to its new module
- No behavior yet — this is structure only; E2 fills it

### Implementation Notes

- Boundaries follow the notebook's own Section numbering (Section 2 scrape, Section 3
  transform/validate, Section 4 load) as documented in CLAUDE.md
- Do not over-design: the notebook's three-DataFrame shape (candidate/state/votes) is the
  contract; keep the modules thin

### Dependencies

- E1-S1 (package must exist)

---

### E1-S3: Port `db_tools.DBC` into `usvote.db` with unit tests

**Issue title:** Port db_tools.DBC into usvote.db with unit tests
**Labels:** `epic:scaffolding`, `testing`, `priority:high`

**Body:**

### Summary

Move the existing `DBC` psycopg2 wrapper from the loose top-level `db_tools.py` into
`usvote/db.py`, add type hints, and give it its first unit tests. `DBC` is the only
importable module today and everything loads through it, so it is the natural first
real code to bring under the package + test umbrella.

### Acceptance Criteria

- Given `usvote.db`, when imported, then `DBC` and its methods (`create_schema`,
  `create_table`, `delete_schema`, `delete_table`, `insert_df_into_table`,
  `select_query_to_df`, `execute_query`, `copy_csv_to_table`, `close_connection`) are available
- Method signatures and behavior match the current `db_tools.py` (no behavior change in this story)
- Type hints added to the public methods
- Unit tests cover SQL-string construction (e.g., `create_table` column-def joining,
  `insert_df_into_table` column list + empty-DataFrame guard) without requiring a live Postgres
- Integration tests that hit a real Postgres are marked `@pytest.mark.integration` and excluded from CI
- The top-level `db_tools.py` either re-exports from `usvote.db` (shim) or is removed with
  the notebook updated to import from the package — developer's call, noted in the PR

### Implementation Notes

- Current `DBC.__init__` calls `sys.exit(1)` on connection failure — consider raising a
  typed exception instead so tests and callers can handle it, but preserve the CLI-friendly
  behavior for the notebook; flag any behavior change explicitly
- `select_query_to_df` uses `pandas.read_sql` on a raw psycopg2 connection (pandas warns
  about this) — note it, but a fix is out of scope for a straight port
- SQL-string tests are the priority; do not build a Postgres test container into CI

### Dependencies

- E1-S1, E1-S2

---

### E1-S4: Set up pytest infrastructure with fixtures directory

**Issue title:** Set up pytest infrastructure with fixtures directory
**Labels:** `epic:scaffolding`, `testing`, `priority:high`

**Body:**

### Summary

Configure pytest with coverage and create the test tree, including a fixtures directory
that will hold saved Archives HTML snippets and expected-output snapshots for E2's parser
and transform tests.

### Acceptance Criteria

- Given the project is set up, `uv run pytest` discovers and runs tests
- `uv run pytest --cov=usvote` produces a coverage report
- Test tree exists: `tests/unit/`, `tests/integration/`, `tests/fixtures/`
- `tests/conftest.py` exists with shared fixtures (e.g., a path helper to `tests/fixtures/`)
- `tests/fixtures/` contains at least one saved raw Archives election-year HTML snippet
  (Table 1 + Table 2 for one year) to seed E2 parser tests
- Integration tests marked `@pytest.mark.integration`; unit tests run without network or DB
- `pyproject.toml` carries pytest + coverage config (testpaths, markers)

### Implementation Notes

- Fixture HTML should be a real Archives year page saved to disk so parser tests never
  hit the network — the notebook currently scrapes live every run
- Pick one structurally-simple modern year plus (ideally) one anomaly year for later E2
  regression fixtures

### Dependencies

- E1-S1

---

### E1-S5: Configure ruff and mypy/pyright

**Issue title:** Configure ruff and mypy or pyright
**Labels:** `epic:scaffolding`, `infrastructure`, `priority:medium`

**Body:**

### Summary

Add linting (ruff) and static type checking (mypy or pyright) with configuration in
`pyproject.toml`, so the growing `src/usvote/` code stays consistent from the start.

### Acceptance Criteria

- Given the repo, `uv run ruff check` runs and passes on the skeleton
- Given the repo, `uv run mypy src/usvote` (or pyright) runs and passes on the skeleton
- Config lives in `pyproject.toml` (ruff rule selection, line length; type-checker strictness)
- `pandas` / `geopandas` / `bs4` third-party stub gaps are handled (ignore rules or
  `types-*` packages) so type checking is not drowned in library-stub noise

### Implementation Notes

- Developer chooses mypy vs. pyright (agentfluent left this to the developer too)
- Start with a pragmatic ruff rule set; strictness can ratchet up later

### Dependencies

- E1-S1

---

### E1-S6: Configure GitHub Actions CI pipeline

**Issue title:** Configure GitHub Actions CI pipeline
**Labels:** `epic:scaffolding`, `infrastructure`, `priority:high`

**Body:**

### Summary

Set up GitHub Actions to run lint, type checks, and unit tests on every PR to `main`,
matching the repo's existing PR-per-feature-branch workflow.

### Acceptance Criteria

- Given a PR against `main`, the CI workflow runs automatically
- CI runs: `uv run ruff check`, `uv run mypy src/usvote` (or pyright), `uv run pytest -m "not integration" --cov=usvote`
- CI installs deps with uv (via `astral-sh/setup-uv`), not pip
- Integration tests (which need a live Postgres and/or network) are excluded from CI
- CI fails if any test fails or lint/type errors are reported
- Workflow file: `.github/workflows/ci.yml`; Python version matches `.python-version`

### Implementation Notes

- Cache uv's package cache for faster runs
- `geopandas` can be heavy to install in CI — confirm the runner installs it cleanly, or
  isolate geo-dependent code so its tests can be marked/skipped if CI install proves painful

### Dependencies

- E1-S1, E1-S4 (pytest infra), E1-S5 (lint/types)

---

### E1-S7: Update CLAUDE.md and README for the `src/` layout

**Issue title:** Update CLAUDE.md and README for the src/ layout
**Labels:** `epic:scaffolding`, `documentation`, `priority:medium`

**Body:**

### Summary

Update CLAUDE.md and README to describe the new `src/usvote/` package, uv/pytest tooling,
and the module-to-notebook-section mapping, while making clear the notebook remains during
incremental migration (D003).

### Acceptance Criteria

- CLAUDE.md "Environment & Running" reflects uv (`uv sync`, `uv run pytest`) and no longer
  implies pipenv-only
- CLAUDE.md "Architecture" documents the `src/usvote/` modules and maps each to its origin
  notebook section
- CLAUDE.md notes there is now a test suite and CI (the current file states "no test suite,
  linter, or build step")
- README install section matches E1-S1's uv-based flow
- Both docs state the notebook is retained as the migration proceeds and note the
  still-open "keep vs. fully migrate the notebook" decision (D003 Action required)

### Dependencies

- E1-S1 through E1-S6 (documents what they built)

---

## E2: EC Ingestion Refactor + Coverage Extension

**Issue title:** Epic: Electoral College ingestion refactor and coverage extension
**Labels:** `epic:ec-ingestion`, `enhancement`

**Body:**

### Summary

Decompose the monolithic `step1_electoral_college_data.ipynb` into the tested
`src/usvote/` modules created in E1, **preserving the notebook's dense inline validations
and hardcoded historical corrections as tests and fixtures** rather than losing them in
the move. Then extend EC coverage from the current 1892 floor toward 1789, with the
structurally-uniform post-1804 era as the MVP spine, and represent contingent elections
where the EC plurality winner is not who took office. See D005 (coverage to 1789–2024,
provenance-first), D006 (Archives is source of truth; canonical candidate/state keys),
D009 (MVP comparison window ~1824), and D010 (pre-12th-Amendment as a later epic;
contingent elections as a modeling nuance).

### Success Criteria

- [ ] Scrape → parse → transform/validate → load runs end-to-end from `usvote.pipeline`, not the notebook
- [ ] Every inline validation from the notebook is preserved as an automated test or an in-pipeline check
- [ ] The known hardcoded corrections are captured as documented, tested fixtures: 2016 "Other" candidates, 2000 DC abstainer, Table1↔Table2 name reconciliations (e.g. "Bob Dole"→"Robert Dole", Trump middle initial), "Faith Spotted Eagle" name split
- [ ] Parser tests run against saved fixture HTML — no live network in unit tests
- [ ] EC coverage extended below 1892 toward 1789; post-1804 era loads on the modern schema; each added era's anomalies documented
- [ ] Contingent elections (1800/1824 House, 1836 Senate VP) are representable: the record distinguishes the EC plurality winner from who actually took office
- [ ] The load path still targets the `dwh` schema (`state`, `candidate`, `votes`) and preserves the FK-dependency create order

### Stories

- [ ] #N — Port the scrape stage into `usvote.scrape` with fixture-based tests
- [ ] #N — Port the Table 1 / Table 2 parsers into `usvote.parse` with fixture-based tests
- [ ] #N — Port the transform/validate stage (candidate/state/votes DataFrames) into `usvote.transform`
- [ ] #N — Preserve hardcoded historical corrections as documented, tested fixtures
- [ ] #N — Port the load stage into `usvote.load` and wire `usvote.pipeline`
- [ ] #N — Externalize hardcoded config (DB params, shapefile path)
- [ ] #N — Extend EC coverage below 1892 toward 1789 (post-1804 spine)
- [ ] #N — Represent contingent elections (EC plurality winner ≠ who took office)
- [ ] #N — Establish canonical candidate + state keys on the EC spine

---

### E2-S1: Port the scrape stage into `usvote.scrape`

**Issue title:** Port the scrape stage into usvote.scrape with fixture-based tests
**Labels:** `epic:ec-ingestion`, `enhancement`, `priority:high`

**Body:**

### Summary

Move `scrape_election_links` and `scrape_raw_election_tables` (notebook Section 2) into
`usvote/scrape.py`, separating live-network scraping from parsing so downstream stages can
be tested against saved HTML.

### Acceptance Criteria

- Given `usvote.scrape`, `scrape_election_links(...)` returns the per-year Archives links
  and `scrape_raw_election_tables(...)` returns the raw HTML tables, matching current notebook output
- Network access is isolated to this module; a saved-HTML path exists so parse/transform
  tests never hit the network
- A thin caching or save-to-disk option lets a developer snapshot Archives pages into
  `tests/fixtures/`
- Unit tests cover link/table extraction against a saved Archives index fixture

### Implementation Notes

- The Archives site structure (two tables per year: Table 1 = top-2 candidates + party,
  Table 2 = home states + votes-by-state matrix) is documented in CLAUDE.md
- Preserve the existing behavior exactly; this is a move + seam, not a rewrite

### Dependencies

- E1-S2 (module skeleton), E1-S4 (fixtures dir)

---

### E2-S2: Port the Table 1 / Table 2 parsers into `usvote.parse`

**Issue title:** Port the Table 1 / Table 2 parsers into usvote.parse with fixture-based tests
**Labels:** `epic:ec-ingestion`, `enhancement`, `priority:high`

**Body:**

### Summary

Move the parser family — `parse_election_years`, `parse_election_year_tables`,
`parse_table1`, `parse_t1_candidate_party`, `parse_table2`, `parse_t2_num_candidates`,
`parse_t2_candidate_state`, `parse_t2_votes_by_state` — into `usvote/parse.py` with tests
against saved fixture HTML.

### Acceptance Criteria

- Given saved Archives HTML for a year, when parsed, then the output matches the notebook's
  `parsed_election_years` structure (per-year dicts with `t1`, `t2.candidate_state`,
  `t2.votes_by_state`)
- Unit tests cover at least one structurally-simple modern year and one anomaly year
- Parser handles the Table 2 variable-candidate-count logic (`parse_t2_num_candidates`)
  as the notebook does
- No network access in these tests

### Implementation Notes

- These functions are pure given HTML input — ideal first real unit-test target
- Snapshot-style assertions against a saved expected-output JSON are acceptable

### Dependencies

- E2-S1 (saved HTML available), E1-S4

---

### E2-S3: Port the transform/validate stage into `usvote.transform`

**Issue title:** Port the transform and validate stage (candidate/state/votes DataFrames) into usvote.transform
**Labels:** `epic:ec-ingestion`, `enhancement`, `priority:high`

**Body:**

### Summary

Move notebook Section 3 — the construction, transformation, and validation of the three
DataFrames (`candidates_df`, `state_df`, `votes_df`) — into `usvote/transform.py`,
converting the notebook's inline assertion-style checks into real, automated validations.

### Acceptance Criteria

- Given parsed election data, `usvote.transform` produces the three DataFrames matching the
  notebook's schema and grain (candidate dim, state dim, votes fact)
- The notebook's inline checks (e.g., `len(x) == len(y)` grain checks, "one row per
  candidate", `value_counts` sanity checks) become explicit validation functions with tests
- Name-part parsing (first / middle / last / suffix, `Jr.` handling) is ported with tests
- `state_df` still joins US state names to the geopandas shapefile data (region, area, lat/lon)
- NaN → None conversion before DB-write boundaries is preserved

### Implementation Notes

- The candidate dimension aggregates multi-state/multi-party candidates into one row with
  `_2` columns (e.g., Bryan D/P, T. Roosevelt R→P) — preserve this
- The geopandas shapefile dependency (TIGER2019) is currently a hardcoded path; E2-S6
  externalizes it, but this story can assume a path is provided
- Validation functions should raise or report clearly so a scrape/parse regression surfaces
  loudly, matching the notebook's "load-bearing validation" intent (CLAUDE.md)

### Dependencies

- E2-S2

---

### E2-S4: Preserve hardcoded historical corrections as documented, tested fixtures

**Issue title:** Preserve hardcoded historical corrections as documented, tested fixtures
**Labels:** `epic:ec-ingestion`, `testing`, `priority:high`

**Body:**

### Summary

The notebook patches real historical anomalies by name at specific cells. These
corrections are hard-won correctness and must survive the refactor as **explicit,
documented, tested** data corrections rather than scattered inline edits. This story
catalogs each one, gives it a provenance comment (source), and locks it with a test.

### Acceptance Criteria

- Each known correction is captured as a named, documented correction with a source note:
  - **2016 "Other" candidates** — Bernie Sanders, Ron Paul, John Kasich, Colin Powell,
    Faith Spotted Eagle: electoral votes + names collected manually from the Archives Notes section
  - **2000 DC abstainer** — the DC elector who abstained (already fixed on `main`; see recent history)
  - **Table 1 ↔ Table 2 name reconciliations** — e.g. "Bob Dole" → "Robert Dole";
    Donald Trump middle-initial reconciliation across his NY/FL rows
  - **"Faith Spotted Eagle" name split** — `name_middle=None`, `name_last="Spotted Eagle"`
- Each correction has a test asserting the corrected value is present after transform
- A single catalog (docstring, module, or `docs/` table) lists every correction with its
  source, so future election-year additions follow the same documented pattern (CLAUDE.md convention)

### Implementation Notes

- CLAUDE.md already documents the convention: "document the source of any manually-entered
  value in a comment as existing cells do" — formalize that here
- Extending coverage below 1892 (E2-S7) will surface *new* anomalies; this story establishes
  the pattern they slot into

### Dependencies

- E2-S3

---

### E2-S5: Port the load stage into `usvote.load` and wire `usvote.pipeline`

**Issue title:** Port the load stage into usvote.load and wire usvote.pipeline
**Labels:** `epic:ec-ingestion`, `enhancement`, `priority:high`

**Body:**

### Summary

Move notebook Section 4 (the `create_tables_from_dfs` load path via `DBC`) into
`usvote/load.py`, and wire the full scrape → parse → transform → load flow together in
`usvote/pipeline.py` so the pipeline runs from the package, not the notebook.

### Acceptance Criteria

- Given the three DataFrames, `usvote.load` writes them into the `dwh` schema (`state`,
  `candidate`, `votes`) in FK-dependency order (state → candidate → votes)
- `usvote.pipeline` exposes a single entry point that runs the end-to-end EC ingestion
- The destructive `replace=True` schema drop/recreate behavior is preserved but made
  **explicit and guarded** (e.g., requires an intentional flag), given it drops and
  recreates the `dwh` schema
- An integration test (marked `@pytest.mark.integration`, excluded from CI) loads a small
  fixture dataset into a real Postgres and verifies row counts/grain

### Implementation Notes

- `create_tables_from_dfs(..., replace=True)` currently cascades a schema drop on every
  full run — CLAUDE.md flags this as "be deliberate about executing the write cells";
  the package version should make destructive writes opt-in, not default-on-import
- Column definitions and FK relations live in the notebook's Section 4.1 `table_column_defs` —
  port them faithfully

### Dependencies

- E2-S3, E1-S3 (`usvote.db`)

---

### E2-S6: Externalize hardcoded config (DB params, shapefile path)

**Issue title:** Externalize hardcoded config (DB connection params, shapefile path)
**Labels:** `epic:ec-ingestion`, `infrastructure`, `priority:medium`

**Body:**

### Summary

Replace the notebook's hardcoded configuration with externalized config so the pipeline is
reproducible across machines. Today the DB connection params live in notebook Section 4.1
and the TIGER2019 shapefile path is hardcoded in Section 1.3 and **must be hand-edited**
before running.

### Acceptance Criteria

- DB connection params (`host`, `port`, `dbname`, `user`) are read from env / config file,
  not hardcoded; password continues to be prompted or read from a secret (never committed)
- The US states shapefile path is configurable (env or config), with a clear error if unset/missing
- A documented example config (`.env.example` or equivalent) lists every required setting
- Running the pipeline on a fresh machine requires editing config, not source code

### Implementation Notes

- Keep it simple — env vars or a small config file; no need for a heavy settings framework
- The shapefile (TIGER2019 STATE) is an external download; document where to get it (census.gov)
  as the README already gestures at

### Dependencies

- E2-S5

---

### E2-S7: Extend EC coverage below 1892 toward 1789 (post-1804 spine)

**Issue title:** Extend EC coverage below 1892 toward 1789 (post-1804 as the MVP spine)
**Labels:** `epic:ec-ingestion`, `enhancement`, `priority:medium`

**Body:**

### Summary

Extend EC ingestion below the current 1892 floor toward 1789, now that the Archives
publishes the full history and Fred has confirmed it is unrestricted (D005). Prioritize the
**structurally-uniform post-1804 era** as the MVP spine; earlier structurally-different
elections are handled per D010.

### Acceptance Criteria

- Given the extended scraper, EC data for post-1804 elections down to (at least) the
  ~1824 comparison floor (D009) parses and loads on the modern `dwh` schema
- Each newly-added election year that required a manual correction is documented via the
  E2-S4 catalog pattern, with source
- Pre-1804 / pre-12th-Amendment years (1789–1800) are **explicitly out of scope** here and
  routed to the later dedicated epic (D010) — the story documents where the spine starts and why
- Parser/transform tests extended with at least one pre-1892 fixture year
- Any Archives table-format differences in older years are handled or clearly flagged

### Implementation Notes

- Older Archives pages may not follow the exact two-table modern shape the parsers assume —
  expect format drift and budget for per-era special-casing (CLAUDE.md warns of this)
- D009's ~1824 comparison floor is the MVP target; loading a bit earlier EC-only data is
  fine as long as it is structurally post-1804 and does not force pre-12A modeling

### Dependencies

- E2-S2, E2-S3, E2-S4

---

### E2-S8: Represent contingent elections (EC plurality winner ≠ who took office)

**Issue title:** Represent contingent elections where the EC plurality winner is not who took office
**Labels:** `epic:ec-ingestion`, `enhancement`, `priority:medium`

**Body:**

### Summary

Model the contingent elections where the Electoral College did not directly decide who took
office: 1800 and 1824 (decided in the House) and 1836 (VP decided in the Senate). The data
model must distinguish the EC plurality/outcome from who *actually* assumed office, because
the EC-vs-PV-vs-hybrid comparison depends on that distinction (D010).

### Acceptance Criteria

- The `votes`/`candidate` model can represent, for a contingent year, both the EC result
  and the office-holder outcome without conflating them
- 1824 (in the MVP window per D009) is correctly represented: EC plurality winner (Jackson)
  vs. who took office (Adams, via the House)
- 1800 and 1836 are representable even if outside the MVP analysis window, so the model does
  not need reworking when they are analyzed later
- Tests assert the EC-outcome vs. office-holder distinction for at least 1824
- The representation is documented (a short design note) so downstream flip/margin logic
  (future E7) knows which field is authoritative for "who won under EC"

### Implementation Notes

- This is a data-modeling nuance, not the full pre-12th-Amendment epic (D010) — scope is the
  distinction, not two-votes-per-elector modeling
- Coordinate the field semantics with the canonical-key work (E2-S9) so the office-holder vs.
  EC-winner distinction is consistent

### Dependencies

- E2-S3; relates to E2-S9

---

### E2-S9: Establish canonical candidate + state keys on the EC spine

**Issue title:** Establish canonical candidate and state keys on the EC spine
**Labels:** `epic:ec-ingestion`, `enhancement`, `priority:high`

**Body:**

### Summary

Define the **canonical candidate key** and **canonical state key** on the EC data, since
EC (National Archives) is the source of truth both datasets will conform to (D006). This is
the spine the future PV join (E6) reconciles against, so it lands in the EC epic even though
its payoff is realized later.

### Acceptance Criteria

- A stable canonical **state key** exists (full state name is the current `state` PK; confirm
  it is stable and unambiguous across all covered years, including states that changed over time)
- A stable canonical **candidate key** exists that survives the name variance already handled
  in transform (multi-state/multi-party aggregation, name reconciliations, split names)
- The keys are documented as the reconciliation spine for future cross-source joins (D006),
  with a note that PV data from both sources (E4 UCSB, E5 MIT) must map onto them
- Tests assert key stability and uniqueness at the documented grain

### Implementation Notes

- Do **not** build the PV join here — only the EC-side canonical keys the join will later target
- The existing `candidate_id` and `state` PKs may already be sufficient; this story's job is to
  make them *canonical and documented*, not necessarily to invent new keys
- Historical edge cases (states admitted/renamed, candidates across parties) should be
  considered so the key does not need re-cutting when PV or older years arrive

### Dependencies

- E2-S3; feeds the deferred E6 (cross-source join) and both PV-ingestion epics (E4, E5)

---

## E3: Popular-Vote Source Determination (Research Spike)

**Issue title:** Epic: Popular-vote source determination spike
**Labels:** `epic:pv-source-research`, `research`

**Body:**

### Summary

Resolve **which** popular-vote data source(s) the project will use and **whether the license
permits public redistribution** via our API. This is a research spike whose deliverable is a
written recommendation, not code. It is the critical-path unblocker for the MIT source: MIT
PV ingestion (E5) and the cross-source join (E6) cannot be responsibly scoped until MIT's
schema, grain, coverage, and license are known. (UCSB historical ingestion, E4, is
un-deferred and does not wait on this spike — see D014.) See D008 (prefer MIT for the
redistributable core), D014 (dual-source: MIT modern + UCSB historical), and D002 (public
API gated on PV-data licensing).

### Success Criteria

- [ ] A written source-determination recommendation exists under `.claude/specs/`
      (`research-pv-source.md` or `prd-pv-ingestion.md`) naming the chosen source(s) and why
- [ ] The recommendation evaluates MIT Election Lab against at least UCSB / American Presidency
      Project on: coverage (years, state-level grain), format, update cadence, and license
- [ ] A **licensing finding** explicitly states whether the chosen source(s) permit public
      redistribution via API — the gate on the D002 stretch goal
- [ ] Coverage back to the ~1824 MVP comparison floor (D009) is assessed per source
- [ ] The recommendation identifies where PV is unavailable or unreliable, feeding the
      provenance-first handling in D005/D014
- [ ] Outcome explicitly unblocks E5 (MIT ingestion) / E6 (join) scoping (schema + grain + license documented)

### Stories

- [ ] #N — Evaluate MIT Election Lab PV returns (coverage, grain, format, license)
- [ ] #N — Evaluate UCSB / American Presidency Project (and note other alternatives)
- [ ] #N — Produce the source-determination recommendation + licensing finding

---

### E3-S1: Evaluate MIT Election Lab PV returns

**Issue title:** Evaluate MIT Election Lab popular-vote returns (coverage, grain, format, license)
**Labels:** `epic:pv-source-research`, `research`, `priority:high`

**Body:**

### Summary

Assess the MIT Election Data + Science Lab as the lead PV source (D008): what presidential
popular-vote data it publishes, at what grain and coverage, in what format, and under what license.

### Acceptance Criteria

- The Lab's presidential PV dataset(s) are identified with: year coverage, geographic grain
  (state-level at minimum), candidate granularity, and file format(s)
- Coverage back to the ~1824 comparison floor (D009) is assessed — where it starts, and where
  early-era gaps exist (the current MIT file reaches only 1976; see D014)
- The dataset license is captured verbatim with a plain-language read on whether it permits
  **redistribution via a public API** (the D002 gate)
- How well the source's candidate/state naming will map onto the EC canonical keys (E2-S9) is
  noted, with any obvious reconciliation friction flagged
- **Optional acceleration:** note the MIT-side outreach contacts (see epic #13 "Outreach
  contacts") as a way to get a definitive licensing answer and a possible pre-1976 extension

### Implementation Notes

- Findings feed the E3-S3 recommendation; this story is fact-gathering, not decision
- Capture exact license text/links — "open" is not specific enough for the D002 gate

### Dependencies

- None (can start during M1 in parallel with E1)

---

### E3-S2: Evaluate UCSB / American Presidency Project and note alternatives

**Issue title:** Evaluate UCSB / American Presidency Project and note other PV alternatives
**Labels:** `epic:pv-source-research`, `research`, `priority:medium`

**Body:**

### Summary

Assess the UCSB American Presidency Project (the notebook's originally-planned Step 2 source)
and briefly note any other viable PV sources, so the recommendation is a real comparison and
the fallback is understood if MIT does not work out.

### Acceptance Criteria

- UCSB/APP presidential PV data is assessed on the same axes as MIT (coverage, grain, format, license)
- Its licensing status is captured, including the current state of any redistribution
  permission (D008 notes no licensing reply to date — record that and any update)
- At least a brief scan of other candidate sources (e.g., other academic/government compilations)
  with a one-line viability note each
- A clear statement of the best fallback if the MIT path stalls

### Implementation Notes

- Keep alternatives lightweight — this is comparison and fallback context, not a second deep dive
- Per D014, UCSB is already adopted as the historical-breadth source (E4); this evaluation
  focuses on confirming coverage/reliability and its non-redistributable status, not re-deciding it

### Dependencies

- None (parallelizable with E3-S1)

---

### E3-S3: Produce the source-determination recommendation + licensing finding

**Issue title:** Produce the PV source-determination recommendation and licensing finding
**Labels:** `epic:pv-source-research`, `research`, `documentation`, `priority:high`

**Body:**

### Summary

Synthesize E3-S1 and E3-S2 into a single written recommendation under `.claude/specs/` that
names the chosen PV source(s), justifies them, and states the licensing finding that gates the
public-API stretch goal. This document is what unblocks E5 (MIT ingestion) / E6 (join) scoping.

### Acceptance Criteria

- A doc exists at `.claude/specs/research-pv-source.md` (or `prd-pv-ingestion.md`) containing:
  - The recommended source(s) and the rationale, referencing D008 and D014
  - A comparison table (MIT vs. UCSB/APP vs. any alternative) across coverage, grain, format, license
  - An explicit **licensing finding**: does each source permit public API redistribution?
    (yes / no / needs-permission-via-contact) — the D002 gate
  - Coverage assessment against the ~1824 MVP floor (D009) and a note on where PV is
    unavailable/unreliable (feeds D005 provenance handling)
  - A short "what this unblocks" section describing the schema/grain assumptions E5/E6 can
    now be scoped against
- If the licensing answer requires the MIT contacts, the doc states that as the explicit
  next action and what question needs answering (see epic #13 "Outreach contacts")
- A new decision is proposed for `decisions.md` recording the final source determination if it
  changes anything beyond D014 (the decision entry itself is a follow-up, not part of this story)

### Implementation Notes

- Mirror the agentfluent research/PRD style already used in `.claude/specs/`
- This closes E3 and is the gate the deferred E5/E6 backlog waits on

### Dependencies

- E3-S1, E3-S2

---

## E4: UCSB Historical PV Scrape + Ingest

**Issue title:** Epic: UCSB historical popular-vote scrape and ingest
**Labels:** `epic:ucsb-ingestion`, `enhancement`

**Body:**

### Summary

Scrape, parse, transform, validate, and load the **UCSB / American Presidency Project**
presidential popular-vote data (~1824–1972) — the historical-breadth layer of the
dual-source PV strategy (D014). This is its **own epic**, separate from the clean MIT CSV
load (E5), because the raw UCSB HTML is messy, era-drifting, and substantially harder than
the structured MIT file — it mirrors the EC ingestion architecture (E2: scrape/snapshot →
parse → transform/validate → load) rather than a simple CSV read. Every record is tagged
`source=UCSB` and `redistributable=false` (pending a license answer), with
provenance/reliability flags per D005/D014. **Un-deferred:** UCSB is the only source
reaching ~1824 (D009), so its necessity does not depend on E3's licensing outcome.

### Success Criteria

- [ ] Raw UCSB presidential PV HTML for the covered range (~1824–1972) is scraped and snapshotted to disk (no live network in parse/transform tests)
- [ ] Parsing handles heavy format drift across eras, producing per-(year, state, candidate) PV records
- [ ] Records transform/validate into state-level PV rows (candidate votes + state total), carrying provenance and reliability flags (D005/D014)
- [ ] Every row is tagged `source=UCSB`, `redistributable=false`
- [ ] UCSB candidate/state names reconcile onto the canonical keys (E2-S9 / #30)
- [ ] Where UCSB PV is unavailable or unreliable, it is flagged with provenance rather than silently dropped or fabricated (D005)

### Stories

- [ ] #N — Scrape + snapshot raw UCSB presidential PV HTML to disk
- [ ] #N — Parse UCSB HTML into per-(year, state, candidate) PV records (handle era drift)
- [ ] #N — Transform + validate UCSB PV into state-level records with provenance flags
- [ ] #N — Load UCSB PV records tagged `source=UCSB`, `redistributable=false`
- [ ] #N — Reconcile UCSB candidate/state names onto the canonical keys

---

### E4-S1: Scrape + snapshot raw UCSB presidential PV HTML

**Issue title:** Scrape and snapshot raw UCSB presidential PV HTML to disk
**Labels:** `epic:ucsb-ingestion`, `infrastructure`, `priority:high`

**Body:**

> **Research note (2026-07-17):** The **snapshot itself is already complete** — it was
> produced *before* this story was worked. A self-contained, stdlib-only snapshot script
> (`_snapshot_ucsb.py`, whose docstring names "backlog #34 (E4-S1)") was written and run on
> **2026-07-06** to collect the HTML promptly and politely in a single pass, so the raw data
> was in hand while the site was cooperative rather than being re-fetched piecemeal later.
> Result: **all 60 elections 1789–2024, every one HTTP 200**, ~8.2MB, plus the
> `/statistics/elections` index page and a `manifest.json` carrying per-year
> url / http_status / bytes / **sha256** / timestamp — **zero errors**. It lives at
> `~/Documents/Projects/data/presidential_vote_analysis/ucsb_raw/`, **outside the repo and
> untracked by git** (UCSB is non-redistributable — D014/D016). `research-pv-source.md` §5
> records this as "pre-satisfies the E4 snapshot story (#34)."
>
> **What that leaves:** the scrape *code* is not in the repo (`src/usvote/ucsb/` does not
> exist, and the script is not importable as `usvote.*` nor under version control), and the
> fixtures AC has since **been amended by D022** — see below. This story is therefore
> re-scoped to **(a) port the script into the package** and **(b) add synthetic fixtures**.
> ACs already met are kept visible with a note on how they were met, not deleted.

### Summary

Scrape the UCSB / American Presidency Project presidential popular-vote pages and snapshot
the raw HTML to disk, separating live-network scraping from parsing (mirrors E2-S1). The
snapshot insulates the pipeline from site changes and lets every downstream stage run
offline. **The snapshot data already exists** (see the research note); the remaining work is
bringing the *scrape code* under `usvote/` with env-var path config + tests, and seeding
**synthetic** parser fixtures per D022.

### Acceptance Criteria

**Already satisfied (2026-07-06 snapshot run) — retained for the record:**

- [x] **Raw HTML is saved to disk (a snapshot cache) so parse/transform stages never hit the
  network** — met: 60/60 elections 1789–2024, all HTTP 200, at
  `~/Documents/Projects/data/presidential_vote_analysis/ucsb_raw/` (one `{year}.html` per
  election + `_index_elections.html`), with a sha256 `manifest.json` for integrity.
- [x] **Network access is isolated to this module** — met in substance: fetching happens only
  in the snapshot script; parse/transform read files from disk. Formalized by the port below.
- [x] **A UCSB scrape module fetches the per-year UCSB PV pages across the covered range** —
  met *functionally* by `_snapshot_ucsb.py`, but the code lives outside the repo and is not
  importable as `usvote.*`. **Closed by the port below.**

**Remaining work:**

- [ ] **(a) Port the snapshot script into the package** at `src/usvote/ucsb/scrape.py`
  (per D015: each PV source is its own sibling subpackage), **preserving its
  robots-compliant behavior exactly**:
  - honors the site's `Crawl-delay: 10`
  - identifies truthfully as `us-presidential-vote-analysis-research/0.1 (personal academic
    research)` — matching `User-agent: *`, explicitly **not** ClaudeBot
  - enumerates year URLs by regexing the already-saved index (no extra network hit)
  - skip-if-already-have; **halts immediately on 403/429** to respect the server
  - writes the per-year sha256 `manifest.json`
- [ ] **Snapshot directory path is resolved from the env var `USVOTE_UCSB_HTML_DIR`** (D023),
  mirroring the established config convention for machine-local external data —
  `USVOTE_MIT_CSV_PATH` / `USVOTE_SHAPEFILE_PATH`, see `src/usvote/config.py` and
  `src/usvote/mit/config.py` — rather than the script's hard-coded `os.path.expanduser(...)`.
  Unset / empty / nonexistent raises the typed `ConfigError`.
- [ ] **Unit tests** cover URL enumeration from the saved index, manifest shape + sha256, the
  skip-if-already-have path, the 403/429 halt, and env-var config resolution — **against
  injected fakes; no live network in CI** (the snapshot must not be re-fetched by a test run).
- [ ] **(b) Synthetic, era-spanning parser fixtures** are added to `tests/fixtures/` per
  **D022** — hand-written HTML mimicking the real UCSB table structure with **fabricated vote
  numbers**, each annotated with the real source year it mimics. Between them they must pin:
  wide-not-long layout (melt required); `colspan`/`rowspan` multi-row headers with the
  candidate-group count drifting by era (2 groups in 1876, 4 in 1824); legislature-chosen-elector
  states with no PV (1824: DE, GA, LA, NY, SC, VT) that must be **flagged, never zeroed** (D005);
  and footnote rows at table bottom.
- [ ] **No UCSB-sourced bytes are committed to this repository** (D022) — this repo is public
  and UCSB is `redistributable=false` (D014/D016). The external snapshot stays external.

> **AC amended (D022).** The original AC3 — "at least a few representative year snapshots
> (spanning different eras) are saved into `tests/fixtures/`" — was written 2026-07-06, before
> the D014/D016 licensing posture hardened. It is **replaced by the synthetic-fixtures AC
> above**: committing real UCSB HTML to a **public** repo *is* redistribution, and pushing is
> effectively irreversible (forks, clones, git history, third-party caches). Recorded as
> amended rather than dropped, since as written it would have required shipping
> non-redistributable content. Full rationale + options weighed: **D022**.

### Implementation Notes

- **Port, don't rewrite.** The crawl-delay, truthful UA, and 403/429 halt are what make
  re-running this scrape ethically and operationally safe — a from-scratch reimplementation
  risks losing them silently.
- **Why port at all, given the snapshot exists?** Two reasons: (1) **reproducibility is the
  D003 star** — a pipeline re-run every four years (the 2028 refresh) cannot depend on a
  script that exists on exactly one machine; (2) the snapshot currently has **no git backup**,
  so the *means to re-fetch it* is as fragile as the data. Porting the code removes the worse
  half of that risk. The **data itself deliberately stays out of the repo** (non-redistributable);
  it is re-fetchable precisely *because* the script is in git. Recorded as **D023**.
- Mirror the EC scrape seam (E2-S1): fetch vs. parse are separate so tests run offline.
- The real 60-year external snapshot remains the **development corpus and acceptance check**
  for E4-S2 (#35) — the synthetic fixtures pin structure in CI, they do not replace it (D022's
  known drift tradeoff).
- Legacy reference: the unmerged branch `origin/feature/step2_scrape_app_site` carries a
  prior-generation BeautifulSoup UCSB scrape in a notebook (selectors
  `section#block-views-election-maps-block-1` for links, `section#block-system-main` for
  tables). It stops before parsing — useful as a **selector reference for #35 only**, not for
  this story.
- This is UCSB-only; MIT is a clean CSV handled separately (E5).

### Dependencies

- E1-S2 (module layout), E1-S4 (fixtures dir); D015 (`usvote/ucsb/` namespace), D022 (synthetic fixtures), D023 (port the script; env var name)

---

### E4-S2: Parse UCSB HTML into per-(year, state, candidate) PV records

**Issue title:** Parse UCSB HTML into per-(year, state, candidate) PV records (handle era drift)
**Labels:** `epic:ucsb-ingestion`, `enhancement`, `priority:high`

**Body:**

### Summary

Parse the snapshotted UCSB HTML into structured per-(year, state, candidate) popular-vote
records, handling the **heavy format drift** across eras that makes UCSB substantially
harder than the MIT CSV.

### Acceptance Criteria

- Given a snapshotted UCSB year page, parsing yields per-(year, state, candidate) records with candidate votes and state totals
- Era-specific format variations are handled; all 60 year pages parse (no year-level parse
  failures exist in the corpus — see [`docs/ucsb-html-formats.md`](../../docs/ucsb-html-formats.md)).
  What is flagged is **popular-vote absence at the record level**, per D024
- Unit tests cover at least one page per distinct era format, against saved **synthetic** fixtures (D022) — no network
- Parsing failures/ambiguities are surfaced loudly (not silently dropped), feeding the provenance/reliability flags in E4-S3
- The parser is **roster-free**. Per (year, state) it emits the one status that is readable from
  markup — **`legislature_chosen`** (a 2-cell row with `colspan = W-1`; 18 rows corpus-wide, all
  carrying the marker substring `electors chosen by state legislature`) — plus the **verbatim note
  text**, preserved unparsed (D024 §5). Elector counts and split allocations in that prose are
  **not** extracted into structured fields (D006: EC is the source of truth for electoral votes)
- The other two statuses are **out of scope here and assigned by E4-S3**: `not_participating` has
  **no markup whatsoever** ([`docs/ucsb-html-formats.md`](../../docs/ucsb-html-formats.md) §4 case
  2 — the row is simply absent) and is detectable only against an expected roster; `popular_vote`
  is that roster's residual category. D024 §6 sources the roster from the **EC spine +
  `UCSB_NONPARTICIPATING_STATES`**, both of which are E4-S3 work — so the parser cannot and must
  not attempt either
- Absence is **never** emitted as `0`. Both the pre-1852 `U+00A0` and the 1852+ `--`
  not-on-ballot cells normalize to one internal sentinel and yield **no record**. Per
  (year, state), `numeric_cells + not_on_ballot_cells == candidate_column_count` with **no
  residual** — any cell that is neither a parseable number nor a recognized sentinel **raises**
  (D024 §4/§7). This within-page guard stays in the parser; the cross-page two-way roster assert
  is E4-S3's

### Implementation Notes

- This is the highest-risk story in the epic — budget for per-era special-casing, as with EC's older years (E2-S7)
- Keep parse pure given HTML input so it is unit-testable against fixtures
- Per D022 the committed fixtures are **synthetic** (structure real, numbers fabricated); the
  **real 60-year external snapshot** at `~/Documents/Projects/data/presidential_vote_analysis/ucsb_raw/`
  is the development corpus and the acceptance check the fixtures alone cannot provide
- [`docs/ucsb-html-formats.md`](../../docs/ucsb-html-formats.md) is the corpus survey that drives
  this story: the six header layouts and their detection signals, the uniform `2 + 3g` data-row
  grammar (one body parser suffices — branch on detected header shape, **never** on year, since
  1936/1964/1972/1976/1984/1988 break chronological ordering), the four absence cases with markup,
  16 ranked parsing risks, the eight fixture representatives, and a proposed function decomposition
- The roster-free split above narrows this story's original status AC, which overreached; D024's
  design is unchanged (see D024 "Action required")

### Dependencies

- E4-S1 (snapshotted HTML available)

---

### E4-S3: Transform + validate UCSB PV into state-level records with provenance flags

**Issue title:** Transform and validate UCSB PV into state-level records with provenance flags
**Labels:** `epic:ucsb-ingestion`, `enhancement`, `priority:high`

**Body:**

### Summary

Transform parsed UCSB rows into validated **state-level** PV records, attaching provenance
and reliability flags per D005/D014. Authentic historical representation — flagging
unreliable or missing PV rather than hiding it — is a product feature.

### Acceptance Criteria

- Parsed UCSB data becomes state-level PV records (candidate votes + state total per year/state)
- Each record carries provenance (`source=UCSB`) and a reliability flag; unreliable or estimated values are marked, not silently accepted
- Where UCSB PV is unavailable, absence is modeled **at its own grain** per D024 — never as a
  null or zero vote in `dwh.pv_votes`. State-level absence (legislature-chosen, non-participating)
  becomes a `dwh.pv_state_status` row; candidate-level absence (not on ballot) becomes **no row**.
  No fabricated values, per D005
- `dwh.pv_state_status` is populated as a **complete roster** — one row per (source, year, state)
  for every state in that year's election, including `popular_vote` states — assembled from the
  **EC spine** (participating states) plus the provenance-carrying constant
  `UCSB_NONPARTICIPATING_STATES` (1864, 1868), which also gains a `docs/corrections.md` row
- **This story owns assignment of `popular_vote` and `not_participating`.** Neither is readable
  from UCSB markup, so E4-S2 emits only `legislature_chosen` + the verbatim note. Here:
  `not_participating` comes from `UCSB_NONPARTICIPATING_STATES`; `popular_vote` is the **residual**
  — any roster state not flagged `legislature_chosen` by the parser and not listed as
  non-participating. All three statuses are therefore assigned in one place, against the complete
  roster
- The **two-way roster assert** is an automated test: every `popular_vote` state has ≥1
  `pv_votes` row; every absence-status state has exactly 0; every `pv_votes` (year, state) is in
  the roster. This is the guard against the inner-join silent-drop hazard, which sum validators
  cannot detect
- Validation checks (grain, and totals reconciliation where possible) run as automated tests
- Redistributability is captured as a per-record/per-source attribute (`redistributable=false` for UCSB pending a license answer) — set here or at load (E4-S4), documented either way

### Implementation Notes

- Mirror the EC transform/validate intent (E2-S3): load-bearing validations become real tested functions
- Provenance / reliability / `redistributable` are first-class attributes per D014. The shared PV
  record shape is **already settled** — D018/D021 shipped `dwh.pv_votes` (MIT landed first and
  defined it), so this story **conforms to the table as-shipped and does not redefine it**. What
  E4 adds is the sibling `dwh.pv_state_status` roster (D024), not a change to the fact table
- The `note` column holds **verbatim UCSB text** and is therefore `redistributable=false` content
  (D024, extending D022/D016) — exclude it from any public API surface, and never let it appear in
  a committed fixture. The `pv_status` enum is a bare historical fact and carries no such restriction
- Statuses arrive from two directions and must be merged deterministically: parser-emitted
  `legislature_chosen` rows (keyed by year, state) join onto the EC-derived roster; a
  `legislature_chosen` state absent from the roster, or a non-participating state the parser also
  flagged, is a **contradiction and should raise** rather than silently resolve

### Dependencies

- E4-S2

---

### E4-S4: Load UCSB PV records tagged source=UCSB, redistributable=false

**Issue title:** Load UCSB PV records tagged source=UCSB, redistributable=false
**Labels:** `epic:ucsb-ingestion`, `enhancement`, `priority:high`

**Body:**

### Summary

Load the validated UCSB state-level PV records into the warehouse, tagged `source=UCSB` and
`redistributable=false`, alongside (not overwriting) EC data. Mirrors the EC load seam
(E2-S5) via `DBC`.

### Acceptance Criteria

- UCSB PV records load into a PV target (a PV fact table in `dwh`, or the agreed shared PV schema) with `source` and `redistributable` columns populated
- The load is idempotent/guarded — no destructive-on-import behavior (same caution as E2-S5's guarded `replace`)
- An integration test (`@pytest.mark.integration`, excluded from CI) loads a small UCSB fixture set and verifies row counts/grain and the source/redistributable tagging
- The PV target schema is documented; the `redistributable` flag is queryable so downstream API work (E8) can exclude non-redistributable rows

### Implementation Notes

- Reuse `usvote.db` (`DBC`, from E1-S3) for the load
- The PV target table design is shared with MIT ingestion (E5); if E5 is unscoped when this lands, define a minimal PV schema here that MIT can conform to, and flag it as a shared-schema decision
- `redistributable=false` is the load-time guardrail behind the D002 public-API gate

### Dependencies

- E4-S3, E1-S3 (`usvote.db`)

---

### E4-S5: Reconcile UCSB candidate/state names onto the canonical keys

**Issue title:** Reconcile UCSB candidate and state names onto the canonical keys
**Labels:** `epic:ucsb-ingestion`, `enhancement`, `priority:high`

**Body:**

### Summary

Reconcile UCSB candidate and state names onto the **canonical candidate/state keys**
established on the EC spine (E2-S9 / #30, D006), so UCSB PV joins cleanly to EC. UCSB name
formats differ from the National Archives, so this is real reconciliation work — analogous
to the EC name reconciliations (E2-S4).

### Acceptance Criteria

- UCSB state names map onto the canonical state key with full coverage across the ~1824–1972 range (including states as they existed historically)
- UCSB candidate names map onto the canonical candidate key; mismatches are resolved as documented, tested reconciliations (mirroring the EC correction catalog, E2-S4)
- Unreconcilable names are flagged with provenance rather than dropped
- Tests assert UCSB→canonical-key mappings for a representative sample across eras

### Implementation Notes

- Depends on the canonical keys existing (E2-S9 / #30) — this story conforms UCSB onto them; it does not redefine the keys
- Reuse the documented-correction pattern from E2-S4 so UCSB reconciliations are auditable
- MIT will need its own analogous reconciliation (in E5); the canonical keys are the shared target for both (D006/D014)

### Dependencies

- E4-S3; relates to E2-S9 (canonical keys)

---

## Deferred / not-yet-scoped epics

Named in [`../docs/ROADMAP.md`](../docs/ROADMAP.md); to be expanded in a later backlog
round. Per D014, the former "E4 PV ingestion" is split into the scoped UCSB epic above (E4)
and the named MIT epic (E5) below.

- **E5 — MIT PV ingestion** (M2): load the clean MIT Election Lab 1976–2024 CSV as the
  API-eligible modern core (covers the 2000/2016 splits); tag `source=MIT`. Gated on E3's
  MIT licensing finding for the redistribution question. Conforms to the canonical keys
  (E2-S9) and the shared PV schema defined in E4.
- **E6 — Canonical key + cross-source join** (M2): join MIT + UCSB PV onto the EC spine
  (E2-S9); EC as source of truth (D006).
- **E7 — Hybrid computation** (M3): EC/PV average; flip detection; three-method margin comparison.
- **E8 — Internal API** (M3): expose the joined dataset; MVP bar = powers our app; excludes
  `redistributable=false` rows from any public surface (D002/D014).
- **E9 — Analytical explorer data mart** (M3): query surface for flips/margins/maps/narrative.
