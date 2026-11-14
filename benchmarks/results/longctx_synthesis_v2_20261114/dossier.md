# DGX Spark TP=2 Audit Dossier: Phase 2 v2: Long-Context Synthesis (Long-Thinking), seeds de-duplicated, caches pre-warmed, binding budgets

## 1. Environment & Engine Configuration
- Result dir: `/home/joseyarashio/dgx-spark-tp2-recipes/benchmarks/results/longctx_synthesis_v2_20261114`
- Runner script: `/home/joseyarashio/dgx-spark-tp2-recipes/benchmarks/run_longctx_synthesis.py`
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

## 2. Per-Arm Summary (`results.jsonl`, total rows=96)
```json
[
  {
    "arm": "EB16_max_tb16k",
    "ok": 16,
    "total": 16,
    "errors": {},
    "finish_counts": {
      "tool_calls": 11,
      "stop": 5
    },
    "empty_content_no_tc": 0,
    "tool_call_reqs": 11,
    "undeclared_tc_reqs": 0,
    "dsml_in_content_reqs": 0,
    "loop_r": 1,
    "loop_r_periods": [
      282
    ],
    "loop_c": 0,
    "loop_c_periods": [],
    "engine_loop_fired": 0,
    "ge4k": 16,
    "ge8k": 16,
    "ge16k": 15,
    "prompt_tokens_p50": 85071,
    "cache_hit_median": 0.9869,
    "comp_p50": 16461,
    "comp_p90": 18098,
    "comp_max": 19006,
    "reas_p50": 16385,
    "reas_p90": 16385,
    "reas_max": 16385,
    "cont_p50": 76,
    "cont_p90": 6371,
    "cont_max": 8557,
    "ttft_p50": 1.132,
    "ttft_p90": 2.362,
    "wall_p50": 472.03,
    "wall_sum": 7821.7
  },
  {
    "arm": "A2_base",
    "ok": 16,
    "total": 16,
    "errors": {},
    "finish_counts": {
      "stop": 15,
      "length": 1
    },
    "empty_content_no_tc": 0,
    "tool_call_reqs": 0,
    "undeclared_tc_reqs": 0,
    "dsml_in_content_reqs": 0,
    "loop_r": 0,
    "loop_r_periods": [],
    "loop_c": 0,
    "loop_c_periods": [],
    "engine_loop_fired": 0,
    "ge4k": 16,
    "ge8k": 16,
    "ge16k": 9,
    "prompt_tokens_p50": 85071,
    "cache_hit_median": 0.9869,
    "comp_p50": 17159,
    "comp_p90": 24347,
    "comp_max": 32768,
    "reas_p50": 9490,
    "reas_p90": 14445,
    "reas_max": 26229,
    "cont_p50": 7200,
    "cont_p90": 9509,
    "cont_max": 10071,
    "ttft_p50": 0.973,
    "ttft_p90": 1.322,
    "wall_p50": 443.12,
    "wall_sum": 7874.7
  },
  {
    "arm": "A1_base",
    "ok": 16,
    "total": 16,
    "errors": {},
    "finish_counts": {
      "length": 2,
      "stop": 14
    },
    "empty_content_no_tc": 0,
    "tool_call_reqs": 0,
    "undeclared_tc_reqs": 0,
    "dsml_in_content_reqs": 0,
    "loop_r": 0,
    "loop_r_periods": [],
    "loop_c": 0,
    "loop_c_periods": [],
    "engine_loop_fired": 0,
    "ge4k": 16,
    "ge8k": 15,
    "ge16k": 9,
    "prompt_tokens_p50": 85071,
    "cache_hit_median": 0.9869,
    "comp_p50": 17182,
    "comp_p90": 32251,
    "comp_max": 32768,
    "reas_p50": 9159,
    "reas_p90": 21956,
    "reas_max": 27027,
    "cont_p50": 6639,
    "cont_p90": 8751,
    "cont_max": 10506,
    "ttft_p50": 1.004,
    "ttft_p90": 1.323,
    "wall_p50": 521.94,
    "wall_sum": 8703.3
  },
  {
    "arm": "E_max",
    "ok": 16,
    "total": 16,
    "errors": {},
    "finish_counts": {
      "stop": 7,
      "length": 9
    },
    "empty_content_no_tc": 6,
    "tool_call_reqs": 0,
    "undeclared_tc_reqs": 0,
    "dsml_in_content_reqs": 0,
    "loop_r": 1,
    "loop_r_periods": [
      62
    ],
    "loop_c": 0,
    "loop_c_periods": [],
    "engine_loop_fired": 0,
    "ge4k": 16,
    "ge8k": 16,
    "ge16k": 13,
    "prompt_tokens_p50": 85071,
    "cache_hit_median": 0.9869,
    "comp_p50": 32768,
    "comp_p90": 32768,
    "comp_max": 32768,
    "reas_p50": 22575,
    "reas_p90": 32768,
    "reas_max": 32768,
    "cont_p50": 5231,
    "cont_p90": 9011,
    "cont_max": 11793,
    "ttft_p50": 0.974,
    "ttft_p90": 1.302,
    "wall_p50": 722.79,
    "wall_sum": 11055.3
  },
  {
    "arm": "K0_kn0",
    "ok": 16,
    "total": 16,
    "errors": {},
    "finish_counts": {
      "stop": 16
    },
    "empty_content_no_tc": 0,
    "tool_call_reqs": 0,
    "undeclared_tc_reqs": 0,
    "dsml_in_content_reqs": 0,
    "loop_r": 0,
    "loop_r_periods": [],
    "loop_c": 0,
    "loop_c_periods": [],
    "engine_loop_fired": 0,
    "ge4k": 16,
    "ge8k": 16,
    "ge16k": 5,
    "prompt_tokens_p50": 84783,
    "cache_hit_median": 0.9835,
    "comp_p50": 12928,
    "comp_p90": 26185,
    "comp_max": 29810,
    "reas_p50": 7512,
    "reas_p90": 16626,
    "reas_max": 19418,
    "cont_p50": 5884,
    "cont_p90": 10159,
    "cont_max": 10392,
    "ttft_p50": 1.177,
    "ttft_p90": 47.867,
    "wall_p50": 435.23,
    "wall_sum": 7975.8
  },
  {
    "arm": "B8_tb8k",
    "ok": 16,
    "total": 16,
    "errors": {},
    "finish_counts": {
      "tool_calls": 8,
      "stop": 8
    },
    "empty_content_no_tc": 0,
    "tool_call_reqs": 8,
    "undeclared_tc_reqs": 0,
    "dsml_in_content_reqs": 0,
    "loop_r": 0,
    "loop_r_periods": [],
    "loop_c": 0,
    "loop_c_periods": [],
    "engine_loop_fired": 0,
    "ge4k": 16,
    "ge8k": 15,
    "ge16k": 0,
    "prompt_tokens_p50": 85071,
    "cache_hit_median": 0.9869,
    "comp_p50": 8269,
    "comp_p90": 11888,
    "comp_max": 14030,
    "reas_p50": 8003,
    "reas_p90": 8193,
    "reas_max": 8193,
    "cont_p50": 141,
    "cont_p90": 6027,
    "cont_max": 7632,
    "ttft_p50": 0.976,
    "ttft_p90": 1.324,
    "wall_p50": 304.22,
    "wall_sum": 4640.4
  }
]
```

