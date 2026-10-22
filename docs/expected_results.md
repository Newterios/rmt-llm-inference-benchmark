# Expected Results (pre-registered)

Fixed on: 23.10.2026, before any benchmark run was executed. This file is committed to git on
that date and is not edited afterwards. Segment 4 of the report compares these expectations with
what the pilot runs show.

Research question: At what daily request volume does running an 8B open-weight LLM on a team's
own hardware become cheaper than a hosted API at equal answer quality?

Hypothesis (carried from Assignment 1, narrowed): a break-even volume exists between 1,000 and
100,000 requests per day; below it the hosted API is cheaper, above it the team's own hardware is
cheaper, and answer quality of the 4-bit local model stays within 5 percentage points of the
hosted bf16 version of the same model.

Cost assumptions used for the expectations (to be replaced by sourced prices in the report):
MacBook Pro M4 Pro 24 GB about 1,100,000 KZT, desktop with RTX 4060 about 700,000 KZT,
straight-line amortization over 3 years, electricity 25 KZT per kWh, 1 USD = 500 KZT.
A "request" is one Alpaca prompt (about 150 prompt tokens) with up to 256 output tokens.

| No. | Expected result (one sentence) | Connected objective (A1 Obj.) | What would falsify it | Confidence and why |
|---|---|---|---|---|
| ER1 | At 1,000 requests/day the amortized cost per 1,000 requests on both local machines is at least 10 times higher than the cheapest hosted Llama 3.1 8B provider (expected: about 1,800 USD-cents vs about 1 to 8 USD-cents). | Obj. 2 (cost per 1,000 requests) | Any local machine whose cost per 1,000 requests at 1,000/day is below or within 10x of the cheapest API price. | High. Hardware amortization alone is about 1.1 to 1.8 USD/day, while 1,000 API requests of this size cost a few cents (OpenRouter price list, 23.10.2026). |
| ER2 | The break-even daily volume, where the RTX 4060 PC becomes cheaper per 1,000 requests than the DeepInfra endpoint, lies between 10,000 and 100,000 requests/day. | Obj. 2, Obj. 5 (decision table) | Break-even below 10,000/day, above 100,000/day, or no break-even because the PC cannot reach the required throughput. | Medium. Pan et al. (2025) report break-even within months for small models, but Tombor and Abonyi (2026) place it at millions of sessions per month; the cheap fp8 price (0.02/0.04 USD per 1M tokens) pushes it upward. |
| ER3 | Neither local machine can sustain 100,000 requests/day (1.16 requests/s averaged over 24 h) with 256-token answers; expected sustainable maximum is 30,000 to 70,000 requests/day for the PC and 20,000 to 50,000 for the Mac. | Obj. 2 (throughput) | Measured aggregate throughput at concurrency 16 that corresponds to 100,000 or more requests/day on either machine. | Medium. Both GPUs have about 270 GB/s memory bandwidth, which limits aggregate decoding to roughly 150 to 300 tokens/s for a 4-bit 8B model (Kwon et al., 2023 show batching gains need many parallel requests). |
| ER4 | GSM8K exact-match accuracy of the local Q4_K_M model is within 5 percentage points of the bf16 hosted version of the same model (CoreWeave), and the fp8 providers are within 3 points of bf16. | Obj. 2 (quality at equal task) | Local Q4_K_M accuracy more than 5 points below bf16, or an fp8 provider more than 3 points away from bf16. | Medium. Huang et al. (2024) report about 2 percent loss at 4 bits; Kurtic et al. (2025) find FP8 practically lossless, but both used larger evaluation sets than our 100 items. |
| ER5 | Time to first token for a single request is below 0.5 s on both local machines and between 0.3 s and 1.5 s for the hosted providers; at concurrency 16 the Mac's p95 end-to-end latency exceeds 20 s. | Obj. 2 (response time) | Local single-request TTFT above 0.5 s, any provider's median TTFT outside 0.3 to 1.5 s, or Mac p95 latency at concurrency 16 below 20 s. | Medium. Prompt processing of about 150 tokens is fast on both GPUs; network round-trips from Kazakhstan to US/EU data centres add 0.2 to 0.4 s. |
| ER6 | The same open-weight model served by three providers differs by a factor of 3 or more in decode speed (Groq fastest) while accuracy differs by at most 2 percentage points. | Obj. 1 (factor list: provider variability) | Fastest-to-slowest provider decode speed ratio below 1.5, or accuracy spread above 2 points. | High for speed (Groq hardware is known to be fast; Li et al., 2026 report large provider spread), medium for accuracy. |
| ER7 | Claude Haiku 5.5 reaches at least 90 percent on the 100 GSM8K items while Llama 3.1 8B (any serving condition) reaches 70 to 88 percent, so the closed model is more accurate but at 1.5 to 10 times the token price of the open-weight providers. | Obj. 5 (decision table) | Llama 3.1 8B matching or exceeding Haiku 5.5, or Haiku 5.5 below 90 percent. | Medium-high. Published GSM8K scores for Llama 3.1 8B Instruct are about 84 percent; a smaller sample and a strict answer format can lower it. |
| ER8 | Local runs have a 0 percent error rate, hosted runs below 2 percent at concurrency 16, except Groq, where rate limiting (HTTP 429) is expected to fail 5 percent or more of requests at concurrency 16 on a pay-as-you-go key. | Obj. 1 (operational factors) | Any local error, a non-Groq provider above 2 percent failures, or Groq below 5 percent failures at concurrency 16. | Low-medium. Rate limits of OpenRouter routes are not published per concurrency. |

Signals that would indicate a broken process rather than a finding (declared now):
- Local TTFT below 0.05 s at concurrency 16 or identical latencies across repeats: prompt cache or slot reuse is on; the run is discarded and repeated with caching off.
- A provider returning the model under a different name in the response, or `provider` field not matching the pinned provider: the run is discarded.
- Quality accuracy of 0 or 100 percent on any condition: the answer-extraction rule failed; fix the parser, do not touch the run data.
- Aggregate throughput higher than single-request throughput multiplied by concurrency: a timing bug.

Six scenarios (T9):
- Bad 1: the local machines cannot finish the concurrency-16 runs without timeouts, so the capacity numbers cannot be measured.
- Bad 2: provider pinning fails (OpenRouter silently falls back), so provider comparison is not interpretable.
- Medium 1: the API is cheaper at every volume we can measure and no break-even exists in range; the answer to the RQ becomes "none below 100,000/day".
- Medium 2: break-even exists for the PC but not for the Mac, so the answer depends on hardware class.
- Good 1: a break-even between 10,000 and 100,000/day is found for both machines and quality loss is under 5 points.
- Good 2: break-even is found and quality of fp8 and Q4 differs measurably, giving a quality-cost trade-off table.
