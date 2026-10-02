# Why the ABI 2 probe does not observe the WFI instruction

The accepted [D/E/C/B/A result](WFI-ABI2-BLOCK-RESULT.md) reads the APSC
command register on the first deep-idle attempt **before** the original
`dsb sy; wfi`. The [incremental patch](0004-aurora-apsc-wfi-first-attempt.patch)
places a counter bracket, one conditional command read, ordering and slot
publication between the power-control MSR and that DSB/WFI pair. The
reviewed [linked build](wfi-build-receipt.json) retained one WFI
instruction and the original retry/tail bytes. A retry branches directly
to the DSB label and skips the read. Thus the four E BUSY words establish
register values at the **first-attempt pre-DSB read**, not at the later WFI
instruction or on retries. The captured bytes contain no observation that
can recover the command value after that read.

An independent `llvm-objdump` inspection of the linked `-wfi` `vmlinux`
(SHA-256 `d514ddae106c1994adf4d93491e9519a3b83f0b57c07c7cc53143d63ff7b88a7`,
GNU Build-ID `11e80be6d8b358eee9aa847a0f814aff02b66c43`) places the command
`ldr x4, [x3]` at `apple_cpu_deep_wfi+0x48`, the slot-publication `stlr` at
`+0x78`, the original `dsb sy` at `+0x7c`, and `wfi` at `+0x80`. **Thirteen
instructions** lie strictly between the read and WFI, including ordering,
counter and record operations. The linked routine's SHA-256
`2545c4ce2e5dcfd433dffa4edbd187b11adc544bbda496a882f1fb61fdccaa82`
matches the candidate object in the [static validation](wfi-build-receipt.json).
These offsets are static linked-code evidence, not a runtime instruction
trace or a measured bound on elapsed read-to-WFI time.

A later or closer software read would still be separated from WFI by at
least instruction execution and possible interrupt/remote-writer activity.
Without an independently established BUSY continuity bound or a concurrent
hardware observation, neither a pre-WFI BUSY nor a pre-WFI clear value
fixes the bit at the instruction. Moving the MMIO read after the original
DSB also changes the reviewed entry sequence and needs a new observer-effect
and ordering analysis. Merely repeating the same ABI 2 block cannot close
this temporal gap; the [predeclared comparator](compare_wfi_blocks.py)
rejects a reverse block after the first positive witness.

The reviewed local Apple cpufreq source, with the
[observer integration](0001-aurora-t8103-apsc-observer.patch), has one normal
Linux SET path for the two T8103 APSC command resources:
`apple_soc_cpufreq_set_target()` in `drivers/cpufreq/apple-soc-cpufreq.c`
polls the **previous** BUSY state clear, then submits a new SET through the
observer wrapper's single original `writeq_relaxed`. Both fast and slow
cpufreq callbacks use that path; on T8103 it returns without waiting for
the new command to complete. Its `dvfs_possible_from_any_cpu` setting allows
a remote CPU to submit while another core enters idle. This is a scoped audit
of the reviewed Linux driver, not exhaustive accounting of possible
firmware or other bus writers. Zero loss in the active observer streams
applies to wrapped driver calls only. No minimum BUSY hold time or invariant
excluding a clear/reassert cycle is established. The [build receipt](wfi-build-receipt.json)
has no build-time full-source or WFI-patch digest, so checked local source
and linked-code correspondence is not cryptographic full-tree provenance.
The source defines `APPLE_DVFS_LAST_CHG_TIME` at command-base offset `0x38`
with a 24 MHz timebase comment but never uses it. Neither that name nor the
comment establishes its T8103 update edge, association with BUSY completion,
or wrap behavior; it cannot retrospectively supply a WFI-time command value.

On the current native T8103 WFI research boot, checked 3 October 2026,
the release is `7.1.12-ARCH-apsc-20261002-wfi` and the decompressed live
configuration SHA-256 is
`f86b80f4dcef277be874f476293d8b8055053072f7209625586b60e2227f905d`.
That configuration reports `# CONFIG_CORESIGHT is not set` and
`# CONFIG_ARM_SPE_PMU is not set`. It has `CONFIG_ARM64_BRBE=y`, but BRBE
hardware support was not verified. The active Apple PMU driver has no BRBE
initialization; the pinned `arm_pmu.c` rejects branch-stack events when
`reg_brbidr` is unset. Both Apple PMUs list only named `cycles` and
`instructions` events in sysfs. `/sys/bus/coresight/devices` is absent;
the exposed perf event-source devices are the two Apple PMUs, breakpoint,
kprobe, software, tracepoint and uprobe. A name-based scan of the live
device tree found no ETM/CoreSight/trace node, and no ETM/TRBE/SPE event
source is registered. These are **current-boot
software and device-tree observations**, not proof that T8103 silicon lacks
an autonomous instruction-trace facility. They do not qualify a usable
instruction trace on this boot.

A separate [m1n1 tethered hypervisor boot](https://asahilinux.org/docs/sw/tethered-boot/)
could trace some guest MMIO access, but its [MMIO tracer](https://github.com/AsahiLinux/m1n1/blob/ce2b8a43cea4220b602af1005dc9dbfc59c9624e/src/hv/hv_vm.c)
intercepts and emulates those accesses. Trapping WFI would likewise change
the native instruction path. A qualified, decoded
[ETM instruction stream](https://developer.arm.com/-/media/Arm%20Developer%20Community/PDF/Learn%20the%20Architecture/Understanding%20Trace.pdf?revision=6b56aa86-4314-49e7-a14d-3ff3e5c8fece)
could establish WFI execution, but instruction trace alone would not report
the simultaneous APSC register value.
These routes need a separately qualified target and synchronized, independent
command-state observation before they can answer the native instruction-state
question.

A stronger observation-only study would need a new protocol and separately
built image. It could timestamp an instruction-adjacent seam and every
retry, and independently sample command state from another cluster with
validated cross-CPU clock alignment and complete write accounting. Such a
sampler would still require a demonstrated temporal/semantic bridge to the
WFI instruction; an adjacent timestamp alone does not supply the missing
command value. The prepared [PCPM sampler](../linux-pcpm-sampler/README.md)
is a possible separate signal for the P-cluster peer-state question, but it
has not been rebuilt and booted on this Aurora target, and its `ACTUAL`
field is not calibrated as rail power. No physical-state or energy claim
can be obtained retrospectively from the ABI 2 packets.

An `dsb sy; command read; wfi` variant with record publication after wake
would narrow the pre-WFI gap but still leave a non-atomic interval for
controller progress or a remote write; recording only the first attempt
would also miss WFI retries. A pair of reads bracketing WFI would need an
independently validated BUSY-transition invariant and complete writer
accounting to imply the value at the instruction. Neither is presently
available. A new software-only build solely to repeat a closer proxy would
therefore not settle issue #5's exact instruction-state question.
