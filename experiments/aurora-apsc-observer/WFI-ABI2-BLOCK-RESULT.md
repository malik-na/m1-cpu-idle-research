# Native ABI 2 D/E/C/B/A result for issue #5, 3 October 2026

The prospective five-boot block found **four APSC command words with BUSY
bit 31 set** at E's first deep-idle attempt after the power-control MSR and
before the original `dsb sy; wfi`. One of those four has a complete own and
three-peer **software idle-interval** witness under the explicitly assumed,
unmeasured 240-tick cross-CPU clock-error model. The verifier therefore
reports `conditional_software_final_entrant_pre_DSB_BUSY_observed`. It does
**not** establish that BUSY persisted to the WFI instruction, that a peer
was physically asleep, that cluster power changed, or that energy improved.
The exact candidate final-core deep-WFI-entry question in [issue #5](https://github.com/malik-na/m1-cpu-idle-research/issues/5)
remains unresolved at those stronger hardware and instruction boundaries.

This follows the predeclared [D/E/C/B/A first-block](WFI-PLAN.md) mode
order. The [sanitized comparison](wfi-abi2-first-block-comparison.json)
replayed every acquisition hash and public receipt/evidence file **in the
five supplied packets**, then checked distinct private boot IDs, strictly
increasing **recorded** UTC capture intervals and matching WFI kernel-build and
collector identities. It cannot independently rule out omitted attempts or
wall-clock correction. The running target was an Apple MacBook Air M1 (J313/T8103),
Aurora source commit `90a95335a49aec3a0045a76da140452ad6585eb3`,
kernel release `7.1.12-ARCH-apsc-20261002-wfi`, GNU Build-ID
`11e80be6d8b358eee9aa847a0f814aff02b66c43`, configuration SHA-256
`f86b80f4dcef277be874f476293d8b8055053072f7209625586b60e2227f905d`,
and Limine entry `Aurora-APSC-research-wfi-seam`. The same-boot FDT
qualification checked eight CPUs and both T8103 APSC command resources;
the stock fallback and working capacity entry stayed installed. The
[build](wfi-build-receipt.json) and [deployment](wfi-deployment-receipt.json)
receipts bind the reviewed installed image and modules to that live
identity. The build receipt lacks a build-time WFI patch/full-source-tree
digest, so the publication-time patch hash is **not** a cryptographic
source-to-image proof. The observation-only variant adds a command read
without a new wait or APSC write; the original WFI instruction/retry and
command writes are unchanged in the reviewed source and linked code.

| Order | Mode and site | Recorded probes/reads | BUSY-bit reads | Fully interior worker pulses per CPU | Thermal zone 0 endpoints |
|---|---|---:|---:|---:|---:|
| [D](WFI-D-RESULT.md) | WFI seam, clock only | 660 | Not read | 40 | 37.3→37.3°C |
| [E](WFI-E-RESULT.md) | WFI seam, command read | 564 | 4 | 40 | 35.8→35.7°C |
| [C](WFI-C-CONTROL-RESULT.md) | Earlier C hook, command read | 563 | 13, all cluster 0 | 40 | 34.1→34.1°C |
| [B](WFI-B-CONTROL-RESULT.md) | Earlier C hook, records only | 472 | Not read | 40 | 33.9→33.9°C |
| [A](WFI-A-BASELINE-RESULT.md) | Observer unarmed | 0 | Not read | 39 | 33.7→33.7°C |

Each worker completed the same pinned 44-pulse program on CPU 1 and CPU 5.
For its worker-duration comparison, the comparator used only pulse indices
**4–42**, 39 fully interior pulses common to all five actual windows; each
worker's per-index checksum matched. Probe and paired-opportunity analyses
use each packet's own clean interior capture window.
All captures used AC online `1`, panel brightness `155`, CPUs 0–7 online,
`apple_idle`/`menu` and matching cpufreq policy settings; instantaneous
reported frequencies varied. Same-boot
machine and user-confirmed Wi-Fi/brightness checks preceded each packet.
All active observer streams had zero overflow, missing commit or mapping
error; the baseline observer remained ready and unarmed. Private pre/post
kernel logs were byte-identical in every packet. Pre/post counter phases
each completed 1,792 exchanges per packet under the declared **conditional**
model, but no guaranteed capture-wide cross-CPU clock bound was measured.
The full boot arguments, boot IDs, raw FDT, logs and private acquisition
manifests are withheld; the [ABI 2 publication contract](WFI-PUBLICATION.md)
defines the numerical projection and hash links.

The E read site is a **first-attempt pre-DSB probe**, before the original
WFI instruction. Its four BUSY rows, raw command words and 24 MHz counter
brackets are replayable from the [public E packet](native-evidence/E/status.txt).
Every row has a preceding successful SET on the same CPU. A target is a
cluster command; the policy representative CPU is not an observed
individual hardware target core. The bounds below use the predeclared
conservative `probe.t1 - SET.t0` on each same-CPU pair:

| Cluster | SET writer / policy CPU / probe CPU | Probe token | SET bracket ticks | Probe bracket ticks | Raw command | Upper lag | Declared stratum |
|---|---|---:|---|---|---|---:|---|
| 0 | 1 / 0 / 1 | 13 | 6896222186–6896222187 | 6896222325–6896222330 | `0x40080102102` | 144 | Primary ≤600 |
| 1 | 4 / 4 / 4 | 2 | 6891456999–6891457000 | 6891457328–6891457340 | `0x40080101101` | 341 | Primary ≤600 |
| 1 | 4 / 4 / 4 | 134 | 6938875994–6938875995 | 6938876432–6938876443 | `0x40080108108` | 449 | Primary ≤600 |
| 1 | 5 / 4 / 5 | 7 | 6898143758–6898143759 | 6898144355–6898144365 | `0x4008010c10c` | 607 | Exploratory ≤2400 only |

The CPU 5/token 7 row is the sole conditional software final-entrant
candidate. Its own complete idle interval and all three cluster-1 peer
software intervals enclose the probe with strict margins **only under
assumed E=240**. Its same-CPU SET→BUSY order is direct, but the 607-tick
upper bound exceeds the primary 600-tick gate, and cross-CPU peer ordering
remains unqualified. The candidate has **no primary paired opportunity**;
it must not be counted as a candidate-primary positive or as proof that the
peers were physically asleep. The other 560 E command reads did not have
BUSY bit 31 set at their individual probe instants. That is a bounded
sample statement, not absence over their windows.

For the declared negative-sensitivity screen, E had only **one cluster-0
and two cluster-1 primary paired SET→probe opportunities**, all BUSY.
Candidate-primary exposure was zero in both clusters. C showed pending
commands in the comparable primary lag stratum for cluster 0 (10/10 BUSY
pairs) but had no cluster-1 primary pair. The 20-primary-pair-per-cluster
zero-detection gate, candidate-specific 20-pair gate and both-cluster C
control gate therefore fail. They do not invalidate the positive raw E
reads; they bar a sensitive negative or cluster-wide rate claim. C and E
are different boots, so their rows are not event-level pairs.

The measured bracket distributions were D WFI clock-only median/p95/max
**1/2/2 ticks** (660 rows), E WFI MMIO **12/14/48 ticks** (564), B C-hook
records-only **2/4/7 ticks** (472), and C C-hook MMIO **13/18/113 ticks**
(563). These bracket only the timed code, excluding event construction,
ring publication and fixed inactive-hook cost. They are different-boot
observations, not isolated total instrumentation overhead or an energy
measurement. The five boots cooled from 37.3°C to 33.7°C while the battery
charged from about 44% to 94%; network traffic and whole-system activity
were observed only at broad endpoints, and no numerical thermal match band
was declared. We therefore do not claim matched thermal/background
conditions or a sensitive C-versus-E contrast. An earlier automatic request
for the C entry booted stock and acquired no C packet; the
[incident](WFI-C-BOOT-SELECTION-INCIDENT.md) is retained separately.

The predeclared comparator rejects a second reverse block after a
first-block pre-DSB BUSY witness. A further study of state at the WFI
instruction, physical peer state, command completion or energy would need
a separately designed observation and its own validation. No Linux
idle-policy change, APSC wait, or physical-power improvement follows from
this block.
