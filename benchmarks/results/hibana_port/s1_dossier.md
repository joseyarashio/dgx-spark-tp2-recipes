# Hibana port, Stage S1 dossier: MoE expert-union measurement on DeepSeek-V4.1-Flash TP=2 (2x DGX Spark GB10)

## Context
- Goal: decide whether to port Hibana's (sharar-project/hibana, Apache-2.0) budgeted expert selection ("route_budget",
  Nemotron Super/Bolt `fast` profile) into our native Zig engine. User policy: stepwise, keep only measured gains, external
  review after every stage, full regression at the end. Model scope is DeepSeek only.
- Hibana's own published numbers for this mechanism (their repo docs, not reproduced here): Bolt (9 of 240-496 experts,
  top-9) keep 6 + 20 per request + 64 per call: 114.2 -> 121.7 tok/s single stream (+6.6%), 213.7 -> 228.9 four streams
  (+7.1%); GPQA sampled thinking 75.8 vs 76.3 (p 1.0). Keep 4, 16:48 was 8% faster but GPQA -6.6 points (p 0.011),
  thinking 1.23x longer. Nemotron Super fast: keep 12, 48:128 (22 of 512 experts).

## Our engine facts (read from code and checkpoint)
- DeepSeek-V4.1-Flash-1017 EXL3 2.9 bpw (mul1 codebook), 40 layers, 384 routed experts top-6 + 1 shared expert (always in
  the last slot; slots = 7), routing = sqrt(softplus(logit)) + bias for selection, weights = selected scores renormalized
  x 1.5 (routed_scaling). Code of the served route kernel (`_route_row`, Triton AOT):
```python
def _route_row(L, BIAS, PICK, WTS, scale, shared_id, NE: tl.constexpr, NB: tl.constexpr, TOPK: tl.constexpr,
               SLOTS: tl.constexpr, SP: tl.constexpr, CG: tl.constexpr):
    e = tl.arange(0, NB)
    ok = e < NE
    if CG:                             # logits other programs just wrote: past this SM's L1
        lg = tl.load(L + e, mask=ok, other=0.0, cache_modifier=".cg")
    else:
        lg = tl.load(L + e, mask=ok, other=0.0)
    sp = tl.where(lg > 20.0, lg, tl.log(1.0 + tl.exp(lg)))
    sc = tl.sqrt(sp)
    b = tl.load(BIAS + e, mask=ok, other=0.0)
    sel = tl.where(ok, sc + b, float("-inf"))
    tot = 0.0
    s = tl.arange(0, SP)
    picks = tl.full((SP,), shared_id, dtype=tl.int32)
    ws = tl.zeros((SP,), dtype=tl.float32)
    for k in tl.static_range(TOPK):
        best = tl.max(sel, axis=0)
        idx = tl.min(tl.where(sel == best, e, NB), axis=0)          # lowest index among ties
        v = tl.sum(tl.where(e == idx, sc, 0.0), axis=0)
        picks = tl.where(s == k, idx, picks)
        ws = tl.where(s == k, v, ws)
        tot += v
        sel = tl.where(e == idx, float("-inf"), sel)
    ws = tl.where(s < TOPK, ws / (tot + 1e-20) * scale, 1.0)
    tl.store(PICK + s, picks, mask=s < SLOTS)
    tl.store(WTS + s, ws, mask=s < SLOTS)


@triton.jit
def _route(L, BIAS, PICK, WTS, scale, shared_id, NE: tl.constexpr, NB: tl.constexpr, TOPK: tl.constexpr,
           SLOTS: tl.constexpr, SP: tl.constexpr, PDL: tl.constexpr = False):
    if PDL:
        _prefetch_l2(BIAS + tl.minimum(tl.arange(0, NB // 32) * 32, NE - 1))   # the bias (a weight) while waiting
        gdc_wait()
        gdc_launch_dependents()
    r = tl.program_id(0)
    _route_row(L + r * NE, BIAS, PICK + r * SLOTS, WTS + r * SLOTS, scale, shared_id, NE, NB, TOPK, SLOTS, SP, False)


```
- TP=2: every rank holds half of every expert (I = 1152 of 2304 per rank). One routed expert, whole checkpoint:
  w1+w2+w3 trellis 3 x 4,423,680 B + scales = 13,315,596 B (12.70 MiB) -> about 6.35 MiB per rank per expert per layer.
- Verify-round MoE path (round.zig `moe`): rowmm_gate -> `_route` -> exl3_experts.decode = decode_prep (groups the window's
  picks into distinct experts `ucount`, members lists) + grouped gate/up kernel + grouped down kernel with per-row combine.
  The grid's x dimension is the number of distinct experts, so weight bytes read scale with distinct experts.
