# DGX Spark TP=2 配方調整與基準實測追蹤庫 (`dgx-spark-tp2-recipes`)

本儲存庫用於追蹤雙節點 NVIDIA DGX Spark (GB10, 2x 128GB Unified Memory, ConnectX-7 200G RoCEv2) 的模型推論配方調整、引擎修補 (`patches/`)、啟動腳本 (`scripts/`)、Port 8889 優先權與階梯式排隊 429 網關 (`proxy/`)、正式評估報告 (`reports/`) 以及每次變更前後的同機實測數據 (`benchmarks/results/`)。

## 硬體與固定約束
- **節點拓撲**：
  - Node 1 (Head): `spark-9e5c` (`192.168.10.148` / Tailscale `100.70.199.89` / CX-7 `10.100.184.2`, `10.100.185.2`)
  - Node 2 (Worker): `spark-7579` (`192.168.10.149` / Tailscale `100.121.64.103` / CX-7 `10.100.184.1`, `10.100.185.1`)
- **Port 8889 優先權排程與階梯式 429 網關 (`spark-fastfail-proxy.service`)**：
  - 固定監聽 `:8889` 轉發 `:8888`
  - `concurrency_limit = 4`（Zig TP=2） / `2`（sudoingX vLLM）
  - `background_max_slots = 3`（背景任務最多佔 3 槽，強制保留 1 槽給前景互動 `X-Priority: high`）
  - `queue_buffer = 4`、`tiered_timeouts = [20.0, 15.0, 10.0, 5.0]`、`extension_seconds = 5.0`

---

## 當前生產主力配置 (Production Champion: `v2b2-p2-priority-proxy`)

- **引擎核心**：`TensorFold-dsv41-zig` (`fbbc9713` 10/25 + `TF_DS_PROMPT_ALIAS=1` + `TF_FILL_CUT_IN=4096` + Vision Cache Tower Skip + **Patch 0027 Tool-Call Prose 保留與換行對齊** + **Patch 0028 Plain Request Text 特殊控制 Token 遮罩**)
- **模型權重**：`Plus-Ten/DeepSeek-V4.1-Flash-1017-TensorFold-EXL3-2.9bpw` (6-bit Head + 6-bit MTP + 512K 序列量化校準 + **43 層官方 FP32 路由偏置 `zz-gate-bias-f32-1017.safetensors`**)
- **專屬雙節點快取**：`/home/joseyarashio/.cache/dsv41-plusten-rank-cache/tf-ds-rank` (`rank0of2-07aebb3f372c40cfc047.bin` / `rank1of2-4f1433d690cae303f7ce.bin`)
- **77 小時連續生產實戰統計 (1,933 筆真實請求)**：
  - **Uptime**：連續運行 77+ 小時 0 崩潰、0 OOM
  - **累計輸入 Prompt Tokens**：1.225 億 tokens（命中快取 9,932 萬 tokens，**實質預填節省率 81.1%**）
  - **累計產出 Completion Tokens**：739,772 tokens
  - **MTP 草稿全週期接受率**：**73.85%**（單筆中位數 76.5%，平均 3.31 tokens/round）
  - **首字延遲 (TTFT)**：互動短請求中位數 **0.196s**｜全場景 P50 **0.380s**｜P95 **0.845s**｜看圖第 2 輪快取命中 **0.73s**｜32K 長預填短請求插隊 **1.00s**

---

## 版本演進與實測紀錄

### `v0-baseline-1012` — 初始基線 (2026-10-12 引擎 + LibertAIDAI 2.9bpw)
- **引擎**：`bertholomus/TensorFold` branch `deepseek-v41-zig` @ `dfc8fe5` (2026-10-12)
- **權重**：`LibertAIDAI/DeepSeek-V4.1-Flash-1017-EXL3-2.9bpw` + 官方 1017 Engram Shards 47 & 48
- **實測檔案**：`benchmarks/results/00_baseline_1012_dfc8fe5.json`

