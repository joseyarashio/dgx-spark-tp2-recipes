#!/usr/bin/env python3
"""Phase 2 Supplement (P2S) — closes all non-restart observability & experimental gaps.

Suites:
  s1  : 85K long-thinking synthesis controls (N=8 convs x 6 arms = 48 reqs, CONC=3):
        - A_base       : effort=high, keep_n=2, budget=0, tools=8, tool_choice="auto"
        - K0_warm      : effort=high, keep_n=0, budget=0, tools=8, tool_choice="auto" (explicitly pre-warmed!)
        - B8_tc_none   : effort=high, keep_n=2, budget=8192, tools=8, tool_choice="none"
        - B8_no_tools  : effort=high, keep_n=2, budget=8192, tools=None
        - EB16_tc_none : effort=max,  keep_n=2, budget=16384, tools=8, tool_choice="none"
        - EB16_no_tools: effort=max,  keep_n=2, budget=16384, tools=None
  s2  : Production-aligned ~200K prompt + 5 tools (N=8 convs x 3 arms = 24 reqs, CONC=2):
        - P200_low     : effort=low,    tools=5, tool_choice="auto", max_tokens=32768
        - P200_med     : effort=medium, tools=5, tool_choice="auto", max_tokens=32768
        - P200_high    : effort=high,   tools=5, tool_choice="auto", max_tokens=32768
  s3a : OMP short-task control (max_tokens=120, tools=0, N=10):
        - OMP120_low   : reasoning_effort="low"
        - OMP120_none  : reasoning_effort="none"
  s3b : Loop reproduction capture on conv_idx=11 (E_max & EB16_max_tb16k, 4 reps each, saves full text).

Usage:
  python3 run_longctx_supplement.py --suite s3a OUT_DIR
  python3 run_longctx_supplement.py --suite all OUT_DIR
  python3 run_longctx_supplement.py --summary OUT_DIR/results_s1.jsonl
"""
import argparse
import collections
import concurrent.futures
import contextlib
import io
import json
import os
import random
import re
import statistics
import string
import sys
import threading
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
with contextlib.redirect_stdout(io.StringIO()):
    import run_5hour_stress_experiment as s5
import run_longctx_synthesis as syn

API = os.environ.get("API", "http://127.0.0.1:8889/v1/chat/completions")
MODEL = "DeepSeek-V4.1-Flash-1017-TF"
MAXTOK = int(os.environ.get("MAXTOK", "32768"))
LOOP_RE = re.compile(r"(.{20,600}?)\1{4,}", re.S)
lock = threading.Lock()


def mem_avail_gib() -> float | None:
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    kb = int(line.split()[1])
                    return round(kb / (1024 * 1024), 3)
    except Exception:
        pass
    return None


