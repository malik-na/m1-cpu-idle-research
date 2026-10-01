# M1 idle tracing: what the m1n1 hypervisor can and cannot establish

Research date: 2026-10-01, Asia/Kolkata. This is a source assessment and proposed experiment, not a hardware result. No SSH session, hardware register, boot configuration or running kernel was accessed or changed for this assessment.

## Finding

**Stock m1n1 can diagnose the macOS last-core/DVFS handshake, but its traces cannot establish native cluster-off residency or native transition latency.** It does not ordinarily trap guest WFI/WFE through the architectural HCR controls, and it deliberately permits retention-compatible deep WFI. However, it suppresses important Apple power-control writes, substitutes guest CPU shutdown/startup, alters CPU-state reads, generates timer activity, and keeps its transport power domains available. Those are concrete interference mechanisms, not merely a generic warning that tracing adds overhead.

The useful first result is a control-flow and register-ordering observation: does the last-active-core path actually call `_waitAPSCPending`, under which bypass-flag value, and what values does it read from `0x210e20020` or `0x211e20020`? Whether that sequence permits longer physical cluster-off periods requires a separate native experiment.

## Inspected revisions

The assessment uses Asahi m1n1 [`3e354a2467f4f724f254362626cae0633918e0c1`](https://github.com/AsahiLinux/m1n1/tree/3e354a2467f4f724f254362626cae0633918e0c1), and compares the relevant files with Aurora m1n1 [`ae94c931bbbaef6ce97e6caf1fcef453edb3e3e6`](https://github.com/aurora-silicon/m1n1/tree/ae94c931bbbaef6ce97e6caf1fcef453edb3e3e6). These are the pinned revisions in the adjacent Aurora audit. The source was retrieved again for this assessment; it was not inferred from prior notes.

`src/hv/hv_exc.c`, `src/hv/hv_vm.c`, and `src/hv/hv_wdt.c` are byte-identical between those revisions. Their SHA-256 digests are respectively `865213c5725878615ca857d86998113a093e379265596ad4394b4569ea9592fe`, `e2f036033a98e123a125f9ffb07798ec79f38d390f82149244a3fb9fd2f5991c`, and `425d9dc6990b2b76118951857dd523d9964595fc0a68534742b57c4a06399b40`. The Python hypervisor and `hv.c` differ, especially in the location of CPU-state emulation. The important interference exists in both, but exact implementations must not be conflated.

## WFI/WFE and Apple power registers

### WFI itself is not routinely converted into a proxy event

`HCR_EL2.TWI` is bit 13 and `TWE` is bit 14. The C initialization writes an explicit HCR value without either bit. The Python initialization adds `TACR`, `FMO` and `TTLBOS`, with other adjustments, and does not enable TWI or TWE. Thus the reviewed default configuration does not intercept guest WFI/WFE through those controls. This is a source default, not a readback of any particular running target. Record actual per-CPU HCR values in the eventual experiment.

Sources: [register definitions](https://github.com/AsahiLinux/m1n1/blob/3e354a2467f4f724f254362626cae0633918e0c1/src/arm_cpu_regs.h#L175-L176), [C initialization](https://github.com/AsahiLinux/m1n1/blob/3e354a2467f4f724f254362626cae0633918e0c1/src/hv/hv.c#L140-L147), [Python initialization](https://github.com/AsahiLinux/m1n1/blob/3e354a2467f4f724f254362626cae0633918e0c1/proxyclient/m1n1/hv/__init__.py#L1405-L1431).

`HACR_EL2` is a different Apple-specific control. The Python setup enables its ACC and PM traps. Looking only at HCR.TWI/TWE would miss the more consequential interference in the power-register path.

### Returning deep WFI is intentionally allowed; full shutdown is substituted

The C system-register handler passes through `CYC_OVRD` writes when they do not set `DISABLE_WFI_RET` or the FIQ-mode mask. Its comment explicitly explains that deep sleep is acceptable to the hypervisor while disabling WFI retention is not. Initialization first sets the WFI mode field back to zero on the primary and guest secondaries; subsequent permitted guest writes can change it.

If a `CYC_OVRD` write sets the rejected bits, the C handler returns false and the Python handler receives it. The Python handler skips that hardware write. For bit 0 specifically, it requests `hv_exit_cpu()` and removes the CPU from its guest-started dictionary. It does not perform the requested physical shutdown. The resulting secondary exit returns to the m1n1 SMP worker, which uses WFE because hypervisor initialization enabled `smp_set_wfe_mode(true)`.

Furthermore, the Python handler treats `ACC_CFG_EL1` and `ACC_OVRD_EL1` as read-only: guest writes are logged and skipped. A macOS trace containing an intended ACC override is therefore not proof that the override reached silicon.

Sources: [CYC_OVRD handler](https://github.com/AsahiLinux/m1n1/blob/3e354a2467f4f724f254362626cae0633918e0c1/src/hv/hv_exc.c#L324-L338), [mode initialization](https://github.com/AsahiLinux/m1n1/blob/3e354a2467f4f724f254362626cae0633918e0c1/src/hv/hv.c#L170-L172), [Python suppression and guest exit](https://github.com/AsahiLinux/m1n1/blob/3e354a2467f4f724f254362626cae0633918e0c1/proxyclient/m1n1/hv/__init__.py#L661-L703), [secondary exit](https://github.com/AsahiLinux/m1n1/blob/3e354a2467f4f724f254362626cae0633918e0c1/src/hv/hv.c#L324-L364), [SMP worker](https://github.com/AsahiLinux/m1n1/blob/3e354a2467f4f724f254362626cae0633918e0c1/src/smp.c#L118-L143).

### Startup and apparent CPU state are also virtualized

The T8103 PMGR CPU-start window at PMGR base plus `0x54000` is hooked. Writes to the core-start offsets call `start_secondary()`, which enters the guest on an existing m1n1 secondary. The hook does not simply forward all writes in that window to hardware.

Asahi's pinned `hv.c` hooks each CPU's `cpu-impl-reg + 0x100`, reads the physical value, then clears the lower byte for CPUs not marked guest-started. Aurora implements a related substitution in the Python handler and installs it during CPU startup. **Guest-visible CPU-state readback is not independent evidence of hardware power state.** Neither implementation should be used to validate the shutdown transition it is emulating.

Sources: [CPU-start hook](https://github.com/AsahiLinux/m1n1/blob/3e354a2467f4f724f254362626cae0633918e0c1/proxyclient/m1n1/hv/__init__.py#L1548-L1610), [Asahi state hook](https://github.com/AsahiLinux/m1n1/blob/3e354a2467f4f724f254362626cae0633918e0c1/src/hv/hv.c#L38-L94), [Aurora state hook](https://github.com/aurora-silicon/m1n1/blob/ae94c931bbbaef6ce97e6caf1fcef453edb3e3e6/proxyclient/m1n1/hv/__init__.py#L1542-L1566).

## Activity introduced by the measurement system

| Mechanism | Exact source behavior | Consequence for an idle experiment |
|---|---|---|
| Hypervisor timer | Interruptible CPU is rearmed at `CNTFRQ/1000`; secondaries use `CNTFRQ/1` when ECV is present, otherwise the same 1 kHz interval | Pinning polling to another cluster does not necessarily remove that cluster's timer wakeups. Record the ECV branch/readback rather than assume it. |
| CPU pinning | `hv_pin_cpu()` only sets `hv_pinned_cpu`; FIQ code uses it to select the interruptible CPU, and proxy entry waits while another CPU is pinned | This is a debugger/proxy control, not guest scheduler affinity or removal of hypervisor execution from all other CPUs. Non-selected proxy entries can spin. |
| Optional watchdog | `wdt_cpu=None` by default. If enabled, its CPU is removed from guest ADT and runs a watchdog loop using `udelay(1000)`; `udelay` polls the physical counter | A hidden physical core can remain busy and prevent its cluster from meeting all-core-idle conditions. This is conditional, not a mandatory reserved core in every run. |
| Proxy time stealing | Enabled by default; proxy entry rendezvous sends IPIs to other guest CPUs; elapsed proxy time is added to `stolen_time`, written through `CNTVOFF_EL2` | Guest virtual elapsed time and host/physical elapsed time differ. All-core rendezvous also disrupts the state being observed. |
| Transport preservation | Essential PMGR hooks maintain UART and selected USB/USB-AON devices and their parents; other power-gating readbacks are overridden | System/fabric power state and whole-machine power cannot be assumed native even if the CPU sequence is understood. |

Sources: [timer setup](https://github.com/AsahiLinux/m1n1/blob/3e354a2467f4f724f254362626cae0633918e0c1/src/hv/hv.c#L152-L168), [timer FIQ handling](https://github.com/AsahiLinux/m1n1/blob/3e354a2467f4f724f254362626cae0633918e0c1/src/hv/hv_exc.c#L578-L613), [pin/proxy wait](https://github.com/AsahiLinux/m1n1/blob/3e354a2467f4f724f254362626cae0633918e0c1/src/hv/hv_exc.c#L109-L127), [watchdog loop](https://github.com/AsahiLinux/m1n1/blob/3e354a2467f4f724f254362626cae0633918e0c1/src/hv/hv_wdt.c#L82-L99), [busy delay](https://github.com/AsahiLinux/m1n1/blob/3e354a2467f4f724f254362626cae0633918e0c1/src/utils.c#L95-L100), [time stealing](https://github.com/AsahiLinux/m1n1/blob/3e354a2467f4f724f254362626cae0633918e0c1/src/hv/hv_exc.c#L40-L79), [transport PMGR hooks](https://github.com/AsahiLinux/m1n1/blob/3e354a2467f4f724f254362626cae0633918e0c1/proxyclient/m1n1/hv/__init__.py#L1474-L1525).

Do not change timer routing, remove the shutdown suppression or disable retention merely to make a trace appear more native. Such a change would need its own interrupt/wake/context-preservation implementation and validation. It would no longer be a straightforward use of the reviewed hypervisor.

## What a trace of the pending bit would mean

The adjacent [binary review](review.md) identifies a conditional last-core call into `_waitAPSCPending`. Its flag at PMGR object `+0x73a52`, bit 0, can bypass the wait. The wait performs two sequential loops, each ending when a read sees bit 31 clear. It is not necessarily two total reads, and no minimum time separating the clear observations has been established. The corresponding physical command-register addresses are `0x210e20020` and `0x211e20020`.

The reviewed Python hypervisor contains a `cpu_hack` list with those two addresses **commented out**; it does not enable the nearby suppress-write hook for them by default. That is useful but insufficient: inspect all active tracer mappings and local modifications before calling a collected value a forwarded hardware value. [Source](https://github.com/AsahiLinux/m1n1/blob/3e354a2467f4f724f254362626cae0633918e0c1/proxyclient/m1n1/hv/__init__.py#L1527-L1540).

`TraceMode.ASYNC` still uses a software stage-2 mapping. Each traced access causes emulation in C. It reduces synchronous host interaction; it is not passive bus snooping. Reads are performed before their event is emitted, while write events are emitted before the physical write is attempted. Consequently a write event by itself is an attempted operation, not confirmation that the device accepted it. A host callback timestamp is not the physical access time: the MMIO event contains flags, PC, address and value, but no target timestamp.

Sources: [trace mapping selection](https://github.com/AsahiLinux/m1n1/blob/3e354a2467f4f724f254362626cae0633918e0c1/proxyclient/m1n1/hv/__init__.py#L323-L348), [invalid PTE mechanism](https://github.com/AsahiLinux/m1n1/blob/3e354a2467f4f724f254362626cae0633918e0c1/src/hv/hv_vm.c#L100-L111), [physical accesses and event ordering](https://github.com/AsahiLinux/m1n1/blob/3e354a2467f4f724f254362626cae0633918e0c1/src/hv/hv_vm.c#L996-L1083), [event structure](https://github.com/AsahiLinux/m1n1/blob/3e354a2467f4f724f254362626cae0633918e0c1/src/hv/hv.h#L20-L26).

This matters particularly for a busy-bit loop. The time spent trapping can let a transition finish before the read is performed, so a trace may show fewer busy observations than native execution would. Synchronous host handling can pause other CPUs through rendezvous, changing who requests DVFS and which core is last active. Conversely additional timing windows can create interleavings absent in a native sample. Observing bit 31 clear is a sampled register fact under that experiment; it is not proof of native quiescence duration, exclusive ownership of the DVFS register, or physical cluster shutdown.

## Bounded diagnostic experiment

This is a design specification, not an already implemented or executed experiment.

1. **Qualify the guest and record its environment.** Preserve matching target/proxy revisions, binary hashes, guest kernel identity, actual HCR/HACR/CYC_OVRD values per core, ECV branch, timer intervals, watchdog choice, CPU topology, active trace mappings, time-stealing configuration, and boot arguments. The Asahi hypervisor guide currently supports macOS 13.5 and 14.8.3; it does not qualify the local macOS 27 build. A successful older guest trace must retain its own identity rather than be attributed to this binary. The guide's example includes `clpc=0`, which is an explicit policy configuration difference and must be recorded. [Guide](https://asahilinux.org/docs/sw/m1n1-hypervisor/).
2. **Trace only the already identified boundary.** Capture function entry/exit and last-core selection; the bypass bit; cluster/core IDs; DVFS request writes; actual reads of the command register including bit 31; subsequent CYC_OVRD and ACC writes with whether each was forwarded or suppressed. Preserve the guest PC so unrelated reads are not mistaken for this wait. Do not add speculative MMIO polling of sleeping clusters.
3. **Use target C/AArch64 recording for timing work.** Extend a reviewed target trace point with a preallocated per-CPU ring, monotonically increasing sequence number, physical-counter timestamps bracketing the access, CPU/cluster/PC, value, flags and drop count. Keep host Python for setup/draining; avoid synchronous per-read host callbacks. Record the guest virtual-time offset when relevant. Buffering reduces transport disturbance but still leaves trap and memory-write disturbance.
4. **Control the measurement itself.** Compare no optional trace, sparse function-boundary records, and the narrow register trace. Measure the extra exits and runtime in each. End timing claims if instrumentation changes the branch frequency or active-core distribution materially; the trace can remain useful for ordering. A lower-overhead mode is still a hypervisor run.
5. **Report the narrow result.** For example: “In guest build X, with configuration Y, N last-core callbacks included the enabled wait; M observed busy reads, and each completed wait had the two expected clear-ending loops.” Report bypassed callbacks, incomplete sequences and dropped records explicitly. Do not convert this into a hardware power-state claim.

The first discriminating result is whether the current macOS path is actually enabled, rather than merely present in the binary. The second is whether it observes an outstanding DVFS command in the context that Linux would call its existing deep-idle routine. No result here justifies copying an unconditional polling loop into Linux.

## Native Linux validation after the diagnostic result

Use a separately reviewed C/AArch64 kernel instrumentation patch around the existing cpufreq request/completion path and `apple_cpu_deep_wfi()` entry/return. Record into per-CPU memory and drain after the window; `printk`, ftrace streaming and USB traffic inside each idle transition would introduce avoidable wakeups. Inspect lock ownership, interrupt masking and the future-write race: a clear read does not stop another CPU from submitting a new DVFS command immediately afterward.

Start with an observation-only baseline and count overlap between transition-pending and last-core idle entry. Distinguish guest/Linux active-core accounting from a physically active hidden core. Use CPU affinity and IRQ affinity in the native Linux experiment; `hv_pin_cpu()` is not a substitute. Keep one cluster for collection when studying the other, while acknowledging that this precludes claims of whole-SoC idle during that window. For the final all-core case, use deferred collection and a controlled wake source.

Only after resolving the concurrency and wake contract should a bounded serialization experiment be considered. Its timeout/failure behavior must preserve a working idle fallback; changing the Linux 10 ms target residency or replacing it with macOS's 50 us software latency would test a different claim. Validate repeated wake correctness and tail latency as well as energy. Linux callback time, CPU-state names, and a bit-clear trace are not sufficient independently calibrated hardware residency measures. A physical power result needs native execution plus a characterized counter or measurement method, and an otherwise matched baseline.

The T480 is useful as a serial host and evidence collector. Its presence does not cure target-side interference. The strongest eventual contribution would combine the binary condition, a diagnostic trace of its actual use, a native Linux concurrency explanation, and a repeatable native energy/wake result.

Historical memory supplied only the investigation boundary between diagnostic tracing and native validation. Every m1n1 implementation claim above was checked against the pinned source during this assessment.
