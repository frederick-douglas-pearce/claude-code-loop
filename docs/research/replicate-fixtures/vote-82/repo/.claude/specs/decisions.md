# Decision Log

Append-only log of significant trade-off decisions made during US Presidential Vote
Analysis development. Format mirrors the sibling agentfluent project: each entry is
`## D0NN: <title>` with **Date**, **Context**, **Decision**, **Rationale**, and an
optional **Action required**.

---

## D001: Analytical guiding star — the EC-vs-PV-vs-hybrid what-if explorer

**Date:** 2026-07-05
**Context:** The project could aim first at a polished presentation surface (a Looker
prototype already exists) or at the analytical capability underneath it. We need a
single near-term star to sequence everything else against.
**Decision:** The first milestone to aim toward is an interactive "what-if" explorer
answering *"would this election have flipped under PV or the hybrid, and by how much?"*
with maps and narrative. The presentation platform / frontend host is **deferred** —
we do not design the frontend now, and the existing Looker prototype is not the
intended host.
**Rationale:**
- The differentiated value is the analysis and the cleanly joined dataset, not the
  chart-rendering layer, which is commodity and swappable.
- Committing to a frontend now would force premature hosting and UX decisions before
  the data model that feeds them is trustworthy.
- A crisp analytical question ("flip and by how much") gives every upstream epic a
  concrete target to conform to.

---

## D002: Public API is a first-class standalone deliverable

**Date:** 2026-07-05
**Context:** The joined EC+PV dataset is valuable in its own right — no equivalent
appears to exist publicly. The API could be treated as mere plumbing for our app, or
as a deliverable in its own right.
**Decision:** A public API over the joined dataset is a first-class standalone
deliverable. The **MVP bar is "the API powers our app."** A fully public /
third-party-developer API is a **stretch goal, gated on PV-data licensing** permitting
redistribution.
**Rationale:**
- The scarcity of a cleanly joined EC+PV dataset means exposing it has independent
  value to third-party developers and researchers.
- Setting the MVP bar at "powers our app" keeps the near-term scope bounded while
  building the API surface in a way that can graduate to public later.
- Third-party exposure hinges on redistribution rights we do not yet have (see D008),
  so it cannot be an MVP commitment.

---

## D003: Adopt a tested `src/` package + reproducible pipeline (retire the monolith)

**Date:** 2026-07-05
**Context:** The pipeline today is a single monolithic Jupyter notebook plus a thin
psycopg2 wrapper. That is fine for a seed but insufficient for numbers that must be
trustworthy and re-runnable every four years.
**Decision:** Adopt an `src/` Python package with a reproducible, tested pipeline,
mirroring the sibling agentfluent project's layout and conventions (uv, pytest, CI).
Replace the monolithic notebook **incrementally**. Target a 4-year ingestion cadence
(new data each presidential cycle).
**Rationale:**
- The thesis is only as credible as the pipeline underneath it; tests and
  reproducibility are the credibility.
- Mirroring agentfluent reuses proven conventions and lowers the cost of context-switching
  between the two repos.
- Incremental replacement preserves the notebook's dense inline validations and
  hardcoded historical corrections rather than discarding hard-won correctness.

**Action required:** M1 must decide the fate of the existing notebook (keep as research
artifact vs. fully migrate) as part of E1/E2 design — recorded as an open question, not
settled here.

---

## D004: Popular-vote ingestion is the critical-path linchpin

**Date:** 2026-07-05
**Context:** EC data is already loaded; PV data is not. The entire comparative thesis
(flips and margins under PV and the hybrid) is impossible without PV.
**Decision:** Treat PV ingestion as the critical-path linchpin. It is sequenced ahead
of the explorer and API, immediately after the `src/` backbone is in place.
**Rationale:**
- Nothing downstream — hybrid computation, flip detection, the explorer, the API — can
  begin producing thesis output until PV data exists and reconciles against EC.
- Naming it the linchpin makes the sequencing non-negotiable: backbone first, PV
  second, analysis third.

---

## D005: EC coverage expands to 1789–2024; PV gaps handled honestly

**Date:** 2026-07-05
**Context:** CLAUDE.md/README describe a 1892 EC floor. The National Archives now
publishes results back to 1789, and Fred has confirmed the Archives data is unrestricted.
PV, by contrast, is patchy or absent in the early republic.
**Decision:** Expand EC coverage to **1789–2024** — the old 1892 cutoff is obsolete.
Where PV is **unavailable**, handle it gracefully (no fabricated values); where PV is
**available-but-unreliable**, flag it explicitly with provenance. Authentic historical
representation is treated as a **product feature**, not an edge case.
**Rationale:**
- The Archives data being unrestricted removes the reason for the old floor.
- Surfacing PV gaps and reliability honestly is exactly the kind of provenance
  serious users (the NPVIC audience, researchers) need; hiding it would undermine trust.
- Provenance flags turn "missing data" from a defect into documented historical fact.

---

## D006: EC (National Archives) is the source of truth; canonical keys are the shared spine

**Date:** 2026-07-05
**Context:** Two datasets from two sources (Archives EC, TBD PV) must be joined.
Without a governing key and a designated authority, reconciliation conflicts have no
tiebreaker.
**Decision:** EC data from the National Archives is the **source of truth** for
reconciliation. A **canonical candidate key** and a **canonical state key** are the
shared spine that both datasets conform to.
**Rationale:**
- The Archives is the authoritative, unrestricted EC record; anchoring reconciliation
  to it gives every join a deterministic tiebreaker.
- Canonical keys absorb the messy real-world variance already seen in the EC data
  (name mismatches, split names, multi-party/multi-state candidates) into one spine
  the PV data must match, rather than reconciling ad hoc per join.
**Implemented by:** issue #30 — the EC-side keys are established, documented, and tested;
see [`docs/canonical-keys.md`](../../docs/canonical-keys.md) for the two-tier definition
(display PK vs. match target) and the `candidate_id`-is-not-canonical rule. The
cross-source join that consumes them is deferred to E6.

---

## D007: MVP candidate scope = candidates who received electoral votes

**Date:** 2026-07-05
**Context:** PV records include many minor candidates who never received an electoral
vote. Including all of them expands the candidate dimension and the reconciliation
burden substantially.
**Decision:** MVP candidate scope is **any candidate who received electoral votes**.
Minor PV-only candidates are tracked as **non-blocking nice-to-haves**. PV is provided
as **totals first**, with more granular detail added later by priority.
**Rationale:**
- Candidates with electoral votes are the ones that can change an EC/PV/hybrid outcome —
  the thesis-relevant set.
- Anchoring the candidate dimension to the EC-bearing set keeps it aligned with the
  source of truth (D006) and bounds reconciliation.
- PV totals are sufficient for flip-and-margin analysis; granularity is enrichment.

---

## D008: PV data source — pursue MIT Election Lab over UCSB / APP

**Date:** 2026-07-05
**Context:** Candidate PV sources include the MIT Election Data + Science Lab
(open-licensed state-level returns) and UCSB's American Presidency Project. Licensing
terms determine whether we can redistribute PV via a public API (see D002).
**Decision:** Pursue **MIT Election Lab** (open-licensed, state-level returns; Fred is
an MIT alum with a potential line to the lab director) over UCSB / American Presidency
Project, which has not replied on licensing and is deprioritized. The **final source
determination is its own research task** (epic E3), not settled by this decision.
**Rationale:**
- MIT's open licensing is the most promising path to the public-redistribution rights
  the stretch public API needs (D002).
- The alumni contact is a potential accelerant for licensing clarity.
- UCSB's licensing silence makes it a redistribution risk; deprioritize rather than block on it.

**Action required:** E3 (PV-source research) resolves the final source and confirms
whether its license permits public API redistribution. Open until then.

**Refined by:** D014 — the either/or framing here is superseded by a **dual-source** PV
strategy (MIT for the redistributable modern core + UCSB for historical breadth). D008
stands as the record of why MIT is the preferred *redistributable* source; see D014.

---

## D009: MVP comparison window starts at ~1824 (retained, mutually-agreed pending)

**Date:** 2026-07-05
**Context:** EC data extends to 1789 (D005), but the national popular vote is patchy in
the early republic. The choice was between anchoring the MVP comparison at ~1824 —
messy, but the first cycle with broad popular participation — versus starting at 1828,
which is cleaner (the first modern-style two-party popular election). 1824 itself is a
contingent election decided in the House, and six states still chose electors by
legislature that year.
**Decision:** **Retain ~1824 as the MVP comparison start** — do not push to 1828. EC
coverage still extends back to 1789 per D005; the *comparison* (flips/margins vs. PV
and hybrid) is what begins at ~1824. This is a **mutually-agreed pending** call — the
direction is set, but it is explicitly open to revisiting before implementation, since
serious data work (E3/E4) precedes any analysis and may surface reasons to adjust.
**Rationale:**
- 1824's messiness is a **narrative opportunity, not a defect.** The House contingent
  outcome and the legislature-chosen electors are exactly the phenomena the project
  exists to illuminate; starting at 1828 would silently bypass the very conditions that
  *made* 1828 cleaner and conformant to modern norms — dishonest, and a missed teaching
  moment.
- The provenance-first stance (D005) already commits us to representing unreliable or
  structurally-unusual data with flags rather than hiding it; 1824 is the flagship case
  for that stance, not an exception to it.
- Marking it pending keeps the decision cheap to revisit: the exact floor year is a
  one-parameter change to the comparison window, and the real data work in E3/E4 is the
  right point to confirm or adjust it.

---

## D010: Pre-12th-Amendment and contingent elections — structural nuances, mostly deferred

**Date:** 2026-07-05
**Context:** Elections of 1789–1800 predate the 12th Amendment: each elector cast two
votes for President and the runner-up became VP — structurally different from modern
tables. Separately, contingent elections decided in the House (1800, 1824) or Senate
(1836 VP) mean the EC plurality winner is not always who took office. The hybrid method
also raises a "no candidate reaches 270" legal ambiguity.
**Decision:**
- Pre-12th-Amendment elections (1789–1800) become their **own later epic**; the MVP
  leans on the structurally-uniform **post-1804** era.
- Contingent elections (1800/1824 House, 1836 Senate VP) are a **known data-modeling
  nuance to represent** — where the EC plurality winner differs from who took office.
- The hybrid "no candidate reaches 270" legal ambiguity is **parked for a later decision**.
**Rationale:**
- The two-votes-per-elector structure would distort the candidate/votes model if forced
  into the modern schema; isolating it protects MVP simplicity.
- Contingent elections are real historical outcomes the dataset must represent faithfully,
  but they are a modeling detail, not an MVP blocker.
- The no-270 hybrid question is a design question best answered alongside the detailed
  hybrid spec (D011), not now.

---

## D011: The hybrid method is settled in principle; its written spec is a future workstream

**Date:** 2026-07-05
**Context:** The hybrid (average of EC and PV) is Fred's original contribution and is
largely settled in his head, but no detailed written specification exists yet.
**Decision:** Treat the hybrid method as **largely settled in principle**. Its detailed
written spec — including the no-270 contingent-election treatment (D010) — is a **named
future workstream, not an MVP blocker**. MVP hybrid computation (E7) implements the
average / flip / margin logic; the formal spec follows.
**Rationale:**
- The core computation (average EC and PV, detect flips, compare margins) is clear
  enough to build the MVP explorer against.
- The edge cases requiring a formal spec (no-270, contingent elections) are rare and
  do not block the common-case analysis that delivers the MVP's value.

---

## D012: Process/tooling mirrors agentfluent conventions

**Date:** 2026-07-05
**Context:** Fred runs this project like the sibling agentfluent repo and wants
consistent PM and engineering conventions across both.
**Decision:** Mirror agentfluent's conventions: `.claude/specs/` for `prd-*`,
`backlog-*`, and `decisions.md`; `docs/ROADMAP.md`; GitHub-issue-driven epics/stories
with `epic:<slug>` and type/priority labels. The **pm agent owns PM artifacts**. Adopt
a `social/` placeholder folder *concept* for future blog/Medium content (not created now).
**Rationale:**
- Shared conventions lower the cost of context-switching between the two repos and let
  agentfluent's proven templates be reused directly.
- Naming the `social/` concept now reserves a home for future content marketing without
  incurring the cost of building it prematurely.

---

## D013: Package name — `usvote`

**Date:** 2026-07-05
**Context:** E1-S1 in the MVP backlog flagged the Python package name as an open
decision, defaulting to `usvote` with alternatives `uspv` and `elections`. The name is
referenced mechanically throughout the E1/E2 backlog as `src/usvote/`.
**Decision:** The package name is **`usvote`**. `src/usvote/` is the canonical package
root. Resolves the E1-S1 open decision.
**Rationale:**
- Fred approved `usvote`.
- Short and unambiguous; "pv" (popular vote) in the name signals the project's
  distinguishing analytical thesis, and it avoids the over-generic `elections` namespace
  that would collide conceptually with the existing `elections` Postgres database.
- Locking the name now removes the one blocker on E1-S1 and stabilizes every module path
  the rest of the backlog references.

---

## D014: Dual-source PV strategy — MIT (modern, API-eligible) + UCSB (historical, analysis-only)

