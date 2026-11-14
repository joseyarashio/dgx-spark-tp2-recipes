#!/usr/bin/env python3
"""Summarize Phase 2 Supplement (S1/S2/S3a/S3b), check raw loop captures against PR#138 thresholds,
and run dual external LLM audit (claude-fable-5-2 + gpt-6-astra).
"""
import collections
import concurrent.futures
import json
import os
import random
import re
import statistics
import sys
import time
import urllib.request

RES_DIR = sys.argv[1]
CFG = json.load(open("/home/joseyarashio/.opencodex/config.json"))
KEY = CFG["apiKeys"][0]["key"]
URL = "http://127.0.0.1:10100/v1/chat/completions"


def q(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(p * (len(xs) - 1)))] if xs else None


def summarize_suite(path: str):
    if not os.path.exists(path):
        return []
    rows = [json.loads(l) for l in open(path)]
    arms = []
    for r in rows:
        if r["arm"] not in arms:
            arms.append(r["arm"])
    out = []
    for name in arms:
        rs = [r for r in rows if r["arm"] == name]
        ok = [r for r in rs if r.get("status") == 200 and not r.get("err")]
        comps = [r["completion_tokens"] or 0 for r in ok]
        reass = [r["reasoning_tokens"] or 0 for r in ok]
        conts = [r["content_tokens"] or 0 for r in ok]
        ttfts = [r["ttft_s"] for r in ok if r.get("ttft_s") is not None]
        walls = [r["wall_s"] for r in ok if r.get("wall_s") is not None]
        caches = [r["cached_tokens"] / max(1, r["prompt_tokens"]) for r in ok if r.get("prompt_tokens")]
        prompts = [r["prompt_tokens"] for r in ok if r.get("prompt_tokens")]
        mems = [r["mem_after_gib"] for r in ok if r.get("mem_after_gib") is not None]
        out.append({
            "arm": name,
            "ok": len(ok),
            "total": len(rs),
            "finish_counts": dict(collections.Counter(r.get("finish") for r in ok)),
            "valid_delivery": sum(1 for r in ok if r.get("valid_delivery")),
            "has_code_block": sum(1 for r in ok if r.get("has_code_block")),
            "tool_call_reqs": sum(1 for r in ok if r.get("tool_calls")),
            "dsml_in_content_reqs": sum(1 for r in ok if r.get("dsml_in_content")),
            "loop_r": sum(1 for r in ok if r.get("loop_r")),
            "loop_r_periods": [r.get("loop_r_period") for r in ok if r.get("loop_r")],
            "loop_c": sum(1 for r in ok if r.get("loop_c")),
            "engine_loop": sum(1 for r in ok if r.get("engine_loop")),
            "prompt_p50": q(prompts, 0.5),
            "cache_hit_min": round(min(caches), 4) if caches else None,
            "cache_hit_med": round(statistics.median(caches), 4) if caches else None,
            "reas_p50": q(reass, 0.5),
            "reas_p90": q(reass, 0.9),
            "cont_p50": q(conts, 0.5),
            "cont_p90": q(conts, 0.9),
            "comp_p50": q(comps, 0.5),
            "ttft_p50": q(ttfts, 0.5),
            "ttft_p90": q(ttfts, 0.9),
            "wall_p50": q(walls, 0.5),
            "wall_sum": round(sum(walls), 1),
            "mem_min_gib": min(mems) if mems else None,
        })
    return out


def paired_s1(path: str):
    if not os.path.exists(path):
        return {}
    rows = [json.loads(l) for l in open(path)]
    by = {(r["conv_idx"], r["arm"]): r for r in rows if r.get("status") == 200 and not r.get("err")}
    arms = []
    for r in rows:
        if r["arm"] not in arms:
            arms.append(r["arm"])
    res = {}
    if "A_base" not in arms:
        return res
    for b in arms:
        if b == "A_base":
            continue
        ids = sorted({r["conv_idx"] for r in rows if (r["conv_idx"], "A_base") in by and (r["conv_idx"], b) in by})
        entry = {}
        for m in ("reasoning_tokens", "content_tokens", "ttft_s", "wall_s"):
            diffs = [by[(i, b)][m] - by[(i, "A_base")][m] for i in ids if by[(i, b)].get(m) is not None and by[(i, "A_base")].get(m) is not None]
            if diffs:
                rng = random.Random(42)
                boots = sorted(statistics.mean(rng.choices(diffs, k=len(diffs))) for _ in range(2000))
                entry[m] = {"n": len(diffs), "mean_diff": round(statistics.mean(diffs), 2),
                            "med_diff": round(statistics.median(diffs), 2),
                            "ci95": [round(boots[50], 2), round(boots[1950], 2)]}
        res[f"{b}_vs_A_base"] = entry
    return res


