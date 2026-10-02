# Native T8103 APSC command observation, 2 October 2026

The completed capacity-kernel block provides a **native command-register
BUSY observation at the C pre-WFI software hook**. It does not establish
BUSY at the WFI instruction or a physical cluster power transition. The
strongest sample followed a recorded SET submission on the same CPU; its
interpretation as a *software candidate final entrant* additionally assumes
an unproven cross-CPU clock-error bound.

## Target and predeclared question

The target was the operator's base-M1 MacBook Air, J313/T8103, booted
natively into Omarchy/Aurora Linux. All three fresh boots used the separate
`Aurora-APSC-research-capacity` entry and release
`7.1.12-ARCH-apsc-20261002`, GNU build ID
`eb8fe1838f2c34f24f83ec53da25d2f9ae150b12`, exported config SHA-256
`f86b80f4dcef277be874f476293d8b8055053072f7209625586b60e2227f905d`,
and the [capacity image](capacity-revision-receipt.json) SHA-256
`e191db32335e471ab372aa486d91373bb7d87d2234db557ed3413fed677563a0`.
The observer/counter source is the three published patches on Aurora commit
[`90a95335a49aec3a0045a76da140452ad6585eb3`](https://github.com/iconidentify/aurora-linux/tree/90a95335a49aec3a0045a76da140452ad6585eb3).
The boot loader reported Limine 12.9.1 and Das U-Boot UEFI 2.110 in the
[protected boot receipt](../../notes/raw/native-linux-boot-qualification-20261002.json);
the complete per-boot FDT and logs remain private. Three different boot IDs
and matching build/config notes were checked without publishing the IDs.
The FDTs retained the same eight-CPU topology and cluster register mapping;
their per-boot dynamic properties differed.

The [protocol](NATIVE-PLAN.md) asked whether a candidate final software
entrant could read APSC command BUSY after a recorded target-cluster SET.
A valid pending read with compatible ordering could support that narrow
claim; complete, sufficiently sensitive zero-BUSY windows could weaken it.
A and B isolate the unarmed and records-only modes; C makes one read of the
cluster command register at each deep-idle entry hook. The hook precedes
context-tracking idle entry and the assembly WFI. The observation-only
patches do not add an idle-policy wait or write a power/frequency register.

## Acquisition and raw data

The [public evidence directory](native-evidence/README.md) holds the
reviewed, byte-exact status and sysfs snapshots, deterministic gzip copies
of the raw numerical CSV streams, a whitelisted chronology, the acquisition
hash mapping, and reproducible decoder outputs. The full private packets
retain boot arguments, complete FDT, kernel logs, build configuration and
acquisition-time `SHA256SUMS`; all original manifests verified before export.
The [export script](publish_native_evidence.py) names the published fields and
checks every private packet file against its manifest. The
[derivation script](derive_native_evidence.py) reruns the observer decoder
from the public CSV/status bytes, with exact input and analyzer hashes in its
[receipt](native-evidence/analysis-receipt.json).

| Fresh boot | Observer | External window | In-window records | Successful SET | MMIO samples / BUSY | Worker pulses fully inside external window |
|---|---|---:|---:|---:|---:|---:|
| [A](native-evidence/A/status.txt) | Unarmed baseline | 2000.182 ms | 0, by design | — | — | 39 per CPU |
| [B](native-evidence/B/analysis-unbounded.json) | Records only | 2037.503 ms | 1,928 | 141 | 0 / 0 | 40 per CPU |
| [C](native-evidence/C/analysis-unbounded.json) | MMIO | 2062.208 ms | 1,682 | 220 | 734 / 16 | 40 per CPU |

Each worker on logical CPUs 1 and 5 completed all 44 ordered pulses of
1,048,576 xorshift iterations with matching checksum sequences. Each boot's
pre and post counter phases completed 1,792 star exchanges, with no call
errors; both phases and status are exported. B and C have zero observer
overflow, missing commits, sequence gaps and MMIO read errors. Five B and
six C idle-entry records trail the capture without matched exits, so the
decoder does not treat them as complete intervals. A was intentionally not
armed. The earlier [pilot](native-pilot-receipt.json) had a CPU-0 ring
overflow in B and is excluded from this matched block.

All sessions used battery power, brightness 155/420 (actual 164), all eight
CPUs online, `apple_idle`/`menu`, and unchanged endpoint frequency/idle
policies. Battery fell from 66% in A to 65% in B and 63% in C; thermal-zone-0
endpoint readings were approximately 34.3, 34.6 and 34.2 °C. USB, network
and background work were not fully observed. The A window ended before
its final worker pulse, unlike B/C; actual windows differed and mode order
was fixed A→B→C. These data do not quantify observer overhead or an energy
effect.

## Positive register witness and clock boundary

The native C status maps the E-cluster command register to `0x210e20020`
and the P-cluster command register to `0x211e20020`: FDT resource bases
plus the documented `0x20` offset. The strongest two raw
[C event rows](native-evidence/C/events.csv.gz) are:

```text
dvfs,7,7,1,4,0xf0,1,11,12,,3350690840,3350690841,0x40000103103,0x4000210c10c,0,0
idle_enter,0,7,1,,,,,,1,3350691390,3350691399,,0x4008010c10c,0,1
```

CPU 7 submitted a successful cluster-1 SET (`ret=0`) ending at counter tick
`3350690841`; the same CPU's later pre-WFI command read began at
`3350691390`, a strict 549-tick gap (22.875 µs at 24 MHz). The returned
word has BUSY bit 31 set and the same pstate fields. Same-CPU order does
not need a cross-CPU clock bound. Other CPUs could have written the same
register between these observations, so this does not assign BUSY causally
to that SET or measure command completion.

The saved default decoder correctly reports
`unavailable_without_clock_bound`. With the **predeclared but unproven**
pairwise error assumption `E=240` ticks (10 µs), the
[conditional C analysis](native-evidence/C/analysis-assumed-E240.json)
finds 37 software candidate final entrants, all cluster 1: one BUSY
(CPU 7) and 36 clear. Recorded idle intervals for CPUs 4–6 surround CPU
7's read, with minimum peer margin 87,081 ticks *after* the assumed
bound. The analogous B analysis finds 53 conditional cluster-1 entrants,
but B made no MMIO reads. The finite pre/post counter exchanges are
compatible with E=240 under a constant-offset model; they cannot guarantee
that bound through the unsampled window. The final-entrant label is therefore
conditional, whereas CPU 7's local SET→BUSY sample order is direct.

The 16 BUSY reads in C are native observations of the APSC command-register
bit, not evidence that 16 final cores reached WFI with a pending command.
Cluster 0 has **zero** conditional final-entrant candidates despite 189
recorded SET writes, so the protocol's 20-opportunity negative gate fails.
There is no defensible cluster-0 absence claim. The C hook is upstream of
the WFI instruction, and no independent rail, residency, energy or wake
measurement accompanied it. Hardware may serialize later, complete the
command before WFI, or handle a pending command safely. These data do not
establish a Linux defect or justify an idle-path change.