- decode_prep (CUDA):
```cuda
__global__ void __launch_bounds__(PREP_THREADS) decode_prep_kernel(
    const TIN* __restrict__ x, int x_stride, const int* __restrict__ pick, const half* __restrict__ suh0,
    const half* __restrict__ suh1, half* __restrict__ out0, half* __restrict__ out1, int K, int slots, int E, int R,
    int* __restrict__ uids, int* __restrict__ ucount, int* __restrict__ members, int maxm,
    const float* __restrict__ wts, const float* __restrict__ y, const float* __restrict__ add, float* __restrict__ out,
    int D, int store_y, int* __restrict__ epoch) {
    const int n = R * slots;
    asm volatile("griddepcontrol.launch_dependents;\n" ::: "memory");   // gate/up (it waits for this grid's end)
    if (blockIdx.x == 0 && threadIdx.x == 0 && epoch != nullptr) epoch[0] += 1;     // this launch's number
    if (blockIdx.x == 0) {
        extern __shared__ int sh_prep[];
        int* sp = sh_prep;
        int* first = sh_prep + n;
        for (int i = threadIdx.x; i < n; i += PREP_THREADS) sp[i] = pick[i];
        __syncthreads();
        for (int i = threadIdx.x; i < n; i += PREP_THREADS) {
            const int e = sp[i];
            int f = e >= 0 && e < E;
            for (int j = 0; f && j < i; ++j) f = sp[j] != e;
            first[i] = f;
        }
        __syncthreads();
        int used = 0;
        for (int i = threadIdx.x; i < n; i += PREP_THREADS) {
            const int e = sp[i];
            if (e < 0 || e >= E) continue;
            int place = 0, pos = 0, tot = 0;
            for (int j = 0; j < n; ++j) {
                const int ej = sp[j];
                place += first[j] && ej < e;
                tot += ej == e;
                pos += ej == e && j < i;
            }
            if (pos < maxm) members[place * maxm + pos] = (i / slots) * 32 + (i % slots);
            if (first[i]) {
                uids[place] = e;
                for (int k = tot; k < maxm; ++k) members[place * maxm + k] = -1;
                ++used;
            }
        }
        __shared__ int used_sh;
        if (threadIdx.x == 0) used_sh = 0;
        __syncthreads();
        if (used) atomicAdd(&used_sh, used);
        __syncthreads();
        if (threadIdx.x == 0) ucount[0] = used_sh;
        if (wts == nullptr) return;
        for (int r = 0; r < R; ++r) {
            int routed = 0;
            for (int q = 0; q < slots; ++q) routed += sp[r * slots + q] >= 0 && sp[r * slots + q] < E;
            if (routed) continue;
            for (int d = threadIdx.x * 4; d < D; d += PREP_THREADS * 4) {
                float acc[4] = {0.f, 0.f, 0.f, 0.f};
                for (int q = 0; q < slots; ++q) {
                    const float w = wts[r * slots + q];
#pragma unroll
                    for (int j = 0; j < 4; ++j)
                        acc[j] = fmaf(w, store_y ? y[((size_t)r * slots + q) * D + d + j] : 0.f, acc[j]);
                }
#pragma unroll
                for (int j = 0; j < 4; ++j)
                    out[(size_t)r * D + d + j] = add ? __fadd_rn(acc[j], add[(size_t)r * D + d + j]) : acc[j];
            }
        }
        return;
    }

```
- down epilogue combine (row's slots summed with wts; a slot whose pick is outside [0,E) is 'not routed', and with
  store_y=1 (the served default in decode) it still adds the y it finds):
```cuda
        if constexpr (EPI == 2) {
            // each member row's per-slot output for this column block, then the row's combine by the program that
            // completes the row's routed slots here
            const int n = by * 128 + 4 * lane;
            for (int row = warp; row < RR; row += W) {
                const int p = rows_sh[row + RR * hp];
                if (p < 0) continue;
                float v[4];
#pragma unroll
                for (int j = 0; j < 4; ++j) {
                    const int col = 4 * lane + j;
                    float s = red[0][row][col];
#pragma unroll
                    for (int w = 1; w < W; ++w) s += red[w][row][col];
                    float q = 0.f;                        // down_combine's split sum from 0 (one split)
                    q += s;
                    v[j] = q;
                }
                epi_fwht128(v, lane);
                float* yo = ep.y + (size_t)p * N + n;
#pragma unroll
                for (int j = 0; j < 4; ++j) yo[j] = v[j] * EPI_HAD * __half2float(ep.svh_d[(size_t)e * N + n + j]);
                if (ep.wts == nullptr) continue;
                __threadfence();
                __syncwarp();
                const int r = p / slots;
                int last = 0;
                if (lane == 0) {
                    int target = 0;
                    for (int q = 0; q < slots; ++q) {
                        const int pe = ep.pick[r * slots + q];
                        target += pe >= 0 && pe < ep.E;
                    }
                    int* c = ep.cnt + r * NY + by;
                    const int before = atomicAdd(c, 1);
                    last = before == target - 1;
                    if (last) *c = 0;
                }
                last = __shfl_sync(0xffffffffu, last, 0);
                if (!last) continue;
                __threadfence();
                float a4[4] = {0.f, 0.f, 0.f, 0.f};
                for (int q = 0; q < slots; ++q) {
                    const float w = ep.wts[r * slots + q];
                    const int pq = r * slots + q;
                    const int pe = ep.pick[pq];
                    float4 yv = make_float4(0.f, 0.f, 0.f, 0.f);
                    if ((pe >= 0 && pe < ep.E) || ep.store_y)
                        yv = __ldcg(reinterpret_cast<const float4*>(ep.y + (size_t)pq * N + n));
                    a4[0] = fmaf(w, yv.x, a4[0]);
                    a4[1] = fmaf(w, yv.y, a4[1]);
                    a4[2] = fmaf(w, yv.z, a4[2]);
                    a4[3] = fmaf(w, yv.w, a4[3]);
                }
#pragma unroll
                for (int j = 0; j < 4; ++j)
                    ep.out[(size_t)r * N + n + j] = ep.add ? __fadd_rn(a4[j], ep.add[(size_t)r * N + n + j]) : a4[j];
                if (ep.discard) {
                    // the row's slots' outputs of this column block (512 bytes each, 128-byte aligned: N a multiple
                    // of 128) are added and read by nothing else: drop their L2 lines (this warp read them all)
                    __syncwarp();
                    if (lane < 4 * slots) {

```
- Served round-time table (draft.zig round_ms, ms by round rows 1..16): 30.0, 35.2, 39.9, 44.9, 48.6, 52.1, 55.6, 59.1,
  62.7, 66.3, 69.6, 72.9, 75.5, 78.2, 81.3, 84.4, 87.5 (index 0 = 1 row). The lane core corrects it online (EMA).
