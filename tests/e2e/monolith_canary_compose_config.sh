#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FILE="$ROOT/docker-compose.monolith.yml"

services="$(docker compose -f "$FILE" config --services)"
test "$services" = "yawamf"

config="$(docker compose -f "$FILE" config)"

printf '%s\n' "$config" | rg -q '^name: yetanother-whosatmyfeeder-monolith$'
printf '%s\n' "$config" | rg -q 'image: ghcr\.io/jellman86/yawamf-monalithic:'
printf '%s\n' "$config" | rg -q 'container_name: yawamf-monalithic'
printf '%s\n' "$config" | rg -q 'published: "9852"'
printf '%s\n' "$config" | rg -q 'target: 8080'
printf '%s\n' "$config" | rg -q 'FRIGATE__FRIGATE_URL: http://frigate:5000'
printf '%s\n' "$config" | rg -q '^  yawamf_network:$'
printf '%s\n' "$config" | rg -q '^    external: true$'
! printf '%s\n' "$config" | rg -q 'wamf-backend|wamf-frontend|yawamf-backend|yawamf-frontend'
