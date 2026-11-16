#!/usr/bin/env python3
"""Find the RoCE v2 IPv4 GID index of each RDMA device and print the one index they share.

Usage: roce_gid.py DEV[,DEV...] [--repair] [--sysfs ROOT]

The served ring (TF_RDMA_GID_INDEX) and NCCL (NCCL_IB_GID_INDEX) take one GID index per process, applied
to every rail. That index is not fixed: when a peer reboots, the link flaps and the kernel can rebuild the
GID table so the RoCE v2 entry for the port's IPv4 address is missing or sits at another index
(2026-11-16: Node1 kept its IPs, index 3 went empty, rank1 crash-looped on ncclAllGather).

For each device: netdev from <sysfs>/class/infiniband/<dev>/device/net, its IPv4 address from `ip -4`,
then the index whose gid is ::ffff:<ipv4> and whose type is "RoCE v2".
--repair: when a device has no such entry, or the rails disagree, re-activate the NetworkManager connection
bound to that netdev (`sudo -n nmcli con up <name>`, matched by DEVICE, not by name: Node2's connection names
are swapped relative to their devices) and look again.
Prints the index on stdout and exits 0; otherwise prints the reason on stderr and exits 1.
"""
import os, subprocess, sys, time


def netdev(sysfs, dev):
    d = f"{sysfs}/class/infiniband/{dev}/device/net"
    names = sorted(os.listdir(d)) if os.path.isdir(d) else []
    return names[0] if names else None


def ipv4(nd, sysfs):
    fake = f"{sysfs}/ipv4/{nd}"  # test fixtures
    if os.path.exists(fake):
        return open(fake).read().strip() or None
    out = subprocess.run(["ip", "-4", "-o", "addr", "show", "dev", nd], capture_output=True, text=True).stdout
    for tok in out.split():
        if "/" in tok and tok.count(".") == 3:
            return tok.split("/")[0]
    return None


def want_gid(ip):
    a, b, c, d = (int(x) for x in ip.split("."))
    return f"0000:0000:0000:0000:0000:ffff:{a:02x}{b:02x}:{c:02x}{d:02x}"


def index_of(sysfs, dev, gid):
    base = f"{sysfs}/class/infiniband/{dev}/ports/1"
    names = os.listdir(f"{base}/gids") if os.path.isdir(f"{base}/gids") else []
    for i in sorted(int(n) for n in names if n.isdigit()):
        try:
            g = open(f"{base}/gids/{i}").read().strip()
            t = open(f"{base}/gid_attrs/types/{i}").read().strip()
        except OSError:  # unused entries refuse reads of their attrs
            continue
        if g == gid and t == "RoCE v2":
            return i
    return None


def scan(sysfs, devs):
    found, why = {}, []
    for dev in devs:
        nd = netdev(sysfs, dev)
        ip = ipv4(nd, sysfs) if nd else None
        if not nd or not ip:
            why.append(f"{dev}: netdev={nd} ipv4={ip}")
            found[dev] = None
            continue
        found[dev] = index_of(sysfs, dev, want_gid(ip))
        if found[dev] is None:
            why.append(f"{dev} ({nd} {ip}): no RoCE v2 GID for ::ffff:{ip}")
    return found, why


def repair(sysfs, devs):
    active = subprocess.run(["nmcli", "-t", "-f", "NAME,DEVICE", "con", "show", "--active"],
                            capture_output=True, text=True).stdout.splitlines()
    by_dev = {line.rsplit(":", 1)[1]: line.rsplit(":", 1)[0] for line in active if ":" in line}
    for dev in devs:
        nd = netdev(sysfs, dev)
        name = by_dev.get(nd) if nd else None
        if not name:
            print(f"repair: no active NetworkManager connection on {nd}", file=sys.stderr)
            continue
        r = subprocess.run(["sudo", "-n", "nmcli", "con", "up", name], capture_output=True, text=True)
        print(f"repair: nmcli con up {name} ({nd}) rc={r.returncode}", file=sys.stderr)


def main(argv):
    devs = argv[0].split(",") if argv else []
    sysfs = argv[argv.index("--sysfs") + 1] if "--sysfs" in argv else "/sys"
    found, why = scan(sysfs, devs)
    shared = set(found.values())
    if (None in shared or len(shared) != 1) and "--repair" in argv:
        print("GID table not usable: " + ("; ".join(why) or f"rails disagree {found}") + "; repairing", file=sys.stderr)
        repair(sysfs, devs)
        for _ in range(10):
            time.sleep(1)
            found, why = scan(sysfs, devs)
            shared = set(found.values())
            if None not in shared and len(shared) == 1:
                break
    if None in shared:
        print("; ".join(why), file=sys.stderr)
        return 1
    if len(shared) != 1:
        print(f"rails disagree on the RoCE v2 GID index: {found}", file=sys.stderr)
        return 1
    print(shared.pop())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
