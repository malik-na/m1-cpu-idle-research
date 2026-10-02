# First native PCPM sparse-MMIO phase screen (ABI 2)

This is a sanitized numerical export from one fresh boot of the T8103/J313
Aurora `7.1.12-ARCH-apsc-20261002-wfi-pcpm` image. The private packet's
SHA-256 manifest, installed image identity, acquisition/decoder source hashes,
and each exported file's private input and published SHA-256 appear in
`export-receipt.json`. The private packet retains boot IDs, boot arguments,
FDT, package checks, and kernel logs. The manifest hash pins that withheld
packet; public replay cannot independently authenticate withheld fields.

APSC ran `records 9500` while PCPM ran `mmio 90 100 0`, with the same four-P
workload and 300 ms measured phase guard as the [predeclared protocol](../../NATIVE-CALIBRATION-PROTOCOL.md).
The PCPM worker completed all 90 slots on E CPU 0 with 90 successful MMIO
reads, no missed slots or read/counter/CPU errors, and valid local brackets.
All 90 full 32-bit words were **`0x000021f0`**: numeric ACTUAL `15`, TARGET
`0`. This includes 24 valid guarded all-P-released reads. The guarded counts
were 14 four-active, 14 one-active, 24 four-released, and 14 four-wake.
The predeclared one-boot ACTUAL contrast **failed** because the released
modal code was identical to the active and wake modal codes. No automatic
second MMIO run follows from this result.

The five raw PCPM/APSC/counter CSV streams are losslessly compressed with
deterministic gzip. Six status files, workload, control timing, the machine
screen and environment comparisons are byte-exact exports. Environmental
snapshots and the timeline are named-field projections that omit network
identifiers and counters, boot IDs, UTC times and process IDs. A separate
[matched records/MMIO comparison](MATCHED-COMPARISON.md) reports only
aggregate network activity and states the limits of comparing two boots.

From the repository root, run:

```sh
python3 experiments/linux-pcpm-sampler/verify_mmio_export.py
```

The verifier checks every published evidence hash, replays raw row and
zero-loss status checks, recomputes guarded phase coverage and the failed
numeric pattern, and checks conditional four-P software witnesses. The
records boot had 21/24 and this MMIO boot 8/24 guarded released samples with
complete four-P software witnesses **under the unverified E=240 tick
cross-CPU assumption** and G=24,000 tick guard. Those counts do not establish
a capture-wide clock bound or a physical rail state. The constant code also
does not rule out deeper states: this register may be insensitive here, or the
sampling activity may perturb the observed system. No residency, energy,
transition time, or causal observer-effect claim follows from this packet.
