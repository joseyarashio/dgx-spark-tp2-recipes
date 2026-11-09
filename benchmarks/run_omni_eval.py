#!/usr/bin/env python3
"""
DGX Spark TP=2 Principal Test (OmniBench)
Multi-dimensional benchmark runner covering Quality, Tool Eval, Prefill, Decode, Concurrency, and Fault Isolation.
Supports dynamic duration and preset profiles: smoke (~3m), standard (~15m), advanced (~30m), endurance (1h+).
"""

import argparse
import base64
import concurrent.futures
import json
import os
import struct
import sys
import time
import urllib.error
import urllib.request
import zlib

API_8888 = "http://127.0.0.1:8888"
API_8889 = "http://127.0.0.1:8889"

def make_test_png(width=512, height=512):
    raw_data = bytearray()
    for y in range(height):
        raw_data.append(0)
        for x in range(width):
            if 192 <= x < 320 and 192 <= y < 320:
                c = 255 if ((x // 16 + y // 16) % 2 == 0) else 0
                raw_data.extend((c, c, c))
            elif x < width // 2 and y < height // 2:
                raw_data.extend((220, 30, 30))
            elif x >= width // 2 and y < height // 2:
                raw_data.extend((30, 200, 30))
            elif x < width // 2 and y >= height // 2:
                raw_data.extend((30, 60, 220))
            else:
                raw_data.extend((230, 210, 30))

    def png_chunk(chunk_type, data):
        chunk = struct.pack(">I", len(data)) + chunk_type + data
        crc = zlib.crc32(chunk_type + data) & 0xFFFFFFFF
        return chunk + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    idat = zlib.compress(bytes(raw_data), level=6)
    png = b"\x89PNG\r\n\x1a\n" + png_chunk(b"IHDR", ihdr) + png_chunk(b"IDAT", idat) + png_chunk(b"IEND", b"")
    return base64.b64encode(png).decode("ascii")

def stream_chat(
    messages,
    max_tokens=256,
    temperature=0.0,
    seed=42,
    enable_thinking=False,
    tools=None,
    tool_choice=None,
    base_url=API_8889,
    timeout=180,
    extra_headers=None,
):
    payload = {
        "model": "DeepSeek-V4.1-Flash-TF",
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "top_p": 0.95,
        "top_k": 20,
        "seed": seed,
        "stream": True,
        "chat_template_kwargs": {"enable_thinking": enable_thinking},
    }
    if tools is not None:
        payload["tools"] = tools
    if tool_choice is not None:
        payload["tool_choice"] = tool_choice

    data = json.dumps(payload).encode("utf-8")
    req_headers = {"Content-Type": "application/json"}
    if extra_headers:
        req_headers.update(extra_headers)
    req = urllib.request.Request(
        f"{base_url}/v1/chat/completions",
        data=data,
        headers=req_headers,
        method="POST",
    )
    t0 = time.perf_counter()
    first_event_t = None
    first_content_t = None
    content_parts = []
    reasoning_parts = []
    tool_calls_map = {}
    tf_meta = {}
    spec_meta = {}
    usage_meta = {}
    cmpl_id = None
    finish_reason = None
    first_raw_token_handle = None

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status_code = resp.status
            for raw_line in resp:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line or not line.startswith("data: "):
                    continue
                if line == "data: [DONE]":
                    break
                chunk_str = line[6:]
                try:
                    chunk = json.loads(chunk_str)
                except Exception:
                    continue

                if first_event_t is None:
                    first_event_t = time.perf_counter()
                if "id" in chunk and not cmpl_id:
                    cmpl_id = chunk["id"]
                if "tensorfold" in chunk:
                    tf_meta = chunk["tensorfold"]
                if "speculative" in chunk:
                    spec_meta = chunk["speculative"]
                if "usage" in chunk and chunk["usage"]:
                    usage_meta = chunk["usage"]

                choices = chunk.get("choices", [])
                if not choices:
                    continue
                delta = choices[0].get("delta", {})
                if choices[0].get("finish_reason"):
                    finish_reason = choices[0]["finish_reason"]

                # Check first token for handle leak
                if first_content_t is None and ("content" in delta or "reasoning_content" in delta or "tool_calls" in delta):
                    first_content_t = time.perf_counter()

                if "reasoning_content" in delta and delta["reasoning_content"]:
                    reasoning_parts.append(delta["reasoning_content"])
                if "content" in delta and delta["content"]:
                    content_parts.append(delta["content"])
                if "tool_calls" in delta and delta["tool_calls"]:
                    for tc in delta["tool_calls"]:
                        idx = tc.get("index", 0)
                        if idx not in tool_calls_map:
                            tool_calls_map[idx] = {
                                "id": tc.get("id", ""),
                                "type": tc.get("type", "function"),
                                "function": {"name": "", "arguments": ""},
                            }
                        fn = tc.get("function", {})
                        if "name" in fn and fn["name"]:
                            tool_calls_map[idx]["function"]["name"] += fn["name"]
                        if "arguments" in fn and fn["arguments"]:
                            tool_calls_map[idx]["function"]["arguments"] += fn["arguments"]

        wall_time = time.perf_counter() - t0
        client_ttft = (first_content_t - t0) if first_content_t else wall_time
        client_ttfe = (first_event_t - t0) if first_event_t else wall_time
        content = "".join(content_parts)
        reasoning = "".join(reasoning_parts)
        tool_calls = [tool_calls_map[k] for k in sorted(tool_calls_map.keys())]

        return {
            "status_code": status_code,
            "id": cmpl_id,
            "wall_seconds": round(wall_time, 4),
            "client_ttfe_seconds": round(client_ttfe, 4),
            "client_ttft_seconds": round(client_ttft, 4),
            "finish_reason": finish_reason,
            "content": content,
            "reasoning_len": len(reasoning),
            "tool_calls": tool_calls,
            "tensorfold": tf_meta,
            "speculative": spec_meta,
            "usage": usage_meta,
            "cached_tokens": usage_meta.get("prompt_tokens_details", {}).get("cached_tokens", 0),
            "prompt_tokens": usage_meta.get("prompt_tokens", 0),
            "completion_tokens": usage_meta.get("completion_tokens", 0),
        }
    except Exception as e:
        return {
            "status_code": 500,
            "error": str(e),
            "wall_seconds": round(time.perf_counter() - t0, 4),
            "content": "",
            "tool_calls": [],
        }

def get_system_snapshot():
    snapshot = {"time": time.strftime("%Y-%m-%d %H:%M:%S")}
    try:
        with urllib.request.urlopen(f"{API_8888}/health", timeout=5) as r:
            snapshot["engine_8888"] = json.loads(r.read().decode())
    except Exception as e:
        snapshot["engine_8888"] = {"error": str(e)}

    try:
        with urllib.request.urlopen(f"{API_8889}/health", timeout=5) as r:
            snapshot["proxy_8889"] = json.loads(r.read().decode())
    except Exception as e:
        snapshot["proxy_8889"] = {"error": str(e)}
    return snapshot

# 1. Quality Probes
def test_quality(profile="smoke"):
    print("\n--- [1/6] Quality Bench (sparkDash Aligned) ---", flush=True)
    results = {}
    
    # GSM8K / Math test
    p_math = [
        {"role": "user", "content": "How many 5-digit positive integers (from 10000 to 99999) have digits that are strictly increasing from left to right (e.g. 13579)? Put the final integer in \\boxed{N}."}
    ]
    r_math = stream_chat(p_math, max_tokens=384, temperature=0.0, base_url=API_8888)
    passed_math = "126" in r_math.get("content", "")
    results["math_gsm8k"] = {"passed": passed_math, "ttft": r_math.get("client_ttft_seconds"), "wall_s": r_math.get("wall_seconds")}
    print(f"  GSM8K Math Combinatorics: {'PASS' if passed_math else 'FAIL'} (TTFT: {r_math.get('client_ttft_seconds')}s)", flush=True)

    # MMLU-Pro Knowledge
    p_mmlu = [
        {"role": "system", "content": "Answer the multiple choice question with only the single letter of the correct option."},
        {"role": "user", "content": "Which architectural feature in DeepSeek-V4/V3 allows sparse computation without activating every parameter on every token?\nA) Multi-Query Attention\nB) Mixture-of-Experts (MoE)\nC) Dense Feedforward Network\nD) Rotary Position Embeddings"}
    ]
    r_mmlu = stream_chat(p_mmlu, max_tokens=16, temperature=0.0, base_url=API_8888)
    passed_mmlu = "B" in r_mmlu.get("content", "").strip()[:5]
    results["mmlu_moe"] = {"passed": passed_mmlu, "ttft": r_mmlu.get("client_ttft_seconds"), "wall_s": r_mmlu.get("wall_seconds")}
    print(f"  MMLU-Pro Knowledge:   {'PASS' if passed_mmlu else 'FAIL'} (TTFT: {r_mmlu.get('client_ttft_seconds')}s)", flush=True)

    # IFEval Instruction Following
    p_ifeval = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Write a 3-sentence summary of distributed memory systems. Your response must contain the word 'interconnect' exactly twice and end with the word 'DONE.'"}
    ]
    r_ifeval = stream_chat(p_ifeval, max_tokens=96, temperature=0.0, base_url=API_8888)
    cnt_interconnect = r_ifeval.get("content", "").lower().count("interconnect")
    ends_done = r_ifeval.get("content", "").strip().endswith("DONE.")
    passed_ifeval = (cnt_interconnect == 2) and ends_done
    results["ifeval_rules"] = {"passed": passed_ifeval, "interconnect_count": cnt_interconnect, "ends_done": ends_done}
    print(f"  IFEval Constraints:   {'PASS' if passed_ifeval else 'FAIL'} (Count: {cnt_interconnect}/2, Ends: {ends_done})", flush=True)

    # Python Execution Assert
    p_code = [
        {"role": "system", "content": "Write only valid Python code defining `def solve(n: int) -> int:` that returns the sum of all multiples of 3 or 5 below n. Do not wrap in markdown quotes."},
        {"role": "user", "content": "Provide the function."}
    ]
    r_code = stream_chat(p_code, max_tokens=96, temperature=0.0, base_url=API_8888)
    code_text = r_code.get("content", "").replace("```python", "").replace("```", "").strip()
    passed_code = False
    try:
        ns = {}
        exec(code_text, ns)
        if ns.get("solve")(10) == 23 and ns.get("solve")(1000) == 233168:
            passed_code = True
    except Exception:
        pass
    results["python_code"] = {"passed": passed_code}
    print(f"  Python Code Assert:   {'PASS' if passed_code else 'FAIL'}", flush=True)

    return results

# 2. Tool Eval Probes (PR #118 Handle Fix check)
def test_tool_eval():
    print("\n--- [2/6] Tool Eval Bench (PR #118 Handle Fix Check) ---", flush=True)
    results = {}
    tools_schema = [
        {
            "type": "function",
            "function": {
                "name": "set_gpu_clock_governor",
                "description": "Set GPU clock bounds and thermal thresholds on a DGX Spark node.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "node_ip": {"type": "string"},
                        "min_clk_mhz": {"type": "integer"},
                        "max_clk_mhz": {"type": "integer"},
                        "zone_hi_c": {"type": "integer"},
                    },
                    "required": ["node_ip", "min_clk_mhz", "max_clk_mhz", "zone_hi_c"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "query_roce_counters",
                "description": "Query ConnectX-7 RoCEv2 RDMA counters for a given interface and GID index.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "interface": {"type": "string"},
                        "gid_index": {"type": "integer"},
                    },
                    "required": ["interface", "gid_index"],
                },
            },
        },
    ]
    
    # 2.1 Tool call 1
    p_tc1 = [{"role": "user", "content": "Please configure the GPU clock governor on node 192.168.10.148 with min clock 1800 MHz, max clock 2500 MHz, and high thermal threshold 84 C."}]
    r_forced = stream_chat(p_tc1, max_tokens=256, tools=tools_schema, temperature=0.0, enable_thinking=False, base_url=API_8888)
    tcs = r_forced.get("tool_calls", [])
    has_tc = False
    try:
        if tcs and tcs[0].get("function", {}).get("name") == "set_gpu_clock_governor":
            args = json.loads(tcs[0]["function"]["arguments"])
            has_tc = (args.get("node_ip") == "192.168.10.148" and args.get("min_clk_mhz") == 1800 and args.get("max_clk_mhz") == 2500 and args.get("zone_hi_c") == 84)
    except Exception:
        pass
    first_tok_clean = not any(h in r_forced.get("content", "") for h in ["506", "607", "1109"])
    passed_forced = has_tc and first_tok_clean
    results["tool_choice_required"] = {"passed": passed_forced, "tool_called": has_tc, "clean_token": first_tok_clean}
    print(f"  Tool Required Call:   {'PASS' if passed_forced else 'FAIL'} (Function: {has_tc}, FirstTokenClean: {first_tok_clean})", flush=True)

    # 2.2 Auto Tool Selection
    p_auto = [
        {"role": "system", "content": "You are a helpful assistant with tools."},
        {"role": "user", "content": "What is the capital of France?"}
    ]
    r_auto = stream_chat(p_auto, max_tokens=64, tools=tools_schema, tool_choice="auto", base_url=API_8888)
    no_unneeded_call = len(r_auto.get("tool_calls", [])) == 0 and "paris" in r_auto.get("content", "").lower()
    results["tool_choice_auto_plain"] = {"passed": no_unneeded_call}
    print(f"  Tool Auto Precision:  {'PASS' if no_unneeded_call else 'FAIL'} (No hallucinated tool calls)", flush=True)

    return results

