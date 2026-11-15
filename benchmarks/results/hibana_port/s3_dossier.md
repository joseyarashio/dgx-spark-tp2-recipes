# Hibana port, Stage S3 dossier: paired quality under forced C8 (DeepSeek-V4.1-Flash TP=2)

## Setup (as pre-registered in your S2 review, with deviations stated)
- Build out.hs3 (S2 kernel rewritten per your R7/Astra race critique: one writer per shared flag; strict env parse
  keep:cap:min_streams all required, min_streams>=2, extra fields refused; 2D path refused; routed_only_y reset at every
  load; on-device stats). Re-verified offline: 57,240 captured layer-calls, 0 pick / 0 weight mismatches vs reference, 7 configs.
- Production share: from the proxy audit log (16.9 busy hours) 20.1% of busy time and 25.7% of generated tokens ran with >=5
  requests in flight (external MacBook client: 46.6% of its tokens). Above your 20% stop line.
- Arms in order A1 (off) -> B1 (4:48:5) -> C1 (4:32:5, positive control) -> A2 (off, A/A floor); restart per arm; same
  binaries; production restored and hash-verified after.
- GSM8K test items 0-499, greedy temp 0 seed 42, thinking off, max_tokens 768, closed-loop 8 concurrent distinct questions,
  same shuffled order (seed 1) in every arm, via proxy 8889 X-Priority 2. Score = last \boxed{} (fallback last number).
- AIME 2024 30 items, thinking on, max_tokens 12288, closed-loop 8, arms A1 and B1 only.
- Deviation: no teacher-forced logits; no tool-eval-bench / loop probe yet; 1 rep per arm; AIME was hit by proxy 429s
  (X-Priority 2 queue timeout at 25 s while 8 long thinking streams held the slots) -> AIME confounded.

