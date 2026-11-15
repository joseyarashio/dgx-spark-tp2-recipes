#!/usr/bin/env python3
"""Send the OmniScenario-1h test plan + evidence dossier to two external reviewers in parallel
(anthropic/claude-opus-5-5 and gpt-6-astra via OpenCodex :10100) and save their critiques."""
import concurrent.futures, json, subprocess, sys, time, urllib.request
from pathlib import Path

CFG = json.load(open("/home/joseyarashio/.opencodex/config.json"))
KEY = CFG["apiKeys"][0]["key"]
BASE = "http://127.0.0.1:10100/v1"
R = Path("/home/joseyarashio/dgx-spark-tp2-recipes")
OUT = R / "benchmarks/results/plan_review_omni_scenario_1h"
OUT.mkdir(parents=True, exist_ok=True)
REVIEWERS = [("anthropic/claude-opus-5-5", 24000), ("gpt-6-astra", 16000)]


def sh(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout


def list_models():
    req = urllib.request.Request(BASE + "/models", headers={"Authorization": f"Bearer {KEY}"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return [m["id"] for m in json.loads(r.read())["data"]]


def dossier():
    plan = (R / "benchmarks/plans/omni_scenario_1h_plan.md").read_text()
    stress = sh(f"sed -n 180,265p {R}/benchmarks/run_30min_stress_experiment.py")
    fields = sh("sed -n 195,260p /home/joseyarashio/TensorFold-dsv41-zig/zig/src/server/fields.zig")
    tmpl = sh("sed -n 1,45p /home/joseyarashio/models/DeepSeek-V4.1-Flash-1017-EXL3-2.9bpw/chat_template.jinja")
    proxy = sh("sed -n 955,1020p /home/joseyarashio/spark-fastfail-proxy/proxy.py")
    cmp_ = sh(f"cd {R}/benchmarks && python3 compare_1hour_runs.py results/omni_eval_1hour_p16_tokenmapfix_loopfallback.json results/omni_eval_1hour_p16_tokenmapfix_pr138.json")
    traffic = (OUT / "traffic_stats.txt").read_text() if (OUT / "traffic_stats.txt").exists() else ""
    return f"""# Evidence dossier

## Cluster
Two DGX Spark GB10 nodes (128 GB unified memory each), DeepSeek-V4.1-Flash-1017 (EXL3 2.9bpw) tensor-parallel TP=2 over ConnectX-7 200G RoCE, native Zig TensorFold engine on :8888 (8 decode slots, MTP speculative decoding, Imprint NVMe prompt-state cache, 2.5 GiB RAM prompt cache), Python priority reverse proxy on :8889 (8 slots, 8-deep queue, slot 8 reserved for P0/P1, tiered queue timeouts 25..4 s, tool_choice required/function -> auto rewrite, short-output effort->none rewrite, loop-guard fallback that re-sends with effort none). MS-DTC thermal governor. Live external client (MacBook) shares the engine.

## Current production release p17 and its last two 1-hour marathon results (compare_1hour_runs.py)
{cmp_}

## Real external traffic, last ~39 h (proxy audit log)
{traffic}

## Existing marathon workload generator (run_30min_stress_experiment.py worker_job)
```python
{stress}
```

## Engine thinking-field parsing (zig/src/server/fields.zig)
```zig
{fields}
```

## Model chat template header (effort handling)
```
{tmpl}
```

## Proxy request rewrites (proxy.py)
```python
{proxy}
```

# The test plan under review
{plan}
"""


PROMPT = """You are reviewing a test plan for a production LLM serving cluster. The owner wants a 1-hour, all-scenario test with no blind spots, and explicitly wants thinking/reasoning covered from every angle, and the standard release regression included.

Review the plan against the evidence dossier. Be concrete and use the cluster numbers given. Cover:
1. Coverage gaps: scenarios real traffic exercises (see the traffic stats) or the engine/proxy code paths support that the plan still misses. Mark each as must-add / nice-to-have.
2. Thinking coverage: is the thinking matrix complete and correctly grounded in the actual code (effort coercion in fields.zig, template levels low/high/max, proxy rewrites, loop-guard fallback, thinking_budget, reasoning history)? Point out wrong assumptions or untestable cells.
3. Time budget and statistical power: can everything fit in 60 minutes at 8 slots given ~30 s mean request time and long-context prefill (~2,200 tok/s cold)? Which cells are underpowered, and what to cut or merge. Give a revised minute-by-minute schedule.
4. Measurement validity: confounders (Imprint cache state, external client traffic, order effects between phases, closed-loop masking of 429 behavior, HTTP 200 vs valid delivery, TTFE vs TTFT), and whether gates are measurable and correctly thresholded. Flag gates that would pass a broken system or fail a healthy one.
5. Safety: anything in the plan that could crash or degrade production (OOM on unified memory, KV pool exhaustion with 220K contexts, BadSlot), and the mitigation.
6. Comparability with the p17 baseline: what can and cannot be compared.
Finish with a prioritized list of concrete changes (max 15 items). Plain technical English. No praise."""


def ask(model, max_tok, text):
    body = {"model": model, "max_tokens": max_tok, "messages": [{"role": "user", "content": PROMPT + "\n\n" + text}]}
    t0 = time.time()
    try:
        req = urllib.request.Request(BASE + "/chat/completions", json.dumps(body).encode(),
                                     {"Content-Type": "application/json", "Authorization": f"Bearer {KEY}"})
        with urllib.request.urlopen(req, timeout=1800) as r:
            d = json.loads(r.read())
        ch = d["choices"][0]
        m = ch["message"]
        return {"model": model, "ok": True, "wall": round(time.time() - t0, 1), "finish": ch.get("finish_reason"),
                "usage": d.get("usage"), "content": m.get("content") or m.get("reasoning_content") or ""}
    except Exception as e:
        err = e.read().decode()[:2000] if hasattr(e, "read") else ""
        return {"model": model, "ok": False, "wall": round(time.time() - t0, 1), "error": repr(e) + " " + err}


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "models":
        print([m for m in list_models() if any(k in m for k in ("opus", "astra", "fable"))])
        return
    text = dossier()
    (OUT / "dossier.md").write_text(text)
    print("dossier chars", len(text), flush=True)
    reviewers = REVIEWERS
    if len(sys.argv) > 2 and sys.argv[1] == "only":
        # e.g. `only anthropic/claude-opus-5-5 64000`: re-ask one reviewer (first try spent the whole budget thinking)
        reviewers = [(sys.argv[2], int(sys.argv[3]))]
    with concurrent.futures.ThreadPoolExecutor(2) as ex:
        res = list(ex.map(lambda s: ask(s[0], s[1], text), reviewers))
    for rv in res:
        tag = rv["model"].replace("/", "_")
        (OUT / f"{tag}.json").write_text(json.dumps(rv, ensure_ascii=False, indent=1))
        if rv.get("content"):
            (OUT / f"{tag}.md").write_text(rv["content"])
        print(rv["model"], rv["ok"], rv.get("finish"), rv.get("wall"), len(rv.get("content") or ""), rv.get("error", "")[:300], flush=True)


if __name__ == "__main__":
    main()
