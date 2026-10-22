#!/usr/bin/env bash
# Main then pilot protocol for one hosted condition. Usage: bench/full_api.sh api_deepinfra
set -euo pipefail
cd "$(dirname "$0")/.."
./bench/main_api.sh "$1"
./bench/pilot_api.sh "$1"