## Raw summaries (runner.log)
```
{"label": "A1_gsm8k", "set": "gsm8k", "n": 500, "correct": 489, "status_ok": 500, "finish_length": 4, "mean_tokens": 202.056, "wall_s": 680.8, "gen_tok_s": 148.4, "mtp_accept": 0.9626, "tokens_per_round": 2.266, "metrics_delta": {"tensorfold:mtp_drafted_total": 58541.0, "tensorfold:mtp_accepted_total": 56353.0, "tensorfold:generation_tokens_total": 101028.0, "tensorfold:decode_rounds_total": 44582.0}}
{"label": "A1_aime", "set": "aime", "n": 30, "correct": 22, "status_ok": 24, "finish_length": 2, "mean_tokens": 2827.2, "wall_s": 507.4, "gen_tok_s": 167.15, "mtp_accept": 0.851, "tokens_per_round": 2.244, "metrics_delta": {"tensorfold:mtp_drafted_total": 55251.0, "tensorfold:mtp_accepted_total": 47021.0, "tensorfold:generation_tokens_total": 84816.0, "tensorfold:decode_rounds_total": 37789.0}}
A1 done 09:38:04
{"label": "B1_gsm8k", "set": "gsm8k", "n": 500, "correct": 487, "status_ok": 500, "finish_length": 3, "mean_tokens": 201.29, "wall_s": 660.8, "gen_tok_s": 152.3, "mtp_accept": 0.9636, "tokens_per_round": 2.268, "metrics_delta": {"tensorfold:mtp_drafted_total": 58293.0, "tensorfold:mtp_accepted_total": 56174.0, "tensorfold:generation_tokens_total": 100645.0, "tensorfold:decode_rounds_total": 44378.0}}
{"label": "B1_aime", "set": "aime", "n": 30, "correct": 17, "status_ok": 20, "finish_length": 2, "mean_tokens": 2619.3, "wall_s": 476.2, "gen_tok_s": 165.03, "mtp_accept": 0.8402, "tokens_per_round": 2.193, "metrics_delta": {"tensorfold:mtp_drafted_total": 50874.0, "tensorfold:mtp_accepted_total": 42744.0, "tensorfold:generation_tokens_total": 78579.0, "tensorfold:decode_rounds_total": 35830.0}}
B1 done 09:57:58
{"label": "C1_gsm8k", "set": "gsm8k", "n": 500, "correct": 487, "status_ok": 500, "finish_length": 4, "mean_tokens": 203.246, "wall_s": 595.4, "gen_tok_s": 170.69, "mtp_accept": 0.9614, "tokens_per_round": 2.266, "metrics_delta": {"tensorfold:mtp_drafted_total": 58962.0, "tensorfold:mtp_accepted_total": 56689.0, "tensorfold:generation_tokens_total": 101623.0, "tensorfold:decode_rounds_total": 44849.0}}
C1 done 10:08:50
{"label": "A2_gsm8k", "set": "gsm8k", "n": 500, "correct": 489, "status_ok": 500, "finish_length": 4, "mean_tokens": 202.056, "wall_s": 681.9, "gen_tok_s": 148.16, "mtp_accept": 0.9643, "tokens_per_round": 2.268, "metrics_delta": {"tensorfold:mtp_drafted_total": 58482.0, "tensorfold:mtp_accepted_total": 56394.0, "tensorfold:generation_tokens_total": 101028.0, "tensorfold:decode_rounds_total": 44541.0}}
A2 done 10:21:06
restored 10d41f91174b005e
DONE

```
## Budget activity (rank 0 device counters; calls = layer-calls)
{
 "B1_gsm8k": "{\"rank\": 0, \"rounds\": 6400, \"calls\": 256000, \"fired\": 116122, \"sum_streams\": 1772400, \"sum_union_before\": 12327659, \"sum_union_after\": 11457612, \"dropped_slots\": 888618, \"dropped_weight_e6\": 77667118826, \"max_rescale_e6\": 2543651}\n",
 "B1_aime": "{\"rank\": 0, \"rounds\": 12672, \"calls\": 497560, \"fired\": 178928, \"sum_streams\": 3196520, \"sum_union_before\": 22473673, \"sum_union_after\": 21112326, \"dropped_slots\": 1389533, \"dropped_weight_e6\": 124060617385, \"max_rescale_e6\": 2543651}\n",
 "C1_gsm8k": "{\"rank\": 0, \"rounds\": 6464, \"calls\": 258560, \"fired\": 255099, \"sum_streams\": 1790320, \"sum_union_before\": 12526395, \"sum_union_after\": 9084672, \"dropped_slots\": 3775417, \"dropped_weight_e6\": 384532769503, \"max_rescale_e6\": 5756657}\n"
}
- B1 gsm8k: fired 45.4% of layer-calls; union per fired call 52.3 -> 44.8 (mean incl. non-fired: 48.2 -> 44.8);
  dropped slots 888,618; mean dropped routed weight per (fired call) row ... (dropped_weight_e6 sum is per call, summed over rows).
- C1 gsm8k: fired 98.7%; union 48.4 -> 35.1.

## Paired GSM8K (computed from the saved answers)
- A1 vs A2 (A/A): 500/500 identical texts, 0 discordant. Baseline is fully deterministic under C8 (batch-invariant).
- A1 vs B1: 118/500 identical texts; 382 diverge; median first-divergence position 119.5 chars; ~324 chars of shared
  prefix per divergence (~90 tokens at ~3.6 chars/token, inferred). Accuracy 489 vs 487: A-only correct 3, B-only correct 1
  (McNemar exact p = 0.625). Mean tokens 202.1 vs 201.3; length finishes 4 vs 3.
- A1 vs C1: 43/500 identical; 457 diverge; median first divergence 74 chars; ~168 chars per divergence. Accuracy 489 vs
  487: A-only 4, C-only 2. Mean tokens 203.2; length finishes 4.
- MTP acceptance (window /metrics deltas): A1 0.9626, A2 0.9643, B1 0.9636, C1 0.9614. Tokens/round 2.266/2.268/2.268/2.266.
- Throughput in this closed-loop run (gen tokens / wall): A1 148.4, A2 148.16, B1 152.3 (+2.7%), C1 170.69 (+15.1%).
  B fired on only ~45% of layer-calls here (streams often < 5 in the drain tail and with short answers).
## AIME (confounded)
- A1: 24/30 answered (6x 429), 22 correct. B1: 20/30 answered (10x 429), 17 correct. On the 18 items both answered: A 16,
  B 15 (A-only 2024-I-10: B answered 1243 vs gold 113), B-only 0. Length-capped: 2 vs 2.
