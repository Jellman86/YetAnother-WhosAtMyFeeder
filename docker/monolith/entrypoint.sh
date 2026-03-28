#!/usr/bin/env bash
set -euo pipefail

backend_pid=""
nginx_pid=""

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

uvicorn app.main:app --host 127.0.0.1 --port 8000 &
backend_pid=$!

nginx -g 'daemon off;' &
nginx_pid=$!

wait -n "${backend_pid}" "${nginx_pid}"
status=$?
shutdown
exit "${status}"
