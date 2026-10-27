#!/usr/bin/env python3
import json
import os
import shutil

LIB_DIR = "/home/joseyarashio/models/DeepSeek-V4.1-Flash-1017-EXL3-2.9bpw"
OOA_DIR = "/home/joseyarashio/models/DeepSeek-V4.1-Flash-1017-EXL3-2.7bpw-OOA"
TARGET_LAYERS = {18, 19, 20, 21, 22, 31, 32, 33, 34, 35, 36}

def main():
    os.makedirs(OOA_DIR, exist_ok=True)
    # Hardlink all LibertAIDAI shards and metadata into OOA_DIR if not present
    for fn in os.listdir(LIB_DIR):
        src = os.path.join(LIB_DIR, fn)
        dst = os.path.join(OOA_DIR, fn)
        if os.path.isfile(src) and fn not in ("model.safetensors.index.json", "exl3_k_map.json"):
            if not os.path.exists(dst):
                os.link(src, dst)

    # Copy zz-gate-bias-f32-1017.safetensors
    bias_src = "/home/joseyarashio/dgx-spark-tp2-recipes/patches/zz-gate-bias-f32-1017.safetensors"
    bias_dst = os.path.join(OOA_DIR, "zz-gate-bias-f32-1017.safetensors")
    if os.path.exists(bias_src) and not os.path.exists(bias_dst):
        shutil.copy2(bias_src, bias_dst)

    # Load LibertAIDAI index and OOA upstream index
    lib_idx = json.load(open(os.path.join(LIB_DIR, "model.safetensors.index.json.bak.f16bias" if os.path.exists(os.path.join(LIB_DIR, "model.safetensors.index.json.bak.f16bias")) else os.path.join(LIB_DIR, "model.safetensors.index.json"))))
    ooa_orig_path = os.path.join(OOA_DIR, "model.safetensors.index.json.ooa_upstream")
    if not os.path.exists(ooa_orig_path):
        shutil.copy2(os.path.join(OOA_DIR, "model.safetensors.index.json"), ooa_orig_path)
    ooa_idx = json.load(open(ooa_orig_path))

    merged_wm = dict(lib_idx["weight_map"])
    replaced_tensors = 0
    for k, sh in ooa_idx["weight_map"].items():
        if k.startswith("layers.") and ".ffn.experts." in k:
            l = int(k.split(".")[1])
            if l in TARGET_LAYERS:
                merged_wm[k] = sh
                replaced_tensors += 1

    # Also point all 43 gate.bias tensors to zz-gate-bias-f32-1017.safetensors
    for k in list(merged_wm.keys()):
        if k.endswith(".ffn.gate.bias") and not k.startswith("vision."):
            merged_wm[k] = "zz-gate-bias-f32-1017.safetensors"

    out_idx = {"metadata": ooa_idx.get("metadata", {}), "weight_map": merged_wm}
    with open(os.path.join(OOA_DIR, "model.safetensors.index.json"), "w") as f:
        json.dump(out_idx, f, indent=2)

    print(f"Prepared OOA hybrid index in {OOA_DIR}: {replaced_tensors} routed expert tensors mapped to OOA K2..K5 shards across layers {sorted(TARGET_LAYERS)}")

if __name__ == "__main__":
    main()
