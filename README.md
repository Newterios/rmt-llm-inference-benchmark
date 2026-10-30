# Local vs hosted inference of an 8B open-weight LLM: benchmark harness and data

Research Methods and Tools, Astana IT University, group SE-2424, Assignments 3 and 4.
Team: Kaiyrbekuly Aitbek, Turganbek Nurhan.

**Research question.** At what daily request volume does running an 8B open-weight LLM on a
team's own hardware become cheaper than a hosted API at equal answer quality?

This repository holds everything needed to repeat the study: the harness, the fixed prompt
sets, every run log (not only the best ones), the price assumptions and the scripts that turn
raw logs into the tables used in the report.

## What is measured

One model, Llama 3.1 8B Instruct, is served under the following conditions and receives the same
prompts at the same concurrency levels:

| Condition | Where the model runs | Weights |
|---|---|---|
| `mac_m4pro` | MacBook Pro M4 Pro 24 GB, llama.cpp (Metal) | Q4_K_M GGUF |
| `pc_rtx4060` | Desktop, RTX 4060 8 GB, llama.cpp (CUDA) | Q4_K_M GGUF |
| `rented_colab_gpu` | Rented cloud GPU: Google Colab runtime, Tesla T4 (L4 was unavailable), llama.cpp (CUDA) | Q4_K_M GGUF |
| `api_deepinfra` | OpenRouter, provider pinned to DeepInfra | fp8 |
| `api_groq` | OpenRouter, provider pinned to Groq | provider-managed |
| `api_coreweave` | OpenRouter, provider pinned to CoreWeave | bf16 |
| `api_claude_haiku` | Anthropic API, `claude-haiku-5-5` (closed-weight reference) | n/a |
| `mac_m4pro_q8` | Same Mac, Q8_0 file (quantization comparison) | Q8_0 GGUF |
| `mac_m4pro_loaded` | Same Mac, first main run while the machine was in use (observation) | Q4_K_M GGUF |
| `api_cloudflare` | OpenRouter, provider pinned to Cloudflare (added when DeepInfra was rate-limited) | fp8 |

Workload levels 1,000 / 10,000 / 100,000 requests per day are represented by closed-loop
concurrency 1 / 4 / 16. Two tasks: `throughput` (Alpaca prompts, 256 max tokens) and
`quality` (GSM8K test questions, exact-match accuracy, 400 max tokens).

Metrics (defined in the report, Segment 3 D.4): time to first token, end-to-end latency
(p50, p95), decode tokens/s per request, aggregate output tokens/s, requests/s and the
sustainable requests/day derived from it, cost per 1,000 requests, failure rate, GSM8K accuracy.

## Folder structure

```
bench/            harness and helper scripts
  make_prompts.py   builds the fixed prompt sets (seed 42) from data/raw
  run.py            sends one prompt set to one condition, writes runs/<condition>/*.jsonl
  summarize.py      recomputes results/*.csv from every run file
  cost_model.py     cost per 1,000 requests at 1k / 10k / 100k requests per day
  conditions.json   the seven conditions (endpoints, provider pins, hardware description)
  prices.json       every price assumption with its source and access date
  serve_mac.sh      llama-server command used on the Mac
  pilot_mac.sh      the pilot protocol
  windows/          the same for the Windows PC (serve_pc.ps1, power_pc.ps1, run_pc.ps1)
  cloud/            Colab notebook for the rented GPU condition and its server-start script
  energy.py         mean power per run level from the powermetrics / nvidia-smi logs
  analyze_a4.py     Assignment 4 analysis: intervals, paired tests, failure classes, cost curves,
                    decision table, sensitivity; reads existing files only, writes results/a4_*.csv
                    and figures/a4_*.png
data/
  raw/              Alpaca (alpaca_data.json) and GSM8K test (gsm8k_test.jsonl) as downloaded
  prompts/          the fixed subsets: throughput_{pilot,main}.jsonl, quality_{pilot,main}.jsonl
                    and prompt_sets_card.json (checksums, counts, disjointness check)
runs/               RAW DATA. One JSONL per run: a meta line, one line per request
                    (timing, tokens, cost, status, full model output), one summary line per level.
                    runs/_smoke/ holds the 3-prompt smoke tests, excluded from analysis.
results/            PROCESSED DATA, produced only by bench/summarize.py, bench/energy.py and bench/cost_model.py
                    (summary_by_level.csv, summary_by_condition.csv, requests_all.csv, power_by_level.csv,
                    cost_per_1000_main.csv, break_even_main.csv, api_pricing_scenarios_main.csv)
                    and by bench/analyze_a4.py (every file named a4_*.csv)
figures/            screenshots and plots used in the report
docs/
  expected_results.md   pre-registered expectations (committed 23.10.2026, before any run)
  research_log.md       dated log of every session
models/             the GGUF file (not committed, 4.92 GB; sha256 in docs/research_log.md)
```

## How to repeat

```bash
python3 -m venv .venv && .venv/bin/pip install httpx pandas numpy tqdm psutil python-dotenv matplotlib anthropic
.venv/bin/python bench/make_prompts.py            # rebuilds the same prompt sets (seed 42)
cp .env.example .env                               # add OPENROUTER_API_KEY / ANTHROPIC_API_KEY
./bench/serve_mac.sh                               # terminal 1 (needs llama.cpp installed)
./bench/pilot_mac.sh                               # terminal 2
.venv/bin/python bench/run.py --condition api_deepinfra --task throughput --set main --concurrency 1 4 16 --repeats 3
.venv/bin/python bench/summarize.py && .venv/bin/python bench/cost_model.py main
.venv/bin/python bench/analyze_a4.py                # Assignment 4 tables and figures, no new requests
```

Model file: `bartowski/Meta-Llama-3.1-8B-Instruct-GGUF`, file `Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf`,
4,920,739,232 bytes, sha256 `7b064f5842bf9532c91456deda288a1b672397a54fa729aa665952863033557c`.

## Data sources and licenses

- Alpaca: Taori et al. (2023), https://github.com/tatsu-lab/stanford_alpaca, CC BY-NC 4.0.
- GSM8K: Cobbe et al. (2021), https://github.com/openai/grade-school-math, MIT.
- Model: Meta Llama 3.1 8B Instruct under the Llama 3.1 Community License; GGUF conversion by bartowski.

No personal data is collected or processed. API keys live only in `.env` (git-ignored).