def post_stream(body: dict, timeout: int = 1800) -> tuple[dict, str, str]:
    req = urllib.request.Request(
        API,
        json.dumps(body, ensure_ascii=False).encode("utf-8"),
        {"Content-Type": "application/json", "X-Priority": "2"},
    )
    t0 = time.perf_counter()
    ttft = None
    c_parts, r_parts = [], []
    tc_by_idx = {}
    fin = None
    usage = {}
    loop_meta = None
    status = 0
    err = None
    for attempt in range(4):
        ttft = None
        c_parts, r_parts = [], []
        tc_by_idx = {}
        fin = None
        usage = {}
        loop_meta = None
        status = 0
        err = None
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                status = resp.status
                for raw in resp:
                    line = raw.decode("utf-8", "replace").strip()
                    if not line.startswith("data: "):
                        continue
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    try:
                        ch = json.loads(data)
                    except Exception:
                        continue
                    if ch.get("usage"):
                        usage = ch["usage"]
                    if isinstance(ch.get("tensorfold"), dict) and ch["tensorfold"].get("loop"):
                        loop_meta = ch["tensorfold"]["loop"]
                    for choice in ch.get("choices") or []:
                        d = choice.get("delta") or {}
                        c_txt = d.get("content") or ""
                        r_txt = d.get("reasoning_content") or d.get("reasoning") or ""
                        tcs = d.get("tool_calls") or []
                        if c_txt:
                            c_parts.append(c_txt)
                        if r_txt:
                            r_parts.append(r_txt)
                        for tc in tcs:
                            ix = tc.get("index", 0)
                            fn = tc.get("function") or {}
                            if ix not in tc_by_idx and fn.get("name"):
                                tc_by_idx[ix] = fn["name"]
                        if (c_txt or r_txt or tcs) and ttft is None:
                            ttft = time.perf_counter() - t0
                        if choice.get("finish_reason"):
                            fin = choice["finish_reason"]
            break
        except urllib.error.HTTPError as e:
            status = e.code
            err = repr(e)[:180]
            if attempt < 3:
                time.sleep(2.0 + random.uniform(1.0, 4.0) * (attempt + 1))
                continue
        except Exception as e:
            err = repr(e)[:180]
            if attempt < 3:
                time.sleep(2.0 + random.uniform(1.0, 4.0))
                continue
            break

    ct, rt = "".join(c_parts), "".join(r_parts)
    m_c = LOOP_RE.search(ct[-16000:])
    m_r = LOOP_RE.search(rt[-16000:])
    tc_names = [tc_by_idx[k] for k in sorted(tc_by_idx)]
    undeclared_tc = [n for n in tc_names if n not in syn.DECLARED_TOOLS]
    dsml_in_content = ("DSML" in ct) or ("<｜DSML｜" in ct) or ("<tool_call>" in ct)
    ptd = usage.get("prompt_tokens_details") or {}
    ctd = usage.get("completion_tokens_details") or {}
    comp = usage.get("completion_tokens")
    reas = ctd.get("reasoning_tokens")
    cont_tok = max(0, comp - reas) if (comp is not None and reas is not None) else None
    valid_delivery = (
        status == 200
        and not err
        and fin == "stop"
        and len(ct.strip()) >= 500
        and not tc_names
        and not dsml_in_content
    )
    meta = {
        "status": status,
        "err": err,
        "finish": fin,
        "prompt_tokens": usage.get("prompt_tokens"),
        "cached_tokens": ptd.get("cached_tokens"),
        "completion_tokens": comp,
        "reasoning_tokens": reas,
        "content_tokens": cont_tok,
        "r_chars": len(rt),
        "c_chars": len(ct),
        "tool_calls": tc_names,
        "undeclared_tc": undeclared_tc,
        "dsml_in_content": dsml_in_content,
        "valid_delivery": valid_delivery,
        "has_code_block": ("```" in ct),
        "loop_r": bool(m_r),
        "loop_r_period": len(m_r.group(1)) if m_r else None,
        "loop_c": bool(m_c),
        "loop_c_period": len(m_c.group(1)) if m_c else None,
        "engine_loop": loop_meta,
        "ttft_s": round(ttft, 3) if ttft else None,
        "wall_s": round(time.perf_counter() - t0, 2),
        "c_head": ct[:400],
        "c_tail": ct[-400:],
        "r_tail": rt[-400:],
    }
    return meta, rt, ct


def warmup_req(msgs: list[dict], tools: list[dict] | None, tool_choice: str | None, effort: str, label: str) -> dict:
    body = {
        "model": MODEL,
        "messages": msgs,
        "max_tokens": 1,
        "temperature": 0.3,
        "reasoning_effort": effort,
        "stream": False,
    }
    if tools is not None:
        body["tools"] = tools
        body["tool_choice"] = tool_choice or "auto"
    req = urllib.request.Request(
        API,
        json.dumps(body, ensure_ascii=False).encode("utf-8"),
        {"Content-Type": "application/json", "X-Priority": "2"},
    )
    t0 = time.perf_counter()
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=1800) as resp:
                r = json.load(resp)
            u = r.get("usage") or {}
            return {
                "label": label,
                "prompt": u.get("prompt_tokens"),
                "cached": (u.get("prompt_tokens_details") or {}).get("cached_tokens"),
                "s": round(time.perf_counter() - t0, 2),
            }
        except Exception as e:
            if attempt == 3:
                return {"label": label, "err": repr(e)[:120], "s": round(time.perf_counter() - t0, 2)}
            time.sleep(3 + 3 * attempt)
    return {}


