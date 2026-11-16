#!/usr/bin/env python3
"""External dual review of the 2026-11-16 requirement list (v1.2.9 merge etc.).
Sends requirements.md + dossier parts to anthropic/claude-opus-5-5 and gpt-6-astra via OpenCodex :10100."""
import concurrent.futures, json, time, urllib.request
from pathlib import Path

D = Path(__file__).resolve().parent
CFG = json.load(open("/home/joseyarashio/.opencodex/config.json"))
KEY = CFG["apiKeys"][0]["key"]
URL = "http://127.0.0.1:10100/v1/chat/completions"
REVIEWERS = [("anthropic/claude-opus-5-5", 64000), ("gpt-6-astra", 32000)]

doc = "\n\n".join([
    (D / "requirements.md").read_text(),
    "# Evidence dossier part 1\n" + (D / "dossier_part1.md").read_text(),
    "# Evidence dossier part 2\n" + (D / "dossier_part2.md").read_text(),
])
(D / "dossier_full.md").write_text(doc)

PROMPT = """You are an independent reviewer for a production LLM serving cluster (two DGX Spark GB10 nodes, DeepSeek-V4.1-Flash TP=2, native Zig TensorFold fork). Review the requirement list R1-R8 against the evidence dossier.

Rules:
- Use only facts, numbers, code and quotes in the dossier. If a claim needs data the dossier does not have, say "unverified" and name the exact command or file that would settle it.
- Challenge the operator's position on every item. Say agree / disagree / partly, with the evidence line.
- The owner's rules: DeepSeek only; each change is its own stage with full regression (30-question bank, decode gate, 1-hour marathon), keep only if positive, roll back if negative; no hardcoded slot counts or thresholds.

Output, in Traditional Chinese (繁體中文), plain technical language, no praise:
1. 逐項審查 R1-R8: verdict (agree/disagree/partly), the key evidence, what the operator missed or got wrong.
2. 對「v1.2.9 值得合併」的最終判斷: merge wholesale / cherry-pick / skip, and what would change your mind (concrete evidence).
3. 風險: anything in the plan that could hurt production (kernel/OTA, memory, quality), with mitigation.
4. 優先順序: at most 8 actions, ordered, each with its acceptance test and rollback.
"""

def ask(spec):
    model, max_tok = spec
    body = {"model": model, "max_tokens": max_tok, "temperature": 0.2,
            "messages": [{"role": "system", "content": PROMPT}, {"role": "user", "content": doc}]}
    t0 = time.time()
    req = urllib.request.Request(URL, json.dumps(body, ensure_ascii=False).encode(),
                                 {"Content-Type": "application/json", "Authorization": f"Bearer {KEY}"})
    try:
        r = json.load(urllib.request.urlopen(req, timeout=1200))
        ch = r["choices"][0]; m = ch["message"]
        return {"model": model, "ok": True, "wall": round(time.time() - t0, 1), "finish": ch.get("finish_reason"),
                "usage": r.get("usage"), "content": m.get("content") or m.get("reasoning_content") or ""}
    except Exception as e:
        return {"model": model, "ok": False, "wall": round(time.time() - t0, 1), "error": repr(e)}

print("dossier chars", len(doc), flush=True)
with concurrent.futures.ThreadPoolExecutor(2) as ex:
    for rv in ex.map(ask, REVIEWERS):
        tag = rv["model"].replace("/", "_")
        (D / f"{tag}.json").write_text(json.dumps(rv, ensure_ascii=False, indent=2))
        (D / f"{tag}.md").write_text(rv.get("content") or rv.get("error") or "")
        print(rv["model"], rv["ok"], rv.get("finish"), rv["wall"], len(rv.get("content") or ""), flush=True)
