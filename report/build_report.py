"""Builds the Assignment 3 report (.docx) from the repository data.

All numbers in tables come from results/*.csv, bench/prices.json, data/prompts/prompt_sets_card.json
and docs/*.md. Prose is written here. Run: .venv/bin/python report/build_report.py
"""
import json
import re
from datetime import date
from pathlib import Path

import pandas as pd
from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

ROOT = Path(__file__).resolve().parent.parent
RES = ROOT / "results"
FIG = ROOT / "figures"
OUT = ROOT.parent / "RMT_A3_Team_KaiyrbekulyAitbek_TurganbekNurhan.docx"

LINKS = json.load(open(ROOT / "report" / "links.json"))
PRICES = json.load(open(ROOT / "bench" / "prices.json"))
CARD = json.load(open(ROOT / "data" / "prompts" / "prompt_sets_card.json"))
S4 = json.load(open(ROOT / "report" / "segment4.json"))
COND = json.load(open(ROOT / "bench" / "conditions.json"))

LABEL = {"mac_m4pro": "L-Mac: MacBook Pro M4 Pro 24 GB, llama.cpp, Q4_K_M",
         "mac_m4pro_loaded": "L-MacL: the same Mac measured while the machine was in use (loaded developer machine)",
         "mac_m4pro_q8": "L-Mac8: the same Mac with the Q8_0 file (quantization comparison)",
         "pc_rtx4060": "L-PC: desktop RTX 4060 8 GB, llama.cpp, Q4_K_M",
         "pc_rtx4060_budget": "L-PCb: minimal RTX 4060 box, cost scenario derived from L-PC",
         "rented_colab_gpu": "R-GPU: rented Google Colab Pro GPU, llama.cpp, Q4_K_M",
         "api_deepinfra": "API-DI: OpenRouter, DeepInfra, fp8",
         "api_novita": "API-NV: OpenRouter, Novita, fp8",
         "api_cloudflare": "API-CF: OpenRouter, Cloudflare, fp8",
         "api_groq": "API-GQ: OpenRouter, Groq",
         "api_coreweave": "API-CW: OpenRouter, CoreWeave, bf16",
         "api_claude_haiku": "API-HK: Anthropic, Claude Haiku 5.5 (closed-weight reference)"}
SHORT = {k: v.split(":")[0] for k, v in LABEL.items()}

# ---------------------------------------------------------------- document helpers
doc = Document()
st = doc.styles["Normal"]
st.font.name = "Calibri"
st.font.size = Pt(11)
st.element.rPr.rFonts.set(qn("w:eastAsia"), "Calibri")
for s in doc.sections:
    s.left_margin = s.right_margin = Cm(2.0)
    s.top_margin = s.bottom_margin = Cm(2.0)

PROSE_WORDS = 0
FIG_N = 0
TAB_N = 0


def p(text, bold=False, italic=False, size=None, align=None, count=True, space_after=6):
    global PROSE_WORDS
    para = doc.add_paragraph()
    run = para.add_run(text)
    run.bold, run.italic = bold, italic
    if size:
        run.font.size = Pt(size)
    if align == "center":
        para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    para.paragraph_format.space_after = Pt(space_after)
    if count:
        PROSE_WORDS += len(text.split())
    return para


def h(text, level=1):
    hd = doc.add_heading(text, level=level)
    for r in hd.runs:
        r.font.color.rgb = RGBColor(0, 0, 0)
        r.font.name = "Calibri"
    return hd


def bullet(text):
    global PROSE_WORDS
    para = doc.add_paragraph(text, style="List Bullet")
    para.paragraph_format.space_after = Pt(2)
    PROSE_WORDS += len(text.split())
    return para


def shade(cell, hex_fill="D9E2F3"):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear"); shd.set(qn("w:color"), "auto"); shd.set(qn("w:fill"), hex_fill)
    tcPr.append(shd)


def table(rows, header=True, widths=None, font=9, caption=None):
    """rows: list of lists of str. First row is the header when header=True."""
    global TAB_N
    if caption:
        TAB_N += 1
        p(f"Table {TAB_N}. {caption}", bold=True, size=10, count=False, space_after=2)
    t = doc.add_table(rows=len(rows), cols=len(rows[0]))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, row in enumerate(rows):
        for j, val in enumerate(row):
            cell = t.cell(i, j)
            cell.text = ""
            para = cell.paragraphs[0]
            run = para.add_run("" if val is None else str(val))
            run.font.size = Pt(font)
            if header and i == 0:
                run.bold = True
                shade(cell)
            para.paragraph_format.space_after = Pt(0)
    if widths:
        for j, w in enumerate(widths):
            for i in range(len(rows)):
                t.cell(i, j).width = Cm(w)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)
    return t


def fig(path, caption, width_cm=15.5):
    global FIG_N
    FIG_N += 1
    path = Path(path)
    if not path.exists():
        p(f"[missing figure {path.name}]", italic=True, count=False)
    else:
        doc.add_picture(str(path), width=Cm(width_cm))
        doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
    cap = p(f"Figure {FIG_N}. {caption}", italic=True, size=9, align="center", count=False)
    return FIG_N


def fmt(x, nd=2):
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return "n/a"
    return f"{x:,.{nd}f}" if isinstance(x, float) else str(x)


# ---------------------------------------------------------------- data
def load_results():
    lvl = pd.read_csv(RES / "summary_by_level.csv") if (RES / "summary_by_level.csv").exists() else pd.DataFrame()
    cond = pd.read_csv(RES / "summary_by_condition.csv") if (RES / "summary_by_condition.csv").exists() else pd.DataFrame()
    cost = pd.read_csv(RES / "cost_per_1000_main.csv") if (RES / "cost_per_1000_main.csv").exists() else pd.DataFrame()
    return lvl, cond, cost


LVL, CND, COST = load_results()
PRESENT = [c for c in LABEL if not LVL.empty and c in set(LVL.condition)]


