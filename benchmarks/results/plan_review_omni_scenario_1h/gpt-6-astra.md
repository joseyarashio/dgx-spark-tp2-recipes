## Overall finding

This cannot be a one-hour test with no blind spots. It can be a one-hour release regression plus a bounded production smoke/stress test, with explicit exclusions and incomplete statistical coverage.

The draft mixes API conformance, model-quality experiments, cache benchmarks, saturation tests, and production fault probes. Some expected results are not supported by the supplied code. Several gates either reject healthy behavior or allow real failures to pass.

There is also a schedule error: the main workload runs from minute 19 to 55, but its events include “minute 44” and “minute 50.” If those are relative to workload start, they occur at minutes 63 and 69. If they are absolute, the minute-12 burst interrupts the thinking matrix. Use one absolute clock.

## 1. Coverage gaps

The proposed weights are not actually traffic-proportional. Real traffic has tools on 269/387 requests, or **69.5%**, versus 40% explicitly assigned to S1/S2. Real cancellations are **11.6%**, versus 5%; non-streaming is **0.26%**, versus 2%. Oversampling rare paths is reasonable, but label this a coverage workload, not a traffic replay.

The dossier gives message-count p90 as **105**, not 107. It does not establish that real long-context concurrency never exceeds two.

| Gap | Priority | Concrete addition |
|---|---|---|
| Reasoning-only exhaustion without delivery | **Must-add** | Reproduce the ten low + named-function cases that consumed all 3,000 tokens in reasoning. Distinguish legal HTTP completion from task delivery. Test a paired high/none control. |
| Real output-budget distribution | **Must-add** | Include omitted `max_tokens`—121 requests—and 120, 3,000, and 32,768. Test `max_completion_tokens` and precedence when both fields exist. A 32,768-token cap need not imply generating that many tokens. |
| Long-history tool conversations | **Must-add** | Exercise approximately 105 messages, assistant reasoning, assistant tool calls, tool results, and subsequent turns. Validate references and conversation continuity, not just one tool-call JSON object. |
| Template serialization branches | **Must-add** | Tool-result merging, consecutive user merging, tool arguments as objects versus JSON strings, and history with/without current `tools`. The template documents different handling for string arguments. |
| Cancellation lifecycle | **Must-add** | Cancel while queued, during prefill before any SSE event, during reasoning decode, during content/tool streaming, and during fallback. “After streaming starts” does not cover a request still prefilling. |
| Priority and queue behavior | **Must-add** | P0/P1 reserved-slot admission, P2 exclusion from that reservation, queue saturation, each configured timeout tier, queued cancellation, and recovery after overload. |
| Rewrite boundaries and bypasses | **Must-add** | Test 255/256/257 tokens; tools absent/empty/nonempty; explicit true/false; kwargs effort; alias switch; and an explicitly supplied `loop_guard_stop`. |
| Cache correctness, not only hit rate | **Must-add** | Cold, RAM hit, verified Imprint hit, and partial-prefix reuse. Change the suffix, tool schema, effort, and history and verify answers do not reuse stale state. |
| Valid stream delivery | **Must-add** | Reassemble reasoning/content/tool argument deltas; require valid termination, usable output, correct finish classification, and no duplicate response after fallback. |
| Structured output | **Must-add, bounded smoke** | The template supports `response_format` schema rendering. Check JSON/schema validity with thinking enabled and disabled. Do not assume rendering guarantees constrained decoding. |
| Alternative endpoints | **Nice-to-have unless part of the release contract** | All observed traffic uses chat completions. Establish actual route and adapter support before allocating live cells to Responses or Anthropic. |
| Long non-streaming timeout boundary | **Nice-to-have; separate test** | A 600-second timeout experiment occupies most of the matrix window and is not a normal functional cell. |
| Large effort-quality benchmark | **Nice-to-have; separate test** | Run paired, adequately sampled math/tool evaluations outside the hour. |
| Restart, rank failure, cold-pool recovery | **Separate maintenance test** | Their exclusion is necessary for production safety, but it means “no blind spots” is false. |

Use mocked tools only. Do not execute generated `bash` or `edit_file` calls against production.

## 2. Thinking coverage: code-grounded corrections

### Effort parsing and template behavior

The draft conflates three separate stages:

