# External Audit Report: Phase 1: Long-Context Tool-Open Controls

## Local Computed Stats
```json
[
  {
    "arm": "A2_base",
    "ok": 36,
    "total": 36,
    "errors": {},
    "finish_counts": {
      "tool_calls": 36
    },
    "empty_content_no_tc": 0,
    "tool_call_reqs": 36,
    "undeclared_tc_reqs": 0,
    "dsml_in_content_reqs": 0,
    "loop_r": 0,
    "loop_r_periods": [],
    "loop_c": 0,
    "loop_c_periods": [],
    "engine_loop_fired": 0,
    "ge4k": 0,
    "ge8k": 0,
    "ge16k": 0,
    "prompt_tokens_p50": 86070,
    "cache_hit_median": 0.9825,
    "comp_p50": 166,
    "comp_p90": 321,
    "comp_max": 763,
    "reas_p50": 108,
    "reas_p90": 246,
    "reas_max": 623,
    "cont_p50": 57,
    "cont_p90": 94,
    "cont_max": 140,
    "ttft_p50": 37.918,
    "ttft_p90": 65.135,
    "wall_p50": 49.67,
    "wall_sum": 1783.2
  },
  {
    "arm": "K1_kn1",
    "ok": 36,
    "total": 36,
    "errors": {},
    "finish_counts": {
      "tool_calls": 36
    },
    "empty_content_no_tc": 0,
    "tool_call_reqs": 36,
    "undeclared_tc_reqs": 0,
    "dsml_in_content_reqs": 0,
    "loop_r": 0,
    "loop_r_periods": [],
    "loop_c": 0,
    "loop_c_periods": [],
    "engine_loop_fired": 0,
    "ge4k": 0,
    "ge8k": 0,
    "ge16k": 0,
    "prompt_tokens_p50": 85960,
    "cache_hit_median": 0.9841,
    "comp_p50": 168,
    "comp_p90": 395,
    "comp_max": 512,
    "reas_p50": 57,
    "reas_p90": 311,
    "reas_max": 415,
    "cont_p50": 76,
    "cont_p90": 141,
    "cont_max": 186,
    "ttft_p50": 32.012,
    "ttft_p90": 50.446,
    "wall_p50": 39.66,
    "wall_sum": 1516.9
  },
  {
    "arm": "K0_kn0",
    "ok": 36,
    "total": 36,
    "errors": {},
    "finish_counts": {
      "tool_calls": 36
    },
    "empty_content_no_tc": 0,
    "tool_call_reqs": 36,
    "undeclared_tc_reqs": 0,
    "dsml_in_content_reqs": 0,
    "loop_r": 0,
    "loop_r_periods": [],
    "loop_c": 0,
    "loop_c_periods": [],
    "engine_loop_fired": 0,
    "ge4k": 0,
    "ge8k": 0,
    "ge16k": 0,
    "prompt_tokens_p50": 85847,
    "cache_hit_median": 0.985,
    "comp_p50": 131,
    "comp_p90": 260,
    "comp_max": 307,
    "reas_p50": 39,
    "reas_p90": 132,
    "reas_max": 208,
    "cont_p50": 73,
    "cont_p90": 140,
    "cont_max": 141,
    "ttft_p50": 18.312,
    "ttft_p90": 55.434,
    "wall_p50": 34.1,
    "wall_sum": 1550.1
  },
  {
    "arm": "A1_base",
    "ok": 36,
    "total": 36,
    "errors": {},
    "finish_counts": {
      "tool_calls": 36
    },
    "empty_content_no_tc": 0,
    "tool_call_reqs": 36,
    "undeclared_tc_reqs": 0,
    "dsml_in_content_reqs": 0,
    "loop_r": 0,
    "loop_r_periods": [],
    "loop_c": 0,
    "loop_c_periods": [],
    "engine_loop_fired": 0,
    "ge4k": 0,
    "ge8k": 0,
    "ge16k": 0,
    "prompt_tokens_p50": 86070,
    "cache_hit_median": 0.9829,
    "comp_p50": 166,
    "comp_p90": 321,
    "comp_max": 763,
    "reas_p50": 108,
    "reas_p90": 246,
    "reas_max": 623,
    "cont_p50": 57,
    "cont_p90": 94,
    "cont_max": 140,
    "ttft_p50": 12.914,
    "ttft_p90": 66.969,
    "wall_p50": 31.82,
    "wall_sum": 1468.0
  },
  {
    "arm": "E_max",
    "ok": 36,
    "total": 36,
    "errors": {},
    "finish_counts": {
      "tool_calls": 36
    },
    "empty_content_no_tc": 0,
    "tool_call_reqs": 36,
    "undeclared_tc_reqs": 0,
    "dsml_in_content_reqs": 0,
    "loop_r": 0,
    "loop_r_periods": [],
    "loop_c": 0,
    "loop_c_periods": [],
    "engine_loop_fired": 0,
    "ge4k": 0,
    "ge8k": 0,
    "ge16k": 0,
    "prompt_tokens_p50": 86070,
    "cache_hit_median": 0.0,
    "comp_p50": 165,
    "comp_p90": 348,
    "comp_max": 638,
    "reas_p50": 109,
    "reas_p90": 224,
    "reas_max": 498,
    "cont_p50": 57,
    "cont_p90": 140,
    "cont_max": 303,
    "ttft_p50": 54.173,
    "ttft_p90": 90.56,
    "wall_p50": 84.29,
    "wall_sum": 3097.7
  },
  {
    "arm": "B16_tb16k",
    "ok": 36,
    "total": 36,
    "errors": {},
    "finish_counts": {
      "tool_calls": 36
    },
    "empty_content_no_tc": 0,
    "tool_call_reqs": 36,
    "undeclared_tc_reqs": 0,
    "dsml_in_content_reqs": 0,
    "loop_r": 0,
    "loop_r_periods": [],
    "loop_c": 0,
    "loop_c_periods": [],
    "engine_loop_fired": 0,
    "ge4k": 0,
    "ge8k": 0,
    "ge16k": 0,
    "prompt_tokens_p50": 86070,
    "cache_hit_median": 0.983,
    "comp_p50": 166,
    "comp_p90": 321,
    "comp_max": 763,
    "reas_p50": 108,
    "reas_p90": 246,
    "reas_max": 623,
    "cont_p50": 57,
    "cont_p90": 94,
    "cont_max": 140,
    "ttft_p50": 11.446,
    "ttft_p90": 50.297,
    "wall_p50": 32.63,
    "wall_sum": 1278.4
  }
]
```


