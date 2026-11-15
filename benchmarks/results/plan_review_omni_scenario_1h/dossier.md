# Evidence dossier

## Cluster
Two DGX Spark GB10 nodes (128 GB unified memory each), DeepSeek-V4.1-Flash-1017 (EXL3 2.9bpw) tensor-parallel TP=2 over ConnectX-7 200G RoCE, native Zig TensorFold engine on :8888 (8 decode slots, MTP speculative decoding, Imprint NVMe prompt-state cache, 2.5 GiB RAM prompt cache), Python priority reverse proxy on :8889 (8 slots, 8-deep queue, slot 8 reserved for P0/P1, tiered queue timeouts 25..4 s, tool_choice required/function -> auto rewrite, short-output effort->none rewrite, loop-guard fallback that re-sends with effort none). MS-DTC thermal governor. Live external client (MacBook) shares the engine.

## Current production release p17 and its last two 1-hour marathon results (compare_1hour_runs.py)
metric                    omni_eval_1hour_p16_tokenmapfix_lo  omni_eval_1hour_p16_tokenmapfix_pr  
start                     2026-11-15 00:51:44                 2026-11-14 21:14:45                 
quality_pass              4/4                                 4/4                                 
tools_pass                True                                True                                
prefill_8k_cold_tok_s     2241.6                              2234.9                              
prefill_8k_cached_ttft_s  0.9082                              0.9255                              
greedy_tok_s              89.49                               90.53                               
mtp_accept                0.7401                              0.7401                              
sampling_tok_s            71.5                                72.61                               
c1                        74.24                               73.66                               
c2                        100.7                               103.06                              
c4                        129.56                              130.12                              
cut_in_32k_s              0.7803                              0.7437                              
marathon_requests         893                                 925                                 
ok_200                    882                                 920                                 
ok_rate_pct               98.77                               99.46                               
status_codes              {200: 882, 429: 11}                 {200: 920, 429: 5}                  
loop_replies              0                                   0                                   
loop_rate_pct             0.0                                 0.0                                 
loop_lowhit_medium        0/139                               0/162                               
gen_tokens                283907                              301331                              
cached_tokens             9136128                             10190848                            
ttft_p50_s                10.321                              10.456                              
ttft_p95_s                24.409                              22.543                              
wall_mean_s               30.09                               28.9                                
wall_p95_s                54.99                               50.52                               
mem_after_gib             None                                None                                


## Real external traffic, last ~39 h (proxy audit log)
external requests 387 span 2026-11-13 21:26:13.724000 -> 2026-11-15 12:29:24.819000
paths {'v1/chat/completions': 387} stream {True: 386, False: 1}
with tools 269 returned tool_calls 188
tool_choice {'None': 291, 'function': 94, 'none': 2}
prompt tokens p50/p90/p99/max 16509 113204 208349 220182  >50K: 123
messages p50/p90 2 105
max_tokens [(None, 121), (120, 94), (3000, 94), (32768, 55), (1024, 12), (4096, 11)]
outcome {'ok': 341, 'client_left': 45, 'proxy_429': 1} finish {'stop': 103, 'None': 46, 'length': 50, 'tool_calls': 188}
hist_reasoning_msgs>0 114
effort=none 55 reasoning tok p50/p90/max 0 0 0 finish [('stop', 54), ('None', 1)]
effort=low 157 reasoning tok p50/p90/max 120 1078 3000 finish [('length', 50), ('None', 42), ('stop', 36), ('tool_calls', 29)]
effort=medium 57 reasoning tok p50/p90/max 60 1892 5073 finish [('tool_calls', 52), ('stop', 4), ('None', 1)]
effort=high 118 reasoning tok p50/p90/max 130 910 3280 finish [('tool_calls', 107), ('stop', 9), ('None', 2)]
proxy effort_rewritten (low->none short output) 54
loop_fallback fired 0 shadow loop detections 4
low + named function tool_choice + finish=length (all 3000 tokens in reasoning, 0 content, no tool call): 10
>100K prompts cached fraction p50 0.97 ttft p50/max 4.8732 125.4782
engine log last 6h effort values seen: high 54, low 19, none 24 (no medium/max)
external requests by hour [(0, 24), (1, 39), (2, 76), (3, 38), (4, 3), (10, 29), (11, 50), (12, 38), (13, 59), (21, 2), (22, 25), (23, 4)]

