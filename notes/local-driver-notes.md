# Local M1 CPU idle driver investigation

Date: 2026-10-01. Scope: static inspection of the installed macOS kernelcache, public Apple XNU source, and read-only IORegistry/sysctl snapshots. No live kernel-memory access, MMIO access, driver calls that alter state, boot changes, or kernel patches were performed. These findings establish code paths and identify useful experiments; they do not establish hardware residency, energy savings, or priority over prior Asahi research.

The two most useful results are a verified unit mismatch in a legacy device-tree property name, and a conditional last-active-core idle handshake that waits on the CPU DVFS command register. A separate result prevents assuming that all generic XNU cluster-power APIs are implemented by the base M1's CLPC driver.

## Provenance and reproduction

The selected on-disk kernelcache's embedded kernel UUID matches the running kernel UUID exactly. This is substantially stronger provenance than finding a plausible file under Preboot. It establishes the kernel build; the inspected kexts are the associated fileset entries, rather than a live-memory dump.

| Item | Observed value |
|---|---|
| macOS build | `26A428` |
| Kernel | Darwin 27.0.0, `xnu-13432.1.9~1/RELEASE_ARM64_T8103` |
| Running and embedded kernel UUID | `1F15A5DA-11D6-39EE-88D2-153E2F90F066` |
| Boot arguments | `-v` |
| ApplePMGR UUID | `D750E484-C320-391D-8C95-CF98C44FBBBC` |
| AppleT8103PMGR UUID | `3D9EFDB5-AAF0-3474-9A5A-C6F62BAE953A` |
| AppleT8103CLPCv3 UUID | `A72F5D6F-6A8C-3D09-9773-39348D1E68A3` |
| IMG4 input SHA-256 | `e5e3b35cca34477d287a447bd1aa7a84f02f8543287b8db2eef722710e95a349` |
| Decompressed SHA-256 | `d196456a0809aca37bbf5918eb633cf8ada9000c48f4c0082ca8f61c86b2866b` |
| Compressed / decompressed bytes | 32,728,017 / 122,945,536 |

Evidence: [running identity](raw/driver-running-kernel-identity.txt), [input path and hashes](raw/driver-kernelcache-metadata.json), [fileset entries and UUIDs](raw/driver-fileset-metadata.json), [selected image UUIDs](raw/driver-image-uuids.json).

[driver-kernelcache-inspect.py](tools/driver-kernelcache-inspect.py) parses the local IMG4/IM4P container and uses macOS `libcompression` to decompress the unencrypted LZFSE payload with a 256 MiB bound. It was run successfully and reproduced the digest above. Optional analysis views replace the copied container's header with an embedded Mach-O header while preserving every original file offset. These copies are for static analysis only. They allow Command Line Tools `llvm-objdump --macho -d --dis-symname SYMBOL VIEW` to work on a fileset entry; the kernel additionally needs `--section=__TEXT_EXEC,__text`. The extracted disassembly and metadata below are preserved in this directory; large decompressed copies are temporary `/private/tmp/m1-power-*.macho` files.

All addresses below are **unslid static image virtual addresses**. For brevity, addresses in tables omit the common `fffffe000` prefix. They are not live process addresses or permission to dereference them.

## 1. The `-us` latency property reaches a nanosecond consumer

