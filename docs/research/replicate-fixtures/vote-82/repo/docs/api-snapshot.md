# The API snapshot — serving contract (E8-S1)

The internal API (E8) serves a **read-only SQLite snapshot**, never a live database
([decision **D028**](../.claude/specs/decisions.md)). The local Postgres warehouse stays
the source of truth; a CLI build step materializes the shipped `ec_pv_redistributable`
join view (E6 / [`src/usvote/join.py`](../src/usvote/join.py)) into an immutable snapshot
file, and the running API reads only that file — so it starts and answers requests with
Postgres stopped (the scale-to-zero cost/reliability lever). This page is the contract the
API layer (E8-S2/S3) consumes; the authority is the module
[`src/usvote/snapshot.py`](../src/usvote/snapshot.py).

## Building it

```
export USVOTE_API_SNAPSHOT_PATH=/path/to/snapshot.sqlite
python -m usvote all           # (re)build the warehouse incl. ec_pv_redistributable
python -m usvote.snapshot      # read the view, write the snapshot (needs local Postgres)
```

`python -m usvote.snapshot` requires the local warehouse **at build time only** — it reads
`dwh.ec_pv_redistributable` and fails loud (pointing you at `usvote all`) if that view is
absent. Pass `-o/--out` to override `USVOTE_API_SNAPSHOT_PATH`. The build is **reproducible
and idempotent**: the same warehouse data always yields the same `snapshot_version`, and
re-running overwrites the file atomically.

## What's redistributable-only, and why the window is 1976–2024

The snapshot reads `ec_pv_redistributable`, which wraps `pv_redistributable` — defined
independently as `WHERE redistributable` (MIT / CC0 only, [D016](../.claude/specs/decisions.md)
/ [D017](../.claude/specs/decisions.md)) — so **no UCSB / `redistributable=false` row can
reach it** (D030). The build re-asserts this at the source (defense-in-depth over the
endpoint and regression guards in E8-S3/S5).

`ec_pv_redistributable` is EC-**left**, so it carries every EC state row from 1824 on with
PV attached only where MIT covers it. The public surface is the **redistributable window**
— the years that actually have PV (1976–2024). Pre-1976 years (all-NULL PV) are honestly
absent by construction (D005/D016), not an error. Within the window, an EC getter MIT does
not cover (a faithless elector, an unpledged slate) keeps its EC row with **NULL** PV — an
honest gap, never a fabricated 0.

## The three tables

### `ec_pv` — the joined fact

One row per `(year, state, candidate_slug)` over the window — that grain is the table's
**PRIMARY KEY**, so a join-view or slug-mapping fan-out fails loud at build (INSERT) rather
than silently shipping duplicates the content hash would bless. Secondary indexes on
`state` / `state_usps` / `candidate_slug` serve the by-state/by-candidate endpoints (the
`year` lookups ride the PK's leftmost prefix). Every EC state row is kept — winners **and**
0-EV losers (the dense-fact rows the thesis explores: "lost the EC, won the PV").

| column | type | notes |
|---|---|---|
| `year`, `state` | INTEGER, TEXT | canonical grain |
| `state_usps` | TEXT | USPS code (`CA`), a clean path key for `/v1/states/{...}` (#97) |
| `candidate` | TEXT | canonical display name |
| `candidate_slug` | TEXT | **public** candidate id (see below) |
| `total_electoral_votes` | INTEGER | the state's EV allotment |
| `president_electoral_votes` | INTEGER | this candidate's EVs in this state (0 for a loser) |
| `national_electoral_votes` | INTEGER | national EV total (window sum over the candidate's states) |
| `president_electoral_rank`, `took_office` | INTEGER | national EC context, broadcast onto every row |
| `source`, `party`, `reliability` | TEXT | PV provenance (NULL where MIT has no PV) |
| `candidate_votes`, `state_total_votes` | INTEGER | PV count and the source's provided denominator (NULL where no PV) |

`candidate_id` — the warehouse's internal, row-order surrogate — is **dropped** and never
exposed ([`docs/canonical-keys.md`](canonical-keys.md), D006). The durable public id is
`candidate_slug`, minted deterministically from the canonical name
([`src/usvote/slug.py`](../src/usvote/slug.py); `Donald J. Trump` → `donald-j-trump`). Two
distinct names colliding onto one slug (the same-name residual) fails the build loud.

### `national_rollup` — precomputed summary

One row per `(year, candidate_slug)` so `/v1/elections/{year}/summary` **reads** instead of
computing in a route handler: `national_electoral_votes`, `national_pv_votes` (NULL for a
no-PV getter), and `national_pv_denominator` (each state's total counted once — the
**non-null** `state_total_votes` per state, so a no-PV getter's NULL row never drops the
state from the sum). Safe to precompute because the window is single-source (MIT), so there
is no cross-source denominator ambiguity (D017).

### `snapshot_meta` — one provenance row

`snapshot_version`, `schema_version`, `row_count`, `candidate_count`, `year_min`/`year_max`,
`source` = MIT, `license` = CC0-1.0 (read from the `pv_source` reference data), and an
informational `build_timestamp`. Feeds the API `meta` block and the ETag.

`year_min`/`year_max` are **descriptive of the snapshot's actual content** — the
redistributable years it contains — not a promise of completeness. A full warehouse build
yields 1976–2024; a warehouse built over a scoped subset of years (e.g. the integration
fixtures) yields a correspondingly narrower window, honestly reported.

## `snapshot_version` is a content hash, not a timestamp

`snapshot_version` is a SHA-256 over the `ec_pv` rows in a deterministic
`ORDER BY (year, state, candidate_slug)` plus `schema_version`. The build timestamp is
**excluded** from it. This is the single value that reconciles reproducibility ("same
warehouse, same version") with the freshness/ETag contract ("identical data, identical
version") the API (E8-S2) serves.

Because the hash covers only the `ec_pv` data rows — **not** the derived `national_rollup`
— a change to how the roll-up is *computed* over identical underlying data would not move
the hash on its own. Such a change therefore **must** bump `SNAPSHOT_SCHEMA_VERSION` (which
is folded into the hash), so cached consumers see a new version.