## Existing marathon workload generator (run_30min_stress_experiment.py worker_job)
```python
    task_choice = random.choices(["HIGH_HIT", "LOW_HIT", "MULTITURN_VISION"], weights=[0.45, 0.35, 0.20])[0]

    if task_choice == "MULTITURN_VISION":
        img_b64 = random.choice(VISION_TEST_IMAGES)
        priority = random.choice([0, 1, 1, 2])
        t_start = time.time()
        # Turn 1
        p1 = [
            {"role": "user", "content": [
                {"type": "text", "text": f"[Diagnostic Log: {SHARED_VISION_CONTEXT}]\nTask {job_id} [Turn 1]: Describe the color quadrants in this image in detail."},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}}
            ]}
        ]
        res1 = send_chat_completion(p1, max_tokens=256, priority=priority, enable_thinking=False)
        res1.update({
            "job_id": job_id,
            "mode": "VISION_TURN1",
            "len_tier": "vision",
            "prompt_tokens_approx": 7600,
            "priority": priority,
            "timestamp": t_start
        })
        if res1.get("status_code") == 200:
            # Turn 2: Followup with cached image context
            ans1 = res1.get("content", "Analyzed image quadrants.")
            p2 = p1 + [
                {"role": "assistant", "content": ans1},
                {"role": "user", "content": f"Task {job_id} [Turn 2]: In the same image, describe the bottom-right corner and identify any geometric pattern in detail."}
            ]
            res2 = send_chat_completion(p2, max_tokens=128, priority=priority, enable_thinking=False)
            res2.update({
                "job_id": f"{job_id}_t2",
                "mode": "VISION_TURN2_CACHED",
                "len_tier": "vision_cached",
                "prompt_tokens_approx": 7800,
                "priority": priority,
                "timestamp": time.time(),
                "turn1_ttft": res1.get("ttft_seconds"),
                "turn2_cached_tokens": res2.get("cached_tokens", 0)
            })
            return res2
        return res1

    # Text tasks
    is_high_hit = (task_choice == "HIGH_HIT")
    len_tier = random.choices(["short", "medium", "long"], weights=[0.35, 0.40, 0.25])[0]

    if is_high_hit:
        mode = "HIGH_HIT"
        if len_tier == "short":
            prefix = SHARED_CORPUS_5K[:2000]
        elif len_tier == "medium":
            prefix = SHARED_CORPUS_12K
        else:
            prefix = SHARED_CORPUS_22K
        query = f"Task {job_id}: Please analyze function block #{random.randint(1, 50)} and summarize invariants."
    else:
        mode = "LOW_HIT"
        # Generate dynamic random text to defeat prefix caching
        rand_salt = "".join(random.choices(string.ascii_letters + string.digits, k=32))
        if len_tier == "short":
            prefix = f"# Dynamic Unique Module [{rand_salt}]\n" + ("x = 10\n" * 300)
        elif len_tier == "medium":
            prefix = f"# Dynamic Unique Module [{rand_salt}]\n" + generate_codebase_corpus(4000, rand_salt)
        else:
            prefix = f"# Dynamic Unique Module [{rand_salt}]\n" + generate_codebase_corpus(12000, rand_salt)
        query = f"Unique verification task {job_id} on ephemeral code."

    messages = [
        {"role": "system", "content": "You are a senior systems engineer reviewing clustered code."},
        {"role": "user", "content": f"Codebase Context:\n```python\n{prefix}\n```\n\nQuestion: {query}"}
    ]
    # Estimate prompt tokens (~4 chars per token)
    prompt_len_approx = len(prefix) // 4
    priority = random.choice([0, 1, 1, 1, 2]) # 0=foreground, 1=normal, 2=background

    # Ample generation budget (384 ~ 1024 tokens) to ensure full reasoning + output decode window
    max_tokens_budget = random.choice([256, 384, 512])
    enable_thinking = random.choice([False, False, True]) # 66% standard generation, 33% deep thinking
    t_start = time.time()
    res = send_chat_completion(messages, max_tokens=max_tokens_budget, priority=priority, enable_thinking=enable_thinking)
    res.update({
        "job_id": job_id,
        "mode": mode,
        "len_tier": len_tier,
        "prompt_tokens_approx": prompt_len_approx,

```

