# Research log

One row per working session, trial batch or model run. Times are Astana time (UTC+5).

| Date | Who | What was done | What went wrong | What was changed |
|---|---|---|---|---|
| 23.10.2026 | Aitbek | Received A1/A2 feedback (18/20 each, RQ too long). Teacher told us to drop the human part. Re-designed study as a technical benchmark (Block D); new RQ fixed. | A1 plan with interviews is no longer valid. | RQ rewritten to one question; interview objective removed. |
| 23.10.2026 | Aitbek | Set up repo, Python venv, downloaded Alpaca (52,002 rows) and GSM8K test (1,319 rows), built fixed prompt sets with seed 42 (pilot 50/30, main 200/100, disjoint). | None. | - |
| 23.10.2026 | Aitbek | Wrote harness bench/run.py (streaming, TTFT, usage, cost, error capture) and conditions.json for 7 conditions. | Anthropic model needs the official SDK; added an anthropic backend with thinking disabled. | - |
| 23.10.2026 | Aitbek | Expected Results ER1 to ER8 and six scenarios written and committed BEFORE any run (docs/expected_results.md). | - | - |
| 23.10.2026 01:25 to 01:36 | Aitbek | Mac pilot: throughput pilot (50 prompts) at concurrency 1, 4, 16, two repeats each; quality pilot (30 GSM8K) at concurrency 4. 330 requests, 0 errors. Smoke tests (3 prompts) moved to runs/_smoke. | Concurrency-16 repeats differ a lot (wall 74 s vs 45 s; p95 latency 48 s vs 23 s). Cause not known yet; main run uses 3 repeats to see if it persists. | Nothing changed in the protocol. |
| 23.10.2026 01:34 | Aitbek | Smoke tests of hosted conditions (2 prompts each). Groq, CoreWeave, Claude Haiku 5.5 OK. Groq at concurrency 16: 16/16 OK, no rate limiting. | DeepInfra and Novita (the two cheapest fp8 endpoints) answered HTTP 429 "temporarily rate-limited upstream, shared pool" for every request at 01:34 to 01:36 Astana time (US evening peak). | Added Cloudflare (fp8, 0.152/0.287 USD per 1M) as a fallback fp8 provider; DeepInfra will be retried at a different time of day and the attempt logged either way. |
| 23.10.2026 01:37 | Aitbek | Launched pilot protocol for api_groq, api_coreweave, api_cloudflare, api_claude_haiku in parallel (same prompt sets and levels as the Mac). | - | - |