def er_rows():
    rows = []
    for line in open(ROOT / "docs" / "expected_results.md", encoding="utf-8"):
        if line.startswith("| ER"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            rows.append(cells)
    return rows


def log_rows():
    rows = []
    for line in open(ROOT / "docs" / "research_log.md", encoding="utf-8"):
        if line.startswith("| ") and not line.startswith("| Date") and not line.startswith("|---"):
            rows.append([c.strip() for c in line.strip().strip("|").split("|")])
    return rows

# ================================================================ TITLE
p("Group SE-2424 | Assignment 3 | Kaiyrbekuly Aitbek, Turganbek Nurhan", bold=True, count=False)
p("Writing a Methodology", bold=True, size=16, align="center", count=False)
p("Topic: Local or Cloud? Cost, Capacity and Quality of an 8B Open-Weight LLM on Own Hardware versus Hosted APIs",
  italic=True, align="center", count=False)
RQ = ("At what daily request volume does running an 8B open-weight LLM on a team's own hardware "
      "become cheaper than a hosted API at equal answer quality?")

# ================================================================ SEGMENT 1
h("Segment 1. Methodology", 1)
h("T1. Basic information", 2)
table([
    ["Item", "Entry"],
    ["Group", "SE-2424"],
    ["Team", "KaiyrbekulyAitbek_TurganbekNurhan"],
    ["Research Question", RQ],
    ["Strength of the RQ", "It asks for one number (a daily volume) that our own measurements and public price lists "
     "can produce, and it has a built-in failure mode: if no such volume exists below the capacity of the hardware, "
     "the answer is 'none', which is still an answer."],
    ["Weakness of the RQ", "'Equal answer quality' is checked on one task family (GSM8K word problems), and the volume "
     "depends on prices that change monthly, so the number has a date on it. The RQ was rewritten after Assignment 2 "
     "on the teacher's advice: the interview part was removed and the four-factor list was dropped."],
    ["Project cloud repository", f"Code, prompts and all run logs: {LINKS['github']}\nRaw data, figures and the research "
     f"log (Google Drive): {LINKS['drive']}"],
    ["Folder structure", "bench/ (harness and scripts), data/raw (datasets as downloaded), data/prompts (fixed subsets), "
     "runs/<condition>/*.jsonl (raw data, one line per request), results/*.csv (processed data), figures/, docs/ "
     "(expected_results.md, research_log.md). The Drive folder mirrors runs/, results/, figures/ and docs/."],
], widths=[4, 13])

h("T2. Approach Card", 2)
table([
    ["Element", "Our choice", "Why"],
    ["Research approach", "Quantitative", "Every variable is measured in seconds, tokens, requests and dollars; nothing is interpreted from opinions."],
    ["Design", "Controlled benchmark experiment with repeated measures: one model, one prompt set, several serving conditions, three concurrency levels, 2 to 3 repeats per cell.",
     "The RQ compares conditions; a benchmark is the only way to get the same workload on every condition."],
    ["Data", "Primary, generated by our own harness; secondary only for prices (vendor price lists) and prompts (public datasets).", "No published study measured our hardware or our prices."],
    ["Analysis", "Descriptive statistics per cell (median, p95), a cost model that converts measured throughput and prices into USD per 1,000 requests, and a break-even search over daily volume.", "The RQ asks for a volume, so the analysis ends with a volume."],
    ["Mixed design?", "No. One method (benchmark) with two tasks (throughput prompts, quality prompts).", "The human part of the earlier plan was removed after Assignment 2."],
], widths=[3.2, 7.8, 6])
p("Strength of the approach for our RQ: every input is fixed and public, so the study can be rerun by anyone with "
  "the repository, a GPU and about 3 USD of API credit, and a disagreement about the result can be settled by "
  "rerunning rather than arguing. Weakness: the hosted conditions depend on provider load at the minute we ran "
  "them, and the two local machines are what the team owns, not a sample of what Kazakhstan startups own, so "
  "the volume we find is a point estimate for this hardware and this week's prices rather than a general law.")

h("T3. Concept table", 2)
table([
    ["Concept (from RQ)", "Dimension", "Indicator", "Unit"],
    ["Cost of inference", "Hardware cost", "Purchase price spread over 3 years of use", "USD per day"],
    ["", "Energy cost", "Power draw under load times busy hours times tariff", "USD per day"],
    ["", "API cost", "Provider-reported cost of each request (OpenRouter usage.cost) or list price times tokens", "USD per request"],
    ["", "Combined", "Daily cost divided by daily volume", "USD per 1,000 requests"],
    ["Daily request volume", "Load level", "Requests per day that a condition must serve; represented in the benchmark by closed-loop concurrency 1, 4 and 16", "requests/day; concurrent requests"],
    ["", "Capacity", "Measured requests per second at concurrency 16 times 86,400", "requests/day"],
    ["Team's own hardware vs hosted API", "Serving condition", "Where the weights run: our Mac, our PC, a rented GPU, or one of five hosted endpoints", "categorical, 9 levels"],
    ["Answer quality", "Correctness", "Final number equals the GSM8K reference answer (exact match after removing commas)", "percent of 100 items"],
    ["Technical performance (needed to compute capacity)", "Latency", "Time to first token; end-to-end time per request (p50, p95)", "seconds"],
    ["", "Throughput", "Output tokens per second per request and aggregated over all concurrent requests", "tokens/s"],
    ["", "Reliability", "Requests that failed, timed out or returned nothing", "percent of requests"],
], widths=[3.6, 2.8, 7.4, 3.2])

h("T4. What exactly was observed", 2)
table([
    ["Observed", "Instrument that records it", "How it is recorded", "Unit", "Where and when"],
    ["Time to first token", "bench/run.py, perf_counter around the HTTP stream", "First content chunk of the stream minus request start", "s", "Every request, all conditions, 23 to 26 October 2026"],
    ["End-to-end latency", "bench/run.py", "Stream end minus request start", "s", "same"],
    ["Prompt and output tokens", "Server-reported usage field (llama-server, OpenRouter, Anthropic SDK)", "Taken from the final stream chunk; if absent, streamed chunks are counted and the row is flagged tokens_estimated", "tokens", "same"],
    ["Cost of a request", "OpenRouter usage.cost; Anthropic list price times tokens; cost model for local runs", "Stored per request (cost_usd)", "USD", "same"],
    ["Request outcome", "bench/run.py", "status ok / error / timeout / empty / refusal with HTTP code and error text", "category", "same"],
    ["Model answer", "bench/run.py", "Full text stored in the raw JSONL; quality runs also store pred, gold, correct", "text, boolean", "same"],
    ["Server configuration", "llama-server /props endpoint", "model_path, total_slots, build_info written to the meta line of every local run file", "text", "Start of every local run"],
    ["GPU power and utilisation", "nvidia-smi -l 1 (PC, rented GPU); powermetrics (Mac)", "One CSV row per second during the run", "W, percent, MB", "Main runs"],
], widths=[2.8, 4, 5.2, 1.5, 3.5])

h("T5. Research strategy", 2)
p("Strategy: experiment, in the form of a controlled benchmark. The serving condition is the manipulated "
  "variable, the workload (prompts, decoding settings, concurrency) is held constant, and cost, capacity and "
  "quality are the measured outcomes. Consequence for the design: because the local machines cannot hold the "
  "16-bit weights of an 8B model in 8 GB of GPU memory, the local conditions use a 4-bit quantized file while "
  "the hosted providers serve fp8 or bf16 weights. We cannot equalise this, so quantization becomes a measured "
  "outcome (the GSM8K accuracy gap) instead of a controlled factor, and the comparison is between 'the model a "
  "team can actually run on this hardware' and 'the model a provider serves', which is the comparison a team faces.")

h("T6. Sample, dataset and cases", 2)
al, gs = CARD["alpaca"], CARD["gsm8k"]
table([
    ["Item", "Entry"],
    ["Population, dataset or case set", f"Requests of a general chat assistant, represented by two public datasets: Stanford Alpaca "
     f"({al['records_total']:,} instruction prompts) for throughput and the GSM8K test split ({gs['records_total']:,} "
     "grade-school math problems with a numeric reference answer) for quality. Cases: nine serving conditions (Table 2 in D.3)."],
    ["Achieved size", f"Throughput: {al['pilot']} pilot + {al['main']} main prompts. Quality: {gs['pilot']} pilot + {gs['main']} main items. "
     "Each throughput prompt is sent at 3 concurrency levels with 2 (pilot) or 3 (main) repeats, so one condition produces "
     f"{al['main'] * 9} main throughput requests and {gs['main'] * 2} main quality requests."],
    ["Selection strategy", f"Dataset selection against stated criteria: Alpaca prompts between {al['length_filter_chars'][0]} and "
     f"{al['length_filter_chars'][1]} characters ({al['records_after_length_filter']:,} of {al['records_total']:,} remain), "
     f"then a random draw with seed {CARD['seed']}; the first {al['pilot']} drawn are the pilot set, the next {al['main']} the main set, "
     f"so the sets do not overlap (overlap check in prompt_sets_card.json: {CARD['disjoint_check']['alpaca_overlap']}). "
     f"GSM8K: random draw with the same seed, {gs['pilot']} pilot then {gs['main']} main, overlap {CARD['disjoint_check']['gsm8k_overlap']}."],
    ["Where it came from", f"Alpaca: {al['source']} (license {al['license']}), file sha256 {al['sha256'][:16]}... "
     f"GSM8K: {gs['source']} (license {gs['license']}), sha256 {gs['sha256'][:16]}... Both downloaded on 23.10.2026."],
], widths=[4, 13])

h("T7. Procedure actually followed", 2)
p("Step 1, design and pre-registration (23.10.2026, 00:50 to 01:24). After the Assignment 2 feedback we rewrote "
  "the RQ, chose Llama 3.1 8B Instruct as the single model (it is the model studied by Kurtic et al. (2025) and "
  "Huang et al. (2024) in our literature review), and listed the serving conditions. We downloaded the two datasets, "
  "built the fixed prompt sets with seed 42, wrote the harness and the condition file, and then wrote the Expected "
  "Results (Segment 1, T9) and committed them to git at 01:23 before the first benchmark request was sent. The "
  "commit hash and time are visible in the repository history.")
p("Step 2, local server setup (01:24). The model file Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf (4,920,739,232 bytes, "
  "sha256 7b064f58...) was downloaded from the bartowski repository on Hugging Face. llama-server build b11429 was "
  "started with 16 parallel slots of 1,024 tokens each, flash attention on, all layers on the GPU, prompt caching "
  "off (so that a repeated prompt is not answered from cache) and reasoning off. The identical command is in "
  f"bench/serve_mac.sh and bench/windows/serve_pc.ps1. Figure {FIG_N + 1} shows the server configuration as reported "
  "by its own /props and /metrics endpoints.")
f_server = fig(FIG / "fig_mac_server_props.png",
               "llama-server on the Mac after the pilot: model path, 16 slots of 1,024 tokens, build b11429, and the "
               "token counters of the /metrics endpoint. Own screenshot, 23.10.2026 01:39.")
p("Step 3, smoke test (01:25). Three prompts of each task were sent at concurrency 1 to check timing, token "
  "accounting and answer extraction. These files are kept in runs/_smoke and excluded from analysis.")
p("Step 4, Mac pilot (01:25 to 01:36). The pilot protocol (bench/pilot_mac.sh) sent the 50 pilot throughput prompts "
  "at concurrency 1, 4 and 16, twice each, with two untimed warm-up requests before each level, then the 30 pilot "
  f"GSM8K items at concurrency 4. Figure {FIG_N + 1} is the console output of this run.")
f_pilot = fig(FIG / "fig_pilot_console.png",
              "Console output of the Mac pilot protocol: one line per level with requests completed, wall time, "
              "requests/s, output tokens/s, median latency and median time to first token. Own screenshot.")
p("Step 5, hosted pilots (01:34 to about 02:00). The same protocol was run against each hosted condition. "
  "Provider pinning uses OpenRouter's provider.order field with allow_fallbacks set to false, and every response "
  "line stores the provider name that OpenRouter returns, so a silent fallback would be visible in the data. "
  "DeepInfra and Novita rejected every request with HTTP 429 (shared upstream pool overloaded) during this "
  "window; the attempts are kept in runs/_smoke and the research log, and Cloudflare was added as a second fp8 "
  "provider. The Anthropic condition uses the official SDK with thinking disabled, so that the closed model "
  "answers in the same single-pass mode as the 8B model.")
p("Step 6, main runs (24 to 26.10.2026). Each condition receives the 200 main throughput prompts at concurrency "
  "1, 4 and 16 with three repeats, and the 100 main GSM8K items at concurrency 4 with two repeats. Local runs are "
  "accompanied by a power log (nvidia-smi once per second on the PC and the rented GPU, powermetrics on the Mac). "
  "The PC is operated by the team with the scripts in bench/windows; the rented GPU condition runs in the public Colab notebook bench/cloud/colab_benchmark.ipynb. "
  f"Figure {FIG_N + 1} shows the raw data file of one run exactly as it is stored.")
f_raw = fig(FIG / "fig_raw_jsonl.png",
            "Head of a raw run file (runs/mac_m4pro/*.jsonl): the meta line with the server configuration, then "
            "one JSON line per request with timing, tokens, status and the model's answer. Own screenshot.")
p("Step 7, processing. bench/summarize.py rebuilds results/requests_all.csv (one row per request, model text "
  "removed), results/summary_by_level.csv (one row per condition, task, set, concurrency and repeat) and "
  "results/summary_by_condition.csv (median over repeats). bench/cost_model.py turns throughput and prices.json "
  "into USD per 1,000 requests at 1,000, 10,000 and 100,000 requests per day. bench/make_figures.py draws the "
  "plots from these CSV files only. Nothing in the report is typed in by hand from a terminal.")
p("Fairness between conditions. All conditions receive byte-identical prompts and system messages, the same "
  "max_tokens (256 throughput, 400 quality), temperature 0 and seed 42 where the endpoint accepts them, the same "
  "180 s timeout, the same warm-up, and the same closed-loop concurrency. The local server runs with prompt cache "
  "off. Hosted conditions were run from the same Mac on the same home connection in Astana. Permissions: no "
  "permissions were needed; the datasets are public under MIT and CC BY-NC 4.0 licences, the model under the "
  "Llama 3.1 Community License, and the API accounts belong to the team. Environment and versions: macOS 26.5.1, "
  "Python 3.14.0, httpx, anthropic SDK 2.1.0, llama.cpp b11429; Windows 11 and CUDA 12 on the PC; versions of "
  "the PC and rented-GPU builds are recorded in the meta line of their run files.")

h("T8. Ethics, privacy and data handling", 2)
table([
    ["Item", "Entry"],
    ["Consent obtained and how", "Not applicable: no human participants. The prompts come from two public datasets and the only people involved are the two team members operating their own machines and accounts."],
    ["Anonymization", "Not applicable. Run files contain no names, e-mails or account identifiers; API keys are read from a git-ignored .env file and never written to logs."],
    ["What personal data we did NOT collect", "No names, contacts, IP addresses, account balances or payment data. Alpaca and GSM8K contain no real personal data; the GSM8K problems use fictional first names."],
    ["Storage, access control and retention", "Raw run files are committed to the public GitHub repository and mirrored to the public Drive folder; both stay open until the end of the trimester and after. The model file is not committed (size) but is identified by checksum."],
    ["Risk accepted, and why it is acceptable", "Hosted providers receive the prompt texts; because the prompts are public dataset items, nothing confidential leaves the machine. Spending risk is bounded: the hosted runs cost under 3 USD in total and the rented GPU under 5 USD. The Alpaca license is non-commercial, which matches an academic benchmark."],
], widths=[4.5, 12.5])

h("T9. Expected Results", 2)
p("Expectations were fixed on 23.10.2026 at 01:23 Astana time, committed to git before the first run, and are "
  "reproduced here from docs/expected_results.md without change. Each line names what would falsify it.", count=False)
table([["No.", "Expected result (one sentence)", "Connected objective (from A1/A2)", "What would falsify it", "Confidence and why"]] + er_rows(),
      widths=[1, 5.5, 2.5, 4, 4], font=8, caption="Expected results, fixed 23.10.2026")
p("Six scenarios. Bad 1: the local machines cannot finish the concurrency-16 levels without timeouts, so capacity "
  "cannot be measured. Bad 2: provider pinning fails silently, so the provider comparison is not interpretable. "
  "Medium 1: the hosted API is cheaper at every measured volume and no break-even exists below 100,000 requests per "
  "day; the answer to the RQ is 'none in range'. Medium 2: a break-even exists for the PC but not for the Mac, so "
  "the answer depends on the hardware class. Good 1: a break-even between 10,000 and 100,000 requests per day is "
  "found for both machines and the quality loss of the 4-bit model is under 5 points. Good 2: the break-even is "
  "found and fp8 and 4-bit quality differ measurably, which gives a quality-cost trade-off table rather than one number. "
  "Date when these expectations were fixed: 23.10.2026.")

h("T10. Method-related expectations (Technical / ML row)", 2)
table([
    ["Declared before data analysis", "Our entry"],
    ["Expected value or range of each metric per condition", "Decode speed per request at concurrency 1: Mac 35 to 50 tokens/s, PC 40 to 60, rented 4090 100 to 150, "
     "Groq 300 to 900, other hosted providers 50 to 150, Haiku 80 to 150. Aggregate output at concurrency 16: Mac 100 to 150 tokens/s, PC 150 to 300, "
     "4090 600 to 1,200. TTFT: local under 0.5 s, hosted 0.3 to 1.5 s. GSM8K accuracy: Llama 8B 70 to 88 percent in every serving condition, Haiku 90 percent or more."],
    ["Expected ranking of conditions", "Throughput at concurrency 16: Groq > rented 4090 > CoreWeave > Cloudflare > PC > Mac. Cost per 1,000 requests at 1,000/day: "
     "cheapest fp8 provider < Groq < CoreWeave < Haiku < rented 4090 < PC < Mac. At 100,000/day the order of PC and the hosted providers is expected to flip."],
    ["Failure modes or error classes expected most often", "HTTP 429 rate limits on hosted endpoints at concurrency 16; answers cut at max_tokens (finish_reason length) on long Alpaca prompts; "
     "GSM8K answers without the 'Answer:' line, which the parser handles by taking the last number; no local errors."],
    ["Result that would indicate leakage or a broken process", "TTFT under 0.05 s on a local run at concurrency 16 (prompt cache still on); provider field different from the pinned provider; "
     "accuracy of exactly 0 or 100 percent (parser failure); aggregate throughput higher than single-request throughput times concurrency (timing bug); "
     "identical wall times across repeats to the millisecond (file reused)."],
], widths=[5, 12])

# ================================================================ SEGMENT 2
h("Segment 2. Data Collection Instrument", 1)
h("T1. Provenance information", 2)
table([
    ["Element", "Source it came from", "Adopted / adapted / self-developed", "What exactly we took", "What we changed, or why we built our own"],
    ["Overall design", "Pan et al. (2025), https://doi.org/10.1109/BigData66926.2025.11400957; Tombor and Abonyi (2026), https://doi.org/10.1109/ACCESS.2026.3726058",
     "Adapted", "The break-even idea: on-premise cost (hardware amortization plus electricity) against commercial API price per request; the cost categories of Tombor and Abonyi.",
     "Pan et al. assume 8 hours of use and data-centre GPUs; we measure the capacity of consumer machines ourselves and express cost at three daily volumes instead of a payback time. Staff cost is left out, which both papers also do."],
    ["Sampling approach", "Kwon et al. (2023), https://doi.org/10.1145/3600006.3613165", "Adapted",
     "The use of the Alpaca instruction set as a request trace for serving benchmarks.",
     "Fixed random subsets with seed 42, a length filter (40 to 600 characters) so every prompt fits a 1,024-token slot, and disjoint pilot and main sets."],
    ["Instrument (harness)", "Own work; follows the OpenAI-compatible streaming API that llama-server and OpenRouter share", "Self-developed",
     "Not applicable", "No published harness measured all of our conditions through one code path with per-request cost and provider capture. Confidence comes from the smoke tests, the pilot (330 local and 1,320 hosted requests with 0 failures on the working providers), the broken-process checks in T10, and the fact that every number is recomputable from the raw files."],
    ["Scales or items", "GSM8K, the evaluation set used by Kurtic et al. (2025), https://doi.org/10.18653/v1/2025.acl-long.1304; dataset by Cobbe et al. (2021)", "Adapted",
     "100 test items with numeric reference answers; exact-match scoring.",
     "Zero-shot with a fixed instruction and an 'Answer: <number>' line instead of few-shot prompting, so that the same prompt works for every endpoint and the output stays short."],
    ["Metrics or evaluation protocol", "Li et al. (2026), arXiv:2605.02821; Kurtic et al. (2025)", "Adapted",
     "Time to first token, output tokens per second and per-provider comparison of the same open-weight model (Li et al.); accuracy of quantized Llama 3.1 8B (Kurtic et al.).",
     "Added closed-loop concurrency levels tied to daily volumes, a per-request cost field, and a sustainable requests-per-day figure derived from throughput."],
    ["Dataset", "Alpaca (Taori et al., 2023); GSM8K (Cobbe et al., 2021)", "Adopted", "The public files as published.", "Nothing in the files; only the subset selection described in T6."],
], widths=[2.4, 3.6, 2.2, 4, 4.8], font=8)

h("T2. Replication status", 2)
table([
    ["Declaration", "What was repeated"],
    ["Original study", "The design (one model, nine serving conditions, three concurrency levels tied to daily volumes), the harness, the prompt sets and the cost model were built by the team. No published study was used as a template because none of the kept papers compares the same 8B model on consumer hardware and across hosted providers at the same workload: Pan et al. (2025) and Tombor and Abonyi (2026) model cost analytically, Li et al. (2026) measure providers but not local hardware, and Kurtic et al. (2025) measure quantization quality but not cost. Elements borrowed from these papers are listed in T1 as 'adapted'."],
], widths=[3, 14])

h("T3. Our research is an original study", 2)
table([
    ["Element", "Our study"],
    ["Research question or hypothesis", RQ + " Hypothesis: a break-even volume exists between 1,000 and 100,000 requests per day, and the 4-bit local model stays within 5 accuracy points of the hosted bf16 model."],
    ["Methodology and design", "Quantitative controlled benchmark with repeated measures; nine serving conditions; concurrency 1, 4, 16; three repeats (main); cost model on measured throughput."],
    ["Population, sample or dataset, and size", "Alpaca 200 main + 50 pilot prompts; GSM8K 100 main + 30 pilot items; seed 42; disjoint subsets."],
    ["Instrument", "bench/run.py harness (streaming client, per-request timing, token and cost capture, answer parser); llama-server with a fixed configuration; OpenRouter provider pinning; Anthropic SDK."],
    ["Experimental or technical procedure", "Segment 1, T7: pre-registration, server setup, smoke test, pilot, hosted pilots, main runs with power logging, processing by scripts."],
    ["Analysis method applied", "Medians and p95 per cell; aggregate throughput to requests per day; cost per 1,000 requests at three volumes; break-even search; accuracy gap between conditions; comparison with pre-registered expectations."],
    ["Main reported result", "Segment 4 reports the pilot comparison; the full result (the break-even volume or its absence) is reported in Assignment 4."],
], widths=[4.5, 12.5])
p("T4 (partial replication) is not applicable.", count=False)

# ================================================================ SEGMENT 3
h("Segment 3. Research Evidence", 1)
h("T1. Instrument register", 2)
table([
    ["Instrument", "Platform", "What it collects", "Public link"],
    ["Benchmark harness bench/run.py", "Python 3.14, httpx, anthropic SDK", "Per request: TTFT, latency, prompt and output tokens, cost, status, provider, answer text; per level: summary line", LINKS["github"] + "/blob/main/bench/run.py"],
    ["Prompt sets", "JSONL files built by bench/make_prompts.py", "The 250 Alpaca prompts and 130 GSM8K items with ids, source indices and gold answers", LINKS["github"] + "/tree/main/data/prompts"],
    ["Local server configuration", "llama.cpp llama-server b11429 (bench/serve_mac.sh, bench/windows/serve_pc.ps1)", "Serves the model; its /props and /metrics endpoints are logged", LINKS["github"] + "/blob/main/bench/serve_mac.sh"],
    ["Condition file", "bench/conditions.json", "Endpoint, model id, provider pin and hardware description of every condition", LINKS["github"] + "/blob/main/bench/conditions.json"],
    ["Power logger", "nvidia-smi (PC, rented GPU), powermetrics (Mac)", "Power draw, utilisation, memory once per second", LINKS["drive"] + " (power logs in runs/)"],
    ["Price assumptions", "bench/prices.json", "Hardware prices, tariff, API list prices with sources and access dates", LINKS["github"] + "/blob/main/bench/prices.json"],
], widths=[3.5, 3.5, 5, 5], font=8)

h("T2. Log journal and data storage", 2)
table([
    ["Item", "Our entry"],
    ["Research log / diary", "docs/research_log.md: dated rows, who did what, what went wrong, what was changed (reproduced in Table " + str(TAB_N + 2) + ")."],
    ["Raw data file", "runs/<condition>/<timestamp>_<task>_<set>.jsonl. One JSON line per request with t_start, ttft_s, latency_s, prompt_tokens, completion_tokens, cost_usd, status, http_status, error, provider, finish_reason, text (the model answer), and for quality runs gold, pred, correct. results/requests_all.csv is the same data as one CSV without the answer texts."],
    ["Processed data file", "results/summary_by_level.csv and results/summary_by_condition.csv (produced by bench/summarize.py; cleaning = drop warm-up rows and the _smoke folder, nothing else), results/cost_per_1000_main.csv (bench/cost_model.py)."],
    ["Public repository", "GitHub (code, prompts, runs, results, figures, docs) and Google Drive (mirror of runs, results, figures, docs, plus the power logs and screenshots). Open to anyone with the link until the end of the trimester and after."],
    ["URL", LINKS["github"] + "\n" + LINKS["drive"]],
    ["Folder structure", "See Segment 1, T1. Raw data = runs/; working copy = results/. The file that produces the Assignment 4 interpretation is results/cost_per_1000_main.csv together with results/summary_by_condition.csv."],
], widths=[4, 13])
table([["Date", "Who", "What was done", "What went wrong", "What was changed"]] + log_rows(),
      widths=[2.2, 1.5, 6, 4, 3.3], font=8, caption="Research log (docs/research_log.md)")

h("T3. Artefacts developed", 2)
table([
    ["Artefact", "What it does in the study", "Public link", "Evidence presented"],
    ["bench/run.py", "Sends prompts, measures, writes raw data", LINKS["github"] + "/blob/main/bench/run.py", f"Figure {f_pilot} (console), Figure {f_raw} (raw file)"],
    ["bench/make_prompts.py", "Builds the fixed prompt sets and their card with checksums", LINKS["github"] + "/blob/main/bench/make_prompts.py", "data/prompts/prompt_sets_card.json"],
    ["bench/summarize.py, bench/cost_model.py, bench/make_figures.py", "Processing, cost model, plots", LINKS["github"] + "/tree/main/bench", "results/*.csv, figures/*.png"],
    ["bench/serve_mac.sh, bench/windows/*.ps1, bench/cloud/colab_benchmark.ipynb", "Identical server configuration on three kinds of machine", LINKS["github"] + "/tree/main/bench", f"Figure {f_server}"],
], widths=[4, 4.5, 5, 3.5], font=8)

h("T4. Block D: Technical study and benchmark", 2)
p("D.0 requirements, where each is met: datasets are cited with authors and links (D.1); the fixed subsets and "
  "seed are given (D.2); no training takes place, and the pilot and main subsets are disjoint (D.2, leakage "
  "statement in D.5); every metric is defined as a formula with its direction (D.4); the comparison condition is "
  "the cheapest hosted provider of the same model, and the closed-weight Claude Haiku 5.5 is a second reference "
  "(D.3); the notebook equivalent (the scripts) and all run logs are in the public repository with a README (T1, T2).")

h("D.1 Dataset card", 3)
table([
    ["Item", "Alpaca (throughput prompts)", "GSM8K test split (quality items)"],
    ["Dataset name and version", "Stanford Alpaca, alpaca_data.json, repository state of 23.10.2026", "GSM8K, grade_school_math/data/test.jsonl, repository state of 23.10.2026"],
    ["Date of access, license", "23.10.2026, CC BY-NC 4.0", "23.10.2026, MIT"],
    ["Full citation with DOI or link", "Taori et al. (2023), https://github.com/tatsu-lab/stanford_alpaca", "Cobbe et al. (2021), https://arxiv.org/abs/2110.14168; data at https://github.com/openai/grade-school-math"],
    ["Size, unit of records", f"{al['records_total']:,} records of instruction, input, output; we use instruction plus input as the prompt", f"{gs['records_total']:,} records of question and answer; the number after '####' is the reference"],
    ["Class or categories existed", "No labels; free-form tasks (writing, lists, code, classification). Length of our prompts: 40 to 600 characters", "No labels; every item is a word problem with one integer or decimal answer"],
    ["Missing or wrong items found and stated", f"{al['records_total'] - al['records_after_length_filter']:,} records fall outside the length filter and are not eligible; no empty instructions found in the drawn subset. Alpaca outputs were generated by text-davinci-003 and are not used", "None in the drawn 130 items; all reference answers parse as numbers. 100 items give a 95 percent confidence half-width of about 7 to 9 accuracy points, which limits how small a gap we can detect"],
    ["Weakness in the dataset-based part", "Alpaca prompts are short English instructions, so prompt processing is a small share of each request; a RAG or long-context product would shift cost toward prompt tokens, which this benchmark does not measure. GSM8K tests arithmetic reasoning only; a team whose product writes marketing copy learns nothing about its quality from this number.", ""],
], widths=[3.5, 6.75, 6.75], font=8)

h("D.2 Splits", 3)
table([
    ["Split", "Proportion", "Size", "Seed"],
    ["Train", "none: no model is trained or tuned", "0", "-"],
    ["Validation (pilot)", "Alpaca: first 50 of the seeded draw; GSM8K: first 30", "50 prompts, 30 items", "42"],
    ["Test (main)", "Alpaca: next 200 of the same draw; GSM8K: next 100", "200 prompts, 100 items", "42"],
    ["Repeated runs per condition", "Throughput: 3 repeats at each of 3 concurrency levels (pilot: 2); quality: 2 repeats at concurrency 4 (pilot: 1)", "1,800 throughput and 200 quality requests per condition in the main set", "42 passed as the decoding seed where supported"],
], widths=[3.5, 6.5, 4, 3])

h("D.3 System configuration", 3)
rows = [["Condition", "Hardware / provider", "Engine and weights", "Key parameters", "Precise rules"]]
for k, v in COND.items():
    if k.startswith("_"):
        continue
    eng = v.get("engine", "")
    params = ("ctx 16,384 shared, 16 slots x 1,024; flash attention on; all 33 layers on GPU; prompt cache off; batch 2,048; "
              "max_tokens 256/400; temperature 0; seed 42") if "llama.cpp" in eng else \
             ("OpenRouter provider.order pinned, allow_fallbacks false; max_tokens 256/400; temperature 0; seed 42 passed; usage.include true")
    if v["backend"] == "anthropic":
        params = "Anthropic SDK 2.1.0, messages.stream; thinking disabled; max_tokens 256/400; default sampling (the API rejects other values)"
    rows.append([SHORT[k], v["hardware"], eng if v["backend"] != "anthropic" else "provider-managed, closed weights",
                 params, "Same system prompt and user prompt bytes for every condition; streaming on; 180 s timeout; 2 warm-up requests per level, not recorded"])
table(rows, widths=[1.8, 4.6, 3.4, 4.4, 2.8], font=7.5, caption="Serving conditions")
p("Comparison condition: the cheapest working hosted endpoint of the same model (DeepInfra fp8 when available, "
  "otherwise Cloudflare fp8) is the baseline against which local cost is judged; Groq and CoreWeave show the spread "
  "within 'the API'; Claude Haiku 5.5 shows what a closed model costs and scores on the same items.")

h("D.4 Metric definitions", 3)
table([
    ["Metric", "Definition (formula or precise rule)", "Direction and why it matters for the RQ"],
    ["Time to first token, TTFT", "t(first streamed content chunk) minus t(request sent), per request; reported as median and p95 over the 200 main prompts", "Lower is better. It is what a user waits before text appears, and it separates prompt-processing cost from decoding."],
    ["End-to-end latency L", "t(stream closed) minus t(request sent), per request; median and p95", "Lower is better. p95 at concurrency 16 shows whether a machine can serve a busy hour without unacceptable waits."],
    ["Decode speed per request", "completion_tokens / (L minus TTFT), per request; median", "Higher is better. The raw generation speed a single user sees."],
    ["Aggregate throughput", "sum of completion_tokens of successful requests in a level / wall time of the level", "Higher is better. Determines how many requests a machine can serve per day."],
    ["Requests per second, RPS", "successful requests in a level / wall time of the level", "Higher is better."],
    ["Sustainable requests per day", "RPS at concurrency 16 x 86,400", "Higher is better. Upper bound on the volume a condition can serve if loaded 24 hours; a volume above it is 'not servable'."],
    ["Cost per 1,000 requests at volume V (local)", "( price / (365 x 3) + kWh(V) x tariff ) / V x 1,000, where kWh(V) = (busy_hours(V) x P_load + (24 minus busy_hours) x P_idle) / 1,000 and busy_hours(V) = V / (RPS_16 x 3,600); prices and tariff from prices.json", "Lower is better. This is the quantity the RQ asks about."],
    ["Cost per 1,000 requests (hosted)", "1,000 x mean(cost_usd per request) from the provider's own usage.cost field; for Anthropic, tokens x list price", "Lower is better."],
    ["Cost per 1,000 requests (rented GPU)", "24 h x hourly rent / V x 1,000, subject to the same capacity rule", "Lower is better."],
    ["Break-even volume", "Smallest V on a log grid from 1,000 to 100,000 at which local cost per 1,000 is below the baseline provider's cost per 1,000; 'none' if no such V below capacity", "The answer to the RQ."],
    ["GSM8K accuracy", "correct / 100, where correct = 1 if the number after the last 'Answer:' (or the last number in the text when the marker is missing) equals the reference within 1e-6; errors count as wrong", "Higher is better. 'Equal answer quality' in the RQ means the gap to the bf16 hosted model is within 5 points."],
    ["Failure rate", "requests with status other than ok / all requests in a level", "Lower is better. An endpoint that drops 5 percent of requests at concurrency 16 cannot serve that volume."],
], widths=[3.3, 8.2, 5.5], font=8)

h("D.5 Evidence to present", 3)
table([
    ["Evidence", "Where it is"],
    ["Repository or notebook link", LINKS["github"] + " (public; prompt sets and seed in data/prompts; every script in bench/)"],
    ["Run logs", "runs/<condition>/*.jsonl in the repository and on Drive: every run, including the two failed DeepInfra and Novita attempts (runs/_smoke) and both concurrency-16 repeats of the Mac pilot that differ by a factor of 1.7"],
    ["Full run", f"Figure {f_pilot}: console of the Mac pilot from the first level to 'done'; the corresponding JSONL ends with a level_summary line for every level"],
    ["Leakage statement", "No model is trained, so training leakage is impossible. The pilot items were used to check the harness and the answer parser; the main items were drawn from the same seeded shuffle after the pilot items, the overlap check in prompt_sets_card.json is 0, and nothing in the harness was changed after seeing main-set outputs. Prompt caching on the local server is off, so a repeated prompt costs full compute."],
    ["Existing artefacts", f"Harness, server scripts and prompt builder with public links (T3); Figures {f_server} to {FIG_N} are our own screenshots and plots"],
], widths=[4, 13], font=8)

from docx.enum.section import WD_ORIENT, WD_SECTION
def landscape(on=True):
    sec = doc.add_section(WD_SECTION.NEW_PAGE)
    if on:
        sec.orientation = WD_ORIENT.LANDSCAPE
        sec.page_width, sec.page_height = Cm(29.7), Cm(21.0)
    else:
        sec.orientation = WD_ORIENT.PORTRAIT
        sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)
    sec.left_margin = sec.right_margin = Cm(1.5); sec.top_margin = sec.bottom_margin = Cm(1.5)
