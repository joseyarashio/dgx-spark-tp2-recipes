#!/usr/bin/env python3
import base64
import concurrent.futures
import json
import os
import re
import struct
import subprocess
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
            # 4 quadrants with distinct colors + checkerboard in center
            if 192 <= x < 320 and 192 <= y < 320:
                c = 255 if ((x // 16 + y // 16) % 2 == 0) else 0
                raw_data.extend((c, c, c))
            elif x < width // 2 and y < height // 2:
                raw_data.extend((220, 30, 30))   # Top-Left: Red
            elif x >= width // 2 and y < height // 2:
                raw_data.extend((30, 200, 30))   # Top-Right: Green
            elif x < width // 2 and y >= height // 2:
                raw_data.extend((30, 60, 220))   # Bottom-Left: Blue
            else:
                raw_data.extend((230, 210, 30))  # Bottom-Right: Yellow

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
    max_tokens=384,
    temperature=0.0,
    seed=42,
    enable_thinking=False,
    tools=None,
    tool_choice=None,
    base_url=API_8888,
    timeout=300,
    extra_headers=None,
):
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

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status_code = resp.status
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
                if first_event_t is None:
                    first_event_t = time.perf_counter() - t0
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
                    ch0 = choices[0]
                    if ch0.get("finish_reason"):
                        finish_reason = ch0["finish_reason"]
                    delta = ch0.get("delta") or {}
                    rc = delta.get("reasoning_content") or ""
                    if rc:
                        reasoning_parts.append(rc)
                    c = delta.get("content") or ""
                    if c:
                        if first_content_t is None:
                            first_content_t = time.perf_counter() - t0
                        content_parts.append(c)
                    tcs = delta.get("tool_calls") or []
                    for tc in tcs:
                        idx = tc.get("index", 0)
                        if idx not in tool_calls_map:
                            tool_calls_map[idx] = {"name": "", "arguments": ""}
                        fn = tc.get("function") or {}
                        if fn.get("name"):
                            tool_calls_map[idx]["name"] += fn["name"]
                        if fn.get("arguments"):
                            tool_calls_map[idx]["arguments"] += fn["arguments"]
                        if first_content_t is None:
                            first_content_t = time.perf_counter() - t0
    except urllib.error.HTTPError as e:
        wall_t = time.perf_counter() - t0
        err_body = ""
        try:
            err_body = e.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        return {
            "status_code": e.code,
            "wall_seconds": round(wall_t, 4),
            "error_body": err_body,
        }
    except Exception as e:
        wall_t = time.perf_counter() - t0
        return {
            "status_code": 0,
            "wall_seconds": round(wall_t, 4),
            "error_body": str(e),
        }

    wall_t = time.perf_counter() - t0
    content_text = "".join(content_parts)
    reasoning_text = "".join(reasoning_parts)
    tool_calls_list = [tool_calls_map[k] for k in sorted(tool_calls_map.keys())]

    log_line = ""
    cached_tokens = 0
    prompt_tokens = 0
    if cmpl_id:
        try:
            out = subprocess.run(
                f"docker logs --tail 80 dsv41-rank0 2>&1 | grep '{cmpl_id}' | tail -n 1",
                shell=True, text=True, capture_output=True
            ).stdout.strip()
            log_line = out
            m_c = re.search(r"cached=([0-9]+)", log_line)
            if m_c:
                cached_tokens = int(m_c.group(1))
            m_p = re.search(r"prompt=([0-9]+)", log_line)
            if m_p:
                prompt_tokens = int(m_p.group(1))
        except Exception:
            pass

    return {
        "status_code": status_code,
        "id": cmpl_id,
        "wall_seconds": round(wall_t, 4),
        "client_ttft_seconds": round(first_content_t or first_event_t or wall_t, 4),
        "finish_reason": finish_reason,
        "tensorfold": tf_meta,
        "speculative": spec_meta,
        "usage": usage_meta,
        "cached_tokens": cached_tokens,
        "prompt_tokens": prompt_tokens,
        "log_line": log_line,
        "content": content_text,
        "reasoning_len": len(reasoning_text),
        "tool_calls": tool_calls_list,
    }

def get_system_metrics():
    def sh(cmd):
        return subprocess.run(cmd, shell=True, text=True, capture_output=True).stdout.strip()

    health = json.loads(sh(f"curl -s {API_8888}/health"))
    proxy = json.loads(sh(f"curl -s {API_8889}/proxy/status"))

    def parse_node(prefix=""):
        cmd = "free -m && echo '---BUDDY---' && cat /proc/buddyinfo && echo '---GPU---' && nvidia-smi --query-gpu=clocks.gr,temperature.gpu,power.draw --format=csv,noheader"
        out = sh(f"ssh -o BatchMode=yes {prefix} \"{cmd}\"") if prefix else sh(cmd)
        parts = out.split("---BUDDY---")
        free_out = parts[0]
        rest = parts[1].split("---GPU---") if len(parts) > 1 else ["", ""]
        buddy_out, gpu_out = rest[0], rest[1].strip() if len(rest) > 1 else ""
        mem_avail, swap_used = 0, 0
        for line in free_out.splitlines():
            sp = line.split()
            if line.startswith("Mem:"):
                mem_avail = int(sp[6])
            elif line.startswith("Swap:") or line.startswith("置換："):
                swap_used = int(sp[2])
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
            "gpu_telemetry": gpu_out,
        }

    return {
        "health": health,
        "proxy": proxy,
        "node1": parse_node(""),
        "node2": parse_node("joseyarashio@10.100.184.1"),
    }

