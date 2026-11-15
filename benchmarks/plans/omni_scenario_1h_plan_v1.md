# OmniScenario-1h 修訂版 v1（併入 Opus 5.5 + GPT-6 Astra 審查）

日期：2026-11-15　對象：p17 生產配方（recipes v2b2-p17-loop-fallback / engine e772dec6 / proxy e2039614）
審查原文：`benchmarks/results/plan_review_omni_scenario_1h/{anthropic_claude-opus-5-5.md, gpt-6-astra.md}`，資料包 `dossier.md`。

定位（照審查改名）：**1 小時有界的發版回歸 + 真實流量形狀壓力測試**，不是「零盲區」。不涵蓋的項目列在第 8 節。

## 0. 審查意見核對（我對照原始碼確認過，非照單全收）

| 審查說法 | 核對結果 | 依據 |
|---|---|---|
| medium 會被併成 high 或 low（兩位都說要實測） | **兩位都錯**：DSv4.1 有自己的數字表，不走 coerce 合併。minimal 25 / low 50 / medium 62 / high 75 / xhigh 88 / max 100；none 關思考；不指定 = 模板預設 high 75 | `families/dsv41/text.zig` efforts；`server.zig:108` 有 Info.efforts 時每個名稱原樣傳、渲染成數字 |
| xhigh 會讓模板報錯（Opus） | **錯**：送進模板的是整數 88，模板接受 1..100 整數 | 同上 + `hf_text.zig` reasoning_effort_value |
| 整數 effort 25/50 經 API 會被擋 | **對**：`thinkingFields` 只收 7 個字串 → 400 | `fields.zig:213` |
| proxy 與 engine 的思考開關判斷不一致 | **對**：proxy 只看 `chat_template_kwargs.enable_thinking`，engine 另認 `thinking` 別名。`{max_tokens:120, thinking:true}` → proxy 改寫 effort=none，engine 又因別名開思考、effort 清空 → 用預設 high 在 120 token 內思考 | `proxy.py:976–997`、`fields.zig:204–221` |
| `--keep-last-n-reasoning 2` 不在配方 | **錯**：rank0.sh 有 `--drop-reasoning-history --keep-last-n-reasoning 2`，線上 cmdline 確認啟用 | `scripts/rank0.sh:14`、`/proc/<pid>/cmdline` |
| 模板有工具時保留全部思考、無工具時丟棄 | **對**：`drop_thinking = not tools`；與 engine 的 keep-last-2 前處理疊加，順序要驗 | `chat_template.jinja:36,182` |
| loop fallback 1 小時內幾乎不會自然觸發，100% 門檻會空轉 | **對**：39 h 外部流量 0 次觸發、影子偵測 4 次 | audit log |
| 基準檔名是 p16 | 檔名歷史沿用；`omni_eval_1hour_p16_tokenmapfix_loopfallback.json` 就是 p17 發版回歸那次（engine af133ae9 + loop fallback）。但該視窗有外部流量 16 筆 / 805 s busy，另一次 pr138 有 14 筆 / 357 s | `loopfallback_regression_20261115/runner.log` + audit |
| 標準馬拉松（893 筆的 1 h）與新場景不能同在 1 小時 | **對**：標準馬拉松本身就占滿 1 小時。本計畫只放標準前段（full_eval A–D + OmniBench 六面向），要比馬拉松需另跑 1 小時 | — |

## 1. 開跑前（不計時，T-20 → 0）

- 狀態：/health、manifest sha（rank0 / rank1 / proxy）、雙機容器、Imprint 狀態數·總量·NVMe 剩餘、雙機 MemAvailable / swap、`SPARK_PROXY_LOOP_FALLBACK` 與 effort 值。
- 外部流量：**整小時暫停 MacBook 客戶端**，並持續監看兩邊 log（engine 非 127.0.0.1、proxy journal），任何外部請求都標注該時窗。
- 追蹤 ID：每筆請求帶 `X-Test-Id`，串起 client → proxy audit → engine `done` 行。
- **閒置安全單發（任一出 500 / BadSlot / follow_refused / 任一節點 MemAvailable < 6 GiB 就中止整場）**：
  1. 整數 effort（25）→ 400，槽位未占。
  2. xhigh → 200，engine log 顯示 effort 88。
  3. 超過上下文（prompt+max_tokens > 1M）→ 4xx。
  4. 壞 JSON → 400。
  5. 32K prefill 中途取消 → 槽位釋放時間、雙機無錯。
  6. 100K prefill 中途取消 → 同上（量測取消要多久才真的釋放，作為主負載 S7 的門檻依據）。
  7. 220K 冷預填 1 筆 → 雙機記憶體曲線、TTFT。
