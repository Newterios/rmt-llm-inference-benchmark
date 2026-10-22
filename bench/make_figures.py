"""Plots for the report, generated only from results/*.csv (no hand-entered numbers)."""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
FIG = ROOT / "figures"
FIG.mkdir(exist_ok=True)
LABELS = {"mac_m4pro": "Mac M4 Pro (local)", "mac_m4pro_loaded": "Mac M4 Pro while in use (local)", "mac_m4pro_q8": "Mac M4 Pro, Q8_0 (local)", "pc_rtx4060": "PC RTX 4060 (local)", "pc_rtx4060_budget": "Budget box RTX 4060 (cost scenario)", "rented_colab_gpu": "Rented GPU (Colab Pro)",
          "api_deepinfra": "API DeepInfra fp8", "api_novita": "API Novita fp8", "api_groq": "API Groq",
          "api_cloudflare": "API Cloudflare fp8", "api_coreweave": "API CoreWeave bf16", "api_claude_haiku": "API Claude Haiku 5.5"}


def main(set_name):
    df = pd.read_csv(ROOT / "results" / "summary_by_condition.csv")
    th = df[(df.task == "throughput") & (df.set == set_name)]
    q = df[(df.task == "quality") & (df.set == set_name)]
    conds = [c for c in LABELS if c in set(th.condition)]

    # Figure A: aggregate output tokens/s vs concurrency
    fig, ax = plt.subplots(figsize=(7, 4))
    for c in conds:
        g = th[th.condition == c].sort_values("concurrency")
        ax.plot(g.concurrency, g.agg_out_tok_per_s, marker="o", label=LABELS[c])
    ax.set_xscale("log", base=2); ax.set_xticks([1, 4, 16]); ax.set_xticklabels(["1", "4", "16"])
    ax.set_xlabel("Concurrent requests"); ax.set_ylabel("Aggregate output tokens per second")
    ax.set_title(f"Throughput by condition ({set_name} set, median of repeats)")
    ax.grid(alpha=.3); ax.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(FIG / f"fig_throughput_{set_name}.png", dpi=160); plt.close(fig)

    # Figure B: p50 and p95 latency at each concurrency
    fig, axes = plt.subplots(1, 2, figsize=(10, 4), sharey=False)
    for ax, col, title in zip(axes, ["latency_p50_s", "latency_p95_s"], ["Median latency", "p95 latency"]):
        for c in conds:
            g = th[th.condition == c].sort_values("concurrency")
            ax.plot(g.concurrency, g[col], marker="o", label=LABELS[c])
        ax.set_xscale("log", base=2); ax.set_xticks([1, 4, 16]); ax.set_xticklabels(["1", "4", "16"])
        ax.set_xlabel("Concurrent requests"); ax.set_ylabel("seconds"); ax.set_title(title); ax.grid(alpha=.3)
    axes[0].legend(fontsize=7)
    fig.tight_layout(); fig.savefig(FIG / f"fig_latency_{set_name}.png", dpi=160); plt.close(fig)

    # Figure C: GSM8K accuracy per condition
    if not q.empty:
        fig, ax = plt.subplots(figsize=(7, 3.5))
        qq = q.groupby("condition").accuracy.median().reindex([c for c in LABELS if c in set(q.condition)])
        ax.barh([LABELS[c] for c in qq.index], qq.values * 100)
        for i, v in enumerate(qq.values * 100):
            ax.text(v + 0.5, i, f"{v:.0f}%", va="center", fontsize=8)
        ax.set_xlabel("GSM8K exact-match accuracy, %"); ax.set_xlim(0, 105)
        ax.set_title(f"Answer quality ({set_name} set)"); ax.grid(axis="x", alpha=.3)
        fig.tight_layout(); fig.savefig(FIG / f"fig_accuracy_{set_name}.png", dpi=160); plt.close(fig)

    # Figure D: cost per 1,000 requests vs daily volume (if the cost model has run)
    cp = ROOT / "results" / f"cost_per_1000_{set_name}.csv"
    if cp.exists():
        cost = pd.read_csv(cp)
        fig, ax = plt.subplots(figsize=(7, 4))
        for c in [c for c in LABELS if c in set(cost.condition)]:
            g = cost[cost.condition == c].sort_values("volume_per_day")
            ax.plot(g.volume_per_day, g.cost_per_1000_usd, marker="o", label=LABELS[c])
        ax.set_xscale("log"); ax.set_yscale("log")
        ax.set_xlabel("Requests per day"); ax.set_ylabel("USD per 1,000 requests")
        ax.set_title("Cost per 1,000 requests vs daily volume"); ax.grid(alpha=.3, which="both"); ax.legend(fontsize=7)
        fig.tight_layout(); fig.savefig(FIG / f"fig_cost_{set_name}.png", dpi=160); plt.close(fig)
    print("figures written to", FIG)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "pilot")