def run_question_bank():
    print("\n=== PART A: 25-Item Question Bank (5 Domains) ===")
    bank_results = {"domains": {}, "summary": {}}

    # 1. Math & Reasoning (5 items)
    math_items = [
        ("math_1_mod", "Find the remainder when 7^2026 + 13^2026 is divided by 100. Be concise and put the final integer in \\boxed{N}.", lambda s: "98" in s),
        ("math_2_comb", "How many 5-digit positive integers (from 10000 to 99999) have digits that are strictly increasing from left to right (e.g. 13579)? Put the final integer in \\boxed{N}.", lambda s: "126" in s),
        ("math_3_prob", "Three fair 6-sided dice are rolled. What is the exact number of outcomes (out of 216) where the sum of the three dice is exactly 11? Put the final integer in \\boxed{N}.", lambda s: "27" in s),
        ("math_4_alg", "If x + 1/x = 5, compute the exact integer value of x^4 + 1/x^4. Put the final integer in \\boxed{N}.", lambda s: "527" in s),
        ("math_5_seq", "A sequence satisfies a_1 = 2 and a_{n+1} = 3*a_n - 1 for n >= 1. Compute the exact value of a_6. Put the final integer in \\boxed{N}.", lambda s: "365" in s),
    ]
    math_res = []
    for qid, prompt, checker in math_items:
        r = stream_chat([{"role": "user", "content": prompt}], max_tokens=1024, temperature=0.0, seed=42, enable_thinking=False)
        passed = bool(checker(r.get("content", "")))
        print(f"  [Math][{qid}] pass={passed} | {r['tensorfold'].get('tokens_per_second', 0):.1f} tok/s | ans={r.get('content', '')[-80:].strip()!r}")
        math_res.append({"id": qid, "passed": passed, "response": r})
    bank_results["domains"]["math"] = math_res

    # 2. MMLU-Pro Hard Knowledge (5 items, letter-only, thinking=False)
    mmlu_items = [
        (
            "mmlu_1_arch",
            "In an IEEE 754 binary64 (double-precision) floating-point number, what is the exact value of the exponent bias, and how many explicit fraction (mantissa) bits are stored?\nA) Bias 127, 23 bits\nB) Bias 1023, 52 bits\nC) Bias 1023, 53 bits\nD) Bias 1024, 52 bits\nE) Bias 16383, 64 bits\nReply with the single capital letter (A, B, C, D, or E) only.",
            "B",
        ),
        (
            "mmlu_2_algo",
            "What is the tightest asymptotic time complexity of finding all-pairs shortest paths in a dense directed graph with V vertices and no negative cycles using the Floyd-Warshall algorithm, and using Johnson's algorithm with Fibonacci heaps on a sparse graph with E = O(V) edges?\nA) O(V^3) and O(V^2 log V)\nB) O(V^2 log V) and O(V^3)\nC) O(V^3) and O(V^3)\nD) O(V^2) and O(V log V)\nE) O(V^3 log V) and O(V^2 log V)\nReply with the single capital letter (A, B, C, D, or E) only.",
            "A",
        ),
        (
            "mmlu_3_chem",
            "According to Molecular Orbital (MO) theory, what is the bond order of the peroxide ion (O2^{2-}) and its magnetic property?\nA) Bond order 2.0, paramagnetic\nB) Bond order 1.5, paramagnetic\nC) Bond order 1.0, diamagnetic\nD) Bond order 1.0, paramagnetic\nE) Bond order 2.5, paramagnetic\nReply with the single capital letter (A, B, C, D, or E) only.",
            "C",
        ),
        (
            "mmlu_4_phys",
            "A relativistic particle has total energy E equal to 3 times its rest energy (E = 3 m c^2). What is its speed v as a fraction of the speed of light c?\nA) (sqrt(8)/3) c\nB) (8/9) c\nC) (sqrt(3)/2) c\nD) (2/3) c\nE) (sqrt(5)/3) c\nReply with the single capital letter (A, B, C, D, or E) only.",
            "A",
        ),
        (
            "mmlu_5_net",
            "In RoCEv2 (RDMA over Converged Ethernet v2), which transport protocol and well-known destination port are used to encapsulate InfiniBand transport and network headers?\nA) TCP port 4420\nB) UDP port 4791\nC) UDP port 4789\nD) GRE protocol 47\nE) SCTP port 3260\nReply with the single capital letter (A, B, C, D, or E) only.",
            "B",
        ),
        (
            "mmlu_6_calc_circuit",
            "Three resistors of 6 ohms, 12 ohms, and 4 ohms are connected in parallel across a 24 V ideal DC voltage source. What is the total power dissipated by the circuit?\nA) 144 W\nB) 288 W\nC) 192 W\nD) 96 W\nE) 384 W\nReply with the single capital letter (A, B, C, D, or E) only, with no explanation.",
            "B",
        ),
        (
            "mmlu_7_calc_thermo",
            "An ideal monatomic gas (gamma = 5/3) undergoes an adiabatic expansion in which its volume increases by a factor of 8. By what factor does its absolute temperature T change?\nA) Decreases by a factor of 2\nB) Decreases by a factor of 4\nC) Decreases by a factor of 8\nD) Decreases by a factor of 16\nE) Decreases by a factor of 2.5\nReply with the single capital letter (A, B, C, D, or E) only, with no explanation.",
            "B",
        ),
        (
            "mmlu_8_calc_cache",
            "A 64 KiB 4-way set-associative cache has 64-byte cache lines and uses 48-bit physical addresses. How many bits are used for the tag, index, and byte offset respectively?\nA) Tag: 32, Index: 10, Offset: 6\nB) Tag: 34, Index: 8, Offset: 6\nC) Tag: 30, Index: 12, Offset: 6\nD) Tag: 33, Index: 9, Offset: 6\nE) Tag: 35, Index: 7, Offset: 6\nReply with the single capital letter (A, B, C, D, or E) only, with no explanation.",
            "B",
        ),
        (
            "mmlu_9_calc_prob",
            "A fair coin is tossed 6 times. What is the exact probability that the number of heads is strictly greater than the number of tails?\nA) 1/2\nB) 11/32\nC) 21/64\nD) 15/32\nE) 5/16\nReply with the single capital letter (A, B, C, D, or E) only, with no explanation.",
            "B",
        ),
        (
            "mmlu_10_calc_linalg",
            "Let A be a 3x3 matrix with eigenvalues 2, -1, and 4. What is the determinant of the matrix (A^2 + I), where I is the 3x3 identity matrix?\nA) 85\nB) 170\nC) 150\nD) 65\nE) 136\nReply with the single capital letter (A, B, C, D, or E) only, with no explanation.",
            "B",
        ),
    ]
    mmlu_res = []
    for qid, prompt, expected in mmlu_items:
        r = stream_chat([{"role": "user", "content": prompt}], max_tokens=32, temperature=0.0, seed=42, enable_thinking=False)
        txt = r.get("content", "").strip()
        m = re.search(r"\b([A-E])\b", txt)
        picked = m.group(1) if m else txt[:1]
        passed = (picked == expected)
        print(f"  [MMLU-Pro][{qid}] pass={passed} (picked={picked!r}, expected={expected!r}) | raw={txt!r}")
        mmlu_res.append({"id": qid, "passed": passed, "picked": picked, "expected": expected, "response": r})
    bank_results["domains"]["mmlu_pro"] = mmlu_res

    # 3. Code Generation + Unit Test Execution Gate (5 items)
    code_items = [
        (
            "code_1_dijkstra",
            "Write only valid Python code (no markdown explanation outside code) defining `def shortest_path(n: int, edges: list[tuple[int, int, int]], src: int, dst: int) -> int:` that returns the minimum weight path in a directed graph with `n` nodes (0 to n-1) and `(u, v, w)` non-negative edges, or `-1` if unreachable.",
            """
assert shortest_path(5, [(0,1,2),(0,2,8),(1,2,3),(1,3,10),(2,3,2),(3,4,1)], 0, 4) == 8
assert shortest_path(3, [(0,1,5)], 0, 2) == -1
assert shortest_path(1, [], 0, 0) == 0
""",
        ),
        (
            "code_2_merge_intervals",
            "Write only valid Python code defining `def merge_intervals(intervals: list[list[int]]) -> list[list[int]]:` that merges all overlapping or touching intervals and returns them sorted by start time.",
            """
assert merge_intervals([[1,3],[2,6],[8,10],[15,18]]) == [[1,6],[8,10],[15,18]]
assert merge_intervals([[1,4],[4,5]]) == [[1,5]]
assert merge_intervals([]) == []
""",
        ),
        (
            "code_3_edit_distance",
            "Write only valid Python code defining `def edit_distance(s1: str, s2: str) -> int:` that computes the Levenshtein distance between two strings.",
            """
assert edit_distance("kitten", "sitting") == 3
assert edit_distance("flaw", "lawn") == 2
assert edit_distance("", "abc") == 3
assert edit_distance("same", "same") == 0
""",
        ),
        (
            "code_4_eval_rpn",
            "Write only valid Python code defining `def eval_rpn(tokens: list[str]) -> int:` that evaluates an arithmetic expression in Reverse Polish Notation with `+`, `-`, `*`, `/` where division truncates toward zero (like `int(a / b)`).",
            """
assert eval_rpn(["2","1","+","3","*"]) == 9
assert eval_rpn(["4","13","5","/","+"]) == 6
assert eval_rpn(["10","6","9","3","+","-11","*","/","*","17","+","5","+"]) == 22
""",
        ),
        (
            "code_5_lis",
            "Write only valid Python code defining `def length_of_lis(nums: list[int]) -> int:` that returns the length of the longest strictly increasing subsequence in O(N log N) time.",
            """
assert length_of_lis([10,9,2,5,3,7,101,18]) == 4
assert length_of_lis([0,1,0,3,2,3]) == 4
assert length_of_lis([7,7,7,7,7]) == 1
assert length_of_lis([]) == 0
""",
        ),
    ]
    code_res = []
    for qid, prompt, test_code in code_items:
        r = stream_chat([{"role": "user", "content": prompt}], max_tokens=512, temperature=0.0, seed=42, enable_thinking=False)
        raw = r.get("content", "")
        m = re.search(r"```(?:python)?\s*(.*?)```", raw, re.DOTALL)
        extracted = m.group(1) if m else raw
        passed = False
        err_msg = ""
        try:
            ns = {}
            exec(extracted + "\n" + test_code, ns, ns)
            passed = True
        except Exception as e:
            err_msg = f"{type(e).__name__}: {e}"
        print(f"  [Code][{qid}] pass={passed} | {r['tensorfold'].get('tokens_per_second', 0):.1f} tok/s | err={err_msg!r}")
        code_res.append({"id": qid, "passed": passed, "error": err_msg, "response": r})
    bank_results["domains"]["code"] = code_res

    # 4. IFEval Strict Instruction Following (5 items)
    ifeval_items = [
        (
            "ifeval_1_json_no_fence",
            'Return a raw JSON object (do NOT wrap in markdown ``` fences) with keys "cluster", "nodes" (array of exactly 2 integers: 148 and 149), and "roce_gbps" (integer 185). Output nothing else.',
            lambda s: (not s.strip().startswith("```")) and json.loads(s.strip()) == {"cluster": json.loads(s.strip()).get("cluster"), "nodes": [148, 149], "roce_gbps": 185},
        ),
        (
            "ifeval_2_exact_bullets",
            "Write exactly 4 bullet points (each line starting with `- `) explaining benefits of RDMA. Do NOT include any introduction or conclusion lines.",
            lambda s: len([ln for ln in s.strip().splitlines() if ln.strip()]) == 4 and all(ln.strip().startswith("- ") for ln in s.strip().splitlines() if ln.strip()),
        ),
        (
            "ifeval_3_forbidden_letter",
            "Write a coherent English sentence of at least 8 words about computers without using the letter 'e' or 'E' anywhere.",
            lambda s: len(s.strip().split()) >= 8 and ("e" not in s.lower()),
        ),
        (
            "ifeval_4_csv_strict",
            "Output a strict 4-line CSV (1 header line + 3 data lines, no markdown fences, no extra text). Header must be exactly `rank,ip,role`.",
            lambda s: (not s.strip().startswith("```")) and len(s.strip().splitlines()) == 4 and s.strip().splitlines()[0].strip() == "rank,ip,role" and all(ln.count(",") == 2 for ln in s.strip().splitlines()),
        ),
        (
            "ifeval_5_end_phrase",
            "In two sentences, explain what KV cache quantization does. Your response must end with the exact phrase: `[END OF REPORT]`.",
            lambda s: s.strip().endswith("[END OF REPORT]"),
        ),
    ]
    ifeval_res = []
    for qid, prompt, checker in ifeval_items:
        r = stream_chat([{"role": "user", "content": prompt}], max_tokens=256, temperature=0.0, seed=42, enable_thinking=False)
        txt = r.get("content", "")
        passed = False
        try:
            passed = bool(checker(txt))
        except Exception:
            passed = False
        print(f"  [IFEval][{qid}] pass={passed} | preview={txt[:80].strip()!r}")
        ifeval_res.append({"id": qid, "passed": passed, "response": r})
    bank_results["domains"]["ifeval"] = ifeval_res

    # 5. Agentic Tool Calling & Multi-Turn Vision (5 items)
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

    agent_res = []
    # 5.1 Tool call 1
    r_tc1 = stream_chat(
        [{"role": "user", "content": "Please configure the GPU clock governor on node 192.168.10.148 with min clock 1800 MHz, max clock 2500 MHz, and high thermal threshold 84 C."}],
        max_tokens=256, temperature=0.0, seed=42, enable_thinking=False, tools=tools_schema
    )
    tc1_ok = False
    try:
        tcs = r_tc1.get("tool_calls") or []
        if tcs and tcs[0]["name"] == "set_gpu_clock_governor":
            args = json.loads(tcs[0]["arguments"])
            tc1_ok = (args.get("node_ip") == "192.168.10.148" and args.get("min_clk_mhz") == 1800 and args.get("max_clk_mhz") == 2500 and args.get("zone_hi_c") == 84)
    except Exception:
        pass
    print(f"  [Agent/Vision][tool_1_governor] pass={tc1_ok} | tool_calls={r_tc1.get('tool_calls')}")
    agent_res.append({"id": "tool_1_governor", "passed": tc1_ok, "response": r_tc1})

    # 5.2 Tool call 2
    r_tc2 = stream_chat(
        [{"role": "user", "content": "Check the RoCEv2 RDMA counters on interface rocep1s0f0 with GID index 3."}],
        max_tokens=256, temperature=0.0, seed=42, enable_thinking=False, tools=tools_schema
    )
    tc2_ok = False
    try:
        tcs = r_tc2.get("tool_calls") or []
        if tcs and tcs[0]["name"] == "query_roce_counters":
            args = json.loads(tcs[0]["arguments"])
            tc2_ok = (args.get("interface") == "rocep1s0f0" and int(args.get("gid_index")) == 3)
    except Exception:
        pass
    print(f"  [Agent/Vision][tool_2_roce] pass={tc2_ok} | tool_calls={r_tc2.get('tool_calls')}")
    agent_res.append({"id": "tool_2_roce", "passed": tc2_ok, "response": r_tc2})

    # 5.3 Tool call 3 (multi-turn after tool result)
    msg_tc3 = [
        {"role": "user", "content": "Check the RoCEv2 RDMA counters on interface rocep1s0f0 with GID index 3."},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "query_roce_counters", "arguments": '{"interface": "rocep1s0f0", "gid_index": 3}'}}]},
        {"role": "tool", "tool_call_id": "call_1", "content": '{"rx_bytes": 9876543210, "tx_bytes": 9876543210, "cnp_packets": 0, "link_speed_gbps": 185}'},
    ]
    r_tc3 = stream_chat(msg_tc3, max_tokens=128, temperature=0.0, seed=42, enable_thinking=False, tools=tools_schema)
    tc3_ok = ("185" in r_tc3.get("content", "") and "0" in r_tc3.get("content", ""))
    print(f"  [Agent/Vision][tool_3_followup] pass={tc3_ok} | ans={r_tc3.get('content', '')[:80].strip()!r}")
    agent_res.append({"id": "tool_3_followup", "passed": tc3_ok, "response": r_tc3})

    # 5.4 & 5.5 Vision Quadrant Recognition + >2K Vision Prompt Cache Resume
    b64_png = make_test_png(512, 512)
    img_url = f"data:image/png;base64,{b64_png}"
    nonce = str(int(time.time()))
    pad_words = " ".join([f"context_token_{i}_{nonce}" for i in range(1200)])
    msg_v1 = [
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": img_url}},
                {"type": "text", "text": f"[Background log: {pad_words}]\nWhat are the colors of the four outer quadrants (Top-Left, Top-Right, Bottom-Left, Bottom-Right) in this image?"},
            ],
        }
    ]
    r_v1 = stream_chat(msg_v1, max_tokens=128, temperature=0.0, seed=42, enable_thinking=False)
    v1_txt = r_v1.get("content", "").lower()
    v1_ok = all(c in v1_txt for c in ["red", "green", "blue", "yellow"])
    print(f"  [Agent/Vision][vision_4_quadrants] pass={v1_ok} | TTFT={r_v1['client_ttft_seconds']}s | log={r_v1.get('log_line')}")
    agent_res.append({"id": "vision_4_quadrants", "passed": v1_ok, "response": r_v1})

    msg_v2 = msg_v1 + [
        {"role": "assistant", "content": r_v1.get("content", "")},
        {"role": "user", "content": "What pattern is located in the very center of the image, and what two colors does it use?"},
    ]
    r_v2 = stream_chat(msg_v2, max_tokens=96, temperature=0.0, seed=42, enable_thinking=False)
    v2_txt = r_v2.get("content", "").lower()
    m_cache = re.search(r"cached=([1-9]\d*)", r_v2.get("log_line", ""))
    v2_cached = bool(m_cache)
    v2_ok = v2_cached and any(w in v2_txt for w in ["checker", "grid", "black", "white"])
    print(f"  [Agent/Vision][vision_5_cache_resume] pass={v2_ok} (cached_hit={v2_cached}) | TTFT={r_v2['client_ttft_seconds']}s | log={r_v2.get('log_line')}")
    agent_res.append({"id": "vision_5_cache_resume", "passed": v2_ok, "cached_hit": v2_cached, "response": r_v2})

    bank_results["domains"]["agent_vision"] = agent_res

    total_passed = 0
    total_count = 0
    for dom, items in bank_results["domains"].items():
        p = sum(1 for x in items if x["passed"])
        c = len(items)
        bank_results["summary"][dom] = {"passed": p, "total": c, "score_pct": round(100.0 * p / c, 1)}
        total_passed += p
        total_count += c
    bank_results["summary"]["overall"] = {"passed": total_passed, "total": total_count, "score_pct": round(100.0 * total_passed / total_count, 1)}
    print(f"  ==> Question Bank Overall: {total_passed}/{total_count} ({bank_results['summary']['overall']['score_pct']}%)")
    return bank_results

