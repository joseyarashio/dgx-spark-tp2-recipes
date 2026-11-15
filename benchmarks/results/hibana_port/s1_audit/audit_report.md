# External audit: s1_dossier.md


## anthropic/claude-opus-5-5 (ok=True, finish=stop, wall=154.7s)

# Hibana route_budget 移植 S1 審查意見(DeepSeek-V4.1-Flash,TP=2,2×GB10)

**總評:**
- S1 的資料擷取本身是乾淨的:僅量測、無算術變更、生產二進位已用 sha256 還原。
- 但有三件事尚未成立:
  1. 「省多少時間」的成本模型;
  2. 「品質能否接受」的檢定力;
  3. S2 實作草案的正確性。
- 我的建議是:**有條件、限時地做 S2**。範圍只限 ≥5 streams 的回合。先做品質判定,再做效能最佳化。單流不值得做。
- 下文標記【推論】者為我的推斷,其餘數字皆取自 dossier。

---

## (1) 量測方法與數據盲點

**A. 兩個內部數字不一致,必須先釐清。**

- **引擎 ucount 與分析器不一致,不是 dossier 所說的「agrees」。**
  - 引擎端:rows 16 為 168703/3560 = 47.39,含 shared,即 routed 約 46.4。
  - 分析器:rows 16 為 51.22 routed。
  - 兩者差約 10%。
  - 可能原因【推論】:
    - stats.json 每 256 回合才寫一次,最後快照停在第 1280 回合。1,432 回合中最後約 152 回合(大多是最後跑的 C8)不在快照內。3560 calls 對應 89 回合,而 dump 中 rows-16 回合有 9160/40 = 229 回合,兩者樣本不同。
    - 分析器以「整個 verify 回合」為單位取聯集,完全忽略 header 裡的 `nw`(windows 數)。若一個回合在引擎內以多個 window/chunk 分別呼叫 `exl3_experts.decode`,實際讀取的聯集是 per-window 的。這種情況下,模擬的 union 與 budget 效果都會偏離真實核心行為。
  - 這點必須先釐清。它直接決定 cap 48 在真實核心中「會不會綁住」。
- **round_ms 表的索引有歧義。**
  - 標稱「rows 1..16」,卻列出 17 個值,又註明 index 0 = 1 row。
  - 若 index 15 才是 16 rows,16-row 回合是 84.4 ms 而非 87.5 ms。比例會從 ~6.5% 變成 ~6.8%。
  - 差異不大,但文件要修正。

**B. 工作負載代表性不足。**

- 只有 9 個 code prompts × 384 tokens、greedy、reps 1。
- C8 只有 154 回合,5–8 streams 合計 190 回合。
- 連續回合的路由高度自相關(同一 prompt、相鄰 token),有效獨立樣本數遠小於 57,280 layer-calls【推論】。
- 5–8 streams 的聯集大小取決於「同批請求之間的領域差異」。所以 51.9 這個數字,以及 cap 48 的命中率(28% rows),在混合領域流量下可能顯著不同。缺少的領域包括中文、數學、長 thinking、工具呼叫、長上下文。
- 缺少生產流量的 streams 分佈。收益只存在於 ≥5 streams 的回合。若生產時間大多花在 1–2 streams,整體收益接近 0。

**C. 模擬的指標不等於品質。**

- 「routing weight dropped」是代理指標:
  - 它不反映被丟 expert 輸出的範數;
  - 不反映 40 層的誤差累積;
  - 也不反映 kept 權重重新正規化的影響。分析器計算 drop 時沒有做 renorm。
- `drop_p95` 在 5–8 streams、cap 48 下是 0.190,但 mean 只有 0.036。分佈是重尾的,真正的風險在尾部。

**D. 量測時的回合組成可能被儀器化擾動。**

- 儀器化後 C2 為 108.47,低於 floor 111.45。
- adaptive draft depth 依 EMA 計時調整,所以回合列數分佈可能與生產略有不同【推論】。
- accept 0.7309 vs 0.726 很接近,影響可能小,但未經驗證。

**E. 頻寬線性成本模型可信度中等,且只能當上界。**

