# Experiment Backlog

Each item has a falsifying outcome and a claim boundary. Work from observation to intervention. A source-permitted race, a software idle count, and a real energy loss are separate propositions.

## E1 — Does macOS actually take the last-core APSC wait?

**Hypothesis.** On the investigated macOS build, apparent final-core idle callbacks often execute the statically enabled `_waitAPSCPending` path, sometimes observing command BUSY.

**First observation.** The five-second [PMGR ktrace capture](Live-Mac-Tracing.md) gives 47,068 complete CPUIdle event pairs and shows longer *apparent* last-core callback durations. A [retrospective marker correlation](../notes/mac-ktrace-perf-request-correlation.md) narrows the timing lead to E-core callbacks shortly after one performance-request signpost, but neither observation identifies the internal wait. On this Mac alone, first repeat the predeclared 50 µs marker-age comparison under controlled work and idle phases, with trace-loss and no-trace baselines. To identify `_waitAPSCPending`, obtain a bounded branch-specific signal or a narrowly scoped guest trace with explicit forwarded/emulated-register records. Preserve CPU/cluster, skip flag, entry/exit, command value and BUSY observations, plus trace loss. A macOS 27 m1n1 guest is not currently documented as supported; an older guest would be a different build and must be labeled separately.

**Would weaken it.** A reliable branch trace consistently shows bypass or no wait during qualifying last-core callbacks, or the BUSY bit is never observed set under a workload that generates relevant DVFS transitions.

**Claim limit.** A timed callback, a trace of an attempted register operation, and a clear BUSY read are not physical cluster-off or energy measurements. [Static path](MacOS-Control-Path.md), [guest trace caveats](../notes/trace-validity.md).

## E2 — Can native Linux enter deep WFI with a pending DVFS command?

**Hypothesis.** The checked Linux source permits the final core to reach deep WFI while a cluster command is still BUSY, possibly after a same-cluster request or a cross-policy writer.

**First observation.** Pin the **actually booted** kernel/configuration, cpufreq policies and fast-switch state. Instrument DVFS submissions and the deep-WFI entry boundary with fixed, preallocated per-CPU records; prefer C setup and a small reviewed AArch64 entry sample. Include issuing/target CPUs, register value, physical counter timestamps, error/drop counts, and command BUSY. Keep the first variant observation-only, with no new wait or register write. The [Linux concurrency review](../notes/linux-dvfs-idle-concurrency.md) specifies exact seams, mapping lifetime and observer-effect controls.

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
