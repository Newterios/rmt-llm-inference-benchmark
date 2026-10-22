"""Cost per 1,000 requests for each condition at daily volumes, from measured data + prices.json.

Local machine, volume V requests/day:
    cost_per_day = hardware_price / (365 * years) + energy_kwh_per_day * price_kwh
    energy_kwh_per_day = (busy_hours * load_watts + (24 - busy_hours) * idle_watts) / 1000
    busy_hours = V / capacity_req_per_hour      (capacity measured at concurrency 16)
    cost_per_1000 = cost_per_day / V * 1000;  if V > capacity_req_per_day the volume is not servable.
Hosted API:
    cost_per_1000 = 1000 * (mean_prompt_tokens * p_in + mean_output_tokens * p_out) / 1e6
    (or the provider-reported cost per request when OpenRouter returns usage.cost).
Rented GPU, volume V:
    cost_per_day = 24 * usd_per_hour (instance kept up) ; same capacity rule.
"""
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
PRICES = json.load(open(ROOT / "bench" / "prices.json"))
VOLUMES = [1_000, 10_000, 100_000]


def main(task="throughput", set_name="main"):
    lvl = pd.read_csv(ROOT / "results" / "summary_by_condition.csv")
    lvl = lvl[(lvl.task == task) & (lvl.set == set_name)]
    rows = []
    for cond, g in lvl.groupby("condition"):
        cap_row = g.loc[g.concurrency.idxmax()]
        cap_per_day = cap_row.sustainable_req_per_day
        in_tok, out_tok = cap_row.prompt_tok_mean, cap_row.out_tok_mean
        cost_per_req_api = cap_row.cost_usd / cap_row.n_ok if pd.notna(cap_row.cost_usd) and cap_row.n_ok else None
        for V in VOLUMES:
            r = {"condition": cond, "volume_per_day": V, "capacity_req_per_day": int(cap_per_day),
                 "servable": V <= cap_per_day, "prompt_tok_mean": in_tok, "out_tok_mean": out_tok}
            if cond in PRICES["api_usd_per_million_tokens"]:
                p = PRICES["api_usd_per_million_tokens"][cond]
                list_cost = (in_tok * p["input"] + out_tok * p["output"]) / 1e6
                r["cost_per_1000_usd"] = 1000 * (cost_per_req_api if cost_per_req_api else list_cost)
                r["basis"] = "provider-reported usage.cost" if cost_per_req_api else "list price x measured tokens"
                r["servable"] = True
            elif cond == "rented_rtx4090":
                h = PRICES["hardware"][cond]
                r["cost_per_1000_usd"] = 24 * h["usd_per_hour"] / V * 1000 if V <= cap_per_day else None
                r["basis"] = "24h instance rent / volume"
            else:
                h = PRICES["hardware"][cond]
                busy_h = V / (cap_per_day / 24)
                load_w = h["load_watts_measured"] or h.get("load_watts_assumed") or 0
                kwh = (busy_h * load_w + max(0, 24 - busy_h) * h["idle_watts_assumed"]) / 1000
                daily = h["price_kzt"] * PRICES["usd_per_kzt"] / (365 * PRICES["amortization_years"]) \
                    + kwh * PRICES["electricity_kzt_per_kwh"] * PRICES["usd_per_kzt"]
                r["cost_per_1000_usd"] = daily / V * 1000 if V <= cap_per_day else None
                r["basis"] = f"amortization {PRICES['amortization_years']}y + electricity ({load_w} W load)"
            rows.append(r)
    out = pd.DataFrame(rows)
    out["cost_per_1000_usd"] = out["cost_per_1000_usd"].round(5)
    out.to_csv(ROOT / "results" / f"cost_per_1000_{set_name}.csv", index=False)
    # break-even search: smallest V (log grid) where local cost < cheapest API cost
    print(out.to_string(index=False))
    return out


if __name__ == "__main__":
    import sys
    main(set_name=sys.argv[1] if len(sys.argv) > 1 else "main")
