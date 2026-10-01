# Base-M1 CPU idle: public baseline and defensible research gaps

Research date: 2026-10-01 (Asia/Kolkata). Target supplied by local investigation: MacBook Air J313 / T8103, macOS 27 build 26A428. This report separates published source behavior from hypotheses about the current macOS binary. It does not establish native Linux runtime behavior or hardware power savings.

## Main result

Asahi already controls M1 CPU clock gating and a returning deep-WFI mode that permits CPU register-state loss. It also has lower-level firmware routines for deeper, non-returning core/cluster sleep. The remaining useful target is the exact macOS policy, register sequencing, cluster coordination, and restart contract for those deeper states—not rediscovering WFI, `CYC_OVRD`, or the existence of power gating.

The local binary investigation now establishes a concrete unit mismatch worth preserving: `cpu-power-gate-latency-us` has raw value 50000, is copied unchanged into `ml_processor_info.powergate_latency`, and the matching running XNU converts that number as **nanoseconds**. The resulting software latency parameter is **50 us**, despite the ADT name's `-us` suffix. This does **not** measure hardware exit latency or prove a 50 us idle-entry threshold. Public-source searches below found no prior explanation of this precise path, but cannot establish universal novelty.

## Pinned baseline

| Source | Revision / status checked live |
|---|---|
| AsahiLinux/linux `asahi` | `77cb8f24c2381a8abb7272d7bbdec548d6426a8a` (head commit dated 2026-08-20) |
| AsahiLinux/m1n1 `main` | `3e354a2467f4f724f254362626cae0633918e0c1` |
| m1n1 PR #618, PSCI via EFI | Open draft; head `d30913b713a4c0e86935f8a9919ec099d495929b` |
| m1n1 PR #670, PMP v1 | Open, non-draft; head `3ea0198a77d9164f374450e58c8268e397be5b7e`; no comments or review comments returned by API |
| Apple open-source XNU | `f6217f891ac0bb64f3d375211650a4c1ff8ca1ea` |

Repository metadata and source files were fetched using read-only GitHub API requests. The XNU source revision is a public reference, not an assertion that it matches macOS 27 build 26A428. The Asahi `asahi` branch is a specific checked baseline; other development branches or unposted work may differ.

## What Linux already does

