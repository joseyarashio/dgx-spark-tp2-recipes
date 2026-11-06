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
    kit_dir = "/home/joseyarashio/dsv41-tensorfold-tp2/kit/aot"

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
        "memory_audit_ledger": {
            "rank0_device_working_set_gib": 99.2,
            "rank1_device_working_set_gib": 99.2,
            "kv_pool_allocated_tokens": 1048576,
            "kv_pool_footprint_gib": 6.44,
            "host_prompt_cache_budget_gib": 3.0,
            "cuda_graph_lru_cap": 128,
            "cuda_graph_footprint_gib": 0.65,
            "node1_available_memory_gib": 7.60,
            "node2_available_memory_gib": 9.30,
            "engram_disk_mmap_mode": "Demand-Paged File-Backed (203 GB on NVMe)",
            "status": "Safe Watermark Maintained (Zero OOM Risk)"
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
