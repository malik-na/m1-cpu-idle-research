# macOS Control Path on the Investigated M1

This page describes the matching **local macOS 27.0 build 26A428** image on T8103, with public XNU as a cross-check. The inspected kernelcache UUID matches the running kernel (`1F15A5DA-11D6-39EE-88D2-153E2F90F066`, XNU `13432.1.9~1`). The public [XNU reference revision](https://github.com/apple-oss-distributions/xnu/tree/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea) is not asserted to be this exact release. See [binary identity and provenance](../notes/local-driver-notes.md).

## Separate layers before reading assembly

1. The scheduler determines whether a core has runnable work and how long it expects to be idle.
2. CLPC can influence a short-idle **WFE** choice through a per-cluster recommendation.
3. XNU calls PMGR to prepare ordinary idle; PMGR accounts active cores and may coordinate the final core with an APSC/DVFS command.
4. The kernel executes the appropriate WFI path. Hardware and firmware determine what physically turns off and what is retained.

System suspend, a non-returning CPU shutdown path, and ordinary returning idle are different mechanisms. The [local instruction landmarks](../notes/kernel-wfi-notes.md) preserve the callback-before-WFI sequence and a distinct disable-retention helper. A nearest-export label in a stripped binary is not proof of an internal function's name.

## The `50000` unit chain

```text
ADT /arm-io/pmgr property cpu-power-gate-latency-us = 50000
  -> ApplePMGR loads it unchanged
  -> processor_info.powergate_latency = 50000
  -> matching XNU treats input as nanoseconds
  -> 1200 ticks at 24 MHz = 50 microseconds
  -> short-delay spin/block decision
```

The source chain is [property loading](../notes/raw/driver-pmgr-property-loading.disasm), [PMGR idle initialization](../notes/raw/driver-pmgr-idle-init.disasm), [running-build registration](../notes/raw/driver-local-ml_processor_register.disasm), and [nanosecond conversion](../notes/raw/driver-kernel-ns-conversion.disasm). Public XNU independently documents the [nanosecond consumer](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/osfmk/arm64/machine_routines.c#L1624) and [delay decision](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/osfmk/arm64/machine_routines.c#L2719).

The property suffix suggests microseconds but the checked consumer uses nanoseconds. This is a **software scheduling threshold**, not an empirically derived power-gate entry cost, hardware exit time, or value to paste into Linux `exit_latency` / `target_residency`.

## CLPC short-idle policy and named stubs

The local `clpc::CLPC::sampleThreadGroups` contains a call to `_ml_update_cluster_wfe_recommendation`; its nearby trace ID is `0x328c00c0`. This supports a real WFE recommendation path. No live frequency or effectiveness of that recommendation has been measured. [Local analysis](../notes/local-driver-notes.md), [public XNU idle source](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/osfmk/arm64/machine_routines.c).

Seven inspected methods named for cluster power requests or enable/disable are branch-target hint plus return on this T8103 image. This is a narrow fact about those entry points, recorded in [their disassembly](../notes/raw/driver-clpc-cluster-noops.disasm). PMGR, autonomous hardware transitions, and other code paths can still gate cores or clusters. An empty method name is not an absence proof for the SoC.

## Last-active-core APSC/DVFS wait

The PMGR CPU-idle routine decrements the cluster active count. On the previous-count-of-one path, a virtual dispatch resolves to `cpuComplexIdleEnter` in the local T8103 image. That function conditionally calls `_waitAPSCPending`. The wait reads the APSC/DVFS command's BUSY bit (`31`) until clear in **two sequential loops**; this means two clear-ending loops, not necessarily two total reads or a known minimum dwell time. [Call-path analysis](../notes/local-driver-notes.md), [exact disassembly](../notes/raw/driver-t8103-apsc-idle.disasm), [independent review](../notes/review.md).

The E-cluster physical command address is `0x210e20020`; the P-cluster address is `0x211e20020`. The local object/resource mapping and register-read selector are documented in [PMGR mapping](../notes/local-driver-notes.md). The inspected [Asahi cpufreq driver](https://github.com/AsahiLinux/linux/blob/77cb8f24c2381a8abb7272d7bbdec548d6426a8a/drivers/cpufreq/apple-soc-cpufreq.c#L171-L207) uses the same command offset `0x20` and BUSY bit 31, waiting for a **previous** command to finish before issuing a new one; it returns after the write without waiting for the new command's completion.

The [instruction-order follow-up](../notes/mac-pmgr-command-order.md) resolves a related ambiguity in the saved trace. In the identified CPU-complex caller, macOS `setPerfState` first waits for an old command, can write a new command to selector `0xe20020`, and performs a post-write BUSY-clear wait only when its caller passes a true boolean; the performance marker follows its return. Three other functions call the same marker helper, and the saved `CPM1PerfStateReq` / `CPM3PerfStateReq` events do not identify their caller. They are neither write timestamps nor unconditional BUSY-clear markers. The idle callback supplies false and has the separate last-core wait described above.

The bypass flag is set by nonzero PMGR feature 2 (`cpu-tvm`). Its captured provider properties omit `cpu-tvm`, the feature default is zero, and the object allocation is zeroed. The checked initialization **predicts** this Mac leaves bypass clear and takes the wait. We have not read the private flag in a live run or counted executed waits. [Flag data flow](../notes/local-driver-skipflag-followup.md).

Linux's checked idle driver has no explicit last-core command wait, but that is not yet a defect. Its source permits an outstanding request during deep-WFI entry, including a conditional cross-cluster writer path; actual timing and physical consequence are unknown. A simple busy-clear sample could also race a later remote write. [Concurrency review](../notes/linux-dvfs-idle-concurrency.md).

The installed PMGR signpost definitions name `PERF_CPU_IDLE` start/end (`0x27001001` / `0x27001002`). A bounded live capture is described in [Live Mac Tracing](Live-Mac-Tracing.md). These events can help locate idle callbacks, but their presence alone does not prove that the internal wait ran.
