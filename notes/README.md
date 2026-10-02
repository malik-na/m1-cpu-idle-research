# M1 CPU idle: local macOS evidence and a Linux implementation path

Investigation date: 1 October 2026, Asia/Kolkata. Target: MacBookAir10,1 / J313 / T8103, 8 GB, macOS 27.0 build 26A428. This report records local observation, actual AArch64 driver disassembly, and pinned comparisons with Asahi, Omacom, and Aurora Silicon. It does not claim a completed new Linux power-saving implementation. The [Omacom source audit](omacom-linux-source-audit.md) checks the additional fork without double-counting an identical upstream commit.

## What we established

1. **Linux already implements M1's returning deep-WFI path.** The CPU-idle driver is byte-identical in the inspected Asahi and Aurora stable/development branches. Reimplementing that path is not a discovery.
2. **A misleading Apple property has now been followed through the actual local binary.** `cpu-power-gate-latency-us = 50000` is copied unchanged into XNU's nanosecond-based software latency field: **50 microseconds**, despite the property name. It is not a measured exit latency or proof of a 50-microsecond gating threshold.
3. **This M1's CLPC driver has real WFE recommendation code, but several named cluster-power-control methods are empty.** Generic XNU interfaces and newer-chip behavior cannot be assumed to describe this machine's runtime policy.
4. **Live C telemetry and an ARM64 assembly workload work without root.** They observe CPU/cluster IDLE residency and entry counts. They do not resolve all physical idle depths.
5. **A concrete macOS/Linux difference is now identified for testing:** the Mac's last-core idle path contains conditional APSC/DVFS-busy synchronization. The checked Linux CPU-idle routine has no explicit equivalent. Whether this matters on Linux remains unmeasured.
6. **Deeper cluster sleep still needs a state-restoration contract.** Low-level stop/start primitives already exist in m1n1; a reliable Linux runtime integration requires considerably more than setting a register bit.
7. **A five-second privileged macOS trace captured the PMGR idle callbacks.** Reconstructed apparent last-active-core entry callbacks took longer than other entries on both clusters. This is runtime evidence for extra software work, not a direct observation of the pending-APSC wait or physical power gating. See the [trace analysis](live-mac-trace.md).
8. **A Mac-only reanalysis narrowed the timing lead.** In the saved trace, apparent last E-core entry callbacks were longer soon after one PMGR performance-request marker. The [reproducible correlation](mac-ktrace-perf-request-correlation.md) is exploratory and does not establish that the APSC wait or command BUSY bit caused the delay.
9. **The matching AArch64 code narrows what that marker can mean.** The CPU-complex caller emits it after `setPerfState` returns, following a command submission path whose post-write BUSY-clear wait is caller-dependent. Three other functions call the marker helper, so a recorded marker alone cannot identify that CPU command path. The idle callback passes the option as false and has a separate last-core wait. [Instruction-order audit](mac-pmgr-command-order.md), [focused disassembly](raw/driver-pmgr-perf-marker-order.disasm).
10. **A bounded EL0 instruction probe established the local access boundary.** User-mode assembly reads the 24 MHz counter and current logical CPU/cluster tag, while direct power-control-register reads fault. [Probe, source, and limits](el0-capability-probe.md).

The unit interpretation is a concrete build-specific reverse-engineering result. A bounded search found no prior public explanation of that exact path. That is not proof Asahi or Aurora researchers have never discovered it.

For the planned move to Omarchy with the [iconidentify Aurora release](iconidentify-aurora-kernel-target.md), use the [native Linux handoff](native-linux-handoff.md). Its first step is read-only qualification of the actual installation; the existing source-pinned experiments are not assumed compatible with an uninspected Aurora build.

The later [Linux read-only qualification](linux-native-qualification-20261002.md) records running-config and visible installed-image matches to that release receipt, build-ID linkage, software `CPU PD` accounting and failed observer prerequisites. It adds target evidence for open ticket #5; it does not observe APSC BUSY or physical cluster state.

The separate [Aurora observer/counter port](../experiments/aurora-apsc-observer/README.md) records clean checks on all touched source files, a complete Image/modules build, unchanged linked WFI bytes and a distinct research boot entry. Its subsequent [native A/B/C result](../experiments/aurora-apsc-observer/NATIVE-RESULT.md) includes a loss-free C command-register BUSY read after a same-CPU SET at the pre-WFI hook. The final-entrant interpretation assumes an unproven cross-CPU clock bound; no physical power or energy result follows. The [reviewed raw numerical packet](../experiments/aurora-apsc-observer/native-evidence/README.md) and decoder recipe are public.

