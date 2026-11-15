#!/usr/bin/env python3
"""Deterministic loop-fallback check: a copy of the live proxy.py on :18889 in front of a mock engine on :18888.
The mock answers any request that carries "loop_guard_stop": true with a reasoning-loop stop (finish_reason
content_filter + error.code reasoning_loop, as zig/src/server/loop_stop.zig emits) and any other request with a normal
answer. Every body the mock receives is recorded, so the fallback body can be checked field by field.
The copy writes its cluster state to a scratch path (not /dev/shm/dgx_cluster_state, which the governor reads), its
audit to a scratch file and its cold-KV dir to scratch, so production state is untouched.
usage: run_loop_fallback_mock.py OUT_DIR
"""
import http.server, json, os, shutil, socketserver, subprocess, sys, threading, time, urllib.request

OUT = os.path.abspath(sys.argv[1])
os.makedirs(OUT, exist_ok=True)
SRC = "/home/joseyarashio/spark-fastfail-proxy"
WORK = os.path.join(OUT, "proxy_copy")
MOCK_PORT, PROXY_PORT = 18888, 18889
MODEL = "DeepSeek-V4.1-Flash-1017-TF"
received = []


def sse(obj):
    return ("data: " + json.dumps(obj) + "\n\n").encode()


class Mock(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def do_GET(self):
        body = json.dumps({"object": "list", "data": [{"id": MODEL, "object": "model"}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        received.append(body)
        looping = body.get("loop_guard_stop") is True
        stream = bool(body.get("stream"))
        if stream:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Connection", "close")
            self.end_headers()
            base = {"id": "mock", "object": "chat.completion.chunk", "model": MODEL}
            self.wfile.write(sse({**base, "choices": [{"index": 0, "delta": {"role": "assistant"}}]}))
            if looping:
                for _ in range(5):
                    self.wfile.write(sse({**base, "choices": [{"index": 0, "delta": {"reasoning_content": "wait, let me recheck. "}}]}))
                self.wfile.write(sse({**base, "choices": [{"index": 0, "delta": {}, "finish_reason": "content_filter"}],
                                      "error": {"message": "loop", "type": "server_error", "param": None, "code": "reasoning_loop"},
                                      "tensorfold": {"loop": {"stopped": True, "period": 7}}}))
            else:
                self.wfile.write(sse({**base, "choices": [{"index": 0, "delta": {"content": "FALLBACK_ANSWER"}}]}))
                self.wfile.write(sse({**base, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                                      "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7}}))
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
            self.close_connection = True
            return
        if looping:
            out = {"id": "mock", "object": "chat.completion", "model": MODEL,
                   "choices": [{"index": 0, "message": {"role": "assistant", "content": "", "reasoning_content": "wait, wait"},
                                "finish_reason": "content_filter"}],
                   "error": {"message": "loop", "type": "server_error", "param": None, "code": "reasoning_loop"}}
        else:
            out = {"id": "mock", "object": "chat.completion", "model": MODEL,
                   "choices": [{"index": 0, "message": {"role": "assistant", "content": "FALLBACK_ANSWER"}, "finish_reason": "stop"}],
                   "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7}}
        b = json.dumps(out).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)


class TServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def prepare_copy():
    shutil.rmtree(WORK, ignore_errors=True)
    os.makedirs(WORK)
    shutil.copy(f"{SRC}/cold_kv.py", WORK)
    src = open(f"{SRC}/proxy.py").read()
    for a, b in [("/dev/shm/dgx_cluster_state", os.path.join(WORK, "cluster_state"))]:
        assert a in src
        src = src.replace(a, b)
    open(f"{WORK}/proxy.py", "w").write(src)
    ck = open(f"{WORK}/cold_kv.py").read()
    ck = ck.replace('Path("/home/joseyarashio/.cache/dgx_cold_kv")', f'Path("{os.path.join(WORK, "cold_kv")}")')
    open(f"{WORK}/cold_kv.py", "w").write(ck)
    cfg = json.load(open(f"{SRC}/config.json"))
    cfg.update(upstream_url=f"http://127.0.0.1:{MOCK_PORT}", listen_port=PROXY_PORT)
    json.dump(cfg, open(f"{WORK}/config.json", "w"))


def call(body):
    req = urllib.request.Request(f"http://127.0.0.1:{PROXY_PORT}/v1/chat/completions", json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read().decode()
    if body.get("stream"):
        content, reasoning, fins, errs = "", "", [], []
        for line in raw.splitlines():
            if line.startswith("data: ") and line[6:].strip().startswith("{"):
                o = json.loads(line[6:])
                if o.get("error"):
                    errs.append(o["error"].get("code"))
                for ch in o.get("choices") or []:
                    content += (ch.get("delta") or {}).get("content") or ""
                    reasoning += (ch.get("delta") or {}).get("reasoning_content") or ""
                    if ch.get("finish_reason"):
                        fins.append(ch["finish_reason"])
        return {"content": content, "reasoning_chars": len(reasoning), "finishes": fins, "errors": errs,
                "done_count": raw.count("[DONE]")}
    o = json.loads(raw)
    ch = o["choices"][0]
    return {"content": ch["message"].get("content"), "finishes": [ch.get("finish_reason")],
            "errors": [o["error"]["code"]] if o.get("error") else [], "done_count": 0}


def main():
    prepare_copy()
    mock = TServer(("127.0.0.1", MOCK_PORT), Mock)
    threading.Thread(target=mock.serve_forever, daemon=True).start()
    env = dict(os.environ, SPARK_PROXY_AUDIT_LOG=os.path.join(OUT, "audit.jsonl"))
    proc = subprocess.Popen([f"{SRC}/.venv/bin/uvicorn", "proxy:app", "--host", "127.0.0.1", "--port", str(PROXY_PORT)],
                            cwd=WORK, env=env, stdout=open(os.path.join(OUT, "proxy.log"), "w"), stderr=subprocess.STDOUT)
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{PROXY_PORT}/proxy/status", timeout=1)
                break
            except Exception:
                time.sleep(0.5)
        time.sleep(4)  # model poll sets the limit
        msgs = [{"role": "user", "content": "hi"}]
        tools = [{"type": "function", "function": {"name": "read_file", "parameters": {"type": "object", "properties": {}}}}]
        cases = [
            # name, body, expect fallback (2 upstream bodies), expect content
            ("stream_high", {"messages": msgs, "reasoning_effort": "high", "max_tokens": 4000, "stream": True}, True),
            ("whole_high", {"messages": msgs, "reasoning_effort": "high", "max_tokens": 4000, "stream": False}, True),
            ("stream_tools_budget", {"messages": msgs, "reasoning_effort": "high", "max_tokens": 4000, "stream": True,
                                     "tools": tools, "thinking_budget": 2048}, True),
            ("alias_thinking_true", {"messages": msgs, "chat_template_kwargs": {"thinking": True}, "max_tokens": 4000, "stream": True}, True),
            ("alias_thinking_false", {"messages": msgs, "chat_template_kwargs": {"thinking": False}, "max_tokens": 4000, "stream": True}, False),
            ("effort_none", {"messages": msgs, "reasoning_effort": "none", "max_tokens": 4000, "stream": True}, False),
            ("client_loop_guard_false", {"messages": msgs, "reasoning_effort": "high", "max_tokens": 4000, "stream": True,
                                         "loop_guard_stop": False}, False),
        ]
        rows, ok_all = [], True
        for name, body, want_fb in cases:
            body = {"model": MODEL, **body}
            n0 = len(received)
            res = call(body)
            ups = received[n0:]
            first, fb = (ups[0] if ups else {}), (ups[1] if len(ups) > 1 else None)
            checks = {"upstream_calls": len(ups) == (2 if want_fb else 1)}
            if want_fb:
                checks.update({
                    "armed": first.get("loop_guard_stop") is True,
                    "fb_effort_none": fb is not None and fb.get("reasoning_effort") == "none",
                    "fb_enable_false": fb is not None and (fb.get("chat_template_kwargs") or {}).get("enable_thinking") is False,
                    "fb_no_budget": fb is not None and "thinking_budget" not in fb,
                    "fb_no_loop_guard": fb is not None and "loop_guard_stop" not in fb,
                    "fb_keeps_tools": fb is not None and fb.get("tools") == body.get("tools"),
                    "answer_spliced": res["content"] == "FALLBACK_ANSWER",
                    "single_final_finish": res["finishes"] == ["stop"],
                    "no_loop_error_to_client": "reasoning_loop" not in res["errors"],
                    "one_done": res["done_count"] == (1 if body.get("stream") else 0),
                })
            else:
                checks.update({"not_armed": "loop_guard_stop" not in first or first.get("loop_guard_stop") is False})
            ok = all(checks.values())
            ok_all &= ok
            row = {"case": name, "pass": ok, "checks": checks, "client": res}
            rows.append(row)
            print(json.dumps(row, ensure_ascii=False), flush=True)
        with open(os.path.join(OUT, "results.jsonl"), "w") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"mock loop fallback: {sum(r['pass'] for r in rows)}/{len(rows)} pass")
        sys.exit(0 if ok_all else 1)
    finally:
        proc.terminate()
        proc.wait(timeout=10)
        mock.shutdown()


if __name__ == "__main__":
    main()
