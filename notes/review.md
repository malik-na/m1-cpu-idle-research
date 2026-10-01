# Independent review of the local CPU-idle findings

Reviewed 2026-10-01. Scope: read-only static inspection of the captured M1 kernel collection and registry, with independent decoding of relevant raw bytes. No sampling, load generation, register writes, kernel changes or system configuration changes were performed by this reviewer.

## Verdict

The strongest claim survives review: **the captured `cpu-power-gate-latency-us` value of 50000 reaches XNU's CPU software latency parameter unchanged, and the local kernel consumes that field as nanoseconds.** Its resulting value is therefore consistent with a **50 microsecond delay-spin parameter**, despite the property-name suffix. This is not a measurement of CPU exit latency or the minimum interval required for hardware power gating.

The seven reviewed CLPC cluster-control methods in the local `AppleT8103CLPCv3` image are genuine instruction-level no-ops. This narrows where to investigate the M1 implementation. It does not establish that M1 cannot gate clusters, that macOS never gates them, or that every CLPC method is inert.

## Evidence chain for the software latency parameter

1. The captured registry value is four bytes `50 c3 00 00`, i.e. little-endian 50000. See `raw/cpu-idle-adt.json` and `raw/driver-cpu-idle-registry-extract.json`. The registry also identifies an attached `AppleT8103PMGR` service with `IOMatchedAtBoot=true`, `IOFunctionParent0000007E`, and the CPU's `function-cpu_idle` target phandle is 126 (`0x7e`).

2. ApplePMGR's parameter-table row 0 contains the `cpu-power-gate-latency-us` name; the next two pointer fields, initial validity byte and initial value are zero. I independently checked the raw 32 bytes at kernel-collection file offset `0x1224588` and the name at file offset `0x6c586a`. The constructor at `0xfffffe0009ade794` copies this table to `this + 0x2668`. Row length is `0x20`; the value lies at row `+0x1c`, hence `this + 0x2684` for row 0.

3. `ApplePMGR::getDTProperty` at `0xfffffe0009adf9b8` obtains the property bytes and performs a plain `ldr w8, [x0]` followed by `str w8, [x19]` at `0xfffffe0009adfa38/3c`. The startup parameter loop reads the result at `0xfffffe0009adef14`. Row 0 takes the unchanged-value path to `str w8, [x21, #0x1c]!` at `0xfffffe0009adef7c`. The clamps and cross-parameter adjustments in this loop apply to other indices. There is no multiplication by 1000 on this row's path.

4. `ApplePMGR::_cpuIdleInit` checks row-0 validity and then executes:

   ```asm
   fffffe0009b1a34c: ldr w8, [x20, #0x2684]
   fffffe0009b1a350: str w8, [x19, #0x54]
   ```

   These instructions were also checked directly in the full collection at file offset `0x2b1634c`, where the bytes are `88 86 66 b9 68 56 00 b9`. `x19` is the `ml_processor_info` argument.

5. The actual M1 dispatch path uses this method. `ApplePMGRFunctionCPUIdle::callFunction` recognizes command `0x10` at `0xfffffe0009b288e0` and calls the PMGR vtable slot `+0x9d8`. The `AppleT8103PMGR` vtable at `0xfffffe00082f2c98`, after its 16-byte header, has raw chained pointer `0x8011291e02b162bc` in this slot. Its target is `0xfffffe0009b1a2bc`, the above `ApplePMGR::_cpuIdleInit`. `AppleT8101PMGR` has the same target. This is not an inference from an unused base-class implementation alone.

6. `AppleARMCPU::start` resolves the literal `function-cpu_idle` (at virtual address `0xfffffe000717c2aa`), sends command `0x10`, and passes its `ml_processor_info` structure at `sp + 0x20` to that function at `0xfffffe0008bdef44..58`. It later passes the same structure to `ml_processor_register` at `0xfffffe0008bdf040..50`. I checked the intervening assembly: it sets other callbacks, but does not overwrite `sp + 0x74`, which is the structure's `+0x54` latency member. The command-0x10 function wrapper also does not alter this field after the PMGR callback returns.

