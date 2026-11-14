#!/usr/bin/env python3
"""Think-close hint A/B on the PR #138 + hint engine (paired: same conversation, same seed, hint off vs on).

The forced think close (loop guard or thinking_budget) is identical up to the cut, so each pair differs only in what the
engine writes at the close: plain "\\n</think>\\n\\n" (off) or HINT + that (on, request field think_close_hint).

Suites:
  L : conv 1 (85K, 8 tools, auto), effort=high, no budget, seeds that looped under PR #138 + extra seeds -> loop-guard closes
  B : synthesis convs 0..7 (85K, 8 tools, auto), effort=high, thinking_budget=8192 -> budget closes (B8 forced 8/16 tool calls)

usage: run_think_close_hint_ab.py OUT_DIR
"""
import concurrent.futures, json, os, sys, threading

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import run_longctx_synthesis as syn
import run_longctx_supplement as sup

OUT_DIR = sys.argv[1]
os.makedirs(OUT_DIR, exist_ok=True)
OUT = os.path.join(OUT_DIR, "results.jsonl")
lock = threading.Lock()
HINT = ("\n\nTime is up for reasoning. I already have all the evidence I need, so I will not call any tool or read any "
        "more files. I will now write the complete final answer directly.")

jobs = []
for seed in (10116, 10216, 10316, 10416):
    jobs.append({"suite": "L", "conv": 1, "effort": "high", "budget": 0, "seed": seed})
for conv in range(8):
    jobs.append({"suite": "B", "conv": conv, "effort": "high", "budget": 8192, "seed": 18000 + conv})

done = set()
if os.path.exists(OUT):
    for l in open(OUT):
        r = json.loads(l)
        if r.get("status") == 200 and not r.get("err"):
            done.add((r["suite"], r["conv"], r["seed"], r["arm"]))


def run_pair(job):
    msgs = syn.apply_keep_n(syn.build_conversation(job["conv"]), 2)
    sup.warmup_req(msgs, syn.TOOLS, "auto", job["effort"], f"{job['suite']}_{job['conv']}")
    for arm in ("off", "on"):
        if (job["suite"], job["conv"], job["seed"], arm) in done:
            continue
        body = {
            "model": sup.MODEL, "messages": msgs, "tools": syn.TOOLS, "tool_choice": "auto",
            "max_tokens": 32768, "temperature": 0.3, "top_p": 0.95, "top_k": 20, "seed": job["seed"],
            "reasoning_effort": job["effort"], "stream": True, "stream_options": {"include_usage": True},
        }
        if job["budget"]:
            body["thinking_budget"] = job["budget"]
        if arm == "on":
            body["think_close_hint"] = HINT
        meta, rt, ct = sup.post_stream(body)
        row = {**job, "arm": arm, **meta, "r_tail_full": rt[-600:]}
        with lock, open(OUT, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        print("AB", json.dumps({k: row[k] for k in ("suite", "conv", "seed", "arm", "finish", "reasoning_tokens",
                                                    "content_tokens", "tool_calls", "dsml_in_content", "valid_delivery",
                                                    "engine_loop", "wall_s")}), flush=True)


with concurrent.futures.ThreadPoolExecutor(3) as ex:
    list(ex.map(run_pair, jobs))