- 試跑（先做一次 5 分鐘縮小版）：驗判定邏輯、量出各場景單筆占槽秒數，用來定交付率門檻與 in-flight token 預算。

## 2. 時間表（絕對時間，整場 60 分）

| 時間 | 內容 |
|---|---|
| 00:00–01:30 | OmniBench standard 六面向前段（順序、設定、nonce 慣例與 p17 相同）— **可與 p17 對照的區塊** |
| 01:30–07:00 | `run_full_eval.py`：Part A 30 題、B、C（含 429 階梯）、D1–D4 |
| 07:00–08:30 | 思考 M1：入口與優先順序（直連 :8888、greedy、max_tokens ≥ 300、各 1 次），以 engine log 的 effort 值 + reasoning 是否出現判定 |
| 07:00–15:00（並行 1 worker） | 思考 M5：10 輪工具鏈（字串型 arguments、平行工具結果、歷史帶 reasoning_content），逐輪記錄 cached_tokens |
| 07:00–15:00（並行 1 worker） | 思考 M6：迴圈誘發 ×3（串流 / 非串流），經 :8889 |
| 08:30–11:30 | 思考 M2：4 題 × {none, minimal, low, medium, high, xhigh, max} × 1，max_tokens 2048（觀察思考長度），看圖 × {none, high} |
| 11:30–15:00 | 思考 M3：proxy 改寫邊界與別名衝突；M4：tool_choice × effort；thinking_budget {0, 1024} × 有/無工具 |
| 15:00–52:00 | 主負載：閉環 N=7、只用 P1/P2（P0 留給探針與突發中的 P0），第 3 節權重 |
| 每 60 s | P0 探針（短問）→ 記 TTFT（約 36 筆） |
| 19:00 | 突發 1：先確認系統已滿，再開環送 16 筆 P2 + 2 筆 P0（50 ms 內） |
| 22:00 | 220K 冷長上下文藏針（nonce 放第一行）；期間暫停 S1 冷啟動 |
| 27:00 | 迴圈誘發 ×3（僅在 M6 觸發 < 3 次時） |
| 31:00 / 34:00 | 100K prefill 取消，依序（prefill 開始後 20 s、40 s） |
| 38:00 | S1 長對話 A 回訪（先由快取指標確認已被擠出 RAM） |
| 41:00 | 突發 2：P0/P1/P2 混合 |
| 47:00 | S1 長對話 B 回訪 |
| 52:00–55:00 | 停止新請求、排空；55:00 仍在跑的取消並標記截斷 |
| 55:00–60:00 | 靜置 30 s 後：CLOSE_WAIT、雙機記憶體、Imprint 快照；5 筆閒置 P0 探針；32K 插隊（帶 nonce，僅觀察） |
| 結束後（不計時） | 冷卻 2 分 → `run_decode_gate.py --reps 3`，與本場 00:00 區塊的解碼值比 |

## 3. 主負載權重（N=7 閉環，按真實流量形狀，屬覆蓋性負載而非重播）

