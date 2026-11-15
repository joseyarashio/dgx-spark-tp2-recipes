# 1 小時全方位場景測試（OmniScenario-1h）草案 v0

日期：2026-11-15　對象：p17 生產配方（recipes v2b2-p17-loop-fallback / engine e772dec6）

## 0. 為什麼要新測試（現有 1h 馬拉松的盲區，均已用實際資料核對）

資料來源：`~/.cache/spark-proxy-audit/completions.jsonl` 外部流量 387 筆（2026-11-13 21:26 ~ 11-15 12:29，385 筆來自 MacBook 100.108.5.82），對照 `run_30min_stress_experiment.py` 的流量組成。

| 面向 | 真實流量 | 現有馬拉松 | 盲區 |
|---|---|---|---|
| 工具 | 269/387 帶 tools，188 筆回 tool_calls | 0 | 工具呼叫完全沒壓到 |
| 上下文 | prompt p50 16.5K、p90 113K、max 220K（只計有回報 prompt_tokens 的筆數）；>50K 共 123 筆，快取命中 81–99% | 最長約 22K | 100K–220K 長上下文 + 長對話（p90 107 則訊息）沒測 |
| 輸出長度 | max_tokens 3000 / 32768 常見 | 256–512 | 長回覆的迴圈、思考爆量測不到 |
| 思考控制 | reasoning_effort low/medium/high/none | 只有 enable_thinking 開關 | effort 路徑、loop fallback 在負載下沒觸發（上次 1h 視窗 loop_fallback=0） |
| 指定工具 | tool_choice=function 94 筆（proxy 改寫成 auto） | 0 | 實際看到 low+指定工具有 10 筆跑滿 3000 token 全是思考、沒呼叫工具 |
| 中途斷線 | client_left 45 筆 | 0 | 取消時槽位釋放、連線殘留沒測 |
| 內容正確性 | — | 只算 HTTP 200 | 答錯、亂呼叫工具也算成功 |
| 突發 | — | 閉環 N=8 | 閉環會遮住 429 fast-fail 行為 |

## 1. 時間表（總 60 分鐘，前後準備不計入）

- T-10 預檢（不計時）：/health、manifest sha（rank0/rank1/proxy）、雙機容器、Imprint 狀態數與總大小、外部流量閒置 90 s 守門、啟動 1 Hz 遙測。
- 00–07 標準測試全套（與歷次發版同一套，可直接對照 p17）：
  - `run_full_eval.py`（約 5.3 分）：Part A 30 題、Part B 單流解碼 / 冷預填 8K·32K / 插隊、Part C C1/C2/C4/C6 + 429 階梯、Part D D1–D4。
  - OmniBench standard 六面向前段（約 1 分）：品質 4 題、工具 required/auto、8K 冷/熱預填、看圖 Scratch Arena、greedy/sampling、C1/C2/C4、32K 插隊、CUDA Graph / NVMe 狀態。
- 07–19 思考矩陣 12 分鐘（第 2b 節，固定 seed、可重現，N=8）。
- 19–55 主負載 36 分鐘：閉環 N=8 混合場景（第 2 節）＋定時插入事件（第 3 節）。S4 子集即舊馬拉松流量，可與 p17 同類別對照。
- 55–60 收尾：P0 探針、32K 插隊（帶 nonce，冷快取）、雙機 MemAvailable / swap / CLOSE_WAIT。
- 之後（不計時）：`run_decode_gate.py --reps 1`，確認長跑後解碼沒有退化。

## 2. 主負載場景（權重依真實流量比例，N=8 閉環）

| 代號 | 場景 | 權重 | 設定 | 判定 |
|---|---|---|---|---|
| S1 | Agent 工具迴圈（OCX / Claude Code 型） | 30% | tools 4–6 個（read_file / bash / edit_file / search），effort high/medium，對話 20–100 則逐輪加長，prompt 30K–200K，前綴共用 | tool_calls 可 JSON 解析、名稱存在於 schema、必填參數齊全；可判定題目檢查是否叫對工具；cached_tokens 比例 |
| S2 | 指定工具 + low | 10% | tool_choice=function、effort low、max_tokens 3000 | 200 且有 tool_calls；記錄「跑滿 3000 全思考無呼叫」比例（已知問題，先量不設門檻） |
| S3 | 短問 | 15% | effort none、max_tokens 120、P0 | TTFT、非空內容 |
| S4 | 程式碼審查（沿用馬拉松 HIGH_HIT/LOW_HIT） | 20% | 2K–22K，max_tokens 256–512 | 與舊馬拉松同類別對照用 |
| S5 | 多輪看圖 | 10% | 沿用測試圖（四色象限＋中央棋盤） | 回答中顏色象限是否正確（可自動判）；Turn 2 快取命中 |
| S6 | 長推理 | 8% | effort high、max_tokens 8K–16K、有標準答案（GSM8K 難題 / AIME 子集） | 正確率、loop_rate、loop_fallback 觸發與接續成功率；429 改為重試直到回答 |
| S7 | 中途斷線 | 5% | 串流開始後 1–30 s 隨機斷開（含 prefill 中斷） | 5 s 內 proxy active_running 回落、engine connections 回落、無 CLOSE_WAIT 累積 |
| S8 | 非串流 | 2% | stream=false | 200 且內容完整 |

