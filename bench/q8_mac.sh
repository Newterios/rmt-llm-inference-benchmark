#!/usr/bin/env bash
# Quantization comparison: same Mac, Q8_0 file. Waits for the Q4 main run to finish, swaps the server, runs the protocol.
set -euo pipefail
cd "$(dirname "$0")/.."
PY=.venv/bin/python
while pgrep -f "bench/main_mac.sh" > /dev/null; do sleep 15; done
pkill -f "llama-server -m models/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf" || true
sleep 5
MODEL=models/Meta-Llama-3.1-8B-Instruct-Q8_0.gguf ALIAS=llama-3.1-8b-instruct-q8_0 nohup ./bench/serve_mac.sh > runs/mac_server_q8.log 2>&1 &
until curl -s -m 2 http://127.0.0.1:8080/health | grep -q '"ok"'; do sleep 2; done
echo "Q8 server up $(date +%H:%M:%S)"
$PY bench/run.py --condition mac_m4pro_q8 --task quality    --set main --concurrency 4 --repeats 2
$PY bench/run.py --condition mac_m4pro_q8 --task throughput --set main --concurrency 1 16 --repeats 2
echo "Q8 done $(date +%H:%M:%S)"
