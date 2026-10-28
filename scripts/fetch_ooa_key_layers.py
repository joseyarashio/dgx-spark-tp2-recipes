#!/usr/bin/env python3
import concurrent.futures
import json
import os
import time
import urllib.request

REPO = "object-oriented-architects/DeepSeek-V4.1-Flash-1017-EXL3-2.7bpw-TensorFold"
OOA_DIR = "/home/joseyarashio/models/DeepSeek-V4.1-Flash-1017-EXL3-2.7bpw-OOA"
TARGET_LAYERS = [18, 19, 20, 21, 22, 31, 32, 33, 34, 35, 36]

def main():
    os.makedirs(OOA_DIR, exist_ok=True)
    url = f"https://huggingface.co/api/models/{REPO}?blobs=true"
    info = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=20).read().decode())

    to_fetch = []
    for s in info.get("siblings", []):
        fn = s["rfilename"]
        sz = (s.get("lfs") or {}).get("size") or s.get("size") or 0
        for l in TARGET_LAYERS:
            if fn.startswith(f"model-exl3-routed-L{l:02d}-"):
                dst = os.path.join(OOA_DIR, fn)
                if not (os.path.exists(dst) and os.path.getsize(dst) == sz and sz > 0):
                    to_fetch.append((fn, sz))
                break

    to_fetch.sort()
    total_bytes = sum(x[1] for x in to_fetch)
    print(f"Downloading {len(to_fetch)} OOA routed-expert shards ({total_bytes / (1024**3):.2f} GiB) for layers {TARGET_LAYERS}...")

    t0 = time.perf_counter()
    done_bytes = 0

    def dl_one(item):
        fn, sz = item
        dst = os.path.join(OOA_DIR, fn)
        furl = f"https://huggingface.co/{REPO}/resolve/main/{fn}"
        for attempt in range(4):
            try:
                req = urllib.request.Request(furl, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=180) as r, open(dst + ".tmp", "wb") as out_f:
                    while True:
                        buf = r.read(4 * 1024 * 1024)
                        if not buf:
                            break
                        out_f.write(buf)
                if os.path.getsize(dst + ".tmp") != sz:
                    raise IOError(f"Incomplete read on {fn}")
                os.replace(dst + ".tmp", dst)
                return fn, sz
            except Exception:
                if attempt == 3:
                    raise
                time.sleep(2)

    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as ex:
        futs = [ex.submit(dl_one, it) for it in to_fetch]
        for i, f in enumerate(concurrent.futures.as_completed(futs), 1):
            fn, sz = f.result()
            done_bytes += sz
            if i % 8 == 0 or i == len(to_fetch):
                dt = time.perf_counter() - t0
                print(f"  [{i}/{len(to_fetch)}] {done_bytes/(1024**3):.2f}/{total_bytes/(1024**3):.2f} GiB ({done_bytes/(1024**2)/max(dt,0.1):.1f} MiB/s) - last: {fn}", flush=True)

    print("=== Completed OOA key layers download! ===")

if __name__ == "__main__":
    main()
