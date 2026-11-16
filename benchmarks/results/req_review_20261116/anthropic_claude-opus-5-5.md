# DGX Spark TP=2 DeepSeek-V4.1 需求 R1–R8 外部審查(2026-11-16)

## 1. 逐項審查 R1–R8

### R1 整包合併 ashhart v1.2.9(6b9de695)

**判定:同意不整包合併。但理由有一處要修正。**

**關鍵證據**
- E1:所有加速項目都不是 DeepSeek,分別是 Nemotron/Metal #3005、GLM-5.3/CUDA #3159 #2722、Qwen3.8/HIP #2697,以及 Flash Next/Nemotron/Qwen 的 CUDA launch 減量。兩項修正是 Nemotron Omni #2985 與 GLM TP=3 #1571。
- E2:#3017 碰到的 DeepSeek 檔案是 0/15,#2156 是 0/10,#2814 是 0/10,#3206 是 0/14。分歧規模是本地領先 157 commits、上游領先 7486 commits,共 11,099 檔、+2,580,440 行。
- E2:上游 README 第 221 行寫「DeepSeek checkpoints are not served yet by any release binary」,而 #827 已 CLOSED 未合併。
- E3:p17 的功能(e772dec66 loop guard stop、19517007d 0048、c976abd76 0064/0065、3d82b32c5 TF_DS_WINDOW、262249bf3 NVMe spill、490644d55 rank cache)都在 `families/dsv41`。上游沒有這個目錄。