## Engine thinking-field parsing (zig/src/server/fields.zig)
```zig

pub const Thinking = struct { effort: ?[]const u8 = null, enable: ?bool = null };

/// ``thinking_fields``: a request's effort and thinking switch where it sets them.
pub fn thinkingFields(cx: *Cx, body: Value, levels: []const []const u8) errors.Refused!Thinking {
    var out: Thinking = .{};
    const raw = body.get("chat_template_kwargs");
    const kwargs: ?Value = if (raw != null and raw.?.truthy()) raw.? else null;
    const kw_object = kwargs == null or kwargs.? == .object;
    var enable: ?Value = if (kwargs) |k| k.get("enable_thinking") else null;
    const has_enable = kwargs != null and kwargs.?.has("enable_thinking");
    if (kw_object and !has_enable) if (thinkingSwitch(if (kwargs) |k| k.get("thinking") else null)) |sw| {
        enable = .{ .bool = sw };
    };
    var effort = body.field("reasoning_effort");
    if (effort == null and kw_object) if (kwargs) |k| {
        effort = k.field("reasoning_effort");
    };
    if (effort) |e| {
        if (e != .string or !isEffort(e.string)) return cx.refuse("reasoning_effort must be none, minimal, low, medium, high, xhigh or max");
        out.effort = coerceEffort(e.string, levels);
        out.enable = !std.mem.eql(u8, e.string, "none");
    }
    if (kw_object) if (enable) |on| {
        out.enable = on.truthy();
        if (out.enable.? and out.effort != null and std.mem.eql(u8, out.effort.?, "none")) out.effort = null;
    };
    return out;
}

fn isEffort(s: []const u8) bool {
    for (efforts) |e| if (std.mem.eql(u8, e, s)) return true;
    return false;
}

fn order(name: []const u8) ?usize {
    for (effort_order, 0..) |e, i| if (std.mem.eql(u8, e, name)) return i;
    return null;
}

/// The nearest level the template names, ties going higher; xhigh and none stay.
pub fn coerceEffort(effort: []const u8, levels: []const []const u8) []const u8 {
    if (levels.len == 0) {
        if (std.mem.eql(u8, effort, "high") or std.mem.eql(u8, effort, "max")) return "xhigh";
        if (std.mem.eql(u8, effort, "minimal")) return "low";
        return effort;
    }
    for (levels) |l| if (std.mem.eql(u8, l, effort)) return effort;
    if (std.mem.eql(u8, effort, "xhigh") or std.mem.eql(u8, effort, "none")) return effort;
    const want = order(effort) orelse return effort;
    var best: []const u8 = effort;
    var best_key: [2]usize = .{ std.math.maxInt(usize), std.math.maxInt(usize) };
    for (levels) |l| {
        const at = order(l) orelse continue;
        const key: [2]usize = .{ if (at > want) at - want else want - at, at };
        if (key[0] < best_key[0] or (key[0] == best_key[0] and key[1] < best_key[1])) {
            best = l;
            best_key = key;
        }
    }
    return best;
}

/// The efforts a chat template names in quotes (``effort_levels``).
pub fn effortLevels(a: Allocator, template: []const u8) Allocator.Error![]const []const u8 {
    var found: std.ArrayList([]const u8) = .empty;

```

## Model chat template header (effort handling)
```
{#-
    DeepSeek-V4.1 chat template.

    Ported from the checkpoint's own encoding/encoding.py (encode_messages with
    add_default_bos_token=True, drop_thinking=True and no `context`), which is the only
    prompt-format spec DeepSeek ships for this model. Verified string-for-string against
    that implementation by tools/test_chat_template_v41.py.

    Inputs beyond the usual `messages` / `tools` / `add_generation_prompt`:
      enable_thinking     bool, default true   -- reference `thinking_mode`
      reasoning_effort    "low"|"high"|"max" or int 1..100, default "high"
      response_format     JSON schema object, rendered into the system block

    Notes:
      * Role markers use FULLWIDTH vertical bars (U+FF5C).
      * BOS is part of the template, so tokenize with add_special_tokens=False.
      * Tool messages are merged into the preceding user turn as <tool_result> blocks,
        and consecutive user messages merge into one turn, both as the reference does.
      * Tool-call arguments are expected as an object. The reference also accepts a JSON
        string and parses it; Jinja cannot, so a string lands in the reference's own
        fallback shape (one parameter named "arguments").
-#}

{%- set dsml = "｜DSML｜" -%}
{%- set bos = "<｜begin▁of▁sentence｜>" -%}
{%- set eos = "<｜end▁of▁sentence｜>" -%}
{%- set sys_tok = "<｜System｜>" -%}
{%- set user_tok = "<｜User｜>" -%}
{%- set asst_tok = "<｜Assistant｜>" -%}
{%- set reminder_tok = "<｜latest_reminder｜>" -%}
{%- set think_open = "<think>" -%}
{%- set think_close = "</think>" -%}
{%- set thinking = enable_thinking if enable_thinking is defined else true -%}
{#- The reference disables thinking-dropping for the whole conversation as soon as any message
    carries tools, which keeps reasoning in every assistant turn -#}
{%- set drop_thinking = not (tools is defined and tools) -%}

{#- Reasoning effort: "low"/"high"/"max" map to 50/75/100, ints pass through -#}
{%- set effort_in = reasoning_effort if reasoning_effort is defined and reasoning_effort is not none else "high" -%}
{%- if effort_in is string -%}
    {%- if effort_in == "low" -%}{%- set effort = 50 -%}
    {%- elif effort_in == "high" -%}{%- set effort = 75 -%}
    {%- elif effort_in == "max" -%}{%- set effort = 100 -%}
    {%- else -%}{{ raise_exception("Invalid reasoning effort: " ~ effort_in ~ ", expected int 1..100 or low/high/max") }}{%- endif -%}
{%- else -%}

```

