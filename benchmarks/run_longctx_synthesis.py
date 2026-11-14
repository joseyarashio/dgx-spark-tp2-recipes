#!/usr/bin/env python3
"""Phase 2 (v2) Long-Thinking Synthesis A/B WITH real tools attached (~85K prompt tokens).

All 6 prior tool turns (with verbose reasoning_content) are provided and the final user turn forbids
further tool calls and asks for an exhaustive synthesis, while `tools` + `tool_choice="auto"` stay
attached (matching real final-synthesis agent turns).

v2 fixes after the Phase 1 dual audit (Fable 5.2 + GPT-6 Astra) and aborted v1 Phase 2 run:
  1. Distinct seed per (conv, arm): seed = 8000 + 16*conv_idx + arm_index. v1 used one seed per
     conversation, so A1/A2/B16 produced byte-identical outputs and the A/A arm measured nothing but
     queueing noise. Now A2_base vs A1_base is a true sampling-noise floor, and every arm carries the
     same seed-noise so comparisons are fair.
  2. Cache-confound removal: each conversation is pre-warmed once for effort=high AND effort=max
     (max_tokens=1) before its timed arms run, so E_max is no longer the only cold-prefill arm
     (v1 E_max cache_hit=0.0 -> +41s TTFT that was prefill, not thinking).
  3. Thinking-budget arms that can actually bind: v1 B16 (effort=high, 16K) never reached the cap
     (high thinks ~8K). v2 tests EB16_max_tb16k (effort=max + 16384, where max thinks 16K-28K and hit
     length 2/3 in v1) and B8_tb8k (effort=high + 8192).
  4. Per-conversation worker: one worker warms then runs all arms for a conversation in random order;
     CONC conversations run in parallel. K1_kn1 dropped (inconclusive in Phase 1, budget for time).

Arms:
  A1_base        : effort=high, keep_n=2, budget=0     (production baseline)
  A2_base        : effort=high, keep_n=2, budget=0     (A/A sampling-noise floor, different seed)
  E_max          : effort=max,  keep_n=2, budget=0
  EB16_max_tb16k : effort=max,  keep_n=2, budget=16384
  K0_kn0         : effort=high, keep_n=0, budget=0     (strip all prior reasoning client-side)
  B8_tb8k        : effort=high, keep_n=2, budget=8192

usage: N=16 CONC=3 run_longctx_synthesis.py OUT.jsonl
       run_longctx_synthesis.py --summary OUT.jsonl
"""
import collections, concurrent.futures, contextlib, io, json, os, random, re, statistics, string, sys, threading, time, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
with contextlib.redirect_stdout(io.StringIO()):
    import run_5hour_stress_experiment as s5

API = os.environ.get("API", "http://127.0.0.1:8889/v1/chat/completions")
MODEL = "DeepSeek-V4.1-Flash-1017-TF"
N = int(os.environ.get("N", "16"))
CONC = int(os.environ.get("CONC", "3"))
MAXTOK = int(os.environ.get("MAXTOK", "32768"))
LOOP_RE = re.compile(r"(.{20,600}?)\1{4,}", re.S)
lock = threading.Lock()

