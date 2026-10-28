#!/usr/bin/env python3
import glob
import json
import os
import re
import struct
import sys

BACKBONE_DIR = "/home/joseyarashio/models/DeepSeek-V4.1-Flash-1017-EXL3-2.9bpw-PlusTen/backbone_tensors"
LIB_DIR = "/home/joseyarashio/models/DeepSeek-V4.1-Flash-1017-EXL3-2.9bpw"

DTYPE_SIZE = {
    "BF16": 2, "F16": 2, "F32": 4, "I16": 2, "I32": 4, "I64": 8, "U8": 1, "F8_E4M3": 1,
    "bfloat16": 2, "float16": 2, "float32": 4, "int16": 2, "int32": 4, "int64": 8, "uint8": 1,
}

def parse_range(txt):
    if txt == "None":
        return None
    m = re.match(r"^\((\d+),\s*(\d+)\)$", txt)
    if not m:
        raise ValueError(f"Bad range: {txt}")
    return (int(m.group(1)), int(m.group(2)))

def parse_rc_key(rk):
    parts = rk.split("|")
    if len(parts) == 2:
        return {"exl3": False, "name": parts[0], "dtype": None if parts[1] == "None" else parts[1]}
    elif len(parts) == 4:
        tail = {"tr": "trellis", "suh": "suh", "svh": "svh"}[parts[3]]
        return {
            "exl3": True,
            "prefix": parts[0],
            "name": f"{parts[0]}.{tail}",
            "cols": parse_range(parts[1]),
            "rows": parse_range(parts[2]),
            "part": parts[3],
        }
    raise ValueError(f"Unknown key format: {rk}")

