# Predeclared first native windows

Prepared 2 October 2026, before the research kernel's first boot. This is a
plan, not hardware evidence or a completed run. The operator explicitly
provided full authorization for the remaining task work. The reviewed
[deployment](deployment-receipt.json) preserves the working stock entry as
the default and adds `Aurora-APSC-research`. The test kernel is
`7.1.12-ARCH-apsc-20261002`, config `f86b80f4…`, build ID `a53a08aa…`.

The first test boot must verify its actual EFI entry, running build ID,
exported config, complete current FDT, native/guest status, all eight CPUs,
`apple_idle`/`menu`, enabled CPU PD state, policies and both debugfs helpers.
The [collector](collect_native.py) refuses a different release/config/build
ID, a guest/container, an unavailable or consumed helper, a changed topology
or incorrect command mapping. It does not install, reboot, mount debugfs,
change policy, or write a power/frequency register. Root authentication must
stay in the terminal, with no password in commands or saved evidence.

The first direct research boot revealed missing Wi-Fi and brightness because
Omarchy had cleaned up its unowned root-filesystem modules. The
[regression record](driver-regression-receipt.json) preserves the failure and
package repair. Start this protocol only after a fresh research boot verifies
Wi-Fi, brightness, module ownership and the original entry/config/build ID.
The failed boot contains no native APSC observation window.

Before the first window, a read-only collector audit led to a scoped
[hardening amendment](native-collector-hardening-receipt.json). The collector
now verifies the exact pilot workload binary and both complete worker CSVs,
checks that workers remain alive before arming, rejects Python optimization,
records panel brightness, and requires valid post-counter and clean observer
decoder results. The original
preparation receipt remains as the historical source snapshot. The kernel
counter pre-phase has no in-kernel timeout, so the five-second limit can only
be checked after its synchronous control write returns.

The observation question is whether a candidate final software entrant
samples command BUSY at the declared C pre-WFI seam after a recorded SET
submission for that cluster. It can be supported by a valid raw pending
sample and compatible command/order witnesses, or weakened by sensitive
matched negative windows. C is before context tracking and the assembly WFI;
this experiment does not claim instruction-level WFI overlap or rail state.

Use three independently booted, otherwise matched research-kernel sessions
in initial order A (baseline), B (records), C (MMIO). Each window is nominally
2,000 ms; retain actual observer and external timing because wake delay may
extend it. A does not arm the observer. B/C each consume its single capture
for that boot. No immediate retry or second capture is a repeat. Reverse
or randomize order for a subsequent matched block if observer comparison is
needed; this first block alone does not support an energy/wake benefit.

Each session runs pre/post counter exchanges from logical CPU 0, 256 rounds
per other CPU (1,792 per phase), outside the observer window. The declared
maximum acceptable pre-phase latency is five seconds; a failed/incomplete
phase, metadata mismatch, unexpected 24 MHz frequency or invalid decoder
acquisition stops before observer arming. Wait five seconds after a valid
pre phase, then start the workload. A successful acquisition is not clock
qualification. Record a proposed 240-tick pairwise tolerance (10 microseconds
at 24 MHz) and a four-tick outward endpoint margin as explicit assumptions.
The decoder retains raw intervals and stable-offset contradictions. It never
automatically passes a clock bound to the observer analyzer. Review pre/post
models and the shared boot/time packet before any conditional cross-CPU
screen; otherwise retain within-CPU order only. Finite endpoint exchanges do
not exclude transient offset changes during idle.

The [workload](pulse_workload.c) performs fixed normal userspace work on
logical CPUs 1 and 5, respectively in the verified E/P groups. Each worker
runs 44 pulses at 50 ms intervals, each with exactly 1,048,576 dependent
64-bit xorshift iterations. Both share a scheduled monotonic start, one
second after launch. The observer window begins 150 ms after that start,
after initial warm-up pulses. Workers retain timing/identity/checksum data
in memory; CSV export waits for the collector to release it after the
actual observer window has drained. No userspace logging runs in the window.
Record completed pulses, overrun/lateness and external window brackets;
nominally equal work is not proof of equal completed work inside the actual
capture. The stock-kernel execution check completed all 44 pulses on each
requested CPU; its private receipt and binary/source hashes are retained.

