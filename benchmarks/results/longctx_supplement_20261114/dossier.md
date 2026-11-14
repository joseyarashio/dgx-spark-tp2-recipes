# Phase 2 Supplement (P2S) Empirical Dossier

## S3a: OMP Short Task (max_tokens=120, tools=0, low vs none)
```json
[
  {
    "arm": "OMP120_low",
    "ok": 10,
    "total": 10,
    "finish_counts": {
      "stop": 5,
      "length": 5
    },
    "valid_delivery": 0,
    "has_code_block": 0,
    "tool_call_reqs": 0,
    "dsml_in_content_reqs": 0,
    "loop_r": 0,
    "loop_r_periods": [],
    "loop_c": 0,
    "engine_loop": 0,
    "prompt_p50": 71,
    "cache_hit_min": 0.0,
    "cache_hit_med": 0.0,
    "reas_p50": 101,
    "reas_p90": 120,
    "cont_p50": 6,
    "cont_p90": 20,
    "comp_p50": 109,
    "ttft_p50": 0.425,
    "ttft_p90": 0.444,
    "wall_p50": 1.77,
    "wall_sum": 17.3,
    "mem_min_gib": null
  },
  {
    "arm": "OMP120_none",
    "ok": 10,
    "total": 10,
    "finish_counts": {
      "stop": 10
    },
    "valid_delivery": 0,
    "has_code_block": 0,
    "tool_call_reqs": 0,
    "dsml_in_content_reqs": 0,
    "loop_r": 0,
    "loop_r_periods": [],
    "loop_c": 0,
    "engine_loop": 0,
    "prompt_p50": 46,
    "cache_hit_min": 0.0,
    "cache_hit_med": 0.0,
    "reas_p50": 0,
    "reas_p90": 0,
    "cont_p50": 9,
    "cont_p90": 20,
    "comp_p50": 9,
    "ttft_p50": 0.332,
    "ttft_p90": 0.357,
    "wall_p50": 0.5,
    "wall_sum": 5.0,
    "mem_min_gib": null
  }
]
```

