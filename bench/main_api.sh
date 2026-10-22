#!/usr/bin/env bash
# Main protocol for one hosted condition. Usage: bench/main_api.sh api_groq
set -euo pipefail
cd "$(dirname "$0")/.."
PY=.venv/bin/python
C=$1
$PY bench/run.py --condition "$C" --task throughput --set main --concurrency 1 4 16 --repeats 3
$PY bench/run.py --condition "$C" --task quality    --set main --concurrency 4 --repeats 2