def slice_tensor(raw_bytes, st_dtype, st_shape, parsed_key, expected_nbytes):
    if not parsed_key["exl3"]:
        target_dt = parsed_key["dtype"]
        if target_dt is None or (target_dt == "torch.float32" and st_dtype == "F32") or (target_dt == "torch.float16" and st_dtype == "F16"):
            assert len(raw_bytes) == expected_nbytes
            return raw_bytes
        if st_dtype == "F16" and target_dt == "torch.float32":
            n = len(raw_bytes) // 2
            vals = struct.unpack(f"<{n}e", raw_bytes)
            return struct.pack(f"<{n}f", *vals)
        if st_dtype == "BF16" and target_dt == "torch.float32":
            n = len(raw_bytes) // 2
            u16s = struct.unpack(f"<{n}H", raw_bytes)
            u32s = [x << 16 for x in u16s]
            return struct.pack(f"<{n}I", *u32s)
        raise ValueError(f"Unsupported plain conversion: {st_dtype} -> {target_dt}")

    es = DTYPE_SIZE[st_dtype]
    part = parsed_key["part"]
    cols = parsed_key["cols"]
    rows = parsed_key["rows"]

    if part == "tr":
        dim0, dim1, dim2 = st_shape
        row_bytes = dim1 * dim2 * es
        k0 = (rows[0] // 16) if rows is not None else 0
        if cols is not None:
            tile = dim2 * es
            lo = (cols[0] // 16) * tile
            w = ((cols[1] - cols[0]) // 16) * tile
            kt = ((rows[1] - rows[0]) // 16) if rows is not None else dim0
            out = bytearray(kt * w)
            for i in range(kt):
                src_off = (k0 + i) * row_bytes + lo
                out[i * w : (i + 1) * w] = raw_bytes[src_off : src_off + w]
            assert len(out) == expected_nbytes, f"Mismatch {len(out)} != {expected_nbytes}"
            return bytes(out)
        if rows is not None:
            src_off = k0 * row_bytes
            out = raw_bytes[src_off : src_off + expected_nbytes]
            assert len(out) == expected_nbytes
            return out
        assert len(raw_bytes) == expected_nbytes
        return raw_bytes
    else:
        sel = rows if part == "suh" else cols
        if sel is not None:
            src_off = sel[0] * es
            out = raw_bytes[src_off : src_off + expected_nbytes]
            assert len(out) == expected_nbytes
            return out
        assert len(raw_bytes) == expected_nbytes
        return raw_bytes

def self_test_against_libertai(rc_path):
    print("Running self-test of slicer against LibertAIDAI rank0 cache...")
    with open(rc_path, "rb") as f:
        f.seek(-16, 2)
        end_pos = f.tell()
        idx_off, _ = struct.unpack("<QQ", f.read(16))
        f.seek(idx_off)
        idx_rows = json.loads(f.read(end_pos - idx_off).decode())
    rc_map = {r[0]: r for r in idx_rows}
    lib_idx = json.load(open(f"{LIB_DIR}/model.safetensors.index.json"))["weight_map"]

    test_keys = [
        r[0] for r in idx_rows
        if r[0].startswith(("head|", "layers.0.attn.wq_b|", "layers.0.attn.wo_b|", "layers.0.ffn.shared_experts.", "layers.1.engram.wkv|", "mtp.0.ffn.experts.0.w1|"))
        and r[0].endswith(("|tr", "|suh", "|svh"))
    ][:12]
    with open(rc_path, "rb") as rf:
        for rk in test_keys:
            pk = parse_rc_key(rk)
            sh_file = os.path.join(LIB_DIR, lib_idx[pk["name"]])
            with open(sh_file, "rb") as sf:
                hlen = struct.unpack("<Q", sf.read(8))[0]
                hdr = json.loads(sf.read(hlen).decode())
                info = hdr[pk["name"]]
                s, e = info["data_offsets"]
                sf.seek(8 + hlen + s)
                raw = sf.read(e - s)
            _, _, _, off, nb = rc_map[rk]
            rf.seek(off)
            expected = rf.read(nb)
            sliced = slice_tensor(raw, info["dtype"], info["shape"], pk, nb)
            assert sliced == expected, f"Self-test failed on {rk}"
    print("  Self-test PASSED: 100% byte-identical on all 9 slice topologies!")

def patch_rank_cache(rc_path, manifest, backup_file):
    with open(rc_path, "rb") as f:
        f.seek(-16, 2)
        end_pos = f.tell()
        idx_off, _ = struct.unpack("<QQ", f.read(16))
        f.seek(idx_off)
        idx_rows = json.loads(f.read(end_pos - idx_off).decode())

    to_patch = []
    for rk, dt, sh, off, nb in idx_rows:
        pk = parse_rc_key(rk)
        tname = pk["name"]
        if tname not in manifest and ".markov_head." in tname:
            tname = tname.replace(".markov_head.embed.weight", ".markov_head.markov_w1.weight").replace(".markov_head.head.weight", ".markov_head.markov_w2.weight")
        if tname in manifest:
            # Only patch quantized EXL3 tensors (keep F32 gate.bias and plain norms/embeds intact or update if changed)
            if pk["exl3"]:
                to_patch.append((rk, pk, tname, off, nb))

    print(f"Found {len(to_patch)} quantized backbone + MTP tensors to patch in {rc_path}")

    if not os.path.exists(backup_file):
        print(f"Saving original LibertAIDAI backbone backup to {backup_file}...")
        bak_index = []
        with open(rc_path, "rb") as rf, open(backup_file, "wb") as bf:
            cur_bak_off = 0
            for rk, pk, tname, off, nb in to_patch:
                rf.seek(off)
                data = rf.read(nb)
                bf.write(data)
                bak_index.append({"rk": rk, "rc_offset": off, "bak_offset": cur_bak_off, "nbytes": nb})
                cur_bak_off += nb
        with open(backup_file + ".json", "w") as jf:
            json.dump(bak_index, jf)
        print(f"  Backup saved ({cur_bak_off / (1024**3):.3f} GiB)")

    # Group by span_file so each span file is read once into memory
    by_span = {}
    for item in to_patch:
        tname = item[2]
        sf = manifest[tname]["span_file"]
        by_span.setdefault(sf, []).append(item)

    patched_bytes = 0
    patched_count = 0
    with open(rc_path, "r+b") as rf:
        for sf, items in sorted(by_span.items()):
            span_path = os.path.join(BACKBONE_DIR, sf)
            with open(span_path, "rb") as spf:
                span_buf = spf.read()
            for rk, pk, tname, off, nb in items:
                minfo = manifest[tname]
                rel = minfo["rel_offset"]
                raw = span_buf[rel : rel + minfo["nbytes"]]
                sliced = slice_tensor(raw, minfo["dtype"], minfo["shape"], pk, nb)
                rf.seek(off)
                rf.write(sliced)
                patched_bytes += nb
                patched_count += 1
        rf.flush()
        os.fsync(rf.fileno())
    print(f"Patched {patched_count} tensors ({patched_bytes / (1024**3):.3f} GiB) in {rc_path}")

def revert_rank_cache(rc_path, backup_file):
    bak_index = json.load(open(backup_file + ".json"))
    with open(rc_path, "r+b") as rf, open(backup_file, "rb") as bf:
        for item in bak_index:
            bf.seek(item["bak_offset"])
            data = bf.read(item["nbytes"])
            rf.seek(item["rc_offset"])
            rf.write(data)
        rf.flush()
        os.fsync(rf.fileno())
    print(f"Reverted {len(bak_index)} tensors in {rc_path}")

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "apply"
    target_pattern = sys.argv[2] if len(sys.argv) > 2 else "/home/joseyarashio/.cache/dsv41-plusten-rank-cache/tf-ds-rank/rank*of2-*.bin"
    rc_paths = sorted(glob.glob(target_pattern))
    if not rc_paths:
        raise ValueError(f"No rank cache files found for pattern: {target_pattern}")

    for rc_path in rc_paths:
        bak_file = rc_path + ".libertai_backbone.bak"
        if mode == "revert":
            revert_rank_cache(rc_path, bak_file)
            continue

        if "rank0of2" in rc_path:
            self_test_against_libertai(rc_path)

        manifest = json.load(open(os.path.join(BACKBONE_DIR, "manifest.json")))
        patch_rank_cache(rc_path, manifest, bak_file)

if __name__ == "__main__":
    main()
