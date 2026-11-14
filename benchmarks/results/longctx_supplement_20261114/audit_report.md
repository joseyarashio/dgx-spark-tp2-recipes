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


---
## Reviewer: anthropic/claude-fable-5-2 (ok=True, finish=stop, wall=186.1s)

# P2S 補測審查報告

**總評**：budget 關閉後的 `stop` 只是表面恢復，不是有效交付；`K0_warm` 沒有可證實的優勢；S2 的 low/medium/high 比較被快取狀態混淆；PR #138 的涵蓋率取決於 `min_repeat` 的語意，目前不能當作止損依據。唯一可直接落地的行為變更是 OMP 短任務關閉 thinking。

## 1. S1：budget 關閉機制與 K0_warm

### (a) 移除 tools / `tool_choice='none'` 後是否恢復正常交付？

沒有。`finish_reason` 變回 `stop`，但內容多數是洩漏到 content 的 DSML。

| 臂 | stop | valid_delivery | DSML in content | cont_p50 |
|---|---|---|---|---|
| B8_tc_none | 8/8 | 2/8 | 6/8 | 76 |
| B8_no_tools | 8/8 | 1/8 | 7/8 | 76 |
| EB16_tc_none | 7/8 | 2/8 | 5/8 | 76 |
| EB16_no_tools | 8/8 | 4/8 | 4/8 | 76 |
| A_base（對照） | 5/8 | 5/8 | 0/8 | 2092 |

- **有效交付變差**：四臂合計有效交付 9/32、DSML 洩漏 22/32，低於 A_base 的 5/8。
- **幾乎二分**：每臂「有效交付 + DSML」約等於 8，與「觸頂即洩漏、未觸頂才正常交付」一致；仍需逐請求交叉表確認。
- **budget 確實是硬上限**：`reas_p50` 為 8193 / 16385，即 budget+1。

**對根因的修正**：「工具 + auto 導致轉向」不成立。

- **真正的觸發點是 budget 強制關閉 thinking**：模型在未想完時下一步就輸出一段約 76 token 的工具呼叫標記。
- **tools+auto 只決定呈現方式**：有 parser 時變成結構化 `tool_calls`（S3b `EB16_rep` 3/4，`cont_p50` 同為 76）；沒有時原樣漏進 content 並回報 `stop`。
- **反向佐證**：S2 掛 5 個工具但無 budget，24 筆中 0 筆 tool call、0 筆 DSML。
- **未驗證處**：Dossier 沒有 DSML 原文，「就是 `read_file`」只由 76 token 吻合推得，需 grep 原始輸出。

**budget 也沒省到資源**：

- `EB16_tc_none` 的 wall 顯著變慢：+171.7 s，CI [5.8, 321.7]。
- EB16 兩臂的 reasoning 均值差約為 0，中位差反而是 +6413.5（CI 跨 0）。
- 只有 `B8_tc_none` 顯著變快（−162.7 s，CI [−291, −23.7]），代價是交付 2/8。

**對照設計的缺口**：

- `tc_none` 與 `no_tools` 的 `prompt_p50`（84092）和快取數值完全相同，兩者很可能渲染出同一份 prompt。若如此，兩臂之間的差異（有效交付 1–4/8）就是抽樣噪音的量級。
- A_base 的 prompt 多 982 token，所以與 A_base 的配對比較同時變動了 budget 和 prompt。
- 「tools+auto+budget」只在 S3b 的單一對話上有 4 筆，不是同套件的配對對照。

### (b) `K0_warm` 是否優於 `A_base`？

沒有證據顯示更好；所有配對 CI 都跨 0。

| 指標 | K0_warm | A_base | 配對差（CI95） |
|---|---|---|---|
| TTFT p50 / p90 | 1.081 / 11.322 s | 0.989 / 10.963 s | 均值 +1.27 s [−2.72, 5.26] |
| finish=length | 2/8 | 3/8 | — |
| valid_delivery | 6/8 | 5/8 | — |
| reasoning tokens | p50 12774 | p50 8570 | −281 [−9117, 8933] |
| wall | p50 426.7 s | p50 462.7 s | +35.5 s [−75, 136] |

- **TTFT**：中位數略差，約 11 秒的尾部仍在，獨立暖快取沒有消除它。
- **尾部不像快取未命中**：兩臂 `cache_hit_min` 都是 0.9765（約 2K token 未命中）。以 S2 的冷 prefill 速率（約 1750 tok/s）估算只需約 1 秒，所以 11 秒尾部另有來源，尚未查明。
- **長度**：只差 1 筆，n=8 下不具意義。
- **待釐清**：`K0_warm` 有 1 筆 `engine_loop=1`，Dossier 未定義其語意。