## S1: 85K Long-Thinking Budget Closure & K0_warm Controls
```json
[
  {
    "arm": "B8_tc_none",
    "ok": 8,
    "total": 8,
    "finish_counts": {
      "stop": 8
    },
    "valid_delivery": 2,
    "has_code_block": 2,
    "tool_call_reqs": 0,
    "dsml_in_content_reqs": 6,
    "loop_r": 0,
    "loop_r_periods": [],
    "loop_c": 0,
    "engine_loop": 0,
    "prompt_p50": 84092,
    "cache_hit_min": 0.9742,
    "cache_hit_med": 0.9862,
    "reas_p50": 8193,
    "reas_p90": 8193,
    "cont_p50": 76,
    "cont_p90": 4008,
    "comp_p50": 8269,
    "ttft_p50": 1.144,
    "ttft_p90": 1.658,
    "wall_p50": 231.98,
    "wall_sum": 1925.1,
    "mem_min_gib": null
  },
  {
    "arm": "B8_no_tools",
    "ok": 8,
    "total": 8,
    "finish_counts": {
      "stop": 8
    },
    "valid_delivery": 1,
    "has_code_block": 1,
    "tool_call_reqs": 0,
    "dsml_in_content_reqs": 7,
    "loop_r": 0,
    "loop_r_periods": [],
    "loop_c": 0,
    "engine_loop": 0,
    "prompt_p50": 84092,
    "cache_hit_min": 0.9742,
    "cache_hit_med": 0.9862,
    "reas_p50": 8193,
    "reas_p90": 8193,
    "cont_p50": 76,
    "cont_p90": 76,
    "comp_p50": 8269,
    "ttft_p50": 0.899,
    "ttft_p90": 1.528,
    "wall_p50": 230.69,
    "wall_sum": 2515.8,
    "mem_min_gib": null
  },
  {
    "arm": "EB16_tc_none",
    "ok": 8,
    "total": 8,
    "finish_counts": {
      "stop": 7,
      "length": 1
    },
    "valid_delivery": 2,
    "has_code_block": 3,
    "tool_call_reqs": 0,
    "dsml_in_content_reqs": 5,
    "loop_r": 0,
    "loop_r_periods": [],
    "loop_c": 0,
    "engine_loop": 0,
    "prompt_p50": 84092,
    "cache_hit_min": 0.9742,
    "cache_hit_med": 0.9862,
    "reas_p50": 16385,
    "reas_p90": 16385,
    "cont_p50": 76,
    "cont_p90": 12453,
    "comp_p50": 16461,
    "ttft_p50": 1.072,
    "ttft_p90": 1.542,
    "wall_p50": 477.67,
    "wall_sum": 4600.3,
    "mem_min_gib": null
  },
  {
    "arm": "K0_warm",
    "ok": 8,
    "total": 8,
    "finish_counts": {
      "stop": 6,
      "length": 2
    },
    "valid_delivery": 6,
    "has_code_block": 6,
    "tool_call_reqs": 0,
    "dsml_in_content_reqs": 0,
    "loop_r": 1,
    "loop_r_periods": [
      28
    ],
    "loop_c": 0,
    "engine_loop": 1,
    "prompt_p50": 84784,
    "cache_hit_min": 0.9765,
    "cache_hit_med": 0.9901,
    "reas_p50": 12774,
    "reas_p90": 32768,
    "cont_p50": 4944,
    "cont_p90": 10068,
    "comp_p50": 18797,
    "ttft_p50": 1.081,
    "ttft_p90": 11.322,
    "wall_p50": 426.68,
    "wall_sum": 3511.1,
    "mem_min_gib": null
  },
  {
    "arm": "EB16_no_tools",
    "ok": 8,
    "total": 8,
    "finish_counts": {
      "stop": 8
    },
    "valid_delivery": 4,
    "has_code_block": 4,
    "tool_call_reqs": 0,
    "dsml_in_content_reqs": 4,
    "loop_r": 0,
    "loop_r_periods": [],
    "loop_c": 0,
    "engine_loop": 0,
    "prompt_p50": 84092,
    "cache_hit_min": 0.9742,
    "cache_hit_med": 0.9862,
    "reas_p50": 16385,
    "reas_p90": 16385,
    "cont_p50": 76,
    "cont_p90": 8442,
    "comp_p50": 16461,
    "ttft_p50": 0.908,
    "ttft_p90": 1.512,
    "wall_p50": 433.6,
    "wall_sum": 4241.5,
    "mem_min_gib": null
  },
  {
    "arm": "A_base",
    "ok": 8,
    "total": 8,
    "finish_counts": {
      "stop": 5,
      "length": 3
    },
    "valid_delivery": 5,
    "has_code_block": 5,
    "tool_call_reqs": 0,
    "dsml_in_content_reqs": 0,
    "loop_r": 1,
    "loop_r_periods": [
      80
    ],
    "loop_c": 0,
    "engine_loop": 0,
    "prompt_p50": 85074,
    "cache_hit_min": 0.9765,
    "cache_hit_med": 0.9869,
    "reas_p50": 8570,
    "reas_p90": 32768,
    "cont_p50": 2092,
    "cont_p90": 6140,
    "comp_p50": 15469,
    "ttft_p50": 0.989,
    "ttft_p90": 10.963,
    "wall_p50": 462.72,
    "wall_sum": 3226.9,
    "mem_min_gib": null
  }
]
```

