#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

START_PORT="${PORT:-3001}"
NEXT_BIN="./node_modules/.bin/next"
LISTENERS="$(lsof -tiTCP:"$START_PORT" -sTCP:LISTEN 2>/dev/null || true)"
START_PIDS="$(pgrep -f "next start" || true)"

if [[ -n "$LISTENERS" || -n "$START_PIDS" ]]; then
  printf "[guard] Preview server appears to already be running or stale processes exist.\n"

  if [[ -n "$LISTENERS" ]]; then
    printf "[guard] Port %s listeners: %s\n" "$START_PORT" "$(echo "$LISTENERS" | tr '\n' ' ' | sed 's/[[:space:]]*$//')"
  fi

  if [[ -n "$START_PIDS" ]]; then
    printf "[guard] next start pids: %s\n" "$(echo "$START_PIDS" | tr '\n' ' ' | sed 's/[[:space:]]*$//')"
  fi

  printf "[guard] Use 'npm run preview:status' to inspect or 'npm run preview:doctor' to recover cleanly.\n"
  exit 1
fi

exec "$NEXT_BIN" start --hostname 0.0.0.0 --port "$START_PORT"