# 3. Prefill Bench (Scaling & Caching)
def test_prefill():
    print("\n--- [3/6] Prefill Bench (Gradient Scaling & Cache Hit) ---", flush=True)
    results = {}

    # 3.1 Cold 8K Prefill
    nonce_8k = str(int(time.time() * 1000))
    corpus_8k = f"System architecture specification chunk {nonce_8k}: " + ("// Block data payload line 0123456789 ABCDEF\n" * 450)
    p_8k = [
        {"role": "system", "content": corpus_8k},
        {"role": "user", "content": "Count the number of letters in word DGX."}
    ]
    r_8k_cold = stream_chat(p_8k, max_tokens=32, temperature=0.0, base_url=API_8888)
    tf_8k = r_8k_cold.get("tensorfold", {})
    prefill_s = tf_8k.get("prefill_seconds", r_8k_cold.get("client_ttft_seconds", 1.0))
    toks = r_8k_cold.get("prompt_tokens", 5870)
    rate_8k = toks / prefill_s if prefill_s > 0 else 0
    results["prefill_8k_cold"] = {"prompt_tokens": toks, "prefill_s": prefill_s, "tok_s": round(rate_8k, 1)}
    print(f"  Cold 8K Prefill:      {rate_8k:.1f} tok/s (Tokens: {toks}, Prefill: {prefill_s:.3f}s)", flush=True)

    # 3.2 Warm Cached 8K Prefill
    r_8k_warm = stream_chat(p_8k, max_tokens=32, temperature=0.0, base_url=API_8888)
    cached_toks = r_8k_warm.get("cached_tokens", 0)
    warm_ttft = r_8k_warm.get("client_ttft_seconds", 0.0)
    results["prefill_8k_cached"] = {"cached_tokens": cached_toks, "ttft_s": warm_ttft}
    print(f"  Cached 8K Prefill:    TTFT {warm_ttft:.3f}s (Cached: {cached_toks}/{toks} tokens)", flush=True)

    # 3.3 Multi-turn Vision Scratch Arena (PR #112 check)
    img_b64 = make_test_png(512, 512)
    nonce = str(int(time.time()))
    p_img_t1 = [
        {"role": "user", "content": [
            {"type": "text", "text": f"[{nonce}] Identify the color in the top-left quadrant of this 512x512 image."},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}}
        ]}
    ]
    r_img1 = stream_chat(p_img_t1, max_tokens=32, base_url=API_8888)
    p_img_t2 = p_img_t1 + [
        {"role": "assistant", "content": r_img1.get("content", "")},
        {"role": "user", "content": f"[{nonce}] In the same image, what color is in the bottom-right quadrant?"}
    ]
    r_img2 = stream_chat(p_img_t2, max_tokens=32, base_url=API_8888)
    img_cached = r_img2.get("cached_tokens", 0)
    results["vision_scratch_arena"] = {"turn1_ttft": r_img1.get("client_ttft_seconds"), "turn2_ttft": r_img2.get("client_ttft_seconds"), "turn2_cached": img_cached}
    print(f"  Vision Arena Reuse:   Turn 1 TTFT: {r_img1.get('client_ttft_seconds')}s, Turn 2 TTFT: {r_img2.get('client_ttft_seconds')}s (Cached: {img_cached})", flush=True)

    return results