### `v1-step1-zig-engine` — Native Zig 引擎升級與記憶體/排程調優 (2026-10-27)
- Fast-forward 至 `fbbc9713` (2026-10-25)，合入 `TF_DS_PROMPT_ALIAS=1`（省 1.63 GiB 預填暫存）、`TF_FILL_CUT_IN=4096`（短請求插隊 TTFT `26.35s -> 0.94s`）、含圖多輪對話快取跳過 Vision Tower 重算（`2.21s -> 0.73s`，提前免疫社群 Issue #90 / PR #93）、Tokenizer 暫存釋放與 Grace Neoverse-V2 `ReleaseFast` 編譯。
- 修復 `proxy.py` 串流請求提前釋放 slot 臭蟲。
- **實測檔案**：`benchmarks/results/full_eval_01_step1_libertai_2.9bpw.json`

### `v2b1-f32-gate-bias` — 修復 43 層官方 FP32 路由偏置 (2026-10-27)
- 修正社群量化將 40 層 MoE + 3 層 MTP 的 `e_score_correction_bias` 截斷為 FP16 導致 95.1% 相鄰專家平手與排序反轉的物理缺陷。
- `temp=0.30` 代碼解碼速度自 `74.0 tok/s` 暴增至 **`90.2 tok/s (+21.4%)`**，MTP 接受率自 `67.6%` 升至 **`79.9%`**。
- **實測檔案**：`benchmarks/results/full_eval_02b1_f32_gate_bias_2.9bpw.json`

### `v2b2-plusten-backbone-head-mtp` — Plus-Ten 6-bit Head/MTP + 512K 序列校準骨幹 (2026-10-27)
- 植入 Plus-Ten 1017 骨幹（Attention、Shared Experts、6-bit LM Head 與 6-bit MTP 稠密層）。
- `temp=0.00` 代碼解碼達 **`95.5 tok/s`**（MTP 接受率 **80.3%**，TPR 3.76），C4 併發聚合吞吐達 **`116.31 tok/s`**，30 題五維度題庫通過率 **93.3% (28/30)**。
- **實測檔案**：`benchmarks/results/full_eval_02b2_plusten_backbone_mtp_2.9bpw.json`

### `v2a-ooa-hybrid-2.7bpw` & `v2c-ultimate-fusion` — OOA 混合位元專家與終極融合實驗 (2026-10-27)
- 測試 OOA 2.7bpw (K2..K5) 敏感度分配專家與 Plus-Ten 骨幹融合，Active RAM 降至 `101.64 GiB`（每節點額外省 1.84 GiB），可透過 `scripts/switch_to_ooa_hybrid.py` 一鍵切換。
- **實測檔案**：`benchmarks/results/full_eval_02a_ooa_hybrid_2.7bpw.json`、`benchmarks/results/full_eval_02c_ultimate_fusion_plusten_ooa.json`

### `v2b2-p1-verified` & `v2b2-p2-priority-proxy` — Serving 工具對話修補與優先權排程網關 (2026-10-28)
- **P1 引擎修補**：合入 `0027-tool-call-prose.patch`（修復非串流 Tool-Call 丟失計畫文字與串流多餘換行導致快取脫靶）與 `0028-plain-request-text.patch`（`U+FDD0` 遮罩保護工具結果內的 `<｜User｜>` / `</think>` 不被誤編碼為控制 Token）。
- **P2 優先權排程**：於 `proxy/proxy.py` 實作 `X-Priority` 優先權佇列（`0: interactive`, `1: normal`, `2: background`）與背景槽位上限（`background_max_slots = 3`），3 路背景滿載下前景互動請求 1.40s 完成。
- **實測檔案**：`benchmarks/results/full_eval_stage2b2_live_verified.json`、`benchmarks/results/full_eval_stage2b2_p1_patched.json`
- **完整 PDF 報告**：`reports/DGX_Spark_TP2_Comprehensive_Benchmark_Report_20261027.pdf`
