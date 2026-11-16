## 1. 逐項審查 R1–R8

以下 verdict 是對操作員立場的判斷，不代表核准部署。任何變更仍須獨立 stage，完成 30 題、decode gate、完整 1 小時 marathon；只有證明正收益才保留。

### R1：整包合併 v1.2.9
**Verdict：partly。支持不整包合併，但部分理由說得過滿。**

- **關鍵證據：**E2：共同祖先為 1.0.2；上游領先 7,486 commits、本地領先 157 commits，差異 11,099 files。上游採 `families/deepseek_v41`、不同 binary 與資產格式；README 明言 release binary 尚不服務 DeepSeek，recipe 仍標示 experimental。
- **漏掉／說錯：**
  - 四項變更沒有修改 DeepSeek 目錄，不等於不影響 DeepSeek。E6 的 server/template/runtime metadata 就是共用路徑。
  - 「p17 功能全部必須重新移植」仍是 **unverified**。架構不同足以要求逐項對照，但不能由目錄差異推導每項功能都不存在。
  - README 說 #827 still open，但 E2 說它 CLOSED unmerged；應稱文件狀態不一致，不能把關閉當成通過整模型 gate。
- **補證方式：**在保留兩邊 refs 的 repo 執行：
  ```
  git diff dgx-spark-tp2-p17 6b9de695 -- zig/src/server zig/src/core zig/src/families
  ```
  對 E3 的 loop guard、DSML、共享池、NVMe、rank cache 逐項建立功能及測試對照表，而不是只數檔案。

### R2：v1.2.9 cherry-pick 候選

#### R2a：#2814 kept_tool_calls
**Verdict：partly。觀測性質成立，低優先序的理由不足。**

- **證據：**E7 明言 parser 決策不變；新增 unoffered/malformed 分類、名稱、stream final chunk 與 metrics。E19 外部 466 rows 中有 332 筆帶 tools；`dsml_in_content` 外部為零。
- **問題：**`dsml_in_content` 並不等價於 unoffered/malformed 分類。零命中不能證明沒有工具封包退回文字，也不能證明現有 proxy 已涵蓋此需求。
- 本地適配是否必要、原 diff 能否套用是 **unverified**；應檢查本地 DSML parser 與 `zig/src/server`，再對匯出的 #2814 patch 執行 `git apply --check`。
- E7 還有固定 8 names／64 bytes 上限。至少 8 的計數上限須對照「不硬編碼 slot counts 或 thresholds」規則，不應照搬後忽略。

#### R2b：#3017 thinking-off effort
**Verdict：partly。不必立即移植，但「完全不適用」不成立。**

- **證據：**E5 第 133–139 行確實只有 thinking 時輸出 effort prefix；但第 39–44 行仍解析 effort，非法字串會拋錯。E6 也改了回應中的 runtime `reasoning_effort`，不只改 prompt。
- **問題：**可推論有效 effort 不會透過該 prefix 改變 thinking-off prompt；不能推論所有輸入、metadata、驗證行為都不變。
- E19 有 `medium`、`none`，但 E5 模板直接接受的名稱是 low/high/max；本地 server 如何轉換是 **unverified**。
- **補證：**檢查本地 `zig/src/server/chat.zig`、`fields.zig`、`chat_generation.zig` 與模型 `chat_template.jinja`。測試 thinking on/off、request effort 有無、server default 有無，以及 E19 出現的名稱；比較渲染 bytes、錯誤與 metadata。

#### R2c：#2156 PSI governor
**Verdict：partly。維持關閉正確，但 proxy ladder 不是替代證明。**

- **證據：**E8：沒有 Linux device 或 whole-checkpoint receipt；僅回收 shared lane host optional states，不涵蓋 family caches，也不協調 TP hosts。
- **問題：**
  - E20 的 proxy ladder 依賴記憶體門檻與固定 concurrency，與 PSI stall governor 不同。
  - E20 已有固定 3/2/1 concurrency、3.05/2.65/3.8 GiB 等規則，與 owner 的 scale-invariant 要求有衝突。
  - #2156 自身也提出固定 PSI thresholds，不能直接當成合規解法。
- 保持 `TENSORFOLD_MEMORY_PRESSURE` 關閉。實際雙主機保護能力是 **unverified**；須用 `/proc/pressure/memory`、`/proc/meminfo` 同步記錄及受控壓力測試證明 shedding、恢復、不振盪、TP 一致性。

