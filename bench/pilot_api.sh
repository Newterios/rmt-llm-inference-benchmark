#!/usr/bin/env bash
# Pilot protocol for one hosted condition. Usage: bench/pilot_api.sh api_groq
set -euo pipefail
cd "$(dirname "$0")/.."
PY=.venv/bin/python
C=$1
$PY bench/run.py --condition "$C" --task throughput --set pilot --concurrency 1 4 16 --repeats 2
$PY bench/run.py --condition "$C" --task quality    --set pilot --concurrency 4 --repeats 1
