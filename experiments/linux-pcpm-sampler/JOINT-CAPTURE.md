# Planning a joint PCPM and software-idle capture

This is a later-native procedure for [PCPM calibration](README.md), not a capture record. It requires separately authorized native boot and acquisition, a qualified target configuration, and the [APSC observer's prerequisites](../linux-apsc-observer/NATIVE-RUN.md). No joint capture has run. Both collectors are one-shot instruments and have independent, synchronous control writes.

## Common time domain

PCPM ABI 2 retains monotonic nanoseconds for scheduling and adds ordered physical-counter timestamps around each sample. The counter bracket contains the existing nanosecond bracket and optional PMGR read. Use these raw ticks when comparing with the APSC observer; do not convert `ktime_get_ns()` by multiplying by `CNTFRQ` or subtracting a guessed boot offset. ABI 1 has no such counter bracket and cannot supply this association retroactively.

Matching frequency and counter-selection metadata is necessary but does not establish cross-CPU clock accuracy or a common boot. Retain the private boot/source/configuration packet and the [counter-qualification helper's](../linux-counter-qualification/README.md) pre/post evidence. Qualifying exchanges must occur outside **both** acquisitions, with the predeclared settling interval before the first starts. Before/after agreement cannot exclude an unsampled transient clock excursion.

## Acquisition order

1. Verify the actual target, both default-off configurations, exact patches, metadata, topology, mapping qualification, unused/ready status and decoder versions. Choose the workload, power/thermal conditions, nominal durations, cadence/phase, clock-error assumption and boundary guard before arming. Preserve pre-acquisition exports.
2. Complete and save the independent counter pre phase. Review its result and wait the declared settling period. Do not perform qualification exchanges while either collector is recording.
3. Launch the two control writes concurrently. A sequential write to the APSC observer followed by a PCPM command waits for the first acquisition to finish and does not create the desired overlap. Use separate operator-controlled processes and preserve each exact command, start/return timing, stderr and exit status. A successful shell launch does not prove overlapping sample windows.
4. Let both one-shot acquisitions finish, save their complete status and CSV exports, and preserve failures even if one command returns early. Do not rearm, overwrite, or use another boot to fill a missing stream. Run the counter post phase only after both collectors have drained.
5. Analyze each stream independently before pairing. Require compatible target/counter metadata, valid raw brackets, stable CPU membership and explicit loss accounting. Derive any usable overlap from the exported raw ticks and stated uncertainty; preserve portions that do not overlap. Short or absent overlap is a failed pairing, not a negative PCPM-state result.

Start PCPM calibration with the APSC observer in **records-only** mode so it supplies a software-idle timeline without its additional APSC register reads. Keep that timeline instrumentation constant across the no-PCPM, PCPM-records and PCPM-MMIO comparisons. A separate observer-disabled baseline is needed to assess its fixed hooks. Studying simultaneous APSC BUSY and PCPM words adds another observer condition and requires its own matched controls. Existing public build checks establish neither timing sensitivity nor measurement cost.

## Conditional association

For a valid PCPM bracket `[p0, p1]`, a candidate association with all four P-core software-idle intervals requires a complete, lossless entry/return witness for **each** P core. Under a separately justified maximum pairwise counter-comparison error `E` and predeclared nonnegative software-boundary guard `G`, require:

```text
peer.entry.t1 + E + G < p0
p1 + E + G < peer.exit.t0
```

Both inequalities are strict. Apply the observer's strict capture-interior checks and non-reentrant per-CPU interval grammar first. Use wide integer arithmetic; do not wrap unsigned sums. Retain every witness, the uncertainty provenance and exclusions. A missing peer, failed counter bracket, overflow/loss, unresolved ordering or unqualified clock prevents that association. Do not choose `E` or `G` afterward to force an attractive result.

This supports only the conditional statement that the PMGR word was sampled within overlapping **software** intervals. Those intervals include work around WFI; the association does not establish physical final-core sleep, rail state, exact transition time or a causal DVFS effect. Sparse code counts are not occupancy. Native workload controls and characterization of the sampler's added barriers, counter reads, timer wakes and MMIO effects remain necessary to calibrate a useful signal.
