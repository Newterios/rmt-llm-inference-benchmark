"""Build fixed prompt sets from the raw datasets with a stated seed.

Throughput prompts come from Stanford Alpaca (Taori et al., 2023).
Quality prompts come from the GSM8K test split (Cobbe et al., 2021).
Pilot and main subsets are disjoint, so pilot data never enters the main runs.
"""
import hashlib
import json
import random
from pathlib import Path

SEED = 42
ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "prompts"
OUT.mkdir(parents=True, exist_ok=True)

N_THROUGHPUT_PILOT, N_THROUGHPUT_MAIN = 50, 200
N_QUALITY_PILOT, N_QUALITY_MAIN = 30, 100


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_jsonl(path: Path, rows):
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def build_alpaca():
    data = json.load(open(RAW / "alpaca_data.json", encoding="utf-8"))
    candidates = []
    for i, item in enumerate(data):
        text = item["instruction"].strip()
        if item.get("input", "").strip():
            text += "\n\n" + item["input"].strip()
        # keep moderate prompts: long enough to be a real task, short enough for a 1024-token slot
        if 40 <= len(text) <= 600:
            candidates.append({"source": "alpaca", "source_index": i, "prompt": text})
    rng = random.Random(SEED)
    rng.shuffle(candidates)
    pick = candidates[: N_THROUGHPUT_PILOT + N_THROUGHPUT_MAIN]
    for k, row in enumerate(pick):
        row["id"] = f"alp-{k:03d}"
    return pick[:N_THROUGHPUT_PILOT], pick[N_THROUGHPUT_PILOT:], len(candidates), len(data)


def build_gsm8k():
    rows = [json.loads(l) for l in open(RAW / "gsm8k_test.jsonl", encoding="utf-8")]
    candidates = []
    for i, item in enumerate(rows):
        gold = item["answer"].split("####")[-1].strip().replace(",", "")
        candidates.append({"source": "gsm8k_test", "source_index": i,
                           "prompt": item["question"].strip(), "gold": gold})
    rng = random.Random(SEED)
    rng.shuffle(candidates)
    pick = candidates[: N_QUALITY_PILOT + N_QUALITY_MAIN]
    for k, row in enumerate(pick):
        row["id"] = f"gsm-{k:03d}"
    return pick[:N_QUALITY_PILOT], pick[N_QUALITY_PILOT:], len(candidates), len(rows)


def main():
    tp, tm, alp_cand, alp_total = build_alpaca()
    qp, qm, gsm_cand, gsm_total = build_gsm8k()
    write_jsonl(OUT / "throughput_pilot.jsonl", tp)
    write_jsonl(OUT / "throughput_main.jsonl", tm)
    write_jsonl(OUT / "quality_pilot.jsonl", qp)
    write_jsonl(OUT / "quality_main.jsonl", qm)
    card = {
        "seed": SEED,
        "alpaca": {"file": "data/raw/alpaca_data.json", "sha256": sha256(RAW / "alpaca_data.json"),
                   "records_total": alp_total, "records_after_length_filter": alp_cand,
                   "length_filter_chars": [40, 600], "pilot": len(tp), "main": len(tm),
                   "source": "https://github.com/tatsu-lab/stanford_alpaca", "license": "CC BY-NC 4.0"},
        "gsm8k": {"file": "data/raw/gsm8k_test.jsonl", "sha256": sha256(RAW / "gsm8k_test.jsonl"),
                  "records_total": gsm_total, "pilot": len(qp), "main": len(qm),
                  "source": "https://github.com/openai/grade-school-math", "license": "MIT"},
        "disjoint_check": {
            "alpaca_overlap": len({r["source_index"] for r in tp} & {r["source_index"] for r in tm}),
            "gsm8k_overlap": len({r["source_index"] for r in qp} & {r["source_index"] for r in qm}),
        },
    }
    json.dump(card, open(OUT / "prompt_sets_card.json", "w"), indent=2)
    print(json.dumps(card, indent=2))


if __name__ == "__main__":
    main()
