# Native ABI 2 records-only control, 3 October 2026

On a fresh boot of `Aurora-APSC-research-wfi-seam`, the B `records` control
captured C-hook event timing **without reading the APSC command register**.
It committed 472 `idle_enter`, 466 `idle_exit`, and 128 successful DVFS SET
records with no observer overflow or missing commit. WFI-probe rows and
command-value reads are zero by design; B cannot support a BUSY-positive or
BUSY-negative finding. Its role in the [predeclared block](WFI-PLAN.md) is
an observational timing and stream-integrity control for C.

The manually selected boot reported release
`7.1.12-ARCH-apsc-20261002-wfi`, GNU Build-ID
`11e80be6d8b358eee9aa847a0f814aff02b66c43`, and configuration SHA-256
`f86b80f4dcef277be874f476293d8b8055053072f7209625586b60e2227f905d`.
Its private boot ID differs from D, E, and C. Same-boot entry, FDT topology,
eight CPUs, observer ABI 2 and module-package checks passed before capture.
The operator confirmed working Wi-Fi and visible dimming to 40 followed by
brightening when restored to 155. AC remained connected, and brightness
was 155 at both capture endpoints.

The requested 2,000 ms acquisition had an actual external window of
2,066.111 ms. Each worker completed pulses 4 through 43, 40 pulses per CPU,
strictly inside that window. All 1,066 observer rows were in the recorded
capture window: 128 DVFS, 472 idle-enter and 466 idle-exit; there were no
CPU-PM-failure rows. Six trailing idle-enter records lack captured exits at
the boundary and are not complete idle intervals. All eight idle streams
and both DVFS streams had zero overflow and zero missing commit. Pre/post
counter phases each completed 1,792 exchanges under the declared
conditional model, which does not establish a capture-wide cross-CPU clock
bound.

The C-hook `idle_enter` read/probe bracket `t1 - t0` in B had median 2,
95th percentile 4 and maximum 7 ticks over 472 no-read records. In the
separate [C MMIO control](WFI-C-CONTROL-RESULT.md), the corresponding
563 valid-read brackets had median 13, 95th percentile 18 and maximum
113 ticks. The counter frequency was 24 MHz in both packets. These are
different boots and timing brackets only: they exclude event construction,
ring publication and the fixed inactive-hook cost, and do not isolate total
observer overhead, latency, energy or a causal cost of the read.

The [public B packet](native-evidence/B-abi2/status.txt) retains raw
numerical event, counter and worker streams, status, filtered chronology,
and bounded environment/activity projections. The
[publication receipt](wfi-b-control-receipt.json) records private-to-public
hashes and independent decoder replay. From the repository root, this
replays the bracket summary from published bytes:

```sh
python3 - <<'PY'
import gzip, sys
from pathlib import Path
sys.path.insert(0, 'experiments/aurora-apsc-observer')
import analyze_wfi
p = Path('experiments/aurora-apsc-observer/native-evidence/B-abi2')
r = analyze_wfi.analyze_text(
    gzip.open(p / 'events.csv.gz', 'rt').read(),
    (p / 'status.txt').read_text(),
    gzip.open(p / 'wfi-events.csv.gz', 'rt').read())
assert r['integrity']['clean']
print(r['established_event_analysis']['accessor_spans']['by_kind']
       ['idle_enter']['records_no_read']['ticks'])
PY
```

Thermal zone 0 was 33.9°C at both endpoints; the battery was charging at
88%. The Wi-Fi link was up and passed traffic across the broad endpoint
interval, while no USB device was listed. Policy and power endpoints
matched, and the private pre/post kernel logs were byte-identical. These
endpoints do not prove activity or thermal equivalence during the armed
window or across D/E/C/B. The [build receipt](wfi-build-receipt.json) lacks
a build-time WFI patch or full source-tree digest, so a publication-time
patch hash alone is not a cryptographic source-to-image proof. The fresh-boot
A baseline and five-packet comparison remain before issue #5's full result
can be closed.
