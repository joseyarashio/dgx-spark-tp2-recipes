# 2026-11-16 需求外部審查彙整（Opus 5.5 + Astra 6）

審查材料：requirements.md（R1–R8）、dossier_full.md（72,562 字元）。兩份審查都正常結束（finish=stop）：Opus 187 秒，Astra 143 秒。

## v1.2.9 判定
- Opus：整版不合併；v1.2.9 本身也沒有值得 cherry-pick 的項目。
- Astra：不整版合併；只能逐項 cherry-pick，而且目前沒有任何一項已核准。
- 共識：兩份都不支持整版合併。

## 已逐條核對的審查主張
- 【成立】上游 deepseek_v41 family 已有人在 GB10 上用於生產（jayleaton/0rand；論壇 #384 的 patch 路徑可證）。所以「上游沒有 DeepSeek」的說法要改成「遷移等於換掉整個引擎」。
- 【成立】#3017：template 第 39–44 行的 effort 解析不受 thinking 開關限制。實際查證：本機 text.zig 把 effort 名稱轉成數字（minimal 25、low 50、medium 62、high 75、xhigh 88、max 100），hf_text.zig 以整數傳給 template，template 對整數直接採用。medium 對應 62 是刻意設計，Opus 擔心的錯誤映射不存在。
- 【成立】只 hold 四個 kernel metapackage 不夠，dgx-spark-ota-update-meta 26.09.3 也要一起 hold。
- 【成立，已查證】兩台的 nvidia 模組封裝版本不一致：Node1 linux-modules-nvidia-580-open-7.0.0-1019 是 +1，Node2 是 +2。兩台 /proc/driver/nvidia/version 同為 580.178.04、同一建置時間。
- 【不成立】「36 筆 dsml_in_content 與 loop_period 是同一批」：依 req_id 比對只重疊 1 筆。DSML 外洩有 28 筆是無 tools、8 筆是 tool_choice=none，finish 全為 stop。另一個相關性（模型在無 tools 時仍輸出 DSML 文字）已記錄在 OmniScenario 試跑發現裡。
- 【已查證】核心日誌：兩台本次開機（11-09 起）與上次開機的 kernel log 中，oops、list corruption、lockup 都是 0 筆。Node2 只在 10-22/10-23 有多次短開機，與 1025 無關。
- 【已查證】rank0 容器 11-15 22:15 CST 啟動，log 涵蓋約 13 小時，ContextFull 0 筆。本機 lane_host 在 ContextFull 時會 requeue（第 399 行）。
- 【成立】proxy 記憶體階梯使用固定 GiB 門檻與固定 3/2/1 併發，違反尺度無關規則。這是兩位都指出的既有技術債。
- 【成立】#52 cache telemetry 的價值被低估：/health 的 memory.cache=0，看不到 prompt cache held 與 budget 的比例，而這正是 Node1 記憶體持續下降的調查所需。
- 【成立】#85 未測的正是生產路徑：生產 temperature 0.30 有採樣，但 #85 沒有在 GB10 上驗證「採樣下有 draft 與 draft:false 結果一致」。
- 【部分成立】R3 只是讀程式的推論，需要用 #51 的 bench_concurrent 參數實測一次才能結案。
- 【Astra】E20 的記憶體變更把 cache 2.5→2.0 與 MALLOC_ARENA_MAX=4 合在一次，且只跑了 52.7 分鐘，不符合「每項各自 1 小時」。屬程序缺口，建議補拆分 A/B。

## 定案行動順序
1. 唯讀證據已完成（本彙整）。
2. 兩台 apt-mark hold：linux-nvidia-hwe-24.04、linux-image-nvidia-hwe-24.04、linux-headers-nvidia-hwe-24.04、linux-modules-nvidia-580-open-nvidia-hwe-24.04、dgx-spark-ota-update-meta；之後用 apt-get -s dist-upgrade 驗證。不需要做推論回歸。
3. 對齊 Node1 的 nvidia 模組 +1→+2：先讀 changelog，再當成獨立 stage（需重開機並跑完整回歸）。
4. initcall-bl 1.0-2（power_wrap_init）：目前不做；本機 kernel 日誌也沒有任何 oops。
5. R3 實測（唯讀）：用 bench_concurrent 跑 1/4/8 並發，並在 trail 中查 add 事件與 round 的對應。
6. #52 最小移植（只做 prompt cache held/budget 讀出）：觀測用的 stage。
7. Structured output 依 #48→#49→#50 分三個 stage。驗收除完整 gate 外，還要包含：無 grammar 請求 token_sha 一致、T=0.30 採樣、loop_guard_stop、tools 與 response_format 同時使用、重放 MacBook 那筆 400。
8. proxy 記憶體階梯改為 PSI 加相對水位，先 shadow 24 小時。
9. 程序補課：cache 2.0 與 MALLOC_ARENA_MAX=4 拆開做 A/B（等 #8 完成後再排）。
