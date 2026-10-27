#!/usr/bin/env python3
import base64
import concurrent.futures
import io
import json
import os
import subprocess
import sys
import time
import urllib.request
import zlib
import struct

API_URL = "http://127.0.0.1:8888"

def make_test_png(width=512, height=512):
    # Deterministic valid RGB PNG without PIL dependency
    raw_data = bytearray()
    for y in range(height):
        raw_data.append(0)  # filter type 0
        for x in range(width):
            r = (x * 255) // width
            g = (y * 255) // height
            b = 128 if (x // 32 + y // 32) % 2 == 0 else 40
            raw_data.extend((r, g, b))

    def png_chunk(chunk_type, data):
        chunk = struct.pack(">I", len(data)) + chunk_type + data
        crc = zlib.crc32(chunk_type + data) & 0xFFFFFFFF
        return chunk + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    idat = zlib.compress(bytes(raw_data), level=6)
    png = b"\x89PNG\r\n\x1a\n" + png_chunk(b"IHDR", ihdr) + png_chunk(b"IDAT", idat) + png_chunk(b"IEND", b"")
    return base64.b64encode(png).decode("ascii")

def stream_chat(messages, max_tokens=384, temperature=0.30, seed=42, enable_thinking=False, timeout=300):
    payload = {
        "model": "DeepSeek-V4.1-Flash-1017-TF",
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "top_p": 0.95,
        "top_k": 20,
        "seed": seed,
        "stream": True,
        "chat_template_kwargs": {"enable_thinking": enable_thinking},
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{API_URL}/v1/chat/completions",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.perf_counter()
    first_token_t = None
    content_parts = []
    tf_meta = {}
    spec_meta = {}
    usage_meta = {}
    cmpl_id = None

    with urllib.request.urlopen(req, timeout=timeout) as resp:
        for raw_line in resp:
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line or not line.startswith("data: "):
                continue
            body = line[6:].strip()
            if body == "[DONE]":
                break
            try:
                chunk = json.loads(body)
            except Exception:
                continue
            if not cmpl_id and "id" in chunk:
                cmpl_id = chunk["id"]
            if "tensorfold" in chunk:
                tf_meta = chunk["tensorfold"]
            if "speculative" in chunk:
                spec_meta = chunk["speculative"]
            if "usage" in chunk and chunk["usage"]:
                usage_meta = chunk["usage"]
            choices = chunk.get("choices") or []
            if choices:
                delta = choices[0].get("delta") or {}
                c = delta.get("content") or delta.get("reasoning_content") or ""
                if c:
                    if first_token_t is None:
                        first_token_t = time.perf_counter() - t0
                    content_parts.append(c)

    wall_t = time.perf_counter() - t0
    full_text = "".join(content_parts)
    # Grab last rank0 log line for this cmpl_id if available
    log_line = ""
    if cmpl_id:
        try:
            out = subprocess.run(
                f"docker logs --tail 50 dsv41-rank0 2>&1 | grep '{cmpl_id}' | tail -n 1",
                shell=True, text=True, capture_output=True
            ).stdout.strip()
            log_line = out
        except Exception:
            pass

    return {
        "id": cmpl_id,
        "wall_seconds": round(wall_t, 4),
        "client_ttft_seconds": round(first_token_t, 4) if first_token_t is not None else None,
        "tensorfold": tf_meta,
        "speculative": spec_meta,
        "usage": usage_meta,
        "log_line": log_line,
        "reply_preview": full_text[:120],
        "reply_len_chars": len(full_text),
    }

def get_system_metrics():
    def sh(cmd):
        return subprocess.run(cmd, shell=True, text=True, capture_output=True).stdout.strip()

    health = json.loads(sh(f"curl -s {API_URL}/health"))
    proxy = json.loads(sh("curl -s http://127.0.0.1:8889/proxy/status"))

    def parse_node(prefix=""):
        cmd_free = "free -m"
        cmd_buddy = "cat /proc/buddyinfo"
        if prefix:
            free_out = sh(f"ssh -o BatchMode=yes {prefix} '{cmd_free}'")
            buddy_out = sh(f"ssh -o BatchMode=yes {prefix} '{cmd_buddy}'")
        else:
            free_out = sh(cmd_free)
            buddy_out = sh(cmd_buddy)
        mem_avail = 0
        swap_used = 0
        for line in free_out.splitlines():
            parts = line.split()
            if line.startswith("Mem:"):
                mem_avail = int(parts[6])
            elif line.startswith("Swap:") or line.startswith("置換："):
                swap_used = int(parts[2])
        orders_9_13 = []
        for line in buddy_out.splitlines():
            if "Normal" in line:
                nums = [int(x) for x in line.split()[4:]]
                orders_9_13 = nums[9:14]
        return {
            "mem_available_mib": mem_avail,
            "swap_used_mib": swap_used,
            "buddy_normal_orders_9_to_13": orders_9_13,
            "buddy_2mib_plus_blocks_total": sum(orders_9_13),
        }

    return {
        "health": health,
        "proxy": proxy,
        "node1": parse_node(""),
        "node2": parse_node("joseyarashio@10.100.184.1"),
    }

def make_unique_prompt(target_words, tag):
    # Generate un-cached synthetic technical prose of approximately target_words tokens
    base_words = [
        "architecture", "pipeline", "tensor", "bandwidth", "latency", "scheduler",
        "quantization", "trellis", "codebook", "allreduce", "infiniband", "packet",
        "register", "shared", "memory", "coalesced", "warp", "occupancy", "prefetch",
        "asynchronous", "descriptor", "barrier", "ring", "topology", "throughput",
    ]
    chunks = [f"[Session-{tag}-Block-{i}: " + " ".join(base_words[(i + j) % len(base_words)] for j in range(20)) + ".]" for i in range(target_words // 24)]
    return "\n".join(chunks) + "\n\n請用一句話總結上述技術詞彙所屬的領域（只需回答一句話）。"

def main():
    label = sys.argv[1] if len(sys.argv) > 1 else "baseline"
    print(f"=== Running Benchmark Suite: {label} ===")
    results = {"label": label, "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")}

    print("[1/6] Capturing initial system & memory state...")
    results["system_before"] = get_system_metrics()

    prompts = {
        "code": "Write a complete, well-commented Python implementation of an LRU Cache using a doubly linked list and hash map, including thread-safety locks, type annotations, and a thorough unit test suite.",
        "prose": "請詳細分析分散式大語言模型推論在雙節點 RoCEv2 網路架構下的通訊瓶頸、All-Reduce 延遲特性、Speculative Decoding 草稿驗證機制，以及 Unified Memory 架構下的記憶體管理策略。",
        "structured": "Output a strict JSON array of 12 fictional cloud GPU cluster nodes. Each object must contain: node_id (string), rack (string), ip_address (string), gpu_model (string), vram_gb (integer), interconnect_gbps (integer), active_streams (integer), thermal_c (float), and status (enum: healthy, degraded, maintenance). Output JSON only.",
    }

    print("[2/6] Running Single-Stream Decode (Code / Prose / Structured @ temp=0.30 & temp=0.0)...")
    single_decode = {}
    for temp_label, temp_val in [("temp_0.30", 0.30), ("temp_0.0", 0.0)]:
        single_decode[temp_label] = {}
        for name, p in prompts.items():
            r = stream_chat([{"role": "user", "content": p}], max_tokens=384, temperature=temp_val, seed=42)
            tf = r.get("tensorfold", {})
            sp = r.get("speculative", {})
            print(f"  [{temp_label}][{name}] {tf.get('tokens_per_second')} tok/s | accept: {sp.get('acceptance_rate')} | tpr: {sp.get('tokens_per_round')} | log: {r.get('log_line')}")
            single_decode[temp_label][name] = r
    results["single_decode"] = single_decode

    print("[3/6] Running 4-Stream Concurrent Decode Aggregate...")
    c4_prompts = [
        ("code", prompts["code"]),
        ("prose", prompts["prose"]),
        ("structured", prompts["structured"]),
        ("algo", "Implement a complete Red-Black Tree in Python with insert, search, left_rotate, right_rotate, and inorder traversal methods. Include docstrings and complexity analysis."),
    ]
    t_c4_start = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        futs = {
            ex.submit(stream_chat, [{"role": "user", "content": p}], 384, 0.30, 100 + idx): name
            for idx, (name, p) in enumerate(c4_prompts)
        }
        c4_res = {}
        for fut in concurrent.futures.as_completed(futs):
            name = futs[fut]
            c4_res[name] = fut.result()
    c4_wall = time.perf_counter() - t_c4_start
    total_tokens = sum((r.get("usage", {}).get("completion_tokens") or 384) for r in c4_res.values())
    sum_stream_tps = sum((r.get("tensorfold", {}).get("tokens_per_second") or 0.0) for r in c4_res.values())
    print(f"  [4-Stream] Wall: {c4_wall:.2f}s | Aggregate wall tok/s: {total_tokens / c4_wall:.2f} | Sum stream tok/s: {sum_stream_tps:.2f}")
    results["concurrent_4stream"] = {
        "wall_seconds": round(c4_wall, 4),
        "total_completion_tokens": total_tokens,
        "aggregate_wall_tok_s": round(total_tokens / c4_wall, 2),
        "sum_stream_tok_s": round(sum_stream_tps, 2),
        "streams": c4_res,
    }

    print("[4/6] Running Cold Prefill (8K & 32K fresh tokens)...")
    nonce = str(int(time.time()))
    prefill_res = {}
    for label_k, words in [("8k", 6800), ("32k", 27500)]:
        p_text = make_unique_prompt(words, f"{label}-{label_k}-{nonce}")
        r = stream_chat([{"role": "user", "content": p_text}], max_tokens=16, temperature=0.0, seed=42)
        tf = r.get("tensorfold", {})
        ptoks = r.get("usage", {}).get("prompt_tokens") or 0
        psec = tf.get("prefill_seconds") or r["client_ttft_seconds"]
        ptps = round(ptoks / psec, 1) if psec else 0
        print(f"  [Prefill {label_k}] prompt_tokens={ptoks} | prefill_s={psec}s | prefill_tok_s={ptps} | log: {r.get('log_line')}")
        r["computed_prefill_tok_s"] = ptps
        prefill_res[label_k] = r
    results["cold_prefill"] = prefill_res

    print("[5/6] Running Multi-Turn Vision Prompt Cache Resume Test (>2K tokens + image)...")
    b64_png = make_test_png(512, 512)
    img_url = f"data:image/png;base64,{b64_png}"
    vision_pad = make_unique_prompt(2400, f"{label}-vision-2k-{nonce}")
    msg_turn1 = [
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": img_url}},
                {"type": "text", "text": vision_pad + "\n請結合上述背景與圖片，用兩句話描述圖片的色彩結構。"},
            ],
        }
    ]
    v_t1 = stream_chat(msg_turn1, max_tokens=64, temperature=0.0, seed=42)
    msg_turn2 = msg_turn1 + [
        {"role": "assistant", "content": v_t1["reply_preview"]},
        {"role": "user", "content": "延續上題，請問圖片中央格紋與左上角有何差異？簡短回答。"},
    ]
    v_t2 = stream_chat(msg_turn2, max_tokens=64, temperature=0.0, seed=42)
    print(f"  [Vision Turn 1] TTFT={v_t1['client_ttft_seconds']}s | log: {v_t1['log_line']}")
    print(f"  [Vision Turn 2 (Resume)] TTFT={v_t2['client_ttft_seconds']}s | log: {v_t2['log_line']}")
    results["vision_cache_resume_2k"] = {"turn1": v_t1, "turn2": v_t2}

    print("[6/6] Running Short-Prompt Cut-In Under 32K Cold Prefill Test...")
    long_prompt = make_unique_prompt(27500, f"{label}-cutin-long-{nonce}")
    def run_long():
        return stream_chat([{"role": "user", "content": long_prompt}], max_tokens=16, temperature=0.0, seed=42)
    def run_short():
        time.sleep(1.0)
        return stream_chat([{"role": "user", "content": f"請回答 123 + 456 等於多少？（測試標籤 {nonce}）"}], max_tokens=16, temperature=0.0, seed=42)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        f_long = ex.submit(run_long)
        f_short = ex.submit(run_short)
        r_long = f_long.result()
        r_short = f_short.result()
    print(f"  [Cut-In] Long 32K TTFT={r_long['client_ttft_seconds']}s | Short Prompt TTFT (sent +1.0s behind)={r_short['client_ttft_seconds']}s")
    results["cut_in_test"] = {"long_32k": r_long, "short_behind_1s": r_short}

    results["system_after"] = get_system_metrics()

    out_path = f"/home/joseyarashio/.hermes/cache/scratch/bench_step1/{label}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"=== Saved full benchmark to {out_path} ===")

if __name__ == "__main__":
    main()
