# Research: Popular-Vote Data Source Determination

> **Status: COMPLETE.** This is the E3 (issue #13) research deliverable. It characterizes the
> two chosen PV sources — MIT Election Lab (E3-S1, #15) and UCSB / American Presidency Project
> (E3-S2, #16) — scans the fallbacks, and consolidates them into the source-determination
> recommendation and licensing finding (E3-S3, #20) that gates the public-API stretch goal
> (D002) and unblocks E5 (MIT ingestion) / E6 (join) scoping. The dual-source direction was
> already decided — see [`decisions.md`](decisions.md) **D014**; this doc is the evidence
> behind it plus the now-resolved licensing verdict.

**Date started:** 2026-07-06 · **UCSB section added:** 2026-07-13 · **Consolidated (E3-S3):** 2026-07-13

---

## 1. Recommendation

**Adopt a dual-source PV strategy (confirms D014, refines D008):**

- **MIT Election Lab** — the **modern, API-eligible core (1976–2024).** Clean state-level
  per-candidate CSV at exactly the fact-table grain, and — the key new finding below —
  released under **CC0 1.0**, so it is **cleared for public-API redistribution** with no
  permission needed. This is the redistributable half D008 was reaching for.
- **UCSB / American Presidency Project** — the **historical-breadth source (1789–2024),
  analysis-only.** The only source in hand that reaches the ~1824 MVP comparison floor (D009)
  and covers the decisive pre-1976 EC/PV splits (1876, 1888) and the 1824 contingent election.
  Treated as **non-redistributable** pending permission, so its rows never touch the public
  API surface.

The two are **complementary, not redundant** (D014): MIT alone cannot reach the MVP window;
UCSB alone cannot be redistributed. Both reconcile onto the EC canonical keys (D006 / #30,
#38), which remain the source-of-truth spine.

**The headline change since D014:** the MIT **licensing gate is now resolved** — CC0 clears
the public API for the modern core. MIT outreach is therefore **no longer required for
licensing**; the only remaining (optional) reason to contact the lab is a possible pre-1976
coverage extension (§6). This is significant enough to warrant a new decision entry (D016,
recorded alongside this synthesis).

## 2. Source comparison (head-to-head)

| Axis | **MIT Election Lab** | **UCSB / American Presidency Project** | ICPSR Study 1 (+79) *(fallback)* |
|---|---|---|---|
| **Coverage** | 1976–2024 (13 elections) | **1789–2024 (60 elections)** — full MVP span | 1824–1968 (+ 1788–1823 via Study 79) |
| **Reaches ~1824 floor (D009)?** | ✗ starts 1976 | ✓ | ✓ |
| **Covers modern EC/PV splits (2000, 2016)?** | ✓ | ✓ | ✗ (ends 1968) |
| **Covers historical splits (1876, 1888)?** | ✗ | ✓ | ✓ |
| **Grain** | one row per (year, state, candidate) — long | one row per (year, state), candidates in columns — **wide, melt required** | county-level, roll up to state |
| **Format** | single clean CSV | per-year HTML tables, `colspan`/`rowspan`, era-drifting layout | structured data files |
| **Effort to ingest** | low (CSV read) | high (era-generic HTML parse, E4/#35) | medium (structured, but access-gated) |
| **License** | **CC0 1.0 (public domain)** | UCSB Terms of Use — no reuse grant | free to ICPSR-member institutions; not an open license |
| **Public-API redistributable? (D002 gate)** | **YES** | **NO — needs permission** (`policy@ucsb.edu`) | **NO — member-access only** |
| **Role (D014)** | modern API-eligible core | historical analysis-only | insurance policy if UCSB parsing stalls |

## 3. Licensing finding (the D002 gate)

The D002 stretch goal — a fully public / third-party-developer API — is gated on PV data
permitting redistribution. Per-source verdict:

| Source | License (verbatim) | Redistributable via public API? | Basis |
|---|---|---|---|
| **MIT Election Lab** | **CC0 1.0 Universal** — URI `http://creativecommons.org/publicdomain/zero/1.0` (Harvard Dataverse dataset `doi:10.7910/DVN/42MVDX`; no custom `termsOfUse` attached) | **YES — cleared.** CC0 is a public-domain dedication: redistribution, commercial use, and derivatives are all permitted with no attribution or permission required. | Harvard Dataverse dataset metadata (license object), verified 2026-07-13 |
| **UCSB / American Presidency Project** | UCSB Terms of Use: *"Other materials accessible within UCSB Web space, without explicit permission, may not be copied, reproduced, republished, uploaded, posted, transmitted, or distributed in any way,"* with only a *"personal non-commercial home use"* exception. APP's About page carries only `Copyright © The American Presidency Project` and defers to these general terms — **no data-specific open license.** | **NO — needs permission** (`policy@ucsb.edu`). Consistent with D008's note of no licensing reply to date. | UCSB Terms of Use + APP About page |
| **ICPSR Study 1 / 79** | Free to ICPSR-member institutions; not an open public-redistribution license | **NO — member access only** | ICPSR study terms |
| **Dave Leip's Atlas** | Proprietary, paywalled; explicitly not for redistribution | **NO** | uselectionatlas.org terms |
| **Wikipedia per-election articles** | CC BY-SA | **YES, with attribution + share-alike** — but provenance below citation bar | Wikimedia licensing |

**Net:** exactly one in-hand source — **MIT (CC0)** — is publicly redistributable, and it is
the modern core. That is enough to ship the public API for 1976–2024. Every pre-1976 (UCSB)
row is tagged `source=UCSB`, `redistributable=false` (E4 / #37) and excluded from the public
surface (D014). No outreach is required to unblock the API.

## 4. MIT Election Lab — data characterization (E3-S1)

**Source file examined:** `~/Documents/Projects/data/presidential_vote_analysis/1976-2024-president.csv`
(downloaded by Fred; lives outside the repo, under the shared external data directory).
**Upstream:** Harvard Dataverse `doi:10.7910/DVN/42MVDX` (MEDSL "U.S. President 1976–…").

| Property | Value |
|---|---|
| Rows | 4,822 |
| Elections covered | **13 — 1976, 1980, …, 2024** (every 4 years) |
| Earliest year | **1976** (the coverage constraint) |
| Jurisdictions | 51 (50 states + DC) |
| Office | US President only |
| Grain | one row per **(year, state, candidate)** |
| Vote fields | `candidatevotes` (candidate's votes in that state), `totalvotes` (state total across all candidates) |
| Candidate metadata | `candidate`, `party_detailed`, `party_simplified`, `writein` (bool) |
| Geo metadata | `state_po` (USPS), `state_fips`, `state_cen`, `state_ic` |
| Housekeeping | `version`, `notes` |
| **License** | **CC0 1.0** (public-domain dedication; no custom terms) — see §3 |

**Strengths**
- State-level candidate totals are exactly the grain the fact table needs; national PV is a
  trivial roll-up (`sum(candidatevotes)` by year, or `sum` of state `totalvotes`).
- 50 states + DC aligns cleanly with the EC state dimension (DC has had electoral votes
  since 1964, so the modern-era join is 1:1 on geography).
- Covers both **modern EC/PV splits — 2000 and 2016** — so the headline modern flip analysis
  is fully supported by MIT alone.
- `writein` + party fields make it easy to filter to the MVP candidate scope (D007: only
  candidates who received electoral votes) and drop the minor-candidate long tail.
- **CC0** means the modern core is public-API-eligible with zero licensing friction.

**Frictions to handle downstream**
- **Name format differs from the EC source.** MIT uses `"BIDEN, JOSEPH R. JR"`,
  `"TRUMP, DONALD J."`; the National Archives EC data uses `"Donald Trump"`. Reconciliation
  is the job of the canonical candidate key (D006 / issue #30, E2-S9).
- **Long tail grows steeply in recent cycles** — distinct candidate names per year run from
  16 (1976) to **167 (2024)**, mostly write-ins. Not a problem under D007 (filter to
  EC-getting candidates), but worth noting for anyone loading the raw file wholesale.

## 5. UCSB / American Presidency Project — data characterization (E3-S2)

**Source examined:** the APP election-statistics pages at
`https://www.presidency.ucsb.edu/statistics/elections/{year}` (index at
`/statistics/elections`). Raw HTML for **all 60 election years is already snapshotted
locally** at `~/Documents/Projects/data/presidential_vote_analysis/ucsb_raw/` (one
`{year}.html` per election 1789–2024, plus the index page). This pre-satisfies the E4
snapshot story (#34) — the parse/transform work builds on files already on disk, no live
scrape needed.

| Property | Value |
|---|---|
| Elections covered | **60 — every election 1789–2024** (the full MVP span and then some) |
| Earliest year | **1789** (reaches the entire ~1824 window and the pre-12th-Amendment era) |
| Jurisdictions | per-**state** rows (one row per state), plus a national total row |
| Office | US President |
| Grain | one row per **(year, state)** with candidate votes spread **across columns**, not one row per (year, state, candidate) as MIT is — melting required |
| Vote fields | per state: `TOTAL VOTE`; per candidate group: `Votes`, `%`, `EV` (electoral votes) |
| Candidate metadata | candidate name + party in the per-year header band; party also encoded by cell `bgcolor` |
| Format | one `<table class="table table-responsive">` per year; candidate column-groups built with `colspan`/`rowspan` multi-row headers; **the number of candidate groups drifts year to year** (e.g. 2 in 1876, 4 in 1824) |
| **License** | UCSB Terms of Use — **no reuse grant**, `redistributable=false` — see §3 |

**Strengths**
- **Coverage is the whole point.** 1789–2024 per state covers every pre-1976 election MIT
  cannot — including the decisive EC/PV splits of **1876 and 1888** and the **1824**
  contingent election. This is the historical-breadth half of D014 and the only source in
  hand reaching the ~1824 MVP floor (D009).
- Per-state grain with candidate `Votes` + `%` + `EV` is rich enough to roll up national PV
  and to cross-check against the EC spine's electoral counts.
- Already snapshotted locally, so ingestion is a pure parse/transform problem with no network
  fragility.

**Frictions to handle downstream (this is why E4 mirrors the EC scrape, not a CSV read)**
- **Wide, not long.** Candidates live in columns, so parsing must melt (year, state) × N
  candidate groups into per-(year, state, candidate) records — the same melt shape as the EC
  `votes_by_state` matrix.
- **Heavy era drift.** The count and layout of candidate column-groups changes every era; the
  `colspan`/`rowspan` header structure must be parsed generically, not by fixed column index.
  This is the core risk #35 calls out.
- **Missing popular vote by design.** Early elections mark states whose electors were **chosen
  by the legislature** (1824: Delaware, Georgia, Louisiana, New York, South Carolina, Vermont),
  with no PV — these must be flagged with provenance, **not** coerced to zero (D005/D014).
- **Name format differs from the Archives** (and from MIT), so UCSB names also reconcile via
  the canonical candidate/state keys (#30, #38).
- **Footnote/annotation rows** appear at table bottom (e.g. 1824's "elected by the House of
  Representatives") — parsing must not mistake them for data rows.

## 6. Other PV sources scanned (fallback context, not a second deep dive)

Lightweight per D008 — the point is a defensible comparison and a known fallback, not to
re-open the dual-source decision.

| Source | Coverage / grain | Format | License posture | One-line viability |
|---|---|---|---|---|
| **ICPSR Study 1 — US Historical Election Returns, 1824–1968** ([link](https://www.icpsr.umich.edu/web/ICPSR/studies/1)) | **county-level**, 1824–1968, all parties | structured data files (curated) | free **to ICPSR-member institutions**; not an open public-redistribution license | **Strongest fallback** if UCSB parsing stalls — cleaner structured returns reaching 1824, and Fred's MIT-affiliation may confer member access; finer (county) grain than we need, roll up to state. A companion study (ICPSR 79) covers **1788–1823**. |
| **Dave Leip's Atlas of U.S. Presidential Elections** ([uselectionatlas.org](https://uselectionatlas.org)) | state (and county) level, 1789–present | web / paid data downloads | **proprietary, paywalled**; explicitly not for redistribution | Authoritative and complete but commercial — usable as a **validation cross-check**, not a redistributable source. |
| **Wikipedia per-election articles** | state-level, 1789–present | HTML infobox/tables | **CC BY-SA** (redistributable *with* attribution + share-alike) | The only clearly **redistributable** historical option, but crowd-sourced provenance is below our citation bar; possible tie-breaker/gap-filler, not a primary. |
| **CQ Press — *Guide to U.S. Elections*** | state-level, comprehensive | print / licensed database | commercial license | Gold-standard reference; licensing cost + no bulk data feed make it impractical here. |

**Best fallback if the MIT path stalls or UCSB parsing proves intractable:** **ICPSR Study 1
(+ Study 79 for 1788–1823)** — structured, academically authoritative, reaches 1824 (and
earlier), and access is plausibly available through Fred's institutional affiliation. It
would not change the redistributability picture (still analysis-only, not an open license),
but it de-risks the *parsing* effort that is E4's main cost. UCSB remains the primary
historical source because its data is already snapshotted and its per-state grain matches the
spine; ICPSR is the insurance policy.

## 7. The coverage gap and why dual-source is required

MIT: **1976–2024** (13 elections). The MVP comparison window starts **~1824** (D009). Every
pre-1976 election in scope — including the historically decisive EC/PV splits of **1876 and
1888**, and the contingent election of **1824** — is outside MIT's range. UCSB / American
Presidency Project is (per Fred) the most complete PV dataset available and reaches back to
the early republic, but only as **raw HTML** requiring a scrape, and under a **restrictive
usage license** (analysis-only). Hence D014: use both, with clearly separated roles and
per-source provenance. Where PV is unavailable by design (legislature-chosen electors) it is
flagged with provenance, never fabricated (D005).

## 8. MIT outreach — now optional (licensing resolved)

The E3 recommendation originally carried two open questions for MIT outreach. Their status:

1. **Usage license — does MIT's license permit public-API redistribution?**
   **RESOLVED (§3): CC0 1.0 — yes.** No outreach needed. The D002 gate is cleared for the
   modern core.
2. **Coverage extension — any plans to extend the dataset before 1976?**
   **Still open, but optional.** Even partial pre-1976 backfill would shift the MIT-vs-UCSB
   division of labor (letting more of the historical window ride on the redistributable
   source). This is the *only* remaining reason to reach out, and it is a nice-to-have, not a
   gate. Per epic #13, outreach stays deferred until analysis back to at least 1976 is in hand.

### Outreach contacts (documented for when/if the coverage question is pursued)

- **Zayne Sember** — https://www.linkedin.com/in/zaynesember/ — published the most recent MIT
  Election Lab dataset (the 1976–2024 president file); lead contact.
- **Sean Greene** — https://www.linkedin.com/in/sean-greene-a467097/ — additional contact.

## 9. What this unblocks

- **MIT PV ingestion (E5)** can be scoped against a known schema/grain (§4) — a clean CSV
  load, distinct from and much simpler than the UCSB scrape epic — and its output is
  **public-API-eligible** (CC0), so E5 rows carry `source=MIT`, `redistributable=true`.
- **The public API (D002 stretch goal)** is un-gated for 1976–2024: no licensing blocker
  remains for the modern core.
- **The EC+PV join (E6)** can assume a two-source fact table where every row carries `source`
  + a `redistributable` flag (extends D005), the public surface filtering to
  `redistributable=true`.
- **Canonical-key reconciliation (#30, #38)** has a concrete second- and third-source name
  format (MIT `"LAST, FIRST M."`; UCSB header-band names) to design against.
- **The UCSB scrape epic (E4)** is confirmed necessary and un-deferred (D014) — only it
  reaches the pre-1976 span — and confirmed analysis-only (§3).
- **Decision recorded — D016 (source determination finalized):** records that E3 confirms
  the D014 dual-source split *and* resolves the D008/D002 licensing gate (MIT = CC0, publicly
  redistributable; UCSB = analysis-only pending permission). See
  [`decisions.md`](decisions.md) **D016**.

## 10. Story checklist

- [x] E3-S1 (#15) — characterize MIT Election Lab (coverage, grain, format, **license: CC0**).
      **Done (§4, §3).**
- [x] E3-S2 (#16) — characterize UCSB / American Presidency Project (coverage, grain, HTML
      structure across eras, license status) + note other alternatives. **Done (§5–§6).**
- [x] E3-S3 (#20) — consolidate into the final recommendation (§1), with the explicit MIT
      licensing finding (§3) and a per-source coverage/redistributability comparison (§2).
      **Done — closes E3.**