**Date:** 2026-07-06
**Context:** Examination of the MIT Election Lab file Fred downloaded
(`1976-2024-president.csv`: 4,822 rows, **13 elections 1976→2024 only**, 51 jurisdictions,
one row per (year, state, candidate), with `candidatevotes` + state `totalvotes` and rich
columns — `state_po`, `state_fips`, `party_detailed`, `party_simplified`, `writein`,
`notes`) confirmed it is a clean, well-structured, state-level PV source that covers the
modern EC/PV splits (2000, 2016). But it only reaches **1976**, so it cannot satisfy the
~1824 MVP comparison window (D009) on its own. UCSB / American Presidency Project remains
the only source reaching ~1824 and is, per Fred, the most complete PV dataset available.
Its name format also differs from the Archives (`"BIDEN, JOSEPH R. JR"` vs `"Donald Trump"`),
so both sources reconcile via the canonical keys (D006 / issue #30).
**Decision:** Adopt **both** PV sources with distinct, non-overlapping roles:
- **MIT Election Lab (1976–2024)** — the clean, structured, **API-eligible modern core**;
  covers the 2000 & 2016 splits.
- **UCSB / American Presidency Project (~1824–1972)** — the **historical-breadth layer**,
  ingested for analysis and flagged **non-redistributable** pending a license answer.
- **Provenance and redistributability become first-class per-source data attributes**
  (every PV record carries `source` and a redistributable flag), extending D005.
**Refines D008.** D008 framed source selection as either/or (MIT over UCSB). D014
supersedes that framing: the two sources have non-overlapping jobs, so dual-source is a
**necessity, not redundancy**. D008 stands as the record of why MIT is the preferred
*redistributable* source; D014 adds UCSB as the required *historical-analysis* source.
**Rationale:**
- MIT's 1976 floor makes it insufficient for the historical thesis (the project needs
  ~1824 per D009); UCSB is the only path to that breadth.
- UCSB is needed for analysis even if it is never redistributable — analysis use and API
  redistribution are separable, which is exactly why redistributability must be a
  per-source attribute rather than an all-or-nothing project property.
- Splitting ingestion by source (clean MIT CSV vs. messy, era-drifting UCSB HTML) lets
  each be built at its own difficulty level instead of one over-general PV loader — hence
  UCSB gets its own epic, mirroring the EC ingestion architecture.
**Outreach path (deferred).** Two MIT-side contacts are the route to resolve MIT's license
terms and a possible pre-1976 coverage extension: **Zayne Sember**
(https://www.linkedin.com/in/zaynesember/ — published the 1976–2024 president file; lead
contact) and **Sean Greene** (https://www.linkedin.com/in/sean-greene-a467097/ —
additional contact). Outreach is **deferred until analysis back to 1976 is in hand**; its
exact mechanics remain open.
**Action required:** Backlog splits the former "E4 PV ingestion" into a scoped **UCSB
historical scrape + ingest** epic (E4, filed now, un-deferred) and a named-but-unscoped
**MIT PV ingestion** epic (E5). Roadmap epic numbering updated accordingly (join → E6,
hybrid → E7, internal API → E8, data mart → E9).

---

## D015: Source-namespacing convention — EC flat at the top level, each PV source its own subpackage

