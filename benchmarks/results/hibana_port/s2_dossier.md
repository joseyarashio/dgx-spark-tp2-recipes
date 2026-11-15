# Hibana port, Stage S2 dossier: budgeted expert selection (keep 4, cap 48, from 5 streams) speed A/B on DeepSeek-V4.1-Flash TP=2

## What changed since the S1 review (your S1 critiques were applied)
- Engine ucount vs dump: over the same first 1,280 rounds the engine counter and the dump agree exactly for every row count
  (e.g. rows 16: 3,560 calls, mean 47.388 incl. shared both ways). The earlier mismatch was the snapshot covering only 1,280 of
  1,432 rounds. Every captured round has nw == live streams, one decode_prep call per layer per round (round-level union is the kernel's unit).
- S2-pre cost measurement (TF_DS_EXPERT_STATS=3, GPU globaltimer before/after exl3_experts.decode, no dumps, 1,280 rounds):
  time per layer-call is linear in ucount: pooled rows>=8 t = 22.8 + 28.60*u us (n=9,760); per row count slopes 26.4-29.9 us,
  no step pattern visible from u=27..69 at rows 16. => ~1.14 ms per round per extra expert over 40 layers (measured, not byte model).
- Grid under CUDA graphs: launched at maxu = min(R*slots, E); programs with ur >= ucount[0] return at once (read in
  experts_grouped.cuh), so cost follows device-side ucount.
- Semantics fixed as Astra proposed: KEEP = first `keep` slots in _route's (sc+bias) selection order; guaranteed set may
  exceed cap (soft cap); fill by summed routing weight, ties by lower id; kept routed weights rescaled so the row's routed
  sum is unchanged (x1.5 preserved); shared slot untouched. Dropped slots become pick -1, weight 0, and when the budget is
  on the decode path sets store_y = 0 for gate/up prep and down combine, so a dropped slot adds exactly 0 (no stale y, no
  NaN path); down's completion counter counts only routed slots (target excludes pick<0), so no maxm growth and no hang.
  No renaming to the row's top expert (avoids maxm overflow and extra FFN rows).
- Gating: only verify rounds (prompt chunks and DSpark drafter untouched), only when distinct pool slots among the round's
  rows >= min_streams and R >= min_streams (R is the graph key, so the launch decision is graph-safe; the kernel re-checks
  streams on device and returns without writing below it).
- TP agreement: env parsed on both ranks; at load the (keep,cap,min_streams) triples are all-gathered over NCCL and the
  engine refuses to start on mismatch. Both ranks logged "moe budget: keep 4, cap 48, from 5 streams".
- Kernel verification: offline replay of 57,240 captured layer-calls through the CUDA kernel vs an independent C++ reference:
  0 pick mismatches, 0 weight mismatches (bitwise), configs 4:48:5, 4:48:1, 5:48:1, 3:32:1, 6:48:1 (no-op, 0 changed),
  4:1000:1 (no-op). Kernel time ~6-10 us per call (one block of 512 threads).
- Off-path identity: with budget off, the new build's 9 greedy sweep outputs (token sha) equal production p17's.

## Kernel
```cuda
// Hibana-style budgeted expert selection for a verify round's MoE (TF_DS_MOE_BUDGET=keep:cap:min_streams), one block.
// pick int32 / wts fp32 [R, slots] as _route wrote them (slots 0..topk-1 routed in selection order, the last the shared
// expert). When the round's live streams (distinct values of its rows' pool slots) reach min_streams and its routed
// union exceeds cap: every row keeps its first `keep` slots; the call's experts are then filled up to cap by summed
// routing weight (ties: the lower id); a row's other slots whose expert is read anyway stay; the rest become pick -1,
// weight 0 (not routed: decode_prep skips them, down's counters do not wait for them, and the combine adds 0 * y). Each
// row's kept routed weights are scaled so their sum is the row's original routed sum. Otherwise nothing is written (the
// round is bit-identical). Deterministic, no atomics on floats: both TP ranks make the same choice.
extern "C" __global__ void __launch_bounds__(512) tf_ds_moe_budget_kernel(int* pick, float* wts, const long long* row_slot,
                                                                          int R, int slots, int topk, int E, int keep,
                                                                          int cap, int min_streams) {
    __shared__ int sp[64 * 8];
    __shared__ float sw[64 * 8];
    __shared__ unsigned char present[512];
    __shared__ unsigned char chosen[512];
    __shared__ float score[512];
    __shared__ int s_union, s_chosen, s_streams;
    const int tid = threadIdx.x;
    const int n = R * slots;
    if (R > 64 || slots > 8 || E > 512) return;
    for (int i = tid; i < n; i += blockDim.x) {
        sp[i] = pick[i];
        sw[i] = wts[i];
    }
    for (int e = tid; e < 512; e += blockDim.x) {
        present[e] = 0;
        chosen[e] = 0;
        score[e] = 0.f;
    }
    if (tid == 0) {
        s_union = 0;
        s_chosen = 0;
        int st = 0;
        for (int r = 0; r < R; ++r) {
            int seen = 0;
            for (int j = 0; j < r; ++j) seen |= row_slot[j] == row_slot[r];
            st += !seen;
        }
        s_streams = st;
    }
    __syncthreads();
    for (int i = tid; i < n; i += blockDim.x) {
        const int q = i % slots, e = sp[i];
        if (q >= topk || e < 0 || e >= E) continue;
        present[e] = 1;
        if (q < keep) chosen[e] = 1;
    }
    __syncthreads();
    for (int e = tid; e < E; e += blockDim.x) {
        if (present[e]) atomicAdd(&s_union, 1);
        if (chosen[e]) atomicAdd(&s_chosen, 1);
    }
    __syncthreads();
    if (s_streams < min_streams || s_union <= cap) return;
    // the other present experts' summed routing weight, rows in order (deterministic)
    for (int e = tid; e < E; e += blockDim.x) {
        if (!present[e] || chosen[e]) continue;
        float s = 0.f;
        for (int i = 0; i < n; ++i)
            if (i % slots < topk && sp[i] == e) s += sw[i];
        score[e] = s;
    }
    __syncthreads();
    // each remaining candidate's rank among the others (higher summed weight first, then the lower id): one pass
    if (tid == 0) s_union = cap - s_chosen;  // the room left (reused)
    __syncthreads();
    const int room = s_union;
    if (room > 0)
        for (int e = tid; e < E; e += blockDim.x) {
            if (!present[e] || chosen[e]) continue;
            const float v = score[e];
            int rank = 0;
            for (int o = 0; o < E; ++o)
                rank += present[o] && !chosen[o] && (score[o] > v || (score[o] == v && o < e));
            present[e] = rank < room ? 2 : 1;
        }
    __syncthreads();
    for (int e = tid; e < E; e += blockDim.x)
        if (present[e] == 2) chosen[e] = 1;
    __syncthreads();
    for (int r = tid; r < R; r += blockDim.x) {
        float all = 0.f, kept = 0.f;
        for (int q = 0; q < topk; ++q) {
            const int e = sp[r * slots + q];
            if (e < 0 || e >= E) continue;
            all += sw[r * slots + q];
            if (chosen[e]) kept += sw[r * slots + q];
        }
        const float f = kept > 0.f ? all / kept : 1.f;
        for (int q = 0; q < topk; ++q) {
            const int i = r * slots + q, e = sp[i];
            if (e < 0 || e >= E) continue;
            if (chosen[e]) {
                wts[i] = sw[i] * f;
            } else {
                pick[i] = -1;
                wts[i] = 0.f;
            }
        }
    }
}

// torch's keys.topk(k, sorted=False).values for the indexer's int64 keys, a row a block (1024 threads): the k largest

```

## Engine diff (zig/src; includes the S1/S2-pre measurement hooks, which are env-gated and off in the A/B)
```diff
diff --git a/zig/src/families/dsv41/exl3_experts.zig b/zig/src/families/dsv41/exl3_experts.zig
index 57814157..2b10fa53 100644
--- a/zig/src/families/dsv41/exl3_experts.zig
+++ b/zig/src/families/dsv41/exl3_experts.zig
@@ -23,6 +23,9 @@ pub const rows_rows_d = 32; // work list rows of grouped_rows: 16 * PROMPT_TILES
 pub const act_f32 = 1; // ACT_F32
 pub const prep_threads = 256; // experts.cu PREP_THREADS
 pub const decode_stages = 3; // DECODE_STAGES: each warp's ring of trellis copies in grouped_cp_kernel (its S)
+/// TF_DS_MOE_BUDGET on: a decode slot that is not routed (the budget's dropped slots, pick -1) adds 0, not the stale y it
+/// finds (store_y 0). Off (the served default) every decode slot is routed, so store_y never matters.
+pub var routed_only_y: bool = false;
 
 /// A K2 range's template: (8, 8), (2, 10) or (2, 16), as every grouped launcher picks it.
 pub fn range(lo: u32, hi: u32) usize {
@@ -393,7 +396,7 @@ pub fn decodeLaunches(ex: weights.Experts, sc: DecodeScratch, x: u64, x_stride:
     for ([_]u64{ sc.ids, sc.count, sc.members }) |v| prep.add(v);
     i32a(&prep, r); // maxm: the member lists' stride
     for ([_]u64{ wts, sc.y, 0, out }) |v| prep.add(v); // no add
-    for ([_]usize{ d, 1 }) |v| i32a(&prep, v); // store_y: a slot that is not routed adds the y it finds
+    for ([_]usize{ d, @intFromBool(!routed_only_y) }) |v| i32a(&prep, v); // store_y: a slot that is not routed adds the y it finds
     prep.add(sc.epoch);
     const prep_warps = prep_threads / 32;
     const blocks = 1 + (p * (d / 128) * 2 + prep_warps - 1) / prep_warps;
@@ -414,7 +417,7 @@ pub fn decodeLaunches(ex: weights.Experts, sc: DecodeScratch, x: u64, x_stride:
     var dn: cuda.Args = .{};
     for ([_]u64{ sc.xd, sc.xd, ex.down_ptr, ex.down_ptr, ex.down_k2, ex.down_k2, sc.ids, sc.count, sc.members, sc.z }) |v| dn.add(v);
     for ([_]usize{ i, d, p, 1, r, slots }) |v| i32a(&dn, v);
-    dn.add(DecodeEpi{ .pick = pick, .E = @intCast(e), .svh_d = ex.svh_d, .y = sc.y, .wts = wts, .out = out, .cnt = sc.cnt_d, .ready = sc.ready, .ready_cnt = sc.ready_cnt, .epoch = sc.epoch, .discard = @intFromBool(4 * slots <= 32) });
+    dn.add(DecodeEpi{ .pick = pick, .E = @intCast(e), .svh_d = ex.svh_d, .y = sc.y, .wts = wts, .out = out, .store_y = @intFromBool(!routed_only_y), .cnt = sc.cnt_d, .ready = sc.ready, .ready_cnt = sc.ready_cnt, .epoch = sc.epoch, .discard = @intFromBool(4 * slots <= 32) });
 
     return .{
         .{ .kernel = .prep, .cfg = .{ .grid = .{ .x = @intCast(blocks) }, .block = .{ .x = prep_threads }, .shared = @intCast(2 * p * 4) }, .args = prep },
diff --git a/zig/src/families/dsv41/model.zig b/zig/src/families/dsv41/model.zig
index 514868a9..292748fb 100644
--- a/zig/src/families/dsv41/model.zig
+++ b/zig/src/families/dsv41/model.zig
@@ -142,6 +142,14 @@ pub const Model = struct {
     clk_rounds: u64 = 0,
     t_forward: u64 = 0,
     t_absorb: u64 = 0,
+    // TF_DS_EXPERT_STATS (a measurement, rank 0): 1 = each decode window's distinct experts by row count, 2 = also
+    // every verify round's picks and weights appended to a file (capped); mapped host memory the kernels write
+    xs_host: ?cuda.HostBuffer = null,
+    xd_host: ?cuda.HostBuffer = null,
+    xt_host: ?cuda.HostBuffer = null,
+    xs_fd: c_int = -1,
+    xs_rounds: u64 = 0,
+    xs_dumped: u64 = 0,
     // world 4: the 2D split's exchanges (prompt2d.zig, TP4's), with the RDMA rings when asked
     two: ?prompt2d.Two = null,
     rdma_rings: ?ring2d.Rings = null,
@@ -194,6 +202,12 @@ pub const Model = struct {
         m.pgraphs = null;
         m.two = null;
         m.rdma_rings = null;
+        m.xs_host = null;
+        m.xd_host = null;
+        m.xt_host = null;
+        m.xs_fd = -1;
+        m.xs_rounds = 0;
+        m.xs_dumped = 0;
         const d = ctx.d;
         m.cfg = try Config.read(a, io, o.model_dir);
         const c = &m.cfg;
@@ -299,6 +313,60 @@ pub const Model = struct {
         }
         m.rd = try round.Round.init(&m.eng, &m.arena, a, o.pool);
         m.amax = try m.arena.take(round.max_rows * 4);
+        if (std.c.getenv("TF_DS_MOE_BUDGET")) |v| {
+            // keep:cap:min_streams, the same on every rank (checked below); verify rounds only
+            var it = std.mem.splitScalar(u8, std.mem.span(v), ':');
+            const keep = std.fmt.parseInt(u32, it.next() orelse "", 10) catch return error.BadMoeBudget;
+            const cap = std.fmt.parseInt(u32, it.next() orelse "", 10) catch return error.BadMoeBudget;
+            const min_streams = std.fmt.parseInt(u32, it.next() orelse "1", 10) catch return error.BadMoeBudget;
+            if (keep == 0 or keep > c.top_k or cap == 0) return error.BadMoeBudget;
+            if (m.ops.moe_budget == null) return error.MissingKernel;
+            m.rd.moe_keep = keep;
+            m.rd.moe_cap = cap;
+            m.rd.moe_min_streams = min_streams;
+            exl3_experts.routed_only_y = true;
+        }
+        {
+            // every rank must route alike: the settings gathered over NCCL and compared
+            const mine = [4]i32{ @intCast(m.rd.moe_keep), @intCast(m.rd.moe_cap), @intCast(m.rd.moe_min_streams), 0x4d4f4542 };
+            const sbuf = try m.arena.take(16);
+            const rbuf = try m.arena.take(16 * @as(usize, o.world));
+            try d.check(d.api.cuMemcpyHtoDAsync_v2(sbuf, &mine, 16, m.stream.handle), "cuMemcpyHtoDAsync");
+            try m.comm.allGather(sbuf, rbuf, 4, .i32, m.stream);
+            try m.stream.synchronize();
+            var all: [16]i32 = undefined;
+            try d.check(d.api.cuMemcpyDtoH_v2(&all, rbuf, 16 * @as(usize, o.world)), "cuMemcpyDtoH");
+            for (0..o.world) |r| if (!std.mem.eql(i32, all[4 * r ..][0..4], &mine)) {
+                std.log.err("TF_DS_MOE_BUDGET differs between ranks: rank {d} has {any}, this rank {any}", .{ r, all[4 * r ..][0..4], mine });
+                return error.MoeBudgetMismatch;
+            };
+            if (m.rd.moe_cap != 0) std.log.info("moe budget: keep {d}, cap {d}, from {d} streams (rank {d}; verify rounds only)", .{ m.rd.moe_keep, m.rd.moe_cap, m.rd.moe_min_streams, o.rank });
+        }
+        if (std.c.getenv("TF_DS_EXPERT_STATS")) |v| {
+            const mode = std.fmt.parseInt(u8, std.mem.span(v), 10) catch 0;
+            if (mode >= 1 and o.rank == 0 and m.ops.ucount_acc != null) {
+                const hb = try cuda.HostBuffer.allocMapped(d, (round.max_rows + 1) * 3 * 8);
+                @memset(hb.bytes, 0);
+                m.xs_host = hb;
+                m.rd.xstats = try hb.device();
+                if (mode == 3) {
+                    // timing alone (no dump, so the copies do not skew it): GPU time of the experts by rows and ucount
+                    const ht = try cuda.HostBuffer.allocMapped(d, (1 + (round.max_rows + 1) * 128 * 2) * 8);
+                    @memset(ht.bytes, 0);
+                    m.xt_host = ht;
+                    m.rd.xtime = try ht.device();
+                } else if (mode >= 2) {
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
@@ -820,6 +888,63 @@ pub const Model = struct {
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
+        var out: [131072]u8 = undefined;
+        var w: std.Io.Writer = .fixed(&out);
+        w.print("{{\"rounds\": {d}, \"by_rows\": {{", .{m.xs_rounds}) catch return;
+        var first = true;
+        for (0..round.max_rows + 1) |r| {
+            if (st[3 * r] == 0) continue;
+            w.print("{s}\"{d}\": [{d}, {d}, {d}]", .{ if (first) "" else ", ", r, st[3 * r], st[3 * r + 1], st[3 * r + 2] }) catch return;
+            first = false;
+        }
+        w.print("}}", .{}) catch return;
+        if (m.xt_host) |ht| {
+            const tt = std.mem.bytesAsSlice(u64, ht.bytes);
+            w.print(", \"xtime\": [", .{}) catch return;
+            var f2 = true;
+            for (0..round.max_rows + 1) |r| for (0..128) |u| {
+                const o = 1 + (r * 128 + u) * 2;
+                if (tt[o] == 0) continue;
+                w.print("{s}[{d}, {d}, {d}, {d}]", .{ if (f2) "" else ", ", r, u, tt[o], tt[o + 1] }) catch return;
+                f2 = false;
+            };
+            w.print("]", .{}) catch return;
+        }
+        w.print("}}\n", .{}) catch return;
+        const fd = std.c.open("/home/joseyarashio/.cache/dsv41-expert-stats/stats.json.part", .{ .ACCMODE = .WRONLY, .CREAT = true, .TRUNC = true }, @as(std.c.mode_t, 0o644));
+        if (fd < 0) return;
+        _ = std.c.write(fd, w.buffered().ptr, w.buffered().len);
+        _ = std.c.close(fd);
+        _ = std.c.rename("/home/joseyarashio/.cache/dsv41-expert-stats/stats.json.part", "/home/joseyarashio/.cache/dsv41-expert-stats/stats.json");
     }
 
     /// The rounds' GPU clocks (a profile): the forward's start and each stretch's ends, for its gaps.
diff --git a/zig/src/families/dsv41/ops.zig b/zig/src/families/dsv41/ops.zig
index a82baee0..38e510e0 100644
--- a/zig/src/families/dsv41/ops.zig
+++ b/zig/src/families/dsv41/ops.zig
@@ -37,6 +37,10 @@ pub const Ops = struct {
     copy16: cuda.Function,
     argmax_rows: cuda.Function,
     gpu_clock: cuda.Function,
+    ucount_acc: ?cuda.Function = null, // TF_DS_EXPERT_STATS (absent from older images)
+    xtime_begin: ?cuda.Function = null,
+    xtime_end: ?cuda.Function = null,
+    moe_budget: ?cuda.Function = null, // TF_DS_MOE_BUDGET
 
     /// The three images (cuda.kernels.torch_pointwise, torch_movement and dsv41_ops, or the fatbins' bytes).
     pub fn load(d: *const cuda.Driver, pointwise: []const u8, movement: []const u8, family: []const u8) !Ops {
@@ -68,6 +72,10 @@ pub const Ops = struct {
             .copy16 = try fm.function("tf_ds_copy_rows16_kernel"),
             .argmax_rows = try fm.function("tf_ds_argmax_rows_kernel"),
             .gpu_clock = try fm.function("tf_ds_clock_kernel"),
+            .ucount_acc = fm.function("tf_ds_ucount_acc_kernel") catch null,
+            .xtime_begin = fm.function("tf_ds_xtime_begin_kernel") catch null,
+            .xtime_end = fm.function("tf_ds_xtime_end_kernel") catch null,
+            .moe_budget = fm.function("tf_ds_moe_budget_kernel") catch null,
         };
     }
 
@@ -302,6 +310,47 @@ pub const Ops = struct {
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
+    /// Budgeted expert selection of a verify round (dsv41_ops.cu tf_ds_moe_budget_kernel): pick / wts [rows, slots] in place.
+    pub fn moeBudget(o: *const Ops, s: cuda.Stream, pick: u64, wts: u64, row_slot: u64, rows: usize, slots: usize, topk: usize, experts: usize, keep: u32, cap: u32, min_streams: u32) !void {
+        const f = o.moe_budget orelse return error.MissingKernel;
+        var a: cuda.Args = .{};
+        a.add(pick);
+        a.add(wts);
+        a.add(row_slot);
+        for ([_]usize{ rows, slots, topk, experts }) |v| a.add(@as(c_int, @intCast(v)));
+        for ([_]u32{ keep, cap, min_streams }) |v| a.add(@as(c_int, @intCast(v)));
+        try go(f, s, 1, 512, &a);
+    }
+
+    /// A measurement: the GPU clock into t0 (before a decode window's experts).
+    pub fn xtimeBegin(o: *const Ops, s: cuda.Stream, t0: u64) !void {
+        const f = o.xtime_begin orelse return error.MissingKernel;
+        var a: cuda.Args = .{};
+        a.add(t0);
+        try go(f, s, 1, 32, &a);
+    }
+
+    /// A measurement: hist[rows][ucount] += (1, now - t0) (after a decode window's experts).
+    pub fn xtimeEnd(o: *const Ops, s: cuda.Stream, ucount: u64, t0: u64, hist: u64, rows: usize) !void {
+        const f = o.xtime_end orelse return error.MissingKernel;
+        var a: cuda.Args = .{};
+        a.add(ucount);
+        a.add(t0);
+        a.add(hist);
+        a.add(@as(c_int, @intCast(rows)));
+        try go(f, s, 1, 32, &a);
+    }
+
     /// dst row i = src row idx[i] (int64 indices, rows of `bytes` bytes); an index outside [0, src_rows) sets the
     /// caller's zeroed uint32 flag `invalid` and leaves that row as it was.
     pub fn gatherRows(o: *const Ops, s: cuda.Stream, src: u64, src_rows: usize, idx: u64, dst: u64, bytes: usize, rows: usize, invalid: u64) !void {
diff --git a/zig/src/families/dsv41/round.zig b/zig/src/families/dsv41/round.zig
index 104053a0..ad4658a8 100644
--- a/zig/src/families/dsv41/round.zig
+++ b/zig/src/families/dsv41/round.zig
@@ -197,6 +197,16 @@ pub const Round = struct {
     clk_marks: bool = false,
     clk_ratio: ?u8 = null, // phase clocks only in the layers of this compress ratio (TF_DS_CLOCK_MARKS=3: ratio 2)
     cur_ratio: u8 = 0, // the layer a stretch is on (its compress ratio) // clocks at every phase mark too (Model.useClock(true)), not only around the stretches
+    // TF_DS_EXPERT_STATS (a measurement, model.zig): per row count (calls, sum, sum^2) of the decode windows' distinct
+    // experts, u64 [max_rows + 1][3]; and each layer's picks and weights, [2][layers][max_rows][slots] (0: off)
+    xstats: u64 = 0,
+    xdump: u64 = 0,
+    xdump_half: usize = 0,
+    // TF_DS_MOE_BUDGET=keep:cap:min_streams (model.zig): the verify rounds' budgeted expert selection (cap 0: off)
+    moe_keep: u32 = 0,
+    moe_cap: u32 = 0,
+    moe_min_streams: u32 = 0,
+    xtime: u64 = 0, // TF_DS_EXPERT_STATS=3: u64 [1 + (max_rows + 1) * 128 * 2]: t0, then (count, ns) by rows, ucount
     clk: u64 = 0, // [1 + 2 * max_clocks] u64: the count, then each clock and its phase (PhaseTimer.Phase or clock_*)
 
     pub fn init(e: *const Engine, a: *prompt.Arena, gpa: std.mem.Allocator, pool_cap: usize) !Round {
@@ -220,6 +230,13 @@ pub const Round = struct {
         rd.clk_ratio = null;
         rd.cur_ratio = 0;
         rd.clk = 0;
+        rd.xstats = 0;
+        rd.xdump = 0;
+        rd.xdump_half = 0;
+        rd.xtime = 0;
+        rd.moe_keep = 0;
+        rd.moe_cap = 0;
+        rd.moe_min_streams = 0;
         rd.bucket = 0;
         rd.has_cand = false;
         rd.kk = 0;
@@ -738,7 +755,11 @@ fn moe(e: *const Engine, rd: *Round, ch: *const Chunk, li: usize) !void {
     const sl = e.slots();
     const kc = try tri_norm.rowmmGate(e.t, rd.x, c.hidden, lay.gate_w, rd.gl, R, c.hidden, c.experts);
     try tri_norm.route(e.t, rd.gl, kc, lay.gate_b, c.top_k, c.routed_scaling, lay.experts.count - 1, rd.pick, rd.mw, R, c.experts, sl);
+    // the rows' pool slots: RoundDecoder.inputs' third row (setGlue)
+    // R is a graph key, so skipping rounds too small to hold min_streams streams is graph-safe (one row a stream at least)
+    if (rd.moe_cap != 0 and R >= rd.moe_min_streams) try e.ops.moeBudget(e.s, rd.pick, rd.mw, rd.inputs + 2 * R * 8, R, sl, c.top_k, c.experts, rd.moe_keep, rd.moe_cap, rd.moe_min_streams);
     try rd.mark(e, .m_rt);
+    if (rd.xtime != 0) try e.ops.xtimeBegin(e.s, rd.xtime);
     if (e.two) |tw| {
         // 2D (round2d.experts, the profile's marks between): gate / up, the intermediate's exchange, down
         try exl3_experts2d.decodeGateUp(e.ex, e.s, lay.experts, ch.xsd, rd.x, c.hidden, rd.pick, rd.mw, rd.pm, R, c.swiglu_limit);
@@ -747,6 +768,14 @@ fn moe(e: *const Engine, rd: *Round, ch: *const Chunk, li: usize) !void {
         try rd.mark(e, .m_x);
         try exl3_experts2d.decodeDown(e.ex, e.s, lay.experts, ch.xsd, tw.xd_full, rd.pick, rd.mw, rd.pm, R);
     } else try exl3_experts.decode(e.ex, e.s, lay.experts, ch.xsd, rd.x, c.hidden, rd.pick, rd.mw, rd.pm, R, c.swiglu_limit);
+    if (rd.xtime != 0) try e.ops.xtimeEnd(e.s, ch.xsd.count, rd.xtime, rd.xtime + 8, R);
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

## S2 speed A/B (ABAB, same binaries both arms on both ranks, only env differs, restart per arm)
- A = budget off, B = TF_DS_MOE_BUDGET=4:48:5. Each arm: run_decode_gate.py --reps 2 (9 code prompts greedy single
  stream x 384 tokens, then C2/C4/C8 ladder x2 with distinct prompts, via proxy 8889, idle-window waits, external POSTs logged).
- Summary lines:
A1: A1 {"verdict": "pass", "sweep_prompts_clean": 9, "sweep_greedy_tps": 87.88, "sweep_mtp_accept": 0.7309, "sweep_greedy_min": 78.67, "sweep_greedy_max": 95.93, "c2_agg": 112.32, "c2_streams_ok": true, "c4_agg": 144.87, "c4_streams_ok": true, "c8_agg": 158.51, "c8_s
B1 {"verdict": "pass", "sweep_prompts_clean": 9, "sweep_greedy_tps": 87.47, "sweep_mtp_accept": 0.7309, "sweep_greedy_min": 78.59, "sweep_greedy_max": 95.14, "c2_agg": 113.99, "c2_streams_ok": true, "c4_agg": 145.27, "c4_streams_ok": true, "c8_agg": 168.09, "c8_s
A2 {"verdict": "pass", "sweep_prompts_clean": 9, "sweep_greedy_tps": 87.32, "sweep_mtp_accept": 0.7309, "sweep_greedy_min": 78.46, "sweep_greedy_max": 95.17, "c2_agg": 113.61, "c2_streams_ok": true, "c4_agg": 144.1, "c4_streams_ok": true, "c8_agg": 157.95, "c8_st
B2 {"verdict": "pass", "sweep_prompts_clean": 9, "sweep_greedy_tps": 86.97, "sweep_mtp_accept": 0.7309, "sweep_greedy_min": 78.29, "sweep_greedy_max": 94.7, "c2_agg": 114.24, "c2_streams_ok": true, "c4_agg": 142.94, "c4_streams_ok": true, "c8_agg": 168.18, "c8_st
restored: 10d41f91174b005e
DONE

- Per-sample ladder (agg tok/s, rep, external count):
### A1
```
sweep 0 0 90.5 279/374 ext 0
sweep 0 1 94.2 284/373 ext 0
sweep 0 2 84.4 268/381 ext 0
sweep 0 3 87.4 274/380 ext 0
sweep 0 4 89.8 277/379 ext 0
sweep 0 5 96.0 287/358 ext 0
sweep 0 6 83.8 270/397 ext 0
sweep 0 7 87.9 275/372 ext 0
sweep 0 8 78.7 260/404 ext 0
sweep 1 0 90.9 279/377 ext 0
sweep 1 1 94.1 284/373 ext 0
sweep 1 2 84.4 268/381 ext 0
sweep 1 3 87.0 274/380 ext 0
sweep 1 4 89.2 277/379 ext 0
sweep 1 5 95.9 287/358 ext 0
sweep 1 6 84.1 270/397 ext 0
sweep 1 7 87.9 275/372 ext 0
sweep 1 8 78.6 260/404 ext 0
c2 0 112.9 2/2 streams ok ext 0
c4 0 142.6 4/4 streams ok ext 0
c8 0 158.3 8/8 streams ok ext 0
c2 1 111.7 2/2 streams ok ext 0
c4 1 147.2 4/4 streams ok ext 0
c8 1 158.8 8/8 streams ok ext 0
{"verdict": "pass", "sweep_prompts_clean": 9, "sweep_greedy_tps": 87.88, "sweep_mtp_accept": 0.7309, "sweep_greedy_min": 78.67, "sweep_greedy_max": 95.93, "c2_agg": 112.32, "c2_streams_ok": true, "c4_agg": 144.87, "c4_streams_ok": true, "c8_agg": 158.51, "c8_streams_ok": true, "checks": {"sweep_greedy_tps": {"value": 87.88, "need": 83.695, "baseline": 88.1, "ok": true}, "sweep_mtp_accept": {"value": 0.7309, "need": 0.6944, "baseline": 0.7309, "ok": true}, "c2_agg": {"value": 112.32, "need": 111.454, "baseline": 117.32, "ok": true}, "c4_agg": {"value": 144.87, "need": 136.2585, "baseline": 143.43, "ok": true}, "c8_agg": {"value": 158.51, "need": 149.207, "baseline": 157.06, "ok": true}}}

```
### B1
```
sweep 0 0 90.8 279/374 ext 0
sweep 0 1 94.3 284/373 ext 0
sweep 0 2 82.9 268/382 ext 0
sweep 0 3 86.6 274/380 ext 0
sweep 0 4 87.9 277/379 ext 0
sweep 0 5 95.1 287/358 ext 0
sweep 0 6 83.5 270/397 ext 0
sweep 0 7 87.8 275/372 ext 0
sweep 0 8 78.8 260/404 ext 0
sweep 1 0 90.6 279/377 ext 0
sweep 1 1 93.5 284/373 ext 0
sweep 1 2 84.3 268/381 ext 0
sweep 1 3 86.8 274/380 ext 0
sweep 1 4 89.0 277/379 ext 0
sweep 1 5 95.2 287/358 ext 0
sweep 1 6 82.9 270/397 ext 0
sweep 1 7 87.2 275/372 ext 0
sweep 1 8 78.4 260/404 ext 0
c2 0 115.6 2/2 streams ok ext 0
c4 0 145.0 4/4 streams ok ext 0
c8 0 166.9 8/8 streams ok ext 0
c2 1 112.3 2/2 streams ok ext 0
c4 1 145.6 4/4 streams ok ext 0
c8 1 169.3 8/8 streams ok ext 0
{"verdict": "pass", "sweep_prompts_clean": 9, "sweep_greedy_tps": 87.47, "sweep_mtp_accept": 0.7309, "sweep_greedy_min": 78.59, "sweep_greedy_max": 95.14, "c2_agg": 113.99, "c2_streams_ok": true, "c4_agg": 145.27, "c4_streams_ok": true, "c8_agg": 168.09, "c8_streams_ok": true, "checks": {"sweep_greedy_tps": {"value": 87.47, "need": 83.695, "baseline": 88.1, "ok": true}, "sweep_mtp_accept": {"value": 0.7309, "need": 0.6944, "baseline": 0.7309, "ok": true}, "c2_agg": {"value": 113.99, "need": 111.454, "baseline": 117.32, "ok": true}, "c4_agg": {"value": 145.27, "need": 136.2585, "baseline": 143.43, "ok": true}, "c8_agg": {"value": 168.09, "need": 149.207, "baseline": 157.06, "ok": true}}}

```
### A2
```
sweep 0 0 90.7 279/374 ext 0
sweep 0 1 93.8 284/373 ext 0
sweep 0 2 84.4 268/381 ext 0
sweep 0 3 86.8 274/380 ext 0
sweep 0 4 89.1 277/379 ext 0
sweep 0 5 95.5 287/358 ext 0
sweep 0 6 83.7 270/397 ext 0
sweep 0 7 87.3 275/372 ext 0
sweep 0 8 78.4 260/404 ext 0
sweep 1 0 90.5 279/377 ext 0
sweep 1 1 93.8 284/373 ext 0
sweep 1 2 84.0 268/381 ext 0
sweep 1 3 86.8 274/380 ext 0
sweep 1 4 89.1 277/379 ext 0
sweep 1 5 94.8 287/358 ext 0
sweep 1 6 83.4 270/397 ext 0
sweep 1 7 87.3 275/372 ext 0
sweep 1 8 78.5 260/404 ext 0
c2 0 110.3 2/2 streams ok ext 0
c4 0 144.1 4/4 streams ok ext 0
c8 0 156.8 8/8 streams ok ext 0
c2 1 116.9 2/2 streams ok ext 0
c4 1 134.0 4/4 streams ok ext 1
c8 1 159.1 8/8 streams ok ext 0
{"verdict": "pass", "sweep_prompts_clean": 9, "sweep_greedy_tps": 87.32, "sweep_mtp_accept": 0.7309, "sweep_greedy_min": 78.46, "sweep_greedy_max": 95.17, "c2_agg": 113.61, "c2_streams_ok": true, "c4_agg": 144.1, "c4_streams_ok": true, "c8_agg": 157.95, "c8_streams_ok": true, "checks": {"sweep_greedy_tps": {"value": 87.32, "need": 83.695, "baseline": 88.1, "ok": true}, "sweep_mtp_accept": {"value": 0.7309, "need": 0.6944, "baseline": 0.7309, "ok": true}, "c2_agg": {"value": 113.61, "need": 111.454, "baseline": 117.32, "ok": true}, "c4_agg": {"value": 144.1, "need": 136.2585, "baseline": 143.43, "ok": true}, "c8_agg": {"value": 157.95, "need": 149.207, "baseline": 157.06, "ok": true}}}

```
### B2
```
sweep 0 0 90.6 279/374 ext 0
sweep 0 1 93.7 284/373 ext 0
sweep 0 2 84.3 268/381 ext 0
sweep 0 3 87.2 274/380 ext 0
sweep 0 4 88.9 277/379 ext 0
sweep 0 5 95.7 287/358 ext 0
sweep 0 6 83.2 270/397 ext 0
sweep 0 7 86.1 275/373 ext 0
sweep 0 8 78.2 260/404 ext 0
sweep 1 0 90.5 279/377 ext 0
sweep 1 1 93.8 284/373 ext 0
sweep 1 2 84.2 268/381 ext 0
sweep 1 3 86.8 274/380 ext 0
sweep 1 4 89.0 277/379 ext 0
sweep 1 5 93.7 287/358 ext 0
sweep 1 6 83.3 270/397 ext 0
sweep 1 7 86.9 275/372 ext 0
sweep 1 8 78.4 260/404 ext 0
c2 0 112.7 2/2 streams ok ext 0
c4 0 141.8 4/4 streams ok ext 0
c8 0 167.0 8/8 streams ok ext 0
c2 1 115.8 2/2 streams ok ext 0
c4 1 144.1 4/4 streams ok ext 0
c8 1 169.4 8/8 streams ok ext 0
{"verdict": "pass", "sweep_prompts_clean": 9, "sweep_greedy_tps": 86.97, "sweep_mtp_accept": 0.7309, "sweep_greedy_min": 78.29, "sweep_greedy_max": 94.7, "c2_agg": 114.24, "c2_streams_ok": true, "c4_agg": 142.94, "c4_streams_ok": true, "c8_agg": 168.18, "c8_streams_ok": true, "checks": {"sweep_greedy_tps": {"value": 86.97, "need": 83.695, "baseline": 88.1, "ok": true}, "sweep_mtp_accept": {"value": 0.7309, "need": 0.6944, "baseline": 0.7309, "ok": true}, "c2_agg": {"value": 114.24, "need": 111.454, "baseline": 117.32, "ok": true}, "c4_agg": {"value": 142.94, "need": 136.2585, "baseline": 143.43, "ok": true}, "c8_agg": {"value": 168.18, "need": 149.207, "baseline": 157.06, "ok": true}}}

```

### Computed
- C8 aggregate: A = 158.3, 158.8, 156.8, 159.1 (mean 158.25, sd 1.02); B = 166.9, 169.3, 167.0, 169.4 (mean 168.15, sd 1.39);
  delta +9.9 tok/s = +6.26%; ranges do not overlap; both B arms above both A arms in both reps.
- Predicted from S1+S2-pre: cap 48 at 5-8 streams removes ~5.8 routed experts per call => ~6.6 ms of an ~84 ms 16-row round
  (~7.8%) minus kernel cost 40 x ~8 us = 0.3 ms => ~7.5% round time upper bound; observed +6.3% throughput.
- Single stream sweep: token sha identical to production in all 4 arms (gate never fires below 5 streams), greedy medians
  87.88 / 87.47 / 87.32 / 86.97 (noise). C2 112.3/114.0/113.6/114.2, C4 144.9/145.3/144.1/142.9 (budget inactive there).
- MTP acceptance at C8 is NOT reported by the gate (only single-stream sweep acceptance, unchanged 0.7309 because inactive).
- One A2 C4 sample had 1 external request (ext 1, 134.0); excluded-by-design consideration.
- After the A/B the production binaries/scripts were restored and hash-verified on both nodes.

## Not yet measured (planned S3 quality stage)
- Output divergence and quality under C8 concurrency (only place the budget is active). Engine exposes no teacher-forced
  logits API; available tools: greedy outputs with seed, the 30-question bank (temp 0, seed 42), tool-eval-bench sampled A/B,
  loop probe, 1h marathon, run_full_eval.py, run_omni_eval.py. MTP acceptance at C8 can be read from /metrics deltas
  (mtp_drafted_total / mtp_accepted_total) per arm.
- Batch invariance is lost when active: a request's output depends on co-scheduled requests (only at >=5 live streams).

## Your previous S1 review (for continuity)
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
   analyzer 先保留所有 rows 的 

## Questions
1. Is +6.26% at C8 (n=4 runs per arm, ABAB) credible and sufficient to proceed to a quality stage? Any confounder left?
2. Design the S3 quality gate concretely with what we have (no teacher forcing): which paired A/B under forced C8
   concurrency (e.g. 30-question bank run as 8 concurrent copies so the budget binds; per-item paired comparison;
   /metrics MTP acceptance delta at C8; long-reasoning items), what sample sizes, what pass thresholds, and what to do
   about the statistical power limit. Keep it feasible within ~3 hours of GPU time.
3. Any remaining correctness risk in the kernel/integration as written?
