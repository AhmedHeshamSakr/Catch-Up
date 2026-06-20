#!/usr/bin/env bash
# Stop the Catch-Up server started by run.sh.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PIDFILE="$ROOT/.run/server.pid"

if [ -f "$PIDFILE" ] && pid="$(cat "$PIDFILE" 2>/dev/null)" && [ -n "$pid" ] && kill "$pid" 2>/dev/null; then
  echo "Stopped Catch-Up (pid $pid)."
  rm -f "$PIDFILE"
else
  echo "Catch-Up does not appear to be running."
  rm -f "$PIDFILE" 2>/dev/null || true
fi
