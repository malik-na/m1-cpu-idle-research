# Predeclared first-attempt WFI-seam extension for issue #5

Prepared 2 October 2026, before any boot or capture with the proposed ABI 2
kernel. This is a protocol, not new machine evidence. The completed ABI 1
[result](NATIVE-RESULT.md) remains the earlier pre-WFI C-hook observation:
one same-CPU SET-to-BUSY witness, conditional software final-entrant status,
and no instruction-level WFI or physical power conclusion. Its C capture has
only one conditional candidate sample within even 2,400 ticks of a preceding
SET, so its separate SET and candidate totals do not establish 20 paired
negative opportunities.

## Site and scope

The ABI 2 variant reserves a slot in C and performs one bracketed command
read in the assembly deep-idle path after the original power-control MSR but
before the original `dsb sy; wfi` retry label. `wfi_clock` performs the same
counter/publish steps without the MMIO read; `wfi_mmio` reads the mapped
device-tree command register once. All other capture modes retain the C-hook
records, and the original WFI instruction/retry and command writes remain
unchanged. A BUSY sample proves BUSY only at this **first-attempt pre-DSB
probe**. It cannot prove BUSY at the later WFI instruction, a completed
command, an asleep peer, or a physical rail transition. The retry path is
unsampled. The new post-MSR read position is untested hardware behavior until
a native boot and controlled pilot succeed.

## Staging and acquisition

Build from the exact installed Aurora source/config/toolchain with the
variant-specific source delta and linked disassembly recorded. Verify image
build ID, config hash, module hashes/vermagic, initramfs contents and installed
UKI bytes before use. Keep the working stock boot entry/default and a separate
research entry. On first boot, check the selected entry and live build ID,
native T8103/FDT command mapping, all eight CPUs, cpuidle/policies, observer
ABI, Wi-Fi and brightness before arming. If boot or device function fails,
return to the stock entry and retain the failure record; do not interpret it
as APSC evidence.

Start with one fresh-boot `wfi_clock` acquisition. Only after its raw
status/events, slot handoff, bounded drain and user-visible device checks
pass, run `wfi_mmio` on a different boot. Each one-shot capture uses the
existing 2,000 ms, CPU 1/5 pulse workload and private collector packet.
Preserve every failed packet. No retries in the same boot are independent
replicates. The first clean D/E acquisitions may enter the matched block;
complete the additional A unarmed, B records and C C-hook MMIO controls on
fresh boots of that same image. Prefer D, E, C, B, A for the first block,
opposite the earlier A/B/C order. If needed, conduct at most one additional
fresh-boot block in reverse order, with the decision made from the declared
gates below. Compare only worker pulse indices fully inside every actual
window, since the earlier A window contained 39 pulses and B/C contained 40.

Match charger state, brightness, online CPUs, policies, thermal band/trend,
USB/network/background activity and completed work. Record deviations as
unknown or unmatched, not as equivalence. Preserve pre/post counter
exchanges and raw timing. The proposed pairwise cross-CPU error bound of
240 ticks is an **assumption**: endpoint exchanges do not rule out a transient
in-run clock offset. Do not publish an unqualified final-core attribution
from this timing alone.

## Decision rules

The primary positive is a clean interior `wfi_mmio` row with raw command
BUSY bit 31 set. Show its CPU/cluster/token, both counter ticks, raw command,
preceding target SET if any, writer/target CPU, intervening or ambiguous
writes, and the same-CPU order where available. Classify peer idle intervals
only as a conditional software-candidate screen under a stated cross-CPU
error sweep, never as physical sleep or exact WFI overlap. A clean same-CPU
SET-to-BUSY row is direct order evidence even if peer attribution remains
conditional.

For negative sensitivity, a *paired opportunity* is one distinct successful
target-cluster SET followed by the earliest clean interior same-cluster E
sample before any possibly intervening SET, within 600 ticks (25 microseconds)
of submission. The 600-tick primary bound is chosen now from the earlier
549-tick BUSY witness; report a 2,400-tick (100 microseconds) exploratory
sweep separately. For different CPUs, order and gap additionally depend on
the explicitly assumed clock-error bound; count same-CPU pairs without that
assumption. Count each SET once and tabulate cluster, boot, lag, writer,
BUSY, and exclusions. An ambiguous write or unmatched clock ordering does
not count. A candidate final entrant also needs complete interior peer
software intervals under the chosen error bound; this label remains
conditional without a separate in-sample peer-state witness.

A zero-detection statement requires clean E packets, no ring overflow,
missing commit, invalid read, mapping error or unmatched interior slot,
unchanged topology/policies, and at least 20 primary paired opportunities
**per cluster**. It may then say only that zero BUSY samples were detected in
those exposed, model-qualified opportunities. It cannot infer absence at
WFI, a universal event rate, or a physical outcome. Require C to demonstrate
pending commands in the comparable lag stratum before treating an E zero as
a sensitive contrast; C and E are different boots, not event-level pairs.
If the gate remains unmet after the two declared blocks, stop and publish
the outcome as underexposed/inconclusive. A changed workload or peer-state
observer requires a new protocol and separate arm before capture.

Compare D/E counter brackets and B/C C-hook brackets (median, high tail and
maximum), ring loss and matched worker timing. These do not isolate total
ring publication cost or the fixed inactive-hook cost. No frequency/idle
policy intervention, new device-register write, hardware wait or energy
claim is part of this experiment.
