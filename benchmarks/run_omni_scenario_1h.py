#!/usr/bin/env python3
"""OmniScenario-1h runner (plan: benchmarks/plans/omni_scenario_1h_plan_v1.md).

Blocks: preflight singles (idle) -> standard front (run_omni_eval standard, run_full_eval) -> thinking matrix M1-M6 ->
main load (N=7 closed loop, P1/P2, real-traffic shapes) with timed events -> drain -> final checks.
Every request row goes to <out>/rows.jsonl as it finishes; telemetry to <out>/telemetry.jsonl; events to events.jsonl.
Kill switch: Node1 MemAvailable < ABORT_N1_GIB, Node2 < ABORT_N2_GIB, swap growth > 512 MiB, BadSlot / follow_refused /
panic / OOM in either rank log, engine /health not ok for 5 s -> stop admissions, close in-flight test streams, keep logs.

usage: run_omni_scenario_1h.py OUT_DIR [--pilot]
"""
import argparse, base64, json, os, random, re, string, struct, subprocess, sys, threading, time, zlib
from concurrent.futures import ThreadPoolExecutor
import httpx

HERE = os.path.dirname(os.path.abspath(__file__))
P88, P89 = "http://127.0.0.1:8888", "http://127.0.0.1:8889"
MODEL = "DeepSeek-V4.1-Flash-1017-TF"
NODE2 = "192.168.10.149"
AUDIT = os.path.expanduser("~/.cache/spark-proxy-audit/completions.jsonl")
DSML = ("<｜DSML｜", "</｜DSML｜", "<tool_call>")
# Node1 runs at ~3.2-3.6 GiB MemAvailable in steady state with --prompt-cache-gib 2.5 (the reviewers' 4/6 GiB lines
# would abort an idle healthy cluster); the proxy prefill ladder bottoms out at 2.65 GiB.
ABORT_N1_GIB, ABORT_N2_GIB, GATE_N1_GIB = 2.5, 3.0, 2.8
SWAP_GROWTH_ABORT_MIB = 512

ap = argparse.ArgumentParser()
ap.add_argument("out")
ap.add_argument("--pilot", action="store_true", help="5-minute logic check: no standard block, short main load")
args = ap.parse_args()
OUT = os.path.abspath(args.out)
os.makedirs(OUT, exist_ok=True)
PILOT = args.pilot
ML_MIN = 4.0 if PILOT else 37.0          # main-load minutes
DRAIN_MIN = 1.0 if PILOT else 3.0
rnd = random.Random(20261115)
lock = threading.Lock()
ABORT = threading.Event()
STOP_ADMIT = threading.Event()
abort_reason = []
active_resps = set()
T0 = time.time()


def now_rel():
    return round(time.time() - T0, 1)


def write(name, obj):
    with lock:
        with open(os.path.join(OUT, name), "a") as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def event(kind, **kw):
    kw.update(kind=kind, t=now_rel(), wall=time.strftime("%H:%M:%S"))
    write("events.jsonl", kw)
    print(f"[{kw['wall']} +{kw['t']/60:5.1f}m] {kind} {json.dumps({k: v for k, v in kw.items() if k not in ('kind', 't', 'wall')}, ensure_ascii=False)[:300]}", flush=True)


# ---------------------------------------------------------------- engine log followers
done_lines = {}          # chatcmpl id -> parsed done line
disk_reads = []          # (t, tokens)
bad_lines = []
BAD_RE = re.compile(r"BadSlot|follow_refused|panic|OutOfMemory|out of memory|MissingTritonVariant|Segmentation", re.I)
DONE_RE = re.compile(r"done (chatcmpl-[0-9a-f]+) prompt=(\d+) cached=(\d+) thinking=(\w+) effort=(\S+) tokens=(\d+) sha=\S+ finish=(\S+)")


def follow(cmd, tag):
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace")
    for line in p.stdout:
        if ABORT.is_set() and tag == "stop":
            break
        m = DONE_RE.search(line)
        if m:
            done_lines[m.group(1)] = {"prompt": int(m.group(2)), "cached": int(m.group(3)), "thinking": m.group(4) == "True",
                                      "effort": m.group(5), "tokens": int(m.group(6)), "finish": m.group(7)}
        if "learned tokens from disk" in line:
            mm = re.search(r"read (\d+) learned tokens", line)
            disk_reads.append((now_rel(), int(mm.group(1)) if mm else None))
        if BAD_RE.search(line):
            bad_lines.append({"t": now_rel(), "rank": tag, "line": line.strip()[:300]})
            write("bad_lines.jsonl", bad_lines[-1])
            trip(f"{tag} log: {line.strip()[:160]}")


def trip(reason):
    if not ABORT.is_set():
        abort_reason.append(reason)
        event("ABORT", reason=reason)
        ABORT.set()
        STOP_ADMIT.set()
        with lock:
            for r in list(active_resps):
                try:
                    r.close()
                except Exception:
                    pass


# ---------------------------------------------------------------- telemetry
def meminfo_local():
    d = {}
    for line in open("/proc/meminfo"):
        k, v = line.split(":", 1)
        d[k] = int(v.split()[0])
    return d["MemAvailable"] / 1048576, (d["SwapTotal"] - d["SwapFree"]) / 1024


node2_state = {"mem": None, "swap": None, "clock": None, "temp": None}


def node2_loop():
    cmd = ["ssh", "-o", "BatchMode=yes", "-o", "ServerAliveInterval=5", NODE2,
           "while true; do a=$(awk '/MemAvailable/{print $2}' /proc/meminfo); st=$(awk '/SwapTotal/{print $2}' /proc/meminfo); "
           "sf=$(awk '/SwapFree/{print $2}' /proc/meminfo); g=$(nvidia-smi --query-gpu=clocks.gr,temperature.gpu --format=csv,noheader,nounits); "
           "echo \"$a $st $sf $g\"; sleep 1; done"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True)
    for line in p.stdout:
        try:
            a, st, sf, rest = line.split(" ", 3)
            clk, tmp = [x.strip() for x in rest.split(",")]
            node2_state.update(mem=int(a) / 1048576, swap=(int(st) - int(sf)) / 1024, clock=int(clk), temp=int(tmp))
        except Exception:
            pass
        if ABORT.is_set() and STOP_TELEM.is_set():
            p.kill()
            break


STOP_TELEM = threading.Event()
telem = []