### S1 Paired vs A_base
```json
{
  "B8_tc_none_vs_A_base": {
    "reasoning_tokens": {
      "n": 8,
      "mean_diff": -8275.75,
      "med_diff": -1778.5,
      "ci95": [
        -17723.25,
        -144.62
      ]
    },
    "content_tokens": {
      "n": 8,
      "mean_diff": -1873.25,
      "med_diff": -423.0,
      "ci95": [
        -3828,
        51.88
      ]
    },
    "ttft_s": {
      "n": 8,
      "mean_diff": -2.14,
      "med_diff": -0.45,
      "ci95": [
        -5.23,
        0.17
      ]
    },
    "wall_s": {
      "n": 8,
      "mean_diff": -162.73,
      "med_diff": -242.77,
      "ci95": [
        -291.01,
        -23.72
      ]
    }
  },
  "B8_no_tools_vs_A_base": {
    "reasoning_tokens": {
      "n": 8,
      "mean_diff": -8040.88,
      "med_diff": -1778.5,
      "ci95": [
        -17723.25,
        295.88
      ]
    },
    "content_tokens": {
      "n": 8,
      "mean_diff": -375,
      "med_diff": -2668.5,
      "ci95": [
        -4456.12,
        6008.88
      ]
    },
    "ttft_s": {
      "n": 8,
      "mean_diff": -2.56,
      "med_diff": -0.44,
      "ci95": [
        -6.23,
        0.17
      ]
    },
    "wall_s": {
      "n": 8,
      "mean_diff": -88.89,
      "med_diff": -126.55,
      "ci95": [
        -211.99,
        42.45
      ]
    }
  },
  "EB16_tc_none_vs_A_base": {
    "reasoning_tokens": {
      "n": 8,
      "mean_diff": 151.12,
      "med_diff": 6413.5,
      "ci95": [
        -9531.25,
        8487.88
      ]
    },
    "content_tokens": {
      "n": 8,
      "mean_diff": 1777.12,
      "med_diff": 57.5,
      "ci95": [
        -2219.5,
        6458.25
      ]
    },
    "ttft_s": {
      "n": 8,
      "mean_diff": -2.32,
      "med_diff": 0.06,
      "ci95": [
        -6.11,
        0.53
      ]
    },
    "wall_s": {
      "n": 8,
      "mean_diff": 171.68,
      "med_diff": 304.48,
      "ci95": [
        5.8,
        321.67
      ]
    }
  },
  "K0_warm_vs_A_base": {
    "reasoning_tokens": {
      "n": 8,
      "mean_diff": -281,
      "med_diff": 987.0,
      "ci95": [
        -9117.12,
        8933.12
      ]
    },
    "content_tokens": {
      "n": 8,
      "mean_diff": 2025.88,
      "med_diff": 1174.0,
      "ci95": [
        -1793.88,
        6102.12
      ]
    },
    "ttft_s": {
      "n": 8,
      "mean_diff": 1.27,
      "med_diff": -0.11,
      "ci95": [
        -2.72,
        5.26
      ]
    },
    "wall_s": {
      "n": 8,
      "mean_diff": 35.52,
      "med_diff": 54.68,
      "ci95": [
        -75.17,
        136.04
      ]
    }
  },
  "EB16_no_tools_vs_A_base": {
    "reasoning_tokens": {
      "n": 8,
      "mean_diff": 9.62,
      "med_diff": 6413.5,
      "ci95": [
        -9531.25,
        8127
      ]
    },
    "content_tokens": {
      "n": 8,
      "mean_diff": 1627.25,
      "med_diff": 1015.5,
      "ci95": [
        -1746.38,
        4866.75
      ]
    },
    "ttft_s": {
      "n": 8,
      "mean_diff": -2.56,
      "med_diff": -0.42,
      "ci95": [
        -6.24,
        0.17
      ]
    },
    "wall_s": {
      "n": 8,
      "mean_diff": 126.83,
      "med_diff": 134.07,
      "ci95": [
        -45.44,
        292.15
      ]
    }
  }
}
```

## S2: Production-Aligned ~200K Prompt + 5 Tools (low / medium / high)
```json
[
  {
    "arm": "P200_high",
    "ok": 8,
    "total": 8,
    "finish_counts": {
      "stop": 7,
      "length": 1
    },
    "valid_delivery": 7,
    "has_code_block": 8,
    "tool_call_reqs": 0,
    "dsml_in_content_reqs": 0,
    "loop_r": 0,
    "loop_r_periods": [],
    "loop_c": 0,
    "engine_loop": 0,
    "prompt_p50": 210454,
    "cache_hit_min": 0.0,
    "cache_hit_med": 0.0,
    "reas_p50": 8109,
    "reas_p90": 15317,
    "cont_p50": 6262,
    "cont_p90": 7524,
    "comp_p50": 14197,
    "ttft_p50": 121.585,
    "ttft_p90": 213.819,
    "wall_p50": 485.26,
    "wall_sum": 4513.6,
    "mem_min_gib": 3.979
  },
  {
    "arm": "P200_low",
    "ok": 8,
    "total": 8,
    "finish_counts": {
      "stop": 8
    },
    "valid_delivery": 8,
    "has_code_block": 8,
    "tool_call_reqs": 0,
    "dsml_in_content_reqs": 0,
    "loop_r": 0,
    "loop_r_periods": [],
    "loop_c": 0,
    "engine_loop": 0,
    "prompt_p50": 210454,
    "cache_hit_min": 0.0,
    "cache_hit_med": 0.0,
    "reas_p50": 7417,
    "reas_p90": 9922,
    "cont_p50": 6036,
    "cont_p90": 7019,
    "comp_p50": 13737,
    "ttft_p50": 117.195,
    "ttft_p90": 125.006,
    "wall_p50": 414.0,
    "wall_sum": 3910.6,
    "mem_min_gib": 3.687
  },
  {
    "arm": "P200_med",
    "ok": 8,
    "total": 8,
    "finish_counts": {
      "stop": 8
    },
    "valid_delivery": 8,
    "has_code_block": 8,
    "tool_call_reqs": 0,
    "dsml_in_content_reqs": 0,
    "loop_r": 0,
    "loop_r_periods": [],
    "loop_c": 0,
    "engine_loop": 0,
    "prompt_p50": 210454,
    "cache_hit_min": 0.9898,
    "cache_hit_med": 0.9926,
    "reas_p50": 6604,
    "reas_p90": 13599,
    "cont_p50": 6342,
    "cont_p90": 9221,
    "comp_p50": 15630,
    "ttft_p50": 1.395,
    "ttft_p90": 3.209,
    "wall_p50": 495.79,
    "wall_sum": 3876.9,
    "mem_min_gib": 3.787
  }
]
```