長上下文同時進行數上限 2（真實流量也是如此），避免超出 KV pool；超過時該 worker 改抽其他場景。

主負載內所有帶思考的請求，effort 依真實比例抽樣：low 40% / high 30% / medium 15% / none 15%（不再只用 enable_thinking 開關）。

## 2b. 思考矩陣（07–19 分，固定 seed，每格判定答案）

對照碼與模板：engine `fields.zig` 接受 none / minimal / low / medium / high / xhigh / max；1017 的 `chat_template.jinja` 只認 low / high / max（或 1–100 整數，預設 high）。`coerceEffort` 取最近一級、同距取高：minimal→low、medium→high（近 6h engine log 只見 high/low/none，沒有 medium，與此一致）、xhigh 原樣傳入模板（行為未知，要測）。所以這段**同時驗「實際有幾級」**：7 個名稱應只產生 none/low/high/max 四種思考行為，用思考 token 長度與 engine log `done ... effort=` 確認，並加測整數 effort（25/50/75/100）。不能只看有回 200。

| 軸 | 測試值 | 判定 |
|---|---|---|
| 開關入口 | `reasoning_effort` / `chat_template_kwargs.enable_thinking` / `chat_template_kwargs.thinking` / Anthropic `thinking.type` disabled·enabled·adaptive / `output_config.effort` | 各入口實際思考狀態一致；enable_thinking=true + effort=none 衝突時依程式規則；非法值回 400 |
| effort 7 級 | none, minimal, low, medium, high, xhigh, max | 思考長度單調（同題 3 seed 中位數）、engine log effort 對應正確、答案正確率 |
| thinking_budget | 0、256、1024、4096（搭配 max_tokens 8K） | 預算觸頂時 `</think>` 被強制插入；**有 tools 時是否轉去亂叫工具**（已知未處理：thinkCut → 工具），無 tools 時內容是否完整；DSML 不漏進 content |
| 思考歷史 | 多輪 10 輪帶 reasoning_content；server 端 `--keep-last-n-reasoning 2` | 第 3 輪前的思考確實被丟、近 2 輪保留；tool loop 不斷鏈；快取命中不因丟棄而崩 |
| 端點 | `/v1/chat/completions`、`/v1/responses`、`/v1/messages`（Anthropic） | 三端點思考輸出位置正確（reasoning_content / reasoning item / thinking block） |
| 串流 | stream true / false | 兩者思考內容一致；非串流長思考 600 s 逾時邊界記錄 |
| 短輸出改寫 | max_tokens ≤ 256 + effort low（無 tools、未明確 enable_thinking=true） | proxy 改寫成 none 並記錄 `effort_rewritten`；有 tools 或 >256 不改寫 |
| 迴圈防護 | 已知迴圈題 × effort low/medium/high | loop_guard 觸發 → proxy 用 none 重送並接續；串流/非串流都驗；`SPARK_PROXY_LOOP_FALLBACK` 現值記錄 |
| 思考 + 工具 | effort × tool_choice（auto / required→auto / 指定 function / none） | tool_calls 合法；none 時不得出現 DSML 文字；真實流量已見 low+指定 function 有 10 筆 3000 token 全思考無呼叫 → 這格量比例 |
| 思考 + 看圖 | 看圖題 × effort none/low/high | 思考開啟時看圖答案仍正確、Turn 2 快取命中 |
| 思考品質 | GSM8K 難題 / AIME 子集 × none/low/high | 正確率隨 effort 的差距（none 可能明顯較低，量化用） |

樣本估算：12 分鐘約 120–160 筆。每格 2–3 seed，屬功能與分級驗證，不足以作 effort 間正確率的統計結論（那要另跑 tool-eval-bench 配對 A/B）。