## 3. Paired Differences vs `A1_base` (note `A2_base_vs_A1_base` is same-config A/A noise floor)
```json
{
  "EB16_max_tb16k_vs_A1_base": {
    "reasoning_tokens": {
      "n": 16,
      "mean_diff": 2915.62,
      "median_diff": 4250.5,
      "ci95": [
        -466.81,
        5839.19
      ]
    },
    "completion_tokens": {
      "n": 16,
      "mean_diff": -2087.38,
      "median_diff": -1619.5,
      "ci95": [
        -6393.56,
        1861.06
      ]
    },
    "ttft_s": {
      "n": 16,
      "mean_diff": 0.83,
      "median_diff": 0.04,
      "ci95": [
        -0.09,
        2.27
      ]
    },
    "wall_s": {
      "n": 16,
      "mean_diff": -55.1,
      "median_diff": 16.75,
      "ci95": [
        -176.95,
        54.27
      ]
    }
  },
  "A2_base_vs_A1_base": {
    "reasoning_tokens": {
      "n": 16,
      "mean_diff": -849.69,
      "median_diff": -687.5,
      "ci95": [
        -4019.62,
        1871.81
      ]
    },
    "completion_tokens": {
      "n": 16,
      "mean_diff": -721.38,
      "median_diff": -919.5,
      "ci95": [
        -3708.56,
        2071.94
      ]
    },
    "ttft_s": {
      "n": 16,
      "mean_diff": -0.1,
      "median_diff": -0.01,
      "ci95": [
        -0.3,
        0.0
      ]
    },
    "wall_s": {
      "n": 16,
      "mean_diff": -51.79,
      "median_diff": -45.65,
      "ci95": [
        -114.13,
        5.83
      ]
    }
  },
  "E_max_vs_A1_base": {
    "reasoning_tokens": {
      "n": 16,
      "mean_diff": 11276.5,
      "median_diff": 11743.5,
      "ci95": [
        7713.81,
        14858.44
      ]
    },
    "completion_tokens": {
      "n": 16,
      "mean_diff": 8929.5,
      "median_diff": 7977.5,
      "ci95": [
        5588.88,
        12513.5
      ]
    },
    "ttft_s": {
      "n": 16,
      "mean_diff": -0.08,
      "median_diff": -0.01,
      "ci95": [
        -0.28,
        0.03
      ]
    },
    "wall_s": {
      "n": 16,
      "mean_diff": 147.0,
      "median_diff": 142.3,
      "ci95": [
        57.31,
        232.64
      ]
    }
  },
  "K0_kn0_vs_A1_base": {
    "reasoning_tokens": {
      "n": 16,
      "mean_diff": -2215.06,
      "median_diff": -2660.5,
      "ci95": [
        -4642.56,
        127.44
      ]
    },
    "completion_tokens": {
      "n": 16,
      "mean_diff": -2532,
      "median_diff": -2597.5,
      "ci95": [
        -4938.38,
        -90.31
      ]
    },
    "ttft_s": {
      "n": 16,
      "mean_diff": 11.8,
      "median_diff": -0.11,
      "ci95": [
        2.94,
        20.99
      ]
    },
    "wall_s": {
      "n": 16,
      "mean_diff": -45.47,
      "median_diff": -39.2,
      "ci95": [
        -122.41,
        42.66
      ]
    }
  },
  "B8_tb8k_vs_A1_base": {
    "reasoning_tokens": {
      "n": 16,
      "mean_diff": -4993.12,
      "median_diff": -3331.0,
      "ci95": [
        -8466.62,
        -2024.44
      ]
    },
    "completion_tokens": {
      "n": 16,
      "mean_diff": -9362.31,
      "median_diff": -5771.5,
      "ci95": [
        -13775.44,
        -5408.94
      ]
    },
    "ttft_s": {
      "n": 16,
      "mean_diff": -0.05,
      "median_diff": -0.0,
      "ci95": [
        -0.3,
        0.15
      ]
    },
    "wall_s": {
      "n": 16,
      "mean_diff": -253.93,
      "median_diff": -233.0,
      "ci95": [
        -356.5,
        -158.67
      ]
    }
  }
}
```