landscape(True)
h("D.6 All metric measurements per condition and per run", 3)
if not LVL.empty:
    cols = ["condition", "task", "set", "concurrency", "repeat", "n_ok", "n", "wall_s", "req_per_s", "agg_out_tok_per_s",
            "ttft_p50_s", "latency_p50_s", "latency_p95_s", "decode_tok_per_s_p50", "cost_usd", "accuracy", "sustainable_req_per_day"]
    rows = [["Cond.", "Task", "Set", "c", "rep", "ok/n", "wall s", "req/s", "out tok/s", "TTFT p50", "L p50", "L p95", "decode tok/s", "cost USD", "acc.", "req/day"]]
    for _, r in LVL.sort_values(["set", "condition", "task", "concurrency", "repeat"]).iterrows():
        rows.append([SHORT.get(r["condition"], r["condition"]), r["task"][:5], r["set"], int(r["concurrency"]), int(r["repeat"]), f'{int(r["n_ok"])}/{int(r["n"])}',
                     fmt(r["wall_s"], 1), fmt(r["req_per_s"], 3), fmt(r["agg_out_tok_per_s"], 1), fmt(r["ttft_p50_s"], 3), fmt(r["latency_p50_s"], 2),
                     fmt(r["latency_p95_s"], 2), fmt(r["decode_tok_per_s_p50"], 1), fmt(r["cost_usd"], 5) if pd.notna(r["cost_usd"]) else "model",
                     fmt(r["accuracy"], 3) if pd.notna(r["accuracy"]) else "-", f'{int(r["sustainable_req_per_day"]):,}' if pd.notna(r["sustainable_req_per_day"]) else "-"])
    table(rows, font=7, widths=[1.6, 1.3, 1.1, 0.8, 0.8, 1.5, 1.5, 1.4, 1.6, 1.5, 1.4, 1.4, 1.7, 1.7, 1.2, 1.8], caption="Every run, every level (results/summary_by_level.csv). cost 'model' = computed by the cost model, not billed")
    fails = LVL[LVL["n_ok"] < LVL["n"]]
    nfail = int((LVL["n"] - LVL["n_ok"]).sum())
    p(f"Repetitions: {int(LVL.repeat.max())} per level in the main set, 2 in the pilot. Failure and error cases: {nfail} failed requests out of "
      f"{int(LVL['n'].sum())} recorded in the table above" + (": " + "; ".join(f"{SHORT.get(r['condition'], r['condition'])} {r['task']} {r['set']} c={int(r['concurrency'])} r={int(r['repeat'])}: {int(r["n"] - r["n_ok"])} ({r["errors"]})" for _, r in fails.iterrows()) if nfail else ".")
      + " The DeepInfra and Novita smoke tests (4 requests, all HTTP 429) are the only requests not in this table.")