1. The API parser accepts or rejects a value.
2. The parser resolves effort and enable flags.
3. The renderer receives a value and produces a prompt.

Instrument all three where possible. Reasoning token count is not proof of which path executed.

| Input/path | What the supplied code establishes |
|---|---|
| Top-level effort versus kwargs effort | Top-level effort is consulted first; kwargs effort is used only if it is absent. |
| String effort | Only the seven listed strings pass `isEffort`. |
| Integer effort 25/50/75/100 | Rejected by this parser if supplied through either `reasoning_effort` field. Template support for integers does not make them API-supported. |
| `minimal` | Expected to coerce to `low` for the stated template levels; assert this in a parser test. |
| `medium` | The draft expects `high`, but the definition of `effort_order` is not included. The implementation breaks ties using the **smaller order index**. Verify the actual ordering rather than relying on the comment. |
| `xhigh` | Explicitly preserved by coercion. The shown template rejects unrecognized strings. Unless another layer translates it, this is an error path, not a fourth-level alias. |
| `none` | Produces effort `none` and enable false. The shown template does not accept the literal effort `none`; successful production behavior implies further handling or suppression before rendering. Inspect that bridge. |
| `enable_thinking=true` with effort `none` | Sets enable true and clears effort to null. The template’s default effort is high if no other layer changes it. |
| `enable_thinking=false` with high | Sets enable false while retaining parsed effort high. Verify effective rendering, not just the logged effort. |
| `thinking` alias | Consulted only when `enable_thinking` is absent, not merely false. Its accepted values depend on `thinkingSwitch`, which is not supplied. |
| Invalid switch types | `enable_thinking` uses truthiness here. A blanket “all illegal values return 400” assertion is not justified. |

The missing `effort_order`, actual extracted `effortLevels`, and renderer bridge are pre-test inspection requirements. The six-hour log containing no medium/max is supporting observation, not proof of coercion or max support.

Do not gate on “seven names produce exactly four behaviors.” `xhigh` contradicts that assumption. Do not gate on monotonic reasoning length: even valid low/high/max settings need not produce monotonically longer reasoning on every prompt, especially with only three samples and output truncation.

### Proxy rewriting

The short-output interceptor covers more than low effort. It rewrites any top-level effort other than `none`, including an absent effort, when the other conditions hold.

Required boundary cases include:

- `max_tokens` 255, 256, 257, zero, negative, boolean, and omitted.
- `max_completion_tokens` used only when `max_tokens` is null/absent.
- Tools absent, `[]`, and nonempty.
- `enable_thinking` exactly true, false, and absent.
- Effort in kwargs only.
- The `thinking` alias set true.

The last case matters: the proxy checks explicit `enable_thinking`, not the alias. It can rewrite effort to none while the engine subsequently resolves the alias as enabled. Log original request, rewritten request, parser output, and rendered thinking state.

`required` and named-function choices become **auto**. Therefore:

- A tool call is not guaranteed by the effective API choice.
- The specifically named function is not guaranteed.
- Tool-call absence may be an application task failure, but is not necessarily a parser/protocol failure.

Separate those assertions.

### Loop fallback

The supplied interceptor only prepares a fallback for paths ending in `chat/completions`, with a messages list, thinking not classified as off, and **no `loop_guard_stop` key**. Even an explicit false value suppresses this automatic path.

Verify:

- Fallback gets effort none and explicit `enable_thinking=false`.
- `thinking_budget` is removed.
- Original request identity links to the retry.
- At most one retry occurs.
- Client cancellation suppresses unnecessary continuation.
- Streaming does not expose duplicated, malformed, or contradictory partial results.
- Non-streaming returns one complete response.

The excerpt does not show fallback delivery logic, so “resend and continue successfully” is not yet established.

Real traffic had **zero fallback firings** and four shadow detections. Three known prompts cannot guarantee a live trigger. Use deterministic loop-event injection in a test proxy or isolated harness; keep production prompts as observational probes. Zero triggers must produce **not exercised**, not 100% success.

### `thinking_budget` and reasoning history

No `thinking_budget` implementation is supplied. The plan cannot yet assert:

- Whether zero means disabled, unlimited, or immediate cutoff.
- Whether cutoff inserts `</think>`.
- Whether accounting includes special tokens.
- What happens when output budget is smaller.
- What happens inside a tool transition.

