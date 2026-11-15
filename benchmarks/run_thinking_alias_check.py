#!/usr/bin/env python3
"""Live check of the proxy's thinking-switch handling vs what the engine actually does (via :8889).
Each case sends one short request and reads the proxy audit record (effort_rewritten, loop_fallback armed via the
engine's `loop_guard_stop` field is not visible, so we record reasoning tokens) plus the reply's reasoning/content.
usage: run_thinking_alias_check.py LABEL OUT.jsonl
"""
import json, sys, time, urllib.request
API = "http://127.0.0.1:8889/v1/chat/completions"
AUDIT = "/home/joseyarashio/.cache/spark-proxy-audit/completions.jsonl"
LABEL, OUT = sys.argv[1], sys.argv[2]
Q = "What is 17 * 23? Answer with the number only."
CASES = [
    # (name, extra body, max_tokens, expect_rewrite, expect_thinking)
    ("plain_120", {}, 120, True, False),
    ("enable_true_120", {"chat_template_kwargs": {"enable_thinking": True}}, 120, False, True),
    ("enable_false_120", {"chat_template_kwargs": {"enable_thinking": False}}, 120, True, False),
    ("alias_true_120", {"chat_template_kwargs": {"thinking": True}}, 120, False, True),
    ("alias_obj_enabled_120", {"chat_template_kwargs": {"thinking": {"type": "enabled"}}}, 120, False, True),
    ("alias_false_120", {"chat_template_kwargs": {"thinking": False}}, 120, True, False),
    ("enable_false_alias_true_120", {"chat_template_kwargs": {"enable_thinking": False, "thinking": True}}, 120, True, False),
    ("effort_none_enable_true_400", {"reasoning_effort": "none", "chat_template_kwargs": {"enable_thinking": True}}, 400, False, True),
    ("kwargs_effort_low_120", {"chat_template_kwargs": {"reasoning_effort": "low"}}, 120, True, False),
    ("plain_400", {}, 400, False, True),
]


def tail_audit(after_ts):
    recs = []
    with open(AUDIT) as f:
        for line in f.readlines()[-50:]:
            try:
                d = json.loads(line)
            except Exception:
                continue
            if d.get("ts", 0) >= after_ts and d.get("client_ip") == "127.0.0.1":
                recs.append(d)
    return recs


def run(name, extra, mt, exp_rw, exp_think):
    body = {"model": "DeepSeek-V4.1-Flash-1017-TF", "messages": [{"role": "user", "content": Q}], "max_tokens": mt,
            "temperature": 0.0, "seed": 42, "stream": False}
    body.update(extra)
    t0 = time.time()
    req = urllib.request.Request(API, json.dumps(body).encode(), {"Content-Type": "application/json", "X-Priority": "0"})
    with urllib.request.urlopen(req, timeout=300) as r:
        d = json.loads(r.read())
    m = d["choices"][0]["message"]
    reasoning = m.get("reasoning_content") or ""
    content = m.get("content") or ""
    time.sleep(0.5)
    aud = [a for a in tail_audit(t0 - 0.5) if a.get("max_tokens") == mt]
    a = aud[-1] if aud else {}
    rw = bool(a.get("effort_rewritten"))
    thinking = len(reasoning) > 0
    row = {"label": LABEL, "case": name, "max_tokens": mt, "effort_rewritten": rw, "audit_effort": a.get("effort"),
           "thinking": thinking, "reasoning_chars": len(reasoning), "content": content[:80],
           "finish": d["choices"][0].get("finish_reason"), "usage": d.get("usage"),
           "thinking_on_audit": a.get("thinking_on"), "expect_rewrite": exp_rw, "expect_thinking": exp_think,
           "pass": rw == exp_rw and thinking == exp_think}
    print(json.dumps(row, ensure_ascii=False), flush=True)
    return row


rows = [run(*c) for c in CASES]
with open(OUT, "a") as f:
    for r in rows:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
print(f"{LABEL}: {sum(r['pass'] for r in rows)}/{len(rows)} pass")