| 代號 | 場景 | 權重 | 設定 |
|---|---|---|---|
| S1 | Agent 工具迴圈 | 40% | 工具 4–6 個（mock 執行，不碰真系統）；effort high/medium/low；對話逐輪加長到 ~105 則；max_tokens 不指定 31% / 32768 14% / 3000；字串型 arguments、平行呼叫、歷史帶思考；長對話總數限 4–6 個（避免擠掉外部使用者的 Imprint 快取） |
| S2 | 指定工具 + low | 15% | tool_choice=function、effort low、max_tokens 3000；記錄「整段思考、無呼叫」比例（列 xfail，見第 5 節） |
| S3a | 短問（會被改寫） | 8% | max_tokens 120、effort low、無工具 → proxy 應改寫成 none |
| S3b | 短問（不改寫） | 7% | max_tokens 120、effort low、帶工具 → 記錄 finish=length 且無內容的比例 |
| S4 | 程式碼審查（舊馬拉松流量） | 10% | 只比單筆正確性，不比延遲 |
| S5 | 多輪看圖 | 5% | 顏色象限可自動判；Turn 2 快取命中 |
| S6 | 長推理 | 5% | 固定 1 個 worker、max_tokens 4K–8K、有標準答案；429 有上限重試（最多 2 次），首試與重試分開記 |
| S7 | 中途取消 | 10% | 取消點：排隊中 / prefill 中 / 思考中 / 內容中 / 工具參數串流中；取消後該 worker 空 10 s 讓釋放可觀測 |

- 長上下文用 **in-flight token 預算**（prompt + max_tokens 總和）控管，含插入事件；額度由試跑時兩台的 MemAvailable 決定。不指定 max_tokens 的請求在試跑確認引擎行為前先設上限。
- 迴圈率改用全部帶思考請求（約 250 筆）+ 影子偵測計算，不只看 S6。

## 4. 思考矩陣（修正後的預期值）

M1 入口與優先順序（直連 :8888，避開 proxy 改寫干擾）：

| 請求 | 預期 |
|---|---|
| effort = none / minimal / low / medium / high / xhigh / max | 思考 off / 25 / 50 / 62 / 75 / 88 / 100（engine log 驗） |
| 不指定 effort、思考開 | 75（模板預設 high） |
| effort 整數 25、`"abc"` | 400 |
| effort=none + enable_thinking=true | 思考開、effort 清空 → 75 |
| effort=high + enable_thinking=false | 思考關 |
| 只給 `chat_template_kwargs.thinking`（無 enable_thinking） | 依別名開/關 |
| enable_thinking 存在（即使 false）+ thinking=true | 以 enable_thinking 為準 |
| 頂層 effort 與 kwargs effort 同時存在 | 頂層優先 |
| chat_template_kwargs 為字串 / `{}` | kwargs 內欄位全忽略 |

M3 proxy 改寫（經 :8889）：
- max_tokens 255 / 256 / 257、0、負數、布林、不給；`max_completion_tokens` 只在 max_tokens 缺時生效。
- tools 不給 / `[]` / 非空；enable_thinking true / false / 不給；effort 只放在 kwargs。
- **別名衝突（已確認的實際缺陷）**：`thinking:true` + max_tokens 120 → 預期會在 120 token 內思考而截斷；`thinking:false` → proxy 仍掛 loop fallback。此格列 xfail 並記錄，是否修 proxy 另議。
- 已自帶 `loop_guard_stop`（含 false）→ 不掛 fallback。

M4 tool_choice × effort：{auto, required, function, none} × {low, high}，max_tokens 3000。required/function 會被改寫成 auto，所以「一定要呼叫工具」不能當協定門檻；呼叫與否記為任務層結果。tool_choice=none 時 content 不得出現 DSML。

M5 思考歷史：用哨兵字串驗證，有工具時歷史思考是否保留、無工具時是否丟棄，engine keep-last-2 與模板規則疊加後的實際結果；逐輪 cached_tokens 邊界要符合預期。

M6 迴圈防護：生產 proxy 上用已知迴圈題誘發（觀察用）；**另起一個測試用 proxy 實例（不同埠）接假 upstream，確定性地回 reasoning_loop**，驗：重送帶 effort none + enable_thinking=false、去掉 thinking_budget、保留 tools、不帶 loop_guard_stop、最多重送 1 次、客戶端已斷線時不再重送、串流不重複不矛盾、非串流只回一份完整回應。

thinking_budget：{0, 1024} × 有/無工具。有工具時強制收尾轉去叫工具是已知缺陷 → xfail 記錄比例。

