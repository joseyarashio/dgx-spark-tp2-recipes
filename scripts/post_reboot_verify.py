#!/usr/bin/env python3
"""Post-reboot self-verification for the DGX Spark TP=2 DeepSeek serving pair.

Usage:
  post_reboot_verify.py arm      record baseline (boot ids, expected hashes) and arm the boot-time check
  post_reboot_verify.py run      run all checks (boot service calls this when armed); writes a report
  post_reboot_verify.py dry-run  run all checks now without requiring a reboot (for testing)

The boot-time unit spark-post-reboot-verify.timer starts `run` 2 min after boot only when the arm marker exists.
The report is written to STATE/deliver.md; the Hermes cron job spark-reboot-report posts it to Slack once.
"""
import hashlib, json, os, re, subprocess, sys, time, urllib.request

HOME = "/home/joseyarashio"
REPO = f"{HOME}/dgx-spark-tp2-recipes"
STATE = f"{HOME}/.cache/spark-reboot-verify"
ARM = f"{STATE}/armed.json"
N2 = "10.100.184.1"
ENGINE = f"{HOME}/TensorFold-dsv41-zig"
LOGS = f"{HOME}/.cache/dsv41-1017-logs"
# Decode is judged by benchmarks/run_decode_gate.py (9-prompt code sweep median + C2/C4/C8 vs the stored
# baseline in benchmarks/gates/decode_gate_baseline.json). A single prompt's greedy tok/s / MTP follow that
# prompt's text (the LRU prompt moved 95 -> 91 tok/s after the Engram token-map fix while pooled MTP rose).
TOKEN_MAP = f"{HOME}/.cache/dsv41-1017-rank-cache/dsv41_token_map.json"
KIT = f"{HOME}/dsv41-2m-kit"
HEALTH_WAIT_S = 25 * 60


def sh(cmd, timeout=60):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout + r.stderr).strip()
    except subprocess.TimeoutExpired:
        return 124, "timeout"


def n2(cmd, timeout=60):
    return sh(f"ssh -o BatchMode=yes -o ConnectTimeout=10 {N2} {json.dumps(cmd)}", timeout)


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def http(url, timeout=5):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status, r.read().decode()
    except Exception as e:
        return 0, str(e)


def boot_ids():
    b1 = open("/proc/sys/kernel/random/boot_id").read().strip()
    _, b2 = n2("cat /proc/sys/kernel/random/boot_id")
    return b1, b2.strip()


def arm():
    os.makedirs(STATE, exist_ok=True)
    m = json.load(open(f"{REPO}/deployments/manifest.json"))
    b1, b2 = boot_ids()
    _, fat2 = n2(f"cd {ENGINE}/fatbins && cat *.fatbin | sha256sum")
    base = {
        "armed_at": time.strftime("%F %T %z"),
        "boot_id_node1": b1, "boot_id_node2": b2,
        "expect": {
            "native_sha256": m["engine_binaries"]["rank0_tensorfold_native_sha256"],
            "lanes_sha256": m["engine_binaries"]["rank1_tf_dsv41_lanes_sha256"],
            "rank0_sh": sha(f"{LOGS}/rank0.sh"), "rank1_sh": sha(f"{LOGS}/rank1.sh"),
            "start_sh": sha(f"{HOME}/start-dsv41.sh"),
            "fatbins_concat": fat2.split()[0] if fat2 else None,
        },
    }
    json.dump(base, open(ARM, "w"), indent=2)
    print(json.dumps(base, indent=2))


