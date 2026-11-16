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
