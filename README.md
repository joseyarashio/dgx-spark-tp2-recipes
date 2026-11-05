# DeepSeek V4.1 Flash 1017 · Dual DGX Spark TP=2 (TensorFold Native Zig)

<div align="center">

[![Language: English](https://img.shields.io/badge/Language-English-2563eb?style=for-the-badge)](#english-edition)
[![語言：繁體中文](https://img.shields.io/badge/%E8%AA%9E%E8%A8%80-%E7%B9%81%E9%AB%94%E4%B8%AD%E6%96%87-059669?style=for-the-badge)](README.zh-TW.md)
[![Engine: TensorFold Native Zig](https://img.shields.io/badge/Engine-TensorFold_Native_Zig-0891b2?style=for-the-badge)](https://github.com/bertholomus/TensorFold)
[![Weights: Plus-Ten 2.9bpw](https://img.shields.io/badge/Weights-Plus--Ten_2.9bpw_6--bit_MTP-d97706?style=for-the-badge)](https://huggingface.co/Plus-Ten/DeepSeek-V4.1-Flash-1017-TensorFold-EXL3-2.9bpw)
[![PDF Report](https://img.shields.io/badge/PDF-4--Page_Benchmark_Report-dc2626?style=for-the-badge)](reports/DGX_Spark_TP2_Comprehensive_Benchmark_Report_20261027.pdf)

</div>

![DeepSeek-V4.1-Flash-1017 on Dual NVIDIA DGX Spark TP2 with TensorFold Native Zig](assets/hero.png)

> **🌍 Bilingual Documentation / 中英雙語文件導覽**：
> - **[English Edition](#english-edition)** (Below)
> - **[繁體中文完整版 (Traditional Chinese Edition)](README.zh-TW.md)** (Or jump directly to [繁體中文章節](#繁體中文完整版))

---

<a id="english-edition"></a>

## English Edition

A production-verified deployment recipe for **DeepSeek-V4.1-Flash-1017 (763B MoE, 1M Context)** across **two NVIDIA DGX Spark (GB10, 2× 128 GB Unified Memory)** systems linked via **Twin ConnectX-7 200G RoCEv2 (185 Gbps)**.

This repository tracks our end-to-end evolution from the initial October 12 baseline (`v0-baseline-1012`) to the **Production Champion (`v2b2-production-champion`)** combining:
1. **TensorFold Native Zig Engine (`fbbc9713` + Custom Serving & Memory Patches)** compiled natively for Grace Neoverse-V2 (`ReleaseFast`) with AOT CUDA fatbins.
2. **Plus-Ten 2.9bpw Sequentially-Calibrated Backbone + 6-bit LM Head & 6-bit MTP Draft Layers** grafted onto pre-sliced TP=2 rank caches.
3. **Official 43-Layer FP32 Router Gate Bias Restoration (`zz-gate-bias-f32-1017.safetensors`)**, eliminating the 95.1% adjacent-expert tie/inversion rate caused by community FP16 truncation.
4. **Serving Correctness Patches (`0027` & `0028`)**, preserving pre-tool-call prose, fixing streaming `\n\n` prefix cache drift, and masking control-token spellings (`<｜User｜>`, `</think>`) in tool outputs via `U+FDD0`.
5. **Port 8889 Fast-Fail Priority Proxy (`spark-fastfail-proxy.service`)**, providing priority-aware slot scheduling (`Prio 0` interactive preemption, `3/4` background slot ceiling), SSE stream-close slot locking, and anti-herd tiered 429 fast-fail (`[20s, 15s, 10s, 5s]`) for instant cloud fallback.

---

### System Architecture & Priority Scheduling Topology

![Dual NVIDIA DGX Spark TP=2 System Architecture and Priority Scheduling Topology](assets/architecture.png)

---

### Measured Results & 6-Stage Evolution

![DGX Spark TP=2 6-Stage Evolution and 77-Hour Production Telemetry Dashboard](assets/benchmark-dashboard.png)

All stages were evaluated on the exact same dual DGX Spark hardware using a **30-item, 5-domain objective evaluation harness** (`benchmarks/run_full_eval.py`: Competition Math, MMLU-Pro Hard Calculation, Executed Python Algorithms with `assert` verification, Strict IFEval Formatting, and Multi-Turn Vision/Tool Calling) plus **C1/C2/C4 Concurrency Scaling** and **C10/C8 Tiered 429 Stress Tests**.

| Stage / Git Tag | 30-Item Eval | `temp=0.0` Code (MTP Accept) | `temp=0.3` Code (MTP Accept) | Prose / JSON (`temp=0.3`) | C1 / C2 / C4 Aggregate | 32K Cut-In TTFT | Vision Turn-2 Cache TTFT | Free RAM (Node 1 / Node 2) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **`v0-baseline-1012`**<br>*(10/12 Zig + LibertAIDAI 2.9b)* | — | 90.9 tok/s<br>*(74.5%)* | 75.9 tok/s<br>*(67.6%)* | 65.7 / 112.1 | 75.6 / 86.0 / 112.2 | 26.35 s | 2.21 s<br>*(cached=0)* | 4.67G / 5.34G |
| **`v1-step1-zig-engine`**<br>*(10/25 Zig + Alias + Cut-In + Vision Skip)* | **28/30**<br>*(93.3%)* | 88.3 tok/s<br>*(74.5%)* | 74.0 tok/s<br>*(67.6%)* | 64.2 / 109.8 | 75.6 / 86.0 / 112.2 | **0.94 s**<br>*(28× faster)* | **0.76 s**<br>*(cached=10K)* | 7.70G / 10.37G |
| **`v2b1-f32-gate-bias`**<br>*(+ Official 43-Layer FP32 Router Bias)* | **28/30**<br>*(93.3%)* | 85.8 tok/s<br>*(71.7%)* | **90.2 tok/s**<br>*(79.9%, +21.4%)* | **67.3** / 107.8 | 74.9 / 86.7 / 115.2 | 1.13 s | **0.72 s** | 8.55G / 11.07G |
| **`v2b2-production-champion`** ⭐<br>*(Plus-Ten 6-bit MTP + P1/P2/P4e Full Hardened)* | **28/30**<br>*(93.3%)* | **95.5 tok/s**<br>*(80.3%, 3.76 TPR)* | 81.1 tok/s<br>*(74.1%)* | 62.2 / 107.9 | 77.9 / **90.2** / **116.3** | **0.94 s**<br>*(Tail Cut-In 1.55s)* | **0.73 s** | **8.04G / 11.00G** |
| **`v2b2-p4e-64row-extended`**<br>*(+ 64-Row Cubins & 32-Stream Support)* | **28/30**<br>*(93.3%)* | 93.0 tok/s<br>*(80.3%)* | 80.1 tok/s<br>*(74.1%)* | 60.7 / 106.2 | 76.8 / 87.7 / 113.3 | 1.21 s | **0.73 s** | 8.04G / 11.00G |
| **`v2a-ooa-hybrid-2.7bpw`**<br>*(OOA K2..K5 Sensitivity MoE)* | 27/30<br>*(90.0%)* | 91.3 tok/s<br>*(77.7%)* | 75.2 tok/s<br>*(66.7%)* | 62.9 / **108.3** | **82.2** / 86.4 / 115.3 | 1.00 s | 0.74 s | 9.85G / **12.99G** |
| **`v2c-ultimate-fusion`**<br>*(Plus-Ten 6-bit Backbone + OOA MoE)* | 27/30<br>*(90.0%)* | 84.1 tok/s<br>*(75.5%)* | 83.8 tok/s<br>*(74.2%)* | 66.9 / 106.2 | 82.1 / 88.5 / 116.2 | **0.95 s** | **0.73 s** | **10.35G** / 12.90G |

📄 **Full 4-Page Benchmark Report (PDF)**: [`reports/DGX_Spark_TP2_Comprehensive_Benchmark_Report_20261027.pdf`](reports/DGX_Spark_TP2_Comprehensive_Benchmark_Report_20261027.pdf)  
📊 **Raw JSON Telemetry**: [`benchmarks/results/`](benchmarks/results/)

---

### 77-Hour Continuous Production Telemetry (1,933 Real Agent Requests)

Following the deployment of `v2b2-production-champion` (October 28 – October 31, 2026), we recorded **77 hours of uninterrupted multi-agent production traffic** across both DGX Spark nodes:

- **Continuous Uptime**: **77 hours 07 minutes** (`0` crashes, `0` OOM events, `0` RDMA/NCCL drops).
- **Completed Chat Completions**: **1,933 requests** (`1,996` total HTTP 200 responses).
- **Total Prompt Tokens Processed**: **122,543,857 tokens (122.54M)**
  - **Prompt Cache Tokens Hit**: **99,323,904 tokens (99.32M — 81.1% of all input tokens skipped prefill!)**
  - **Prompt Length Distribution**: Mean `63,396` · Median `37,146` · P90 `166,700` · P95 `195,954` · Max `265,449 tokens`.
- **Total Completion Tokens Generated**: **739,772 tokens** (Mean `382.7` · Median `172.0` · P95 `1,170.8` · Max `12,565 tokens`).
- **Lifetime DSpark Speculative Decoding Efficiency**:
  - **Draft Tokens Accepted**: **516,222 / 699,055 (73.85% lifetime acceptance rate; per-request median 76.5%)**
  - **Mean Tokens Per Verification Round (TPR)**: **3.31 tokens/round**.
- **End-to-End Time To First Token (TTFT)**:
  - **Interactive Short Prompts (40–120 tokens)**: **0.196 s** median
  - **Overall Production Traffic**: **0.380 s** median (P50) · **0.580 s** mean · **0.804 s** P90 · **0.845 s** P95
  - **Foreground Interactive Preemption (`X-Priority: high`) under 3 Active Background Streams**: **1.40 s** total completion.

---

### Key Engineering Breakthroughs

#### 1. Why Restoring Official FP32 Router Bias Boosts `temp=0.30` Code Decode by +21.4%
Community EXL3 quantizations (`LibertAIDAI` and derivatives) truncated the 40 MoE layers and 3 MTP layers' `ffn.gate.bias` (`e_score_correction_bias`) from `F32` to `F16`. Because these bias values sit in the `[+9.8, +20.0]` range where FP16 ULP step size is `0.0078 ~ 0.0156`—larger than the actual score gap between adjacent experts (`0.001 ~ 0.008`)—**14,604 out of 15,360 adjacent expert pairs (95.1%) suffered ties or rank inversions**. During speculative decoding, the main model and MTP draft heads frequently diverged on borderline experts. Grafting the official FP32 bias tensors (`zz-gate-bias-f32-1017.safetensors`) via `scripts/extract_f32_gate_bias.py` raised MTP acceptance from `67.6%` to **`79.9%`** (`2.76 → 3.52 tokens/round`) and `temp=0.30` code decode from `74.0` to **`90.2 tok/s`**.

#### 2. Vision Cache Tower Skip (Pre-empting Upstream Issue #90 / PR #93)
In stock `fbbc9713`, resuming a multi-turn conversation containing images from the prompt cache (`kept` state) still re-ran the Vision Tower (`vit`) over every historical image prior to the resume offset (`resume_at`), adding **+5.5 seconds** to every follow-up turn. Our Step 1 patch (`patches/step1-custom-patches-on-fbbc9713.patch` in `zig/src/families/dsv41/lanes.zig`) skips any image span wholly within `resume_at`:
```zig
const resume_at: usize = if (kept) |sn| sn.at else 0;
...
if (@as(usize, img.at) + img.tokens <= resume_at) continue;
```
This cuts Turn-2 multi-turn vision TTFT from `2.21s ~ 7.28s` down to **`0.73s`**.

#### 3. Serving Layer Integrity for Multi-Turn Agents (`Patch 0027` & `Patch 0028`)
- **`patches/0027-tool-call-prose.patch`**: Fixes two critical agent bugs in DeepSeek-V4.1 tool calling: (1) non-streaming replies with tool calls previously returned `"content": null`, discarding the model's reasoning/plan prose before the tool call; (2) streaming replies emitted the two `\n\n` framing newlines before `<｜DSML｜ calls>` as content, causing the next turn's history to become `text\n\n\n\n<｜DSML｜ calls>` and breaking KV prefix cache matching right before the calls.
- **`patches/0028-plain-request-text.patch`**: Inserts a Unicode noncharacter mark (`U+FDD0`) inside any added-token spelling (`<｜User｜>`, `</think>`, `<｜DSML｜`) found in user/tool messages before template rendering, and strips it prior to BPE pre-tokenization. Tool outputs containing raw logs or source code can never inject control tokens.

#### 4. P4 Production Hardening Suite & Vision Architecture
- **Incremental Tail Cut-In (`PR #95` / `Patch 0045`)**: Evaluates `prompt.len - resume_at <= 4096` instead of full prompt length. A multi-turn conversation with 15K~300K cached history and 1.5K new tokens now cuts in between in-flight 32K prefill pieces in **1.52s** (down from 31.7s, a **20.9× reduction**).
- **Vision Prepare Scratch Arena (`PR #112` / `Patch 0056`)**: PNG decoding, bicubic resizing, padding, and patchification now run in an isolated `ArenaAllocator` reset after each image, copying only 16-aligned final payloads into request memory. Memory drop during multi-screenshot requests fell by **68%** (0.71 GiB → 0.23 GiB), completely preventing long-agent screenshot OOM.
- **CUDA Graph LRU Capping (`Patch 0033`)**: Enforces `TF_DS_GRAPH_CAP=128` with LRU eviction to prevent device/host memory creep across long-running multi-week production uptime.
- **Anthropic Compatibility & Keepalive (`Patches 0029–0032`)**: Full `/v1/messages` compatibility (optional `budget_tokens`, lenient `clear_thinking`, mid-turn system roles) and 25s SSE `: ping` keepalive.
- **Verified Synthetic Vision Probe**: Real base64 data-URL input natively verified with `scripts/vision_probe.py` (Circle/Square shape & color 100%, 4-quadrant counting 100%, OCR token accuracy 100%).
- **64-Row Decode Window & 32-Stream Support (`v0.7.5` / `v2b2-p4e-64row-extended`)**: Grafts 16 new `_rowmm_parts` cubins (K=5120, N=384, rows 49..64) into the kit (`aot.json` entries 198 → 214) and widens the engine to `round.max_rows = 64` and `max_streams = 32`. While keeping our verified 4-slot concurrency and 1.05M pool intact (preserving 8+ GiB free RAM), this completely removes the legacy 48-row ceiling and enables batch-invariant scaling.
- **Triple-Layer Boot Self-Healing**: Automated recovery via Docker `--restart unless-stopped`, user systemd `spark-fastfail-proxy.service` (Port 8889), and `spark-dsv41-cluster.service` boot health-check watchdog.

---

### Quick Start & Operations

```bash
# 1. Start the Production Champion (Stage 2B-2 Plus-Ten + P1/P2 Patches)
/home/joseyarashio/start-dsv41.sh

# 2. Switch between Stage 2B-2 (Max Speed/IQ) and Stage 2C (+3.68 GiB Extra Free RAM)
python3 scripts/switch_to_ooa_hybrid.py deactivate   # Stage 2B-2 Plus-Ten (Default)
python3 scripts/switch_to_ooa_hybrid.py activate     # Stage 2C Ultimate Fusion (OOA Hybrid MoE)

# 3. Check Port 8889 Priority Proxy & Port 8888 Engine Telemetry
curl -s http://127.0.0.1:8889/proxy/status | python3 -m json.tool
curl -s http://127.0.0.1:8888/health | python3 -m json.tool

# 4. Run the Full 30-Item 5-Domain Benchmark & Concurrency Stress Suite
python3 benchmarks/run_full_eval.py my_run_label
```

---
---

<a id="繁體中文完整版"></a>

## 繁體中文完整版 (Traditional Chinese Edition)

> 📘 獨立繁體中文專頁：[**`README.zh-TW.md`**](README.zh-TW.md)

這是一套針對 **兩台 NVIDIA DGX Spark（GB10，2× 128 GB Unified Memory）** 透過 **ConnectX-7 200G RoCEv2 雙軌直連（185 Gbps）** 部署 **DeepSeek-V4.1-Flash-1017（763B MoE，1M Context）** 的生產級調優配方與實測追蹤庫。

本儲存庫完整記錄了從 10/12 初始基線（`v0-baseline-1012`）一路演進至目前線上 **最佳生產主力配置（`v2b2-production-champion`）** 的每一步原始碼修補、權重融合腳本與同機實測數據：

1. **TensorFold Native Zig 原生引擎升級（`fbbc9713` + 記憶體與排程修補）**：針對 Grace Neoverse-V2 原生 CPU（`ReleaseFast`）編譯，啟用 `TF_DS_PROMPT_ALIAS=1`（省 1.63 GiB 預填暫存）、`TF_FILL_CUT_IN=4096`（長預填下短請求 **0.94 秒**插隊）與 **Vision Cache Tower Skip（多輪看圖跳過已快取圖片重算，TTFT 僅 0.73 秒，提前免疫社群 Issue #90 / PR #93）**。
2. **Plus-Ten 2.9bpw 512K 序列校準骨幹 + 6-bit LM Head & 6-bit MTP 草稿頭**：透過 `scripts/apply_plusten_backbone.py` 精準切片植入 4,944 個高精度骨幹與草稿張量。
3. **43 層官方 FP32 路由偏置修復（`zz-gate-bias-f32-1017.safetensors`）**：解決社群量化將路由偏置截斷為 FP16 導致 **95.1% 相鄰專家平手與排序反轉** 的物理缺陷，使日常 `temp=0.30` 代碼速度自 `74.0` 暴增至 **`90.2 tok/s (+21.4%)`**，確定性 `temp=0.00` 代碼達 **`95.5 tok/s`**（MTP 接受率 **80.3%**）。
4. **Serving 層 Agent 對話完整性修補（`Patch 0027` & `Patch 0028`）**：
   - `0027-tool-call-prose.patch`：修復非串流 Tool-Call 丟失計畫文字（`content: null`）以及串流多出 `\n\n` 導致下一輪 Prompt Cache 前綴錯位脫靶的重大問題。
   - `0028-plain-request-text.patch`：在渲染模板前以 `U+FDD0` 遮罩請求與工具回傳中的 `<｜User｜>`、`</think>`、`<｜DSML｜` 字樣，杜絕日誌或程式碼文字被誤編碼為控制 Token。
5. **Port 8889 優先權排程與階梯式秒退 429 網關（`proxy/proxy.py`）**：
   - 支援 `X-Priority` 優先權排程（`0: 前景互動`、`1: 一般`、`2: 背景批次`）與背景槽位上限（`background_max_slots = 3`），強制保留第 4 槽給主互動 Agent（3 路背景滿載下前景 **`1.40s`** 完成交付）。
   - 嚴格將 Slot 鎖定至 SSE 串流（`aiter_raw()`）完整結束，並提供 `[20s, 15s, 10s, 5s]` 階梯超時與防驚群延展，超額突發 **`1.2 ms`** 秒退 HTTP 429 觸發雲端備援。

---

## Credits & Attribution

- **[BertholomusAI / TensorFold](https://github.com/bertholomus/TensorFold)**: Native Zig TP=2 inference runtime, AOT CUDA kernels, DSpark speculative decoding, and 1017 rank-cache architecture.
- **[Plus-Ten](https://huggingface.co/Plus-Ten/DeepSeek-V4.1-Flash-1017-TensorFold-EXL3-2.9bpw)**: Sequentially-calibrated 512K-token EXL3 2.9bpw backbone, 6-bit LM Head/MTP, and official FP32 router bias verification.
- **[Object-Oriented Architects (OOA)](https://huggingface.co/object-oriented-architects/DeepSeek-V4.1-Flash-1017-EXL3-2.7bpw-TensorFold)**: Layer-sensitivity K2..K5 hybrid MoE quantization.
- **[LibertAIDAI](https://huggingface.co/LibertAIDAI/DeepSeek-V4.1-Flash-1017-EXL3-2.9bpw)** & **[DeepSeek](https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash-1017)**: Base 1017 EXL3 pack, official checkpoint, and Engram lookup tables.
- **[MiaAI-Lab](https://github.com/MiaAI-Lab/DeepSeek-v4.1-Flash-1017-2x-DGX-Sparks)** & **[@Coinupbtc](https://github.com/Coinupbtc)**: Upstream reference patches `0027-tool-call-prose` and `0028-plain-request-text`.