TOOLS = [
    {"type": "function", "function": {"name": "read_file", "description": "Read lines from a source or config file.",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "start_line": {"type": "integer"}, "end_line": {"type": "integer"}}, "required": ["path"]}}},
    {"type": "function", "function": {"name": "search_files", "description": "Regex search across repository files.",
        "parameters": {"type": "object", "properties": {"pattern": {"type": "string"}, "glob": {"type": "string"}}, "required": ["pattern"]}}},
    {"type": "function", "function": {"name": "patch_file", "description": "Apply a targeted replacement in a file.",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "old_text": {"type": "string"}, "new_text": {"type": "string"}}, "required": ["path", "old_text", "new_text"]}}},
    {"type": "function", "function": {"name": "run_tests", "description": "Execute a test target and return stdout/exit code.",
        "parameters": {"type": "object", "properties": {"suite": {"type": "string"}, "filter": {"type": "string"}}, "required": ["suite"]}}},
    {"type": "function", "function": {"name": "inspect_logs", "description": "Fetch recent log lines for a service.",
        "parameters": {"type": "object", "properties": {"service": {"type": "string"}, "lines": {"type": "integer"}}, "required": ["service"]}}},
    {"type": "function", "function": {"name": "check_cluster_health", "description": "Query node health, memory, and RDMA counters.",
        "parameters": {"type": "object", "properties": {"node": {"type": "string", "enum": ["rank0", "rank1", "both"]}}, "required": ["node"]}}},
    {"type": "function", "function": {"name": "git_diff", "description": "Show current uncommitted diff.",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "list_directory", "description": "List files in a directory.",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
]
DECLARED_TOOLS = {t["function"]["name"] for t in TOOLS}

ARMS = [
    {"name": "A1_base",        "effort": "high", "keep_n": 2, "budget": 0},
    {"name": "A2_base",        "effort": "high", "keep_n": 2, "budget": 0},
    {"name": "E_max",          "effort": "max",  "keep_n": 2, "budget": 0},
    {"name": "EB16_max_tb16k", "effort": "max",  "keep_n": 2, "budget": 16384},
    {"name": "K0_kn0",         "effort": "high", "keep_n": 0, "budget": 0},
    {"name": "B8_tb8k",        "effort": "high", "keep_n": 2, "budget": 8192},
]
ARM_INDEX = {a["name"]: i for i, a in enumerate(ARMS)}

SYNTH_PROMPTS = [
    ("Audit every coordinator and metrics module in the workspace snapshot for subtle concurrency, ABA, and cache-invalidation bugs.",
     "All tools have already run. Do NOT call any more tools. In your final response, write: (1) an exhaustive class-by-class bug audit citing exact line numbers and interleaving schedules for every race, (2) a unified patch fixing all of them without introducing deadlocks, and (3) formal state invariants proving safety under arbitrary crash/retry."),
    ("Reconcile the conflicting throughput, memory, and prefix-reuse numbers across turns 1-6 and design a scale-invariant admission and eviction algorithm.",
     "No further tool calls are needed or permitted. Provide a rigorous first-principles analysis deriving exact byte formulas, counterexamples for why the current thresholds oscillate, the complete replacement Python/Zig pseudocode, and an edge-case verification table covering 1..64 concurrent slots."),
    ("Analyze why the cluster stalls at high context pressure despite healthy HTTP/200 health checks and design an atomic two-phase recovery protocol.",
     "Stop calling tools—you already have all logs and code above. Produce a complete state-machine transition matrix, prove liveness and absence of split-brain across Rank 0 and Rank 1 under partial packet loss, and give the minimal diff."),
    ("Design a zero-regression refactoring of the entire snapshot that decouples state tracking from request scheduling without breaking any public invariant.",
     "Do NOT invoke any tools; synthesize everything directly. Enumerate every coupling edge in the snapshot, derive the dependency DAG, write the complete refactored module interfaces, and prove backward compatibility across all 4 failure modes."),
]


def build_conversation(conv_idx: int) -> list[dict]:
    rng = random.Random(9000 + conv_idx)
    salt = "".join(rng.choices(string.ascii_letters + string.digits, k=24))
    corpus = s5.generate_codebase_corpus(48000, salt)
    task_desc, synth_ask = SYNTH_PROMPTS[conv_idx % len(SYNTH_PROMPTS)]
    msgs: list[dict] = [
        {"role": "system", "content": (
            "You are a principal distributed systems engineer completing the final synthesis turn of an autonomous audit. "
            "Follow tool instructions strictly: when the user states all evidence is collected and forbids further tool calls, "
            "reason thoroughly and deliver the complete answer directly without calling tools."
        )},
        {"role": "user", "content": f"Workspace snapshot [{salt}]:\n```python\n{corpus}\n```\n\nObjective: {task_desc}"},
    ]
    steps = [
        ("list_directory", {"path": "src/"}, '{"entries": ["coordinator.py", "cache.py", "metrics.py", "retry.py", "barrier.py", "tests/"]}'),
        ("search_files", {"pattern": "synchronize_state|barrier|slot|evict", "glob": "*.py"}, '{"matches": ["coordinator.py:142", "coordinator.py:218", "cache.py:88", "barrier.py:44"]}'),
        ("read_file", {"path": "src/coordinator.py", "start_line": 120, "end_line": 240}, '{"lines": "120: lock.acquire(); barrier.wait(slot); # may block while holding prefix_lock; retry mutates epoch without fencing"}'),
        ("read_file", {"path": "src/cache.py", "start_line": 60, "end_line": 160}, '{"lines": "60: if spare_mib <= 0: evict_fifo(); # shares lockless counter with prefetch; stale RAM entry shadows disk"}'),
        ("check_cluster_health", {"node": "both"}, '{"rank0": {"mem_avail_gib": 3.05, "gpu_util": 97, "power_w": 16.2}, "rank1": {"mem_avail_gib": 4.10, "gpu_util": 0, "last_err": "BadSlot"}}'),
        ("run_tests", {"suite": "stress_cluster", "filter": f"race_{conv_idx % 4}"}, '{"exit_code": 1, "output": "FAIL: 3/40 runs deadlocked or returned stale KV; retry storm 4821 reqs in 1.8s; mem_avail dipped to 2.61 GiB"}'),
    ]
    for s_idx, (tname, targs, tres) in enumerate(steps):
        cid = f"synth_{conv_idx}_{s_idx}"
        # Deliberately multi-clause, self-questioning reasoning_content to test keep-last-n-reasoning mimicry
        reas = (
            f"Wait — let me double check step {s_idx + 1} carefully. We want to examine {tname} with {json.dumps(targs)}. "
            f"Hold on: earlier in snapshot [{salt}], I noticed metrics and state synchronization might share an unguarded transition, "
            f"or wait, is it the eviction counter or the barrier epoch? Let me verify before concluding: first check {tname}, "
            f"then cross-check against coordinator.py and cache.py, wait—also check if rank1 BadSlot could come from slot mismatch, "
            f"or from stale prefix_key. Better run {tname} first and re-verify every assumption carefully."
        )
        msgs.append({
            "role": "assistant",
            "content": "",
            "reasoning_content": reas,
            "tool_calls": [{"id": cid, "type": "function", "function": {"name": tname, "arguments": json.dumps(targs)}}],
        })
        msgs.append({"role": "tool", "tool_call_id": cid, "content": tres})
    msgs.append({"role": "user", "content": synth_ask})
    return msgs


def apply_keep_n(messages: list[dict], keep_n: int) -> list[dict]:
    reas_idxs = [idx for idx, m in enumerate(messages) if m.get("reasoning_content")]
    if len(reas_idxs) <= keep_n:
        return messages
    drop_set = set(reas_idxs[: len(reas_idxs) - keep_n])
    out = []
    for idx, m in enumerate(messages):
        if idx in drop_set:
            mc = dict(m)
            mc.pop("reasoning_content", None)
            out.append(mc)
        else:
            out.append(m)
    return out


def run_one(conv_idx: int, arm: dict, out_path: str):
    msgs = apply_keep_n(build_conversation(conv_idx), arm["keep_n"])
    body = {
        "model": MODEL,
        "messages": msgs,
        "tools": TOOLS,
        "tool_choice": "auto",
        "max_tokens": MAXTOK,
        "temperature": 0.3,
        "top_p": 0.95,
        "top_k": 20,
        "seed": 8000 + 16 * conv_idx + ARM_INDEX[arm["name"]],
        "reasoning_effort": arm["effort"],
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    if arm["budget"] > 0:
        body["thinking_budget"] = arm["budget"]
    req = urllib.request.Request(API, json.dumps(body, ensure_ascii=False).encode("utf-8"),
                                 {"Content-Type": "application/json", "X-Priority": "2"})
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
            with urllib.request.urlopen(req, timeout=1800) as resp:
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
    undeclared_tc = [n for n in tc_names if n not in DECLARED_TOOLS]
    dsml_in_content = ("DSML" in ct) or ("<｜DSML｜" in ct) or ("<tool_call>" in ct)
    ptd = usage.get("prompt_tokens_details") or {}
    ctd = usage.get("completion_tokens_details") or {}
    comp = usage.get("completion_tokens")
    reas = ctd.get("reasoning_tokens")
    row = {
        "conv_idx": conv_idx,
        "arm": arm["name"],
        "seed": body["seed"],
        "status": status,
        "err": err,
        "finish": fin,
        "prompt_tokens": usage.get("prompt_tokens"),
        "cached_tokens": ptd.get("cached_tokens"),
        "completion_tokens": comp,
        "reasoning_tokens": reas,
        "content_tokens": (max(0, comp - reas) if comp is not None and reas is not None else None),
        "r_chars": len(rt),
        "c_chars": len(ct),
        "tool_calls": tc_names,
        "undeclared_tc": undeclared_tc,
        "dsml_in_content": dsml_in_content,
        "loop_r": bool(m_r),
        "loop_r_period": len(m_r.group(1)) if m_r else None,
        "loop_c": bool(m_c),
        "loop_c_period": len(m_c.group(1)) if m_c else None,
        "engine_loop": loop_meta,
        "ttft_s": round(ttft, 3) if ttft else None,
        "wall_s": round(time.perf_counter() - t0, 2),
    }
    with lock, open(out_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(json.dumps({k: row[k] for k in ("conv_idx", "arm", "finish", "prompt_tokens", "cached_tokens",
                                           "reasoning_tokens", "content_tokens", "tool_calls", "dsml_in_content",
                                           "loop_r", "loop_c", "wall_s")}), flush=True)
    return row


def warmup(conv_idx: int, out_path: str):
    msgs = build_conversation(conv_idx)
    info = {"conv_idx": conv_idx}
    for effort in ("high", "max"):
        body = {"model": MODEL, "messages": msgs, "tools": TOOLS, "tool_choice": "auto",
                "max_tokens": 1, "temperature": 0.3, "reasoning_effort": effort, "stream": False}
        req = urllib.request.Request(API, json.dumps(body, ensure_ascii=False).encode("utf-8"),
                                     {"Content-Type": "application/json", "X-Priority": "2"})
        t0 = time.perf_counter()
        res = None
        for attempt in range(4):
            try:
                r = json.load(urllib.request.urlopen(req, timeout=1800))
                u = r.get("usage") or {}
                res = {"prompt": u.get("prompt_tokens"), "cached": (u.get("prompt_tokens_details") or {}).get("cached_tokens"),
                       "s": round(time.perf_counter() - t0, 1)}
                break
            except Exception as e:
                res = {"err": repr(e)[:120]}
                time.sleep(3 + 3 * attempt)
        info[effort] = res
    with lock, open(out_path + ".warmup.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(info) + "\n")
    print("WARMUP", json.dumps(info), flush=True)


def run_conv(conv_idx: int, arms: list, out_path: str):
    warmup(conv_idx, out_path)
    for a in arms:
        run_one(conv_idx, a, out_path)


def summarize(path: str):
    rows = [json.loads(l) for l in open(path)]
    arms = [a["name"] for a in ARMS if any(r["arm"] == a["name"] for r in rows)]
    for name in arms:
        rs = [r for r in rows if r["arm"] == name]
        ok = [r for r in rs if r["status"] == 200 and not r["err"]]
        comps = sorted(r["completion_tokens"] or 0 for r in ok)
        reass = sorted(r["reasoning_tokens"] or 0 for r in ok)
        ttfts = sorted(r["ttft_s"] for r in ok if r["ttft_s"] is not None)
        caches = [r["cached_tokens"] / max(1, r["prompt_tokens"]) for r in ok if r.get("prompt_tokens")]
        print(
            f"{name:10s} ok {len(ok):2d}/{len(rs):2d} | fin_len {sum(r['finish']=='length' for r in ok):2d} "
            f"empty_c {sum(r['c_chars']==0 and not r['tool_calls'] for r in ok):2d} | "
            f"loop_r {sum(r['loop_r'] for r in ok):2d} loop_c {sum(r['loop_c'] for r in ok):2d} eng_loop {sum(bool(r['engine_loop']) for r in ok):2d} | "
            f"ge4k {sum((r['completion_tokens'] or 0)>=4000 for r in ok):2d} ge8k {sum((r['completion_tokens'] or 0)>=8000 for r in ok):2d} | "
            f"tc {sum(bool(r['tool_calls']) for r in ok):2d} dsml_txt {sum(r['dsml_in_content'] for r in ok):2d} bad_tc {sum(bool(r['undeclared_tc']) for r in ok):2d} | "
            f"comp p50 {comps[len(comps)//2] if comps else None} p90 {comps[int(.9*(len(comps)-1))] if comps else None} max {comps[-1] if comps else None} | "
            f"reas p50 {reass[len(reass)//2] if reass else None} | cache_med {round(statistics.median(caches),3) if caches else None} | "
            f"ttft_p50 {ttfts[len(ttfts)//2] if ttfts else None}"
        )


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--summary":
        return summarize(sys.argv[2])
    out_path = sys.argv[1]
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    done = set()
    if os.path.exists(out_path):
        done = {(r["conv_idx"], r["arm"]) for r in map(json.loads, open(out_path)) if r.get("status") == 200 and not r.get("err")}
    rng = random.Random(42)
    convs = []
    for c in range(N):
        g = [a for a in ARMS if (c, a["name"]) not in done]
        rng.shuffle(g)
        if g:
            convs.append((c, g))
    print(f"convs={len(convs)} jobs={sum(len(g) for _, g in convs)} N={N} conc={CONC} out={out_path}", flush=True)
    with concurrent.futures.ThreadPoolExecutor(CONC) as ex:
        list(ex.map(lambda cg: run_conv(cg[0], cg[1], out_path), convs))
    summarize(out_path)


if __name__ == "__main__":
    main()