- Production: TF_DS_STREAMS=8, round rows 16 (TF_DS_ROUND_ROWS default), adaptive draft depth per stream.
- Baseline decode gate (production p17, decode_gate_loopfallback.json): 9-prompt greedy median 87.01 tok/s, MTP accept
  0.726, C2 118.59, C4 141.79, C8 156.83 tok/s aggregate.

## S1 method
- Measurement-only build on branch hibana-port (diff below, 115 lines, no change to arithmetic): env TF_DS_EXPERT_STATS=2 on
  rank 0 only; a 1-thread kernel after each decode-window MoE adds decode_prep's ucount into mapped host memory by row count;
  mode 2 also copies each layer's pick/wts [R,7] (D2D into mapped memory) and appends each verify round to rounds.bin.
- Served under the normal production launcher (only rank0.sh gained the env line), workload = run_decode_gate.py --reps 1
  (9 code prompts greedy single stream x 384 tokens, then C2/C4/C8 with distinct prompts, through proxy 8889, external
  traffic 0 on every sample). 1,432 verify rounds captured (57,280 layer-calls). Then the production binary and rank0.sh were
  restored (sha256 10d41f91.. and 340cdaaf.. verified, env checked inside the container).
- Offline simulation of Hibana route_budget on the captured rounds (analyzer below): each row keeps its top KEEP routed
  experts; the call reads at most min(CAP, PER_REQ x streams) distinct routed experts, filled by summed routing weight;
  rows take any of their top-6 the call reads (free riders). Reported: experts read, routing-weight share dropped per row
  (mean/p95/max), rows that lose any expert.
- Stream histogram of captured rounds: {'1': 1007, '2': 115, '3': 7, '4': 113, '5': 7, '6': 21, '7': 8, '8': 154}
- Decode gate during the instrumented run (NOT a candidate; instrumentation adds per-layer D2D copies + host writes):
  greedy 85.03, accept 0.7309, C2 108.47 (below the 111.45 floor), C4 145.03, C8 157.53.

## S1 results
### Distinct routed experts per layer-call by round rows (no budget)
- rows 2: layer-calls 2000, mean distinct routed experts 9.66, max 12
- rows 3: layer-calls 11240, mean distinct routed experts 13.17, max 18
- rows 4: layer-calls 5840, mean distinct routed experts 16.44, max 24
- rows 5: layer-calls 7480, mean distinct routed experts 19.62, max 30
- rows 6: layer-calls 14640, mean distinct routed experts 22.33, max 36
- rows 7: layer-calls 800, mean distinct routed experts 25.82, max 40
- rows 8: layer-calls 800, mean distinct routed experts 29.68, max 47
- rows 9: layer-calls 960, mean distinct routed experts 31.55, max 51
- rows 10: layer-calls 720, mean distinct routed experts 32.77, max 55
- rows 11: layer-calls 680, mean distinct routed experts 35.96, max 62
- rows 12: layer-calls 400, mean distinct routed experts 37.45, max 60
- rows 13: layer-calls 840, mean distinct routed experts 41.31, max 66
- rows 14: layer-calls 920, mean distinct routed experts 44.50, max 72
- rows 15: layer-calls 800, mean distinct routed experts 45.23, max 73
- rows 16: layer-calls 9160, mean distinct routed experts 51.22, max 85
- Engine-side ucount (includes the shared expert) agrees: e.g. rows 16 sum/calls = 168703/3560.
- No 1-row rounds occur in serving: a lone stream verifies pending + drafts.

