#!/usr/bin/env python3
"""Decode gate: 9-prompt code sweep (median) + C2/C4/C8 ladder, against a stored baseline.

Why: a single prompt's greedy tok/s and MTP acceptance follow that prompt's text. After the
2026-11-11 Engram token-map fix, the LRU prompt's output diverged at char 89 and its acceptance
fell 0.80 -> 0.74 (accepted 281 -> 279, drafted 350 -> 377), while the pooled acceptance over 89
paired requests rose 0.772 -> 0.786. Across 9 code prompts acceptance spans 0.64-0.80 and greedy
80-96 tok/s, so one prompt swings about +/-8%. Judge the median over the sweep, plus concurrency.

Runs through 8889 (MS-DTC sees the load). Waits for an idle window (no live connection, no
external POST for 60 s) before each sample; samples with external traffic are dropped.

usage: run_decode_gate.py [--reps N] [--label L] [--write-baseline]
exit 0 = pass, 1 = fail, 2 = inconclusive (too few clean samples)
"""
import argparse, concurrent.futures, json, os, statistics, subprocess, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from run_full_eval import stream_chat, API_8889  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
BASELINE = os.path.join(HERE, "gates", "decode_gate_baseline.json")
IDLE_S = 60
TOPICS = ["an LRU cache with a doubly linked list", "a thread-safe bounded blocking queue", "a trie with prefix search and deletion",
          "a min-heap priority queue with decrease-key", "a token-bucket rate limiter", "an interval tree with overlap queries",
          "a consistent-hash ring with virtual nodes", "a write-ahead log with checksums and replay"]
LRU = ("Write a complete, well-commented Python implementation of an LRU Cache using a doubly linked list and hash map, "
       "including thread-safety locks, type annotations, and a thorough unit test suite.")
SWEEP = [LRU] + [f"Write a complete, well-commented Python implementation of {t}, with type annotations and unit tests." for t in TOPICS]
# Gate = fraction of the stored baseline median (scale-free: re-baseline when the model/recipe changes on purpose).
FLOOR = {"sweep_greedy_tps": 0.95, "sweep_mtp_accept": 0.95, "c2_agg": 0.95, "c4_agg": 0.95, "c8_agg": 0.95}


def clk():
    try:
        return int(subprocess.check_output(["nvidia-smi", "--query-gpu=clocks.gr", "--format=csv,noheader,nounits"]).decode().strip())
    except Exception:
        return -1


def external_since(t0):
    since = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(t0 - 1))
    j = subprocess.run(["journalctl", "--user", "-u", "spark-fastfail-proxy", "--since", since, "--no-pager", "-o", "cat"],
                       capture_output=True, text=True).stdout.splitlines()
    n = sum(1 for l in j if "POST /v1/" in l and "127.0.0.1" not in l)
    d = subprocess.run(["docker", "logs", "--since", f"{max(1, int(time.time() - t0) + 2)}s", "dsv41-rank0"], capture_output=True, text=True)
    return n + sum(1 for l in (d.stdout + d.stderr).splitlines() if "POST /v1/" in l and "127.0.0.1" not in l)


def live_connections():
    try:
        return json.loads(subprocess.check_output(["curl", "-s", "-m", "3", "http://127.0.0.1:8888/health"]))["live"]["connections"]
    except Exception:
        return -1


def wait_idle(maxwait=1800):
    t = time.time()
    while time.time() - t < maxwait:
        if live_connections() == 0 and external_since(time.time() - IDLE_S) == 0:
            return True
        time.sleep(5)
    return False


def single(prompt):
    idle = wait_idle()
    t0 = time.time(); c0 = clk()
    r = stream_chat([{"role": "user", "content": prompt}], max_tokens=384, temperature=0.0, seed=42, base_url=API_8889)
    s, tf = r.get("speculative", {}), r.get("tensorfold", {})
    toks = (r.get("usage") or {}).get("completion_tokens", 0)
    return {"tps": tf.get("tokens_per_second", 0), "accepted": s.get("accepted", 0), "drafted": s.get("drafted", 0),
            "rounds": s.get("rounds", 0), "tokens": toks, "sha": tf.get("token_sha"), "clk": [c0, clk()],
            "external": external_since(t0), "idle_before": idle, "status": r.get("status_code")}


