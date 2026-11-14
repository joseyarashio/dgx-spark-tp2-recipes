# External Audit Report: Phase 2 v2: Long-Context Synthesis (Long-Thinking), seeds de-duplicated, caches pre-warmed, binding budgets

## Local Computed Stats
```json
[
  {
    "arm": "EB16_max_tb16k",
    "ok": 16,
    "total": 16,
    "errors": {},
    "finish_counts": {
      "tool_calls": 11,
      "stop": 5
    },
    "empty_content_no_tc": 0,
    "tool_call_reqs": 11,
    "undeclared_tc_reqs": 0,
    "dsml_in_content_reqs": 0,
    "loop_r": 1,
    "loop_r_periods": [
      282
    ],
    "loop_c": 0,
    "loop_c_periods": [],
    "engine_loop_fired": 0,
    "ge4k": 16,
    "ge8k": 16,
    "ge16k": 15,
    "prompt_tokens_p50": 85071,
    "cache_hit_median": 0.9869,
    "comp_p50": 16461,
    "comp_p90": 18098,
    "comp_max": 19006,
    "reas_p50": 16385,
    "reas_p90": 16385,
    "reas_max": 16385,
    "cont_p50": 76,
    "cont_p90": 6371,
    "cont_max": 8557,
    "ttft_p50": 1.132,
    "ttft_p90": 2.362,
    "wall_p50": 472.03,
    "wall_sum": 7821.7
  },
  {
    "arm": "A2_base",
    "ok": 16,
    "total": 16,
    "errors": {},
    "finish_counts": {
      "stop": 15,
      "length": 1
    },
    "empty_content_no_tc": 0,
    "tool_call_reqs": 0,
    "undeclared_tc_reqs": 0,
    "dsml_in_content_reqs": 0,
    "loop_r": 0,
    "loop_r_periods": [],
    "loop_c": 0,
    "loop_c_periods": [],
    "engine_loop_fired": 0,
    "ge4k": 16,
    "ge8k": 16,
    "ge16k": 9,
    "prompt_tokens_p50": 85071,
    "cache_hit_median": 0.9869,
    "comp_p50": 17159,
    "comp_p90": 24347,
    "comp_max": 32768,
    "reas_p50": 9490,
    "reas_p90": 14445,
    "reas_max": 26229,
    "cont_p50": 7200,
    "cont_p90": 9509,
    "cont_max": 10071,
    "ttft_p50": 0.973,
    "ttft_p90": 1.322,
    "wall_p50": 443.12,
    "wall_sum": 7874.7
  },
  {
    "arm": "A1_base",
    "ok": 16,
    "total": 16,
    "errors": {},
    "finish_counts": {
      "length": 2,
      "stop": 14
    },
    "empty_content_no_tc": 0,
    "tool_call_reqs": 0,
    "undeclared_tc_reqs": 0,
    "dsml_in_content_reqs": 0,
    "loop_r": 0,
    "loop_r_periods": [],
    "loop_c": 0,
    "loop_c_periods": [],
    "engine_loop_fired": 0,
    "ge4k": 16,
    "ge8k": 15,
    "ge16k": 9,
    "prompt_tokens_p50": 85071,
    "cache_hit_median": 0.9869,
    "comp_p50": 17182,
    "comp_p90": 32251,
    "comp_max": 32768,
    "reas_p50": 9159,
    "reas_p90": 21956,
    "reas_max": 27027,
    "cont_p50": 6639,
    "cont_p90": 8751,
    "cont_max": 10506,
    "ttft_p50": 1.004,
    "ttft_p90": 1.323,
    "wall_p50": 521.94,
    "wall_sum": 8703.3
  },
  {
    "arm": "E_max",
    "ok": 16,
    "total": 16,
    "errors": {},
    "finish_counts": {
      "stop": 7,
      "length": 9
    },
    "empty_content_no_tc": 6,
    "tool_call_reqs": 0,
    "undeclared_tc_reqs": 0,
    "dsml_in_content_reqs": 0,
    "loop_r": 1,
    "loop_r_periods": [
      62
    ],
    "loop_c": 0,
    "loop_c_periods": [],
    "engine_loop_fired": 0,
    "ge4k": 16,
    "ge8k": 16,
    "ge16k": 13,
    "prompt_tokens_p50": 85071,
    "cache_hit_median": 0.9869,
    "comp_p50": 32768,
    "comp_p90": 32768,
    "comp_max": 32768,
    "reas_p50": 22575,
    "reas_p90": 32768,
    "reas_max": 32768,
    "cont_p50": 5231,
    "cont_p90": 9011,
    "cont_max": 11793,
    "ttft_p50": 0.974,
    "ttft_p90": 1.302,
    "wall_p50": 722.79,
    "wall_sum": 11055.3
  },
  {
    "arm": "K0_kn0",
    "ok": 16,
    "total": 16,
    "errors": {},
    "finish_counts": {
      "stop": 16
    },
    "empty_content_no_tc": 0,
    "tool_call_reqs": 0,
    "undeclared_tc_reqs": 0,
    "dsml_in_content_reqs": 0,
    "loop_r": 0,
    "loop_r_periods": [],
    "loop_c": 0,
    "loop_c_periods": [],
    "engine_loop_fired": 0,
    "ge4k": 16,
    "ge8k": 16,
    "ge16k": 5,
    "prompt_tokens_p50": 84783,
    "cache_hit_median": 0.9835,
    "comp_p50": 12928,
    "comp_p90": 26185,
    "comp_max": 29810,
    "reas_p50": 7512,
    "reas_p90": 16626,
    "reas_max": 19418,
    "cont_p50": 5884,
    "cont_p90": 10159,
    "cont_max": 10392,
    "ttft_p50": 1.177,
    "ttft_p90": 47.867,
    "wall_p50": 435.23,
    "wall_sum": 7975.8
  },
  {
    "arm": "B8_tb8k",
    "ok": 16,
    "total": 16,
    "errors": {},
    "finish_counts": {
      "tool_calls": 8,
      "stop": 8
    },
    "empty_content_no_tc": 0,
    "tool_call_reqs": 8,
    "undeclared_tc_reqs": 0,
    "dsml_in_content_reqs": 0,
    "loop_r": 0,
    "loop_r_periods": [],
    "loop_c": 0,
    "loop_c_periods": [],
    "engine_loop_fired": 0,
    "ge4k": 16,
    "ge8k": 15,
    "ge16k": 0,
    "prompt_tokens_p50": 85071,
    "cache_hit_median": 0.9869,
    "comp_p50": 8269,
    "comp_p90": 11888,
    "comp_max": 14030,
    "reas_p50": 8003,
    "reas_p90": 8193,
    "reas_max": 8193,
    "cont_p50": 141,
    "cont_p90": 6027,
    "cont_max": 7632,
    "ttft_p50": 0.976,
    "ttft_p90": 1.324,
    "wall_p50": 304.22,
    "wall_sum": 4640.4
  }
]
```


