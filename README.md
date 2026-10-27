# DGX Spark TP=2 配方調整與基準實測追蹤庫 (`dgx-spark-tp2-recipes`)

本儲存庫用於追蹤雙節點 NVIDIA DGX Spark (GB10, 2x 128GB Unified Memory, ConnectX-7 200G RoCEv2) 的模型推論配方調整、引擎修補 (`patches/`)、啟動腳本 (`scripts/`)、Port 8889 階梯式排隊 429 規則 (`proxy/`) 以及每次變更前後的同機實測數據 (`benchmarks/results/`)。

## 硬體與固定約束
- **節點拓撲**：
  - Node 1 (Head): `spark-9e5c` (`192.168.10.148` / Tailscale `100.70.199.89` / CX-7 `10.100.184.2`, `10.100.185.2`)
  - Node 2 (Worker): `spark-7579` (`192.168.10.149` / Tailscale `100.121.64.103` / CX-7 `10.100.184.1`, `10.100.185.1`)
- **不變規則（Port 8889 階梯式排隊 429 Proxy）**：
  - `spark-fastfail-proxy.service` 固定監聽 `:8889` 轉發 `:8888`
  - `concurrency_limit = 4`（Zig TP=2） / `2`（sudoingX vLLM）
  - `queue_buffer = 4`、`tiered_timeouts = [20.0, 15.0, 10.0, 5.0]`、`extension_seconds = 5.0`

---

## 版本演進與實測紀錄

### `v0-baseline-1012` — 初始基線 (2026-10-12 引擎 + LibertAIDAI 2.9bpw)
- **引擎**：`bertholomus/TensorFold` branch `deepseek-v41-zig` @ `dfc8fe5` (2026-10-12) + `TF_SEED_RANDOM=1` / `TF_TOP_K_MAX=56`
- **權重**：`LibertAIDAI/DeepSeek-V4.1-Flash-1017-EXL3-2.9bpw` + 官方 1017 Engram Shards 47 & 48
- **實測檔案**：`benchmarks/results/00_baseline_1012_dfc8fe5.json`

### `v1-step1-zig-engine` — 項目 1：Native Zig 引擎升級與記憶體/排程調優 (2026-10-27)
- **引擎升級**：
  - Fast-forward 至 `origin/deepseek-v41-zig` @ `fbbc9713` (2026-10-25)
  - 揀選合入：
    - `3b902fd2` (`TF_DS_PROMPT_ALIAS=1`)：25 個預填 scratch 合併為 5 個共享區（`2,585 MiB -> 956 MiB`）
    - `bfa786f4` (`share_check`)：單獨執行長預填時不中斷分塊，僅在有其他請求等待時讓出時間片
    - `44023692`：含圖多輪對話命中快取時跳過 Vision Tower 重複編碼
    - `837205e2`：Tokenizer 每次 `encode` 結束立即歸還 BPE 暫存記憶體
    - `84096b4d`：1017 EXL3 權重載入相容性（支援 converter markov 名稱與 BF16 Engram/head 自動轉換）
  - 編譯最佳化：改為針對 Grace Neoverse-V2 原生 CPU (`native`) + 全模組 `ReleaseFast`
- **啟動與系統調優 (`scripts/`)**：
  - 雙節點停止舊容器後先 `sleep 3; sync` 待 103 GiB 完全釋放，再執行 `vm.drop_caches=3` 與 `vm.compact_memory=1` 重組 2 MiB / 32 MiB 連續大頁
  - `pkill -f` 改用括號樣式 `[t]ensorfold-native` / `[t]f-dsv41-lanes` 避免誤殺父 subshell
  - `rank0.sh` 啟用 `TF_DS_PROMPT_ALIAS=1`、`TF_FILL_CHUNKS=2`、`TF_FILL_FIRST=2`、`TF_FILL_CUT_IN=4096`
- **A/B 實測成效 (`benchmarks/results/01_*.json`)**：
  - `/health` Active 記憶體：`107.07 GiB -> 103.48 GiB`（**每節點省 3.59 GiB**）
  - 可用記憶體 (`MemAvailable`)：Node 1 `4,669 -> 8,350 MiB (+3.60 GiB)`；Node 2 `5,342 -> 11,066 MiB (+5.59 GiB)`
  - 60K 冷預填下短請求插隊 TTFT：`26.35s -> 0.94s`（**快 28 倍**），單獨 8K/60K 預填速度達 `2,313 / 2,296 tok/s`
  - 多輪看圖快取續接 (>4K tokens + 512x512 PNG Turn 2)：`cached=0 (2.21s) -> cached=4096 (0.86~0.91s)`（**快 2.5 倍**）
  - 冷啟動時間：`~120s -> 23.7s`
