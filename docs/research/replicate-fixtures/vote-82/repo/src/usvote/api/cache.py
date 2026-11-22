"""HTTP freshness for the ``/v1`` surface — a content-hash ETag + ``Cache-Control``.

The ETag is a **process constant**: the whole-snapshot ``snapshot_version`` (a content
hash, D028), identical for every row of an immutable snapshot. So there is no per-body
hashing — the conditional-request logic is pure string handling, extracted here into
:func:`etag_for` / :func:`if_none_match_satisfied` and unit-tested directly (the
"validation is load-bearing" rule), with :func:`cache_dependency` the thin FastAPI
adapter that a ``/v1`` router hangs off so E8-S3 endpoints inherit the headers with no
per-route code.

Emitting these **locally** (not only behind a CDN) is deliberate: the eventual Cloud Run
+ CDN path (E8-S7 / D031/D032) then becomes a config change, not a code change.
"""

from __future__ import annotations

from fastapi import Request, Response
from starlette.status import HTTP_304_NOT_MODIFIED

#: The ``Cache-Control`` served on every ``/v1`` response (D031/D034). Deliberately a
#: *moderate* browser ``max-age`` — **not** ``immutable, max-age=1yr`` — so a rare
#: bug-fix redeploy reflects promptly instead of stranding a stale response in a browser
#: for a year. The *long* hold lives at the CDN edge (a Cloudflare Edge Cache TTL,
#: purged on each new snapshot version — D034), which is purge-reachable; a long
#: ``s-maxage`` here is not, so unreachable intermediaries could strand stale data.
#: ``stale-while-revalidate`` lets the edge serve slightly-stale while it refreshes;
#: ``stale-if-error`` keeps reads answerable if the zero-scaled origin is unreachable.
CACHE_CONTROL = (
    "public, max-age=3600, stale-while-revalidate=86400, stale-if-error=86400"
)


def etag_for(snapshot_version: str) -> str:
    """Return the RFC-7232 entity-tag for a snapshot version (a quoted string).

    A strong validator: the snapshot is immutable and the version is its content hash,
    so equal versions are byte-identical responses.
    """
    return f'"{snapshot_version}"'


def if_none_match_satisfied(if_none_match: str | None, etag: str) -> bool:
    """Return whether an ``If-None-Match`` header value matches ``etag`` (⇒ 304).

    Implements the RFC-7232 §3.2 comparison for a conditional GET: ``*`` matches any
    current representation; otherwise the header is a comma-separated list of entity-
    tags and a match is a weak comparison (the ``W/`` prefix is ignored, since our tag
    is strong and weak-equality is the required test for ``If-None-Match``). Returns
    ``False`` for an absent/blank header.
    """
    if not if_none_match:
        return False
    candidates = [c.strip() for c in if_none_match.split(",")]
    if "*" in candidates:
        return True
    target = etag.removeprefix("W/")
    return any(c.removeprefix("W/") == target for c in candidates)


class NotModified(Exception):  # noqa: N818 — not an error condition; a 304 signal
    """Signals a conditional-GET hit — the app handler turns it into a bare ``304``.

    Carried as an exception (not a returned ``Response``) because only a raise
    short-circuits a FastAPI dependency before the route body runs. ``etag`` is echoed
    back on the 304 so a CDN/client re-validates against the same tag.
    """

    def __init__(self, etag: str) -> None:
        super().__init__("resource not modified")
        self.etag = etag


def cache_dependency(request: Request, response: Response) -> None:
    """A ``/v1`` route dependency: stamp freshness headers; raise 304 on a match.

    Reads the live ``snapshot_version`` off ``request.app.state.repository`` so the ETag
    always reflects the loaded snapshot. Sets ``ETag`` + ``Cache-Control`` on every
    ``/v1`` response, and — when the client's ``If-None-Match`` already holds this
    version — raises :class:`NotModified`, which the app's handler turns into a bodyless
    ``304``. Health/liveness routes deliberately do **not** use this (they are
    ``no-store``); only ``/v1`` responses are cacheable.
    """
    etag = etag_for(request.app.state.repository.snapshot_version)
    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = CACHE_CONTROL
    if if_none_match_satisfied(request.headers.get("if-none-match"), etag):
        raise NotModified(etag)


def not_modified_handler(request: Request, exc: Exception) -> Response:
    """App exception handler: render :class:`NotModified` as a bare ``304``.

    A 304 carries no body; only the validators are echoed. Registered on the app in
    :func:`usvote.api.app.create_app`.
    """
    # Registered only for NotModified, so this always holds; assert rather than fall
    # back to an empty ETag, which would silently mask a mis-registration.
    assert isinstance(exc, NotModified)
    return Response(
        status_code=HTTP_304_NOT_MODIFIED,
        headers={"ETag": exc.etag, "Cache-Control": CACHE_CONTROL},
    )
