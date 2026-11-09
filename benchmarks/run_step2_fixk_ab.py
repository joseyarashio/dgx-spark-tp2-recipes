#!/usr/bin/env python3
"""Step 2 A/B: draft depth cap (TF_DS_FIX_K) vs default adaptive allocation.
Runs through 8889 so MS-DTC sees the load. Each sample records GPU clock and whether
any external (non-127.0.0.1) request hit the engine during the window; contaminated
samples are flagged and excluded from the medians."""
import concurrent.futures, json, statistics, subprocess, sys, time
sys.path.insert(0, "/home/joseyarashio/dgx-spark-tp2-recipes/benchmarks")
from run_full_eval import stream_chat, API_8889

LABEL = sys.argv[1]
REPS = int(sys.argv[2]) if len(sys.argv) > 2 else 5
OUT = f"/home/joseyarashio/dgx-spark-tp2-recipes/benchmarks/results/step2_fixk_{LABEL}.json"
CODE = "Write a complete, well-commented Python implementation of an LRU Cache using a doubly linked list and hash map, including thread-safety locks, type annotations, and a thorough unit test suite."
PROSE = "請詳細分析分散式大語言模型推論在雙節點 RoCEv2 網路架構下的通訊瓶頸、All-Reduce 延遲特性、Speculative Decoding 草稿驗證機制，以及 Unified Memory 架構下的記憶體管理策略。"

def clk():
    try:
        return int(subprocess.check_output(["nvidia-smi", "--query-gpu=clocks.gr", "--format=csv,noheader,nounits"]).decode().strip())
    except Exception:
        return -1

def external_since(t0):
    since = f"{max(1, int(time.time() - t0) + 2)}s"
    out = subprocess.run(["docker", "logs", "--since", since, "dsv41-rank0"], capture_output=True, text=True)
    lines = (out.stdout + out.stderr).splitlines()
    return sum(1 for l in lines if "POST /v1/" in l and "127.0.0.1" not in l)

def wait_idle(maxwait=120):
    t = time.time()
    while time.time() - t < maxwait:
        try:
            h = json.loads(subprocess.check_output(["curl", "-s", "http://127.0.0.1:8888/health"]))
            if h["live"]["connections"] == 0:
                return True
        except Exception:
            pass
        time.sleep(1)
    return False

def single(prompt, temp):
    wait_idle()
    t0 = time.time(); c0 = clk()
    r = stream_chat([{"role": "user", "content": prompt}], max_tokens=384, temperature=temp, seed=42, base_url=API_8889)
    c1 = clk()
    tf, sp = r.get("tensorfold", {}), r.get("speculative", {})
    return {"tps": tf.get("tokens_per_second", 0), "acc": sp.get("acceptance_rate", 0),
            "tpr": sp.get("tokens_per_round", 0), "rounds": sp.get("rounds", 0),
            "clk": [c0, c1], "external": external_since(t0), "status": r.get("status_code")}

def conc(c):
    wait_idle()
    t0 = time.time(); c0 = clk()
    ps = [CODE + f" // worker {i} {time.time_ns()}" for i in range(c)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=c) as ex:
        rs = list(ex.map(lambda p: stream_chat([{"role": "user", "content": p}], max_tokens=256, temperature=0.0, seed=42, base_url=API_8889), ps))
    wall = time.time() - t0
    toks = sum((r.get("usage") or {}).get("completion_tokens", 0) for r in rs)
    rounds = sum(r.get("speculative", {}).get("rounds", 0) for r in rs)
    acc = [r.get("speculative", {}).get("accepted", 0) for r in rs]
    dr = [r.get("speculative", {}).get("drafted", 0) for r in rs]
    return {"agg_tps": toks / wall if wall else 0, "wall": wall, "tokens": toks,
            "accept": sum(acc) / max(1, sum(dr)), "statuses": [r.get("status_code") for r in rs],
            "clk": [c0, clk()], "external": external_since(t0)}

res = {"label": LABEL, "time": time.strftime("%F %T"), "greedy_code": [], "sample_prose": [], "c4": [], "c8": []}
for i in range(REPS):
    res["greedy_code"].append(single(CODE, 0.0))
    res["sample_prose"].append(single(PROSE, 0.7))
for i in range(max(2, REPS // 2)):
    res["c4"].append(conc(4))
    res["c8"].append(conc(8))

def med(xs, k):
    clean = [x[k] for x in xs if x["external"] == 0]
    return (round(statistics.median(clean), 2) if clean else None, len(clean), len(xs))

res["summary"] = {
    "greedy_tps": med(res["greedy_code"], "tps"), "greedy_acc": med(res["greedy_code"], "acc"),
    "greedy_tpr": med(res["greedy_code"], "tpr"),
    "sample_tps": med(res["sample_prose"], "tps"),
    "c4_agg": med(res["c4"], "agg_tps"), "c8_agg": med(res["c8"], "agg_tps"),
}
json.dump(res, open(OUT, "w"), indent=2, ensure_ascii=False)
print(json.dumps({"label": LABEL, **res["summary"]}, ensure_ascii=False))
print("raw greedy:", [(round(x["tps"], 1), x["clk"], x["external"]) for x in res["greedy_code"]])
print("raw c8:", [(round(x["agg_tps"], 1), x["statuses"].count(200), x["external"]) for x in res["c8"]])
