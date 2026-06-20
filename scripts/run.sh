#!/usr/bin/env bash
# Catch-Up local launcher: boots the single-port server (FastAPI serving the
# built console + /api) and opens it in a chromeless app window.
#
# Behavior:
#   - reads the port from app/.env directly (never imports the app package)
#   - if our app is already healthy on that port, just opens the window (no dup)
#   - if the port is taken by something else, picks the next free port
#   - first run: builds the console (frontend/out) if missing
#   - starts uvicorn detached (survives this script), logs to .run/server.log
#   - opens Chrome/Edge/Brave in --app mode (no tabs/address bar); else the
#     default browser
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT"

RUN_DIR="$ROOT/.run"
mkdir -p "$RUN_DIR"
LOG="$RUN_DIR/server.log"
PIDFILE="$RUN_DIR/server.pid"

note() {  # best-effort macOS notification + stdout
  echo "▶ $1"
  command -v osascript >/dev/null 2>&1 &&
    osascript -e "display notification \"$1\" with title \"Catch-Up\"" >/dev/null 2>&1 || true
}

read_port() {
  local p=""
  if [ -f app/.env ]; then
    p="$(grep -E '^[[:space:]]*APP_PORT=' app/.env 2>/dev/null | tail -1 | cut -d= -f2- | tr -d "\"' \t" || true)"
  fi
  case "$p" in (''|*[!0-9]*) p=8000 ;; esac
  echo "$p"
}

is_our_app() {  # $1 = port ; true only if OUR app answers (marker, Codex #9)
  curl -fsS --max-time 1 "http://127.0.0.1:$1/api/health" 2>/dev/null \
    | grep -q '"app"[[:space:]]*:[[:space:]]*"catch-up"'
}

port_listening() {  # $1 = port
  lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1
}

pick_port() {  # from $1 upward: reuse-our-app | free | next
  local p="$1" i
  for i in $(seq 0 20); do
    if is_our_app "$p" || ! port_listening "$p"; then echo "$p"; return 0; fi
    p=$((p + 1))
  done
  echo "$1"
}

open_app() {  # $1 = url ; chromeless window if a Chromium browser exists
  local url="$1" app bin
  for app in "Google Chrome" "Microsoft Edge" "Brave Browser" "Chromium"; do
    bin="/Applications/$app.app/Contents/MacOS/$app"
    if [ -x "$bin" ]; then
      "$bin" --app="$url" >/dev/null 2>&1 &
      return 0
    fi
  done
  open "$url" 2>/dev/null || true  # default browser / installed PWA
}

PORT="$(read_port)"

# Already running? Open and done.
if is_our_app "$PORT"; then
  note "Already running on $PORT — opening."
  open_app "http://127.0.0.1:$PORT"
  exit 0
fi

PORT="$(pick_port "$PORT")"
if is_our_app "$PORT"; then open_app "http://127.0.0.1:$PORT"; exit 0; fi

command -v uv >/dev/null 2>&1 || { echo "uv not found — install from https://docs.astral.sh/uv/"; exit 1; }

# First run: build the console (same-origin base) if it isn't there yet.
if [ ! -d frontend/out ]; then
  command -v npm >/dev/null 2>&1 || { echo "npm not found — install Node 20+ to build the console."; exit 1; }
  note "First run: building the console (~1-2 min)…"
  ( cd frontend && npm ci && NEXT_PUBLIC_API_BASE="" npm run build )
fi

start_server() {  # $1 = port ; detached, survives this script
  nohup uv run python -m uvicorn app.api.app:create_app --factory \
    --host 127.0.0.1 --port "$1" >"$LOG" 2>&1 &
  echo $! >"$PIDFILE"
}

note "Starting Catch-Up…"
attempts=0
waited=0
start_server "$PORT"
while :; do
  pid="$(cat "$PIDFILE" 2>/dev/null || echo)"
  if [ -n "$pid" ] && ! kill -0 "$pid" 2>/dev/null; then
    # Server exited early (likely a port bind race) — try the next port a few times.
    attempts=$((attempts + 1))
    [ "$attempts" -gt 5 ] && { echo "Could not bind a port. See $LOG"; tail -n 20 "$LOG"; exit 1; }
    PORT="$(pick_port "$((PORT + 1))")"
    waited=0
    start_server "$PORT"
    continue
  fi
  if is_our_app "$PORT"; then
    note "Catch-Up ready at http://127.0.0.1:$PORT"
    open_app "http://127.0.0.1:$PORT"
    exit 0
  fi
  waited=$((waited + 1))
  if [ "$waited" -gt 120 ]; then   # ~60s without a healthy response
    echo "Server did not become healthy in time. See $LOG"; tail -n 20 "$LOG"; exit 1
  fi
  sleep 0.5
done
