"""Pydantic response models + the shared ``{data, meta}`` envelope (E8-S3, #97).

The public surface of the API. Each snapshot column (:mod:`usvote.snapshot_schema`
``DATA_COLUMNS`` / ``ROLLUP_COLUMNS``) maps to a **field on one of these models** whose
name reads naturally to an external consumer — the ``president_*`` internal prefix (this
candidate's per-state electoral votes, not "the president's") is renamed to a clearer
public name. The snapshot column is the field's ``validation_alias`` (input only), so a
row keyed by snapshot columns validates directly (``model_validate(dict(row))``) while
the response serializes back under the **public field name** (FastAPI dumps
``by_alias=True``, falling back to the field name when only a validation alias is set).

That column↔field mapping is the single source of truth a drift guard keys off
(``tests/unit/test_api_models.py``): every ``DATA_COLUMNS`` / ``ROLLUP_COLUMNS`` entry
must be a field name / validation alias on its model or on :data:`_DROPPED_COLUMNS`, so
a column added to the snapshot contract cannot silently fail to surface.

Boundary (D028): pydantic + :mod:`usvote.snapshot_schema` only (no pandas, no DB).
"""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from usvote.api import provenance
from usvote.snapshot_schema import SnapshotMeta

#: Snapshot columns intentionally **not** on any public model. Empty today (every
#: ``ec_pv`` / ``national_rollup`` column is exposed under a public name), but the drift
#: guard reads this list, so a deliberately-internal future column has an explicit home
#: here rather than silently failing the completeness assert.
_DROPPED_COLUMNS: frozenset[str] = frozenset()


def _config(example: dict[str, Any]) -> ConfigDict:
    """Row config that also carries one OpenAPI example (in public field names).

    ``populate_by_name=True`` lets a snapshot row validate by ``validation_alias`` *and*
    lets an example authored in the **public** field name validate — so the examples
    Swagger renders are exactly what an external consumer sends/receives, and the
    ``test_api_models`` drift guard can ``model_validate`` each one (D004: validation is
    load-bearing).
    """
    return ConfigDict(populate_by_name=True, json_schema_extra={"examples": [example]})


# Realistic examples, authored once as module constants so the drift guard can import
# and ``model_validate`` them. The 2000 Bush/Florida observation is the canonical
# figure — the election the whole thesis is built around (lost the PV, took office).
_COVERAGE_EXAMPLE: dict[str, Any] = {"year_min": 1976, "year_max": 2024}

_EC_PV_ROW_EXAMPLE: dict[str, Any] = {
    "year": 2000,
    "state": "Florida",
    "state_usps": "FL",
    "candidate": "George W. Bush",
    "candidate_slug": "george-w-bush",
    "state_electoral_votes": 25,
    "electoral_votes": 25,
    "national_electoral_votes": 271,
    "electoral_rank": 1,
    "took_office": True,
    "source": "MIT",
    "party": "REPUBLICAN",
    "popular_votes": 2912790,
    "state_popular_total": 5963110,
    "reliability": "exact",
}

_NATIONAL_SUMMARY_EXAMPLE: dict[str, Any] = {
    "year": 2000,
    "candidate": "Albert Gore Jr.",
    "candidate_slug": "albert-gore-jr",
    "party": "DEMOCRAT",
    "national_electoral_votes": 266,
    "electoral_rank": 2,
    "took_office": False,
    "national_pv_votes": 50996062,
    "national_pv_denominator": 105593982,
}

_YEAR_LIST_EXAMPLE: dict[str, Any] = {"year": 2000, "candidate_count": 7}

# Derive every display field from the provenance maps (not literals), so the shipped
# example can't drift from _SOURCES / _LICENSES if a name or URL is ever edited.
_EX_SRC = provenance.source_display("MIT")
_EX_LIC = provenance.license_display("CC0-1.0")

_PROVENANCE_EXAMPLE: dict[str, Any] = {
    "snapshot_version": (
        "bc6056f38fd9ed04f396a2e54a38a657994a4d8f0a8a317526e47bfb92cd33f2"
    ),
    "source": _EX_SRC.code,
    "source_name": _EX_SRC.name,
    "license": _EX_LIC.code,
    "license_url": _EX_LIC.url,
    "coverage": _COVERAGE_EXAMPLE,
    "redistributable_note": provenance.redistributable_note(_EX_SRC, _EX_LIC),
}

