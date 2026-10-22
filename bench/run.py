"""Benchmark harness: sends a fixed prompt set to one inference condition at a fixed
concurrency, streams the answers, and records per-request timing, tokens, cost and errors.

Usage example:
  python bench/run.py --condition mac_m4pro --task throughput --set pilot --concurrency 1 4 16 --repeats 2

Every request is written as one JSON line. Nothing is aggregated away: the summary is
recomputed from the JSONL by bench/summarize.py, so the raw file is the source of truth.
"""
import argparse
import asyncio
import datetime as dt
import json
import os
import platform
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

SYSTEM_THROUGHPUT = "You are a helpful assistant. Answer the request directly and concisely."
SYSTEM_QUALITY = ("Solve the math word problem. Reason step by step in a few short lines, "
                  "then write the final line exactly in the form 'Answer: <number>'.")
WARMUP_PROMPT = "Reply with the single word: ready."
NUM_RE = re.compile(r"-?\d[\d,]*\.?\d*")


def now_iso():
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")


def git_commit():
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                                       stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return None


def extract_number(text):
    """Return the number after the last 'Answer:' marker, else the last number in the text."""
    if not text:
        return None
    m = list(re.finditer(r"Answer:\s*\$?\s*(-?\d[\d,]*\.?\d*)", text, flags=re.I))
    cand = m[-1].group(1) if m else None
    if cand is None:
        nums = NUM_RE.findall(text)
        cand = nums[-1] if nums else None
    if cand is None:
        return None
    cand = cand.replace(",", "").rstrip(".")
    try:
        return float(cand)
    except ValueError:
        return None


def gold_matches(pred, gold):
    if pred is None or gold is None:
        return False
    try:
        return abs(pred - float(gold)) < 1e-6
    except ValueError:
        return False


