#!/usr/bin/env python3
"""Memory breakdown sampler for both Spark nodes (every INTERVAL s until DURATION s or OUT/STOP exists).
Per sample: /proc/meminfo fields (MemAvailable, MemFree, Cached, Buffers, AnonPages, Shmem, SUnreclaim, SReclaimable,
Mlocked, PageTables, VmallocUsed, SwapUsed), rank0 tensorfold-native RSS/anon, GPU memory used by that pid, engine
/health memory.active/peak, proxy active/queue; Node 2 meminfo + tf-dsv41-lanes RSS over one persistent ssh.
The engine prompt-cache 'held' MiB comes from the rank0 log afterwards (prompt cache: ... states, N MiB ...).
usage: mem_sampler.py OUT_DIR [DURATION_S] [INTERVAL_S]
"""
import json, os, subprocess, sys, threading, time, urllib.request

OUT = os.path.abspath(sys.argv[1])
DUR = float(sys.argv[2]) if len(sys.argv) > 2 else 4200
IV = float(sys.argv[3]) if len(sys.argv) > 3 else 5
os.makedirs(OUT, exist_ok=True)
F = ["MemAvailable", "MemFree", "Cached", "Buffers", "AnonPages", "Shmem", "SUnreclaim", "SReclaimable", "Mlocked",
     "PageTables", "VmallocUsed", "SwapTotal", "SwapFree", "Unevictable"]
n2 = {}


def meminfo(text):
    d = {}
    for line in text.splitlines():
        k, _, v = line.partition(":")
        if k in F:
            d[k] = int(v.split()[0]) / 1048576  # GiB
    if "SwapTotal" in d:
        d["SwapUsed"] = d.pop("SwapTotal") - d.pop("SwapFree")
    return {k: round(v, 3) for k, v in d.items()}


def proc_status(pid):
    d = {}
    try:
        for line in open(f"/proc/{pid}/status"):
            k, _, v = line.partition(":")
            if k in ("VmRSS", "RssAnon", "RssFile", "RssShmem", "VmSwap"):
                d[k] = round(int(v.split()[0]) / 1048576, 3)
    except Exception:
        pass
    return d


def node2_loop():
    cmd = ["ssh", "-o", "BatchMode=yes", "-o", "ServerAliveInterval=5", "192.168.10.149",
           f"while true; do cat /proc/meminfo; p=$(pgrep -f tf-dsv41-lanes | head -1); "
           f"grep -E '^(VmRSS|RssAnon|RssFile|RssShmem):' /proc/$p/status 2>/dev/null | sed 's/^/P_/'; echo ===; sleep {IV}; done"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True)
    buf = []
    for line in p.stdout:
        if line.strip() == "===":
            txt = "".join(buf)
            buf = []
            d = meminfo(txt)
            for l in txt.splitlines():
                if l.startswith("P_"):
                    k, _, v = l[2:].partition(":")
                    d["lanes_" + k] = round(int(v.split()[0]) / 1048576, 3)
            n2.clear()
            n2.update(d)
        else:
            buf.append(line)
        if os.path.exists(os.path.join(OUT, "STOP")):
            p.kill()
            break


def get(url):
    try:
        return json.loads(urllib.request.urlopen(url, timeout=2).read())
    except Exception:
        return {}


def main():
    threading.Thread(target=node2_loop, daemon=True).start()
    pid = subprocess.run(["pgrep", "-f", "tensorfold-native serve"], capture_output=True, text=True).stdout.split()
    pid = pid[0] if pid else None
    t0 = time.time()
    with open(os.path.join(OUT, "mem.jsonl"), "a") as f:
        while time.time() - t0 < DUR and not os.path.exists(os.path.join(OUT, "STOP")):
            t = time.time()
            row = {"ts": round(t, 1), "t": round(t - t0, 1), "n1": meminfo(open("/proc/meminfo").read())}
            if pid:
                row["rank0"] = proc_status(pid)
            try:
                g = subprocess.run(["nvidia-smi", "--query-compute-apps=pid,used_memory", "--format=csv,noheader,nounits"],
                                   capture_output=True, text=True, timeout=3).stdout
                row["gpu_used_mib"] = sum(int(l.split(",")[1]) for l in g.strip().splitlines() if l.strip())
            except Exception:
                pass
            h = get("http://127.0.0.1:8888/health")
            if h.get("memory"):
                row["eng_active_gib"] = round(h["memory"]["active"] / 2**30, 3)
                row["eng_peak_gib"] = round(h["memory"]["peak"] / 2**30, 3)
                row["eng_conn"] = h["live"]["connections"]
            s = get("http://127.0.0.1:8889/proxy/status")
            row["px_active"], row["px_wait"] = s.get("active_running"), s.get("waiting_in_queue")
            row["n2"] = dict(n2)
            f.write(json.dumps(row) + "\n")
            f.flush()
            time.sleep(max(0.0, IV - (time.time() - t)))


if __name__ == "__main__":
    main()