def make_unique_prompt(target_words, tag):
    base_words = [
        "architecture", "pipeline", "tensor", "bandwidth", "latency", "scheduler",
        "quantization", "trellis", "codebook", "allreduce", "infiniband", "packet",
        "register", "shared", "memory", "coalesced", "warp", "occupancy", "prefetch",
        "asynchronous", "descriptor", "barrier", "ring", "topology", "throughput",
    ]
    chunks = [f"[Session-{tag}-Block-{i}: " + " ".join(base_words[(i + j) % len(base_words)] for j in range(20)) + ".]" for i in range(target_words // 24)]
    return "\n".join(chunks) + "\n\n請用一句話總結上述技術詞彙所屬的領域（只需回答一句話）。"

def run_perf_and_stress(label):
    print("\n=== PART B: Single-Stream Decode, Cold Prefill & Cut-In ===")
    perf = {}
    prompts = {
        "code": "Write a complete, well-commented Python implementation of an LRU Cache using a doubly linked list and hash map, including thread-safety locks, type annotations, and a thorough unit test suite.",
        "prose": "請詳細分析分散式大語言模型推論在雙節點 RoCEv2 網路架構下的通訊瓶頸、All-Reduce 延遲特性、Speculative Decoding 草稿驗證機制，以及 Unified Memory 架構下的記憶體管理策略。",
        "structured": "Output a strict JSON array of 12 fictional cloud GPU cluster nodes. Each object must contain: node_id (string), rack (string), ip_address (string), gpu_model (string), vram_gb (integer), interconnect_gbps (integer), active_streams (integer), thermal_c (float), and status (enum: healthy, degraded, maintenance). Output JSON only.",
    }
    single_decode = {}
    for temp_label, temp_val in [("temp_0.30", 0.30), ("temp_0.0", 0.0)]:
        single_decode[temp_label] = {}
        for name, p in prompts.items():
            r = stream_chat([{"role": "user", "content": p}], max_tokens=384, temperature=temp_val, seed=42)
            tf = r.get("tensorfold", {})
            sp = r.get("speculative", {})
            print(f"  [{temp_label}][{name}] {tf.get('tokens_per_second', 0):.2f} tok/s | accept: {sp.get('acceptance_rate', 0):.3f} | tpr: {sp.get('tokens_per_round', 0):.2f}")
            single_decode[temp_label][name] = r
    perf["single_decode"] = single_decode

    nonce = str(int(time.time()))
    prefill_res = {}
    for label_k, words in [("8k", 6800), ("32k", 27500)]:
        p_text = make_unique_prompt(words, f"{label}-{label_k}-{nonce}")
        r = stream_chat([{"role": "user", "content": p_text}], max_tokens=16, temperature=0.0, seed=42)
        tf = r.get("tensorfold", {})
        ptoks = r.get("usage", {}).get("prompt_tokens") or 0
        psec = tf.get("prefill_seconds") or r["client_ttft_seconds"]
        ptps = round(ptoks / psec, 1) if psec else 0
        print(f"  [Cold Prefill {label_k}] tokens={ptoks} | prefill_s={psec:.2f}s | tok/s={ptps}")
        r["computed_prefill_tok_s"] = ptps
        prefill_res[label_k] = r
    perf["cold_prefill"] = prefill_res

    # Short prompt cut-in under 32K prefill
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
    print(f"  [Cut-In] Long 32K TTFT={r_long['client_ttft_seconds']}s | Short Prompt TTFT (+1.0s behind)={r_short['client_ttft_seconds']}s")
    perf["cut_in_test"] = {"long_32k": r_long, "short_behind_1s": r_short}

    print("\n=== PART C: Concurrency Scaling (C1 / C2 / C4 / C6) & Port 8889 Tiered 429 Stress Test ===")
    c_prompts = [
        ("s1_code", prompts["code"]),
        ("s2_prose", prompts["prose"]),
        ("s3_structured", prompts["structured"]),
        ("s4_algo", "Implement a complete Red-Black Tree in Python with insert, search, left_rotate, right_rotate, and inorder traversal methods. Include docstrings and complexity analysis."),
        ("s5_db", "Write an asynchronous connection pool manager in Python for SQLite with WAL mode, background checkpointing, and connection leak detection."),
        ("s6_raft", "Write a complete Raft consensus leader election implementation in Python with randomized election timers and RPC heartbeat message handlers.")
    ]
    scaling = {}
    for c_level in [1, 2, 4, 6]:
        subset = c_prompts[:c_level]
        t0 = time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(max_workers=c_level) as ex:
            futs = {
                ex.submit(stream_chat, [{"role": "user", "content": p}], 384, 0.30, 200 + idx, False, None, None, API_8889): name
                for idx, (name, p) in enumerate(subset)
            }
            res_map = {futs[f]: f.result() for f in concurrent.futures.as_completed(futs)}
        wall = time.perf_counter() - t0
        tot_tok = sum((r.get("usage", {}).get("completion_tokens") or 384) for r in res_map.values())
        agg_tps = round(tot_tok / wall, 2)
        mean_stream_tps = round(sum((r.get("tensorfold", {}).get("tokens_per_second") or 0) for r in res_map.values()) / c_level, 2)
        print(f"  [Concurrency C{c_level} via :8889] Wall={wall:.2f}s | Aggregate={agg_tps} tok/s | Per-stream mean={mean_stream_tps} tok/s")
        scaling[f"C{c_level}"] = {
            "wall_seconds": round(wall, 4),
            "total_tokens": tot_tok,
            "aggregate_wall_tok_s": agg_tps,
            "per_stream_mean_tok_s": mean_stream_tps,
            "streams": res_map,
        }
    perf["concurrency_scaling"] = scaling

    # Burst C14 Stress Test against Port 8889 Fast-Fail Tiered Queue (6 active + 8 queued + 2 immediate 429)
    print("  [Stress Test C14 Burst via :8889] Sending 16 concurrent requests (6 active + 8 queued + 2 immediate 429)...")
    def burst_worker(idx):
        if idx >= 6:
            time.sleep(0.10 + (idx - 6) * 0.02)
        return stream_chat(
            [{"role": "user", "content": f"Worker {idx}: Write a detailed Python class implementing a thread-safe priority queue with heap operations."}],
            max_tokens=384 if idx < 6 else 64,
            temperature=0.30,
            seed=300 + idx,
            base_url=API_8889,
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as ex:
        futs = {ex.submit(burst_worker, i): i for i in range(16)}
        burst_results = {}
        for f in concurrent.futures.as_completed(futs):
            i = futs[f]
            burst_results[f"worker_{i}"] = f.result()

    status_counts = {}
    immediate_429 = []
    tiered_429 = []
    completed_200 = []
    for k, r in sorted(burst_results.items()):
        sc = r.get("status_code")
        status_counts[sc] = status_counts.get(sc, 0) + 1
        if sc == 200:
            completed_200.append((k, r["wall_seconds"]))
        elif sc == 429:
            eb = r.get("error_body", "")
            if "queue_full" in eb:
                immediate_429.append((k, r["wall_seconds"], eb))
            else:
                tiered_429.append((k, r["wall_seconds"], eb))

    print(f"    -> Status counts: {status_counts}")
    print(f"    -> Immediate 429 (queue_full, >8th req): {[(x[0], x[1]) for x in immediate_429]}")
    print(f"    -> Tiered timeout 429 (escaped standby queue): {[(x[0], x[1]) for x in tiered_429]}")
    print(f"    -> Completed 200 OK: {completed_200}")
    perf["stress_burst_c10_port8889"] = {
        "status_counts": status_counts,
        "immediate_429_count": len(immediate_429),
        "tiered_429_count": len(tiered_429),
        "completed_200_count": len(completed_200),
        "workers": burst_results,
    }

    # Heavy Stall C8 Test to verify Tiered Standby Queue Dropout (pos 4 escapes at 5s)
    print("  [Stress Test C8 Heavy Stall via :8889] 4 long active requests (900 tokens) + 4 standby queue waiters (testing tiered timeout dropout)...")
    def stall_worker(idx):
        if idx >= 4:
            time.sleep(0.20 + (idx - 4) * 0.05)
        return stream_chat(
            [{"role": "user", "content": f"Stall Worker {idx}: Write a very long, comprehensive 1500-word textbook chapter on Linux kernel memory management, slab allocators, page tables, and NUMA balancing with full code examples."}],
            max_tokens=900 if idx < 4 else 64,
            temperature=0.30,
            seed=400 + idx,
            base_url=API_8889,
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(stall_worker, i): i for i in range(8)}
        stall_results = {f"worker_{futs[f]}": f.result() for f in concurrent.futures.as_completed(futs)}

    stall_status = {}
    stall_tiered_429 = []
    for k, r in sorted(stall_results.items()):
        sc = r.get("status_code")
        stall_status[sc] = stall_status.get(sc, 0) + 1
        if sc == 429:
            stall_tiered_429.append((k, r["wall_seconds"], r.get("error_body", "")))
    print(f"    -> Heavy Stall Status counts: {stall_status}")
    print(f"    -> Tiered timeout 429 dropouts: {[(x[0], x[1]) for x in stall_tiered_429]}")
    perf["stress_heavy_stall_c8_port8889"] = {
        "status_counts": stall_status,
        "tiered_429_dropouts": stall_tiered_429,
        "workers": stall_results,
    }
    return perf

def generate_synthetic_codebase(target_tokens=32000):
    """Generates a structured, realistic multi-module Python codebase for cache testing."""
    base_module = '''
# Module: core/distributed_coordinator.py
import asyncio, time, logging, struct, uuid
from typing import Dict, List, Optional, Tuple, Any

logger = logging.getLogger("coordinator")

class DistributedNode:
    def __init__(self, node_id: str, address: str, port: int, roce_gid: int = 3):
        self.node_id = node_id
        self.address = address
        self.port = port
        self.roce_gid = roce_gid
        self.active_channels: Dict[str, Any] = {}
        self.heartbeat_ts = time.time()
        self.lock = asyncio.Lock()

    async def register_channel(self, channel_id: str, buffer_size: int) -> bool:
        async with self.lock:
            if channel_id in self.active_channels:
                return False
            self.active_channels[channel_id] = {
                "created": time.time(),
                "buffer_size": buffer_size,
                "in_flight": 0
            }
            logger.info(f"Channel {channel_id} registered on {self.node_id}:{self.port}")
            return True

    async def poll_roce_counters(self) -> Dict[str, int]:
        return {
            "rx_packets": 1048576,
            "tx_packets": 1048576,
            "rx_bytes": 1073741824,
            "tx_bytes": 1073741824,
            "pfc_rx_pause": 0,
            "pfc_tx_pause": 0,
            "cnp_rx": 0,
            "cnp_tx": 0,
        }
'''
    needed_chars = int(target_tokens * 3.5)
    repeats = (needed_chars // len(base_module)) + 1
    full_text = ("# Distributed Systems Core Architecture Implementation\n" +
                 "# High-Performance RoCEv2 Clustered Runtime Source\n\n")
    for i in range(repeats):
        full_text += f"# Section {i+1}: Clustered Channel Definition\n"
        full_text += base_module.replace("coordinator", f"coordinator_sub_{i}")
    return full_text[:needed_chars]

def run_concurrency_cache_benchmark(label: str = "baseline"):
    """
    PART D: Multi-Agent Concurrency & Advanced Cache-Hit Benchmark (Strata Evaluation Suite)
    Specifically measures:
      D1. 4-Subagent Simultaneous Project Review (Burst Delay-Hit Scenario)
      D2. Staggered In-Flight Arrival (Prefill Pipeline Overlap)
      D3. 6-Turn Deep Autonomous Agent Tool Loop (Cache Growth & Retention)
      D4. Mixed Workload Priority Slicing (2 Background Scans + 2 Foreground Interactive)
    """
    print("\n============================================================")
    print(" PART D: Multi-Agent Concurrency & Advanced Cache-Hit Benchmark")
    print("============================================================")
    d_results: dict[str, object] = {}

    codebase_32k = generate_synthetic_codebase(target_tokens=30000)
    print(f"Generated synthetic shared codebase: {len(codebase_32k)} chars (~{len(codebase_32k)//3.5:.0f} tokens)\n")

    # --- D1: 4-Subagent Simultaneous Project Review ---
    print("  [D1: 4-Subagent Simultaneous Project Review (Burst Delay-Hit Scenario)]")
    tasks = [
        ("worker_0", "Audit the architecture, locking safety, and channel registration for race conditions.", 0),
        ("worker_1", "Identify deadlock, memory leak, and unhandled exception risks in this distributed coordinator.", 1),
        ("worker_2", "Write a complete pytest test suite covering active channels, concurrency locks, and counter polling.", 2),
        ("worker_3", "Review error handling, logging coverage, and graceful shutdown procedures under network partition.", 3)
    ]

    def subagent_task(name, instruction, seed_offset):
        messages = [
            {"role": "system", "content": "You are an elite principal software engineer conducting an exhaustive codebase review."},
            {"role": "user", "content": f"Here is the project codebase repository:\n```python\n{codebase_32k}\n```\n\nTask: {instruction}"}
        ]
        return stream_chat(
            messages,
            max_tokens=256,
            temperature=0.20,
            seed=500 + seed_offset,
            base_url=API_8889,
            timeout=300
        )

    t0_burst = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(subagent_task, t[0], t[1], t[2]): t[0] for t in tasks}
        d1_workers = {}
        for f in concurrent.futures.as_completed(futs):
            w_name = futs[f]
            d1_workers[w_name] = f.result()
    wall_burst = time.perf_counter() - t0_burst

    leader_ttft = d1_workers["worker_0"].get("client_ttft_seconds", d1_workers["worker_0"]["wall_seconds"])
    follower_ttfts = [d1_workers[f"worker_{i}"].get("client_ttft_seconds", d1_workers[f"worker_{i}"]["wall_seconds"]) for i in range(1, 4)]
    mean_follower_ttft = sum(follower_ttfts) / len(follower_ttfts)
    total_output_tokens = sum(w.get("usage", {}).get("completion_tokens", 0) for w in d1_workers.values())
    agg_throughput = total_output_tokens / wall_burst if wall_burst > 0 else 0.0

    print(f"    -> Wall-clock total: {wall_burst:.2f}s | Aggregate throughput: {agg_throughput:.2f} tok/s")
    print(f"    -> Leader (Worker 0) TTFT: {leader_ttft:.2f}s | Follower Mean TTFT: {mean_follower_ttft:.2f}s")
    print(f"    -> Delay-Hit Penalty Gap: {mean_follower_ttft - leader_ttft:+.2f}s")
    for i in range(4):
        w = d1_workers[f"worker_{i}"]
        ttft = w.get("client_ttft_seconds", w["wall_seconds"])
        out_t = w.get("usage", {}).get("completion_tokens", 0)
        c_tok = w.get("cached_tokens", 0) or w.get("usage", {}).get("cached_tokens", 0) or w.get("tensorfold", {}).get("cached", 0)
        print(f"       worker_{i}: TTFT={ttft:.2f}s, wall={w['wall_seconds']:.2f}s, out_tok={out_t}, cached={c_tok}")

    d_results["d1_burst_delay_hit"] = {
        "wall_total_s": wall_burst,
        "aggregate_tok_per_s": agg_throughput,
        "leader_ttft_s": leader_ttft,
        "mean_follower_ttft_s": mean_follower_ttft,
        "delay_hit_penalty_s": mean_follower_ttft - leader_ttft,
        "workers": d1_workers
    }

    # --- D2: Staggered In-Flight Arrival ---
    print("\n  [D2: Staggered In-Flight Arrival (Prefill Pipeline Overlap)]")
    stagger_offsets = [0.0, 3.0, 6.0, 10.0]
    def staggered_task(idx, delay_s):
        if delay_s > 0:
            time.sleep(delay_s)
        messages = [
            {"role": "system", "content": "You are a code reviewer."},
            {"role": "user", "content": f"Repository codebase:\n```python\n{codebase_32k}\n```\n\nSummarize channel registration safety in 3 bullet points (Query {idx})."}
        ]
        res = stream_chat(
            messages,
            max_tokens=128,
            temperature=0.20,
            seed=600 + idx,
            base_url=API_8889,
            timeout=300
        )
        res["stagger_delay_s"] = delay_s
        return res

    t0_stagger = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(staggered_task, i, stagger_offsets[i]): f"worker_{i}" for i in range(4)}
        d2_workers = {}
        for f in concurrent.futures.as_completed(futs):
            w_name = futs[f]
            d2_workers[w_name] = f.result()
    wall_stagger = time.perf_counter() - t0_stagger

    print(f"    -> Staggered batch wall-clock: {wall_stagger:.2f}s")
    for i in range(4):
        w = d2_workers[f"worker_{i}"]
        ttft = w.get("client_ttft_seconds", w["wall_seconds"])
        c_tok = w.get("cached_tokens", 0) or w.get("usage", {}).get("cached_tokens", 0) or w.get("tensorfold", {}).get("cached", 0)
        print(f"       worker_{i} (offset +{w['stagger_delay_s']:.0f}s): TTFT={ttft:.2f}s, wall={w['wall_seconds']:.2f}s, cached={c_tok}")

    d_results["d2_staggered_inflight"] = {
        "wall_total_s": wall_stagger,
        "workers": d2_workers
    }

    # --- D3: 6-Turn Deep Autonomous Agent Tool Loop ---
    print("\n  [D3: 6-Turn Deep Autonomous Agent Tool Loop (Cache Growth & Retention)]")
    conversation = [
        {"role": "system", "content": "You are an autonomous coding agent executing a multi-step investigation."}
    ]
    turn_steps = [
        ("Initial architecture scan: inspect DistributedNode init.", 1500),
        ("Inspect active channel registration and locks.", 2000),
        ("Analyze RoCE counter polling and packet metrics.", 2500),
        ("Simulate high-concurrency race condition test.", 3000),
        ("Analyze failure recovery during network partition.", 3500),
        ("Compile comprehensive final report with recommendations.", 4000)
    ]
    d3_turns = []
    for t_idx, (step_prompt, extra_chars) in enumerate(turn_steps, 1):
        extra_content = f"\n\n[Tool Observation {t_idx}]:\n" + ("x" * extra_chars)
        conversation.append({"role": "user", "content": step_prompt + extra_content})
        res = stream_chat(
            conversation,
            max_tokens=96,
            temperature=0.20,
            seed=700 + t_idx,
            base_url=API_8889,
            timeout=300
        )
        assistant_reply = res.get("content", "Analysis complete.")
        conversation.append({"role": "assistant", "content": assistant_reply})
        p_toks = res.get("prompt_tokens", 0) or res.get("usage", {}).get("prompt_tokens", 0) or res.get("tensorfold", {}).get("prompt", 0)
        c_toks = res.get("cached_tokens", 0) or res.get("usage", {}).get("cached_tokens", 0) or res.get("tensorfold", {}).get("cached", 0)
        ttft = res.get("client_ttft_seconds", res["wall_seconds"])
        out_toks = res.get("usage", {}).get("completion_tokens", 0)
        gen_time = max(0.001, res["wall_seconds"] - ttft)
        tok_per_s = out_toks / gen_time if out_toks > 0 else 0.0
        cache_ratio = (c_toks / p_toks * 100) if p_toks > 0 else 0.0
        print(f"    -> Turn {t_idx}: prompt_tok={p_toks}, cached_tok={c_toks} ({cache_ratio:.1f}%), TTFT={ttft:.3f}s, out_speed={tok_per_s:.1f} tok/s")
        d3_turns.append({
            "turn": t_idx,
            "prompt_tokens": p_toks,
            "cached_tokens": c_toks,
            "cache_hit_pct": cache_ratio,
            "ttft_seconds": ttft,
            "tokens_per_second": tok_per_s,
            "wall_seconds": res.get("wall_seconds", 0)
        })

    d_results["d3_agent_loop_6turns"] = d3_turns

    # --- D4: Mixed Workload Priority Slicing ---
    print("\n  [D4: Mixed Workload Priority Slicing (2 Background + 2 Foreground Interactive)]")
    def mixed_worker(name, prio_str, delay_s):
        if delay_s > 0:
            time.sleep(delay_s)
        headers = {"X-Priority": prio_str}
        if prio_str == "low":
            messages = [
                {"role": "user", "content": f"Background Scan {name}: Full repository scan.\n```python\n{codebase_32k}\n```"}
            ]
            m_toks = 128
        else:
            messages = [
                {"role": "user", "content": f"Interactive User {name}: What is the primary port used for distributed coordinator?"}
            ]
            m_toks = 64
        res = stream_chat(
            messages,
            max_tokens=m_toks,
            temperature=0.20,
            base_url=API_8889,
            timeout=300,
            extra_headers=headers
        )
        res["priority"] = prio_str
        res["delay_s"] = delay_s
        return res

    mixed_specs = [
        ("bg_worker_1", "low", 0.0),
        ("bg_worker_2", "low", 0.2),
        ("fg_user_1", "high", 1.5),
        ("fg_user_2", "high", 2.5)
    ]
    t0_mixed = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(mixed_worker, s[0], s[1], s[2]): s[0] for s in mixed_specs}
        d4_workers = {}
        for f in concurrent.futures.as_completed(futs):
            w_name = futs[f]
            d4_workers[w_name] = f.result()
    wall_mixed = time.perf_counter() - t0_mixed

    print(f"    -> Mixed workload total wall: {wall_mixed:.2f}s")
    for s in mixed_specs:
        w = d4_workers[s[0]]
        ttft = w.get("client_ttft_seconds", w["wall_seconds"])
        print(f"       {s[0]} ({w['priority']}, delay={w['delay_s']}s): TTFT={ttft:.2f}s, wall={w['wall_seconds']:.2f}s, sc={w.get('status_code')}")

    d_results["d4_mixed_priority"] = {
        "wall_total_s": wall_mixed,
        "workers": d4_workers
    }
    return d_results

def main():
    label = sys.argv[1] if len(sys.argv) > 1 else "step1_libertai_2.9bpw"
    out_dir = "/home/joseyarashio/dgx-spark-tp2-recipes/benchmarks/results"
    os.makedirs(out_dir, exist_ok=True)

    print(f"============================================================")
    print(f" Running Full Question Bank + Stress Test: {label}")
    print(f"============================================================")

    res: dict[str, object] = {"label": label, "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")}
    res["system_before"] = get_system_metrics()
    res["question_bank"] = run_question_bank()
    res["perf_and_stress"] = run_perf_and_stress(label)
    res["concurrency_and_cache"] = run_concurrency_cache_benchmark(label)
    res["system_after"] = get_system_metrics()

    out_path = os.path.join(out_dir, f"full_eval_{label}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    print(f"\n=== Saved full evaluation to {out_path} ===")

if __name__ == "__main__":
    main()