def conc(c):
    idle = wait_idle()
    t0 = time.time(); c0 = clk()
    ps = [f"Write a complete, well-commented Python implementation of {TOPICS[i % len(TOPICS)]}, with type annotations and unit tests. // run {time.time_ns()}" for i in range(c)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=c) as ex:
        rs = list(ex.map(lambda p: stream_chat([{"role": "user", "content": p}], max_tokens=384, temperature=0.0, seed=42, base_url=API_8889), ps))
    wall = time.time() - t0
    toks = [(r.get("usage") or {}).get("completion_tokens", 0) for r in rs]
    return {"agg_tps": sum(toks) / wall if wall else 0, "wall": wall, "tokens": toks,
            "accept": sum(r.get("speculative", {}).get("accepted", 0) for r in rs) / max(1, sum(r.get("speculative", {}).get("drafted", 0) for r in rs)),
            "statuses": [r.get("status_code") for r in rs], "clk": [c0, clk()], "external": external_since(t0), "idle_before": idle}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=1, help="sweep repetitions (each = 9 prompts) and ladder repetitions")
    ap.add_argument("--label", default=time.strftime("%Y%m%d_%H%M%S"))
    ap.add_argument("--write-baseline", action="store_true")
    a = ap.parse_args()

    res = {"label": a.label, "time": time.strftime("%F %T"), "sweep": [], "c2": [], "c4": [], "c8": []}
    for rep in range(a.reps):
        for i, p in enumerate(SWEEP):
            x = single(p); x["prompt"] = i; x["rep"] = rep
            res["sweep"].append(x)
            print("sweep", rep, i, round(x["tps"], 1), f"{x['accepted']}/{x['drafted']}", "ext", x["external"], flush=True)
    for rep in range(max(1, a.reps)):
        for c in (2, 4, 8):
            x = conc(c); res[f"c{c}"].append(x)
            ok = sum(1 for s, t in zip(x["statuses"], x["tokens"]) if s == 200 and t > 1)
            print(f"c{c}", rep, round(x["agg_tps"], 1), f"{ok}/{c} streams ok", "ext", x["external"], flush=True)

    clean = [x for x in res["sweep"] if x["external"] == 0 and x["status"] == 200 and x["tokens"] > 1]
    # per-prompt median over reps, then median over prompts (each prompt weighs the same)
    per_prompt = {}
    for x in clean:
        per_prompt.setdefault(x["prompt"], []).append(x)
    tps = [statistics.median(v["tps"] for v in xs) for xs in per_prompt.values()]
    acc = [statistics.median(v["accepted"] / max(1, v["drafted"]) for v in xs) for xs in per_prompt.values()]
    s = {"sweep_prompts_clean": len(per_prompt), "sweep_greedy_tps": round(statistics.median(tps), 2) if tps else None,
         "sweep_mtp_accept": round(statistics.median(acc), 4) if acc else None,
         "sweep_greedy_min": round(min(tps), 2) if tps else None, "sweep_greedy_max": round(max(tps), 2) if tps else None}
    for c in (2, 4, 8):
        xs = [x for x in res[f"c{c}"] if x["external"] == 0 and all(t > 1 for t in x["tokens"]) and set(x["statuses"]) == {200}]
        s[f"c{c}_agg"] = round(statistics.median(x["agg_tps"] for x in xs), 2) if xs else None
        s[f"c{c}_streams_ok"] = all(all(t > 1 for t in x["tokens"]) and set(x["statuses"]) == {200} for x in res[f"c{c}"])
    res["summary"] = s

    verdict, checks = 0, {}
    if s["sweep_prompts_clean"] < 7 or any(s[f"c{c}_agg"] is None for c in (2, 4, 8)):
        verdict = 2
    if a.write_baseline:
        os.makedirs(os.path.dirname(BASELINE), exist_ok=True)
        json.dump({"label": a.label, "time": res["time"], **{k: s[k] for k in FLOOR}}, open(BASELINE, "w"), indent=2)
        print("baseline written:", BASELINE)
    elif os.path.exists(BASELINE):
        b = json.load(open(BASELINE))
        for k, f in FLOOR.items():
            need = round(b[k] * f, 4)
            checks[k] = {"value": s[k], "need": need, "baseline": b[k], "ok": s[k] is not None and s[k] >= need}
        if verdict == 0 and not all(v["ok"] for v in checks.values()):
            verdict = 1
        if not all(s[f"c{c}_streams_ok"] for c in (2, 4, 8)):
            verdict = 1
    res["checks"] = checks
    res["verdict"] = {0: "pass", 1: "fail", 2: "inconclusive"}[verdict]
    out = os.path.join(HERE, "results", f"decode_gate_{a.label}.json")
    json.dump(res, open(out, "w"), indent=2, ensure_ascii=False)
    print(json.dumps({"verdict": res["verdict"], **s, "checks": checks}, ensure_ascii=False))
    sys.exit(verdict)


if __name__ == "__main__":
    main()