_META_EXAMPLE: dict[str, Any] = {"provenance": _PROVENANCE_EXAMPLE, "count": 2}

_SNAPSHOT_META_RESPONSE_EXAMPLE: dict[str, Any] = {
    "provenance": _PROVENANCE_EXAMPLE,
    "schema_version": 1,
    "row_count": 1734,
    "candidate_count": 25,
    "build_timestamp": "2026-07-24T01:05:05.969957+00:00",
}

_ERROR_EXAMPLE: dict[str, Any] = {
    "error": {
        "code": "year_not_found",
        "message": (
            "No election data for year 1800; the snapshot's redistributable window is "
            "1976–2024."
        ),
    }
}


class EcPvRow(BaseModel):
    """One joined EC+PV fact row — a single ``(year, state, candidate)`` observation.

    The ``electoral_*`` / ``popular_*`` fields are renamed from the snapshot's internal
    ``president_*`` / ``candidate_votes`` / ``*_total_votes`` columns for a reader.
    PV fields are ``None`` for an EC getter MIT does not cover (an honest gap, never a
    fabricated 0) — see ``docs/api-snapshot.md``.
    """

    model_config = _config(_EC_PV_ROW_EXAMPLE)

    year: int = Field(description="Election year.")
    state: str = Field(description="Full state name (the canonical grain key).")
    state_usps: str = Field(description="USPS two-letter code, e.g. 'CA'.")
    candidate: str = Field(description="Canonical candidate display name.")
    candidate_slug: str = Field(
        description="Durable public candidate id (deterministic name slug)."
    )
    state_electoral_votes: int = Field(
        validation_alias="total_electoral_votes",
        description="The state's total electoral-vote allotment this year.",
    )
    electoral_votes: int = Field(
        validation_alias="president_electoral_votes",
        description="This candidate's electoral votes in this state (0 for a loser).",
    )
    national_electoral_votes: int = Field(
        description="This candidate's national EC total this year (window sum)."
    )
    electoral_rank: int = Field(
        validation_alias="president_electoral_rank",
        description="This candidate's national EC finishing rank (1 = most EVs).",
    )
    took_office: bool = Field(
        description="Whether this candidate assumed the presidency this term."
    )
    source: str | None = Field(
        default=None, description="PV data source (None where no PV is available)."
    )
    party: str | None = Field(
        default=None, description="Party of record (None where no PV is available)."
    )
    popular_votes: int | None = Field(
        default=None,
        validation_alias="candidate_votes",
        description="This candidate's popular votes in this state (None where no PV).",
    )
    state_popular_total: int | None = Field(
        default=None,
        validation_alias="state_total_votes",
        description="The state's total votes cast (source denominator; None if no PV).",
    )
    reliability: str | None = Field(
        default=None, description="PV reliability tag (None where no PV is available)."
    )


class NationalSummaryRow(BaseModel):
    """One per-candidate national roll-up row for a year (from ``national_rollup``).

    The flip-relevant national totals only — national EC, national PV, and the PV
    denominator. No hybrid / flip / margin (those are E8-S8).
    """

    model_config = _config(_NATIONAL_SUMMARY_EXAMPLE)

    year: int = Field(description="Election year.")
    candidate: str = Field(description="Canonical candidate display name.")
    candidate_slug: str = Field(description="Durable public candidate id.")
    party: str | None = Field(
        default=None, description="Party of record (None where no PV is available)."
    )
    national_electoral_votes: int = Field(
        description="This candidate's national electoral-vote total this year."
    )
    electoral_rank: int = Field(
        validation_alias="president_electoral_rank",
        description="National EC finishing rank (1 = most EVs).",
    )
    took_office: bool = Field(
        description="Whether this candidate assumed the presidency this term."
    )
    national_pv_votes: int | None = Field(
        default=None,
        description="This candidate's national popular-vote total (None where no PV).",
    )
    national_pv_denominator: int | None = Field(
        default=None,
        description="Total votes cast nationally this year (each state counted once).",
    )


class YearListItem(BaseModel):
    """One entry in the list-years index: a covered year and its candidate count."""

    model_config = _config(_YEAR_LIST_EXAMPLE)

    year: int = Field(description="A redistributable election year in the data.")
    candidate_count: int = Field(
        description="Distinct candidates with national roll-up rows this year."
    )


