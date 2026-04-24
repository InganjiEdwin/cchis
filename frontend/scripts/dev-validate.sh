#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

BASE_URL="${BASE_URL:-http://127.0.0.1:3000}"
ITERATIONS="${ITERATIONS:-4}"
LOGIN_ROUTE="${LOGIN_ROUTE:-/login}"

ROUTES=(
  "/login"
  "/forgot-password"
  "/request-access"
  "/privacy"
  "/terms"
  "/verify-2fa"
  "/setup-2fa"
  "/unauthorized"
  "/overview"
  "/alerts"
  "/wards"
  "/chvs"
  "/system"
  "/profile"
  "/facility-readiness"
)

extract_css_path() {
  perl -ne 'if (m{href="([^"]*/_next/static/css/[^"]+\.css[^"]*)"}) { print "$1\n"; exit }'
}

fetch_css_path() {
  local html
  html="$(curl -fsS "$BASE_URL$LOGIN_ROUTE")"
  printf "%s" "$html" | extract_css_path
}

validate_css_asset() {
  local css_path="$1"
  local response
  response="$(curl -sS -o /dev/null -w '%{http_code} %{content_type}' "$BASE_URL$css_path")"
  local status content_type
  status="${response%% *}"
  content_type="${response#* }"

  if [[ "$status" != "200" ]]; then
    printf "[validate] CSS asset failed: %s returned status %s\n" "$css_path" "$status" >&2
    return 1
  fi

  if [[ "$content_type" != text/css* ]]; then
    printf "[validate] CSS asset failed: %s returned content type %s\n" "$css_path" "$content_type" >&2
    return 1
  fi
}

validate_route() {
  local route="$1"
  local status
  status="$(curl -sS -o /dev/null -w '%{http_code}' "$BASE_URL$route")"

  case "$status" in
    200|307|308)
      return 0
      ;;
    *)
      printf "[validate] Route probe failed: %s returned status %s\n" "$route" "$status" >&2
      return 1
      ;;
  esac
}

printf "[validate] Base URL: %s\n" "$BASE_URL"
printf "[validate] Iterations: %s\n" "$ITERATIONS"

for iteration in $(seq 1 "$ITERATIONS"); do
  printf "[validate] Cycle %s/%s\n" "$iteration" "$ITERATIONS"

  css_path="$(fetch_css_path)"
  if [[ -z "$css_path" ]]; then
    printf "[validate] Unable to locate app stylesheet from %s\n" "$LOGIN_ROUTE" >&2
    exit 1
  fi

  printf "[validate] Using stylesheet: %s\n" "$css_path"
  validate_css_asset "$css_path"

  for route in "${ROUTES[@]}"; do
    validate_route "$route"
    validate_css_asset "$css_path"
  done
done

printf "[validate] All route and stylesheet probes passed.\n"
