#!/usr/bin/env python3
"""Read-only native Linux inventory and paired CPU-idle counters. No root needed.

Run after booting Linux: python3 linux-idle-audit.py --seconds 30 > idle-audit.json
Counter deltas measure the driver's requested states, not proven physical gating.
"""
import argparse
import datetime
import glob
import json
import os
import pathlib
import platform
import time


def read(path):
    try:
        return pathlib.Path(path).read_text().strip()
    except (OSError, UnicodeError) as exc:
        return {"unavailable": str(exc)}


def snapshot():
    paths = set()
    for pattern in (
        "/sys/devices/system/cpu/cpuidle/*",
        "/sys/devices/system/cpu/cpu[0-9]*/cpuidle/state*/*",
        "/sys/devices/system/cpu/cpufreq/policy*/*",
        "/sys/devices/system/cpu/cpu[0-9]*/topology/*",
        "/sys/devices/system/cpu/cpu[0-9]*/cpu_capacity",
        "/sys/class/power_supply/*/power_now",
        "/sys/class/power_supply/*/energy_now",
        "/sys/class/power_supply/*/voltage_now",
        "/sys/class/power_supply/*/current_now",
        "/sys/class/power_supply/*/status",
    ):
        paths.update(glob.glob(pattern))
    paths.update(("/sys/devices/system/cpu/online", "/sys/devices/system/cpu/possible",
                  "/sys/devices/system/cpu/isolated", "/proc/cmdline", "/proc/interrupts",
                  "/proc/softirqs", "/proc/loadavg", "/sys/kernel/debug/pm_genpd/pm_genpd_summary"))
    return {"monotonic_s": time.monotonic(), "files": {
        p: read(p) for p in sorted(paths) if not pathlib.Path(p).is_dir()}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, default=30)
    args = parser.parse_args()
    if platform.system() != "Linux":
        parser.error("Run this on the M1 booted natively into Linux.")
    if not 1 <= args.seconds <= 300:
        parser.error("seconds must be between 1 and 300")
    before = snapshot()
    time.sleep(args.seconds)
    after = snapshot()
    deltas = {}
    for path, new in after["files"].items():
        old = before["files"].get(path)
        if "/cpuidle/state" in path and pathlib.Path(path).name in {"usage", "time", "above", "below", "rejected", "s2idle"}:
            if isinstance(new, str) and isinstance(old, str) and new.isdigit() and old.isdigit():
                deltas[path] = int(new) - int(old)
    result = {"captured_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "uname": list(platform.uname()), "uid": os.getuid(),
              "model": read("/proc/device-tree/model"), "before": before, "after": after,
              "elapsed_s": after["monotonic_s"]-before["monotonic_s"], "idle_counter_deltas": deltas,
              "limitation": "CPU-idle usage/time reflect software requests; confirm actual hardware gating independently."}
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
