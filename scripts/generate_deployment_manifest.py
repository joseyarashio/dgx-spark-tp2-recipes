#!/usr/bin/env python3
import os, sys, hashlib, json, subprocess

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()

def sha256_dir(path, ext=None):
    h = hashlib.sha256()
    for root, _, files in sorted(os.walk(path)):
        for f in sorted(files):
            if ext and not f.endswith(ext):
                continue
            fp = os.path.join(root, f)
            h.update(f.encode())
            with open(fp, "rb") as fp_in:
                while chunk := fp_in.read(65536):
                    h.update(chunk)
    return h.hexdigest()

def generate():
    recipes_dir = "/home/joseyarashio/dgx-spark-tp2-recipes"
    engine_dir = "/home/joseyarashio/TensorFold-dsv41-zig"
    kit_dir = "/home/joseyarashio/dsv41-2m-kit/aot"

    engine_commit = subprocess.run(["git", "-C", engine_dir, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    recipe_commit = subprocess.run(["git", "-C", recipes_dir, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    patchset_sha256 = sha256_dir(os.path.join(recipes_dir, "patches"), ".patch")
    kernel_manifest_sha256 = sha256_dir(kit_dir)

    launch_h = hashlib.sha256()
    for sf in ["/home/joseyarashio/start-dsv41.sh", "/home/joseyarashio/.cache/dsv41-1017-logs/rank0.sh", "/home/joseyarashio/.cache/dsv41-1017-logs/rank1.sh"]:
        if os.path.exists(sf):
            launch_h.update(open(sf, "rb").read())
    launch_config_sha256 = launch_h.hexdigest()
    proxy_sha256 = sha256_file(os.path.join(recipes_dir, "proxy", "proxy.py"))

    def meminfo_gib(cmd):
        out = subprocess.run(cmd, capture_output=True, text=True).stdout
        for line in out.splitlines():
            if line.startswith("MemAvailable:"):
                return round(int(line.split()[1]) / 1024 / 1024, 2)
        return None
    import re, urllib.request
    rank0 = open("/home/joseyarashio/.cache/dsv41-1017-logs/rank0.sh").read()
    rank1 = open("/home/joseyarashio/.cache/dsv41-1017-logs/rank1.sh").read()
    pool = int(re.search(r"--pool (\d+)", rank1).group(1))
    prompt_cache = float(re.search(r"--prompt-cache-gib ([0-9.]+)", rank0).group(1))
    parallel = int(re.search(r"--parallel (\d+)", rank0).group(1))
    try:
        mem = json.loads(urllib.request.urlopen("http://127.0.0.1:8888/health", timeout=5).read())["memory"]["active"]
        active_gib = round(mem / 2**30, 2)
    except Exception:
        active_gib = None
    binaries = {
        "rank0_tensorfold_native_sha256": sha256_file(os.path.join(engine_dir, "out/native/bin/tensorfold-native")),
        "rank1_tf_dsv41_lanes_sha256": sha256_file(os.path.join(engine_dir, "out/bin/tf-dsv41-lanes")),
    }
    node2_lanes = subprocess.run(["ssh", "-o", "BatchMode=yes", "10.100.184.1", "sha256sum", os.path.join(engine_dir, "out/bin/tf-dsv41-lanes")], capture_output=True, text=True).stdout.split()
    binaries["node2_tf_dsv41_lanes_sha256"] = node2_lanes[0] if node2_lanes else None
    binaries["rank1_binary_synced"] = binaries["node2_tf_dsv41_lanes_sha256"] == binaries["rank1_tf_dsv41_lanes_sha256"]

    manifest = {
        "manifest_version": "1.0.0",
        "cluster_topology": {
            "nodes": 2,
            "interconnect": "ConnectX-7 200Gbps RoCEv2 dual-rail direct",
            "measured_bandwidth_gbps": 185.0,
            "host_memory_per_node_gib": 121.0,
            "gpu_microarchitecture": "NVIDIA Grace-Blackwell SM121 (GB10)",
            "cpu_microarchitecture": "MediaTek 10x Cortex-X925 (3.9GHz) + 10x Cortex-A725 (2.8GHz)",
            "cpu_pinning": "5-9,15-19 (10x Cortex-X925 Super-Cores)"
        },
        "cryptographic_hashes": {
            "recipe_commit": recipe_commit,
            "engine_commit": engine_commit,
            "patchset_sha256": patchset_sha256,
            "kernel_manifest_sha256": kernel_manifest_sha256,
            "launch_config_sha256": launch_config_sha256,
            "proxy_sha256": proxy_sha256
        },
        "engine_binaries": binaries,
        "memory_audit_ledger": {
            "measured_at": subprocess.run(["date", "+%F %T %z"], capture_output=True, text=True).stdout.strip(),
            "rank0_engine_active_gib": active_gib,
            "parallel_slots": parallel,
            "kv_pool_allocated_tokens": pool,
            "host_prompt_cache_budget_gib": prompt_cache,
            "cuda_graph_lru_cap": 128,
            "node1_available_memory_gib": meminfo_gib(["cat", "/proc/meminfo"]),
            "node2_available_memory_gib": meminfo_gib(["ssh", "-o", "BatchMode=yes", "10.100.184.1", "cat", "/proc/meminfo"]),
            "engram_mode": "O_DIRECT Linux AIO from local NVMe (203 GB tables)"
        }
    }

    os.makedirs(os.path.join(recipes_dir, "deployments"), exist_ok=True)
    out_file = os.path.join(recipes_dir, "deployments", "manifest.json")
    with open(out_file, "w") as f:
        json.dump(manifest, f, indent=2)
    return manifest

if __name__ == "__main__":
    m = generate()
    print(json.dumps(m, indent=2))