The local PMGR device-tree property `cpu-power-gate-latency-us` contains bytes `50 c3 00 00`, the little-endian integer **50000**. Reading its suffix literally would suggest 50 milliseconds. The checked binary passes that integer unchanged to an XNU field converted from **nanoseconds**: the corresponding threshold is **50 microseconds** (1200 absolute-time ticks at the machine's 24 MHz timebase).

This is a software policy/input-unit result. It is **not** a measurement of hardware power-gate entry or wake latency, and the private live `cpu_data` value was not read.

| Step | Exact static evidence |
|---|---|
| Default table | ApplePMGR constructor copies `0x380` bytes (28 rows of 32 bytes) from VM `8228588`, full-file offset `0x1224588`, into `this+0x2668`. Row 0 names `cpu-power-gate-latency-us`; its initial value is zero. |
| Property load | Start's parameter loop calls `SystemProp::getDTProperty`; that function copies the OSData's 32-bit value without scaling. The row-0 value lands at `this+0x2684`. Scaling branches apply to other parameter IDs, not row 0. |
| Override review | The same property can be a boot-argument override; recorded boot arguments contain only `-v`. The generic `setProperties` writer skips row 0 because its alias/symbol pointer remains null. This is not a proof that no unobserved private memory mutation could occur. |
| PMGR callback | `ApplePMGR::_cpuIdleInit(ml_processor_info*)` at `9b1a2bc`: `ldr w8,[x20,#0x2684]` at `9b1a34c`; `str w8,[x19,#0x54]` at `9b1a350`. |
| Actual M1 dispatch | `AppleT8103PMGR` vtable address point `82f2c98+0x10`, slot `+0x9d8`, resolves to that inherited `_cpuIdleInit`. |
| Registration wrapper | `AppleARMCPU::start` passes its structure at `sp+0x20` through `function-cpu_idle` command `0x10` at `8bdef44`. There is no intervening write to `sp+0x74` (structure `+0x54`) before `ml_processor_register` at `8bdf050`. `ApplePMGRFunctionCPUIdle::callFunction` dispatches command `0x10` through vtable slot `+0x9d8`. |
| Local XNU consumer | `_ml_processor_register` at `bce8078` loads structure `+0x54` at `bce8164`, applies the **inlined** nanoseconds-to-absolute-time conversion, and stores the result at CPU data `+0xa8` at `bce81b4`. The arithmetic matches the exported local `_nanoseconds_to_absolutetime` implementation at `bceede4`. There is no direct call instruction here; the conversion is inlined. |

Evidence: [parameter rows and bytes](raw/driver-pmgr-parameter-table.json), [constructor/property loading](raw/driver-pmgr-property-loading.disasm), [PMGR callback](raw/driver-pmgr-idle-init.disasm), [independent registration-wrapper extraction](raw/review-registration-wrapper.disasm), [local registration consumer](raw/driver-local-ml_processor_register.disasm), [local conversion implementation](raw/driver-kernel-ns-conversion.disasm), [independent review](review.md).

The public Apple XNU source independently explains the field: `ml_processor_register` calls `nanoseconds_to_absolutetime(in_processor_info->powergate_latency, &cpu_data_ptr->cpu_idle_latency)`, and `ml_delay_should_spin` compares an interval against `cpu_idle_latency`. This public source is supporting semantic evidence, not an assertion that its revision equals the private running build. Pinned public source: [machine_routines.c](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/osfmk/arm64/machine_routines.c) and [machine_routines.h](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/osfmk/arm64/machine_routines.h).

The public symbolicator anchor identifying the property reader as CPU idle initialization was a useful lead, not proof of the units. The local load/store, wrapper, vtable, and consumer analysis supply that proof. Other fileset entries contain a newer `cpu-power-gate-latency-ns` string; this corroborates a naming concern but cannot by itself establish semantics for the active legacy driver.

## 2. Conditional last-active-core idle wait on the CPU DVFS command register

The M1's active PMGR dispatch contains a **conditional pre-idle wait** on bit 31 of the same CPU DVFS register family that Linux cpufreq accesses. The checked path is tied to the transition from one active core to zero within a cluster. It therefore provides a concrete target for a macOS-versus-Linux trace comparison.

### Call path and condition

`ApplePMGR::_cpuIdle(CPUCore*, bool, uint64_t*)` starts at `9b195f0`. On idle entry it uses the prior cluster active count from cluster state `+0x64`, decrements it, and tests the prior count against 1 (`9b19954`). The one-to-zero path sets a transition flag at `9b19ad0`; other paths clear it. Conditional dispatch at `9b19e64` uses vtable slot `+0xf78`. The actual T8103 slot resolves to inherited `AppleT8101PMGR::cpuComplexIdleEnter()` at `9e991d8`.

`cpuComplexIdleEnter` **does not unconditionally wait**. At `9e99228`, it reads byte `this+0x73a52`; bit 0 set skips the pending wait. The [skip-flag follow-up](local-driver-skipflag-followup.md) establishes the captured configuration that predicts this flag is clear; it has not read the private flag live. When the flag permits the wait, it selects performance-domain ID 2 for cluster 0 or ID 5 for cluster 1 and calls `_waitAPSCPending` at `9e99248`.

`AppleT8101PMGR::_waitAPSCPending(unsigned char)` starts at `9e98680`. It calls `readACCReg` with logical selector `0xE20020` for the chosen cluster and polls bit 31. Its control flow requires two successful bit-clear passes before returning. Other reads support bookkeeping/diagnostics; a simple string search would not reveal the physical target.

Evidence: [complete PMGR idle function](raw/driver-pmgr-cpuidle.disasm), [idle entry and pending-wait disassembly](raw/driver-t8103-apsc-idle.disasm), [independent last-core dispatch extraction](raw/review-last-core-dispatch.disasm).

### Logical selector to physical mapping

The actual T8103 vtable slot `+0x1148` resolves `readACCReg` to `9ec67a4`. That method chooses one of two nine-row mapping tables, finds the matching base, subtracts the selector base, then calls `ApplePMGR::readReg64`.

| Cluster | Mapping table VM / full-file offset | Table row for `0xE20020` | `initRegMaps` binding | IORegistry resource address | Read target |
|---|---|---|---|---|---|
| E / 0 | `7775734` / `0x771734` | RegMap 9, base `0xE20000` | RegMap 9 → provider resource 5, call at `9ec499c` | `0x210e20000`, length `0x2000` | `0x210e20020`, bit 31 |
| P / 1 | `777577c` / `0x77177c` | RegMap 21, base `0xE20000` | RegMap 21 → provider resource 14, call at `9ec4a74` | `0x211e20000`, length `0x2000` | `0x211e20020`, bit 31 |

The absolute physical addresses come from the captured provider's `IODeviceMemory`, not an assumed bus prefix. `initRegMap` obtains the provider mapping; `readReg64` bounds-checks the offset before the 64-bit mapped read. **No physical register was read during this investigation.** This is static address resolution plus registry metadata.

Evidence: [table bytes, decoded rows, resources and computed addresses](raw/driver-apsc-register-mapping.json), [complete mapping/access disassembly](raw/driver-apsc-register-access.disasm).

**Next useful experiment:** trace the last-core callback condition, skip flag, outstanding DVFS command, two-clear-poll sequence, and ensuing idle entry together on macOS; compare with Linux's cpufreq/cpuidle interleaving. The binary shows a synchronization mechanism worth understanding. It does not prove Linux has a correctness bug, that this mechanism explains an energy gap, or that adding an unconditional busy-wait to Linux would be correct. The skip flag and interrupt/locking context must be resolved before proposing a change.

## 3. Base-M1 CLPC cluster-power methods are stubs

Several tempting CLPC symbols in this exact M1 driver are literally two instructions, bytes `5f 24 03 d5 c0 03 5f d6`: `hint #0x22; ret`.

| Method | Address |
|---|---|
| `clpc::CLPC::requestClusterPowerStates(uint64_t,uint64_t,uint64_t,bool)` | `9dfe2c0` |
| `clpc::CLPC::requestClusterPowerStates(uint64_t)` | `9dfe2c8` |
| `requestClusterPowerStatesForPerf` | `9dfe2d0` |
| `requestClusterPowerStatesForLimits` | `9dfe2d8` |
| `disableCluster` | `9dfe2e8` |
| `enableCluster` | `9dfe2f0` |
| `setCPUDynamicClusterPowerDown` | `9e0e530` |

Evidence: [exact disassembly](raw/driver-clpc-cluster-noops.disasm), independently checked in [review.md](review.md).

This invalidates an inference that simply finding generic XNU powered-core APIs proves these named CLPC operations dynamically shut down clusters on base M1. It does **not** show that automatic hardware cluster gating, other PMGR paths, or other chips lack cluster shutdown. The observed last-core PMGR path above is a separate mechanism.

## 4. CLPC does provide per-cluster WFE recommendations

In `clpc::CLPC::sampleThreadGroups`, local assembly calls `_ml_update_cluster_wfe_recommendation` at `9e170a4`. It detects a boolean policy change, rounds a per-cluster floating duration with `roundf`, converts to unsigned integer, and passes cluster index, duration, and zero flags. A subsequent `kernel_debug` call at `9e170ec` uses event `0x328c00c0` with cluster, old boolean, new boolean, and duration. This is a more promising CPU-idle policy trace target than the stubbed cluster-power symbols.

Evidence: [caller excerpt](raw/driver-clpc-wfe-update.disasm), [local kernel receiver](raw/driver-kernel-ns-conversion.disasm). The public XNU receiver and idle implementation treat this as an absolute-time recommendation; do not label the argument microseconds without conversion. The public `cpu_idle` path includes WFE decisions before the final WFI/platform idle path: [pinned Apple source](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/osfmk/arm64/cpu.c).

The installed PMGR signpost definition also exposes CPUIdle entry/exit trace names; [the captured plist](raw/driver-ApplePMGR.kext-PMGRSignposts.plist.json) and [idle disassembly](raw/driver-pmgr-cpuidle.disasm) provide starting points. These are named tracing surfaces, not evidence that an unprivileged session has access to every event.

## What remains unknown

- The actual hardware idle states/residencies reached on this machine and their energy cost. IOReport's aggregate IDLE values do not identify SRAM retention versus deeper gating.
- The runtime value and provenance of the APSC wait's skip flag, how often the last-core path finds a pending DVFS command, and how macOS coordinates it with interrupt delivery.
- How much of the Linux-versus-macOS idle difference comes from WFE policy, DVFS synchronization, device activity, firmware, or other subsystems.
- Whether any finding is unpublished or unknown to Asahi developers. A local binary finding and a public-source comparison cannot establish that negative.

The earlier `m1-power-lab` status was reviewed to avoid presenting its harness work as a new hardware measurement. Its documented native captures had not yet produced the physical runtime qualification needed to close these questions. This report preserves a narrower, reproducible set of static findings for the next experiment.

## Follow-up: the APSC skip condition is now resolved statically

The [focused skip-flag follow-up](local-driver-skipflag-followup.md) supersedes the unresolved-provenance statements above. The flag is set by nonzero `cpu-tvm` (feature 2), defaults clear through zeroed object allocation, and the captured local PMGR provider has no `cpu-tvm` property. The checked initialization therefore predicts that this M1 takes the pending-APSC wait path. A live private flag read and event-frequency measurement remain unperformed.