### Budget simulation, grouped by live streams in the round
#### 1 stream
- keep 6 cap  0 per  0: experts read 17.8 (100% of union) | drop mean 0.000 p95 0.000 | rows losing 0%
- keep 5 cap  0 per 20: experts read 16.9 (95% of union) | drop mean 0.022 p95 0.123 | rows losing 22%
- keep 5 cap  0 per 16: experts read 16.1 (90% of union) | drop mean 0.041 p95 0.133 | rows losing 39%
- keep 4 cap  0 per 20: experts read 16.5 (93% of union) | drop mean 0.030 p95 0.189 | rows losing 21%
- keep 4 cap  0 per 16: experts read 15.0 (84% of union) | drop mean 0.069 p95 0.250 | rows losing 45%
- keep 4 cap  0 per 12: experts read 13.4 (75% of union) | drop mean 0.115 p95 0.270 | rows losing 71%
- keep 3 cap  0 per 12: experts read 12.1 (68% of union) | drop mean 0.155 p95 0.392 | rows losing 72%
- keep 4 cap 48 per  0: experts read 17.8 (100% of union) | drop mean 0.000 p95 0.000 | rows losing 0%
- keep 4 cap 32 per  0: experts read 17.8 (100% of union) | drop mean 0.000 p95 0.000 | rows losing 0%
#### 2-4 streams
- keep 6 cap  0 per  0: experts read 36.6 (100% of union) | drop mean 0.000 p95 0.000 | rows losing 0%
- keep 5 cap  0 per 20: experts read 36.4 (100% of union) | drop mean 0.001 p95 0.000 | rows losing 2%
- keep 5 cap  0 per 16: experts read 35.9 (98% of union) | drop mean 0.007 p95 0.082 | rows losing 7%
- keep 4 cap  0 per 20: experts read 36.4 (99% of union) | drop mean 0.002 p95 0.000 | rows losing 1%
- keep 4 cap  0 per 16: experts read 35.6 (97% of union) | drop mean 0.009 p95 0.088 | rows losing 6%
- keep 4 cap  0 per 12: experts read 32.9 (90% of union) | drop mean 0.035 p95 0.204 | rows losing 25%
- keep 3 cap  0 per 12: experts read 32.5 (89% of union) | drop mean 0.038 p95 0.233 | rows losing 24%
- keep 4 cap 48 per  0: experts read 35.5 (97% of union) | drop mean 0.009 p95 0.091 | rows losing 7%
- keep 4 cap 32 per  0: experts read 30.5 (83% of union) | drop mean 0.061 p95 0.236 | rows losing 43%
#### 5-8 streams
- keep 6 cap  0 per  0: experts read 51.9 (100% of union) | drop mean 0.000 p95 0.000 | rows losing 0%
- keep 5 cap  0 per 20: experts read 51.9 (100% of union) | drop mean 0.000 p95 0.000 | rows losing 0%
- keep 5 cap  0 per 16: experts read 51.9 (100% of union) | drop mean 0.000 p95 0.000 | rows losing 0%
- keep 4 cap  0 per 20: experts read 51.9 (100% of union) | drop mean 0.000 p95 0.000 | rows losing 0%
- keep 4 cap  0 per 16: experts read 51.9 (100% of union) | drop mean 0.000 p95 0.000 | rows losing 0%
- keep 4 cap  0 per 12: experts read 51.9 (100% of union) | drop mean 0.000 p95 0.000 | rows losing 0%
- keep 3 cap  0 per 12: experts read 51.9 (100% of union) | drop mean 0.000 p95 0.000 | rows losing 0%
- keep 4 cap 48 per  0: experts read 46.1 (89% of union) | drop mean 0.036 p95 0.190 | rows losing 28%
- keep 4 cap 32 per  0: experts read 37.4 (72% of union) | drop mean 0.111 p95 0.266 | rows losing 73%

### First-principles byte estimate (upper bound, assumes expert reads are bandwidth-bound and linear)
- 16-row round (5-8 streams): 51.9 routed + 1 shared = 52.9 experts x 6.35 MiB x 40 layers = 13.1 GiB per rank per round;
  at ~273 GB/s that is ~52 ms of the table's 87.5 ms. A cap of 48 reads 46.1 routed (-5.8) -> ~1.44 GiB less, ~5.7 ms
  (~6.5% of the round) at 3.6% mean routing weight dropped and 28% of rows losing at least one expert. Cap 32: -14.5
  experts, ~14 ms (~16%), but 11.1% weight dropped and 73% rows affected.
- Single stream (rows ~3-6): 17.8 routed; keep 4 / 12 per request reads 13.4 (-4.4) -> ~1.1 GiB, ~4 ms of ~45-52 ms
  (~8-9%), at 11.5% weight dropped and 71% of rows affected; keep 5 / 20 per request: -0.9 experts (~2%), 2.2% dropped.
- Per-request caps (Hibana style) do not bind at all at 5-8 streams (union 51.9 < 12 x streams); only the absolute cap does.

## Implementation sketch for S2 (if approved)
- A graph-safe CUDA kernel between `_route` and decode_prep in round.zig moe (verify rounds only; prompt chunks and the
  DSpark drafter untouched): per-expert score sum over the window's rows, keep set = every row's top KEEP, then fill by summed
  weight up to the cap; each row's dropped slots are renamed to the row's top expert at weight 0 (Hibana repeat=True, so
  decode_prep/down epilogue counters stay consistent and no stale y is added), kept weights renormalized over kept (x 1.5).
  Env-gated (default off), parameters TF_DS_MOE_KEEP / TF_DS_MOE_CAP / TF_DS_MOE_PER_REQ. The kept-weight renormalization
  rule (renormalize vs leave as-is) is an open choice.
- Note: dropping experts changes the target's verify logits, so it also shifts draft acceptance and the emitted tokens
  (lossy; it changes greedy outputs).