## 3. 定時插入事件（主負載中執行，記錄前後 60 s 指標）

- 每 5 分鐘：P0 互動探針（短問）→ TTFE ≤ 1.0 s。
- 第 12 分鐘：開環突發 16 筆同時送入 → 超出容量的要在 < 10 ms 回 429 + Retry-After，P0 不得被拒。
- 第 20 分鐘：220K 冷長上下文 + 藏針題 → 答對、TTFT 記錄、MemAvailable 不跌破 3.0 GiB。
- 第 28 分鐘：已知會迴圈的提示（取自 run_loop_guard_probe）×3 → loop_fallback 在負載下觸發且接續成功。
- 第 36 分鐘：100K prefill 中途斷線 ×2 → 槽位釋放、後續請求不受影響。
- 第 44 分鐘：第二次開環突發（16 筆，混 P0/P2）。
- 第 50 分鐘：同一 S1 長對話隔 20 分鐘後回訪 → 檢查 RAM 擠出後是否從 NVMe（Imprint）讀回。

不納入（需要重啟、會中斷服務）：rank0 重啟後的冷池回呼、rank1 故障注入、開機自癒。這些另排，不混進 1 小時。

## 4. 遙測（1 Hz，雙機）

GPU clock / 溫度 / 功率、MemAvailable、swap、proxy `/proxy/status`（active、queue、bg）、engine `/health` live、`/metrics`（MTP 接受率、prefill/decode）、`ss` CLOSE_WAIT 數、docker logs 錯誤關鍵字（BadSlot、follow_refused、MissingTritonVariant、OOM、panic）、外部 IP 請求數（engine log + proxy journal 兩邊）。

## 5. 通過門檻（預先宣告）

硬門檻（任一不過＝不通過）：
- 30 題 ≥ 28/30。
- HTTP 500 = 0、OOM = 0、BadSlot / follow_refused = 0、engine 仍 ok。
- 有效交付率（200 且 valid_delivery，不只看 200）≥ 98%（S7 斷線除外）。
- S1 工具呼叫格式合法率 = 100%；DSML 漏進 content = 0。
- 開環突發：fast-fail < 10 ms；P0 被拒 = 0；P0 探針 TTFE ≤ 1.0 s。
- MemAvailable（Node 1）全程 ≥ 3.0 GiB；swap 不增長。
- GPU clock ≥ 2350 MHz 的時間 ≥ 95%（負載時段）。
- S7 斷線後 5 s 內槽位歸還，結束時 CLOSE_WAIT = 0。
- 長跑後 decode gate 通過（≥ 95% 基準）。
- 思考：所有入口與端點的思考開關結果一致；非法 effort 回 400；短輸出改寫只在規則內觸發；迴圈防護觸發後重送接續成功率 100%；effort=none 或 tool_choice=none 時 DSML 漏進 content = 0。

觀察指標（首跑建立基準，不設門檻）：
- 各場景 TTFT p50/p95、wall、cached_tokens 比例、每小時完成數。
- S2「全思考無呼叫」比例、S6 正確率與 loop_rate、S5 看圖正確率、針題命中。

## 6. 已知限制（先講清楚）

- 首跑沒有可比的歷史基準：流量組成不同，不能拿來跟 p17 的 882/893 比。若需要對照，S4 子集可和舊馬拉松同類別比，或另跑一次舊馬拉松。
- 樣本數：預估 1 小時約 400–600 筆（長上下文會壓低數量）。S6 約 30–45 筆，0 迴圈時 95% 上界仍有約 7–10%；S7 約 20–30 筆。要更強結論需重跑或加長。
- Imprint 快取狀態會影響結果：開跑前記錄狀態數與年齡，報告標註暖/冷。
- 外部流量：MacBook 在 0–3 點、10–13 點最活躍，5–9 點近兩天為 0。建議 05:00 開跑，或先暫停 MacBook 客戶端；被污染的樣本標為不確定。

## 7. 實作

- 新腳本 `benchmarks/run_omni_scenario_1h.py`（重用現有 SSE 解析；場景、事件時間表、門檻寫在腳本頂端常數）。
- 遙測 `benchmarks/omni_scenario_telemetry.py` 背景執行，輸出 jsonl。
- 報告 `benchmarks/results/omni_scenario_1h_<ts>.json` + 每場景摘要 + 門檻判定。
- 先做 5 分鐘縮小版試跑（每場景至少 2 筆、事件縮短間隔），確認判定邏輯正確才排正式 1 小時。