## Reviewer: anthropic/claude-fable-5-2 (ok=True, finish=stop, wall=112.7s)

**總評：這份 v2 只支持兩個結論：`E_max` 在 32768 上限下不可用，以及 thinking budget 在掛工具時會讓模型改發 tool call 而不是交付綜合答案。其餘差異都落在 A/A 噪聲內。**

## (1) 實驗方法與數據盲點

- **A/A 噪聲底很大，且 A1 是偏高的基準。** `A2_base_vs_A1_base` 的 reasoning ci95 為 [-4019.62, 1871.81]，wall mean_diff 為 -51.79s（ci95 [-114.13, 5.83]，幾乎排除 0）。A1 的 comp_p90 是 32251，A2 是 24347；length 是 2 對 1。所有 arm 只對 A1 配對，會系統性偏向「比基準短、比基準快」。
- **`ok: 16/16` 與 `empty_content_no_tc` 掩蓋了失敗。** budget arm 在 prompt 明令禁止工具下仍以 `tool_calls` 結束：EB16 是 11/16，B8 是 8/16，合計 19/32；其餘四個 arm 是 0/64。因為有 tool call，`empty_content_no_tc` 記為 0，但 cont_p50 只有 76 與 141（A1 為 6639）。
- **budget 的實作層不可見。** reas_p90/reas_max 等於 16385 與 8193（budget+1），顯示是強制截斷。但 `rank0.sh` 沒有任何 budget 旗標，harness 預設打 `:8889` 而引擎在 `8888`（推測中間有 proxy），節錄又被截斷，無法判定是引擎側還是 proxy 側。
- **K0 重演了 v1 的 cache 混淆。** 預熱只描述 effort=high 與 max，未提及 keep_n=0 的前綴。K0 的 ttft_p90 是 47.867s（其他 arm 約 1.3s），ttft mean_diff 是 +11.8（ci95 [2.94, 20.99]），median_diff 卻是 -0.11，也就是少數請求冷 prefill。dossier 只給 `cache_hit_median`（0.9835 對 0.9869），尾部看不到。
- **K0 的處理強度極弱，且兩側機制重疊。** prompt_tokens_p50 是 84783 對 85071，只差 288 tokens。`rank0.sh` 預設已帶 `--drop-reasoning-history --keep-last-n-reasoning 2`，所以 client 側的 keep_n=2 與引擎側丟棄無法區分；當次 `DROP_REASONING_HISTORY` 的值也未記錄。
- **E_max 的數據是右截尾。** comp_p50、comp_p90、reas_p90 全為 32768，length 9/16，所以 +11276.5 reasoning 與 +147.0s wall 都只是下界。
- **樣本與設計限制。**
  - `SYNTH_PROMPTS` 只有 4 條（`conv_idx % 4`），N=16 實為 4 個模板各 4 份，CI 未處理群聚。
  - 5 組比較乘 4 個指標，沒有多重比較校正。
  - 沒有任何品質或正確性指標。
  - 沒有「不掛工具」或 `tool_choice="none"` 的 arm，工具存在本身的效應無法分離。
  - CONC=3 且 arm 隨機序，wall 受同時在跑的其他 arm 污染。
  - `TF_LEARN_TTL_S=0` 加 `--learn`，使 cache 狀態跨 run 殘留。
  - `ge4k/ge8k/ge16k` 的定義不在節錄內。
