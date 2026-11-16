# Requirements under review (DGX Spark TP=2 DeepSeek-V4.1, 2026-11-16)

Context: a daily tracker reported upstream/downstream changes. The owner then asked "TensorFold 1.2.9 — this version is worth merging" and now asks for an external review of the requirement list below. The operator's (my) current position is written next to each item. Challenge each position with evidence from the dossier. Do not accept my position by default.

## R1. Merge ashhart/TensorFold v1.2.9 (tag 6b9de695) into the production engine
- Owner's view: worth merging (release says faster decode and long prompts, Ollama API, two fixes, replies unchanged).
- My position: do NOT merge wholesale. The speedups and fixes are for Nemotron/Metal, GLM-5.3/CUDA, Qwen3.8/HIP, Nemotron Omni, Living Weights; the four reviewed items touch 0 DeepSeek files; v1.2.9 README says DeepSeek is not served by any release binary; fork divergence is 7486 vs 157 commits, 11,099 files; upstream DeepSeek lives in a rewritten family (deepseek_v41, binary tensorfold-dsv41, different asset format), so p17 features (loop guard stop, DSML streaming 0048/0064/0065, TF_DS_WINDOW 2M pool, NVMe imprint, rank cache) would all need re-porting and a full re-qualification.
- Alternative I propose: cherry-pick individual upstream items only, each as its own stage.

## R2. Cherry-pick candidates from v1.2.9
- R2a #2814 kept_tool_calls counters (unoffered/malformed tool envelopes kept as text). My position: low priority; it is observability only; local proxy already flags dsml_in_content (36 rows, 0 external). Local parser differs (DSML, patches 0064/0065), so the diff will not apply as-is.
- R2b #3017 thinking-off named effort reaches the template. My position: not applicable — the local DSv4.1 template only writes "Reasoning Effort: N" in thinking mode (template line 133-139), so with thinking off the prompt bytes cannot change.
- R2c #2156 Linux PSI memory pressure governor. My position: not now — it sheds only lane-host optional states, is untested on any device ("Keep the Linux opt-in off until a GB10 run..."), does not coordinate TP hosts; the proxy already has a memory ladder.
- R2d Ollama API #3342, --config TOML #2885: not needed (clients use OpenAI API via OpenCodex).

## R3. bertholomus PR #51 TF_FILL_DRAIN
- My position: do not port. It only recovers a slowdown caused by TF_FILL_MANY, which the local fork does not have; local lane host admits all queued short prompts (`while (h.admitOne()) {}`) before the round, and a short prompt finishes inside its first piece (TF_FILL_FIRST=2). Its numbers were measured at round rows 32, prompt-cache 0, driver 595.

## R4. Structured output (response_format / json_schema / guided_choice)
- Evidence: 1 real 400 from the owner's MacBook on 11-16 00:19 (response_format refused). Forum user moved to jayleaton's build because structured output works there. Candidates: Mia PR #85 (patch 0060, 21k lines, 3,166 engine lines, applied on fbbc971, same as the engine base we forked from) or bertholomus #48/#49/#50 (open, stacked).
- My position: a real need, but not urgent; wait for #48-#50 to land upstream or port #85 into an isolated build prefix, then run the full gate. Unknowns: cost of sampled redraw on GB10, interaction with our patches 0048/0064/0065 and the loop guard (a forced `</think>` under a grammar ends the request with HTTP 500 per #85).

## R5. Kernel 7.0.0-1025 risk (forum #388215)
- Evidence: both nodes on 7.0.0-1019, driver 580.178.04, dgx-release 7.6.0, ota-meta 26.09.2; 1025 metapackages are upgradable on both, no apt holds, no unattended-upgrades config, apt-daily timers active. Forum: one user had memory-corruption Oopses on 1025 that stopped after reverting to 1019 and after adding `power_wrap_init` to initcall_blacklist via nvidia-spark-initcall-bl 1.0-2; another user (2x GX10, TP=2 vLLM) has node-2 freezes since the 7.6.0 OTA that persisted on the older 6.17 kernel and older driver; he lists iommu.passthrough=0, kho=off, pci=pcie_bus_safe as new since the stable period. Our nodes boot with iommu.passthrough=0 kho=off pci=pcie_bus_safe and initcall_blacklist=tegra234_cbb_init (no power_wrap_init), initcall-bl 1.0-2 upgradable.
- My position: apt-mark hold the kernel metapackages (linux-nvidia-hwe-24.04, linux-image-nvidia-hwe-24.04, linux-headers-nvidia-hwe-24.04, linux-modules-nvidia-580-open-nvidia-hwe-24.04) on both nodes. Open question: whether to also take nvidia-spark-initcall-bl 1.0-2 (power_wrap_init) on 1019 now.

## R6. jayleaton 2.8bpw pack / engine
- My position: do not switch. Head MemAvailable ~4.5 GiB vs ~7 GiB at four ~500K sessions; our Node1 already runs at ~3.4-4.0 GiB available. Only one run per side, different bpw.

## R7. Forum watermark PSA (vm.min_free_kbytes raised -> MemAvailable under-reads)
- Evidence: both nodes min_free_kbytes=45166 (kernel default ~44 MiB), so not affected.

## R8. Other open PRs: bertholomus #55 (ContextFull backoff per job), #52 (cache telemetry), Mia #139/#140/#141.
- My position: #55 may matter only if ContextFull happens; local rank0 log has 0 ContextFull lines. #52 telemetry could help the prompt-cache growth investigation (held vs budget) but is a draft. Mia #139-#141 not applicable (no spill-v2; build-only).


# Evidence dossier part 1
## E1. v1.2.9 release notes (verbatim)
# TensorFold 1.2.9

1.2.9 brings faster decode and long prompts, an Ollama-compatible API, and fixes for a wrong reply and a hang. Every
speedup below keeps replies unchanged.

## Speed

