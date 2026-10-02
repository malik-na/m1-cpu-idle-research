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

A later or closer software read would still be separated from WFI by at
least instruction execution and possible interrupt/remote-writer activity.
Without an independently established BUSY continuity bound or a concurrent
hardware observation, neither a pre-WFI BUSY nor a pre-WFI clear value
fixes the bit at the instruction. Moving the MMIO read after the original
DSB also changes the reviewed entry sequence and needs a new observer-effect
and ordering analysis. Merely repeating the same ABI 2 block cannot close
this temporal gap; the [predeclared comparator](compare_wfi_blocks.py)
rejects a reverse block after the first positive witness.

On the current native T8103 WFI research boot, checked 3 October 2026,
the release is `7.1.12-ARCH-apsc-20261002-wfi` and the decompressed live
configuration SHA-256 is
`f86b80f4dcef277be874f476293d8b8055053072f7209625586b60e2227f905d`.
That configuration reports `# CONFIG_CORESIGHT is not set` and
`# CONFIG_ARM_SPE_PMU is not set`. `/sys/bus/coresight/devices` is absent;
the exposed perf event-source devices are the two Apple PMUs, breakpoint,
kprobe, software, tracepoint and uprobe. A name-based scan of the live
device tree found no ETM/CoreSight/trace node. These are **current-boot
software and device-tree observations**, not proof that T8103 silicon lacks
an autonomous instruction-trace facility. They do not qualify a usable
instruction trace on this boot.

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
