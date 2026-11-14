#!/usr/bin/env python3
"""End-to-end check of the proxy loop fallback on the real long-context cases that looped at high effort.

Sends each case exactly as the client would (effort high, tools, tool_choice auto, original seed and budget; no
loop_guard_stop field: the proxy adds it), through :8889. Compare against the same cases' earlier high-effort runs.
usage: run_loop_fallback_e2e.py OUT_DIR
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
CASES = [  # (label, conv, seed, budget): every case that hit a long reasoning loop at high effort on 2026-11-14
    ("B1", 1, 18001, 8192), ("B2", 2, 18002, 8192), ("B3", 3, 18003, 8192),
    ("L10316", 1, 10316, 0), ("L10416", 1, 10416, 0),
    ("Q1s11", 1, 11, 0), ("Q1s22", 1, 22, 0), ("Q3s22", 3, 22, 0),
]


def run(case):
    label, conv, seed, budget = case
    msgs = syn.apply_keep_n(syn.build_conversation(conv), 2)
    sup.warmup_req(msgs, syn.TOOLS, "auto", "high", label)
    body = {"model": sup.MODEL, "messages": msgs, "tools": syn.TOOLS, "tool_choice": "auto", "max_tokens": 32768,
            "temperature": 0.3, "top_p": 0.95, "top_k": 20, "seed": seed, "reasoning_effort": "high", "stream": True,
            "stream_options": {"include_usage": True}}
    if budget:
        body["thinking_budget"] = budget
    meta, rt, ct = sup.post_stream(body)
    row = {"label": label, "conv": conv, "seed": seed, "budget": budget, **meta}
    with lock, open(OUT, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print("E2E", json.dumps({k: row.get(k) for k in ("label", "finish", "reasoning_tokens", "content_tokens", "c_chars",
                                                     "tool_calls", "dsml_in_content", "engine_loop", "wall_s")}), flush=True)


with concurrent.futures.ThreadPoolExecutor(3) as ex:
    list(ex.map(run, CASES))
