#!/usr/bin/env bash
set -euo pipefail

full_image="${1:-}"
target_image="${2:-}"
expected_target_flavor="${3:-}"

if [[ -z "$full_image" || -z "$target_image" || -z "$expected_target_flavor" ]]; then
  echo "usage: monolith_runtime_flavor_switch.sh <full-image> <target-image> <target-flavor>" >&2
  exit 64
fi

case "$expected_target_flavor" in
  cpu|intel|cuda) ;;
  *)
    echo "unsupported switch target: $expected_target_flavor" >&2
    exit 64
    ;;
esac

run_id="${GITHUB_RUN_ID:-local}-${GITHUB_RUN_ATTEMPT:-0}-${RANDOM}"
config_volume="yawamf-switch-config-${run_id}"
data_volume="yawamf-switch-data-${run_id}"
full_container="yawamf-switch-full-${run_id}"
target_container="yawamf-switch-${expected_target_flavor}-${run_id}"
active_container=""

cleanup() {
  status=$?
  trap - EXIT
  if [[ $status -ne 0 && -n "$active_container" ]]; then
    echo "Runtime flavor switch failed; active container logs follow:" >&2
    docker logs "$active_container" >&2 2>/dev/null || true
  fi
  docker rm --force "$full_container" "$target_container" >/dev/null 2>&1 || true
  docker volume rm --force "$config_volume" "$data_volume" >/dev/null 2>&1 || true
  exit "$status"
}
trap cleanup EXIT

wait_healthy() {
  local container_name="$1"
  local running health

  for _attempt in $(seq 1 90); do
    running="$(docker inspect --format '{{.State.Running}}' "$container_name")"
    health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}missing{{end}}' "$container_name")"
    if [[ "$running" != "true" || "$health" == "unhealthy" ]]; then
      echo "Container stopped or became unhealthy (container=$container_name, running=$running, health=$health)" >&2
      return 1
    fi
    if [[ "$health" == "healthy" ]]; then
      return 0
    fi
    sleep 2
  done

  health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}missing{{end}}' "$container_name")"
  echo "Container did not become healthy (container=$container_name, health=$health)" >&2
  return 1
}

start_container() {
  local container_name="$1"
  local image="$2"

  active_container="$container_name"
  docker run --detach \
    --name "$container_name" \
    --volume "$config_volume:/config" \
    --volume "$data_volume:/data" \
    "$image" >/dev/null
  wait_healthy "$container_name"
}

stop_container() {
  local container_name="$1"
  docker rm --force "$container_name" >/dev/null
  if [[ "$active_container" == "$container_name" ]]; then
    active_container=""
  fi
}

config_checksum() {
  docker exec "$1" sha256sum /config/config.json | awk '{print $1}'
}

model_checksum() {
  docker exec "$1" sha256sum /data/models/runtime-flavor-switch-contract/model.onnx | awk '{print $1}'
}

model_config_checksum() {
  docker exec "$1" sha256sum /data/models/runtime-flavor-switch-contract/model_config.json | awk '{print $1}'
}

assert_database_state() {
  local container_name="$1"
  local integrity sentinel

  integrity="$(docker exec "$container_name" sqlite3 /data/speciesid.db 'PRAGMA integrity_check;')"
  sentinel="$(docker exec "$container_name" sqlite3 /data/speciesid.db \
    "SELECT value FROM runtime_flavor_switch_contract WHERE key = 'persistent-state';")"
  [[ "$integrity" == "ok" ]]
  [[ "$sentinel" == "preserved" ]]
}

assert_classifier_status() {
  local container_name="$1"
  local expected_flavor="$2"
  local expected_warning="$3"
  local status_json

  status_json="$(docker exec "$container_name" curl -fsS http://127.0.0.1:8080/api/classifier/status)"
  python3 -c '
import json
import sys

expected_flavor, expected_warning = sys.argv[1:3]
status = json.load(sys.stdin)
actual_warning = status.get("image_flavor_warning") or ""

assert status.get("image_flavor") == expected_flavor, status
assert status.get("selected_provider") == "cuda", status
assert actual_warning == expected_warning, status
assert "cpu" in (status.get("packaged_inference_providers") or []), status
' "$expected_flavor" "$expected_warning" <<<"$status_json"
}

