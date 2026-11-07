#!/usr/bin/env python3
import concurrent.futures
import json
import logging
import os
import random
import string
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List

API_URL = "http://127.0.0.1:8889/v1/chat/completions"
STATUS_URL = "http://127.0.0.1:8889/proxy/status"
DURATION_SECONDS = 18000  # 5 hours (18000s)
MAX_CONCURRENCY = 8     # 6 active GPU slots + 2 standby queue (within 14 limit)
OUTPUT_FILE = Path("/home/joseyarashio/dgx-spark-tp2-recipes/benchmarks/results/stress_5hour_experiment.json")

# Prepare shared prefix pools for High-Hit scenarios (up to 20K~25K tokens)
def generate_codebase_corpus(num_tokens: int, seed_str: str) -> str:
    random.seed(seed_str)
    lines = []
    lines.append(f"# Synthetic Codebase Block [{seed_str}] target {num_tokens} tokens")
    current_tokens = 0
    i = 0
    while current_tokens < num_tokens:
        cls_name = f"ClusterCoordinator_{seed_str}_{i}"
        chunk = f"""
class {cls_name}:
    def __init__(self, node_id: int = {i}):
        self.node_id = node_id
        self.state = 'INITIALIZED'
        self.metrics = {{'pfc_pause': 0, 'rdma_tx': 1048576, 'rdma_rx': 1048576}}

    async def synchronize_state(self, peer_ip: str, timeout_ms: int = 250):
        if not peer_ip.startswith('10.100.'):
            raise ValueError('Invalid cluster CIDR subnet')
        return True
"""
        lines.append(chunk)
        current_tokens += len(chunk.split()) * 2  # Approximate token count
        i += 1
    return "\n".join(lines)

print("Pre-generating high-hit shared corpora (5K, 12K, 22K tokens)...")
SHARED_CORPUS_5K = generate_codebase_corpus(5000, "shared_5k_pool")
SHARED_CORPUS_12K = generate_codebase_corpus(12000, "shared_12k_pool")
SHARED_CORPUS_22K = generate_codebase_corpus(22000, "shared_22k_pool")
SHARED_POOLS = [SHARED_CORPUS_5K, SHARED_CORPUS_12K, SHARED_CORPUS_22K]

def send_chat_completion(messages: List[Dict[str, str]], max_tokens: int = 384, priority: int = 1, enable_thinking: bool = False) -> Dict[str, Any]:
    payload = {
        "model": "DeepSeek-V4.1-Flash-1017-TF",
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.3,
        "top_p": 0.95,
        "top_k": 20,
        "stream": True,
        "chat_template_kwargs": {"enable_thinking": enable_thinking}
    }
    data_bytes = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(API_URL, data=data_bytes, headers={
        "Content-Type": "application/json",
        "X-Priority": str(priority)
    })

    t0 = time.perf_counter()
    first_token_t = None
    total_tokens = 0
    cached_tokens = 0
    status_code = 0
    error_msg = None

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            status_code = resp.status
            for line in resp:
                if not line:
                    continue
                line_str = line.decode("utf-8", errors="replace").strip()
                if not line_str.startswith("data: "):
                    continue
                data_part = line_str[6:].strip()
                if data_part == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_part)
                    if first_token_t is None:
                        first_token_t = time.perf_counter()
                    choices = chunk.get("choices", [])
                    if choices:
                        delta = choices[0].get("delta", {})
                        if delta.get("content") or delta.get("reasoning_content"):
                            total_tokens += 1
                    # Extract usage / cache info if available
                    usage = chunk.get("usage")
                    if usage:
                        prompt_details = usage.get("prompt_tokens_details") or {}
                        if "cached_tokens" in prompt_details:
                            cached_tokens = prompt_details["cached_tokens"]
                except Exception:
                    pass
    except urllib.error.HTTPError as e:
        status_code = e.code
        error_msg = f"HTTP {e.code}"
    except Exception as e:
        status_code = 500
        error_msg = str(e)

    t1 = time.perf_counter()
    wall = round(t1 - t0, 4)
    ttft = round((first_token_t - t0), 4) if first_token_t else wall

    return {
        "status_code": status_code,
        "wall_seconds": wall,
        "ttft_seconds": ttft,
        "tokens": total_tokens,
        "cached_tokens": cached_tokens,
        "error": error_msg
    }