- **一個支持線性模型的一致性檢查【推論】:**
  - 若 index 0 = 1 row,rows 6 → 16 回合時間 52.1 → 84.4 ms,Δ = 32.3 ms。
  - 同區間 distinct routed 從 22.33 → 51.22,Δ = 28.9 experts。
  - 每個 expert(40 層合計)的邊際成本 ≤ 1.12 ms。這個上界還混入了每列的非 expert 成本(attention、KV 等)。
  - 位元組模型:6.35 MiB × 40 ≈ 266 MB,在 273 GB/s 下 ≈ 0.975 ms。
  - 兩者吻合,但吻合得「太好」:扣掉每列成本後,隱含的有效頻寬接近 100% 峰值。
- 這意味著兩種可能之一:
  - 實際每個 expert 的邊際成本低於位元組模型;
  - 或 rows 與 distinct 的對應在不同 stream 組成間有混淆。rows 6 多為單流,rows 16 多為多流。
- 結論:~5.7 ms(6.5%)應視為上界。實際收益很可能更低。
- **trellis decode 若是 compute-bound,對線性比例影響不大。** 每個 distinct expert 都要完整解碼一次權重,成本仍隨 distinct 數線性增加【推論】。真正會破壞線性的是:
  - **(a) 圖擷取與 grid 尺寸。** dossier 說 grid x = distinct experts,但 ucount 是 device 端資料,CUDA graph 的 grid 在擷取時就固定了。實際上應該是按上限啟動、多餘 block 提早退出【推論,需讀碼確認】。
  - **(b) wave quantization。** 從 52.9 降到 47.1 個 expert,不一定跨過 SM wave 邊界,節省可能呈階梯而非線性【推論】。
  - **(c) S2 新增的成本。** 每層多一個選擇核心,共 40 次 launch;另外「改名到 top expert、weight 0」的 slot 會讓該 expert 多算一列 FFN(見第 3 節)。

---

## (2) 可成立結論與過度推論

**可成立:**

1. 單流(1–2 streams)的 per-request budget 收益/風險比很差。
   - keep 4 / per 12:最多約 8–9%,但 drop 平均 11.5%,71% rows 受影響。這與 Hibana 自己 keep 4 失敗的結果(GPQA −6.6,p 0.011)同方向。
   - keep 5 / per 20:只省 0.9 個 expert(約 2%)。這在 decode gate 的雜訊內,不可檢出。
   - **單流應排除在 S2 之外。**
2. 在 5–8 streams 下,Hibana 式 per-request cap 完全不會綁住(union 51.9 < 12 × streams)。只有絕對 cap 有作用。這點由模擬資料直接支持。
3. distinct experts 隨 rows 單調增加,所以 expert 讀取量是大批次回合時間的主要可變成本之一(線性一致性檢查支持此點)。

**過度推論或尚不成立:**

1. 「cap 48 帶來 ~6.5% 回合加速」只是上界。理由:
   - 未扣除選擇核心與改名 slot 的額外計算;
   - 未考慮 wave quantization;
   - 未經實測斜率驗證;
   - 也未扣除 MTP 接受率的變化。
   - 目標 logits 改變會影響 draft 接受率。接受率每下降一點,每回合產出 token 就減少,可能吃掉一大部分 6% 的收益【推論】。
2. 換算到 C8 aggregate(156.83 tok/s)也不會是 +6.5%。並非所有 C8 回合都是 16 rows、也並非都綁住 cap。
3. 不能引用 Hibana 的 GPQA「無損」(75.8 vs 76.3,p 1.0)。
   - 那是不同模型(Bolt top-9)、不同 keep 比例下的結果。
   - p = 1.0 只代表「沒有偵測到差異」,不代表等價。
   - 我們的 keep 4/6 在比例上接近他們的 keep 6/9,但沒有任何資料證明它在 DeepSeek 上可遷移。
4. 「C2 108.47 低於 floor」不能歸因於任何事物。
   - 這是儀器化 build,且 reps 1。
   - 它反而暴露出 decode gate 的單次變異可能已接近 5–10%(118.59 vs 108.47)。
   - 若變異真有這麼大,單次 gate 無法檢出 6% 的收益。

