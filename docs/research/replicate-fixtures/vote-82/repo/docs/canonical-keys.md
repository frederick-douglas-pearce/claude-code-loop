# Canonical keys — the cross-source reconciliation spine

The project joins Electoral College data (National Archives) with popular-vote data
from two other sources (UCSB, [E4](https://github.com/frederick-douglas-pearce/us-presidential-vote-analysis/issues/33);
MIT, E5). Two datasets from three sources need a governing key and a designated
authority, or reconciliation conflicts have no tiebreaker.

Per [decision **D006**](../.claude/specs/decisions.md), the **EC data is the source of
truth**, and a **canonical candidate key** and **canonical state key** are the shared
spine every other source conforms to. This page is the human-browsable description of
those keys. The authoritative, machine-readable definition is the set of constants in
the "canonical keys" section of
[`src/usvote/transform.py`](../src/usvote/transform.py), each locked by a test in
[`tests/test_transform.py`](../tests/test_transform.py).

> **Scope (issue #30).** This establishes and documents the EC-side keys only. It does
> **not** build the cross-source join (deferred to E6) or any source's reconciliation
> logic ([#38](https://github.com/frederick-douglas-pearce/us-presidential-vote-analysis/issues/38)
> maps UCSB names onto these keys). The job here is to fix the target the join will aim at.

## The two keys are two-tier

Each key has a **human/display form** (the primary key the warehouse stores and people
read) and a **machine match target** (the stable, format-normalized columns a foreign
source actually reconciles onto, because its display strings never match the Archives'
verbatim — UCSB prints `BIDEN, JOSEPH R. JR`; MIT carries `state_po`/`state_fips`).

| Key | Display form (warehouse PK) | Match target (reconcile onto) | `transform.py` constant |
|---|---|---|---|
| **Candidate** | the reconciled full `name` (e.g. `Donald J. Trump`) | the parsed name parts `name_first` / `name_middle` / `name_last` / `name_suffix` | `CANDIDATE_KEY`, `CANDIDATE_MATCH_COLUMNS` |
| **State** | the full `state` name (e.g. `District of Columbia`) | the USPS code `state_usps` (e.g. `DC`) | `STATE_KEY`, `STATE_MATCH_COLUMN` |

Both keys **absorb the variance already handled in transform** so a foreign source only
has to match the canonical form, never the raw one:

- **Candidate** — multi-state candidates are aggregated to one row (primary `state` +
  `state_2`), multi-party to `party`/`party_2`, and name spellings are reconciled to a
  single canonical form (Trump `Donald Trump`→`Donald J. Trump`, McGovern, Bob Dole,
  the Faith Spotted Eagle surname split). See [`corrections.md`](corrections.md) for the
  full catalog of name reconciliations, which double as the first instances of this
  canonical-key problem.
- **State** — the full state name is stable and unambiguous across all covered years;
  TIGER territories are dropped so the dimension is exactly the 50 states + DC.

## `candidate_id` is **not** a canonical key

`build_candidate_dim` assigns `candidate_id` as a **1-based, row-order surrogate**. It
shifts whenever the candidate set or its order changes (for example when EC coverage is
extended below 1892,
[#32](https://github.com/frederick-douglas-pearce/us-presidential-vote-analysis/issues/32)).
It is therefore:

- an **internal join key only** — fine for wiring the votes fact to the candidate
  dimension within one build;
- **never** a cross-source reconciliation key (a PV source carries names, not our
  surrogate); and
- **never** an externally-exposed identifier (e.g. through the planned API, E8). If a
  durable public candidate id is ever needed, mint a deterministic name slug — do not
  promote `candidate_id`.

The test `test_candidate_key_is_stable_but_candidate_id_is_not` locks this distinction:
the `name` key set is invariant to input row order; the `candidate_id`→`name` mapping is
not.

## Known residual: same-name collisions

The canonical candidate key is the full `name` string, guarded by a one-row-per-name
grain check. A single build cannot, on its own, distinguish **two different people who
share an identical full name**. Because candidate rows are aggregated by name *before*
the grain check, such a collision would silently merge two people into one row rather
than tripping the uniqueness assert.

`_candidate_states` therefore carries a **canary** (`MAX_HOME_STATES`): a candidate that
aggregates to **more than two distinct home states** is unrepresentable in the
`state`/`state_2` model and raises `TransformError` instead of silently dropping the
third state. That catches the collision when it manifests as an over-count. A stronger,
curated per-name allow-list is deferred until coverage actually surfaces a same-name
collision (most likely when extending below 1892, #32) — at which point the fix follows
the corrections pattern: a provenance-carrying constant + a test + a catalog row.

## How each source conforms onto the keys

A foreign PV source conforms by rewriting its native `state`/`candidate` strings to the
canonical **display** forms above, in its own source-namespaced reconcile stage:

- **UCSB** (#38, D025) — `reconcile_ucsb` in
  [`src/usvote/ucsb/reconcile.py`](../src/usvote/ucsb/reconcile.py). UCSB's **state** names
  were already reconciled in #36 (`UCSB_STATE_RECONCILIATIONS`); this story reconciles
  **candidate** names via `UCSB_CANDIDATE_RECONCILIATIONS` — a curated, provenance-carrying
  map keyed by `(year, ucsb_native_name)` (111 entries; keyed by year because 49 elections
  reuse surnames across people, e.g. the two Roosevelts). Like MIT's, UCSB's header spelling
  is not a mechanical transform of the canonical `name` (`STROM THURMOND` → `J. Strom
  Thurmond`, `ADLAI E. STEVENSON` → `Adlai Stevenson`, `JOHN C. FREMONT` → `John C. Frémont`).
  Unlike MIT, reconcile also applies the **D007 candidate scope** here — UCSB has no
  `party_simplified` proxy, so scoping to EC-getters is a name match: the 8 popular-vote-only
  minors are dropped (`UCSB_NON_GETTER_COLUMNS`) and a reciprocal completeness guard, against
  an injected EC-getter frame, proves no major was silently lost (`EC_GETTERS_WITHOUT_POPULAR_VOTE`
  exempts the 13 getters — faithless/unpledged/legislature-chosen — that held no popular vote).
- **MIT** (#67, D020) — `reconcile_mit` in
  [`src/usvote/mit/reconcile.py`](../src/usvote/mit/reconcile.py), via two curated,
  provenance-carrying maps: `MIT_STATE_RECONCILIATIONS` (51 jurisdictions,
  `DISTRICT OF COLUMBIA` → `District of Columbia`) and `MIT_CANDIDATE_RECONCILIATIONS`
  (18 D/R nominees, 1976–2024, bounded by D019). MIT's `"LAST, FIRST M. SUFFIX"` is not
  a mechanical transform of the canonical `name` — the same reconciliation drops MIT's
  middle initial for some (`OBAMA, BARACK H.` → `Barack Obama`) and adds one for others
  (`FORD, GERALD` → `Gerald R. Ford`) — which is why it is a curated map, not a parser.

**Sources emit the display key, and E6 joins on it.** Because reconciliation removes the
*format* variance, the "match target" columns (name-parts, `state_usps`) are not needed
for the PV↔EC join: both sources produce the canonical `name` / full `state` name
directly, and the cross-source union/join (E6, #68/#69) keys on the display form. The
reconcile stage produces canonical *values* offline; #69 owns the reciprocal guard that
every reconciled value is actually present in the EC dims (an unmatched value must fail
loud there, not vanish in an inner join).

## The union is the raw fact; the series are read-time views (#68, D017)

Once both sources sit on the canonical keys, they are already stacked in **one**
`dwh.pv_votes` — each loaded through `load_pv_records`, tagged by `source`, with `source`
part of the natural key so the 1976–2024 overlap keeps **both** rows. That table *is* the
raw union; #68 adds no second fact table. It exposes three D017 series as thin read-time
views over the union (see [`src/usvote/pv/views.py`](../src/usvote/pv/views.py)):

- **`pv_preferred`** — the default analysis series: exactly one row per `(year, state,
  candidate)`, MIT winning the overlap and UCSB supplying everything earlier. Resolved by
  `DISTINCT ON (year, state, candidate) ORDER BY …, precedence_rank`.
- **`pv_redistributable`** — the public API surface, defined *independently* as `WHERE
  redistributable` (MIT only), never as a filter over `pv_preferred`, so no change to
  preference resolution can leak a non-redistributable UCSB row onto it.
- **`pv_ucsb`** — the whole-span UCSB-only consistency control.

Precedence, `redistributable`, and license are **data, not code** — one row per source in
the `dwh.pv_source` reference table ([`src/usvote/pv/source.py`](../src/usvote/pv/source.py)),
which the views join on `source`. A UCSB redistribution grant, or adding a third source, is
a one-row edit with no view or DDL change.

**The join (#69) reads a resolved view, never the raw union.** Joining the EC spine to
`dwh.pv_votes` directly would fan the overlap out 2× and double-count every downstream
sum/margin — the raw tagged union and the resolved single-row series are deliberately
named apart to prevent that mistake. It landed as
[`src/usvote/join.py`](../src/usvote/join.py) (D026): an **EC-left join**
(`ec_pv_preferred` for analysis, `ec_pv_redistributable` for the API) at the canonical
`(year, state, candidate)` grain. EC-left works because the EC votes fact is **dense** —
the Archives prints `-` for "no electoral votes here", read as `0`, so a candidate who
*lost* a state's electoral votes is a real `0`-EV row (not a missing one), and the LEFT
JOIN keeps it with its popular votes attached — exactly the "lost the EC, won the PV" data
the thesis explores. That module is also where **this page's promised reciprocal guard
runs**, now at the fact grain: a `NOT EXISTS` anti-join asserts every resolved PV
`(year, state, candidate)` matches an EC votes row, enforced as a view-creation
precondition — an unmatched value fails loud there rather than being silently dropped by
the LEFT JOIN.
