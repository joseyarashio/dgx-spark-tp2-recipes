#!/usr/bin/env python3
import glob
import json
import os
import shutil
import struct
import sys

def patch_rank_cache(rc_path, pt_hdr, pt_bytes, backup_path):
    with open(rc_path, "rb") as f:
        f.seek(-16, 2)
        end_pos = f.tell()
        idx_off, magic = struct.unpack("<QQ", f.read(16))
        f.seek(idx_off)
        idx_rows = json.loads(f.read(end_pos - idx_off).decode())
    rc_map = {r[0]: r for r in idx_rows}

    if not os.path.exists(backup_path):
        bak = {}
        with open(rc_path, "rb") as f:
            for k in sorted(pt_hdr.keys()):
                if k == "__metadata__":
                    continue
                rk = f"{k}|torch.float32"
                if rk in rc_map:
                    _, dt, sh, off, nbytes = rc_map[rk]
                    f.seek(off)
                    bak[rk] = {"offset": off, "nbytes": nbytes, "hex": f.read(nbytes).hex()}
        with open(backup_path, "w") as bf:
            json.dump(bak, bf, indent=2)
        print(f"Saved original F16 gate.bias backup ({len(bak)} tensors) to {backup_path}")

    patched = 0
    with open(rc_path, "r+b") as f:
        for k, pv in sorted(pt_hdr.items()):
            if k == "__metadata__":
                continue
            rk = f"{k}|torch.float32"
            if rk in rc_map:
                _, dt, sh, off, nbytes = rc_map[rk]
                s, e = pv["data_offsets"]
                new_b = pt_bytes[s:e]
                assert len(new_b) == nbytes, f"Size mismatch for {rk}: {len(new_b)} != {nbytes}"
                f.seek(off)
                f.write(new_b)
                patched += 1
        f.flush()
        os.fsync(f.fileno())
    print(f"Patched {patched}/43 F32 gate.bias tensors in {rc_path}")

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "apply"
    model_dir = "/home/joseyarashio/models/DeepSeek-V4.1-Flash-1017-EXL3-2.9bpw"
    st_src = "/tmp/zz-gate-bias-f32-1017.safetensors"
    st_dst = os.path.join(model_dir, "zz-gate-bias-f32-1017.safetensors")
    if os.path.exists(st_src) and not os.path.exists(st_dst):
        shutil.copy2(st_src, st_dst)

    with open(st_dst, "rb") as f:
        hlen = struct.unpack("<Q", f.read(8))[0]
        pt_hdr = json.loads(f.read(hlen).decode())
        pt_bytes = f.read()

    idx_path = os.path.join(model_dir, "model.safetensors.index.json")
    idx_bak = os.path.join(model_dir, "model.safetensors.index.json.bak.f16bias")
    if os.path.exists(idx_path):
        if not os.path.exists(idx_bak):
            shutil.copy2(idx_path, idx_bak)
        if mode == "apply":
            idx_data = json.load(open(idx_path))
            for k in pt_hdr:
                if k != "__metadata__":
                    idx_data["weight_map"][k] = "zz-gate-bias-f32-1017.safetensors"
            with open(idx_path, "w") as f:
                json.dump(idx_data, f, indent=2)
        elif mode == "revert" and os.path.exists(idx_bak):
            shutil.copy2(idx_bak, idx_path)

    for rc_path in glob.glob("/home/joseyarashio/.cache/dsv41-1017-rank-cache/tf-ds-rank/rank*of2-*.bin"):
        bak_path = rc_path + ".f16bias.bak.json"
        if mode == "apply":
            patch_rank_cache(rc_path, pt_hdr, pt_bytes, bak_path)
        elif mode == "revert" and os.path.exists(bak_path):
            bak = json.load(open(bak_path))
            with open(rc_path, "r+b") as f:
                for rk, info in bak.items():
                    f.seek(info["offset"])
                    f.write(bytes.fromhex(info["hex"]))
                f.flush()
                os.fsync(f.fileno())
            print(f"Reverted {len(bak)} tensors in {rc_path}")

if __name__ == "__main__":
    main()
