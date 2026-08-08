#!/usr/bin/env bash
set -euo pipefail

backend_pid=""
nginx_pid=""
export YA_WAMF_STARTUP_STATUS_PATH="${YA_WAMF_STARTUP_STATUS_PATH:-/tmp/yawamf-startup-status.json}"

write_startup_status() {
    local status="$1"
    local phase="$2"
    local progress="$3"
    local started_at
    local temporary_path="${YA_WAMF_STARTUP_STATUS_PATH}.tmp"
    started_at="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
    mkdir -p "$(dirname "${YA_WAMF_STARTUP_STATUS_PATH}")" 2>/dev/null || return 0
    if ! printf '{"status":"%s","phase":"%s","progress":%s,"started_at":"%s","updated_at":"%s"}\n' \
        "${status}" "${phase}" "${progress}" "${started_at}" "${started_at}" > "${temporary_path}" \
        || ! mv "${temporary_path}" "${YA_WAMF_STARTUP_STATUS_PATH}"; then
        rm -f "${temporary_path}" 2>/dev/null || true
    fi
}

shutdown() {
    if [ -n "${backend_pid}" ]; then
        kill -TERM "${backend_pid}" 2>/dev/null || true
    fi
    if [ -n "${nginx_pid}" ]; then
        kill -TERM "${nginx_pid}" 2>/dev/null || true
    fi
    wait "${backend_pid}" 2>/dev/null || true
    wait "${nginx_pid}" 2>/dev/null || true
}

trap shutdown TERM INT

mkdir -p \
    /tmp/nginx/client_temp \
    /tmp/nginx/proxy_temp \
    /tmp/nginx/fastcgi_temp \
    /tmp/nginx/uwsgi_temp \
    /tmp/nginx/scgi_temp

write_startup_status "starting" "launching" 5

uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log &
backend_pid=$!

nginx -g 'daemon off;' &
nginx_pid=$!

wait -n "${backend_pid}" "${nginx_pid}"
status=$?
shutdown
exit "${status}"
