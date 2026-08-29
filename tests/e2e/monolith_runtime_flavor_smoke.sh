#!/usr/bin/env bash
set -euo pipefail

image="${1:-}"
expected_flavor="${2:-}"
platform="${3:-}"

if [[ -z "$image" || -z "$expected_flavor" ]]; then
  echo "usage: monolith_runtime_flavor_smoke.sh <image> <expected-flavor> [platform]" >&2
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

# The default execution mode loads models lazily in worker processes, so the
# classification below pays a cold worker spawn. Emulated platforms need more
# patience than the production defaults allow.
docker_args=(
  run --detach --name "$container_name"
  -e CLASSIFICATION__WORKER_READY_TIMEOUT_SECONDS=240
  -e CLASSIFIER_BACKGROUND_IMAGE_LEASE_TIMEOUT_SECONDS=300
)
if [[ -n "$platform" ]]; then
  docker_args+=(--platform "$platform")
fi
docker "${docker_args[@]}" "$image" >/dev/null

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

classifier_status="$(
  docker exec "$container_name" \
    curl -fsS http://127.0.0.1:8080/api/classifier/status
)"
printf '%s' "$classifier_status" | docker exec -i "$container_name" python -c '
import json
import sys

status = json.load(sys.stdin)
if status.get("image_execution_mode") == "subprocess":
    # The default mode holds no model in the API process; workers load their
    # own copy on first use. The classification below is the load proof.
    pass
elif status.get("loaded") is not True:
    error = status.get("error") or "unknown error"
    raise SystemExit(f"classifier not loaded: {error}")
if not status.get("effective_model_id"):
    raise SystemExit("classifier did not report its effective model")
if int(status.get("labels_count") or 0) < 2:
    raise SystemExit("classifier labels were not loaded")
'

docker exec "$container_name" python -c '
from PIL import Image

Image.new("RGB", (224, 224), color=(96, 128, 96)).save("/tmp/yawamf-smoke.png")
'
# The first request pays the cold worker spawn and may outlive its lease on an
# emulated platform; the pool persists, so a retry classifies immediately.
classification=""
for attempt in 1 2 3; do
  if classification="$(
    docker exec "$container_name" \
      curl -fsS --max-time 360 -F image=@/tmp/yawamf-smoke.png \
      http://127.0.0.1:8080/api/classifier/classify
  )" && printf '%s' "$classification" \
    | docker exec -i "$container_name" python -c 'import json,sys; raise SystemExit(0 if json.load(sys.stdin).get("status") == "ok" else 1)'; then
    break
  fi
  echo "classification attempt $attempt did not succeed; the worker may still be spawning" >&2
  sleep 15
done
printf '%s' "$classification" | docker exec -i "$container_name" python -c '
import json
import sys

result = json.load(sys.stdin)
if result.get("status") != "ok":
    error = result.get("error") or "unknown error"
    raise SystemExit(f"classification failed: {error}")
if not result.get("predictions"):
    raise SystemExit("classification returned no predictions")
'