def write_jsonl(path: str, obj: dict):
    with lock, open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Suite 1: 85K Budget & K0_warm Controls
# ---------------------------------------------------------------------------
S1_ARMS = [
    {"name": "A_base",        "effort": "high", "keep_n": 2, "budget": 0,     "tools": True,  "tc": "auto"},
    {"name": "K0_warm",       "effort": "high", "keep_n": 0, "budget": 0,     "tools": True,  "tc": "auto"},
    {"name": "B8_tc_none",    "effort": "high", "keep_n": 2, "budget": 8192,  "tools": True,  "tc": "none"},
    {"name": "B8_no_tools",   "effort": "high", "keep_n": 2, "budget": 8192,  "tools": False, "tc": None},
    {"name": "EB16_tc_none",  "effort": "max",  "keep_n": 2, "budget": 16384, "tools": True,  "tc": "none"},
    {"name": "EB16_no_tools", "effort": "max",  "keep_n": 2, "budget": 16384, "tools": False, "tc": None},
]
S1_IDX = {a["name"]: i for i, a in enumerate(S1_ARMS)}


def run_s1(out_dir: str, n_convs: int, conc: int):
    out_path = os.path.join(out_dir, "results_s1.jsonl")
    warm_path = os.path.join(out_dir, "warmup_s1.jsonl")
    raw_path = os.path.join(out_dir, "loops_raw.jsonl")
    done = set()
    if os.path.exists(out_path):
        done = {(r["conv_idx"], r["arm"]) for r in map(json.loads, open(out_path)) if r.get("status") == 200 and not r.get("err")}

    rng = random.Random(20261114)
    convs = []
    for c in range(n_convs):
        g = [a for a in S1_ARMS if (c, a["name"]) not in done]
        rng.shuffle(g)
        if g:
            convs.append((c, g))
    print(f"[S1] convs={len(convs)} jobs={sum(len(g) for _, g in convs)} conc={conc} out={out_path}", flush=True)

    def do_conv(conv_idx: int, arms: list[dict]):
        base_msgs = syn.build_conversation(conv_idx)
        msgs_k2 = syn.apply_keep_n(base_msgs, 2)
        msgs_k0 = syn.apply_keep_n(base_msgs, 0)
        # Warm ALL prefix variants needed by arms in this conv
        needed_warms = set()
        for a in arms:
            needed_warms.add((a["effort"], a["keep_n"], a["tools"], a["tc"]))
        w_info = {"conv_idx": conv_idx, "warms": []}
        # Warm base keep_n=2 with tools first so KV blocks populate sequentially
        warm_specs = sorted(needed_warms, key=lambda x: (x[1] != 2, not x[2], x[0]))
        for eff, kn, use_t, tc in warm_specs:
            m = msgs_k0 if kn == 0 else msgs_k2
            t = syn.TOOLS if use_t else None
            w_info["warms"].append(warmup_req(m, t, tc, eff, f"{eff}_k{kn}_t{int(use_t)}_{tc}"))
        write_jsonl(warm_path, w_info)
        print("WARM_S1", json.dumps({"conv_idx": conv_idx, "warms": w_info["warms"]}), flush=True)

        for a in arms:
            m = msgs_k0 if a["keep_n"] == 0 else msgs_k2
            seed = 10000 + 16 * conv_idx + S1_IDX[a["name"]]
            body = {
                "model": MODEL,
                "messages": m,
                "max_tokens": MAXTOK,
                "temperature": 0.3,
                "top_p": 0.95,
                "top_k": 20,
                "seed": seed,
                "reasoning_effort": a["effort"],
                "stream": True,
                "stream_options": {"include_usage": True},
            }
            if a["tools"]:
                body["tools"] = syn.TOOLS
                body["tool_choice"] = a["tc"]
            if a["budget"] > 0:
                body["thinking_budget"] = a["budget"]
            meta, rt, ct = post_stream(body)
            row = {"suite": "s1", "conv_idx": conv_idx, "arm": a["name"], "seed": seed,
                   "effort": a["effort"], "keep_n": a["keep_n"], "budget": a["budget"],
                   "tools": 8 if a["tools"] else 0, "tool_choice": a["tc"], **meta}
            write_jsonl(out_path, row)
            if meta["loop_r"] or meta["loop_c"]:
                write_jsonl(raw_path, {"suite": "s1", "conv_idx": conv_idx, "arm": a["name"], "seed": seed,
                                       "loop_r_period": meta["loop_r_period"], "loop_c_period": meta["loop_c_period"],
                                       "reasoning": rt, "content": ct})
            print("S1", json.dumps({k: row[k] for k in ("conv_idx", "arm", "finish", "prompt_tokens", "cached_tokens",
                                                        "reasoning_tokens", "content_tokens", "tool_calls", "valid_delivery",
                                                        "loop_r", "ttft_s", "wall_s")}), flush=True)

    with concurrent.futures.ThreadPoolExecutor(conc) as ex:
        list(ex.map(lambda cg: do_conv(cg[0], cg[1]), convs))


