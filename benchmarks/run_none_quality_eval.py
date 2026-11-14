#!/usr/bin/env python3
"""Blind quality check: is an effort=none answer an acceptable stand-in for a high-effort answer?

Phase gen: synthesis convs 0..3 (85K, 8 tools, tool_choice=auto; the 4 synthesis prompts) x seeds (11, 22)
  x effort {high, none}, full content kept. high runs as production does (no thinking_budget, loop guard on).
Phase judge: for every (conv, seed) where both arms delivered (finish=stop, content >= 200 tokens, no DSML), two external
  judges (claude-fable-5-2, gpt-6-astra) see the task, the evidence and both answers as X / Y in a random order
  (order recorded, model names hidden), score each on 5 criteria 1-10 and pick a preference.

usage: run_none_quality_eval.py OUT_DIR [gen|judge|all]
"""
import concurrent.futures, json, os, random, re, sys, threading, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import run_longctx_synthesis as syn
import run_longctx_supplement as sup

OUT_DIR = sys.argv[1]
PHASE = sys.argv[2] if len(sys.argv) > 2 else "all"
os.makedirs(OUT_DIR, exist_ok=True)
GEN = os.path.join(OUT_DIR, "answers.jsonl")
JUDGE = os.path.join(OUT_DIR, "judgements.jsonl")
lock = threading.Lock()
CONVS = (0, 1, 2, 3)
SEEDS = (11, 22)
EFFORTS = ("high", "none")
JUDGES = (("anthropic/claude-fable-5-2", 6000), ("gpt-6-astra", 6000))
CFG = json.load(open("/home/joseyarashio/.opencodex/config.json"))
KEY = CFG["apiKeys"][0]["key"]
URL = "http://127.0.0.1:10100/v1/chat/completions"


def delivered(r):
    return r.get("status") == 200 and r.get("finish") == "stop" and (r.get("content_tokens") or 0) >= 200 \
        and not r.get("dsml_in_content")


def gen():
    done = set()
    if os.path.exists(GEN):
        for line in open(GEN):
            r = json.loads(line)
            if r.get("status") == 200 and not r.get("err"):
                done.add((r["conv"], r["seed"], r["effort"]))

    def run(conv):
        msgs = syn.apply_keep_n(syn.build_conversation(conv), 2)
        sup.warmup_req(msgs, syn.TOOLS, "auto", "high", f"q_{conv}")
        for seed in SEEDS:
            for effort in EFFORTS:
                if (conv, seed, effort) in done:
                    continue
                body = {
                    "model": sup.MODEL, "messages": msgs, "tools": syn.TOOLS, "tool_choice": "auto",
                    "max_tokens": 32768, "temperature": 0.3, "top_p": 0.95, "top_k": 20, "seed": seed,
                    "reasoning_effort": effort, "stream": True, "stream_options": {"include_usage": True},
                }
                meta, rt, ct = sup.post_stream(body)
                row = {"conv": conv, "seed": seed, "effort": effort, **meta, "content_full": ct}
                with lock, open(GEN, "a", encoding="utf-8") as f:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
                print("GEN", json.dumps({k: row.get(k) for k in ("conv", "seed", "effort", "finish", "reasoning_tokens",
                                                                 "content_tokens", "tool_calls", "engine_loop", "wall_s")}),
                      flush=True)

    with concurrent.futures.ThreadPoolExecutor(3) as ex:
        list(ex.map(run, CONVS))


def evidence(conv):
    msgs = syn.build_conversation(conv)
    task = msgs[1]["content"].split("Objective:", 1)[1].strip()
    tools = []
    for m in msgs:
        if m.get("role") == "assistant" and m.get("tool_calls"):
            c = m["tool_calls"][0]["function"]
            tools.append(f"- call {c['name']}({c['arguments']})")
        elif m.get("role") == "tool":
            tools.append(f"  -> {m['content']}")
    return task, "\n".join(tools), msgs[-1]["content"]


RUBRIC = ["evidence_grounding", "technical_correctness", "completeness_vs_request", "depth_of_reasoning", "actionability"]


