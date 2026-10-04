# Records and sparse-MMIO boot comparison

Both boots used the same pinned kernel image, nine-second four-P workload,
APSC `records 9500` control, 100 ms PCPM cadence, charger, brightness, CPU
policy and USB state. The first PCPM boot recorded timestamps without a
register read; the second made sparse reads. Both acquisition streams passed
their machine integrity screens and had zero PCPM slot, CPU and counter loss,
zero APSC overflow or missing commits, and complete counter pre/post phases.

| Observation | Records-only boot | Sparse-MMIO boot |
| --- | ---: | ---: |
| PCPM register reads | 0 | 90, all `0x000021f0` |
| Guarded all-P-released sample brackets | 24 | 24 |
| Conditional complete four-P software witnesses | 21/24 | 8/24 |
| PCPM local monotonic bracket median | 458 ns | 4,062.5 ns |
| PCPM local monotonic bracket maximum | 3,209 ns | 83,872 ns |
| APSC idle commits on P CPUs 4, 5, 6, 7 | 130, 547, 621, 341 | 517, 844, 461, 469 |
| APSC DVFS commits on clusters 0, 1 | 618, 81 | 1,697, 327 |
| Four-active delivered loop iterations | 5,788,631,040 | 5,594,382,336 (−3.356%) |
| One-active delivered loop iterations | 1,454,243,840 | 1,452,212,224 (−0.140%) |
| Four-wake delivered loop iterations | 5,776,998,400 | 5,811,568,640 (+0.598%) |
| Battery, AC, brightness | 100%; online; 155 | 100%; online; 155 |
| Thermal sensor, before → after | 33.5 → 33.5 °C | 33.9 → 33.8 °C |
| Non-loopback network traffic between environment snapshots, received/sent | 130,244 / 32,418 bytes | 549,751 / 122,701 bytes |

The 21/24 and 8/24 witness counts use strict interval inequalities with
**E=240 ticks assumed**, not verified as a capture-wide cross-CPU error
bound, and G=24,000 ticks as the software-boundary guard. All eight MMIO
words with conditional witnesses were still `0x000021f0`. The longer MMIO
sample brackets show that the read took time locally; they do not measure
its effect on P-core power state. APSC idle/DVFS counts and delivered work
varied, and network activity was higher between the MMIO boot's environment
snapshots. Those snapshots also include pre/post qualification and settling,
so the deltas are not restricted to the nine-second capture. Two nonidentical
boots cannot isolate whether MMIO caused any of these differences. The
predeclared observer-effect protocol still needs an unarmed/no-PCPM control,
an additional matched records-mode control, and varied cadence/phase if this signal is
pursued further. The failed ACTUAL contrast gives no automatic reason for a
second MMIO boot.

The public replay script recomputes the row counts, guarded phase brackets,
conditional witnesses, and sample-bracket medians from the exported streams.
The battery, thermal and policy endpoints are in the public snapshot
projections. Network bytes are aggregate deltas for the sole non-loopback
interface, with its name removed. They were derived from the four private
environment snapshots with SHA-256 hashes (records before/after:
`3438e7dd8cca0825480e9537fd4a296073c3cddc36c1e4811270f100400c9d40`,
`a71c24d93830839dffbed7cc057d5b11f64be81fd8db7e57460caeb5981db250`;
MMIO before/after:
`42120d3d4205967e483384d8778c8451012953707b94388802d568b4ab07dcf2`,
`2b2113751016d2a380588c20da87711d138316ce84eeda7a8b8edf77c63b1986`).
Those private network counters are deliberately absent from the public
packet, so this aggregate comparison cannot be replayed from public files
alone. It is a disclosed contextual difference, not a causal estimate.