- External POSTs during the whole S3 window: see header line (0 expected).

## Your S2 pre-registered gate (for reference)
- flip rate <= 0.5% per token (median divergence >= ~140 tokens); minority-stream check; MTP accept B-A >= -0.010;
  T2 paired accuracy one-sided 95% lower bound > -5 points and point >= -2; length within +-5%; EOS/truncation +-3 points;
  loop probe 0 new; positive control flips >= 1.5x of B; speed re-test ABBA >=3 restarts, >= +4% at C8.

## Previous S2 reviews
# External audit: s2_dossier.md


## anthropic/claude-opus-5-5 (ok=True, finish=stop, wall=230.5s)

# Hibana 移植 S2 審查意見(budget 4:48:5,DeepSeek-V4.1-Flash,TP=2)

**總評**

- **S1 審查提出的修正大多已落實。** 包括 ucount 對帳、實測斜率、grid 語義、soft cap、不改名、store_y=0、TP 一致性檢查,以及 off-path sha 一致。
- **C8 +6.26% 作為「速度有變化」的證據是可信的,足以進入品質階段。** 但它還不足以證明「同品質下更快」:C8 下的輸出長度、內容和 MTP 接受率都沒有量。
- **單流「雜訊」的說法需要修正。** 數據顯示的是 ABAB 設計下的線性漂移,不是零效應的直接證據。
- **核心本身的離線驗證很扎實,但沒有覆蓋整合層。** 至少有 4 個整合風險需要在 S3 前關閉。

標記說明:【計算】是我用 dossier 數字算出的;【推論】是我的推斷;【建議值】是我提出、需預先登記的門檻;其餘皆為 dossier 原文數字。

---

## (1) 量測方法與數據盲點

**A. C8 效果量大,但統計單位要說清楚。**

- 以 4 vs 4 樣本計:差 9.9 tok/s,Welch t ≈ 11.5;完全分離的排列檢定 p = 2/70 ≈ 0.029【計算】。
- 但每個 arm 內的 rep 0 和 rep 1 共用同一次啟動,不是獨立重複。真正的獨立單位是「重啟」,每臂 n = 2。
  - 2 vs 2 的排列檢定,最小 p 只能到 0.33【計算】。設計本身無法給出形式顯著性。
- 支撐結論的是效果量:B 的最小值 166.9 比 A 的最大值 159.1 高 7.8 tok/s,約為合併 sd 的 6 倍【計算】。
- 結論:速度差異可信,但目前的檢定力來自效果量,不是來自設計。

**B. ABAB 不能抵消線性漂移,單流數據正好顯示了這一點。**

- 單流 greedy 依執行順序單調下降:A1 87.88 → B1 87.47 → A2 87.32 → B2 86.97。
- 我逐題計算了 9 個 prompt 的 A、B 平均:**9/9 題都是 B 較低**,平均約 −0.35 tok/s(−0.4%)【計算】。若當作獨立檢定,符號檢定 p ≈ 0.004。
- 不過 ABAB 下 B 平均晚一個位置,而每一步的漂移約 0.28–0.30 tok/s(A1→A2 降 0.56,B1→B2 降 0.50)【計算】。
  - 所以這個差異幾乎完全可以用漂移解釋【推論】。
- 這帶出三點:
  1. dossier 稱「noise」並不精確。正確說法是「與線性漂移一致,無法與 R≥5 時多出的 kernel launch 開銷區分」。
  2. 在 C8,漂移方向對 B 不利,所以 +6.26% 偏保守【推論】。
  3. **之後所有 A/B 改用 ABBA 或 ABBAAB。**

**C. C8 吞吐提升的歸因沒有被驗證。主要殘餘混淆如下。**

1. **輸出內容與長度改變。**
   - budget 生效時 C8 輸出會偏離基線。agg tok/s 等於「生成 token 數 / 牆鐘時間」。
   - 若 B 更早 EOS、尾段少於 5 流的時間比例改變,或出現重複迴圈,都會改變 agg。
   - 迴圈還會**提高** MTP 接受率,進而提高吞吐【推論】。
   - dossier 沒有列出 C8 每流的 token 數、接受與 draft 計數,也沒有 sha 或長度比較。這是目前最大的混淆。
