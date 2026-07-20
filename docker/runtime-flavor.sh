#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "usage: runtime-flavor.sh <validate|requirements|needs-intel-runtime|packaged-providers> <flavor> <arch>" >&2
  exit 64
}

command="${1:-}"
flavor="${2:-}"
arch="${3:-}"

validate() {
  case "$flavor" in
    full|cpu|intel|cuda|rpi) ;;
    *)
      echo "unsupported YA-WAMF runtime flavor: $flavor" >&2
      return 64
      ;;
  esac

  case "$arch" in
    amd64|arm64|aarch64) ;;
    *)
      echo "unsupported YA-WAMF image architecture: $arch" >&2
      return 64
      ;;
  esac

  if [[ "$flavor" == "rpi" && "$arch" != "arm64" && "$arch" != "aarch64" ]]; then
    echo "the rpi runtime flavor requires arm64" >&2
    return 64
  fi
  if [[ ("$flavor" == "full" || "$flavor" == "intel" || "$flavor" == "cuda") && "$arch" != "amd64" ]]; then
    echo "the $flavor runtime flavor requires amd64" >&2
    return 64
  fi
}

[[ -n "$command" && -n "$flavor" && -n "$arch" ]] || usage
validate

case "$command" in
  validate)
    ;;
  requirements)
    if [[ "$flavor" == "rpi" ]]; then
      echo "requirements-provider-cpu.txt"
    else
      echo "requirements-provider-$flavor.txt"
    fi
    ;;
  needs-intel-runtime)
    [[ "$flavor" == "full" || "$flavor" == "intel" ]]
    ;;
  packaged-providers)
    case "$flavor" in
      full) echo "cpu,cuda,intel_cpu,intel_gpu,intel_npu" ;;
      cpu|rpi) echo "cpu" ;;
      intel) echo "cpu,intel_cpu,intel_gpu,intel_npu" ;;
      cuda) echo "cpu,cuda" ;;
    esac
    ;;
  *)
    usage
    ;;
esac
