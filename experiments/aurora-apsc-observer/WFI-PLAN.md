# Predeclared first-attempt WFI-seam extension for issue #5

Prepared 2 October 2026, before any boot or capture with the proposed ABI 2
kernel. This is a protocol, not new machine evidence. The completed ABI 1
[result](NATIVE-RESULT.md) remains the earlier pre-WFI C-hook observation:
one same-CPU SET-to-BUSY witness, conditional software final-entrant status,
and no instruction-level WFI or physical power conclusion. Its C capture has
only one conditional candidate sample within even 2,400 ticks of a preceding
SET, so its separate SET and candidate totals do not establish 20 paired
negative opportunities.

The separately built ABI 2 release has now been installed as
`Aurora-APSC-research-wfi-seam`; the [deployment receipt](wfi-deployment-receipt.json)
records the checked module package and EFI readback. This changes the
deployment status only. At this plan's original checkpoint the image was
unbooted; the subsequent [D clock pilot](WFI-D-RESULT.md) is a separate
runtime result. The acquisition rules below were declared before that boot
and remain unchanged.

After the successful D pilot, the original research entry and image were
retired under the plan's first-boot rule. The reviewed
[retirement receipt](wfi-efi-retirement-receipt.json) is a later operational
record, not an amendment to the capture decision gates below.
The later [E result](WFI-E-RESULT.md) is a separate command-state observation;
the remaining C/B/A controls and comparison gates below are still pending.

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
unsampled. The new post-MSR read position remains untested with a
command-register read; the D clock pilot tested the same seam without one.

The [ABI 2 packet publication contract](WFI-PUBLICATION.md) was prepared
before the first capture. It specifies private provenance checks and a
reviewed numerical/environment export for each fresh-boot packet; it is not
itself a native result.

## Staging and acquisition

Build from the exact installed Aurora source/config/toolchain with the
variant-specific source delta and linked disassembly recorded. Verify image
build ID, config hash, module hashes/vermagic, initramfs contents and installed
UKI bytes before use. The [build receipt](wfi-build-receipt.json) and
[deployment receipt](wfi-deployment-receipt.json) record those offline and
installed checks. The stock default, working capacity entry and earlier
research entry remain available through the first test boot. Retire an
obsolete research EFI image only after its replacement boots successfully
with the device and observer checks below; retain its source, hashes and
findings in the repository. On first boot, check the selected entry and live
build ID, native T8103/FDT command mapping, all eight CPUs, cpuidle/policies,
observer ABI, Wi-Fi and brightness before arming. If boot or device function
fails, return to the stock entry and retain the failure record; do not
interpret it as APSC evidence.

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

**Pre-capture power-baseline amendment, 2 October 2026:** the battery reached
39% while discharging after WFI image installation and before any ABI 2 boot
or acquisition. All new ABI 2 A/B/C/D/E matched boots therefore use the
charger connected (`macsmc-ac/online=1`) and panel brightness 155. Check
those values on the same boot before arming and at both capture endpoints.
If a boot differs, do not capture or compare it under this block until it is
separately qualified. The earlier battery-powered ABI 1 A/B/C packets remain
historical evidence, not substitutes for these same-image controls.

## Decision rules

The primary positive is a clean interior `wfi_mmio` row with raw command
BUSY bit 31 set. Show its CPU/cluster/token, both counter ticks, raw command,
preceding target SET if any, writer/target CPU, intervening or ambiguous
writes, and the same-CPU order where available. Classify peer idle intervals
only as a conditional software-candidate screen under a stated cross-CPU
error sweep, never as physical sleep or exact WFI overlap. A clean same-CPU
SET-to-BUSY row is direct order evidence even if peer attribution remains
conditional.

Report raw interior E BUSY rows and **candidate-final-entrant E BUSY rows
separately**. A candidate requires that the E sample's own CPU/token have a
complete, model-interior idle-enter/exit interval and that all three other
same-cluster CPUs have complete, model-interior software intervals whose
entry ends strictly before the candidate's own idle-enter bracket begins,
and whose exit starts strictly after the entire E bracket under assumed
pairwise `E=240`. The candidate's own interval must strictly contain the
E bracket. Missing, incomplete,
contradictory or clock-ambiguous intervals cannot qualify. This is a
conditional software label, not proof that peers were asleep or that BUSY
persisted at the WFI instruction. A raw BUSY row lacking that label answers
only the first-attempt command-state subquestion, not the candidate-final-core
part of issue #5.