#### R2d：Ollama API、TOML config
**Verdict：partly。Ollama 可略過，TOML 不應用同一理由否定。**

- **證據：**E1：#3342 是新增 client API；#2885 是讀取 serve flags。E4 已有可保存的 shell launch scripts。
- **問題：**OpenAI client 不需要 Ollama API，與 TOML 是否有助 launch 可重現性是兩個問題。
- TOML 對本地是否有正收益為 **unverified**；檢查 `rank0.sh`、`rank1.sh` 與 #2885 的解析／優先序測試。沒有明確減少配置錯誤的證據前，兩者都不部署。

### R3：TF_FILL_DRAIN
**Verdict：partly。暫不移植合理；本地「所有短 prompt 都已同回合完成」未證實。**

- **證據：**E9 明言只把 `TF_FILL_MANY` 的退化補回 unset 水準；E10 本地沒有 MANY，且 admission loop 會持續呼叫 `admitOne()`。
- **問題：**admission 不等於完成 prefill。E10 有 `FillBusy`、cut-in、圖片限制；僅憑 `TF_FILL_FIRST=2` 不能證明所有所謂短 prompt 都在第一 piece 完成。
- 本地 burst 行為為 **unverified**。應在 `zig/src/core/lane_host_fill_test.zig` 加入與 E9 相同的 round-count fixture，並跑：
  ```
  tools/bench_concurrent.py --tokens 256 --reps 3 --temperatures 0 --levels 1,4,8 --alone --serial
  ```
  此處 concurrency 是測試點，不是新增 production slot 上限。若本地沒有退化，不應為上游數字新增旋鈕。

### R4：Structured output
**Verdict：partly。需求成立，但「不急，等 merge」不是充分的優先序依據。**

- **證據：**E19 是 owner 真實請求被 400 拒絕；E15 的替代 build 已有 strict schema 使用案例。E12 的 #85 與 E11 的 #48–#50 是同一變更路線，不是兩套獨立驗證。
- **問題：**
  - upstream merge 不等於本地 p17 相容，也不等於 owner gate 通過。
  - E12 的 GB10 對照不是純單變更：對照 image 還少 restore-room patch 與另一個 test patch。其速度結果不能純歸因於 grammar。
  - sampled drafted/plain、guided_choice exactness、長 extraction、圖片尚未完成 GB10 驗證。Production temperature 是 0.30（E4），不能只驗 temperature 0。
  - R4 宣稱 forced `</think>` 會 HTTP 500，但提供的 E12 在「Edge cases」處截斷；該路徑為 **unverified**。須讀 `zig/patches/0060-structured-output.patch` 的 grammar／loop-guard 錯誤處理並重現。
- 建議優先做隔離 build 的功能驗證，不因一筆 400 直接上 production，也不無期限等待上游。採用 #48→#49→#50 時，每個增量都各自完整回歸。

### R5：Kernel 1025／OTA
**Verdict：partly。暫時 hold 有理由，但四個 metapackage 不構成完整防線。**

- **證據：**E17：兩機仍為 1019／580.178.04，但 kernel、initcall-bl、OTA 都可升級。OTA dependency 包含 `nvidia-spark-run-apt-upgrade`。本機 1019 modules 也有獨立更新。
- **問題：**
  - timer active 不等於會無人值守安裝；「一定自動升級」是 **unverified**。用 `apt-config dump`、`systemctl cat apt-daily.service apt-daily-upgrade.service` 及 `/var/log/apt/history.log` 查明。
  - hold metapackage 不一定阻止既有 versioned modules、userspace 或 GRUB 配置更新。
  - E14 第一案例只說回退 1019 後初期無再發，加入 blacklist 後仍在 monitoring；不是已證實「兩種修法都解決」。
  - 第二案例在舊 kernel／driver 仍凍結，因此不能把所有 OTA 問題歸因於 1025，也不能把 IOMMU 參數視為已知根因。
- **initcall-bl 1.0-2：**不建議立即隨 OTA 一起裝。在 1019 的本地效果是 **unverified**；先看 `apt-cache policy nvidia-spark-initcall-bl`、`apt-get -s install nvidia-spark-initcall-bl=1.0-2`，下載並檢查 package scripts，再安排獨立維護 stage。

