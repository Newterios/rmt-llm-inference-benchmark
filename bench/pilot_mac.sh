#!/usr/bin/env bash
# Pilot protocol for the Mac condition (two full pilot trials at every concurrency level).
set -euo pipefail
cd "$(dirname "$0")/.."
PY=.venv/bin/python
$PY bench/run.py --condition mac_m4pro --task throughput --set pilot --concurrency 1 4 16 --repeats 2
$PY bench/run.py --condition mac_m4pro --task quality    --set pilot --concurrency 4 --repeats 1
$PY bench/summarize.py
