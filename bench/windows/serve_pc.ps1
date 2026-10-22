# Same server configuration as bench/serve_mac.sh: 16 slots x 1024 tokens, prompt cache off.
$model = Join-Path $PSScriptRoot "..\..\models\Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf"
$server = "C:\llama\llama-server.exe"
if (-not (Test-Path $server)) { Write-Error "llama-server.exe not found at $server"; exit 1 }
& $server -m $model --alias llama-3.1-8b-instruct-q4_k_m --host 127.0.0.1 --port 8080 `
  -c 16384 -np 16 -b 2048 -ub 512 -ngl 99 -fa on --no-cache-prompt --metrics --reasoning off
