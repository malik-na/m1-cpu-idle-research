# Evidence Standard

CPU-idle language often jumps from an API name to a silicon claim. This project keeps six levels distinct. A higher level needs its own observation; it is not inferred automatically from a lower one.

| Level | What it can establish | Example here | What it cannot establish alone |
|---|---|---|---|
| Public source | Behavior permitted or intended by a pinned revision | Asahi `cpuidle-apple.c` sets the returning deep-WFI mode | Behavior of an unverified installed kernel or hardware outcome |
| Matching local binary | Instructions and data flow in the installed build | ApplePMGR polls the DVFS command on a last-core path | How often a conditional path executes |
| Live software trace | An event/branch/value at a sample point | `PERF_CPU_IDLE` events in a bounded macOS ktrace capture | Physical cluster-off residency, energy, or an untraced branch |
| Software accounting | Time spent in an OS reporting state or callback | IOReport IDLE, Linux `state1/time` | Which silicon idle depth occurred |
| Native hardware state | A characterized state-machine read or external measurement on the native target | Proposed PCPM `ACTUAL` read | Full rail-off or energy without validating the state semantics |
| Matched energy and wake behavior | Effect under controlled completed work and conditions | Not yet achieved for the proposed APSC wait | Universal behavior across builds/chips/workloads |

An m1n1 hypervisor trace is a **guest control-flow diagnostic**. It can show forwarded or emulated operations under a recorded configuration, but its timer, proxy transport, and power-register handling can change the very idle behavior being studied. See [`notes/trace-validity.md`](../notes/trace-validity.md).

## Claim rules

- **Use exact target language.** “The checked macOS 27.0 / 26A428 binary contains a wait” is supportable; “macOS always waits” needs runtime and version scope.
- **Name the measurement.** A `CPU PD` software interval is not a physical CPU power-down measurement. A PMGR state read, if qualified, reports that controller's state, not automatically the voltage rail.
- **Keep declared parameters separate from observations.** Linux `exit_latency` and `target_residency` are governor metadata. macOS's `cpu-power-gate-latency-us` becomes a 50 microsecond *software* parameter in this build; neither value is a measured silicon break-even point.
- **Report failed and negative probes.** Include trace loss, incomplete intervals, no-op registrations, zero counters, permission failures, and conditions in which a candidate did not distinguish states.
- **Label inference explicitly.** State which source or measurement supports a conclusion, what extra assumption is needed, and one plausible alternative.
- **Treat novelty as a checked-scope statement.** Name repositories, revisions and search surface; do not equate an absent search result with universal non-discovery.

For numeric power comparisons, record matched completed work, battery/AC status, display and USB state, thermal trends, sampling cadence, run order, and confidence/variance. A whole-machine discharge delta does not isolate CPU idle. For timing, include counter frequency, target versus host clock, event loss, and instrumentation overhead.