Inspect that implementation first. Then test below/at/above cutoff with and without tools, and with a smaller total output cap.

Likewise, `--keep-last-n-reasoning 2` is not grounded in the supplied implementation. Do not change a production startup flag merely to create a matrix cell.

The template explicitly sets `drop_thinking` based on **current nonempty tools**, preserving reasoning when tools are present. That conflicts with a universal expectation that all but the last two reasoning turns disappear. Inspect preprocessing order and rendered prompts using sentinel reasoning strings. Test tools present/absent and historical tool messages with no current tools.

“Streaming and non-streaming thinking content is identical” is also too strong under sampling and concurrent execution. Require equivalent structure and task validity; use deterministic controls for exact comparisons.

## 3. Time budget and statistical power

### Capacity

At eight continuously occupied slots and 30 seconds per request:

- Full-hour ideal ceiling: **960 requests**.
- Twelve-minute matrix: **192 requests**.
- Thirty-six-minute main workload: **576 requests**.

These are optimistic capacity calculations, not forecasts. They exclude serial regressions, queue waits, retries, long generations, and variable prefill time. Reserving a slot for P0/P1 can also reduce usable concurrency for other priorities.

At 2,200 tokens/s cold prefill:

| Prompt | Approximate cold prefill |
|---|---:|
| 8K | 3.6 s |
| 32K | 14.5 s |
| 100K | 45.5 s |
| 220K | 100 s |

These assume comparable throughput at larger lengths; they are not guaranteed scaling. Two cold long requests do not necessarily prefill independently at that rate.

An 8K–16K output at the baseline single-stream 71–90 tokens/s is roughly **90–225 seconds**, before prefill. Under contention it can take longer. S6 retries further invalidate the 30-second assumption.

The matrix is far too large. Just seven efforts × four tool choices × two stream modes × three repetitions is **168 requests**, before budgets, history, vision, aliases, endpoints, and fallback. Use equivalence classes and pairwise interactions, not a Cartesian product.

### Power

For zero failures, the approximate one-sided 95% failure-rate upper bound is `3/n`:

- 3 samples: approximately 63% using the exact binomial bound—not evidence of reliability.
- 30 samples: approximately 9.5%.
- 45 samples: approximately 6.4%.
- About **149 zero-failure samples** are needed to bound failure probability below 2%.

Thus S6, S7, S8, individual effort cells, and fallback cells are functional probes, not reliability measurements. Per-cell p95 from two or three observations is meaningless.

The predicted S6 30–45 and S7 20–30 counts apply, at best, to the main-workload sample count—not all requests across the hour. Multi-turn jobs and fallback attempts must not be silently counted as independent initial jobs.

### Revised schedule

This schedule assumes the exact standard regression bundle has been timed and fits eight minutes. If it overruns, shorten the mixed workload, not the release regression.

| Absolute minute | Work |
|---|---|
| 00–08 | Exact standard release regression, unchanged. Tag its traffic separately. Avoid repeating overlapping OmniBench components unless both suites are genuinely mandatory. |
| 08–10 | Reconcile results, establish controlled cache fixtures, verify effective thinking configuration. |
| 10–16 | Bounded thinking/API smoke: approximately 40–60 prioritized requests. Cover effective levels, conflicts, short rewrite boundaries, tools, history, and validated budget behavior. |
| 16–18 | Small staged priority/queue bursts; verify admission, timeout, cancellation, and recovery. Pause ordinary load for interpretable results. |
| 18–30 | Mixed traffic block A with explicit quotas; mostly warmed long prefixes. One cancellation probe per lifecycle stage. |
| 30–33 | One admitted 220K cold needle probe, with a small P0 coexistence probe only if memory allows. No second concurrent long-context request. |
| 33–45 | Mixed traffic block B; repeat matched cache/effort controls. Bounded loop probes, no forced live fault injection. |
| 45–48 | Verified Imprint revisit after at least 20 minutes; second bounded burst with mixed priorities. |
| 48–52 | Complete missing quotas and recovery probes. Stop admitting long requests. |
| 52–55 | Drain or explicitly cancel outstanding test requests; verify resource recovery. |
| 55–58 | Post-load decode gate and matched latency controls **inside the hour**. |
| 58–60 | Final health, both-node memory/swap, slot/KV recovery, socket reconciliation, and outstanding-request accounting. |