**Date:** 2026-07-06
**Context:** Defining the `src/usvote/` module skeleton (E1-S2 / issue #17, landed as
PR #40) created the Electoral College / National Archives pipeline modules flat at the
top level: `usvote/scrape.py`, `usvote/parse.py`, `usvote/transform.py`,
`usvote/load.py`, `usvote/db.py`, `usvote/pipeline.py`. The architect review of #17
flagged that D014 commits the project to two additional ingestion sources — UCSB (E4,
un-deferred) and MIT (E5) — each with its own full scrape→parse→transform→load pipeline.
E4-S1 already anticipates paths like `usvote/ucsb/scrape.py`. Without a stated
convention, those source modules would either collide with the flat EC module names (two
`scrape.py` files doing different jobs) or force an awkward retroactive move of the EC
modules into an `usvote/ec/` subpackage once E4 lands.
**Decision:** Adopt a **source-namespacing convention** for `src/usvote/` (D003):
- The **EC / National Archives pipeline stays flat** at the top level (`usvote/scrape.py`,
  `usvote/parse.py`, `usvote/transform.py`, `usvote/load.py`, `usvote/db.py`,
  `usvote/pipeline.py`).
- **Each popular-vote source lands as its own sibling subpackage** — `usvote/ucsb/` (E4)
  and `usvote/mit/` (E5) — each with its own scrape/parse/transform/load stages.
- The **EC-flat / PV-nested asymmetry is deliberate**, not an oversight. A future reader
  should not "fix" it by nesting EC under `usvote/ec/`.

This resolves the architecture point raised by issue #17 / the E1-S2 skeleton. The
convention is also carried as a working note ("Source-namespacing convention") in
CLAUDE.md, added in PR #40; **this entry is the authoritative decision record** that the
CLAUDE.md note reflects.
**Rationale:**
- EC (National Archives) is the source-of-truth spine that both PV sources reconcile
  against (D006); keeping it flat at the top level reflects its primary/anchor status.
- The two PV sources have materially different ingestion shapes (clean MIT CSV vs. messy,
  era-drifting UCSB HTML, per D014), so each warrants its own namespaced subpackage rather
  than being flattened into one shared PV loader or colliding with EC module names.
- Recording the convention now prevents a retroactive restructuring of the EC modules once
  E4 lands, and gives E4/E5 an unambiguous home.

---

## D016: PV source determination finalized — MIT is CC0 (public-API-eligible); UCSB analysis-only

**Date:** 2026-07-13
**Context:** E3 (PV-source research, epic #13) was the task D008 named to resolve the final
PV source and confirm whether its license permits public-API redistribution — the gate
D002 leaves open. E3-S1 (#15) characterized MIT, E3-S2 (#16) UCSB / American Presidency
Project, and E3-S3 (#20) consolidated them into
[`research-pv-source.md`](research-pv-source.md). During consolidation the MIT license was
verified against the upstream Harvard Dataverse record (dataset `doi:10.7910/DVN/42MVDX`,
the source of Fred's `1976-2024-president.csv`): its license object is **CC0 1.0**
(`http://creativecommons.org/publicdomain/zero/1.0`) with **no custom terms of use
attached**. D008 had described MIT only as "open-licensed" and D014 still carried the
license question as an open, outreach-gated item.
**Decision:** Treat the PV source determination as **settled**:
- **MIT Election Lab (1976–2024) is licensed CC0 1.0** — a public-domain dedication.
  Redistribution, commercial use, and derivatives are permitted with no attribution or
  permission required, so the modern core is **cleared for public-API redistribution**.
  MIT rows carry `source=MIT`, `redistributable=true`.
- **UCSB / American Presidency Project remains analysis-only** — no data-specific reuse
  grant (UCSB Terms of Use prohibit redistribution without explicit permission via
  `policy@ucsb.edu`). UCSB rows carry `source=UCSB`, `redistributable=false` and are
  excluded from any public API surface.
- The **D002 public-API stretch goal is un-gated for 1976–2024** on the licensing axis; no
  outreach is required to ship the modern core publicly.
**Resolves D008's open action and closes the licensing question D014 deferred.** D014's
dual-source split stands unchanged; this entry records that the split's licensing basis is
now confirmed rather than pending. D008 remains the record of *why* MIT was preferred; D016
records that the preference is now backed by a verified CC0 license.
**Rationale:**
- CC0 is unambiguous and verified at the authoritative upstream (Dataverse license object),
  so the redistribution gate is settled on evidence, not on a hoped-for outreach reply.
- Keeping UCSB analysis-only is the safe, defensible default (its Terms of Use grant no
  reuse), and per-source `redistributable` flags (D014) already let the public surface
  filter cleanly to CC0 MIT rows.
**Action required:** None to unblock the API. MIT outreach is now **optional**, narrowed to
a single nice-to-have question — a possible **pre-1976 coverage extension** (which would let
more of the historical window ride on the redistributable source). Per epic #13 this stays
deferred until analysis back to at least 1976 is in hand.

---

## D017: PV source-overlap policy — MIT-preferred canonical series, UCSB the consistency control, both stored

**Date:** 2026-07-13
**Context:** MIT (1976–2024, CC0, redistributable — D016) and UCSB (physically 1789–2024,
analysis-only) both cover **1976–2024**, so the warehouse holds two PV values for the same
(year, state, candidate) across that overlap. D014 settled that both sources are stored and
tagged, but not which is authoritative where both exist — a question parked as an acceptance
criterion on the E6 union story (#68). The thesis is a **per-election** what-if (would this
election have flipped under PV/hybrid, and by how much), computed from each election's own
PV+EC; its headline outputs are normalized (flip booleans, margin percentages). The human's
steer: MIT is the definitive reference *where available* (it is the only API-exposed source,
for licensing reasons), but a **single-source UCSB series across all elections** should stay
available so a longitudinal comparison can be internally consistent. Reviewed with the
architect (see #68 comment) before recording.
**Decision:** Adopt a layered source-overlap policy. **This is subordinate to D006** — "MIT-
preferred" is a preference *among PV sources only*; the EC/National-Archives spine remains
the source of truth, and PV is joined onto it (EC on the left; missing PV surfaces as an
explicit gap, never a fabricated value — D005).

1. **Storage (unchanged from D014):** both sources' PV rows are stored and tagged `source`
   + `redistributable`; **the union keeps both rows always** (no dedup at load/union time —
   precedence is a read-time view concern, resolved in #68).
2. **Canonical/default analysis series — `pv_preferred`:** MIT wins wherever it exists
   (1976–2024); UCSB supplies everything earlier. Exactly one preferred PV value per
   (year, state, candidate), resolved by a documented precedence rank (`DISTINCT ON key
   ORDER BY precedence_rank`).
3. **Overlap (1976–2024) is a validation gate, not dual-truth:** where both sources exist,
   compare them. Close agreement is the **empirical justification that the pre-1976 UCSB
   methodology is comparable to MIT** — i.e. that the source seam at 1976 does not introduce
   a step. Disagreements beyond a tolerance are flagged with provenance (D005 reliability),
   not silently resolved. The magnitude of these discrepancies is measured by a dedicated
   research task (filed as #70) whose finding calibrates the tolerance and confirms or
   challenges the benign-seam assumption below.
4. **Public API surface — `pv_redistributable`:** exposes only `redistributable=true` rows →
   MIT → 1976–2024; pre-1976 PV is honestly absent from the public surface. This series is
   defined **independently** (`WHERE redistributable`), not as a filter over `pv_preferred`,
   so no future change to canonical resolution can leak a non-redistributable UCSB row onto
   the public API. It coincides with `pv_preferred` across the overlap by construction.
5. **UCSB single-source control — `pv_ucsb`:** the whole-span UCSB-only series stays fully
   queryable as the internally-consistent longitudinal lens. It is the **control** that lets
   us measure whether the 1976 seam matters — so the human's two desires (MIT-definitive
   *and* a consistent all-elections series) are served by one mechanism, not traded off.

**Benign-seam scope boundary (a load-bearing caveat, per the architect):** MIT-precedence is
safe for the analysis because a source change at 1976 does not bias the **normalized
per-election metrics** (flip booleans and margin %, where ratios cancel the source). It is
**not** automatically safe for (a) a raw national-PV-*count* series read across the seam, or
(b) a margin *trend* line, if the two sources differ in "other/write-in" handling or in the
total-votes denominator. Two mitigations are part of this decision: state the caveat
wherever a cross-seam longitudinal view is presented, and **pin the margin denominator to
each source's own provided state-total column** rather than re-summing candidate rows (which
would make margins sensitive to each source's minor-candidate coverage — D007 scopes
candidates to EC-getters, so re-summing would systematically differ between sources).

**Encoding (how this is materialized):** a small **`pv_source` reference table** carries
`source`, `precedence_rank`, `redistributable`, and license as the single source of truth for
these attributes (data, not code). Three **thin views** — `pv_preferred`, `pv_redistributable`,
`pv_ucsb` — express the three series over one union of the raw per-source rows. **No
materialized canonical table**; at this scale (low thousands of rows) plain views resolve in
milliseconds, and `CREATE MATERIALIZED VIEW` remains a one-line escape hatch if ever needed.
**Consequence for E6:** #68 (union) stacks-and-tags and keeps both rows; #69 joins the EC
spine to the **resolved single-row `pv_preferred`** (or `pv_redistributable` for the API path),
**not** the raw union — joining the raw union would fan the 1976–2024 overlap out 2× and
double-count downstream sums/margins. "Unified PV" is therefore two distinct objects (raw
tagged union vs. resolved preferred series); they are named apart to prevent that mistake.
**Rationale:**
- Precedence-as-data + a resolve-once view (options a+b combined) keeps the pick in exactly
  one place and avoids the drift of maintaining two materialized artifacts.
- A materialized "canonical PV" table was **rejected**: the API cannot read a canonical that
  mixes in pre-1976 UCSB rows, so it would force two materialized artifacts with duplicated,
  drift-prone resolution logic — all cost, no benefit at this scale.
- Defining `pv_redistributable` independently (not as a filter of `pv_preferred`) is the
  guardrail that keeps the D002/D016 licensing boundary structural rather than incidental.
- **Forward-compatible:** a UCSB redistribution grant becomes a one-row edit
  (`redistributable=true`) that auto-widens the public series; the ICPSR fallback (or any
  future source) drops in as one additional ranked row in `pv_source` without touching any
  view or join.
**Action required:**
- E6 #68 — resolve its parked AC to "keep both rows; add the `pv_source` reference table and
  the three views"; E6 #69 — join EC to `pv_preferred`/`pv_redistributable`, not the raw union.
- File the MIT-vs-UCSB overlap discrepancy research task (**#70**) that empirically tests the
  benign-seam assumption and calibrates the overlap tolerance (layer 3). It depends on E4
  (UCSB parsed to the overlap years) and E5 (MIT read) landing.

---

## D018: Shared PV record shape — the one schema both MIT and UCSB conform to

**Date:** 2026-07-15
**Context:** E5-S2 (#65) transforms MIT PV into "the shared PV record shape" — but that
shape is nominally owned by E4-S3 (#36, UCSB), and UCSB is unstarted (`src/usvote/ucsb/`
does not exist). The backlog anticipated this race (E4-S4 note, backlog-mvp.md:1025): whichever
PV source lands first **defines a minimal shared PV schema the other conforms to, flagged as a
shared-schema decision**. MIT is landing first, and MIT is the canonical/preferred PV source
(D016/D017) at the (year, state, candidate) fact grain already — so MIT is the right source to
*establish* the shape rather than retrofit onto a UCSB-first design. This decision fixes that
shape so #65 has a concrete target and #36/#38 (UCSB) later conform to it, not the reverse.

**Decision:** Adopt one **state-level, long-format PV record shape** — one row per
`(source, year, state, candidate)` — as the shared output contract of every PV source's
transform stage and the column contract of the shared PV target table. MIT (#65) and UCSB
(#36) both emit exactly these logical columns; sources differ only in *how* they populate
them, never in the shape.

**Logical columns (transform output):**

| Column | Type | MIT mapping | Notes |
|---|---|---|---|
| `year` | int | `year` | |
| `state` | str (canonical) | `state` (full name) | Canonical **state key** (full name, → EC `state` dim, D006). Populated MIT-native at #65; reconciled onto the canonical key at #67 (UCSB: #38). See FK-ordering note below. |
| `candidate` | str (canonical) | `candidate` | Canonical **candidate key**. Same reconcile-later contract as `state` (#67/#38). |
| `party` | str | `party_simplified` (main line) | **Descriptive-only, not the key.** For an aggregated fusion candidate (see grain note) the party is the **plurality line** — the `party_simplified` of the constituent row with the most `candidatevotes`. Party *authority* lives in the EC candidate dim (D006); this column is for validation/display and must not become a second source of party truth. `party_detailed` is MIT-only and **not** carried into the shape. |
| `candidate_votes` | int | `candidatevotes` | Popular votes for this candidate in this state, **summed across fusion lines** (see grain note). |
| `state_total_votes` | int | `totalvotes` | The **source's own** state-total denominator, carried verbatim. Pinning to the provided total (not re-summing candidate rows) is required by D017's benign-seam caveat — re-summing would make margins sensitive to each source's minor-candidate coverage, which D007 scopes differently. |
| `source` | str | literal `"MIT"` | Provenance (D014). `"MIT"` / `"UCSB"`. **The only provenance column stored in the fact** — `redistributable`/`precedence_rank`/license are derived by join to the `pv_source` reference table (D017), never stored per-row. |
| `reliability` | enum \| null | literal `"exact"` | D005/D014 reliability flag, constrained to `{exact, estimated, unreliable}` (CHECK / lookup, not a free string). Genuinely **per-row** — UCSB varies it by year/state — so it stays in the fact (unlike `redistributable`, which is per-source). MIT is a clean modern release → `"exact"`. Column exists in the shape **now** so UCSB needs no ALTER later. |

**Grain & natural key:** exactly one row per `(source, year, state, candidate)`. `source` is
part of the key because the union deliberately keeps both sources' rows (D017 — no dedup at
load); precedence between sources is a read-time view concern (`pv_preferred` etc., D017), never
a transform/load-time drop. Grain uniqueness is a tested validation (mirroring the EC transform
intent, E2-S3).

**Fusion-line aggregation (load-bearing — the raw MIT CSV is *not* at this grain).** MIT lists a
candidate on multiple party lines in fusion-voting states as **separate rows** (e.g. 2016 NY:
three `CLINTON, HILLARY` rows across Democratic / Working Families / Women's Equality; two
`TRUMP, DONALD J.` rows), while other year/states are pre-aggregated (2020 NY Biden is one row).
D007's EC-getter filter does **not** collapse these — the fusion cases *are* the major
candidates. Transform therefore **sums `candidatevotes` to one row per (year, state, candidate)
before** the grain assertion, taking `party` from the plurality line and `state_total_votes`
verbatim (it is already the all-lines state total). Skipping this makes the grain assertion fail
and, worse, silently corrupts D017's `pv_preferred` `DISTINCT ON (year,state,candidate)` —
which would keep one fusion line and **undercount a major candidate**. This is a tested
validation, not a comment.

**What is deliberately *not* in the shape:**
- **No stored `redistributable` column.** It is per-*source* (license), so it lives once in the
  `pv_source` reference table (D017) and is surfaced by join — never duplicated per fact row. This
  is what keeps "a UCSB redistribution grant is a one-row edit" true (D017). The transform frame
  *may* carry a literal `redistributable` for self-documentation, but the persistent target table
  does not store it.
- **No surrogate `pv_id` and no FK enforcement at transform** — those are added at the load seam
  (#66/#37), not by transform, exactly as EC assigns `votes_id` at load. Transform emits a logical
  frame. **FK ordering:** because #65 emits MIT-native `state`/`candidate` strings that do not yet
  match the EC dims, FK enforcement to `state`/`candidate` must **follow** reconciliation (#67) —
  or the first load lands FK-deferred. Adding FKs before #67 would reject or silently drop every
  unreconciled row (the inner-join silent-drop hazard).
- **No aggregate/total rows.** Unlike the EC `votes` table's `is_total` rows, PV state totals ride
  as the `state_total_votes` *column*; national totals are derived downstream, not stored.
- **No `writein` column.** D007 scopes candidates to EC-getters, which drops MIT's write-in long
  tail (up to 167 names in 2024) at transform; the survivors are non-write-in, so the flag is
  vacuous. (The filter itself is applied and tested in #65 via `writein` + `party_simplified`.)
- **No fabricated gap rows.** Where a source lacks a (year, state, candidate) value it is an
  **absent row**, never a zero-filled placeholder (D005).

**Rationale:**
- **Long format, not wide** mirrors the EC `votes` fact (melted, one row per candidate/state) so
  PV joins onto the EC spine at a matching grain (D006) with no reshape at join time.
- **`source` in the key** is what makes D017's "keep both rows, resolve at read-time" policy
  expressible — a shape keyed only on (year, state, candidate) could not hold the 1976–2024
  MIT/UCSB overlap without a lossy dedup the union explicitly forbids.
- **`reliability` present from day one** avoids an ALTER/backfill when UCSB lands; MIT simply
  pins it to `"exact"`. Same forward-compat logic as the source-derived `redistributable`.
- **Canonical keys are the target, reconciliation is a later story** — #65 legitimately emits
  MIT-native `state`/`candidate` strings and #67 maps them, so this decision names the *columns*
  as canonical without forcing #65 to also own reconciliation (keeps the stories separable, as
  the backlog sequences them).
- **Transform emits a logical frame; load owns keys/FKs/NaN→None** keeps the single write
  chokepoint (`usvote.db.insert_df_into_table`) authoritative and matches how EC is layered.

**Action required:**
- #65 (MIT transform) targets this exact column set; **fusion-line aggregation runs before** the
  grain assertion; grain + totals-reconciliation validations become tested functions; 2000 & 2016
  covered.
- **Totals reconciliation is `<=`, not `==`, post-filter.** After the D007 EC-getter filter,
  `sum(candidate_votes) <= state_total_votes` is expected (the dropped minor candidates are the
  residual); equality would spuriously fail. Best practice: assert *full* reconciliation on the
  **pre-filter** frame (catches read/parse regressions), then `<=` on the filtered frame.
- #36/#38 (UCSB) **conform** to this shape when E4 is scoped — populating `source="UCSB"` and real
  `reliability` values — rather than defining a rival shape. `redistributable=false` for UCSB is a
  `pv_source` row, not a fact column.
- The shared PV **target table** (#66/#37) is these columns (`source` + `reliability`, **not**
  `redistributable`) + a surrogate PK; FKs to the EC `state`/`candidate` dims are added only once
  reconciliation (#67) lands (or the load is FK-deferred until then). `redistributable`,
  `precedence_rank`, and license come from the `pv_source` reference table by join (D017). DDL is
  finalized at the first load story, consistent with this shape. **Finalized in #66 — see D021.**

---

## D019: MIT D007 candidate-scope proxy — `party_simplified ∈ {DEMOCRAT, REPUBLICAN}`

**Date:** 2026-07-15
**Context:** D007 scopes the MVP to "candidates who received electoral votes," and D018 fixed the
*mechanism* of the MIT filter (`writein` + `party_simplified`) but left the *value set* open. MIT
carries **no electoral-vote data**, so the true EC-getter set is not computable inside the pure
MIT transform (#65). A value set must be chosen without coupling MIT transform to the EC spine.
**Context surfaced by architect review of the #65 implementation plan.**
**Decision:** The MIT transform (#65) keeps rows where `writein == False` **and** the candidate's
(fusion-aggregated) `party_simplified` is in **`{DEMOCRAT, REPUBLICAN}`**. This is a deliberate
*proxy* for D007's "received electoral votes," valid because across 1976–2024 **every electoral
vote went to a Democratic or Republican nominee**, so the two-value party filter is effectively
exact for this window — offline, with zero maintenance. Two known, deliberate deviations:
- **Libertarian/Green PV candidates are excluded.** None received an electoral vote in 1976–2024,
  so including them would both violate D007 and manufacture PV rows with no EC counterpart that
  #67/E6's inner-join would drop silently (the inner-join silent-drop hazard).
- **Faithless-elector EC recipients are deferred to #67** (e.g. 2016 Powell / Faith Spotted Eagle
  / Kasich / Paul / Sanders; 1988 Bentsen; 2004 Edwards). They are immaterial to state
  sums/margins, and the *exact* EC-getter set becomes joinable at reconciliation (#67 / D006)
  where canonical keys exist.
**Rationale:**
- `{DEMOCRAT, REPUBLICAN}` dominates a hand-curated per-year allow-list (exact but maintained for
  no MVP gain) and injecting the EC-getter set from the spine (correct, but that coupling is the
  #67 answer, not #65's). D018 already defers candidate *identity* to #67; this keeps #65's scope
  to "select + type + filter + validate."
- The filter runs on the **fusion-aggregated** frame (party = the plurality line), so a fusion
  candidate is judged by their main party, never a secondary `OTHER`-coded line — see D018's
  fusion-aggregation note.
- Encoded as a named, provenance-carrying constant in `usvote/mit/transform.py`, mirroring the EC
  correction-constant pattern, and locked by a test.
**Action required:**
- #65 implements the `{DEMOCRAT, REPUBLICAN}` constant + filter; #67 supersedes the proxy with the
  exact EC-getter set once canonical keys land, at which point the faithless-elector deferral is
  revisited.

---

## D020: MIT name reconciliation — curated maps producing canonical *values*, in a separate offline stage

**Date:** 2026-07-15
**Context:** E5-S4 (#67) reconciles MIT's native `state`/`candidate` strings (left MIT-native by
#65, D018) onto the canonical keys the EC spine defines (D006, #30) — the MIT analogue of the
UCSB reconciliation (#38). Three mechanism choices were open and settled with the user +
architect review before coding: (a) how candidate names map, (b) what the reconciliation targets,
(c) where the stage runs. MIT prints `"LAST, FIRST M. SUFFIX"`; the EC canonical `name` is not a
mechanical transform of it — across 1976–2024 the reconciliation *drops* MIT's middle initial for
some nominees (`OBAMA, BARACK H.` → `Barack Obama`; `BUSH, GEORGE H.W.` → `George Bush`) and
*adds* one for others (`FORD, GERALD` → `Gerald R. Ford`; `MONDALE, WALTER` → `Walter F. Mondale`),
plus given-name substitutions (`CLINTON, BILL` → `William J. Clinton`; `GORE, AL` →
`Albert Gore Jr.`). RHS names were derived from the National Archives Table 1 per year (+ the
`Bob Dole` → `Robert Dole` EC correction), LHS from the distinct `candidate` values `transform_mit`
emits on the real file — both enumerated, not guessed.

**Decision:** Reconcile via **curated, provenance-carrying lookup maps** in a **separate offline
reconcile stage** (`src/usvote/mit/reconcile.py`, `reconcile_mit`) that produces the canonical
**values** directly:
1. **Curated maps, not a parser.** `MIT_STATE_RECONCILIATIONS` (51 jurisdictions) and
   `MIT_CANDIDATE_RECONCILIATIONS` (18 D/R nominees, bounded by D019). Each value is the whole
   canonical string — no token-level nickname/middle-initial logic — mirroring the EC
   `CANDIDATE_NAME_FIXES` catalog. The map is keyed on the MIT string and is **many-to-one safe**
   (multiple MIT spellings of one person → the same canonical name); the inverse (one MIT string →
   two people) does not occur and is assumed not to (per D006 each EC candidate has a single
   canonical name across all years; a violation would be an upstream EC-transform bug).
2. **Static canonical values, not a live join.** Reconcile emits only the **display keys**
   (`name`, full `state` name) deterministically; it does **not** join against the live EC dims,
   so the stage is pure/offline (no DB, shapefile, network). The EC "match target" columns
   (name-parts, `state_usps`) exist to absorb *format* variance the maps have already removed, so
   E6/#69 joins on the display key directly. **#69 owns the reciprocal guard** — that every
   reconciled MIT name/state is present in the EC dims (the offline map only pins RHS in a test).
3. **State map on the ALLCAPS name, not `state_po`.** D018's shape drops `state_po`, and the full
   state name is documented stable/unambiguous, so the map keys the ALLCAPS name (the AC also
   names `state_po`; we deviate deliberately, documented in `reconcile.py`). `.title()` is *not*
   used — DC's lowercase "of" needs the explicit entry.
4. **Separate stage, not folded into `transform_mit`.** `transform_mit` validates MIT-internal
   correctness (totals, scope); reconcile validates cross-source conformance to the EC spine — a
   different concern with a different authority (SRP; matches the per-source read/transform seams,
   D015).

**Validation (each raises `MITReconcileError`):** full state + candidate coverage (unmapped value
→ raise, the inner-join silent-drop guard); unique `(year, state, candidate)` grain re-asserted
*after* the rewrite (catches two MIT strings collapsing onto one canonical name); D018 shape +
row-count preserved. The two-Bushes non-collision (`George Bush` ≠ `George W. Bush`) and the pinned
RHS values are locked by tests in `tests/unit/test_mit_reconcile.py`.

**Rationale:**
- The reconciliation is genuinely non-mechanical (middles dropped *and* added, given-name
  substitutions), so a parser would need per-name overrides for most nominees anyway — a curated
  map is simpler and fully auditable at this scale (18 nominees, 51 states).
- Emitting canonical *values* offline keeps #67 free of the DB/shapefile/network that a live join
  would drag in, and keeps the D002/D016 licensing boundary and the join itself as #69's concern.
- **Supersedes D019's proxy question narrowly:** the D019 `{DEMOCRAT, REPUBLICAN}` scope already
  yields exactly the 18 EC-getter nominees for 1976–2024, so #67 confirms rather than replaces the
  proxy; no faithless-elector recipient appears in MIT's D/R-scoped PV rows, so that D019 deferral
  is discharged as "out of scope for MIT PV" rather than acted on.

**Action required:**
- #69 (E6 join) must carry the reciprocal guard: assert every reconciled MIT `name`/`state` is
  present in the EC candidate/state dims (fail loud, not an inner-join silent drop).
- The EC transform has no *general* guard against a future un-`FIXED` cross-year name split (one
  person printed two ways in different years → two silent candidate rows); the known case (Trump)
  is handled by `CANDIDATE_NAME_FIXES` and tested. A general invariant check belongs with the EC
  coverage-extension work (#32), not #67 — flagged here so it is not lost.

---

## D021: Shared PV target table DDL finalized — `dwh.pv_votes` (state-FK-only, no candidate FK)

**Date:** 2026-07-16
**Context:** D018 fixed the shared PV *record shape* and left one action open: "DDL is finalized
at the first load story." MIT is the first PV source to load (it is the canonical/preferred source
per D016/D017), so **#66 (E5-S3, PR #75)** is that story — it created the shared, source-neutral
PV fact table and loaded MIT into it. This entry records the DDL that shipped, so a future reader
knows the concrete table — its name, exact column order, types, and constraints — without
reverse-engineering it from the loader. Architect-reviewed before merge.

**Decision:** The shared, source-neutral PV fact table is **`dwh.pv_votes`** — named to parallel
the EC `votes` fact, and kept deliberately distinct from D017's resolved-series **view** names
(`pv_preferred` / `pv_redistributable` / `pv_ucsb`) and the `pv_source` reference table. Columns,
in DDL order:

| # | Column | Type | Constraint |
|---|---|---|---|
| 1 | `pv_id` | integer | surrogate **PK**, assigned at load |
| 2 | `source` | varchar | NOT NULL |
| 3 | `year` | smallint | NOT NULL |
| 4 | `state` | varchar | `REFERENCES dwh.state` (state-FK) |
| 5 | `candidate` | varchar | **no FK** |
| 6 | `party` | varchar | nullable |
| 7 | `candidate_votes` | integer | NOT NULL |
| 8 | `state_total_votes` | integer | NOT NULL |
| 9 | `reliability` | varchar | `CHECK (reliability IN ('exact','estimated','unreliable'))`, nullable |

Table constraint: **`UNIQUE (source, year, state, candidate)`** — the D018 natural key.

**Key design calls (architect-reviewed):**
- **State-FK-only, no candidate FK.** The EC `candidate` PK is `candidate_id`, not the `name`
  string this shape carries — so a PV→EC candidate FK cannot target this column, and a PV FK onto
  the EC candidate dim would **invert the D006 spine dependency** (EC is the source of truth PV
  joins *onto*, not the reverse). Candidate referential integrity is instead guarded **offline at
  reconcile (#67)** and **at the EC↔PV join seam (#69)** — not by a DDL constraint.
- **`state`/`candidate`/`party`/`reliability` left nullable in the DDL** for UCSB forward-compat;
  the shared loader's `assert_pv_shape` enforces NON-NULL on the natural-key + vote columns for the
  frame actually being loaded. Nullable-in-DDL + asserted-at-load lets one physical table serve
  both MIT's strict rows and UCSB's looser rows without an ALTER later.
- **No `redistributable` column** — it is per-*source* (license), so it lives once in the
  `pv_source` reference table (D017) and is surfaced by join, never duplicated per fact row. #66
  deferred `pv_source` itself to **E6 / #68** (per D017); `dwh.pv_votes` carries `source` only.

**Rationale:**
- Recording the concrete DDL closes D018's "finalized at the first load story" action and gives
  #37 (UCSB) an exact conformance target rather than a shape description.
- The nullable-DDL + `assert_pv_shape` split is what lets a single table serve both sources; the
  no-candidate-FK call is what keeps D006's spine direction structural rather than incidental.

**Action required:**
- **#37 (UCSB load) conforms to `dwh.pv_votes` as-shipped** — same columns/types/constraints,
  populating `source="UCSB"` and real `reliability` values; it does **not** redefine the table.
- **#68 (E6)** adds the `pv_source` reference table + the three D017 views over `dwh.pv_votes`;
  `redistributable` (incl. MIT's `redistributable=true`) is surfaced there by join, not on the fact.

---

## D022: UCSB parser fixtures are synthetic, not real snapshots — amends E4-S1 (#34) AC3

**Date:** 2026-07-17
**Context:** E4-S1 (#34) carries an acceptance criterion — written 2026-07-06, before the
D014/D016 licensing posture hardened — requiring that "at least a few representative year
snapshots (spanning different eras) are saved into `tests/fixtures/`" to seed the UCSB parser
tests (E4-S2 / #35). That AC is now in **direct conflict with D014/D016**: this repository is
**public**, and UCSB / American Presidency Project content is `redistributable=false` (UCSB Terms
of Use grant no reuse; redistribution requires explicit permission via `policy@ucsb.edu` —
research-pv-source.md §3). **Committing UCSB HTML to a public repo *is* redistribution**, and the
act is effectively **irreversible** — once pushed, the bytes persist in forks, clones, git
history, and third-party caches beyond our control. The AC and the licensing decision cannot both
be honored as written.

The raw snapshot itself already exists in full — **all 60 elections 1789–2024, every one HTTP
200**, fetched 2026-07-06 — at `~/Documents/Projects/data/presidential_vote_analysis/ucsb_raw/`,
**outside the repo and untracked by git** (research-pv-source.md §5). So the question at issue is
only **what ships into `tests/fixtures/`**, never whether the parser has real data to be
developed against.

**Decision:** UCSB parser fixtures are **hand-written synthetic HTML** that mimics the real UCSB
table structure with **fabricated vote numbers**. **No UCSB-sourced bytes are committed to this
repository.** The real snapshot stays where it is — external, untracked, analysis-only — and
remains the artifact each fixture is *derived from* by close reading, never by copy.

Each synthetic fixture is **annotated with the real source year it mimics** (e.g. "structure
mimics 1824; vote values are fabricated") so the derivation stays auditable. Between them the
fixtures must pin every structural case #35 must handle (research-pv-source.md §5):
- **Wide-not-long layout** — candidates in columns; the melt to per-(year, state, candidate) records.
- **`colspan`/`rowspan` multi-row headers**, with the **candidate-group count drifting by era**
  (2 groups in 1876, 4 in 1824) — forcing generic header parsing, never fixed column indices.
- **Legislature-chosen-elector states with no PV** (1824: Delaware, Georgia, Louisiana, New York,
  South Carolina, Vermont) — which must be **flagged with provenance, never coerced to zero** (D005).
- **Footnote/annotation rows at table bottom** (e.g. 1824's "elected by the House of
  Representatives") — which must not be mistaken for data rows.

**This decision amends E4-S1's AC3** (issue #34 and its `backlog-mvp.md` entry): "representative
year snapshots saved into `tests/fixtures/`" is **replaced by** "synthetic era-spanning fixtures
saved into `tests/fixtures/`." The original AC is recorded as **amended, not silently dropped** —
as written it would have required shipping non-redistributable content.

**Options weighed:**
1. **Commit small excerpts of the real HTML** — reduces the *volume* redistributed but not the
   *fact* of it; the licensing question is unchanged by size. **Rejected.**
2. **Hand-written synthetic fixtures** — no UCSB content ships; parser tests still pin every
   structural case; runs in CI. **Chosen.**
3. **Keep fixtures external + env-var-gate the parser tests** — uses real data, but the parser
   tests cannot then run in CI, which is most of the point of having them. **Rejected.**

**Rationale:**
- **The parser cares about structural shape, not vote values.** #35's job is to survive
  `colspan`/`rowspan` header drift, melt a wide table, and distinguish footnote rows and no-PV
  states from data. Every one of those cases is expressible with fabricated numbers, so real UCSB
  values buy the tests nothing they cannot get synthetically.
- **Keeps the parser tests in CI** — unlike option 3, which would leave CI blind to exactly the
  era-drift regressions that make #35 the highest-risk story in the epic.
- **Keeps the public repo free of non-redistributable content** — unlike options 1 and 3, which
  either ship UCSB bytes or accept a blind CI. Since pushing is irreversible, the conservative
  option is the only reversible one.
- Consistent with D014/D016 treating redistributability as a **first-class per-source attribute**:
  UCSB is usable for analysis *and* undistributable, and those are separable — the fixtures are
  where that separation becomes structural rather than incidental.

**Known tradeoff (and its mitigation):** synthetic fixtures can **drift from real UCSB quirks** —
a structure we invent may be subtly cleaner than the one the site actually serves, so a green test
suite could coexist with a parser that fails on the real snapshot. Mitigations: (a) derive each
fixture from **close reading of the real snapshot**, not from imagination; (b) **annotate the real
source year** each fixture mimics, so the derivation is re-checkable; (c) treat a parse run over
the **full external 60-year snapshot** as an acceptance check for #35 that the fixtures alone
cannot provide.

**Action required:**
- **#34** — AC3 amended per this entry; the remaining fixture work is *synthetic* era-spanning
  fixtures, not real snapshots. The `backlog-mvp.md` E4-S1 entry is updated to match.
- **#35 (UCSB parse)** — its "one page per distinct era format, against saved fixtures" AC reads
  as *synthetic* fixtures; the real 60-year external snapshot remains the development corpus and
  acceptance check.
- **No UCSB HTML is ever committed** to this repository while `redistributable=false` stands.
  Should UCSB ever grant permission (D017 notes this is a one-row `pv_source` edit for *data*),
  this fixture decision may be revisited — though the synthetic fixtures would remain adequate
  regardless.

---

## D023: Port the UCSB snapshot script into the package — code comes in, data stays out

**Date:** 2026-07-17
**Context:** The UCSB HTML snapshot E4-S1 (#34) asks for **already exists in full** — all 60
elections 1789–2024, every one HTTP 200, fetched 2026-07-06 — produced by a self-contained,
stdlib-only script, `_snapshot_ucsb.py`, whose own docstring names "backlog #34 (E4-S1)". Both
the snapshot **and the script** live at
`~/Documents/Projects/data/presidential_vote_analysis/ucsb_raw/` — **outside the repo and
untracked by git**. D022 settled what ships into `tests/fixtures/` (synthetic HTML, no UCSB
bytes) but not what happens to the **scrape code**: `src/usvote/ucsb/` does not exist, and the
script is neither importable as `usvote.*` nor under version control. The port rationale existed
only in #34's Implementation Notes; this entry promotes it to a decision of record.

**Decision:** **Port `_snapshot_ucsb.py` into the package** at `src/usvote/ucsb/scrape.py`, per
D015's sibling-subpackage namespacing (each PV source is its own subpackage; EC stays flat).

**Port, don't rewrite.** The script's robots-compliant behavior is preserved **exactly**, not
reimplemented:
- honors the site's **`Crawl-delay: 10`**
- identifies truthfully as **`us-presidential-vote-analysis-research/0.1 (personal academic
  research)`** — matching `User-agent: *`, explicitly **not** ClaudeBot
- enumerates year URLs by **regexing the already-saved index** (no extra network hit)
- **skip-if-already-have**
- **halts immediately on 403/429**
- writes the per-year **sha256 `manifest.json`**

These politeness behaviors are precisely what a from-scratch reimplementation would lose, and
their loss is **invisible until the site blocks us** — by which point the damage (to the
project's access and to a public archive's goodwill) is already done. A rewrite would be judged
green by any test that only checks "did we get the HTML."

**The snapshot DATA stays outside the repo.** Only the *code* comes in. UCSB is
`redistributable=false` (D014/D016) and this repo is public, so committing the HTML is
redistribution (D022's reasoning applies unchanged to the snapshot itself, not just to fixtures).
The resulting **asymmetry is deliberate and worth naming**: the data is knowingly left
**un-backed-up by git**, and it is safely re-fetchable **precisely because the script is in git**.
The script in version control is what makes the data's absence from version control an acceptable
risk rather than a single point of failure.

**The snapshot directory path is resolved from the env var `USVOTE_UCSB_HTML_DIR`** rather than
the script's hard-coded `os.path.expanduser(...)`. The name follows the established sibling
config convention — `USVOTE_MIT_CSV_PATH` and `USVOTE_SHAPEFILE_PATH` both name **format + role**,
so `USVOTE_UCSB_HTML_DIR` is exactly parallel; a `..._SNAPSHOT_DIR` variant would name role only
and break the pattern. Unset / empty / nonexistent raises the typed `ConfigError`, as the sibling
config modules do.

**Rationale:**
- **Reproducibility is the D003 star.** The 2028 refresh must regenerate the snapshot by running
  a versioned, tested module — not by hunting for a loose script on one machine. A pipeline whose
  ingestion step exists only as untracked local code is not reproducible in any meaningful sense.
- **The means to re-fetch was as fragile as the data.** The snapshot has no backup and exists on
  exactly one disk; before this port, so did the *only* copy of the fetch logic. Porting the code
  removes the worse half of that risk — losing the data costs a polite re-scrape, whereas losing
  the script costs re-deriving the URL enumeration, the politeness rules, and the manifest format
  from scratch.
- **It creates the `usvote/ucsb/` namespace that #35–#38 all need**, so it is the natural first
  story of the epic regardless of the snapshot's existence.

**Counter-argument (recorded honestly):** the snapshot is **one-and-done for historical data** —
1789–2024 does not change — so a re-scraper earns its keep only about **every four years**. That
is a real argument against porting. It loses anyway because the cost is **~70 lines of
already-written code** (a port, not a build), while the downside case — losing the only copy of
the fetch logic — is **silent until it matters**, and matters at exactly the moment (a refresh
deadline) when re-deriving it is most expensive.

**Related:** **D022** (its sibling — that entry governs *fixtures*, this one governs *code*; both
land on "no UCSB bytes in the repo"); **D015** (the `usvote/ucsb/` namespacing this port obeys);
**D003** (the reproducibility star it serves); **D014**/**D016** (why the data stays out).

**Action required:**
- **#34** — the port is scoped as remaining-work item (a), with the robots-compliant behaviors
  enumerated as ACs so a reviewer can check each one survived the port; env var is
  `USVOTE_UCSB_HTML_DIR`; unit tests cover URL enumeration, manifest shape + sha256,
  skip-if-already-have, the 403/429 halt, and config resolution — **against injected fakes, no
  live network in CI** (a test run must never re-fetch the snapshot).
- **No UCSB HTML is committed** by this port (D022) — only the code that can re-fetch it.

---

## D024: PV absence is modeled at its own grain — a `pv_state_status` roster, never a null vote

**Date:** 2026-07-18
**Context:** A survey of all 60 real UCSB year pages (see
[`docs/ucsb-html-formats.md`](../../docs/ucsb-html-formats.md)) established that **no year fails
to parse**. E4-S2's acceptance criterion "era-specific format variations are handled (or
explicitly flagged where a year cannot be parsed cleanly)" was written expecting year-level parse
failures; there are none. What actually needs flagging is **popular-vote absence at the record
level**, in four structurally distinct cases:

1. **State chose electors by legislature** — no popular vote was ever held. 18 rows across 12
   years (1824 DE/GA/LA/NY/SC/VT; 1828 DE/SC; 1832–1860 SC each cycle; 1868 FL; 1876 CO). Markup
   is a 2-cell row whose second cell has `colspan = width-1`, carrying verbatim prose such as
   *"3 electors chosen by state legislature and awarded to Rutherford B. Hayes"* or, for 1824
   New York, *"…: 2 for Crawford; 1 for Adams"* — i.e. the prose sometimes records a **split
   elector allocation**.
2. **State did not participate at all** — the row is simply **absent, with no markup whatsoever**.
   1864 (11 Confederate states), 1868 (3 states). Only a prose footnote elsewhere on the page
   attests to it.
3. **Candidate not on that state's ballot, pre-1852** — the Votes cell is a lone `U+00A0`.
4. **Candidate not on that state's ballot, 1852+** — the Votes cell is `--`.

Crucially: **a literal `0` never appears in a state-row vote column anywhere in the corpus.**
"Zero popular votes" is never encoded, so absence must never be modeled as zero.

Two prior decisions constrain the answer. **D021** shipped `dwh.pv_votes` with
`candidate_votes`/`state_total_votes` **NOT NULL**, enforced for *every* source by
`usvote.pv.schema.REQUIRED_NON_NULL`; and its action item states that UCSB (#37) **conforms to the
table as-shipped and does not redefine it**. **D018** already settled that a source lacking a
(year, state, candidate) value yields an **absent row, never a zero-filled placeholder**.

**Decision:** Model PV absence **at the grain at which each case actually occurs**, adding a
sibling table rather than amending the shared PV fact.

1. **`dwh.pv_votes` is untouched.** No `ALTER`, no nullable `candidate_votes`, no weakened
   `assert_pv_shape`. The "null vote + reason enum" design is **rejected**: it would relax a
   shipped constraint for both sources to describe a UCSB-only phenomenon, and it denormalizes a
   (year, state) fact onto N candidate rows with nothing keeping the copies consistent.
2. **Cases 3–4 produce no row**, per D018's existing absent-row policy. Both the pre-1852 `U+00A0`
   and the 1852+ `--` normalize to one internal parser sentinel — the era difference is a parsing
   detail, not a data attribute.
3. **Cases 1–2 land in a new sibling table `dwh.pv_state_status`**, grain `(source, year, state)`,
   with columns `pv_status` (CHECK-constrained), `note` (nullable text), and `source`. It is a
   **complete roster — one row per state in that year's election, including ordinary ones** — not
   an exceptions table. This is what makes absence detectable at all: an exceptions-only table
   cannot distinguish "no exception" from "we never looked."
4. **`pv_status` has exactly three values:** **`popular_vote`** (held and recorded in `pv_votes`),
   **`legislature_chosen`** (case 1), **`not_participating`** (case 2). Deliberately absent: any
   value for cases 3–4 (they are one fact, not two); a secession/unreconstructed split (the enum
   encodes the data-modeling consequence, not the historical cause — cause goes in `note`); and
   any `unknown`/`unparsed` bucket — **anything the parser cannot classify raises**, because an
   `unknown` slot is where parse failures go to die quietly.
5. **The verbatim legislature prose is preserved unparsed** in `note`. Elector counts and the 1824
   NY split allocation are **not** extracted into structured columns: doing so would create a
   **second source of electoral-vote truth**, contrary to D006 — the same ruling D018 made for
   `party` ("must not become a second source of party truth"). Nothing is lost, because the EC
   `votes` fact already carries per-state per-candidate electoral votes from the authoritative
   source. Only the **structural** cross-check is automated (every `legislature_chosen`
   (year, state) has ≥1 EC `votes` row); textual name-matching against the prose is a one-time
   manual audit recorded in `docs/`, not a test.
6. **The roster is assembled from the EC spine plus a named constant — never from UCSB markup.**
   The participating-state roster for year Y is the distinct states in the EC `votes` fact (D006
   makes EC authoritative on participation; costs no new reference data). Case 2 comes from
   `UCSB_NONPARTICIPATING_STATES` in `usvote/ucsb/transform.py` — 14 entries, each with its cause
   — following the established anomaly pattern (constant + test + `docs/corrections.md` row). A
   general statehood-admission roster is **rejected**: it needs reference data the repo lacks (the
   `state` dim is TIGER geography, no admission dates) for a set that is **historically closed**
   and can never grow.
   - *Clarified 2026-07-18 during the #36 architect review (scope refinement; no part of this
     decision reverses).* §6 assumed the EC spine covers every year UCSB publishes PV for. It does
     not: `UNSUPPORTED_EC_YEARS` (`pipeline.py:53`) gates 1868 and 1872, for which UCSB *does*
     publish PV. **UCSB ingestion is therefore scoped to the EC spine** — `ec_ingest_years()` minus
     `NO_POPULAR_VOTE_YEARS` — **derived at runtime, never duplicated as a literal year set in
     `usvote/ucsb/`**, so #57 lifting the gate admits both years to E4 with no change in
     `usvote/ucsb/`. A roster that comes back empty for an in-scope year **raises**. Rationale:
     `pv_coverage` (§8) is EV-weighted and therefore uncomputable without an EC spine for the year,
     so ingesting 1868/1872 would create exactly the partial-coverage years D009 mandates a caveat
     for, with no means to quantify one. This **defers, not hides**: the gating is expected to be
     temporary (#57 is tracked, deprioritized behind bulk-ingest and the API, and non-trivial),
     `UCSB_NONPARTICIPATING_STATES` retains all 14 entries including 1868's three, and
     `docs/corrections.md` records that the 1868 rows are catalogued but not yet ingested.
   - *Also clarified:* the participating-state roster derives from `dwh.votes` **with totals rows
     excluded** (`is_total = false` / `state IS NOT NULL`) — `votes.state` is NULL on totals rows,
     so a naive `SELECT DISTINCT year, state` yields a NULL roster entry per year. The same filter
     applies to E6's MIT roster backfill, which §Rationale describes as a mechanical
     `INSERT … SELECT DISTINCT`.
   - *Clarified 2026-07-19 during #36 implementation (the design is unchanged; its stated
     justification was wrong).* §6 above says the roster is the EC spine "**plus**"
     `UCSB_NONPARTICIPATING_STATES`, implying a non-participating state is *missing* from the spine
     and the constant supplies its row. Measured against the real spine, it is not: the Archives
     Table 2 carries rows for non-participating states with **`total_electoral_votes = 0`**, so
     `dwh.votes` already yields the *complete* roster (1864: 36 states, against UCSB's 25 popular-
     vote rows). **The constant therefore supplies the `pv_status`, not the roster row**, and the
     union is retained as belt-and-braces rather than as the mechanism. This matters because a
     future reader who measures the same thing has a live incentive to delete the constant from
     roster assembly as dead code — which would silently lose the status assignment, leaving 1864's
     eleven states classified `popular_vote` with zero facts.
   - *Consequently, a structural cross-check is available and is now enforced* (§7-adjacent, the
     generalization of §5's "every `legislature_chosen` (year, state) has ≥1 EC `votes` row"):
     **(a)** every in-scope `UCSB_NONPARTICIPATING_STATES` entry must have
     `total_electoral_votes = 0` in the spine, validating the constant against the authority; and
     **(b)** no zero-EV roster state may be classified `popular_vote`. Verified exact corpus-wide —
     the zero-EV roster states are precisely 1864's eleven, in every in-scope year, with no false
     positives. (b) deliberately couples E4 to the Archives' rendering: a silent change in how
     non-participating states are rendered would corrupt the roster invisibly, and surfacing that is
     the roster's entire purpose, so its error message says plainly that the cause is an EC-spine
     change rather than a UCSB one. **Do not "optimize" the roster by filtering to
     `total_electoral_votes > 0`** — that drops exactly the states this design exists to represent.
     For **#57**: whatever spine it builds for 1868 must render that year's three non-participating
     states as zero-EV rows, or check (a) will fire.
7. **The silent-drop guard is a two-way tested assert**, and is the roster's primary purpose:
   every `popular_vote` roster state has **≥1** `pv_votes` row; every absence-status state has
   **exactly 0**; and every `pv_votes` (year, state) is **in** the roster. The third check is what
   catches a phantom or dropped state that a sum validator cannot see. A **within-page** guard
   complements it: per (year, state), `numeric_cells + not_on_ballot_cells ==
   candidate_column_count` with **no residual**.
8. **`pv_coverage`** — the share of a year's **electoral votes** cast by `popular_vote` states —
   is the honest qualifier on partial-coverage years (see the D009 note below). Weighted by
   electoral votes, not state count, because EV is the analytically relevant weight and is already
   loaded.

**Licensing consequence (extends D022/D016):** the `note` column holds **verbatim UCSB text** and
is therefore `redistributable=false` content — it must be excluded from any public API surface and
must never appear in a committed fixture. The `pv_status` enum is a bare historical fact and
carries no such restriction. Same distinction D022 drew for fixtures, surfacing in a new place.

**Consequence for D009 (strengthens, does not change):** the ~1824 comparison start **stands**. For
a legislature-chosen state the national PV is **not an incomplete measurement of the national
electorate — it is a complete measurement of a smaller one**; those voters never voted, so there
is no missing value to impute and any "adjusted" national PV would be fabrication (D005).
Partial-coverage years therefore remain usable in an EC-vs-PV comparison, reported as *"PV among
states that held one"*, with `pv_coverage` surfaced and a **mandatory caveat wherever a year with
`pv_coverage < 100%` is displayed**. **No exclusion threshold** is set — an arbitrary cutoff would
hide exactly the years the project exists to illuminate. This is grounds to move D009 from
"mutually-agreed pending" toward settled: D009 named E3/E4's data work as the confirmation point,
and that work has now confirmed it *with a mechanism attached*.

**Rationale:**
- **Grain drives structure.** Cases 1–2 assert "this election had no popular-vote event in this
  state" — true independent of any candidate. Expressing it as a candidate-level null is a
  category error that happens to fit in the column.
- **Absence never enters the fact table**, so the corpus finding that `0` is never encoded is
  honored structurally: there is no cell that could be mistakenly zero-filled.
- **A complete roster is the only shape that makes case 2 representable at all** (it has no
  markup) and simultaneously supplies the expected-state roster the silent-drop guard needs — one
  mechanism, two jobs.
- **MIT is not taxed.** Cases 1–2 cannot occur in 1976–2024, and the design imposes no
  shared-shape change; MIT's roster rows are a mechanical `INSERT … SELECT DISTINCT` over
  already-loaded rows.

**Known trade-off (recorded):** modeling cases 3–4 as no-row loses the distinction between
"attested not on ballot" and "absent from our data." Accepted because D007 scopes candidates to
EC-getters, for whom "no row" and "zero votes" are arithmetically identical in every flip and
margin computation. **Revisit trigger:** if the explorer wants "appeared on the ballot in N
states" as a narrative statistic, cases 3–4 need their own table.

**Related:** **D021** (the shipped `dwh.pv_votes` DDL this conforms to rather than amends);
**D018** (absent-row-not-zero-fill, and the "no second source of truth" ruling reapplied here);
**D006** (EC as the source of truth for electoral votes and participation); **D005** (no
fabricated values); **D009** (the ~1824 window, strengthened via `pv_coverage`); **D022**/**D016**
(the redistributability line the `note` column falls on).

**Action required:**
- **#35 (E4-S2)** — parser emits, per (year, state), a classified status + the verbatim note, and
  **raises** on any unclassifiable cell; the no-residual cell-count assert is a tested function.
  - *Clarified 2026-07-18 during the #35 architect review (story boundary only — no part of this
    decision changes).* The parser emits **only `legislature_chosen`**, the sole status readable
    from markup (§4 case 1). `not_participating` has no markup at all (§4 case 2) and
    `popular_vote` is the roster's residual, so **both are assigned in #36**, which per §6 owns the
    only legitimate roster inputs — the EC spine and `UCSB_NONPARTICIPATING_STATES`. §6 forbids
    deriving participation from UCSB markup, so #35's original three-status AC was unsatisfiable as
    written. The parser retains the §7 **within-page** no-residual guard and §4's raise-on-
    unclassifiable rule; the cross-page two-way roster assert stays in #36 per §7.
- **#36 (E4-S3)** — builds the roster from the EC spine + `UCSB_NONPARTICIPATING_STATES`; the
  two-way roster/fact assert is a tested function, scoped by source and in-scope year set;
  `docs/corrections.md` gains the case-2 rows. Per the §6 clarification, UCSB's year scope is
  derived from `ec_ingest_years()`, and **state-name** canonicalization moves here from #38 (the
  roster is keyed on `dwh.state`'s canonical PK, so it must precede the assert); #38 keeps
  **candidate**-name reconciliation.
- **#57** — lifting 1868/1872 from `UNSUPPORTED_EC_YEARS` also admits them to UCSB ingestion; its
  test updates must cover the UCSB roster path (18-vs-17 legislature-chosen count, and
  `UCSB_NONPARTICIPATING_STATES` going from 11 consumed entries to 14).
- **#37 (E4-S4)** — creates `dwh.pv_state_status` and loads UCSB rows; `dwh.pv_votes` is used
  as-shipped (D021).
- **E6** — a small MIT roster-backfill story (derived, not a reopening of #65/#66); `pv_coverage`
  is defined alongside the D017 views; the `note` column is excluded from the public surface.
- **ROADMAP Open Question 6 ("Shared PV record schema") is closed** — resolved by D018/D021, which
  reversed its premise: MIT landed first and defined the shape; UCSB conforms.

---

## D025: UCSB candidate reconciliation scopes to EC-getters via a reciprocal completeness guard

**Date:** 2026-07-20
**Context:** E4-S4 (#38) reconciles UCSB **candidate** names onto the canonical EC candidate
key (D006) *and* applies the D007 candidate scope (MVP = candidates who received electoral
votes). MIT (#67) could require **full coverage** — every native name mapped, else raise —
because D019 had already pre-scoped it to `party_simplified ∈ {DEMOCRAT, REPUBLICAN}`. UCSB
has no party proxy: it prints the top 2–4 candidates each year (majors *and* notable minors
like Debs 1912, Perot 1992/1996, Nader 2000), so scoping to EC-getters *is* a name match, and
telling a legitimately dropped minor from a **forgotten major** needs the EC-getter authority.
The #38 architect review weighed two designs: **Fork 1** — enumerate every UCSB column,
minors included, with an explicit DROP sentinel (full coverage like MIT); **Fork 2** — map
EC-getters only and guard completeness reciprocally.

**Decision:** **Fork 2.** In `usvote/ucsb/reconcile.py`:

1. `UCSB_CANDIDATE_RECONCILIATIONS` maps only EC-getter columns, keyed `(year,
   ucsb_native_name)` → canonical `name` (111 entries; keyed by year because 49 elections reuse
   surnames across different people and drift one person's spelling across years). The 8
   popular-vote-only minors are enumerated in `UCSB_NON_GETTER_COLUMNS` and dropped under D007.
   `_assert_native_coverage` requires **every** UCSB column to be in one bucket or the other —
   an unclassified column raises rather than being silently dropped.
2. Dropping-by-omission is made safe not by enumerating minors (Fork 1's open-ended,
   burden-heavy catalog that D007 exists to avoid) but by a **reciprocal completeness guard**:
   every EC-getter that held a popular vote must survive into the reconciled facts. The getter
   set arrives as an injected `ec_getters` frame (dependency injection, the pattern
   `transform_ucsb` already uses for `ec_participation`), so reconcile stays pure/offline.
3. `EC_GETTERS_WITHOUT_POPULAR_VOTE` (13 entries) exempts EC-getters who by design have no
   popular-vote row — faithless/unpledged electors (1960 Byrd, the 2016 faithless five, 2004
   Edwards, …) and legislature-chosen awards (1832 Floyd, 1836 Mangum). It is historically
   closed. Without it the guard would false-positive on exactly these.
4. This guard is **distinct from and additional to** E6/#69's join-side guard. The #36 two-way
   roster assert operates at `(year, state)` grain and *cannot* catch a forgotten major (its
   states stay non-empty via the other majors), and #69 only ever sees surviving rows — so an
   **ingest-side, candidate-grain** guard here is the only thing that can catch it. #69 still
   owns the reciprocal join-side check that every reconciled name is present in the EC dim.
5. A prerequisite **EC-side** correction strips the 1944 footnote asterisk from the canonical
   name (`Franklin D. Roosevelt*` → `Franklin D. Roosevelt`, via
   `usvote.transform.strip_name_footnote_markers`), so FDR is one cross-year-consistent
   canonical key and UCSB maps 1944 to the clean name.

**Rationale:**
- D007 exists to *bound* the reconciliation burden to the thesis-relevant (EC-getter) set;
  Fork 1's minor catalog is exactly the open-ended list it rejects, and drop-by-omission already
  has precedent (D019 drops non-{D,R} without cataloguing minors).
- The completeness guard, injected offline, gives the anti-silent-drop guarantee that full
  enumeration would — without the catalog — and catches the one failure (a forgotten major in a
  multi-major state) that no later stage can.
- Keying on `(year, name)` resolves recurring surnames and *is* the per-year D007 decision
  (Van Buren won EVs in 1836, ran Free-Soil with none in 1848).

**Action items:**
- **#38 (E4-S4)** — `reconcile_ucsb(pv_votes, roster, ec_getters, *, years)`; the three curated
  constants; `docs/corrections.md` gains the candidate-reconciliation and 1944-asterisk rows;
  `docs/canonical-keys.md`'s UCSB line describes the shipped map. Committed test-input-only
  witness `ec_getters_by_year.json` (names only, D024 §5) drives the offline 49-year guard run.
- **#37 (E4-S5)** — resolves `ec_getters` from `dwh.votes` joined to `dwh.candidate`
  (`president_electoral_votes > 0`, totals rows excluded) and runs reconcile before the load.
- **#69 (E6)** — carries the reciprocal join-side guard that every reconciled UCSB/MIT name is
  present in the EC `candidate` dim.

---

## D026: The EC↔PV join is an EC-left join over the *dense* EC votes fact (year, state, candidate)

**Date:** 2026-07-21 (corrected 2026-07-22 — see "Correction")
**Context:** E6-S2 (#69) joins the resolved PV series onto the EC spine — `pv_preferred` for the
analysis path (E7), `pv_redistributable` for the API path (E8) — reading a **resolved view, never
the raw `dwh.pv_votes` union** (D017; joining the union fans the 1976–2024 overlap out 2× and
double-counts every downstream sum/margin). D017 framed the join as "EC on the left, PV attaches,
missing PV surfaces as an explicit gap," a natural reading of D006 (EC is the source of truth PV
joins *onto*). The project's primary thesis (D001) is a per-state and national **margin** question
— "where does a candidate lose the EC but win the PV, and by how much" — which needs *both* majors'
per-state popular votes, i.e. a losing candidate's per-state row must survive the join.

**Correction (2026-07-22): the premise that drove the first design was empirically false.** The
first draft of #69 adopted a **FULL OUTER "participant" view** on the belief that the EC `votes`
fact is **sparse** — that `build_votes_fact`'s `.dropna(subset=["president_electoral_votes"])`
drops any candidate/state cell with no electoral votes, so a loser (Biden in Texas 2020) has *no EC
row* and an EC-left join would drop them. **That is wrong.** The Archives Table 2 prints `-` for
"won no electoral votes here", and `parse_t2_votes_by_state` reads `-` as **0** (`parse.py:385`),
so `.dropna()` (which only removes the ragged cross-year NaNs of the multi-year `json_normalize`)
drops **no** losers. The CI integration test caught it — `(2016, Texas, Clinton)` came back as a
real EC row with `president_electoral_votes = 0`, not a missing one. Verified across the **entire**
dataset by rebuilding the fact for all years: **49/49 years are rectangular** (`rows == states ×
getters`), and **~59% of state rows (3,162 / 5,327) are explicit 0-EV loser rows**. The EC fact is
**dense**, not sparse.

Consequences: an **EC-left** join already keeps every loser's per-state row (they are 0-EV rows,
with the national rank/`took_office` already broadcast onto them by the transform), so it satisfies
the thesis directly. And because PV is scoped to EC-getters (D007) in participating states (D024),
**every PV key matches a dense EC row** — so the full-outer's PV-only arm was *provably dead*
(`has_ec_state_row` always true, its fill CASE never fired). The full-outer was correct-but-over-
justified machinery resting on a false premise; EC-left is simpler and honest.

**Decision:** Join the EC state-level `votes` rows to the resolved PV view with an **EC-LEFT JOIN**
on `(year, state, candidate)` — `dwh.votes v (WHERE state IS NOT NULL) JOIN dwh.candidate c LEFT
JOIN <pv_view> p ON (v.year, v.state, c.name) LEFT JOIN dwh.pv_source s`. Subordinate to D006 (EC
governs the candidate universe and is the join's left/authoritative side) and D017 (resolved view,
not the union).

1. **Two views, one parameterized builder.** `ec_pv_preferred` (over `pv_preferred`, for E7) and
   `ec_pv_redistributable` (over `pv_redistributable`, for E8) are the same join over a different
   resolved PV view. **Views, not materialized tables** (D017's default).
2. **Three row types the grain expresses:**
   - **winner+PV** — EC actual (electoral votes > 0), PV actual.
   - **loser+PV** — a real EC **0-EV row** (dense fact — *not* a filled/fabricated value), PV
     actual. The rows the thesis is *about*; an EC-left join keeps them because they exist.
   - **getter-without-PV** — EC actual, PV **NULL**. Pre-1976 getters, or faithless getters with no
     popular vote — an honest D005 gap, never a fabricated PV.
3. **Scope is per-year EC-getters, for free.** `pv_preferred` is already D007/D019-scoped to per-year
   EC-getters (D025), and `dwh.votes` only holds getters, so no popular-vote-only minor leaks in.
4. **The dense fact is guarded, not assumed.** Density is what makes EC-left preserve losers, so it
   is asserted rather than left emergent: `assert_rectangular_state_grain` in `build_votes_fact`
   fails loud if any year's state fact is not rectangular (`rows == states × getters`). This closes
   a real seam — `assert_state_count_by_year` only checks the rank-1 winner per state, and
   `assert_totals_equal_state_sum` is blind to a dropped 0-row — before coverage extends below 1892
   (#32) and some early table breaks it silently. **No EC-0 is ever fabricated:** every electoral
   value comes straight from `dwh.votes`; a getter with no PV keeps NULL PV (D005).
5. **National context via a window SUM.** `national_electoral_votes` is
   `SUM(president_electoral_votes) OVER (PARTITION BY year, candidate_id)` — exact because the fact
   is dense and the state-sum equals the published national total (`assert_totals_equal_state_sum`),
   so it needs no join to the `is_total` rows; `president_electoral_rank`/`took_office` are already
   broadcast onto the state rows by the transform. Flip detection reads off this one view.
6. **This module is EC-domain.** `src/usvote/join.py`, a **sibling to `usvote/spine.py`** (not under
   `usvote/pv/`), because it names `dwh.votes`/`dwh.candidate` — the greppable invariant "**nothing
   under `usvote/pv/` names `dwh.votes`**" forbids a `pv/` home.
7. **The reciprocal guard is a fact-level anti-join, and load-bearing.** Under an EC-left join a PV
   row matching **no** EC votes row is *silently dropped* (the project's documented inner-join
   footgun). So the guard #69 owns (`docs/canonical-keys.md`) is stronger than dim-membership: a
   `NOT EXISTS` anti-join asserts every resolved PV `(year, state, candidate)` matches an EC state
   row `(year, state, name)`, failing loud with the offending keys as a **view-creation
   precondition**. It also catches a D007 getter-scope violation, or a name/state that exists in the
   dims but not for that election. Supporting the `c.name` join, **`UNIQUE(name)` is added to
   `dwh.candidate`** (D021's table carried `candidate_id` PK, `name` unconstrained).
8. **Winner-has-PV coverage guard (EC→PV direction).** Complementing the anti-join, an EC **winner**
   (`president_electoral_votes > 0`) inside the PV window with no PV is a reconciliation miss and
   fails loud — keyed on `> 0`, **not** every EC row, because a *loser*'s 0-EV row may legitimately
   lack PV (a regional candidate like Thurmond 1948 on the ballot in only some states). Exemptions
   are the getters that legitimately held no popular vote (`EC_GETTERS_WITHOUT_POPULAR_VOTE`,
   promoted to the dependency-free `usvote/getters.py`). It returns its inspected-winner count so a
   caller asserts a vacuity floor. Wired live in the gated real-corpus integration test over
   `ec_pv_preferred`.
9. **Honest consumer split.** E7 reads `ec_pv_preferred`; E8 reads `ec_pv_redistributable`, which
   **never surfaces a `redistributable=false` (UCSB) row** — inherited from `pv_redistributable`'s
   independent `WHERE redistributable` (D017/D002/D014/D016), not re-derived at the join.

**Rationale:**
- **Match the data, not an assumption.** EC-left is the simplest join that satisfies the thesis
  *given the dense fact*; the full-outer's PV-only arm and 0-fill were solving a non-problem. When a
  premise turns out false, the honest fix is to remove the machinery it justified, not keep it.
- **Density is now guarded, not lucky.** The rectangularity assert makes the property the whole
  simplification rests on a checked invariant — so a future ragged early table (below 1892, #32)
  fails at the transform, not as a silently-dropped loser downstream.
- **Fail-loud over silent surfacing.** EC-left's one risk (a dropped unmatched PV row) is caught by
  the anti-join precondition — a loud failure with keys beats a full-outer's silently-visible row.
- **Forward-compatible.** A third PV source drops in via #68's data-driven precedence with no change
  to the join, which reads whatever `pv_preferred`/`pv_redistributable` resolve to.

**Related:** **D017** (resolved views not the raw union); **D006** (EC as source of truth — the
join's left/authoritative side); **D005** (no fabricated PV — NULL-not-zero on the PV side);
**D007**/**D024** (getter + participating-state scope that makes PV ⊆ the dense EC rows);
**D021** (the `dwh.candidate` DDL this adds `UNIQUE(name)` to); **D002**/**D014**/**D016** (the
`redistributable=false` boundary `ec_pv_redistributable` must not cross); **D020**/**D025** (#69
carries the reciprocal name-in-dim guard those defer to it, now fact-level); **#89** (the missing EC
HTML snapshot that made verifying density require a full live re-scrape).

**Action required:**
- **#69 (E6-S2)** — implement `usvote/join.py`: the parameterized EC-left builder, the two views
  (`ec_pv_preferred`, `ec_pv_redistributable`), the national-EV window sum, the fact-level anti-join
  precondition, and the winner-has-PV coverage guard.
- Add **`assert_rectangular_state_grain` to `build_votes_fact`** (guards the dense-fact premise).
- Add **`UNIQUE(name)` to the `dwh.candidate` DDL** (supports the `c.name` join).
- Promote **`EC_GETTERS_WITHOUT_POPULAR_VOTE` to `usvote/getters.py`** (a second cross-boundary
  consumer — the winner-has-PV guard — makes it an EC-domain fact, not a UCSB one).
- **Automated tests:** no-fan-out; the anti-join guard (a PV row matching no EC row fails loud);
  rectangularity (a dropped loser row fails at the transform); a **split-vote state** (ME/NE — each
  getter keeps its real EC count); winner-has-PV over the real corpus with the exemption set + a
  vacuity floor; and the `ec_pv_redistributable` leak-guard.

## D027: Package entry points are subcommand-based, with a top-level `warehouse.py` composition root

**Date:** 2026-07-22
**Context:** #84b, split out of #84 (84a landed the `DBC.transaction()` primitive + the uniform
per-pipeline ownership rule). Before this, the three ingest entry points disagreed on what
`python -m X` meant: `python -m usvote` ran the whole EC pipeline, `python -m usvote.ucsb`
*snapshotted* raw HTML (not a pipeline run), and `usvote.mit` had no `__main__` at all. The same
spelling meant "run the pipeline" for EC and "fetch raw data" for UCSB. E6 also needs a single
one-command build of the entire warehouse (EC spine + both PV sources + the E6-S2 join views), which
no entry point provided.

**Decision (five parts):**

1. **All package `__main__`s are subcommand-based, but every bare invocation keeps its historical
   meaning as a *named default subcommand*.** `python -m usvote` → EC (subcommands `ec`, `all`);
   `python -m usvote.ucsb` → snapshot (subcommands `snapshot`, `load`); `python -m usvote.mit` → load
   (single `load` subcommand). The issue framed the wart as "same spelling, different meaning"; this
   **reduces it to a documented default, not eliminates it** — `python -m usvote` loads and
   `python -m usvote.ucsb` snapshots still differ, but each is now a discoverable default, and the
   asymmetry is principled (only UCSB has a network stage to snapshot; MIT reads a local CSV).

2. **Bare `python -m usvote` stays EC — it is *not* re-pointed at `all`.** `all` additionally requires
   `USVOTE_MIT_CSV_PATH` (and the UCSB snapshot for the full set), so making bare mean `all` would
   *raise* the config bar on the single most common command and break a CLAUDE.md-documented
   invocation. Backward compatibility (including bare `--replace`) is preserved; the whole-warehouse
   build is the explicit `all` subcommand.

3. **The whole-warehouse orchestrator lives in a new top-level `usvote/warehouse.py`
   (`run_warehouse`), a composition root — NOT inside `usvote/pipeline.py`.** `warehouse.py` imports
   *from* every source (EC + `usvote/mit` + `usvote/ucsb`). Putting that wiring in `pipeline.py` (an
   EC-spine module) would make the EC spine import the PV sources — the exact D015 source-to-source
   inversion. A composition root sits **above** both EC and PV, like `usvote/__main__`, so it is
   exempt from the prohibition for the same reason `__main__` is. The exemption is kept honest by the
   reverse invariant — **nothing under `usvote/{mit,ucsb,pv}/` imports `usvote.warehouse`** — enforced
   by a test mirroring the greppable `dwh.votes` guard (a back-import would invert D015 into a cycle).

4. **The build is per-source atomic, not globally atomic; recovery is `--replace`, not a bare
   re-run.** `run_warehouse` opens **no** transaction of its own — each pipeline already owns its
   DB-write transaction (84a's uniform rule), and `DBC.transaction()` raises on a nested open, so the
   orchestrator sequences them and never wraps them. Consequence: a mid-build failure leaves the
   already-committed sources in place and later ones absent. Because the PV/EC loaders are
   create-if-absent/append, a bare re-run raises a unique/PK violation on the first already-loaded
   source before it reaches the missing one, so the honest recovery path is
   `run_warehouse(..., replace=True)` (a clean full rebuild). Network/scrape stays outside every
   transaction, so no build holds one open across HTTP.

5. **`--replace` maps EC-destructive + PV-additive, and the join views are always rebuilt.** For `all`,
   `--replace` forwards to `run_ec_pipeline(replace=True)` (which does `DROP SCHEMA dwh CASCADE`,
   taking the PV tables *and* the E6-S2 views with it) while the PV sources load `replace=False` onto
   the fresh schema — the only sane mapping, and exactly the integration-test order. The resolved-PV +
   EC↔PV join views are therefore **always rebuilt as the final step** (`build_pv_union` +
   `create_ec_pv_views`, both idempotent, both transaction-free): without that rebuild a `--replace`
   build would leave the warehouse with fact tables but no `ec_pv_preferred`/`ec_pv_redistributable`
   for E7/E8 to read. For a single-source subcommand (`usvote.mit load --replace`,
   `usvote.ucsb load --replace`) `--replace` is instead *table-level* (rebuild that source's PV
   table(s), never the schema) — one flag, two scopes, spelled out in `--help`.

**Alternatives rejected:** bare `python -m usvote` → `all` (raises the config bar, breaks a documented
command — part 2); orchestrator inside `pipeline.py` (D015 inversion — part 3); a global transaction
across the whole build (would hold one open across HTTP scrapes, and 84a's raise-on-nest forbids it —
part 4); a per-source `--replace` matrix (overkill — part 5); env-magic UCSB gating inside
`run_warehouse` (the programmatic seam takes an explicit `ucsb_html_dir=None` to skip; only the CLI
auto-detects `USVOTE_UCSB_HTML_DIR`, and only *loudly* with a printed notice + `--require-ucsb`, so a
warehouse silently missing the UCSB analysis-only control can never happen — D024/D017).

**Related:** **#84a** (the `DBC.transaction()` primitive + uniform per-pipeline ownership this builds
on); **D015** (source-namespacing / no source-to-source imports — the composition-root carve-out
here); **D023** (the UCSB snapshot, why `python -m usvote.ucsb` defaults to `snapshot`); **D024**/
**D017** (missing data modeled explicitly, never silent — the loud UCSB gating and the structured
`WarehouseResult`); **D016** (EC + MIT = the redistributable public core, UCSB = the analysis-only
control — why a fresh public clone builds EC + MIT and skips UCSB); **D026** (the join views
`run_warehouse` rebuilds); **E7/E8** (the `ec_pv_preferred`/`ec_pv_redistributable` consumers the
always-rebuild step and the `WarehouseResult` receipt are designed for).

**Action required:**
- Add `usvote/warehouse.py` (`run_warehouse`, `rebuild_views`, `WarehouseResult`) — done.
- Rewrite `usvote/__main__.py` (subcommands `ec`/`all`, bare = EC), add `usvote/mit/__main__.py`
  (`load`), rewrite `usvote/ucsb/__main__.py` (subcommands `snapshot`/`load`, bare = snapshot) — done.
- Add the reverse-import guard test (nothing under `usvote/{mit,ucsb,pv}/` imports `usvote.warehouse`)
  and CLI/orchestrator unit tests; point the live-DB integration test at `run_warehouse` (the shipped
  path) — done.
- A future `views` subcommand (rebuild views without re-scraping) is a thin wrapper over
  `rebuild_views`; the dispatch is left open for it (#84 follow-up).

---

## D028: The E8 API serves a read-only embedded snapshot, not a live database

**Date:** 2026-07-23
**Context:** E8 (#94) exposes `ec_pv_redistributable` over HTTP. The obvious design points the
API at the warehouse Postgres, but that makes Postgres a production runtime dependency — the one
component that will not scale to zero (a managed instance carries a monthly floor even at zero
traffic) and the one most likely to fail a request. The redistributable dataset is tiny and
read-mostly (~a dozen elections × ~51 jurisdictions × the D/R nominees, refreshed on a ~4-year
cadence + occasional corrections), so a live query engine is disproportionate to the workload.

**Decision:** The API reads a **read-only embedded snapshot** materialized from
`ec_pv_redistributable`, with **no live DB at serve time**. Postgres stays the *local* warehouse /
source of truth. Refined per the E8 architect review (three parts):

1. **The snapshot store is SQLite** (stdlib `sqlite3` driver — zero runtime deps, indexed
   by-year/by-state/by-candidate filtering, a `meta` table for provenance), not static JSON. The CDN
   caches API *responses*, not the store, so JSON buys no caching edge; SQLite ages better as
   coverage widens (S8 hybrid columns, a possible pre-1976 extension).
2. **"No live DB at serve time" is a structural import-graph invariant, not a runtime property.**
   The snapshot *build* reads Postgres, so it lives in a new top-level `usvote/snapshot.py` (an
   EC-domain consumer of `ec_pv_redistributable`, in the `spine.py`/`join.py`/`warehouse.py` family,
   composition-root-exempt from D015 per D027) — **not** inside `usvote/api/`. `usvote/api/` imports
   only the snapshot artifact + a thin `SnapshotRepository`, and a unit test asserts nothing under
   `usvote/api/` imports `usvote.db` or psycopg2 — mirroring the project's existing greppable layering
   guards (`dwh.votes` not named under `pv/`; `usvote.warehouse` not imported under the sources).
3. **The snapshot version is a content hash, not a build timestamp.** `snapshot_version` = a hash of
   the data rows extracted with a deterministic `ORDER BY (year, state, candidate)` (+ a schema
   version); the build timestamp is informational metadata only, excluded from the version and the
   ETag. A timestamp would break both the byte-reproducibility AC and cache correctness (identical
   data must yield an identical ETag).

**Rationale:**
- Cost/reliability/ease all point the same way: a scale-to-zero container serving an immutable
  SQLite file has no DB to provision, connection to drop, or floor to pay, and runs standalone in
  local dev with Postgres stopped.
- Making the DB-free property *structural* means a future change can't quietly reintroduce a live
  query path without failing a test — the same discipline the rest of the package already relies on.
- A content-derived version is the single value that reconciles reproducibility with the freshness
  contract (D-below) and lets a second consumer cache honestly.

**Related:** **#94/#95/#96** (E8 epic + the snapshot-build and app-skeleton stories); **D026**
(`ec_pv_redistributable`, the view the snapshot reads); **D027** (composition-root exemption reused by
`usvote/snapshot.py`); **D017** (redistributable surface); **[[nan-none-db-boundary]]**-style single
write chokepoint, applied here to the single *read/materialize* chokepoint.

**Action required:**
- Add `usvote/snapshot.py` (materialize `ec_pv_redistributable` → SQLite; content-hash version;
  national roll-up table; drop `candidate_id`, mint the public slug — see D-slug below) and its build
  entry point.
- Add the `usvote/api/`-imports-no-DB guard test.

---

## D029: E8's API MVP is decoupled from E7 — it depends only on E6's join view

**Date:** 2026-07-23
**Context:** The ROADMAP's original critical path read `E7 (hybrid) + E9 (mart) → E8 (API)`. But E6
landed `ec_pv_redistributable`, and the API MVP (redistributable EC+PV at the canonical grain) needs
nothing from the hybrid computation to be useful and to power our app.

**Decision:** The **E8 API MVP depends only on E6** (`ec_pv_redistributable`), not on E7 or E9. Hybrid
/ flip / margin fields are added to the API as a **later story (E8-S8, #102), gated on E7** — arriving
as new *optional* response fields under the same `/v1` (additive, non-breaking) and flowing through
the same snapshot materialization seam (no second extract path). The ROADMAP critical-path note is
updated to match; E9 (mart) may later become an additional read source behind the same
`SnapshotRepository` seam but is not an MVP dependency.

**Rationale:**
- Shipping the foundation now (a robust, public-graduation-ready surface over data that already
  exists) beats waiting on hybrid work for a first release, and matches the "running quickly on a
  robust foundation" goal.
- Because hybrid is only defined on the redistributable window, S8 stays automatically D030-consistent
  and additive — so decoupling costs no rework, it only reorders.

**Related:** **#94/#102** (epic + the E7-gated hybrid story); **D011** (hybrid computation, E7);
**D026** (the E6 view); ROADMAP "First-cut epic outline" critical path (edited alongside this entry).

**Action required:** Edit `docs/ROADMAP.md` so the critical path reflects E6 → E8 (MVP) directly,
with E7 + E9 → the explorer and E8's later hybrid fields — done alongside this entry.

---

## D030: The API surface is redistributable-only from day one

**Date:** 2026-07-23
**Context:** E8 will eventually graduate to a public/third-party API (D002), gated on PV licensing
(D008/D014). UCSB PV is `redistributable=false`; MIT is the redistributable modern core (D016). The
question was whether the *internal* MVP could serve everything and filter later, or exclude
non-redistributable rows from the start.

**Decision:** The API serves **only redistributable rows from the first release** — it reads
`ec_pv_redistributable`, which wraps `pv_redistributable`, defined *independently* as
`WHERE redistributable` (D017). No preference-resolution or later feature change can leak a UCSB row
onto the API surface. Defense-in-depth: the redistributable-only guarantee is re-asserted at the
snapshot source (E8-S1), the endpoints (E8-S3), and a regression test (E8-S5).

**Rationale:**
- Building the internal MVP on exactly the surface the public API will use means **zero rework at
  graduation** — the licensing boundary is structural (an invalid state is unrepresentable), not a
  filter someone must remember to apply.
- The CC0/UCSB stakes justify the triple guard as proportionate, not gold-plating.

**Related:** **#94** (epic); **D002** (public-API deliverable + gate); **D008/D014** (PV licensing);
**D016** (EC + MIT = redistributable core, UCSB = analysis-only); **D017** (`pv_redistributable`
defined independently as `WHERE redistributable`); **[[inner-join-silent-drop]]** (why the guard is
tested, not assumed).

---

## D031: The API is FastAPI/REST with `/v1` and OpenAPI-as-a-deliverable, not GraphQL

**Date:** 2026-07-23
**Context:** The stack choice was FastAPI/REST vs. GraphQL (both viable in Python). The dataset is
small and tabular with a few obvious query patterns (by year / state / candidate + a national
summary), and a near-term goal is advertising the API to the MIT Election Lab.

**Decision:** **FastAPI (REST)**, versioned `/v1` from day one, with the **auto-generated
OpenAPI/Swagger docs treated as a first-class deliverable** (its own story, E8-S4) — the
self-documenting surface *is* half the pitch to external consumers. No pagination for the MVP (every
endpoint is already scoped by year/state/candidate; the whole corpus is low-thousands of rows), but
`meta.count` is retained and a server-side cap prevents any unbounded path, so pagination stays an
additive change. Freshness contract: a **content-hash ETag** (per D028) plus
`Cache-Control: public, max-age=3600, stale-while-revalidate=...`, emitted from the app locally so the
CDN step (E8-S7) is config, not code. CORS via a `USVOTE_API_CORS_ORIGINS` env allow-list (localhost
default, never a silent `*`).

**Rationale:**
- GraphQL's flexibility buys little for a handful of fixed query shapes and costs a learning curve,
  harder CDN caching (POST queries don't cache as cleanly as REST GETs), and more surface area.
- REST GETs + OpenAPI are the more discoverable, cacheable, standard choice for a public reference-data
  API; a GraphQL layer can be added later if a real consumer demands it.
- `/v1` and cache headers on day one are near-free hedges that make the public/Cloud-Run graduation a
  config step rather than a rewrite.

**Related:** **#94/#96/#97/#98** (epic + skeleton/endpoints/docs stories); **D002** (public-API
graduation the OpenAPI asset serves).

---

## D032: The API ships as a cloud-agnostic container with the snapshot baked in; Cloud Run is the post-MVP target

**Date:** 2026-07-23
**Context:** Hosting was Open Question #3 (undecided infra). Priorities: cost > reliability > ease,
with initial traffic tiny (our own dashboard) and a likely later pivot to a cloud provider once the
API is advertised. Candidates considered: Cloud Run, Fly.io, Render/Railway, Vercel.

**Decision:** The MVP **runs locally** and ships as a **cloud-agnostic container** (no
provider-specific coupling), with the **snapshot baked into the image** (snapshot-version ==
image-version, so no runtime mount and no artifact/code version skew). The **eventual cloud target is
Google Cloud Run** — scale-to-zero, pay-per-request, portable container, generous free tier — but the
actual deploy (+ CDN, custom domain, auth/rate-limiting posture) is a **later/stretch story
(E8-S7, #101)**, not an MVP commitment. Vercel is rejected as a Python-second-class frontend platform;
Fly.io/Render remain fallbacks if Cloud Run's cost profile changes.

**Rationale:**
- A baked-in immutable snapshot on a scale-to-zero container is the cheapest and most reliable option
  at our volume, and the refresh path (rebuild-and-redeploy) is fine precisely because data changes
  every ~4 years.
- Keeping the container provider-agnostic means the hosting decision can be deferred/changed without
  touching application code — cost is the top priority and the market moves.

**Related:** **#94/#100/#101** (epic + Dockerfile + Cloud-Run-deploy stories); **D028** (the baked-in
snapshot); ROADMAP Open Question #3 (this decision resolves the API-hosting half).

## D033: The API container installs a slim serve-only dependency closure, not the full package deps

**Date:** 2026-07-24
**Context:** E8-S6 (#100) containerizes the API (D032: cloud-agnostic image, snapshot
baked in). A full package install drags the warehouse/analysis stack — pandas, geopandas,
GDAL, psycopg2, matplotlib — into the image (hundreds of MB, slow cold start), failing the
AC that the image be "reasonably small and starts fast (scale-to-zero friendly)." But the
API serve path never uses that stack: `usvote/api/` imports only fastapi/starlette/pydantic
+ `usvote.snapshot_schema`/`usvote.config` (both stdlib-only) + stdlib — the D028
import-graph invariant.

**Decision:** The container installs the `usvote` package with `--no-deps` and adds only the
serve-time closure (fastapi, uvicorn, pydantic), whose versions are resolved from `uv.lock`
via a dedicated `serve` dependency-group (never hand-pinned literals in the Dockerfile, which
would fork the version truth from the lock). The container's runtime dependency closure thus
**intentionally diverges** from the package's declared base dependencies — the D028
import-graph invariant is what makes that divergence safe, and this decision elevates that
invariant from a code-layering guard to a load-bearing deployment guarantee. An `api` *extra*
is explicitly **not** the mechanism: extras are additive and cannot subtract the heavy base
deps; the size lever comes from `--no-deps` + the lock-derived serve group.

**Rationale:**
- Slim is required to meet the scale-to-zero AC; the import graph is already test-enforced,
  so the closure divergence rests on an existing invariant, not a new hope.
- Sourcing serve versions from `uv.lock` keeps a single version source of truth; CI and the
  container resolve the same fastapi/uvicorn/pydantic.
- The divergence introduces a silent-drift failure mode (an allowed-but-unpackaged import
  added to `usvote/api/` — e.g. httpx — passes the denylist import-graph test but breaks the
  slim image at `docker run`). This is guarded by the CI docker job running the built image
  and hitting `/health` (a container smoke test), not by a bespoke positive-allowlist test.

**Related:** **D028** (import-graph invariant this exploits), **D032** (the container/hosting
decision this refines), **#100** (E8-S6), `tests/unit/test_api_import_graph.py`.

## D034: Deploy the API to Cloud Run behind Cloudflare (free), keyless via WIF, with a GCS-sourced CI-built image and version-based edge caching

**Date:** 2026-07-24
**Context:** E8-S7 (#101) graduates the D032 cloud-agnostic container to a public host. Roadmap Open Question #3's hosting half. Priorities (owner, 2026-07-24): cost first (scale-to-zero, single instance), then request throttling/anti-bot, then reliability. Locked human decisions: Cloudflare **free** plan in front (not a GCP HTTPS LB, whose ~$18–25/mo fixed cost fights scale-to-zero); deploy via **GitHub Actions + Workload Identity Federation** (keyless). Provisioning is owner-run (owner's GCP + Cloudflare creds); the repo ships deploy glue + runbooks + the app changes.

**Decision:**
1. **Host:** Cloud Run, `--min-instances=0 --max-instances=1`, request-based CPU, single region, `--allow-unauthenticated --ingress=all`, fronted by Cloudflare (proxied DNS on an owner-supplied custom domain) for CDN + rate limiting + Bot Fight Mode. A GCP Billing Budget → Pub/Sub kill-switch sets `max-instances=0` on spend threshold (Cloud Run has no native hard cost cap).
2. **Snapshot → image:** the snapshot is a **data input** to a **CI-built** image, not a locally-built image. It lives in a private, object-versioned **GCS bucket**; the deploy workflow pulls it into the build context, builds in Actions, pushes to **Artifact Registry**, deploys. The image is tagged with the `snapshot_version` content hash. Refresh (AC4): rebuild snapshot locally from the warehouse → upload to the bucket → run the deploy workflow. Rejected: local build+push (laptop-tied, fails AC3); Actions/release artifacts (expiry / support-commitment overhead).
3. **Origin lock-down:** a stdlib-only app middleware requires a shared-secret header (injected by a Cloudflare Transform Rule) on `/v1` — **only when `USVOTE_API_ORIGIN_SECRET` is set** (fail-open for local dev/tests/smoke), `/health` always exempt (Cloud Run probes and the D033 smoke test don't traverse Cloudflare). Chosen over Cloud Run ingress/IAM/mTLS, all of which the no-LB decision or Cloud Run's TLS model rule out. Fail-open is made safe by (a) surfacing enforcement state in `/health` + a startup log line and (b) a post-deploy workflow assertion that raw `run.app` `/v1` returns 403 and the Cloudflare hostname returns 200.
4. **Caching:** version-based, not TTL. The response header stays moderate and honest to all caches — `public, max-age=3600, stale-while-revalidate=86400, stale-if-error=86400` + the strong `snapshot_version` ETag. The *long* hold lives in a Cloudflare **Cache Rule Edge Cache TTL** (purge-reachable), and the deploy workflow **purges the Cloudflare cache after the new revision is serving traffic**. This keeps true scale-to-zero (edge absorbs reads; browser revalidations terminate at the warm edge and never wake the origin) while a bug-fix deploy reflects promptly (new ETag + moderate browser max-age + edge purge).
5. **Deploy auth/secrets:** WIF provider attribute-locked to this repo; two least-privilege service accounts (deploy vs runtime); Cloudflare purge token (cache-purge, single zone) in GitHub Actions secrets; `USVOTE_API_ORIGIN_SECRET` in GCP Secret Manager bound to the service. Deploy trigger is `workflow_dispatch` (+ optional tag), never `pull_request`.

**Rationale:**
- Cloudflare-free + scale-to-zero + single instance is the cheapest posture that still gets CDN + rate limiting; a GCP LB's fixed floor contradicts the top priority.
- A CI-built image over a GCS-sourced snapshot satisfies "reproducible, not laptop-tied" while respecting that the snapshot itself can only be produced from the local warehouse.
- The version-based cache model exploits the ~4-yearly data cadence: reads never wake the origin between versions, and invalidation is an explicit purge keyed to the content hash rather than a TTL guess.
- The origin secret is the only lock-down layer available once a GCP LB is off the table; making its enforcement observable + post-deploy-asserted converts a fail-open footgun into a verified control.

**Related:** **#101** (this story); **D028** (DB-free snapshot + content-hash ETag the cache/purge model rests on); **D030** (redistributable-only, reconfirmed in the hosted context); **D031** (`/v1` + the `Cache-Control`/ETag contract emitted locally so the CDN step is config); **D032** (cloud-agnostic image + Cloud Run target this realizes); **D033** (slim image + import-graph invariant the middleware must not break); ROADMAP Open Question #3 (hosting half).

## D035: The Cloudflare front is a Worker, not Origin/Transform/Cache Rules (free-plan reality)

**Date:** 2026-07-25
**Context:** D034 specified the Cloudflare front as zone Rules — an **Origin Rule "Host Header Override"** (so Cloud Run's Host-routed `run.app` front end accepts the request), a **Transform Rule** to inject the origin secret, and a **Cache Rule** for the edge TTL. During provisioning (#101) the free Cloudflare plan turned out to **paywall Origin Rules "Host Header Override"** — and without it a proxied `CNAME api → run.app` returns a **Google 404**, because Cloud Run's front end routes by the HTTP `Host` header, which Cloudflare forwards as `api.<domain>` (unknown to Cloud Run).

**Decision:** Front Cloud Run with a **Cloudflare Worker** (`usvote-api-proxy`, bound as a Custom Domain on `api.<domain>`) instead of zone Rules. The Worker: (1) rebuilds the request against the `run.app` URL so the outbound Host is `run.app` (fixes the 404); (2) injects the `X-Usvote-Origin-Secret` header from a Worker **secret binding** (replaces the Transform Rule); (3) caches `GET /v1` 200s via the **Cache API** with a long `s-maxage` edge hold + moderate browser `max-age` (replaces the Cache Rule). Rate limiting + Bot Fight Mode stay zone-level WAF features (the Worker does not rate-limit). This **supersedes D034's Cloudflare *mechanism* only** — D034's *intent* is unchanged and fully preserved: origin-locked (`run.app/v1` → 403, Cloudflare → 200), version-based edge caching, purge-on-deploy (`purge_everything` clears the Worker's `caches.default`), scale-to-zero. The deploy workflow (`deploy.yml`) is unaffected — its post-deploy 403/200 smoke and cache purge work identically against the Worker.

**Also recorded here:** the origin secret must be stored **without a trailing newline**. `openssl rand -hex 32 | gcloud secrets versions add` stores the `\n`, which Cloud Run injects, so the lock 403s (the Worker's clean header value ≠ stored `value + \n`). Use `printf '%s' "$(openssl rand -hex 32)"`.

**Related:** **D034** (the deploy decision whose Cloudflare mechanism this revises), **#101**, `docs/deploy-cloud-run.md` (§4 + §7 updated), `.github/workflows/deploy.yml` (unchanged). Live at `https://api.us-presidential-election-center.org`.