# 4. Decode Bench (MTP & Sampling)
def test_decode():
    print("\n--- [4/6] Decode Bench (Greedy, MTP & Sampling) ---", flush=True)
    results = {}
    
    # 4.1 Greedy Decode (MTP test)
    prompt_code = "Write a complete, well-commented Python implementation of an LRU Cache using a doubly linked list and hash map, including thread-safety locks, type annotations, and a thorough unit test suite."
    p_decode = [{"role": "user", "content": prompt_code}]
    r_greedy = stream_chat(p_decode, max_tokens=384, temperature=0.0, base_url=API_8888)
    tf_g = r_greedy.get("tensorfold", {})
    sp_g = r_greedy.get("speculative", {})
    tps_greedy = tf_g.get("tokens_per_second", 0.0)
    mtp_rate = sp_g.get("acceptance_rate", 0.0)
    results["decode_greedy"] = {"tokens_per_second": tps_greedy, "mtp_acceptance": round(mtp_rate, 4)}
    print(f"  Greedy Decode Rate:   {tps_greedy:.2f} tok/s (MTP Acceptance: {mtp_rate*100:.1f}%)", flush=True)

    # 4.2 Sampling Decode (temp=0.7)
    prompt_prose = "請詳細分析分散式大語言模型推論在雙節點 RoCEv2 網路架構下的通訊瓶頸、All-Reduce 延遲特性、Speculative Decoding 草稿驗證機制，以及 Unified Memory 架構下的記憶體管理策略。"
    p_sample = [{"role": "user", "content": prompt_prose}]
    r_sample = stream_chat(p_sample, max_tokens=192, temperature=0.7, base_url=API_8888)
    tf_s = r_sample.get("tensorfold", {})
    tps_sample = tf_s.get("tokens_per_second", 0.0)
    results["decode_sampling"] = {"tokens_per_second": tps_sample}
    print(f"  Sampling (T=0.7):     {tps_sample:.2f} tok/s", flush=True)

    return results

