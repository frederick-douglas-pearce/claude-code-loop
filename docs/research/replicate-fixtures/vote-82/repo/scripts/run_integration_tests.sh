#!/usr/bin/env bash
#
# Run the live-Postgres integration tests (marked @pytest.mark.integration),
# which are excluded from the default suite / CI.
#
# The tests are DESTRUCTIVE: any database you point them at has its `dwh` schema
# dropped and recreated (usvote.load's replace=True path), plus a `usvote_test`
# schema created/dropped. This script therefore defaults to a throwaway database
# (usvote_test), refuses to run against `elections`, and refuses any OTHER
# pre-existing database it did not create unless ALLOW_EXISTING_DB=1 is set — so
# your real data warehouse is never touched by accident.
#
# The postgres password is never stored: it is read from an interactive prompt
# (silently, not echoed, not in shell history) unless USVOTE_TEST_DB_PASSWORD is
# already exported. Do not hardcode it here or commit it anywhere.
#
# Usage:
#   scripts/run_integration_tests.sh                 # prompts for password, runs
#   USVOTE_TEST_DB_NAME=my_db scripts/run_integration_tests.sh
#   scripts/run_integration_tests.sh -k some_test    # extra args pass to pytest
#
# Overridable via env (defaults shown):
#   USVOTE_TEST_DB_HOST=localhost
#   USVOTE_TEST_DB_PORT=5432
#   USVOTE_TEST_DB_NAME=usvote_test
#   USVOTE_TEST_DB_USER=postgres
#   USVOTE_TEST_DB_PASSWORD   (prompted if unset)
#   KEEP_TEST_DB=1            keep the throwaway DB afterwards (default: drop it)
#   ALLOW_EXISTING_DB=1       allow a non-default DB that already exists (opt-in)

set -euo pipefail

# Resolve the repo root from this script's location so it runs from anywhere.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

# Fail clearly if the Postgres client tools are not on PATH (rather than letting
# set -e abort mid-run on the first missing binary). Check each one: `command -v`
# with multiple names only reports on the last, so it must be called per tool.
for tool in psql createdb dropdb; do
  command -v "${tool}" >/dev/null 2>&1 || {
    echo "postgres client tool '${tool}' not found on PATH." >&2
    exit 1
  }
done

export USVOTE_TEST_DB_HOST="${USVOTE_TEST_DB_HOST:-localhost}"
export USVOTE_TEST_DB_PORT="${USVOTE_TEST_DB_PORT:-5432}"
export USVOTE_TEST_DB_NAME="${USVOTE_TEST_DB_NAME:-usvote_test}"
export USVOTE_TEST_DB_USER="${USVOTE_TEST_DB_USER:-postgres}"

# Safety rail: the tests drop the dwh schema, so never point them at the real DB.
if [[ "${USVOTE_TEST_DB_NAME}" == "elections" ]]; then
  echo "Refusing to run: USVOTE_TEST_DB_NAME=elections is your real warehouse." >&2
  echo "These tests drop the dwh schema. Use a throwaway DB (default: usvote_test)." >&2
  exit 1
fi

# Read the password silently unless it is already in the environment.
if [[ -z "${USVOTE_TEST_DB_PASSWORD:-}" ]]; then
  read -rsp "postgres password for ${USVOTE_TEST_DB_USER}@${USVOTE_TEST_DB_HOST}: " USVOTE_TEST_DB_PASSWORD
  echo
  export USVOTE_TEST_DB_PASSWORD
fi

# psql/createdb/dropdb read PGPASSWORD, not our USVOTE_* vars. A short helper keeps
# the connection flags in one place.
pg() {
  local cmd="$1"; shift
  PGPASSWORD="${USVOTE_TEST_DB_PASSWORD}" "${cmd}" -h "${USVOTE_TEST_DB_HOST}" \
    -p "${USVOTE_TEST_DB_PORT}" -U "${USVOTE_TEST_DB_USER}" -w "$@"
}

# Confirm connectivity up front so a bad host/port/password fails clearly here
# rather than as an opaque error from inside pytest.
if ! pg psql -d postgres -tAc "SELECT 1" >/dev/null 2>&1; then
  echo "Could not connect to Postgres — check the host/port/user/password." >&2
  exit 1
fi

# Does the target database already exist? Query pg_database directly: no fragile
# `psql -l | cut | grep` pipeline (which can SIGPIPE under pipefail and can
# substring-match one DB name against another).
exists="$(pg psql -d postgres -tAc \
  "SELECT 1 FROM pg_database WHERE datname = '${USVOTE_TEST_DB_NAME}'")"

# Safety rail #2: these tests DROP the dwh schema in the target DB. That is safe
# for a throwaway we create fresh; it is NOT safe for a database that already
# exists and might hold real data. Refuse a pre-existing DB unless it is the
# default throwaway name or the caller explicitly opts in.
created_db=0
if [[ "${exists}" == "1" ]]; then
  if [[ "${USVOTE_TEST_DB_NAME}" != "usvote_test" && -z "${ALLOW_EXISTING_DB:-}" ]]; then
    echo "Refusing to run: database '${USVOTE_TEST_DB_NAME}' already exists and was" >&2
    echo "not created by this script. The tests drop its dwh schema. Point at a" >&2
    echo "throwaway DB, or set ALLOW_EXISTING_DB=1 if you are certain." >&2
    exit 1
  fi
else
  echo "Creating throwaway database ${USVOTE_TEST_DB_NAME}"
  pg createdb "${USVOTE_TEST_DB_NAME}"
  created_db=1
fi

# Clean up on ANY exit (including Ctrl-C during pytest): drop the DB only if this
# script created it and the caller did not ask to keep it, then forget the
# password. A drop failure is warned, never allowed to mask the test status.
cleanup() {
  if [[ "${created_db}" -eq 1 && -z "${KEEP_TEST_DB:-}" ]]; then
    echo "Dropping throwaway database ${USVOTE_TEST_DB_NAME}"
    pg dropdb "${USVOTE_TEST_DB_NAME}" \
      || echo "warning: could not drop ${USVOTE_TEST_DB_NAME}" >&2
  fi
  unset USVOTE_TEST_DB_PASSWORD || true
}
trap cleanup EXIT

# Run the integration-marked tests (pass through any extra args, e.g. -k / -v).
set +e
uv run pytest -m integration -v "$@"
status=$?
set -e

exit "${status}"
