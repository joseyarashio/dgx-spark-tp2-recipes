#!/usr/bin/env python3
"""Multi-turn prefix-reuse loss probe (Edge0 "multi-turn reuse sometimes recomputes" check, adapted to TensorFold).

For every turn of a scripted multi-turn conversation it records the served prompt ids (via /tokenize on the same
messages, after replicating the server's --drop-reasoning-history), the previous turn's prompt ids and generated ids
(return_token_ids), and usage.cached_tokens, then splits the uncached prefill of each turn into:

  new        tokens after the ideal resume point (new user/tool message + generation header): unavoidable
  reply      the previous turn's generated reply, re-prefilled because states are only kept inside a prompt pass
  drift      previous prompt tokens that no longer prefix the new prompt (template/reasoning-drop rewrite)
  grain      prefix that is stable but not resumed (2048-row chunk floor, history_len mark placement, misses)
  retok      generated ids that differ from the re-rendered reply (Edge0's tokenization-mismatch case)

  P - C = new + reply + drift + grain        (reply/retok overlap: retok is reported, not added)

Usage: run_prefix_reuse_probe.py [--base http://127.0.0.1:8889] [--turns 6] [--out results/prefix_reuse_probe.json]
"""
import argparse, json, os, random, time, urllib.request

MODEL = "DeepSeek-V4.1-Flash-TF"
KEEP_LAST_N = 2  # rank0.sh: --drop-reasoning-history --keep-last-n-reasoning 2