2. **MTP 接受率(C8)未量。** 速度收益是「回合變短」與「每回合 token 數變化」的淨值,目前無法拆分。
3. **adaptive draft depth 依計時調整。**
   - 單流 drafted 數在不同 arm 間有 ±1 的波動(例如 381 對 382,372 對 373),證明它對時序敏感。
   - budget 讓回合變短後,C8 的 draft depth 分布可能改變。這屬於合法效果的一部分,但需要報告。
4. **沒有生效計數器。**
   - 不知道 C8 中有多少比例的 verify 回合真的觸發 budget,也不知道觸發後 ucount 的分布。
   - soft cap 下,keep 集合聯集本身就可能 > 48;16 列 × keep 4 最多 64 個 expert【推論】。

**D. 與預測的對比需要更正算術。**

- 回合時間減少 7.5%,在每回合 token 數不變時,對應吞吐上升 1/(1−0.075) − 1 ≈ +8.1%,不是 7.5%【計算】。
- 觀測到的 +6.26% 吞吐,等價於回合時間減少約 5.9%【計算】,約為上界的 77%。
- 不是所有 C8 回合都是 16 列,也不是都觸發 cap,所以接近上界有兩種解釋【推論】:
  - 接受率沒有明顯下降;
  - 或混淆 1(輸出變化)在起作用。
- 建議在 B arm 開 TF_DS_EXPERT_STATS=3 跑一次 C8,直接驗證機制。預期:
  - 16 列回合的 ucount 從約 52 降到 49 左右(含 shared);
  - 每層時間按斜率 28.6 µs × Δu 下降。

**E. 其他盲點。**

- C2、C4 雖未觸發 cap,但 R ≥ 5 的回合仍會 launch kernel,只是提前返回。這部分開銷沒有單獨量測。
  - C4 的 B − A 為 −0.27%,在雜訊內。
- 單流在 R ≥ 5 時也會 launch。開銷上界為 40 × 6–10 µs ≈ 0.24–0.4 ms/回合【計算】。
- 生產流量中 ≥5 streams 的時間占比仍未提供。這決定整體收益,是 S1 就提過的盲點。

---

## (2) 可成立結論與過度推論

**可成立:**

1. 在本測試工作負載的 C8 下,budget 4:48:5 帶來可重現的吞吐提升,約 +6%,4/4 分離。
2. 1 到 4 streams 完全不受影響:
   - 單流 4 arm 的 token sha 與生產一致;
   - C2/C4 在雜訊內。
   - 這同時證明 off-path 與門控在這些負載下正確。
3. 核心邏輯與獨立 C++ 參考實作位元一致(57,240 次呼叫、6 組配置)。no-op 配置確實不改寫任何資料。
4. 成本模型(28.6 µs/expert/layer,約 1.14 ms/回合/expert)與觀測量級一致。S1 擔心的 wave 階梯在 u = 27..69 範圍內沒有出現。

**過度推論或尚不成立:**

1. **「+6.26% 是同品質下的加速」不成立。** C8 輸出、長度、接受率都未比較(見 1C)。
2. **「單流差異是雜訊」應改為「與漂移一致」。** 見 1B。
3. **離線 57,240 次呼叫的零誤差,只驗證了 kernel 函數本身。**
   - 它沒有驗證整合層的輸入,特別是 `row_slot` 指標(見第 3 節 R1)。
   - replay 用的是 host 端擷取的 `rows.slots`,不是 kernel 實際讀到的 device 緩衝。
4. **「C8 有效」不能外推到生產混合流量。**
   - 本測試的 C8 多為同領域的 code prompt,聯集較小。
   - 跨領域批次的聯集更大,觸發更頻繁、丟棄更多,速度收益和品質損失都可能更大【推論】。
5. **新的系統性問題:對少數派請求的公平性。**
   - 填充規則是「按全批 routing weight 總和」,會偏向多數 stream 共用的 expert。
   - 結果是:一個中文或數學請求和 7 個 code 請求同批時,它的第 5、6 個 expert 被丟的機率顯著較高【推論】。
   - 同質批次的品質評測會**低估**這類請求受到的傷害。