def telemetry_loop():
    swap0 = None
    bad_health = 0
    cl = httpx.Client(timeout=2.0)
    while not STOP_TELEM.is_set():
        t = time.time()
        row = {"t": now_rel()}
        try:
            row["n1_mem"], row["n1_swap"] = meminfo_local()
            g = subprocess.run(["nvidia-smi", "--query-gpu=clocks.gr,temperature.gpu,power.draw", "--format=csv,noheader,nounits"],
                               capture_output=True, text=True, timeout=2).stdout.strip().split(",")
            row["n1_clock"], row["n1_temp"], row["n1_power"] = int(g[0]), int(g[1]), float(g[2])
        except Exception:
            pass
        row.update({f"n2_{k}": v for k, v in node2_state.items()})
        try:
            h = cl.get(P88 + "/health").json()
            row["eng_ok"] = h.get("status") == "ok"
            row["eng_conn"] = h["live"]["connections"]
            row["eng_wait"] = h["live"]["waiting"]
        except Exception:
            row["eng_ok"] = False
        try:
            s = cl.get(P89 + "/proxy/status").json()
            row["px_active"], row["px_bg"], row["px_wait"] = s["active_running"], s["bg_running"], s["waiting_in_queue"]
        except Exception:
            pass
        telem.append(row)
        write("telemetry.jsonl", row)
        if swap0 is None and row.get("n1_swap") is not None:
            swap0 = (row["n1_swap"], row.get("n2_swap") or 0)
        bad_health = bad_health + 1 if not row.get("eng_ok") else 0
        if bad_health >= 5:
            trip("engine /health not ok for 5 s")
        if row.get("n1_mem") is not None and row["n1_mem"] < ABORT_N1_GIB:
            trip(f"Node1 MemAvailable {row['n1_mem']:.2f} GiB < {ABORT_N1_GIB}")
        if row.get("n2_mem") is not None and row["n2_mem"] < ABORT_N2_GIB:
            trip(f"Node2 MemAvailable {row['n2_mem']:.2f} GiB < {ABORT_N2_GIB}")
        if swap0 and row.get("n1_swap") is not None and row["n1_swap"] - swap0[0] > SWAP_GROWTH_ABORT_MIB:
            trip(f"Node1 swap grew {row['n1_swap'] - swap0[0]:.0f} MiB")
        if swap0 and row.get("n2_swap") is not None and row["n2_swap"] - swap0[1] > SWAP_GROWTH_ABORT_MIB:
            trip(f"Node2 swap grew {row['n2_swap'] - swap0[1]:.0f} MiB")
        time.sleep(max(0.0, 1.0 - (time.time() - t)))


# ---------------------------------------------------------------- request core
client = httpx.Client(timeout=httpx.Timeout(900.0, connect=10.0), limits=httpx.Limits(max_connections=64))


def chat(body, port=P89, priority=1, cancel=None, tag=None, timeout=900.0, scenario="?", prefill_cancel_at=None):
    """Stream a chat completion (or send non-stream) and return a row. cancel(stage, t_since_start, row) -> bool closes."""
    body = {"model": MODEL, **body}
    stream = body.get("stream", True)
    body["stream"] = stream
    if stream:
        body["stream_options"] = {"include_usage": True}
    hdr = {"X-Priority": str(priority), "Content-Type": "application/json"}
    row = {"scenario": scenario, "tag": tag, "port": port[-4:], "priority": priority, "stream": stream, "status": None,
           "ttfe": None, "ttft": None, "t_content": None, "content": "", "reasoning_chars": 0, "tool_calls": [],
           "finish": None, "usage": None, "error": None, "done_seen": False, "id": None, "cancelled": None,
           "t_start": now_rel(), "max_tokens": body.get("max_tokens"), "effort": body.get("reasoning_effort")}
    t0 = time.perf_counter()
    reasoning = []
    tcs = {}
    if ABORT.is_set():
        row["error"] = "aborted_before_send"
        return row
    try:
        if not stream:
            r = client.post(port + "/v1/chat/completions", content=json.dumps(body, ensure_ascii=False).encode(), headers=hdr, timeout=timeout)
            row["status"] = r.status_code
            row["wall"] = round(time.perf_counter() - t0, 3)
            if r.status_code == 200:
                o = r.json()
                ch = o["choices"][0]
                m = ch.get("message") or {}
                row.update(id=o.get("id"), finish=ch.get("finish_reason"), usage=o.get("usage"), content=m.get("content") or "",
                           reasoning_chars=len(m.get("reasoning_content") or ""), done_seen=True,
                           error=(o.get("error") or {}).get("code") if o.get("error") else None)
                for t in m.get("tool_calls") or []:
                    tcs[len(tcs)] = {"id": t.get("id"), "name": t["function"]["name"], "args": t["function"].get("arguments") or ""}
            else:
                row["error"] = r.text[:300]
        else:
            with client.stream("POST", port + "/v1/chat/completions", content=json.dumps(body, ensure_ascii=False).encode(), headers=hdr, timeout=timeout) as r:
                with lock:
                    active_resps.add(r)
                timer = None
                if prefill_cancel_at is not None:
                    # a reply still in prefill sends no SSE line, so close the socket from a timer
                    def _pc():
                        if row["ttft"] is None:
                            row["cancelled"] = "prefill"
                            row["t_cancel_abs"] = time.time()
                            try:
                                r.close()
                            except Exception:
                                pass
                    timer = threading.Timer(prefill_cancel_at, _pc)
                    timer.start()
                try:
                    row["status"] = r.status_code
                    if r.status_code != 200:
                        row["error"] = r.read().decode(errors="replace")[:300]
                    else:
                        n_content = 0
                        for line in r.iter_lines():
                            el = time.perf_counter() - t0
                            if row["ttfe"] is None:
                                row["ttfe"] = round(el, 3)
                            if cancel and cancel("pre", el, row):
                                row["cancelled"] = row["cancelled"] or "prefill"
                                break
                            if not line.startswith("data:"):
                                continue
                            d = line[5:].strip()
                            if d == "[DONE]":
                                row["done_seen"] = True
                                break
                            try:
                                o = json.loads(d)
                            except Exception:
                                continue
                            row["id"] = row["id"] or o.get("id")
                            if o.get("error"):
                                row["error"] = o["error"].get("code") if isinstance(o["error"], dict) else str(o["error"])
                            if o.get("usage"):
                                row["usage"] = o["usage"]
                            for ch in o.get("choices") or []:
                                dl = ch.get("delta") or {}
                                stage = None
                                if dl.get("reasoning_content"):
                                    reasoning.append(dl["reasoning_content"])
                                    stage = "thinking"
                                if dl.get("content"):
                                    row["content"] += dl["content"]
                                    n_content += 1
                                    stage = "content"
                                    if row["t_content"] is None:
                                        row["t_content"] = round(el, 3)
                                for t in dl.get("tool_calls") or []:
                                    i = t.get("index", 0)
                                    e = tcs.setdefault(i, {"id": None, "name": "", "args": ""})
                                    e["id"] = e["id"] or t.get("id")
                                    f = t.get("function") or {}
                                    e["name"] += f.get("name") or ""
                                    e["args"] += f.get("arguments") or ""
                                    stage = "tool_args"
                                if stage and row["ttft"] is None:
                                    row["ttft"] = round(el, 3)
                                if ch.get("finish_reason"):
                                    row["finish"] = ch["finish_reason"]
                                if stage and cancel and cancel(stage, el, row):
                                    row["cancelled"] = stage
                                    break
                            if row["cancelled"]:
                                break
                finally:
                    if timer:
                        timer.cancel()
                    with lock:
                        active_resps.discard(r)
            row["wall"] = round(time.perf_counter() - t0, 3)
    except Exception as e:
        if STOP_ADMIT.is_set() and not row["cancelled"]:
            row["cancelled"] = "drain"  # closed by the end-of-run drain: censored, not a failure
        if not row["cancelled"]:
            row["error"] = row["error"] or f"{type(e).__name__}: {str(e)[:200]}"
        row["wall"] = round(time.perf_counter() - t0, 3)
    row["reasoning_chars"] = row["reasoning_chars"] or sum(len(x) for x in reasoning)
    row["tool_calls"] = [tcs[k] for k in sorted(tcs)]
    row["dsml_in_content"] = any(m in row["content"] for m in DSML)
    row["tools_active"] = bool(body.get("tools")) and body.get("tool_choice") != "none"
    row["dsml_leak_tools_active"] = row["dsml_in_content"] and row["tools_active"]
    bad_args = 0
    for t in row["tool_calls"]:
        try:
            json.loads(t["args"] or "{}")
        except Exception:
            bad_args += 1
    row["tool_args_bad"] = bad_args
    row["loop_shadow"] = bool(re.search(r"(.{20,600}?)\1{4,}", row["content"][-12000:], re.S))
    return row


