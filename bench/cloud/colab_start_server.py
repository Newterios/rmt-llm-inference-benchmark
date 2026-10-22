"""Start llama-server inside the Colab runtime with the fixed benchmark configuration.
Port 8090 is used because Colab itself occupies 8080. Defines `server` and `power` for the notebook."""
import json, os, subprocess, time, httpx
from datetime import datetime
cond = json.load(open("bench/conditions.json"))["rented_colab_gpu"]
port = cond["base_url"].split(":")[-1].split("/")[0]
os.makedirs("runs/rented_colab_gpu", exist_ok=True)
server = subprocess.Popen(["/content/llama.cpp/build/bin/llama-server", "-m", "models/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf",
    "--alias", "llama-3.1-8b-instruct-q4_k_m", "--host", "127.0.0.1", "--port", port,
    "-c", "16384", "-np", "16", "-b", "2048", "-ub", "512", "-ngl", "99", "-fa", "on",
    "--no-cache-prompt", "--metrics", "--reasoning", "off"],
    stdout=open("runs/rented_server.log", "w"), stderr=subprocess.STDOUT)
for _ in range(150):
    try:
        if httpx.get(f"http://127.0.0.1:{port}/health", timeout=2).status_code == 200:
            break
    except Exception:
        pass
    if server.poll() is not None:
        print(open("runs/rented_server.log").read()[-3000:]); raise SystemExit("llama-server exited")
    time.sleep(2)
props = httpx.get(f"http://127.0.0.1:{port}/props").json()
print({k: props.get(k) for k in ("model_path", "total_slots", "build_info")},
      "n_ctx per slot:", props.get("default_generation_settings", {}).get("n_ctx"))
stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
power = subprocess.Popen(f"nvidia-smi --query-gpu=timestamp,name,power.draw,utilization.gpu,memory.used,temperature.gpu --format=csv -l 1 > runs/rented_colab_gpu/power_{stamp}.csv", shell=True)
os.system("grep -E 'offloaded|n_slots|listening' runs/rented_server.log")
