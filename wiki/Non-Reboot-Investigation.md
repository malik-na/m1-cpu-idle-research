# Investigating the Running Mac Without Rebooting

A boot change is **not required** to continue this line of research. The running macOS system permits exact-build static analysis, unprivileged IOReport sampling, and—with a local administrator session—a bounded kernel trace. These methods can narrow *software policy and event ordering*. They cannot, by themselves, certify a physical cluster rail-off state.

## What is available now

| Route | Current status | Useful answer | Limit |
|---|---|---|---|
| Matching kernelcache and kext disassembly | Completed for macOS 27.0 build 26A428 | Exact PMGR/CLPC control flow and register access | Conditional path frequency is unknown from static code |
| Unprivileged AArch64 `MRS` capability probe | Completed; [source and results](../notes/el0-capability-probe.md) | 24 MHz counter and current logical CPU/cluster tag for bounded user-mode experiments | Power-control registers and PMGR MMIO remain inaccessible at EL0 |
| Unprivileged IOReport collector plus custom AArch64 workload | Completed | CPU/cluster IDLE reporting, entries, modeled energy channels, timed pulse response | One CPU IDLE bin; probe changes wake activity |
| Privileged `ktrace` | Five-second capture succeeded; see [Live Mac Tracing](Live-Mac-Tracing.md) | PMGR `PERF_CPU_IDLE` event timing and apparent last-core callback work | Trace event is software; internal APSC wait needs more specific instrumentation |
| `powermetrics` | Not yet captured in this investigation | Depending on the build, additional CPU frequency, residency and SoC power reporting | Root required; reported/model values are not a physical idle-depth oracle |
| Privileged DTrace FBT inventory | Tested on 26A428; header only and a SIP restriction diagnostic, despite exit status 0 | Establishes that this native FBT route is unavailable under the tested configuration | No PMGR probe, branch, or BUSY value was observed; this does not prove the functions are absent |

The [privileged inventory record](../notes/raw/mac-fbt-inventory-26A428.json) and [direct-observation route](../notes/mac-apsc-direct-observation-route.md) preserve the exact command, output, and interpretation. The operator's sudo authentication succeeded for that command. Its diagnostic identifies SIP as the restriction; repeating authentication does not qualify a probe. No security configuration was changed.

The [user-mode register probe](../notes/el0-capability-probe.md) uses actual `MRS` instructions in isolated processes. `CNTVCT_EL0`/`CNTPCT_EL0` and Apple's `TPIDR_EL0` CPU tag are readable here; a direct `CYC_OVRD` read faults. This makes assembly useful for timestamp and current-CPU attribution, while fixing its privilege boundary empirically. The existing [plain-C IOReport tool and ARM64 assembly workload](../notes/telemetry-notes.md) run without a boot change or root. The 32.481-second capture demonstrates observable IDLE changes but delivered unequal work between foreground and background pulse phases, so it does not establish an energy policy win. [`notes/raw/ioreport/paired-c-assembly-summary.json`](../notes/raw/ioreport/paired-c-assembly-summary.json) retains the summary.

The installed PMGR signpost catalog identifies `0x27001001` / `0x27001002` as the **begin/end of each** `PERF_CPU_IDLE` callback, and local CLPC code contains a WFE-recommendation event at `0x328c00c0`. A successful five-second root trace recorded the former and no instance of the latter. Absence in one short capture does not prove CLPC's code never executes. See [Live Mac Tracing](Live-Mac-Tracing.md).

## Why the macOS Hypervisor API is not host introspection

Apple's [Hypervisor framework](https://developer.apple.com/documentation/hypervisor) creates a virtual machine with `hv_vm_create`, maps host-process memory into **guest** physical address space with [`hv_vm_map`](https://developer.apple.com/documentation/hypervisor/hv_vm_map%28_%3A_%3A_%3A_%3A%29), and runs virtual CPUs with [`hv_vcpu_run`](https://developer.apple.com/documentation/hypervisor/hv_vcpu_run%28_%3A%29). **Inference from that documented API:** creating an entitled VM does not attach an observer to the already-running macOS kernel or expose host PMGR registers. The app may control and trace its guest, not retroactively place the host under its own EL2 control.

[m1n1's hypervisor](https://asahilinux.org/docs/sw/m1n1-hypervisor/) takes control *before* booting a macOS guest, through a separate boot object and guest setup. That is a different placement in the boot chain. The official guide currently documents macOS 13.5 and 14.8.3 guests, not the investigated macOS 27 build. Its own power-register emulation and timer/proxy activity also affect idle interpretation; see [trace validity audit](../notes/trace-validity.md).

The latest disk inventory in this investigation showed only the macOS APFS container and its macOS/recovery volumes, with no visible current Asahi/Linux boot partition. This is a dated machine observation, not a claim about future disk state or the historical Linux experiments. Re-run a read-only disk inventory before any later boot plan; an old native trace does not imply a currently bootable Linux installation.

## Useful next non-reboot step

The saved PMGR events have an [exploratory timing correlation](../notes/mac-ktrace-perf-request-correlation.md): E-cluster apparent-last-core callbacks were longer shortly after one performance-request marker. Repeating that comparison cannot supply the missing branch or BUSY value. With the native FBT gate failed, the immediate work is to build and review the [Linux observation patch and analyzer](../experiments/linux-apsc-observer/README.md) for the later native session. A new Mac trace is useful only if it answers a separately defined question, with traced/no-trace controls, loss, and observer effects. The [experiment backlog](Experiment-Backlog.md) gives the discriminating criteria.
