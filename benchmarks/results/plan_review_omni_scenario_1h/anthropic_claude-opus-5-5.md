# Review of OmniScenario-1h v0 against the evidence dossier

## 1. Coverage gaps

The traffic stats show the real mix is tool-heavy, and many requests have no max_tokens. The plan under-weights both.

| # | Gap | Evidence | Priority |
|---|---|---|---|
| G1 | **max_tokens absent.** No scenario omits max_tokens. If the engine reserves or allows the full context for these, they are the main source of KV-pool and slot-hold risk. | 121/387 (31%) of real requests have `max_tokens=None`. | must-add |
| G2 | **max_tokens 32768 on agent requests.** S6 caps at 8K–16K and S1 sets no output budget. | 55/387 (14%) use 32768. | must-add |
| G3 | **Tool share too low.** S1+S2 = 40% of requests. | Real: 269/387 (70%) carry tools; 188 returned tool_calls. | must-add (reweight) |
| G4 | **Short requests do not match client behavior.** S3 sends `effort=none`, so the proxy rewrite never fires (it requires `orig_effort != "none"`). | 94 requests have max_tokens=120. 54 were rewritten low→none, and effort=none is 55 total, so almost every real "none" comes from the rewrite. About 40 of the 120-token requests were not rewritten, most likely because they carry tools. That group runs low-effort thinking inside 120 tokens. | must-add: S3a = 120 tok + effort low, no tools (rewrite path). S3b = 120 tok + effort low + tools (no rewrite; measure finish=length and empty content). |
| G5 | **Cancellation rate and timing.** S7 is 5% and fires 1–30 s after stream start. | client_left 45/387 = 11.6%. effort=low has 42 finish=None, so real cancels happen during long low-effort reasoning, not only early. | must-add: weight ~10%. Cancel points: during prefill, during `<think>`, during content, mid tool-call delta. |
| G6 | **Tool-call history shape.** OpenAI clients send `function.arguments` as a JSON string. The template header says a string "lands in the reference's own fallback shape (one parameter named arguments)". Unless the engine parses it before rendering, every multi-turn agent prompt renders malformed history. Also missing: parallel tool calls, multiple tool results merged into one user turn, and `reasoning_content` in history with tools present (`drop_thinking = false`, so all past reasoning is kept and prompts grow). | hist_reasoning_msgs>0: 114 requests. | must-add to S1 |
| G7 | **Proxy queue semantics.** The plan treats every 429 as fast-fail. Queue-full rejection is fast. Queue-timeout rejection takes 4–25 s by design (tiered timeouts). Slot 8 is reserved for P0/P1, so P2 work sees only 7 slots. | 429s in both p17 runs (11, 5) under a closed loop of 8 are consistent with P2 queue timeouts. | must-add: classify 429 by `time_in_queue` and tier. |
| G8 | **Over-context request.** A prompt + max_tokens above the model limit (220K + 32768 = 252K is already close) must return 4xx, not OOM or BadSlot. | max 220,182 prompt tokens observed. | must-add, single request at idle in preflight |
| G9 | **Thinking-alias mismatch between proxy and engine** (details in §2). With `chat_template_kwargs.thinking=true` and max_tokens ≤256, the proxy rewrites effort to none, then the engine turns thinking back on at default high. | Code reading. | must-add (one matrix cell) |
| G10 | **Request correlation ID** across client, proxy audit, and engine `done` log. Without it, "rewrite only within rules", "effort coerced correctly" and "fallback fired" cannot be checked per request. | — | must-add (instrumentation) |
| G11 | **Imprint/NVMe capacity side effect.** Many unique 30K–220K prompts can evict the external user's cached long sessions. | Real >100K prompts run at 0.97 cached and TTFT p50 4.9 s; cold is ~100 s. | must-add: pre/post check of state count, bytes, disk free |
| G12 | tool_choice=none with tools present | 2 real | nice-to-have |
| G13 | `max_completion_tokens` alias (the proxy rewrite reads it) and `response_format` (the template renders it) | 0 observed / unknown | nice-to-have |
| G14 | `/v1/responses`, `/v1/messages` | 0/387 real; all traffic is chat/completions | nice-to-have, outside hard gates (see §2) |
| G15 | Malformed JSON body. The proxy does `except Exception: pass` and forwards the raw bytes; the engine should return 400. | — | nice-to-have, idle |
| G16 | Open-loop Poisson arrivals at ~1.1× capacity for a few minutes | Real 429s are rare (1) | nice-to-have |

