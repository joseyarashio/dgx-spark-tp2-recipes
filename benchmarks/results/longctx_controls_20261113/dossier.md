# DGX Spark TP=2 Audit Dossier: Phase 1: Long-Context Tool-Open Controls

## 1. Environment & Engine Configuration
- Result dir: `results/longctx_controls_20261113`
- Runner script: `/home/joseyarashio/dgx-spark-tp2-recipes/benchmarks/run_longctx_controls.py`
- `rank0.sh`:
```bash
#!/bin/bash
set -euo pipefail
export TF_SEED_RANDOM=1
export TF_TOP_K_MAX=56
export TF_DS_PROMPT_ALIAS=1
export TF_FILL_CHUNKS=2
export TF_FILL_FIRST=2
export TF_FILL_CUT_IN=8192
export TF_DS_STREAMS=8
export TF_DS_WINDOW=2097152
export TF_LEARN_TTL_S=0  # no time expiry; the 200 GB (--learn-gib 186.26) LRU cap is the only eviction
DROP_REASONING_FLAG=""
if [ "${DROP_REASONING_HISTORY:-1}" = "1" ]; then
    DROP_REASONING_FLAG="--drop-reasoning-history --keep-last-n-reasoning 2"
fi
exec /home/joseyarashio/TensorFold-dsv41-zig/out/native/bin/tensorfold-native serve \
  /home/joseyarashio/models/DeepSeek-V4.1-Flash-1017-EXL3-2.9bpw \
  --host 0.0.0.0 --port 8888 --name DeepSeek-V4.1-Flash-1017-TF \
  --alias DeepSeek-V4.1-Flash-TF \
  --alias current \
  --context 1048576 --parallel 8 --thinking --max-tokens 32768 --loop-guard \
  $DROP_REASONING_FLAG \
  --prompt-cache-gib 2.5 \
  --learn --learn-dir /home/joseyarashio/.cache/dsv41-nvme-imprint --learn-gib 186.26 \
  --temperature 0.30 --top-p 0.95 --top-k 20 --backend cuda

```