def worker_job(job_id: int) -> Dict[str, Any]:
    # Random scenario: High-Hit (60%) vs Low-Hit/Unique (40%)
    is_high_hit = random.random() < 0.60
    # Length tiers: Short (<2K, 30%), Medium (2K-8K, 40%), Long (10K-25K, 30%)
    len_tier = random.choices(["short", "medium", "long"], weights=[0.35, 0.40, 0.25])[0]

    if is_high_hit:
        mode = "HIGH_HIT"
        if len_tier == "short":
            prefix = SHARED_CORPUS_5K[:2000]
        elif len_tier == "medium":
            prefix = SHARED_CORPUS_12K
        else:
            prefix = SHARED_CORPUS_22K
        query = f"Task {job_id}: Please analyze function block #{random.randint(1, 50)} and summarize invariants."
    else:
        mode = "LOW_HIT"
        # Generate dynamic random text to defeat prefix caching
        rand_salt = "".join(random.choices(string.ascii_letters + string.digits, k=32))
        if len_tier == "short":
            prefix = f"# Dynamic Unique Module [{rand_salt}]\n" + ("x = 10\n" * 300)
        elif len_tier == "medium":
            prefix = f"# Dynamic Unique Module [{rand_salt}]\n" + generate_codebase_corpus(4000, rand_salt)
        else:
            prefix = f"# Dynamic Unique Module [{rand_salt}]\n" + generate_codebase_corpus(12000, rand_salt)
        query = f"Unique verification task {job_id} on ephemeral code."

    messages = [
        {"role": "system", "content": "You are a senior systems engineer reviewing clustered code."},
        {"role": "user", "content": f"Codebase Context:\n```python\n{prefix}\n```\n\nQuestion: {query}"}
    ]
    # Estimate prompt tokens (~4 chars per token)
    prompt_len_approx = len(prefix) // 4
    priority = random.choice([0, 1, 1, 1, 2]) # 0=foreground, 1=normal, 2=background

    # Ample generation budget (384 ~ 1024 tokens) to ensure full reasoning + output decode window
    max_tokens_budget = random.choice([256, 384, 512])
    enable_thinking = random.choice([False, False, True]) # 66% standard generation, 33% deep thinking
    t_start = time.time()
    res = send_chat_completion(messages, max_tokens=max_tokens_budget, priority=priority, enable_thinking=enable_thinking)
    res.update({
        "job_id": job_id,
        "mode": mode,
        "len_tier": len_tier,
        "prompt_tokens_approx": prompt_len_approx,
        "priority": priority,
        "timestamp": t_start
    })
    # If received non-200 (queue full/timeout/error), backoff slightly (1~2.5s) to mimic real Agent behavior
    if res.get("status_code") != 200:
        time.sleep(random.uniform(1.0, 2.5))
    return res

def main():
    print(f"=== Starting 5-Hour Random Concurrency Experiment (Duration: {DURATION_SECONDS}s / 5.0h, Concurrency: {MAX_CONCURRENCY}) ===")
    t_end = time.time() + DURATION_SECONDS
    job_counter = 0
    all_results = []
    minute_samples = []

    last_report_t = time.time()
    report_interval = 60 # print brief status every 1 minute to track live progress

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_CONCURRENCY) as executor:
        active_futures = {}
        # Prime the executor with initial jobs
        for _ in range(MAX_CONCURRENCY):
            job_counter += 1
            f = executor.submit(worker_job, job_counter)
            active_futures[f] = job_counter

        while time.time() < t_end or active_futures:
            # Wait for at least one future to complete
            done, _ = concurrent.futures.wait(active_futures.keys(), timeout=1.0, return_when=concurrent.futures.FIRST_COMPLETED)
            for f in done:
                jid = active_futures.pop(f)
                try:
                    res = f.result()
                    all_results.append(res)
                except Exception as e:
                    all_results.append({"job_id": jid, "status_code": 500, "error": str(e), "wall_seconds": 0})
                    time.sleep(1.0) # Backoff on unexpected error to prevent tight spin loops

                # If within 30 min duration, replenish worker
                if time.time() < t_end:
                    job_counter += 1
                    new_f = executor.submit(worker_job, job_counter)
                    active_futures[new_f] = job_counter

            # Periodic status logging
            if time.time() - last_report_t >= report_interval:
                last_report_t = time.time()
                elapsed_min = (time.time() - (t_end - DURATION_SECONDS)) / 60.0
                sc_counts = {}
                for r in all_results[-100:]:
                    sc_counts[r["status_code"]] = sc_counts.get(r["status_code"], 0) + 1
                
                # Fetch Proxy status
                cold_info = {}
                try:
                    with urllib.request.urlopen(STATUS_URL, timeout=3) as resp:
                        pst = json.loads(resp.read().decode())
                        cold_info = pst.get("cold_kv", {})
                except Exception:
                    pass

                print(f"  [Progress {elapsed_min:.1f}/300.0 min] Total requests completed: {len(all_results)} | Recent 100 Status: {sc_counts} | Cold KV count: {cold_info.get('cold_sessions_count')}, {cold_info.get('total_cold_mb')} MB")
                minute_samples.append({
                    "elapsed_minutes": round(elapsed_min, 2),
                    "total_completed": len(all_results),
                    "cold_kv": cold_info
                })

    print(f"\n=== 5-Hour Experiment Finished! Total requests: {len(all_results)} ===")
    
    # Save full results
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    summary_data = {
        "experiment_duration_s": DURATION_SECONDS,
        "max_concurrency": MAX_CONCURRENCY,
        "total_requests": len(all_results),
        "minute_samples": minute_samples,
        "results": all_results
    }
    with open(OUTPUT_FILE, "w") as f:
        json.dump(summary_data, f)
    print(f"Results saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
