#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
IMAGE_TAG="yawamf-monalithic:test"
CID="yawamf-monolith-smoke"
TMP_DIR="$(mktemp -d)"
trap 'docker rm -f "$CID" >/dev/null 2>&1 || true; rm -rf "$TMP_DIR"' EXIT

mkdir -p "$TMP_DIR/config" "$TMP_DIR/data"

docker build -t "$IMAGE_TAG" "$ROOT"
docker run -d --name "$CID" \
  -p 19852:80 \
  -v "$TMP_DIR/config:/config" \
  -v "$TMP_DIR/data:/data" \
  "$IMAGE_TAG"

for _ in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:19852/health >/dev/null; then
    break
  fi
  sleep 2
done

curl -fsS http://127.0.0.1:19852/ >/dev/null
curl -fsS http://127.0.0.1:19852/health >/dev/null
curl -fsS http://127.0.0.1:19852/api/version >/dev/null
