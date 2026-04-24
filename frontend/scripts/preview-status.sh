#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

STATUS_PORT="${PORT:-3001}"

printf "[status] Port %s listeners\n" "$STATUS_PORT"
lsof -nP -iTCP:"$STATUS_PORT" -sTCP:LISTEN || true

printf "\n[status] next start processes\n"
pgrep -af "next start" || true

printf "\n[status] build output\n"
if [[ -d ".next" ]]; then
  du -sh .next
else
  printf ".next does not exist\n"
fi
