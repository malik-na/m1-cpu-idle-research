# First native PCPM records-only packet (ABI 2)

This is a reviewed numerical export from one boot of the T8103/J313 Aurora
`7.1.12-ARCH-apsc-20261002-wfi-pcpm` kernel. Its release, module-package
name, UKI hash, source-tree hash, patch hash, configuration hash, and
Build-ID are pinned in `export-receipt.json`.
The private acquisition packet is identified by its basename and SHA-256
manifest hash there; it retains full boot/FDT/log/package evidence locally.

The simultaneous controls requested `records 90 100 0` from PCPM and
`records 9500` from APSC. Four P-pinned workers ran the predeclared
four-active, one-active, all-released, and four-wake schedule, with an E-pinned
coordinator. `schedule.json`, `control-writes.json`, the workload JSONL,
filtered `timeline.jsonl`, and environmental projections retain the timing
and conditions needed to interpret the raw samples. Raw PCPM, APSC, and
counter CSV streams are losslessly compressed as deterministic gzip. All six
kernel status files are byte-exact copies, including errors and drop counts.
The source and published SHA-256 of each stream appear in
`export-receipt.json`; `gunzip -c FILE.csv.gz` reproduces the corresponding
private CSV byte for byte.
Run `python3 experiments/linux-pcpm-sampler/verify_records_export.py` from
the repository root to verify published hashes and replay the conditional
four-P interval calculation.

The first-boot machine screen passed, but `first-boot-review.json` explicitly
keeps later MMIO acquisition behind an independent software-interval and
counter-alignment review. In this records-only mode `read_attempted=0` and
`raw_valid=0` for all PCPM rows. No PMGR register word was read. These data
cannot establish a PCPM hardware state, rail power, physical CPU sleep, or
the APSC command value at the final WFI instruction. Cross-CPU timing remains
an assumption unless separately qualified. See the predeclared
`../../NATIVE-CALIBRATION-PROTOCOL.md` and the analysis code in this
experiment for the conditional interpretation.

The export omits boot IDs, boot arguments, full FDT, kernel logs, process IDs,
user paths, network counters/identifiers, and private package contents.
Environment snapshots and the timeline are named-field projections; their
source hashes and transformation rules are recorded in the receipt. The
numerical CSVs, status files, schedule, controls, workload, phase coverage,
and first-boot review are otherwise byte-exact after decompression.
