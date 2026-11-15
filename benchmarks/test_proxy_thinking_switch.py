#!/usr/bin/env python3
"""Offline truth table: proxy _thinking_switch/_thinking_on must match the engine's thinkingFields
(zig/src/server/fields.zig) for a server started with --thinking. Run with the proxy venv python."""
import importlib.util, sys

sys.path.insert(0, "/home/joseyarashio/spark-fastfail-proxy")  # proxy imports its sibling cold_kv
spec = importlib.util.spec_from_file_location("proxy", "/home/joseyarashio/spark-fastfail-proxy/proxy.py")
assert spec is not None and spec.loader is not None
proxy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(proxy)

# (body, expected engine thinking on)
CASES = [
    ({}, True),
    ({"reasoning_effort": "none"}, False),
    ({"reasoning_effort": "low"}, True),
    ({"chat_template_kwargs": {"enable_thinking": True}}, True),
    ({"chat_template_kwargs": {"enable_thinking": False}}, False),
    ({"chat_template_kwargs": {"enable_thinking": None}}, False),       # present key, falsy
    ({"chat_template_kwargs": {"enable_thinking": 0}}, False),
    ({"chat_template_kwargs": {"thinking": True}}, True),
    ({"chat_template_kwargs": {"thinking": False}}, False),
    ({"chat_template_kwargs": {"thinking": {"type": "enabled"}}}, True),
    ({"chat_template_kwargs": {"thinking": {"type": "disabled"}}}, False),
    ({"chat_template_kwargs": {"thinking": "yes"}}, True),               # unknown alias value: ignored -> default on
    ({"chat_template_kwargs": {"enable_thinking": False, "thinking": True}}, False),
    ({"reasoning_effort": "none", "chat_template_kwargs": {"enable_thinking": True}}, True),
    ({"reasoning_effort": "high", "chat_template_kwargs": {"enable_thinking": False}}, False),
    ({"reasoning_effort": "none", "chat_template_kwargs": {"thinking": True}}, True),
    ({"chat_template_kwargs": {"reasoning_effort": "none"}}, False),
    ({"reasoning_effort": "high", "chat_template_kwargs": {"reasoning_effort": "none"}}, True),  # top-level first
    ({"chat_template_kwargs": {}}, True),                                 # empty kwargs = absent
    ({"chat_template_kwargs": "x"}, True),                                # non-object kwargs ignored
]
bad = 0
for body, want in CASES:
    got = proxy._thinking_on(body)
    ok = got == want
    bad += not ok
    print(("ok  " if ok else "FAIL"), body, "->", got, "want", want)
print(f"{len(CASES) - bad}/{len(CASES)} pass")
sys.exit(1 if bad else 0)
