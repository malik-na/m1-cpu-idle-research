# Findings Index

All findings below refer to the investigated base-M1 Mac and pinned public revisions in the [research report](../notes/README.md). Follow each evidence link before extending the claim to another build or chip.

| Finding | Evidence | Boundary |
|---|---|---|
| `cpu-power-gate-latency-us = 50000` is passed unchanged to XNU's nanosecond latency input, yielding 50 microseconds in this running build. | [Local binary chain](../notes/local-driver-notes.md), [independent review](../notes/review.md), [public XNU registration](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/osfmk/arm64/machine_routines.c#L1624) | Software spin/block parameter; not measured exit latency or Linux target residency. |
| The PMGR last-active-core idle branch resolves to `cpuComplexIdleEnter` and conditionally `_waitAPSCPending`; the wait polls DVFS BUSY bit 31 until clear in two sequential loops. | [PMGR disassembly analysis](../notes/local-driver-notes.md), [skip-flag follow-up](../notes/local-driver-skipflag-followup.md) | Static configuration predicts wait enabled; frequency and effect remain unmeasured. |
| The E/P cluster command registers map to `0x210e20020` and `0x211e20020`. Linux uses offset `0x20` and BUSY bit 31 for the same command family. | [Register mapping](../notes/local-driver-notes.md), [Asahi cpufreq source](https://github.com/AsahiLinux/linux/blob/77cb8f24c2381a8abb7272d7bbdec548d6426a8a/drivers/cpufreq/apple-soc-cpufreq.c) | Matching address/bit does not establish an idle correctness issue. |
| In the installed PMGR CPU-complex path, the performance marker follows `setPerfState` return. Its optional post-write wait depends on a caller boolean; the idle callback passes false and has a separate last-core wait. | [Instruction-order audit](../notes/mac-pmgr-command-order.md), [focused disassembly](../notes/raw/driver-pmgr-perf-marker-order.disasm) | Three other callers share the marker helper; a captured event does not identify the call site, command write, or hardware completion. |
| User-mode AArch64 can read the 24 MHz counter and current logical CPU/cluster tag on this Mac; sampled power-control reads fault. | [Live EL0 probe](../notes/el0-capability-probe.md), [reproducible C/assembly](../notes/tools/el0-capabilities.c) | Timestamp and attribution capability; no PMGR BUSY or physical idle-depth access. |
| A privileged FBT inventory on native 26A428 produced zero probe rows and a SIP restriction diagnostic, with exit status 0. | [Complete sanitized inventory](../notes/raw/mac-fbt-inventory-26A428.json), [route decision](../notes/mac-apsc-direct-observation-route.md) | This native observation route is blocked in the tested configuration; it says nothing about whether the static wait actually executes. |
| The active T8103 CLPC code updates a WFE recommendation, while seven inspected named cluster-power methods are two-instruction returns. | [Local driver analysis](../notes/local-driver-notes.md), [disassembly](../notes/raw/driver-clpc-cluster-noops.disasm) | Empty named methods do not prove cluster gating absent elsewhere. |
| The checked Asahi, Omacom, and Aurora M1 `cpuidle-apple.c` files are byte-identical and already enter returning deep WFI. Omacom's default branch is the exact pinned Asahi commit. | [Omacom audit](../notes/omacom-linux-source-audit.md), [Aurora audit](../notes/aurora-cpu-idle.md), [Asahi source](https://github.com/AsahiLinux/linux/blob/77cb8f24c2381a8abb7272d7bbdec548d6426a8a/drivers/cpuidle/cpuidle-apple.c) | Does not establish identical whole trees, installed kernels, or physical residency. |
| A 32.481-second unprivileged macOS IOReport/assembly workload capture differentiated software CPU/cluster IDLE behavior across pulse phases. | [Measurement note](../notes/telemetry-notes.md), [phase summary](../notes/raw/ioreport/paired-c-assembly-summary.json) | Unequal delivered work and one IDLE bin prevent a power-policy or idle-depth conclusion. |
| Historical native Linux reporting shows all eight CPUs entering `CPU PD` software state. | [Prior Native Linux Results](Prior-Native-Linux-Results.md) | Historical capture; not refreshed this session and not physical rail-off proof. |
| A five-second macOS `ktrace` run produced 47,068 complete PMGR CPUIdle callback pairs, with longer apparent last-active-core enter callbacks. | [Live Mac Tracing](Live-Mac-Tracing.md), [sanitized aggregate](../notes/raw/ktrace/idle-5s-summary.json) | Bracket duration is software work, not evidence that the APSC wait ran or that hardware powered down. |
| In that trace, 166 apparent last E-core entry callbacks began within 50 µs after a `CPM1PerfStateReq` marker and had 14.251 µs median bracket duration, versus 3.458 µs for 2,822 callbacks at least 1 ms after a marker or with no preceding marker. | [Reproducible trace correlation](../notes/mac-ktrace-perf-request-correlation.md) | Exploratory temporal association; no branch, DVFS BUSY, physical state, or causal energy observation. |
| On the native T8103 Aurora capacity kernel, a cluster-1 APSC command read at the C pre-WFI hook had BUSY set 549 counter ticks after a same-CPU SET. C had 734 valid reads, 16 BUSY and zero stream loss. | [Native result](../experiments/aurora-apsc-observer/NATIVE-RESULT.md), [reviewed numerical packet](../experiments/aurora-apsc-observer/native-evidence/README.md) | Final-entrant reconstruction needs an unproven 240-tick cross-CPU bound; no observation at WFI, physical cluster state, energy, defect, or cluster-0 negative. |

## Still open

The [2 October Linux qualification](../notes/linux-native-qualification-20261002.md) refreshed the visible stock kernel/configuration and software accounting. A separate [Aurora port](../experiments/aurora-apsc-observer/README.md) passed full build and native A/B/C capture gates; its [result](../experiments/aurora-apsc-observer/NATIVE-RESULT.md) answers the narrower question of a BUSY command-register value at the pre-WFI hook. The stronger WFI-instruction, hardware-state and physical-overlap question remains open.

The [first requested test restart](../experiments/aurora-apsc-observer/restart-outcome-receipt.json)
selected the stock entry. The test bundle and menu entry remained verified;
the selection cause is unresolved. Later direct menu selection did boot the
research images and support the separate native result above.

The operator later booted the research release directly but found Wi-Fi and
brightness unavailable. [Raw-log and package checks](../experiments/aurora-apsc-observer/driver-regression-receipt.json)
show Omarchy had removed the unowned research modules on an earlier stock
boot. The complete matching module tree was restored and package-owned;
Wi-Fi and brightness worked on the later research boot. The subsequent
capacity image yielded the A/B/C capture above.

1. How often does the running macOS last-core path actually execute the pending-command wait, and how often does it observe BUSY?
2. Can an outstanding Linux DVFS command overlap the final core's deep-WFI entry in the current native kernel, including remote writers? If so, does hardware already handle it safely?
3. Which independent native observation distinguishes a physical cluster state while minimally disturbing it?
4. What complete restart, interrupt, timer, and state-restoration contract would permit a deeper non-returning state from Linux runtime idle?
5. Under matched work, does any validated change improve energy without unacceptable wake latency or instability?

Each question has a bounded first experiment in [Experiment Backlog](Experiment-Backlog.md).
