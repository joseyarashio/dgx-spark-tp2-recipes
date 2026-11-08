#!/usr/bin/env python3
"""
MS-DTC: Multi-Stream Dynamic Thermal Compensation Governor for DGX Spark GB10 TP=2.
Dynamically adjusts GPU graphics clock based on active stream concurrency, thermal velocity (dT/dt),
and board temperature, balancing single-stream latency, multi-stream throughput, and thermal safety.
"""

import glob
import os
import subprocess
import sys
import threading
import time

MIN_CLK = int(os.environ.get("MIN_CLK", "1800"))
MAX_CLK = int(os.environ.get("MAX_CLK", "2500"))
STEP = int(os.environ.get("STEP", "150"))
ZONE_PANIC = float(os.environ.get("ZONE_PANIC", "89.0"))
ZONE_HI = float(os.environ.get("ZONE_HI", "84.0"))
ZONE_SWEET = float(os.environ.get("ZONE_SWEET", "80.0"))
ZONE_COOL = float(os.environ.get("ZONE_COOL", "75.0"))
INTERVAL = float(os.environ.get("INTERVAL", "0.5"))
STANDBY_CLK = int(os.environ.get("STANDBY_CLK", "2400"))

NODE2_IP = os.environ.get("NODE2_IP", "10.100.184.1")
SHM_STATE_FILE = "/dev/shm/dgx_cluster_state"

def read_board_temp() -> float:
    hi = 0
    for z in glob.glob("/sys/class/thermal/thermal_zone*/temp"):
        try:
            with open(z) as f:
                v = int(f.read().strip()) // 1000
                if v > hi:
                    hi = v
        except Exception:
            pass
    return float(hi)

def read_cluster_state() -> tuple[int, int]:
    """Returns (active_streams, waiting_in_queue)."""
    try:
        if os.path.exists(SHM_STATE_FILE):
            with open(SHM_STATE_FILE) as f:
                parts = f.read().strip().split(",")
                if len(parts) >= 3:
                    active = int(parts[0])
                    waiting = int(parts[1])
                    ts_ms = int(parts[2])
                    # If updated within last 8 seconds, it is valid
                    if time.time() * 1000 - ts_ms < 8000:
                        return active, waiting
    except Exception:
        pass
    return 0, 0

def apply_clocks(clk: int):
    def _apply_node1():
        subprocess.run(["sudo", "-n", "nvidia-smi", "-lgc", f"0,{clk}"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def _apply_node2():
        subprocess.run(["ssh", "-o", "BatchMode=yes", f"joseyarashio@{NODE2_IP}",
                        f"sudo -n nvidia-smi -lgc 0,{clk}"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    t1 = threading.Thread(target=_apply_node1)
    t2 = threading.Thread(target=_apply_node2)
    t1.start()
    t2.start()
    t1.join(timeout=3.0)
    t2.join(timeout=3.0)

def main():
    print(f"[{time.strftime('%X')}] Starting MS-DTC Governor: range=[{MIN_CLK}, {MAX_CLK}]MHz step={STEP}MHz sync=[Node1, Node2]")
    sys.stdout.flush()

    cur_clk = MAX_CLK
    apply_clocks(cur_clk)

    prev_temp = read_board_temp()
    prev_time = time.time()
    last_heartbeat = time.time()
    idle_since = time.time() if read_cluster_state()[0] == 0 else 0.0

    while True:
        time.sleep(INTERVAL)
        now = time.time()
        dt = max(0.1, now - prev_time)
        board_t = read_board_temp()
        t_dot = (board_t - prev_temp) / dt
        prev_temp = board_t
        prev_time = now

        active_streams, waiting = read_cluster_state()

        # Track idle duration
        if active_streams == 0 and waiting == 0:
            if idle_since == 0.0:
                idle_since = now
        else:
            idle_since = 0.0

        # Decision Logic (MS-DTC Core)
        reason = "HOLD"
        target_clk = cur_clk

        if board_t >= ZONE_PANIC:
            target_clk = MIN_CLK
            reason = f"PANIC_OVERHEAT (T={board_t:.1f}C >= {ZONE_PANIC}C)"
        elif active_streams == 0 and waiting == 0:
            # Standby mode: 2400 MHz (consumes only ~9.4W, ready for instant burst)
            # If board is hot (> 72C), drop to 1800 MHz to accelerate cooling
            if board_t > 72.0:
                target_clk = MIN_CLK
                reason = f"HOT_IDLE_COOLDOWN (T={board_t:.1f}C > 72C)"
            else:
                target_clk = STANDBY_CLK
                reason = f"STANDBY_READY (T={board_t:.1f}C, cap={STANDBY_CLK}MHz)"
        else:
            # Active load with active_streams >= 1 or waiting > 0
            # Mechanism 1: Concurrency-Aware Base Floor
            f_floor = MIN_CLK + min(active_streams * 75, 600)  # N=1: 1875, N=2: 1950, N=4: 2100, N>=8: 2400
            
            if board_t < ZONE_SWEET:
                # Cold or sweet zone: uncap to full speed
                target_clk = MAX_CLK
                reason = f"SWEET_ZONE_BURST (T={board_t:.1f}C < {ZONE_SWEET}C, N={active_streams})"
            elif board_t < ZONE_HI:
                # 80C <= T < 84C
                # Mechanism 3: Derivative Damping
                if t_dot > 0.4:
                    # Rapidly heating
                    target_clk = max(cur_clk - STEP, f_floor)
                    reason = f"FAST_HEATING_DAMP (T_dot=+{t_dot:.2f}C/s, floor={f_floor})"
                else:
                    # Stable or cooling down -> hold frequency
                    target_clk = max(cur_clk, f_floor)
                    reason = f"STABLE_HOLD (T_dot={t_dot:+.2f}C/s, T={board_t:.1f}C, N={active_streams})"
            else:
                # T >= ZONE_HI (84C)
                if t_dot > 0.2:
                    target_clk = max(cur_clk - STEP, f_floor)
                    reason = f"ZONE_HI_STEP_DOWN (T={board_t:.1f}C, T_dot=+{t_dot:.2f}C/s, floor={f_floor})"
                else:
                    # Even above 84C, if temperature is dropping or stable, hold f_floor
                    target_clk = max(cur_clk, f_floor)
                    reason = f"ZONE_HI_DAMP_HOLD (T={board_t:.1f}C, T_dot={t_dot:+.2f}C/s, floor={f_floor})"

        # Clamp to bounds
        target_clk = max(MIN_CLK, min(MAX_CLK, target_clk))

        if target_clk != cur_clk:
            print(f"[{time.strftime('%X')}] CLK CHANGE: {cur_clk}MHz -> {target_clk}MHz | Reason: {reason} | T={board_t:.1f}C (dT/dt={t_dot:+.2f}C/s) N={active_streams}")
            sys.stdout.flush()
            cur_clk = target_clk
            apply_clocks(cur_clk)
        elif now - last_heartbeat >= 30.0:
            print(f"[{time.strftime('%X')}] STEADY: cap={cur_clk}MHz T={board_t:.1f}C (dT/dt={t_dot:+.2f}C/s) streams={active_streams} wait={waiting}")
            sys.stdout.flush()
            last_heartbeat = now

if __name__ == "__main__":
    main()