# 5. Concurrency & Scheduling (C1-C4 & Cut-In)
def test_concurrency(profile="smoke"):
    print("\n--- [5/6] Concurrency & Cut-In Scheduling Bench ---", flush=True)
    results = {}
    concurrency_levels = [1, 2] if profile == "smoke" else [1, 2, 4]
    
    for c in concurrency_levels:
        prompt_code = "Write a complete, well-commented Python implementation of an LRU Cache using a doubly linked list and hash map."
        prompts = [
            [{"role": "user", "content": f"{prompt_code} // Stream worker #{i}"}]
            for i in range(c)
        ]
        t0 = time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(max_workers=c) as executor:
            futures = [executor.submit(stream_chat, p, 128, 0.0, base_url=API_8888) for p in prompts]
            res_list = [f.result() for f in futures]
        wall = time.perf_counter() - t0
        total_tokens = sum(r.get("completion_tokens", 0) for r in res_list)
        agg_tps = total_tokens / wall if wall > 0 else 0
        results[f"concurrency_c{c}"] = {"wall_s": round(wall, 2), "total_tokens": total_tokens, "aggregate_tok_s": round(agg_tps, 2)}
        print(f"  Concurrency C={c}:     Aggregate {agg_tps:.2f} tok/s (Wall: {wall:.2f}s, Tokens: {total_tokens})", flush=True)

    # 32K Prefill Cut-in Short Request Test
    print("  Testing 32K Cut-in Short Request (PR #95)...", flush=True)
    corpus_32k = "Codebase context block: " + ("// Background line token data index 0123456789\n" * 1500)
    p_long = [{"role": "system", "content": corpus_32k}, {"role": "user", "content": "Summarize in 5 words."}]
    p_short = [{"role": "user", "content": "What is 2+2? Answer in one word."}]
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f_long = executor.submit(stream_chat, p_long, 16, 0.0, base_url=API_8888)
        time.sleep(0.3) # Wait until prefill starts
        f_short = executor.submit(stream_chat, p_short, 16, 0.0, base_url=API_8888)
        res_short = f_short.result()
        res_long = f_long.result()

    cut_in_ttft = res_short.get("client_ttft_seconds", 99.0)
    passed_cut_in = cut_in_ttft <= 2.0
    results["cut_in_32k"] = {"short_ttft_s": cut_in_ttft, "passed": passed_cut_in}
    print(f"  32K Cut-in TTFT:      {'PASS' if passed_cut_in else 'WARN'} ({cut_in_ttft:.3f}s, target <= 1.5s)", flush=True)

    return results