## S3b: Loop Capture on conv_idx=11 & Raw Repetition Verification
```json
[
  {
    "arm": "E_max_rep",
    "ok": 4,
    "total": 4,
    "finish_counts": {
      "stop": 1,
      "length": 3
    },
    "valid_delivery": 1,
    "has_code_block": 1,
    "tool_call_reqs": 0,
    "dsml_in_content_reqs": 0,
    "loop_r": 1,
    "loop_r_periods": [
      433
    ],
    "loop_c": 0,
    "engine_loop": 0,
    "prompt_p50": 83890,
    "cache_hit_min": 0.9765,
    "cache_hit_med": 0.9765,
    "reas_p50": 32768,
    "reas_p90": 32768,
    "cont_p50": 0,
    "cont_p90": 0,
    "comp_p50": 32768,
    "ttft_p50": 1.283,
    "ttft_p90": 1.284,
    "wall_p50": 290.81,
    "wall_sum": 921.1,
    "mem_min_gib": null
  },
  {
    "arm": "EB16_rep",
    "ok": 4,
    "total": 4,
    "finish_counts": {
      "length": 1,
      "tool_calls": 3
    },
    "valid_delivery": 0,
    "has_code_block": 1,
    "tool_call_reqs": 3,
    "dsml_in_content_reqs": 0,
    "loop_r": 1,
    "loop_r_periods": [
      212
    ],
    "loop_c": 0,
    "engine_loop": 0,
    "prompt_p50": 83890,
    "cache_hit_min": 0.9765,
    "cache_hit_med": 0.9765,
    "reas_p50": 16385,
    "reas_p90": 16385,
    "cont_p50": 76,
    "cont_p90": 76,
    "comp_p50": 16461,
    "ttft_p50": 1.278,
    "ttft_p90": 1.35,
    "wall_p50": 152.75,
    "wall_sum": 763.3,
    "mem_min_gib": null
  }
]
```

### Raw Loop Matches (checking unit length, repeat count, and est tokens vs PR#138 min_repeat=1024 tokens)
```json
[
  {
    "suite": "s1",
    "conv_idx": 1,
    "arm": "A_base",
    "seed": 10016,
    "r_len": 138311,
    "c_len": 0,
    "matched": true,
    "unit_len_chars": 80,
    "repeats_matched": 200,
    "total_repeat_chars": 16000,
    "est_repeat_tokens": 4211,
    "unit_preview": "\" counter/eviction. I'll write Python for the coordinator, and Zig for the atomic\""
  },
  {
    "suite": "s1",
    "conv_idx": 4,
    "arm": "K0_warm",
    "seed": 10065,
    "r_len": 25604,
    "c_len": 6683,
    "matched": true,
    "unit_len_chars": 28,
    "repeats_matched": 33,
    "total_repeat_chars": 924,
    "est_repeat_tokens": 243,
    "unit_preview": "\".\\n\\nLet me write.\\n\\nI'll write\""
  },
  {
    "suite": "s3b",
    "conv_idx": 11,
    "arm": "E_max_rep",
    "seed": 8178,
    "r_len": 6998,
    "c_len": 3855,
    "matched": false
  },
  {
    "suite": "s3b",
    "conv_idx": 11,
    "arm": "EB16_rep",
    "seed": 8179,
    "r_len": 60718,
    "c_len": 62437,
    "matched": false
  },
  {
    "suite": "s3b",
    "conv_idx": 11,
    "arm": "E_max_rep",
    "seed": 15008,
    "r_len": 121128,
    "c_len": 0,
    "matched": true,
    "unit_len_chars": 433,
    "repeats_matched": 36,
    "total_repeat_chars": 15588,
    "est_repeat_tokens": 4102,
    "unit_preview": "'\\nWait, the refactor is to decouple state tracking from request scheduling. So:\\n- State tracking: metrics, cache, barrier slot\\n- Request scheduling: coordinator, retry\\n\\nRefactored i'"
  },
  {
    "suite": "s3b",
    "conv_idx": 11,
    "arm": "EB16_rep",
    "seed": 15025,
    "r_len": 68603,
    "c_len": 0,
    "matched": true,
    "unit_len_chars": 212,
    "repeats_matched": 75,
    "total_repeat_chars": 15900,
    "est_repeat_tokens": 4184,
    "unit_preview": "'er: cache must not evict to disk; eviction must invalidate. Actually \"stale RAM entry shadows disk\" means RAM entry is stale and shadows disk. Fix: cache must check disk on miss, o'"
  }
]
```