# ---------------------------------------------------------------------------
# Suite 2: Production-Aligned ~200K Prompt + 5 Tools x (low, medium, high)
# ---------------------------------------------------------------------------
S2_TOOLS = syn.TOOLS[:5]
S2_ARMS = [
    {"name": "P200_low",  "effort": "low"},
    {"name": "P200_med",  "effort": "medium"},
    {"name": "P200_high", "effort": "high"},
]
S2_IDX = {a["name"]: i for i, a in enumerate(S2_ARMS)}


def build_200k_conversation(conv_idx: int) -> list[dict]:
    rng = random.Random(12000 + conv_idx)
    salt = "".join(rng.choices(string.ascii_letters + string.digits, k=24))
    corpus = s5.generate_codebase_corpus(121000, salt)
    task_desc, synth_ask = syn.SYNTH_PROMPTS[conv_idx % len(syn.SYNTH_PROMPTS)]
    msgs: list[dict] = [
        {"role": "system", "content": (
            "You are a principal distributed systems engineer working inside an autonomous coding agent. "
            "Use the 5 provided tools only if more evidence is strictly needed; otherwise deliver a complete, grounded engineering analysis."
        )},
        {"role": "user", "content": f"Large repository snapshot [{salt}]:\n```python\n{corpus}\n```\n\nObjective: {task_desc}"},
    ]
    steps = [
        ("search_files", {"pattern": "synchronize_state|barrier|slot|evict", "glob": "*.py"}, '{"matches": ["coordinator.py:142", "cache.py:88"]}'),
        ("read_file", {"path": "src/coordinator.py", "start_line": 120, "end_line": 240}, '{"lines": "120: lock.acquire(); barrier.wait(slot); # may block while holding prefix_lock"}'),
        ("read_file", {"path": "src/cache.py", "start_line": 60, "end_line": 160}, '{"lines": "60: if spare_mib <= 0: evict_fifo(); # stale RAM entry shadows disk"}'),
        ("inspect_logs", {"service": "dsv41-rank0", "lines": 40}, '{"tail": ["WARN slot 3 resumed 192512/196608", "WARN retry burst 400ms", "MEM avail=3.12GiB"]}'),
        ("run_tests", {"suite": "stress_cluster", "filter": f"race_{conv_idx % 4}"}, '{"exit_code": 1, "output": "FAIL: 3/40 runs deadlocked or returned stale KV"}'),
    ]
    for s_idx, (tname, targs, tres) in enumerate(steps):
        cid = f"p200_{conv_idx}_{s_idx}"
        reas = (
            f"Step {s_idx + 1}: Checking {tname}({json.dumps(targs)}) on snapshot [{salt}] "
            f"to isolate lock ordering and KV eviction timing before proposing the final patch."
        )
        msgs.append({
            "role": "assistant",
            "content": "",
            "reasoning_content": reas,
            "tool_calls": [{"id": cid, "type": "function", "function": {"name": tname, "arguments": json.dumps(targs)}}],
        })
        msgs.append({"role": "tool", "tool_call_id": cid, "content": tres})
    msgs.append({"role": "user", "content": synth_ask})
    return syn.apply_keep_n(msgs, 2)


