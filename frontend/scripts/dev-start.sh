#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

NEXT_BIN="./node_modules/.bin/next"
LISTENERS="$(lsof -tiTCP:3000 -sTCP:LISTEN 2>/dev/null || true)"
NEXT_DEV_PIDS="$(pgrep -f "next dev" || true)"
MANIFEST_HASH_FILE=".next/cache/dev-manifest.hash"
DEV_VENDOR_CHUNKS=(
  ".next/server/vendor-chunks/@tanstack.js"
  ".next/server/vendor-chunks/@swc.js"
  ".next/server/vendor-chunks/next.js"
  ".next/server/vendor-chunks/tailwind-merge.js"
)

compute_manifest_hash() {
  shasum package.json package-lock.json 2>/dev/null | shasum | awk '{print $1}'
}

clear_next_cache() {
  printf "[guard] Clearing stale .next cache...\n"
  rm -rf .next
}

if [[ -n "$LISTENERS" || -n "$NEXT_DEV_PIDS" ]]; then
  printf "[guard] Frontend dev server appears to already be running or stale processes exist.\n"

  if [[ -n "$LISTENERS" ]]; then
    printf "[guard] Port 3000 listeners: %s\n" "$(echo "$LISTENERS" | tr '\n' ' ' | sed 's/[[:space:]]*$//')"
  fi

  if [[ -n "$NEXT_DEV_PIDS" ]]; then
    printf "[guard] next dev pids: %s\n" "$(echo "$NEXT_DEV_PIDS" | tr '\n' ' ' | sed 's/[[:space:]]*$//')"
  fi

  printf "[guard] Use 'npm run dev:status' to inspect or 'npm run dev:doctor' to recover cleanly.\n"
  exit 1
fi

CURRENT_MANIFEST_HASH="$(compute_manifest_hash)"
PREVIOUS_MANIFEST_HASH="$(cat "$MANIFEST_HASH_FILE" 2>/dev/null || true)"

if [[ -d ".next" && -n "$PREVIOUS_MANIFEST_HASH" && "$CURRENT_MANIFEST_HASH" != "$PREVIOUS_MANIFEST_HASH" ]]; then
  printf "[guard] Frontend dependency manifests changed since the last dev run.\n"
  clear_next_cache
fi

if [[ -d ".next" ]]; then
  for chunk_path in "${DEV_VENDOR_CHUNKS[@]}"; do
    if [[ ! -f "$chunk_path" ]]; then
      printf "[guard] Missing dev vendor chunk detected: %s\n" "$chunk_path"
      clear_next_cache
      break
    fi
  done
fi

mkdir -p "$(dirname "$MANIFEST_HASH_FILE")"
printf "%s" "$CURRENT_MANIFEST_HASH" > "$MANIFEST_HASH_FILE"

exec "$NEXT_BIN" dev --hostname 0.0.0.0 "$@"
