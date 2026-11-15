// Offline check of tf_ds_moe_budget_kernel against the Python reference (analyze_expert_union.budget semantics with
// renormalization): reads captured verify rounds (rounds.bin), runs the kernel per layer, compares the kept sets and
// weights. Also times the kernel. Build: nvcc -O3 -arch=sm_121 -o budget_check budget_check.cu
#include <cuda_runtime.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cmath>
#include <vector>
#include <set>
#include <map>
#include <algorithm>
#define main kernel_file_main_unused
#include "dsv41_ops_budget.cuh"
#undef main

struct Round { int R, L, S, nw; std::vector<int> slots; std::vector<int> picks; std::vector<float> wts; };

static bool readRound(FILE* f, Round& r) {
    unsigned h[8];
    if (fread(h, 4, 8, f) != 8) return false;
    if (h[0] != 0x58535431) return false;
    r.R = h[1]; r.L = h[2]; r.S = h[3]; r.nw = h[4];
    r.slots.resize(r.R); r.picks.resize((size_t)r.L * r.R * r.S); r.wts.resize(r.picks.size());
    if (fread(r.slots.data(), 4, r.R, f) != (size_t)r.R) return false;
    if (fread(r.picks.data(), 4, r.picks.size(), f) != r.picks.size()) return false;
    if (fread(r.wts.data(), 4, r.wts.size(), f) != r.wts.size()) return false;
    return true;
}

// reference: keep set = top `keep` slots of every row; fill by summed weight (ties lower id) to cap; renormalize
static void reference(const int* p, const float* w, int R, int S, int topk, int E, int keep, int cap, int minst, int streams,
                      std::vector<int>& op, std::vector<float>& ow) {
    op.assign(p, p + R * S); ow.assign(w, w + R * S);
    std::set<int> present, chosen;
    for (int r = 0; r < R; ++r) for (int q = 0; q < topk; ++q) { int e = p[r * S + q]; if (e >= 0 && e < E) { present.insert(e); if (q < keep) chosen.insert(e); } }
    if (streams < minst || (int)present.size() <= cap) return;
    std::vector<std::pair<float, int>> cand;
    for (int e : present) if (!chosen.count(e)) { float s = 0; for (int i = 0; i < R * S; ++i) if (i % S < topk && p[i] == e) s += w[i]; cand.push_back({s, e}); }
    std::sort(cand.begin(), cand.end(), [](auto a, auto b) { return a.first > b.first || (a.first == b.first && a.second < b.second); });
    int room = cap - (int)chosen.size();
    for (int i = 0; i < room && i < (int)cand.size(); ++i) chosen.insert(cand[i].second);
    for (int r = 0; r < R; ++r) {
        float all = 0, kept = 0;
        for (int q = 0; q < topk; ++q) { int e = p[r * S + q]; if (e < 0 || e >= E) continue; all += w[r * S + q]; if (chosen.count(e)) kept += w[r * S + q]; }
        float f = kept > 0 ? all / kept : 1.f;
        for (int q = 0; q < topk; ++q) { int i = r * S + q, e = p[i]; if (e < 0 || e >= E) continue; if (chosen.count(e)) ow[i] = w[i] * f; else { op[i] = -1; ow[i] = 0; } }
    }
}

int main(int argc, char** argv) {
    const char* path = argc > 1 ? argv[1] : "rounds.bin";
    int keep = argc > 2 ? atoi(argv[2]) : 4, cap = argc > 3 ? atoi(argv[3]) : 48, minst = argc > 4 ? atoi(argv[4]) : 5;
    FILE* f = fopen(path, "rb");
    if (!f) { perror(path); return 2; }
    int *dp; float *dw; long long* ds; cudaMalloc(&dp, 64 * 8 * 4); cudaMalloc(&dw, 64 * 8 * 4); cudaMalloc(&ds, 64 * 8); unsigned long long* dstats; cudaMalloc(&dstats, 64); cudaMemset(dstats, 0, 64);
    cudaEvent_t a, b; cudaEventCreate(&a); cudaEventCreate(&b);
    long calls = 0, changed = 0, pick_mis = 0, wts_bad = 0; double max_rel = 0, ms_tot = 0; long timed = 0;
    Round r;
    while (readRound(f, r)) {
        std::set<int> st(r.slots.begin(), r.slots.end());
        std::vector<long long> sl(r.slots.begin(), r.slots.end());
        cudaMemcpy(ds, sl.data(), r.R * 8, cudaMemcpyHostToDevice);
        for (int li = 0; li < r.L; ++li) {
            const int* p = &r.picks[(size_t)li * r.R * r.S]; const float* w = &r.wts[(size_t)li * r.R * r.S];
            cudaMemcpy(dp, p, r.R * r.S * 4, cudaMemcpyHostToDevice); cudaMemcpy(dw, w, r.R * r.S * 4, cudaMemcpyHostToDevice);
            cudaEventRecord(a);
            tf_ds_moe_budget_kernel<<<1, 512>>>(dp, dw, ds, r.R, r.S, r.S - 1, 384, keep, cap, minst, dstats);
            cudaEventRecord(b); cudaEventSynchronize(b);
            float ms; cudaEventElapsedTime(&ms, a, b); ms_tot += ms; timed++;
            std::vector<int> kp(r.R * r.S); std::vector<float> kw(r.R * r.S);
            cudaMemcpy(kp.data(), dp, r.R * r.S * 4, cudaMemcpyDeviceToHost); cudaMemcpy(kw.data(), dw, r.R * r.S * 4, cudaMemcpyDeviceToHost);
            std::vector<int> rp; std::vector<float> rw;
            reference(p, w, r.R, r.S, r.S - 1, 384, keep, cap, minst, (int)st.size(), rp, rw);
            calls++;
            bool ch = false;
            for (int i = 0; i < r.R * r.S; ++i) {
                if (kp[i] != p[i] || kw[i] != w[i]) ch = true;
                if (kp[i] != rp[i]) pick_mis++;
                double rel = fabs((double)kw[i] - rw[i]) / (fabs(rw[i]) + 1e-12);
                if (rw[i] == 0 ? kw[i] != 0 : rel > 1e-6) wts_bad++;
                if (rw[i] != 0) max_rel = std::max(max_rel, rel);
                if (!std::isfinite(kw[i])) wts_bad++;
            }
            changed += ch;
        }
    }
    unsigned long long hs[8]; cudaMemcpy(hs, dstats, 64, cudaMemcpyDeviceToHost); printf("stats calls %llu fired %llu union %llu->%llu dropped_slots %llu dropped_w %.3f maxf %.4f\n", hs[0], hs[1], hs[3], hs[4], hs[5], hs[6]/1e6, hs[7]/1e6);
    printf("{\"keep\": %d, \"cap\": %d, \"min_streams\": %d, \"calls\": %ld, \"changed\": %ld, \"pick_mismatch\": %ld, \"wts_bad\": %ld, \"max_rel\": %.3g, \"kernel_us_mean\": %.2f}\n",
           keep, cap, minst, calls, changed, pick_mis, wts_bad, max_rel, 1000.0 * ms_tot / timed);
    return pick_mis || wts_bad ? 1 : 0;
}