## Wayfinder research decisions

The [APSC/DVFS decision map](https://github.com/malik-na/m1-cpu-idle-research/issues/1) coordinates the next multi-session work. Three source-only method decisions now have reviewable notes: [how to observe the macOS last-core wait](mac-apsc-direct-observation-route.md), [how to capture native Linux DVFS-to-WFI ordering](linux-dvfs-wfi-trace-choice.md), and [how to calibrate PCPM as a native state signal](native-pcpm-signal-decision.md). These are experiment routes, not new BUSY, physical-state, or energy observations.

## The 50-microsecond result

The inspected kernelcache matches the **running kernel UUID** `1F15A5DA-11D6-39EE-88D2-153E2F90F066` and XNU `13432.1.9~1`, T8103. The chain is:

```text
ADT /arm-io/pmgr: cpu-power-gate-latency-us
    raw bytes 50 c3 00 00 = 50000
        |
ApplePMGR property loading: unchanged 32-bit value
        |
ApplePMGR::_cpuIdleInit: object +0x2684 -> processor-info +0x54
        |
XNU ml_processor_register: nanoseconds -> absolute-time ticks
        |
CPU software idle-latency field (+0xa8): 1200 ticks at 24 MHz
        |
50 microseconds, used by the short-delay spin/block decision
```

The evidence is the [property loader](raw/driver-pmgr-property-loading.disasm), [idle initialization](raw/driver-pmgr-idle-init.disasm), [running-build registration routine](raw/driver-local-ml_processor_register.disasm), and [nanosecond conversion](raw/driver-kernel-ns-conversion.disasm). See the full [local driver analysis](local-driver-notes.md) and [independent review](review.md).

Public XNU supplies a useful cross-check: [CPU registration](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/osfmk/arm64/machine_routines.c#L1624) converts `powergate_latency` as nanoseconds; [the delay decision](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/osfmk/arm64/machine_routines.c#L2719) uses the resulting latency to decide whether to spin. That public revision is not claimed to be this macOS release; the matching local binary is the decisive evidence.

**Do not copy 50000 into Linux's idle metadata.** Linux's `exit_latency` and `target_residency` serve different contracts. Neither a property suffix nor this decoded software parameter establishes the hardware's measured break-even time.

## How the macOS path fits together

There are separate decisions: whether a thread has runnable work; whether a short idle gap should use WFE; how PMGR prepares a core/cluster for WFI; and what the hardware actually powers down. System suspend is another layer.

The public [XNU idle path](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/osfmk/arm64/machine_routines.c) checks a performance-controller WFE recommendation before falling back to its deeper idle context. Locally, `clpc::CLPC::sampleThreadGroups` has a real call to `_ml_update_cluster_wfe_recommendation` at `0xfffffe0009e170a4`. The nearby trace event is `0x328c00c0`, with cluster, old/new recommendation flags and duration as arguments. The existence of this code is established; how frequently it executes under our workload was not measured.

Conversely, seven inspected `requestClusterPowerStates*`, `setCPUDynamicClusterPowerDown`, `disableCluster` and `enableCluster` methods in the active T8103 CLPC image consist of a branch-target hint plus return. This is a narrow result about those functions. It does **not** establish that M1 cannot gate clusters, or that no other PMGR/hardware mechanism does so. See [the disassembly](raw/driver-clpc-cluster-noops.disasm).

The actual PMGR CPU-idle routine has substantial logic, including core/cluster accounting and conditional PMP notification. The T8103 PMGR image also has `cpuComplexIdleEnter` and `_waitAPSCPending` implementations, preserved in [the APSC disassembly](raw/driver-t8103-apsc-idle.disasm). These are useful targets for a later trace; static branches alone do not show which conditions occur in a live idle interval.

The [local kernel instruction landmarks](kernel-wfi-notes.md) also preserve the callback-before-WFI sequence and a distinct non-returning shutdown helper. The ordinary WFI call and explicit disable-retention shutdown must not be conflated. Nearest-export names printed for stripped internal functions are not reliable function names.

### Concrete lead: last-core idle versus an outstanding frequency transition

The driver data flow narrows this to a specific experiment:

- `ApplePMGR::_cpuIdle` decrements the cluster's active count on entry and detects a previous count of one. Its transition path dispatches vtable offset `+0xf78`, which resolves to `cpuComplexIdleEnter` in the T8103 image.
- `cpuComplexIdleEnter` conditionally calls `_waitAPSCPending`. The [skip-flag follow-up](local-driver-skipflag-followup.md) resolves the controlling initialization to feature 2, `cpu-tvm`. This property is absent from the captured provider trees, its default is zero, and the object allocator requests zeroed memory. The checked initialization therefore predicts that this Mac executes the wait. This is a static configuration prediction, not a live read of the private flag.
- The wait routine polls bit 31 of register selector `0xE20020`, obtaining two successful clear observations. The selector and provider-resource mapping resolve to **`0x210e20020` for E cores and `0x211e20020` for P cores**.
- These match the DVFS command register used by Linux. Its [pinned frequency driver](https://github.com/AsahiLinux/linux/blob/77cb8f24c2381a8abb7272d7bbdec548d6426a8a/drivers/cpufreq/apple-soc-cpufreq.c) defines command offset `0x20` and busy bit 31, waits for a previous command before submitting another, writes the new command, and returns. The [checked idle routine](https://github.com/AsahiLinux/linux/blob/77cb8f24c2381a8abb7272d7bbdec548d6426a8a/drivers/cpuidle/cpuidle-apple.c) contains no explicit matching command-register wait or last-core accounting.

This is a **static implementation difference**, not proof that Linux needs the same wait. Other synchronization or hardware behavior may make it unnecessary; macOS may be waiting for a different subsequent operation. The next probe should establish whether BUSY overlaps Linux last-core deep-idle entry, confirm the statically predicted macOS branch, and determine whether the difference changes completed state transitions or energy. It must not insert an unbounded busy loop into a Linux idle handler. The raw register accesses have not been issued from macOS user space.

The [Linux concurrency review](linux-dvfs-idle-concurrency.md) checks 17 relevant files at both pinned kernel revisions. A request can be outstanding as the submitting CPU becomes idle; with schedutil fast switching, another cluster can also submit a request through the remote idle-load-balancing path. Apple's `dvfs_possible_from_any_cpu` permits that writer. The inspected locks serialize frequency requests but do not wait for the new request's hardware completion or exclude cpuidle. These are source-permitted timelines, not observed failures. They also explain why simply copying a BUSY-clear loop would be incomplete: another CPU may submit a new command after the check. The report specifies the smallest C/AArch64 observation seams and the mapping/lifetime/observer-effect constraints for a later patch.

Exact-symbol and address searches (`_waitAPSCPending`, `cpuComplexIdleEnter` with APSC, and `210e20020` with idle) found no indexed public explanation in this session. The register and its busy-bit definition are already known. The potential contribution is the **idle-entry ordering relationship**, with hardware validation still required.

## What Asahi and Aurora already implement

| Mechanism | Checked Linux/m1n1 status | Research boundary |
|---|---|---|
| Ordinary WFI / clock gating | Implemented | Verify selection and wakeup frequency on native Linux |
| Returning state-losing deep WFI | Implemented in the identical Asahi/Aurora `apple_idle` driver | Driver residency is not independent proof of physical rail-off time |
| APSC and snooze boot setup | Present in m1n1, with equivalent M1 initialization in Aurora | Compare runtime transitions, not just initial register values |
| Non-returning deeper sleep / stop and restart primitives | Present in m1n1 | Missing a validated Linux runtime save/restart/coordination contract in the checked path |
| PSCI via EFI proposal | Existing WFI/deep-WFI states in checked revision; CPU_OFF unsupported | An interface/upstreaming effort, not demonstrated additional battery savings |

The common Linux driver declares WFI exit/target times of 1/1 microseconds and CPU PD exit/target times of 10/10000 microseconds. These are **declared policy metadata**, not this session's measurements. It saves registers and calls the CPU PM notifier path before setting `CYC_OVRD` WFI mode bits 25:24 and entering WFI. The returning path differs from m1n1's non-returning sleep that additionally handles `ACC_OVRD`, retention disablement and restart from a reset vector.

Sources and precise differences are in [the Asahi baseline report](asahi-known-gaps.md) and [the Aurora comparison](aurora-cpu-idle.md), including immutable commits, exact file hashes, PR evidence and search limits. Aurora's experiments on T8140/J700 must not be transferred to this base M1.

## What we actually measured

The final collector is [plain C](tools/ioreport.c), using CoreFoundation C and the existing IOReport interface. It ran as the normal user, with no sudo. The workload uses a [C controller](tools/idle-pulse.c) and [custom ARM64 assembly](tools/idle-burst.S), reading `CNTVCT_EL0` and executing bounded arithmetic bursts. It writes no privileged registers. An earlier Objective-C collector remains for comparison; both inventories matched all **7,749 channel identities and metadata**.

The final capture ran for **32.481 seconds**. It included ambient intervals and two eight-second pulse phases, with a nominal 500-microsecond burst every 10 milliseconds. Only one-second samples entirely contained within each phase were used below:

| Phase | Fully contained samples | E-cluster IDLE | P-cluster IDLE |
|---|---:|---:|---:|
| Ambient before | 4 | 43.55% | 78.58% |
| User-priority pulses | 7 | 40.28% | 63.16% |
| Ambient between | 3 | 37.47% | 64.32% |
| Background-priority pulses | 7 | 42.13% | 65.96% |
| Ambient after | 7 | 43.03% | 73.30% |

This was an interactive Mac with uncontrolled background activity, not a quiescent or equal-work power benchmark. During the user-priority phase the probe delivered 800 bursts and about 0.401 seconds of busy time. During the background phase it delivered only 136 bursts and about 0.069 seconds of busy time, skipping 666 expired schedule slots. Median timer lateness was about 1.9 ms versus 62.2 ms. The probe deliberately skips missed periods instead of generating catch-up load. Thus these phases **cannot establish which policy saves more energy for equal completed work**. Timer scheduling/coalescing and competing work are confounders, not measured hardware wake latency.

SoC `SLP_S2R` and `DEEP_WAIT` reported zero active residency and zero transitions throughout. The CPU IDLE channels changed many times while the machine remained awake. `AWAKE` reported about 99.942% active with zero transitions; its tiny inactive residue is not evidence of actual sleep episodes.

The CPU interface exposes **one undifferentiated IDLE bin**. It does not tell us whether each interval was shallow WFI, deeper WFI, or reset-based cluster shutdown. ECPM/PCPM IDLE bins were zero and are not usable substitutes. PMP OFF/ON describes the PMP coprocessor, not host CPU shutdown. Raw PMGR counters are preserved, but the CPU device IDs do not appear as a straightforward set of corresponding `DEV###` channels in this inventory; a numeric-name match is insufficient for a gating claim.

Data: [raw paired capture](raw/ioreport/paired-c-assembly.jsonl), [workload timing](raw/ioreport/paired-c-assembly-phases.json), [phase summary](raw/ioreport/paired-c-assembly-summary.json), and [telemetry caveats](telemetry-notes.md). The collector itself creates reporting activity and periodic wakeups. No power-saving percentage follows from this experiment.

## The next implementation experiment

The ThinkPad T480 running Linux is suitable as an external m1n1 host. It handles USB proxy/serial and host-side tooling; it need not have an Apple or ARM processor. A USB-A-to-USB-C **data** cable is a straightforward option, with USB-C on the Mac. The official [m1n1 guide](https://asahilinux.org/docs/sw/m1n1-user-guide/#proxy-mode) documents Linux `/dev/ttyACM*` interfaces and cross-compilation.

The first experiment should answer one narrow question: **does macOS synchronize the final core's idle entry with an outstanding DVFS transition in a situation the checked Linux path handles differently?** Deeper reset-based cluster sleep is a subsequent, larger implementation target.

1. Reuse the earlier native Linux captures recovered from the T480. All eight CPUs entered software CPU PD, and a menu/teo ABBA comparison found no measurable energy benefit. The [saved summary](t480-references/evidence__alarm-cpu-idle-03-summary.json) establishes this baseline, not current physical residency. On the next Linux boot, refresh kernel/DT/m1n1 identity and relevant controls; do not repeat generic governor experiments without a new hypothesis. The read-only [audit tool](tools/linux-idle-audit.py) is available for that refresh, but was only syntax-checked in this session.
2. Qualify the T480 USB proxy, serial capture and recovery before a state-changing experiment. A proxy connection is not yet a working hypervisor guest or a validated wakeup path.
3. The [initial PMGR CPUIdle trace](live-mac-trace.md) has now captured `0x27001001/2`; the five-second window contained no CLPC WFE recommendation event `0x328c00c0`. A [retrospective performance-request correlation](mac-ktrace-perf-request-correlation.md) provides a predeclared timing comparison for a controlled Mac-only repeat. The next trace must still resolve the conditional APSC wait and DVFS command registers `0x210e20020`/`0x211e20020`. Record last-active-core transitions, command submission/BUSY completion, WFI entry/exit and wake source. Establish whether the wait executes before assigning a hardware consequence.
4. Implement one selected mechanism behind an opt-in, default-off experimental Linux/firmware path. For full-state-loss sleep, define CPU/cluster state preservation, reset-vector re-entry, timer/interrupt restoration, last-core coordination, pending-wakeup races and firmware ownership before enabling the state. A plain `WFI` replacement is insufficient.
5. Validate wake correctness and latency, then measure energy **natively**, with matched completed work and documented USB/display/charging/thermal conditions. Hypervisor and USB activity can alter the idle states being studied.

The [current m1n1 macOS guest guide](https://asahilinux.org/docs/sw/m1n1-hypervisor/#supported-macos-versions) supports macOS 13.5 and 14.8.3; **macOS 27 is not a documented supported guest**. The existing boot stub must not be mistaken for a full supported macOS research installation. Guest compatibility or a separate supported research installation must be resolved before using the local macOS 27 binary as a hypervisor target. No reboot, boot-policy change, kernel installation or hardware-register write was performed in this investigation.

The [hypervisor validity audit](trace-validity.md) identifies concrete interference: ACC writes are suppressed, full shutdown is substituted with guest-CPU exit, CPU-state readback can be rewritten, and timers/proxy activity change idle opportunities. Returning deep WFI is intentionally permitted; it would be wrong to claim all deep WFI is blocked. Stock asynchronous MMIO records also lack target timestamps. Use a hypervisor trace to diagnose control flow and access ordering, with explicit forwarded/suppressed-operation records. Validate physical residency, latency and energy separately under native Linux.

The [native observable audit](idle-observable-audit.md) nominates PCPM's PMGR state register at **`0x23b700048`**, with **ACTUAL in bits7:4**, for a sparse read-only capture from an E core using the already-owned PMGR regmap. This can independently report PMGR's current state for that controller. It does not by itself establish full-cluster rail-off or time in a particular idle depth. The low nibble is DESIRED state; confusing it with ACTUAL would invalidate the experiment. Reading `cpu-impl-reg+0x100` is a worse first choice because its interpretation is narrower and access can disappear after the last core stops.

## Earlier native evidence recovered from the T480

The T480 holds an earlier native Linux investigation. This public repository retains selected [sanitized summaries](t480-references/evidence__alarm-cpu-idle-03-summary.json), not its private working tree. These are historical experiments, not measurements repeated during this macOS session.

- The 120-second native capture reports software CPU PD time of 85.5–91.0% on E cores and 99.1–99.6% on P cores. The separate 15-second trace had simultaneous software PD intervals; neither measure independently establishes physical rail-off time.
- The menu/teo ABBA windows average approximately 3.8630/3.8648 W. That experiment found no measurable benefit from the governor switch.
- Later OSD and display experiments are documented as completed: removing hidden OSD wakeups had no material energy result; display-off changed whole-machine discharge by about 1.521 W. The latter includes the display/compositor response and is not CPU-only power.
- The earlier base-M1 PMP-v1 investigation checked protocol fields and ATC report IDs. Those are prior local results, not discoveries of this session; their complete underlying evidence is not published here.

This closes a potential false lead: Linux selecting its advertised deep-idle state is already demonstrated on this Mac. The unresolved issue is the hardware effect and ordering of that entry, not simply whether the `apple_idle` driver exists.

## Reproduction and evidence boundaries

From this directory, compile the verified normal-user tools:

```sh
clang -std=c11 -O2 -Wall -Wextra -Werror tools/ioreport.c -framework CoreFoundation -o tools/ioreport-c
clang -O2 -Wall -Wextra tools/idle-pulse.c tools/idle-burst.S -o tools/idle-pulse
tools/ioreport-c '@idle' 6 1 > raw/ioreport/recheck.jsonl
```

The tool sandbox prevented subscriptions and IORegistry access, while ordinary user execution outside that sandbox worked. This is separate from gaining macOS kernel privilege. `powermetrics` was not used: noninteractive sudo required authentication. The physical wake/energy question remains unresolved; the saved evidence gives a specific way to pursue it.

Full IORegistry dumps contain machine identifiers and are omitted from this public repository. The compressed/decompressed Apple binaries were inspected locally; the report preserves hashes and focused disassembly rather than publishing the complete binaries.

## T480 connection status

A ThinkPad T480 running Linux is available as an external host for future USB proxy work. A USB-A-to-USB-C cable supplies power, but ordinary macOS did not enumerate a m1n1 proxy serial interface on the T480 during this check. That is expected without m1n1 proxy mode and does not validate the cable's data path. The current m1n1 checkout used for read-only comparison was pinned at `06a4601a351ebfd1abb6abba9a44c34e40d94776`; no current boot artifact was qualified. Recheck connection, kernel identity, and boot configuration before any native or hypervisor experiment.