## Reviewer: anthropic/claude-fable-5-2 (ok=True, finish=stop, wall=121.5s)

**總評:本輪唯一站得住的是「工具呼叫格式在約 86K 上下文未出錯」與「K0 會縮短 reasoning」;E_max、B16 與所有延遲比較,都不足以支持上線決策。**

## (1) 實驗方法與數據盲點

- **A/A 只量到時間噪音,沒量到取樣變異。** A1、A2、B16 的 `comp/reas/cont` 各分位完全相同(166/321/763、108/246/623、57/94/140),配對差 `ci95=[0,0]`,即同 seed 下輸出可重現。216 列中獨立生成至多 144 筆,每個對話只有一個 seed。
- **時間噪音地板極大。** 同配置的 A2 與 A1,`ttft_p50` 為 37.918 對 12.914,`wall_sum` 為 1783.2 對 1468.0(約 +21%),`ttft_s` 的 A/A `ci95=[-4.92, 23.29]`。B16 輸出相同,`wall_sum` 卻是 1278.4。TTFT 的定義(首個 reasoning 或首個 content token)在節錄中也看不到。
- **快取狀態未受控。** 各臂隨機交錯,共用同一 `salt` 前綴,先跑者替後跑者暖快取。`cache_hit_median` 看不出各臂有幾筆冷啟動,也沒有執行順位欄位。`TF_LEARN_TTL_S=0` 加上支援 resume,先前執行可能已預熱。
- **E_max 的 `cache_hit_median=0.0` 是設計造成的混淆。** 其他臂約 0.983–0.985,而 `prompt_tokens_p50` 同為 86070。每個對話只有一筆 max,若 effort 會改變前綴或快取鍵,它必然是冷的。它的整段 prefill 在 `CONC=4` 下還會拖慢同時段的其他臂。
- **提示設計是偽重複。** `TASKS` 只有 4 個,`is_synth = conv_idx % 2` 與 `conv_idx % 4` 完全綁定(任務 0、2 恆為 synth),實際只有 4 種模板乘上 9 個 salt,CI 卻以 n=36 計算。6 步工具歷史對所有任務固定,例如 JSON validator 任務也搜尋 `synchronize_state|barrier|slot`。語料是生成的填充物,不需從中檢索。
- **輸出範圍太窄。** 216/216 的 `finish_counts` 都是 `tool_calls`,`comp_max` 僅 763,而 `MAXTOK=32768`。`LOOP_RE` 需要 20–600 字元單位連續出現 5 次以上,在此長度下幾乎沒有觸發機會。
- **看不到參數如何生效。** 程式碼截斷於 `cid = f"call_{conv_idx}_{`,`effort`、`keep_n`、`budget`、`tool_choice` 與取樣參數的送法都不可見。`API` 預設走 8889,引擎在 8888,且引擎已固定 `--keep-last-n-reasoning 2`。因此 K1/K0 很可能是客戶端或 proxy 剝除,而非引擎旗標路徑。
- **其他缺口。** 沒有無工具對照臂,沒有任何品質指標(工具選擇、參數正確性),也沒有 rank1 配置,TP=2 拓撲無從驗證。
- **稽核列數對不上。** `total_audit_rows=239`,扣掉 `external_rows=2` 後為 237,比 `results.jsonl` 的 216 多 21 列,來源未說明(重試、resume、其他本地流量都有可能)。

