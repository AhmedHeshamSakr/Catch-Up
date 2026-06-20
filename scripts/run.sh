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

read_port() {  # dotenv-ish: honors 'export', strips inline comments, validates range
  local line val p=""
  if [ -f app/.env ]; then
    line="$(grep -E '^[[:space:]]*(export[[:space:]]+)?APP_PORT=' app/.env 2>/dev/null | tail -1 || true)"
    val="${line#*=}"     # value after the first '='
    val="${val%%#*}"     # drop any inline comment
    val="$(printf '%s' "$val" | tr -d "\"' \t")"
    p="$val"
  fi
  case "$p" in (''|*[!0-9]*) p=8000 ;; esac
  if [ "$p" -lt 1024 ] 2>/dev/null || [ "$p" -gt 65535 ] 2>/dev/null; then p=8000; fi
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

# Serialize concurrent cold starts (Codex #5): only one launch picks a port and
# starts a server at a time. A waiting launch opens the winner's server as soon as
# it's healthy, so two double-clicks never start two servers.
LOCK="$RUN_DIR/launch.lock"
acquired=0
for _ in $(seq 1 200); do
  if mkdir "$LOCK" 2>/dev/null; then acquired=1; break; fi
  if is_our_app "$(read_port)"; then open_app "http://127.0.0.1:$(read_port)"; exit 0; fi
  sleep 0.3
done
if [ "$acquired" -eq 0 ]; then  # stale lock — take it over
  rmdir "$LOCK" 2>/dev/null || true
  mkdir "$LOCK" 2>/dev/null || true
fi
trap 'rmdir "$LOCK" 2>/dev/null || true' EXIT INT TERM

# Re-check under the lock (the winner may have just brought it up).
PORT="$(read_port)"
if is_our_app "$PORT"; then open_app "http://127.0.0.1:$PORT"; exit 0; fi

PORT="$(pick_port "$PORT")"
if is_our_app "$PORT"; then open_app "http://127.0.0.1:$PORT"; exit 0; fi

command -v uv >/dev/null 2>&1 || { echo "uv not found — install from https://docs.astral.sh/uv/"; exit 1; }

# Build the console if missing OR if a stale build baked a non-same-origin API
# base (e.g. a dev `npm run build` with .env.local) — single-port needs same-origin.
if [ ! -d frontend/out ] || grep -rqs "localhost:8000" frontend/out 2>/dev/null; then
  command -v npm >/dev/null 2>&1 || { echo "npm not found — install Node 20+ to build the console."; exit 1; }
  note "Building the console (~1-2 min)…"
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