## 4. Proxy Production Audit & Shadow Loop Scanner Snapshot (`/home/joseyarashio/.cache/spark-proxy-audit/completions.jsonl`)
```json
{
  "total_audit_rows": 532,
  "external_rows": 138,
  "external_clients": {
    "100.79.40.68": 2,
    "100.108.5.82": 136
  },
  "external_outcomes": {
    "ok|stop": 13,
    "client_left|None": 23,
    "ok|length": 35,
    "ok|tool_calls": 67
  },
  "external_shadow_loops": [
    {
      "client_ip": "100.108.5.82",
      "effort": "low",
      "prompt_tokens": null,
      "shadow_loop_ch": "reasoning",
      "shadow_loop_period_chars": 220,
      "shadow_loop_at_chars": 1640,
      "finish_reason": null,
      "outcome": "client_left"
    },
    {
      "client_ip": "100.108.5.82",
      "effort": "low",
      "prompt_tokens": null,
      "shadow_loop_ch": "reasoning",
      "shadow_loop_period_chars": 59,
      "shadow_loop_at_chars": 1076,
      "finish_reason": null,
      "outcome": "client_left"
    },
    {
      "client_ip": "100.108.5.82",
      "effort": "low",
      "prompt_tokens": null,
      "shadow_loop_ch": "reasoning",
      "shadow_loop_period_chars": 45,
      "shadow_loop_at_chars": 2854,
      "finish_reason": null,
      "outcome": "client_left"
    }
  ],
  "external_ge4k": [
    {
      "client_ip": "100.108.5.82",
      "effort": "medium",
      "tools_count": 5,
      "prompt_tokens": 196883,
      "reasoning_tokens": 5073,
      "content_tokens": 5643,
      "finish_reason": "stop",
      "outcome": "ok",
      "shadow_loop_ch": null
    },
    {
      "client_ip": "100.108.5.82",
      "effort": "medium",
      "tools_count": 5,
      "prompt_tokens": 220182,
      "reasoning_tokens": 2580,
      "content_tokens": 3676,
      "finish_reason": "stop",
      "outcome": "ok",
      "shadow_loop_ch": null
    }
  ]
}
```