Match charging and power-source state, display/brightness, USB devices,
thermal band/trend, network/background activity, settling and completed
work across A/B/C. Preserve pre/post policy, idle counters and power/thermal
snapshots and record unobserved conditions as unknown. Do not manufacture
opportunities through hotplug, governor/limit changes, state disabling or
boot-argument changes. Equal endpoint snapshots cannot exclude transient
external changes. Keep the existing firmware and DT delivery route.

A negative claim requires zero overflow/missing commits, valid command
samples, unchanged policy/online masks, adequate clock ordering and at
least 20 successful SET submissions plus 20 unambiguous interior candidate
final-entrant samples for each cluster. Record exclusions and ambiguities.
Fewer opportunities, clock uncertainty, loss, errors or differing conditions
produce an inconclusive acquisition, not a no-overlap conclusion. Inspect
B/C accessor durations and completed work to assess recording/read effects;
A/B/C do not isolate the built-in inactive hooks' fixed cost. That needs a
separate disabled full-kernel control. Preserve failed runs and raw status
and events privately before publishing sanitized projections.

On the authorized, verified research boot, with private `native_packet_root`
(mode 0700, operator-owned) and compiled `pulse_workload`:

```sh
sudo python3 collect_native.py "$native_packet_root" baseline --workload "$native_workload"
# On a different matched research boot:
sudo python3 collect_native.py "$native_packet_root" records --workload "$native_workload"
# On a third matched research boot:
sudo python3 collect_native.py "$native_packet_root" mmio --workload "$native_workload"
```

The collector publishes no files or hardware claims. It saves raw private
boot/config/DT/logs, command chronology, phase/capture files, decoder output,
workload rows, errors and SHA-256 hashes. Its `unverified_input` decoder label
remains intentional. Review the packet against [NATIVE-RUN](../linux-apsc-observer/NATIVE-RUN.md)
and [PROVENANCE](../../PROVENANCE.md). #5 stays open until the native result
and its limitations have been assessed.

## Adaptive correction after the first records pilot

The first independent A baseline completed, but the first B records capture
failed the observer integrity gate. During B's 2.045-second active interval,
CPU 0 attempted 4,809 idle records, filled its 2,048-event ring and overflowed
2,761 records. All other idle and DVFS streams were loss-free; both workers
and both counter phases completed. The decoder suppressed the whole-stream
screen. B contains no MMIO samples and supports neither a BUSY observation
nor a no-overlap conclusion. The failed raw packet is retained privately.

The retained B prefix reaches 20 cluster-0 SET submissions only after its
CPU-0 ring fills, so shortening the window cannot preserve the predeclared
negative-opportunity gate for that observed workload. The incremental
[capacity patch](0003-aurora-apsc-ring-capacity.patch) raises fixed idle/DVFS
ring limits to 16,384/8,192 with no change to the reserve or record logic.
Qualify a newly linked kernel image and installation before new capture. The
first A/B pair is pilot evidence; repeat A, B and C on three fresh boots of
the *same new image* with the original two-second window, workload and
matching criteria. Preserve any further failed run as a separate packet and
amend this protocol explicitly if conditions require another change.

The [capacity revision receipt](capacity-revision-receipt.json) records a
successful new image and separate entry `Aurora-APSC-research-capacity`.
Its GNU build ID is `eb8fe1838f2c34f24f83ec53da25d2f9ae150b12`;
the release string remains the same because all 1,867 rebuilt modules are
byte-identical. Check that build ID and the new entry on every fresh boot;
the release string alone cannot distinguish the two research images.

## Result of the capacity-image block

Three fresh independent A/B/C boots then completed under this build ID.
B and C were loss-free; C recorded 734 valid command reads, including 16
BUSY values. One cluster-1 BUSY read followed a target-cluster SET on the
same CPU and is a conditional final-entrant candidate under the declared
but unproven 240-tick pairwise clock-error assumption. The full
[result](NATIVE-RESULT.md) and [reviewed event packet](native-evidence/README.md)
preserve counts, timestamps, counter phases, observed matching deviations
and the claim boundary. The cluster-0 negative-opportunity gate failed;
the result does not establish WFI-instruction overlap or physical power.

The separately [predeclared first-attempt WFI-seam extension](WFI-PLAN.md)
addresses the remaining near-WFI observation and paired-opportunity gaps on
a separately built, statically qualified ABI 2 image. Its distinct-release
modules and EFI entry are installed and checked in the
[deployment receipt](wfi-deployment-receipt.json). The image remains
**unbooted**; no ABI 2 capture or hardware behavior is established.