## 2. Per-Arm Summary (`results.jsonl`, total rows=216)
```json
[
  {
    "arm": "A2_base",
    "ok": 36,
    "total": 36,
    "errors": {},
    "finish_counts": {
      "tool_calls": 36
    },
    "empty_content_no_tc": 0,
    "tool_call_reqs": 36,
    "undeclared_tc_reqs": 0,
    "dsml_in_content_reqs": 0,
    "loop_r": 0,
    "loop_r_periods": [],
    "loop_c": 0,
    "loop_c_periods": [],
    "engine_loop_fired": 0,
    "ge4k": 0,
    "ge8k": 0,
    "ge16k": 0,
    "prompt_tokens_p50": 86070,
    "cache_hit_median": 0.9825,
    "comp_p50": 166,
    "comp_p90": 321,
    "comp_max": 763,
    "reas_p50": 108,
    "reas_p90": 246,
    "reas_max": 623,
    "cont_p50": 57,
    "cont_p90": 94,
    "cont_max": 140,
    "ttft_p50": 37.918,
    "ttft_p90": 65.135,
    "wall_p50": 49.67,
    "wall_sum": 1783.2
  },
  {
    "arm": "K1_kn1",
    "ok": 36,
    "total": 36,
    "errors": {},
    "finish_counts": {
      "tool_calls": 36
    },
    "empty_content_no_tc": 0,
    "tool_call_reqs": 36,
    "undeclared_tc_reqs": 0,
    "dsml_in_content_reqs": 0,
    "loop_r": 0,
    "loop_r_periods": [],
    "loop_c": 0,
    "loop_c_periods": [],
    "engine_loop_fired": 0,
    "ge4k": 0,
    "ge8k": 0,
    "ge16k": 0,
    "prompt_tokens_p50": 85960,
    "cache_hit_median": 0.9841,
    "comp_p50": 168,
    "comp_p90": 395,
    "comp_max": 512,
    "reas_p50": 57,
    "reas_p90": 311,
    "reas_max": 415,
    "cont_p50": 76,
    "cont_p90": 141,
    "cont_max": 186,
    "ttft_p50": 32.012,
    "ttft_p90": 50.446,
    "wall_p50": 39.66,
    "wall_sum": 1516.9
  },
  {
    "arm": "K0_kn0",
    "ok": 36,
    "total": 36,
    "errors": {},
    "finish_counts": {
      "tool_calls": 36
    },
    "empty_content_no_tc": 0,
    "tool_call_reqs": 36,
    "undeclared_tc_reqs": 0,
    "dsml_in_content_reqs": 0,
    "loop_r": 0,
    "loop_r_periods": [],
    "loop_c": 0,
    "loop_c_periods": [],
    "engine_loop_fired": 0,
    "ge4k": 0,
    "ge8k": 0,
    "ge16k": 0,
    "prompt_tokens_p50": 85847,
    "cache_hit_median": 0.985,
    "comp_p50": 131,
    "comp_p90": 260,
    "comp_max": 307,
    "reas_p50": 39,
    "reas_p90": 132,
    "reas_max": 208,
    "cont_p50": 73,
    "cont_p90": 140,
    "cont_max": 141,
    "ttft_p50": 18.312,
    "ttft_p90": 55.434,
    "wall_p50": 34.1,
    "wall_sum": 1550.1
  },
  {
    "arm": "A1_base",
    "ok": 36,
    "total": 36,
    "errors": {},
    "finish_counts": {
      "tool_calls": 36
    },
    "empty_content_no_tc": 0,
    "tool_call_reqs": 36,
    "undeclared_tc_reqs": 0,
    "dsml_in_content_reqs": 0,
    "loop_r": 0,
    "loop_r_periods": [],
    "loop_c": 0,
    "loop_c_periods": [],
    "engine_loop_fired": 0,
    "ge4k": 0,
    "ge8k": 0,
    "ge16k": 0,
    "prompt_tokens_p50": 86070,
    "cache_hit_median": 0.9829,
    "comp_p50": 166,
    "comp_p90": 321,
    "comp_max": 763,
    "reas_p50": 108,
    "reas_p90": 246,
    "reas_max": 623,
    "cont_p50": 57,
    "cont_p90": 94,
    "cont_max": 140,
    "ttft_p50": 12.914,
    "ttft_p90": 66.969,
    "wall_p50": 31.82,
    "wall_sum": 1468.0
  },
  {
    "arm": "E_max",
    "ok": 36,
    "total": 36,
    "errors": {},
    "finish_counts": {
      "tool_calls": 36
    },
    "empty_content_no_tc": 0,
    "tool_call_reqs": 36,
    "undeclared_tc_reqs": 0,
    "dsml_in_content_reqs": 0,
    "loop_r": 0,
    "loop_r_periods": [],
    "loop_c": 0,
    "loop_c_periods": [],
    "engine_loop_fired": 0,
    "ge4k": 0,
    "ge8k": 0,
    "ge16k": 0,
    "prompt_tokens_p50": 86070,
    "cache_hit_median": 0.0,
    "comp_p50": 165,
    "comp_p90": 348,
    "comp_max": 638,
    "reas_p50": 109,
    "reas_p90": 224,
    "reas_max": 498,
    "cont_p50": 57,
    "cont_p90": 140,
    "cont_max": 303,
    "ttft_p50": 54.173,
    "ttft_p90": 90.56,
    "wall_p50": 84.29,
    "wall_sum": 3097.7
  },
  {
    "arm": "B16_tb16k",
    "ok": 36,
    "total": 36,
    "errors": {},
    "finish_counts": {
      "tool_calls": 36
    },
    "empty_content_no_tc": 0,
    "tool_call_reqs": 36,
    "undeclared_tc_reqs": 0,
    "dsml_in_content_reqs": 0,
    "loop_r": 0,
    "loop_r_periods": [],
    "loop_c": 0,
    "loop_c_periods": [],
    "engine_loop_fired": 0,
    "ge4k": 0,
    "ge8k": 0,
    "ge16k": 0,
    "prompt_tokens_p50": 86070,
    "cache_hit_median": 0.983,
    "comp_p50": 166,
    "comp_p90": 321,
    "comp_max": 763,
    "reas_p50": 108,
    "reas_p90": 246,
    "reas_max": 623,
    "cont_p50": 57,
    "cont_p90": 94,
    "cont_max": 140,
    "ttft_p50": 11.446,
    "ttft_p90": 50.297,
    "wall_p50": 32.63,
    "wall_sum": 1278.4
  }
]
```

