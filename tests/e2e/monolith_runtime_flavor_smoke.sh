#!/usr/bin/env bash
set -euo pipefail

image="${1:-}"
expected_flavor="${2:-}"

if [[ -z "$image" || -z "$expected_flavor" ]]; then
  echo "usage: monolith_runtime_flavor_smoke.sh <image> <expected-flavor>" >&2
  exit 64
fi

container_name="yawamf-${expected_flavor}-smoke-${RANDOM}"

cleanup() {
  status=$?
  trap - EXIT
  if [[ $status -ne 0 ]]; then
    echo "Runtime flavor smoke test failed; container logs follow:" >&2
    docker logs "$container_name" >&2 2>/dev/null || true
  fi
  docker rm --force "$container_name" >/dev/null 2>&1 || true
  exit "$status"
}
trap cleanup EXIT

docker run --detach --name "$container_name" "$image" >/dev/null

for _attempt in $(seq 1 90); do
  running="$(docker inspect --format '{{.State.Running}}' "$container_name")"
  health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}missing{{end}}' "$container_name")"

  if [[ "$running" != "true" || "$health" == "unhealthy" ]]; then
    echo "Container stopped or became unhealthy (running=$running, health=$health)" >&2
    exit 1
  fi
  if [[ "$health" == "healthy" ]]; then
    break
  fi
  sleep 2
done

health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}missing{{end}}' "$container_name")"
if [[ "$health" != "healthy" ]]; then
  echo "Container did not become healthy (health=$health)" >&2
  exit 1
fi

actual_flavor="$(
  docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' "$container_name" \
    | sed -n 's/^YAWAMF_IMAGE_FLAVOR=//p' \
    | head -n 1
)"
if [[ "$actual_flavor" != "$expected_flavor" ]]; then
  echo "Image flavor mismatch: expected $expected_flavor, got ${actual_flavor:-<unset>}" >&2
  exit 1
fi

# Re-run the in-image healthcheck explicitly so the smoke contract cannot pass
# because of a stale Docker health state.
docker exec "$container_name" /usr/local/bin/yawamf-healthcheck.sh