## S1 instrumentation diff (engine)
```diff
diff --git a/zig/kernels/cuda/dsv41_ops.cu b/zig/kernels/cuda/dsv41_ops.cu
index 8503b89e..58216c8b 100644
--- a/zig/kernels/cuda/dsv41_ops.cu
+++ b/zig/kernels/cuda/dsv41_ops.cu
@@ -34,6 +34,19 @@ extern "C" __global__ void tf_ds_clock_kernel(uint64_t* buf, uint32_t tag, uint3
     }
 }
 
+// A measurement (TF_DS_EXPERT_STATS): after a decode window's experts, add the window's distinct expert count (decode_prep's
+// ucount, the shared expert included) to stats[rows] = (calls, sum ucount, sum ucount^2). One thread; captured in the
+// round graphs like any kernel; reads nothing the forward writes later and writes nothing the forward reads.
+extern "C" __global__ void tf_ds_ucount_acc_kernel(const int* ucount, unsigned long long* stats, int rows) {
+    if (threadIdx.x == 0 && blockIdx.x == 0) {
+        const unsigned long long u = (unsigned long long)ucount[0];
+        unsigned long long* s = stats + 3 * (size_t)rows;
+        s[0] += 1ull;
+        s[1] += u;
+        s[2] += u * u;
+    }
+}
+
 // torch's keys.topk(k, sorted=False).values for the indexer's int64 keys, a row a block (1024 threads): the k largest
 // values are one multiset whatever the order (the keys are unique: score bits above, inverted index below), and
 // _topk_finish sorts their indices. A radix select finds the k-th largest key (eight 8-bit digits from the top, signed
diff --git a/zig/src/families/dsv41/model.zig b/zig/src/families/dsv41/model.zig
index 514868a9..4d8a4e98 100644
--- a/zig/src/families/dsv41/model.zig
+++ b/zig/src/families/dsv41/model.zig
@@ -142,6 +142,13 @@ pub const Model = struct {
     clk_rounds: u64 = 0,
     t_forward: u64 = 0,
     t_absorb: u64 = 0,
+    // TF_DS_EXPERT_STATS (a measurement, rank 0): 1 = each decode window's distinct experts by row count, 2 = also
+    // every verify round's picks and weights appended to a file (capped); mapped host memory the kernels write
+    xs_host: ?cuda.HostBuffer = null,
+    xd_host: ?cuda.HostBuffer = null,
+    xs_fd: c_int = -1,
+    xs_rounds: u64 = 0,
+    xs_dumped: u64 = 0,
     // world 4: the 2D split's exchanges (prompt2d.zig, TP4's), with the RDMA rings when asked
     two: ?prompt2d.Two = null,
     rdma_rings: ?ring2d.Rings = null,
@@ -194,6 +201,11 @@ pub const Model = struct {
         m.pgraphs = null;
         m.two = null;
         m.rdma_rings = null;
+        m.xs_host = null;
+        m.xd_host = null;
+        m.xs_fd = -1;
+        m.xs_rounds = 0;
+        m.xs_dumped = 0;
         const d = ctx.d;
         m.cfg = try Config.read(a, io, o.model_dir);
         const c = &m.cfg;
@@ -299,6 +311,25 @@ pub const Model = struct {
         }
         m.rd = try round.Round.init(&m.eng, &m.arena, a, o.pool);
         m.amax = try m.arena.take(round.max_rows * 4);
+        if (std.c.getenv("TF_DS_EXPERT_STATS")) |v| {
+            const mode = std.fmt.parseInt(u8, std.mem.span(v), 10) catch 0;
+            if (mode >= 1 and o.rank == 0 and m.ops.ucount_acc != null) {
+                const hb = try cuda.HostBuffer.allocMapped(d, (round.max_rows + 1) * 3 * 8);
+                @memset(hb.bytes, 0);
+                m.xs_host = hb;
+                m.rd.xstats = try hb.device();
+                if (mode >= 2) {
+                    const xhalf = c.layers * round.max_rows * m.eng.slots() * 4;
+                    const hd = try cuda.HostBuffer.allocMapped(d, 2 * xhalf);
+                    @memset(hd.bytes, 0);
+                    m.xd_host = hd;
+                    m.rd.xdump = try hd.device();
+                    m.rd.xdump_half = xhalf;
+                    m.xs_fd = std.c.open("/home/joseyarashio/.cache/dsv41-expert-stats/rounds.bin", .{ .ACCMODE = .WRONLY, .CREAT = true, .TRUNC = true }, @as(std.c.mode_t, 0o644));
+                }
+                std.log.info("expert stats: on (mode {d}, layers {d}, slots {d})", .{ mode, c.layers, m.eng.slots() });
+            }
+        }
         if (o.graphs) m.graphs = round.Graphs.init(gpa, o.graph_cap);
         if (o.side) try m.rd.useSide(&m.eng);
         if (o.prefetch) try m.rd.usePrefetch(&m.eng);
@@ -820,6 +851,50 @@ pub const Model = struct {
         }
         try m.stream.synchronize();
         if (m.prof) m.t_absorb = m.now() - t1;
+        if (m.xs_host != null) m.expertStats(rows);
+    }
+
+    /// TF_DS_EXPERT_STATS: every 256 rounds the stats file; with mode 2 this round's picks and weights appended
+    /// (header: magic, rows, layers, slots, windows; each row's stream slot; picks i32 [layers][rows][slots]; weights f32
+    /// the same), until 2 GiB.
+    fn expertStats(m: *Model, rows: round.Rows) void {
+        m.xs_rounds += 1;
+        const R = rows.ids.len;
+        if (m.xs_fd >= 0 and m.xd_host != null and m.xs_dumped < (2 << 30)) {
+            const sl = m.eng.slots();
+            const L = m.w.layers.len;
+            const nw: u32 = if (rows.windows) |w| @intCast(w.len) else 1;
+            const hdr: [8]u32 = .{ 0x58535431, @intCast(R), @intCast(L), @intCast(sl), nw, 0, 0, 0 };
+            var slots_buf: [round.max_rows]i32 = @splat(0);
+            for (0..R) |i| slots_buf[i] = if (rows.slots) |s| @intCast(s[i]) else 0;
+            const hb = m.xd_host.?.bytes;
+            const half = m.rd.xdump_half;
+            var n: usize = 0;
+            n += @intCast(@max(0, std.c.write(m.xs_fd, std.mem.asBytes(&hdr).ptr, 32)));
+            n += @intCast(@max(0, std.c.write(m.xs_fd, std.mem.sliceAsBytes(slots_buf[0..R]).ptr, R * 4)));
+            for (0..2) |part| for (0..L) |li| {
+                const off = part * half + li * round.max_rows * sl * 4;
+                n += @intCast(@max(0, std.c.write(m.xs_fd, hb[off..].ptr, R * sl * 4)));
+            };
+            m.xs_dumped += n;
+        }
+        if (m.xs_rounds % 256 != 0) return;
+        const st = std.mem.bytesAsSlice(u64, m.xs_host.?.bytes);
+        var out: [16384]u8 = undefined;
+        var w: std.Io.Writer = .fixed(&out);
+        w.print("{{\"rounds\": {d}, \"by_rows\": {{", .{m.xs_rounds}) catch return;
+        var first = true;
+        for (0..round.max_rows + 1) |r| {
+            if (st[3 * r] == 0) continue;
+            w.print("{s}\"{d}\": [{d}, {d}, {d}]", .{ if (first) "" else ", ", r, st[3 * r], st[3 * r + 1], st[3 * r + 2] }) catch return;
+            first = false;
+        }
+        w.print("}}}}\n", .{}) catch return;
+        const fd = std.c.open("/home/joseyarashio/.cache/dsv41-expert-stats/stats.json.part", .{ .ACCMODE = .WRONLY, .CREAT = true, .TRUNC = true }, @as(std.c.mode_t, 0o644));
+        if (fd < 0) return;
+        _ = std.c.write(fd, w.buffered().ptr, w.buffered().len);
+        _ = std.c.close(fd);
+        _ = std.c.rename("/home/joseyarashio/.cache/dsv41-expert-stats/stats.json.part", "/home/joseyarashio/.cache/dsv41-expert-stats/stats.json");
     }
 
     /// The rounds' GPU clocks (a profile): the forward's start and each stretch's ends, for its gaps.
diff --git a/zig/src/families/dsv41/ops.zig b/zig/src/families/dsv41/ops.zig
index a82baee0..a0e872a4 100644
--- a/zig/src/families/dsv41/ops.zig
+++ b/zig/src/families/dsv41/ops.zig
@@ -37,6 +37,7 @@ pub const Ops = struct {
     copy16: cuda.Function,
     argmax_rows: cuda.Function,
     gpu_clock: cuda.Function,
+    ucount_acc: ?cuda.Function = null, // TF_DS_EXPERT_STATS (absent from older images)
 
     /// The three images (cuda.kernels.torch_pointwise, torch_movement and dsv41_ops, or the fatbins' bytes).
     pub fn load(d: *const cuda.Driver, pointwise: []const u8, movement: []const u8, family: []const u8) !Ops {
@@ -68,6 +69,7 @@ pub const Ops = struct {
             .copy16 = try fm.function("tf_ds_copy_rows16_kernel"),
             .argmax_rows = try fm.function("tf_ds_argmax_rows_kernel"),
             .gpu_clock = try fm.function("tf_ds_clock_kernel"),
+            .ucount_acc = fm.function("tf_ds_ucount_acc_kernel") catch null,
         };
     }
 
@@ -302,6 +304,16 @@ pub const Ops = struct {
         try go(o.gpu_clock, s, 1, 32, &a);
     }
 
+    /// A measurement: stats[rows] += (1, ucount, ucount^2) from a decode window's distinct-expert count (one thread).
+    pub fn ucountAcc(o: *const Ops, s: cuda.Stream, ucount: u64, stats: u64, rows: usize) !void {
+        const f = o.ucount_acc orelse return error.MissingKernel;
+        var a: cuda.Args = .{};
+        a.add(ucount);
+        a.add(stats);
+        a.add(@as(c_int, @intCast(rows)));
+        try go(f, s, 1, 32, &a);
+    }
+
     /// dst row i = src row idx[i] (int64 indices, rows of `bytes` bytes); an index outside [0, src_rows) sets the
     /// caller's zeroed uint32 flag `invalid` and leaves that row as it was.
     pub fn gatherRows(o: *const Ops, s: cuda.Stream, src: u64, src_rows: usize, idx: u64, dst: u64, bytes: usize, rows: usize, invalid: u64) !void {
diff --git a/zig/src/families/dsv41/round.zig b/zig/src/families/dsv41/round.zig
index 104053a0..54d0e419 100644
--- a/zig/src/families/dsv41/round.zig
+++ b/zig/src/families/dsv41/round.zig
@@ -197,6 +197,11 @@ pub const Round = struct {
     clk_marks: bool = false,
     clk_ratio: ?u8 = null, // phase clocks only in the layers of this compress ratio (TF_DS_CLOCK_MARKS=3: ratio 2)
     cur_ratio: u8 = 0, // the layer a stretch is on (its compress ratio) // clocks at every phase mark too (Model.useClock(true)), not only around the stretches
+    // TF_DS_EXPERT_STATS (a measurement, model.zig): per row count (calls, sum, sum^2) of the decode windows' distinct
+    // experts, u64 [max_rows + 1][3]; and each layer's picks and weights, [2][layers][max_rows][slots] (0: off)
+    xstats: u64 = 0,
+    xdump: u64 = 0,
+    xdump_half: usize = 0,
     clk: u64 = 0, // [1 + 2 * max_clocks] u64: the count, then each clock and its phase (PhaseTimer.Phase or clock_*)
 
     pub fn init(e: *const Engine, a: *prompt.Arena, gpa: std.mem.Allocator, pool_cap: usize) !Round {
@@ -220,6 +225,9 @@ pub const Round = struct {
         rd.clk_ratio = null;
         rd.cur_ratio = 0;
         rd.clk = 0;
+        rd.xstats = 0;
+        rd.xdump = 0;
+        rd.xdump_half = 0;
         rd.bucket = 0;
         rd.has_cand = false;
         rd.kk = 0;
@@ -747,6 +755,13 @@ fn moe(e: *const Engine, rd: *Round, ch: *const Chunk, li: usize) !void {
         try rd.mark(e, .m_x);
         try exl3_experts2d.decodeDown(e.ex, e.s, lay.experts, ch.xsd, tw.xd_full, rd.pick, rd.mw, rd.pm, R);
     } else try exl3_experts.decode(e.ex, e.s, lay.experts, ch.xsd, rd.x, c.hidden, rd.pick, rd.mw, rd.pm, R, c.swiglu_limit);
+    if (rd.xstats != 0) try e.ops.ucountAcc(e.s, ch.xsd.count, rd.xstats, R);
+    if (rd.xdump != 0) {
+        const n = R * sl * 4;
+        const off = li * max_rows * sl * 4;
+        try e.d.check(e.d.api.cuMemcpyDtoDAsync_v2(rd.xdump + off, rd.pick, n, e.s.handle), "cuMemcpyDtoDAsync");
+        try e.d.check(e.d.api.cuMemcpyDtoDAsync_v2(rd.xdump + rd.xdump_half + off, rd.mw, n, e.s.handle), "cuMemcpyDtoDAsync");
+    }
     // the prefetch behind the experts: the next layer's attention mix and input linears (an Engram layer: the first
     // 4 MiB of its wkv), after the last layer the head
     if (li + 1 < e.w.layers.len) {

```

