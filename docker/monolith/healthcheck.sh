#!/usr/bin/env bash
set -euo pipefail

curl -fsS http://127.0.0.1:8080/health >/dev/null
curl -fsS http://127.0.0.1:8000/ready >/dev/null
