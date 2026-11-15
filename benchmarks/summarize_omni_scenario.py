#!/usr/bin/env python3
"""Summarize an OmniScenario-1h run directory against the v1 plan gates. usage: summarize_omni_scenario.py RUN_DIR"""
import collections, json, os, statistics, sys

D = sys.argv[1]
rows = [json.loads(l) for l in open(os.path.join(D, "rows.jsonl"))]
ev = [json.loads(l) for l in open(os.path.join(D, "events.jsonl"))]
tel = [json.loads(l) for l in open(os.path.join(D, "telemetry.jsonl"))]
bad = [json.loads(l) for l in open(os.path.join(D, "bad_lines.jsonl"))] if os.path.exists(os.path.join(D, "bad_lines.jsonl")) else []
E = {}
for e in ev:
    E.setdefault(e["kind"], []).append(e)


def q(xs, p):
    xs = sorted(x for x in xs if x is not None)
    return round(xs[min(len(xs) - 1, int(p * (len(xs) - 1)))], 3) if xs else None


out = {"run": D, "scenarios": {}, "gates": {}, "xfail": {}, "observe": {}}
by = collections.defaultdict(list)
for r in rows:
    by[r.get("scenario")].append(r)
MAIN = ["S1", "S2", "S3a", "S3b", "S4", "S5", "S6", "S7"]
for s, rs in sorted(by.items(), key=lambda kv: str(kv[0])):
    out["scenarios"][s] = {
        "n": len(rs), "status": dict(collections.Counter(r.get("status") for r in rs)),
        "valid": sum(1 for r in rs if r.get("valid")), "finish": dict(collections.Counter(r.get("finish") for r in rs)),
        "ttft_p50": q([r.get("ttft") for r in rs], .5), "ttft_p95": q([r.get("ttft") for r in rs], .95),
        "wall_p50": q([r.get("wall") for r in rs], .5), "wall_p95": q([r.get("wall") for r in rs], .95),
        "cancelled": dict(collections.Counter(r.get("cancelled") for r in rs if r.get("cancelled"))),
    }

# delivery (main load, excluding S7 intentional cancels, drain-censored, bursts, xfail cells)
den = [r for s in MAIN if s != "S7" for r in by[s] if r.get("cancelled") != "drain"]
xf = [r for r in den if r.get("xfail_all_reasoning") or r.get("xfail_empty_length")]
den2 = [r for r in den if r not in xf]
q429 = [r for r in den2 if r.get("status") == 429]
den3 = [r for r in den2 if r.get("status") != 429]
out["gates"]["main_valid_delivery_excl_429"] = f"{sum(1 for r in den3 if r.get('valid'))}/{len(den3)}"
out["gates"]["main_429"] = {"n": len(q429), "wall": sorted(round(r.get('wall') or 0, 2) for r in q429)[:40]}
eng_fail = [r for r in rows if r.get("status") and r["status"] >= 500 or (r.get("status") == 200 and r.get("stream") and not r.get("done_seen") and not r.get("cancelled"))]
out["gates"]["engine_failures(5xx or truncated 200)"] = [(r.get("scenario"), r.get("tag"), r.get("status"), r.get("error")) for r in eng_fail]
out["gates"]["dsml_leak_with_tools_active"] = [(r.get("scenario"), r.get("tag")) for r in rows if r.get("dsml_leak_tools_active")]
out["gates"]["tool_args_unparsable"] = sum(r.get("tool_args_bad") or 0 for r in rows)
out["gates"]["bad_log_lines"] = bad[:10]
out["gates"]["abort"] = [e.get("reason") for e in E.get("ABORT", [])]
for k in ("preflight_done", "M1_done", "M3_done", "M6_done", "burst1_done", "burst2_done", "needle_done", "cancel100k_done", "revisit_done", "final_checks", "omni_standard_done", "full_eval_done"):
    if k in E:
        out["gates"][k] = [{kk: vv for kk, vv in e.items() if kk not in ("kind", "wall")} for e in E[k]]
