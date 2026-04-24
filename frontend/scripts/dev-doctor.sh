#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

printf "[doctor] Killing stale Next dev processes...\n"
pkill -f "next dev" 2>/dev/null || true

printf "[doctor] Clearing .next cache...\n"
rm -rf .next

printf "[doctor] Starting fresh dev server on 0.0.0.0:3000...\n"
npm run dev:raw -- --hostname 0.0.0.0
