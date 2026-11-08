#!/usr/bin/env python3
import concurrent.futures
import json
import logging
import os
import random
import string
import struct
import sys
import time
import urllib.request
import urllib.error
import zlib
import base64
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List

API_URL = "http://127.0.0.1:8889/v1/chat/completions"
STATUS_URL = "http://127.0.0.1:8889/proxy/status"
DURATION_SECONDS = 1800  # 30 minutes
MAX_CONCURRENCY = int(os.environ.get("MAX_CONCURRENCY", "8"))  # Rebalanced to N=8 (Little's Law equilibrium: 0ms bufferbloat, 99.5%+ delivery)
OUTPUT_FILE = Path(os.environ.get("OUTPUT_FILE", "/home/joseyarashio/dgx-spark-tp2-recipes/benchmarks/results/stress_30min_ms_dtc_experiment.json"))

def make_test_png(width=256, height=256, color_idx=0):
    raw_data = bytearray()
    colors = [
        ((220, 30, 30), (30, 200, 30), (30, 60, 220), (230, 210, 30)),
        ((30, 200, 30), (220, 30, 30), (230, 210, 30), (30, 60, 220)),
        ((30, 60, 220), (230, 210, 30), (220, 30, 30), (30, 200, 30)),
    ][color_idx % 3]
    for y in range(height):
        raw_data.append(0)
        for x in range(width):
            if x < width // 2 and y < height // 2:
                raw_data.extend(colors[0])
            elif x >= width // 2 and y < height // 2:
                raw_data.extend(colors[1])
            elif x < width // 2 and y >= height // 2:
                raw_data.extend(colors[2])
            else:
                raw_data.extend(colors[3])
    def png_chunk(chunk_type, data):
        chunk = struct.pack(">I", len(data)) + chunk_type + data
        crc = zlib.crc32(chunk_type + data) & 0xFFFFFFFF
        return chunk + struct.pack(">I", crc)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    idat = zlib.compress(bytes(raw_data), level=6)
    png = b"\x89PNG\r\n\x1a\n" + png_chunk(b"IHDR", ihdr) + png_chunk(b"IDAT", idat) + png_chunk(b"IEND", b"")
    return base64.b64encode(png).decode("ascii")

print("Pre-generating synthetic multi-turn vision test images...")
VISION_TEST_IMAGES = [make_test_png(256, 256, i) for i in range(3)]
SHARED_VISION_CONTEXT = " ".join([f"cluster_telemetry_metric_{i}" for i in range(1200)])

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
    first_event_t = None
    first_token_t = None
    total_tokens = 0
    usage_completion_tokens = 0
    cached_tokens = 0
    status_code = 0
    error_msg = None
    content_text = []

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
                    if first_event_t is None:
                        first_event_t = time.perf_counter()
                    choices = chunk.get("choices", [])
                    if choices:
                        delta = choices[0].get("delta", {})
                        c = delta.get("content")
                        if isinstance(c, str) and c:
                            content_text.append(c)
                        has_tok = bool(
                            (isinstance(delta.get("content"), str) and len(delta["content"]) > 0)
                            or (isinstance(delta.get("reasoning_content"), str) and len(delta["reasoning_content"]) > 0)
                            or (isinstance(delta.get("tool_calls"), list) and len(delta["tool_calls"]) > 0)
                        )
                        if has_tok:
                            if first_token_t is None:
                                first_token_t = time.perf_counter()
                            total_tokens += 1
                    # Extract usage / cache info if available
                    usage = chunk.get("usage")
                    if usage:
                        if usage.get("completion_tokens"):
                            usage_completion_tokens = int(usage["completion_tokens"])
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
    ttfe = round((first_event_t - t0), 4) if first_event_t else wall
    ttft = round((first_token_t - t0), 4) if first_token_t else wall

    return {
        "status_code": status_code,
        "wall_seconds": wall,
        "ttfe_seconds": ttfe,
        "ttft_seconds": ttft,
        "tokens": usage_completion_tokens or total_tokens,
        "cached_tokens": cached_tokens,
        "content": "".join(content_text),
        "error": error_msg
    }

def worker_job(job_id: int) -> Dict[str, Any]:
    task_choice = random.choices(["HIGH_HIT", "LOW_HIT", "MULTITURN_VISION"], weights=[0.45, 0.35, 0.20])[0]

    if task_choice == "MULTITURN_VISION":
        img_b64 = random.choice(VISION_TEST_IMAGES)
        priority = random.choice([0, 1, 1, 2])
        t_start = time.time()
        # Turn 1
        p1 = [
            {"role": "user", "content": [
                {"type": "text", "text": f"[Diagnostic Log: {SHARED_VISION_CONTEXT}]\nTask {job_id} [Turn 1]: Describe the color quadrants in this image in detail."},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}}
            ]}
        ]
        res1 = send_chat_completion(p1, max_tokens=256, priority=priority, enable_thinking=False)
        res1.update({
            "job_id": job_id,
            "mode": "VISION_TURN1",
            "len_tier": "vision",
            "prompt_tokens_approx": 7600,
            "priority": priority,
            "timestamp": t_start
        })
        if res1.get("status_code") == 200:
            # Turn 2: Followup with cached image context
            ans1 = res1.get("content", "Analyzed image quadrants.")
            p2 = p1 + [
                {"role": "assistant", "content": ans1},
                {"role": "user", "content": f"Task {job_id} [Turn 2]: In the same image, describe the bottom-right corner and identify any geometric pattern in detail."}
            ]
            res2 = send_chat_completion(p2, max_tokens=128, priority=priority, enable_thinking=False)
            res2.update({
                "job_id": f"{job_id}_t2",
                "mode": "VISION_TURN2_CACHED",
                "len_tier": "vision_cached",
                "prompt_tokens_approx": 7800,
                "priority": priority,
                "timestamp": time.time(),
                "turn1_ttft": res1.get("ttft_seconds"),
                "turn2_cached_tokens": res2.get("cached_tokens", 0)
            })
            return res2
        return res1

    # Text tasks
    is_high_hit = (task_choice == "HIGH_HIT")
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
    print(f"=== Starting Random Concurrency Experiment (Duration: {DURATION_SECONDS}s / {DURATION_SECONDS/60:.1f}m, Concurrency: {MAX_CONCURRENCY}) ===")
    t_end = time.time() + DURATION_SECONDS
    job_counter = 0
    all_results = []
    minute_samples = []

    last_report_t = time.time()
    report_interval = 30 # print brief status every 30 seconds to track live progress

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

                print(f"  [Progress {elapsed_min:.1f}/{DURATION_SECONDS/60:.1f} min] Total requests completed: {len(all_results)} | Recent 100 Status: {sc_counts} | Cold KV count: {cold_info.get('cold_sessions_count')}, {cold_info.get('total_cold_mb')} MB")
                minute_samples.append({
                    "elapsed_minutes": round(elapsed_min, 2),
                    "total_completed": len(all_results),
                    "cold_kv": cold_info
                })

    print(f"\n=== {DURATION_SECONDS/60:.1f}-Minute Experiment Finished! Total requests: {len(all_results)} ===")
    
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
    return summary_data

if __name__ == "__main__":
    main()
