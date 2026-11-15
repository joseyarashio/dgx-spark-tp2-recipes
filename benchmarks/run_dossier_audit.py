#!/usr/bin/env python3
"""Dual external critic (Claude Opus 5.5 + GPT-6 Astra, via OpenCodex :10100) on a self-contained dossier file.

usage: run_dossier_audit.py DOSSIER.md OUT_DIR [--opus-tokens 24000] [--astra-tokens 16000]
Writes OUT_DIR/critic_<model>.json and OUT_DIR/audit_report.md; prints finish reasons (a 'length' finish is flagged).
"""
import argparse, concurrent.futures, json, os, time, urllib.request

ap = argparse.ArgumentParser()
ap.add_argument("dossier")
ap.add_argument("out")
ap.add_argument("--opus-tokens", type=int, default=24000)
ap.add_argument("--astra-tokens", type=int, default=16000)
a = ap.parse_args()
os.makedirs(a.out, exist_ok=True)
CFG = json.load(open("/home/joseyarashio/.opencodex/config.json"))
KEY = CFG["apiKeys"][0]["key"]
URL = "http://127.0.0.1:10100/v1/chat/completions"
dossier = open(a.dossier).read()
SYS = ("You are an independent principal reviewer of LLM inference engines on bandwidth-bound unified-memory GPUs. "
       "Audit the supplied dossier critically. Use only numbers and code facts it contains; mark any inference as such. "
       "Challenge the measurement method, the cost model, statistical power, quality risk and whether the proposed next "
       "stage is worth doing at all. Answer in Traditional Chinese with 4 numbered sections: "
       "(1) 量測方法與數據盲點, (2) 可成立結論與過度推論, (3) 下一階段是否值得做與具體參數, (4) 驗收門檻與回退條件。")


def ask(spec):
    model, mt = spec
    body = {"model": model, "messages": [{"role": "system", "content": SYS}, {"role": "user", "content": dossier}],
            "max_tokens": mt, "temperature": 0.2}
    t0 = time.time()
    try:
        req = urllib.request.Request(URL, json.dumps(body).encode(), {"Content-Type": "application/json", "Authorization": f"Bearer {KEY}"})
        r = json.load(urllib.request.urlopen(req, timeout=900))
        ch = r["choices"][0]
        m = ch["message"]
        return {"model": model, "ok": True, "wall": round(time.time() - t0, 1), "finish": ch.get("finish_reason"),
                "usage": r.get("usage"), "content": m.get("content") or m.get("reasoning_content") or ""}
    except Exception as e:
        return {"model": model, "ok": False, "wall": round(time.time() - t0, 1), "error": repr(e)}


with concurrent.futures.ThreadPoolExecutor(2) as ex:
    reviews = list(ex.map(ask, [("anthropic/claude-opus-5-5", a.opus_tokens), ("gpt-6-astra", a.astra_tokens)]))
rep = [f"# External audit: {os.path.basename(a.dossier)}\n"]
for rv in reviews:
    json.dump(rv, open(os.path.join(a.out, f"critic_{rv['model'].replace('/', '_')}.json"), "w"), ensure_ascii=False, indent=1)
    rep.append(f"\n## {rv['model']} (ok={rv['ok']}, finish={rv.get('finish')}, wall={rv['wall']}s)\n")
    rep.append(rv.get("content") or rv.get("error") or "")
open(os.path.join(a.out, "audit_report.md"), "w").write("\n".join(rep))
print([(rv["model"], rv["ok"], rv.get("finish"), len(rv.get("content") or "")) for rv in reviews])
