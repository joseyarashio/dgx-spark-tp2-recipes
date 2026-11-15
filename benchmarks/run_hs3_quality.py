#!/usr/bin/env python3
"""Hibana port S3: paired quality under forced concurrency. Runs a dataset closed-loop at C concurrent distinct prompts
through 8889 (greedy, seed 42), saves every answer, scores it, and records /metrics MTP deltas for the run window.

usage: run_hs3_quality.py LABEL --set gsm8k|aime [--n N] [--offset K] [--conc 8] [--thinking] [--max-tokens M]
out: results/hibana_port/s3/<LABEL>.jsonl (+ <LABEL>.summary.json)
"""
import argparse, concurrent.futures, json, os, random, re, sys, threading, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from run_full_eval import stream_chat, API_8889  # noqa: E402

OUT = os.path.join(HERE, "results", "hibana_port", "s3")


def metrics():
    t = urllib.request.urlopen("http://127.0.0.1:8888/metrics", timeout=10).read().decode()
    m = {}
    for l in t.splitlines():
        if l.startswith("tensorfold:") and " " in l and "{" not in l:
            k, v = l.split(" ", 1)
            m[k] = float(v)
    return m


def load(name, n, off):
    if name == "gsm8k":
        rows = [json.loads(l) for l in open(os.path.join(HERE, "data", "gsm8k_test.jsonl"))]
        out = []
        for i, r in enumerate(rows):
            ans = r["answer"].split("####")[-1].strip().replace(",", "")
            out.append({"id": f"gsm{i}", "q": r["question"] + "\nSolve step by step, then give the final answer as \\boxed{N}.", "gold": ans})
        return out[off:off + n]
    rows = json.load(open(os.path.join(HERE, "data", "aime2024.json")))
    return [{"id": r["id"], "q": r["problem"] + "\nGive the final answer as \\boxed{N}.", "gold": str(r["answer"]).strip()} for r in rows][off:off + n]


def extract(text):
    m = re.findall(r"\\boxed\{([^{}]*)\}", text or "")
    if not m:
        nums = re.findall(r"-?\d[\d,]*\.?\d*", text or "")
        return nums[-1].replace(",", "").rstrip(".") if nums else None
    v = m[-1].replace(",", "").replace("$", "").strip()
    return v


def same(a, gold):
    if a is None:
        return False
    try:
        return abs(float(a) - float(gold)) < 1e-6
    except ValueError:
        return a.strip() == gold.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("label")
    ap.add_argument("--set", default="gsm8k")
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--conc", type=int, default=8)
    ap.add_argument("--thinking", action="store_true")
    ap.add_argument("--max-tokens", type=int, default=768)
    ap.add_argument("--shuffle", type=int, default=1, help="order seed (same seed = same co-scheduling order)")
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    items = load(a.set, a.n, a.offset)
    order = list(range(len(items)))
    random.Random(a.shuffle).shuffle(order)
    path = os.path.join(OUT, a.label + ".jsonl")
    lock = threading.Lock()
    f = open(path, "w")
    m0 = metrics()
    t0 = time.time()

    def run(i):
        it = items[i]
        r = stream_chat([{"role": "user", "content": it["q"]}], max_tokens=a.max_tokens, temperature=0.0, seed=42,
                        enable_thinking=a.thinking, base_url=API_8889, timeout=3600,
                        extra_headers={"X-Priority": "2"})
        ans = extract(r.get("content"))
        u = r.get("usage") or {}
        rec = {"id": it["id"], "gold": it["gold"], "pred": ans, "ok": same(ans, it["gold"]), "status": r.get("status_code"),
               "finish": r.get("finish_reason"), "completion_tokens": u.get("completion_tokens"),
               "reasoning_len": r.get("reasoning_len"), "content": r.get("content"), "wall": r.get("wall_seconds"),
               "spec": r.get("speculative")}
        with lock:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
        return rec

    with concurrent.futures.ThreadPoolExecutor(a.conc) as ex:
        recs = list(ex.map(run, order))
    m1 = metrics()
    dt = time.time() - t0
    d = {k: m1.get(k, 0) - m0.get(k, 0) for k in ("tensorfold:mtp_drafted_total", "tensorfold:mtp_accepted_total", "tensorfold:generation_tokens_total", "tensorfold:decode_rounds_total")}
    s = {"label": a.label, "set": a.set, "n": len(recs), "correct": sum(r["ok"] for r in recs),
         "status_ok": sum(r["status"] == 200 for r in recs), "finish_length": sum(r["finish"] == "length" for r in recs),
         "mean_tokens": sum(r["completion_tokens"] or 0 for r in recs) / max(1, len(recs)), "wall_s": round(dt, 1),
         "gen_tok_s": round(d["tensorfold:generation_tokens_total"] / dt, 2),
         "mtp_accept": round(d["tensorfold:mtp_accepted_total"] / max(1, d["tensorfold:mtp_drafted_total"]), 4),
         "tokens_per_round": round(d["tensorfold:generation_tokens_total"] / max(1, d["tensorfold:decode_rounds_total"]), 3),
         "metrics_delta": d}
    json.dump(s, open(os.path.join(OUT, a.label + ".summary.json"), "w"), indent=1)
    print(json.dumps(s))


if __name__ == "__main__":
    main()
