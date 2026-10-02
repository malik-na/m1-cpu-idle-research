# Native ABI 2 first-attempt command-state capture, 2 October 2026

On a fresh J313/T8103 boot of `Aurora-APSC-research-wfi-seam`, the E
`wfi_mmio` capture recorded **four APSC command words with BUSY bit 31 set**
at the first deep-idle attempt after the power-control MSR and before the
original `dsb sy; wfi`. This is a positive observation at that probe site.
It does not say whether BUSY persisted at the WFI instruction, whether a
peer was physically asleep, or whether cluster power was removed.

The live release was `7.1.12-ARCH-apsc-20261002-wfi`, GNU Build-ID
`11e80be6d8b358eee9aa847a0f814aff02b66c43`, configuration SHA-256
`f86b80f4dcef277be874f476293d8b8055053072f7209625586b60e2227f905d`.
The selected Limine entry and same-boot raw FDT checks verified eight CPUs,
the two T8103 cluster command resources at `0x210e20020` and
`0x211e20020`, and the published controller topology. This boot's private
ID differs from the [D clock-only pilot](WFI-D-RESULT.md); both use the same
release/build/configuration and workload. The private qualification and
operator-confirmed Wi-Fi/brightness acceptance preceded E. AC was connected,
and brightness was restored to 155 before acquisition.

The requested 2,000 ms acquisition had an actual external window of
2,038.350 ms. Both CPU 1 and CPU 5 completed 40 pulses strictly within that
window. The observer committed all 564 matched first-attempt WFI probes
(369 cluster 0, 195 cluster 1), with zero overflow, missing commit, bad
mapping, after-stop sample or pending slot after drain. The four BUSY reads
were one on cluster 0 and three on cluster 1. Every one has a recorded
preceding successful SET on the **same CPU**. The table uses the
predeclared conservative upper bound `sample.t1 - SET.t0`; the full paired-
opportunity classification additionally assumes an unmeasured 240-tick
cross-CPU error to establish strict capture interior, earliest sample, and
absence of intervening writes from other CPUs.

| Cluster | SET writer / policy representative / probe CPU | Probe token | Raw command | Upper SET-to-probe bound | Declared pair stratum | Conditional software final-entrant screen |
|---|---|---:|---|---:|---|---|
| 0 | 1 / 0 / 1 | 13 | `0x40080102102` | 144 ticks | Primary (≤600) | No |
| 1 | 4 / 4 / 4 | 2 | `0x40080101101` | 341 ticks | Primary (≤600) | No |
| 1 | 4 / 4 / 4 | 134 | `0x40080108108` | 449 ticks | Primary (≤600) | No |
| 1 | 5 / 4 / 5 | 7 | `0x4008010c10c` | 607 ticks | Exploratory (≤2,400) only | Yes, under assumed E=240 |

The CPU 5/token 7 row's raw bracket gap is 596 ticks, but its **upper**
bound is 607. It therefore fails the declared 600-tick primary gate. Its
own software idle interval and all three other cluster-1 CPU intervals are
complete and strictly model-interior; the peers entered before CPU 5's
entry and remained in their recorded software intervals through the probe.
That makes it one *conditional software candidate final entrant*. The
cross-CPU clock bound was assumed rather than measured throughout capture,
and software idle intervals do not prove peer physical sleep. There are zero
candidate-qualified **primary** pairs in either cluster.

The [public E packet](native-evidence/E/status.txt) retains raw numerical
observer, WFI, counter and worker streams, status/error counts, a filtered
chronology and bounded endpoint observations. The
[publisher](publish_wfi_evidence.py) verified the private acquisition
manifest, independently replayed the ABI 2 analyzer, and produced the
[reviewed receipt](wfi-mmio-receipt.json) linking private input and public
output hashes. This replay from published bytes reproduces the BUSY pairs:

```sh
python3 - <<'PY'
import gzip, sys
from pathlib import Path
sys.path.insert(0, 'experiments/aurora-apsc-observer')
import analyze_wfi
p = Path('experiments/aurora-apsc-observer/native-evidence/E')
r = analyze_wfi.analyze_text(
    gzip.open(p / 'events.csv.gz', 'rt').read(),
    (p / 'status.txt').read_text(),
    gzip.open(p / 'wfi-events.csv.gz', 'rt').read())
assert r['integrity']['clean']
for row in r['paired_opportunities']['decisions']:
    if row['status'] in ('primary_pair', 'exploratory_only_pair') and row['sample']['busy_bit31']:
        print(row['status'], row['set']['cluster'], row['set']['cpu'],
              row['sample']['cpu'], row['sample']['token'],
              row['sample']['raw_command'], row['largest_lag_under_model_ticks'])
PY
```

The capture has only **one cluster-0 and two cluster-1 primary paired
opportunities**, below the predeclared 20-per-cluster negative-exposure gate;
candidate-primary exposure is zero in both clusters. Those gates limit a
zero-detection claim, not the four positive raw observations. Pre/post
counter phases each completed 1,792 exchanges with no recorded errors under
the declared conditional model, but they do not guarantee a capture-wide
cross-CPU clock bound. AC/brightness/policy endpoints matched, thermal zone
0 was 35.8→35.7°C, and the pre/post kernel logs were byte-identical in the
private packet. Network traffic occurred over the broad endpoint interval;
background activity during the armed window is not isolated. D's probe
bracket median/p95/max was 1/2/2 ticks; E's was 12/14/48 ticks. That
comparison is observational and does not isolate total observer cost or
energy use; D and E also differed in thermal conditions.

The [build](wfi-build-receipt.json) and [deployment](wfi-deployment-receipt.json)
receipts link the running binary and modules to the installed research
image. The build receipt did not record a build-time hash of the WFI patch
or complete source tree, so the patch's publication hash alone is not a
cryptographic source-to-binary proof. Full boot arguments, raw FDT, logs,
boot ID and acquisition-time manifest remain private. The predeclared
[D/E/C/B/A block](WFI-PLAN.md) now has a separate
[fresh-boot C control](WFI-C-CONTROL-RESULT.md); B/A controls and cross-boot
comparability review remain before issue #5's full result is closed.