移出這 1 小時（另排）：effort 對正確率的統計比較（AIME/GSM8K）、`/v1/responses` 與 `/v1/messages`（39 h 真實流量 0 筆）、600 s 非串流逾時、解析器窮舉單元測試。

## 5. 門檻

硬門檻（任一不過＝不通過）：
- 閒置安全單發全部符合預期。
- 30 題：不低於 p17 同題庫分數 −1（p17 為 28/30，temperature 0 + seed 42 可重現）。
- 引擎層錯誤 = 0：5xx、200 但串流截斷、DSML 漏進 content、工具參數無法解析、BadSlot、follow_refused、OOM、panic、/health 非 ok。
- 有效交付（定義：串流以 finish_reason + [DONE] 結束；finish 為 stop / tool_calls，或該格預期的 length；有內容或工具呼叫；工具參數可解析且名稱存在；fallback 有最終答案）：分母排除 S7、刻意超載的突發、xfail 格；門檻值由試跑定。
- 429 分類：佇列滿的 429 在 proxy 端 ≤ 10 ms（client 端 p99 ≤ 50 ms）且帶 Retry-After；佇列逾時的 429 依階梯 4–25 s，分開計。
- 突發中預留槽位可用時 P0 被拒 = 0。
- M1 每格 engine log 的 effort / 思考狀態與第 4 節預期一致。
- 迴圈 fallback：確定性注入 ≥ 3 次且全部成功；生產端未觸發時標「未測到」，不算通過也不算失敗。
- 取消：槽位釋放時間 ≤ 閒置試跑量到的值 + 餘裕；結束時測試自己的連線 CLOSE_WAIT = 0（靜置 30 s 後）。
- 雙機 MemAvailable：低於 4 GiB 中止；全程 ≥ 3 GiB；swap 不增長。
- 長跑後解碼：3 次中位數 ≥ 本場起始值的 95%。
- 與 p17 對照（前段區塊，差距 > 雜訊範圍 2 倍視為退步訊號）：8K 冷預填 2235–2242 tok/s（±0.3%）、8K 快取 TTFT 0.908–0.926 s、greedy 89.5–90.5、sampling 71.5–72.6、C1/C2/C4（±2.3%）、32K 插隊 0.744–0.780 s。

xfail（記錄比例，不擋發版）：S2 整段思考無呼叫（真實約 11%）、thinking_budget 收尾轉叫工具、proxy 別名衝突。

觀察（首跑建立基準）：GPU 時脈分布、各場景 TTFT/wall、cached 比例、思考長度隨 effort 的趨勢、看圖正確率、針題命中、S6 正確率、P0 TTFT p95。

## 6. 中止開關

任一節點 MemAvailable < 4 GiB、swap 增長、BadSlot / follow_refused / OOM / panic、engine /health 連續 5 s 非 ok → 停止送新請求、取消進行中的測試請求、保留全部 log；不自動重啟生產。

## 7. 可比 / 不可比

- 可比：第 2 節 00:00–01:30 區塊與 full_eval 各項（同順序、同設定、外部流量已暫停）。
- 不可比：總請求數、200 率、整體 TTFT / wall 分布、產出與快取 token 數、迴圈率、結尾的 32K 插隊、記憶體（p17 沒有紀錄）。S4 只比單筆正確性。
- 要比 1 小時馬拉松（893 筆那種）→ 另排 1 小時跑原 `run_omni_eval.py --profile standard --duration 3600`。

## 8. 不涵蓋（需重啟或屬另一類測試）

rank0 重啟後冷池回呼、rank1 故障注入、開機自癒、effort 正確率統計 A/B、/responses 與 /messages 端點、600 s 逾時、5 小時耐久。

## 9. 實作

- `benchmarks/run_omni_scenario_1h.py`：場景、時間表、門檻常數在檔頭；追蹤 ID；中止開關。
- `benchmarks/omni_scenario_telemetry.py`：雙機 1 Hz（docker logs 用單一 follower，不重複全量讀）。
- `benchmarks/mock_loop_upstream.py` + 測試 proxy 實例：迴圈 fallback 確定性驗證。
- 報告：`results/omni_scenario_1h_<ts>.json` + 每場景摘要 + 門檻判定。
