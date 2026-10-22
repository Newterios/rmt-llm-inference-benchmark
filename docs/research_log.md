# Research log

One row per working session, trial batch or model run. Times are Astana time (UTC+5).

| Date | Who | What was done | What went wrong | What was changed |
|---|---|---|---|---|
| 23.10.2026 | Aitbek | Received A1/A2 feedback (18/20 each, RQ too long). Teacher told us to drop the human part. Re-designed study as a technical benchmark (Block D); new RQ fixed. | A1 plan with interviews is no longer valid. | RQ rewritten to one question; interview objective removed. |
| 23.10.2026 | Aitbek | Set up repo, Python venv, downloaded Alpaca (52,002 rows) and GSM8K test (1,319 rows), built fixed prompt sets with seed 42 (pilot 50/30, main 200/100, disjoint). | None. | - |
| 23.10.2026 | Aitbek | Wrote harness bench/run.py (streaming, TTFT, usage, cost, error capture) and conditions.json for 7 conditions. | Anthropic model needs the official SDK; added an anthropic backend with thinking disabled. | - |
| 23.10.2026 | Aitbek | Expected Results ER1 to ER8 and six scenarios written and committed BEFORE any run (docs/expected_results.md). | - | - |
