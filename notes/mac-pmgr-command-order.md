# Installed PMGR instruction order: DVFS command, optional BUSY wait, and trace marker

**Target and evidence tier:** MacBookAir10,1 / T8103, macOS 27.0 build 26A428, XNU `13432.1.9~1`, running and embedded kernel UUID `1F15A5DA-11D6-39EE-88D2-153E2F90F066`. The inspected IMG4 SHA-256 is `e5e3b35cca34477d287a447bd1aa7a84f02f8543287b8db2eef722710e95a349`. This is exact-build **static AArch64 disassembly**, followed by a recheck of the [previously captured software trace](mac-ktrace-perf-request-correlation.md). It is not a live read of the PMGR command register. The [focused instruction excerpts](raw/driver-pmgr-perf-marker-order.disasm) and [fileset extraction method](tools/driver-kernelcache-inspect.py) make the result reviewable without publishing the kernelcache. All 106 published instruction lines were checked verbatim against `xcrun llvm-objdump` on freshly extracted matching fileset views.

## Result

In the identified **CPU-complex** caller, the PMGR `0x270030x0` marker is emitted **after** `AppleT8101PMGR::setPerfState` returns, not at the instant a DVFS command is written. Whether that return follows a BUSY-clear poll for the **new** command depends on a boolean argument supplied by the caller. The trace helper has **three other direct callers** in this ApplePMGR image, and the saved event does not identify which caller emitted a particular `0x27003010` or `0x27003030`. The marker also does not carry the boolean or a sampled BUSY bit. Consequently the saved timing correlation is a workload-selection clue, not a measured time from an identified CPU command write or BUSY-clear observation to idle.

| Order in the checked command path | Instruction anchor | What it establishes |
|---|---|---|
| Entry to `setPerfState(domain, state, postWriteWait, aux)` | `9e9801c`: `mov x21,x3` | The incoming boolean is retained in `w21`; `postWriteWait` is our descriptive name, not a recovered parameter name. |
| Prior-command synchronization for CPU domains 2/5 | `9e98090`–`9e98098`: call `_waitAPSCPending(domain)` | The old APSC command is waited out before this path's new command work. |
| Read and modify the CPU DVFS command register | `9e98318`–`9e98344`: `readACCReg(...,0xe20020)`, insert requested low and shifted performance nibble | The call operates on the same logical selector whose BUSY bit is polled by the last-core path. |
| Submit the new command | `9e98370`–`9e9838c`: OR `0x02000000` and call vtable `+0x1158`, resolved to `writeACCReg(...,0xe20020,value)` | This is a command submission in the inspected path; the write call's return is not a demonstrated hardware transition completion. |
| Optional post-command synchronization | `9e98630`: `cbz w21`; otherwise `9e9863c`: call `_waitAPSCPending(domain)` | A true flag adds the post-write BUSY-clear wait. Its value on each recorded marker is unknown; BUSY clear alone is not a physical rail-state measurement. |
| Return to `ApplePMGR::_updateCPUComplexPerfState`, then emit marker | virtual `+0xe40` call at `9b18934`, resolved to `setPerfState`; `tracePerfStateChange` call at `9b189b0` | In this caller, the software marker occurs downstream of the virtual call and intervening PMGR work. |
| Construct event ID | `9b3635c`–`9b36364`: `0x27003000 | (index << 4)` | The CPU-complex caller gets the index through a halfword lookup at `9b188e0`. The suffix does not independently establish physical E/P identity or the emitting call site. |

The exact `AppleT8103PMGR` vtable resolutions are `+0xe40 → 0xfffffe0009e97ff4` (`AppleT8101PMGR::setPerfState`), `+0x1148 → 0xfffffe0009ec67a4` (`AppleT8103PMGR::readACCReg`), and `+0x1158 → 0xfffffe0009ec68fc` (`AppleT8103PMGR::writeACCReg`). The mapping of selector `0xe20020` through the provider resources to physical E/P addresses is independently documented in [the original driver analysis](local-driver-notes.md); the addresses are **not** dereferenced by this user-mode investigation. The marker event names come from the [installed signpost catalog](raw/driver-ApplePMGR.kext-PMGRSignposts.plist.json).

The other `tracePerfStateChange` calls are at `9af1fb0` in `_socPerfStateChangeThreadCallout`, `9b160ec` in `_handleSOCPerfStateRequest`, and `9b1688c` in the generic `_setPerfState`; the CPU-complex call is at `9b189b0`. Each passes an index and state to the same event-ID helper. This audit has **not** mapped every caller's index values or proved that the saved CPM1/CPM3 records all came from the CPU-complex path. That unresolved provenance further limits the prior timing correlation.

The idle path makes the boolean argument especially relevant. `ApplePMGR::_cpuIdle` passes **zero** in `w3` to `_updateCPUComplexPerfState` at `9b19dcc`–`9b19dd4`. If that call takes the CPU-domain `setPerfState` path and submits a command, it does not request the optional post-write wait there. The separate last-active-core dispatch later calls `cpuComplexIdleEnter`, whose enabled branch calls `_waitAPSCPending`; [the idle-path analysis](local-driver-notes.md) and [feature-flag follow-up](local-driver-skipflag-followup.md) establish that conditional path and its expected flag setting. This explains why the last-core wait is a distinct synchronization point, rather than treating every performance request as synchronous.

The checked `cpuComplexIdleEnter` code also has a branch *after* the wait: if object field `this+0x73a58` equals 2, virtual calls resolve to `getComplexToVoltageRail(complex)` and then `enableSingingCapWidget(rail,true)` (`9e9924c`–`9e992a8`). The field's live value and configuration source have **not** been established. The method names suggest rail-related PMGR bookkeeping, but do not prove a physical rail transition or that this branch ran on the measured Mac.

## Recheck of the saved trace

[`marker-scope.py`](tools/marker-scope.py) reconstructs each CPU's `0x27001001`–`0x27001002` PMGR callback bracket from the published, sanitized five-second stream. It reports:

```text
0x27003010: total=492, same_cpu_callback=0, any_cpu_callback=62
0x27003030: total=414, same_cpu_callback=0, any_cpu_callback=45
```

Thus none of these markers was emitted **inside the emitting CPU's own** bracketed CPUIdle callback in that capture. This rules out the simplest same-callback explanation for the earlier 166 near-marker apparent-last-E-core entries. It does not establish that all markers were independent of idle policy: another CPU's callback may overlap, the marker can follow variable PMGR work, the target domain and post-write-wait boolean are unrecorded, and trace loss or untraced operations remain possible. A marker on CPU 0–3 does not prove it targets that cluster.

## Linux implication and falsifier

The checked [Omacom/Asahi Linux source](omacom-linux-source-audit.md) waits for an **old** command before issuing a new cpufreq request and returns after writing it. Its deep-WFI idle routine has no explicit last-core BUSY wait. The macOS disassembly provides a concrete comparison point, but no evidence yet that Linux reaches WFI with bit 31 set or that doing so changes energy or wake correctness. The next observation needs the actual command write/target, post-write-wait flag or BUSY samples, final-core status, and WFI entry on a pinned runtime. A controlled native Linux run that never observes a pending command near its candidate last-core WFI entries would weaken this mechanism as an explanation for an idle-power gap; a positive overlap would still need independent physical-state and energy validation before a Linux wait policy is justified.
