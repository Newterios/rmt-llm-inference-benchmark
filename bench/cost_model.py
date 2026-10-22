"""Cost per 1,000 requests for each condition at daily volumes, from measured data + prices.json.

Local machine at volume V requests/day:
    daily_cost = attribution * price_usd / (365 * years) + kWh(V) * tariff
    kWh(V)     = (busy_h * P_load + (24 - busy_h) * P_idle) / 1000,  busy_h = V / (RPS_16 * 3600)
    cost_1000  = daily_cost / V * 1000 ; V above capacity (RPS_16 * 86400) is "not servable".
Hosted API:
    cost_1000  = 1000 * mean(provider-reported cost per request)  (or list price x measured tokens)
Rented GPU:
    cost_1000  = 24 h * usd_per_hour / V * 1000, same capacity rule.
Two attribution scenarios are written: dedicated (1.0) and shared_dev_machine (0.25).
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
PRICES = json.load(open(ROOT / "bench" / "prices.json"))
VOLUMES = [1_000, 10_000, 100_000]
GRID = np.unique(np.round(np.logspace(3, 5, 41)).astype(int))  # 1,000 .. 100,000


def local_cost_1000(h, V, cap_per_day, attribution):
    if V > cap_per_day:
        return None
    busy_h = V / (cap_per_day / 24)
    load_w = h["load_watts_measured"] or h.get("load_watts_assumed") or 0
    kwh = (busy_h * load_w + (24 - busy_h) * h["idle_watts_assumed"]) / 1000
    daily = attribution * h["price_usd"] / (365 * PRICES["amortization_years"]) \
        + kwh * PRICES["electricity_kzt_per_kwh"] * PRICES["usd_per_kzt"]
    return daily / V * 1000


def main(set_name="main"):
    cnd = pd.read_csv(ROOT / "results" / "summary_by_condition.csv")
    th = cnd[(cnd.task == "throughput") & (cnd.set == set_name)]
    rows, breakeven = [], []
    api_cost = {}
    for cond, g in th.groupby("condition"):
        cap_row = g.loc[g.concurrency.idxmax()]
        cap = float(cap_row.sustainable_req_per_day)
        if cond in PRICES["api_usd_per_million_tokens"]:
            p = PRICES["api_usd_per_million_tokens"][cond]
            per_req = cap_row.cost_usd / cap_row.n_ok if pd.notna(cap_row.cost_usd) and cap_row.n_ok else \
                (cap_row.prompt_tok_mean * p["input"] + cap_row.out_tok_mean * p["output"]) / 1e6
            api_cost[cond] = 1000 * per_req
    baseline = min(api_cost, key=api_cost.get) if api_cost else None
    for cond, g in th.groupby("condition"):
        cap_row = g.loc[g.concurrency.idxmax()]
        cap = float(cap_row.sustainable_req_per_day)
        for scen, attribution in PRICES["attribution_scenarios"].items():
            if cond in api_cost and scen != "dedicated":
                continue
            for V in VOLUMES:
                r = {"condition": cond, "scenario": scen if cond not in api_cost else "n/a", "volume_per_day": V,
                     "capacity_req_per_day": int(cap), "servable": V <= cap,
                     "prompt_tok_mean": round(cap_row.prompt_tok_mean, 1), "out_tok_mean": round(cap_row.out_tok_mean, 1)}
                if cond in api_cost:
                    r["cost_per_1000_usd"] = api_cost[cond]; r["servable"] = True
                    r["basis"] = "provider-reported usage.cost x 1000" if pd.notna(cap_row.cost_usd) else "list price x measured tokens"
                elif cond == "rented_rtx4090":
                    h = PRICES["hardware"][cond]
                    r["cost_per_1000_usd"] = 24 * h["usd_per_hour"] / V * 1000 if V <= cap else None
                    r["basis"] = "24 h rent / volume"
                else:
                    h = PRICES["hardware"][cond]
                    r["cost_per_1000_usd"] = local_cost_1000(h, V, cap, attribution)
                    r["basis"] = f"{attribution:.2f} x {h['price_usd']} USD / 3 y + electricity"
                rows.append(r)
            # break-even search against the cheapest hosted provider
            if cond not in api_cost and baseline:
                h = PRICES["hardware"][cond]
                be = None
                for V in GRID:
                    c = (24 * h["usd_per_hour"] / V * 1000 if V <= cap else None) if cond == "rented_rtx4090" \
                        else local_cost_1000(h, int(V), cap, attribution)
                    if c is not None and c < api_cost[baseline]:
                        be = int(V); break
                breakeven.append({"condition": cond, "scenario": scen, "baseline": baseline,
                                  "baseline_cost_per_1000_usd": round(api_cost[baseline], 5),
                                  "capacity_req_per_day": int(cap), "break_even_req_per_day": be,
                                  "note": "none below capacity" if be is None else "found"})
    out = pd.DataFrame(rows)
    out["cost_per_1000_usd"] = out["cost_per_1000_usd"].astype(float).round(5)
    out.to_csv(ROOT / "results" / f"cost_per_1000_{set_name}.csv", index=False)
    be = pd.DataFrame(breakeven)
    be.to_csv(ROOT / "results" / f"break_even_{set_name}.csv", index=False)
    pd.set_option("display.width", 200)
    print(out.to_string(index=False)); print(); print(be.to_string(index=False))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "main")