For negative sensitivity, a *paired opportunity* is one distinct successful
target-cluster SET followed by the earliest clean interior same-cluster E
sample before any possibly intervening SET, within 600 ticks (25 microseconds)
of submission. The 600-tick primary bound is chosen now from the earlier
549-tick BUSY witness; report a 2,400-tick (100 microseconds) exploratory
sweep separately. For different CPUs, SET-to-sample order and gap additionally
depend on the explicitly assumed clock-error bound. Same-CPU SET-to-sample
order and lag do not need that bound, but the **full paired-opportunity count**
still uses the assumed 240-tick error to establish strict capture interior
and to exclude an earlier sample or intervening SET on another CPU. Count
each SET once and tabulate cluster, boot, lag, writer, BUSY, and exclusions.
An ambiguous write or unmatched clock ordering does not count. This
clarification was made before the ABI 2 image's first capture. A candidate
final entrant also needs complete interior peer software intervals under the
chosen error bound; this label remains
conditional without a separate in-sample peer-state witness.

**Bracket-bound clarification, before the first ABI 2 capture:** the 549-tick
historical observation is the strict gap between the SET-write bracket end and
the C-read bracket start, not a worst-case write-to-read elapsed time. For the
600/2,400-tick gates, use the conservative upper bound `sample.t1 - SET.t0`
plus assumed pairwise cross-CPU error (zero for the same CPU). Retain the
bracket gap separately as a lower bound. This applies equally to E and the
comparable-lag C control; an earlier decoder used the lower bound as its gate
and was corrected before native ABI 2 acquisition.

A zero-detection statement requires clean E packets, no ring overflow,
missing commit, invalid read, mapping error or unmatched interior slot,
unchanged topology/policies, and at least 20 primary paired opportunities
**per cluster**. It may then say only that zero BUSY samples were detected in
those exposed, model-qualified opportunities. It cannot infer absence at
WFI, a universal event rate, or a physical outcome. Require C to demonstrate
pending commands in the comparable lag stratum before treating an E zero as
a sensitive contrast; C and E are different boots, not event-level pairs.
For the issue's **candidate-final-core** negative question, require at least
20 of those primary E pairs **per cluster** to have E samples passing the
complete own/peer interval screen above. Count that candidate-specific
exposure separately; the generic 20-pair gate cannot substitute for it.
If candidate-specific exposure fails, report the candidate question as
underexposed even when generic E samples are all clear. Cross-boot thermal
band/trend and USB/network/background comparability must also be explicitly
reviewed before calling a zero a sensitive C-versus-E contrast; endpoints
alone do not prove those conditions during the window.
If the gate remains unmet after the two declared blocks, stop and publish
the outcome as underexposed/inconclusive. A changed workload or peer-state
observer requires a new protocol and separate arm before capture.

Prospective C-control clarification, recorded before any ABI 2 native capture:
screen successful target-cluster SETs against the earliest valid, strictly
interior same-cluster C-hook `idle_enter` MMIO sample using the same assumed
240-tick cross-CPU ordering/interior model and possible-intervening-SET
exclusions as E. An invalid C read suppresses that control rather than being
skipped in favor of a later sample. Report C's 600-tick primary and 2,400-tick
exploratory lag strata by cluster; at least one BUSY C primary pair in a
cluster demonstrates pending command at that earlier site in a comparable
lag stratum. This is a control for interpreting E zero, **not** an additional
20-pair C gate or a same-event C/E comparison. The existing E 20-pair-per-
cluster gate and claim boundary above are unchanged. Identify the SET writer
CPU, the cpufreq policy representative CPU and cluster mask, and the C/E
sampling CPU separately; a cluster command has no observed individual
hardware target core in these records.

Compare D/E counter brackets and B/C C-hook brackets (median, high tail and
maximum), ring loss and matched worker timing. These do not isolate total
ring publication cost or the fixed inactive-hook cost. No frequency/idle
policy intervention, new device-register write, hardware wait or energy
claim is part of this experiment.