## 2. S2：約 210K prompt + 5 tools

| 臂 | valid | length | reas p50 / p90 | cache_hit 中位 | TTFT p50 / p90 | mem_min |
|---|---|---|---|---|---|---|
| low | 8/8 | 0 | 7417 / 9922 | 0.0 | 117.2 / 125.0 s | 3.687 GiB |
| medium | 8/8 | 0 | 6604 / 13599 | 0.9926 | 1.4 / 3.2 s | 3.787 GiB |
| high | 7/8 | 1 | 8109 / 15317 | 0.0 | 121.6 / 213.8 s | 3.979 GiB |

- **交付**：長上下文加工具、不設 budget 時交付穩定：23/24 有效，0 loop，0 tool call 轉向。
- **effort 的影響**：只看得到尾部。reasoning 的 p90 隨 effort 遞增，中位數不單調；S2 沒有配對 CI，不能宣稱三檔有顯著差異。high 沒有顯示好處，且出現唯一一筆 `length`。
- **快取與 effort 完全混淆**：low 和 high 全程命中率 0.0，medium 全程約 0.99。TTFT 的 85 倍差距反映的是冷熱狀態，不是 effort。
- **未命中原因不明**：可能是切換 effort 使前綴失效、臂順序，或記憶體壓力造成驅逐。Dossier 無法區分，這是 S2 最大的未解項。
- **暖快取沒有換來更短的總時間**：medium 的 `wall_sum`（3877 s）與冷啟動的 low（3911 s）幾乎相同，代表它的生成階段多花約 900 秒。原因待查，可能是輸出較長或解碼吞吐較低。
- **冷啟動成本**：210K 冷 prefill 約 2 分鐘，p90 達 214 秒。
- **RAM**：三臂最低餘量為 3.69–3.98 GiB，24 筆全部成功。Dossier 沒有總 RAM、swap 或併發數據，只能說「單流序列執行未失敗」，不能證明有安全裕度。S1 和 S3 的記憶體數據全為 null。

## 3. S3a 與 S3b

### S3a：`OMP120_none` 止損方案

- **止損有效**：`length` 截斷從 5/10 降到 0/10。low 臂的 thinking 會吃光額度（`reas_p90` = 120 = `max_tokens`）。
- **更快**：`wall_sum` 從 17.3 s 降到 5.0 s，TTFT p50 從 0.425 s 降到 0.332 s。
- **品質未驗證**：兩臂 `valid_delivery` 都是 0/10，驗證器看來不適用於短任務。目前只能說「不再被截斷」，不能說「內容正確」。
- **適用範圍**：僅限已測形狀（無工具、prompt 約 50–70 token、`max_tokens=120`）。「保留 low 並調高 `max_tokens`」沒有測過。

### S3b：PR #138 對本機重複片段的涵蓋率

| 來源 | 單位長度 | 約合 token | 重複次數 | 估計重複 token |
|---|---|---|---|---|
| A_base | 80 字元 | 21 | 200 | 4211 |
| E_max_rep | 433 字元 | 114 | 36 | 4102 |
| EB16_rep | 212 字元 | 56 | 75 | 4184 |
| K0_warm | 28 字元 | 7 | 33 | 243 |

涵蓋率取決於 `min_repeat=1024 tokens` 的語意：

- **若指累計重複長度**：涵蓋 3/4。漏掉的 `K0_warm`（243 token）之後有產出 content（`c_len` 6683），不觸發反而合理。
- **若指最小重複單位長度**：涵蓋 0/4。最大單位只有約 114 token，比門檻小約 9 倍。

其他限制：

- **估計值是下限**：三筆的重複總長都約 16,000 字元，看起來是偵測視窗上限，實際 loop 可能長得多。
- **多數失控不是週期性 loop**：`E_max_rep` 有 3/4 燒完 32768 token 且 content 為 0，只有 1 筆被判為 loop；A_base 的 3 筆 `length` 也只有 1 筆。即使在最有利的語意下，PR #138 也只處理約三分之一的耗盡事件。
- **觸發後行為未測**：若 PR #138 以強制關閉 thinking 來中斷，可能重現 S1 的 DSML 轉向。
- **樣本極小**：S3b 只有單一對話、每臂 4 筆。

## 4. 最終定案建議

