#!/bin/sh
# The vote-82 fixture's shakedowns (#392): each runs one command in a fresh sandboxed
# replicate dir, with no model and no credentials, and writes <out>/<id>/shakedown.json.
# Usage: sh shakedowns.sh <out-dir> <uv-bin> [id-prefix]
# The TEST_CMD and HERMETIC_TEST_CMD strings below are the fixture config's rows, byte for byte.
set -u
out=$1; uv=$2; p=${3:-}
here=$(cd "$(dirname "$0")" && pwd)
research=$(cd "$here/../.." && pwd)
test_cmd='uv run pytest'
hermetic_cmd="unshare -rn -- sh -c 'ip link set lo up && uv run --offline pytest'"
probe='python3 -c "import socket; socket.create_connection((\"1.1.1.1\", 443), 3)"'
run() {
  id=$p$1; shift
  python3 "$research/replicate.py" shakedown --fixture "$here" --replicate-id "$id" \
    --out "$out" --uv-bin "$uv" --command "$1"
  echo "$id harness-exit=$? command-exit=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("exit_code"))' "$out/$id/shakedown.json")"
}
# socket-blocked passes when its command exits non-zero (the block held); every other
# command passes at 0. socket-open is the control that shows the probe can connect.
run test-hermetic "$test_cmd && $hermetic_cmd"
run socket-open "$probe"
run socket-blocked "unshare -rn -- sh -c 'ip link set lo up && $probe'"
run lint-type "uv run ruff check && uv run mypy"
run locked "uv run --locked pytest"
run python-a "uv run python -VV"
run python-b "uv run python -VV"
