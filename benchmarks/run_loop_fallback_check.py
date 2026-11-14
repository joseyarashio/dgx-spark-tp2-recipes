#!/usr/bin/env python3
"""Functional check of the proxy's reasoning-loop fallback (engine per-request loop_guard_stop + proxy re-send).

Cases (all via :8889):
  1. stream, looping prompt (thinking on)      -> engine stops, proxy splices an effort=none answer: finish stop, content
  2. whole reply, looping prompt               -> same, as one chat.completion JSON
  3. stream, looping prompt, 1 tool offered    -> fallback keeps tools; answer or tool call, never content_filter
  4. stream, normal prompt                     -> untouched: no fallback, normal stop
  5. stream, looping prompt, effort none       -> no gate at all (thinking off)
usage: run_loop_fallback_check.py OUT.jsonl
"""
import json, sys, time, urllib.request

API = "http://127.0.0.1:8889/v1/chat/completions"
OUT = sys.argv[1]
LOOP = "Output exactly 1500 copies of the token 'ha' separated by single spaces, nothing else."
TOOL = [{"type": "function", "function": {"name": "read_file", "description": "Read a file.",
                                          "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}}]


def call(name, prompt, stream=True, effort="high", tools=None):
    body = {"model": "DeepSeek-V4.1-Flash-1017-TF", "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 4000, "temperature": 0.0, "seed": 42, "reasoning_effort": effort, "stream": stream}
    if stream:
        body["stream_options"] = {"include_usage": True}
    if tools:
        body["tools"] = tools
    req = urllib.request.Request(API, json.dumps(body).encode(), {"Content-Type": "application/json", "X-Priority": "2"})
    t0 = time.time()
    fin, content, reasoning, tcs, err, loop, n_events, roles = None, "", "", [], None, None, 0, 0
    with urllib.request.urlopen(req, timeout=900) as resp:
        if stream:
            for raw in resp:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                d = line[5:].strip()
                if d == "[DONE]":
                    n_events += 1
                    continue
                o = json.loads(d)
                n_events += 1
                if o.get("error"):
                    err = o["error"]
                if (o.get("tensorfold") or {}).get("loop"):
                    loop = o["tensorfold"]["loop"]
                for ch in o.get("choices") or []:
                    dl = ch.get("delta") or {}
                    if dl.get("role"):
                        roles += 1
                    content += dl.get("content") or ""
                    reasoning += dl.get("reasoning_content") or ""
                    tcs += [t.get("function", {}).get("name") for t in dl.get("tool_calls") or [] if t.get("function", {}).get("name")]
                    if ch.get("finish_reason"):
                        fin = ch["finish_reason"]
        else:
            o = json.load(resp)
            ch = o["choices"][0]
            fin, err, loop = ch.get("finish_reason"), o.get("error"), (o.get("tensorfold") or {}).get("loop")
            content = ch["message"].get("content") or ""
            reasoning = ch["message"].get("reasoning_content") or ""
            tcs = [t["function"]["name"] for t in ch["message"].get("tool_calls") or []]
    row = {"case": name, "stream": stream, "finish": fin, "content_chars": len(content), "reasoning_chars": len(reasoning),
           "tool_calls": tcs, "error": err, "tensorfold_loop": loop, "events": n_events, "role_deltas": roles,
           "wall_s": round(time.time() - t0, 1), "content_head": content[:120]}
    with open(OUT, "a") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(json.dumps(row, ensure_ascii=False), flush=True)


call("1_stream_loop", LOOP)
call("2_whole_loop", LOOP, stream=False)
call("3_stream_loop_tool", LOOP, tools=TOOL)
call("4_stream_normal", "In two sentences, what is a mutex?")
call("5_stream_loop_effort_none", LOOP, effort="none")
