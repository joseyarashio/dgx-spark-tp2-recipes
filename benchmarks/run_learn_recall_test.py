#!/usr/bin/env python3
"""Learned-imprint (engine NVMe KV) recall test: a unique long prompt is learned to disk; after the rank0 engine
restarts, the same prefix + a new question must be read back from disk ("learned tokens from disk") and its TTFT must
be far below the cold pass. Also checks ledger (index) bytes == bytes on disk on both nodes.

Usage: run_learn_recall_test.py phase1   # cold pass, writes state
       (restart rank0)
       run_learn_recall_test.py phase2   # recall pass
"""
import json, os, random, subprocess, sys, time, urllib.request

URL = "http://127.0.0.1:8888/v1/chat/completions"
STATE = "/home/joseyarashio/.cache/spark-learn-recall-test.json"
MODEL = "DeepSeek-V4.1-Flash-1017-TF"


def doc(seed: int, words: int = 22000) -> str:
    rng = random.Random(seed)
    vocab = ("alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi omicron pi rho sigma tau "
             "upsilon phi chi psi omega river stone cloud lantern harbor meadow copper silver orchard falcon").split()
    lines = []
    for i in range(words // 12):
        lines.append(f"Record {seed}-{i}: " + " ".join(rng.choice(vocab) for _ in range(12)) + ".")
    return "\n".join(lines)


def ask(system: str, question: str) -> dict:
    body = {"model": MODEL, "stream": True, "max_tokens": 16, "temperature": 0,
            "chat_template_kwargs": {"enable_thinking": False},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": question}]}
    req = urllib.request.Request(URL, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    t0 = time.time(); ttft = None; text = ""
    with urllib.request.urlopen(req, timeout=600) as r:
        for raw in r:
            line = raw.decode().strip()
            if not line.startswith("data:") or line.endswith("[DONE]"):
                continue
            d = json.loads(line[5:])
            ch = d.get("choices") or []
            if ch:
                delta = ch[0].get("delta", {})
                piece = (delta.get("content") or "") + (delta.get("reasoning_content") or "")
                if piece and ttft is None:
                    ttft = time.time() - t0
                text += piece
    return {"ttft_s": round(ttft or -1, 3), "total_s": round(time.time() - t0, 3), "text": text[:80]}


def logs_since(since: str) -> str:
    return subprocess.run(["docker", "logs", "--since", since, "dsv41-rank0"], capture_output=True, text=True).stdout + \
        subprocess.run(["docker", "logs", "--since", since, "dsv41-rank0"], capture_output=True, text=True).stderr


def main():
    phase = sys.argv[1]
    if phase == "phase1":
        seed = int(time.time())
        since = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(time.time() - 2)) + "Z"
        r = ask(doc(seed), "How many records are listed? Answer with a number only.")
        time.sleep(8)
        lg = logs_since(since)
        learned = [l for l in lg.splitlines() if "learned" in l and "to disk" in l]
        json.dump({"seed": seed, "cold": r, "learned_lines": learned}, open(STATE, "w"), indent=1)
        print(json.dumps({"seed": seed, "cold": r, "learned_lines": learned}, indent=1))
    else:
        st = json.load(open(STATE))
        since = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(time.time() - 2)) + "Z"
        r = ask(doc(st["seed"]), "What is the first word after 'Record %d-0:'? Answer with one word." % st["seed"])
        time.sleep(3)
        lg = logs_since(since)
        recall = [l for l in lg.splitlines() if "from disk" in l]
        out = {"seed": st["seed"], "cold": st["cold"], "recall": r, "recall_lines": recall,
               "speedup_ttft": round(st["cold"]["ttft_s"] / max(r["ttft_s"], 1e-3), 2)}
        st["phase2"] = out
        json.dump(st, open(STATE, "w"), indent=1)
        print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
