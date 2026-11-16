#!/usr/bin/env python3
"""S6 shadow: memory-pressure signals on both Spark nodes vs. the proxy's fixed-GiB ladder. Observe only.

Nothing here touches the proxy, the engine or any admission decision. Every INTERVAL seconds it records, per node:
  - MemAvailable / MemFree / SwapUsed (GiB)
  - PSI memory some/full avg10/avg60 and the stall-time delta (us) since the last sample
  - /proc/vmstat deltas: pswpin, pswpout, pgscan_kswapd, pgscan_direct, allocstall_*, pgmajfault
  - rank0 engine: prompt-cache held/budget MiB (latest "prompt cache:" log line), /health memory.active
  - proxy: active/queue from /dev/shm/dgx_cluster_state
and two decisions for Node 1 (where the proxy runs):
  - legacy: the live ladder in proxy.py _can_run_priority_locked (max_large 3 / 2 / 1 at 3.05 / 2.65 GiB)
  - candidate: a scale-free level from stall/reclaim signals only (no GiB constants):
      critical if PSI full avg10 >= 10 %, warning if PSI some avg10 >= 10 % or full avg10 >= 1 %
      or any direct reclaim (allocstall/pgscan_direct delta > 0) or swap-in delta > 0, else normal.
The PSI percentages are the defaults #2156 proposes; they are fractions of wall time, so they do not depend on RAM
size or slot count. Report: shadow_report.py summarizes agreement, legacy throttles with no stall, stalls the
legacy ladder missed.

usage: memory_pressure_shadow.py OUT_DIR [DURATION_S] [INTERVAL_S]     (OUT_DIR/STOP ends it early)
"""
import json, os, re, subprocess, sys, threading, time, urllib.request

OUT = os.path.abspath(sys.argv[1])
DUR = float(sys.argv[2]) if len(sys.argv) > 2 else 86400
IV = float(sys.argv[3]) if len(sys.argv) > 3 else 5
os.makedirs(OUT, exist_ok=True)
VMS = ("pswpin", "pswpout", "pgscan_kswapd", "pgscan_direct", "allocstall_normal", "allocstall_movable",
       "allocstall_dma", "allocstall_dma32", "pgmajfault")
PROBE = ("cat /proc/meminfo; echo @@PSI; cat /proc/pressure/memory; echo @@VM; "
         "grep -E '^(" + "|".join(VMS) + ") ' /proc/vmstat")


def parse(text):
    d = {}
    mem, _, rest = text.partition("@@PSI")
    psi, _, vm = rest.partition("@@VM")
    for line in mem.splitlines():
        k, _, v = line.partition(":")
        if k in ("MemAvailable", "MemFree", "SwapTotal", "SwapFree"):
            d[k] = int(v.split()[0]) / 1048576
    if "SwapTotal" in d:
        d["SwapUsed"] = d.pop("SwapTotal") - d.pop("SwapFree")
    for line in psi.splitlines():
        m = re.match(r"(some|full) avg10=([\d.]+) avg60=([\d.]+) avg300=([\d.]+) total=(\d+)", line.strip())
        if m:
            k = m.group(1)
            d[f"psi_{k}_avg10"] = float(m.group(2))
            d[f"psi_{k}_avg60"] = float(m.group(3))
            d[f"_psi_{k}_total"] = int(m.group(5))
    for line in vm.splitlines():
        p = line.split()
        if len(p) == 2:
            d["_vm_" + p[0]] = int(p[1])
    return d


class Node:
    def __init__(self, host):
        self.host, self.prev, self.cur = host, None, {}

    def sample(self):
        if self.host is None:
            txt = subprocess.run(["bash", "-c", PROBE], capture_output=True, text=True, timeout=10).stdout
        else:
            txt = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", self.host, PROBE],
                                 capture_output=True, text=True, timeout=15).stdout
        d = parse(txt)
        out = {k: (round(v, 3) if isinstance(v, float) else v) for k, v in d.items() if not k.startswith("_")}
        if self.prev:
            for k in ("some", "full"):
                key = f"_psi_{k}_total"
                if key in d and key in self.prev:
                    out[f"psi_{k}_stall_us"] = d[key] - self.prev[key]
            for v in VMS:
                key = "_vm_" + v
                if key in d and key in self.prev:
                    out["d_" + v] = d[key] - self.prev[key]
        self.prev = d
        return out