6. **批次不變性喪失仍需產品端決策。** 速度數據無法替代這個決策。

---

## (3) 下一階段是否值得做與具體參數

**結論:值得做 S3,但有前提。**

- 先關閉以下整合風險,約 1–2 小時工程,不占 GPU 預算。
- 同時取得生產 streams 分布。若 ≥5 streams 的 token 占比很低(例如 < 20%【建議值】),整體收益不到 1.3%。這種情況下不值得以批次不變性為代價,應直接結案。

### 3.1 必須先關閉的正確性與整合風險

**R1:`row_slot = rd.inputs + 2*R*8` 的 stride 假設。**
- 這個寫法假設 inputs 是 [3][R]、stride 為 R。若實際 stride 是 max_rows 或 graph bucket,kernel 會讀到錯誤資料,stream 計數也會錯。
- 離線 replay 無法發現這個問題。
- 處理:加 debug 模式,把 kernel 讀到的 row_slot 拷回,逐回合與 host 的 `rows.slots` 比對。

**R2:padding 列與非 verify 列。**
- 若 graph bucket 會補 padding 列,或 verify 回合可能夾帶 prompt chunk 或其他非 verify 列,問題有兩個:
  - 它們的 slot 值會被算成一個 stream。例如 4 流加上哨兵值 −1,就成為 5 流,C4 也會觸發。
  - 它們的 picks 會進入聯集與 score,影響真實列的選擇。
- `moe()` 的程式碼本身沒有 verify 與 prompt 的判斷,「只作用於 verify 回合」目前只是 dossier 的陳述。
- 處理:讀碼確認,並用計數器證明 C4 觸發次數為 0。

**R3:2D 路徑(world 4,`e.two`)未接上 `routed_only_y`。**
- diff 只改了 `exl3_experts.decodeLaunches`。在 TP4/2D 下開啟 budget 會出問題:
  - pick −1 的 slot 會走 store_y=1 的舊行為,0 × 殘值 y 可能產生 NaN;
  - 計數器語義也未知。
- 處理:在 `e.two != null` 時,載入階段直接 `return error.BadMoeBudget`。

**R4:`min_streams` 預設為 "1",且接受 0。**
- 例如 `TF_DS_MOE_BUDGET=4:48` 會在單流時生效(單流 R ≥ 9 時聯集就可能 > 48)。
- 處理:改為必填,且要求 ≥ 2,或強制 ≥ 5。

**R5:「keep = 前 4 個 slot」依賴 `_route` 按 (sc+bias) 降序寫出。**
- 若 topk 是 unsorted,或順序並非降序,keep 的語義就錯了。C++ 參考採用相同定義,所以無法發現。
- 另外,bias 排序與 weight 排序不同。被丟的 slot 可能權重很大,導致 f = all/kept 放大。
- 處理:
  - 讀碼並斷言排序;
  - 增加計數器記錄 max f 及其分布。

**R6:`rd.pick` / `rd.mw` 的其他消費者是否容忍 −1?**
- 需要逐一確認:prefetch、統計、drafter 輸入、任何以 pick 為索引的路徑。

**R7(低風險,屬於脆弱寫法):**
- 排名迴圈中,`present[e]` 在其他執行緒讀取時被寫成 2。因為只檢查真假值,所以目前正確。但這是資料競爭,建議改寫到獨立的 `rank_ok[]`。
- R > 64、slots > 8、E > 512 時會靜默不生效。應在載入時斷言 `max_rows ≤ 64`,避免日後擴大 max_rows 時 budget 悄悄失效。

**R8:缺少生效統計(S3 判讀的必要條件)。**
- 需要 device 計數器記錄:
  - 觸發回合數;
  - 觸發前後的 ucount;
  - 每列被丟的 routed weight 比例;
  - 按 stream 區分的最大值。
- 沒有這些,S3 無法區分「品質沒變」與「根本沒觸發」。

### 3.2 S3 品質閘門(約 3 小時 GPU)

