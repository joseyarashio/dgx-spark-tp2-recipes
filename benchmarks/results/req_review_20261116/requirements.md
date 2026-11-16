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
