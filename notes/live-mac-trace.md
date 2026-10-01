# Live macOS CPU-idle callback trace

**Capture:** 1 October 2026, macOS 27.0 build 26A428, M1 MacBookAir10,1 / T8103. The machine stayed in macOS. The user authenticated `sudo` locally and ran a bounded five-second trace:

```sh
sudo /usr/bin/ktrace trace -T 5s -b 8 -f S0x2700,S0x328c --ndjson > /private/tmp/m1-idle-5s.ndjson
```

The full 22 MB output stays on the Mac. Its SHA-256 is `4c98c1622767c503b40476d52f647f07449d30dde3ddc871cf55dec7b12e1d99`. The [published event stream](raw/ktrace/idle-5s-events.jsonl.gz) strips wall-clock time, process name, PID and thread ID, preserving relative timestamp, CPU ID, event ID and numeric arguments. It is enough to independently recalculate the [aggregate](raw/ktrace/idle-5s-summary.json) using [the analyzer](tools/analyze-ktrace.py):

```sh
python3 tools/analyze-ktrace.py raw/ktrace/idle-5s-events.jsonl.gz
```

This command ran as root because `ktrace` requires it for whole-system events. An unprivileged attempt exited immediately with `ktrace must be run as root when tracing the current system`. Neither attempt changed boot policy or wrote a hardware register. Tracing may itself change CPU wakeups and scheduling.

## What the events mean

The installed [ApplePMGR signpost definition](raw/driver-ApplePMGR.kext-PMGRSignposts.plist.json) names `0x27001001` and `0x27001002` the begin and end of a **CPUIdle interval**. These are the begin/end of a *single PMGR callback*, **not** a begin before WFI and an end after wakeup. The matching [PMGR `_cpuIdle` disassembly](raw/driver-pmgr-cpuidle.disasm) calls `_kernel_debug` with `0x27001001` near function entry (`9b1966c`–`9b19688`) and forms `0x27001002` near its exit (`9b19ef0`–`9b19f10`). It passes the callback direction as the second trace argument. The `enterCPUIdle` wrapper calls `_cpuIdle(..., true, ...)` (`9b1a458`–`9b1a460`); `exitCPUIdle` uses `false` (`9b1a57c`–`9b1a584`). Thus argument 1 (zero-based `args[1]`) is 1 for preparation on idle entry and 0 for cleanup after wakeup. The trace can begin with either direction on a CPU because collection starts midstream.

The capture spans 5.048 seconds of event timestamps and contains **47,068 complete PMGR callback begin/end pairs** over eight CPUs. There were no nested, orphaned, or mismatched pairs in the saved interval; there were no out-of-order records. The filter also captured 906 performance-state request events and 27 `PERF_CLOCK_GATE` begin/end pairs. It captured **zero** CLPC WFE-recommendation events (`0x328c00c0`). This absence is confined to these five seconds and this filter; it does not show that the CLPC code is unused in general.

## A live last-core timing signal

The analyzer tracks each core's most recently completed PMGR enter/exit callback: entry marks it *apparently idle*, exit marks it active. For an entry callback, it calls the core an **apparent last active core** only if all three peer cores in its four-core cluster were already marked idle and no peer callback was in progress. Entries with unknown or in-flight peer states are excluded from the comparison. This reconstruction assumes CPUs 0–3 are the E cluster and 4–7 are the P cluster; it observes PMGR software transitions, not the physical rail state.

| Cluster | Entry condition | n | Median callback duration | 90th percentile |
|---|---|---:|---:|---:|
| E | Apparent last active core | 3,334 | 3.500 µs | 8.542 µs |
| E | Another core active | 16,425 | 0.333 µs | 0.708 µs |
| P | Apparent last active core | 727 | 2.709 µs | 6.375 µs |
| P | Another core active | 2,766 | 0.084 µs | 0.291 µs |

The split persists when the same comparison is made per CPU (the full breakdown is in the aggregate JSON). This is **live evidence of additional last-core PMGR software work** on this build. It is consistent with the statically identified last-core branch in `_cpuIdle`, but the trace does not identify which instruction or subroutine consumed the time. Cluster accounting, PMP notification, APSC synchronization, or other work can contribute. The trace therefore does **not** confirm that `_waitAPSCPending` actually executed, show that its BUSY bit was set, or prove physical CPU/cluster power gating. The idle gap *between* entry and exit callbacks is a separate interval and cannot be equated to one hardware depth without another state observable.

## Next discriminating experiment

A simultaneous read-only trace of the PMGR last-core callback, the APSC/DVFS BUSY bit, and a calibrated physical-state indicator would test the Linux implementation question. The candidate Linux PMGR `PCPM` ACTUAL field is described in [the observable audit](idle-observable-audit.md); it has not been read during this macOS trace. The [Mac-only performance-request correlation](mac-ktrace-perf-request-correlation.md) helps choose workloads, but software requests are not proof of an outstanding hardware command. Root `ktrace` alone cannot expose a private function entry or the MMIO value on this SIP-enabled system. A later native Linux experiment should use sparse, bounded reads through the already-owned PMGR mapping and validate observer effects and wake correctness.
