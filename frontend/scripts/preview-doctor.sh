#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

PREVIEW_PORT="${PORT:-3001}"

printf "[doctor] Killing stale preview processes...\n"
pkill -f "next start" 2>/dev/null || true

printf "[doctor] Rebuilding production preview bundle...\n"
npm run build

printf "[doctor] Starting fresh preview server on 0.0.0.0:%s...\n" "$PREVIEW_PORT"
PORT="$PREVIEW_PORT" npm run preview:raw
