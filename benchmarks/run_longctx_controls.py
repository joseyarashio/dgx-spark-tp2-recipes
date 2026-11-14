#!/usr/bin/env python3
"""Controlled long-context, real-tools A/B over key unexplored variables (~82K prompt tokens).

Tests 6 interleaved arms per conversation (randomized order per conv_idx, same seed=7000+conv_idx,
stream=True, LOOP_CUT=0 so natural lengths & completions are observed cleanly):
  A1_base   : effort=high, keep_n=2, budget=0   (production baseline rep 1)
  A2_base   : effort=high, keep_n=2, budget=0   (built-in A/A noise floor rep 2)
  E_max     : effort=max,  keep_n=2, budget=0   (effort high vs max)
  K1_kn1    : effort=high, keep_n=1, budget=0   (strip older reasoning, keep last 1)
  K0_kn0    : effort=high, keep_n=0, budget=0   (strip all prior reasoning)
  B16_tb16k : effort=high, keep_n=2, budget=16384 (thinking_budget WITH real tools)

Supports resume by skipping completed (conv_idx, arm) pairs.
usage: N=36 CONC=4 run_longctx_controls.py OUT.jsonl
       run_longctx_controls.py --summary OUT.jsonl
"""
import collections, concurrent.futures, contextlib, io, json, os, random, re, statistics, string, sys, threading, time, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
with contextlib.redirect_stdout(io.StringIO()):
    import run_5hour_stress_experiment as s5

API = os.environ.get("API", "http://127.0.0.1:8889/v1/chat/completions")
MODEL = "DeepSeek-V4.1-Flash-1017-TF"
N = int(os.environ.get("N", "36"))
CONC = int(os.environ.get("CONC", "4"))
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
    {"name": "A1_base",   "effort": "high", "keep_n": 2, "budget": 0},
    {"name": "A2_base",   "effort": "high", "keep_n": 2, "budget": 0},
    {"name": "E_max",     "effort": "max",  "keep_n": 2, "budget": 0},
    {"name": "K1_kn1",    "effort": "high", "keep_n": 1, "budget": 0},
    {"name": "K0_kn0",    "effort": "high", "keep_n": 0, "budget": 0},
    {"name": "B16_tb16k", "effort": "high", "keep_n": 2, "budget": 16384},
]

TASKS = [
    ("Diagnose why intermittent RDMA sync stalls happen only under mixed prefill/decode batches and propose the safest next verification step.",
     "FAIL test_tp2_sync: timeout after 30.0s waiting on rank1 barrier when slot_id=3 resumed partial prefix; rank0 GPU-Util=97% power=16.2W; rank1 GPU-Util=0%."),
    ("Investigate why multi-turn KV cache hit rate drops after turn 4 despite stable prefix bytes, and decide whether to inspect another file or give the fix.",
     "CACHE_METRICS: turn1=0% turn2=94% turn3=96% turn4=95% turn5=12% turn6=14%; evicted=0; kept_states=142; mem_spare_mib=0; note: turn5 added tool_choice='auto'."),
    ("Audit the coordinator retry and backoff loop for cascade risks under transient 502/429 responses.",
     "STRESS_RESULT: 4821 requests in 1.8s after upstream 502 spike; worker_threads=8; backoff_only_on_429=True; queue_waiters=0; client_timeout_ms=60000."),
    ("Determine why a strict JSON config validator rejects a valid schema update on node2 while node1 accepts it.",
     "DIFF_OUT: node1 sha=de40bcdd ok; node2 sha=d33e73ff mismatch on engram_map; restart_log=skipped check because SSH timed out after 2s."),
]