landscape(False)
# ================================================================ SEGMENT 4
h("Segment 4. Expected Against Observed. Preliminary comparison", 1)
h("T1. Completion table", 2)
def completion_rows():
    rows = []
    if LVL.empty:
        return rows
    for cond in [c for c in LABEL if c in set(LVL.condition)]:
        g = LVL[LVL.condition == cond]
        def n(task, s):
            gg = g[(g.task == task) & (g.set == s)]
            return int(gg.n_ok.sum()), int(gg["n"].sum())
        tm, tmn = n("throughput", "main"); tp, tpn = n("throughput", "pilot")
        qm, qmn = n("quality", "main"); qp, qpn = n("quality", "pilot")
        planned = "1,800 throughput + 200 quality requests (main); 300 + 30 (pilot)"
        if cond in ("mac_m4pro_q8",):
            planned = "800 throughput (c=1, c=16 x 2) + 200 quality (main); no pilot"
        if cond in ("mac_m4pro_loaded",):
            planned = "not planned (observation)"
        rows.append([SHORT[cond] + ": " + LABEL[cond].split(": ", 1)[1], planned,
                     f"main: {tm}/{tmn} throughput, {qm}/{qmn} quality; pilot: {tp}/{tpn} throughput, {qp}/{qpn} quality (ok/sent)"])
    for extra in S4.get("completion", []):
        rows.append(extra)
    return rows
