# DeepSeek V4.1 Flash 1017 · 雙節點 DGX Spark TP=2 生產配方與基準追蹤庫 (`dgx-spark-tp2-recipes`)

<div align="center">

[![語言：繁體中文](https://img.shields.io/badge/%E8%AA%9E%E8%A8%80-%E7%B9%81%E9%AB%94%E4%B8%AD%E6%96%87-059669?style=for-the-badge)](README.zh-TW.md)
[![Language: English](https://img.shields.io/badge/Language-English-2563eb?style=for-the-badge)](README.md)
[![發行版本：超越級生產冠軍 P15](https://img.shields.io/badge/%E7%94%9F%E7%94%A2%E5%86%A0%E8%BB%9D-v2b2--p15--transcending--champion-10b981?style=for-the-badge)](https://github.com/bertholomus/TensorFold)
[![推論引擎：TensorFold Native Zig](https://img.shields.io/badge/Engine-TensorFold_Native_Zig-0891b2?style=for-the-badge)](https://github.com/bertholomus/TensorFold)
[![模型權重：Plus-Ten 2.9bpw](https://img.shields.io/badge/Weights-Plus--Ten_2.9bpw_6--bit_MTP-d97706?style=for-the-badge)](https://huggingface.co/Plus-Ten/DeepSeek-V4.1-Flash-1017-TensorFold-EXL3-2.9bpw)
[![PDF 報告](https://img.shields.io/badge/PDF-%E7%94%9F%E7%94%A2%E5%86%A0%E8%BB%9D%E9%87%8C%E7%A8%8B%E7%A2%91%E5%A0%B1%E5%91%8A-dc2626?style=for-the-badge)](reports/DGX_Spark_TP2_Production_Champion_Milestone_Report_20261109.pdf)

</div>

![DeepSeek-V4.1-Flash-1017 on Dual NVIDIA DGX Spark TP2 with TensorFold Native Zig](assets/hero.png)

> **🌍 中英雙語導覽 / Bilingual Documentation**：
> - **繁體中文版**（本頁：`README.zh-TW.md`）
> - **[English Edition (`README.md`)](README.md)**

---

## 專案概述

本儲存庫記錄了在 **兩台 NVIDIA DGX Spark（GB10，2× 128 GB Unified LPDDR5X Memory）** 透過 **ConnectX-7 200G RoCEv2 雙軌直連（實測 185 Gbps）** 叢集架構下，將 **DeepSeek-V4.1-Flash-1017（763B MoE，1M Context）** 調優至全面超越早期基準的 **超越級生產冠軍配方（`v2b2-p15-transcending-champion`）**。

在 1 小時連續隨機混流高壓馬拉松（`omni_eval_1hour_p15_transcending_champion.json`）實測中，本配方達成：
* **100.00% 完美成功交付**：833 / 833 筆請求全量成功交付，**0 筆失敗、0 筆 429 秒退、0 筆 OOM**。
* **9,566,208 (9.57M) Tokens 快取命中復用**：創歷史全時段最高紀錄（比 P11 基準多出 +30.7 萬 tokens）。
* **279,583 Tokens 生成總量**：創歷史全時段最高紀錄（比 P11 基準多出 +5,736 tokens）。
* **30.63 秒平均整體耗時**：比 P11 基準更快 0.47 秒，動態排隊常駐僅 0~1 筆，達成 **0ms 緩衝膨脹**。

---

### 五大關鍵技術革新與突破

1. **解耦 2M 多流共享 KV 池（Patch 0063 / `out.p11b` / `out.2m`）**：
   * 將單一請求上下文長度（1M）與多流共享緩衝池（`TF_DS_WINDOW=2097152`）徹底解耦。
   * 透過 MLA 壓縮（890 bytes/token/rank），2M 完整 Token KV 池於每節點僅佔用 **1.74 GiB** 物理空間。
2. **Strata 三層存儲分級架構與 NVMe 快取最大化**：
   * **L1 熱池（UMA LPDDR5X @ 546 GB/s）**：常駐 2M KV 池與 2.5 GiB 主機顯存快照池（`--prompt-cache-gib 2.5`）。
   * **L2 溫池（PCIe 4.0 NVMe Learn Imprint 最大化）**：**32 GiB 持久化學習印記（`--learn --learn-gib 32`）**，**126.9 GB 快照存儲（3,433+ 份活躍塊檔案）**，**零宿主實體顯存索引佔用**，重啟時毫秒級熱 Radix 樹還原。
   * **L3 冷池（異步落盤冷存儲）**：50 GB 硬配額管理，背景 gzip 異步落盤，主推論線程 0ms 阻塞。
3. **8 槽位 Erlang 安全工作竊取排程器（Port 8889 Proxy）**：
   * 1~6 號槽位標準全開放，**7 號槽位支援安全工作竊取（Safe Work-Stealing）**（在無可運行之 P0/P1 緊急任務時開放 P2 背景長文本借調），**8 號槽位神聖保留**（專屬 P0 前景互動與 P1 視覺跟隨）。
   * 階梯式超時矩陣 `[25s, 22s, 19s, 16s, 13s, 10s, 7s, 4s]`，P0 自適應 16s 視窗，>12K 根節點主動展延 +8s 防驚群。
4. **3.05 GiB 主動預填流水線屏障**：
   * 根據主機剩餘可用 RAM 階梯動態調控大預填並發（>20K tokens）：RAM ≥ 3.05G 允許 3 路並發；< 3.05G 壓制為 2 路。
   * 暖前綴完全豁免（標記為 512B），大預填計數器於首字 Delta 發出時立即遞減釋放，徹底根除虛假阻擋。
5. **MS-DTC 動態溫控變速箱（`scripts/ms_dtc_governor.py`）**：
   * 50 MHz 平滑調頻消除 150MHz 離散震盪；2400 MHz 待機（9.4W），2500 MHz 甜區爆發，89°C 軟夾持於 2200 MHz（杜絕 1800MHz 崩潰斷崖）。

---

### 系統架構與 Strata 存儲設計圖

![Dual NVIDIA DGX Spark TP=2 System Architecture and Strata Tiered Storage](assets/architecture.png)

---

### 1 小時馬拉松長跑全階段實測數據對照表

所有階段均在完全相同的硬體配置下，以 1 小時連續壓力測試基準（`benchmarks/run_omni_eval.py --profile standard --duration 3600`）進行全量回歸評測：

| 評測核心指標 | P11 基準 | P12 v1 (初版) | P12 v4 (去截斷) | P13 (前綴感知) | P14 (負向回退) | P15 終極超越冠軍 ⭐ |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **總發起請求數** | 839 | 711 | 725 | 757 | 778 | **833** |
| **成功交付筆數 (200 OK)** | 836 (99.64%) | 647 (91.00%) | 713 (98.34%) | 745 (98.41%) | 694 (89.20%) | **833 (100.00% 完美全交付)** |
| **429 秒退 / 丟棄筆數** | 3 (0.36%) | 64 (9.00%) | 12 (1.66%) | 12 (1.59%) | 84 (10.80%) | **0 (0.00% 零秒退)** |
| **Prompt Cache 命中 Tokens** | 9,259,008 | 5,027,840 | 5,701,632 | 7,018,496 | 5,793,792 | **9,566,208 (歷史新高 +30.7萬)** |
| **產出 Tokens 總量** | 273,847 | 211,262 | 228,633 | 239,951 | 226,285 | **279,583 (歷史新高 +5,736)** |
| **單筆平均耗時 (Wall Clock)** | 31.10 秒 | 37.84 秒 | 35.22 秒 | 32.58 秒 | 41.93 秒 | **30.63 秒 (比基準快 0.47 秒)** |
| **P0 互動式任務交付率** | 100.0% | 100.0% | 100.0% | 98.2% (退 3) | 99.4% (退 1) | **100.0% (163/163 全交付)** |
| **P1 視覺追蹤任務交付率** | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | **100.0% (499/499 全交付)** |
| **P2 背景長文本任務交付率** | 98.2% | 63.2% (退 60) | 92.9% (退 12) | 94.7% (退 9) | 54.0% (退 80) | **100.0% (171/171 全交付)** |
| **單流貪婪解碼速率** | 91.56 tok/s | 91.80 tok/s | 92.10 tok/s | 92.38 tok/s | 92.10 tok/s | **92.14 tok/s (MTP 81.7%)** |
| **多流滿載聚合吞吐 (C8)** | 168.0 tok/s | 162.0 tok/s | 170.5 tok/s | 172.0 tok/s | 169.0 tok/s | **175.0 tok/s (8 槽位滿載)** |
| **系統全量接入速率** | 2,648 tok/s | 1,455 tok/s | 1,647 tok/s | 2,016 tok/s | 1,672 tok/s | **2,735 tok/s (35.2x 解碼放大)** |
| **冷 8K 預填速率** | 2,135 tok/s | 2,097 tok/s | 2,145 tok/s | 2,210 tok/s | 2,180 tok/s | **2,221 tok/s (TTFT 2.64s)** |
| **32K 搶佔插隊首字延遲** | 0.94 秒 | 1.13 秒 | 0.88 秒 | 0.79 秒 | 0.82 秒 | **0.783 秒** |
| **視覺第二輪快取首字延遲** | 0.71 秒 | 0.73 秒 | 0.54 秒 | 0.48 秒 | 0.49 秒 | **0.475 秒 (100% 快取命中)** |
| **Node 1 穩態可用顯存** | 3.80 GiB | 4.10 GiB | 3.50 GiB | 3.50 GiB | 3.48 GiB | **3.20 ~ 3.50 GiB (>2.80G 安全底線)** |
| **Node 1 Swap 記憶體洩漏** | 0 MB | 0 MB | 473 MB 平整 | 473 MB 平整 | 473 MB 平整 | **473 MB 平整 (零活動 · 零 OOM)** |

---

### 端到端延遲瀑布分解（Latency Waterfall Breakdown）

```
總平均請求耗時：30.63 秒 (100.0%)
│
├── [TTFE] 快速失敗代理排隊與鎖持有：0.82 秒 (佔 2.7%)
│   └── 處於 Little's Law 平衡態 L = 7.09；8 槽位滿載下維持 0ms 緩衝膨脹
│
├── [TTFT] 上下文接入與動態預填階梯：10.45 秒 (佔 34.1%)
│   ├── 冷 8K 預填速率：2,221.0 tok/s
│   ├── 32K 背景並發插隊延遲：0.783 秒
│   └── 視覺第二輪跟隨任務：0.475 秒 (第二輪 8,192 tokens 100% 命中)
│
└── [TTET] 自回歸解碼輸出階段：20.18 秒 (佔 63.2%)
    ├── 單流貪婪解碼：92.14 tok/s
    ├── DSpark 投機接受率 (MTP)：81.7%
    └── DSML 原生工具調用首字發出：+0.694 秒
```

---

### 快速啟動與運維指令

```bash
# 1. 啟動生產冠軍叢集（雙機 TP=2 + Strata 2M 池 + 2.5G 快照）
/home/joseyarashio/start-dsv41.sh

# 2. 檢查 Port 8889 快速失敗代理狀態與 POSIX 共享記憶體健康
curl -s http://127.0.0.1:8889/proxy/status | python3 -m json.tool

# 3. 執行 1 小時全維度標準壓力測試（OmniBench Marathon）
python3 benchmarks/run_omni_eval.py --profile standard --duration 3600

# 4. 檢視即時硬體溫度、GPU 時脈與 MS-DTC 變速箱日誌
sudo journalctl -u spark-ms-dtc -f
```

---

## 參與貢獻與致謝

- **[BertholomusAI / TensorFold](https://github.com/bertholomus/TensorFold)**：原生 Zig TP=2 推論引擎、AOT CUDA 內核與 DSpark 投機解碼。
- **[Plus-Ten](https://huggingface.co/Plus-Ten/DeepSeek-V4.1-Flash-1017-TensorFold-EXL3-2.9bpw)**：序列校準 2.9bpw 骨幹與 6-bit LM Head / MTP 草稿頭。
- **[DeepSeek](https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash-1017)**：官方開源檢查點與 43 層 FP32 路由偏置權重。
- **[MiaAI-Lab](https://github.com/MiaAI-Lab/DeepSeek-v4.1-Flash-1017-2x-DGX-Sparks)**：上游參考修補 Patch 0048 原生工具串流。
