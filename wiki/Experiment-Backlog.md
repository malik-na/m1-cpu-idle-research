# Experiment Backlog

Each item has a falsifying outcome and a claim boundary. Work from observation to intervention. A source-permitted race, a software idle count, and a real energy loss are separate propositions.

## E1 — Does macOS actually take the last-core APSC wait?

**Hypothesis.** On the investigated macOS build, apparent final-core idle callbacks often execute the statically enabled `_waitAPSCPending` path, sometimes observing command BUSY.

**Evidence so far and next observation.** The five-second [PMGR ktrace capture](Live-Mac-Tracing.md) gives 47,068 complete CPUIdle event pairs and shows longer *apparent* last-core callback durations. A [retrospective marker correlation](../notes/mac-ktrace-perf-request-correlation.md) narrows the timing lead to E-core callbacks shortly after one performance-request signpost, but neither observation identifies the internal wait. The [instruction audit](../notes/mac-pmgr-command-order.md) shows that the CPU-complex emitter marks after `setPerfState` return, while the optional post-command BUSY-clear wait depends on an unrecorded caller flag; three other functions share the same marker helper. Repeating that correlation cannot supply the missing branch or BUSY value. The operator-authenticated [FBT inventory](../notes/raw/mac-fbt-inventory-26A428.json) failed its availability gate under SIP on this build; more sudo authentication does not qualify a probe. The next direct observation needs the [route note's](../notes/mac-apsc-direct-observation-route.md) caller-attributed branch and raw-value records on a separately qualified target. Preserve CPU/cluster, skip flag, entry/exit, forwarded-versus-emulated access, command value, BUSY and trace loss. The [EL0 probe](../notes/el0-capability-probe.md) can timestamp and tag a user-mode workload, but cannot read the command register. The m1n1 route remains a later authorized reboot experiment: macOS 27 guest compatibility is unqualified, and an older guest is a different build requiring its own instruction profile. The failed native FBT gate does not prove every qualified-target route infeasible, so the observation ticket remains open.

**Would weaken it.** A reliable branch trace consistently shows bypass or no wait during qualifying last-core callbacks, or the BUSY bit is never observed set under a workload that generates relevant DVFS transitions.

**Claim limit.** A timed callback, a trace of an attempted register operation, and a clear BUSY read are not physical cluster-off or energy measurements. [Static path](MacOS-Control-Path.md), [guest trace caveats](../notes/trace-validity.md).

## E2 — Can native Linux enter deep WFI with a pending DVFS command?

**Hypothesis.** The checked Linux source permits the final core to reach deep WFI while a cluster command is still BUSY, possibly after a same-cluster request or a cross-policy writer.

**First observation.** Pin the **actually booted** kernel/configuration, cpufreq policies and fast-switch state. Instrument DVFS submissions and the deep-WFI entry boundary with fixed, preallocated per-CPU records; prefer C setup and a small reviewed AArch64 entry sample. Include issuing/target CPUs, register value, physical counter timestamps, error/drop counts, and command BUSY. Keep the first variant observation-only, with no new wait or register write. The [Linux concurrency review](../notes/linux-dvfs-idle-concurrency.md) specifies exact seams, mapping lifetime and observer-effect controls.

**Native result, 3 October 2026.** The [qualified ABI 2 D/E/C/B/A block](../experiments/aurora-apsc-observer/WFI-ABI2-BLOCK-RESULT.md) found four raw BUSY reads at the first-attempt **pre-DSB** WFI-seam probe, including one conditional software final-entrant candidate under an unmeasured cross-CPU timing bound. The candidate's same-CPU SET-to-read upper bound is 607 ticks, exploratory rather than primary. The experiment did not observe the BUSY bit at the later WFI instruction or a physical peer/cluster state. The five-boot comparator accepted the positive block and rejected a second reverse block under the declared rules; a stronger hardware or instruction-boundary question needs a new protocol.

**Would weaken it.** Across repeated, controlled last-core and remote-writer opportunities, no pending command is observed near entry, with enough sensitivity and loss accounting to bound the negative result.

**Claim limit.** A positive BUSY sample proves pending command at a sample point, not harmful hardware collapse or a need to busy-wait. A remote writer can race after any check.

## E3 — Find an independent native physical-state signal

**Hypothesis.** PCPM's PMGR state register can distinguish at least one deeper cluster state while a core in another cluster reads it sparsely.

**First observation.** The audited candidate is `0x23b700048`, using the existing PMGR mapping; decode `ACTUAL=(raw >> 4) & 0xf`, preserving the raw value, error and timestamps. The low nibble is DESIRED and must not be substituted. Compare (a) active P-cluster work, (b) individual P cores in software CPU PD, and (c) overlapping P-core CPU PD intervals. Test whether sampling frequency changes the observed state. [Native observable audit](../notes/idle-observable-audit.md).

**Would weaken it.** The register remains constant across independently different conditions, faults when the domain is idle, or the act of reading prevents the transition.

**Claim limit.** Even a changing ACTUAL code is PMGR's reported state; map that state machine before calling it full rail-off. Sparse samples estimate occupancy only under documented sampling assumptions.

## E4 — Compare policy only after E1–E3

If E1 shows a real macOS wait, E2 shows Linux overlap, and E3 or another independently characterized signal connects overlap to a physical consequence, design a **bounded, opt-in** Linux policy experiment. Specify writer synchronization, timeout/fallback, wake and latency behavior, hotplug and mapping lifetime, and register ownership. Match completed work and USB/display/charging/thermal conditions against an unmodified native baseline. A blind BUSY-clear loop is not justified by the present evidence.

## E5 — Deeper non-returning CPU/cluster state

m1n1 already has stop/start and non-returning sleep primitives. A Linux runtime path would need a complete saved-state and reset-vector contract, timer/interrupt restoration, last-core coordination, pending-wakeup handling, firmware ownership, and safe fallback. Start with a written transition state machine and targeted correctness tests, then energy qualification. This is a separate, larger project from E1–E4. [Asahi baseline](Linux-and-Aurora-Baseline.md).
