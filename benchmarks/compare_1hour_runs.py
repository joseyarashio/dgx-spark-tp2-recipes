#!/usr/bin/env python3
"""Compare 1-hour standard OmniBench runs (same run_omni_eval.py --profile standard --duration 3600).

Every metric comes from one run's own JSON (no cross-run cherry-picking). Usage:
  compare_1hour_runs.py NEW.json BASE1.json [BASE2.json ...]
"""
import json, re, statistics, sys, os

# Same >=20-char unit repeated >=5x back to back; the unit is bounded for speed (identical hits on
# every historical 1h run). 200 OK does not mean usable: a looped reply is a failed reply.
LOOP = re.compile(r"(.{20,600}?)\1{4,}", re.S)


def looped(r):
    c = r.get("content")
    return isinstance(c, str) and bool(LOOP.search(c))


def pct(xs, q):
    xs = sorted(xs)
    if not xs:
        return None
    k = (len(xs) - 1) * q
    f = int(k)
    c = min(f + 1, len(xs) - 1)
    return xs[f] + (xs[c] - xs[f]) * (k - f)


def summarize(path):
    d = json.load(open(path))
    dim = d["dimensions"]
    m = dim.get("continuous_stress_marathon", {})
    res = m.get("results", [])
    ok = [r for r in res if r.get("status_code") == 200]
    codes = {}
    for r in res:
        codes[r.get("status_code")] = codes.get(r.get("status_code"), 0) + 1
    ttft = [r["ttft_seconds"] for r in ok if r.get("ttft_seconds") is not None and r["ttft_seconds"] >= 0]
    wall = [r["wall_seconds"] for r in ok if r.get("wall_seconds") is not None]
    vis = [r for r in res if r.get("task_type", "").startswith("vision") or "turn" in json.dumps({k: v for k, v in r.items() if k != "content"}).lower()]
    q = dim.get("quality", {})
    cc = dim.get("concurrency", {})
    pf = dim.get("prefill", {})
    dc = dim.get("decode", {})
    out = {
        "file": os.path.basename(path),
        "start": d.get("timestamp"),
        "quality_pass": f"{sum(1 for v in q.values() if isinstance(v, dict) and v.get('passed'))}/{len(q)}",
        "tools_pass": all(v.get("passed") for v in dim.get("tool_eval", {}).values() if isinstance(v, dict)),
        "prefill_8k_cold_tok_s": pf.get("prefill_8k_cold", {}).get("tok_s"),
        "prefill_8k_cached_ttft_s": pf.get("prefill_8k_cached", {}).get("ttft_s"),
        "greedy_tok_s": round(dc.get("decode_greedy", {}).get("tokens_per_second") or 0, 2),
        "mtp_accept": dc.get("decode_greedy", {}).get("mtp_acceptance"),
        "sampling_tok_s": round(dc.get("decode_sampling", {}).get("tokens_per_second") or 0, 2),
        "c1": cc.get("concurrency_c1", {}).get("aggregate_tok_s"),
        "c2": cc.get("concurrency_c2", {}).get("aggregate_tok_s"),
        "c4": cc.get("concurrency_c4", {}).get("aggregate_tok_s"),
        "cut_in_32k_s": cc.get("cut_in_32k", {}).get("short_ttft_s"),
        "marathon_requests": len(res),
        "ok_200": len(ok),
        "ok_rate_pct": round(100 * len(ok) / max(len(res), 1), 2),
        "status_codes": codes,
        "loop_replies": sum(1 for r in ok if looped(r)),
        "loop_rate_pct": round(100 * sum(1 for r in ok if looped(r)) / max(len(ok), 1), 2),
        "loop_lowhit_medium": "{}/{}".format(
            sum(1 for r in ok if r.get("mode") == "LOW_HIT" and r.get("len_tier") == "medium" and looped(r)),
            sum(1 for r in ok if r.get("mode") == "LOW_HIT" and r.get("len_tier") == "medium")),
        "gen_tokens": sum(r.get("tokens") or 0 for r in ok),
        "cached_tokens": sum(r.get("cached_tokens") or 0 for r in ok),
        "ttft_p50_s": round(pct(ttft, 0.5) or 0, 3),
        "ttft_p95_s": round(pct(ttft, 0.95) or 0, 3),
        "wall_mean_s": round(statistics.mean(wall), 2) if wall else None,
        "wall_p95_s": round(pct(wall, 0.95) or 0, 2),
        "mem_after_gib": None,
    }
    sa = d.get("system_after", {})
    for k in ("mem_available_gib", "node1_mem_available_gib", "host_mem_available_gib"):
        if k in sa:
            out["mem_after_gib"] = sa[k]
    return out


def main():
    rows = [summarize(p) for p in sys.argv[1:]]
    keys = [k for k in rows[0] if k not in ("file",)]
    print("metric".ljust(26) + "".join(r["file"][:34].ljust(36) for r in rows))
    for k in keys:
        print(k.ljust(26) + "".join(str(r[k])[:34].ljust(36) for r in rows))
    json.dump(rows, open(os.path.join(os.path.dirname(os.path.abspath(sys.argv[1])), "compare_1hour_latest.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
