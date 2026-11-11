#!/usr/bin/env python3
"""Repetition-loop A/B over per-request sampling overrides (server defaults untouched).

Scenarios
  lowmed : marathon LOW_HIT/medium prompt (~4K unique code), max_tokens 2048, thinking 1/3
  agent  : ~40K unique code + review task, reasoning_effort=max, max_tokens 16384
Arms are interleaved per prompt (same prompt i runs once per arm, order shuffled) so live
traffic hits every arm equally. Streams are cut as soon as a loop is detected, so a loop costs
seconds, not a full 32K budget. Loop = same >=20-char unit repeated >=5x back to back
(identical to the historical marathon rescan), checked on content and reasoning separately.

  ARMS='[{"name":"t0.3","temperature":0.3}, ...]' N_LOWMED=120 N_AGENT=16 CONC=6 python3 run_loop_ab.py
"""
import concurrent.futures, contextlib, io, json, os, random, re, string, sys, threading, time, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
with contextlib.redirect_stdout(io.StringIO()):
    import run_5hour_stress_experiment as s5

API = os.environ.get("API", "http://127.0.0.1:8889/v1/chat/completions")
MODEL = "DeepSeek-V4.1-Flash-1017-TF"
LOOP = re.compile(r"(.{20,600}?)\1{4,}", re.S)  # bounded unit: same hits as the historical rescan (25/25 on p16_ttl0cap), ~25x faster
ARMS = json.loads(os.environ.get("ARMS", "[]"))
N_LOWMED = int(os.environ.get("N_LOWMED", "120"))
N_AGENT = int(os.environ.get("N_AGENT", "16"))
CONC = int(os.environ.get("CONC", "6"))
OUT = os.environ.get("OUT", os.path.join(os.path.dirname(os.path.abspath(__file__)), "results", "loop_ab.jsonl"))
CHECK_EVERY = 3000  # chars between loop checks while streaming
lock = threading.Lock()


def lowmed(i):
    rng = random.Random(1000 + i)
    salt = "".join(rng.choices(string.ascii_letters + string.digits, k=32))
    prefix = f"# Dynamic Unique Module [{salt}]\n" + s5.generate_codebase_corpus(4000, salt)
    msgs = [{"role": "system", "content": "You are a senior systems engineer reviewing clustered code."},
            {"role": "user", "content": f"Codebase Context:\n```python\n{prefix}\n```\n\nQuestion: Unique verification task {i} on ephemeral code."}]
    think = rng.choice([False, False, True])
    return {"messages": msgs, "max_tokens": int(os.environ.get("LOWMED_MAX", "3072")), "chat_template_kwargs": {"enable_thinking": think}}, {"think": think}


def agent(i):
    rng = random.Random(5000 + i)
    salt = "".join(rng.choices(string.ascii_letters + string.digits, k=32))
    corpus = s5.generate_codebase_corpus(40000, salt)
    task = rng.choice([
        "Audit every class above for correctness bugs in synchronize_state and the metrics handling. "
        "For each bug give the class name, the exact faulty line, why it is wrong, and a minimal patch.",
        "Design a refactor that removes the duplication across these coordinator classes without changing "
        "behaviour. Give the new module layout, the migration steps, and the tests that prove equivalence.",
        "Find the three most likely production incidents this code would cause on a 2-node RDMA cluster, "
        "with a reproduction plan and a fix for each.",
    ])
    msgs = [{"role": "system", "content": "You are a coding agent. Think carefully, then answer precisely."},
            {"role": "user", "content": f"Repository snapshot [{salt}]:\n```python\n{corpus}\n```\n\n{task}"}]
    return {"messages": msgs, "max_tokens": 16384, "reasoning_effort": "max"}, {"think": True}