The [pinned Apple cpuidle driver](https://github.com/AsahiLinux/linux/blob/77cb8f24c2381a8abb7272d7bbdec548d6426a8a/drivers/cpuidle/cpuidle-apple.c) registers `apple_idle` on T8103 and provides two states. Both participate in ordinary idle and suspend-to-idle:

| Driver state | Implementation | Declared exit latency | Declared target residency |
|---|---|---:|---:|
| `WFI`, CPU clock-gated | `cpu_do_idle()` | 1 us | 1 us |
| `CPU PD`, CPU/cluster powered down | CPU PM save/restore around `apple_cpu_deep_wfi()` | 10 us | 10000 us |

These are driver metadata, not measurements taken on this machine. In particular the `CPU PD` name does not establish how often the entire cluster actually loses power.

The deep routine saves x18–x30 on the stack, sets bits 25:24 of `S3_5_C15_C5_0` to 3, executes `DSB SY` and `WFI`, loops until `ISR_EL1` reports an interrupt, clears bit 24, and restores saved registers. CPU PM notifiers handle floating-point and other state. This is already public working code, so implementing the same bit flip again would not be a new discovery.

The [pinned m1n1 register definitions](https://github.com/AsahiLinux/m1n1/blob/3e354a2467f4f724f254362626cae0633918e0c1/src/cpu_regs.h#L523) name `S3_5_C15_C5_0` as `CYC_OVRD`: WFI mode occupies bits 25:24, while bit 0 is `DISABLE_WFI_RET`. [CPU initialization](https://github.com/AsahiLinux/m1n1/blob/3e354a2467f4f724f254362626cae0633918e0c1/src/chickens.c#L247) establishes WFI mode 2, enables WFI retention, unmasks external IRQ/FIQ modes, and enables branch-prediction-state retention through `ACC_CFG` bits 3:2. The M1 feature table declares these Apple registers unlocked.

The [2021 Asahi report](https://asahilinux.org/2021/03/progress-report-january-february-2021/) had already described M1's autonomous choice between clock gating and power gating, register loss, and using an override to make ordinary Linux WFI retain its expected state. Thus the automatic heuristic itself is also known; its exact current policy and hardware consequences remain possible research targets.

CPU frequency control is a separate implemented path. The [pinned cpufreq driver](https://github.com/AsahiLinux/linux/blob/77cb8f24c2381a8abb7272d7bbdec548d6426a8a/drivers/cpufreq/apple-soc-cpufreq.c) writes cluster DVFS command offset `0x20`, handles T8103's two pstate fields, and reads actual pstate from status offset `0x50`. Frequency selection must not be mistaken for idle-state selection.

## Deeper sleep is known, but lacks the same Linux return contract

[m1n1 `cpu_sleep(true)`](https://github.com/AsahiLinux/m1n1/blob/3e354a2467f4f724f254362626cae0633918e0c1/src/utils.c#L249) does considerably more than returning `deep_wfi()`. For M1's `SLEEP_GLOBAL` mode it programs `ACC_OVRD` (`S3_5_C15_C6_0`) with:

- `PWR_DN_SRM(3)`, bits 14:13;
- `DIS_L2_FLUSH_ACC_SLEEP(2)`, bits 16:15;
- `TRAIN_DOWN_LINK(3)`, bits 18:17;
- `POWER_DOWN_CPM(3)`, bits 26:25;
- `DISABLE_PIO_ON_WFI_CPU`, bit 32;
- `DEEP_SLEEP`, bit 34.

It then selects WFI mode 3 and **disables retention with bit 0**, entering an `ISB; WFI` loop with no ordinary return path. The names are Asahi's source definitions; they are not independent silicon documentation.

[m1n1 SMP support](https://github.com/AsahiLinux/m1n1/blob/d30913b713a4c0e86935f8a9919ec099d495929b/src/smp.c) also knows the T8103 CPU-start block offset `0x54000` within PMGR. It requests core stop through the block's `+0x0` bitmap, arranges sleep on that core, and notes that powering down the last core in a cluster makes its register interface inaccessible. Core startup establishes RVBAR and writes the `+0x4` system-active bitmap and `+0x8 + 4*cluster` core-start bitmap. [Asahi's SMP documentation](https://asahilinux.org/docs/hw/cpu/smp/) describes these startup registers as well.

The important gap is not a lack of any deep-sleep code. It is a validated OS runtime contract: where a fully stopped CPU restarts, which CPU/cluster/interrupt/cache state must be saved and rebuilt, who owns that state, how wakeups are synchronized, and whether the transition saves energy for the predicted idle interval.

The checked [T8103 Linux DTS](https://github.com/AsahiLinux/linux/blob/77cb8f24c2381a8abb7272d7bbdec548d6426a8a/arch/arm64/boot/dts/apple/t8103.dtsi) still uses `spin-table` CPU bringup. It does not provide a finished firmware CPU-off/on runtime service through this boot protocol.

## PSCI via EFI is an interface proposal, not a demonstrated battery fix

The [July 8 RFC cover letter](https://lkml.rescloud.iu.edu/hypermail/linux/kernel/2607.1/00279.html) explains the problem: Apple Silicon lacks EL3, and Linux wants EL2 for KVM. Full-state-loss idle needs firmware assistance, but the standard higher-privilege PSCI conduits are unavailable. The proposed EFI mapping supports a direct atomic-safe firmware call.

The [pinned PR #618 `psci.c`](https://github.com/AsahiLinux/m1n1/blob/d30913b713a4c0e86935f8a9919ec099d495929b/src/psci.c) only dispatches suspend state 0 to ordinary WFI and state 1 to `deep_wfi()`. `CPU_OFF` returns `NOT_SUPPORTED`; this is not a finished full-power-off/hotplug implementation. The accompanying [T8103 DTS RFC](https://lists.openwall.net/linux-kernel/2026/07/08/527) describes ordinary WFI and deep WFI, the latter with 5 us entry, 5 us exit, and 10000 us minimum residency.

The [PR author explicitly cautioned](https://github.com/AsahiLinux/m1n1/pull/618) that the work re-expresses existing downstream functionality and does not yet improve battery life. It currently needs extra kernel patches and direct kernel loading rather than U-Boot. September discussion shows [acceptance of the conduit was still contested](https://lkml.iu.edu/2609.0/07554.html); the [author describes U-Boot integration as later work](https://lkml.iu.edu/2609.0/08450.html). This should not be installed as a presumed power fix.

## The local 50000 property: promising conversion boundary, no novelty yet

The local investigation found `cpu-power-gate-latency-us = 50000` (`50 c3 00 00`). The same property and value already occur in researchers' published [iPhone12,3 / 17C54 dump](https://gist.github.com/bazad/1faef1a6fe396b820a43170b43e38be1) and [j82ap dump](https://gist.github.com/zhuowei/715ded46d018cc7d05265e58d6a65083). Its name or numeric presence is not novel.

A [pinned direct symbol anchor from blacktop](https://github.com/blacktop/symbolicator/blob/9971f6a2e4b8eb2801548eeedc42a0327c88d838/kernel/25.6/kexts/ApplePMGRBringupV2.json#L3404) associates this string with `CPUManager::initCPUIdle(ml_processor_info*)`, through `SystemProp::getDTProperty(char const*, unsigned int*)`. This older reconstruction supplied a search lead. The local binary investigation independently followed the current `ApplePMGR::_cpuIdleInit` path.

Apple's own [AppleARMSMP.cpp](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/iokit/Kernel/arm/AppleARMSMP.cpp#L197) calls `gPMGR->initCPUIdle(&this_processor_info)` before registering each CPU, then connects callbacks to `gPMGR->enterCPUIdle()` and `exitCPUIdle()`. The corresponding [XNU registration code](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/osfmk/arm64/machine_routines.c#L1624) converts `powergate_latency` using `nanoseconds_to_absolutetime`. Its [delay decision](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/osfmk/arm64/machine_routines.c#L2719) uses that duration to choose whether to spin instead of block.

The local analysis matched the running kernel UUID `1F15A5DA-11D6-39EE-88D2-153E2F90F066`, XNU `13432.1.9~1`, T8103, to the inspected kernelcache. It followed the raw property's storage into the PMGR object and its unchanged copy from PMGR object offset `+0x2684` into `ml_processor_info +0x54`. The [local `ml_processor_register` disassembly](raw/driver-local-ml_processor_register.disasm) then shows:

- `0xfffffe000bce8164`: 32-bit load from processor-info offset `+0x54`;
- subsequent inline arithmetic matching `_nanoseconds_to_absolutetime`;
- `0xfffffe000bce81b4`: store of the converted value into CPU-data offset `+0xa8`.

Thus the binary data flow agrees with the public XNU unit contract. The raw ADT number does not represent 50 milliseconds at this software interface. No physical wakeup latency was measured, and this static data flow is not proof that the parameter determines when a core is gated.

The remaining work is:

1. Preserve the complete PMGR property-to-structure disassembly alongside the XNU consumer for reproducibility.
2. Follow other consumers before treating it as an idle threshold.
3. Separately measure actual transition behavior. Linux `target_residency` and `exit_latency` are different contracts and cannot safely be replaced by this ADT number.

A GitHub code search for this exact property restricted to `org:AsahiLinux` returned no results on the research date. That is only a bounded search result, not proof that Asahi developers do not know its semantics.

Independent novelty queries performed on 2026-10-01:

| Search | Result |
|---|---|
| GitHub code: `"cpu-power-gate-latency-us" org:AsahiLinux` | No matches |
| GitHub code: `"cpu-power-gate-latency-us" "powergate_latency"` | No matches |
| GitHub code: `"cpu-power-gate-latency-us" "nanoseconds"` | No matches |
| GitHub code: `"_cpuIdleInit"` | No matches |
| Web: exact property plus `nanoseconds`, `50us`, or `_cpuIdleInit` | No relevant prior semantic explanation returned; older raw dumps were returned |

This establishes only that this bounded public search did not locate the precise unit-conversion analysis. Public code indexing may omit branches, gists, recent updates, and binary-only research; it cannot establish universal novelty. The local binary evidence establishes the specific conversion path on this build; it does not establish that the observation is unknown to Asahi maintainers.

## Best local observations to gather without privilege changes

| Observation | What it can establish | What it cannot establish alone |
|---|---|---|
| Exact ADT CPU/PMGR fields and raw bytes | Firmware-provided topology, IDs, state tables, candidate policy values | Actual register programming or transitions |
| Exact macOS/kernel/PMGR driver identities and hashes | Reproducible target and cross-version comparison | Binary behavior from names alone |
| CPU IOReport state-residency and transition deltas during controlled idle/wakeup intervals | Which reported states change, how often, and with which workload cadence | Whether a label means physical core/cluster rail off |
| PMGR `CLK`, `PWR`, `DEV`, `EVT` counter mapping to ADT entries | Candidate independent clock/domain activity indicators | Counter-ID semantics or units without validation |
| A sweep of wakeup intervals around 1/5/10/20/50/100 ms at fixed short work duration | Policy crossover hypotheses and reproducible residency curves | Causality from one trace, or equivalence to Linux cpuidle states |
| PMGR init/idle binary cross-references and explicit loads/stores | Current driver transformations and a narrow implemented mechanism | Safe transplant into Linux without a state-save/resume design |

Preserve full timestamped raw samples. Record background CPU load, assertions, display state, AC/battery state, thermal state, and sampling overhead. Keep samplers light enough that their own wakeups do not dominate the idle interval. Native Linux validation ultimately needs its own baseline and telemetry; the macOS experiment establishes the reference behavior.

The pinned ADT parser is [public m1n1 source](https://github.com/AsahiLinux/m1n1/blob/3e354a2467f4f724f254362626cae0633918e0c1/proxyclient/m1n1/adt.py#L53): 48-byte device entries, 24-byte clocks/power-domain/event entries, and 12-byte `ps-regs` entries. Device IDs use `id1` or `id2` according to the tree layout. Device register address is the selected PMGR register base plus `ps-regs[psreg].offset + 8*psidx`. Numeric IOReport counter names should be matched empirically before assigning them to these IDs.

## Secondary context: PMP and system-level idle

[Asahi's April 2026 report](https://asahilinux.org/2026/04/progress-report-7-0/) distinguishes PMGR power domains from PMP coordination and explicitly says the base M1 uses an older incompatible PMP variant. Its approximately half-watt improvement was measured on a 14-inch **M1 Pro**, not this M1 Air. The checked [Linux PMP driver](https://github.com/AsahiLinux/linux/blob/77cb8f24c2381a8abb7272d7bbdec548d6426a8a/drivers/soc/apple/pmp.rs#L402) matches `apple,t6000-pmp-v2` only.

[PMP v1 PR #670](https://github.com/AsahiLinux/m1n1/pull/670) already publishes endpoint `0x20`, 64 KiB shared-memory monitoring, configuration messages, device-power messages, tentative state-change messages, and copying `energy-model-dram-configs` from the PMP ADT nub. The code and mappings are an existing baseline. PMP may affect system/fabric idle, but it is not interchangeable with CPU idle policy, and its state labels cannot prove CPU rail state.

## What would count as a useful new result

A candidate contribution would be a reproducible, version-pinned result connecting a specific macOS condition to a specific register or firmware action and then to an independently observed CPU/cluster state change, with a Linux implementation contract and measured wakeup correctness/energy benefit. The 50000 property's conversion is now a concrete static finding; its practical use still needs to be connected to decisions and transitions. Other targets include distinguishing retention versus reset-based cluster-off telemetry or isolating a required wakeup/restore step absent from the checked Linux path.

No observation in this report alone proves a new Linux power-saving mechanism. An exhaustive statement that “Asahi has never discovered this” is not supportable from public searches; unmerged branches, IRC research, and private experiments may already contain it. The defensible wording is a finding absent from the specifically searched published baseline, with exact supporting artifacts and remaining tests.