**原則一:強制觸發。**
- 每一輪都要讓 ≥5 個**不同** prompt 同時活著:用封閉迴路 C8 加待處理佇列。
- **不能把同一題複製 8 份。** greedy 下 8 個相同 stream 的路由完全相同,聯集等於單流聯集,cap 根本不會綁住。
- 每一輪都要記錄觸發率(R8),作為測試有效性的前提。

**原則二:利用基線的批次不變性。**
- 先驗證基線 A 在 C8 下的 greedy 輸出與單流 sha 一致。
- 若一致,則在 budget 下第一個分歧 token 之前,B 的每個 token 都是在基線前綴上做 teacher-forced 預測。
- 因此可以用「首次分歧位置」估計**每 token top-1 翻轉率**:翻轉率 = 分歧數 / 分歧前累計 token 數,屬於設限存活分析。
- 這是在沒有 logits API 的情況下,最接近 teacher forcing、統計力也最高的指標。

**原則三:加陽性對照。**
- 跑短版的 4:32:5。S1 模擬顯示它丟棄 11.1% 權重、影響 73% rows。
- 若各指標連 cap 32 都分不出來,說明閘門不靈敏,4:48:5 的「通過」沒有意義。

**時間分配(以 C8 約 160 tok/s 估算【計算】),全部採 ABBA:**

| 階段 | 時長 | 內容 | 量測 |
|---|---|---|---|
| T0 | 15 分 | 關閉 R1–R8;C8 基線不變性檢查(16 個 prompt) | sha;觸發率;C4 觸發 = 0 |
| T1 | 35 分 | 64 個不同 prompt(9 code + 30 題庫 + 25 個跨領域:中文、數學、工具、長 thinking),512 token,greedy,3 種排列(改變同批鄰居),arm A/B;4:32:5 只跑 1 種排列 | 翻轉率;分歧比例;/metrics 接受率差;長度與 EOS 分布;n-gram 重複率 |
| T2 | 約 100 分 | 正確率配對 A/B:從 run_full_eval / run_omni_eval 取 ≥300 題可自動評分題目(含 ≥30 題長推理,4–8k token),C8 並發、題目隨機混排(混合領域) | 逐題配對,McNemar 精確檢定 |
| T3 | 30 分 | C8 下的 loop probe;「少數派」批次:1 個中文或數學 stream + 7 個 code stream,重複 8 次輪替 | 迴圈數;少數派 stream 的翻轉率 / 丟棄權重 vs 多數派 |

**T2 的可行性與檢定力:**
- 300 題 × 約 1.5k token × 2 arm ≈ 0.9M token,約 95 分鐘【計算】。
- 若 A 已驗證批次不變,A arm 可重用單流或既有的 temp-0 結果,省下約一半時間。這是條件式節省。
- 若題庫可用題數 < 300【推論:dossier 未提供 run_full_eval 的題量】,降級為「只能偵測 ≥8 點的退化」,並明確寫進結論。

**統計力限制的處理(必須誠實寫進決策紀錄):**
- 配對二元結果、不一致率約 15%、單側 α = 0.05、power 0.8 時【計算】:
  - 偵測 5 點退化約需 370 題;
  - 偵測 3 點約需 1,030 題。
- 3 小時內**只能排除 ≥5 點左右的退化**,也就是 Hibana keep 4 那種量級(−6.6)。無法排除 1–3 點。
- 這個缺口的補償方式:
  - 以 T1 翻轉率(高統計力)作為主判定,T2 作為「排除大型傷害」的檢查;
  - 用劑量反應(cap 32 > cap 48)驗證指標方向;
  - 若最終上線,**以 opt-in 或限定負載的方式**,而非全域預設。
-

## Questions
1. Verdict per your pre-registered gate: pass / fail / inconclusive, criterion by criterion. Note the flip-rate criterion
   (~1.1%/token inferred) vs accuracy/acceptance/length (all within bounds), and GSM8K's 97.8% ceiling.
2. Given the result, is the budget worth keeping as an opt-in (default off) feature, or should it be removed entirely
   under the stepwise policy (keep only measured, defensible gains)? Weigh: batch-invariance loss (A/A is bit-identical
   today, B is not), +6.3% decode-gate C8 but +2.7% on this realistic closed loop, 26% of production tokens at >=5 streams.
3. If keep: what exactly remains before release (minimum). If remove: confirm the removal plan.