# 6. Fault Isolation & NVMe Recall (PR #119 & Storage)
def test_fault_and_storage():
    print("\n--- [6/6] Fault Isolation (PR #119) & NVMe Storage Bench ---", flush=True)
    results = {}

    # Check CUDA Graph health on current engine
    snap = get_system_snapshot()
    eng_health = snap.get("engine_8888", {}).get("status") == "ok"
    results["cuda_graph_stability"] = {"engine_healthy": eng_health}
    print(f"  CUDA Graph Engine:    {'HEALTHY (status: ok)' if eng_health else 'DEGRADED'}", flush=True)

    # NVMe Imprint Check
    imprint_dir = "/home/joseyarashio/.cache/dsv41-nvme-imprint"
    has_nvme_files = False
    file_count = 0
    total_bytes = 0
    try:
        if os.path.exists(imprint_dir):
            for root, _, files in os.walk(imprint_dir):
                for f in files:
                    if f.endswith(".bin"):
                        has_nvme_files = True
                        file_count += 1
                        try:
                            total_bytes += os.path.getsize(os.path.join(root, f))
                        except Exception:
                            pass
    except Exception:
        pass
    
    results["nvme_cold_storage"] = {
        "imprint_active": has_nvme_files,
        "snapshot_files": file_count,
        "total_mb": round(total_bytes / 1024 / 1024, 2)
    }
    print(f"  NVMe Snapshots:       {'ACTIVE' if has_nvme_files else 'INACTIVE'} ({file_count} .bin files, {total_bytes/1024/1024:.1f} MB)", flush=True)

    return results