s1 = by["S1"] + by["M5"]
out["gates"]["S1_tool_ok"] = f"{sum(1 for r in s1 if r.get('tool_ok'))}/{len(s1)}"
p0 = by["P0"]
out["gates"]["P0_probe"] = {"n": len(p0), "ok": sum(1 for r in p0 if r.get("status") == 200), "ttft_p50": q([r.get("ttft") for r in p0], .5),
                            "ttft_p95": q([r.get("ttft") for r in p0], .95), "ttft_max": q([r.get("ttft") for r in p0], 1)}
loaded = [t for t in tel if (t.get("px_active") or 0) > 0]
out["gates"]["mem"] = {"n1_min": round(min(t.get("n1_mem") or 99 for t in tel), 2), "n2_min": round(min(t.get("n2_mem") or 99 for t in tel), 2),
                       "n1_swap_delta_mib": round((tel[-1].get("n1_swap") or 0) - (tel[0].get("n1_swap") or 0), 1),
                       "n2_swap_delta_mib": round((tel[-1].get("n2_swap") or 0) - (tel[0].get("n2_swap") or 0), 1)}
out["observe"]["clock_loaded"] = {"ticks": len(loaded), "ge2350_pct": round(100 * sum(1 for t in loaded if (t.get("n1_clock") or 0) >= 2350) / max(1, len(loaded)), 1),
                                  "n1_clock_p50": q([t.get("n1_clock") for t in loaded], .5), "n1_temp_max": max((t.get("n1_temp") or 0) for t in tel)}
out["xfail"]["S2_all_reasoning"] = f"{sum(1 for r in by['S2'] if r.get('xfail_all_reasoning'))}/{len(by['S2'])}"
out["xfail"]["S3b_empty_length"] = f"{sum(1 for r in by['S3b'] if r.get('xfail_empty_length'))}/{len(by['S3b'])}"
out["xfail"]["M4b_budget_cut_to_tool"] = [(r.get("tag"), r.get("xfail_cut_to_tool")) for r in by["M4b"]]
out["observe"]["S3a_rewritten"] = f"{sum(1 for r in by['S3a'] if r.get('rewritten'))}/{len(by['S3a'])}"
out["observe"]["S5_vision_ok"] = f"{sum(1 for r in by['S5'] if r.get('vision_ok'))}/{len(by['S5'])}"
out["observe"]["S5_turn2_cached"] = q([r.get("turn2_cached") for r in by["S5"] if r.get("tag") == "turn2"], .5)
out["observe"]["S6_correct"] = f"{sum(1 for r in by['S6'] if r.get('correct'))}/{len(by['S6'])}"
out["observe"]["S7_proxy_release_s"] = {st: q([r.get("proxy_release_s") for r in by["S7"] if r.get("cancel_stage") == st], .5) for st in ("prefill", "thinking", "content", "tool_args")}
out["observe"]["loop_shadow_all"] = f"{sum(1 for r in rows if r.get('loop_shadow'))}/{len(rows)}"
think = [r for r in rows if (r.get("reasoning_chars") or 0) > 0]
out["observe"]["thinking_requests"] = len(think)
m2 = by["M2"]
out["observe"]["M2_reasoning_tokens_by_effort"] = {e: q([r.get("reasoning_tokens") for r in m2 if r.get("tag", "").endswith("|" + e)], .5)
                                                   for e in ("none", "minimal", "low", "medium", "high", "xhigh", "max")}
out["observe"]["M2_correct_by_effort"] = {e: f"{sum(1 for r in m2 if r.get('tag', '').endswith('|' + e) and r.get('correct'))}/{sum(1 for r in m2 if r.get('tag', '').endswith('|' + e))}"
                                          for e in ("none", "minimal", "low", "medium", "high", "xhigh", "max")}
out["observe"]["main_load_completed"] = sum(len(by[s]) for s in MAIN)
out["observe"]["S1_cached_ratio_p50"] = q([(r.get("cached_tokens") or 0) / r["prompt_tokens"] for r in by["S1"] if r.get("prompt_tokens")], .5)
json.dump(out, open(os.path.join(D, "summary.json"), "w"), indent=1, ensure_ascii=False, default=str)
print(json.dumps(out, indent=1, ensure_ascii=False, default=str))
