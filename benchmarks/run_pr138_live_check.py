#!/usr/bin/env python3
"""PR #138 live check: re-run the 85K conversations that produced long reasoning loops (conv 1 A_base, conv 11 effort=max)
with tools + tool_choice=auto on the guarded engine. Records whether the engine guard fired, and what the reply did after
the forced think close (stop with content / tool_calls / DSML in content / length).

usage: run_pr138_live_check.py OUT.jsonl
"""
import concurrent.futures, json, os, sys, threading

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import run_longctx_synthesis as syn
import run_longctx_supplement as sup

OUT = sys.argv[1]
lock = threading.Lock()
JOBS = [
    {"name": "conv1_high", "conv": 1, "effort": "high", "seeds": [10016, 10116, 10216]},
    {"name": "conv11_max", "conv": 11, "effort": "max", "seeds": [15008, 15108, 15208]},
]


def run(job, seed):
    msgs = syn.apply_keep_n(syn.build_conversation(job["conv"]), 2)
    body = {
        "model": sup.MODEL, "messages": msgs, "tools": syn.TOOLS, "tool_choice": "auto",
        "max_tokens": 32768, "temperature": 0.3, "top_p": 0.95, "top_k": 20, "seed": seed,
        "reasoning_effort": job["effort"], "stream": True, "stream_options": {"include_usage": True},
    }
    meta, rt, ct = sup.post_stream(body)
    row = {"job": job["name"], "conv": job["conv"], "effort": job["effort"], "seed": seed, **meta}
    with lock, open(OUT, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print("LIVE", json.dumps({k: row[k] for k in ("job", "seed", "finish", "reasoning_tokens", "content_tokens",
                                                  "tool_calls", "dsml_in_content", "valid_delivery", "engine_loop",
                                                  "loop_r", "loop_r_period", "wall_s")}), flush=True)


tasks = [(j, s) for j in JOBS for s in j["seeds"]]
with concurrent.futures.ThreadPoolExecutor(3) as ex:
    list(ex.map(lambda t: run(*t), tasks))
