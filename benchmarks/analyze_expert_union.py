#!/usr/bin/env python3
"""Hibana port S1: what a budgeted expert selection (Hibana route_budget) would do on this engine's real verify rounds.

Reads the engine's TF_DS_EXPERT_STATS=2 dump (rounds.bin: each verify round's picks and weights per layer) and stats.json
(distinct experts per decode window by row count), and simulates route_budget offline:
  each row keeps its top KEEP routed experts (by routing weight); the call reads at most min(CAP, PER_REQ x streams)
  distinct routed experts, filled by summed routing weight; every row also takes its other top-k experts the call reads
  anyway (free riders). Reports, per configuration: distinct routed experts read (mean, by row count), the share of
  routing weight dropped per token (mean / p95 / max), and the fraction of rows that lose any expert.

usage: analyze_expert_union.py [--dump ~/.cache/dsv41-expert-stats/rounds.bin] [--out results.json]
"""
import argparse, collections, json, os, statistics, struct, sys

MAGIC = 0x58535431


def rounds(path):
    with open(path, "rb") as f:
        while True:
            h = f.read(32)
            if len(h) < 32:
                return
            magic, R, L, S, nw = struct.unpack("<5I", h[:20])
            if magic != MAGIC:
                raise SystemExit(f"bad magic at {f.tell() - 32}")
            slots = struct.unpack(f"<{R}i", f.read(4 * R))
            body = f.read(2 * L * R * S * 4)
            if len(body) < 2 * L * R * S * 4:
                return
            picks = struct.unpack(f"<{L * R * S}i", body[: L * R * S * 4])
            wts = struct.unpack(f"<{L * R * S}f", body[L * R * S * 4:])
            yield R, L, S, nw, slots, picks, wts


def budget(rows, keep, cap, per_req, streams):
    """rows: list of [(expert, weight)] (routed only, rank order). Returns (distinct read, dropped share per row)."""
    lim = min(cap, per_req * streams) if per_req else cap
    must = set()
    for r in rows:
        must.update(e for e, _ in r[:keep])
    chosen = set(must)
    if len(chosen) < lim:
        score = collections.Counter()
        for r in rows:
            for e, w in r:
                if e not in chosen:
                    score[e] += w
        for e, _ in score.most_common():
            if len(chosen) >= lim:
                break
            chosen.add(e)
    drop = []
    for r in rows:
        tot = sum(w for _, w in r) or 1.0
        drop.append(sum(w for e, w in r if e not in chosen) / tot)
    return len(chosen), drop


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", default=os.path.expanduser("~/.cache/dsv41-expert-stats/rounds.bin"))
    ap.add_argument("--stats", default=os.path.expanduser("~/.cache/dsv41-expert-stats/stats.json"))
    ap.add_argument("--out", default=None)
    ap.add_argument("--max-rounds", type=int, default=20000)
    a = ap.parse_args()
    # configurations: (keep, cap, per_request); cap is per layer per call over routed experts
    cfgs = [(k, c, p) for k in (6, 5, 4, 3) for (c, p) in ((24, 0), (32, 0), (48, 0), (64, 0), (96, 0), (0, 12), (0, 16), (0, 20))]
    acc = {c: {"distinct": [], "drop": [], "rows_hit": 0, "rows": 0} for c in cfgs}
    base = collections.defaultdict(list)  # rows -> distinct routed experts per layer-call (no budget)
    n_rounds = 0
    streams_hist = collections.Counter()
    for R, L, S, nw, slots, picks, wts in rounds(a.dump):
        n_rounds += 1
        if n_rounds > a.max_rounds:
            break
        streams = len(set(slots))
        streams_hist[streams] += 1
        for li in range(L):
            rows = []
            for r in range(R):
                o = (li * R + r) * S
                # routed slots are 0..S-2 (the shared expert is the last slot, every row); keep rank order
                rows.append([(picks[o + q], wts[o + q]) for q in range(S - 1) if 0 <= picks[o + q] < 384])
            distinct = len({e for r in rows for e, _ in r})
            base[R].append(distinct)
            if R == 1:
                continue  # one row: a budget never binds below top-k
            for c in cfgs:
                keep, cap, per = c
                capv = cap if cap else 10 ** 9
                n, drop = budget(rows, keep, capv, per, streams)
                ac = acc[c]
                ac["distinct"].append(n / max(1, distinct))
                ac["drop"].extend(drop)
                ac["rows"] += len(drop)
                ac["rows_hit"] += sum(1 for d in drop if d > 0)
    out = {"rounds": n_rounds, "streams_hist": dict(sorted(streams_hist.items())),
           "baseline_distinct_by_rows": {r: {"n": len(v), "mean": statistics.mean(v), "max": max(v)} for r, v in sorted(base.items())}}
    res = []
    for c, ac in acc.items():
        if not ac["drop"]:
            continue
        d = sorted(ac["drop"])
        res.append({"keep": c[0], "cap": c[1], "per_req": c[2], "read_frac_of_union": statistics.mean(ac["distinct"]),
                    "drop_mean": statistics.mean(d), "drop_p95": d[int(0.95 * (len(d) - 1))], "drop_max": d[-1],
                    "rows_losing_any": ac["rows_hit"] / ac["rows"]})
    out["budget"] = res
    if os.path.exists(a.stats):
        out["engine_stats"] = json.load(open(a.stats))
    s = json.dumps(out, indent=1)
    if a.out:
        open(a.out, "w").write(s)
    print(s)


if __name__ == "__main__":
    main()
