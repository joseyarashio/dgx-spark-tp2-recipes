#!/usr/bin/env python3
"""Step 4 premise probe: how much NVMe (Engram O_DIRECT AIO) traffic a decode run generates, and what latency the
device shows while serving it. Samples /proc/diskstats for nvme0n1 around a greedy single stream and a C8 burst."""
import concurrent.futures, json, sys, time
sys.path.insert(0, "/home/joseyarashio/dgx-spark-tp2-recipes/benchmarks")
from run_full_eval import stream_chat, API_8889

CODE = "Write a complete, well-commented Python implementation of an LRU Cache using a doubly linked list and hash map, including thread-safety locks, type annotations, and a thorough unit test suite."

def disk():
    for l in open("/proc/diskstats"):
        p = l.split()
        if p[2] == "nvme0n1":
            # reads completed, sectors read, ms reading, ..., ms doing io (p[12]), weighted ms (p[13])
            return {"r": int(p[3]), "sect": int(p[5]), "r_ms": int(p[6]), "io_ms": int(p[12])}

def run(label, fn):
    d0, t0 = disk(), time.time()
    out = fn()
    d1, t1 = disk(), time.time()
    dr = d1["r"] - d0["r"]
    res = {"label": label, "wall_s": round(t1 - t0, 3), "reads": dr, "mib": round((d1["sect"] - d0["sect"]) * 512 / 2**20, 2),
           "reads_per_s": round(dr / (t1 - t0), 1), "avg_read_ms": round((d1["r_ms"] - d0["r_ms"]) / max(1, dr), 4),
           "device_busy_pct": round(100 * (d1["io_ms"] - d0["io_ms"]) / ((t1 - t0) * 1000), 2), **out}
    print(json.dumps(res, ensure_ascii=False))
    return res

def single():
    r = stream_chat([{"role": "user", "content": CODE}], max_tokens=384, temperature=0.0, seed=42, base_url=API_8889)
    sp = r.get("speculative", {})
    return {"tps": round(r.get("tensorfold", {}).get("tokens_per_second", 0), 2), "rounds": sp.get("rounds", 0),
            "tokens": (r.get("usage") or {}).get("completion_tokens", 0)}

def c8():
    ps = [CODE + f" // w{i} {time.time_ns()}" for i in range(8)]
    with concurrent.futures.ThreadPoolExecutor(8) as ex:
        rs = list(ex.map(lambda p: stream_chat([{"role": "user", "content": p}], max_tokens=256, temperature=0.0, seed=42, base_url=API_8889), ps))
    return {"tokens": sum((r.get("usage") or {}).get("completion_tokens", 0) for r in rs),
            "rounds_sum": sum(r.get("speculative", {}).get("rounds", 0) for r in rs)}

idle = run("idle_10s", lambda: (time.sleep(10), {})[1])
out = [idle] + [run(f"single_{i}", single) for i in range(3)] + [run(f"c8_{i}", c8) for i in range(2)]
json.dump(out, open("/home/joseyarashio/dgx-spark-tp2-recipes/benchmarks/results/step4_engram_io_probe.json", "w"), indent=2)