## (2) 可成立結論與過度推論修正

**可成立:**
- 在約 86K 上下文、8 個工具、短輸出條件下,`undeclared_tc_reqs`、`dsml_in_content_reqs`、`empty_content_no_tc`、`errors` 全為 0。
- K0 相對 A1 的 reasoning 平均差 −72.94(`ci95=[-104.36, -46.5]`),completion 平均差 −57.64(`ci95=[-94.78, -27.31]`)。方向可信,但有效樣本數被高估。

**需修正:**

| 可能的說法 | 修正 |
|---|---|
| effort=max 使 TTFT 多 41.49 秒 | 這是快取未命中的代價。reasoning 差的 `median_diff=0.0`、`ci95=[-27.53, 32.25]`,max 在此提示下沒有多想。只能說「同對話內切換 effort 疑似使快取失效」,且未證實 effort 有送達引擎。 |
| thinking_budget 搭配工具安全 | `reas_max=623`,遠低於 16384,預算從未生效。無法區分「未觸及」與「參數被丟棄」,屬無效檢定。 |
| K1 有效 | reasoning 的 `ci95=[-63.78, 1.42]` 跨零,未證實。 |
| K0 省成本或更快 | 由 `prompt_tokens_p50` 差推算,每輪歷史 reasoning 僅約 110 token(86070→85960→85847),約佔提示的 0.26%。`ttft_s`/`wall_s` 的 CI 全跨零。`cont_p50` 從 57 升到 73,較像 reasoning 移到 content,或模型模仿無 reasoning 的歷史格式(假說)。品質未量。 |
| 無 loop、無 ≥4K 輸出 | 只對 763 token 以下、必以工具呼叫結束的情境成立,不能外推到長篇最終回答。 |
| 生產環境無異常 | 外部流量只有 2 筆、單一客戶端,且皆為 `ok|stop`,與基準測試的 `tool_calls` 分佈不同。 |

## (3) 與既有結論的交叉影響

Dossier 沒有附先前結論的數據,以下只就文內暗示的部分評估。

- **生產基線(high / keep_n=2 / budget=0):** 本輪沒有任何證據支持更動,但也只在短工具回合上重新確認。
- **「≥80K 區」風險(docstring 提及):** 僅格式正確性得到正面證據。長生成與 loop 風險沒有測到,不應據此降級。
- **先前的無工具 thinking_budget 結果(由「WITH real tools」推知):** 本輪無法延伸到有工具情境。
- **快取機制(`--prompt-cache-gib 2.5` 與 learn 186.26 GiB):** E_max 的 0.0 若屬實,代表 effort 是快取鍵或前綴的一部分。這會影響任何依請求動態調整 effort 的路由策略,需獨立確認。
- **`--drop-reasoning-history` 旗標路徑:** 若 K 臂是客戶端剝除,結果不能直接當作改引擎旗標的依據。

## (4) 下一步驗證與上線順序建議

1. **先修量測(不需重跑模型):**
   - 對齊 239 與 216 的差額。
   - 輸出逐列的 `cache_hit`、執行順位與冷暖標記。
   - 明確定義 TTFT。
   - 記錄各臂實際送出的 payload 或提示雜湊,確認 `effort`、`budget`、`keep_n` 的生效位置。
2. **E_max 重測:** 每個對話跑兩次 max(E1/E2),或整段對話一致使用 max,把快取代價與 effort 效果分開。
3. **B16 改為會生效的檢定:** 預算設在 `reas_p50=108` 以下,先證明參數有作用,再測 16384。
4. **K0/K1 補強:**
   - 加入工具選擇與參數的品質評分。
   - 改用模型實際產生的較長 reasoning 歷史。
   - 經引擎旗標路徑(`--keep-last-n-reasoning`)測試。
   - 每個對話至少 3 個 seed。
5. **重做提示設計:**
   - 解除任務與 `is_synth` 的綁定。
   - 讓工具歷史與任務一致。
   - 加入以 `stop` 結束的長輸出情境與無工具對照臂。
   - 延遲另以 `CONC=1` 單獨量測,CI 按模板分群計算。
6. **上線順序:**
   - 維持現行基線。
   - max 與 thinking_budget 暫不啟用。
   - K0 通過品質評估後,才進 shadow 再到 canary。
   - 外部稽核樣本需遠多於 2 筆,才能用來佐證生產安全。

## Reviewer: gpt-6-astra (ok=True, finish=stop, wall=44.1s)