### R6：jayleaton 2.8bpw pack／engine
**Verdict：partly。維持現況合理，但不能判定替代 stack 較差。**

- **證據：**E15：四個約 500K sessions 時 head 約 4.5 GiB 對 7 GiB；長 prefill 約快 11%，prose decode 約慢 10–15%；high effort 同分、max 結果不確定。
- **問題：**不同 pack、不同 engine、單次品質測試；不能把他人的記憶體差額直接扣到本地 E17 的 MemAvailable，更不能斷言 2.8bpw 品質下降。
- 同 pack 的 engine A/B、同 engine 的 pack A/B 都是 **unverified**。E15 提供 f16 相容 patch，讓同 pack 對照值得研究，但 patch 本身也須獨立驗證。
- 不做 production stack switch；若研究，engine 與 pack 必須分 stage。

### R7：watermark PSA
**Verdict：agree，但只限「目前沒有該 PSA 的 raised-watermark 問題」。**

- **證據：**E17 兩機 `min_free_kbytes=45166`，且 MemAvailable 均大於 MemFree，與 E15 的 5 GiB 舊設定不同。
- **漏項：**不能因此推論記憶體充裕。E20 預計 prompt cache 還可能增長約 1.5 GiB；E17 PSI avg 為零只是當下觀察，不能保證尖峰安全。
- 重開機後持續維持此值仍為 **unverified**；用：
  ```
  sysctl vm.min_free_kbytes
  grep -R -n min_free_kbytes /etc/sysctl.conf /etc/sysctl.d /usr/lib/sysctl.d /run/sysctl.d
  ```
  不應抄論壇的記憶體 floors。

### R8：#55、#52、Mia #139–#141
**Verdict：partly。**

- **#55：**E11 證明其基底有 head-of-line blocking，但 GPU／end-to-end 尚未驗證。rank0 零 `ContextFull` log 不代表沒發生，除非先證明每次都記錄。查本地：
  ```
  rg -n 'ContextFull|backoff' zig/src/core
  ```
  再以 E11 的 fitting-warm-request fixture 驗證本地是否受影響；目前為 **unverified**。
- **#52：**值得提高到記憶體診斷優先項，但仍是 draft。E18 的 `cache: 0` 不能直接解釋成 prompt cache 沒佔 RAM；它與 E20 約 580 MiB held 的口徑關係為 **unverified**。查 `prompt_cache.zig`、`families/dsv41/lanes.zig` 與 health/metrics producer。
- **#139：**本地沒有 spill-v2 是操作員敘述；E3 有雙平面 NVMe spill，但不證明版本。用 `rg -n 'spill.v2|spill_v2' zig` 及完整 PR diff 確認，不能只看標題。
- **#140/#141：**「build-only 所以不適用」不成立。E13 的 #140 更換 NVIDIA、Pillow、Zig pins；可改變產物與 runtime dependency。適用性為 **unverified**，須看完整 PR diff、Dockerfile、build scripts；不是低風險免費更新。

## 2. 「v1.2.9 值得合併」最終判斷

**選擇：cherry-pick；不是 merge wholesale，也不是立即批准任何候選。**

現有 dossier 沒有 v1.2.9 對這套 DeepSeek p17 production 的完整合格證據。release 的速度與「replies unchanged」不能外推成全 server、全 family、所有請求都不變；E1 自己也列出 prompt／拒絕行為的變化。

會改變判斷的具體證據：

1. 同 DeepSeek checkpoint、相同精度與 production 配置的可重現 A/B。
2. E3 本地功能逐項保留的程式與測試證據，包括 DSML streaming、loop guard、NVMe restore、共享池與 rank cache。
3. 每項增量分開完成 30 題、decode gate、完整 1 小時 marathon，並交付原始結果、build SHA、launch scripts。
4. 同時證明品質、decode、長 prompt、記憶體及外部 API 無退化，且有明確正收益。
5. 消除或重新設計硬編碼 slot／threshold 規則。

即使上述成立，也不能用一個巨大合併 stage 取代 owner 要求的逐項驗證。

## 3. Production 風險與緩解