**一個被忽略的系統性風險:批次不變性喪失。**

- 加了 cap 之後,某個請求的輸出取決於同批其他請求的路由。
- 後果:
  - 相同 prompt 在不同並發下會產生不同結果;
  - greedy 回歸基線失去可重現性;
  - 除錯困難;
  - 存在請求間互相影響的公平性問題。
- 這需要明確的產品決策,不只是技術決策。

---

## (3) 下一階段是否值得做與具體參數

**結論:值得做一個小而限時的 S2,但要改變順序並縮小範圍。**

收益天花板是 ~6% 的上界,只發生在高並發。只有在 S2-pre 證明實測斜率支持 ≥4% 時,才寫最佳化核心。

**S2-pre(寫核心之前,低成本):**

1. **補齊分析器表格**(資料已經在手):
   - 增列 keep 5 / cap 48、keep 4 / cap 56、keep 4 / cap 52、keep 5 / cap 56。
   - 另做一組「只在 streams ≥ 5 時啟用」的子集統計。
   - 修正 `nw` 處理,改為逐 window 取聯集。
   - 解釋 47.39 vs 52.22 的落差。
2. **專家核心微基準**:
   - 條件:R = 16、真實權重、圖擷取,用合成 picks 讓 ucount 從 30 到 60、每步 2。
   - 量 `exl3_experts.decode` 每層的時間,擬合截距與斜率,並檢查是否有階梯。
   - 對照值:6.35 MiB / 273 GB/s ≈ 24.4 µs per expert per layer【計算】。
   - 若實測斜率低於約 17 µs(< 70%),cap 48 的回合收益會降到 ~4.5% 以下【推論】,建議停止。
3. **用既有的 clock marks(TF_DS_CLOCK_MARKS)量出 C8 16-row 回合中 MoE experts 段的實際占比。** 確認是否接近 52/87 ms。
4. **讀碼確認三件事:**
   - grid 在 graph 中是否按上限啟動;
   - `maxm` 的值;
   - store_y 路徑的行為。

**S2 實作草案的正確性問題,務必在寫核心前處理:**

- **maxm 溢位會讓 combine 永遠不觸發。**
  - 把丟棄的 slot 改名為該列 top expert 之後,熱門 expert 的 member 數會增加。
  - decode_prep 中 `if (pos < maxm)` 會靜默丟掉超出的 member。
  - 但 down epilogue 的 `target` 仍把該 slot 算成「已路由」。
  - 結果 `atomicAdd` 計數永遠達不到 target,該列輸出不會被 combine。這會是靜默錯誤或殘值。
  - 必須證明 maxm ≥ 每個 expert 可能的最大 member 數,或在選擇核心中保證不超過。
- **改名 slot 會實際多算一列 FFN。** 它省下了位元組,卻增加了計算,必須計入成本。
- **改用 pick = −1 的替代方案有風險。** 在 store_y = 1 時仍會讀取殘留的 y。w = 0 時 0 × y = 0,但若殘值是 NaN 或 Inf,結果就是 NaN。除非保證 y 緩衝有界,否則不要用。

**第一個測試配置(單一):keep 4 / cap 48 / per_req 0,且只在 live streams ≥ 5 時啟用。**

- 理由:
  - 在 5–8 streams 下,模擬約省 5.8 個 expert;drop 平均 3.6%,p95 0.190,28% rows 受影響。
  - 若門控在 ≥5 streams,1–4 streams 完全無損,單流 87 tok/s 不受影響。
  - keep 4/6 在比例上對應 Hibana 已驗證的 keep 6/9。
- 若補表顯示 keep 5 / cap 48 或 cap 56 能在省下 ≥4 個 expert 的同時把受影響 rows 壓到約 15% 以下,改用那個較保守的點。
- **不要測 cap 32。** 11.1% weight 被丟、73% rows 受影響,品質風險過高。
- **重新正規化:建議 renormalize over kept(× 1.5)。** 這與 Hibana 經驗證的行為一致,並保持 MoE 輸出尺度。不過這只是判斷,應在品質階段 A/B 兩種規則(見第 4 節的 logits KL)。

