# syntax=docker/dockerfile:1

# Cloud-agnostic container for the read-only usvote API (E8-S6, #100 / D032/D033).
#
# The image serves the FastAPI app from a SQLite snapshot BAKED IN at build time — no
# live database, no network dependency at runtime (D028). snapshot-version == image-
# version, so there is no data/code skew (the snapshot is copied in, never mounted).
#
# SLIM by design (D033): usvote/api/ imports only fastapi/starlette/pydantic + stdlib
# (enforced by tests/unit/test_api_import_graph.py), so the container installs the
# `usvote` package with `--no-deps` and adds ONLY the `serve` dependency-group — the
# heavy warehouse/analysis stack (pandas/geopandas/GDAL/psycopg2/matplotlib) never
# enters the image. Serve versions come from uv.lock (`--frozen`), never hand-pinned.
#
# Build (the snapshot must be in the build context — it lives outside the repo, so copy
# it in first; see README "Running the API in a container"):
#     cp "$USVOTE_API_SNAPSHOT_PATH" ./api_snapshot.sqlite
#     docker build -t usvote-api .
# Run (no DB needed; Postgres can be stopped):
#     docker run --rm -p 8080:8080 usvote-api
#     curl localhost:8080/health

# ---- builder: resolve the slim serve closure + install the package (no heavy deps) ----
# The uv image is built on python:3.14-slim-bookworm, so the venv's interpreter path
# matches the runtime stage below and the copied .venv resolves there.
FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim AS builder

# Copy the venv (not symlink into the uv cache), compile bytecode for faster cold start,
# and never let uv download its own interpreter — use the image's system python so the
# venv is portable to the runtime stage.
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app

# Only the files the install needs, so a snapshot/docs/test change doesn't bust this
# layer's cache. README.md + LICENSE are referenced by pyproject (readme/license-files),
# so the hatchling wheel build needs them present.
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src

# 1) the serve-time closure only (fastapi/uvicorn/pydantic), lock-resolved, no project;
# 2) the usvote package itself with NO deps (its heavy base deps stay out of the image).
RUN uv sync --frozen --no-install-project --only-group serve \
    && uv pip install --no-deps .

# ---- runtime: the same slim python base, venv + snapshot copied in, non-root ----------
FROM python:3.14-slim-bookworm AS runtime

# The baked-in snapshot path the app reads (D028). PATH puts the venv first so `uvicorn`
# and `python` resolve to it without activation.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    USVOTE_API_SNAPSHOT_PATH=/app/snapshot/api_snapshot.sqlite

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv

# Bake the pre-built snapshot into the image. SNAPSHOT_FILE is a build-context path; a
# missing file fails the build loudly (COPY errors) rather than shipping an empty image.
ARG SNAPSHOT_FILE=api_snapshot.sqlite
COPY ${SNAPSHOT_FILE} /app/snapshot/api_snapshot.sqlite

# Run as an unprivileged user; the app only ever reads the snapshot (stateless/read-only).
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

# Cloud-agnostic: listen on $PORT (Cloud Run injects it) with a sane local default; no
# vendor SDKs, no secrets baked in. EXPOSE documents the default.
EXPOSE 8080

# exec-form via sh -c so ${PORT} expands AND `exec` makes uvicorn PID 1 — it then
# receives SIGTERM directly and drains on scale-in (graceful scale-to-zero), instead of
# being SIGKILLed as a child of a non-forwarding shell.
CMD ["/bin/sh", "-c", "exec uvicorn --factory usvote.api:create_app --host 0.0.0.0 --port ${PORT:-8080}"]
