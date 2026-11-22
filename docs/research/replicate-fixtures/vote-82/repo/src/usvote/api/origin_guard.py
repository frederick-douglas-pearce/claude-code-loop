"""Origin lock-down for the public deployment (E8-S7, #101 / D034).

When the deployed API is fronted by Cloudflare (D034), a bot could bypass the edge
rate-limits + WAF by hitting the raw Cloud Run ``run.app`` URL directly. To close that,
a Cloudflare Transform Rule injects a shared secret header on every proxied request, and
this guard **rejects any ``/v1`` request that lacks it** (403).

Enforcement is **opt-in and fail-open** (the architect-reviewed default): it activates
only when :data:`usvote.api.config.ORIGIN_SECRET_VAR` is set
(:attr:`ApiSettings.origin_secret`). Unset — local dev, the unit suite, the D033
container smoke test — means no enforcement, so those paths are unaffected. The
fail-open default is made **observable** rather than silent (a ``/health`` field + a
one-line startup log) so a dropped Secret-Manager binding in production is visible, and
a post-deploy check asserts the raw origin 403s.

``/health`` (and everything outside the ``/v1`` prefix) is **always exempt**: Cloud
Run's own startup/liveness probes and the D033 smoke test do not traverse Cloudflare, so
they never carry the secret.

Stdlib-only (:mod:`hmac`) + starlette — nothing new crosses the D028 ``usvote/api/``
import boundary (guarded by ``tests/unit/test_api_import_graph.py``).
"""

from __future__ import annotations

import hmac
import logging
from collections.abc import Awaitable, Callable

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

_LOG = logging.getLogger("usvote.api.origin_guard")

#: Header carrying the shared origin secret. Cloudflare injects it via a Transform Rule;
#: a direct-to-``run.app`` request from a bot will not have it. A custom name, unlikely
#: to collide with a real client header.
ORIGIN_SECRET_HEADER = "X-Usvote-Origin-Secret"

#: The 403 body a rejected direct-origin request receives. Mirrors the ``{error: {code,
#: message}}`` shape the ``/v1`` 404 handler uses, and is never cached.
_FORBIDDEN_BODY = {
    "error": {
        "code": "forbidden_origin",
        "message": (
            "Direct origin access is not permitted; requests must go through the "
            "public endpoint."
        ),
    }
}


def _make_guard(
    secret: str, protected_prefix: str
) -> Callable[[Request, Callable[[Request], Awaitable[Response]]], Awaitable[Response]]:
    """Build the HTTP-middleware coroutine that enforces the origin secret.

    Factored out (rather than nested in :func:`install_origin_guard`) so the comparison
    logic is unit-testable without spinning an app. Requests under ``protected_prefix``
    must present :data:`ORIGIN_SECRET_HEADER` equal to ``secret`` (constant-time
    compare); all other paths pass through untouched.
    """

    # Compare as bytes, not str: Starlette decodes header values as latin-1, so a
    # client can send a non-ASCII secret header — and hmac.compare_digest raises
    # TypeError on non-ASCII *str* (→ a 500 instead of a clean 403). Bytes comparison
    # has no ASCII restriction and is still constant-time.
    expected = secret.encode("utf-8")

    async def guard(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.url.path.startswith(protected_prefix):
            provided = request.headers.get(ORIGIN_SECRET_HEADER, "").encode("utf-8")
            if not hmac.compare_digest(provided, expected):
                return JSONResponse(
                    status_code=403,
                    content=_FORBIDDEN_BODY,
                    headers={"Cache-Control": "no-store"},
                )
        return await call_next(request)

    return guard


def install_origin_guard(
    app: object, *, secret: str | None, protected_prefix: str
) -> bool:
    """Register the origin-secret guard on ``app`` iff ``secret`` is set; return active?

    ``app`` is a Starlette/FastAPI instance (typed ``object`` so this module needs no
    fastapi import beyond the request/response types). When ``secret`` is falsy the
    guard is **not** installed (fail-open) and ``False`` is returned; both branches log
    the resulting posture so it is never silent.
    """
    if not secret:
        _LOG.info(
            "origin guard: OPEN — %s unset, no enforcement (expected for local/CI)",
            "USVOTE_API_ORIGIN_SECRET",
        )
        return False

    _LOG.info(
        "origin guard: ENFORCED on %s* — a matching %s header is required "
        "(Cloudflare origin secret)",
        protected_prefix,
        ORIGIN_SECRET_HEADER,
    )
    # app.middleware("http") is the documented registration hook; the object type keeps
    # this module free of any concrete FastAPI symbol (slim import graph, D028).
    app.middleware("http")(_make_guard(secret, protected_prefix))  # type: ignore[attr-defined]
    return True
