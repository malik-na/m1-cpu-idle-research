# Public A/B/C native event packet

The separate [ABI 2 D clock-only pilot](../WFI-D-RESULT.md) is in [`D/`](D/status.txt).
It uses the first-attempt WFI seam without a command-register read, so it is
not a BUSY observation or a substitute for the earlier capacity-kernel
A/B/C controls. Its [receipt](../wfi-clock-pilot-receipt.json) records the
private-to-public hashes, same-boot qualification, replay and limits. The
numeric streams in D are byte-exact after deterministic gzip, while its
environment and activity files are validated projections. See the
[ABI 2 publication contract](../WFI-PUBLICATION.md) for the exact boundary.

This directory is the reviewed numerical subset of three private,
acquisition-time hashed packets from separate boots of the same capacity
kernel. `A` is observer-unarmed, `B` records events without command reads,
and `C` also samples the APSC command register at the pre-WFI hook. Read
the [result and limits](../NATIVE-RESULT.md) before interpreting the rows.

Within each letter, `events.csv.gz`, `counter-pre-events.csv.gz`,
`counter-events.csv.gz` and `workload-cpu{1,5}.csv.gz` are **byte-exact raw
CSV after deterministic gzip** (`mtime=0`, level 9); their uncompressed
SHA-256 values and public-file hashes are in [export-receipt.json](export-receipt.json).
`status.txt`, both counter status files, and the before/after sysfs snapshots
are byte-exact copies. `chronology.json` retains only selected action,
UTC/monotonic time, mode and exit fields, in original order. The
[exporter](../publish_native_evidence.py) defines the whitelist. Boot IDs,
boot arguments, full FDT, full kernel logs, configuration and command paths
remain in the private acquisition packets; no private packet was modified.

The observer's raw times are generic counter **ticks** at the recorded
24 MHz `cntfrq`. Chronology and snapshot `monotonic_ns` are nanoseconds;
UTC strings locate the sessions. The status files preserve ring attempt,
commit, overflow, missing-commit and error information. The workload CSVs
preserve every scheduled/completed pulse and checksum. The counter CSVs
preserve individual pre/post exchange brackets, metadata, flags and errors.

Run `python3 experiments/aurora-apsc-observer/derive_native_evidence.py`
from the repository root to regenerate the four B/C observer analyses and
their [hash receipt](analysis-receipt.json). The `unbounded` runs pass no
clock error bound. `assumed-E240` passes
`--pairwise-clock-error-ticks 240`; this is a conditional model input, not
a clock-qualification result. The raw counter inputs can be decompressed
and checked with
[`experiments/linux-counter-qualification/analyze.py`](../../linux-counter-qualification/analyze.py),
using `--pairwise-tolerance-ticks 240 --endpoint-uncertainty-ticks 4`
for the protocol's assumed model. The decoder reports conditional offset
constraints, never a guaranteed error bound across the capture.