- **Nemotron on Metal** (without an MTP head): concurrent streams share one round. On an M5 Ultra, two streams decode
  about 20% faster, four about 75%, eight 2.3 to 2.5 times and 24 streams 3.2 to 3.5 times (#3005).
- **GLM-5.3-Flash on CUDA:**
  - Long prompts' first token comes 0.6% to 13.7% sooner at TP=3 from 131,072 to 2,000,000 tokens, and 6.7% sooner at
    TP=2 at 1,000,000; shorter prompts at TP=2 stay within about 2% either way (#3159).
  - After a 1,040,384-token prompt, decode rounds are 5.05%, 9.36% and 11.36% shorter at 1, 4 and 8 streams (#2722).
- **Qwen3.8-Flash-Next on HIP** (gfx1151): one stream decodes about 6% faster, four streams 2.8% to 4.6% (#2697).
- **Fewer CUDA launches** for Flash Next draws (#2927), Nemotron 3.5 draws (15 a level instead of about 112, #3124) and
  Qwen3.8-27B prompts (#2925).

## Models and features

- **An Ollama-compatible API:** `/api/chat`, `/api/generate`, `/api/embed`, `/api/tags`, `/api/show`, `/api/ps` and
  `/api/version` on the same engine paths as the OpenAI routes (#3342).
- **`tensorfold serve --config FILE.toml`** reads serve flags from a file, so a launch can be checked in (#2885).
- **Linux:** an opt-in memory-pressure governor driven by PSI, `TENSORFOLD_MEMORY_PRESSURE=1` (#2156).
- **Groundwork, not used by any served model yet:** a CUDA image path for the dense engine (#2768), dots.mocr's vision
  kernels (#2767), and HIP's TCP fabric for two hosts without RDMA (#2961).
- **An experimental Living Weights v2 controller** in `tools/living_weights_v2` (#3320).

## Server and API

- `/v1/models` lists each model's `input_types`. A video sent to a model without video is a 400, not a 500 (#3019).
- Logprobs work with tools, stop strings and reasoning, and on the Responses API (#3206).
- With thinking off, a request's reasoning effort reaches the template (#3017).
- Replies say when they kept a tool call as text, in `tensorfold.kept_tool_calls` and two `/metrics` counters (#2814).
- Streams can carry the committed token IDs, opt-in (#3285).

## Fixes

- **Nemotron Omni on CUDA:** a failed image request no longer leaks into the next reply (#2985).
- **GLM-5.3-Flash at TP=3:** `prompt_logprobs` over about 100 tokens no longer hangs (#1571).
- **Living Weights:** the drift gate no longer refuses a lesson over the writer's own wording (#2929).
- **CUDA:** the release server refuses a GPU it has no kernels for, by name, at startup (#2914).

## For developers

- `zig build test-host` gathers the Linux host checks (#2095); flaky tests fixed (#2963, #3015, #3310, #3347, #3349,
  #3355); docs for `TF_GLM_PROF` (#2990) and a Jammed XSFP4 NZ5 row (#2981).

## What changes by default

- **GLM on CUDA:** the `TF_GLM_INDEX_CUDA` kernels and `TF_GLM_DSEL` are on by default.
- **Flash Next on CUDA:** sampled draws are batched by default; `TF_FLASHNEXT_BATCH_DRAWS=0` restores per-stream draws.
- **Flash Next on HIP:** on one RDNA 3.5 GPU (gfx1150 to gfx1153) serving alone, MTP drafts stop under a 0.8
  confidence floor; other HIP GPUs and families keep 0.3, and `--mtp-confidence` still overrides it.
- **Server:** `--reasoning-effort` no longer changes a thinking-off prompt.
- **Server:** a `video_url` part sent to a model without video gets HTTP 400 (`invalid_request_error`), not a 500.
- **CUDA:** the release server refuses, by name at startup, a GPU it has no kernels for.

The first three keep replies unchanged. The fourth changes the prompt of a thinking-off request when the server sets
`--reasoning-effort`. The last two turn a failure into a named refusal.

## Thanks

@Bizuayeu, @Defilan, @garvrao80, @gilby, @jimthedj65, @jishnuvenugopal, @laudney, Mia's AI Lab (@MiaAI-Lab),
@Nipale-ai, @Shoestring-dev, @ss-cong, @tarsnake and @WebReflection.


## E2. Fork divergence vs v1.2.9 tag 6b9de695 (git, measured today)
merge-base f8fe17d24 (2026-10-07, TensorFold 1.0.2). local fork ahead 157 commits, v1.2.9 ahead 7486 commits. git diff --shortstat: 11099 files changed, 2580440 insertions(+), 54644 deletions(-).
Local DeepSeek family dir: zig/src/families/dsv41 (binary tensorfold-native + tf-dsv41-lanes). v1.2.9 has 0 files under families/dsv41; it has families/deepseek_v41 (binary tensorfold-dsv41, assets TF_DSV41_ASSETS/{rope.bin,engram-token-map.bin,aot/}).
v1.2.9 README line 221: "DeepSeek checkpoints are **not served yet** by any release binary: whole-model gate #827 is still open." (#827 is CLOSED unmerged). docs/recipes/deepseek-v41-cuda.md starts: "Experimental DeepSeek-V4.1 CUDA asset preparation. The native engine remains experimental."
Files touched under deepseek/dsv41 paths by the v1.2.9 items: #3017 0/15, #2156 0/10, #2814 0/10, #3206 0/14.

## E3. Local fork top commits (production engine branch dgx-spark-tp2-p17)
e772dec66 2026-11-15 loop guard: --loop-guard-stop and a per-request "loop_guard_stop" end the reply where the guard fires
a9873075d 2026-11-15 lanes: --loop-guard also closes a long passage repeated verbatim in the reasoning (PR #138 backport)
6e0a623dd 2026-11-10 dsv41 learned imprint: LRU order across restarts follows the files' last use
430be1274 2026-11-09 dsv41 learned imprint: cap counts bytes on disk, TF_LEARN_TTL_S expiry, startup reprobe
c976abd76 2026-11-09 feat(server): apply Patch 0064 (short dsml payload safety) and Patch 0065 (embedded dsml tag preservation and stream control)
19517007d 2026-11-09 feat(server): port Patch 0048 (DeepSeek-V4.1 DSML tool calls stream as they decode)
3d82b32c5 2026-11-09 feat(native): support TF_DS_WINDOW for multi-stream shared pool capacity decoupling
5f50e10b0 2026-11-09 feat(p8-cuda-graph): port PR #119 (Patch 0062 leaveCapture CUDA graph failure isolation)
262249bf3 2026-11-09 feat(p8-nvme): dual-plane NVMe cold KV spill & recall with host staging and multi-node sync
ca9478114 2026-11-09 fix(lanes): support TF_DS_STREAMS and auto-expand streams for --parallel on rank 1
b2c33a85d 2026-11-09 feat(p4d): port PR #112 (0056 picture prepare scratch arena, 0.71G -> 0.23G mem dip)
84fd8be60 2026-11-09 feat(p4c): apply 0029, 0030, 0031 (Anthropic frontend compatibility) and 0032 (stream keepalive ping)
4fd0a020d 2026-11-09 feat(p4b): add 0033 graph-cap LRU cache (cap 128) and 0023 keep-alive connection arena limit (1MB)
df14a3555 2026-11-09 feat(p4a): port 0045-cut-in-tail & 0034 (incremental tail cut-in for cached long & vision turns)
e73b096e8 2026-11-09 feat(p1-patches): apply patch 0027 (tool-call prose preserve & newline fix) and patch 0028 (plain request text control token masking)
490644d55 2026-11-09 feat(dsv41): add tf-dsv41-rank-cache CPU rank-cache generator (2591b860)

## E4. Production launch scripts
### rank0.sh
#!/bin/bash
set -euo pipefail
export TF_SEED_RANDOM=1
export TF_TOP_K_MAX=56
export TF_DS_PROMPT_ALIAS=1
export TF_FILL_CHUNKS=2
export TF_FILL_FIRST=2
export TF_FILL_CUT_IN=8192
export TF_DS_STREAMS=8
export TF_DS_WINDOW=2097152
export MALLOC_ARENA_MAX=4  # glibc kept 49 x 64 MiB per-thread arenas (1.6 GiB RSS) on rank0 after a day of requests; rank1 uses 75 MiB
export TF_LEARN_TTL_S=0  # no time expiry; the 200 GB (--learn-gib 186.26) LRU cap is the only eviction
DROP_REASONING_FLAG=""
if [ "${DROP_REASONING_HISTORY:-1}" = "1" ]; then
    DROP_REASONING_FLAG="--drop-reasoning-history --keep-last-n-reasoning 2"
fi
exec /home/joseyarashio/TensorFold-dsv41-zig/out/native/bin/tensorfold-native serve \
  /home/joseyarashio/models/DeepSeek-V4.1-Flash-1017-EXL3-2.9bpw \
  --host 0.0.0.0 --port 8888 --name DeepSeek-V4.1-Flash-1017-TF \
  --alias DeepSeek-V4.1-Flash-TF \
  --alias current \
  --context 1048576 --parallel 8 --thinking --max-tokens 32768 --loop-guard \
  $DROP_REASONING_FLAG \
  --prompt-cache-gib 2.0 \
  --learn --learn-dir /home/joseyarashio/.cache/dsv41-nvme-imprint --learn-gib 186.26 \
  --temperature 0.30 --top-p 0.95 --top-k 20 --backend cuda
### rank1.sh
#!/bin/bash
set -euo pipefail
export TF_DS_PROMPT_ALIAS=1
export TF_DS_STREAMS=8
exec /home/joseyarashio/TensorFold-dsv41-zig/out/bin/tf-dsv41-lanes \
  /home/joseyarashio/models/DeepSeek-V4.1-Flash-1017-EXL3-2.9bpw \
  /home/joseyarashio/.cache/dsv41-plusten-rank-cache/tf-ds-rank \
  1 2 10.100.184.2 29620 \
  /home/joseyarashio/dsv41-2m-kit \
  --engram /home/joseyarashio/dsv41-engram-1017 \
  --token-map /home/joseyarashio/.cache/dsv41-1017-rank-cache/dsv41_token_map.json \
  --vision-bias /home/joseyarashio/dsv41-2m-kit/vision/gate_bias_vl.safetensors \
  --pool 2097152 --rdma rocep1s0f1,roceP2p1s0f1 \
  --graphs 1 --side 1 --prefetch 1 --aio 1 \
  --streams 8

## E5. Local DSv4.1 chat template effort handling (model chat_template.jinja)
11:      reasoning_effort    "low"|"high"|"max" or int 1..100, default "high"
38:{#- Reasoning effort: "low"/"high"/"max" map to 50/75/100, ints pass through -#}
39:{%- set effort_in = reasoning_effort if reasoning_effort is defined and reasoning_effort is not none else "high" -%}
40:{%- if effort_in is string -%}
41:    {%- if effort_in == "low" -%}{%- set effort = 50 -%}
42:    {%- elif effort_in == "high" -%}{%- set effort = 75 -%}
43:    {%- elif effort_in == "max" -%}{%- set effort = 100 -%}
44:    {%- else -%}{{ raise_exception("Invalid reasoning effort: " ~ effort_in ~ ", expected int 1..100 or low/high/max") }}{%- endif -%}
46:    {%- set effort = effort_in -%}
133:    {#- Reasoning-effort prefix, first message only, thinking mode only. The System token
139:        {%- set ns.out = ns.out + "Reasoning Effort: " ~ effort ~ " (range 1-100, the higher the value, the more thorough the reasoning)\n\n" -%}
    {%- set idx = loop.index0 -%}
    {%- set role = m.role -%}

    {#- Reasoning-effort prefix, first message only, thinking mode only. The System token
        also leads when the conversation opens with a system message. -#}
    {%- if idx == 0 and (thinking or role == "system") -%}
        {%- set ns.out = ns.out + sys_tok -%}
    {%- endif -%}
    {%- if idx == 0 and thinking -%}
        {%- set ns.out = ns.out + "Reasoning Effort: " ~ effort ~ " (range 1-100, the higher the value, the more thorough the reasoning)\n\n" -%}
    {%- endif -%}

    {%- if role == "system" -%}

## E6. ashhart #3017 diff core (chat.zig/fields.zig)
diff --git a/zig/src/server/chat.zig b/zig/src/server/chat.zig
index 2b44473aea3..ff7b42ef37e 100644
--- a/zig/src/server/chat.zig
+++ b/zig/src/server/chat.zig
@@ -159,7 +159,9 @@ pub fn prepare(srv: *Server, cx: *Cx, input: Input, gone: anytype) Failure!Prepa
     const thinking = input.prompt == null and (flag(f, "enable_thinking") orelse srv.config.enable_thinking);
     const instruct = input.prompt == null and !thinking and !input.own; // a client's chat with thinking off may take --instruct-sampling's set
     const reasoning = thinking and srv.info.capability(.reasoning) and (srv.text.vtable.format != .kimi or input.prompt == null); // the prompt renders `thinking`; the reply reads `reasoning`
-    const effort = srv.effortFor(if (f.get("reasoning_effort")) |e| (if (e == .string) e.string else null) else null);
+    const asked = if (f.get("reasoning_effort")) |e| (if (e == .string) e.string else null) else null;
+    const effort = srv.effortFor(asked);
+    cx.named_effort = if (input.prompt == null) fields_mod.namedEffort(asked, srv.effort_levels) else null; // a raw prompt has no template
     cx.clear_thinking = flag(f, "clear_thinking");
     cx.template_fields = f;
     const rendered = try prompt_mod.prepare(srv, cx, input, thinking, effort);
diff --git a/zig/src/server/chat_generation.zig b/zig/src/server/chat_generation.zig
index bbce5e35334..fb3f011eb31 100644
--- a/zig/src/server/chat_generation.zig
+++ b/zig/src/server/chat_generation.zig
@@ -307,7 +307,8 @@ pub const Generation = struct {
         const decode_tokens = g.collected.items.len -| 1;
         const runtime = try json.newObject(a);
         try runtime.put(a, "enable_thinking", .{ .bool = thinking });
-        try runtime.put(a, "reasoning_effort", if (!thinking) .{ .string = "none" } else if (effort) |e| .{ .string = e } else .null);
+        // the effort the template heard: with thinking off, only one the request named
+        try runtime.put(a, "reasoning_effort", if (!thinking) .{ .string = cx.named_effort orelse "none" } else if (effort) |e| .{ .string = e } else .null);
         try runtime.put(a, "engine", .{ .string = g.srv.info.name });
         try runtime.put(a, "tokens_per_second", .{ .float = if (decode_s > 0) @as(f64, @floatFromInt(decode_tokens)) / decode_s else 0 });
         try runtime.put(a, "seconds", .{ .float = @max(0, decode_s) }); // the reply's decode seconds, as tokens_per_second divides them
diff --git a/zig/src/server/errors.zig b/zig/src/server/errors.zig
index 2622f5d6586..01ba7e783c0 100644
--- a/zig/src/server/errors.zig
+++ b/zig/src/server/errors.zig
@@ -32,6 +32,8 @@ pub const Cx = struct {
     param: ?[]const u8 = null,
     /// The request's ``chat_template_kwargs.clear_thinking``, over the server's (GLM-5.3 templates only).
     clear_thinking: ?bool = null,
+    /// The effort the request itself named (no server default): a thinking-off prompt renders only this one.
+    named_effort: ?[]const u8 = null,
     /// The request controls a native prompt renderer must retain in every prefix probe.
     template_fields: @import("json").Value = .null,
 
diff --git a/zig/src/server/fields.zig b/zig/src/server/fields.zig
index df765944fe6..aad8720a231 100644
--- a/zig/src/server/fields.zig
+++ b/zig/src/server/fields.zig
@@ -243,6 +243,12 @@ fn order(name: []const u8) ?usize {
     return null;
 }
 
+/// The effort a request itself names, on the template's levels; null for none or `none` (never --reasoning-effort).
+pub fn namedEffort(request: ?[]const u8, levels: []const []const u8) ?[]const u8 {
+    const e = request orelse return null;
+    return if (std.mem.eql(u8, e, "none")) null else coerceEffort(e, levels);
+}
+
 /// The nearest level the template names, ties going higher; xhigh and none stay.
 pub fn coerceEffort(effort: []const u8, levels: []const []const u8) []const u8 {
     if (levels.len == 0) {
diff --git a/zig/src/server/fixtures/thinking/README.md b/zig/src/server/fixtures/thinking/README.md

## E7. ashhart #2814 body
When a model writes a tool-call envelope the server can't accept (it names a tool the request didn't offer, or its markup is malformed), the server keeps it as text in `content`. Until now it only logged a count, so clients couldn't tell (#2800).

- A reply that kept an envelope now carries `tensorfold.kept_tool_calls`: `unoffered` and `malformed` counts, plus `unoffered_names` as the model wrote them, capped at 8 names of 64 bytes each. It appears on the whole reply and on a stream's final chunk. A reply that kept nothing adds no fields.
- `/metrics` adds `kept_tool_calls_unoffered_total` and `kept_tool_calls_malformed_total`.
- `docs/api.md` no longer says calls to tools that weren't offered come back as tool calls: they're kept as text, and the new fields say so.
- No new flag or setting. The parse's decisions are unchanged; it only records why it kept an envelope.

Checks: `zig build test-tool-parse-host test-tool-visibility-http-host test-admission-host` pass, 124/124. New tests cover an unoffered call and a malformed one, on the whole reply and on a stream, and check that a clean reply has no new fields and that the metrics counters move. `zig fmt --check` is clean, and the lean count is unchanged.

Fixes #2800.

- Synthena (Ash's Agent)


## E8. ashhart #2156 RUNBOOK excerpt
+### Experimental Linux memory pressure
+
+On Linux, `TENSORFOLD_MEMORY_PRESSURE=1` (or `on`) opts the shared lane host into the same governor and cache
+watermark. Unset keeps it off until device qualification. The reader samples `/proc/pressure/memory` and
+`/proc/meminfo` without allocating; both must be available and valid at startup. It reads at most four times a
+second, raises the level immediately and waits five seconds of lower readings before easing it.
+Inside a container or cgroup, these proc files describe the whole host, not the container's memory limit.
+The opt-in therefore follows host pressure and does not provide container-local pressure or admission limits.
+
+The proposed thresholds use PSI's `avg10` stall percentages:
+
+| Level | Any of these readings |
+| --- | --- |
+| Warning | PSI some at least 10%; PSI full at least 1% |
+| Critical | PSI full at least 10% |
+
+Critical takes precedence. MemAvailable is diagnostic and does not set the level. A normally budgeted unified-memory
+server can have a small available margin without reclaim stalls. The OS reader has no engine-specific planned margin,
+so it uses PSI rather than guessing a floor from total RAM. MemFree and file-cache size do not set the level either. Unknown or malformed data follows the existing source contract: no reading,
+counted as normal by the governor. Windows is unchanged. The 503 message refers to the system on every platform.
+
+Only optional states managed by the shared lane host are shed. Borrowed states remain protected. Family-owned
+caches and a backend's independent driver need their own qualification; this does not coordinate pressure across
+TP hosts or replace the pre-load page-cache release/admission checks used on GB10 (#1857, #1868).
+
+`zig build test-memory-pressure-host` checks planted proc files, thresholds, invalid/oversized input, the existing
+hysteresis, protected state, cache shedding, admission and resumed/fresh equality on an instrumented target.
+No Linux device, memory-hog or whole-checkpoint receipt is claimed. Keep the Linux opt-in off until a GB10 run
+shows shedding, recovery without oscillation and exact drafted/plain, resumed/fresh and concurrent/solo replies
+at unchanged checkpoint precision (#2129).
 

## E9. bertholomus PR #51 (merged 11-15 into deepseek-v41-zig-tp2) body
## What this changes

With `TF_FILL_CHUNKS` and `TF_FILL_MANY`, the lane host starts one prompt pass a turn and a decode round follows each,
so short prompts that arrive together start a round apart: P1 R P2 R P3 R P4 instead of P1 P2 P3 P4 R. On two GB10s
with 8 lanes, that costs a burst of 8 short requests 36-38% of its aggregate decode rate against the same build with
the fill switches unset.

`TF_FILL_DRAIN=ROWS` lets the host start passes that go in whole back to back in the same turn, up to ROWS rows. Under
`TF_FILL_MANY` it lifts that burst's aggregate rate by 56-60% (code: 198 to 318 tok/s; chat: 185 to 288) and brings
its slowest first token from 1.01 s to 0.60 s. That is the unset numbers again, not past them. Passes in pieces keep
`TF_FILL_ROUNDS`. Unset or 0, nothing changes.

In detail, with `TF_FILL_DRAIN=ROWS` (and `TF_FILL_CHUNKS` + `TF_FILL_MANY`):
- `run()` keeps calling `fillOne()` in the same turn, re-admitting between calls, while the next pass goes in whole
  at its first step.
- It stops at the first pass that needs pieces, when the lanes are full, or when the next pass would take the turn's
  rows past ROWS. The first pass always runs.
- A backend that holds one pass at a time admits the next once the last went in, so it drains too.
- Unset, `Info.fill_drain` is 0 and `run()` takes its current path.

Files: `core/engine_api.zig` (`Info.fill_drain`), `families/dsv41/native.zig` (reads `TF_FILL_DRAIN`),
`native/cuda.zig` (passes it through), `core/lane_host.zig` (`fillOne()` / `run()`), and
`core/lane_host_fill_test.zig` (two tests). I left `TF_FILL_DRAIN` out of the `native.zig` header table, because a
three-line entry there adds lean findings. It is documented on one line where it is read.

## Receipt

- **Environment:** two GB10 nodes, TP2, the RDMA ring. Ubuntu 24.04.5, kernel 7.0.0-1019-nvidia, driver 595.99.02,
  `nvcr.io/nvidia/pytorch@sha256:2140e699b3beaf7f96a0081fd9c9406bc3832b435cdb60dfa2d261f7d2f34a1c`.
  - Checkpoint: DeepSeek-V4.1-Flash-1017 EXL3 2.9 bpw (LibertAI's pack at `afc7aa0a`, with a `wo_b` weight patch in
    blocks 2-39, the same base as #43); engram from `deepseek-ai/DeepSeek-V4.1-Flash-1017` at `1bae0e10`.
  - Engine: `deepseek-v41-zig-tp2` at `a57deb9d` plus this change, plus an env switch for the RDMA GID index (our
    RoCE v2 GID is 3). Its code lines are identical to this PR's; only comment wording differs.
  - Serve: 8 streams, round rows 32, window 1,048,576, `--parallel 8`, `--prompt-cache-gib 0`. Engine env in every
    arm: `TF_DS_GRAPHS=1 TF_DS_HC_SIDE=1 TF_DS_L2_PREFETCH=1 TF_DS_ENGRAM_AIO=1 TF_DS_REPLAY_FLOOR=1 TF_DS_IDX_SPLIT=1
    TENSORFOLD_PLAIN_SPECIALS=1 TF_DS_PROMPT_ALIAS=1 TF_DS_SOLO_OVERHEAD=1 TF_DS_NO_COPIES=1`, plus the grammar
    library, SSE keepalive and stats settings.
  - Only the `TF_FILL_*` switches differed between arms; each start's container env was read back and checked.
- **Concurrency:** `tools/bench_concurrent.py --tokens 256 --reps 3 --temperatures 0 --levels 1,4,8 --alone --serial`,
  run in the order DRAIN, MANY, unset, DRAIN, MANY (two passes of each switch, alternated). Medians, tok/s:

  | prompt | streams | unset | `CHUNKS=1 MANY=1` | `CHUNKS=1 MANY=1 DRAIN=4096` |
  |---|---|---|---|---|
  | code | 1 | 79.4 | 79.4 / 79.4 | 79.6 / 79.5 |
  | code | 4, aggregate | 212.9 | 168.8 / 168.5 | **212.8 / 213.0** |
  | code | 8, aggregate | 318.4 | 198.9 / 198.1 | **318.4 / 317.5** |
  | code | 8, steady | 342.6 | 214.8 / 212.1 | **342.5 / 341.7** |
  | code | 8, slowest first token (s) | 0.60 | 1.01 / 1.01 | **0.60 / 0.60** |
  | chat | 1 | 69.5 | 69.5 / 69.5 | 69.6 / 69.6 |
  | chat | 4, aggregate | 191.8 | 145.7 / 145.5 | **191.9 / 192.1** |
  | chat | 8, aggregate | 288.3 | 185.0 / 184.8 | **287.9 / 287.6** |
  | chat | 8, slowest first token (s) | 0.91 | 1.33 / 1.33 | **0.91 / 0.92** |

- **Exactness:** in all five passes, every concurrent reply's `token_sha256` equals its alone run's (78/78 per pass),
  and the alone runs equal `"draft": false` (2/2 per pass).
- **Decode speed** (`tools/bench_openai.py --tokens 256 --reps 3 --temperatures 0`, fibonacci-raw / gpu-chat-no-think):
  unset 79.44 / 69.50, MANY 79.42 / 69.53 and 79.43 / 69.51, DRAIN 79.83 / 69.68 and 79.54 / 69.61.
- **What it does not do:** with the fill switches unset, short prompts in a burst already start together. DRAIN brings
  `TF_FILL_MANY` back to that level, not past it. Its use is to run `TF_FILL_MANY` (for long prompts beside live
  streams) without paying for it on bursts of short ones. If you'd rather not have another switch, it could become
  `TF_FILL_MANY`'s behaviour with a fixed budget; happy to change it.
- **New tests** (`core/lane_host_fill_test.zig`, over the fake backend): three 4-token prompts all wait before the host
  starts, and a hook records the core's round count at each one-step pass.
  - Without `fill_drain`, the three passes start at increasing round counts (a round apart).
  - With `fill_drain = 64`, all three start before
## E10. Local lane host (zig/src/core/lane_host.zig run loop) and engine addStream: local fork has TF_FILL_CHUNKS/FIRST/ROUNDS/CUT_IN, no TF_FILL_MANY

    /// The filling job's next piece, when its turn has come; its first tokens once its prompt pass ends.
    fn fillOne(h: *LaneHost) void {
        const job = h.filling orelse return;
        const done = h.core.fillStep() catch |e| {
            h.filling = null;
            _ = if (e == error.Cancelled) h.cancel(job) else h.drop(job, h.words(e));
            return;
        };
        if (!done) return;
        h.filling = null;
        h.prefilled(job, job.began);
        if (h.deliver(job)) h.remove(job);
    }

    fn run(h: *LaneHost) void {
        while (true) {
            h.takeCancels();
            while (h.admitOne()) {}
            h.fillOne();
            h.noteLive();
            h.lock();
            if (h.closing) {
                const left = h.queued.items.len + h.admitted.items.len;
                h.unlock();
                if (left == 0) return;
                h.closeAll();
                continue;
            }
            if (h.core.activeCount() == 0) {
                if (h.filling != null) {
                    h.unlock();
                    continue;
                }
                if (h.cancels.items.len == 0 and (h.queued.items.len == 0 or h.admitted.items.len >= h.info_.lanes))
                    h.wake.waitTimeout(h.io, &h.mutex, .{ .duration = .{ .raw = .fromMilliseconds(100), .clock = .awake } }) catch {};
                h.unlock();
                continue;
            }
            h.unlock();
            h.core.step() catch |e| {
    pub fn addStream(e: *Engine, s: *Stream) !void {
        _ = e.arena.reset(.retain_capacity);
        try trail.event(e, &.{ f("ev", str("add")), f("stream", str(s.id)) });
        if (e.filling != null) {
            const at = @min(@as(usize, s.reuse.at), s.prompt_len);
            if (!e.cutsIn(s.prompt_len - at, picturesPast(s.images, at))) return error.FillBusy;
            s.cut_in = e.cut_in; // the backend holds it to the bound once it knows where the pass really resumes
            e.backend.prefill(s) catch |err| {
                if (err == error.Cancelled) e.backend.release(s);
                return err;
            };
            return e.started(s);
        }
        if (e.fill_chunks > 0 and e.backend.vtable.prefill_part != null and (e.activeCount() > 0 or e.cut_in > 0)) {
            if (!try e.piece(s, if (e.fill_first > 0) e.fill_first else e.fill_chunks)) {
                e.filling = s;
                e.rounds_since = 0;
                return;
            }
        } else e.backend.prefill(s) catch |err| {
            if (err == error.Cancelled) e.backend.release(s); // the host finishes a cancelled stream without the core
            return err;
        };
        try e.started(s);
    }

    /// Whether a prompt that computes `tokens` tokens (past the kept state it resumes, all of it without one) runs whole
    /// between the filling stream's pieces. `rows`: it needs picture rows (a picture past that state); such a prompt,
    /// like any while the filling pass has pictures of its own, does not cut in (one at a time).
    pub fn cutsIn(e: *const Engine, tokens: usize, rows: bool) bool {
        const filling = e.filling orelse return false;
        return e.cut_in > 0 and tokens <= e.cut_in and !rows and filling.images.len == 0;
    }

## E11. bertholomus open PRs #55 #52 #50 #48 #49 (bodies trimmed)
### #55 OPEN Scope ContextFull admission backoff to the refused request
Root cause: a host-wide `ContextFull` retry hold prevents later queued work from reaching admission even when it can fit. Evidence: the CPU regression on `e100ee8` leaves a fitting warm request unadmitted (`expected 4, found null` cached tokens).

Move the occupancy threshold and retry deadline onto the refused job. The existing admission picker skips jobs whose backoff is still active, preserving their queue position so an eligible head regains priority when its deadline arrives or occupancy falls. Existing pool-fit fairness, single-fill, cache ownership, and near-completion gates remain in place.

The new synchronous CPU fixtures cover fitting warm admission, retention and eventual admission of the refused job, bounded retries, deadline priority, retry after a partial occupancy decrease, and cancellation of only the waiting job. All 61 lane-host tests pass with Zig 0.17.0 in ReleaseSafe; the engine API semantic compile-only check, formatting, and diff checks also pass.

Validation limits: the broad engine API suite panics in the Imprint allocation-failure test; the same focused test also panics on the unmodified pinned base. The native build is blocked in this WSL environment by `checking cache failed: manifest_stat Unexpected`, before a successful server build. GPU and end-to-end inference validation are pending. Please treat this as a draft until those platform checks are available.

Related: [#51](https://github.com/bertholomus/TensorFold/pull/51) addresses fill/drain sc
### #52 OPEN cache: additive shared-pool and prompt-state telemetry
Draft: additive cache telemetry for the shared pool and the prompt-state store.

## What it adds

`GET /health` gains an optional `live.cache` group, and `/metrics` gains matching `kv_pool_*` and
`prompt_state_cache_*` families. Both are observation only: nothing here changes admission, eviction,
placement or any inference decision, and no GPU sync is added.

- **`core/lanes/cache.zig`** — the contract for a backend to describe itself:
  - the shared pool as four disjoint allocator spans (`active_reserved`, `retained_prefix`,
    `retained_growth`, `unclaimed`) that sum to `capacity_positions`, plus `valid_states`,
    `invalidations_total` (valid→stale, counted once) and `placement_blocks_total`;
  - the prompt-state store as a byte budget (`budget/held/spare_bytes`, `entries`) with lookups,
    replacements (`evictions`), `refusals`, and failures split into keep / restore / peer-forget
    stages next to the existing `failed` aggregate;
  - the status envelope: `schema_version`, `engine_epoch`, `observed_unix_ns`, `consistent`,
    `context_limit_positions`, `stream_capacity`, and the two optional groups;
  - the interval math (`accountIvs`) as pure functions, so a backend passes its own spans and does
    not reinvent the partition.
- **`prompt_cache.zig`** — increments the three stage counters where each failure already happens;
  `failed` keeps its exact previous meaning, and the stages sum to it going forward.
- **`families/dsv41/lanes.zig`** — counts a valid→stale tran
### #50 OPEN feat(grammar): compile json_schema and guided_choice in Zig (xgrammar 0.2.8 strict)
## What this changes

After the last PR, DeepSeek-V4.1 takes `json_object`, but `json_schema` and `guided_choice` still get HTTP 400. Anthropic `output_config.format` requests are schemas too, so they get no structured output either.

With this PR, the server compiles a `json_schema` or a `guided_choice` list into a small program, and the stream keeps its reply inside it. `guided_json`, `structured_outputs` (`json` and `choice`) and Anthropic `output_config.format` take the same path. `regex` and `grammar` stay HTTP 400. It stacks on #49 and has three commits: the compiler, a fix to its key lookup, then numeric bounds.

The rules follow xgrammar 0.2.8 strict mode. If a schema uses something the engine can't enforce, the request gets HTTP 400 before any token, and the message names the keyword and where it is.

What's in it:

- `schema.zig`: compiles a schema in xgrammar's keyword order. `schema_keys.zig` holds the keyword rules.
- `formats.zig`: the `date-time`, `date`, `time`, `uuid`, `ipv4` and `email` automata, built from xgrammar's patterns.
- `schema_match.zig`: matches reply bytes against a program. Each object keeps a trie of its keys, so a key byte is one trie edge and one binary search.
- `bounds.zig`: `minimum`, `maximum`, `exclusiveMinimum` and `exclusiveMaximum` on `integer` and `number`, matching xgrammar 0.2.8. The trie builder moved to `bytetrie.zig`.
- `docs/api.md`: lists the keywords the engine takes.

## Why

No merged TensorFold engine enforces a grammar f
### #48 OPEN feat(grammar): add a json_object byte matcher and token byte table (no callers yet)
## What this changes

Right now the Zig server answers every structured request (`response_format` and friends) with HTTP 400, because no family sets `Info.structures` (`server.zig:177`). This is the first of three PRs that add structured output for DeepSeek-V4.1. The plan and my open questions are in MiaAI-Lab/DeepSeek-v4.1-Flash-1017-2x-DGX-Sparks#22.

This one only adds a library in `core/grammar`. Nothing calls it yet, so no served token changes. It checks a reply byte by byte against xgrammar's `json_object` grammar, and it knows which bytes each token would add to a reply.

What's in it:

- `core/grammar/json.zig`: the byte matcher. Its whole state is a 32-byte value.
- `core/grammar/vocab.zig`: a table from each logits column to the bytes its token adds. For DeepSeek-V4.1 it builds in 5 ms and takes 1.48 MB.
- `tokenizer.tokenBytes(id)`: one token's raw bytes. It shares `steps.appendByteLevel` with the decoder.
- `tools/zig/xgrammar_json_corpus.py`: writes and rechecks a frozen test corpus labelled by xgrammar 0.2.8.

The matcher differs from xgrammar 0.2.8 in three places on purpose: it refuses an encoded surrogate in a string, nesting past 128 levels, and every added token like `</think>`. The reasons are in the details.

## Receipt

`zig build test` goes from 236/236 to 254/254. On a frozen corpus of 3,000 byte strings, the matcher gives xgrammar 0.2.8's verdict every time. `tokenBytes` matches xgrammar's `decoded_vocab` on every token of DeepSeek-V4.1 and Qwen3.6-3
### #49 OPEN feat(dsv41): support response_format json_object by redrawing masked rows on rank 0
## What this changes

Right now DeepSeek-V4.1 on the Zig engine refuses `response_format` `{"type": "json_object"}` with HTTP 400. With this PR, DeepSeek-V4.1 takes `json_object` with drafts on and keeps the reply inside xgrammar's root object.

It stacks on #48 and has two commits: the lane core, then DeepSeek-V4.1.

Quick background: a verify is the pass where the full model checks the drafted tokens. A greedy row is drawn at temperature 0, so it takes the top token. Rank 0 and rank 1 are the two engine processes, one per Spark.

What's in it:

- Lane core: after each verify, the engine walks the accepted tokens under the stream's grammar. A greedy row keeps its pick if the grammar allows it. Any other row goes to a new optional `Backend.VTable.redraw`, which draws again with the refused tokens at -inf.
- The first token is masked too. A token the grammar refuses ends only its own stream.
- A backend without `redraw` keeps `Info.structures` false, so other families don't change.
- DeepSeek-V4.1: rank 0 already holds every verify row's logits, so `redraw` needs no kernel, frame or memory-plan change. Rank 1 never sees the grammar.
- `sampling.zig`: masked versions of argmax, top candidates and the keyed draw.

## Why

MiaAI-Lab/DeepSeek-v4.1-Flash-1017-2x-DGX-Sparks#22 reports 2 of 120 extraction replies with JSON that didn't parse.

On the design: #39 (the Python line) cuts the window at the first refused draft, before the verify. This PR walks after the verify instead, so 

## E12. MiaAI-Lab PR #85 structured output body
## Description and Motivation

On main, the Zig engine refuses every structured-output request with HTTP 400. That's `response_format` `json_object` and `json_schema`, `guided_json`, `guided_choice`, `structured_outputs` and Anthropic `output_config.format`. So a client has to put the schema in the prompt and check every reply itself. #22 runs into this for document extraction. I ran into it with a pydantic schema that has a `confidence` field between 0 and 1.

`zig/patches/0060-structured-output.patch` makes all of them work, with DSpark drafts on.

Terms I use below. The engine turns the schema into a grammar, the rules for which bytes can come next. DSpark drafts are guesses from a small draft model, and a verify is the full model checking them in one pass. Rank 0 is the process that serves HTTP.

What's in it:

- Rank 0 keeps each reply inside its request's grammar. Rank 1 never sees the grammar.
- Schemas follow xgrammar 0.2.8 (the grammar library vLLM uses) and get the usual structure keywords, six `format`s, and numeric bounds (`minimum`, `maximum` and the exclusive ones).
- After each verify, rank 0 runs the accepted tokens through the matcher, the new code that checks them byte by byte against the grammar. If the grammar refuses a token, rank 0 picks a new one at that position with the refused tokens masked out. So a reply comes out the same whether it's drafted, run with `"draft": false`, or sitting next to other requests.
- Anything it can't enforce gets a 400 before the first token, and the error names the keyword (`regex`, EBNF `grammar`, `pattern`, `multipleOf` and more, full list in `docs/api.md`).
- There's no switch. A request without a grammar runs the same code as before.

The patch is 21,222 lines, but only 3,166 of them are engine code. Two saved corpora (test strings with xgrammar's verdict on each) take 13,447, and tests and fixtures take 2,833.

## Related Issues

- #22. This covers everything there except regex and EBNF, so I left off a closing keyword.
- Renumbered from 0039 to 0060 on 2026-11-06, regenerated on main's whole series so it sorts after 0059. The results table below was measured on the 0039 build.
- The same change is open on the engine side as bertholomus/TensorFold#48, #49 and #50. Once `TF_REF` includes them, this patch can go.

---

## Testing

- It applies with the Dockerfile's loop on a clean `fbbc971` checkout.
- Host tests (main `0e7d421` + this patch, x86_64, Zig 0.17.0): `zig build test` 589/591 (main is 527/529 with the same two spill failures), `zig_test.sh` 97/97 and 98/98, `test_lanes.sh` 50/50, grammar module 46/46, `port_test.sh` 148/148.
- The matcher agrees with xgrammar 0.2.8 on every string in the corpora: 3,000 `json_object`, 5,400 schema and choice, 4,950 with bounds.
- On my two DGX Sparks at temperature 0, `tools/exact.py` (31 cases, no grammar) gives `IDENTICAL` against my image without this patch (setup below). For `json_object` and `json_schema`, the drafted, `"draft": false` and 4 concurrent replies all have the same `token_sha` (a sha256 of the reply's token ids).
- Speed without a grammar, one run each: 32K prefill 2,151.4 tok/s with the patch vs 2,162.1 without, and one-stream decode 82.1 vs 82.2 tok/s.

Not tested on the Sparks: drafted vs `"draft": false` for sampled replies and for `guided_choice`, and #22's long extraction replies and pictures (the reporter offered to test a branch).

<details>
<summary>Test details and edge cases</summary>

Host tests:

| | main | main + 0039 |
| --- | --- | --- |
| `zig build test` | 527/529 | 589/591 |
| `zig/tests/server/zig_test.sh` | 91/91 and 95/95 | 97/97 and 98/98 |
| `tools/zig/test_lanes.sh` | 44/44 | 50/50 |
| `zig test zig/src/core/grammar/grammar.zig` | (no module) | 46/46 |

The two `zig build test` failures are the spill store's "write faults" check and fsio's `a partial direct write off the 4 KiB grid finishes buffered`. Both do short `O_DIRECT` writes in a test folder on XFS, and this patch doesn't touch spill code. `test_lanes.sh` skips its recorded fixtures (4 and 5 tests) on both sides because `TF_LANES_FIXTURES` isn't set.

With xgrammar 0.2.8 installed, `tools/zig/xgrammar_json_corpus.py --check` and `xgrammar_schema_corpus.py --check` label the corpora again and find 0 differences. The Zig tests check the matcher's verdict on each string, down to the index of the byte it refuses. On the fake target (the lane core's test backend), new tests check that `json_object`, `json_schema` and choice replies come out the same drafted, with `"draft": false` and sharing a round with other requests, both greedy and sampled. A schema reply that decodes while the engine reads another prompt in pieces equals the same reply run alone.

Why drafted replies stay exact: in the verify pass each position has a row of logits. At temperature 0, a row keeps its token if the grammar allows it. Every other row gets drawn again from the logits rank 0 already holds, with the refused tokens set to -inf (a new optional `Backend.VTable.redraw`). That masked draw is bit for bit the plain draw on a copy of the row with the refused tokens at -inf, and a refused draft can never equal the masked pick.

Setup on the Sparks: kernel 7.0.0-1019-nvidia, driver 580.178.04, the EAQ v1 pack @45ee5d0f, `CONTEXT=1048576`, `PARALLEL=6`, `POOL=2101248`, drafts on, `GRAPH_CAP=128`, `SPILL_GIB=256`, `KV_SHARD=0`, `TF_DS_ENGRAM_LEAD=1`, `TF_FILL_CHUNKS=1`, `TF_FILL_CUT_IN=8192`. The image also has other patches and script changes of mine that I'm still testing. The image I compared against had the same ones, minus this patch and two more of mine (the restore-room patch, which is my next PR, and one that only changes tests).

Results there:

- My structured-output check script passes 15 of 15. The shared `token_sha` is `b85c5effc473` for `json_object` and `9e3c566430ac` for `json_schema`. A plain reply next to 3 structured ones equals its solo reply. The other checks look for valid JSON (thinking off and on, a nested schema, both `guided_choice` spellings, streaming, Anthropic `output_config.format`) and for the 400s on `pattern`, `guided_regex` and `ignore_eos`.
- The pydantic schema I mentioned at the top is 170 lines with `$defs`. The `triage_report.json` fixture in this patch is that schema with shorter descriptions. I sent it 3 s into a 43,707-token prompt that the engine was reading in pieces. It came back HTTP 200 with every required key and `finish_reason` `stop`.
- One-stream decode used two 512-token prompts, twice each, 256 tokens out. The 32K prefill reply has `token_sha` `2222e35c1fbc` on both images.
- With a grammar, a 40-item JSON list decoded at 122.4 tok/s under `json_schema` and 122.3 under `json_object` (streamed, thinking off, best of two).
- Sampled replies: only the Anthropic request ran sampled on the Sparks (server default temperature), and its JSON was valid. A sampled stream draws every accepted row again, and I haven't measured that cost on GB10.

Edge cases:

- N
## E13. Mia PR #139 #140 #141 titles
#139 OPEN Add optional spill-v2 expiry and host-memory admission floor
#140 OPEN Maintenance: pin NVIDIA 26.10, Pillow 13 and Zig 0.17.1
#141 OPEN Build: separate native stages and retain Zig caches (stacked on #140)

## E14. NVIDIA forum #388215 (kernel 1025 freezes) — posts
=== #388215 DGX Spark: kernel 7.0.0-1025-nvidia memory corruption and system freezes posts=8
  #1 2026-11-06T17:53 alex.zare99: My NVIDIA DGX Spark experienced repeated kernel-memory corruption and system freezes after updating to kernel 7.0.0-1025-nvidia. System configuration: • Hardware: NVIDIA DGX Spark / GB10, ARM64, 128 GB shared memory • OS: Ubuntu 26.04.1 LTS; retained DGX release marker reports 7.6.0 • Failing kernel: 7.0.0-1025-nvidia • Package/build: 7.0.0-1025.26, #26-Ubuntu • Previous kernel: 7.0.0-1019-nvidia • Previous package: 7.0.0-1019.19~24.04.2 • NVIDIA open driver: 580.178.04 on both kernels Failures on November 6, 2026 — times are PST (UTC−08:00): 08:11:35–36: kernel linked-list corruption followed by a NULL-pointer Oops in remove_wait_queue while handling a Python process. 08:31:17: linked-list 
  #2 2026-11-06T21:06 aniculescu: Do the kernel failures you are seeing appear when running a workload or while the unit is idle? If idle, how long after boot?
  #3 2026-11-06T21:11 alex.zare99: The failures occurred during normal desktop use, including VS Code, with background services running. I haven’t confirmed a failure while the unit was completely idle. The three recorded kernel-corruption episodes began approximately 3 minutes 28 seconds, 11 minutes 7 seconds, and 7 minutes 44 seconds after their respective boots. All three used 7.0.0-1025-nvidia. I don’t yet have a reliable workload trigger or controlled idle-versus-load comparison. After reverting to 7.0.0-1019-nvidia, no further kernel-corruption events appeared during the initial observation period.
  #4 2026-11-07T02:00 user158576: Can you check “ cat /proc/cmdline" and "apt-cache policy nvidia-spark-initcall-bl ” Without the nvidia-spark-initcall-bl 1.0-2 fix, your system will become unstable with certain display. Since you are on Ubuntu 26.04, you won’t automatically get the nvidia-spark-initcall-bl 1.0-2 fix. You will need to manually add the blacklist in the kernel boot arg, initcall_blacklist=tegra234_cbb_init,power_wrap_init tegra234_cbb_init should be already there. Just need to add power_wrap_init
  #5 2026-11-07T21:22 alex.zare99: I checked the system. It currently has nvidia-spark-initcall-bl 1.0-1; version 1.0-2 is not available. The kernel already has initcall_blacklist=tegra234_cbb_init, but power_wrap_init is missing. Please confirm the recommended persistent GRUB change to add power_wrap_init.
  #6 2026-11-08T02:12 user158576: Yes, you need to persistently have the power_wrap_init workaround in your grub. Let me know if you need step by step instruction for modifying the GRUB config.
  #7 2026-11-09T15:41 alex.zare99: Thanks. I’ve already added power_wrap_init persistently to my GRUB configuration alongside tegra234_cbb_init, and confirmed it is active in /proc/cmdline. I’ve also installed nvidia-spark-initcall-bl version 1.0-2. I’m monitoring the system now for further freezes or kernel errors.
  #10 2026-11-15T09:27 dgk960: DGX Spark (GB10): node freezes since the DGX OS 7.6.0 update (Nov 10) Setup 2× DGX Spark-based ASUS Ascent GX10 (GB10, 128 GB), Ubuntu 24.04.5 / DGX OS, connected by ConnectX-7 (QSFP direct link). Workload: vLLM tensor-parallel (TP=2) across both nodes, launched with sparkrun, plus a few Docker containers on node 1. Affected node: node 2 (serial W4MSAG001954CG3, UEFI GX10DGX.0106.2026.0707.0731, firmware last updated Sep 1). Node 1 has not frozen. What happens Node 2 stops responding without warning: no network, nothing written to the journal (last entries are routine earlyoom / cron lines). It needs a manual power-on. Node 1 sees the ConnectX link go down at that moment. Timeline (node 2, f
=== #386125 DeepSeek-V4.1-Flash-1017 (EXL3 2.9bpw) on 2x DGX Spark with TensorFold: 57 tok/s text, 92 tok/s code, 2.1-2.3x the vLLM kit posts=381
#6 2026-11-08T02:12 user158576: Yes, you need to persistently have the power_wrap_init workaround in your grub. Let me know if you need step by step instruction for modifying the GRUB config.

#7 2026-11-09T15:41 alex.zare99: Thanks. I’ve already added power_wrap_init persistently to my GRUB configuration alongside tegra234_cbb_init, and confirmed it is active in /proc/cmdline. I’ve also installed nvidia-spark-initcall-bl version 1.0-2. I’m monitoring the system now for further freezes or kernel errors.

#10 2026-11-15T09:27 dgk960: DGX Spark (GB10): node freezes since the DGX OS 7.6.0 update (Nov 10) Setup 2× DGX Spark-based ASUS Ascent GX10 (GB10, 128 GB), Ubuntu 24.04.5 / DGX OS, connected by ConnectX-7 (QSFP direct link). Workload: vLLM tensor-parallel (TP=2) across both nodes, launched with sparkrun, plus a few Docker containers on node 1. Affected node: node 2 (serial W4MSAG001954CG3, UEFI GX10DGX.0106.2026.0707.0731, firmware last updated Sep 1). Node 1 has not frozen. What happens Node 2 stops responding without warning: no network, nothing written to the journal (last entries are routine earlyoom / cron lines). It needs a manual power-on. Node 1 sees the ConnectX link go down at that moment. Timeline (node 2, from journalctl --list-boots and the last journal line of each boot) Before the update, node 2 ran 63 days without a freeze (Sep 8 → Nov 10, kernel 6.17.0-1032-nvidia, driver 580.173.02). On Nov 10 the OTA update took DGX OS 7.2.3 → 7.6.0 ( dgx-spark-ota-update-meta 25.09.3 → 26.09.3, ~500 packages), including kernel 7.0.0-1025-nvidia and driver 580.178.04. Freeze (last journal entry) Kernel Driver Nov 11 10:20 7.0.0-1025-nvidia 580.178.04 Nov 11 12:42 7.0.0-1025-nvidia 580.178.04 Nov 11 21:15 7.0.0-1025-nvidia 580.178.04 Nov 14 21:07 7.0.0-1025-nvidia 580.178.04 Nov 14 21:35 6.17.0-1032-nvidia 580.178.04 Nov 15 08:05 6.17.0-1032-nvidia 580.173.02 What I tested Booted the previous kernel 6.17.0-1032-nvidia (GRUB) with driver 580.178.04 → froze (Nov 14 21:35). Also downgraded the driver to 580.173.02 (both nodes) → froze (Nov 15 08:05). The rest of the 7.6.0 userspace and configuration stayed at the new versions. Both nodes are now back on the current release: kernel 7.0.0-1025-nvidia, driver 580.178.04. Note: during the downgrade, linux-modules-*-oracle-64k packages were pulled in as a dependency. Their /lib/modprobe.d blacklist contains blacklist sbsa_gwdt , so the SBSA watchdog driver was not loaded and the firmware-armed watchdog reset both nodes ~19 min after every boot. Those resets are not counted as freezes above. That situation is fixed (packages removed, sbsa_gwdt loads at boot again). Configuration change noticed in the update nv-iommu 25.12-1 (installed Nov 10) adds /etc/default/grub.d/iommu.cfg with iommu.passthrough=0 (from the dgx_spark entry in /etc/nvidia-platform.d/nvidia-platform-configs.json ). Before the update: iommu: Default domain type: Passthrough Since the update: iommu: Default domain type: Translated (set via kernel command line) Current kernel command line: init_on_alloc=0 iommu.passthrough=0 console=tty0 ... crashkernel=1G-:0M quiet splash initcall_blacklist=tegra234_cbb_init,power_wrap_init kho=off pci=pcie_bus_safe initcall_blacklist , kho=off and pci=pcie_bus_safe were also not present during the 63-day stable period. Available data I can provide nvidia-bug-report.sh output from both nodes, full journals for every boot listed above, apt history of the update, and temperature/power logs recorded on Nov 14–15. Happy to run any test


## E15. NVIDIA forum #386125 tail (jayleaton vs Mia, watermark PSA)
#379 2026-11-12T05:46 0rand: Honestly have no idea, sounds extremely alien

#381 2026-11-13T01:13 a.fairaizl: Long post - but a bit of info PSA: a raised vm.min_free_kbytes from an older recipe makes MemAvailable under-read, and everything keyed on it misfires ( I spent a long time due to this troubleshooting) Setup: four GB10 nodes on a switchless ring (two DGX Spark 4 TB, two ASUS GX10 1 TB), run as two TP=2 pairs: DeepSeek-V4.1-Flash-1017 EXL3 2.9bpw on the Zig TensorFold engine, and GLM-5.3-Flash NVFP4. We run MiaAI-Lab’s 2× recipe (now at c7f2b85 ), not Elevatormusic’s kit, but this is host-side and applies to either. Cause. MemAvailable ≈ MemFree − watermark reserve + part of the page cache, and the reserve is about 1.5 × min_free_kbytes . Our DSv4.1 nodes still had 5 GiB set from albond’s Qwen3.5 recipe in June (right for vLLM then; our fault for never revisiting it). That hides about 7.5 GiB. The GLM pair never had the setting, which made it a handy control. Test: grep -E 'MemFree|MemAvailable' /proc/meminfo; cat /proc/sys/vm/min_free_kbytes . If MemAvailable is several GiB under MemFree , that’s your watermarks. On the kernel’s own default (about 45 MB on these boxes) it reads true. What it broke for us The recipe’s load check: the default 12.2 GiB reserve wouldn’t load with ~119 GiB free, so we lowered it to 7.5, against the recipe’s own warning. The recipe’s memguard: killed the rank at once, so we turned it off. Production: the watermark took nearly all the ~8 GiB left after load, the page cache had nowhere to live, and under live traffic the head sat at kswapd 90% / PSI 

#382 2026-11-13T15:46 dashtotherock: I’ve been using @0rand ’s stack for 1017 to replace 0731 for like more than a week, I think it is pretty good so far, I don’t regret the upgrade. I use max effort with reasonix.

#383 2026-11-13T16:23 dashtotherock: I was using Deepseek-v41-1017-exl3-2.9bpw (EXL3, avg_bits 2.9) before, but there's an error: mtp.0.ffn.gate.bias: f16 {128}, expected f32 storage of {128} UnexpectedTensor I am not sure it was fixed, at the time to work with 0rand’s stack (28 Oct 2026) you have to use 2.8bpw: jayleaton/DeepSeek-V4.1-Flash-1017-EXL3-2.8bpw are you using @0rand ’s stack 0rand/deepseek-v41-tensorfold-spark ?

#384 2026-11-13T16:45 wolttam: It’s actually a tiny patch that is needed to make 0rand/jayleaton’s tensorfold build work with Mia’s weights. I’ll share that patch here: diff --git a/engine/zig/zig/src/families/deepseek_v41/names.zig b/engine/zig/zig/src/families/deepseek_v41/names.zig index 216feeb..1cfb3b6 100644 --- a/engine/zig/zig/src/families/deepseek_v41/names.zig +++ b/engine/zig/zig/src/families/deepseek_v41/names.zig @@ -83,7 +83,7 @@ pub fn expertName(block: []const u8, e: u32, p: ExpertProj, buf: []u8) ![]const pub const Store = enum { /// norms: bf16 in the pack (fp32 in the forward), fp32 accepted norm, - /// fp32 only (sinks, hc_*, router bias) + /// fp32, or fp16 widened exactly to fp32 (sinks, hc_*, router bias) f32, /// fp16 or bf16, rounded to bf16 once (router gate, indexer weights_proj, Markov heads) half, @@ -91,7 +91,7 @@ pub const Store = enum { pub fn accepts(s: Store, d: DType) bool { return switch (s) { .norm =&gt; d == .bf16 or d == .f32, - .f32 =&gt; d == .f32, + .f32 =&gt; d == .f32 or d == .f16, .half =&gt; d == .bf16 or d == .f16, }; } diff --git a/engine/zig/zig/src/families/deepseek_v41/plan.zig b/engine/zig/zig/src/families/deepseek_v41/plan.zig index 277e9f9..a65c579 100644 --- a/engine/zig/zig/src/families/deepseek_v41/plan.zig +++ b/engine/zig/zig/src/families/deepseek_v41/plan.zig @@ -253,7 +253,7 @@ const Builder = struct { const info = try b.pack.need(name); var n: u64 = 1; for (info.dims()) |d| n *= d; - if (info.dtype != .f32 and info.dtype != .bf16 or n != b.c.hid

#385 2026-11-14T12:48 a.fairaizl: No, MiaAI-Lab’s 2× recipe at c7f2b85 on Mia’s 2.9bpw. Thanks @wolttam for the patch; I’ll try 0rand’s Zig build with it once our soak finishes. It should be finishing up shortly. Actually, that was quicker than I thought - Follow-up: the 24 h soak at stock watermarks passed. 8,869 requests of mixed long sessions plus short requests, no guard kills, no PSI trips, no restarts. If you set your own memory floors: Set floors from where trouble starts, not from where normal running sits: We derived a floor of 6.25 GiB MemAvailable from an hour of synthetic tests. Run in shadow alongside the real guard, it would have fired 4,577 times in a day. Real traffic sat about 1 GiB lower than any synthetic shape. The floors we kept, 2.5 / 1.5 GiB with PSI as the main trigger, never fired. The head’s engine memory creeps up, then stops: Ours climbed about 0.3 GiB over the first few rounds of load. A restart dropped it 0.7 GiB, eight more rounds brought it back to the same level, and it then stayed flat for ten hours. The allocator is keeping its high-water mark, not a leak, so it’s nothing to restart for.

#386 2026-11-15T17:13 a.fairaizl: DeepSeek-V4.1 on TensorFold: MiaAI-Lab 2× (2.9bpw) vs jayleaton (2.8bpw) Follow-up . Both nodes on stock watermarks, as in the earlier post. Credit to jayleaton and ashhart for the engine work behind this. What changed. Structured output now works. Verified with one nested strict schema (required nested object, integer, enums at both levels, additionalProperties: false), which returned valid JSON with the correct value. Upstream’s structured suite also passes direct: 12 schema cases and 10 tool cases. Build. jayleaton TensorFold 12257eb51 (jayleaton 6fabbdd), 2.8bpw pack (HF 859396591c34). The comparison row is MiaAI-Lab 2× at 2.9bpw. The bit-width difference is a confound: any score gap could come from quantization rather than the engine. Served on 4 slots, TP=2 across two GB10 nodes. Accuracy. tool-eval-bench 2.7.1.dev11, --seed 42 --hardmode, thinking on, 4 slots. Both sides ran through the same LiteLLM gateway with --parallel 4. TC-45 and TC-64 are excluded from the shared comparison. Shared 180 points MiaAI-Lab 2× (2.9bpw) jayleaton (2.8bpw) High 162 162 Max 166 160 Tied at high. At max the 6-point gap comes from one run per side, and we haven’t measured run-to-run noise at the same setting, so that result is inconclusive. jayleaton passes TC-64 (2/2); the MiaAI-Lab runs excluded it after a 400 on response_format. TC-45. Excluded on both bench versions we tested. The bench’s pre-check sends a contradictory instruction (a required tool plus “do not call any tools”) that t

#387 2026-11-15T19:01 2893f57acbe7739fc460e9bd7: So what exactly is the current stack to use for this? 0rand’s with MiaAI model and that patch? Or just use native MiaAI? Or something else? This topic had a ton of work and then suddenly died off randomly.

#388 2026-11-15T20:30 a.fairaizl: Anyone else feel free to chime in if seeing better numbers or config - What I’m running right now: jayleaton’s deepseek-v41-tensorfold-spark with its own 2.8bpw pack. Main reasons: Structured output works ( response_format with strict schemas, tool_choice required/named). The MiaAI-Lab Zig build returns 400 on response_format . Upstream ships real tests (structured-output suite, grammar goldens) and publishes SHA256SUMS for the pack. Long-context prefill is ~11% faster than MiaAI-Lab at a matched ~600K. The cost: prose decode is ~10–15% slower, and at four ~500K sessions the head sits at ~4.5 GiB MemAvailable vs ~7 GiB on MiaAI-Lab, so don’t run anything else on the head under heavy load. Accuracy: tool-eval-bench is tied at high effort and inconclusive at max (one run each). MiaAI-Lab’s 2× recipe on its own is solid and well documented if you don’t need structured output. It ran fine for us at the recipe defaults once the watermark was fixed. (also keep in mind I’m running DGX Spark 4tb with Asus GX10 with 1 tb as worker node in the pair)

#389 2026-11-15T20:47 0rand: What’s wrong with jayleaton’s quant? It’s better than Miaai one by all metrics including TEB Ps I stopped commenting much because everything just works awesomely, I don’t feel like any improvement needed.

#390 2026-11-15T21:44 giles8: Yeah, same I am not commenting mostly on just 100% everything working right now. Eargerly awaiting some model releases, but all ok right now.

#391 2026-11-15T23:00 Dickson: Same here not gonna “stack-hop” until Qwen 4 releases next week.


## E16. NVIDIA forum #389131 (CDMM slow load)
#1 2026-11-15T13:26 1497245907: TL;DR — On DGX Spark (GB10), model weight loading can stall indefinitely at ~22 MB/s with one CPU core spinning inside libcuda , GPU at 1% utilisation. Neither --weight-loader-disable-mmap nor checkpoint prefetching helps, and rolling back from kernel 7.0.0-1019 to 6.17.0-1031 does not change it. Changing the coherent-memory mode fixes it: echo 'options nvidia NVreg_CoherentGPUMemoryMode=numa' | sudo tee /etc/modprobe.d/99-coherent-numa.conf sudo reboot # verify: grep -i CoherentGPUMemoryMode /proc/driver/nvidia/params -&gt; "numa" Weight loading went from “never finishes” to 50 s for 21.9 GB, and full server startup from &gt;48 min to 6 min 06 s . I am posting this because the two existing GB10 loading threads (the mmap one and the “system wide slowdown 50/60%” one) both turned out to be different bottlenecks on this box, and neither fix applied. The fix is reproducible in both directions: I have since toggled the parameter back to driver and the stall returned at the same tensor index, then toggled it back to numa and loading completed again — all on the same driver build, same kernel, same image. Still current as of 2026-11-15. The box is on the newest DGX OS release (7.6.0 / driver 615.71.09) and the DGX Spark package repo offers nothing newer: 615.71.09 is the newest driver, 610.57.04 is a transition shell ( Depends: *-615 ), and there is no 620 package in the Spark repo at all. The only pending update is dgx-spark-ota-update-meta 26.09.3, which just pulls nvidia-spark-c

#2 2026-11-16T01:39 elsaco: On the Spark the nvidia module has CoherentGPUMemoryMode set to an empty string so it defaults to “driver” mode. From open-gpu-kernel-modules/kernel-open/nvidia/nv-reg.h at e6a2e01579fbbd1ca2ed43fef2ee2589e9bd8bd9 · NVIDIA/open-gpu-kernel-modules · GitHub /* * Option: CoherentGPUMemoryMode * * Description: * * This option can be set to control how GPU Memory is accessed through * the coherent link. * * This option has no effect on platforms that do not support onlining * device memory to a NUMA node. * * Possible string values: * * "driver" (or unset) : disable onlining coherent memory to the OS as a NUMA node. The driver * will manage it in this case (default) * "numa" : enable onlining coherent memory to the OS as a NUMA node */ NVIDIA does recommend that HPC systems are configured in NUMA mode rather than CDMM mode for best performance of Unified Memory applications. See NVIDIA HPC Compilers User's Guide — NVIDIA HPC Compilers User's Guide 26.9 documentation It’s a user choice, if you think your Spark is a HPC system 😊



# Evidence dossier part 2
## E17. Live host state, both nodes (measured 2026-11-16 ~10:50 CST)
### local
7.0.0-1019-nvidia
580.178.04
BOOT_IMAGE=/boot/vmlinuz-7.0.0-1019-nvidia root=UUID=9f3cd4b6-f34e-435e-9fcf-ed7861f7cf99 ro init_on_alloc=0 iommu.passthrough=0 console=tty0 plymouth.ignore-serial-consoles plymouth.use-simpledrm earlycon=uart,mmio32,0x16A00000 console=tty0 console=ttyS0,921600 crashkernel=1G-:0M quiet splash initcall_blacklist=tegra234_cbb_init kho=off pci=pcie_bus_safe vt.handoff=7
dgx-release 7.6.0
dgx-spark-ota-update-meta 26.09.2
nv-iommu 25.12-1
nvidia-driver-580-open 580.178.04-0ubuntu0.24.04.1
nvidia-spark-initcall-bl 1.0-1
dgx-spark-ota-update-meta/noble-updates 26.09.3 all [可升級自：26.09.2]
linux-headers-nvidia-hwe-24.04/noble-updates,noble-security 7.0.0-1025.26~24.04.1 arm64 [可升級自：7.0.0-1019.19~24.04.2]
linux-image-nvidia-hwe-24.04/noble-updates,noble-security 7.0.0-1025.26~24.04.1 arm64 [可升級自：7.0.0-1019.19~24.04.2]
linux-modules-nvidia-580-open-7.0.0-1019-nvidia/noble-updates,noble-security 7.0.0-1019.19~24.04.2+2 arm64 [可升級自：7.0.0-1019.19~24.04.2+1]
linux-modules-nvidia-580-open-nvidia-hwe-24.04/noble-updates,noble-security 7.0.0-1025.26~24.04.1 arm64 [可升級自：7.0.0-1019.19~24.04.2+1]
linux-nvidia-hwe-24.04/noble-updates,noble-security 7.0.0-1025.26~24.04.1 arm64 [可升級自：7.0.0-1019.19~24.04.2]
nvidia-spark-initcall-bl/不明,noble-updates 1.0-2 arm64 [可升級自：1.0-1]
min_free_kbytes=45166 swappiness=1
MemFree:         2210012 kB
MemAvailable:    3966128 kB
Cached:          3854092 kB
SwapTotal:      16777212 kB
SwapFree:       16059520 kB
some avg10=0.00 avg60=0.00 avg300=0.00 total=39048695
full avg10=0.00 avg60=0.00 avg300=0.00 total=39022056
Mon 2026-11-16 12:19:08 CST      1h 16min Mon 2026-11-16 01:15:42 CST       9h ago apt-daily.timer                apt-daily.service
Tue 2026-11-17 06:10:25 CST           19h Mon 2026-11-16 06:58:12 CST  4h 4min ago apt-daily-upgrade.timer        apt-daily-upgrade.service
01autoremove
### 10.100.184.1
7.0.0-1019-nvidia
580.178.04
BOOT_IMAGE=/boot/vmlinuz-7.0.0-1019-nvidia root=UUID=9f3cd4b6-f34e-435e-9fcf-ed7861f7cf99 ro init_on_alloc=0 iommu.passthrough=0 console=tty0 plymouth.ignore-serial-consoles plymouth.use-simpledrm earlycon=uart,mmio32,0x16A00000 console=tty0 console=ttyS0,921600 crashkernel=1G-:0M quiet splash initcall_blacklist=tegra234_cbb_init kho=off pci=pcie_bus_safe vt.handoff=7
dgx-release 7.6.0
dgx-spark-ota-update-meta 26.09.2
nv-iommu 25.12-1
nvidia-driver-580-open 580.178.04-0ubuntu0.24.04.1
nvidia-spark-initcall-bl 1.0-1
dgx-spark-ota-update-meta/noble-updates 26.09.3 all [可升級自：26.09.2]
linux-headers-nvidia-hwe-24.04/noble-updates,noble-security 7.0.0-1025.26~24.04.1 arm64 [可升級自：7.0.0-1019.19~24.04.2]
linux-image-nvidia-hwe-24.04/noble-updates,noble-security 7.0.0-1025.26~24.04.1 arm64 [可升級自：7.0.0-1019.19~24.04.2]
linux-modules-nvidia-580-open-nvidia-hwe-24.04/noble-updates,noble-security 7.0.0-1025.26~24.04.1 arm64 [可升級自：7.0.0-1019.19~24.04.2+2]
linux-nvidia-hwe-24.04/noble-updates,noble-security 7.0.0-1025.26~24.04.1 arm64 [可升級自：7.0.0-1019.19~24.04.2]
nvidia-spark-initcall-bl/不明,noble-updates 1.0-2 arm64 [可升級自：1.0-1]
min_free_kbytes=45166 swappiness=1
MemFree:         2112324 kB
MemAvailable:    5854680 kB
Cached:          5848208 kB
SwapTotal:      16777212 kB
SwapFree:       16777180 kB
some avg10=0.00 avg60=0.00 avg300=0.00 total=7881364
full avg10=0.00 avg60=0.00 avg300=0.00 total=7879860
Mon 2026-11-16 20:29:49 CST       9h Mon 2026-11-16 06:03:32 CST 4h 59min ago apt-daily.timer                apt-daily.service
Tue 2026-11-17 06:25:21 CST      19h Mon 2026-11-16 06:04:50 CST 4h 58min ago apt-daily-upgrade.timer        apt-daily-upgrade.service
01autoremove

dgx-spark-ota-update-meta 26.09.3 Depends include: nvidia-spark-initcall-bl, nvidia-spark-grub-kho, nvidia-spark-grub-pci, nvidia-spark-run-apt-upgrade, ... (apt-cache depends). nvidia-spark-initcall-bl 1.0-2 is upgradable from 1.0-1 on node1. Note forum #388215: the fix adds power_wrap_init to initcall_blacklist; both nodes currently boot with initcall_blacklist=tegra234_cbb_init only.

## E18. Engine memory and cache (rank0 /health, /metrics)
{"active": 113904717092, "cache": 0, "peak": 114172103972}
tensorfold:requests_running 0
tensorfold:requests_waiting 0
tensorfold:prompt_tokens_total 23522575
tensorfold:generation_tokens_total 366404
tensorfold:mtp_drafted_total 308147
tensorfold:mtp_accepted_total 242110
rank0 log: "rank cache: 95.1 GiB of expert entries read whole in 8.2 s" (so the CDMM 22 MB/s load issue from #389131 is not present). /proc/driver/nvidia/params CoherentGPUMemoryMode: "" (default).

## E19. Proxy audit log (spark-fastfail-proxy :8889), 2026-11-13 21:10 .. 2026-11-16 10:12, 9799 rows
all rows 9799 external rows 466 {'100.79.40.68': 47, '100.108.5.82': 412, '100.70.199.89': 7}
external status {'200|None': 463, '429|None': 2, '400|None': 1}
external tools>0 332 thinking_off 7
external effort {'medium': 101, 'high': 132, 'low': 165, 'none': 62, 'None': 2, 'max': 4}
dsml_in_content all 36 external 0
loop_period all 36 external 0
shadow_loop_ch all 54 external 4
budget_hit all 11 external 0
all-time 400 by client {'127.0.0.1': 12, '100.108.5.82': 1}
last 2000 rows status|reason {'200|None': 1731, '429|None': 266, '400|None': 3}
The single external 400 (2026-11-16 00:19:18 CST, client 100.108.5.82 = owner MacBook, model "current", thinking off): rank0 log "refused chatcmpl-b1eb...: structured output (response_format and the guided_* fields) is not supported by this engine yet".
Note: most 429s in the last 2000 rows come from the 127.0.0.1 OmniScenario-1h benchmark (closed-loop test harness), not from real clients.

## E20. Recent production decisions (owner knowledge base)
- p17 (2026-11-15): PR #138 long-loop guard backport + --loop-guard-stop per-request + proxy effort-none fallback. 30-q bank 28/30, decode gate pass 87.0 tok/s, C2/C4/C8 118.6/141.8/156.8, 1h marathon 882/893 x200.
- 2026-11-15 22:16: rank0 --prompt-cache-gib 2.5 -> 2.0 (owner floor: not below 2.0) + MALLOC_ARENA_MAX=4. Node1 idle 2.43 -> 5.42 GiB. OmniScenario-1h full 52.7 min, Node1 min 2.86 GiB, cache hit 0.884, P0 36/36, 429=169 all queue_full (8/8 running + 8/8 queued), investigating whether the tester re-sends right after a 429 (commit 3593042 added 1 s backoff in the harness).
- RAM prompt cache held grows toward budget (2048 MiB), currently ~580 MiB after the run -> Node1 idle may drop ~1.5 GiB more over time.
- Proxy memory ladder: large prefill (>16K) concurrency 3 at free>=3.05 GiB, 2 at >=2.65, 1 below; base threshold 3.8 GiB when prompt cache is 2.0 GiB.
- Rejected before: TF_DS_FIX_K=2/3 (-15..-21%), TF_DS_ROUND_ROWS 24/32 (noise), think-close hint, loop-guard-stop+seed retry.
- Owner rules: DeepSeek only (no switching to other model families); every change goes stage by stage with full regression (30-q bank + decode gate + 1h marathon), keep only if positive, roll back if negative; no hardcoded slot counts or thresholds (scale-invariant).
