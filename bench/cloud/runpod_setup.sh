#!/usr/bin/env bash
# Rented GPU condition. Tested target: RunPod or Vast.ai pod with one RTX 4090, Ubuntu 22.04 image
# with CUDA 12.x. Run this inside the pod (ssh or web terminal). Takes about 10 minutes.
set -euo pipefail
apt-get update -qq && apt-get install -y -qq git curl python3-venv build-essential cmake > /dev/null
git clone https://github.com/Newterios/rmt-llm-inference-benchmark.git
cd rmt-llm-inference-benchmark
python3 -m venv .venv && .venv/bin/pip install -q httpx pandas numpy tqdm psutil python-dotenv anthropic
# build llama.cpp for CUDA (pin the same major build as on the Mac if possible)
git clone --depth 1 https://github.com/ggml-org/llama.cpp.git /opt/llama.cpp
cmake -S /opt/llama.cpp -B /opt/llama.cpp/build -DGGML_CUDA=ON -DCMAKE_BUILD_TYPE=Release > /dev/null
cmake --build /opt/llama.cpp/build --target llama-server -j "$(nproc)" > /dev/null
curl -L -o models/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf \
  https://huggingface.co/bartowski/Meta-Llama-3.1-8B-Instruct-GGUF/resolve/main/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf
sha256sum models/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf
nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv
nohup /opt/llama.cpp/build/bin/llama-server -m models/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf \
  --alias llama-3.1-8b-instruct-q4_k_m --host 127.0.0.1 --port 8080 \
  -c 16384 -np 16 -b 2048 -ub 512 -ngl 99 -fa on --no-cache-prompt --metrics --reasoning off \
  > runs/rented_server.log 2>&1 &
until curl -s http://127.0.0.1:8080/health | grep -q ok; do sleep 2; done
mkdir -p runs/rented_rtx4090
nohup bash -c 'nvidia-smi --query-gpu=timestamp,power.draw,utilization.gpu,memory.used --format=csv -l 1' \
  > runs/rented_rtx4090/power_$(date +%Y%m%d-%H%M%S).csv 2>&1 &
PY=.venv/bin/python
$PY bench/run.py --condition rented_rtx4090 --task throughput --set pilot --concurrency 1 4 16 --repeats 2
$PY bench/run.py --condition rented_rtx4090 --task throughput --set main  --concurrency 1 4 16 --repeats 3
$PY bench/run.py --condition rented_rtx4090 --task quality    --set main  --concurrency 4 --repeats 2
echo "DONE. Now copy runs/rented_rtx4090 and runs/rented_server.log back (scp or git push with a token)."