| 項目 | 決定 | 依據 |
|---|---|---|
| OMP 短任務（無工具、`max_tokens`≤120）強制關閉 thinking | 可落地 | 截斷 5/10→0/10，wall −71%；需補適用的驗證器 |
| Proxy 偵測 content 中的 DSML，標記為失敗或重試 | 可落地（防禦性） | 22/32 筆以 `stop` 靜默回傳壞內容 |
| Proxy 記錄 budget 觸頂（reasoning = budget+1）與記憶體 | 可落地（觀測性） | S1/S3 記憶體為 null；需逐請求交叉表 |
| 200K 級請求的首 token 逾時放寬到 214 秒以上 | 可落地 | 冷 TTFT p90 = 213.8 s |
| 200K 級維持單流，不開併發 | 可落地 | 最低餘量僅 3.69 GiB |
| 長上下文啟用 `thinking_budget`（B8/EB16） | 維持凍結 | 交付 1–4/8，低於基線 5/8；EB16 還更慢 |
| 以 `tool_choice='none'` 或移除工具作為修復 | 維持凍結 | 只改了 `finish_reason` |
| 以 `K0_warm` 取代 `A_base` | 維持凍結 | 無顯著差異，TTFT 尾部仍在 |
| 調整生產環境的 effort 預設 | 維持凍結 | 快取混淆；不建議升到 high |
| 依賴 PR #138 作為 loop 止損 | 待引擎端 | 語意未確認（3/4 或 0/4）；觸發後行為未測 |
| budget 關閉後的 DSML 轉向 | 待引擎端修復 | 根因在強制關閉後的生成行為，Proxy 只能偵測 |

**解凍前須補測**：

1. 同一批 8 個對話上做「tools+auto+budget」配對臂，並輸出逐請求的「觸頂 × DSML」交叉表。
2. S2 在同一 effort 下先暖快取再量測，分離 effort 與快取的影響。
3. 確認 PR #138 的 `min_repeat` 語意與觸發後行為。
4. 查明 85K 下約 11 秒 TTFT 尾部的來源。

---
## Reviewer: gpt-6-astra (ok=True, finish=stop, wall=93.9s)

# P2S 補測審查結論

**總結：budget 後的協定終止有所恢復，但有效交付未恢復；`K0_warm` 未證明優於 `A_base`；約 210K 的 low／medium 可作有條件配置候選，但 TTFT 比較受快取狀態混淆；`OMP120_none` 僅是成本止損，不能當成功交付方案；PR #138 對已驗證重複片段的估計門檻涵蓋率為 3/4，並非實測攔截率。**

以下嚴格區分 `ok`、`finish_reason` 與 `valid_delivery`。三者不能互相代替；各組樣本亦不足以證明生產可靠性。

## 1. S1：budget 關閉機制與 K0_warm

### 1.1 移除 tools／設定 `tool_choice='none'`：恢復的是什麼？

| 組別 | reasoning p50／p90 | stop | 有效交付 | content 含 DSML | 正式工具呼叫 |
|---|---:|---:|---:|---:|---:|
| B8_tc_none | 8193／8193 | 8/8 | 2/8 | 6/8 | 0 |
| B8_no_tools | 8193／8193 | 8/8 | 1/8 | 7/8 | 0 |
| EB16_tc_none | 16385／16385 | 7/8 | 2/8 | 5/8 | 0 |
| EB16_no_tools | 16385／16385 | 8/8 | 4/8 | 4/8 | 0 |

**裁定：不能稱為恢復「正常 stop 交付」。**

- B8 兩組與 EB16_no_tools 全部回報 `stop`，EB16_tc_none 仍有一次 `length`。
- 但有效交付只有 **12.5%–50%**，且 **50%–87.5%** 的請求在 content 中出現 DSML。
- 四組 content p50 都只有 **76 tokens**。因此，`stop` 不代表預期答案已產生，更不代表 budget 關閉流程已完成語義上的正常交接。
- reasoning p50／p90 固定在 8193 或 16385，支持存在明確的 budget 邊界現象；僅憑聚合結果，不能判定引擎內部具體狀態轉換。

### 1.2 對「掛 tools + auto 後轉向 read_file」根因的修正

補測支持的修正是：

> **不能再將問題僅歸因於 tools + auto 允許正式工具呼叫。禁止工具後，正式呼叫消失，但 DSML 仍大量出現在 content；問題未被消除，只是輸出表現改變。**

這與「budget 邊界後的輸出模式／工具格式交接存在問題」相容，但尚不足以證明具體引擎根因。

必須保留兩項證據界線：

1. Dossier **沒有提供 `read_file` 名稱、arguments 或相應原始輸出**，因此不能證明為何特別選擇 `read_file`。
2. S3b 的 EB16_rep 有 3/4 正式工具呼叫，可確認該組存在工具路徑；但不能把不同組別直接視為完整的配對因果實驗。

