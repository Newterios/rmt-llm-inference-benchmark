"""Assignment 4 analysis. Reads only files that already exist (runs/*.jsonl, results/*.csv,
bench/prices.json) and writes results/a4_*.csv and figures/a4_*.png. No new requests are sent.

Formulas used
  Wilson 95% interval for an accuracy p = k/n (z = 1.96):
      centre = (p + z^2/2n) / (1 + z^2/n),  half = z * sqrt(p(1-p)/n + z^2/4n^2) / (1 + z^2/n)
  Exact McNemar test for two conditions answering the same 100 items (repeat 1 of each):
      b = items right only in A, c = items right only in B,
      p = min(1, 2 * sum_{i=0..min(b,c)} C(b+c, i) / 2^(b+c))
  Repeat spread of a level = (max - min) / median of the repeats, in percent.
  Energy per 1,000 requests (Wh) = P_load (W) / req_per_s / 3.6
  Capacity if every answer had 256 tokens = aggregate output tokens/s / 256 * 86,400
"""
import json
import math
import re
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RES, FIG = ROOT / "results", ROOT / "figures"
PRICES = json.load(open(ROOT / "bench" / "prices.json"))
LAB = {"mac_m4pro": "Mac M4 Pro Q4", "mac_m4pro_q8": "Mac M4 Pro Q8", "mac_m4pro_loaded": "Mac in use Q4",
       "pc_rtx4060": "PC RTX 4060 Q4", "pc_rtx4060_budget": "Budget box RTX 4060",
       "rented_colab_gpu": "Colab T4 run 1", "rented_colab_t4_run2": "Colab T4 run 2",
       "api_deepinfra": "DeepInfra fp8", "api_cloudflare": "Cloudflare fp8", "api_groq": "Groq",
       "api_coreweave": "CoreWeave bf16", "api_claude_haiku": "Claude Haiku 5.5"}
MAIN = ["mac_m4pro", "mac_m4pro_q8", "pc_rtx4060", "rented_colab_gpu", "rented_colab_t4_run2",
        "api_deepinfra", "api_cloudflare", "api_groq", "api_coreweave", "api_claude_haiku"]
LLAMA = [c for c in MAIN if c != "api_claude_haiku"]


def wilson(k, n, z=1.96):
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - h, c + h


def mcnemar_exact(b, c):
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def load_quality_main(cond):
    rows = []
    for f in sorted((ROOT / "runs" / cond).glob("*_quality_main.jsonl")):
        for line in open(f):
            d = json.loads(line)
            if d.get("type") in ("meta", "level_summary") or "prompt_id" not in d or d.get("warmup"):
                continue
            d["run_file"] = str(f.relative_to(ROOT))
            rows.append(d)
    return pd.DataFrame(rows)