## Proxy request rewrites (proxy.py)
```python
        body_json: dict = {}
        orig_tool_choice = None
        orig_effort = None
        effort_rewritten = False
        loop_fallback_bytes: Optional[bytes] = None
        # Request interceptors:
        # 1. DSML Interceptor: rewrite non-standard tool_choice to "auto" for DeepSeek-V4.1
        # 2. Short No-Think Stop-Loss: short tool-less requests (max_tokens <= 256) burn budget in <think> -> set effort="none"
        try:
            body_json = json.loads(body_bytes)
            if isinstance(body_json, dict):
                body_modified = False
                orig_tool_choice = body_json.get("tool_choice")
                tc = orig_tool_choice
                if tc is not None and tc != "auto" and tc != "none":
                    logger.info(f"DSML Interceptor: rewriting tool_choice={tc} to 'auto' for DeepSeek compatibility")
                    body_json["tool_choice"] = "auto"
                    body_modified = True

                orig_effort = body_json.get("reasoning_effort")
                tools_val = body_json.get("tools")
                has_tools = isinstance(tools_val, list) and len(tools_val) > 0
                max_tok_val = body_json.get("max_tokens") if body_json.get("max_tokens") is not None else body_json.get("max_completion_tokens")
                ctk_val = body_json.get("chat_template_kwargs")
                enable_thinking_explicit = ctk_val.get("enable_thinking") if isinstance(ctk_val, dict) else None
                if (
                    SHORT_NO_THINK_MAX_TOKENS > 0
                    and not has_tools
                    and isinstance(max_tok_val, int)
                    and not isinstance(max_tok_val, bool)
                    and 0 < max_tok_val <= SHORT_NO_THINK_MAX_TOKENS
                    and orig_effort != "none"
                    and enable_thinking_explicit is not True
                ):
                    logger.info(
                        f"Short No-Think Stop-Loss: rewriting reasoning_effort={orig_effort!r} to 'none' "
                        f"(max_tokens={max_tok_val}, tools=0)"
                    )
                    body_json["reasoning_effort"] = "none"
                    effort_rewritten = True
                    body_modified = True

                thinking_off = body_json.get("reasoning_effort") == "none" or enable_thinking_explicit is False
                if (
                    LOOP_FALLBACK_ENABLED
                    and path.strip("/").endswith("chat/completions")
                    and not thinking_off
                    and "loop_guard_stop" not in body_json
                    and isinstance(body_json.get("messages"), list)
                ):
                    fb = {k: v for k, v in body_json.items() if k not in ("thinking_budget",)}
                    fb["reasoning_effort"] = LOOP_FALLBACK_EFFORT
                    if LOOP_FALLBACK_EFFORT == "none":
                        ctk_fb = dict(ctk_val) if isinstance(ctk_val, dict) else {}
                        ctk_fb["enable_thinking"] = False
                        fb["chat_template_kwargs"] = ctk_fb
                    loop_fallback_bytes = json.dumps(fb, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                    body_json["loop_guard_stop"] = True
                    body_modified = True

                if body_modified:
                    body_bytes = json.dumps(body_json, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        except Exception:
            pass
        prefix_key = compute_prefix_key(body_bytes)
        if prefix_key:

```

# The test plan under review
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