**順序:先品質,後效能。**

1. 先寫一個不追求速度、但正確的選擇核心(env 門控)。
2. 跑品質判定。
3. 品質不過就整案停止,省下最佳化工作。

---

## (4) 驗收門檻與回退條件

**品質門檻(主判定;現有的 30 題銀行檢定力不足):**

- **30 題 ≥ 28/30 只能當煙霧測試。**
  - 30 題的標準誤約 4 個百分點,偵測不出 Hibana 那種 −6.6 點的退化。
  - 用配對非劣性檢定以 2 點為邊界時,若不一致率約 10%,約需 1,500 題【計算】。不切實際。
- **主指標改為 teacher-forced 配對 logits 比較:**
  - 在相同 token 序列上比較基線與 budget 版本。
  - 序列必須在 C8 並發下跑,cap 才會綁住。
  - 量測項目:
    - 逐 token KL(base‖budget)的 mean 與 p99;
    - top-1 一致率;
    - MTP 接受率差。
  - 建議預先登記的門檻【建議值】:
    - top-1 一致率 ≥ 99%;
    - C8 下接受率下降 ≤ 0.01(基線 0.726);
    - KL p99 不超過 baseline 自身數值雜訊的固定倍數。數值雜訊以同配置重跑兩次量得。
- **次要指標:**
  - tool-eval-bench 取樣 A/B(配對、同種子,點數差的信賴區間下界 ≥ −3 點);
  - loop probe 零新增迴圈;
  - 1h marathon 無 NaN、無 hang、無計數器卡死;
  - 30 題 ≥ 28/30。

**效能門檻:**

- 基線與候選各至少 5 reps,取 median 並報告離散度。
- C8 aggregate 提升 ≥ +4%,且大於 2 倍 run-to-run 標準差。
- greedy 單流與 C2/C4 在雜訊內不退步。門控 ≥5 streams 時應為零差異,這同時可用來驗證門控是否正確。
- 選擇核心本身每回合的開銷需單獨報告。

**回退條件(任一成立就回退):**

- S2-pre 的實測斜率或 MoE 占比顯示上界不足 4%:不寫最佳化核心,整案結案。
- C8 實得提升低於 3%,或無法與雜訊區分。
- MTP 接受率下降 > 0.01,或 KL / top-1 不過門檻。
- 任何 NaN、輸出缺列(maxm 或計數器問題)、hang,或 marathon 失敗。
- 產品端不接受「輸出依同批流量而變」。
- **回退方式:**
  - 預設 env off 不足以算回退;未採納時應移除程式碼,避免 decode_prep 路徑多一個維護分支。
  - 採納後仍需在最終全回歸中,用 env off 重新確認 greedy 輸出與 baseline p17 位元一致。

## gpt-6-astra (ok=True, finish=stop, wall=92.0s)

## 1. 量測方法與數據盲點

**審查判定：S1 足以證明 expert union 有壓縮空間，但不足以核准目前的 S2 kernel 實作。應先修正可重現性與成本模型，再決定是否值得做。**

- **所附 analyzer 無法直接重現分流數表格。**它只將所有流數累積到同一個 `acc`，沒有輸出 1、2–4、5–8 streams 分組，也沒有輸出預算後的平均絕對 expert 數；輸出的是逐 layer-call `n / distinct` 的平均。這不等於總 expert 數之比。表格可能來自其他程式，但目前未附，不能視為已核實。

- **「engine-side ucount agrees」目前不成立。**  
  `168703 / 3560 ≈ 47.39`，這包含 shared expert；離線 rows=16 的 51.22 加 shared 應為 52.22。上述為直接計算，兩者明顯不是同一均值。程式只每 256 rounds 寫一次 `stats.json`，沒有展示結束時 flush，因此**可能是截取時間不同〔推論〕**；但必須用相同 rounds、相同 windows 做逐筆核對，不能以此例聲稱一致。

