"""The shared synthetic snapshot fixture for the API tests (E8-S5, #99).

The whole API test surface (``test_api_app`` #96, ``test_api_endpoints`` #97,
``test_api_openapi`` #98, the E2E walk and the redistributable guard #99) is served
from **one** synthetic ``ec_pv_redistributable``-shaped frame defined here, so a
snapshot-schema change updates a single fixture rather than the several near-identical
``_row``/``_frame`` copies these tests used to carry.

**Built, never committed.** There is no checked-in ``.sqlite`` binary — the pytest
fixtures in ``tests/unit/conftest.py`` materialize this frame through the real
:func:`usvote.snapshot.build_snapshot` writer at test time, so the fixture can never
drift from the actual snapshot schema (the issue's anti-drift note).

**Synthetic, and safe to commit.** Values are fabricated (mirroring the D022
synthetic-fixture posture), but unlike the UCSB corpus this data is EC/MIT/CC0-shaped
and carries **no** licensing restriction — every row is ``source="MIT"``,
``redistributable=True``. No real UCSB bytes are involved.

The frame deliberately encodes a real **"EC winner ≠ PV winner"** flip year in the
1976–2024 redistributable window (2016): the candidate who *took office* leads the
Electoral College but **trails** the national popular vote — so the national-summary /
flip assertions the API exposes are meaningful. 2020 is an ordinary split year (its
rows are kept byte-for-byte compatible with #97's original endpoint assertions).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd

#: Deterministic build timestamp so a snapshot's content hash (and thus the ETag) is
#: stable across test runs. Informational only — excluded from the content hash (D028).
SNAPSHOT_TS = datetime(2026, 7, 23, 12, 0, tzinfo=UTC)

#: State full-name → USPS code, for the states this fixture builds rows for.
_USPS = {"Texas": "TX", "California": "CA"}


def api_snapshot_row(
    *,
    year: int,
    state: str,
    candidate_id: int,
    candidate: str,
    president_ev: int,
    national_ev: int,
    rank: int,
    took_office: bool,
    candidate_votes: int | None,
    state_total: int | None,
    total_ev: int,
    source: str | None = "MIT",
    party: str | None = None,
    reliability: str | None = "exact",
    redistributable: bool = True,
) -> dict[str, object]:
    """One ``build_snapshot`` input row (``join.EC_PV_COLUMNS`` + ``state_usps``).

    Keyword-only so a caller reads at a glance and can't transpose the many ints. The
    ``source`` / ``redistributable`` overrides exist so the redistributable-only guard
    test (#99) can craft a deliberately non-redistributable row and assert the build
    fails loud; the happy-path fixtures never override them.
    """
    if party is None:
        party = "DEMOCRAT" if candidate == "Cand B" else "REPUBLICAN"
    return {
        "year": year,
        "state": state,
        "state_usps": _USPS[state],
        "candidate_id": candidate_id,
        "candidate": candidate,
        "total_electoral_votes": total_ev,
        "president_electoral_votes": president_ev,
        "national_electoral_votes": national_ev,
        "president_electoral_rank": rank,
        "took_office": took_office,
        "source": source,
        "party": party,
        "candidate_votes": candidate_votes,
        "state_total_votes": state_total,
        "reliability": reliability,
        "redistributable": redistributable,
    }


def synthetic_ec_pv_frame() -> pd.DataFrame:
    """The canonical synthetic ``ec_pv_redistributable`` input frame.

    Two candidates (``Cand A`` / ``Cand B``) × two states (Texas / California) across
    two years:

    - **2016 — the flip.** ``Cand B`` takes office with the larger national EC total
      (55 vs 38) but the *smaller* national popular vote (13,000,000 vs 18,000,000):
      an "EC winner ≠ PV winner" year, so ``/v1/elections/2016/summary`` can be asserted
      to expose the flip. (``national_electoral_votes`` equals the sum of the candidate's
      per-state ``president_electoral_votes``, matching the real view's window sum.)
    - **2020 — ordinary split.** ``Cand A`` wins Texas, ``Cand B`` wins California and
      takes office (national EC 55 vs 38). These rows match #97's original fixture so its
      value-specific rollup assertions carry over unchanged.
    """
    return pd.DataFrame(
        [
            # 2016 — national flip: B took office (EC 55) but A won the PV (18M vs 13M).
            # national_ev == sum of the candidate's per-state president_ev (A: 38+0=38,
            # B: 0+55=55), so the fixture matches the real view's window sum.
            api_snapshot_row(
                year=2016, state="Texas", candidate_id=1, candidate="Cand A",
                president_ev=38, national_ev=38, rank=2, took_office=False,
                candidate_votes=8_000_000, state_total=14_000_000, total_ev=38,
            ),
            api_snapshot_row(
                year=2016, state="California", candidate_id=1, candidate="Cand A",
                president_ev=0, national_ev=38, rank=2, took_office=False,
                candidate_votes=10_000_000, state_total=17_000_000, total_ev=55,
            ),
            api_snapshot_row(
                year=2016, state="Texas", candidate_id=2, candidate="Cand B",
                president_ev=0, national_ev=55, rank=1, took_office=True,
                candidate_votes=6_000_000, state_total=14_000_000, total_ev=38,
            ),
            api_snapshot_row(
                year=2016, state="California", candidate_id=2, candidate="Cand B",
                president_ev=55, national_ev=55, rank=1, took_office=True,
                candidate_votes=7_000_000, state_total=17_000_000, total_ev=55,
            ),
            # 2020 — split: A wins TX (38), B wins CA (55, rank 1, took office).
            api_snapshot_row(
                year=2020, state="Texas", candidate_id=1, candidate="Cand A",
                president_ev=38, national_ev=38, rank=2, took_office=False,
                candidate_votes=5_000_000, state_total=11_000_000, total_ev=38,
            ),
            api_snapshot_row(
                year=2020, state="Texas", candidate_id=2, candidate="Cand B",
                president_ev=0, national_ev=55, rank=1, took_office=True,
                candidate_votes=6_000_000, state_total=11_000_000, total_ev=38,
            ),
            api_snapshot_row(
                year=2020, state="California", candidate_id=1, candidate="Cand A",
                president_ev=0, national_ev=38, rank=2, took_office=False,
                candidate_votes=6_000_000, state_total=17_000_000, total_ev=55,
            ),
            api_snapshot_row(
                year=2020, state="California", candidate_id=2, candidate="Cand B",
                president_ev=55, national_ev=55, rank=1, took_office=True,
                candidate_votes=11_000_000, state_total=17_000_000, total_ev=55,
            ),
        ]
    )
