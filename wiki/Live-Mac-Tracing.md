# Live Mac Tracing: Bounded PMGR CPU-Idle Capture

A privileged, **five-second** `ktrace` capture succeeded on the investigated macOS 27.0 build 26A428 without rebooting. It recorded PMGR `PERF_CPU_IDLE` callbacks from all eight CPUs. The current result is a software-timing observation: **apparent last-active-core callbacks take longer than other callbacks**. It does not establish that `_waitAPSCPending` executed, that BUSY was set, or that a core/cluster physically powered off.

The [detailed local trace note](../notes/live-mac-trace.md), [sanitized event stream](../notes/raw/ktrace/idle-5s-events.jsonl.gz), [aggregate](../notes/raw/ktrace/idle-5s-summary.json), and [analyzer](../notes/tools/analyze-ktrace.py) preserve the result. The full trace stays out of this public repository because system-wide traces can include process names and other private activity. Its SHA-256 is `4c98c1622767c503b40476d52f647f07449d30dde3ddc871cf55dec7b12e1d99` for provenance; a hash does not make the private file public.

## What was captured

| Metric | Result |
|---|---:|
| Parsed records | 95,096 |
| Capture span | 5.048 s |
| Complete `PERF_CPU_IDLE` begin/end pairs | 47,068 |
| CPUs represented | 8 |
| Orphan, nested, or mismatched begin/end pairs | 0 in analyzed pairs |
| CLPC WFE-recommendation event `0x328c00c0` | 0 in this short capture |

`ktrace decode 0x27001001 0x27001002` names `PERF_CPU_IDLE` start and end. These are **function-bracket markers** around individual `ApplePMGR::_cpuIdle` calls. The local disassembly shows `args[0]` is the CPU identifier and `args[1]` is **1 for the enter callback or 0 for the exit callback**. Each direction has its own start/end pair; a start marker with `args[1]=0` is therefore the beginning of an *exit callback*, not an idle exit event by itself. The NDJSON fields used here include `timestampns`, `cpuid`, `debugid`, `eventname`, and `args`. [Local PMGR disassembly](../notes/raw/driver-pmgr-cpuidle.disasm), [trace note](../notes/live-mac-trace.md).

The analyzer reconstructs an apparent per-core idle state from completed enter and exit callbacks. It calls an **enter callback** an *apparent last-active-core callback* when all other cores in that cluster were previously observed idle and no peer callback was in progress. This is a software reconstruction from the trace; unobserved pre-window state and kernel-internal accounting are not independently known. The reconstruction yields:

| Cluster | Apparent last-active-core enter callbacks | Median bracket duration | Other enter callbacks | Median bracket duration |
|---|---:|---:|---:|---:|
| E | 3,334 | 3,500 ns | 16,425 | 333 ns |
| P | 727 | 2,709 ns | 2,766 | 84 ns |

The duration is time spent **inside the PMGR callback brackets**, not time in WFI or physical idle. The observed split is consistent with additional last-core work and justifies a narrower probe. The local binary already shows multiple possible last-core operations, so duration alone cannot identify the APSC wait. An absence of `0x328c00c0` in five seconds only says that event was not recorded in this capture and filter configuration.

## Bounded recipe on this macOS build

The successful command was:

```sh
umask 077
sudo /usr/bin/ktrace trace -T 5s -b 8 -f S0x2700,S0x328c --ndjson > /private/tmp/m1-idle-5s.ndjson
```

`S0x2700` selects the class/subclass containing PMGR CPUIdle; `S0x328c` includes the CLPC candidate. The 8 MB buffer is a configuration parameter, not a promise that an NDJSON output file will be small. `-T 5s` bounds the trace duration. Authenticate at the Mac's own `sudo` prompt; do not put a password into command arguments, files, chat, or repository history. Run `ktrace decode 0x27001001 0x27001002 0x328c00c0` first to verify event decoding on the target build. The target may already have a trace session; check local `ktrace` documentation and active configuration before replacing it.

The command may include events beyond the three exact IDs because a filter chooses **subclasses**, not individual codes. Review event counts and trace loss before interpreting output. The public analyzer/aggregate show the transformation used for this capture. Keep new full-system traces private; publish compact aggregates or carefully reviewed examples with build, filter, parser, and hash provenance.

## Access and method boundary

An unprivileged live `ktrace` attempt exited with “ktrace must be run as root when tracing the current system.” Unprivileged `dtrace -l` attempts for a relevant FBT or profile probe returned “DTrace requires additional privileges.” Unprivileged `powermetrics` returned “must be invoked as the superuser.” An earlier unprivileged `ktrace info` attempt returned “Too many levels of remote in path”; that error alone did not establish why information was unavailable. The successful trace used a locally authorized administrator `sudo` session. Root allowed this supported tracing command; it did not bypass SIP or grant user space arbitrary host physical-register reads.

Apple's [Hypervisor framework](https://developer.apple.com/documentation/hypervisor) documents `hv_vm_create`, mapping a host-process region into guest physical memory with [`hv_vm_map`](https://developer.apple.com/documentation/hypervisor/hv_vm_map%28_%3A_%3A_%3A_%3A%29), and running a guest vCPU with [`hv_vcpu_run`](https://developer.apple.com/documentation/hypervisor/hv_vcpu_run%28_%3A%29). The inference is specific: an entitled macOS process can manage a **guest VM**, but the documented API does not make the already-running host kernel its guest or expose host PMGR MMIO. [m1n1's boot-first hypervisor](https://asahilinux.org/docs/sw/m1n1-hypervisor/) is a distinct arrangement, and its guest traces have [documented power-state interference](../notes/trace-validity.md).

## Next discriminating trace

The next result should name whether the actual `_waitAPSCPending` branch ran and whether its reads observed BUSY, while preserving cluster, CPU, callback direction, timestamps and loss. A five-second duration split tells us **where to look**, not what the internal work was. A native Linux comparison later needs its own instrumented command-submission-to-WFI timeline and an independently qualified physical-state or energy observable. See [Experiment Backlog](Experiment-Backlog.md).