- **Kernel／OTA：**部分 hold 仍可能留下 modules、userspace、GRUB 變更入口。先做 simulated upgrade 與套件腳本審核，保存已知可開機 kernel、套件版本及 GRUB 配置；不在服務中的 TP pair 上直接試單機 reboot。
- **降版副作用：**E14 曾因 oracle-64k dependency blacklist `sbsa_gwdt` 導致 watchdog reset。rollback 也須檢查 dependency 與 boot log，不能只確認 kernel 版本。
- **記憶體：**cache 尚未填滿，idle 數字不是最壞情況。同步觀測雙機 PSI、MemAvailable、cache held/budget、排隊與拒絕原因；用實測壓力及實際容量設計控制，不抄固定 GiB floors。
- **品質／grammar：**DSML、thinking、loop guard、sampled redraw 可能交互影響；必測 streaming、取消、混合 structured/plain、draft/plain、並行／單獨及長 extraction。未支援 schema 應確認在首 token 前拒絕。
- **錯判測試：**E20 的記憶體調整同時改 cache 與 allocator，且 marathon 只有 52.7 分鐘，不符合「每個變更各自完整 1 小時」。E19 的大量 429 主要來自 benchmark，不能直接算成客戶事故，也不能全部忽略。
- **不必要的 memory-mode 變更：**E18 已有 95.1 GiB／8.2 秒載入，沒有 E16 的 22 MB/s 症狀。不應套用 NUMA workaround。

## 4. 優先順序：最多 8 項

下列凡涉及變更，均適用共同驗收：**獨立 stage、30 題、decode gate、完整 1 小時 marathon；無正收益不保留，有負收益立即 rollback。** 測試工具的確切 bank／marathon 路徑未提供，屬 **unverified**；須先從 p17 gate 執行紀錄與 harness commit `3593042` 補齊可重跑命令。

| 順序 | 動作 | 驗收 | Rollback |
|---|---|---|---|
| 1 | 盤點並限制未審核的 kernel／OTA 更新入口 | 兩機執行 `apt-mark showhold`、`apt-config dump`、`apt-get -s dist-upgrade`；確認四個 metapackage 之外的更新路徑也已審核 | 移除新增 hold／還原更新策略；不因此立即執行升級 |
| 2 | 建立可重現基線，補驗 cache 與 allocator 兩個獨立 stage | 對 E20 的 `2.5→2.0` 與 `MALLOC_ARENA_MAX=4` 分別 A/B；每個完整 gates，harness backoff 固定不混改 | 各 stage 還原前一配置；cache 不低於 owner 的 2.0 floor |
| 3 | 審核 initcall-bl 1.0-2，再決定隔離試驗 | package scripts、模擬安裝、重開機後 `/proc/cmdline`、kernel journal、TP gates；無本地正收益證據則不推廣 | 還原 package／GRUB、啟動已知良好 1019，確認 watchdog 與雙機連線 |
| 4 | 適配 #52 cache telemetry | 四個 span 合計等於 capacity；failure 分項與 aggregate 一致；held/budget 口徑可解釋；無 inference 行為或 decode 退化 | 切回前一 binary，移除新增 telemetry |
| 5 | Structured output 隔離實作 | 重播 owner 400；schema／choice、sampled、DSML、loop guard、draft/plain、並行及長 extraction 全測；#48/#49/#50 各自 gates，不一次帶入 | 切回前一 build prefix；保留原本明確拒絕行為，不假裝已支援 schema |
| 6 | 修正 memory admission 的固定 slot／threshold 設計 | 先 shadow，依雙機壓力與實際資源驗證；不振盪、不誤殺、可恢復，不降低品質或 decode | 停用新控制器、恢復前一策略；記錄舊策略仍未符合 scale-invariant |
| 7 | 隔離評估 #2814 | unoffered／malformed、whole／stream、clean reply、metrics 全覆蓋；parser 決策不變；處理固定計數上限的合規問題 | 還原 parser instrumentation 與 API 欄位 |
| 8 | 先重現 #55／R3 問題，再決定是否改 scheduling | 本地 CPU fixtures 與 burst trace 證明問題存在；若修，#55 與 DRAIN 分開 stage，測取消、公平性、warm admission、token exactness | 各自回退 scheduling 變更；沒有本地問題就不移植 |

目前應把「有 release」與「本地可部署」分開：優先補齊更新控制、可重現基線、記憶體口徑與 structured-output 驗證，而不是追版本號。