#!/usr/bin/env python3
"""Option 2 feasibility: does a lower reasoning effort avoid the loops that PR #138 catches?

Takes every (conv, seed) that looped in the hint A/B or the --loop-guard-stop backtest (engine_loop period >= 9),
and re-runs the same request at effort medium / low / none (thinking off), two seeds each (the original seed and
seed+7777, the seed the stop backtest retried with). Same messages, tools (8, tool_choice=auto), thinking_budget and
sampling as the original. The engine is the production PR #138 default (loop guard closes and lets the model answer).

A proxy fallback ("on a reasoning loop, re-send at a lower effort") is worth building only if these arms deliver an
answer (finish=stop, content >= 200 tokens, no DSML) clearly more often than the high-effort original.

usage: run_effort_fallback_probe.py OUT_DIR
"""
import concurrent.futures, json, os, sys, threading

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import run_longctx_synthesis as syn
import run_longctx_supplement as sup

OUT_DIR = sys.argv[1]
os.makedirs(OUT_DIR, exist_ok=True)
OUT = os.path.join(OUT_DIR, "results.jsonl")
R = os.path.join(HERE, "results")
lock = threading.Lock()


def looped_cases():
    cases = {}
    for path in ("think_close_hint_ab_20261114/results.jsonl", "loop_stop_backtest_20261114/results.jsonl"):
        for line in open(os.path.join(R, path)):
            r = json.loads(line)
            loop = r.get("engine_loop") or {}
            if (loop.get("period") or 0) >= 9:
                cases[(r["suite"], r["conv"], r["seed"])] = {"suite": r["suite"], "conv": r["conv"], "seed": r["seed"],
                                                              "budget": r.get("budget") or 0}
    return [cases[k] for k in sorted(cases)]


done = set()
if os.path.exists(OUT):
    for line in open(OUT):
        r = json.loads(line)
        if r.get("status") == 200 and not r.get("err"):
            done.add((r["suite"], r["conv"], r["seed"], r["effort"], r["run_seed"]))


def run(case):
    msgs = syn.apply_keep_n(syn.build_conversation(case["conv"]), 2)
    sup.warmup_req(msgs, syn.TOOLS, "auto", "medium", f"{case['suite']}_{case['conv']}")
    for effort in ("medium", "low", "none"):
        for run_seed in (case["seed"], case["seed"] + 7777):
            if (case["suite"], case["conv"], case["seed"], effort, run_seed) in done:
                continue
            body = {
                "model": sup.MODEL, "messages": msgs, "tools": syn.TOOLS, "tool_choice": "auto",
                "max_tokens": 32768, "temperature": 0.3, "top_p": 0.95, "top_k": 20, "seed": run_seed,
                "reasoning_effort": effort, "stream": True, "stream_options": {"include_usage": True},
            }
            if case["budget"] and effort != "none":
                body["thinking_budget"] = case["budget"]
            meta, rt, ct = sup.post_stream(body)
            row = {**case, "effort": effort, "run_seed": run_seed, **meta}
            with lock, open(OUT, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            print("FB", json.dumps({k: row.get(k) for k in ("suite", "conv", "seed", "effort", "run_seed", "finish",
                                                            "reasoning_tokens", "content_tokens", "tool_calls",
                                                            "engine_loop", "wall_s")}), flush=True)


cases = looped_cases()
print("cases", json.dumps(cases), flush=True)
with concurrent.futures.ThreadPoolExecutor(3) as ex:
    list(ex.map(run, cases))