_last_pc = {}


def engine():
    e = {}
    try:
        with urllib.request.urlopen("http://127.0.0.1:8888/health", timeout=3) as r:
            m = json.load(r).get("memory") or {}
            e["engine_active_gib"] = round(m.get("active", 0) / 2**30, 3)
    except Exception:
        e["engine_active_gib"] = None
    try:
        # the line is printed per request only, so keep the last value seen (a quiet engine holds its cache)
        tail = subprocess.run(["docker", "logs", "--since", f"{int(IV) + 5}s", "dsv41-rank0"], capture_output=True,
                              text=True, timeout=10)
        lines = [l for l in (tail.stdout + tail.stderr).splitlines() if "prompt cache:" in l and " MiB" in l]
        if not _last_pc:
            full = subprocess.run(["docker", "logs", "--tail", "5000", "dsv41-rank0"], capture_output=True,
                                  text=True, timeout=20)
            lines = [l for l in (full.stdout + full.stderr).splitlines() if "prompt cache:" in l and " MiB" in l] + lines
        if lines:
            m = re.search(r"(\d+) states, (\d+) MiB and (\d+) MiB spare of (\d+) MiB", lines[-1])
            if m:
                _last_pc.update(pc_states=int(m.group(1)), pc_held_mib=int(m.group(2)), pc_spare_mib=int(m.group(3)),
                                pc_budget_mib=int(m.group(4)))
        e.update(_last_pc)
    except Exception:
        pass
    try:
        e["proxy_state"] = open("/dev/shm/dgx_cluster_state").read().strip()
    except Exception:
        pass
    return e


def legacy(free):
    # mirror of proxy.py _can_run_priority_locked for est_tokens > threshold (live code, sha dbc02a5c)
    max_large = 3 if free >= 3.05 else (2 if free >= 2.65 else 1)
    return {"max_large": max_large, "p0_blocked": free < 2.65, "p1p2_blocked": free < 2.65}


def candidate(n):
    some, full = n.get("psi_some_avg10", 0.0), n.get("psi_full_avg10", 0.0)
    reclaim = sum(n.get("d_" + k, 0) for k in ("pgscan_direct", "allocstall_normal", "allocstall_movable",
                                                "allocstall_dma", "allocstall_dma32"))
    if full >= 10.0:
        lvl = "critical"
    elif some >= 10.0 or full >= 1.0 or reclaim > 0 or n.get("d_pswpin", 0) > 0:
        lvl = "warning"
    else:
        lvl = "normal"
    return {"level": lvl, "direct_reclaim": reclaim}


def main():
    n1, n2 = Node(None), Node("192.168.10.149")
    path = os.path.join(OUT, "shadow.jsonl")
    t_end = time.time() + DUR
    with open(path, "a") as f:
        while time.time() < t_end and not os.path.exists(os.path.join(OUT, "STOP")):
            t0 = time.time()
            rec: dict = {"ts": round(t0, 3)}
            try:
                a = n1.sample()
            except Exception as ex:
                a = {"error": repr(ex)}
            try:
                b = n2.sample()
            except Exception as ex:
                b = {"error": repr(ex)}
            rec["n1"], rec["n2"] = a, b
            rec.update(engine())
            if "MemAvailable" in a:
                rec["legacy"] = legacy(a["MemAvailable"])
                rec["candidate"] = candidate(a)
            if "MemAvailable" in b:
                rec["candidate_n2"] = candidate(b)
            f.write(json.dumps(rec) + "\n")
            f.flush()
            time.sleep(max(0.0, IV - (time.time() - t0)))


if __name__ == "__main__":
    main()