- **loop 偵測有落差。** client 端 `LOOP_RE` 抓到 2 筆（週期 282 與 62，都在 effort=max），`engine_loop_fired` 卻全為 0。這可能是 `--loop-guard` 漏抓，也可能是 regex 誤報，目前無法判定。

## (2) 可成立結論與過度推論修正

**可成立：**
- **`E_max` 配 32768 不可上線。** length 9/16、`empty_content_no_tc` 6/16，wall ci95 [57.31, 232.64] 明確超出噪聲底。
- **budget 在此情境會破壞交付。** 兩個 budget arm 都把 reasoning 壓在 budget+1，同時把輸出導向違規的 tool call（19/32 對 0/64）。

**需修正的推論：**
- **「B8 省 253.93s wall、少 9362 completion tokens」不是效率增益。** 省下的主要是沒寫出來的答案。
- **「EB16 讓 max 可用」不成立。** length 確實從 9 降到 0，但換來 11/16 的 tool_calls。它的 reasoning 差（ci95 [-466.81, 5839.19]）與 wall 差（-55.1）也都在 A/A 範圍內。
- **「K0 減少思考量」證據不足。** reasoning ci95 是 [-4642.56, 127.44]，跨 0。completion ci95 上界 -90.31 只是勉強排除 0，未經校正，且 A/A 本身就有 -721.38。它的 stop 16/16 對 A1 的 14/16，在 n=16 下也無意義。
- **「max 比較容易 loop」不能下。** 2/32 對 0/64，樣本太小。
- **「截斷導致 tool call」目前只是關聯。** 彙總數字吻合，但需要逐列交叉表（`reasoning_tokens == budget+1` 對 `finish_reason`）才能確認因果。

## (3) 與既有結論的交叉影響

