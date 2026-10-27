#!/usr/bin/env python3
import concurrent.futures
import json
import os
import struct
import time
import urllib.request

REPO = "Plus-Ten/DeepSeek-V4.1-Flash-1017-TensorFold-EXL3-2.9bpw"
OUT_DIR = "/home/joseyarashio/models/DeepSeek-V4.1-Flash-1017-EXL3-2.9bpw-PlusTen/backbone_tensors"

def is_target_tensor(k: str) -> bool:
    # All 100%-active quantized tensors + MTP drafter (excluding the 189 GiB of 3-bit main routed experts)
    if k.startswith("layers.") and ".ffn.experts." in k:
        return False
    return True

def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    idx_path = "/home/joseyarashio/models/DeepSeek-V4.1-Flash-1017-EXL3-2.9bpw-PlusTen/model.safetensors.index.json"
    wm = json.load(open(idx_path))["weight_map"]

    target_by_shard = {}
    for k, sh in wm.items():
        if is_target_tensor(k):
            target_by_shard.setdefault(sh, []).append(k)

    print(f"Fetching headers for {len(target_by_shard)} shards from {REPO}...")
    headers = {}
    def get_hdr(sh):
        url = f"https://huggingface.co/{REPO}/resolve/main/{sh}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Range": "bytes=0-8191"})
        b8 = urllib.request.urlopen(req, timeout=20).read()
        hlen = struct.unpack("<Q", b8[:8])[0]
        req2 = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Range": f"bytes=8-{8+hlen-1}"})
        hdr = json.loads(urllib.request.urlopen(req2, timeout=30).read().decode())
        return sh, 8 + hlen, hdr

    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as ex:
        for sh, base, hdr in ex.map(get_hdr, sorted(target_by_shard.keys())):
            headers[sh] = (base, hdr)

    # Coalesce contiguous byte spans per shard so we make minimal Range requests
    spans = []
    total_bytes = 0
    manifest = {}
    for sh, keys in sorted(target_by_shard.items()):
        base, hdr = headers[sh]
        items = []
        for k in keys:
            v = hdr[k]
            s, e = v["data_offsets"]
            items.append((s, e, k, v["dtype"], v["shape"]))
        items.sort(key=lambda x: x[0])
        # Group adjacent/nearby items within 1 MiB gap
        cur_s, cur_e, cur_items = items[0][0], items[0][1], [items[0]]
        for it in items[1:]:
            if it[0] - cur_e <= 1048576:
                cur_e = max(cur_e, it[1])
                cur_items.append(it)
            else:
                spans.append((sh, base, cur_s, cur_e, cur_items))
                total_bytes += (cur_e - cur_s)
                cur_s, cur_e, cur_items = it[0], it[1], [it]
        spans.append((sh, base, cur_s, cur_e, cur_items))
        total_bytes += (cur_e - cur_s)

    print(f"Coalesced {sum(len(v) for v in target_by_shard.values())} target tensors into {len(spans)} contiguous HTTP Range spans ({total_bytes / (1024**3):.3f} GiB total)")

    t0 = time.perf_counter()
    downloaded_bytes = 0

    def download_span(idx_span):
        idx, (sh, base, s, e, items) = idx_span
        span_file = os.path.join(OUT_DIR, f"span_{idx:04d}_{sh}_{s}_{e}.bin")
        expected_len = e - s
        if not (os.path.exists(span_file) and os.path.getsize(span_file) == expected_len):
            url = f"https://huggingface.co/{REPO}/resolve/main/{sh}"
            lo = base + s
            hi = base + e - 1
            for attempt in range(4):
                try:
                    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Range": f"bytes={lo}-{hi}"})
                    with urllib.request.urlopen(req, timeout=120) as r, open(span_file + ".tmp", "wb") as out_f:
                        while True:
                            buf = r.read(4 * 1024 * 1024)
                            if not buf:
                                break
                            out_f.write(buf)
                    os.replace(span_file + ".tmp", span_file)
                    break
                except Exception as err:
                    if attempt == 3:
                        raise
                    time.sleep(2)
        entries = {}
        for ts, te, k, dt, shape in items:
            entries[k] = {
                "span_file": os.path.basename(span_file),
                "rel_offset": ts - s,
                "nbytes": te - ts,
                "dtype": dt,
                "shape": shape,
            }
        return expected_len, entries

    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as ex:
        futs = [ex.submit(download_span, (i, sp)) for i, sp in enumerate(spans)]
        for i, f in enumerate(concurrent.futures.as_completed(futs), 1):
            nb, ents = f.result()
            downloaded_bytes += nb
            manifest.update(ents)
            if i % 10 == 0 or i == len(spans):
                dt = time.perf_counter() - t0
                print(f"  [{i}/{len(spans)}] {downloaded_bytes/(1024**3):.2f}/{total_bytes/(1024**3):.2f} GiB ({downloaded_bytes/(1024**2)/max(dt,0.1):.1f} MiB/s)", flush=True)

    manifest_path = os.path.join(OUT_DIR, "manifest.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"=== Completed Plus-Ten backbone fetch: {len(manifest)} tensors saved to {manifest_path} ===")

if __name__ == "__main__":
    main()