**實務意義：`tool_choice='none'`／移除 tools 可用於禁用工具，但不能宣稱是 budget 交付修復。**

### 1.3 K0_warm 是否優於 A_base？

| 指標 | A_base | K0_warm |
|---|---:|---:|
| cache hit 中位數 | 98.69% | 99.01% |
| TTFT p50／p90 | 0.989／10.963 秒 | 1.081／11.322 秒 |
| reasoning p50／p90 | 8570／32768 | 12774／32768 |
| content p50／p90 | 2092／6140 | 4944／10068 |
| completion p50 | 15469 | 18797 |
| wall p50 | 462.72 秒 | 426.68 秒 |
| 有效交付 | 5/8 | 6/8 |
| length | 3/8 | 2/8 |
| reasoning loop／engine_loop | 1／0 | 1／1 |

**裁定：沒有證據證明 TTFT 或長度效率較佳。**

- 暖快取後，K0_warm 的 TTFT p50、p90 仍略高。
- 配對 TTFT 平均差為 **+1.27 秒**，95% CI **[-2.72, 5.26]**；不支持穩定優勢。
- 若「長度較佳」指更短、更省 tokens：K0_warm 的 reasoning、content、completion 中位數反而更高。
- 若指答案更完整：content 確實較長、有效交付多一筆，但配對 content 差的 CI 跨零，且不能把較長直接等同較高品質。
- wall 的組別 p50 雖降低，配對平均差卻為 **+35.52 秒**、CI 跨零；不能單憑 p50 宣告加速。
- K0_warm 仍有重複及一次 `engine_loop`。

**獨立暖快取未建立 K0 的優越性，不應據此升為預設。**

## 2. S2：約 210K prompt + 5 tools

### 2.1 實測表現

| 指標 | low | medium | high |
|---|---:|---:|---:|
| 有效交付 | 8/8 | 8/8 | 7/8 |
| stop／length | 8／0 | 8／0 | 7／1 |
| cache hit min／median | 0／0 | 98.98%／99.26% | 0／0 |
| TTFT p50／p90，秒 | 117.195／125.006 | 1.395／3.209 | 121.585／213.819 |
| reasoning p50／p90 | 7417／9922 | 6604／13599 | 8109／15317 |
| content p50／p90 | 6036／7019 | 6342／9221 | 6262／7524 |
| completion p50 | 13737 | 15630 | 14197 |
| wall p50，秒 | 414.00 | 495.79 | 485.26 |
| 最低 RAM 裕度，GiB | 3.687 | 3.787 | 3.979 |

三組皆無觀測到 DSML、正式工具呼叫或 loop，且都有 8/8 code block。**但 high 仍只有 7/8 有效交付，顯示 code block 不能作為成功判準。**

### 2.2 效能與快取判讀

- **low 是目前最合理的成本／交付候選：**本批 8/8 有效、wall p50 最低，reasoning p90 亦最低。
- **medium 的低 TTFT 與高快取命中同時出現。**不能將約 1.4 秒相對約 117–122 秒的差距歸因於 reasoning effort。
- low／high 的 cache hit 最小值與中位數均為零，**不等於已證明每一筆都是零命中**。
- high 未展現有效交付優勢，且 TTFT p90、reasoning p90 更高，無充分理由升為預設。
- reasoning p50 並不依 low → medium → high 單調增加，因此不能把 effort 名稱當成固定 token budget。
- 雖然配置了 5 tools，三組都沒有實際工具呼叫；本測試**不驗證工具執行或多輪工具循環的可靠性**。

### 2.3 RAM 安全裕度

本批最低觀測裕度介於 **3.687–3.979 GiB**，且請求全部 `ok`。可確認本批執行未呈現請求失敗，但不能據此宣告容量安全：

- 沒有更高併發、其他常駐負載或更長上下文的資料。
- 沒有採樣頻率資訊，不能排除未捕捉的瞬時低點。
- high 的最低裕度略大，不足以推論 high 比 low 更省 RAM。

**應維持本次已測負載範圍，加入 RAM admission control；目前資料不足以給出可靠的數值放行門檻。**

## 3. S3a／S3b：短任務止損與重複檢驗

### 3.1 OMP120_none：成本止損有效，任務交付無效