class Coverage(BaseModel):
    """The inclusive year window the snapshot contains (descriptive, not a promise)."""

    year_min: int = Field(description="Earliest election year in the snapshot.")
    year_max: int = Field(description="Latest election year in the snapshot.")


class Provenance(BaseModel):
    """Where every response's data came from — identical across the whole snapshot.

    The raw ``source`` / ``license`` codes and ``coverage`` / ``snapshot_version`` are
    read **straight from the snapshot metadata** (E8-S1) so they can't drift from what
    was actually built; the human ``source_name`` / ``license_url`` /
    ``redistributable_note`` are the presentation of those codes
    (:mod:`usvote.api.provenance`). The note makes the D030 redistributable boundary
    explicit: MIT (CC0) only, UCSB excluded.
    """

    model_config = _config(_PROVENANCE_EXAMPLE)

    snapshot_version: str = Field(description="Content-hash snapshot version (ETag).")
    source: str = Field(description="PV data source code, e.g. 'MIT'.")
    source_name: str = Field(description="Spelled-out source, e.g. 'MIT Election Lab'.")
    license: str = Field(description="PV data license code, e.g. 'CC0-1.0'.")
    license_url: str = Field(description="Canonical URL for the license.")
    coverage: Coverage = Field(description="The year window the snapshot contains.")
    redistributable_note: str = Field(
        description="Plain-language statement of the redistributable data boundary."
    )

    @classmethod
    def from_snapshot_meta(cls, meta: SnapshotMeta) -> Provenance:
        """Build from snapshot metadata, resolving the code → display mappings.

        Raises :class:`usvote.api.provenance.UnknownProvenanceCode` if the snapshot's
        source/license code has no public display — a new source must be mapped, never
        silently blanked.
        """
        src = provenance.source_display(meta.source)
        lic = provenance.license_display(meta.license)
        return cls(
            snapshot_version=meta.snapshot_version,
            source=src.code,
            source_name=src.name,
            license=lic.code,
            license_url=lic.url,
            coverage=Coverage(year_min=meta.year_min, year_max=meta.year_max),
            redistributable_note=provenance.redistributable_note(src, lic),
        )


class Meta(BaseModel):
    """The response envelope's ``meta`` block: provenance + this response's count.

    ``provenance`` is snapshot-scoped (the same on every response); ``count`` is
    response-scoped and is always ``len(data)`` for the response it accompanies — for an
    election detail response the sibling ``summary`` list is **not** counted.
    """

    model_config = _config(_META_EXAMPLE)

    provenance: Provenance = Field(description="Data source, license, and coverage.")
    count: int = Field(description="Number of items in this response's `data` array.")


class SnapshotMetaResponse(BaseModel):
    """The ``GET /v1/meta`` payload: full snapshot provenance plus build/ops details.

    ``provenance`` is the same block that rides in every response envelope's ``meta``;
    the remaining fields are operational (schema version, row/candidate counts, the
    informational build timestamp) — useful when inspecting the served snapshot.
    """

    model_config = ConfigDict(
        json_schema_extra={"examples": [_SNAPSHOT_META_RESPONSE_EXAMPLE]}
    )

    provenance: Provenance = Field(description="Data source, license, and coverage.")
    schema_version: int = Field(description="Snapshot serving-contract schema version.")
    row_count: int = Field(description="Number of `ec_pv` fact rows in the snapshot.")
    candidate_count: int = Field(description="Distinct candidates in the snapshot.")
    build_timestamp: str = Field(
        description="When the snapshot was built (informational; not part of the ETag)."
    )


T = TypeVar("T")


class Envelope(BaseModel, Generic[T]):
    """The standard ``{data, meta}`` response wrapper for a list payload."""

    data: list[T]
    meta: Meta


class ElectionResponse(BaseModel):
    """One election: its per-state fact rows plus the national roll-up (AC point 2).

    ``data`` carries the state rows; ``summary`` carries the per-candidate national
    roll-up. ``meta.count`` counts ``data`` only.
    """

    data: list[EcPvRow]
    summary: list[NationalSummaryRow]
    meta: Meta


class ErrorDetail(BaseModel):
    code: str = Field(description="Stable machine-readable error code.")
    message: str = Field(description="Human-readable explanation.")


class ErrorBody(BaseModel):
    """The typed body returned on a 404 (never a stack trace)."""

    model_config = ConfigDict(json_schema_extra={"examples": [_ERROR_EXAMPLE]})

    error: ErrorDetail