## Analyzer
```python
#!/usr/bin/env python3
"""Hibana port S1: what a budgeted expert selection (Hibana route_budget) would do on this engine's real verify rounds.

Reads the engine's TF_DS_EXPERT_STATS=2 dump (rounds.bin: each verify round's picks and weights per layer) and stats.json
(distinct experts per decode window by row count), and simulates route_budget offline:
  each row keeps its top KEEP routed experts (by routing weight); the call reads at most min(CAP, PER_REQ x streams)
  distinct routed experts, filled by summed routing weight; every row also takes its other top-k experts the call reads
  anyway (free riders). Reports, per configuration: distinct routed experts read (mean, by row count), the share of
  routing weight dropped per token (mean / p95 / max), and the fraction of rows that lose any expert.

usage: analyze_expert_union.py [--dump ~/.cache/dsv41-expert-stats/rounds.bin] [--out results.json]
"""
import argparse, collections, json, os, statistics, struct, sys

MAGIC = 0x58535431


def rounds(path):
    with open(path, "rb") as f:
        while True:
            h = f.read(32)
            if len(h) < 32:
                return
            magic, R, L, S, nw = struct.unpack("<5I", h[:20])
            if magic != MAGIC:
                raise SystemExit(f"bad magic at {f.tell() - 32}")
            slots = struct.unpack(f"<{R}i", f.read(4 * R))
            body = f.read(2 * L * R * S * 4)
            if len(body) < 2 * L * R * S * 4:
                return
            picks = struct.unpack(f"<{L * R * S}i", body[: L * R * S * 4])
            wts = struct.unpack(f"<{L * R * S}f", body[L * R * S * 4:])
            yield R, L, S, nw, slots, picks, wts


def budget(rows, keep, cap, per_req, streams):
    """rows: list of [(expert, weight)] (routed only, rank order). Returns (distinct read, dropped share per row)."""
    lim = min(cap, per_req * streams) if per_req else cap
    must = set()
    for r in rows:
        must.update(e for e, _ in r[:keep])
    chosen = set(must)
    if len(chosen) < lim:
        score = collections.Counter()
        for r in rows:
            for e, w in r:
                if e not in chosen:
                    score[e] += w
        for e, _ in score.most_common():
            if len(chosen) >= lim:
                break
            chosen.add(e)
    drop = []
    for r in rows:
        tot = sum(w for _, w in r) or 1.0
        drop.append(sum(w for e, w in r if e not in chosen) / tot)
    return len(chosen), drop


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", default=os.path.expanduser("~/.cache/dsv41-expert-stats/rounds.bin"))
    ap.add_argument("--stats", default=os.path.expanduser("~/.cache/dsv41-expert-stats/stats.json"))
    ap.add_argument("--out", default=None)
    ap.add_argument("--max-rounds", type=int, default=20000)
    a = ap.parse_args()
    # configurations: (keep, cap, per_request); cap is per layer per call over routed experts
    cfgs = [(k, c, p) for k in (6, 5, 4, 3) for (c, p) in ((24, 0), (32, 0), (48, 0), (64, 0), (96, 0), (0, 12), (0, 16), (0, 20))]
    acc = {c: {"distinct": [], "drop": [], "rows_hit": 0, "rows": 0} for c in cfgs}
    base = collections.defaultdict(list)  # rows -> distinct routed experts per layer-call (no budget)
    n_rounds = 0
    streams_hist = collections.Counter()
    for R, L, S, nw, slots, picks, wts in rounds(a.dump):
        n_rounds += 1
        if n_rounds > a.max_rounds:
            break
        streams = len(set(slots))
        streams_hist[streams] += 1
        for li in range(L):
            rows = []
            for r in range(R):
                o = (li * R + r) * S
                # routed slots are 0..S-2 (the shared expert is the last slot, every row); keep rank order
                rows.append([(picks[o + q], wts[o + q]) for q in range(S - 1) if 0 <= picks[o + q] < 384])
            distinct = len({e for r in rows for e, _ in r})
            base[R].append(distinct)
            if R == 1:
                continue  # one row: a budget never binds below top-k
            for c in cfgs:
                keep, cap, per = c
                capv = cap if cap else 10 ** 9
                n, drop = budget(rows, keep, capv, per, streams)
                ac = acc[c]
                ac["distinct"].append(n / max(1, distinct))
                ac["drop"].extend(drop)
                ac["rows"] += len(drop)
                ac["rows_hit"] += sum(1 for d in drop if d > 0)
    out = {"rounds": n_rounds, "streams_hist": dict(sorted(streams_hist.items())),
           "baseline_distinct_by_rows": {r: {"n": len(v), "mean": statistics.mean(v), "max": max(v)} for r, v in sorted(base.items())}}
    res = []
    for c, ac in acc.items():
        if not ac["drop"]:
            continue
        d = sorted(ac["drop"])
        res.append({"keep": c[0], "cap": c[1], "per_req": c[2], "read_frac_of_union": statistics.mean(ac["distinct"]),
                    "drop_mean": statistics.mean(d), "drop_p95": d[int(0.95 * (len(d) - 1))], "drop_max": d[-1],
                    "rows_losing_any": ac["rows_hit"] / ac["rows"]})
    out["budget"] = res
    if os.path.exists(a.stats):
        out["engine_stats"] = json.load(open(a.stats))
    s = json.dumps(out, indent=1)
    if a.out:
        open(a.out, "w").write(s)
    print(s)


if __name__ == "__main__":
    main()

```