| 指標 | OMP120_low | OMP120_none |
|---|---:|---:|
| stop／length | 5／5 | 10／0 |
| 有效交付／code block | 0／0 | 0／0 |
| reasoning p50 | 101 | 0 |
| completion p50 | 109 | 9 |
| TTFT p50 | 0.425 秒 | 0.332 秒 |
| wall p50 | 1.77 秒 | 0.50 秒 |
| wall 合計 | 17.3 秒 | 5.0 秒 |

`none` 消除了觀測到的 reasoning tokens 與 `length` 終止，wall 合計下降約 **71%**。但 **10/10 仍未有效交付**。

因此：

- 可將其定義為**降低失敗成本的止損模式**。
- 不可定義為 OMP 短任務修復或可靠完成配置。
- Proxy 必須將其無效內容標為失敗／未完成，不能因 `stop` 就回報成功。
- 本資料沒有驗證其他 token 上限或其他替代路徑，不能指定未測方案為已解決方案。

### 3.2 PR #138：應比較累計重複量，不是字元週期

以提供的 **`est_repeat_tokens`** 對照 1024-token 門檻：

| 已原文驗證片段 | 單位長度，字元 | 次數 | 累計重複字元 | 估計重複 tokens | 達門檻 |
|---|---:|---:|---:|---:|---|
| A_base，seed 10016 | 80 | 200 | 16000 | 4211 | 是 |
| K0_warm，seed 10065 | 28 | 33 | 924 | 243 | 否 |
| E_max_rep，seed 15008 | 433 | 36 | 15588 | 4102 | 是 |
| EB16_rep，seed 15025 | 212 | 75 | 15900 | 4184 | 是 |

**在「1024 tokens 指累計重複量」的比較口徑下，四段已驗證片段有三段達門檻，估計門檻涵蓋率為 75%。**

關鍵限制：

- 28／80／212／433 是**重複單位的字元長度**，不能直接拿來與 1024 tokens 比較。
- tokens 是估算值，不是 tokenizer 精算。
- 兩筆 `matched=false` 不能當作已確認重複，更不能直接判成 PR 漏抓；它們不納入上述四段的分母。
- 這是**門檻適用性分析，不是 PR #138 的實測召回率**。Dossier 未提供該 PR 套用後的攔截結果或完整判定邏輯。
- K0_warm 的短片段估計只有 243 tokens，卻有 `engine_loop=1`；無法由此把引擎既有偵測與 PR #138 機制畫上等號。

S3b 亦顯示：E_max_rep 有 **3/4 length、僅 1/4 有效交付**；EB16_rep 有 **3/4 tool_calls、0/4 有效交付**。budget 限制、工具終止與重複控制，都不能單獨保證可用答案。

## 4. 最終定案建議

### 可直接落地 Proxy／配置的項目

| 項目 | 定案 |
|---|---|
| 成功判定 | **立即分離**傳輸成功、終止原因、內容有效性；不得以 `ok`、`stop` 或 code block 單獨判成功。 |
| DSML 防護 | content 出現非預期 DSML 時隔離並標為異常；不要把正文 DSML 自動提升為可執行工具呼叫。 |
| 工具權限 | 不需工具時可移除 tools／設 `tool_choice='none'`，但明確標示這是權限控制，不是交付修復。 |
| 約 210K 預設候選 | 在本次已測任務與負載範圍，**優先 low、受控上線**；medium 保留為已驗證的暖快取配置選項，不宣稱其 effort 本身帶來 TTFT 優勢。 |
| 止損與監測 | 記錄 cache hit、TTFT、wall、RAM、reasoning／content tokens、DSML 與有效交付；保留硬性生成／時間上限。 |
| OMP120_none | 僅可作明確標示失敗的低成本止損路徑，不作正常成功服務。 |

### 維持凍結或待修復／驗證

1. **凍結將 B8／EB16 視為正常交付修復的推廣。**有效交付低、DSML 外洩仍多；需引擎端釐清 budget 邊界與輸出格式交接。
2. **不將 K0_warm 升為預設。**無穩定 TTFT／長度效率優勢，仍有重複與 `engine_loop`。
3. **不將 high 升為約 210K 的預設。**本批沒有交付收益，反而多一次 `length`。
4. **不宣告 PR #138 已解決本機 loop。**需 tokenizer 精算、實際套用 PR 重播並檢驗攔截結果；短片段覆蓋仍未獲保證。
5. **凍結未測的容量與工具流程外推。**目前不支持擴大併發、更長上下文，或宣稱完整工具往返已驗證。

**最終判詞：可以落地的是「權限、有效性驗證、成本止損與受控配置」；尚不能落地為成功保證的是「budget 修復、K0 優勢、OMP120 交付，以及 PR #138 的實際 loop 修復能力」。**