7. The local `ml_processor_register` at `0xfffffe000bce8164` loads `w8` from input structure `+0x54`; its arithmetic converts the value with the same nanosecond conversion used by local `nanoseconds_to_absolutetime`, storing the result at CPU-data `+0xa8` at `0xfffffe000bce81b4`. There is no x1000 scaling. With the captured 24 MHz timebase, evaluating the exact multiplication/high-half/shift sequence gives 1200 ticks for input 50000, equivalent to 50000 ns. The calculation also gives 1,200,000 ticks for input 50,000,000, demonstrating that these interpretations differ by precisely 1000.

8. [Pinned public XNU source](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/osfmk/arm64/machine_routines.c) identifies the field assignment as `nanoseconds_to_absolutetime(in_processor_info->powergate_latency, &cpu_idle_latency)` and uses it in `ml_delay_should_spin` as the comparison `interval < cpu_idle_latency`. The local binary establishes the conversion; the source supplies the readable field and consumer semantics. Do not imply that every instruction in the running, newer kernel was checked against a matching source release.

## Overwrite and override challenges

- A boot-argument override exists: the startup loop calls `PE_parse_boot_argn` with the property name and can replace the value. The investigation's captured boot arguments are reported as `-v`, so no latency override was found. This reviewer could not independently re-read `kern.uuid/kern.bootargs` from inside the tool sandbox (`Operation not permitted`), and relies on the main investigation's live identity capture for that assertion.
- ApplePMGR's generic `setProperties` path can update parameter-table rows, so a blanket claim that parameters are immutable would be wrong. However, at `0xfffffe0009ae400c..10` it first requires a nonzero row `+0x10` property symbol. Row 0 begins with that field zero; startup only creates such a symbol if the alternate property-name pointer at row `+8` is nonzero. Row 0 has no alternate name, so this generic property writer skips it.
- `_applyParam` subtracts 1 from its index and accepts only indices 1 through 17; index 0 branches to its return. It does not secretly rescale or refresh the latency value.
- Direct and indexed table accesses were inspected in the ApplePMGR assembly. No later row-0 rewrite or conversion was found. This is a focused static review, not a whole-kernel proof of absence of arbitrary aliasing writes. No live kernel-memory read of the resulting per-CPU field was performed.

## CLPC no-op verification

Each of the following methods is exactly two AArch64 instructions: `hint #0x22` (the branch-target landing instruction) and `ret`, raw bytes `5f 24 03 d5 c0 03 5f d6`.

| Method | Virtual address |
| --- | --- |
| `requestClusterPowerStates(unsigned long long, unsigned long long, unsigned long long, bool)` | `0xfffffe0009dfe2c0` |
| `requestClusterPowerStates(unsigned long long)` | `0xfffffe0009dfe2c8` |
| `requestClusterPowerStatesForPerf` | `0xfffffe0009dfe2d0` |
| `requestClusterPowerStatesForLimits` | `0xfffffe0009dfe2d8` |
| `disableCluster` | `0xfffffe0009dfe2e8` |
| `enableCluster` | `0xfffffe0009dfe2f0` |
| `setCPUDynamicClusterPowerDown` | `0xfffffe0009e0e530` |

I checked the disassembly and independently read these bytes from the full collection using its segment virtual-address/file-offset mapping. The four contiguous request methods reside at full-collection file offset `0x2dfa2c0`; the setter is at `0x2e0a530`. The supported conclusion is specific to these compiled methods and this image.

## Additional review: conditional APSC pending wait during last-core idle entry

The local-driver agent's later APSC finding also survives a focused static check. This is a more direct candidate for a Linux/macOS execution-path comparison than the software latency parameter, but its necessity and effect remain unmeasured.

