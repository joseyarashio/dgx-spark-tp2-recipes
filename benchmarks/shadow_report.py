#!/usr/bin/env python3
"""Summarize memory_pressure_shadow.py output: legacy fixed-GiB ladder vs scale-free stall/reclaim level.
usage: shadow_report.py OUT_DIR"""
import collections, json, os, sys, time

rows = [json.loads(l) for l in open(os.path.join(sys.argv[1], "shadow.jsonl")) if l.strip()]
rows = [r for r in rows if "legacy" in r]
if not rows:
    sys.exit("no samples")
span_h = (rows[-1]["ts"] - rows[0]["ts"]) / 3600
c = collections.Counter()
for r in rows:
    lg, cd = r["legacy"], r["candidate"]["level"]
    throttled = lg["max_large"] < 3
    c[("legacy_throttle" if throttled else "legacy_full", cd)] += 1


def series(key, node="n1"):
    return [r[node][key] for r in rows if key in r.get(node, {})]


out = {
    "samples": len(rows),
    "span_h": round(span_h, 2),
    "from": time.strftime("%F %T", time.localtime(rows[0]["ts"])),
    "to": time.strftime("%F %T", time.localtime(rows[-1]["ts"])),
    "matrix": {f"{a}|{b}": n for (a, b), n in sorted(c.items())},
    "legacy_throttled_while_no_pressure": sum(n for (a, b), n in c.items() if a == "legacy_throttle" and b == "normal"),
    "pressure_while_legacy_full": sum(n for (a, b), n in c.items() if a == "legacy_full" and b != "normal"),
    "n1_memavail_min_max": [min(series("MemAvailable")), max(series("MemAvailable"))],
    "n2_memavail_min_max": [min(series("MemAvailable", "n2")), max(series("MemAvailable", "n2"))],
    "n1_psi_some_avg10_max": max(series("psi_some_avg10") or [0]),
    "n1_psi_full_avg10_max": max(series("psi_full_avg10") or [0]),
    "n2_psi_some_avg10_max": max(series("psi_some_avg10", "n2") or [0]),
    "n1_stall_some_s": round(sum(series("psi_some_stall_us")) / 1e6, 3),
    "n2_stall_some_s": round(sum(series("psi_some_stall_us", "n2")) / 1e6, 3),
    "n1_swapin_pages": sum(series("d_pswpin")),
    "n1_direct_reclaim_pages": sum(series("d_pgscan_direct")),
    "n1_kswapd_scan_pages": sum(series("d_pgscan_kswapd")),
    "n2_swapin_pages": sum(series("d_pswpin", "n2")),
    "n1_swapused_first_last": [series("SwapUsed")[0], series("SwapUsed")[-1]],
    "pc_held_mib_first_last": [next((r.get("pc_held_mib") for r in rows if r.get("pc_held_mib") is not None), None),
                               next((r.get("pc_held_mib") for r in reversed(rows) if r.get("pc_held_mib") is not None), None)],
    "candidate_n2_levels": dict(collections.Counter(r.get("candidate_n2", {}).get("level") for r in rows)),
}
print(json.dumps(out, indent=2, ensure_ascii=False))