def judge_one(model, max_tok, conv, seed, a_high, a_none):
    rnd = random.Random(conv * 1000 + seed * 7 + len(model))
    x_is_high = rnd.random() < 0.5
    x, y = (a_high, a_none) if x_is_high else (a_none, a_high)
    task, tools, ask = evidence(conv)
    prompt = (
        "You are a strict, independent senior distributed-systems reviewer. Two anonymous answers (X and Y) were written "
        "for the same final-synthesis turn of an audit. The workspace was a ~48K-token synthetic Python snapshot made of "
        "hundreds of near-identical `ClusterCoordinator_*` classes (each with a node_id, a state field, a metrics dict "
        "with pfc_pause/rdma_tx/rdma_rx, and an async synchronize_state). The only real evidence is the tool trace below.\n\n"
        f"OBJECTIVE: {task}\n\nTOOL TRACE:\n{tools}\n\nFINAL USER REQUEST: {ask}\n\n"
        "Score each answer 1-10 on: " + ", ".join(RUBRIC) + ". Penalize invented facts not supported by the trace or the "
        "snapshot description, logical errors, and ignoring parts of the request. Length alone is not quality. Then give "
        "a preference: X, Y or tie.\n"
        "Reply with ONLY a JSON object: {\"X\": {criterion: score, ...}, \"Y\": {criterion: score, ...}, "
        "\"preference\": \"X|Y|tie\", \"reason\": \"<= 60 words\"}\n\n"
        f"===== ANSWER X =====\n{x}\n\n===== ANSWER Y =====\n{y}\n"
    )
    body = {"model": model, "messages": [{"role": "user", "content": prompt}], "max_tokens": max_tok, "temperature": 0.0}
    req = urllib.request.Request(URL, json.dumps(body, ensure_ascii=False).encode(),
                                 {"Content-Type": "application/json", "Authorization": f"Bearer {KEY}"})
    t0 = time.perf_counter()
    out = {"model": model, "conv": conv, "seed": seed, "x_is_high": x_is_high}
    for attempt in range(3):
        try:
            r = json.load(urllib.request.urlopen(req, timeout=900))
            msg = r["choices"][0]["message"]
            txt = msg.get("content") or ""
            m = re.search(r"\{.*\}", txt, re.S)
            j = json.loads(m.group(0))
            high = j["X"] if x_is_high else j["Y"]
            none = j["Y"] if x_is_high else j["X"]
            pref = j.get("preference", "tie").strip()
            winner = "tie" if pref.lower() == "tie" else ("high" if (pref.upper() == "X") == x_is_high else "none")
            out.update({"ok": True, "high": high, "none": none, "winner": winner, "reason": j.get("reason"),
                        "wall_s": round(time.perf_counter() - t0, 1)})
            break
        except Exception as e:
            out.update({"ok": False, "err": repr(e)[:200]})
            time.sleep(5 * (attempt + 1))
    with lock, open(JUDGE, "a", encoding="utf-8") as f:
        f.write(json.dumps(out, ensure_ascii=False) + "\n")
    print("JUDGE", json.dumps({k: out.get(k) for k in ("model", "conv", "seed", "ok", "winner", "reason")},
                              ensure_ascii=False), flush=True)


def judge():
    rows = [json.loads(l) for l in open(GEN)]
    by = {}
    for r in rows:
        by[(r["conv"], r["seed"], r["effort"])] = r
    jobs = []
    for conv in CONVS:
        for seed in SEEDS:
            h, n = by.get((conv, seed, "high")), by.get((conv, seed, "none"))
            if h and n and delivered(h) and delivered(n):
                for model, mt in JUDGES:
                    jobs.append((model, mt, conv, seed, h["content_full"], n["content_full"]))
    print("judge jobs", len(jobs), flush=True)
    with concurrent.futures.ThreadPoolExecutor(4) as ex:
        list(ex.map(lambda a: judge_one(*a), jobs))


if PHASE in ("gen", "all"):
    gen()
if PHASE in ("judge", "all"):
    judge()