## 5. Experiment Harness Excerpt
```python
#!/usr/bin/env python3
"""Phase 2 (v2) Long-Thinking Synthesis A/B WITH real tools attached (~85K prompt tokens).

All 6 prior tool turns (with verbose reasoning_content) are provided and the final user turn forbids
further tool calls and asks for an exhaustive synthesis, while `tools` + `tool_choice="auto"` stay
attached (matching real final-synthesis agent turns).

v2 fixes after the Phase 1 dual audit (Fable 5.2 + GPT-6 Astra) and aborted v1 Phase 2 run:
  1. Distinct seed per (conv, arm): seed = 8000 + 16*conv_idx + arm_index. v1 used one seed per
     conversation, so A1/A2/B16 produced byte-identical outputs and the A/A arm measured nothing but
     queueing noise. Now A2_base vs A1_base is a true sampling-noise floor, and every arm carries the
     same seed-noise so comparisons are fair.
  2. Cache-confound removal: each conversation is pre-warmed once for effort=high AND effort=max
     (max_tokens=1) before its timed arms run, so E_max is no longer the only cold-prefill arm
     (v1 E_max cache_hit=0.0 -> +41s TTFT that was prefill, not thinking).
  3. Thinking-budget arms that can actually bind: v1 B16 (effort=high, 16K) never reached the cap
     (high thinks ~8K). v2 tests EB16_max_tb16k (effort=max + 16384, where max thinks 16K-28K and hit
     length 2/3 in v1) and B8_tb8k (effort=high + 8192).
  4. Per-conversation worker: one worker warms then runs all arms for a conversation in random order;
     CONC conversations run in parallel. K1_kn1 dropped (inconclusive in Phase 1, budget for time).

Arms:
  A1_base        : effort=high, keep_n=2, budget=0     (production baseline)
  A2_base        : effort=high, keep_n=2, budget=0     (A/A sampling-noise floor, different seed)
  E_max          : effort=max,  keep_n=2, budget=0
  EB16_max_tb16k : effort=max,  keep_n=2, budget=16384
  K0_kn0         : effort=high, keep_n=0, budget=0     (strip all prior reasoning client-side)
  B8_tb8k        : effort=high, keep_n=2, budget=8192

usage: N=16 CONC=3 run_longctx_synthesis.py OUT.jsonl
       run_longctx_synthesis.py --summary OUT.jsonl
"""
import collections, concurrent.futures, contextlib, io, json, os, random, re, statistics, string, sys, threading, time, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
with contextlib.redirect_stdout(io.StringIO()):
    import run_5hour_stress_experiment as s5

API = os.environ.get("API", "http://127.0.0.1:8889/v1/chat/completions")
MODEL = "DeepSeek-V4.1-Flash-1017-TF"
N = int(os.environ.get("N", "16"))
CONC = int(os.environ.get("CONC", "3"))
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
    {"name": "A1_base",        "effort": "high", "keep_n": 2, "budget": 0},
    {"name": "A2_base",        "effort": "high", "keep_n": 2, "budget": 0},
    {"name": "E_max",          "effort": "max",  "keep_n": 2, "budget": 0},
    {"name": "EB16_max_tb16k", "effort": "max",  "keep_n": 2, "budget": 16384},
    {"name": "K0_kn0",         "effort": "high", "keep_n": 0, "budget": 0},
    {"name": "B8_tb8k",        "effort": "high", "keep_n": 2, "budget": 8192},
]
ARM_INDEX = {a["name"]: i for i, a in enumerate(ARMS)}

SYNTH_PROMPTS = [
    ("Audit every coordinator and metrics module in the workspace snapshot for subtle concurrency, ABA, and cache-invalidation bugs.",
     "All tools have already run. Do NOT call any more tools. In your final response, write: (1) an exhaustive class-by-class bug audit citing exact line numbers and interleaving schedules for every race, (2) a unified patch fixing all of them without introducing deadlocks, and (3) formal state invariants proving safety under arbitrary crash/retry."),
    ("Reconcile the conflicting throughput, memory, and prefix-reuse numbers across turns 1-6 and design a scale-invariant admission and eviction algorithm.",
     "No further tool calls are needed or permitted. Provide a rigorous first-principles analysis deriving exact byte formulas, counterexamples for why the current thresholds oscillate, the complete replacement Python/Zig pseudocode, and an edge-case verification table covering 1..64 concurrent slots."),
    ("Analyze why the cluster stalls at high context pressure despite healthy HTTP/200 health checks and design an atomic two-phase recovery protocol.",
     "Stop calling tools—you already have all logs and code above. Produce a complete state-machine transition matrix, prove liveness and absence of split-brain across Rank 0 and Rank 1 under partial packet loss, and give the minimal diff."),
    ("Design a zero-regression refactoring of the entire snapshot that decouples state tracking from request scheduling without breaking any public invariant.",
     "Do NOT invoke any tools; synthesize everything directly. Enumerate every coupling edge in the snapshot, derive the dependency DAG, write the complete refactored module interfaces, and prove backward compatibility across all 4 failure modes."),
]


def build_conversation(conv_idx: int) -> list[dict]:
    rng = random.Random(9000 + conv_idx)
    salt = "".join(rng.choices(string.ascii_letters + string.digits, k=24))
    corpus = s5.generate_codebase_corpus(48000, salt)
    task_desc, synth_ask = SYNTH_PROMPTS[conv_idx % len(SYNTH_PROMPTS)]
    msgs: list[dict] = [
        {"role": "system", "content": (
            "You are a principal distributed systems engineer completing the final synthesis turn of an autonomous audit. "
            "Follow tool instructions strictly: when the user states all evidence is collected and forbids further tool calls, "
            "reason thoroughly and deliver the complete answer directly without calling tools."
        )},
        {"role": "user", "content": f"Workspace snapshot [{salt}]:\n```python\n{corpu
```
