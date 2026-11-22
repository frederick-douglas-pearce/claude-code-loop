"""The ``/v1`` data endpoints (E8-S3, #97) — by year / state / candidate + summary.

Every handler reads **only** through :class:`~usvote.api.repository.SnapshotRepository`
(no SQL, parsing, aggregation, or computation; the roll-up and slug are precomputed
in the snapshot, #95) and returns a typed Pydantic model wrapped in the shared
``{data, meta}`` envelope.

**Why the cache logic is called manually, not as a router dependency.** The ``/v1`` ETag
is a whole-snapshot constant, so a blanket ``cache_dependency`` (as ``/v1/meta`` uses)
would raise a 304 for *any* matching ``If-None-Match`` **before** the handler could tell
whether the resource exists — an unknown year would 304 instead of 404. So each data
handler validates existence first (→ 404), and only then calls
:func:`~usvote.api.cache.cache_dependency` to stamp the ETag / ``Cache-Control`` and
short-circuit a genuine conditional hit. A 404 never carries cacheable headers.

Import boundary (D028): fastapi + the models/repository/cache siblings only — no pandas,
no DB.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request, Response
from starlette.status import HTTP_404_NOT_FOUND

from usvote.api import models
from usvote.api.cache import cache_dependency
from usvote.api.repository import SnapshotRepository

#: 422 Unprocessable Content. Spelled as the literal to dodge starlette's churn on the
#: constant's name (``…_ENTITY`` → ``…_CONTENT``); the code itself is stable.
_HTTP_422 = 422

router = APIRouter()

_NOT_FOUND_RESPONSE: dict[int | str, dict[str, object]] = {
    HTTP_404_NOT_FOUND: {"model": models.ErrorBody}
}


class ResourceNotFound(Exception):
    """A requested path identifier (year / state / candidate) is not in the snapshot.

    Rendered as a typed :class:`~usvote.api.models.ErrorBody` 404 by an app handler — a
    clean, uncacheable body, never a stack trace (#97).
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _repo(request: Request) -> SnapshotRepository:
    repo: SnapshotRepository = request.app.state.repository
    return repo


def _meta(repo: SnapshotRepository, count: int) -> models.Meta:
    """Build the envelope ``meta`` — snapshot provenance + this response's ``count``.

    Provenance comes straight from the cached snapshot metadata (drift-proof),
    resolved to its public display via ``Provenance.from_snapshot_meta``.
    """
    return models.Meta(
        provenance=models.Provenance.from_snapshot_meta(repo.meta()),
        count=count,
    )


def _validate_year_range(year_from: int | None, year_to: int | None) -> None:
    """Reject an inverted window with a 422 (a bad param, not a silently-empty 200)."""
    if year_from is not None and year_to is not None and year_from > year_to:
        raise HTTPException(
            status_code=_HTTP_422,
            detail=f"year_from ({year_from}) must not exceed year_to ({year_to}).",
        )


_YEAR_FROM = Query(None, description="Only include years >= this value.")
_YEAR_TO = Query(None, description="Only include years <= this value.")


@router.get(
    "/elections",
    response_model=models.Envelope[models.YearListItem],
    summary="List the election years the snapshot covers.",
    tags=["Elections"],
)
def list_elections(
    request: Request,
    response: Response,
    year_from: int | None = _YEAR_FROM,
    year_to: int | None = _YEAR_TO,
) -> models.Envelope[models.YearListItem]:
    """Every covered (redistributable) year with its distinct-candidate count."""
    _validate_year_range(year_from, year_to)
    repo = _repo(request)
    cache_dependency(request, response)
    rows = repo.list_years(year_from, year_to)
    data = [models.YearListItem.model_validate(r) for r in rows]
    return models.Envelope(data=data, meta=_meta(repo, len(data)))


@router.get(
    "/elections/{year}",
    response_model=models.ElectionResponse,
    responses=_NOT_FOUND_RESPONSE,
    summary="One election: per-state rows plus the national roll-up.",
    tags=["Elections"],
)
def get_election(
    year: int,
    request: Request,
    response: Response,
    state: str | None = Query(None, description="Narrow to one USPS state code."),
    candidate: str | None = Query(None, description="Narrow to one candidate slug."),
) -> models.ElectionResponse:
    """The state fact rows for a year (``data``) plus its roll-up (``summary``).

    An unknown or out-of-window year (e.g. pre-1976) is a 404, not an error. The
    optional ``state`` / ``candidate`` filters narrow ``data`` (and ``meta.count``); a
    filter that matches nothing is a 200 with an empty ``data`` (a filter, not a missing
    resource). ``summary`` is the **national** roll-up for the whole year and is
    deliberately *not* narrowed by those filters — national totals are the flip context,
    unchanged by a per-state/candidate view of the rows.
    """
    repo = _repo(request)
    if not repo.year_exists(year):
        raise ResourceNotFound("year_not_found", _unknown_year_message(repo, year))
    cache_dependency(request, response)
    rows = repo.rows_by_year(year, state=state, candidate=candidate)
    summary = repo.rollup_by_year(year)
    data = [models.EcPvRow.model_validate(r) for r in rows]
    return models.ElectionResponse(
        data=data,
        summary=[models.NationalSummaryRow.model_validate(s) for s in summary],
        meta=_meta(repo, len(data)),
    )


@router.get(
    "/elections/{year}/summary",
    response_model=models.Envelope[models.NationalSummaryRow],
    responses=_NOT_FOUND_RESPONSE,
    summary="The national roll-up for one election year.",
    tags=["Elections"],
)
def get_election_summary(
    year: int,
    request: Request,
    response: Response,
) -> models.Envelope[models.NationalSummaryRow]:
    """Per-candidate national EC + PV totals (+ denominator) for a year.

    Reads the precomputed ``national_rollup`` — no aggregation in the handler. No
    hybrid / flip / margin (those are E8-S8).
    """
    repo = _repo(request)
    # Gate on the roll-up itself (not ``ec_pv`` via ``year_exists``): existence and the
    # data served are then the *same* source, so this can't 200-with-empty on a
    # (build-regression) year present in the fact but absent from the roll-up.
    rows = repo.rollup_by_year(year)
    if not rows:
        raise ResourceNotFound("year_not_found", _unknown_year_message(repo, year))
    cache_dependency(request, response)
    data = [models.NationalSummaryRow.model_validate(r) for r in rows]
    return models.Envelope(data=data, meta=_meta(repo, len(data)))


@router.get(
    "/states/{usps}",
    response_model=models.Envelope[models.EcPvRow],
    responses=_NOT_FOUND_RESPONSE,
    summary="One state's rows across every covered year.",
    tags=["States"],
)
def get_state(
    usps: str,
    request: Request,
    response: Response,
    year_from: int | None = _YEAR_FROM,
    year_to: int | None = _YEAR_TO,
) -> models.Envelope[models.EcPvRow]:
    """All EC+PV rows for one state (by USPS code) across the covered window."""
    _validate_year_range(year_from, year_to)
    repo = _repo(request)
    if not repo.state_exists(usps):
        raise ResourceNotFound(
            "state_not_found",
            f"No state with USPS code {usps.upper()!r} in the snapshot.",
        )
    cache_dependency(request, response)
    rows = repo.rows_by_state(usps, year_from=year_from, year_to=year_to)
    data = [models.EcPvRow.model_validate(r) for r in rows]
    return models.Envelope(data=data, meta=_meta(repo, len(data)))


@router.get(
    "/candidates/{slug}",
    response_model=models.Envelope[models.EcPvRow],
    responses=_NOT_FOUND_RESPONSE,
    summary="One candidate's rows across every covered year.",
    tags=["Candidates"],
)
def get_candidate(
    slug: str,
    request: Request,
    response: Response,
    year_from: int | None = _YEAR_FROM,
    year_to: int | None = _YEAR_TO,
) -> models.Envelope[models.EcPvRow]:
    """All EC+PV rows for one candidate (by public slug) across the covered window.

    The slug is the durable public candidate id (D006); ``candidate_id`` is never a path
    key or a response field.
    """
    _validate_year_range(year_from, year_to)
    repo = _repo(request)
    if not repo.candidate_exists(slug):
        raise ResourceNotFound(
            "candidate_not_found",
            f"No candidate with slug {slug.lower()!r} in the snapshot.",
        )
    cache_dependency(request, response)
    rows = repo.rows_by_candidate(slug, year_from=year_from, year_to=year_to)
    data = [models.EcPvRow.model_validate(r) for r in rows]
    return models.Envelope(data=data, meta=_meta(repo, len(data)))


def _unknown_year_message(repo: SnapshotRepository, year: int) -> str:
    m = repo.meta()
    return (
        f"No election data for year {year}; the snapshot's redistributable window is "
        f"{m.year_min}–{m.year_max}."
    )
