#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FILE="$ROOT/docker-compose.monolith.yml"

services="$(docker compose -f "$FILE" config --services)"
test "$services" = "yawamf"

config="$(docker compose -f "$FILE" config)"

printf '%s\n' "$config" | grep -Eq '^name: yetanother-whosatmyfeeder-monolith$'
printf '%s\n' "$config" | grep -Eq 'image: ghcr\.io/jellman86/yawamf-monalithic:'
printf '%s\n' "$config" | grep -Eq 'container_name: yawamf-monalithic'
printf '%s\n' "$config" | grep -Eq 'published: "9852"'
printf '%s\n' "$config" | grep -Eq 'target: 8080'
printf '%s\n' "$config" | grep -Eq 'FRIGATE__FRIGATE_URL: http://frigate:5000'
printf '%s\n' "$config" | grep -Eq '^  yawamf_network:$'
printf '%s\n' "$config" | grep -Eq '^    external: true$'
! printf '%s\n' "$config" | grep -Eq 'wamf-backend|wamf-frontend|yawamf-backend|yawamf-frontend'