## 3. Paired Differences vs `A1_base` (note `A2_base_vs_A1_base` is same-config A/A noise floor)
```json
{
  "A2_base_vs_A1_base": {
    "reasoning_tokens": {
      "n": 36,
      "mean_diff": 0,
      "median_diff": 0.0,
      "ci95": [
        0,
        0
      ]
    },
    "completion_tokens": {
      "n": 36,
      "mean_diff": 0,
      "median_diff": 0.0,
      "ci95": [
        0,
        0
      ]
    },
    "ttft_s": {
      "n": 36,
      "mean_diff": 9.19,
      "median_diff": 1.97,
      "ci95": [
        -4.92,
        23.29
      ]
    },
    "wall_s": {
      "n": 36,
      "mean_diff": 8.75,
      "median_diff": 9.75,
      "ci95": [
        -3.66,
        20.84
      ]
    }
  },
  "K1_kn1_vs_A1_base": {
    "reasoning_tokens": {
      "n": 36,
      "mean_diff": -29.33,
      "median_diff": -44.5,
      "ci95": [
        -63.78,
        1.42
      ]
    },
    "completion_tokens": {
      "n": 36,
      "mean_diff": -5.03,
      "median_diff": -1.5,
      "ci95": [
        -41.36,
        27.94
      ]
    },
    "ttft_s": {
      "n": 36,
      "mean_diff": 5.46,
      "median_diff": 10.21,
      "ci95": [
        -6.45,
        16.37
      ]
    },
    "wall_s": {
      "n": 36,
      "mean_diff": 1.36,
      "median_diff": 9.08,
      "ci95": [
        -9.61,
        11.23
      ]
    }
  },
  "K0_kn0_vs_A1_base": {
    "reasoning_tokens": {
      "n": 36,
      "mean_diff": -72.94,
      "median_diff": -73.5,
      "ci95": [
        -104.36,
        -46.5
      ]
    },
    "completion_tokens": {
      "n": 36,
      "mean_diff": -57.64,
      "median_diff": -48.0,
      "ci95": [
        -94.78,
        -27.31
      ]
    },
    "ttft_s": {
      "n": 36,
      "mean_diff": 3.34,
      "median_diff": 5.69,
      "ci95": [
        -9.27,
        15.45
      ]
    },
    "wall_s": {
      "n": 36,
      "mean_diff": 2.28,
      "median_diff": 6.72,
      "ci95": [
        -9.94,
        13.63
      ]
    }
  },
  "E_max_vs_A1_base": {
    "reasoning_tokens": {
      "n": 36,
      "mean_diff": 4.25,
      "median_diff": 0.0,
      "ci95": [
        -27.53,
        32.25
      ]
    },
    "completion_tokens": {
      "n": 36,
      "mean_diff": 5.14,
      "median_diff": 0.0,
      "ci95": [
        -32.67,
        43.56
      ]
    },
    "ttft_s": {
      "n": 36,
      "mean_diff": 41.49,
      "median_diff": 40.19,
      "ci95": [
        29.85,
        52.99
      ]
    },
    "wall_s": {
      "n": 36,
      "mean_diff": 45.27,
      "median_diff": 39.68,
      "ci95": [
        32.03,
        56.79
      ]
    }
  },
  "B16_tb16k_vs_A1_base": {
    "reasoning_tokens": {
      "n": 36,
      "mean_diff": 0,
      "median_diff": 0.0,
      "ci95": [
        0,
        0
      ]
    },
    "completion_tokens": {
      "n": 36,
      "mean_diff": 0,
      "median_diff": 0.0,
      "ci95": [
        0,
        0
      ]
    },
    "ttft_s": {
      "n": 36,
      "mean_diff": -4.99,
      "median_diff": -6.03,
      "ci95": [
        -15.22,
        5.89
      ]
    },
    "wall_s": {
      "n": 36,
      "mean_diff": -5.27,
      "median_diff": -11.15,
      "ci95": [
        -14.66,
        4.2
      ]
    }
  }
}
```

## 4. Proxy Production Audit & Shadow Loop Scanner Snapshot (`/home/joseyarashio/.cache/spark-proxy-audit/completions.jsonl`)
```json
{
  "total_audit_rows": 239,
  "external_rows": 2,
  "external_clients": {
    "100.79.40.68": 2
  },
  "external_outcomes": {
    "ok|stop": 2
  },
  "external_shadow_loops": [],
  "external_ge4k": []
}
```

