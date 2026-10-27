#!/usr/bin/env python3
import glob
import os
import shutil
import subprocess
import sys

OOA_CACHE_DIR = "/home/joseyarashio/.cache/dsv41-ooa-rank-cache/tf-ds-rank"
DS_CACHE_DIR = "/home/joseyarashio/.cache/dsv41-1017-rank-cache/tf-ds-rank"

def main():
    action = sys.argv[1] if len(sys.argv) > 1 else "activate"
    ooa_r0 = glob.glob(f"{OOA_CACHE_DIR}/rank0of2-*.bin")[0]
    ooa_r1 = glob.glob(f"{OOA_CACHE_DIR}/rank1of2-*.bin")[0]

    if action == "activate":
        print(f"Activating OOA Hybrid 2.7bpw rank cache...")
        # Move current LibertAIDAI rank files aside
        for f in glob.glob(f"{DS_CACHE_DIR}/rank*of2-*.bin"):
            if not f.endswith(".active_ooa"):
                os.rename(f, f + ".active_ooa")
        # Hardlink OOA cache files into DS_CACHE_DIR
        r0_dst = os.path.join(DS_CACHE_DIR, os.path.basename(ooa_r0))
        r1_dst = os.path.join(DS_CACHE_DIR, os.path.basename(ooa_r1))
        if not os.path.exists(r0_dst):
            os.link(ooa_r0, r0_dst)
        if not os.path.exists(r1_dst):
            os.link(ooa_r1, r1_dst)

        # Do same on Node 2
        cmd = f"""
        for f in {DS_CACHE_DIR}/rank*of2-*.bin; do
            [ -f \"\\$f\" ] && [ \"\\${{f%.active_ooa}}\" = \"\\$f\" ] && mv \"\\$f\" \"\\$f.active_ooa\"
        done
        [ ! -f {DS_CACHE_DIR}/{os.path.basename(ooa_r1)} ] && ln {OOA_CACHE_DIR}/{os.path.basename(ooa_r1)} {DS_CACHE_DIR}/{os.path.basename(ooa_r1)} || true
        """
        subprocess.check_call(["ssh", "-o", "BatchMode=yes", "joseyarashio@10.100.184.1", cmd])
        print("OOA Hybrid 2.7bpw rank cache ACTIVATED on Node 1 & Node 2!")

    elif action == "deactivate":
        print("Restoring LibertAIDAI/PlusTen rank cache...")
        for f in glob.glob(f"{DS_CACHE_DIR}/rank*of2-*.bin"):
            if not f.endswith(".active_ooa"):
                os.remove(f)
            else:
                os.rename(f, f[:-11])
        cmd = f"""
        for f in {DS_CACHE_DIR}/rank*of2-*.bin; do
            [ -f \"\\$f\" ] && [ \"\\${{f%.active_ooa}}\" != \"\\$f\" ] && mv \"\\$f\" \"\\${{f%.active_ooa}}\" || rm -f \"\\$f\"
        done
        """
        subprocess.check_call(["ssh", "-o", "BatchMode=yes", "joseyarashio@10.100.184.1", cmd])
        print("Restored original rank cache on Node 1 & Node 2!")

if __name__ == "__main__":
    main()