def main():
    req = pd.read_csv(RES / "requests_all.csv", low_memory=False)
    lvl = pd.read_csv(RES / "summary_by_level.csv")
    cond = pd.read_csv(RES / "summary_by_condition.csv")
    cost = pd.read_csv(RES / "cost_per_1000_main.csv", keep_default_na=False, na_values=[""])
    power = pd.read_csv(RES / "power_by_level.csv")

    # 1. Repeat-to-repeat spread vs differences between conditions (main throughput)
    th = lvl[(lvl.task == "throughput") & (lvl.set == "main") & lvl.condition.isin(MAIN + ["mac_m4pro_loaded"])]
    rv = th.groupby(["condition", "concurrency"]).agg(
        repeats=("repeat", "count"), agg_tok_s_min=("agg_out_tok_per_s", "min"),
        agg_tok_s_median=("agg_out_tok_per_s", "median"), agg_tok_s_max=("agg_out_tok_per_s", "max"),
        req_per_s_median=("req_per_s", "median"), latency_p50_median=("latency_p50_s", "median"),
        latency_p50_min=("latency_p50_s", "min"), latency_p50_max=("latency_p50_s", "max")).reset_index()
    rv["spread_pct"] = (rv.agg_tok_s_max - rv.agg_tok_s_min) / rv.agg_tok_s_median * 100
    rv.round(3).to_csv(RES / "a4_repeat_variability.csv", index=False)
    # pairwise gap between conditions at concurrency 16 vs the larger repeat spread of the two
    c16 = rv[(rv.concurrency == 16) & rv.condition.isin(MAIN)].set_index("condition")
    pairs = []
    for a in c16.index:
        for b in c16.index:
            if a >= b:
                continue
            ma, mb = c16.loc[a, "agg_tok_s_median"], c16.loc[b, "agg_tok_s_median"]
            gap = abs(ma - mb) / min(ma, mb) * 100
            sp = max(c16.loc[a, "spread_pct"], c16.loc[b, "spread_pct"])
            # ranges overlap?
            overlap = not (c16.loc[a, "agg_tok_s_max"] < c16.loc[b, "agg_tok_s_min"] or
                           c16.loc[b, "agg_tok_s_max"] < c16.loc[a, "agg_tok_s_min"])
            pairs.append({"condition_a": a, "condition_b": b, "median_a": ma, "median_b": mb,
                          "gap_pct": gap, "max_repeat_spread_pct": sp, "repeat_ranges_overlap": overlap,
                          "gap_exceeds_spread": (gap > sp) and not overlap})
    pd.DataFrame(pairs).round(2).to_csv(RES / "a4_condition_gaps_c16.csv", index=False)

    # 2. Accuracy with Wilson intervals, repeat flips, paired McNemar tests, wrong-answer classes
    acc_rows, flips, items, wrong = [], [], {}, []
    for c in MAIN:
        q = load_quality_main(c)
        q["correct"] = q["correct"].fillna(False).astype(bool)
        for r, g in q.groupby("repeat"):
            k, n = int(g.correct.sum()), len(g)
            lo, hi = wilson(k, n)
            acc_rows.append({"condition": c, "repeat": r, "correct": k, "n": n, "accuracy": k / n,
                             "wilson_low": lo, "wilson_high": hi})
        piv = q.pivot_table(index="prompt_id", columns="repeat", values="correct", aggfunc="first")
        flips.append({"condition": c, "items": len(piv), "items_changed_between_repeats": int((piv[1] != piv[2]).sum()),
                      "correct_in_both": int((piv[1] & piv[2]).sum()), "wrong_in_both": int((~piv[1] & ~piv[2]).sum())})
        items[c] = piv[1]
        for _, d in q[~q.correct].iterrows():
            txt = d.get("text") or ""
            has_marker = bool(re.search(r"Answer:\s*\$?-?[\d,]*\.?\d", txt))
            fr = d.get("finish_reason")
            if d.get("status") != "ok":
                cls = "request failed"
            elif fr in ("length", "max_tokens") and not has_marker:
                cls = "cut at 400 tokens before the answer line"
            elif not has_marker:
                cls = "no Answer line (last number taken)"
            else:
                cls = "wrong final number"
            wrong.append({"condition": c, "repeat": d["repeat"], "prompt_id": d["prompt_id"], "class": cls,
                          "gold": d.get("gold"), "pred": d.get("pred"), "finish_reason": fr,
                          "completion_tokens": d.get("completion_tokens"), "run_file": d["run_file"]})
    acc = pd.DataFrame(acc_rows)
    acc.round(4).to_csv(RES / "a4_accuracy_ci.csv", index=False)
    pd.DataFrame(flips).to_csv(RES / "a4_quality_repeat_flips.csv", index=False)
    wr = pd.DataFrame(wrong)
    wr.to_csv(RES / "a4_wrong_answers.csv", index=False)
    wcls = wr.groupby(["condition", "class"]).size().unstack(fill_value=0)
    wcls["total_wrong_answers"] = wcls.sum(axis=1)
    wcls.reset_index().to_csv(RES / "a4_wrong_answer_classes.csv", index=False)
    tests = []
    base = items["api_coreweave"]
    for c in MAIN:
        if c == "api_coreweave":
            continue
        a = items[c].reindex(base.index)
        b_only = int((a & ~base).sum()); c_only = int((~a & base).sum())
        tests.append({"condition": c, "baseline": "api_coreweave", "accuracy_condition": a.mean(),
                      "accuracy_baseline": base.mean(), "difference_points": (a.mean() - base.mean()) * 100,
                      "right_only_condition": b_only, "right_only_baseline": c_only,
                      "mcnemar_exact_p": mcnemar_exact(b_only, c_only)})
    pd.DataFrame(tests).round(4).to_csv(RES / "a4_paired_tests.csv", index=False)
    # items every Llama condition got wrong in repeat 1
    allw = pd.DataFrame({c: items[c] for c in LLAMA})
    hard = allw[~allw.any(axis=1)].index.tolist()
    prompts = {json.loads(l)["id"]: json.loads(l) for l in open(ROOT / "data" / "prompts" / "quality_main.jsonl")}
    raw = [json.loads(l) for l in open(ROOT / "data" / "raw" / "gsm8k_test.jsonl")]
    qm = load_quality_main("mac_m4pro")
    hw = []
    for p in hard:
        pr = prompts[p]
        mp = qm[(qm.prompt_id == p) & (qm.repeat == 1)].pred.iloc[0]
        hw.append({"prompt_id": p, "source_index": pr["source_index"], "question": pr["prompt"], "gold": pr["gold"],
                   "reference_solution_in_gsm8k": raw[pr["source_index"]]["answer"].replace("\n", " "),
                   "mac_q4_pred_repeat1": mp, "haiku_correct": bool(items["api_claude_haiku"].get(p)),
                   "llama_conditions_wrong": int((~allw.loc[p]).sum())})
    pd.DataFrame(hw).to_csv(RES / "a4_items_wrong_everywhere.csv", index=False)

    # 3. Request-level failure classes (all recorded requests)
    def fclass(r):
        e = str(r.error)
        if "429" in e:
            return "HTTP 429 rate limit (shared upstream pool)"
        if "ReadError" in e:
            return "connection closed mid-stream (ReadError)"
        if "imeout" in e:
            return "timeout"
        return "other"
    bad = req[req.status != "ok"].copy()
    bad["failure_class"] = bad.apply(fclass, axis=1)
    fc = bad.groupby(["condition", "failure_class", "task", "set", "concurrency", "repeat"]).size() \
        .rename("failed_requests").reset_index()
    tot = req.groupby(["condition", "task", "set", "concurrency", "repeat"]).size().rename("sent").reset_index()
    fc = fc.merge(tot, on=["condition", "task", "set", "concurrency", "repeat"])
    fc.to_csv(RES / "a4_error_classes.csv", index=False)
    ftot = req.groupby("condition").agg(sent=("status", "size"), failed=("status", lambda s: int((s != "ok").sum())))
    ftot["failure_pct"] = ftot.failed / ftot.sent * 100
    ftot.round(2).reset_index().to_csv(RES / "a4_failures_by_condition.csv", index=False)
    # DeepInfra failures per minute (Astana time)
    di = req[(req.condition == "api_deepinfra")].copy()
    di["minute"] = pd.to_datetime(di.t_start).dt.strftime("%H:%M")
    dim = di.groupby("minute").agg(sent=("status", "size"), failed=("status", lambda s: int((s != "ok").sum()))).reset_index()
    dim.to_csv(RES / "a4_deepinfra_by_minute.csv", index=False)
    # CoreWeave / Cloudflare connection errors: when did they happen
    rd = bad[bad.failure_class.str.startswith("connection")][["condition", "task", "set", "concurrency", "repeat", "prompt_id", "t_start", "latency_s", "error"]]
    rd.to_csv(RES / "a4_connection_errors.csv", index=False)

    # 4. Answer length and truncation (main throughput), capacity at 256-token answers
    tm = req[(req.task == "throughput") & (req.set == "main") & (req.status == "ok") & req.condition.isin(MAIN)]
    al = tm.groupby("condition").agg(requests=("completion_tokens", "size"), out_tok_mean=("completion_tokens", "mean"),
                                     out_tok_median=("completion_tokens", "median"),
                                     cut_at_256=("finish_reason", lambda s: int(s.isin(["length", "max_tokens"]).sum())))
    al["cut_pct"] = al.cut_at_256 / al.requests * 100
    al.round(2).reset_index().to_csv(RES / "a4_answer_length.csv", index=False)
    capr = []
    for c in ["mac_m4pro", "mac_m4pro_q8", "pc_rtx4060", "rented_colab_gpu", "rented_colab_t4_run2"]:
        r = cond[(cond.condition == c) & (cond.task == "throughput") & (cond.set == "main") & (cond.concurrency == 16)].iloc[0]
        capr.append({"condition": c, "agg_out_tok_per_s_c16": r.agg_out_tok_per_s, "out_tok_mean": r.out_tok_mean,
                     "capacity_measured_req_per_day": r.sustainable_req_per_day,
                     "capacity_if_256_token_answers": r.agg_out_tok_per_s / 256 * 86400})
    pd.DataFrame(capr).round(1).to_csv(RES / "a4_capacity_check.csv", index=False)

    # 5. Latency distribution per condition at concurrency 16 (main)
    l16 = tm[tm.concurrency == 16]
    ld = l16.groupby("condition").latency_s.describe(percentiles=[.05, .25, .5, .75, .95])
    ld.round(3).reset_index().to_csv(RES / "a4_latency_distribution_c16.csv", index=False)

    # 6. Resource cost: energy per 1,000 requests at concurrency 16
    rc = []
    for c in ["mac_m4pro", "pc_rtx4060", "rented_colab_gpu", "rented_colab_t4_run2"]:
        h = PRICES["hardware"].get(c, {})
        r = cond[(cond.condition == c) & (cond.task == "throughput") & (cond.set == "main") & (cond.concurrency == 16)].iloc[0]
        pw = power[(power.condition == c) & (power.task == "throughput") & (power.set == "main") & (power.concurrency == 16)]
        gpu_w = pw.mean_watts.mean() if len(pw) else np.nan
        rc.append({"condition": c, "req_per_s_c16": r.req_per_s, "measured_device_watts_c16": gpu_w,
                   "load_watts_in_cost_model": h.get("load_watts_measured"),
                   "wh_per_1000_requests_measured_device": gpu_w / r.req_per_s / 3.6 if gpu_w == gpu_w else np.nan,
                   "wh_per_1000_requests_cost_model": (h.get("load_watts_measured") or np.nan) / r.req_per_s / 3.6})
    pd.DataFrame(rc).round(2).to_csv(RES / "a4_resource_cost.csv", index=False)

    # 7. Cost curves on a fine grid, cost-quality at 100k/day, decision table
    grid = np.unique(np.round(np.logspace(3, np.log10(250_000), 241)).astype(int))
    curves = []
    cap_of = cost.groupby("condition").capacity_req_per_day.first()
    for c in ["mac_m4pro", "pc_rtx4060", "pc_rtx4060_budget"]:
        h = PRICES["hardware"][c]
        cap = cap_of[c]
        for scen, att in PRICES["attribution_scenarios"].items():
            for V in grid:
                if V > cap:
                    continue
                busy = V / (cap / 24)
                kwh = (busy * h["load_watts_measured"] + (24 - busy) * h["idle_watts_assumed"]) / 1000
                daily = att * h["price_usd"] / (365 * PRICES["amortization_years"]) + kwh * PRICES["electricity_kzt_per_kwh"] * PRICES["usd_per_kzt"]
                curves.append({"condition": c, "scenario": scen, "volume_per_day": V, "cost_per_1000_usd": daily / V * 1000})
    for c in ["rented_colab_gpu"]:
        h = PRICES["hardware"][c]
        hourly = h.get("usd_per_hour") or h["compute_units_per_hour"] * h["usd_per_compute_unit"]
        for V in grid:
            if V <= cap_of[c]:
                curves.append({"condition": c, "scenario": "rented 24 h", "volume_per_day": V, "cost_per_1000_usd": 24 * hourly / V * 1000})
    api = cost[cost.scenario == "n/a"].groupby("condition").cost_per_1000_usd.first()
    for c, v in api.items():
        for V in grid:
            curves.append({"condition": c, "scenario": "hosted", "volume_per_day": V, "cost_per_1000_usd": v})
    cu = pd.DataFrame(curves)
    cu.to_csv(RES / "a4_cost_curves.csv", index=False)
    # break-even on the fine grid against DeepInfra (cheapest) and Groq (cheapest within 5 points of bf16)
    bev = []
    for base in ["api_deepinfra", "api_groq"]:
        b = api[base]
        for (c, s), g in cu[~cu.scenario.eq("hosted")].groupby(["condition", "scenario"]):
            below = g[g.cost_per_1000_usd < b].sort_values("volume_per_day")
            bev.append({"condition": c, "scenario": s, "baseline": base, "baseline_cost_per_1000_usd": b,
                        "capacity_req_per_day": int(cap_of[c]),
                        "break_even_req_per_day": int(below.volume_per_day.iloc[0]) if len(below) else None,
                        "cost_at_capacity_edge": g.cost_per_1000_usd.min()})
    pd.DataFrame(bev).round(5).to_csv(RES / "a4_break_even_two_baselines.csv", index=False)
    _b = pd.DataFrame(bev)
    be2_groq_budget = float(_b[(_b.condition == "pc_rtx4060_budget") & (_b.scenario == "dedicated") & (_b.baseline == "api_groq")].break_even_req_per_day.iloc[0])
    be2_groq_pc = float(_b[(_b.condition == "pc_rtx4060") & (_b.scenario == "dedicated") & (_b.baseline == "api_groq")].break_even_req_per_day.iloc[0])
    accm = acc.groupby("condition").accuracy.mean()
    cq = []
    for c in MAIN + ["pc_rtx4060_budget"]:
        src = "pc_rtx4060" if c == "pc_rtx4060_budget" else c
        for scen in (["dedicated", "shared_dev_machine"] if c in PRICES["hardware"] and not c.startswith("rented") else ["n/a" if c in api.index else "dedicated"]):
            row = cost[(cost.condition == c) & (cost.scenario == scen) & (cost.volume_per_day == 100_000)]
            if row.empty:
                continue
            cq.append({"condition": c, "scenario": scen, "cost_per_1000_usd_at_100k": row.cost_per_1000_usd.iloc[0],
                       "gsm8k_accuracy_mean_of_repeats": accm.get(src, np.nan)})
    pd.DataFrame(cq).round(5).to_csv(RES / "a4_cost_quality_100k.csv", index=False)
    # decision table: cheapest option at each volume whose accuracy is within 5 points of bf16 (ER4 rule)
    bf16 = accm["api_coreweave"]
    dec = []
    for V in [1_000, 10_000, 100_000]:
        for scen in ["dedicated", "shared_dev_machine"]:
            opts = []
            for c in MAIN + ["pc_rtx4060_budget"]:
                src = "pc_rtx4060" if c == "pc_rtx4060_budget" else c
                s = "n/a" if c in api.index else scen
                if c.startswith("rented") and scen != "dedicated":
                    continue
                row = cost[(cost.condition == c) & (cost.scenario == s) & (cost.volume_per_day == V)]
                if row.empty or pd.isna(row.cost_per_1000_usd.iloc[0]):
                    continue
                a = accm.get(src, np.nan)
                fail = ftot.failure_pct.get(src, 0.0)
                opts.append((row.cost_per_1000_usd.iloc[0], c, a, fail))
            ok = [o for o in opts if o[2] >= bf16 - 0.05]
            best = min(ok)
            best_local = min([o for o in ok if not o[1].startswith("api_")])
            reliable = min([o for o in ok if o[3] < 2.0])
            dec.append({"volume_per_day": V, "hardware_scenario": scen,
                        "cheapest_within_5_points_of_bf16": best[1], "its_cost_per_1000_usd": best[0],
                        "its_failure_pct": best[3],
                        "cheapest_with_failures_below_2pct": reliable[1], "that_cost_per_1000_usd": reliable[0],
                        "cheapest_own_or_rented_hardware": best_local[1], "local_cost_per_1000_usd": best_local[0],
                        "local_to_cheapest_ratio": best_local[0] / best[0]})
    pd.DataFrame(dec).round(5).to_csv(RES / "a4_decision_table.csv", index=False)

    # 8. Output examples: one GSM8K item answered by four conditions
    ex_id = None
    q = {c: load_quality_main(c) for c in ["mac_m4pro", "api_deepinfra", "api_coreweave", "api_claude_haiku"]}
    r1 = {c: d[d.repeat == 1].set_index("prompt_id") for c, d in q.items()}
    for pid in r1["mac_m4pro"].index:
        vals = [bool(r1[c].loc[pid, "correct"]) for c in r1]
        if vals == [True, False, True, True]:
            ex_id = pid; break
    ex = []
    for c, d in r1.items():
        t = d.loc[ex_id]
        ex.append({"prompt_id": ex_id, "condition": c, "gold": t.gold, "pred": t.pred, "correct": bool(t.correct),
                   "completion_tokens": t.completion_tokens, "finish_reason": t.finish_reason,
                   "answer_last_300_chars": (t.text or "")[-300:].replace("\n", " ")})
    pd.DataFrame(ex).to_csv(RES / "a4_output_examples.csv", index=False)

    # 9. Derived values used in the expected-versus-observed table (one row per quantity)
    erc = []
    def add(er, what, value, source):
        erc.append({"er": er, "quantity": what, "value": value, "source": source})
    di_c = api["api_deepinfra"]
    for c in ["mac_m4pro", "pc_rtx4060", "pc_rtx4060_budget"]:
        for scen in ["dedicated", "shared_dev_machine"]:
            v = cost[(cost.condition == c) & (cost.scenario == scen) & (cost.volume_per_day == 1000)].cost_per_1000_usd.iloc[0]
            add("ER1", f"{c} {scen} cost at 1,000/day divided by DeepInfra cost", v / di_c, "cost_per_1000_main.csv")
    hk = api["api_claude_haiku"]
    for c in ["api_deepinfra", "api_groq", "api_coreweave", "api_cloudflare"]:
        add("ER7", f"Claude Haiku cost per 1,000 divided by {c}", hk / api[c], "cost_per_1000_main.csv")
    dec16 = cond[(cond.task == "throughput") & (cond.set == "main") & (cond.concurrency == 16)].set_index("condition")
    llama_api = ["api_groq", "api_coreweave", "api_deepinfra", "api_cloudflare"]
    sp = dec16.loc[llama_api, "decode_tok_per_s_p50"]
    add("ER6", "fastest / slowest median decode speed per request at concurrency 16 (Groq / Cloudflare)", sp.max() / sp.min(), "summary_by_condition.csv")
    la = accm[["api_groq", "api_coreweave", "api_deepinfra", "api_cloudflare", "mac_m4pro"]]
    add("ER6", "accuracy spread across hosted Llama providers, points", (accm[llama_api].max() - accm[llama_api].min()) * 100, "a4_accuracy_ci.csv")
    add("ER4", "Mac Q4 minus CoreWeave bf16, points", (accm["mac_m4pro"] - bf16) * 100, "a4_accuracy_ci.csv")
    add("ER4", "PC Q4 minus CoreWeave bf16, points", (accm["pc_rtx4060"] - bf16) * 100, "a4_accuracy_ci.csv")
    add("ER4", "DeepInfra fp8 minus CoreWeave bf16, points", (accm["api_deepinfra"] - bf16) * 100, "a4_accuracy_ci.csv")
    add("ER4", "Cloudflare fp8 minus CoreWeave bf16, points", (accm["api_cloudflare"] - bf16) * 100, "a4_accuracy_ci.csv")
    add("ER3", "PC capacity / upper bound expected (70,000)", dec16.loc["pc_rtx4060", "sustainable_req_per_day"] / 70000, "summary_by_condition.csv")
    add("ER3", "Mac capacity / upper bound expected (50,000)", dec16.loc["mac_m4pro", "sustainable_req_per_day"] / 50000, "summary_by_condition.csv")
    add("ER8", "DeepInfra failed requests / sent, percent", ftot.loc["api_deepinfra", "failure_pct"], "a4_failures_by_condition.csv")
    pc100 = cost[(cost.condition == "pc_rtx4060") & (cost.scenario == "dedicated") & (cost.volume_per_day == 100000)].cost_per_1000_usd.iloc[0]
    add("LIT", "Claude Haiku cost per 1,000 divided by PC dedicated at 100,000/day", hk / pc100, "cost_per_1000_main.csv")
    lat = pd.read_csv(RES / "a4_latency_distribution_c16.csv").set_index("condition")
    for c in ["mac_m4pro", "pc_rtx4060", "api_groq", "api_claude_haiku"]:
        add("LIT", f"{c} p95 / median latency at concurrency 16", lat.loc[c, "95%"] / lat.loc[c, "50%"], "a4_latency_distribution_c16.csv")
    for c in ["pc_rtx4060", "mac_m4pro"]:
        add("LIT", f"{c} aggregate tokens/s at concurrency 16 / concurrency 1",
            dec16.loc[c, "agg_out_tok_per_s"] / cond[(cond.condition == c) & (cond.task == "throughput") & (cond.set == "main") & (cond.concurrency == 1)].agg_out_tok_per_s.iloc[0],
            "summary_by_condition.csv")
    add("LIT", "Groq / Mac aggregate tokens/s at concurrency 16", dec16.loc["api_groq", "agg_out_tok_per_s"] / dec16.loc["mac_m4pro", "agg_out_tok_per_s"], "summary_by_condition.csv")
    add("LIT", "budget box break-even vs Groq x 30 (requests per month)", be2_groq_budget * 30, "a4_break_even_two_baselines.csv")
    add("LIT", "PC break-even vs Groq x 30 (requests per month)", be2_groq_pc * 30, "a4_break_even_two_baselines.csv")
    add("LIT", "Tombor threshold per day: 2,400,000 sessions per month / 30", 2_400_000 / 30, "Tombor and Abonyi (2026)")
    # sensitivity of the budget-box and PC break-even against Groq to amortization years and tariff
    sens = []
    for c in ["pc_rtx4060_budget", "pc_rtx4060"]:
        h = PRICES["hardware"][c]; cap = cap_of[c]
        for years in [2, 3, 5]:
            for tariff_x in [1.0, 2.0]:
                be = None
                for V in grid:
                    if V > cap:
                        break
                    busy = V / (cap / 24)
                    kwh = (busy * h["load_watts_measured"] + (24 - busy) * h["idle_watts_assumed"]) / 1000
                    elec = kwh * PRICES["electricity_kzt_per_kwh"] * tariff_x * PRICES["usd_per_kzt"]
                    daily = h["price_usd"] / (365 * years) + elec
                    if daily / V * 1000 < api["api_groq"]:
                        be = int(V); break
                V = 100000
                busy = V / (cap / 24)
                kwh = (busy * h["load_watts_measured"] + (24 - busy) * h["idle_watts_assumed"]) / 1000
                elec = kwh * PRICES["electricity_kzt_per_kwh"] * tariff_x * PRICES["usd_per_kzt"]
                share = elec / (h["price_usd"] / (365 * years) + elec) * 100
                sens.append({"condition": c, "amortization_years": years, "tariff_multiplier": tariff_x,
                             "break_even_vs_groq_req_per_day": be, "electricity_share_of_daily_cost_at_100k_pct": share})
    pd.DataFrame(sens).round(2).to_csv(RES / "a4_sensitivity_break_even.csv", index=False)
    pd.DataFrame(erc).round(3).to_csv(RES / "a4_er_checks.csv", index=False)

    # ---------------- figures ----------------
    plt.rcParams.update({"font.size": 9})
    # A: repeats at c=16
    fig, ax = plt.subplots(figsize=(7.5, 3.8))
    order = [c for c in MAIN if c in set(th.condition)]
    for i, c in enumerate(order):
        g = th[(th.condition == c) & (th.concurrency == 16)]
        ax.scatter([i] * len(g), g.agg_out_tok_per_s, color="black", s=18)
        ax.plot([i - .25, i + .25], [g.agg_out_tok_per_s.median()] * 2, color="grey")
    ax.set_xticks(range(len(order))); ax.set_xticklabels([LAB[c] for c in order], rotation=35, ha="right")
    ax.set_yscale("log"); ax.set_ylabel("Aggregate output tokens/s (log)")
    ax.set_title("Each repeat at concurrency 16 (dots) and their median (line)")
    ax.grid(alpha=.3, axis="y"); fig.tight_layout(); fig.savefig(FIG / "a4_repeats_c16.png", dpi=170); plt.close(fig)
    # B: latency distribution boxplot c=16
    fig, ax = plt.subplots(figsize=(7.5, 3.8))
    data = [l16[l16.condition == c].latency_s.values for c in order]
    ax.boxplot(data, whis=(5, 95), showfliers=False, medianprops={"color": "black"})
    ax.set_xticks(range(1, len(order) + 1)); ax.set_xticklabels([LAB[c] for c in order], rotation=35, ha="right")
    ax.set_yscale("log"); ax.set_ylabel("End-to-end latency, s (log)")
    ax.set_title("Latency of every successful request at concurrency 16 (box 25-75%, whiskers 5-95%)")
    ax.grid(alpha=.3, axis="y"); fig.tight_layout(); fig.savefig(FIG / "a4_latency_box_c16.png", dpi=170); plt.close(fig)
    # C: accuracy with Wilson interval (repeat 1) and repeat 2 marker
    fig, ax = plt.subplots(figsize=(7.5, 3.8))
    for i, c in enumerate(order):
        a1 = acc[(acc.condition == c) & (acc.repeat == 1)].iloc[0]
        a2 = acc[(acc.condition == c) & (acc.repeat == 2)].iloc[0]
        ax.errorbar(i, a1.accuracy * 100, yerr=[[(a1.accuracy - a1.wilson_low) * 100], [(a1.wilson_high - a1.accuracy) * 100]],
                    fmt="o", color="black", capsize=3)
        ax.scatter(i + .15, a2.accuracy * 100, marker="x", color="grey")
    ax.axhline(bf16 * 100 - 5, ls=":", color="grey")
    ax.text(len(order) - .5, bf16 * 100 - 4.6, "bf16 minus 5 points", ha="right", fontsize=7, color="grey")
    ax.set_xticks(range(len(order))); ax.set_xticklabels([LAB[c] for c in order], rotation=35, ha="right")
    ax.set_ylabel("GSM8K accuracy, % of 100 items"); ax.set_ylim(55, 100)
    ax.set_title("Repeat 1 with 95% Wilson interval (dot), repeat 2 (cross)")
    ax.grid(alpha=.3, axis="y"); fig.tight_layout(); fig.savefig(FIG / "a4_accuracy_ci.png", dpi=170); plt.close(fig)
    # D: wrong answer classes stacked
    fig, ax = plt.subplots(figsize=(7.5, 3.6))
    w = wcls.drop(columns="total_wrong_answers").reindex(order).fillna(0)
    bottom = np.zeros(len(w))
    for col, hatch in zip(w.columns, ["", "//", "..", "xx"]):
        ax.bar(range(len(w)), w[col].values, bottom=bottom, label=col, color="white", edgecolor="black", hatch=hatch)
        bottom += w[col].values
    ax.set_xticks(range(len(w))); ax.set_xticklabels([LAB[c] for c in w.index], rotation=35, ha="right")
    ax.set_ylabel("Wrong answers in 200 (2 repeats)"); ax.legend(fontsize=7)
    ax.set_title("Why GSM8K answers were wrong"); fig.tight_layout(); fig.savefig(FIG / "a4_wrong_classes.png", dpi=170); plt.close(fig)
    # E: DeepInfra timeline
    fig, ax = plt.subplots(figsize=(7.5, 3.2))
    x = range(len(dim))
    ax.bar(x, dim.sent - dim.failed, color="lightgrey", edgecolor="black", label="answered")
    ax.bar(x, dim.failed, bottom=dim.sent - dim.failed, color="black", label="HTTP 429")
    step = max(1, len(dim) // 12)
    ax.set_xticks(list(x)[::step]); ax.set_xticklabels(dim.minute[::step], rotation=0, fontsize=7)
    ax.set_xlabel("Minute, Astana time, 23.10.2026"); ax.set_ylabel("Requests sent")
    ax.set_title("DeepInfra pilot and main rerun, requests per minute: answered and rejected"); ax.legend(fontsize=7)
    fig.tight_layout(); fig.savefig(FIG / "a4_deepinfra_timeline.png", dpi=170); plt.close(fig)
    # F: cost curves
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    styles = {"dedicated": "-", "shared_dev_machine": "--", "rented 24 h": "-.", "hosted": ":"}
    for (c, s), g in cu.groupby(["condition", "scenario"]):
        if c in ("api_cloudflare", "api_coreweave"):
            continue
        lab = LAB[c] + {"dedicated": ", full price", "shared_dev_machine": ", 25% of price", "rented 24 h": ", rented 24 h", "hosted": ""}[s]
        ax.plot(g.volume_per_day, g.cost_per_1000_usd, ls=styles[s], label=lab, lw=1.3)
    ax.set_xscale("log"); ax.set_yscale("log"); ax.set_xlabel("Requests per day (log)"); ax.set_ylabel("USD per 1,000 requests (log)")
    ax.set_title("Cost per 1,000 requests; local lines stop at measured capacity"); ax.grid(alpha=.3, which="both"); ax.legend(fontsize=6.5, ncol=2)
    fig.tight_layout(); fig.savefig(FIG / "a4_cost_curves.png", dpi=170); plt.close(fig)
    # G: cost vs accuracy at 100k
    cqd = pd.DataFrame(cq)
    fig, ax = plt.subplots(figsize=(7.0, 4.0))
    offs = {("pc_rtx4060_budget", "shared_dev_machine"): (-22, -14), ("pc_rtx4060", "shared_dev_machine"): (-4, -25),
            ("mac_m4pro", "shared_dev_machine"): (4, 5), ("pc_rtx4060_budget", "dedicated"): (-22, 7),
            ("pc_rtx4060", "dedicated"): (4, -13), ("mac_m4pro", "dedicated"): (4, 5), ("api_groq", "n/a"): (5, -4)}
    cqd = cqd[~cqd.condition.isin(["mac_m4pro_q8", "rented_colab_t4_run2"])]
    for _, r in cqd.iterrows():
        mk = "o" if r.scenario in ("n/a",) else ("s" if r.scenario == "dedicated" else "^")
        ax.scatter(r.cost_per_1000_usd_at_100k, r.gsm8k_accuracy_mean_of_repeats * 100, marker=mk, color="black")
        tag = LAB[r.condition] + ("" if r.scenario in ("n/a", "dedicated") else ", 25%")
        ax.annotate(tag, (r.cost_per_1000_usd_at_100k, r.gsm8k_accuracy_mean_of_repeats * 100), fontsize=6.5,
                    xytext=offs.get((r.condition, r.scenario), (3, 3)), textcoords="offset points")
    ax.set_xscale("log"); ax.set_xlabel("USD per 1,000 requests at 100,000 requests/day (log)")
    ax.set_ylabel("GSM8K accuracy, %"); ax.set_title("Cost and answer quality at 100,000 requests per day")
    ax.grid(alpha=.3, which="both"); fig.tight_layout(); fig.savefig(FIG / "a4_cost_vs_quality.png", dpi=170); plt.close(fig)
    # H: answer length histogram (main throughput, local Q4 conditions pooled vs hosted)
    fig, ax = plt.subplots(figsize=(7.0, 3.4))
    loc = tm[tm.condition.isin(["mac_m4pro", "pc_rtx4060", "rented_colab_gpu"])].completion_tokens
    ax.hist(loc, bins=range(0, 270, 8), color="lightgrey", edgecolor="black")
    ax.axvline(loc.mean(), color="black", ls="--"); ax.text(loc.mean() + 3, ax.get_ylim()[1] * .9, f"mean {loc.mean():.0f}", fontsize=8)
    ax.set_xlabel("Output tokens per answer (limit 256)"); ax.set_ylabel("Requests")
    ax.set_title("Answer length on the local Q4 machines, main throughput set")
    fig.tight_layout(); fig.savefig(FIG / "a4_answer_length.png", dpi=170); plt.close(fig)
    pd.DataFrame({"pooled_conditions": ["mac_m4pro+pc_rtx4060+rented_colab_gpu"], "requests": [len(loc)],
                  "mean_tokens": [round(loc.mean(), 1)], "median_tokens": [loc.median()],
                  "share_at_256_pct": [round((loc >= 256).mean() * 100, 1)]}).to_csv(RES / "a4_answer_length_local_pooled.csv", index=False)
    print("written results/a4_*.csv and figures/a4_*.png")


if __name__ == "__main__":
    main()