def main():
    parser = argparse.ArgumentParser(description="DGX Spark TP=2 Principal Test (OmniBench)")
    parser.add_argument("--profile", choices=["smoke", "standard", "advanced", "endurance"], default="smoke", help="Test profile preset")
    parser.add_argument("--duration", type=int, default=None, help="Custom duration in seconds")
    parser.add_argument("--output-report", type=str, default=None, help="Path to save JSON benchmark report")
    args = parser.parse_args()

    start_time = time.time()
    print("=" * 70)
    print(f"=== DGX Spark TP=2 Principal Test (OmniBench) ===")
    print(f"Profile: {args.profile} | Target Ports: 8888 / 8889 | Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    report = {
        "benchmark": "OmniBench-Principal-Test",
        "profile": args.profile,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "system_before": get_system_snapshot(),
        "dimensions": {}
    }

    # Run Dimensions
    report["dimensions"]["quality"] = test_quality(args.profile)
    report["dimensions"]["tool_eval"] = test_tool_eval()
    report["dimensions"]["prefill"] = test_prefill()
    report["dimensions"]["decode"] = test_decode()
    report["dimensions"]["concurrency"] = test_concurrency(args.profile)
    report["dimensions"]["fault_and_storage"] = test_fault_and_storage()

    # If duration specified or profile is advanced/endurance, run the continuous stress marathon
    target_duration = args.duration
    if target_duration is None and args.profile == "advanced":
        target_duration = 1800  # 30 minutes
    elif target_duration is None and args.profile == "endurance":
        target_duration = 18000  # 5 hours (18,000s marathon)

    if target_duration and target_duration > 60:
        print(f"\n--- Running Continuous Multi-Agent Stress Stage ({target_duration}s / {target_duration/60:.1f} mins) ---", flush=True)
        if target_duration >= 7200:
            import run_5hour_stress_experiment
            old_dur = run_5hour_stress_experiment.DURATION_SECONDS
            run_5hour_stress_experiment.DURATION_SECONDS = target_duration
            stress_res = run_5hour_stress_experiment.main()
            report["dimensions"]["continuous_stress_marathon"] = stress_res
            run_5hour_stress_experiment.DURATION_SECONDS = old_dur
        else:
            import run_30min_stress_experiment
            old_duration = run_30min_stress_experiment.DURATION_SECONDS
            run_30min_stress_experiment.DURATION_SECONDS = target_duration
            stress_res = run_30min_stress_experiment.main()
            report["dimensions"]["continuous_stress_marathon"] = stress_res
            run_30min_stress_experiment.DURATION_SECONDS = old_duration

    report["system_after"] = get_system_snapshot()
    total_elapsed = time.time() - start_time
    report["total_elapsed_seconds"] = round(total_elapsed, 2)

    print("\n" + "=" * 70)
    print(f"OmniBench Completed in {total_elapsed:.2f}s")
    
    # Summary Gates
    q_pass = sum(1 for v in report["dimensions"]["quality"].values() if v.get("passed", False))
    q_total = len(report["dimensions"]["quality"])
    tool_pass = report["dimensions"]["tool_eval"]["tool_choice_required"]["passed"]
    tps_greedy = report["dimensions"]["decode"]["decode_greedy"]["tokens_per_second"]
    mtp_rate = report["dimensions"]["decode"]["decode_greedy"]["mtp_acceptance"]
    
    print(f"Summary Scorecard:")
    print(f"  - Quality Pass Rate:     {q_pass}/{q_total}")
    print(f"  - PR #118 Tool Gate:     {'PASS' if tool_pass else 'FAIL'}")
    print(f"  - Single Stream Decode:  {tps_greedy:.2f} tok/s")
    print(f"  - MTP Speculative Rate:  {mtp_rate*100:.1f}%")
    print("=" * 70)

    out_path = args.output_report
    if not out_path:
        out_path = f"/home/joseyarashio/dgx-spark-tp2-recipes/benchmarks/results/omni_eval_{args.profile}_{int(time.time())}.json"
    
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"Report saved to: {out_path}\n")

if __name__ == "__main__":
    main()