- **v1 的「high 約思考 8K、B16 不會綁定」需下修。** v2 的 A1 reas_p90 是 21956、max 是 27027；A2 max 是 26229。16K 上限在 high 的尾部其實會綁定，基準自己也有 3/32 撞到 length。
- **v1 的「max 撞 length 2/3」被 v2 以更大樣本確認**（9/16）。
- **Phase 1 的 keep_n 結論仍未解決。** K1 當時不明，K0 現在仍在噪聲內，沒有依據更動 `--keep-last-n-reasoning 2`。
- **`A1_base` 作為「production baseline」的代表性存疑。** 生產稽核顯示的樣貌與 benchmark 差很多：
  - 外部 138 列中 136 列來自單一 client；≥4K 的只有 2 列。
  - 那 2 列都是 effort=medium、tools_count=5，prompt 為 196883 與 220182（benchmark 是 85071、8 個工具），reasoning 只有 5073 與 2580。
  - 3 筆 shadow loop 全在 effort=low，發生在 1076 到 2854 chars，結局全是 client_left。
  - benchmark 完全沒測 low 與 medium，也沒測約 200K 的 prompt。
- **生產上更大的問題不在本實驗範圍。** `ok|length` 是 35/138，`client_left` 是 23/138，而 `ok|stop` 只有 13/138。

## (4) 下一步驗證與上線順序建議

1. **維持 A1 配置，凍結 budget 與 max 上線。** 這一步不需要新實驗。
2. **先補逐列觀測。** 需要每列的 cache_hit、是否觸及 budget、finish_reason、被呼叫的工具名，並產出觸頂對 tool_calls 的交叉表。
3. **釐清並修正 budget 截斷語意。** 先確認實作在哪一層，再加三個對照 arm：`tool_choice="none"`、移除 `tools`、截斷後注入「直接作答」的引導。主要終點改為「stop 且 content 達門檻」的交付率，不再用 token 數或 wall。
4. **修正統計設計。** 基準改用 A1 與 A2 合併或多次重複；加大 N 並按 4 個模板做群聚；加入品質評分。
5. **重做 K0。** 預熱要涵蓋 keep_n=0 的前綴，並與 `DROP_REASONING_HISTORY=0/1` 做 2×2，分離 client 側與引擎側。
6. **對齊生產。** 加入 effort=low 與 medium、約 200K prompt、5 個工具；另外調查 35 筆 length 與 23 筆 client_left 的成因。
7. **驗證 loop-guard。** 把 2 筆 benchmark loop 與 3 筆生產 shadow loop 重播給引擎，確認是漏抓還是誤報。

**上線順序：** 先做觀測（第 2 項），再修 budget 語意並重測，通過後才對 high 加 budget 做 canary。`E_max` 要等「budget 不再誘發 tool call」成立後才重新評估。

## Reviewer: gpt-6-astra (ok=True, finish=stop, wall=45.9s)

## 1. 實驗方法與數據盲點

- **去重 seed 改善 A/A，但不等於消除抽樣混淆。** `seed = 8000 + 16*conv_idx + arm_index` 讓同一對話各臂使用不同 seed；配對控制的是對話，不是相同隨機抽樣。`A2_base_vs_A1_base` 的 `wall_s.mean_diff=-51.79`、`ci95=[-114.13, 5.83]` 顯示背景變異不可忽略；單次 A/A 亦不是固定的顯著性門檻。
- **預熱未完全控制快取。** `K0_kn0` 的 `prompt_tokens_p50=84783`、`cache_hit_median=0.9835`，其他臂為 `85071`、`0.9869`；其 `ttft_p90=47.867`。中位快取命中率無法排除尾端 miss、排程與並行干擾，不能直接將 TTFT 差異歸因於移除 reasoning。
- **這是刻意施壓的合成任務，不是品質基準。** 提示要求 exhaustive audit、完整 patch 與形式證明，且工具仍以 `tool_choice="auto"` 附掛。沒有 tools 缺席對照，無法區分預算效應與工具可用性的交互作用；也沒有答案正確性、完整性或 patch 驗證結果。
- **機制證據不完整。** runner 摘錄未展示完整請求組裝、預算傳遞、計時與 `ci95` 計算；註解描述不等同執行證明。`ok=16` 只能支持記錄層面的成功，不能代表任務成功。

