#!/usr/bin/env bash
# Main protocol for the Mac condition.
set -euo pipefail
cd "$(dirname "$0")/.."
PY=.venv/bin/python
$PY bench/run.py --condition mac_m4pro --task throughput --set main --concurrency 1 4 16 --repeats 3
$PY bench/run.py --condition mac_m4pro --task quality    --set main --concurrency 4 --repeats 2