## Hibana route_budget (reference)
```python
def route_budget(fused: torch.Tensor, bias: torch.Tensor, k: int, latent: int, keep: int, budget: int,
                 slots: torch.Tensor | None = None, steps: int = 1, per_request: int = 0, repeat: bool = True,
                 fallback: int = 0):
    """Budgeted top-k over fused FP32 [R, E + latent] -> (ids [R, k], renormalized weights [R, k], BF16 latent): the
    call reads at most min(budget, per_request x real requests) distinct experts (or `budget` without
    `per_request`), more only when the rows' guaranteed top `keep` exceed it (a budget of 0: the guaranteed experts
    alone). Each real row takes those of its top k (by choice score) that are in the set, in rank order, its top
    `keep` first (the others ride along free); its weights are its plain sigmoid scores renormalized over those. Slots
    left over (all of a padded row's) name the row's top expert (a padded row: row 0's) at weight 0, or without
    `repeat` no expert (id E). `fallback` (< keep): when the guaranteed experts' union exceeds the cap, each real row is
    guaranteed only its top `fallback` and the cap fills by routing weight (rows keep whichever of their top k the set
    holds). Five launches, no atomics, no host sync."""
    from hibana.kernels.flashnext_fused import _budget_score_kernel
    r = fused.shape[0]
    e = fused.shape[1] - latent
    block, cp = triton.next_power_of_2(e), triton.next_power_of_2(k)
    nw = block // 32
    dev = fused.device
    cand = torch.empty((r, cp), dtype=torch.int32, device=dev)
    p = torch.empty((r, cp), dtype=torch.float32, device=dev)
    bits = torch.empty((r, nw), dtype=torch.int32, device=dev)
    bits2 = torch.empty((r, nw), dtype=torch.int32, device=dev) if fallback else bits
    dense = torch.empty((r, block), dtype=torch.float32, device=dev)
    score = torch.empty((block,), dtype=torch.float32, device=dev)
    chosen = torch.empty((nw,), dtype=torch.int32, device=dev)
    ids = torch.empty((r, k), dtype=torch.int32, device=dev)
    w = torch.empty((r, k), dtype=torch.float32, device=dev)
    lat = torch.empty((r, latent), dtype=torch.bfloat16, device=dev)
    sl = cand if slots is None else slots
    common = dict(C=k, CP=cp, STEPS=steps, HAS_SLOTS=slots is not None)
    _route_rank_kernel[(r,)](fused, bias, sl, cand, p, bits, dense, lat, fused.stride(0), bits2, e, BLOCK=block,
                             KEEP=keep, K=k, LAT=latent, G=fallback, num_warps=1, **common)
    _budget_score_kernel[(block // 32,)](dense, score, r, BLOCK=block, EB=32, RB=16, num_warps=1)
    rb = min(64, max(16, triton.next_power_of_2(r)))
    _share_select_kernel[(nw,)](score, bits, sl, chosen, r, budget, per_request, bits2, E=e, BLOCK=block,
                                NW=nw, RB=rb, STEPS=steps, HAS_SLOTS=slots is not None, G=fallback, num_warps=4)
    _share_pick_kernel[(triton.cdiv(r, rb),)](sl, cand, p, chosen, ids, w, r, k, NW=nw, RB=rb, num_warps=4,
                                              KP=triton.next_power_of_2(k), NONE=e, REPEAT=repeat, **common)
    return ids, w, lat

```

## Questions for the reviewers
1. Is the measurement sound (workload representativeness: code prompts + C2/C4/C8 only; 1,432 rounds) and is the
   bandwidth-linear benefit estimate credible on an EXL3 trellis kernel (decode can be compute-bound on trellis decode)?
2. Is a lossy MoE budget worth implementing here at all, given the estimated ~6% at C8 for cap 48 and the quality risk?
   If yes, which single configuration should S2 test first, and what quality gate (we have: 30-question greedy bank >= 28/30,
   decode gate, 1h marathon, tool-eval-bench sampled A/B, loop probe)?
3. What should be measured before writing the kernel (e.g. per-layer expert kernel time vs distinct experts) to confirm
   expert reads are the bottleneck?
