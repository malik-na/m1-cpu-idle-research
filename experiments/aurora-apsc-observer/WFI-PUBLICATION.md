# ABI 2 native packet publication contract

Prepared before the first ABI 2 acquisition. The [first-attempt protocol](WFI-PLAN.md)
and installed [build](wfi-build-receipt.json) and
[deployment](wfi-deployment-receipt.json) receipts remain the experiment's
predeclared context. This document and its synthetic tests are **publication
preparation, not native evidence**. At this document's original checkpoint no
ABI 2 packet had been published. The later [D pilot result](WFI-D-RESULT.md)
and [receipt](wfi-clock-pilot-receipt.json), followed by the
[E result](WFI-E-RESULT.md) and [receipt](wfi-mmio-receipt.json), and the
[C control](WFI-C-CONTROL-RESULT.md) with its
[receipt](wfi-c-control-receipt.json), and the
[B control](WFI-B-CONTROL-RESULT.md) with its
[receipt](wfi-b-control-receipt.json), and the
[A baseline](WFI-A-BASELINE-RESULT.md) with its
[receipt](wfi-a-baseline-receipt.json), are separate evidence. The
[five-packet comparison](WFI-ABI2-BLOCK-RESULT.md) is a later cross-boot
analysis, not a substitute for any individual packet.

[`publish_wfi_evidence.py`](publish_wfi_evidence.py) accepts one private,
acquisition-time hashed packet at a time, together with private mode-0600
same-boot FDT qualification and operator-confirmed Wi-Fi/brightness acceptance
receipts created before the capture. Both must match the packet's private
boot ID; the qualification and both capture snapshots must show connected
charger. It supports
all five ABI 2 modes:
unarmed A `baseline`, B `records`, C C-hook `mmio`, D `wfi_clock`, and E
`wfi_mmio`. It verifies every private `SHA256SUMS` entry and exact packet file
set, the collector's terminal `complete` action and acquisition-time source
hash, the WFI release/configuration/GNU Build-ID/selected entry, and the
checked public build/deployment chain. It checks that the collector source
saved inside the private packet hashes to the acquisition-time collector
digest, independent of later source edits. The qualification must match the
packet's private boot ID and carry the exact T8103 CPU/performance-domain and
APSC command-resource projection; only that fixed, nonidentifying projection
and its canonical hash enter the public receipt. The qualification's same-boot
monotonic timestamp must precede acquisition; wall-clock correction cannot
decide that order. It replays the saved counter analyses
and, for B–E, the ABI 2 observer analysis from raw numerical streams. A
baseline instead requires ready status and zero observer events and counters.
The D pilot additionally requires at least one matched first-attempt WFI
sample strictly inside recorded start/stop ticks by the **assumed**, unmeasured
E=240 cross-CPU error bound. The analyzer's raw `in_window` count alone uses
`t1<=stop_tick` and does not prove ordering against a stop written on another
CPU. A clean after-stop-only or near-stop-only packet remains private evidence,
but cannot qualify as the D pilot for publication or EFI retirement. An observed
external window outside 1.5–3.0 seconds, absent fully
interior worker pulses, or changed policy/charger/brightness endpoints causes
publication rejection; these are review gates around the requested 2,000 ms
window, not a cross-CPU clock calibration.

The receipt's `wfi_peer_candidate_status` and
`wfi_peer_candidate_by_cluster` fields summarize only the analyzer's
**assumed-E=240 software peer-interval screen**. Own/peer interval and
writer/target proofs remain in the private saved analyzer output and can be
reconstructed from the published raw numerical streams. Raw E BUSY samples
remain a separate observation. Candidate labels do not establish a physical
final core, BUSY at the later WFI instruction, or a completed cluster power
transition.