**operator 漏掉或說錯的地方**
1. **「上游 DeepSeek 不可用」說得太滿。** E15 #384 wolttam 的 patch 路徑是 `engine/zig/zig/src/families/deepseek_v41/`。也就是說,jayleaton/0rand 那個 structured output 能用的 build,正是建立在 ashhart 的 `deepseek_v41` family 上。所以「release binary 不服務 DeepSeek」只代表 ashhart 沒發布。這套程式碼已經有人在 GB10 上跑生產(E15 #386 #388)。R1 的理由應改為「遷移到 `deepseek_v41` 等於換引擎,屬於 R6 的問題」,而不是「上游沒有 DeepSeek」。
2. **追蹤對象選錯。** 本地 p17 的移植來源是 bertholomus `deepseek-v41-zig-tp2`(#51 合併處,E9)與 Mia 的 patch 序列(0048/0060/0062/0064/0065,PR #112/#119/#138)。ashhart 的 release 和生產引擎只有間接關係。每日 tracker 應以 bertholomus 分支與 Mia patch 編號為主軸。
3. **E1 的「replies unchanged」本身就有例外。** release 自己說第四項預設變更(`--reasoning-effort` 不再改變 thinking-off prompt)會改 prompt。這點對本地無影響,因為 rank0.sh 沒有 `--reasoning-effort`(E4)。但「回覆不變」不能拿來當合併依據。
4. #3206(logprobs 與 tools/stop/reasoning 並用)沒列入審查。E19 沒有 logprobs 需求的證據,屬 unverified。可用 proxy log `grep -c '"logprobs"'` 確認。

### R2a #2814 kept_tool_calls 計數

**判定:部分同意。** 低優先正確,但理由不完整。

**關鍵證據**
- E7:「The parse's decisions are unchanged; it only records why it kept an envelope」。這確實只是觀測。
- E19:`dsml_in_content` 全部 36 筆,外部 0 筆。

**漏掉的地方**
- 36 筆 `dsml_in_content` 與 `loop_period` 36 筆數量相同。兩者是否是同一批請求(loop 造成 DSML 外洩)目前 unverified。可用 proxy audit log 依 request id 交叉比對兩欄位。
- 如果是同一批,問題在 loop guard 或 0064/0065,不是缺計數器。
- 本地 parser 是 DSML(0048/0064/0065),#2814 的 diff 套不上。要達到同樣效果,proxy 已經有 `dsml_in_content` 欄位,不需要動引擎。
- 結論:不移植。應先查這 36 筆的成因。

### R2b #3017 thinking-off 指名 effort 進 template

**判定:結論同意(prompt bytes 不變),但 operator 只看了 133–139 行,漏了 39–44 行。**

**關鍵證據**
- E5 第 138–140 行:`{%- if idx == 0 and thinking -%} ... "Reasoning Effort: "`。thinking off 時不輸出 effort 字串。
- E6 的 `cx.named_effort` 只影響 thinking-off 的 render,以及 runtime 回報欄位。

**漏掉的地方**
1. **effort 字串的驗證在頂層執行。** E5 第 39–44 行在頂層 `set`,不受 thinking 限制。字串只接受 low/high/max,其他值走 `raise_exception`。
2. **外部請求大量送出不合法的值。** E19 外部 effort 分布有 `medium` 101 筆、`none` 62 筆,但外部 200 有 463 筆。所以必定有一層在 template 之前改寫了 effort(proxy 的 effort-none fallback、E20 p17,或 server 端的 coerce)。
3. **待查問題:`medium` 實際映射成多少?** 50(low)還是 75(high)?這決定 101 筆外部 thinking 請求的推理深度。目前 unverified。
   - 解決方式:用 `reasoning_effort:"medium"`、thinking on 送一筆請求。
   - 比對 rank0 log 或 trail 裡的 prompt token 數,或渲染後的 "Reasoning Effort: N"。
   - 再對照 proxy 原始碼的 effort 改寫規則。
4. 本地 runtime 回報 thinking-off 時固定是 `"none"`。這屬於外觀問題,不值得單獨一個 stage。

### R2c #2156 PSI 記憶體壓力 governor

**判定:同意現在不移植。但 operator 錯過了這裡真正可用的東西。**

**關鍵證據**
- E8:「Keep the Linux opt-in off until a GB10 run shows shedding, recovery without oscillation...」。
- E8:「does not coordinate pressure across TP hosts」。
- E8:「Family-owned caches ... need their own qualification」。本地 prompt cache 與 NVMe imprint 都是 dsv41 family 自有,不在 shed 範圍內。

**漏掉的地方**
1. **現行 proxy 記憶體階梯本身違反 owner 規則。** E20 的階梯用固定門檻 3.05、2.65、3.8 GiB,正是「no hardcoded thresholds」禁止的形式。#2156 的設計原則(E8:「MemAvailable is diagnostic and does not set the level ... uses PSI rather than guessing a floor from total RAM」)正好是 scale-invariant 的替代方案。
2. **E15 #385 的實測經驗可以直接參考。**
   - 從合成測試推出的 6.25 GiB 門檻,shadow 執行一天會誤觸發 4,577 次。
   - 最後保留的是 PSI 為主、低 floor 為輔,完全沒有觸發。
   - 可行路線是在 proxy 端加入 PSI 讀值(`/proc/pressure/memory` avg10),先以 shadow 模式跑。這不需要動引擎。
3. **E17 有尚未解釋的壓力跡象,不能只看 avg10=0.00。**
   - local 節點 swap 用了 16777212−16059520 = 717,692 kB ≈ 0.68 GiB,且 swappiness=1。
   - local 的 PSI some total 是 39.0 s,peer 是 7.9 s。
   - 這代表 local 節點確實發生過 reclaim 壓力。

### R2d Ollama API #3342、--config TOML #2885

**判定:同意。**
- E19 的外部用戶端只有 3 個 IP。operator 說用戶端走 OpenAI API,但 dossier 沒有 proxy 的路徑統計,屬 unverified。可用 proxy audit log 依 path 計數 `/api/`。
- `--config` 對 native 啟動腳本(E4)沒有增量價值。

### R3 bertholomus #51 TF_FILL_DRAIN

**判定:部分同意。** 不移植的結論合理,但目前只有讀程式碼的推論,沒有實測。

**關鍵證據**
- E10:`run()` 先 `while (h.admitOne()) {}` 再 `fillOne()`。本地沒有 TF_FILL_MANY。
- `addStream` 中,`filling != null` 時,`tokens <= cut_in(8192)` 且無圖片的 prompt 會整段 prefill,也就是 cut-in。
- E9 自己說:「with the fill switches unset, short prompts in a burst already start together」。

**漏掉的地方**
1. **本地並非 unset 狀態,而是 `TF_FILL_CHUNKS=2`、`FIRST=2`、`CUT_IN=8192`。**
   - 由於 `cut_in > 0`,即使沒有 active stream,每個 prompt 也會走 `e.piece(s, fill_first)`。
   - 「短 prompt 在第一個 piece 內完成」取決於 piece 大小,dossier 沒有這項資料,屬 unverified。
   - 解決方式:查 `zig/src/core/` 中 `piece()` 與 `fill_chunks` 的單位(用 `grep -n "fn piece" -A30`)。
2. **吞吐數字有落差,值得量一次。**
   - p17 的 C8 是 156.8 tok/s(E20)。#51 的 unset 8 streams aggregate 是 code 318.4、chat 288.3。
   - 兩者的 harness、thinking、輸出長度、round rows 32 和 prompt-cache 0 都不同,不能直接比較。
   - 但這個差距值得用 #51 的同一指令在本地跑一次:`tools/bench_concurrent.py --tokens 256 --reps 3 --temperatures 0 --levels 1,4,8 --alone --serial`。
   - 同時看 trail log 中每個 `add` 事件對應的 round 計數。
   - 如果 8 個短 prompt 的開始時間間隔是一個 round,R3 的推論就不成立。
3. **driver 595 與 580 的差異和決策無關。** operator 列出來沒有意義。
4. **owner 規則面:** TF_FILL_DRAIN=ROWS 是固定 rows 預算,作者自己也提出可改成「a fixed budget」。即使要移植,也不符合 scale-invariant 原則。

### R4 Structured output

**判定:部分不同意。** 「需要但不急」可以接受,但 operator 低估了一個關鍵未知數。

**關鍵證據**
- E19:外部 466 筆中只有 1 筆 400(00:19:18,owner MacBook,thinking off,model "current")。
- E15 #386:TC-64 在 MiaAI 這一側因 response_format 400 被排除。
- E15 #388:用戶以 structured output 作為換 build 的主因。

**operator 漏掉的地方**
1. **生產環境本身就是 sampled 路徑。**
   - rank0.sh 設定 `--temperature 0.30` 與 `TF_SEED_RANDOM=1`,MTP 接受率 242110/308147 = 78.6%(E18)。
   - E12 明說「Not tested on the Sparks: drafted vs "draft": false for sampled replies and for guided_choice」,以及「A sampled stream draws every accepted row again, and I haven't measured that cost on GB10」。
   - 所以未測的正是生產預設路徑,不是邊角情況。
2. **「forced `</think>` 下會 HTTP 500」在 dossier 中無法證實。** E12 在「Edge cases」處被截斷。dossier 能證實的只有 E11 #48「refuses ... every added token like `</think>`」。
   - 解決方式:讀 #85 全文的 Edge cases 段,或 `zig/patches/0060-structured-output.patch` 中 `</think>` 相關測試。
3. **#85 的量測條件與本地不同。**
   - #85 用 EAQ v1 pack @45ee5d0f、PARALLEL=6、POOL=2101248、TF_FILL_CHUNKS=1,而且 image 還有「other patches ... I'm still testing」。
   - 本地是 LibertAI 2.9bpw、parallel 8、FILL_CHUNKS=2、FIRST=2。#85 的 IDENTICAL 結果不能直接沿用。
4. **兩條路線的取捨。**
   - #85 是 patch 0060,對 fbbc971 產生。本地已經多了 0048/0064/0065(皆改 server)與 loop guard(改 lanes)。
   - #48–#50 位於 bertholomus 的 Zig 分支,也就是本地實際追蹤的分支,且拆成三步。依 owner「一次一個 stage」原則,#48(無呼叫者,回覆不變)→ #49(json_object)→ #50(schema)本身就是三個可分別驗收的 stage,比一次套 21k 行的 #85 更合規。
   - #85 作者也說「Once TF_REF includes them, this patch can go」。
5. **需求面待確認。** 那 1 筆 400 是 owner 自己的 MacBook 用了哪個用戶端、哪個功能?如果是某個工具固定送 `response_format`,需求頻率會比 1/466 高。屬 unverified。可在 proxy log 查該筆的 User-Agent 與 response_format.type。

### R5 Kernel 7.0.0-1025

**判定:同意 hold。但 hold 的範圍不夠,證據解讀也偏了。**

**關鍵證據**
- E17:兩節點都是 1019 與 580.178.04,cmdline 只有 `initcall_blacklist=tegra234_cbb_init`。
- E17:apt-daily 與 apt-daily-upgrade 的 timer 都在跑。apt.conf.d 只看到 `01autoremove`,未見 unattended-upgrades 設定。

**漏掉或說錯的地方**
1. **1025 有問題的證據其實很弱。**
   - E14 #1 的用戶是 Ubuntu 26.04、桌面使用,缺 power_wrap_init。他同時做了退回 1019 和加 blacklist 兩件事,變因混在一起。
   - E14 #10 dgk960 在 6.17 加舊 driver 下也凍結,且他的 cmdline 已含 power_wrap_init。他懷疑的 iommu.passthrough=0、kho=off、pci=pcie_bus_safe,我們的節點已經全都有了。
   - 所以真正該問的是「我們在現行 cmdline 下是否穩定」,不是「1025 好不好」。目前 unverified。
   - 解決方式:兩節點都跑 `journalctl --list-boots`、`last -x reboot shutdown`、`journalctl -k | grep -iE 'oops|list_del|corrupt|watchdog'`。
2. **OTA meta 也要處理。**
   - E17:dgx-spark-ota-update-meta 26.09.3 依賴 nvidia-spark-initcall-bl、nvidia-spark-grub-kho、nvidia-spark-grub-pci、nvidia-spark-run-apt-upgrade。
   - 如果有人從 DGX Dashboard 或 OTA 觸發,meta 會拉動 cmdline 與 kernel。
   - hold 清單應加上 `dgx-spark-ota-update-meta`。也要確認 hold 後對 meta 執行 `apt-get -s dist-upgrade` 不會因依賴把 hold 解掉。
3. **兩節點的 nvidia 模組封裝版本不一致,operator 沒發現。**
   - local 有 `linux-modules-nvidia-580-open-7.0.0-1019-nvidia` 可從 `+1` 升到 `+2`。
   - peer(10.100.184.1)的 hwe metapackage 顯示「可升級自 …+2」,代表 peer 已是 +2。
   - TP=2 兩端的 kernel module 封裝版本不同,差異內容 unverified。
   - 解決方式:`apt changelog linux-modules-nvidia-580-open-7.0.0-1019-nvidia`,以及兩節點各跑 `dpkg -l | grep linux-modules-nvidia-580` 與 `cat /proc/driver/nvidia/version`。
4. **initcall-bl 1.0-2 現在不該做。**
   - E14 #4 說的是「unstable with certain display」。我們的節點是否接顯示器 unverified。
   - dgk960 有 power_wrap_init 仍然凍結,所以它不是通用穩定修正。
   - 它需要改 cmdline 加重開機,屬於 kernel 級變更,必須是獨立 stage。只有在第 1 點查到 oops 或 list corruption 時才做。

### R6 jayleaton 2.8bpw

**判定:同意不切換。但 operator 的記憶體比較方式不成立。**

**關鍵證據**
- E15 #388:prose decode 慢 10–15%,而本地 decode gate 是 87.0 tok/s(E20),預期過不了 gate。
- E15 #388:600K prefill 快約 11%。
- E15 #386:high effort 162 對 162,max effort 一次一側,作者自己說 inconclusive。

**說錯的地方**
1. **記憶體數字不能這樣比。** 對方是「四個約 500K session 負載下」4.5 GiB 對 7 GiB。本地 3.97 GiB 是 idle 時的值(E17 local,E18 requests_running 0),而且本地設定是 parallel 8、2M window、2.0 GiB prompt cache。對方另有 4TB 加 1TB GX10 的硬體混搭(E15 #388)。
2. **「bpw 不同」這個混淆可以排除。** E15 #384 wolttam 的 patch 讓 jayleaton build 能載入 Mia 2.9bpw。如果要評估,同一 pack 的 A/B 是可行的。
3. **真正不切換的理由:** 換引擎等於丟掉 E3 全部 p17 移植。structured output 可以經 R4 取得,不需要換引擎。

### R7 watermark PSA

**判定:同意。**
- E17:min_free_kbytes=45166(約 44.1 MiB,即 E15 #381 說的預設約 45 MB)。
- local 的 MemAvailable 3.97 GiB 大於 MemFree 2.21 GiB,peer 是 5.85 大於 2.11。這符合 #381「on the kernel's own default it reads true」的描述。
- 補充:這同時表示 MemAvailable 在本機是可信的。R2c 改用 PSI 的理由是 scale-invariance,不是讀值錯誤。

### R8 #55 / #52 / Mia #139–#141

**判定:部分同意。**

**#55**
- 「0 ContextFull lines」要附上 log 涵蓋的期間。如果 rank0 log 只從 11-15 22:16 重啟後開始,樣本太短。屬 unverified。可看 log 首行時間戳與 `grep -c ContextFull`。
- 本地 lane_host 是否有 host-wide ContextFull hold 也 unverified。可跑 `grep -n ContextFull zig/src/core/lane_host.zig`。
- E11 #55 本身是 draft,「GPU and end-to-end inference validation are pending」,連 native build 都沒過。現在不移植。

**#52**
- operator 低估了它。E18 `/health` 顯示 `"cache": 0`,但 E20 說 prompt cache held 約 580 MiB。現有 telemetry 看不到 held 對 budget。這正是 E20 的調查(Node1 idle 可能再降約 1.5 GiB)缺的資料。
- 但它是 draft。可改為只移植最小部分:`prompt_cache.zig` 的 held/budget 讀出,屬觀測用途,但仍算一個 stage。

**Mia #139**
- 「host-memory admission floor」看標題像固定門檻,與 owner 規則衝突。
- 本地的 262249bf3 NVMe spill 是否等於 spill-v2 unverified。可比對 #139 改動的檔案與 `git log --oneline -- <spill 路徑>`。

**#140/#141**
- 屬容器與 build,與 native 部署(E4)無關。同意不適用。

## 2. 對「v1.2.9 值得合併」的最終判斷

**判斷:skip 整包。v1.2.9 本身目前也沒有值得 cherry-pick 的項目。**

- R2a 和 R2b 對 DSv4.1 沒有行為收益:R2b 的 template 不渲染,R2a 是觀測而且 parser 不同。
- R2c 未經 GB10 驗證,且不協調 TP。
- R2d 沒有需求。
- 真正有價值的上游工作來自 bertholomus `deepseek-v41-zig-tp2` 與 Mia 的 patch:#48–#50 structured output 與 #52 telemetry。這些與 v1.2.9 無關。

**會讓我改變判斷的具體證據(任一成立就重評)**
1. ashhart 的 release binary 正式服務 DeepSeek(#827 或其後繼 gate 合併,README 第 221 行改寫)。
2. 同一 Mia 2.9bpw pack 下,以 wolttam patch 跑 `deepseek_v41` family 的 A/B,在本地同時達到:
   - 30 題 bank ≥ 28/30;
   - decode gate ≥ 87.0 tok/s;
   - 1h marathon 不劣於 882/893;
   - Node1 MemAvailable 不低於現行。
   這等於證明可以換到上游 family。
3. 本地量測顯示 v1.2.9 某項通用(非 family)修正對應到一個生產中確實發生的錯誤,例如 proxy log 中出現對應的 500 或 hang。

## 3. 風險與緩解

**Kernel / OTA**

| 風險 | 緩解 |
|---|---|
| 只 hold kernel metapackages,但 dgx-spark-ota-update-meta 26.09.3 仍會經依賴改 grub(kho/pci/initcall),並帶入 run-apt-upgrade。 | 一併 hold meta。執行 `apt-get -s dist-upgrade` 確認沒有 kernel、grub 或 initcall 變動。 |
| 兩節點的 nvidia kernel module 封裝版本不一致(local +1,peer +2),是未解釋的不對稱。 | 先查 changelog。決定兩端對齊到同一版時,視為一個 stage(重開機加完整 regression)。 |
| initcall-bl 1.0-2 會改 cmdline 並需要重開機。TP=2 必須兩端都停機。 | 只有在 journal 查到 oops 才做。做法是先改 rank1 節點觀察開機與 RDMA ring,再改 rank0。回退方式是從 GRUB 選單移除 power_wrap_init。 |

**記憶體**
- 現況偏緊:local 節點 idle MemAvailable 3.97 GiB、swap 已用 0.68 GiB。prompt cache 往 2.0 GiB 成長,還會再吃約 1.5 GiB(E20)。
- 這時候疊上任何新功能都會擠壓 proxy 階梯。若以現行 3.8 GiB 基準計算,large prefill 並行度已經會被降級。
- 緩解:
  - 每個 stage 都記錄 Node1 MemAvailable 的最小值與 swap 增量。
  - 任何 stage 若讓 marathon 期間 Node1 最小值低於該 stage 前的基準,就判為負面。基準以相對比較,不設絕對值。

**品質**
- structured output 與 loop guard stop、DSML 串流(0048/0064/0065)、sampled MTP redraw 的交互作用,全都沒有在 GB10 上測過。
- 已知風險:
  - grammar 下 loop guard 截斷,會產生不合法 JSON 但回 200。
  - grammar 與 tool call 同時出現在一個請求時的行為不明。
- 緩解:驗收集必須包含「沒有 grammar 的請求 token_sha 與現行完全相同」。這是最強的保護,能證明不用 structured output 的流量零影響。

**effort 映射**
- `medium` 在 101 筆外部請求中的實際映射未知。
- 如果 proxy 把它映到 low(50),目前生產品質可能已經偏低,而且 30 題 bank 不一定能覆蓋到這種情況。

**規則違反**
- proxy 階梯的固定 GiB 門檻,以及 #51 和 #139 引入的固定 rows/floor,都與「no hardcoded thresholds」衝突。

## 4. 優先順序(8 項)

| # | 行動 | 驗收 | 回退 |
|---|---|---|---|
| 1 | 兩節點 `apt-mark hold` 四個 kernel metapackage 加上 `dgx-spark-ota-update-meta`。此項不改 runtime,不需要推論 regression。 | `apt-mark showhold` 列出 5 個套件。`apt-get -s dist-upgrade` 無 linux-*/grub/initcall 變動。`uname -r` 仍是 1019。 | `apt-mark unhold <pkgs>` |
| 2 | 只蒐集證據,不改設定:兩節點 `journalctl --list-boots`、`journalctl -k \| grep -iE 'oops\|list_del\|corrupt'`;比對 nvidia module +1/+2 的 changelog;確認 rank0 log 涵蓋期間與 ContextFull 計數。 | 產出一份報告,說明有無非預期重開、oops,以及 module 差異內容。依結果決定第 8 項做不做。 | 無(唯讀) |
| 3 | 實測 R3:在現行 p17 上跑 #51 的 `bench_concurrent.py` 同參數,並查 trail log 的 `add` 事件與 round 計數。同時查 `piece()` 的單位。 | 8 個短 prompt 的 `add` 落在同一 round:R3 結論成立,結案。若間隔一個 round:另開 stage 評估 drain 類改動,而且必須是無固定 rows 的版本。 | 無(唯讀) |
| 4 | 實測 effort 映射:thinking on 分別送 `low/medium/high/max/none`,記錄渲染後的 "Reasoning Effort: N",並對照 proxy 的改寫規則。 | 每個值都有明確的 N,且 `medium` 的映射是刻意設計的結果。若不是,另開 proxy stage 修正,並跑完整 regression。 | 無(唯讀) |
| 5 | 查清 36 筆 `dsml_in_content` 與 36 筆 `loop_period` 是否重疊(依 request id)。 | 有結論:屬 loop guard 問題,或屬 0064/0065 parser 問題。 | 無(唯讀) |
| 6 | Structured output stage A:移植 bertholomus #48(只有 library,無呼叫者)。用獨立 build prefix,rank1 binary 不換。 | 30 題 bank ≥ 28/30;decode gate ≥ 87.0 tok/s(在既有雜訊內);C2/C4/C8 不劣於 118.6/141.8/156.8;1h marathon 不劣於 882/893;Node1 MemAvailable 最小值不低於 stage 前。 | rank0.sh 的 binary 路徑改回現行 `out/native/bin`,重啟 rank0。 |
| 7 | Structured output stage B/C:移植 #49 json_object,通過後再移植 #50 schema,各自獨立 stage。 | 除第 6 項全部 gate 外,另需:<br>• 無 grammar 請求用 `tools/exact.py` 31 cases 得 IDENTICAL;<br>• T=0.30 sampled 下,drafted、`draft:false`、4 並發三者的 JSON 都合法,並記錄 redraw 造成的 tok/s 損失;<br>• thinking on;<br>• `loop_guard_stop` 加 grammar 的組合;<br>• tools 加 response_format 的組合;<br>• 原本那筆 MacBook 請求重放後回 200。 | 同第 6 項,回到前一個 stage 的 binary。 |
| 8 | 條件式:proxy 階梯加入 PSI avg10 作為主訊號,並用相對 MemAvailable 取代固定 GiB。先 shadow 24h,只記錄不動作。initcall-bl 1.0-2 只在第 2 項查到 oops 時做,另開 stage。 | shadow 期間記錄觸發次數與真實壓力事件(swap 增量、kswapd)的對應,誤觸發要接近 0。之後再切成 active,並跑完整 regression。 | proxy 設定切回舊階梯。initcall 從 GRUB 移除 power_wrap_init 後重開機。 |

#52(prompt cache held/budget telemetry)排在第 7 項之後,作為最小化移植的觀測 stage。v1.2.9 的任何項目都不在這份清單內。