table([["Data to be collected", "Planned", "Collected (at report date)"]] + completion_rows(), widths=[6, 5, 6], font=8)
h("T2. Comparison", 2)
table([["Expected result", "What actual data shows", "Verdict", "Where it can be found"]] + S4["comparison"],
      widths=[4.5, 6, 2.5, 4], font=8)
h("T3. What the first data says about the instrument", 2)
for para in S4["text"]:
    p(para)
for fpath, cap in S4.get("figures", []):
    fig(FIG / fpath, cap)

# ================================================================ REFERENCES
h("Reference list", 1)
REFS = [
    "Cobbe, K., Kosaraju, V., Bavarian, M., Chen, M., Jun, H., Kaiser, L., Plappert, M., Tworek, J., Hilton, J., Nakano, R., Hesse, C. and Schulman, J. (2021) 'Training verifiers to solve math word problems', arXiv preprint, arXiv:2110.14168. Available at: https://doi.org/10.48550/arXiv.2110.14168.",
    "Grattafiori, A. et al. (2024) 'The Llama 3 herd of models', arXiv preprint, arXiv:2407.21783. Available at: https://doi.org/10.48550/arXiv.2407.21783.",
    "Huang, W., Zheng, X., Ma, X., Qin, H., Lv, C., Chen, H., Luo, J., Qi, X., Liu, X. and Magno, M. (2024) 'An empirical study of LLaMA3 quantization: from LLMs to MLLMs', Visual Intelligence, 2(1), article 36. Available at: https://doi.org/10.1007/s44267-024-00070-x.",
    "Kurtic, E., Marques, A., Pandit, S., Kurtz, M. and Alistarh, D. (2025) '\"Give me BF16 or give me death\"? Accuracy-performance trade-offs in LLM quantization', in Proceedings of the 63rd Annual Meeting of the Association for Computational Linguistics (Volume 1: Long Papers). Vienna: Association for Computational Linguistics, pp. 26872-26886. Available at: https://doi.org/10.18653/v1/2025.acl-long.1304.",
    "Kwon, W., Li, Z., Zhuang, S., Sheng, Y., Zheng, L., Yu, C.H., Gonzalez, J.E., Zhang, H. and Stoica, I. (2023) 'Efficient memory management for large language model serving with PagedAttention', in Proceedings of the 29th Symposium on Operating Systems Principles (SOSP '23). Koblenz: ACM, pp. 611-626. Available at: https://doi.org/10.1145/3600006.3613165.",
    "Li, H., He, Z., Liu, X., Xu, Y., Liu, D., Ma, J., Wu, L., Wu, Y., Tang, X. and Shi, T. (2026) 'When is the same model not the same service? A measurement study of hosted open-weight LLM APIs', arXiv preprint, arXiv:2605.02821v3. Available at: https://arxiv.org/abs/2605.02821v3 (Accessed: 3 October 2026).",
    "Pan, G., Chodnekar, V., Roy, A. and Wang, H. (2025) 'A cost-benefit analysis of on-premise large language model deployment: breaking even with commercial LLM services', in 2025 IEEE International Conference on Big Data (BigData). Macau: IEEE, pp. 2234-2239. Available at: https://doi.org/10.1109/BigData66926.2025.11400957.",
    "Taori, R., Gulrajani, I., Zhang, T., Dubois, Y., Li, X., Guestrin, C., Liang, P. and Hashimoto, T.B. (2023) Stanford Alpaca: an instruction-following LLaMA model. Available at: https://github.com/tatsu-lab/stanford_alpaca (Accessed: 23 October 2026).",
    "Tombor, P. and Abonyi, J. (2026) 'Activity-based costing framework for total cost of ownership analysis of LLM services', IEEE Access, 14, pp. 130163-130186. Available at: https://doi.org/10.1109/ACCESS.2026.3726058.",
]
for r in REFS:
    para = doc.add_paragraph(r)
    para.paragraph_format.left_indent = Cm(1)
    para.paragraph_format.first_line_indent = Cm(-1)
    para.paragraph_format.space_after = Pt(4)
    for run in para.runs:
        run.font.size = Pt(10)

h("Free-access links", 1)
for name, url in LINKS.items():
    p(f"{name}: {url}", count=False)

doc.save(OUT)
print(f"saved {OUT}\nprose words (excluding tables, captions, RQ, references, links): {PROSE_WORDS}\nfigures: {FIG_N}, tables: {TAB_N}")
