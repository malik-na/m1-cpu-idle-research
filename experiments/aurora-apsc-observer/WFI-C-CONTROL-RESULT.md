# Native ABI 2 C-hook control, 2 October 2026

On a fresh boot of the same WFI research image used for D and E, the C
`mmio` control observed **13 APSC command words with BUSY bit 31 set** at
the earlier C `idle_enter` hook, all in cluster 0. Ten cluster-0 successful
SETs had a BUSY C sample in the predeclared primary comparable-lag stratum
(conservative upper bound at most 600 ticks). Cluster 1 had **no primary
paired opportunity**, so this C packet does not establish comparable-lag
cluster-1 control sensitivity. C and E are different boots and do not sample
the same events. A C-hook read does not establish command state at the later
first-attempt WFI probe, at the WFI instruction, or in physical hardware
power state.

The manually selected `Aurora-APSC-research-wfi-seam` boot reported release
`7.1.12-ARCH-apsc-20261002-wfi`, GNU Build-ID
`11e80be6d8b358eee9aa847a0f814aff02b66c43`, and configuration SHA-256
`f86b80f4dcef277be874f476293d8b8055053072f7209625586b60e2227f905d`.
Its private boot ID differs from both D and E. Same-boot FDT, eight-CPU,
observer and entry qualification passed before capture. The operator
confirmed working Wi-Fi and visible dim/bright restoration; AC was connected
and panel brightness was restored to 155. The preceding automatic one-shot
request had instead booted stock Omarchy, without a C acquisition; see the
[boot-selection incident](WFI-C-BOOT-SELECTION-INCIDENT.md). It is not part
of this C packet.

The requested 2,000 ms capture had an actual external window of
2,041.002 ms, with 40 completed worker pulses on each of CPU 1 and CPU 5
strictly inside it. The observer committed 171 successful target-cluster SETs
(145 cluster 0, 26 cluster 1) and 563 valid C-hook MMIO `idle_enter` reads
(466 cluster 0, 97 cluster 1). There were no invalid C reads, overflows or
missing commits. The seven trailing `idle_enter` records without captured
exits cross the capture boundary; they are not counted as complete idle
intervals. WFI probe rows are zero by design in `mmio` mode.

| Cluster | Successful SETs | Strict model-interior C reads | Raw BUSY reads | Primary SET-to-C pairs, at most 600 ticks | Primary BUSY | Exploratory pairs, at most 2,400 ticks | Exploratory BUSY |
|---|---:|---:|---:|---:|---:|---:|---:|
| 0 | 145 | 465 | 13 | 10 | 10 | 14 | 11 |
| 1 | 26 | 97 | 0 | 0 | 0 | 1 | 0 |

The primary and exploratory classifications use the predeclared
conservative upper bound `C sample.t1 - SET.t0`, plus 240 ticks for a
cross-CPU SET/sample pair. One cluster-0 example is a same-CPU writer and
sampler on CPU 0: the C sample at token 14 read `0x40080101101` with a
104-tick upper bound after successful SET sequence 10. Same-CPU local order
and lag are direct, but the **full paired-opportunity classification** still
depends on the unmeasured 240-tick cross-CPU error assumption to establish
strict capture interior, the earliest same-cluster sample, and no possibly
intervening write. Eight of the ten cluster-0 primary pairs have same-CPU
SET/sample; two are cross-CPU. The cluster-1 exploratory pair was clear and
cannot substitute for a primary exposure. The C control has no separate
20-pair gate; its role is to test whether pending commands can be seen at
this earlier site in a comparable lag stratum before interpreting a zero E
result. The positive E result already reports its own raw BUSY reads and
exposure limits [separately](WFI-E-RESULT.md).

The [public C packet](native-evidence/C-abi2/status.txt) retains raw
numerical observer, counter and worker streams, status, filtered chronology,
and bounded environment/activity projections. The
[publication receipt](wfi-c-control-receipt.json) links each private input
hash to its reviewed public export and records the replayed analysis. From
the repository root, the following reproduces the C pair summary from
published bytes:

```sh
python3 - <<'PY'
import gzip, sys
from pathlib import Path
sys.path.insert(0, 'experiments/aurora-apsc-observer')
import analyze_wfi
p = Path('experiments/aurora-apsc-observer/native-evidence/C-abi2')
r = analyze_wfi.analyze_text(
    gzip.open(p / 'events.csv.gz', 'rt').read(),
    (p / 'status.txt').read_text(),
    gzip.open(p / 'wfi-events.csv.gz', 'rt').read())
assert r['integrity']['clean']
for cluster, row in r['c_hook_comparable_lag']['by_cluster'].items():
    print(cluster, row['primary_pairs'], row['primary_busy'],
          row['exploratory_pairs'], row['exploratory_busy'])
PY
```

Pre/post counter phases each completed 1,792 exchanges under the declared
conditional model; they do not guarantee a capture-wide cross-CPU clock
bound. AC, brightness and policy endpoints matched, thermal zone 0 was
34.1°C at both endpoints, and the private kernel logs were byte-identical
before and after acquisition. Network traffic occurred across the broad
endpoint interval; endpoint equality does not establish the armed window's
background load or cross-boot equivalence. D, E and C had different thermal
conditions. Full boot identifiers, boot arguments, raw FDT and logs remain
private. The [build receipt](wfi-build-receipt.json) lacks a build-time WFI
patch or full source-tree digest; the reviewed patch's publication hash alone
is not a cryptographic source-to-image proof. The predeclared
[D/E/C/B/A block](WFI-PLAN.md) now has a separate
[fresh-boot B control](WFI-B-CONTROL-RESULT.md); A and cross-boot
comparability review remain before issue #5's full result can be closed.
