US Presidential Election Analysis: Electoral College, Popular Vote, or Both?
======
This project analyzes historical US Presidential Election data to better understand the relationship between the Electoral College Vote results and the Popular Vote results. Debate frequently flares up as to whether the Electoral College approach for determining the winner of US Presidential Elections should be changed so that the Popular Vote decides who wins instead. Reviewing the actual data of past Presidential Elections shows the differences between these two approaches for past elections. For example, how many times would a different outcome have occurred if the Popular Vote decided the presidential election outcome, and how would the margin of victory be different?

In the spirit of checks and balances &mdash; a pillar of our democratic republic &mdash; I propose a third option: what about using the average of the Electoral College Vote and Popular Vote? Exploring a more balanced approach for determining the US President is the focus of the final portion of this historical voting analysis.

The project is broken down into several steps, with the first two focused on data collection and validation, while the third focuses on analyzing the historical data under different approaches to determining the election outcome:
  1. [X] **Electoral College data** &mdash; scrapes electoral college vote data for each US Presidential Election from 1824 to the present (excluding the contested 1868 and 1872 Reconstruction elections) from the [National Archives website](https://www.archives.gov/electoral-college/results), and writes the data to a data warehouse schema in an `elections` Postgres database. Originally the `step1_electoral_college_data.ipynb` notebook; now also runnable as the installable `usvote` package (see [Configuration](#configuration)).
  2. [X] **Popular vote data** &mdash; ingests popular-vote results from two sources &mdash; the [MIT Election Lab](https://electionlab.mit.edu/) 1976&ndash;2024 dataset and the historical [UCSB American Presidency Project](https://www.presidency.ucsb.edu/) pages &mdash; reconciles them onto the same candidate and state keys as Step 1, adds them to a shared fact table in the data warehouse schema built in Step 1, and joins the result back onto the Electoral College spine (analysis of the discrepancies is Step 3).
  3. [ ] **Voting data analysis** &mdash; performs the voting analysis, develops visualizations, and creates objects within a data mart schema to support dashboard development.

> **Now an installable package.** What began as Step 1's notebook has grown into an installable `usvote` Python package under `src/` (decision D003). It now spans the Electoral College spine (`usvote/`), both popular-vote sources (`usvote/mit/`, `usvote/ucsb/`) over a shared set of PV contracts (`usvote/pv/`), the EC&harr;PV join seam (`usvote/join.py`), and a `usvote/warehouse.py` composition root that builds the whole warehouse in one command. The Step&nbsp;1 notebook is retained while the "keep the notebook vs. fully migrate off it" decision (D003) stays open. See [CLAUDE.md](CLAUDE.md) for the module-to-notebook-section map and the `uv`/pytest tooling, and the [`docs/`](docs/) folder &mdash; [ROADMAP](docs/ROADMAP.md), [canonical-keys](docs/canonical-keys.md), [corrections](docs/corrections.md) &mdash; for the design decisions and data catalogs.

The data model for the data warehouse loosely follows a star schema design &mdash; appropriate for historical data of moderate size &mdash; with dimension tables that organize data for the Presidential Candidates and for the US States, and a fact table (`dwh.votes`) that contains the Electoral College Votes by State data for each Presidential Election.

The popular-vote work (Step&nbsp;2) extends that schema without disturbing the spine. A parallel `dwh.pv_votes` fact holds the reconciled MIT and UCSB popular-vote records at the shared `(year, state, candidate)` grain, and a `dwh.pv_state_status` roster records, per source and year, whether each state ran a popular vote, chose its electors by legislature, or did not participate (the `pv_status` enum &mdash; `popular_vote` / `legislature_chosen` / `not_participating`). Two views then join the resolved popular vote back onto the Electoral College spine: `ec_pv_preferred` (the analysis surface) and `ec_pv_redistributable` (the license-clean public subset).

The data collected, transformed, validated, and written to the `elections` Postgres database for this project is designed to back an API and/or power dashboards that surface key findings from the voting analysis &mdash; the `ec_pv_preferred` join view is the intended analysis surface for that Step&nbsp;3 work.

## Usage
1. Fork this repo and then clone it to your local environment

```
$ git clone https://github.com/frederick-douglas-pearce/us-presidential-vote-analysis
```

2. Install/Data Requirements
  * **Python** (>=3.11; developed on 3.14) and [**uv**](https://docs.astral.sh/uv/) for dependency and environment management. From a fresh clone, `uv sync` reads `pyproject.toml` + `uv.lock` to create a virtual environment and install all dependencies (BeautifulSoup, requests, pandas, geopandas, matplotlib, psycopg2, and the dev/notebook tools):

```
$ uv sync
```
  * **PostgreSQL** (>12.9) containing a database with permissions for creating a schema and tables. Typical defaults suffice: `host=localhost`, `port=5432`, `dbname=elections`, `user=postgres`, and whatever `password` you choose. The `usvote` package reads these from the environment (the standard libpq `PG*` variables) &mdash; see [Configuration](#configuration) below; the password is prompted securely at runtime via `getpass` when unset. The step&nbsp;1 notebook reads the same values from the environment.
  * **US States Shapefile** is required to obtain state data, such as name, region id, land area, lat/lon of state's center, etc. Download the required file from [here](https://www2.census.gov/geo/tiger/TIGER2019/STATE/), place it on your file system somewhere accessible, and point the `USVOTE_SHAPEFILE_PATH` environment variable at the unzipped `.shp` (see [Configuration](#configuration)); `geopandas` will take care of the rest.

3. Run the Electoral College ingestion. With the environment configured (see [Configuration](#configuration)), the packaged pipeline is the primary path:

```
$ python -m usvote            # create-if-absent load (bare = the EC spine)
$ python -m usvote --replace  # destructive: drop and recreate the dwh schema first
```

  The entry points are subcommand-based; bare `python -m usvote` stays the EC spine for backward compatibility. To build the **whole** warehouse — the EC spine plus the popular-vote sources (MIT, and UCSB when its snapshot is present) plus the EC↔PV join views — in one command:

```
$ python -m usvote all              # EC + MIT + (auto-detected) UCSB + join views
$ python -m usvote all --replace    # clean full rebuild (drops the schema, then reloads all)
$ python -m usvote all --no-ucsb    # EC + MIT only (the redistributable public core)
```

  `all` also needs `USVOTE_MIT_CSV_PATH` (and, for UCSB, `USVOTE_UCSB_HTML_DIR`); it prints a loud notice and builds without UCSB when that snapshot is absent (pass `--require-ucsb` to fail instead). A single popular-vote source can also be loaded on its own with `python -m usvote.mit load` or `python -m usvote.ucsb load` (both require the EC spine already loaded); `python -m usvote.ucsb` (bare) still *snapshots* the raw UCSB pages.

### The internal API (E8)

The `usvote/api/` subpackage serves the redistributable EC+PV data over HTTP from a **read-only SQLite snapshot** — with **no live database at serve time** ([D028](.claude/specs/decisions.md); the app never imports `usvote.db`/psycopg2, enforced by a test). Postgres is the local source of truth, read only when the snapshot is *built*. Two steps:

```
$ export USVOTE_API_SNAPSHOT_PATH=/path/to/snapshot.sqlite
$ python -m usvote.snapshot     # build the snapshot from dwh.ec_pv_redistributable (needs the warehouse)
$ python -m usvote.api          # serve it locally (no DB needed); or `python -m usvote.api serve --port 8000`
```

For production/container use, point an ASGI server straight at the app factory: `uvicorn --factory usvote.api:create_app`. The server starts and answers requests with Postgres **stopped** — that is the point. `GET /health` reports the loaded snapshot's version and coverage; the data endpoints live under the versioned `/v1` prefix: `GET /v1/elections` (list covered years), `/v1/elections/{year}` (per-state rows + national summary), `/v1/elections/{year}/summary` (the national roll-up), `/v1/states/{usps}`, and `/v1/candidates/{slug}` (each a typed Pydantic model in a shared `{data, meta}` envelope; [`GET /v1/meta`](docs/api-snapshot.md) is the provenance block). CORS defaults to localhost and is overridden with `USVOTE_API_CORS_ORIGINS`.

**Browsing the docs (start here as an external developer).** Interactive OpenAPI docs render at **`/docs`** (Swagger UI) and **`/redoc`** (ReDoc) — the hand-off surface. They carry the thesis, the endpoint reference with realistic examples, and a first-class **data-provenance & licensing** statement up front: the popular-vote data is sourced from the **MIT Election Lab** under **CC0 1.0** (public domain), and non-redistributable UCSB data is excluded ([D016](.claude/specs/decisions.md)/[D030](.claude/specs/decisions.md)). That same provenance — source, license, coverage window, and snapshot version — also travels in every response under `meta.provenance`, so it can never drift from what was actually built.

#### Running the API in a container

The API also ships as a **cloud-agnostic Docker image** with the snapshot **baked in** — the MVP's single runnable deliverable ([D032](.claude/specs/decisions.md)). Because the snapshot is copied *into* the image (never mounted), the container's data version equals its image version, so there is no artifact/code skew. The running container needs **no database and no network** — Postgres can be stopped.

Build the snapshot first (that step, and only that step, needs the warehouse), copy it into the build context, then build and run:

```
# 1. Build the snapshot from the warehouse (needs Postgres) — see the smoke test below.
$ python -m usvote.snapshot                        # writes $USVOTE_API_SNAPSHOT_PATH

# 2. Copy it into the build context (it lives outside the repo; the copy is git-ignored).
$ cp "$USVOTE_API_SNAPSHOT_PATH" ./api_snapshot.sqlite

# 3. Build the image and run it (no DB needed at runtime).
$ docker build -t usvote-api .
$ docker run --rm -p 8080:8080 usvote-api          # Cloud-Run-style: listens on $PORT (default 8080)

$ curl -s localhost:8080/health | jq -c '{v: .snapshot_version[0:8], rows: .row_count, years: .coverage}'
# → {"v":"bc6056f3","rows":1734,"years":{"year_min":1976,"year_max":2024}}
```

The image is **slim by design** (~150 MB): the API serve path imports only FastAPI + stdlib, so the container installs the package with `--no-deps` plus a lock-pinned `serve` dependency-group — the heavy warehouse/analysis stack (pandas/GDAL/psycopg2/matplotlib) never enters the image ([D033](.claude/specs/decisions.md)). It is cloud-agnostic (listens on `$PORT`, no vendor SDKs, no baked-in secrets), so the Cloud Run deploy (E8-S7, #101) is a deploy step, not a rebuild. To refresh the data, rebuild the snapshot and the image (acceptable given the ~4-yearly refresh cadence). A CI job builds and boots the image against a synthetic placeholder snapshot to catch Dockerfile rot.

#### Deploying it publicly (Cloud Run + Cloudflare)

The API is deployed publicly to **Google Cloud Run** (scale-to-zero, single instance) fronted by **Cloudflare (free)** for CDN caching, rate limiting, and bot protection — see the runbook [`docs/deploy-cloud-run.md`](docs/deploy-cloud-run.md) ([D034](.claude/specs/decisions.md)). Cost is the priority: the container scales to **zero** when idle, caps at **one** instance, uses request-based CPU, Cloudflare's edge absorbs repeat reads, and a **budget kill-switch** ([`deploy/killswitch/`](deploy/killswitch/)) caps the worst case — at this traffic it sits inside the Cloud Run free tier (≈ $0). A keyless (Workload-Identity-Federation) `workflow_dispatch` GitHub Action ([`.github/workflows/deploy.yml`](.github/workflows/deploy.yml)) builds a snapshot-hash-tagged image from a private GCS-hosted snapshot, deploys, and purges the edge cache after cutover (**version-based** invalidation, not TTL). A direct hit on the raw `run.app` URL is rejected (403) so bots can't bypass Cloudflare's edge — enforced only in the deployed environment, fail-open locally. The Cloudflare front is a **Worker** that rewrites the `Host` header to the `run.app` name, injects the secret, and caches `/v1` at the edge (the free plan paywalls Origin Rules' Host override; [D035](.claude/specs/decisions.md)). The API is live at **`https://api.us-presidential-election-center.org`**.

#### Local smoke test (full pipeline → live API)

The end-to-end check we run repeatedly while building out E8: warehouse → snapshot → HTTP, then hit the live endpoints against real 1976&ndash;2024 data. Configure the environment first (see [Configuration](#configuration)) — the build steps read `PGPASSWORD` from your git-ignored `.env`, so load it into the shell once:

```
$ set -a; source .env; set +a               # load PG* + USVOTE_* (never commit .env)

# 1. Build the warehouse (needs Postgres). ~30s; scrapes the Archives + loads MIT.
$ python -m usvote all                       # a fresh/empty DB needs no --replace

# 2. Materialize the read-only snapshot (needs Postgres; reads dwh.ec_pv_redistributable).
$ python -m usvote.snapshot

# 3. Serve it (no DB — only USVOTE_API_SNAPSHOT_PATH). Pick a free port if 8000 is taken.
$ python -m usvote.api serve --port 8000     # Swagger UI at http://127.0.0.1:8000/docs
```

Then, in a second shell, sanity-check the live surface (these need only the running server — no database):

```
$ B=http://127.0.0.1:8000/v1
$ curl -s "$B/elections" | jq -c '{count: .meta.count, first: .data[0], last: .data[-1]}'
# → {"count":13,"first":{"year":1976,...},"last":{"year":2024,...}}

$ curl -s "$B/elections/2000/summary" \
    | jq -c '.data[] | {slug: .candidate_slug, ec: .national_electoral_votes, pv: .national_pv_votes, took_office}'
# → Bush: 271 EC / 50,456,169 PV / took_office true
#   Gore: 266 EC / 50,996,062 PV / took_office false   ← the thesis: lost the EC, won the popular vote

$ curl -s -o /dev/null -w '%{http_code}\n' "$B/elections/1900"   # → 404 (pre-1976, outside the window)
```

`GET /health` (unversioned) reports the loaded snapshot's version and coverage with no database at all. Stop the server with Ctrl-C.

  Alternatively, open the original notebook in JupyterLab to run or explore step 1 interactively:

```
$ uv run jupyter lab
```
  * Once a JupyterLab session is running in your browser, find the notebook you want to work with using the File Browser in the left panel, then double click on the notebook to open it.
  * Both paths require an internet connection for scraping data, plus the US States shapefile downloaded and pointed to via `USVOTE_SHAPEFILE_PATH`.


## Configuration

The `usvote` package reads all configuration from the environment &mdash; no source
edits are needed to run it on a fresh machine (issue #31). Copy the template and edit
the values:

```
$ cp .env.example .env          # .env is git-ignored; never commit real secrets
$ # ...edit .env...
$ set -a; source .env; set +a   # load into the shell (quote any path with spaces)
```

No dotenv library is required &mdash; the variables are read from the process
environment, so exporting them by hand or using `direnv` works equally well.

| Variable | Purpose | Default |
|---|---|---|
| `PGHOST` | Postgres host | `localhost` |
| `PGPORT` | Postgres port | `5432` |
| `PGDATABASE` | database name | `elections` |
| `PGUSER` | database user | `postgres` |
| `PGPASSWORD` | database password | *(unset &rarr; prompted securely at runtime)* |
| `USVOTE_SHAPEFILE_PATH` | path to the unzipped TIGER2019 STATE shapefile (`.shp`) | *(required)* |
| `USVOTE_MIT_CSV_PATH` | path to the MIT Election Lab `1976-2024-president.csv` | *(required for the MIT popular-vote pipeline)* |
| `USVOTE_UCSB_HTML_DIR` | path to the local UCSB raw-HTML snapshot directory | *(required for the UCSB popular-vote scrape)* |
| `USVOTE_API_SNAPSHOT_PATH` | path to the read-only SQLite API snapshot — written by `python -m usvote.snapshot`, read by `python -m usvote.api` | *(required for the snapshot build and the API)* |
| `USVOTE_API_CORS_ORIGINS` | comma-separated CORS allow-list for the API | *(unset &rarr; localhost dev origins; never a silent `*`)* |

Database settings use the standard libpq `PG*` names, so the same values are shared
with `psql`, `pg_dump`, and other Postgres tools. The TIGER2019 STATE shapefile is a
free download from the [Census Bureau](https://www2.census.gov/geo/tiger/TIGER2019/STATE/).
The MIT president CSV is a free CC0&nbsp;1.0 download from
[Harvard Dataverse](https://doi.org/10.7910/DVN/42MVDX); like the shapefile it lives
outside the repo and is located via its environment variable, not committed.

The UCSB snapshot directory holds the raw per-election HTML fetched by
`python -m usvote.ucsb` (one `{year}.html` per election, plus `_index_elections.html`
and a sha256 `manifest.json`). UCSB / American Presidency Project content is **not
redistributable**, so this directory must live **outside** this public repository and
its bytes are never committed &mdash; only the scrape code is versioned (see D023). The
scrape is deliberately polite (honors the site's `Crawl-delay: 10`, so a full run takes
~10&nbsp;minutes) and re-runnable (already-saved pages are skipped).

Once configured, run the Electoral College ingestion pipeline from the package (an
alternative to executing the step&nbsp;1 notebook cells):

```
$ python -m usvote            # create-if-absent load
$ python -m usvote --replace  # destructive: drop and recreate the dwh schema first
```

You are prompted for `PGPASSWORD` at runtime unless it is already set in the
environment.


## License
* Copyright 2021 Frederick D. Pearce
* Licensed under the Apache License, Version 2.0 (the "License")
* You may obtain a copy of the License from
[LICENSE](https://github.com/frederick-douglas-pearce/us-presidential-vote-analysis/blob/main/LICENSE) or
[here](http://www.apache.org/licenses/LICENSE-2.0)
 
