// Hibana-style budgeted expert selection for a verify round's MoE (TF_DS_MOE_BUDGET=keep:cap:min_streams), one block.
// pick int32 / wts fp32 [R, slots] as _route wrote them (slots 0..topk-1 routed in descending sc + bias order, the last
// the shared expert). When the round's live streams (distinct values of its rows' pool slots) reach min_streams and its
// routed union exceeds cap: every row keeps its first `keep` slots; the call's experts are then filled up to cap by summed
// routing weight (ties: the lower id); a row's other slots whose expert is read anyway stay; the rest become pick -1,
// weight 0 (not routed: decode_prep skips them, down's counters do not wait for them, and with store_y 0 the combine adds
// 0). Each row's kept routed weights are scaled so their sum is the row's original routed sum. Otherwise nothing is
// written. Every shared flag has one writer (the thread owning expert e scans the window itself); deterministic, both TP
// ranks choose alike. stats (null: none), u64 [8]: calls, triggered, sum streams, sum union before, sum union after,
// sum dropped slots, sum dropped weight (x 1e6, rounded), max rescale (x 1e6).
extern "C" __global__ void __launch_bounds__(512) tf_ds_moe_budget_kernel(int* pick, float* wts, const long long* row_slot,
                                                                          int R, int slots, int topk, int E, int keep,
                                                                          int cap, int min_streams,
                                                                          unsigned long long* stats) {
    __shared__ int sp[64 * 8];
    __shared__ float sw[64 * 8];
    __shared__ unsigned char present[512];
    __shared__ unsigned char guaranteed[512];
    __shared__ unsigned char chosen[512];
    __shared__ float score[512];
    __shared__ int s_streams, s_union, s_guar;
    __shared__ float s_drop_w[64];
    __shared__ float s_f[64];
    __shared__ int s_drop_n[64];
    const int tid = threadIdx.x;
    const int n = R * slots;
    if (R > 64 || slots > 8 || E > 512 || R < 1) return;  // the loader refuses these shapes
    for (int i = tid; i < n; i += blockDim.x) {
        sp[i] = pick[i];
        sw[i] = wts[i];
    }
    if (tid == 0) {
        int st = 0;
        for (int r = 0; r < R; ++r) {
            int seen = 0;
            for (int j = 0; j < r; ++j) seen |= row_slot[j] == row_slot[r];
            st += !seen;
        }
        s_streams = st;
    }
    __syncthreads();
    // expert e's flags and score, written only by the thread owning e (a scan of the window's routed slots)
    for (int e = tid; e < 512; e += blockDim.x) {
        unsigned char pr = 0, gu = 0;
        float sc = 0.f;
        if (e < E)
            for (int i = 0; i < n; ++i) {
                const int q = i % slots;
                if (q < topk && sp[i] == e) {
                    pr = 1;
                    gu |= q < keep;
                    sc += sw[i];
                }
            }
        present[e] = pr;
        guaranteed[e] = gu;
        score[e] = gu ? 0.f : sc;
        chosen[e] = gu;
    }
    __syncthreads();
    if (tid == 0) {
        int u = 0, g = 0;
        for (int e = 0; e < E; ++e) {
            u += present[e];
            g += guaranteed[e];
        }
        s_union = u;
        s_guar = g;
    }
    __syncthreads();
    const bool fire = s_streams >= min_streams && s_union > cap;
    if (fire) {
        const int room = cap - s_guar;
        // rank among the non-guaranteed present experts: reads present / guaranteed / score only, writes chosen[e] (own)
        if (room > 0)
            for (int e = tid; e < E; e += blockDim.x) {
                if (!present[e] || guaranteed[e]) continue;
                const float v = score[e];
                int rank = 0;
                for (int o = 0; o < E; ++o)
                    rank += present[o] && !guaranteed[o] && (score[o] > v || (score[o] == v && o < e));
                chosen[e] = rank < room;
            }
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
            int dn = 0;
            for (int q = 0; q < topk; ++q) {
                const int i = r * slots + q, e = sp[i];
                if (e < 0 || e >= E) continue;
                if (chosen[e]) {
                    wts[i] = sw[i] * f;
                } else {
                    pick[i] = -1;
                    wts[i] = 0.f;
                    ++dn;
                }
            }
            s_drop_w[r] = all > 0.f ? (all - kept) / all : 0.f;
            s_f[r] = f;
            s_drop_n[r] = dn;
        }
    }
    __syncthreads();
    if (stats != nullptr && tid == 0) {
        stats[0] += 1ull;
        stats[2] += (unsigned long long)s_streams;
        stats[3] += (unsigned long long)s_union;
        if (fire) {
            int after = 0;
            for (int e = 0; e < E; ++e) after += chosen[e] && present[e];
            double dw = 0.0, mf = 0.0;
            unsigned long long dn = 0;
            for (int r = 0; r < R; ++r) {
                dw += s_drop_w[r];
                dn += (unsigned long long)s_drop_n[r];
                if (s_f[r] > mf) mf = s_f[r];
            }
            stats[1] += 1ull;
            stats[4] += (unsigned long long)after;
            stats[5] += dn;
            stats[6] += (unsigned long long)(dw * 1e6 + 0.5);
            const unsigned long long mfi = (unsigned long long)(mf * 1e6 + 0.5);
            if (mfi > stats[7]) stats[7] = mfi;
        } else {
            stats[4] += (unsigned long long)s_union;
        }
    }
}

