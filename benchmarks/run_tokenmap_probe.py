#!/usr/bin/env python3
"""Short correctness probe for the Engram token-map bug: greedy questions whose right answer is
'yes, spelled correctly' plus the LOW_HIT-style code review that looped. Prints a pass count."""
import json, re, sys, urllib.request, os
API = os.environ.get("API", "http://127.0.0.1:8888/v1/chat/completions")
LOOP = re.compile(r"(.{20,600}?)\1{4,}", re.S)
CODE = """```python
class ClusterCoordinator_a_0:
    def __init__(self, node_id: int = 0):
        self.node_id = node_id
        self.state = 'INITIALIZED'

    async def synchronize_state(self, peer_ip: str, timeout_ms: int = 250):
        if not peer_ip.startswith('10.100.'):
            raise ValueError('Invalid cluster CIDR subnet')
        return True
```"""
Q = [
    ("init_yes", "In Python, is `__init__` spelled correctly in `def __init__(self):`? Answer yes or no, then one sentence.", r"^\W*yes"),
    ("three_yes", CODE + "\nAre `__init__`, `async def` and `startswith` all spelled correctly? Answer with one word: yes or no.", r"^\W*yes"),
    ("review", CODE + "\nReview this class in at most 5 bullet points.", None),
    ("name_main", "What does `if __name__ == \"__main__\":` do in Python? One sentence.", r"__name__"),
    ("repr", "Is `__repr__` a valid Python dunder method name? Answer yes or no.", r"^\W*yes"),
]
ok = 0
for name, p, want in Q:
    body = {"model": "current", "messages": [{"role": "user", "content": p}], "max_tokens": 400, "temperature": 0,
            "chat_template_kwargs": {"enable_thinking": False}}
    d = json.load(urllib.request.urlopen(urllib.request.Request(API, json.dumps(body).encode(), {"Content-Type": "application/json"}), timeout=300))
    c = d["choices"][0]["message"]["content"] or ""
    loop = bool(LOOP.search(c))
    bad = bool(re.search(r"(misspel|typo|should be `__init__`|is not a (real )?dunder|is wrong)", c, re.I))
    good = (not loop) and (not bad) and (want is None or re.search(want, c.strip(), re.I | re.M) is not None)
    ok += good
    print(f"{'PASS' if good else 'FAIL'} {name:10s} loop={loop} bad={bad} | {c.strip()[:160]!r}")
print(f"probe {ok}/{len(Q)}")