Move exhaustive parser tests, adapter conformance, deterministic fallback injection, timeout tests, and statistical quality comparisons to separate suites. The preflight may remain outside the hour, but distinguish total operational time from timed test duration.

## 4. Measurement validity and gates

### Confounders

**Imprint and RAM cache:** Counts and ages do not establish residency for a particular prompt. Twenty minutes does not prove RAM eviction. Require cache-source telemetry or a controlled fixture. Do not flush production caches. A nonce near the end of a prompt does not make its prefix cold.

**External traffic:** Ninety idle seconds and a historically quiet hour are not isolation. Pause the MacBook client for the full run or measure all competing requests, including direct engine traffic. Contention contaminates neighboring requests, not just the external requests themselves.

**Phase order:** Regression warms caches and hardware; long contexts pressure memory; thermal control changes clocks. Use matched controls before and after phases and repeat with different block order across runs.

**Closed-loop load:** Eight workers reduce offered load as latency rises and hide queue pressure. Keep closed-loop load for saturation efficiency, but use bounded open-loop arrivals for admission behavior. Record scheduled arrival, actual send, queue time, and completion.

**Retries:** Remove S6’s retry-until-answer policy. It hides rejection rates and can consume the rest of the hour. Count initial attempts and retries separately, with a fixed attempt and wall-time budget.

### Gates needing correction

| Gate | Problem and replacement |
|---|---|
| Burst of 16 must fast-fail | Eight running plus eight queued can accommodate 16 in an empty system, subject to reservation policy. Establish occupancy first; measure actual overflow separately. |
| All 429s under 10 ms | Queue timeouts are 4–25 s. Only immediate overflow rejections belong in this metric. Separate server admission latency from client network latency. |
| P0 never rejected | One reserved slot is not unlimited P0 capacity. Gate admission under a specifically constructed available-reservation case; characterize rejection when all capacity is exhausted. |
| P0 TTFE ≤1 s | Depends on queue, cache, load, and what counts as an event. A header, role delta, or heartbeat can pass while no useful answer arrives. Measure first SSE event, first generated token, first content/tool output, and complete delivery separately. |
| Effective delivery ≥98% | Define denominator. Exclude intentional cancellation and classify intentional overload separately; do not erase ordinary 429s through retry. Report conditional delivery among admitted requests and user-level success among offered normal requests. |
| S2 failure “observation only” | Contradicts S2’s tool-call requirement and possibly the global delivery gate. Either count those cases as failed task delivery or declare an explicit known-failure allowance. |
| No DSML for effort none | Thinking disabled does not disable tools. Structured tool calls can be valid. Gate raw protocol leakage into visible content, not legitimate tool output. |
| Tool schema legality 100% | Useful as an observed invariant, but validate types, constraints, call IDs and delta assembly, not merely JSON parsing and required fields. Separate malformed output from wrong tool selection. |
| `follow_refused=0` | The dossier does not define this event. Determine whether it can represent safe admission refusal before classifying every occurrence as corruption. |
| Clock ≥2350 MHz for 95% | Can fail healthy governor behavior. Report thermal/power state and workload-normalized performance; use a clock gate only if validated for this production recipe. |
| Node 1 memory ≥3 GiB | Ignores the other TP rank and is not a demonstrated safety margin. Monitor both nodes and use allocation-aware admission. |
| Cancellation recovery in 5 s | May be unsupported for an in-flight prefill kernel. Establish cancellation checkpoints and separately measure acknowledgement, request termination, slot release, and KV reclamation. |
| Final CLOSE_WAIT=0 | Confounded by unrelated clients and transient sockets. Gate persistent test-owned leaks after a grace interval. |
| Post-run decode ≥95%, one repetition | Weak against measurement noise and cache/thermal differences. Use repeated matched controls and report dispersion. |
| Fallback success 100% | Vacuously passes with zero triggers unless an exercised-count requirement exists. |
| HTTP 500=0 | Does not catch all 5xx, truncated 200 streams, or silent stalls. Gate unexpected server errors and invalid completion explicitly. |

## 5. Production safety