def run_s2(out_dir: str, n_convs: int, conc: int):
    out_path = os.path.join(out_dir, "results_s2.jsonl")
    warm_path = os.path.join(out_dir, "warmup_s2.jsonl")
    raw_path = os.path.join(out_dir, "loops_raw.jsonl")
    done = set()
    if os.path.exists(out_path):
        done = {(r["conv_idx"], r["arm"]) for r in map(json.loads, open(out_path)) if r.get("status") == 200 and not r.get("err")}

    rng = random.Random(20261115)
    convs = []
    for c in range(n_convs):
        g = [a for a in S2_ARMS if (c, a["name"]) not in done]
        rng.shuffle(g)
        if g:
            convs.append((c, g))
    print(f"[S2] convs={len(convs)} jobs={sum(len(g) for _, g in convs)} conc={conc} out={out_path}", flush=True)

    def do_conv(conv_idx: int, arms: list[dict]):
        msgs = build_200k_conversation(conv_idx)
        mem_pre = mem_avail_gib()
        w = warmup_req(msgs, S2_TOOLS, "auto", "medium", "p200_med")
        w["conv_idx"] = conv_idx
        w["mem_before_gib"] = mem_pre
        w["mem_after_gib"] = mem_avail_gib()
        write_jsonl(warm_path, w)
        print("WARM_S2", json.dumps(w), flush=True)

        for a in arms:
            seed = 12000 + 16 * conv_idx + S2_IDX[a["name"]]
            body = {
                "model": MODEL,
                "messages": msgs,
                "tools": S2_TOOLS,
                "tool_choice": "auto",
                "max_tokens": MAXTOK,
                "temperature": 0.3,
                "top_p": 0.95,
                "top_k": 20,
                "seed": seed,
                "reasoning_effort": a["effort"],
                "stream": True,
                "stream_options": {"include_usage": True},
            }
            m0 = mem_avail_gib()
            meta, rt, ct = post_stream(body)
            m1 = mem_avail_gib()
            row = {"suite": "s2", "conv_idx": conv_idx, "arm": a["name"], "seed": seed,
                   "effort": a["effort"], "tools": 5, "mem_before_gib": m0, "mem_after_gib": m1, **meta}
            write_jsonl(out_path, row)
            if meta["loop_r"] or meta["loop_c"]:
                write_jsonl(raw_path, {"suite": "s2", "conv_idx": conv_idx, "arm": a["name"], "seed": seed,
                                       "loop_r_period": meta["loop_r_period"], "loop_c_period": meta["loop_c_period"],
                                       "reasoning": rt, "content": ct})
            print("S2", json.dumps({k: row[k] for k in ("conv_idx", "arm", "finish", "prompt_tokens", "cached_tokens",
                                                        "reasoning_tokens", "content_tokens", "tool_calls", "loop_r",
                                                        "ttft_s", "wall_s", "mem_after_gib")}), flush=True)

    with concurrent.futures.ThreadPoolExecutor(conc) as ex:
        list(ex.map(lambda cg: do_conv(cg[0], cg[1]), convs))


