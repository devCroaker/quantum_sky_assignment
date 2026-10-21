#!/usr/bin/env bash
#
# Start both halves of the application and wait.
#
# Invoked by `make dev`, which is the one documented command. This exists as a
# script rather than as Makefile recipe lines because two long-running servers
# need a shared trap: without one, interrupting make leaves an orphaned uvicorn
# holding port 8000, and the next run fails with an error about the address
# being in use rather than about anything the reader did.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

HOST="${NETSCOPE_HOST:-127.0.0.1}"
PORT="${NETSCOPE_PORT:-8000}"

cleanup() {
  # Kill the whole process group of each child, because vite spawns workers
  # that outlive a plain kill of the parent.
  trap - INT TERM EXIT
  [[ -n "${API_PID:-}" ]] && kill -- "-${API_PID}" 2>/dev/null || true
  [[ -n "${WEB_PID:-}" ]] && kill -- "-${WEB_PID}" 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup INT TERM EXIT

echo "starting the API on http://${HOST}:${PORT}"
set -m
.venv/bin/python -m uvicorn netscope.api.app:create_app --factory \
  --host "${HOST}" --port "${PORT}" &
API_PID=$!
set +m

# Wait for the API to answer before starting the front end, so that a bad input
# file reports its own error instead of the browser showing a failed fetch.
for _ in $(seq 1 50); do
  if curl -sf "http://${HOST}:${PORT}/api/v1/network" >/dev/null 2>&1; then
    break
  fi
  if ! kill -0 "${API_PID}" 2>/dev/null; then
    echo "the API exited during startup, see the message above" >&2
    exit 1
  fi
  sleep 0.2
done

echo "starting the front end on http://localhost:5173"
set -m
(cd frontend && VITE_DATA_SOURCE=live npm run dev -- --host "${HOST}") &
WEB_PID=$!
set +m

echo
echo "netscope is running. Open http://localhost:5173 and press ctrl-c to stop."
echo

# Poll rather than `wait -n`, which needs bash 4. macOS ships bash 3.2, so the
# one documented command would have failed on the reviewer's own machine while
# working on a Linux runner. Polling costs nothing here and runs anywhere.
while kill -0 "${API_PID}" 2>/dev/null && kill -0 "${WEB_PID}" 2>/dev/null; do
  sleep 1
done

echo "one of the two servers stopped, shutting the other down" >&2