async def call_openai_compat(client, cond, messages, max_tokens, seed, temperature, timeout):
    """Stream one chat completion through an OpenAI-compatible endpoint. Returns a record dict."""
    body = {
        "model": cond["model"],
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "seed": seed,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    body.update(cond.get("extra_body", {}))
    headers = {"Content-Type": "application/json"}
    key_env = cond.get("api_key_env")
    if key_env:
        key = os.environ.get(key_env)
        if not key:
            raise RuntimeError(f"{key_env} is not set in .env")
        headers["Authorization"] = f"Bearer {key}"
        headers["HTTP-Referer"] = "https://github.com/Newterios/rmt-llm-inference-benchmark"
        headers["X-Title"] = "RMT A3 inference benchmark"
    rec = {"ttft_s": None, "latency_s": None, "prompt_tokens": None, "completion_tokens": None,
           "tokens_estimated": False, "cost_usd": None, "provider": None, "finish_reason": None,
           "status": "ok", "http_status": None, "error": None, "text": "", "chunks": 0}
    t0 = time.perf_counter()
    try:
        async with client.stream("POST", cond["base_url"].rstrip("/") + "/chat/completions",
                                 json=body, headers=headers, timeout=timeout) as resp:
            rec["http_status"] = resp.status_code
            if resp.status_code != 200:
                rec["status"] = "error"
                rec["error"] = (await resp.aread())[:500].decode(errors="replace")
                rec["latency_s"] = time.perf_counter() - t0
                return rec
            async for line in resp.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    obj = json.loads(data)
                except json.JSONDecodeError:
                    continue
                if "error" in obj and not obj.get("choices"):
                    rec["status"] = "error"
                    rec["error"] = json.dumps(obj["error"])[:500]
                    break
                if obj.get("provider"):
                    rec["provider"] = obj["provider"]
                for ch in obj.get("choices", []):
                    delta = ch.get("delta", {}) or {}
                    piece = delta.get("content")
                    if piece:
                        if rec["ttft_s"] is None:
                            rec["ttft_s"] = time.perf_counter() - t0
                        rec["text"] += piece
                        rec["chunks"] += 1
                    if ch.get("finish_reason"):
                        rec["finish_reason"] = ch["finish_reason"]
                usage = obj.get("usage")
                if usage:
                    rec["prompt_tokens"] = usage.get("prompt_tokens")
                    rec["completion_tokens"] = usage.get("completion_tokens")
                    if usage.get("cost") is not None:
                        rec["cost_usd"] = usage["cost"]
    except httpx.TimeoutException as e:
        rec["status"] = "timeout"
        rec["error"] = repr(e)[:300]
    except Exception as e:  # network errors, protocol errors
        rec["status"] = "error"
        rec["error"] = repr(e)[:300]
    rec["latency_s"] = time.perf_counter() - t0
    if rec["status"] == "ok" and rec["completion_tokens"] is None:
        # provider did not return usage: estimate from streamed chunks and flag it
        rec["completion_tokens"] = rec["chunks"]
        rec["tokens_estimated"] = True
    if rec["status"] == "ok" and not rec["text"]:
        rec["status"] = "empty"
    return rec


async def call_anthropic(aclient, cond, system, user, max_tokens, timeout):
    """Stream one message through the official Anthropic SDK. Thinking is disabled so that the
    comparison with a non-reasoning 8B model stays like-for-like."""
    rec = {"ttft_s": None, "latency_s": None, "prompt_tokens": None, "completion_tokens": None,
           "tokens_estimated": False, "cost_usd": None, "provider": "Anthropic", "finish_reason": None,
           "status": "ok", "http_status": None, "error": None, "text": "", "chunks": 0}
    t0 = time.perf_counter()
    try:
        async with aclient.messages.stream(
            model=cond["model"], max_tokens=max_tokens, system=system,
            thinking={"type": "disabled"},
            messages=[{"role": "user", "content": user}],
        ) as stream:
            async for text in stream.text_stream:
                if text:
                    if rec["ttft_s"] is None:
                        rec["ttft_s"] = time.perf_counter() - t0
                    rec["text"] += text
                    rec["chunks"] += 1
            final = await stream.get_final_message()
            rec["http_status"] = 200
            rec["finish_reason"] = final.stop_reason
            rec["prompt_tokens"] = final.usage.input_tokens
            rec["completion_tokens"] = final.usage.output_tokens
            # list price for claude-haiku-5-5 (prompts <= 100K tokens): $0.10 / $0.50 per 1M tokens
            rec["cost_usd"] = final.usage.input_tokens * 0.10 / 1e6 + final.usage.output_tokens * 0.50 / 1e6
            if final.stop_reason == "refusal":
                rec["status"] = "refusal"
    except Exception as e:
        rec["status"] = "timeout" if "Timeout" in type(e).__name__ else "error"
        rec["error"] = repr(e)[:300]
        rec["http_status"] = getattr(e, "status_code", None)
    rec["latency_s"] = time.perf_counter() - t0
    if rec["status"] == "ok" and not rec["text"]:
        rec["status"] = "empty"
    return rec


async def run_level(cond, cond_name, prompts, task, concurrency, repeat, args, out_path, meta):
    system = SYSTEM_QUALITY if task == "quality" else SYSTEM_THROUGHPUT
    sem = asyncio.Semaphore(concurrency)
    results = []
    aclient = None
    if cond["backend"] == "anthropic":
        import anthropic
        aclient = anthropic.AsyncAnthropic(timeout=args.timeout, max_retries=0)
    limits = httpx.Limits(max_connections=concurrency + 2, max_keepalive_connections=concurrency + 2)
    async with httpx.AsyncClient(limits=limits, timeout=args.timeout) as client:
        async def one(p, is_warmup=False):
            async with sem:
                t_start = now_iso()
                if cond["backend"] == "anthropic":
                    rec = await call_anthropic(aclient, cond, system, p["prompt"], args.max_tokens, args.timeout)
                else:
                    messages = [{"role": "system", "content": system}, {"role": "user", "content": p["prompt"]}]
                    rec = await call_openai_compat(client, cond, messages, args.max_tokens, args.seed,
                                                   args.temperature, args.timeout)
                rec.update({"type": "request", "condition": cond_name, "task": task, "set": args.set,
                            "concurrency": concurrency, "repeat": repeat, "prompt_id": p["id"],
                            "warmup": is_warmup, "t_start": t_start, "max_tokens": args.max_tokens})
                if task == "quality":
                    rec["gold"] = p.get("gold")
                    rec["pred"] = extract_number(rec["text"]) if rec["status"] == "ok" else None
                    rec["correct"] = gold_matches(rec["pred"], p.get("gold")) if rec["status"] == "ok" else False
                if rec["status"] == "ok" and rec["ttft_s"] and rec["completion_tokens"]:
                    decode = rec["latency_s"] - rec["ttft_s"]
                    rec["decode_tok_per_s"] = rec["completion_tokens"] / decode if decode > 0 else None
                else:
                    rec["decode_tok_per_s"] = None
                return rec

        # warm-up: two untimed requests so model load / connection setup is not counted
        for _ in range(args.warmup):
            await one({"id": "warmup", "prompt": WARMUP_PROMPT}, is_warmup=True)
        wall0 = time.perf_counter()
        results = await asyncio.gather(*[one(p) for p in prompts])
        wall = time.perf_counter() - wall0
    ok = [r for r in results if r["status"] == "ok"]
    summary = {
        "type": "level_summary", "condition": cond_name, "task": task, "set": args.set,
        "concurrency": concurrency, "repeat": repeat, "n_requests": len(results), "n_ok": len(ok),
        "n_failed": len(results) - len(ok),
        "wall_s": round(wall, 3),
        "requests_per_s": round(len(ok) / wall, 4) if wall else None,
        "agg_output_tok_per_s": round(sum(r["completion_tokens"] or 0 for r in ok) / wall, 2) if wall else None,
        "total_prompt_tokens": sum(r["prompt_tokens"] or 0 for r in ok),
        "total_completion_tokens": sum(r["completion_tokens"] or 0 for r in ok),
        "total_cost_usd": round(sum(r["cost_usd"] or 0 for r in ok), 6) if any(r["cost_usd"] is not None for r in ok) else None,
        "finished_at": now_iso(),
    }
    if task == "quality":
        summary["accuracy"] = round(sum(1 for r in ok if r["correct"]) / len(results), 4) if results else None
    with open(out_path, "a", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
        f.write(json.dumps(summary, ensure_ascii=False) + "\n")
    lat = sorted(r["latency_s"] for r in ok)
    ttft = sorted(r["ttft_s"] for r in ok if r["ttft_s"])
    p50 = lat[len(lat) // 2] if lat else None
    p50t = ttft[len(ttft) // 2] if ttft else None
    extra = f" acc={summary['accuracy']}" if task == "quality" else ""
    print(f"[{cond_name}] {task}/{args.set} c={concurrency} r={repeat}: ok={len(ok)}/{len(results)} "
          f"wall={wall:.1f}s req/s={summary['requests_per_s']} out_tok/s={summary['agg_output_tok_per_s']} "
          f"p50_lat={p50 and round(p50, 2)}s p50_ttft={p50t and round(p50t, 3)}s cost=${summary['total_cost_usd']}{extra}",
          flush=True)
    return summary


def local_server_props(base_url):
    try:
        r = httpx.get(base_url.replace("/v1", "") + "/props", timeout=5)
        if r.status_code == 200:
            p = r.json()
            keep = {k: p.get(k) for k in ("model_path", "total_slots", "build_info", "default_generation_settings")}
            if isinstance(keep.get("default_generation_settings"), dict):
                keep["n_ctx_per_slot"] = keep["default_generation_settings"].get("n_ctx")
                keep.pop("default_generation_settings", None)
            return keep
    except Exception:
        return None
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--condition", required=True)
    ap.add_argument("--task", choices=["throughput", "quality"], required=True)
    ap.add_argument("--set", choices=["pilot", "main"], required=True)
    ap.add_argument("--concurrency", type=int, nargs="+", default=[1])
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--max-tokens", type=int, default=None)
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--timeout", type=float, default=180.0)
    ap.add_argument("--warmup", type=int, default=2)
    ap.add_argument("--limit", type=int, default=None, help="use only the first N prompts (smoke tests)")
    ap.add_argument("--note", default="")
    args = ap.parse_args()
    if args.max_tokens is None:
        args.max_tokens = 400 if args.task == "quality" else 256

    conds = json.load(open(ROOT / "bench" / "conditions.json"))
    cond = conds[args.condition]
    prompts = [json.loads(l) for l in open(ROOT / "data" / "prompts" / f"{args.task}_{args.set}.jsonl", encoding="utf-8")]
    if args.limit:
        prompts = prompts[: args.limit]

    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = ROOT / "runs" / args.condition
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{stamp}_{args.task}_{args.set}.jsonl"
    meta = {
        "type": "meta", "condition": args.condition, "condition_config": {k: v for k, v in cond.items() if k != "api_key_env"},
        "task": args.task, "set": args.set, "n_prompts": len(prompts), "concurrency_levels": args.concurrency,
        "repeats": args.repeats, "max_tokens": args.max_tokens, "temperature": args.temperature, "seed": args.seed,
        "timeout_s": args.timeout, "warmup": args.warmup, "started_at": now_iso(), "hostname": socket.gethostname(),
        "platform": platform.platform(), "python": sys.version.split()[0], "git_commit": git_commit(),
        "harness": "bench/run.py", "note": args.note,
    }
    if cond["backend"] == "openai_compat" and "127.0.0.1" in cond["base_url"]:
        meta["server_props"] = local_server_props(cond["base_url"])
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(meta, ensure_ascii=False) + "\n")
    print(f"writing {out_path.relative_to(ROOT)}", flush=True)

    summaries = []
    for c in args.concurrency:
        for r in range(1, args.repeats + 1):
            summaries.append(asyncio.run(run_level(cond, args.condition, prompts, args.task, c, r, args, out_path, meta)))
    print("done:", out_path.relative_to(ROOT))


if __name__ == "__main__":
    main()
