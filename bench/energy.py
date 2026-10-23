"""Mean power during each run level, from the power logs.

Mac: powermetrics text log (cpu_power, gpu_power samplers): one sample per second with
'*** Sampled system activity (<date>) ...' headers, 'CPU Power: N mW', 'GPU Power: N mW'.
PC / Colab: nvidia-smi CSV with timestamp and power.draw [W] (GPU only).
Writes results/power_by_level.csv: condition, task, set, concurrency, repeat, mean_watts, samples.
"""
import re
import glob
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RES = ROOT / "results"


def parse_powermetrics(path):
    rows, ts, cpu, gpu = [], None, None, None
    for line in open(path, errors="replace"):
        m = re.match(r"\*\*\* Sampled system activity \((.+?)\)", line)
        if m:
            if ts is not None:
                rows.append((ts, (cpu or 0) + (gpu or 0), cpu, gpu))
            ts = pd.to_datetime(m.group(1).split(" +")[0].split(" -")[0], errors="coerce")
            cpu = gpu = None
            continue
        m = re.match(r"CPU Power:\s*(\d+)\s*mW", line)
        if m:
            cpu = int(m.group(1)) / 1000
        m = re.match(r"GPU Power:\s*(\d+)\s*mW", line)
        if m:
            gpu = int(m.group(1)) / 1000
    if ts is not None:
        rows.append((ts, (cpu or 0) + (gpu or 0), cpu, gpu))
    df = pd.DataFrame(rows, columns=["t", "watts", "cpu_w", "gpu_w"]).dropna(subset=["t"])
    df["t"] = df["t"].dt.tz_localize(None)
    return df


def parse_nvidia_smi(path):
    df = pd.read_csv(path, skipinitialspace=True)
    df.columns = [c.strip() for c in df.columns]
    tcol = [c for c in df.columns if "timestamp" in c][0]
    pcol = [c for c in df.columns if "power.draw" in c][0]
    df["t"] = pd.to_datetime(df[tcol], errors="coerce")
    df["watts"] = pd.to_numeric(df[pcol].astype(str).str.replace(" W", ""), errors="coerce")
    return df[["t", "watts"]].dropna()


def main():
    logs = []
    for p in glob.glob(str(ROOT / "runs" / "*" / "power_*")):
        cond = Path(p).parent.name
        try:
            df = parse_powermetrics(p) if p.endswith(".txt") else parse_nvidia_smi(p)
        except Exception as e:
            print("skip", p, e); continue
        if cond.startswith("rented_colab"):
            # the Colab VM clock is UTC; request timestamps are converted to Astana time below
            df["t"] = df["t"].dt.tz_localize("UTC").dt.tz_convert("Asia/Almaty").dt.tz_localize(None)
        df["condition"] = cond
        logs.append(df)
    if not logs:
        print("no power logs"); return
    power = pd.concat(logs, ignore_index=True)
    req = pd.read_csv(RES / "requests_all.csv")
    req["t0"] = pd.to_datetime(req.t_start, utc=True).dt.tz_convert("Asia/Almaty").dt.tz_localize(None)
    req["t1"] = req["t0"] + pd.to_timedelta(req.latency_s, unit="s")
    out = []
    for k, g in req.groupby(["condition", "task", "set", "concurrency", "repeat"]):
        # power logs live in the folder of the physical machine; derived conditions share it
        base = k[0].replace("_loaded", "").replace("_q8", "")
        pw = power[power.condition == base]
        if pw.empty:
            continue
        a, b = g.t0.min(), g.t1.max()
        w = pw[(pw.t >= a) & (pw.t <= b)]
        if len(w):
            out.append(dict(zip(["condition", "task", "set", "concurrency", "repeat"], k)) |
                       {"mean_watts": round(w.watts.mean(), 1), "max_watts": round(w.watts.max(), 1), "samples": len(w),
                        "window_s": round((b - a).total_seconds(), 1)})
    res = pd.DataFrame(out)
    res.to_csv(RES / "power_by_level.csv", index=False)
    print(res.to_string(index=False))


if __name__ == "__main__":
    main()
