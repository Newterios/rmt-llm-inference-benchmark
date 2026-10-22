"""Recompute all summary tables from the raw JSONL run files.

Reads every runs/<condition>/*.jsonl, keeps only non-warmup request records, and writes:
  results/requests_all.csv      every request, one row (the processed data file)
  results/summary_by_level.csv  one row per (condition, task, set, concurrency, repeat)
  results/summary_by_condition.csv  medians across repeats per (condition, task, set, concurrency)
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "runs"
OUT = ROOT / "results"
OUT.mkdir(exist_ok=True)


def load_requests():
    rows = []
    for path in sorted(p for p in RUNS.glob("*/*.jsonl") if not p.parent.name.startswith("_")):
        for line in open(path, encoding="utf-8"):
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("type") == "request" and not obj.get("warmup"):
                obj["run_file"] = str(path.relative_to(ROOT))
                obj.pop("text", None)  # outputs stay in the raw JSONL only
                rows.append(obj)
    return pd.DataFrame(rows)


def pct(s, q):
    s = s.dropna()
    return float(np.percentile(s, q)) if len(s) else np.nan


def main():
    df = load_requests()
    if df.empty:
        print("no runs found")
        return
    df.to_csv(OUT / "requests_all.csv", index=False)
    keys = ["condition", "task", "set", "concurrency", "repeat"]
    rows = []
    for k, g in df.groupby(keys):
        ok = g[g.status == "ok"]
        t0 = pd.to_datetime(g.t_start).min()
        # wall time of the level: from first request start to last request end
        ends = pd.to_datetime(g.t_start) + pd.to_timedelta(g.latency_s, unit="s")
        wall = (ends.max() - t0).total_seconds()
        row = dict(zip(keys, k))
        row.update({
            "n": len(g), "n_ok": len(ok), "fail_rate": round(1 - len(ok) / len(g), 4),
            "wall_s": round(wall, 2),
            "req_per_s": round(len(ok) / wall, 4) if wall else np.nan,
            "agg_out_tok_per_s": round(ok.completion_tokens.sum() / wall, 2) if wall else np.nan,
            "ttft_p50_s": round(pct(ok.ttft_s, 50), 3), "ttft_p95_s": round(pct(ok.ttft_s, 95), 3),
            "latency_p50_s": round(pct(ok.latency_s, 50), 3), "latency_p95_s": round(pct(ok.latency_s, 95), 3),
            "decode_tok_per_s_p50": round(pct(ok.decode_tok_per_s, 50), 2),
            "prompt_tok_mean": round(ok.prompt_tokens.mean(), 1), "out_tok_mean": round(ok.completion_tokens.mean(), 1),
            "tokens_estimated": bool(ok.tokens_estimated.any()) if "tokens_estimated" in ok else False,
            "cost_usd": round(ok.cost_usd.sum(), 6) if ok.cost_usd.notna().any() else np.nan,
            "accuracy": round(ok.correct.sum() / len(g), 4) if "correct" in g and g.task.iloc[0] == "quality" else np.nan,
            "sustainable_req_per_day": round(len(ok) / wall * 86400) if wall else np.nan,
            "errors": "; ".join(sorted({str(e)[:60] for e in g[g.status != "ok"].error.dropna()}))[:300],
        })
        rows.append(row)
    lvl = pd.DataFrame(rows).sort_values(keys)
    lvl.to_csv(OUT / "summary_by_level.csv", index=False)
    agg_keys = ["condition", "task", "set", "concurrency"]
    num = lvl.select_dtypes("number").columns.difference(agg_keys + ["repeat"])
    cond = lvl.groupby(agg_keys)[list(num)].median().reset_index()
    cond["repeats"] = lvl.groupby(agg_keys).repeat.count().values
    cond.to_csv(OUT / "summary_by_condition.csv", index=False)
    pd.set_option("display.width", 250, "display.max_columns", 30)
    print(lvl[["condition", "task", "set", "concurrency", "repeat", "n_ok", "n", "wall_s", "req_per_s",
               "agg_out_tok_per_s", "ttft_p50_s", "latency_p50_s", "latency_p95_s", "decode_tok_per_s_p50",
               "cost_usd", "accuracy"]].to_string(index=False))


if __name__ == "__main__":
    main()