# ---------------------------------------------------------------------------
# Suite 3a: OMP Short-Task Control (max_tokens=120, tools=0, low vs none)
# ---------------------------------------------------------------------------
OMP_PROMPTS = [
    "Summarize this coding session in a concise 5-word title: 'Fixed RDMA ring buffer deadlock when slot 3 resumed partial KV prefix on rank1'.",
    "Generate a short 4-to-7 word git branch title for: 'Add priority-aware work stealing on slot 7 in fastfail proxy'.",
    "Produce a concise session title (<=8 words) for: 'Diagnosed 33 ok|length failures caused by reasoning_effort=low with max_tokens=120'.",
    "Create a brief title for: 'Backport PR #138 long-loop detector to DeepSeek-V4.1 TP2 Zig engine'.",
    "Give a 5-word task title for: 'Benchmark 200K prompt prefill and memory headroom across low, medium, and high effort'.",
]


def run_s3a(out_dir: str, n_items: int = 10):
    out_path = os.path.join(out_dir, "results_s3a.jsonl")
    done = set()
    if os.path.exists(out_path):
        done = {(r["idx"], r["arm"]) for r in map(json.loads, open(out_path)) if r.get("status") == 200 and not r.get("err")}
    for i in range(n_items):
        p = OMP_PROMPTS[i % len(OMP_PROMPTS)]
        for arm_name, effort in [("OMP120_low", "low"), ("OMP120_none", "none")]:
            if (i, arm_name) in done:
                continue
            body = {
                "model": MODEL,
                "messages": [
                    {"role": "system", "content": "Generate a concise title only. Do not explain."},
                    {"role": "user", "content": p},
                ],
                "max_tokens": 120,
                "temperature": 0.3,
                "seed": 14000 + 4 * i + (0 if effort == "low" else 1),
                "reasoning_effort": effort,
                "stream": True,
                "stream_options": {"include_usage": True},
            }
            meta, rt, ct = post_stream(body, timeout=180)
            row = {"suite": "s3a", "idx": i, "arm": arm_name, "effort": effort, "content_full": ct, **meta}
            write_jsonl(out_path, row)
            print("S3A", json.dumps({"idx": i, "arm": arm_name, "finish": meta["finish"],
                                     "reas_tok": meta["reasoning_tokens"], "cont_tok": meta["content_tokens"],
                                     "c_chars": meta["c_chars"], "content": ct[:80]}), flush=True)


# ---------------------------------------------------------------------------
# Suite 3b: Loop Capture on conv_idx=11 (saves full text to loops_raw.jsonl)
# ---------------------------------------------------------------------------
def run_s3b(out_dir: str, reps: int = 4):
    out_path = os.path.join(out_dir, "results_s3b.jsonl")
    raw_path = os.path.join(out_dir, "loops_raw.jsonl")
    msgs = syn.apply_keep_n(syn.build_conversation(11), 2)
    warmup_req(msgs, syn.TOOLS, "auto", "max", "conv11_max")
    done = set()
    if os.path.exists(out_path):
        done = {(r["rep"], r["arm"]) for r in map(json.loads, open(out_path)) if r.get("status") == 200 and not r.get("err")}
    arms = [
        ("E_max_rep", 0),
        ("EB16_rep", 16384),
    ]
    for rep in range(reps):
        for arm_name, budget in arms:
            if (rep, arm_name) in done:
                continue
            seed = 8178 if (rep == 0 and budget == 0) else (8179 if (rep == 0 and budget == 16384) else 15000 + 8 * rep + (1 if budget else 0))
            body = {
                "model": MODEL,
                "messages": msgs,
                "tools": syn.TOOLS,
                "tool_choice": "auto",
                "max_tokens": MAXTOK,
                "temperature": 0.3,
                "top_p": 0.95,
                "top_k": 20,
                "seed": seed,
                "reasoning_effort": "max",
                "stream": True,
                "stream_options": {"include_usage": True},
            }
            if budget > 0:
                body["thinking_budget"] = budget
            meta, rt, ct = post_stream(body)
            row = {"suite": "s3b", "conv_idx": 11, "rep": rep, "arm": arm_name, "seed": seed, "budget": budget, **meta}
            write_jsonl(out_path, row)
            # Save full reasoning + content whenever loop_r/c OR for first rep of each arm
            if meta["loop_r"] or meta["loop_c"] or rep == 0:
                write_jsonl(raw_path, {"suite": "s3b", "conv_idx": 11, "rep": rep, "arm": arm_name, "seed": seed,
                                       "loop_r": meta["loop_r"], "loop_r_period": meta["loop_r_period"],
                                       "reasoning": rt, "content": ct})
            print("S3B", json.dumps({"rep": rep, "arm": arm_name, "seed": seed, "finish": meta["finish"],
                                     "reas_tok": meta["reasoning_tokens"], "loop_r": meta["loop_r"],
                                     "loop_r_period": meta["loop_r_period"], "engine_loop": meta["engine_loop"],
                                     "wall_s": meta["wall_s"]}), flush=True)