def analyze_loops_raw(path: str):
    if not os.path.exists(path):
        return []
    out = []
    LOOP_RE = re.compile(r"(.{20,600}?)\1{4,}", re.S)
    for line in open(path):
        r = json.loads(line)
        rt = r.get("reasoning") or ""
        m = LOOP_RE.search(rt[-16000:])
        info = {
            "suite": r.get("suite"),
            "conv_idx": r.get("conv_idx"),
            "arm": r.get("arm"),
            "seed": r.get("seed"),
            "r_len": len(rt),
            "c_len": len(r.get("content") or ""),
            "matched": bool(m),
        }
        if m:
            unit = m.group(1)
            # count full contiguous repeats from m.start()
            tail = rt[-16000:][m.start():]
            reps = 0
            pos = 0
            while tail.startswith(unit, pos):
                reps += 1
                pos += len(unit)
            info["unit_len_chars"] = len(unit)
            info["repeats_matched"] = reps
            info["total_repeat_chars"] = pos
            info["est_repeat_tokens"] = round(pos / 3.8)
            info["unit_preview"] = repr(unit[:180])
        out.append(info)
    return out


s1 = summarize_suite(os.path.join(RES_DIR, "results_s1.jsonl"))
s2 = summarize_suite(os.path.join(RES_DIR, "results_s2.jsonl"))
s3a = summarize_suite(os.path.join(RES_DIR, "results_s3a.jsonl"))
s3b = summarize_suite(os.path.join(RES_DIR, "results_s3b.jsonl"))
p_s1 = paired_s1(os.path.join(RES_DIR, "results_s1.jsonl"))
loops_info = analyze_loops_raw(os.path.join(RES_DIR, "loops_raw.jsonl"))

dossier = f"""# Phase 2 Supplement (P2S) Empirical Dossier

## S3a: OMP Short Task (max_tokens=120, tools=0, low vs none)
```json
{json.dumps(s3a, indent=2, ensure_ascii=False)}
```

## S1: 85K Long-Thinking Budget Closure & K0_warm Controls
```json
{json.dumps(s1, indent=2, ensure_ascii=False)}
```

### S1 Paired vs A_base
```json
{json.dumps(p_s1, indent=2, ensure_ascii=False)}
```

## S2: Production-Aligned ~200K Prompt + 5 Tools (low / medium / high)
```json
{json.dumps(s2, indent=2, ensure_ascii=False)}
```

## S3b: Loop Capture on conv_idx=11 & Raw Repetition Verification
```json
{json.dumps(s3b, indent=2, ensure_ascii=False)}
```

### Raw Loop Matches (checking unit length, repeat count, and est tokens vs PR#138 min_repeat=1024 tokens)
```json
{json.dumps(loops_info, indent=2, ensure_ascii=False)}
```
"""

with open(os.path.join(RES_DIR, "dossier.md"), "w", encoding="utf-8") as f:
    f.write(dossier)
print("Wrote", os.path.join(RES_DIR, "dossier.md"))


def call_critic(model: str, max_tok: int):
    prompt = (
        "你是獨立、嚴格的分散式推理系統與基準測試審計員。請僅根據下方補測 Dossier 的實測數據（不推測未測數據）給出結構化繁體中文審查：\n"
        "1. **S1（budget 關閉機制 + K0_warm）**：(a) 移除 tools / `tool_choice='none'` 後，觸及 `thinking_budget` 是否恢復正常 `stop` 交付？這如何證明/修正「為何掛工具+auto 會轉向 `read_file`」的根因？(b) 獨立暖快取後 `K0_warm` 的 TTFT 與長度是否優於 `A_base`？\n"
        "2. **S2（~200K + 5 tools）**：`low / medium / high` 在真實長上下文下表現、快取、TTFT 與 RAM 安全裕度。\n"
        "3. **S3a（OMP `max_tokens=120`）與 S3b（loop 原始文本檢驗）**：評估 `OMP120_none` 止損方案與 PR #138（`min_repeat=1024 tokens`）對本機抓到之重複片段的涵蓋率。\n"
        "4. **最終定案建議**：哪些可以直接落地 Proxy/配置，哪些仍須維持凍結或待引擎端修復。\n\n"
        + dossier
    )
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tok,
        "temperature": 0.2,
    }
    req = urllib.request.Request(URL, json.dumps(body, ensure_ascii=False).encode(),
                                 {"Content-Type": "application/json", "Authorization": f"Bearer {KEY}"})
    t0 = time.perf_counter()
    try:
        r = json.load(urllib.request.urlopen(req, timeout=600))
        ch = r["choices"][0]
        msg = ch["message"]
        txt = msg.get("content") or msg.get("reasoning_content") or ""
        res = {"model": model, "ok": True, "finish": ch.get("finish_reason"),
               "wall_s": round(time.perf_counter() - t0, 1), "text": txt}
    except Exception as e:
        res = {"model": model, "ok": False, "err": repr(e)[:200], "wall_s": round(time.perf_counter() - t0, 1), "text": ""}
    fname = f"critic_{model.replace('/', '_')}.json"
    with open(os.path.join(RES_DIR, fname), "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    return res


with concurrent.futures.ThreadPoolExecutor(2) as ex:
    critics = list(ex.map(lambda m: call_critic(*m), [
        ("anthropic/claude-fable-5-2", 24000),
        ("gpt-6-astra", 16000),
    ]))

report = [dossier]
for c in critics:
    report.append(f"\n---\n## Reviewer: {c['model']} (ok={c['ok']}, finish={c.get('finish')}, wall={c['wall_s']}s)\n\n{c.get('text') or c.get('err')}")
with open(os.path.join(RES_DIR, "audit_report.md"), "w", encoding="utf-8") as f:
    f.write("\n".join(report))
print("Wrote", os.path.join(RES_DIR, "audit_report.md"))
