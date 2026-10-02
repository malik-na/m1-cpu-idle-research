# ABI 2 native packet publication contract

Prepared before the first ABI 2 acquisition. The [first-attempt protocol](WFI-PLAN.md)
and installed [build](wfi-build-receipt.json) and
[deployment](wfi-deployment-receipt.json) receipts remain the experiment's
predeclared context. This document and its synthetic tests are **publication
preparation, not native evidence**. No ABI 2 packet has been published at this
checkpoint.

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

Successful publication produces a receipt and a directory of exactly nine
numerical streams plus three filtered JSON files. The observer and counter
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

The `counter_pre_begin/end` and `counter_post_begin/end` chronology markers
bracket synchronous kernel counter-qualification runs. They do not include
the later userspace status/event export and decoder time.

The device acceptance records the operator's Wi-Fi report and a brightness
change followed by restoration to 155, plus private live driver/readback
checks. It is process evidence, not an independent packet-transfer or visual
brightness measurement. The full FDT, boot arguments, boot ID, boot configuration, bootctl output,
kernel log, command arguments and unfiltered snapshots remain in the private
packet. The saved collector source and full same-boot qualification receipt
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