def run(scn, i, arm):
    body, meta = (lowmed if scn == "lowmed" else agent)(i)
    body.update({"model": MODEL, "stream": True, "stream_options": {"include_usage": True}})
    body.update({k: v for k, v in arm.items() if k != "name"})
    req = urllib.request.Request(API, json.dumps(body).encode(), {"Content-Type": "application/json", "X-Priority": "2"})
    t0 = time.time(); ttft = None; c = []; r = []; cn = rn = 0; nxt = CHECK_EVERY
    fin = None; usage = {}; loop_ch = None; status = 0; err = None
    try:
        with urllib.request.urlopen(req, timeout=1800) as resp:
            status = resp.status
            for raw in resp:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data: "):
                    continue
                data = line[6:]
                if data == "[DONE]":
                    break
                try:
                    ch = json.loads(data)
                except Exception:
                    continue
                if ch.get("usage"):
                    usage = ch["usage"]
                for choice in ch.get("choices") or []:
                    d = choice.get("delta") or {}
                    if d.get("content"):
                        c.append(d["content"]); cn += len(d["content"])
                    rc = d.get("reasoning_content") or d.get("reasoning")
                    if rc:
                        r.append(rc); rn += len(rc)
                    if (d.get("content") or rc) and ttft is None:
                        ttft = time.time() - t0
                    if choice.get("finish_reason"):
                        fin = choice["finish_reason"]
                if cn + rn >= nxt:
                    nxt = cn + rn + CHECK_EVERY
                    if LOOP.search("".join(c)[-12000:]):
                        loop_ch = "content"
                    elif LOOP.search("".join(r)[-12000:]):
                        loop_ch = "reasoning"
                    if loop_ch:
                        fin = "loop_cut"
                        break
    except Exception as e:
        err = str(e)[:120]
    ct, rt = "".join(c), "".join(r)
    if not loop_ch:
        loop_ch = "content" if LOOP.search(ct) else ("reasoning" if LOOP.search(rt) else None)
    unit = loop_pos = loop_period = None
    if loop_ch:
        m = LOOP.search(ct if loop_ch == "content" else rt)
        unit = m.group(1)[:80] if m else None
        loop_pos = round(m.start() / max(len(ct if loop_ch == "content" else rt), 1), 3) if m else None
        loop_period = len(m.group(1)) if m else None
    row = {"arm": arm["name"], "scn": scn, "i": i, **meta, "status": status, "err": err, "finish": fin,
           "loop": bool(loop_ch), "loop_channel": loop_ch, "loop_unit": unit, "loop_pos": loop_pos, "loop_period": loop_period, "chars": len(ct), "rchars": len(rt),
           "completion_tokens": usage.get("completion_tokens"), "prompt_tokens": usage.get("prompt_tokens"),
           "ttft": round(ttft, 2) if ttft else None, "wall": round(time.time() - t0, 2), "ts": t0,
           "content_tail": ct[-400:], "reasoning_tail": rt[-400:]}
    with lock, open(OUT, "a") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def main():
    jobs = [(scn, i, arm) for scn, n in (("lowmed", N_LOWMED), ("agent", N_AGENT)) for i in range(n) for arm in ARMS]
    rng = random.Random(42)
    # shuffle arm order inside each prompt group, keep prompt groups roughly in sequence
    grouped = {}
    for j in jobs:
        grouped.setdefault((j[0], j[1]), []).append(j)
    order = []
    for k in grouped:
        g = grouped[k]; rng.shuffle(g); order.extend(g)
    print(f"jobs={len(order)} arms={[a['name'] for a in ARMS]} conc={CONC} out={OUT}", flush=True)
    done = 0; t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(CONC) as ex:
        for row in ex.map(lambda j: run(*j), order):
            done += 1
            if done % 30 == 0:
                print(f"  {done}/{len(order)} {time.time() - t0:.0f}s", flush=True)
    summarize(OUT)


def summarize(path):
    rows = [json.loads(l) for l in open(path)]
    keys = sorted({(r["scn"], r["arm"]) for r in rows})
    for scn, arm in keys:
        rs = [r for r in rows if r["scn"] == scn and r["arm"] == arm]
        ok = [r for r in rs if r["status"] == 200 and not r["err"]]
        lp = [r for r in ok if r["loop"]]
        toks = [r["completion_tokens"] for r in ok if r["completion_tokens"]]
        print(f"{scn:7s} {arm:12s} ok {len(ok)}/{len(rs)} loops {len(lp)} ({100*len(lp)/max(len(ok),1):.1f}%) "
              f"[content {sum(r['loop_channel']=='content' for r in lp)} / reasoning {sum(r['loop_channel']=='reasoning' for r in lp)}] "
              f"finish_length {sum(r['finish']=='length' for r in ok)} tok_mean {sum(toks)/max(len(toks),1):.0f}", flush=True)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--summary":
        summarize(sys.argv[2] if len(sys.argv) > 2 else OUT)
    else:
        main()