def run(require_reboot=True):
    os.makedirs(STATE, exist_ok=True)
    t_start = time.time()
    base = json.load(open(ARM)) if os.path.exists(ARM) else None
    checks = []
    perf_inconclusive = []

    def add(name, ok, detail=""):
        checks.append({"name": name, "ok": bool(ok), "detail": str(detail)[:300]})

    # 0. Node 2 reachable (wait up to 10 min)
    rc = 1
    for _ in range(60):
        rc, _o = n2("true", 15)
        if rc == 0:
            break
        time.sleep(10)
    add("Node2 SSH 可達", rc == 0)

    # 1. Reboot actually happened on both nodes
    b1, b2 = boot_ids()
    if base:
        r1, r2 = b1 != base["boot_id_node1"], b2 != base["boot_id_node2"]
        add("Node1 已重開（boot_id 改變）", r1 or not require_reboot, f"{base['boot_id_node1'][:8]}→{b1[:8]}")
        add("Node2 已重開（boot_id 改變）", r2 or not require_reboot, f"{base['boot_id_node2'][:8]}→{b2[:8]}")
    _, up1 = sh("uptime -s"); _, up2 = n2("uptime -s")

    # 2. Wait for the serving pair to come up by itself (container restart policy / watchdog timer)
    t0 = time.time(); code = 0
    while time.time() - t0 < HEALTH_WAIT_S:
        code, _b = http("http://127.0.0.1:8888/health")
        if code == 200:
            break
        time.sleep(10)
    add("8888 /health 自動恢復", code == 200, f"等待 {round(time.time() - t0)}s")
    c89, _ = http("http://127.0.0.1:8889/health")
    add("8889 proxy /health", c89 == 200)
    _, models = http("http://127.0.0.1:8888/v1/models")
    add("模型 ID DeepSeek-V4.1-Flash-TF", "DeepSeek-V4.1-Flash-TF" in models)

    # 3. Containers
    _, c1 = sh("docker inspect dsv41-rank0 --format '{{.State.Status}} {{.RestartCount}} {{.State.StartedAt}}'")
    _, c2 = n2("docker inspect dsv41-rank1 --format '{{.State.Status}} {{.RestartCount}} {{.State.StartedAt}}'")
    add("rank0 容器 running", c1.startswith("running"), c1)
    add("rank1 容器 running", c2.startswith("running"), c2)
    _, wd = sh(f"grep -a 'WATCHDOG' {LOGS}/cluster_watchdog.log | tail -n 3")
    how = "watchdog 介入" if base and any(l[1:20] >= base["armed_at"][:19] for l in wd.splitlines() if l.startswith("[")) else "容器 restart policy 自動拉起"

    # 4. Binaries / scripts identical to the consolidated recipe
    if base:
        e = base["expect"]
        add("rank0 tensorfold-native sha256", sha(f"{ENGINE}/out/native/bin/tensorfold-native") == e["native_sha256"])
        _, l2 = n2(f"sha256sum {ENGINE}/out/bin/tf-dsv41-lanes")
        add("rank1 tf-dsv41-lanes sha256（Node2）", l2.split()[0:1] == [e["lanes_sha256"]])
        add("rank0.sh / rank1.sh / start-dsv41.sh 未變", sha(f"{LOGS}/rank0.sh") == e["rank0_sh"] and sha(f"{LOGS}/rank1.sh") == e["rank1_sh"] and sha(f"{HOME}/start-dsv41.sh") == e["start_sh"])
        _, f2 = n2(f"cd {ENGINE}/fatbins && cat *.fatbin | sha256sum")
        add("Node2 fatbins 備份完好", f2.split()[0:1] == [e["fatbins_concat"]])
    want_map = json.load(open(f"{KIT}/engram.json"))["token_map_sha256"]
    _, m2 = n2(f"sha256sum {TOKEN_MAP}")
    add("Engram token map sha 雙機 = engram.json", sha(TOKEN_MAP) == want_map and m2.split()[0:1] == [want_map], want_map[:16])

    # 5. Host services
    for u in ["spark-fastfail-proxy.service", "spark-ms-dtc-governor.service", "spark-dsv41-cluster.timer", "hermes-gateway.service"]:
        _, s = sh(f"systemctl --user is-active {u}")
        add(f"{u} active", s == "active", s)
    _, g1 = sh("systemctl is-active gpu-thermal-governor.service"); _, g2 = n2("systemctl is-active gpu-thermal-governor.service")
    add("舊 gpu-thermal-governor 雙機未啟動", g1 != "active" and g2 != "active", f"N1={g1} N2={g2}")
    _, s1 = sh("cat /proc/sys/vm/swappiness"); _, s2 = n2("cat /proc/sys/vm/swappiness")
    add("swappiness=1 雙機", s1 == "1" and s2 == "1", f"N1={s1} N2={s2}")
    _, ip1 = sh("ip -br a"); _, ip2 = n2("ip -br a")
    add("RoCE 位址（10.100.184/185）雙機", "10.100.184.2" in ip1 and "10.100.185.2" in ip1 and "10.100.184.1" in ip2 and "10.100.185.1" in ip2)
    _, gl = sh(f"tail -n 1 {HOME}/.cache/ms_dtc_governor.log")
    _, clk1 = sh("nvidia-smi --query-gpu=clocks.gr,temperature.gpu --format=csv,noheader,nounits")
    _, clk2 = n2("nvidia-smi --query-gpu=clocks.gr,temperature.gpu --format=csv,noheader,nounits")
    def memavail(txt):
        m = re.search(r"MemAvailable:\s+(\d+)", txt)
        return f"{int(m.group(1)) / 1048576:.2f}" if m else "?"
    mem1 = memavail(open("/proc/meminfo").read())
    mem2 = memavail(n2("cat /proc/meminfo")[1])

    # 6. Functional + performance smoke vs historical best (retry once if contaminated by external traffic)
    smoke = None; attempts = []
    def external_last(sec):
        _, o = sh(f"docker logs --since {sec}s dsv41-rank0 2>&1 | grep 'POST /v1/' | grep -vc '127.0.0.1'")
        return int(o or 0)
    idle_wait = 0
    if code == 200:
        time.sleep(30)
        # wait up to 30 min for 90 s without external (non-localhost) requests, so the perf numbers are clean
        while idle_wait < 1800 and external_last(90) > 0:
            time.sleep(30); idle_wait += 30
        for attempt in range(2):
            ts = time.time()
            out = f"{REPO}/benchmarks/results/omni_eval_smoke_postreboot_{int(ts)}.json"
            rc, log = sh(f"cd {REPO}/benchmarks && timeout 600 python3 run_omni_eval.py --profile smoke --output-report {out}", 660)
            _, ext = sh(f"journalctl --user -u spark-fastfail-proxy --since @{int(ts)} --no-pager -o cat | grep -E 'POST' | grep -vc '127.0.0.1'")
            _, ext8 = sh(f"docker logs --since {int(time.time() - ts) + 2}s dsv41-rank0 2>&1 | grep 'POST /v1/' | grep -vc '127.0.0.1'")
            external = int(ext or 0) + int(ext8 or 0)
            if os.path.exists(out):
                r = json.load(open(out)); d = r["dimensions"]
                smoke = {
                    "file": os.path.basename(out), "external_requests": external,
                    "quality": f"{sum(v.get('passed', False) for v in d['quality'].values())}/{len(d['quality'])}",
                    "quality_all": all(v.get("passed", False) for v in d["quality"].values()),
                    "tool_gate": d["tool_eval"]["tool_choice_required"]["passed"],
                    "greedy": round(d["decode"]["decode_greedy"]["tokens_per_second"], 2),
                    "mtp": d["decode"]["decode_greedy"]["mtp_acceptance"],
                    "c2": d["concurrency"]["concurrency_c2"]["aggregate_tok_s"],
                    "cut_in_s": d["concurrency"]["cut_in_32k"]["short_ttft_s"], "cut_in_ok": d["concurrency"]["cut_in_32k"]["passed"],
                    "prefill_8k_tok_s": d["prefill"]["prefill_8k_cold"]["tok_s"],
                }
                attempts.append(smoke)
                if external == 0:
                    break
                w = 0
                while w < 900 and external_last(90) > 0:
                    time.sleep(30); w += 30
            else:
                attempts.append({"error": log[-300:]})
                break
    if smoke:
        add("品質題全過", smoke["quality_all"], smoke["quality"])
        add("工具呼叫門檻", smoke["tool_gate"])
        add("32K 插隊 TTFT ≤ 1.5s", smoke["cut_in_ok"], smoke["cut_in_s"])
    else:
        add("smoke 測試執行", False, attempts[-1] if attempts else "服務未恢復，未執行")
    gate = None
    if code == 200:
        label = f"postreboot_{int(time.time())}"
        grc, glog = sh(f"cd {REPO}/benchmarks && timeout 2400 python3 run_decode_gate.py --reps 1 --label {label}", 2460)
        gpath = f"{REPO}/benchmarks/results/decode_gate_{label}.json"
        if os.path.exists(gpath):
            gate = json.load(open(gpath))
            gs = gate["summary"]
            if gate["verdict"] == "inconclusive":
                perf_inconclusive.append(f"解碼門檻：乾淨樣本不足（外部流量），無法判定；{gs}")
            else:
                for k, v in gate["checks"].items():
                    add(f"解碼門檻 {k} ≥ 基準 95%", v["ok"], f"{v['value']}（需 {v['need']}，基準 {v['baseline']}）")
                add("C2/C4/C8 每路都有產出", all(gs[f"c{c}_streams_ok"] for c in (2, 4, 8)))
        else:
            add("解碼門檻執行", False, glog[-300:])

    ok = all(c["ok"] for c in checks)
    fails = [c for c in checks if not c["ok"]]
    rep = {"time": time.strftime("%F %T %z"), "overall_pass": ok, "mode": "run" if require_reboot else "dry-run",
           "uptime_since": {"node1": up1, "node2": up2}, "recovered_by": how, "checks": checks, "smoke_attempts": attempts,
           "gpu_clock_temp": {"node1": clk1, "node2": clk2}, "mem_available_gib": {"node1": mem1, "node2": mem2},
           "governor_last": gl[-160:], "decode_gate": (gate or {}).get("summary"), "perf_inconclusive": perf_inconclusive, "idle_wait_s": idle_wait, "elapsed_s": round(time.time() - t_start)}
    stamp = time.strftime("%Y%m%d_%H%M%S")
    json.dump(rep, open(f"{STATE}/report_{stamp}.json", "w"), indent=2, ensure_ascii=False)
    json.dump(rep, open(f"{REPO}/benchmarks/results/post_reboot_verify_{stamp}.json", "w"), indent=2, ensure_ascii=False)

    verdict = f"❌ {len(fails)} 項失敗" if not ok else ("⚠️ 功能全過，效能無法判定（外部流量）" if perf_inconclusive else "✅ 全部通過")
    lines = [f"*DGX Spark 雙機重開機自主驗證（{rep['mode']}）：{verdict}*",
             f"• 開機時間：Node1 {up1}，Node2 {up2}；服務恢復方式：{how}",
             f"• 驗證共 {len(checks)} 項，耗時 {rep['elapsed_s']}s"]
    if smoke:
        lines.append(f"• smoke：品質 {smoke['quality']}、工具 {'PASS' if smoke['tool_gate'] else 'FAIL'}、單題單流 {smoke['greedy']} tok/s（僅參考）、"
                     f"32K 插隊 {smoke['cut_in_s']}s、8K 預填 {smoke['prefill_8k_tok_s']} tok/s；測試期間外部請求 {smoke['external_requests']} 次")
    if gate:
        gs = gate["summary"]
        lines.append(f"• 解碼門檻（{gate['verdict']}）：9 題程式碼中位 *{gs['sweep_greedy_tps']} tok/s*（{gs['sweep_greedy_min']}–{gs['sweep_greedy_max']}）、"
                     f"MTP {gs['sweep_mtp_accept']}、C2 {gs['c2_agg']}、C4 {gs['c4_agg']}、C8 {gs['c8_agg']}")
    lines.append(f"• GPU 時脈,溫度：Node1 {clk1}，Node2 {clk2}；可用記憶體：Node1 {mem1} GiB，Node2 {mem2} GiB")
    if smoke is not None:
        lines.append(f"• 等待外部流量空檔：{idle_wait}s")
    for x in perf_inconclusive:
        lines.append(f"• ⚠️ {x}")
    if fails:
        lines.append("• 失敗項目：")
        lines += [f"  – {c['name']}：{c['detail']}" for c in fails]
    else:
        lines.append("• 通過項目：" + "、".join(c["name"] for c in checks))
    lines.append(f"• 報告：`benchmarks/results/post_reboot_verify_{stamp}.json`")
    md = "\n".join(lines)
    if require_reboot:
        open(f"{STATE}/deliver.md", "w").write(md)
    if require_reboot and os.path.exists(ARM):
        os.rename(ARM, f"{STATE}/armed_consumed_{stamp}.json")
    print(md)
    return 0 if ok else 1


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "dry-run"
    if cmd == "arm":
        arm()
    elif cmd == "run":
        sys.exit(run(True))
    else:
        sys.exit(run(False))