## 2. 可成立結論與過度推論修正

- **`E_max` 在本工作負載下增加成本，且有交付風險。** 相對 `A1_base`，`wall_s.mean_diff=147.0`、`ci95=[57.31, 232.64]`；`finish_counts.length=9`、`empty_content_no_tc=6`。可反對將其直接設為此類任務的預設，但不能推論所有長上下文任務都不適合 max，亦無證據證明增加的 reasoning 改善品質。
- **`B8_tb8k` 確實縮短本次請求，但不是已證實的等品質加速。** `wall_s.mean_diff=-253.93`、`ci95=[-356.5, -158.67]`；然而 `tool_call_reqs=8`，違反明確禁止工具的任務要求。`EB16_max_tb16k` 同樣有 `tool_call_reqs=11`。`undeclared_tc_reqs=0` 只表示工具名稱已宣告，不表示呼叫獲准；這些請求也未必已完成 synthesis。
- **預算呈現約束跡象，不能據此定位實作。** `reas_max=8193` 與 `16385` 對應設定的 `8192` 與 `16384`，支持預算附近出現截點；是否涉及計數邊界、強制轉段或工具轉向，仍需原始串流與引擎追蹤。
- **`EB16`、`K0` 尚無可靠 wall-time 優勢。** 前者 `wall_s.mean_diff=-55.1` 接近 A/A 的 `-51.79`，且區間跨零；後者 `ci95=[-122.41, 42.66]`。`K0` 的 completion 減少亦不能替代品質驗證。

## 3. 與既有結論的交叉影響

- **v1 的冷 prefill 問題，不能再當作 max 思考較慢的機制證據。** 本次 `E_max` 的 `ttft_s.ci95=[-0.28, 0.03]`，但 completion 與 wall 增加；應將首 token 延遲與生成階段成本分開解讀。
- **不能把 `K0_kn0` 結果外推成引擎歷史裁剪效果。** 它是 client-side 移除 reasoning；服務另有條件啟用的 `--drop-reasoning-history --keep-last-n-reasoning 2`。沒有引擎旗標開關對照，也沒有實際生效設定與序列化後輸入，無法辨識兩層機制的獨立貢獻。
- **loop guard 的有效性仍未建立。** `E_max`、`EB16` 各有 `loop_r=1`，但 `engine_loop_fired=0`；離線 `LOOP_RE` 的重複判定不等於引擎觸發條件。production shadow 樣本的 `prompt_tokens=null`、`outcome=client_left`，只能提出排查線索，不能證明 loop 導致離線或引擎失效。
- **production 快照不能直接驗證實驗外部效度。** 外部請求主要集中於 `136` 筆的單一 client；展示的長輸出樣本為 `effort=medium`、`tools_count=5`，與本次合成條件不同。

## 4. 下一步驗證與上線順序建議

- **先補可稽核性：** 保存完整請求、實際生效旗標、逐請求 `cache_hit`、原始串流與計時邊界；核對預算傳遞、`reasoning_tokens` 計數、`tool_calls` 與 `ci95` 方法。重複 A/A、輪換 seed 對臂配置，避免固定 seed 配置被當成公平性的充分證據。
- **再拆混淆：** 對 `K0` 的實際輸入另外預熱，分開比較冷／暖快取；獨立交叉測試 client-side 裁剪與引擎歷史裁剪。加入 tools 存在／缺席對照，保持任務與其餘參數一致。
- **以完成任務為驗收單位：** 將禁止工具時的 `tool_calls`、空答案、`length` 與內容品質共同評估；若允許後續工具流程，計算直到最終答案的整段成本，而非僅比較首個請求的 `wall_s`。
- **上線順序：** 暫留 `A1_base`；優先 shadow 驗證 `B8_tb8k`，通過工具遵循與品質檢查後才灰度。`EB16` 僅作 max 路徑的受控候選；`K0` 待快取與裁剪機制釐清；`E_max` 不宜直接升為預設。