#!/usr/bin/env bash
# Start llama-server on the Mac with the fixed benchmark configuration.
# 16 parallel slots x 1024 tokens of context each = 16384 tokens shared context,
# prompt caching off so that repeated prompts are not served from cache.
set -euo pipefail
cd "$(dirname "$0")/.."
MODEL=${MODEL:-models/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf}
ALIAS=${ALIAS:-llama-3.1-8b-instruct-q4_k_m}
exec llama-server -m "$MODEL" --alias "$ALIAS" \
  --host 127.0.0.1 --port 8080 \
  -c 16384 -np 16 -b 2048 -ub 512 -ngl 99 -fa on \
  --no-cache-prompt --metrics --reasoning off \
  "$@"