- `ApplePMGR::_cpuIdle` reads the complex's active-core count from `+0x64` at `0xfffffe0009b19710`, decrements it on entry, and checks whether the old count was 1 at `0xfffffe0009b19954`. That last-core path carries a flag to the conditional virtual call at `0xfffffe0009b19e48..64`, using vtable slot `+0xf78`.
- I independently checked the actual `AppleT8103PMGR` vtable: slot `+0xf78` contains raw chained pointer `0x8011f8d402e951d8`, resolving to `AppleT8101PMGR::cpuComplexIdleEnter` at `0xfffffe0009e991d8`. Slot `+0x1148`, used by the wait routine, contains `0x801113df02ec27a4`, resolving to the M1-specific `AppleT8103PMGR::readACCReg` at `0xfffffe0009ec67a4`.
- `cpuComplexIdleEnter` at `0xfffffe0009e99228..48` can call `_waitAPSCPending` for E domain 2 or P domain 5. **It first tests `this + 0x73a52`, bit 0, and skips the wait when this bit is set.** The live value and complete initialization provenance of this flag were not established here. It would be too strong to say every macOS last-core idle entry executes the wait.
- `_waitAPSCPending` at `0xfffffe0009e98680` reads logical ACC selector `0xe20020` and repeats while returned bit 31 is set. The outer loop starts with `w22=1`, then repeats with `w22=0`. Thus it executes **two sequential waits ending in a bit-31-clear observation**, rather than requiring exactly two total reads. If the bit is set, each wait may read repeatedly. This does not by itself establish a timing interval between clear observations or explain why the second wait exists.
- I independently decoded the M1 mapping tables. E selector `0xe20020` resolves to RegMap 9, offset `0x20`; P resolves to RegMap 21, offset `0x20`. `initRegMaps` at `0xfffffe0009ec498c..9c` maps RegMap 9 to provider memory resource 5; at `0xfffffe0009ec4a64..74` it maps RegMap 21 to resource 14. The captured provider's `IODeviceMemory` entries (full dump withheld because it contains machine identifiers; derived values are in `raw/driver-apsc-register-mapping.json`) contain absolute bases `0x210e20000` and `0x211e20000`, respectively, each length `0x2000`. The effective addresses are therefore **`0x210e20020` and `0x211e20020`**. These are resolved addresses from static code and registry data; this reviewer did not read those hardware registers.

Primary evidence is `raw/driver-t8103-apsc-idle.disasm`, the full temporary AppleT8103PMGR disassembly, and `raw/io-service.plist`. The last-core call site is preserved in `raw/review-last-core-dispatch.disasm`.

Supported next step: instrument the corresponding Linux idle/DVFS interaction and establish whether pending transitions overlap last-core idle entry, and whether serialization already occurs elsewhere. This review does **not** establish a Linux correctness bug, a missing power-saving switch, the relevant bypass flag's active setting, or the safety/performance benefit of copying the wait into Linux. A successful experiment must determine those points before treating this as an implementation requirement.

## Claims not supported by this evidence

- A measured 50 microsecond hardware wake or exit latency.
- A 50 microsecond hardware idle-entry threshold or target residency.
- A 50 millisecond hardware latency inferred solely from the ADT property's `-us` suffix.
- That fixing this parameter in Linux will reproduce macOS power consumption or permit CPU/cluster power collapse.
- That CPU IOReport `IDLE` residency distinguishes WFI, retention and power collapse.
- That macOS does not gate M1 clusters because the reviewed CLPC methods return immediately.
- That the result is unknown to Asahi developers. A repository/search comparison can show that it was not found in searched public material; it cannot establish what another group has discovered privately or in unsearched discussions.

## Reproduction boundary

The main investigation ties this collection's kernel UUID `1F15A5DA-11D6-39EE-88D2-153E2F90F066` to the running kernel; see `raw/driver-image-uuids.json` and `raw/driver-kernelcache-metadata.json`. This reviewer directly checked binary contents but did not independently overcome the sandbox restriction on live identity sysctls. The public XNU source revision is separately recorded in `raw/driver-xnu-source-revision.txt`.

Preserved primary excerpts: `raw/driver-pmgr-property-loading.disasm`, `raw/driver-pmgr-idle-init.disasm`, `raw/driver-local-ml_processor_register.disasm`, `raw/driver-kernel-ns-conversion.disasm`, `raw/driver-clpc-cluster-noops.disasm`, and `raw/review-registration-wrapper.disasm`. Full temporary disassemblies used for the wrapper and overwrite review are `/private/tmp/m1-power-AppleARMPlatform.disasm` and `/private/tmp/m1-power-ApplePMGR.disasm`.
