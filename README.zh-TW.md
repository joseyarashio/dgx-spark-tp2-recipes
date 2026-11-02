# DeepSeek V4.1 Flash 1017 · 雙節點 DGX Spark TP=2 生產配方與基準追蹤庫 (`dgx-spark-tp2-recipes`)

<div align="center">

[![語言：繁體中文](https://img.shields.io/badge/%E8%AA%9E%E8%A8%80-%E7%B9%81%E9%AB%94%E4%B8%AD%E6%96%87-059669?style=for-the-badge)](README.zh-TW.md)
[![Language: English](https://img.shields.io/badge/Language-English-2563eb?style=for-the-badge)](README.md)
[![Engine: TensorFold Native Zig](https://img.shields.io/badge/Engine-TensorFold_Native_Zig-0891b2?style=for-the-badge)](https://github.com/bertholomus/TensorFold)
[![Weights: Plus-Ten 2.9bpw](https://img.shields.io/badge/Weights-Plus--Ten_2.9bpw_6--bit_MTP-d97706?style=for-the-badge)](https://huggingface.co/Plus-Ten/DeepSeek-V4.1-Flash-1017-TensorFold-EXL3-2.9bpw)
[![PDF Report](https://img.shields.io/badge/PDF-4%E9%A0%81%E5%AE%8C%E6%95%B4%E5%AF%A6%E6%B8%AC%E5%A0%B1%E5%91%8A-dc2626?style=for-the-badge)](reports/DGX_Spark_TP2_Comprehensive_Benchmark_Report_20261027.pdf)

</div>

![DeepSeek-V4.1-Flash-1017 on Dual NVIDIA DGX Spark TP2 with TensorFold Native Zig](assets/hero.png)

> **🌍 中英雙語導覽 / Bilingual Documentation**：
> - **繁體中文版**（本頁：`README.zh-TW.md`）
> - **[English Edition (`README.md`)](README.md)**

---

## 專案概述

本儲存庫為 **雙節點 NVIDIA DGX Spark（GB10，2× 128 GB Unified Memory）** 透過 **ConnectX-7 200G RoCEv2 雙軌直連（185 Gbps）** 部署 **DeepSeek-V4.1-Flash-1017（763B MoE，1M Context）** 的完整生產級配方、引擎修補（`patches/`）、啟動與切換腳本（`scripts/`）、Port 8889 優先權與階梯式 429 排程網關（`proxy/`）以及六階段 A/B 實測報告（`reports/`、`benchmarks/results/`）。

我們的生產主力配置（**`v2b2-production-champion`**）結合了五大核心工程突破：
1. **TensorFold Native Zig 原生引擎（`fbbc9713` + 記憶體與排程修補）**：針對 Grace Neoverse-V2 原生 CPU（`ReleaseFast`）編譯，啟用 `TF_DS_PROMPT_ALIAS=1`（省 1.63 GiB 預填暫存）、`TF_FILL_CUT_IN=4096`（長預填下短請求 **0.94 秒**插隊）與 **Vision Cache Tower Skip（多輪看圖跳過已快取圖片重算，TTFT 僅 0.73 秒，提前免疫社群 Issue #90 / PR #93）**。
2. **Plus-Ten 2.9bpw 512K 序列校準骨幹 + 6-bit LM Head & 6-bit MTP 草稿頭**：透過 `scripts/apply_plusten_backbone.py` 直接在預切分之 `rank0of2` / `rank1of2` 二進位快取上植入 4,944 個高精度骨幹與草稿張量。
3. **43 層官方 FP32 路由偏置修復（`zz-gate-bias-f32-1017.safetensors`）**：徹底消除社群量化將 40 層 MoE + 3 層 MTP 的路由偏置截斷為 FP16 導致 **95.1% 相鄰專家平手與排序反轉** 的物理缺陷，使日常 `temp=0.30` 代碼解碼自 `74.0` 暴增至 **`90.2 tok/s (+21.4%)`**，確定性 `temp=0.00` 代碼達 **`95.5 tok/s`**（MTP 草稿接受率達 **80.3%**）。
4. **Serving 層 Agent 工具對話完整性修補（`Patch 0027` & `Patch 0028`）**：
   - `0027-tool-call-prose.patch`：修復非串流 Tool-Call 丟失思考規劃文字（`content: null`）以及串流多出 `\n\n` 導致下一輪 Prompt Cache 前綴錯位脫靶的重大問題。
   - `0028-plain-request-text.patch`：在渲染模板前以 `U+FDD0` 遮罩請求與工具結果中的 `<｜User｜>`、`</think>`、`<｜DSML｜` 字樣，杜絕日誌或程式碼文字被誤編碼為控制 Token。
5. **Port 8889 優先權排程與階梯式秒退 429 網關（`proxy/proxy.py`）**：
   - 支援 `X-Priority` 優先權佇列（`0: 前景互動`、`1: 一般`、`2: 背景批次`）與背景槽位上限（`background_max_slots = 3`），強制保留第 4 槽給主互動 Agent（3 路背景滿載下前景 **`1.40s`** 完成交付）。
   - 嚴格將 Slot 鎖定至 SSE 串流（`aiter_raw()`）完整結束，並提供 `[20s, 15s, 10s, 5s]` 階梯超時與防驚群延展，超額突發 **`1.2 ms`** 秒退 HTTP 429 觸發雲端備援。

---

## 系統拓撲與優先權排程架構圖

![Dual NVIDIA DGX Spark TP=2 System Architecture and Priority Scheduling Topology](assets/architecture.png)

---

## 六階段 A/B 實測演進與 77 小時生產儀表板

![DGX Spark TP=2 6-Stage Evolution and 77-Hour Production Telemetry Dashboard](assets/benchmark-dashboard.png)

所有階段均在同一組雙 DGX Spark 硬體上，以 **30 題五維度客觀題庫**（`benchmarks/run_full_eval.py`：數學推理、MMLU-Pro 硬核計算、Python 演算法單元測試 `assert` 實際執行、IFEval 嚴格格式驗證、Agent 工具呼叫與多輪看圖快取命中）加上 **C1/C2/C4 併發擴展** 與 **C10/C8 階梯 429 壓力測試** 實機驗證：

| 方案階段 / Git Tag | 30 題標準題庫 | `temp=0.0` Code (MTP 接受率) | `temp=0.3` Code (MTP 接受率) | 中文長文 / JSON (`temp=0.3`) | C1 / C2 / C4 併發吞吐 | 32K 插隊 TTFT | 看圖第 2 輪快取 TTFT | 可用記憶體 (Node 1 / Node 2) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **`v0-baseline-1012`**<br>*(10/12 Zig + LibertAIDAI 2.9b)* | — | 90.9 tok/s<br>*(74.5%)* | 75.9 tok/s<br>*(67.6%)* | 65.7 / 112.1 | 75.6 / 86.0 / 112.2 | 26.35 s | 2.21 s<br>*(cached=0)* | 4.67G / 5.34G |
| **`v1-step1-zig-engine`**<br>*(10/25 Zig + Alias + 插隊 + 看圖快取)* | **28/30**<br>*(93.3%)* | 88.3 tok/s<br>*(74.5%)* | 74.0 tok/s<br>*(67.6%)* | 64.2 / 109.8 | 75.6 / 86.0 / 112.2 | **0.94 s**<br>*(快 28 倍)* | **0.76 s**<br>*(cached=10K)* | 7.70G / 10.37G |
| **`v2b1-f32-gate-bias`**<br>*(+ 官方 43 層 FP32 路由偏置)* | **28/30**<br>*(93.3%)* | 85.8 tok/s<br>*(71.7%)* | **90.2 tok/s**<br>*(79.9%, +21.4%)* | **67.3** / 107.8 | 74.9 / 86.7 / 115.2 | 1.13 s | **0.72 s** | 8.55G / 11.07G |
| **`v2b2-production-champion`** ⭐<br>*(Plus-Ten 6-bit MTP + P1 0027/0028 + P2 網關)* | **28/30**<br>*(93.3%)* | **95.5 tok/s**<br>*(80.3%, 3.76 TPR)* | 81.1 tok/s<br>*(74.1%)* | 62.2 / 107.9 | 77.9 / **90.2** / **116.3** | **1.00 s** | **0.73 s** | **8.04G / 11.00G** |
| **`v2a-ooa-hybrid-2.7bpw`**<br>*(OOA K2..K5 敏感度混合 MoE)* | 27/30<br>*(90.0%)* | 91.3 tok/s<br>*(77.7%)* | 75.2 tok/s<br>*(66.7%)* | 62.9 / **108.3** | **82.2** / 86.4 / 115.3 | 1.00 s | 0.74 s | 9.85G / **12.99G** |
| **`v2c-ultimate-fusion`**<br>*(Plus-Ten 6-bit 骨幹 + OOA 專家)* | 27/30<br>*(90.0%)* | 84.1 tok/s<br>*(75.5%)* | 83.8 tok/s<br>*(74.2%)* | 66.9 / 106.2 | 82.1 / 88.5 / 116.2 | **0.95 s** | **0.73 s** | **10.35G** / 12.90G |

📄 **完整 4 頁正式 PDF 實測報告**：[`reports/DGX_Spark_TP2_Comprehensive_Benchmark_Report_20261027.pdf`](reports/DGX_Spark_TP2_Comprehensive_Benchmark_Report_20261027.pdf)  
📊 **各階段原始 JSON 測試數據**：[`benchmarks/results/`](benchmarks/results/)

---

## 77 小時連續生產實戰統計（1,933 筆真實 Agent 請求）

自 2026/10/28 16:47 上線 `v2b2-production-champion` 至 2026/10/31，雙節點集群連續運行 **77 小時 07 分鐘** 的真實生產統計：

- **服務穩定度**：連續 77+ 小時 **0 崩潰、0 OOM、0 RDMA 斷線**；待機溫度 **42°C**、待機功耗僅 **9.5W ~ 10.1W**。
- **累計完成請求**：**1,933 筆對話生成**（HTTP 200 OK 共 `1,996 次`）。
- **累計處理輸入 Prompt**：**122,543,857 tokens（1.225 億 tokens）**
  - **累計命中 Prompt Cache**：**99,323,904 tokens（9,932 萬 tokens，實質節省 81.1% 的預填運算！）**
  - **每筆輸入長度**：平均 `63,396 tokens` · 中位數 `37,146 tokens` · P90 `166,700` · P95 `195,954` · 最大 **`265,449 tokens`**。
- **累計產出 Completion Tokens**：**739,772 tokens**（平均 `382.7` · 中位數 `172.0` · 最大 `12,565 tokens`）。
- **MTP 投機草稿全週期表現**：累計命中 `516,222 / 699,055`（**全週期接受率 73.85%**，單筆中位數 **76.5%**，平均每輪產出 **3.31 tokens**）。
- **首字延遲（TTFT）**：互動短請求中位數 **`0.196 秒`** · 全場景中位數 **`0.380 秒`** · P90 **`0.804 秒`** · P95 **`0.845 秒`**。

---

## 維運與一鍵切換指令指南

```bash
# 1. 啟動日常最佳主力配置 (Stage 2B-2 Plus-Ten + P1/P2 Patches)
/home/joseyarashio/start-dsv41.sh

# 2. 在「極致智商/速度 (Stage 2B-2)」與「極致省記憶體 (Stage 2C OOA 混合專家)」間秒級切換
python3 /home/joseyarashio/dgx-spark-tp2-recipes/scripts/switch_to_ooa_hybrid.py deactivate  # 切回 Stage 2B-2 (預設主力)
python3 /home/joseyarashio/dgx-spark-tp2-recipes/scripts/switch_to_ooa_hybrid.py activate    # 切至 Stage 2C (每節點多省 1.84 GiB)

# 3. 檢查 Port 8889 優先權排程網關與 Port 8888 引擎即時狀態
curl -s http://127.0.0.1:8889/proxy/status | python3 -m json.tool
curl -s http://127.0.0.1:8888/health | python3 -m json.tool

# 4. 執行 30 題五維度題庫 + C1/C2/C4 併發 + Port 8889 階梯 429 完整實測
python3 /home/joseyarashio/dgx-spark-tp2-recipes/benchmarks/run_full_eval.py verify_run
```

---

## 致謝與上游來源 (Credits)

- **[BertholomusAI / TensorFold](https://github.com/bertholomus/TensorFold)**：Native Zig TP=2 推論引擎、AOT CUDA 核心、DSpark 投機解碼與 1017 Rank-Cache 架構。
- **[Plus-Ten](https://huggingface.co/Plus-Ten/DeepSeek-V4.1-Flash-1017-TensorFold-EXL3-2.9bpw)**：512K 序列校準之 EXL3 2.9bpw 骨幹、6-bit LM Head/MTP 與官方 FP32 路由偏置驗證。
- **[Object-Oriented Architects (OOA)](https://huggingface.co/object-oriented-architects/DeepSeek-V4.1-Flash-1017-EXL3-2.7bpw-TensorFold)**：K2..K5 敏感度非均勻 MoE 專家量化。
- **[LibertAIDAI](https://huggingface.co/LibertAIDAI/DeepSeek-V4.1-Flash-1017-EXL3-2.9bpw)** 與 **[DeepSeek](https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash-1017)**：基礎 1017 EXL3 權重、官方原始權重與 Engram 查找表。
- **[MiaAI-Lab](https://github.com/MiaAI-Lab/DeepSeek-v4.1-Flash-1017-2x-DGX-Sparks)** 與 **[@Coinupbtc](https://github.com/Coinupbtc)**：上游修補 `0027-tool-call-prose` 與 `0028-plain-request-text`。