## 5. Experiment Harness Excerpt
```python
#!/usr/bin/env python3
"""Controlled long-context, real-tools A/B over key unexplored variables (~82K prompt tokens).

Tests 6 interleaved arms per conversation (randomized order per conv_idx, same seed=7000+conv_idx,
stream=True, LOOP_CUT=0 so natural lengths & completions are observed cleanly):
  A1_base   : effort=high, keep_n=2, budget=0   (production baseline rep 1)
  A2_base   : effort=high, keep_n=2, budget=0   (built-in A/A noise floor rep 2)
  E_max     : effort=max,  keep_n=2, budget=0   (effort high vs max)
  K1_kn1    : effort=high, keep_n=1, budget=0   (strip older reasoning, keep last 1)
  K0_kn0    : effort=high, keep_n=0, budget=0   (strip all prior reasoning)
  B16_tb16k : effort=high, keep_n=2, budget=16384 (thinking_budget WITH real tools)

Supports resume by skipping completed (conv_idx, arm) pairs.
usage: N=36 CONC=4 run_longctx_controls.py OUT.jsonl
       run_longctx_controls.py --summary OUT.jsonl
"""
import collections, concurrent.futures, contextlib, io, json, os, random, re, statistics, string, sys, threading, time, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
with contextlib.redirect_stdout(io.StringIO()):
    import run_5hour_stress_experiment as s5

API = os.environ.get("API", "http://127.0.0.1:8889/v1/chat/completions")
MODEL = "DeepSeek-V4.1-Flash-1017-TF"
N = int(os.environ.get("N", "36"))
CONC = int(os.environ.get("CONC", "4"))
MAXTOK = int(os.environ.get("MAXTOK", "32768"))
LOOP_RE = re.compile(r"(.{20,600}?)\1{4,}", re.S)
lock = threading.Lock()

TOOLS = [
    {"type": "function", "function": {"name": "read_file", "description": "Read lines from a source or config file.",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "start_line": {"type": "integer"}, "end_line": {"type": "integer"}}, "required": ["path"]}}},
    {"type": "function", "function": {"name": "search_files", "description": "Regex search across repository files.",
        "parameters": {"type": "object", "properties": {"pattern": {"type": "string"}, "glob": {"type": "string"}}, "required": ["pattern"]}}},
    {"type": "function", "function": {"name": "patch_file", "description": "Apply a targeted replacement in a file.",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "old_text": {"type": "string"}, "new_text": {"type": "string"}}, "required": ["path", "old_text", "new_text"]}}},
    {"type": "function", "function": {"name": "run_tests", "description": "Execute a test target and return stdout/exit code.",
        "parameters": {"type": "object", "properties": {"suite": {"type": "string"}, "filter": {"type": "string"}}, "required": ["suite"]}}},
    {"type": "function", "function": {"name": "inspect_logs", "description": "Fetch recent log lines for a service.",
        "parameters": {"type": "object", "properties": {"service": {"type": "string"}, "lines": {"type": "integer"}}, "required": ["service"]}}},
    {"type": "function", "function": {"name": "check_cluster_health", "description": "Query node health, memory, and RDMA counters.",
        "parameters": {"type": "object", "properties": {"node": {"type": "string", "enum": ["rank0", "rank1", "both"]}}, "required": ["node"]}}},
    {"type": "function", "function": {"name": "git_diff", "description": "Show current uncommitted diff.",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "list_directory", "description": "List files in a directory.",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
]
DECLARED_TOOLS = {t["function"]["name"] for t in TOOLS}

ARMS = [
    {"name": "A1_base",   "effort": "high", "keep_n": 2, "budget": 0},
    {"name": "A2_base",   "effort": "high", "keep_n": 2, "budget": 0},
    {"name": "E_max",     "effort": "max",  "keep_n": 2, "budget": 0},
    {"name": "K1_kn1",    "effort": "high", "keep_n": 1, "budget": 0},
    {"name": "K0_kn0",    "effort": "high", "keep_n": 0, "budget": 0},
    {"name": "B16_tb16k", "effort": "high", "keep_n": 2, "budget": 16384},
]

TASKS = [
    ("Diagnose why intermittent RDMA sync stalls happen only under mixed prefill/decode batches and propose the safest next verification step.",
     "FAIL test_tp2_sync: timeout after 30.0s waiting on rank1 barrier when slot_id=3 resumed partial prefix; rank0 GPU-Util=97% power=16.2W; rank1 GPU-Util=0%."),
    ("Investigate why multi-turn KV cache hit rate drops after turn 4 despite stable prefix bytes, and decide whether to inspect another file or give the fix.",
     "CACHE_METRICS: turn1=0% turn2=94% turn3=96% turn4=95% turn5=12% turn6=14%; evicted=0; kept_states=142; mem_spare_mib=0; note: turn5 added tool_choice='auto'."),
    ("Audit the coordinator retry and backoff loop for cascade risks under transient 502/429 responses.",
     "STRESS_RESULT: 4821 requests in 1.8s after upstream 502 spike; worker_threads=8; backoff_only_on_429=True; queue_waiters=0; client_timeout_ms=60000."),
    ("Determine why a strict JSON config validator rejects a valid schema update on node2 while node1 accepts it.",
     "DIFF_OUT: node1 sha=de40bcdd ok; node2 sha=d33e73ff mismatch on engram_map; restart_log=skipped check because SSH timed out after 2s."),
]


def build_conversation(conv_idx: int) -> list[dict]:
    rng = random.Random(3000 + conv_idx)
    salt = "".join(rng.choices(string.ascii_letters + string.digits, k=24))
    # ~49K generated codebase corpus -> ~85K-92K prompt tokens (inside the >=80K zone)
    corpus = s5.generate_codebase_corpus(49000, salt)
    task_desc, final_err = TASKS[conv_idx % len(TASKS)]
    is_synth = (conv_idx % 2 == 0)
    tail_prompt = (
        f"Task: {task_desc}\nAll initial diagnostics have been collected in the turns below. "
        "Decide if any single check is still missing or synthesize the complete root cause, exact patch, and proof."
        if is_synth else f"Task: {task_desc}\nStart by inspecting the relevant components."
    )
    msgs: list[dict] = [
        {"role": "system", "content": (
            "You are a principal distributed systems engineer working inside an autonomous coding agent. "
            "Use the provided tools when you need to verify files, logs, or tests. "
            "When you have enough evidence, provide a concise, grounded diagnosis and next action without inventing unverified paths."
        )},
        {"role": "user", "content": f"Workspace snapshot [{salt}]:\n```python\n{corpus}\n```\n\n{tail_prompt}"},
    ]
    # Build 6 multi-turn tool calls WITH realistic reasoning_content on each assistant turn
    steps = [
        ("list_directory", {"path": "src/"}, '{"entries": ["coordinator.py", "cache.py", "metrics.py", "retry.py", "tests/"]}'),
        ("search_files", {"pattern": "synchronize_state|barrier|slot", "glob": "*.py"}, '{"matches": ["src/coordinator.py:142", "src/coordinator.py:218", "src/cache.py:88"]}'),
        ("read_file", {"path": "src/coordinator.py", "start_line": 120, "end_line": 240}, '{"lines": "120: def synchronize_state(slot_id, prefix_len): ... # lock held across barrier"}'),
        ("read_file", {"path": "src/cache.py", "start_line": 60, "end_line": 140}, '{"lines": "60: def lookup_or_evict(key, spare_mib): ... # evict FIFO when spare_mib == 0"}'),
        ("check_cluster_health" if is_synth else "inspect_logs",
         {"node": "both"} if is_synth else {"service": "tp2-worker", "lines": 30},
         '{"rank0": {"mem_avail_gib": 3.4, "gpu_util": 97}, "rank1": {"mem_avail_gib": 4.1, "gpu_util": 0}}' if is_synth
         else '{"tail": ["WARN slot 3 resumed 84992/88064", "INFO rank1 heartbeat ok", "WARN retry burst 400ms"]}'),
        ("run_tests", {"suite": "unit_cluster", "filter": f"case_{conv_idx % 4}"}, f'{{"exit_code": 1, "output": "{final_err}"}}'),
    ]
    for s_idx, (tname, targs, tres) in enumerate(steps):
        cid = f"call_{conv_idx}_{
```
