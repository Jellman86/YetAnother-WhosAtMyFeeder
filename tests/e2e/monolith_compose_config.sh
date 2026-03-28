#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

for file in docker-compose.yml docker-compose.prod.yml docker-compose.dev.yml; do
  services="$(docker compose -f "$ROOT/$file" config --services)"
  echo "$services"
  test "$services" = "yawamf"
done