## 1. 實驗方法與數據盲點
- **延遲受快取與執行狀態混淆。** `E_max.cache_hit_median=0.0`，`A1_base=0.9829`；不能把延遲差直接歸因於 `effort=max` 的推理成本。`TF_LEARN_TTL_S=0`、持久化 `--learn-dir` 與 LRU 淘汰亦使請求間狀態可能延續；隨機交錯不等於快取條件相同。
- **A/A 顯示延遲噪音明顯。** `A2_base_vs_A1_base` 的 `ttft_s.mean_diff=9.19`、`ci95=[-4.92,23.29]`；`wall_s.mean_diff=8.75`、`ci95=[-3.66,20.84]`。這不是可機械扣除的固定噪音值，也不能拿各臂 `p50` 相減替代配對分析。
- **提示設計存在綁定。** `TASKS[conv_idx % len(TASKS)]` 與 `is_synth=(conv_idx % 2 == 0)` 使任務類型和「綜合／檢查」提示固定關聯，未形成交叉對照。歷史工具結果為預填內容；全臂皆以 `tool_calls` 結束，未證明完成診斷、修補或實際工具執行正確。
- **證據鏈未完整。** 程式節錄在 `cid` 處截斷，未展示請求組裝、計時、配對與 `ci95` 算法。預設 API 為 `8889`，引擎為 `8888`；`keep_n`、`budget` 究竟由客戶端、代理或引擎實作，不能僅憑臂名稱判定。

## 2. 可成立結論與過度推論修正
- **`K0_kn0` 支持「本工作負載輸出 token 減少」，不支持「已加速」。** 配對 `reasoning_tokens.mean_diff=-72.94`、`ci95=[-104.36,-46.5]`；`completion_tokens.mean_diff=-57.64`、`ci95=[-94.78,-27.31]`。但 `ttft_s`、`wall_s` 的區間皆跨零，且未評估刪除歷史推理後的任務品質。
- **`K1_kn1` 尚無明確效益證據。** token 與延遲的配對區間皆跨零；不可把較低 `reas_p50` 當作可靠收益。
- **`B16_tb16k` 是未觸及預算的測試。** `budget=16384`，但 `reas_max=623`；與基線 token 配對差為零，既不能證明預算有效，也不能證明有工具時預算被忽略。延遲區間跨零，不成立加速結論。
- **`E_max` 只能確認目前整體路徑較慢。** `ttft_s.mean_diff=41.49`、`wall_s.mean_diff=45.27`，區間皆不跨零；但快取差異尚未隔離，token 差異亦無明確證據。
- 各臂 `36/36` 成功且異常計數為零，只支持本次樣本的觀測結果；不等於長推理、工具參數正確性或端到端可靠性已獲驗證。

## 3. 與既有結論的交叉影響
- dossier 未提供既有實驗完整結果，**不能宣稱推翻或複驗既有結論**。尤其本次皆提供 `TOOLS`，沒有工具缺席對照，不能推論工具存在與否對預算或迴圈的因果影響。
- `LOOP_CUT=0` 是 harness 註解中的設定；引擎仍啟用 `--loop-guard`。`engine_loop_fired=0` 表示未記錄觸發，不代表所有防護皆停用。`LOOP_RE` 的文字重複偵測也不能涵蓋語義迴圈或跨工具循環。
- `--drop-reasoning-history --keep-last-n-reasoning 2` 是條件式啟動參數；不能直接把 `K0_kn0` 的結果視為引擎端改成保留零筆的實證。
- 生產稽核 `239` 筆中僅 `external_rows=2`，皆為 `ok|stop`。這不足以驗證外部長上下文、工具呼叫或稀有迴圈風險。

## 4. 下一步驗證與上線順序建議
- **先補可追溯性：** 提供完整 runner、實際請求、代理轉換與引擎生效設定，核對 `keep_n`、`budget`、`effort` 的作用位置；定義 `ttft_s` 是首個串流事件、推理輸出還是內容輸出。
- **再隔離性能原因：** 保留 A/A，將冷／熱快取分層，控制持久化學習狀態、併發及執行順序；依 `conv_idx` 配對檢查 `cache_hit_median` 背後的逐請求資料，而非只比較彙總中位數。
- **補行為與機制對照：** 交叉配置任務與提示模式，加入工具存在／缺席對照及確實能逼近 `budget=16384` 的任務；完成工具執行與回傳，評估診斷、參數、修補及測試結果。
- **上線優先序：** 暫維持 `A1_base`；`K0_kn0` 優先做品質影子驗證，通過後再有限導入，但不承諾降延遲。`K1_kn1` 暫無充分採用理由；`B16_tb16k` 先驗證是否真正限額；`E_max` 先查清快取失配，再考慮擴大使用。