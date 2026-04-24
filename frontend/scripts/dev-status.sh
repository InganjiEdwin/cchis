#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

printf "[status] Port 3000 listeners\n"
lsof -nP -iTCP:3000 -sTCP:LISTEN || true

printf "\n[status] next dev processes\n"
pgrep -af "next dev" || true

printf "\n[status] .next directory\n"
if [[ -d ".next" ]]; then
  du -sh .next
else
  printf ".next does not exist\n"
fi

printf "\n[status] dev vendor chunks\n"
if [[ -d ".next/server/vendor-chunks" ]]; then
  ls -1 .next/server/vendor-chunks
else
  printf ".next/server/vendor-chunks does not exist\n"
fi
