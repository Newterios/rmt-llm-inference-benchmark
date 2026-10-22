# Running the PC (RTX 4060) condition on Windows

1. Install Python 3.11+ (python.org, tick "Add to PATH") and Git for Windows.
2. Download the CUDA build of llama.cpp: https://github.com/ggml-org/llama.cpp/releases
   take `llama-<build>-bin-win-cuda-12.x-x64.zip` AND `cudart-llama-bin-win-cuda-12.x-x64.zip`,
   unzip both into `C:\llama\` so that `C:\llama\llama-server.exe` exists.
3. Clone the repo and create the environment:
   ```powershell
   git clone https://github.com/Newterios/rmt-llm-inference-benchmark.git
   cd rmt-llm-inference-benchmark
   py -m venv .venv
   .\.venv\Scripts\pip install httpx pandas numpy tqdm psutil python-dotenv anthropic
   ```
4. Download the model into `models\` (same file and checksum as on the Mac):
   ```powershell
   curl.exe -L -o models\Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf https://huggingface.co/bartowski/Meta-Llama-3.1-8B-Instruct-GGUF/resolve/main/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf
   ```
5. Open PowerShell window 1 and start the server:
   ```powershell
   .\bench\windows\serve_pc.ps1
   ```
   Wait for "server is listening". Check that it says `offloaded 33/33 layers to GPU`.
6. Open PowerShell window 2 and start the power logger (keep it running during the whole run):
   ```powershell
   .\bench\windows\power_pc.ps1
   ```
7. Open PowerShell window 3 and run the benchmark:
   ```powershell
   .\bench\windows\run_pc.ps1
   ```
8. Take screenshots of: window 1 (server log with layers offloaded), `nvidia-smi` during the run,
   and window 3 when it prints `done:`. Put them in `figures\pc\`.
9. Commit and push:
   ```powershell
   git add runs results figures
   git commit -m "PC RTX 4060 runs"
   git push
   ```
