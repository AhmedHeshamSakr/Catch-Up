#!/usr/bin/env bash
# Stop the Catch-Up server started by run.sh.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PIDFILE="$ROOT/.run/server.pid"

pid=""
[ -f "$PIDFILE" ] && pid="$(cat "$PIDFILE" 2>/dev/null || echo)"

# Verify the recorded PID is still OUR uvicorn process before signaling — a stale
# pidfile whose PID macOS has reused must not get an unrelated process killed.
if [ -n "$pid" ] && ps -p "$pid" -o command= 2>/dev/null | grep -q "app.api.app:create_app"; then
  if kill "$pid" 2>/dev/null; then
    echo "Stopped Catch-Up (pid $pid)."
  else
    echo "Could not signal pid $pid."
  fi
  rm -f "$PIDFILE"
else
  echo "Catch-Up does not appear to be running (no live server for the recorded PID)."
  rm -f "$PIDFILE" 2>/dev/null || true
fi