def post(base, path, body, timeout=900):
    req = urllib.request.Request(base + path, data=json.dumps(body, ensure_ascii=False).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def lcp(a, b):
    n = min(len(a), len(b))
    i = 0
    while i < n and a[i] == b[i]:
        i += 1
    return i


def drop_reasoning(msgs, keep):
    """zig/src/server/messages.zig dropReasoning: strip reasoning_content from all but the last `keep` carriers."""
    carriers = [i for i, m in enumerate(msgs) if m.get("reasoning_content") is not None]
    drop = set(carriers[:max(0, len(carriers) - keep)])
    out = []
    for i, m in enumerate(msgs):
        m = dict(m)
        if i in drop:
            m.pop("reasoning_content", None)
        out.append(m)
    return out


def args_as_objects(msgs):
    """zig/src/server/messages.zig toolArguments: /tokenize skips it, so parse string arguments here."""
    out = []
    for m in msgs:
        if m.get("tool_calls"):
            m = dict(m)
            calls = []
            for c in m["tool_calls"]:
                c = json.loads(json.dumps(c))
                a = c.get("function", {}).get("arguments")
                if isinstance(a, str):
                    try:
                        c["function"]["arguments"] = json.loads(a)
                    except Exception:
                        c["function"]["arguments"] = {"_invalid_arguments": a}
                calls.append(c)
            m["tool_calls"] = calls
        out.append(m)
    return out


def corpus(seed, words):
    rng = random.Random(seed)
    vocab = ("service request queue latency budget kernel thread memory buffer socket cache prefix chunk "
             "token stream slot lane rank node clock thermal governor proxy engine snapshot imprint disk").split()
    return "\n".join(f"L{seed}-{i}: " + " ".join(rng.choice(vocab) for _ in range(14)) + "."
                     for i in range(words // 14))


TOOLS = [{"type": "function", "function": {
    "name": "read_file", "description": "Read a line range of a source file.",
    "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "start": {"type": "integer"},
                                                    "end": {"type": "integer"}}, "required": ["path"]}}}]


def scenario_defs(seed):
    sys_doc = corpus(seed, 7000)  # ~9-10K tokens: above min_prompt, several 2048 chunks
    sys_agent = ("You are a code-review agent. Use read_file to inspect files before answering; call one tool "
                 "per step. Codebase index follows.\n" + sys_doc)
    sys_chat = "You are a concise assistant. Reference document follows.\n" + sys_doc
    qs = ["Summarize the reference in two sentences.", "Which word appears most often in lines 10-20?",
          "Give one risk this document implies.", "Rewrite your previous answer as a bullet list.",
          "What would you check next?", "Answer in one word: is the document consistent?",
          "List three line ids you looked at.", "Done. Final one-line conclusion."]
    return [
        # name, system, tools, thinking, echo_reasoning
        ("A_chat_think_echo", sys_chat, None, True, True),
        ("B_agent_tools_think_echo", sys_agent, TOOLS, True, True),
        ("C_agent_tools_think_noecho", sys_agent, TOOLS, True, False),
        ("D_agent_tools_nothink", sys_agent, TOOLS, False, False),
    ], qs


def run_scenario(base, name, system, tools, thinking, echo, qs, turns, seed, max_tokens):
    msgs = [{"role": "system", "content": system}, {"role": "user", "content": qs[0]}]
    prev_prompt, prev_gen = None, []
    rows = []
    rng = random.Random(seed)
    for t in range(turns):
        body = {"model": MODEL, "messages": msgs, "stream": False, "max_tokens": max_tokens, "temperature": 0,
                "return_token_ids": True, "chat_template_kwargs": {"enable_thinking": thinking}}
        if tools:
            body["tools"] = tools
        served = drop_reasoning(args_as_objects(msgs), KEEP_LAST_N)
        tk = {"model": MODEL, "messages": served, "add_generation_prompt": True,
              "chat_template_kwargs": {"enable_thinking": thinking}}
        if tools:
            tk["tools"] = tools
        ids = post(base.replace(":8889", ":8888"), "/tokenize", tk)["tokens"]
        # the history the server marks (prepare(): render without the generation header); new_msg = P - history
        k = len(served)
        while k > 0 and served[k - 1]["role"] != "assistant":
            k -= 1
        hist_len = 0
        if k > 0:
            th = dict(tk, messages=served[:k], add_generation_prompt=False)
            hist_len = len(post(base.replace(":8889", ":8888"), "/tokenize", th)["tokens"])
        t0 = time.time()
        r = post(base, "/v1/chat/completions", body)
        wall = time.time() - t0
        u = r.get("usage", {})
        P = u.get("prompt_tokens", 0)
        C = (u.get("prompt_tokens_details") or {}).get("cached_tokens", 0)
        tf = r.get("tensorfold") or {}
        gen = list(tf.get("token_ids") or [])
        row = {"turn": t + 1, "prompt": P, "tokenize_len": len(ids), "len_match": P == len(ids), "cached": C,
               "uncached": P - C, "prefill_s": tf.get("prefill_seconds"), "ttft_s": tf.get("time_to_first_token"),
               "wall_s": round(wall, 3), "gen_tokens": len(gen), "finish": r["choices"][0].get("finish_reason")}
        if prev_prompt is not None:
            full = prev_prompt + prev_gen
            d_prompt = lcp(prev_prompt, ids)          # stable part of the previous prompt
            d_full = lcp(full, ids)                   # stable part incl. the generated reply
            new = P - d_full
            reply = max(0, d_full - len(prev_prompt))
            drift = len(prev_prompt) - d_prompt
            grain = max(0, d_prompt - C)
            row.update({"prev_prompt": len(prev_prompt), "prev_gen": len(prev_gen), "lcp_prev_prompt": d_prompt,
                        "lcp_prev_full": d_full, "new": new, "reply": reply, "drift": drift, "grain": grain,
                        "retok": len(full) - d_full if d_full >= len(prev_prompt) else None,
                        "hist_len": hist_len, "hist_floor2048": hist_len // 2048 * 2048,
                        "new_msg": P - hist_len,                       # truly new: user/tool msg + header
                        "rerender": max(0, hist_len - d_full),          # prior turn as re-rendered, not resumable
                        "lost_to_grain": max(0, min(d_full, hist_len) - C),  # resumable but below no kept state
                        "drift_at": d_prompt if drift else None,
                        "check": (new + reply + drift + grain) - (P - C)})
        rows.append(row)
        prev_prompt, prev_gen = ids, gen
        m = r["choices"][0]["message"]
        am = {"role": "assistant", "content": m.get("content") or ""}
        if echo and m.get("reasoning_content"):
            am["reasoning_content"] = m["reasoning_content"]
        if m.get("tool_calls"):
            am["tool_calls"] = m["tool_calls"]
        msgs.append(am)
        if m.get("tool_calls"):
            for c in m["tool_calls"]:
                msgs.append({"role": "tool", "tool_call_id": c.get("id", "call"),
                             "content": corpus(rng.randrange(1 << 30), 900)})
        else:
            msgs.append({"role": "user", "content": qs[(t + 1) % len(qs)]})
        print(f"  {name} t{t+1}: P={P} C={C} unc={P-C} " + " ".join(
            f"{k}={row[k]}" for k in ("new_msg", "rerender", "lost_to_grain", "reply", "drift", "retok", "hist_len",
                                      "prefill_s") if k in row), flush=True)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8889")
    ap.add_argument("--turns", type=int, default=6)
    ap.add_argument("--max-tokens", type=int, default=400)
    ap.add_argument("--seed", type=int, default=int(time.time()))
    ap.add_argument("--only", default="")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "results",
                                                  f"prefix_reuse_probe_{time.strftime('%Y%m%d_%H%M%S')}.json"))
    a = ap.parse_args()
    defs, qs = scenario_defs(a.seed)
    report = {"seed": a.seed, "base": a.base, "keep_last_n": KEEP_LAST_N, "scenarios": {}}
    for i, (name, system, tools, thinking, echo) in enumerate(defs):
        if a.only and a.only not in name:
            continue
        print(f"[{name}] tools={bool(tools)} thinking={thinking} echo_reasoning={echo}", flush=True)
        # a fresh system prompt per scenario so scenarios never resume each other's states
        sysx = f"[probe {a.seed}-{i}]\n" + system
        rows = run_scenario(a.base, name, sysx, tools, thinking, echo, qs, a.turns, a.seed + i, a.max_tokens)
        tail = [r for r in rows if "new" in r]
        agg = {k: sum(r[k] for r in tail) for k in ("prompt", "cached", "uncached", "new", "reply", "drift", "grain",
                                                     "new_msg", "rerender", "lost_to_grain")}
        agg["prefill_s"] = round(sum(r["prefill_s"] or 0 for r in tail), 3)
        agg["turn1_prefill_s"] = rows[0]["prefill_s"]
        agg["turn1_prompt"] = rows[0]["prompt"]
        agg["retok_turns"] = sum(1 for r in tail if r.get("retok"))
        agg["len_mismatch_turns"] = sum(1 for r in rows if not r["len_match"])
        report["scenarios"][name] = {"tools": bool(tools), "thinking": thinking, "echo_reasoning": echo,
                                     "rows": rows, "turns2plus": agg}
        print(f"  => {agg}", flush=True)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    json.dump(report, open(a.out, "w"), indent=1)
    print("wrote", a.out)


if __name__ == "__main__":
    main()
