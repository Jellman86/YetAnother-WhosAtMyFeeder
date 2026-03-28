#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
IMAGE_TAG="yawamf-monalithic:test"
CID="yawamf-monolith-smoke"
trap 'docker rm -f "$CID" >/dev/null 2>&1 || true' EXIT

docker build -t "$IMAGE_TAG" "$ROOT"
docker run -d --name "$CID" \
  -p 19852:8080 \
  -e DB_PATH=/tmp/speciesid.db \
  -e CONFIG_DIR=/tmp/config \
  -e CONFIG_FILE=/tmp/config/config.json \
  -e MEDIA_CACHE_DIR=/tmp/media_cache \
  "$IMAGE_TAG"

for _ in $(seq 1 90); do
  status="$(docker inspect "$CID" --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}')"
  if [ "$status" = "healthy" ]; then
    break
  fi
  if [ "$status" = "unhealthy" ]; then
    docker logs "$CID" >&2 || true
    exit 1
  fi
  sleep 2
done

status="$(docker inspect "$CID" --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}')"
if [ "$status" != "healthy" ]; then
  docker logs "$CID" >&2 || true
  echo "container did not become healthy: $status" >&2
  exit 1
fi

docker inspect "$CID" --format '{{range (index .NetworkSettings.Ports "8080/tcp")}}{{println .HostPort}}{{end}}' | grep -qx '19852'
docker exec "$CID" curl -fsS http://127.0.0.1:8080/ >/dev/null
docker exec "$CID" curl -fsS http://127.0.0.1:8080/health >/dev/null
docker exec "$CID" curl -fsS http://127.0.0.1:8080/api/version >/dev/null
