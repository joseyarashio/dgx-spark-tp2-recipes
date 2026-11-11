#!/usr/bin/env python3
"""Repeat the OmniBench 32K cut-in probe N times with the idle/external-traffic gate.

Same payload as run_omni_eval.test_concurrency cut_in_32k, plus a per-rep nonce so the
long prompt is cold every rep (otherwise reps 2..N hit the RAM prompt cache).
usage: run_cutin_reps.py <label> [reps]
"""
import concurrent.futures, json, statistics, sys, time
sys.path.insert(0, "/home/joseyarashio/dgx-spark-tp2-recipes/benchmarks")
from run_omni_eval import stream_chat, API_8889
import subprocess

# idle / external-traffic gate copied from run_round_rows_ab.py (that module runs on import)
def clk():
    try:
        return int(subprocess.check_output(["nvidia-smi", "--query-gpu=clocks.gr", "--format=csv,noheader,nounits"]).decode().strip())
    except Exception:
        return -1


def external_since(t0):
    """Non-local POSTs since t0 on the proxy journal and on the engine log."""
    since = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(t0 - 1))
    j = subprocess.run(["journalctl", "--user", "-u", "spark-fastfail-proxy", "--since", since, "--no-pager", "-o", "cat"],
                       capture_output=True, text=True).stdout.splitlines()
    n = sum(1 for l in j if "POST /v1/" in l and "127.0.0.1" not in l)
    d = subprocess.run(["docker", "logs", "--since", f"{max(1, int(time.time() - t0) + 2)}s", "dsv41-rank0"], capture_output=True, text=True)
    n += sum(1 for l in (d.stdout + d.stderr).splitlines() if "POST /v1/" in l and "127.0.0.1" not in l)
    return n


def live_connections():
    try:
        return json.loads(subprocess.check_output(["curl", "-s", "-m", "3", "http://127.0.0.1:8888/health"]))["live"]["connections"]
    except Exception:
        return -1


def wait_idle(maxwait=1800):
    t = time.time()
    while time.time() - t < maxwait:
        if live_connections() == 0 and external_since(time.time() - 60) == 0:
            return True
        time.sleep(5)
    return False



LABEL = sys.argv[1]
REPS = int(sys.argv[2]) if len(sys.argv) > 2 else 5
OUT = f"/home/joseyarashio/dgx-spark-tp2-recipes/benchmarks/results/cutin_reps_{LABEL}.json"

reps = []
for i in range(REPS):
    idle = wait_idle()
    nonce = str(time.time_ns())
    corpus = f"Codebase context block {nonce}: " + ("// Background line token data index 0123456789\n" * 1500)
    p_long = [{"role": "system", "content": corpus}, {"role": "user", "content": "Summarize in 5 words."}]
    p_short = [{"role": "user", "content": f"What is 2+2? Answer in one word. #{nonce}"}]
    t0 = time.time(); c0 = clk()
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        fl = ex.submit(stream_chat, p_long, 16, 0.0, base_url=API_8889)
        time.sleep(0.3)
        fs = ex.submit(stream_chat, p_short, 16, 0.0, base_url=API_8889)
        rs, rl = fs.result(), fl.result()
    rec = {"short_ttft_s": rs.get("client_ttft_seconds"), "long_ttft_s": rl.get("client_ttft_seconds"),
           "status": [rs.get("status_code"), rl.get("status_code")], "clk": [c0, clk()],
           "external": external_since(t0), "idle_before": idle}
    reps.append(rec)
    print("cutin", i, rec, flush=True)
    time.sleep(5)

clean = [r["short_ttft_s"] for r in reps if r["external"] == 0 and r["short_ttft_s"] is not None]
summary = {"cutin_median_s": round(statistics.median(clean), 4) if clean else None,
           "cutin_min_s": min(clean) if clean else None, "cutin_max_s": max(clean) if clean else None,
           "clean": len(clean), "total": len(reps)}
json.dump({"label": LABEL, "time": time.strftime("%F %T"), "reps": reps, "summary": summary}, open(OUT, "w"), indent=2)
print(json.dumps({"label": LABEL, **summary}))