- **window 與 round 的量測單位有待證明。**dump offset 只有 layer，沒有 window；header 儲存 `nw`，analyzer 卻忽略它。若一輪有多個 decode windows，**可能覆寫同 layer 的前一個 window，或把 window union 誤當 round union〔推論〕**。必須證明本次全為單 window，否則補上 window 邊界及逐 window dump。

- **檔案完整性檢查不足。**寫入端未處理 short write／錯誤重試；讀取端遇到不足的 header 或 body 就靜默結束。應核對預期 round 數、完整位元組數、每筆形狀及結尾完整性。`ucount` 累加不是 atomic，也須證明所有寫入由同一有序 stream 執行。

- **量測沒有改算術，不代表沒有改樣本分布。**逐層 mapped-memory copy、host 寫檔及只對 rank 0 加負擔，都可能影響 TP 等待、批次組成與自適應 draft depth〔推論〕。C2 從 118.59 到 108.47，而 C4、C8 反而提高，不能把差異全部歸因於 instrumentation，更不能拿來估算候選方案效能。

- **統計樣本數不能算成 57,280 個獨立觀測。**同一 prompt 的連續 rounds、同一 round 的 40 layers 都相關；而且只有 `--reps 1`。1,007 rounds 是單流，亦不能代表 production streams=8 的比例。應以 prompt／完整執行為配對重複單位，分開報告 C2、C4、C8，而非用 layer-call 數營造統計力。

另須修正時間表：資料列有 17 個值；按「index 0 = 1 row」，16 rows 對應 **84.4 ms，不是 87.5 ms**。EMA 修正後的實際時間也尚未提供。

## 2. 可成立結論與過度推論

**可以成立的結論：**

- 此 grouped 路徑確實以 distinct experts 決定 grid 的一個維度，因此減少 union 是合理的最佳化方向。
- 依所列模擬，per-request 預算在這批 5–8-stream 樣本幾乎沒有節省；要改善此區間，需測 absolute budget。
- aggressive 設定伴隨大量路由擾動：cap 32 的 73% rows 受影響、平均移除 11.1% routed weight，不能稱為低風險最佳化。
- 這是**改變 target 模型的有損近似**，不是維持原模型語義的 speculative decoding 加速。

**目前的過度推論及語義問題：**

1. **CAP 是軟預算，不是硬上限。**  
   analyzer 先保留所有 rows 的 guaranteed experts，超過 `lim` 也不裁減。cap 32 卻平均讀取 37.4，正好展示這點。應記錄超額頻率、超額大小與各層分布；不能承諾「最多 CAP」。

2. **KEEP 並非依 routing weight 排序。**  
   `_route_row` 依 `sc + bias` 選擇並排列 slots，weights 則來自 `sc`。analyzer 的 `r[:keep]` 保留的是 selection rank，不是純 weight 最大者。必須統一文件、離線模型與 S2 語義。

3. **目前 byte estimate 是條件式情境，不是已證實的效能上界。**  
   13.1 GiB、5.7 ms 的推導要求每個 expert 的有效讀取近似 checkpoint bytes、有效頻寬接近 273 GB/s，且節省可直接轉為 critical-path 時間。檔案未提供這些量測。Trellis 解碼計算、cache reuse、不同 members 數、kernel occupancy、TP 等待及 overlap 都可能改變結果〔推論〕。

4. **混用了分組。**  
   51.9 是 5–8 streams 均值，51.22 才是 rows=16 均值。不能未核對聯合分布，就拿前者搭配固定 16-row 時間算改善。

5. **減少 expert union 不等於減少所有工作。**  
   `repeat=True` 仍保留每列全部 slots；零權重重複 slot 仍可能執行 expert 計算〔推論〕。`decode_prep` 的主要迴圈仍按 `R * slots` 掃描，新增 budget kernel 也有成本。

6. **routing-weight loss 不是品質誤差界。**  
   它沒有考慮 expert 輸出大小、方向或跨層累積。重新正規化也會改動所有保留分支。Hibana 的 GPQA `p=1.0` 不是等價性證明，更不能轉用到 DeepSeek；另一設定的品質下降反而證明風險真實存在。

## 3. 下一階段是否值得做與具體參數

**現在值得做的是「成本驗證」，不是完整移植。若目標要求維持原始 greedy 輸出，這條有損路線應直接停止。**