Weighting note: real traffic averages ~10 req/h, with a peak of 76 in one hour. N=8 closed-loop is a stress test with real-traffic shapes, not a replay. Section 2's claim that "≤2 concurrent long contexts matches real traffic" is not shown in the dossier.

## 2. Thinking matrix vs the actual code

### Wrong or unsupported assumptions

1. **Integer effort (25/50/75/100) is untestable as a behavior.**
   - `thinkingFields` refuses any `reasoning_effort` that is `!= .string` or not in `efforts`. This applies at the top level and inside `chat_template_kwargs`.
   - The template's int 1..100 path is unreachable through the API.
   - Turn the cell into a negative test: expect 400 with the refusal message, and no slot consumed.

2. **xhigh does not have "unknown behavior".**
   - `coerceEffort` returns `xhigh` unchanged, because the levels list is non-empty and xhigh is special-cased.
   - The template's string branch accepts only low/high/max and otherwise calls `raise_exception("Invalid reasoning effort...")`.
   - The expected result is a render failure. The only question is whether it surfaces as 4xx or 500, and whether the slot is released.
   - Run it once at idle in preflight, not under load. As written, it can trip the "HTTP 500 = 0" hard gate from a test-induced path.

3. **medium→high is not established.**
   - The doc comment says "ties going higher".
   - The code breaks ties by choosing the *smaller* `effort_order` index (`key[1] < best_key[1]`). `effort_order` is not in the dossier.
   - If it is ascending (none…max, like the refusal message's list), medium→low. If it is descending, medium→high.
   - The engine-log observation (high 54, low 19, none 24, no medium) does not decide this. It fits either mapping, and also fits there simply being no medium requests in that 6 h window.
   - Determine the mapping from the engine `done ... effort=` line on one request. Do not hard-code it in the expected-results table.

4. **Behavior count.**
   - Distinct reachable states are: off (none), 50 (low, minimal), 75 (high, plus medium if it maps up), 100 (max), and error (xhigh, int, invalid).
   - An absent effort with thinking on renders at the template default, high (75).

5. **Conflict rules need explicit expected values, not "依程式規則" ("per the code's rules").**

   | Request | Expected |
   |---|---|
   | `effort=none` + `enable_thinking=true` | effort set to null, thinking ON at template default high |
   | `effort=high` + `enable_thinking=false` | thinking OFF |
   | `chat_template_kwargs.thinking` | consulted only if the `enable_thinking` key is absent |
   | `chat_template_kwargs.reasoning_effort` | used only if top-level `reasoning_effort` is absent |
   | `chat_template_kwargs` non-object (e.g., a string) | kwargs effort and enable both ignored |
   | `chat_template_kwargs = {}` | treated as absent (falsy) |
   | `minimal` | low, enable=true |

6. **Proxy and engine disagree on the thinking switch.**
   - The proxy reads only `chat_template_kwargs.enable_thinking` and top-level `reasoning_effort`.
   - Consequence 1: `{max_tokens:120, chat_template_kwargs:{thinking:true}}` is rewritten to `effort=none`. The engine then sets enable=true from the `thinking` alias, nulls the effort, and thinks at high within 120 tokens. The stop-loss is defeated.
   - Consequence 2: `thinking:false` is not recognized as `thinking_off` by the proxy, so loop fallback is armed for a non-thinking request.
   - Consequence 3: an effort in `chat_template_kwargs` is overridden by the injected top-level none.
   - These are real cells. Put them in.

7. **The proxy confounds the entry-point cells.**
   - Any cell with max_tokens ≤256, no tools and no explicit `enable_thinking=true` is rewritten to none on :8889.
   - Run the entry-point and coercion cells against the engine on :8888, using greedy decoding and max_tokens ≥300.
   - Run only the rewrite, fallback and tool_choice cells through :8889.

8. **Loop-guard fallback.**
   - It is armed only for paths ending in `chat/completions`, so the fallback cells on `/responses` and `/messages` are invalid.
   - Real rate: fallback fired 0 times and shadow detection 4 times in 39 h / 387 requests. Natural triggering in one hour is ≈0.
   - The "100% success" gate passes vacuously at 0 triggers. Require ≥3 actual triggers, induced deterministically. Otherwise report the result as *not exercised*, which does not count as passing.
   - Record `LOOP_FALLBACK_ENABLED` and `LOOP_FALLBACK_EFFORT`.
   - Define what streaming "接續" ("continuation") means at the client: whether partial reasoning was already sent, and what the final payload must contain.
   - The fallback body drops `thinking_budget`, keeps tools, and does not carry `loop_guard_stop`. Assert all three.

9. **thinking_budget.**
   - Engine handling is not in the dossier, and real traffic does not use it.
   - "thinkCut → tools" is declared a known unfixed bug. Mark it xfail. As a hard gate it fails every run; as no gate it is useless.
   - Reduce to 2 budgets × tools/no-tools.

10. **Reasoning history.**
    - The template already drops all past reasoning when there are no tools, and keeps all of it when tools are present.
    - `--keep-last-n-reasoning 2` does not appear anywhere in the dossier. If it is not in the p17 recipe, it needs a restart, which the plan excludes, so the cell is untestable.
    - If it is enabled, it rewrites an earlier turn on every request. The cached prefix must then end at the third-from-last assistant turn. Gate on the per-turn `cached_tokens` boundary, not on "does not crash".

11. **Endpoints.**
    - `thinking.type adaptive` and `output_config.effort` are not grounded in any shown code.
    - The proxy's tool_choice rewrite turns an Anthropic `{"type":"auto"}` object into the string `"auto"`.
    - The short rewrite ignores the request path. Anthropic requests always carry max_tokens, so tool-less ≤256 requests get `reasoning_effort` injected.
    - `/responses` uses `max_output_tokens`, which the proxy does not read.
    - Expect failures. Keep these cells nice-to-have and outside the hard gates.

12. **tool_choice.**
    - `required` and `function` are rewritten to `auto`, so "required forces a call" cannot be tested through the proxy.
    - S2's "200 with tool_calls" expectation is not guaranteed by design.
    - Real data: 10 of the ~94 function requests (~11%) burned all 3000 tokens in reasoning. With tools, finish=length leaves the loop guard irrelevant.

13. **Reproducibility.**
    - A fixed seed at N=8 with continuous batching and MTP is not reproducible.
    - Stream vs non-stream "identical thinking content" holds only structurally: reasoning present, same finish class, valid tool call.

14. **Monotonic thinking length is underpowered.**
    - A 3-seed median on heavy-tailed lengths cannot show it. Real data: low p50/p90 120/1078 vs high 130/910, task-confounded.
    - Make it observational. The hard check is the per-request engine-log effort value.

15. **Effort-vs-accuracy with 2–3 seeds per cell** gives no statistical signal. AIME at high effort costs ~250–500 slot-seconds per item. Cut it from the hour.

## 3. Time budget and statistical power

**Throughput assumptions.**
- c4 aggregate is ~130 tok/s, so ~20–25 tok/s per stream at 8 concurrent, and lower with long attention.
- Cold prefill is ~2,200 tok/s at 8K and slower at 200K. Real 220K TTFT reached 125 s.

**Main load as written.** 36 min × 8 slots = 17,280 slot-s. Estimated slot-time per request:

| Scenario | Slot-time per request |
|---|---|
| S1 | ~35 s |
| S2 | ~45 s |
| S3 | ~7 s |
| S4 | ~30 s |
| S5 (two turns) | ~25 s |
| S6 (8–16K tokens at ~20 tok/s) | 400–800 s |
| S7 | ~15 s |
| S8 | ~30 s |

- Weighted mean ≈ 74 s, so about 230 main-load requests.
- **S6 consumes about 65% of slot time while being 8% of requests.** About 5 of 8 workers sit in S6 decode at any moment.
- S6 requests started after ~min 42 cannot finish by 55, so the S6 sample is censored toward short answers.

**Realistic counts vs the plan's figures.**

| Scenario | Plan | Realistic | Consequence |
|---|---|---|---|
| S6 | 30–45 | ≈19 | 0-loop upper 95% bound by rule of three ≈ 16%, against a real shadow-loop rate of ~1%. Useless as a loop measure. Measure loop rate over all ~250 thinking requests instead. |
| S7 | 20–30 | ≈12 | |
| S2 | — | ≈23 | 95% CI on the ~11% all-reasoning rate is roughly 1–30% |

- P0 probes every 5 min gives 7 samples, too few for a latency gate.

**Thinking matrix as written.**
- About 133 requests at ~45 s average ≈ 6,000 slot-s, which exceeds 12 min × 8 = 5,760.
- The loop prompts and the 10-turn sequential history chain bound wall time.
- It does not fit unless quality, endpoints, int-effort-as-behavior, and the 600 s non-stream timeout are cut.

**Standard regression.**
- At 893 requests × 30 s / 8 slots ≈ 56 min, the p17 "1-hour" run *is* the marathon.
- The full standard regression and a new 60-minute scenario cannot both fit in one hour. Only the front-part benchmarks fit.

**Cuts and merges.**
- Cap S6 at max_tokens 4K–8K and run it on one dedicated worker. Long outputs are covered by S1 with 32768 or no max_tokens.
- Move to separate runs: AIME/GSM8K accuracy, /responses and /messages, 600 s non-stream, xhigh and int effort (idle preflight only).
- Run the main load at N=7 to leave slot 8 for P0 probes and the external client.
- Stop admitting new requests at min 52 and drain.

**Revised schedule** (main-load mean ≈ 47 s → about 300–330 requests; S2 ≈ 50, S7 ≈ 33):

| Time | Content |
|---|---|
| T-20..0 (untimed) | Health, manifest shas, containers. Imprint count/bytes/age and NVMe free. MemAvailable/swap on both nodes. External client paused and confirmed, then monitored continuously. Telemetry started. Correlation IDs on. Idle safety singles: xhigh, int effort, over-context 4xx, malformed JSON, one 32K cancel-during-prefill (check slot release and no BadSlot), one 220K cold prefill with memory watched. **Abort the run if any of these gives a 500, BadSlot, or MemAvailable < 6 GiB.** |
| 00:00–01:30 | OmniBench standard front: same order, settings and cold-nonce conventions as the p17 runs. This is the comparable block. |
| 01:30–07:00 | run_full_eval: Part A 30q, B, C (incl. 429 ladder), D |
| 07:00–08:30 | Matrix M1 on :8888 (greedy, max_tokens 300, 1 rep). About 16 precedence/entry/coercion cells, checked by engine log + `reasoning_content` presence. Effort mapping resolved here. |
| 07:00–15:00 (parallel, 1 worker) | M5: 10-turn tool chain with string arguments, parallel tool results, `reasoning_content` in history. Per-turn `cached_tokens` recorded. |
| 07:00–15:00 (parallel, 1 worker) | M6: loop induction ×3, stream and non-stream, through :8889 |
| 08:30–11:30 | M2 effort behavior: 4 prompts × {none, low, high, max} × 1, max_tokens 2048 (observational). Plus vision × {none, high} × 1. |
| 11:30–15:00 | M3 proxy cells: rewrite incl. alias cases, 6 cells. M4: tool_choice {auto, required, function, none} × {low, high}, max_tokens 3000. thinking_budget {0, 1024} × tools/no-tools (xfail where known). |
| 15:00–52:00 | Main load, N=7 closed loop, revised weights (S1 40, S2 15, S3a/b 15, S4 10, S5 5, S6 5 on a dedicated worker, S7 10). P0 TTFT probe every 60 s (~36 samples). |
| 19:00 | Burst 1: 16 P2 + 2 P0 open-loop within 50 ms |
| 22:00 | 220K cold needle with nonce on the first line. Pre-reserved in the long-context token budget; S1 cold starts paused until its first token. Window = event duration + 60 s. |
| 27:00 | Loop induction ×3, only if fewer than 3 triggers occurred in M6 |
| 31:00 / 34:00 | 100K prefill cancels, sequential, at 20 s and 40 s into prefill |
| 38:00 | S1 session A revisit. Confirm RAM eviction from cache metrics first. |
| 41:00 | Burst 2: mixed P0/P1/P2 |
| 47:00 | S1 session B revisit |
| 52:00–55:00 | Drain: no new admissions. Anything still running at 55:00 is cancelled and marked censored. |
| 55:00–60:00 | 30 s settle. CLOSE_WAIT, memory and Imprint snapshots. 5 idle P0 probes. 32K cut-in with nonce (observational only). |
| post | 2 min cool-down, then `run_decode_gate.py --reps 3`, compared with the block-1 decode number from this same run. |

## 4. Measurement validity

### Confounders

- **External traffic.** The "lo" baseline started 00:51 on 11-15, inside the client's busiest hours (0–3). It has fewer requests (893 vs 925), more 429s (11 vs 5) and a worse TTFT p95 (24.4 vs 22.5). Check the audit log for external requests in both baseline windows before treating them as clean. A 90 s idle guard is not enough; tag every result window with the external request count.
- **Imprint state.**
  - The HIGH_HIT corpora and the standard 8K "cached" test likely already persist on NVMe from earlier runs.
  - Do not purge: that degrades production, since the external user's sessions run at 0.97 hit.
  - Use nonces for every "cold" measurement. Record hit/miss per request from `cached_tokens`.
  - Verify the RAM→NVMe path through engine cache metrics, not by inferring from TTFT.
- **Order and thermal effects.**
  - The 32K cut-in at the end runs after heat soak, cache churn and fragmentation, so it is not comparable to the p17 cut-in. Keep only the front-block value for comparison.
  - The bursts at 19 and 41 run under different thermal states. Compare each event to its own pre-window.
- **Closed-loop masking.**
  - S7's "active_running falls back within 5 s" cannot be observed. The worker refills the slot immediately, and 1 Hz telemetry would blur it anyway.
  - Use the engine's per-slot free/cancel log with timestamps, or idle that worker for 10 s after each cancel.
  - Whether a TP=2 prefill can be aborted mid-chunk is unknown. If it cannot, a 100K cancel holds the slot ~50 s, and the 5 s gate fails by design. Measure in the pilot first.
- **HTTP 200 vs valid delivery.**
  - With streaming, 200 is sent before any generation.
  - Define valid delivery as all of:
    - the stream ends with a finish_reason and `[DONE]`;
    - finish ∈ {stop, tool_calls}, or length only where the cell expects it;
    - non-empty content or tool_calls;
    - tool args parse and names exist in the schema;
    - no DSML in content;
    - for fallback, a final answer is present.
  - finish=length with 0 content tokens is invalid even though it returned 200.
- **TTFE vs TTFT.**
  - A first SSE event can be a role or keepalive chunk emitted before prefill starts.
  - Gate on TTFT: the first reasoning or content token.
  - p17's cut_in_32k was 0.74–0.78 s idle, so ≤1.0 s is a reasonable idle target. Under N=7 load with a concurrent 220K prefill it is unproven; set the loaded threshold from the pilot.
- **Priority mix.** The S4 generator sends 20% P0 and 60% P1. Test traffic then occupies the reserved slot and queue positions meant for probes and the external client. In the main load, use P1/P2 only; reserve P0 for probes and burst P0 items.

### Gates

| Gate | Problem | Fix |
|---|---|---|
| Valid delivery ≥98% | p17 reached only 98.77% / 99.46% on HTTP 200 alone, with lighter work. Longer slot holds (200K, 3000-token S2) raise P2 queue-timeout 429s. S2's known ~11% defect at 10–15% weight costs 1–1.6 points by itself. Likely **fails a healthy system**. | Exclude S7, designated burst overflow, and S2 xfail. Count 429s separately by type. Hard-gate engine-attributable failures = 0 (500, truncated stream, DSML leak, unparsable args). Set the delivery threshold after the pilot. |
| Fast-fail <10 ms | A Python asyncio client handling ~24 concurrent streams adds jitter. It also mixes in queue-timeout 429s, which take 4–25 s by design. | Measure server-side from the proxy log (≤10 ms) or client-side (p99 ≤50 ms). Queue-full 429s only, Retry-After present. |
| P0 rejected = 0 | Fails a healthy system if the queue is already full of P0/P1 and the proxy does not preempt. | State the proxy policy; gate on it. With P0 limited to probes this gate becomes meaningful. |
| P0 TTFE ≤1.0 s | Measures the wrong event, and n=7. | TTFT, ~36 probes, p95 threshold from the pilot, report the max. |
| Loop fallback 100% | **Passes a broken system** at 0 triggers. | Require ≥3 induced triggers. |
| GPU clock ≥2350 MHz for 95% | No baseline in p17 output. The MS-DTC governor may lower clocks deliberately, so it can fail a healthy system. | Observational on the first run. |
| MemAvailable ≥3.0 GiB, Node 1 only | No p17 memory baseline (`mem_after_gib None`). Rank1 is unmonitored. | Monitor both nodes. Abort at 4 GiB; gate at 3 GiB. |
| 30q ≥28/30 | p17's Part A score is not in the dossier. Under sampling at 95% true accuracy, P(≤27) ≈ 19%. | Use p17 score −1 if greedy-deterministic; otherwise a binomial-justified threshold. |
| Thinking length monotonic | Underpowered (§2.14). | Observational. Gate on logged effort and enable state per request ID. |
| "All entry points consistent" | Can't check from output text. | Engine log plus reasoning presence, greedy, :8888. |
| S1 tool format 100% | Fine for parse errors and DSML leaks, which are engine-level. "Called the right tool / all required params" is model quality. | Keep 100% for parse/DSML; make tool choice and params observational or ≥95%. |
| CLOSE_WAIT = 0 at end | External sockets and teardown transients. | After a 30 s settle, counting only test-client↔proxy and proxy↔engine sockets. |
| Decode gate ≥95%, reps 1 | p17 greedy spread 89.5–90.5 (1.1%); 95% is fine. A single rep right after heat soak conflates thermal effects with state degradation. | Reps 3 after a 2 min cool-down, vs this run's block-1 value. |
| S6 "retry 429 until answered" | Hides 429s and adds load. | Count retries explicitly. |

## 5. Safety

- **KV pool and unified memory.**
  - The "≤2 long concurrent" cap counts requests and ignores the events: the 220K needle, two 100K cancels (originally concurrent) and revisits push in-flight long contexts to 3–4.
  - Replace it with a global in-flight token budget (prompt + max_tokens) enforced by the client, covering events and S1 together.
  - Size the budget from the pilot's MemAvailable readings on both nodes.
  - Until the engine's admission behavior for absent max_tokens is known, cap it in the pilot before allowing it in the full run.
- **Cancel during prefill under TP=2.** This is the most likely path to BadSlot or follow_refused (a rank desync). Test it with a single cancel at idle in preflight first, then sequential cancels only. Any occurrence of either error aborts the run.
- **xhigh and int effort.** Single requests at idle only. Confirm 4xx and a released slot before any load.
- **220K cold prefill.** About 100–150 s of prefill-dominated GPU time.
  - The external client is starved for that period if it is not paused.
  - If prefill is not chunked against decode, all 7 other streams stall.
  - Pause S1 cold starts during the event.
- **Cache eviction affects production after the test.**
  - Several million unique tokens of long prompts can evict the external user's 100K–220K states from the 2.5 GiB RAM cache and possibly from NVMe. That user's TTFT then goes from ~5 s to ~100 s on their next resume.
  - Check Imprint capacity and eviction policy beforehand, and keep the number of unique long sessions small (4–6 total, grown turn by turn).
- **External user and the reserved slot.** The main load at N=8 with P0/P1 traffic takes slot 8 away from the external user. Use N=7, P1/P2 only, and keep the client paused for the whole hour.
- **No abort criteria in the plan.** Add a kill switch that stops admissions and cancels in-flight work on any of:
  - MemAvailable < 4 GiB on either node;
  - swap growth;
  - BadSlot, follow_refused, OOM or panic;
  - engine `/health` not ok for 5 s.
- **Test-host load.** Run the load client and telemetry off the GB10 nodes. Use `docker logs --since` or a single follower, not repeated full log reads at 1 Hz.

## 6. Comparability with the p17 baseline

**First, verify the baseline identity.**
- The two runs are labeled `p16_tokenmapfix`, while the target is p17 `v2b2-p17-loop-fallback` / engine e772dec6.
- If the baselines predate loop fallback, every thinking request body differed: no `loop_guard_stop` was set and no fallback was armed.

**Comparable**, if run first, with the same order and settings, cold-state nonces, and a verified-idle external client. Noise bands are the observed spread between the two p17 runs:

| Metric | Observed range | Spread |
|---|---|---|
| quality_pass, tools_pass | — | — |
| prefill_8k_cold | 2234.9–2241.6 tok/s | ±0.3% |
| prefill_8k_cached_ttft | 0.908–0.926 s | ±2% |
| greedy_tok_s | 89.5–90.5 | ±1.2% |
| mtp_accept | 0.7401 | identical |
| sampling_tok_s | 71.5–72.6 | ±1.5% |
| c1 / c2 / c4 | — | up to ±2.3% (c2) |
| cut_in_32k (front block only) | 0.744–0.780 s | ±5% |

Treat a difference beyond ~2× these spreads as a regression signal.

**Not comparable:**
- marathon_requests, ok_200 and ok_rate, status_codes, ttft p50/p95, wall mean/p95, gen_tokens, cached_tokens, loop_rate.
- loop_lowhit_medium (p17: 0/139, 0/162). S4 at 10–20% weight yields under ~10 LOW_HIT-medium requests.
- The S4 subset under mixed load: per-request latency depends on what shares the batch (200K prefills, tool loops). The plan's claim that S4 is comparable "by category" is wrong for latency and loop counts. It is valid only for per-request correctness.
- Memory: p17 has no memory figure.
- The end-of-run 32K cut-in.

If a marathon comparison is required for release, run `omni_eval_1hour` as a separate hour. It cannot be included in this one.

## Prioritized changes

1. **Run a pilot at idle.** Include xhigh, int effort, over-context, malformed JSON, a 32K and a 100K cancel during prefill, and one 220K cold prefill with both nodes' memory watched. Add abort criteria (MemAvailable < 4 GiB, swap growth, BadSlot/follow_refused/OOM/panic, health not ok), wired to a kill switch.
2. **Replace the long-context count cap with an in-flight token budget** (prompt + max_tokens) that includes events. Run the two 100K cancels sequentially.
3. **Reweight the main load to real traffic.**
   - Tools ~55–70%.
   - max_tokens absent (31%) and 32768 (14%) on agent requests.
   - S3 sent as the client sends it: effort low, with and without tools.
   - S7 at ~10%, cancelling during prefill, reasoning, content and tool-call deltas.
4. **Cap S6** at 4K–8K max_tokens on one dedicated worker. Compute loop rate over all thinking requests (~250) plus shadow detections.
5. **Add to S1:** string-typed tool arguments in history, parallel tool calls/results, `reasoning_content` in history. Check per-turn `cached_tokens`.
6. **Fix the matrix expectations.**
   - int effort → 400; xhigh → template error (expect 4xx).
   - Resolve the medium mapping empirically.
   - `enable_thinking=true` + `effort=none` → high.
   - Add the proxy/engine alias-mismatch cells.
7. **Run entry and coercion cells on :8888**, greedy, max_tokens ≥300, checked via engine log. Run only rewrite, fallback and tool_choice cells via :8889.
8. **Cut from the hour:** effort-accuracy (AIME/GSM8K), /responses and /messages, 600 s non-stream, and `--keep-last-n-reasoning` unless it is in the current recipe.
9. **Loop fallback gate requires ≥3 deterministic triggers.** Define streaming continuation semantics. Assert that `thinking_budget` is dropped and tools are kept.
10. **Mark thinkCut→tools and S2 all-reasoning as xfail** with tracked rates, not hard gates.
11. **Define valid delivery explicitly.**
    - Hard-gate engine-attributable failures at 0.
    - Split 429s into queue-full vs queue-timeout and by priority.
    - Set the delivery threshold from the pilot, not 98%.
12. **Replace TTFE with TTFT.**
    - P0 probe every 60 s.
    - Fast-fail measured at the proxy (server-side ≤10 ms) or client-side (p99 ≤50 ms).
    - P0 reserved for probes; main load at N=7 using P1/P2.
13. **Demote the GPU-clock gate to observational.** Monitor MemAvailable on both nodes. Make the 30q threshold relative to p17's Part A score. Run the decode gate with 3 reps after a 2 min cool-down.
14. **Make S7 slot release observable** through engine per-slot cancel/free logs or a worker idle after each cancel, plus correlation IDs across client, proxy and engine.
15. **Comparability.**
    - Verify the baseline recipe (p16 vs p17 labels) and external traffic in both baseline windows.
    - Compare only front-block metrics against the stated noise bands.
    - Record Imprint state and capacity before and after; keep unique long sessions to 4–6 to limit eviction of the external user's cache.
    - Pause the external client for the whole hour.