The two nodes provide 128 GB unified memory each, not one freely interchangeable 256 GB allocation pool. TP requires each rank to remain healthy. Memory also serves weights, KV, workspaces, caches, and the operating system.

“Two long contexts maximum” is not a sufficient guard:

- Two 220K contexts imply approximately **440K prompt tokens**, before output reservations.
- Other six slots still consume KV.
- Long outputs extend KV residency.
- Cold prefill can require transient workspace not represented by cached-context measurements.
- The external client can bypass the harness’s concurrency limiter.

Before admitting the 220K probe, obtain actual KV capacity, current occupancy, per-rank headroom, output reservation behavior, and prefill workspace requirements. Start with one long request and reduced background occupancy. If this cannot be bounded, move the cold 220K test to a maintenance window.

Use an allocation-aware safety controller, not just 1 Hz polling. On declining headroom, swap growth, KV exhaustion, or abnormal latency, stop new test admissions. On BadSlot, panic, rank failure, or OOM, terminate the experiment and preserve logs; do not keep stressing or automatically restart production without an approved procedure.

Cancellation/reuse tests should initially be staged at low concurrency because they are precisely where stale slot references and BadSlot failures may surface.

## 6. Comparability with p17

First resolve provenance: the dossier calls these p17 production results, but both column names say `p16_tokenmapfix`. Verify recipe, engine/proxy commits, model/template hashes, and harness version.

Potentially comparable **only with identical methodology**:

- The four quality questions and tool checks.
- Cold 8K prefill: **2,234.9–2,241.6 tok/s**.
- Cached 8K TTFT: **0.9082–0.9255 s**.
- Greedy decode: **89.49–90.53 tok/s**.
- Sampling decode: **71.5–72.61 tok/s**.
- MTP acceptance: **0.7401**, with the same workload and calculation.
- C1/C2/C4 and the 32K cut-in test.

The **0.7437–0.7803 s cut-in** result cannot be interpreted as total cold 32K request TTFT: cold prefill alone is approximately 14.5 seconds at the supplied throughput. Recover its exact timing definition.

Not directly comparable:

- New total completion count versus **893/925**.
- New delivery rate versus **98.77%/99.46% HTTP-200 rate**.
- New overall TTFT/wall distributions versus baseline p50 TTFT approximately 10.4 s and p95 22.5–24.4 s.
- New tool, long-context, fallback, cancellation, or reasoning-quality results.
- Memory regression: both baseline memory fields are null.

S4 is not automatically a valid baseline comparison. The historical generator included vision, different traffic proportions, budget/priority distributions, and only a thinking boolean. Competing S1/S6 requests change S4’s scheduling environment. Also, the historical vision worker returns the second-turn result on success, potentially hiding first-turn request accounting. Compare exact request-level strata or run the unchanged old marathon separately.

## Prioritized concrete changes

1. Rename the test as a bounded one-hour release/regression stress test; enumerate exclusions.
2. Verify baseline provenance and retain the exact standard release suite and metric definitions.
3. Replace the schedule with absolute timestamps, drain time, and an in-hour post-load decode check.
4. Inspect `effort_order`, extracted levels, renderer bridging, budget code, and history preprocessing before defining thinking expectations.
5. Remove integer-effort success, four-behavior, monotonic-length, and universal endpoint-equivalence gates.
6. Replace the thinking Cartesian product with deterministic parser tests plus 40–60 prioritized live interaction probes.
7. Add explicit short-rewrite boundary, alias-conflict, and fallback-suppression cases.
8. Treat reasoning-only exhaustion as failed task delivery; resolve the S2 known-failure policy.
9. Add request IDs linking logical jobs, turns, retries, fallback attempts, proxy rewrites, and engine execution.
10. Replace retry-until-answer with bounded attempts and preserve all initial rejection outcomes.
11. Separate overflow 429, queued timeout, reserved-slot admission, and normal-traffic delivery gates.
12. Add allocation-aware long-context admission on both ranks; isolate the 220K cold probe or defer it.
13. Isolate external traffic and verify cache source/residency rather than inferring it from age.
14. Add lifecycle cancellation, stream reassembly, tool-history, structured-output, and cache-correctness checks using mocked tools.
15. Report exercised counts and confidence bounds per cell; mark untriggered paths untested and move statistical quality, timeout, and fault-injection coverage outside the hour.