def build_conversation(conv_idx: int) -> list[dict]:
    rng = random.Random(3000 + conv_idx)
    salt = "".join(rng.choices(string.ascii_letters + string.digits, k=24))
    # ~49K generated codebase corpus -> ~85K-92K prompt tokens (inside the >=80K zone)
    corpus = s5.generate_codebase_corpus(49000, salt)
    task_desc, final_err = TASKS[conv_idx % len(TASKS)]
    is_synth = (conv_idx % 2 == 0)
    tail_prompt = (
        f"Task: {task_desc}\nAll initial diagnostics have been collected in the turns below. "
        "Decide if any single check is still missing or synthesize the complete root cause, exact patch, and proof."
        if is_synth else f"Task: {task_desc}\nStart by inspecting the relevant components."
    )
    msgs: list[dict] = [
        {"role": "system", "content": (
            "You are a principal distributed systems engineer working inside an autonomous coding agent. "
            "Use the provided tools when you need to verify files, logs, or tests. "
            "When you have enough evidence, provide a concise, grounded diagnosis and next action without inventing unverified paths."
        )},
        {"role": "user", "content": f"Workspace snapshot [{salt}]:\n```python\n{corpus}\n```\n\n{tail_prompt}"},
    ]
    # Build 6 multi-turn tool calls WITH realistic reasoning_content on each assistant turn
    steps = [
        ("list_directory", {"path": "src/"}, '{"entries": ["coordinator.py", "cache.py", "metrics.py", "retry.py", "tests/"]}'),
        ("search_files", {"pattern": "synchronize_state|barrier|slot", "glob": "*.py"}, '{"matches": ["src/coordinator.py:142", "src/coordinator.py:218", "src/cache.py:88"]}'),
        ("read_file", {"path": "src/coordinator.py", "start_line": 120, "end_line": 240}, '{"lines": "120: def synchronize_state(slot_id, prefix_len): ... # lock held across barrier"}'),
        ("read_file", {"path": "src/cache.py", "start_line": 60, "end_line": 140}, '{"lines": "60: def lookup_or_evict(key, spare_mib): ... # evict FIFO when spare_mib == 0"}'),
        ("check_cluster_health" if is_synth else "inspect_logs",
         {"node": "both"} if is_synth else {"service": "tp2-worker", "lines": 30},
         '{"rank0": {"mem_avail_gib": 3.4, "gpu_util": 97}, "rank1": {"mem_avail_gib": 4.1, "gpu_util": 0}}' if is_synth
         else '{"tail": ["WARN slot 3 resumed 84992/88064", "INFO rank1 heartbeat ok", "WARN retry burst 400ms"]}'),
        ("run_tests", {"suite": "unit_cluster", "filter": f"case_{conv_idx % 4}"}, f'{{"exit_code": 1, "output": "{final_err}"}}'),
    ]
    for s_idx, (tname, targs, tres) in enumerate(steps):
        cid = f"call_{conv_idx}_{s_idx}"
        reas = (
            f"Step {s_idx + 1}: Given the task '{task_desc[:70]}', I should check {tname}({json.dumps(targs)}) "
            f"to narrow down whether the fault originates in state synchronization, cache eviction, or retry handling. "
            f"Looking at the repository snapshot [{salt}], prior modules showed coupling between slot state and metrics; let's inspect the exact output first before drawing conclusions."
        )
        msgs.append({
            "role": "assistant",
            "content": "",
            "reasoning_content": reas,
            "tool_calls": [{"id": cid, "type": "function", "function": {"name": tname, "arguments": json.dumps(targs)}}],
        })
        msgs.append({"role": "tool", "tool_call_id": cid, "content": tres})
    return msgs


def apply_keep_n(messages, keep_n: int):
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
        "seed": 7000 + conv_idx,
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
    jobs = []
    for c in range(N):
        g = [(c, a) for a in ARMS if (c, a["name"]) not in done]
        rng.shuffle(g)
        jobs.extend(g)
    print(f"jobs={len(jobs)} N={N} conc={CONC} out={out_path}", flush=True)
    with concurrent.futures.ThreadPoolExecutor(CONC) as ex:
        list(ex.map(lambda j: run_one(j[0], j[1], out_path), jobs))
    summarize(out_path)


if __name__ == "__main__":
    main()
