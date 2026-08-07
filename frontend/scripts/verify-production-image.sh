#!/bin/sh
set -eu

image_name="${1:?usage: verify-production-image.sh IMAGE}"
container_id=""

cleanup() {
  if [ -n "$container_id" ]; then
    docker rm -f "$container_id" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

container_id="$(docker run -d "$image_name")"

healthy=""
for _attempt in $(seq 1 30); do
  if docker exec "$container_id" wget -qO- http://127.0.0.1:3000/api/health >/dev/null 2>&1; then
    healthy=1
    break
  fi
  sleep 1
done

if [ -z "$healthy" ]; then
  docker logs "$container_id" || true
  echo "Frontend production image did not pass its health endpoint smoke test." >&2
  exit 1
fi

if docker exec "$container_id" sh -c \
  "grep -R -n -E 'http://localhost:8000|ws://localhost:8000' /app/.next /app/server.js"; then
  echo "Frontend production image contains a localhost API or WebSocket origin." >&2
  exit 1
fi