def valid(row, allow_length=False):
    if row.get("status") != 200 or row.get("error"):
        return False
    if row["stream"] and not row["done_seen"]:
        return False
    ok_fin = row["finish"] in ("stop", "tool_calls") or (allow_length and row["finish"] == "length")
    has = bool(row["content"].strip()) or bool(row["tool_calls"])
    return ok_fin and has and not row["dsml_in_content"] and row["tool_args_bad"] == 0


def engine_effort(row, wait=3.0):
    t = time.time()
    while row.get("id") and row["id"] not in done_lines and time.time() - t < wait:
        time.sleep(0.2)
    return done_lines.get(row.get("id"))


def audit_for(row, wait=3.0):
    """The proxy audit record for this reply (matched on upstream_id)."""
    if not row.get("id"):
        return None
    t = time.time()
    while time.time() - t < wait:
        try:
            with open(AUDIT, "rb") as f:
                f.seek(max(0, os.path.getsize(AUDIT) - 400000))
                tail = f.read().decode(errors="replace").splitlines()
            for line in reversed(tail):
                if row["id"] in line:
                    return json.loads(line)
        except Exception:
            pass
        time.sleep(0.3)
    return None


def record(row, **extra):
    row.update(extra)
    row["t_end"] = now_rel()
    write("rows.jsonl", row)
    return row


