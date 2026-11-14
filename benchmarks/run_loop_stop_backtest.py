#!/usr/bin/env python3
"""--loop-guard-stop backtest on the same 12 jobs as run_think_close_hint_ab.py (same convs, seeds, effort, budget).

Engine runs with --loop-guard-stop. A loop fire now ends the reply with finish_reason=content_filter and
error.code=reasoning_loop (no answer, no tool call). The client (a stand-in for a proxy policy) retries such a reply
once with a different seed. Records the first attempt and the retry separately, so we can compare:
  - stop alone: how fast and how cleanly a loop now fails (vs PR #138 default: forced close -> tool_calls)
  - stop + one retry: end-to-end valid-answer rate and wall time vs the default A/B 'off' arm

usage: run_loop_stop_backtest.py OUT_DIR
"""
import concurrent.futures, json, os, sys, threading, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import run_longctx_synthesis as syn
import run_longctx_supplement as sup

OUT_DIR = sys.argv[1]
os.makedirs(OUT_DIR, exist_ok=True)
OUT = os.path.join(OUT_DIR, "results.jsonl")
lock = threading.Lock()
RETRY_SEED_OFFSET = 7777

jobs = []
for seed in (10116, 10216, 10316, 10416):
    jobs.append({"suite": "L", "conv": 1, "effort": "high", "budget": 0, "seed": seed})
for conv in range(8):
    jobs.append({"suite": "B", "conv": conv, "effort": "high", "budget": 8192, "seed": 18000 + conv})


def one(job, msgs, seed, attempt):
    body = {
        "model": sup.MODEL, "messages": msgs, "tools": syn.TOOLS, "tool_choice": "auto",
        "max_tokens": 32768, "temperature": 0.3, "top_p": 0.95, "top_k": 20, "seed": seed,
        "reasoning_effort": job["effort"], "stream": True, "stream_options": {"include_usage": True},
    }
    if job["budget"]:
        body["thinking_budget"] = job["budget"]
    meta, rt, ct = sup.post_stream(body)
    row = {**job, "arm": "stop", "attempt": attempt, "run_seed": seed, **meta}
    with lock, open(OUT, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print("STOP", json.dumps({k: row.get(k) for k in ("suite", "conv", "seed", "attempt", "finish", "reasoning_tokens",
                                                      "content_tokens", "tool_calls", "engine_loop", "wall_s")}), flush=True)
    return row


def run(job):
    msgs = syn.apply_keep_n(syn.build_conversation(job["conv"]), 2)
    sup.warmup_req(msgs, syn.TOOLS, "auto", job["effort"], f"{job['suite']}_{job['conv']}")
    first = one(job, msgs, job["seed"], 0)
    if first.get("finish") == "content_filter":
        one(job, msgs, job["seed"] + RETRY_SEED_OFFSET, 1)


with concurrent.futures.ThreadPoolExecutor(3) as ex:
    list(ex.map(run, jobs))
