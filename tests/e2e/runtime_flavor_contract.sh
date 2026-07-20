#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HELPER="$ROOT/docker/runtime-flavor.sh"

test "$("$HELPER" requirements full amd64)" = "requirements-provider-full.txt"
test "$("$HELPER" requirements cpu amd64)" = "requirements-provider-cpu.txt"
test "$("$HELPER" requirements intel amd64)" = "requirements-provider-intel.txt"
test "$("$HELPER" requirements cuda amd64)" = "requirements-provider-cuda.txt"
test "$("$HELPER" requirements rpi arm64)" = "requirements-provider-cpu.txt"

"$HELPER" needs-intel-runtime full amd64
"$HELPER" needs-intel-runtime intel amd64
! "$HELPER" needs-intel-runtime cpu amd64
! "$HELPER" needs-intel-runtime cuda amd64
! "$HELPER" needs-intel-runtime rpi arm64

test "$("$HELPER" packaged-providers full amd64)" = "cpu,cuda,intel_cpu,intel_gpu,intel_npu"
test "$("$HELPER" packaged-providers cpu amd64)" = "cpu"
test "$("$HELPER" packaged-providers intel amd64)" = "cpu,intel_cpu,intel_gpu,intel_npu"
test "$("$HELPER" packaged-providers cuda amd64)" = "cpu,cuda"
test "$("$HELPER" packaged-providers rpi arm64)" = "cpu"

! "$HELPER" validate intel arm64 >/dev/null 2>&1
! "$HELPER" validate cuda arm64 >/dev/null 2>&1
! "$HELPER" validate rpi amd64 >/dev/null 2>&1
! "$HELPER" validate unexpected amd64 >/dev/null 2>&1