def summarize(path: str):
    rows = [json.loads(l) for l in open(path)]
    arms = []
    for r in rows:
        if r["arm"] not in arms:
            arms.append(r["arm"])
    for name in arms:
        rs = [r for r in rows if r["arm"] == name]
        ok = [r for r in rs if r.get("status") == 200 and not r.get("err")]
        fin = collections.Counter(r.get("finish") for r in ok)
        reass = sorted(r["reasoning_tokens"] or 0 for r in ok)
        conts = sorted(r["content_tokens"] or 0 for r in ok)
        ttfts = sorted(r["ttft_s"] for r in ok if r.get("ttft_s") is not None)
        walls = sorted(r["wall_s"] for r in ok if r.get("wall_s") is not None)
        caches = [r["cached_tokens"] / max(1, r["prompt_tokens"]) for r in ok if r.get("prompt_tokens")]
        valid = sum(1 for r in ok if r.get("valid_delivery"))
        print(
            f"{name:14s} ok={len(ok):2d}/{len(rs):2d} valid={valid:2d} fin={dict(fin)} "
            f"tc={sum(bool(r.get('tool_calls')) for r in ok):2d} dsml={sum(bool(r.get('dsml_in_content')) for r in ok):2d} "
            f"loop_r={sum(bool(r.get('loop_r')) for r in ok):2d} | "
            f"reas_p50={reass[len(reass)//2] if reass else None} cont_p50={conts[len(conts)//2] if conts else None} | "
            f"cache_med={round(statistics.median(caches),4) if caches else None} "
            f"ttft_p50={ttfts[len(ttfts)//2] if ttfts else None} ttft_p90={ttfts[int(0.9*(len(ttfts)-1))] if ttfts else None} "
            f"wall_p50={walls[len(walls)//2] if walls else None}"
        )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--suite", choices=["s1", "s2", "s3a", "s3b", "all"], default="all")
    ap.add_argument("--n-s1", type=int, default=8)
    ap.add_argument("--n-s2", type=int, default=8)
    ap.add_argument("--conc-s1", type=int, default=3)
    ap.add_argument("--conc-s2", type=int, default=2)
    ap.add_argument("--summary", help="Summarize a jsonl file")
    ap.add_argument("out_dir", nargs="?")
    args = ap.parse_args()
    if args.summary:
        summarize(args.summary)
        return
    if not args.out_dir:
        ap.error("out_dir is required unless --summary is set")
    os.makedirs(args.out_dir, exist_ok=True)
    if args.suite in ("s3a", "all"):
        run_s3a(args.out_dir, n_items=10)
        summarize(os.path.join(args.out_dir, "results_s3a.jsonl"))
    if args.suite in ("s1", "all"):
        run_s1(args.out_dir, n_convs=args.n_s1, conc=args.conc_s1)
        summarize(os.path.join(args.out_dir, "results_s1.jsonl"))
    if args.suite in ("s2", "all"):
        run_s2(args.out_dir, n_convs=args.n_s2, conc=args.conc_s2)
        summarize(os.path.join(args.out_dir, "results_s2.jsonl"))
    if args.suite in ("s3b", "all"):
        run_s3b(args.out_dir, reps=4)
        summarize(os.path.join(args.out_dir, "results_s3b.jsonl"))


if __name__ == "__main__":
    main()