Successful publication produces a receipt and a directory of exactly nine
numerical streams plus four filtered JSON files. The observer and counter
CSV files and two worker CSV files are byte-exact after deterministic gzip;
the observer/counter status files are byte-exact. `chronology.json` retains
only validated fields allowed for each named acquisition action and its time;
extra workload fields are rejected. The two environment
files replace raw sysfs paths with fixed labels for CPU online/idle state,
policy, AC/battery, panel brightness and thermal zone 0; they retain sampled
values and observation times. The receipt records input/output hashes,
decoder-source hashes and options, measured window duration, fully interior
worker pulse indices, loss/integrity status, and the conditional paired-
opportunity model. For a D pilot, its `release`, `gnu_build_id`,
`selected_entry`, `mode`, `integrity_clean`, and `packet_sha256s_sha256`
fields can also bind a later EFI-retirement readback to the reviewed private
packet. This receipt alone does not justify retiring an entry; the separate
live boot/device checks remain necessary.

`build_chain.wfi_patch_file_sha256_at_publication` identifies the repository
patch file when publication runs. The build receipt did not record a build-time
WFI patch or source-tree digest, so the receipt explicitly sets
`build_time_wfi_patch_or_source_digest_recorded` to false. The current private
source files and linked object provide retrospective consistency checks, but
this publication-time hash alone is not a cryptographic binding from patch
bytes to the built image.

The pre-capture environment amendment adds private, hashed
`environment-observation-before.json` and
`environment-observation-after.json` to **ABI 2** packets only. The collector
reads a bounded `/sys/class/net` interface inventory (state, carrier and
byte/packet counters), a bounded `/sys/bus/usb/devices` VID:PID/class inventory,
and aggregate `/proc/stat` CPU/context-switch counts. It does not read MAC
addresses, IP addresses, USB serials, process names or process IDs. The ABI 1
collector path remains unchanged. These endpoint reads occur with the existing
before/after snapshots, outside the armed window, to avoid adding a new read
inside the WFI observation path.

`activity-summary.json` is an independently replayed projection of those
private files. It publishes `wlan0` state and traffic deltas, aggregate
other-interface traffic/counts, USB device counts and private VID:PID/class
multiset equality, plus whole-system CPU/context-switch deltas. Other
interface names, USB node names and VID:PIDs stay private; the public receipt
links both private input hashes to the projection hash. Network counter reset
or interface change yields a null traffic delta instead of a false zero.
Aggregate CPU counters include the workload and collector, so they cannot
isolate background activity. Endpoint equality does not establish USB,
network, CPU-load or thermal equivalence throughout the capture or across
different boots. There is no predeclared thermal tolerance; reviewers must
leave a sensitive matched C/E negative inconclusive when comparability is
not independently established.

The `counter_pre_begin/end` and `counter_post_begin/end` chronology markers
bracket synchronous kernel counter-qualification runs. They do not include
the later userspace status/event export and decoder time.

The device acceptance records the operator's Wi-Fi report and a brightness
change followed by restoration to 155, plus private live driver/readback
checks. It is process evidence, not an independent packet-transfer or visual
brightness measurement. The full FDT, boot arguments, boot ID, boot configuration, bootctl output,
kernel log, command arguments and unfiltered snapshots remain in the private
packet. A pre-arm `journalctl --boot --dmesg` availability check and a
post-capture log export must both succeed with nonempty output; publication
requires both hashed streams and the corresponding successful command records.
The publisher does not parse the private log for warnings or errors. The saved
collector source and full same-boot qualification receipt
and device acceptance also remain private. The public receipt does not include the packet path, boot UUID, MAC
address, private FDT hash or an account identifier. It does not establish
distinct boots or matched conditions across A/B/C/D/E. Those require a later
private comparison of boot IDs and per-packet evidence. The endpoint readings
cannot rule out intervening power or policy changes, and USB/network/background
activity is not fully observed. The assumed 240-tick cross-CPU error remains
unproven through the capture. Even a clean E BUSY sample is a first-attempt
pre-DSB observation, not state at the WFI instruction or physical power.

The [synthetic publisher tests](test_publish_wfi_evidence.py) exercise all
five modes, hash and identity mismatches, incomplete acquisition, altered
analyzer output, condition changes, abnormal window length and withheld
private values. They are not hardware validation. After an actual packet
passes private review, run the publisher with its private `--packet`, matching
private `--qualification` and `--device-acceptance`, exact `--mode`, new evidence-directory `--out`,
and new `--receipt` path. Review
those outputs before adding them and updating `MANIFEST.sha256`; then run
`python3 tools/verify_repository.py` before pushing the research branch.