寫 kernel 前，先完成：

- 修正 analyzer，重現所有分組表格；同一捕獲區間逐 window 核對 `ucount = routed union + shared`。
- 在無逐層 dump 的條件下，量測 `decode_prep`、grouped gate/up、grouped down、整個 MoE、整輪及 TP 等待時間。
- 以 **layer、R、streams、union、每 expert members 分布**分組觀察，而非只對 union 做一條回歸線。
- 使用已捕獲輸入做隔離重播：保持 R 與 slot 數，套用離線預算後的 picks／weights，再測 expert kernels。這是成本實驗，不是品質驗證。
- 量測實際記憶體流量、cache 行為與 trellis 計算限制；將量測出的可節省時間與新增選擇、同步、renormalization 成本比較。
- 最後再驗證自適應 draft depth 下的端到端結果；EMA 不能代替成本模型驗證。

**只有上述結果顯示明確淨收益，才條件式批准單一 S2 候選：**

```text
TF_DS_MOE_KEEP=4
TF_DS_MOE_CAP=48
TF_DS_MOE_PER_REQ=0
```

理由是它直接測試 production 高流數下真正會約束 union 的設定；cap 32 風險過高，per-request 設定在該區間沒有展示價值。優先量測 C8，但 C2、C4、單流仍須驗收。

固定語義如下，避免同階段加入多個變因：

- KEEP 依現有 `sc + bias` 的 slot 順序。
- 保留 guaranteed union 超額行為，不加入 fallback。
- routed 保留權重重新正規化至總和 1.5；shared slot 與權重 1.0 不動。
- dropped slot 重複該列首選 expert、權重為 0。
- 同分排序明確且 deterministic，兩個 TP ranks 必須選出一致結果。

**重複 expert 的安全性不能直接宣告。**須驗證 `maxm` 容量、members 重複項、完成計數、graph replay 及有限輸出。若重複零權重 slot 的輸出為 NaN，零權重也不保證隔離 NaN。不要改成無效 pick 而忽略 `store_y=1` 的 stale-y 路徑。

## 4. 驗收門檻與回退條件

- **正確性先行：**用 KEEP=6、不約束預算的模式驗證 no-op；最好直接 bypass，避免無必要 renormalization 引入差異。核對兩 ranks 的 picks／weights、shared 不變、成員容量、計數器復位、graph replay 與離線參考一致。

- **效能必須來自正式無 instrumentation 執行。**配對、交錯執行 baseline／candidate，涵蓋單流與 C2/C4/C8；報告完整執行間變異與差值區間。只有重複可見、扣除新增成本後的端到端收益才保留。C2 的既有 **111.45 floor** 是必要條件，但僅過 floor 不代表沒有退步；其他基準門檻未提供，不應自行補造。

- **驗收有效輸出，不只驗收每輪時間。**一起記錄 tok/s、acceptance、draft depth、round rows、輸出長度及完成時間。候選若每輪較快，卻因 acceptance 下降或回答變長而拖慢任務，應判失敗。

- **品質採「必要但不充分」閘門。**30 題 greedy bank **≥28/30**、loop probe、1h marathon 都要過，但這些不能證明無品質退化。tool-eval-bench 應使用配對 sampled A/B，揭露樣本數、差異、不確定性與失敗類型。現有 dossier 沒有品質非劣性容忍值及變異估計，因此目前無法宣稱統計力足夠；「未顯著下降」不能當作通過。

- **立即回退條件：**任一 rank 路由不一致、NaN／stale-y／容量或計數問題、品質閘門失敗、迴圈異常、既有效能 floor 失守，或收益無法在重複執行中確認。若 isolated replay 已顯示節省不足以抵銷 budget 成本，就在寫正式 kernel 前停止。

**最終建議：保留 S1 作為探索性證據，暫緩 S2 實作批准。先補齊資料一致性與實際 kernel 成本；若成立，只測 KEEP=4／CAP=48／PER_REQ=0。沒有可重複的淨收益與可辯護的品質證據，就維持 default off，依既定政策不保留此最佳化。**