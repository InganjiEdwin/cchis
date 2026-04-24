#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

pkill -f "next dev" 2>/dev/null || true
rm -rf .next
npm run dev:raw -- --hostname 0.0.0.0