docker volume create "$config_volume" >/dev/null
docker volume create "$data_volume" >/dev/null

# Let the full image create the current schema and generated auth secret, then
# add representative persisted state using the same non-root runtime user.
start_container "$full_container" "$full_image"
docker exec "$full_container" python -c '
import json
from pathlib import Path

path = Path("/config/config.json")
payload = json.loads(path.read_text(encoding="utf-8"))
payload.setdefault("classification", {})["inference_provider"] = "cuda"
temporary = path.with_name(path.name + ".switch.tmp")
temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
temporary.replace(path)

model_dir = Path("/data/models/runtime-flavor-switch-contract")
model_dir.mkdir(parents=True, exist_ok=True)
(model_dir / "model.onnx").write_bytes(b"persistent-model-artifact")
(model_dir / "model_config.json").write_text(
    json.dumps(
        {
            "model_id": "runtime-flavor-switch-contract",
            "runtime": "onnx",
            "supported_inference_providers": ["cpu", "cuda", "intel_gpu"],
        },
        indent=2,
    )
    + "\n",
    encoding="utf-8",
)
'
docker exec "$full_container" sqlite3 -cmd '.timeout 30000' /data/speciesid.db \
  "CREATE TABLE IF NOT EXISTS runtime_flavor_switch_contract (key TEXT PRIMARY KEY, value TEXT NOT NULL); INSERT OR REPLACE INTO runtime_flavor_switch_contract (key, value) VALUES ('persistent-state', 'preserved');"
stop_container "$full_container"

# Restart full once so the recorded baseline represents a normally loaded user
# configuration, not a file changed underneath a running process.
start_container "$full_container" "$full_image"
assert_classifier_status "$full_container" full ""
assert_database_state "$full_container"
baseline_config_checksum="$(config_checksum "$full_container")"
baseline_model_checksum="$(model_checksum "$full_container")"
baseline_model_config_checksum="$(model_config_checksum "$full_container")"
baseline_git_hash="$(docker exec "$full_container" printenv GIT_HASH)"
stop_container "$full_container"

# Switch to the provider image with the exact same volumes. A CUDA selection is
# deliberately incompatible with CPU so the safe, non-mutating warning/fallback
# path is exercised while config, database, and downloaded-model storage remain.
expected_warning=""
if [[ "$expected_target_flavor" != "cuda" ]]; then
  expected_warning="selected_provider_not_packaged"
fi
start_container "$target_container" "$target_image"
assert_classifier_status "$target_container" "$expected_target_flavor" "$expected_warning"
assert_database_state "$target_container"
[[ "$(config_checksum "$target_container")" == "$baseline_config_checksum" ]]
[[ "$(model_checksum "$target_container")" == "$baseline_model_checksum" ]]
[[ "$(model_config_checksum "$target_container")" == "$baseline_model_config_checksum" ]]
[[ "$(docker exec "$target_container" printenv GIT_HASH)" == "$baseline_git_hash" ]]
stop_container "$target_container"

# Switch back to full as the rollback proof. Persistent state and the user’s
# explicitly selected provider must still be byte-for-byte intact.
start_container "$full_container" "$full_image"
assert_classifier_status "$full_container" full ""
assert_database_state "$full_container"
[[ "$(config_checksum "$full_container")" == "$baseline_config_checksum" ]]
[[ "$(model_checksum "$full_container")" == "$baseline_model_checksum" ]]
[[ "$(model_config_checksum "$full_container")" == "$baseline_model_config_checksum" ]]
[[ "$(docker exec "$full_container" printenv GIT_HASH)" == "$baseline_git_hash" ]]