# ---------------------------------------------------------------- content generators
def png(colors, w=256, h=256):
    raw = bytearray()
    for y in range(h):
        raw.append(0)
        for x in range(w):
            raw.extend(colors[(0 if y < h // 2 else 2) + (0 if x < w // 2 else 1)])

    def chunk(t, d):
        c = struct.pack(">I", len(d)) + t + d
        return c + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    data = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(bytes(raw))) + chunk(b"IEND", b"")
    return base64.b64encode(data).decode()


RGBY = {"red": (220, 30, 30), "green": (30, 200, 30), "blue": (30, 60, 220), "yellow": (230, 210, 30)}
IMAGES = []
for perm in (("red", "green", "blue", "yellow"), ("green", "red", "yellow", "blue"), ("blue", "yellow", "red", "green")):
    IMAGES.append((perm, png([RGBY[c] for c in perm])))
VISION_CTX = " ".join(f"cluster_telemetry_metric_{i}" for i in range(1200))  # > 2048 tokens so Turn 1 commits a snapshot


def code_corpus(tokens, seed):
    r = random.Random(seed)
    out, n, i = [f"# module {seed}\n"], 0, 0
    while n < tokens:
        name = f"Svc_{seed}_{i}"
        c = (f"class {name}:\n    def __init__(self, cap: int = {r.randint(1, 999)}):\n        self.cap = cap\n        self.items = []\n\n"
             f"    def push(self, x):\n        if len(self.items) >= self.cap:\n            raise OverflowError('{name} full')\n        self.items.append(x)\n\n"
             f"    def drain(self, k: int = {r.randint(1, 64)}):\n        out, self.items = self.items[:k], self.items[k:]\n        return out\n\n")
        out.append(c)
        n += len(c) // 4
        i += 1
    return "".join(out)


TOOLS = [
    {"type": "function", "function": {"name": "read_file", "description": "Read a file from the repository.",
                                      "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "offset": {"type": "integer"}, "limit": {"type": "integer"}}, "required": ["path"]}}},
    {"type": "function", "function": {"name": "grep", "description": "Search the repository for a regex.",
                                      "parameters": {"type": "object", "properties": {"pattern": {"type": "string"}, "path": {"type": "string"}}, "required": ["pattern"]}}},
    {"type": "function", "function": {"name": "list_dir", "description": "List a directory.",
                                      "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
    {"type": "function", "function": {"name": "edit_file", "description": "Replace text in a file.",
                                      "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "old": {"type": "string"}, "new": {"type": "string"}}, "required": ["path", "old", "new"]}}},
    {"type": "function", "function": {"name": "bash", "description": "Run a shell command (sandboxed).",
                                      "parameters": {"type": "object", "properties": {"cmd": {"type": "string"}}, "required": ["cmd"]}}},
]
TOOL_NAMES = {t["function"]["name"]: t["function"]["parameters"].get("required", []) for t in TOOLS}


def tool_ok(row):
    """Every tool call names a declared tool and carries its required parameters."""
    for t in row["tool_calls"]:
        if t["name"] not in TOOL_NAMES:
            return False
        try:
            a = json.loads(t["args"] or "{}")
        except Exception:
            return False
        if not isinstance(a, dict) or any(k not in a for k in TOOL_NAMES[t["name"]]):
            return False
    return True


def mock_tool(name, args, seed):
    r = random.Random(f"{seed}{name}{args}")
    if name == "read_file":
        return code_corpus(r.randint(1500, 4000), f"f{r.randint(0, 10**6)}")
    if name == "grep":
        return "\n".join(f"src/mod_{r.randint(0, 99)}.py:{r.randint(1, 900)}: raise OverflowError" for _ in range(r.randint(5, 40)))
    if name == "list_dir":
        return "\n".join(f"mod_{i}.py" for i in range(r.randint(5, 60)))
    if name == "edit_file":
        return "ok: 1 replacement"
    return "exit 0\n" + "\n".join(f"test_{i} PASSED" for i in range(r.randint(3, 30)))


AIME = json.load(open(os.path.join(HERE, "data/aime2024.json")))


def boxed(s):
    m = re.findall(r"\\boxed\{([^{}]*)\}", s)
    return m[-1].strip() if m else None


# ---------------------------------------------------------------- preflight singles
def preflight():
    event("preflight_start")
    res = {}
    r = client.post(P88 + "/v1/chat/completions", json={"model": MODEL, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 8, "reasoning_effort": 25})
    res["int_effort_400"] = r.status_code == 400
    r = chat({"messages": [{"role": "user", "content": "What is 2+3? Answer briefly."}], "max_tokens": 300, "reasoning_effort": "xhigh", "temperature": 0}, port=P88, scenario="pre_xhigh")
    d = engine_effort(r)
    res["xhigh_200"] = r["status"] == 200 and valid(r)
    res["xhigh_engine"] = d
    record(r)
    r = client.post(P88 + "/v1/chat/completions", json={"model": MODEL, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 3_000_000})
    res["over_context_4xx"] = 400 <= r.status_code < 500
    res["over_context_status"] = r.status_code
    r = client.post(P89 + "/v1/chat/completions", content=b'{"model": "x", "messages": [', headers={"Content-Type": "application/json"})
    res["malformed_json_4xx"] = 400 <= r.status_code < 500
    res["malformed_json_status"] = r.status_code
    # cancel during prefill: 32K and 100K cold prompts, closed before the first token; slot release from /health
    for size, after in ((32000, 4.0), (100000, 20.0)) if not PILOT else ((32000, 4.0),):
        nonce = f"{time.time_ns()}"
        body = {"messages": [{"role": "user", "content": f"[{nonce}]\n" + code_corpus(size, nonce) + "\nSummarize."}], "max_tokens": 64, "reasoning_effort": "none"}
        r = chat(body, port=P89, priority=1, prefill_cancel_at=after, scenario=f"pre_cancel_{size // 1000}k")
        t_cancel = {"t": r.get("t_cancel_abs") or time.time()}
        rel = None
        t = time.time()
        while time.time() - t < 120:
            try:
                if client.get(P88 + "/health").json()["live"]["connections"] == 0:
                    rel = round(time.time() - t_cancel.get("t", t), 2)
                    break
            except Exception:
                pass
            time.sleep(0.2)
        res[f"cancel_{size // 1000}k_release_s"] = rel
        res[f"cancel_{size // 1000}k_cancelled"] = r["cancelled"]
        record(r, release_s=rel)
        time.sleep(2)
        if bad_lines:
            break
    res["bad_lines"] = len(bad_lines)
    event("preflight_done", **res)
    return res


# ---------------------------------------------------------------- standard front
def standard_front():
    out = {}
    if PILOT:
        return out
    for name, cmd in (("omni_standard", ["python3", f"{HERE}/run_omni_eval.py", "--profile", "standard", "--output-report", f"{OUT}/omni_standard_front.json"]),
                      ("full_eval", ["python3", f"{HERE}/run_full_eval.py", f"omniscenario_{time.strftime('%Y%m%d_%H%M')}"])):
        if ABORT.is_set():
            break
        event(f"{name}_start")
        t = time.time()
        with open(f"{OUT}/{name}.log", "w") as lf:
            rc = subprocess.run(cmd, cwd=HERE, stdout=lf, stderr=subprocess.STDOUT).returncode
        out[name] = {"rc": rc, "s": round(time.time() - t, 1)}
        event(f"{name}_done", **out[name])
    return out


# ---------------------------------------------------------------- thinking matrix
EFF_NUM = {"minimal": 25, "low": 50, "medium": 62, "high": 75, "xhigh": 88, "max": 100}


def m1_entry():
    Q = [{"role": "user", "content": "A train covers 120 km in 1.5 hours. What is its average speed in km/h? Explain briefly."}]
    cases = []
    for e in ["none", "minimal", "low", "medium", "high", "xhigh", "max"]:
        cases.append((f"effort_{e}", {"reasoning_effort": e}, e != "none", e if e != "none" else "none"))
    cases += [
        ("no_effort", {}, True, None),
        ("none_plus_enable_true", {"reasoning_effort": "none", "chat_template_kwargs": {"enable_thinking": True}}, True, None),
        ("high_plus_enable_false", {"reasoning_effort": "high", "chat_template_kwargs": {"enable_thinking": False}}, False, "none"),
        ("alias_true", {"chat_template_kwargs": {"thinking": True}}, True, None),
        ("alias_false", {"chat_template_kwargs": {"thinking": False}}, False, "none"),
        ("enable_false_alias_true", {"chat_template_kwargs": {"enable_thinking": False, "thinking": True}}, False, "none"),
        ("top_high_kwargs_none", {"reasoning_effort": "high", "chat_template_kwargs": {"reasoning_effort": "none"}}, True, "high"),
        ("kwargs_effort_low", {"chat_template_kwargs": {"reasoning_effort": "low"}}, True, "low"),
        ("kwargs_string", {"chat_template_kwargs": "x", "reasoning_effort": "low"}, True, "low"),
        ("kwargs_empty", {"chat_template_kwargs": {}}, True, None),
    ]
    rows = []

    def one(c):
        name, extra, want_think, want_eff = c
        r = chat({"messages": Q, "max_tokens": 600, "temperature": 0, "seed": 42, **extra}, port=P88, scenario="M1", tag=name)
        d = engine_effort(r)
        got_think = d["thinking"] if d else None
        got_eff = d["effort"] if d else None
        ok = r["status"] == 200 and d is not None and got_think == want_think and (want_eff is None or got_eff == want_eff)
        if want_eff is None and want_think and d:  # no effort named: engine passes none and the template default (high 75) applies
            ok = ok and got_eff in ("none", "null", "-")
        return record(r, want_think=want_think, want_eff=want_eff, eng=d, ok=ok)
    with ThreadPoolExecutor(7) as ex:
        rows = list(ex.map(one, cases))
    for bad in ({"reasoning_effort": "abc"}, {"reasoning_effort": 50}, {"chat_template_kwargs": {"reasoning_effort": 75}}):
        r = client.post(P88 + "/v1/chat/completions", json={"model": MODEL, "messages": Q, "max_tokens": 8, **bad})
        rows.append(record({"scenario": "M1", "tag": f"invalid_{json.dumps(bad)}", "status": r.status_code, "ok": r.status_code == 400}))
    event("M1_done", ok=sum(1 for r in rows if r.get("ok")), n=len(rows), fails=[r["tag"] for r in rows if not r.get("ok")])
    return rows


def m2_levels():
    probs = AIME[:4]
    cells = [(p, e) for p in probs for e in ["none", "minimal", "low", "medium", "high", "xhigh", "max"]]

    def one(c):
        p, e = c
        r = chat({"messages": [{"role": "user", "content": p["problem"] + "\nPut the final answer in \\boxed{}."}], "max_tokens": 2048,
                  "reasoning_effort": e, "temperature": 0, "seed": 7}, port=P88, scenario="M2", tag=f"{p['id']}|{e}")
        d = engine_effort(r)
        ans = boxed(r["content"])
        return record(r, eng=d, reasoning_tokens=((r.get("usage") or {}).get("completion_tokens_details") or {}).get("reasoning_tokens"),
                      correct=(ans == str(p["answer"])), ok=r["status"] == 200 and not r["error"])
    with ThreadPoolExecutor(7) as ex:
        rows = list(ex.map(one, cells if not PILOT else cells[:7]))
    for e in ("none", "high"):
        perm, img = IMAGES[0]
        r = chat({"messages": [{"role": "user", "content": [{"type": "text", "text": "Name the color of each quadrant: top-left, top-right, bottom-left, bottom-right."},
                                                              {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img}"}}]}],
                  "max_tokens": 1024, "reasoning_effort": e, "temperature": 0}, port=P88, scenario="M2v", tag=f"vision|{e}")
        rows.append(record(r, ok=vision_ok(r["content"], perm)))
    by = {}
    for r in rows:
        if r["scenario"] == "M2":
            e = r["tag"].split("|")[1]
            by.setdefault(e, []).append(r.get("reasoning_tokens") or 0)
    event("M2_done", reasoning_tokens_by_effort={k: sorted(v) for k, v in by.items()},
          correct={e: sum(1 for r in rows if r["scenario"] == "M2" and r["tag"].endswith("|" + e) and r.get("correct")) for e in by},
          vision=[r.get("ok") for r in rows if r["scenario"] == "M2v"])
    return rows


def vision_ok(text, perm):
    t = text.lower()
    return all(c in t for c in perm)


def m3_rewrite():
    Q = [{"role": "user", "content": "What is 17 * 23? Answer with the number only."}]
    T1 = [TOOLS[0]]
    cases = [  # name, body, expect_rewrite
        ("mt255", {"max_tokens": 255, "reasoning_effort": "low"}, True),
        ("mt256", {"max_tokens": 256, "reasoning_effort": "low"}, True),
        ("mt257", {"max_tokens": 257, "reasoning_effort": "low"}, False),
        ("mt120_noeffort", {"max_tokens": 120}, True),
        ("mt120_tools_empty", {"max_tokens": 120, "reasoning_effort": "low", "tools": []}, True),
        ("mt120_tools", {"max_tokens": 120, "reasoning_effort": "low", "tools": T1}, False),
        ("mt120_enable_true", {"max_tokens": 120, "chat_template_kwargs": {"enable_thinking": True}}, False),
        ("mt120_alias_true", {"max_tokens": 120, "chat_template_kwargs": {"thinking": True}}, False),
        ("mt120_enable_false", {"max_tokens": 120, "chat_template_kwargs": {"enable_thinking": False}}, True),
        ("mct120", {"max_completion_tokens": 120, "reasoning_effort": "low"}, True),
        ("mt_bool", {"max_tokens": True, "reasoning_effort": "low"}, False),
        ("mt0", {"max_tokens": 0, "reasoning_effort": "low"}, False),
        ("mt120_effort_none", {"max_tokens": 120, "reasoning_effort": "none"}, False),
    ]
    rows = []
    for name, extra, want in cases:
        r = chat({"messages": Q, "temperature": 0, **extra}, port=P89, priority=1, scenario="M3", tag=name, stream=None) if False else \
            chat({"messages": Q, "temperature": 0, **extra}, port=P89, priority=1, scenario="M3", tag=name)
        a = audit_for(r)
        got = bool(a and a.get("effort_rewritten"))
        rows.append(record(r, audit_effort=a and a.get("effort"), rewritten=got, want_rewrite=want,
                           ok=(got == want) if r["status"] == 200 else (name in ("mt_bool", "mt0"))))
    event("M3_done", ok=sum(1 for r in rows if r.get("ok")), n=len(rows),
          fails=[(r["tag"], r.get("status"), r.get("rewritten")) for r in rows if not r.get("ok")])
    return rows


def m4_toolchoice():
    Q = [{"role": "system", "content": "You are a coding agent. Use tools to inspect the repository before answering."},
         {"role": "user", "content": "Find where OverflowError is raised in src/ and show the surrounding code."}]
    cells = [(tc, e) for tc in ("auto", "required", {"type": "function", "function": {"name": "grep"}}, "none") for e in ("low", "high")]
    cells += [("budget", (b, tl)) for b in (0, 1024) for tl in (True, False)]

    def one(c):
        tc, e = c
        if tc == "budget":
            b, tl = e
            body = {"messages": Q, "max_tokens": 4096, "reasoning_effort": "high", "thinking_budget": b}
            if tl:
                body["tools"] = TOOLS
            r = chat(body, scenario="M4b", tag=f"budget{b}|tools={tl}")
            return record(r, valid=valid(r), tool_ok=tool_ok(r), xfail_cut_to_tool=bool(b and tl and r["tool_calls"]))
        body = {"messages": Q, "tools": TOOLS, "tool_choice": tc, "max_tokens": 3000, "reasoning_effort": e}
        r = chat(body, scenario="M4", tag=f"{tc if isinstance(tc, str) else 'function'}|{e}")
        return record(r, valid=valid(r), tool_ok=tool_ok(r), all_reasoning=(r["finish"] == "length" and not r["content"].strip() and not r["tool_calls"]),
                      ok=(not r["dsml_in_content"]) and r["tool_args_bad"] == 0 and r["status"] == 200)
    with ThreadPoolExecutor(6) as ex:
        rows = list(ex.map(one, cells))
    event("M4_done", rows=[(r["tag"], r["finish"], len(r["tool_calls"]), r.get("valid"), r["dsml_in_content"]) for r in rows])
    return rows


def m5_history():
    """10-turn tool chain: model tool calls kept with string arguments, mock results, reasoning_content kept in history."""
    sess = Session("M5", 20000, effort="high", scenario="M5")
    rows = []
    for _ in range(10 if not PILOT else 3):
        if ABORT.is_set():
            break
        rows.append(sess.turn(max_tokens=3000))
    event("M5_done", turns=[(r.get("prompt_tokens"), r.get("cached_tokens"), len(r["tool_calls"]), r.get("valid")) for r in rows])
    return rows


def m6_loop():
    out = os.path.join(OUT, "m6_mock_loop")
    rc = subprocess.run(["python3", f"{HERE}/run_loop_fallback_mock.py", out], capture_output=True, text=True, timeout=300)
    last = (rc.stdout.strip().splitlines() or [""])[-1]
    event("M6_done", rc=rc.returncode, summary=last)
    return {"rc": rc.returncode, "summary": last}


# ---------------------------------------------------------------- agent sessions
class Session:
    def __init__(self, name, base_tokens, effort="high", scenario="S1"):
        self.name, self.effort, self.scenario = name, effort, scenario
        nonce = f"{name}-{time.time_ns()}"
        self.msgs = [{"role": "system", "content": "You are a senior coding agent working in a repository. Use the tools to inspect code, then explain findings. Keep answers concise."},
                     {"role": "user", "content": f"Repository snapshot [{nonce}]:\n```python\n{code_corpus(base_tokens, nonce)}\n```\n"
                                                 "Task: audit this codebase for unbounded buffers and race conditions. Start by grepping for OverflowError, then read the relevant files."}]
        self.busy = threading.Lock()
        self.turns = 0
        self.last_used = time.time()
        self.base = base_tokens

    def est_tokens(self):
        return sum(len(json.dumps(m, ensure_ascii=False)) for m in self.msgs) // 4

    def turn(self, max_tokens="pick"):
        if max_tokens == "pick":
            max_tokens = rnd.choices([None, 32768, 3000], weights=[31, 14, 55])[0]
        body = {"messages": self.msgs, "tools": TOOLS, "tool_choice": "auto", "reasoning_effort": self.effort}
        if max_tokens:
            body["max_tokens"] = max_tokens
        r = chat(body, priority=1, scenario=self.scenario, tag=f"{self.name}#{self.turns}")
        self.last_used = time.time()
        u = r.get("usage") or {}
        cached = (u.get("prompt_tokens_details") or {}).get("cached_tokens")
        ok = valid(r) and tool_ok(r)
        if r["status"] == 200 and not r["error"] and (r["content"] or r["tool_calls"]):
            a = {"role": "assistant", "content": r["content"] or ""}
            if r["tool_calls"]:
                a["tool_calls"] = [{"id": t["id"] or f"call_{self.turns}_{i}", "type": "function", "function": {"name": t["name"], "arguments": t["args"] or "{}"}}
                                   for i, t in enumerate(r["tool_calls"])]
            if r["reasoning_chars"]:
                a["reasoning_content"] = f"(reasoning of turn {self.turns}, {r['reasoning_chars']} chars)"
            self.msgs.append(a)
            if r["tool_calls"]:
                for i, t in enumerate(a["tool_calls"]):
                    try:
                        args = json.loads(t["function"]["arguments"])
                    except Exception:
                        args = {}
                    self.msgs.append({"role": "tool", "tool_call_id": t["id"], "content": mock_tool(t["function"]["name"], json.dumps(args, sort_keys=True), self.name + str(self.turns))})
            else:
                self.msgs.append({"role": "user", "content": rnd.choice(["Continue: read the next file that raises OverflowError.", "Now grep for 'drain(' and check the callers.", "Run the tests with bash and report failures."])})
        self.turns += 1
        return record(r, prompt_tokens=u.get("prompt_tokens"), cached_tokens=cached, valid=ok, tool_ok=tool_ok(r), session=self.name, turn=self.turns,
                      est_tokens=self.est_tokens())


# ---------------------------------------------------------------- main load scenarios
inflight_tokens = [0]
cold_long = [0]
BUDGET_TOKENS = 1_600_000   # sum of (prompt + max_tokens) in flight; the shared KV pool is 2,097,152 positions
pause_cold = threading.Event()


def reserve(n, cold_big=False, wait=60):
    t = time.time()
    while True:
        with lock:
            if inflight_tokens[0] + n <= BUDGET_TOKENS and (not cold_big or (cold_long[0] < 1 and not pause_cold.is_set())):
                inflight_tokens[0] += n
                if cold_big:
                    cold_long[0] += 1
                return True
        if time.time() - t > wait or ABORT.is_set():
            return False
        time.sleep(0.5)


def release(n, cold_big=False):
    with lock:
        inflight_tokens[0] -= n
        if cold_big:
            cold_long[0] -= 1


SESSIONS = []
REVISIT = {}


def s1():
    free = [s for s in SESSIONS if s.name not in REVISIT and s.busy.acquire(blocking=False)]
    if not free:
        return s3a()
    s = free[0]
    for o in free[1:]:
        o.busy.release()
    try:
        big_cold = s.turns == 0 and s.base > 50000
        n = s.est_tokens() + 33000
        if not reserve(n, big_cold):
            return None
        try:
            return s.turn()
        finally:
            release(n, big_cold)
    finally:
        s.busy.release()


def s2():
    nonce = time.time_ns()
    msgs = [{"role": "system", "content": "You are a coding agent."},
            {"role": "user", "content": f"[{nonce}] Here is a diff to review:\n" + code_corpus(3000, nonce) + "\nRead the file src/queue.py to check the drain() bounds."}]
    r = chat({"messages": msgs, "tools": [TOOLS[0]], "tool_choice": {"type": "function", "function": {"name": "read_file"}}, "max_tokens": 3000, "reasoning_effort": "low"},
             priority=rnd.choice([1, 2]), scenario="S2")
    allr = r["finish"] == "length" and not r["content"].strip() and not r["tool_calls"]
    return record(r, valid=valid(r) or allr, xfail_all_reasoning=allr, tool_ok=tool_ok(r))


def s3a():
    r = chat({"messages": [{"role": "user", "content": rnd.choice(["Give a one-line definition of a mutex.", "What is 23*19? Number only.", "Name the capital of Japan."])}],
              "max_tokens": 120, "reasoning_effort": "low"}, priority=rnd.choice([1, 2]), scenario="S3a")
    a = audit_for(r, wait=2.0)
    return record(r, valid=valid(r, allow_length=True), rewritten=bool(a and a.get("effort_rewritten")))


def s3b():
    r = chat({"messages": [{"role": "user", "content": "Quickly: which file defines the queue class? Use a tool if needed."}],
              "tools": TOOLS, "max_tokens": 120, "reasoning_effort": "low"}, priority=rnd.choice([1, 2]), scenario="S3b")
    empty_len = r["finish"] == "length" and not r["content"].strip() and not r["tool_calls"]
    return record(r, valid=valid(r, allow_length=True) or empty_len, xfail_empty_length=empty_len, tool_ok=tool_ok(r))


SHARED = {k: code_corpus(k, f"shared_{k}") for k in (2000, 12000, 22000)}


def s4():
    hit = rnd.random() < 0.56
    tier = rnd.choices([2000, 12000, 22000], weights=[35, 40, 25])[0]
    if hit:
        prefix = SHARED[tier]
        q = f"Analyze class #{rnd.randint(1, 50)} and summarize its invariants."
    else:
        salt = "".join(rnd.choices(string.ascii_letters, k=24))
        prefix = code_corpus(min(tier, 12000), salt)
        q = "Verify this ephemeral module for bugs."
    r = chat({"messages": [{"role": "system", "content": "You are a senior systems engineer reviewing clustered code."},
                           {"role": "user", "content": f"Codebase:\n```python\n{prefix}\n```\nQuestion: {q}"}],
              "max_tokens": rnd.choice([256, 384, 512]), "reasoning_effort": rnd.choice(["none", "none", "low", "high"])},
             priority=rnd.choice([1, 1, 2]), scenario="S4", tag="hit" if hit else "low")
    return record(r, valid=valid(r, allow_length=True))


def s5():
    perm, img = rnd.choice(IMAGES)
    pr = rnd.choice([1, 2])
    m1 = [{"role": "user", "content": [{"type": "text", "text": f"[Diagnostic log: {VISION_CTX}]\nName the color of each quadrant (top-left, top-right, bottom-left, bottom-right)."},
                                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img}"}}]}]
    r1 = chat({"messages": m1, "max_tokens": 256, "reasoning_effort": "none"}, priority=pr, scenario="S5", tag="turn1")
    record(r1, valid=valid(r1, allow_length=True), vision_ok=vision_ok(r1["content"], perm))
    if r1["status"] != 200:
        return r1
    m2 = m1 + [{"role": "assistant", "content": r1["content"]}, {"role": "user", "content": "Which color is in the bottom-right corner? One word."}]
    r2 = chat({"messages": m2, "max_tokens": 128, "reasoning_effort": rnd.choice(["none", "low"])}, priority=pr, scenario="S5", tag="turn2")
    c2 = ((r2.get("usage") or {}).get("prompt_tokens_details") or {}).get("cached_tokens")
    return record(r2, valid=valid(r2, allow_length=True), vision_ok=perm[3] in r2["content"].lower(), turn2_cached=c2)


def s6():
    p = rnd.choice(AIME)
    attempts = []
    for i in range(3):
        r = chat({"messages": [{"role": "user", "content": p["problem"] + "\nPut the final answer in \\boxed{}."}], "max_tokens": rnd.choice([4096, 8192]),
                  "reasoning_effort": "high"}, priority=2, scenario="S6", tag=p["id"])
        attempts.append(r["status"])
        if r["status"] != 429:
            break
        time.sleep(2)
    return record(r, valid=valid(r, allow_length=True), correct=boxed(r["content"]) == str(p["answer"]), attempts=attempts)


def s7():
    stage = rnd.choice(["prefill", "thinking", "content", "tool_args"])
    nonce = time.time_ns()
    if stage == "prefill":
        body = {"messages": [{"role": "user", "content": f"[{nonce}]\n" + code_corpus(30000, nonce) + "\nSummarize."}], "max_tokens": 256, "reasoning_effort": "none"}
    elif stage == "thinking":
        body = {"messages": [{"role": "user", "content": rnd.choice(AIME)["problem"]}], "max_tokens": 4096, "reasoning_effort": "high"}
    elif stage == "content":
        body = {"messages": [{"role": "user", "content": "Write a 600-word essay on cache coherence."}], "max_tokens": 1500, "reasoning_effort": "none"}
    else:
        body = {"messages": [{"role": "user", "content": "Create the file notes/design.md with a 300-word design doc for a bounded queue."}],
                "tools": TOOLS, "max_tokens": 3000, "reasoning_effort": "low"}
    after = rnd.uniform(1.0, 8.0)

    def cancel(st, el, row):
        if stage == "prefill":
            return False
        return st == stage and el >= (row["ttft"] or el) + (after if stage != "tool_args" else 0)
    r = chat(body, priority=rnd.choice([1, 2]), cancel=cancel, scenario="S7", tag=stage,
             prefill_cancel_at=(3.0 if stage == "prefill" else None))
    if not r["cancelled"]:
        return record(r, valid=valid(r, allow_length=True), cancel_missed=True)
    pre = telem[-1].get("px_active") if telem else None
    rel = None
    t = time.time()
    while time.time() - t < 12:
        if telem and pre is not None and (telem[-1].get("px_active") or 0) < pre:
            rel = round(time.time() - t, 1)
            break
        time.sleep(0.25)
    time.sleep(max(0, 10 - (time.time() - t)))  # this worker idles so the release is observable
    return record(r, cancel_stage=stage, proxy_release_s=rel)


SCEN = [(s1, 40), (s2, 15), (s3a, 8), (s3b, 7), (s4, 10), (s5, 5), (s7, 10)]  # S6 runs on its own worker


def worker(i, t_end):
    while time.time() < t_end and not STOP_ADMIT.is_set():
        f = rnd.choices([f for f, _ in SCEN], weights=[w for _, w in SCEN])[0]
        try:
            f()
        except Exception as e:
            write("errors.jsonl", {"t": now_rel(), "worker": i, "err": repr(e)[:300]})
            time.sleep(1)


def s6_worker(t_end):
    while time.time() < t_end and not STOP_ADMIT.is_set():
        try:
            s6()
        except Exception as e:
            write("errors.jsonl", {"t": now_rel(), "worker": "s6", "err": repr(e)[:300]})
            time.sleep(1)


def p0_probe(tag="probe"):
    r = chat({"messages": [{"role": "user", "content": "What is 17 * 23? Number only."}], "max_tokens": 64, "reasoning_effort": "none"}, priority=0, scenario="P0", tag=tag)
    return record(r, valid=valid(r, allow_length=True))


def burst(name, mix):
    """Open-loop: all requests sent within ~50 ms while the main load holds the slots."""
    st = telem[-1] if telem else {}
    event(f"{name}_start", px_active=st.get("px_active"), px_wait=st.get("px_wait"))
    reqs = []
    for pr, n in mix:
        reqs += [pr] * n
    rows = []

    def one(pr):
        r = chat({"messages": [{"role": "user", "content": f"[{time.time_ns()}] Reply with the word OK."}], "max_tokens": 64, "reasoning_effort": "none"},
                 priority=pr, scenario="BURST", tag=f"{name}|p{pr}", timeout=120)
        a = audit_for(r, wait=1.0) if r["status"] == 200 else None
        return record(r, valid=valid(r, allow_length=True), burst=name)
    with ThreadPoolExecutor(len(reqs)) as ex:
        rows = list(ex.map(one, reqs))
    # server-side reject latency from the proxy audit (proxy_429 rows in this window)
    sc = {}
    for r in rows:
        sc[(r["priority"], r["status"])] = sc.get((r["priority"], r["status"]), 0) + 1
    rej = [r["wall"] for r in rows if r["status"] == 429]
    event(f"{name}_done", status_by_prio={f"p{k[0]}:{k[1]}": v for k, v in sc.items()}, reject_wall_s=sorted(rej)[:20],
          p0_rejected=sum(1 for r in rows if r["priority"] == 0 and r["status"] == 429))
    return rows


def needle_220k():
    pause_cold.set()
    try:
        code = "ZEBRA-" + "".join(rnd.choices(string.digits, k=6))
        nonce = time.time_ns()
        body_txt = code_corpus(215000, f"needle{nonce}")
        cut = int(len(body_txt) * 0.6)
        text = f"[{nonce}]\n" + body_txt[:cut] + f"\n# NOTE: the deployment secret is {code}\n" + body_txt[cut:]
        n = len(text) // 4 + 128
        if not reserve(n, cold_big=False, wait=180):
            event("needle_skipped", reason="token budget")
            return None
        event("needle_start", est_tokens=n)
        try:
            r = chat({"messages": [{"role": "user", "content": text + "\n\nWhat is the deployment secret written in the NOTE comment? Reply with it only."}],
                      "max_tokens": 64, "reasoning_effort": "none"}, priority=1, scenario="NEEDLE", timeout=900)
        finally:
            release(n)
        u = r.get("usage") or {}
        rec = record(r, valid=valid(r, allow_length=True), found=code in r["content"], prompt_tokens=u.get("prompt_tokens"),
                     cached=(u.get("prompt_tokens_details") or {}).get("cached_tokens"))
        event("needle_done", found=rec["found"], ttft=r["ttft"], prompt_tokens=u.get("prompt_tokens"),
              min_n1_mem=min((t.get("n1_mem") or 99) for t in telem[-300:]), min_n2_mem=min((t.get("n2_mem") or 99) for t in telem[-300:]))
        return rec
    finally:
        pause_cold.clear()


def cancel_100k(after):
    nonce = time.time_ns()
    n = 100000
    if not reserve(n + 300, wait=120):
        return None
    try:
        body = {"messages": [{"role": "user", "content": f"[{nonce}]\n" + code_corpus(n, nonce) + "\nSummarize."}], "max_tokens": 256, "reasoning_effort": "none"}
        r = chat(body, priority=1, prefill_cancel_at=after, scenario="CANCEL100K", tag=f"after{after}s")
    finally:
        release(n + 300)
    tc = r.get("t_cancel_abs") or time.time()
    c0 = telem[-1].get("eng_conn") if telem else None
    event("cancel100k_done", after=after, cancelled=r["cancelled"], status=r["status"], wall=r.get("wall"), eng_conn_at_cancel=c0, bad_lines=len(bad_lines))
    return record(r)


def revisit(sess):
    idle = round(time.time() - sess.last_used)
    d0 = len(disk_reads)
    with sess.busy:
        r = sess.turn(max_tokens=3000)
    reads = disk_reads[d0:]
    event("revisit_done", session=sess.name, idle_s=idle, prompt=r.get("prompt_tokens"), cached=r.get("cached_tokens"), ttft=r.get("ttft"), disk_reads=reads)
    REVISIT.pop(sess.name, None)
    return r


def main_load():
    ml0 = time.time()
    t_end = ml0 + ML_MIN * 60
    event("main_load_start", minutes=ML_MIN)
    bases = [30000, 50000, 80000, 120000, 160000] if not PILOT else [20000, 40000]
    for i, b in enumerate(bases):
        SESSIONS.append(Session(f"sess{i}_{b // 1000}k", b, effort=rnd.choice(["high", "medium", "low"])))
    threads = [threading.Thread(target=worker, args=(i, t_end), daemon=True) for i in range(6)]
    threads.append(threading.Thread(target=s6_worker, args=(t_end,), daemon=True))
    for t in threads:
        t.start()
    sc = (lambda m: m * (ML_MIN / 37.0))
    sched = [
        (sc(3.5), "mark_revisit_A", lambda: REVISIT.setdefault(SESSIONS[0].name, True)),
        (sc(4.0), "burst1", lambda: burst("burst1", [(2, 16), (0, 2)])),
        (sc(5.0), "mark_revisit_B", lambda: REVISIT.setdefault(SESSIONS[1].name, True)),
        (sc(7.0), "needle", needle_220k if not PILOT else (lambda: None)),
        (sc(16.0), "cancel100k_20", (lambda: cancel_100k(20.0)) if not PILOT else (lambda: None)),
        (sc(19.0), "cancel100k_40", (lambda: cancel_100k(40.0)) if not PILOT else (lambda: None)),
        (sc(24.0), "revisit_A", lambda: revisit(SESSIONS[0])),
        (sc(26.0), "burst2", lambda: burst("burst2", [(0, 6), (1, 6), (2, 6)])),
        (sc(32.0), "revisit_B", lambda: revisit(SESSIONS[1])),
    ]
    done = set()
    next_probe = time.time() + 60
    ev_threads = []
    while time.time() < t_end and not ABORT.is_set():
        el = (time.time() - ml0) / 60
        for at, name, fn in sched:
            if name not in done and el >= at:
                done.add(name)
                th = threading.Thread(target=lambda fn=fn, name=name: (event(f"{name}_fire"), fn()), daemon=True)
                th.start()
                ev_threads.append(th)
        if time.time() >= next_probe:
            next_probe += 60
            threading.Thread(target=p0_probe, daemon=True).start()
        time.sleep(0.5)
    STOP_ADMIT.set()
    event("main_load_stop_admit")
    t_drain = time.time() + DRAIN_MIN * 60
    for t in threads + ev_threads:
        t.join(timeout=max(0.1, t_drain - time.time()))
    still = [t for t in threads + ev_threads if t.is_alive()]
    if still:
        event("drain_cancel", in_flight=len(active_resps))
        with lock:
            for r in list(active_resps):
                try:
                    r.close()
                except Exception:
                    pass
        for t in still:
            t.join(timeout=30)
    event("main_load_done")


def final_checks():
    time.sleep(30)
    res = {}
    ss = subprocess.run(["ss", "-tan"], capture_output=True, text=True).stdout.splitlines()
    res["close_wait_8888_8889"] = sum(1 for l in ss if "CLOSE-WAIT" in l and (":8888 " in l or ":8889 " in l))
    res["probes"] = [p0_probe("final")["ttft"] for _ in range(5)]
    # 32K cut-in (cold, nonce): long prompt then a P0 short after 1 s
    nonce = time.time_ns()
    longb = {"messages": [{"role": "user", "content": f"[{nonce}]\n" + code_corpus(32000, nonce) + "\nSummarize in one line."}], "max_tokens": 32, "reasoning_effort": "none"}
    th = threading.Thread(target=lambda: record(chat(longb, priority=1, scenario="CUTIN", tag="long")), daemon=True)
    th.start()
    time.sleep(1.0)
    r = chat({"messages": [{"role": "user", "content": "Say hi."}], "max_tokens": 8, "reasoning_effort": "none"}, priority=0, scenario="CUTIN", tag="short")
    record(r)
    th.join(timeout=120)
    res["cutin_short_ttft"] = r["ttft"]
    res["n1_mem"], res["n1_swap"] = meminfo_local()
    res["n2_mem"], res["n2_swap"] = node2_state["mem"], node2_state["swap"]
    res["imprint_files"] = int(subprocess.run("sudo -n find /home/joseyarashio/.cache/dsv41-nvme-imprint -name '*.r0.bin' | wc -l", shell=True, capture_output=True, text=True).stdout.strip() or -1)
    event("final_checks", **res)
    return res


# ---------------------------------------------------------------- run
def main():
    env = {"pilot": PILOT, "start": time.strftime("%F %T"), "proxy_sha": subprocess.run(["sha256sum", os.path.expanduser("~/spark-fastfail-proxy/proxy.py")], capture_output=True, text=True).stdout[:8],
           "imprint_files": int(subprocess.run("sudo -n find /home/joseyarashio/.cache/dsv41-nvme-imprint -name '*.r0.bin' | wc -l", shell=True, capture_output=True, text=True).stdout.strip() or -1)}
    json.dump(env, open(os.path.join(OUT, "env.json"), "w"), indent=1)
    threading.Thread(target=follow, args=(["docker", "logs", "-f", "--since", "1s", "dsv41-rank0"], "rank0"), daemon=True).start()
    threading.Thread(target=follow, args=(["ssh", "-o", "BatchMode=yes", NODE2, "docker logs -f --since 1s dsv41-rank1 2>&1"], "rank1"), daemon=True).start()
    threading.Thread(target=node2_loop, daemon=True).start()
    threading.Thread(target=telemetry_loop, daemon=True).start()
    time.sleep(3)
    summary = {"env": env}
    try:
        summary["preflight"] = preflight()
        pf = summary["preflight"]
        if not (pf["int_effort_400"] and pf["xhigh_200"] and pf["malformed_json_4xx"]) or bad_lines:
            event("preflight_failed")
        if not ABORT.is_set():
            summary["standard"] = standard_front()
        for name, fn in (("M1", m1_entry), ("M3", m3_rewrite), ("M6", m6_loop)):
            if ABORT.is_set():
                break
            event(f"{name}_start")
            fn()
        if not ABORT.is_set():
            # M2 (levels), M4 (tool choice / budget) and M5 (10-turn history) overlap
            event("M245_start")
            ths = [threading.Thread(target=f, daemon=True) for f in (m2_levels, m4_toolchoice, m5_history)]
            for t in ths:
                t.start()
            for t in ths:
                t.join()
        if not ABORT.is_set():
            main_load()
        summary["final"] = final_checks()
    finally:
        summary["abort"] = abort_reason
        summary["elapsed_min"] = round((time.time() - T0) / 60, 1)
        json.dump(summary, open(os.path.join(OUT, "summary_raw.json"), "w"), indent=1, default=str)
        event("run_done", elapsed_min=summary["elapsed_min"], abort=abort_reason)
        STOP_TELEM.set()


if __name__ == "__main__":
    main()
