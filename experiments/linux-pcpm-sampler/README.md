# Native PCPM sampler preparation

This experiment prepares [Calibrate PCPM ACTUAL during native Linux idle](https://github.com/malik-na/m1-cpu-idle-research/issues/6). It has **not been run on native M1 hardware**. It provides no physical-state calibration, measured power saving, or reason to change Linux idle policy. The [signal decision](../../notes/native-pcpm-signal-decision.md) remains the experiment's specification. A 2 October source audit found and corrected a PMGR-bank selection defect in the formerly built patch; the corrected patch has host selector and application checks but **has not had a new ARM64 build or native boot**. See the [review](REVIEW.md) and [build boundary](BUILD-VALIDATION.md).

The default-off C patch targets Asahi Linux `77cb8f24c2381a8abb7272d7bbdec548d6426a8a`. A normal-priority kernel worker runs on a verified Icestorm CPU and records either timestamps alone or sparse reads of the existing PMGR map at offset `0x48`. It adds no power-state writes or idle-path wait. Read-only collection still wakes a core and can disturb the power state being studied.

The [build receipt](BUILD-VALIDATION.md) records enabled, disabled and combined ARM64 object builds, exact input hashes, instruction checks and their limits. The [review](REVIEW.md) distinguishes corrected implementation assumptions from remaining native evidence.

## Acquisition contract

Read [ABI 2](ABI.md) before applying the [patch](0001-t8103-pcpm-sampler.patch). Both modes require the exact T8103 CPU topology and the unique compatible node whose first PMGR resource is `0x23b700000`/`0x14000`, plus a normally initialized, internally created, clockless generic syscon regmap. T8103 also has a smaller PMGR mini bank with the same compatible; it is excluded by resource identity, not treated as an error. The added registry accessor performs an existing-only lookup: it cannot create a mapping, attach a clock, or deassert reset. An absent or unqualified mapping fails the command. The source-level check covers the pinned Asahi and current Aurora T8103 trees; a native boot and later DT/regmap changes still require requalification.

One valid command consumes the acquisition for that boot, including qualification failure or records-only collection. The kernel preserves a failed read or CPU mismatch and aborts its remaining slots. Export occurs after the worker stops. Slot accounting distinguishes attempted rows, scheduling losses and the unattempted tail after failure; missing data must never be interpreted as a zero register value.

The fixed command budget is at most 1,000 nominal slots across 10 seconds, with periods of 10–1,000 milliseconds and explicit phase. It skips missed or too-close slots instead of polling to catch up. These are scheduling limits, not a guarantee that an MMIO transaction or scheduler returns within a hard deadline. Exact accepted syntax, timing rules and raw exports are in the ABI.

ABI 2 adds ordered raw physical-counter brackets around each sample while retaining monotonic nanoseconds for scheduling. Both modes execute the same added timestamp work. The bound worker records counter-reader metadata and rejects an unsuitable raw-reader configuration before sampling. These brackets permit a later conditional comparison with the APSC observer's ticks; they do not establish cross-CPU accuracy. The [joint-capture procedure](JOINT-CAPTURE.md) covers concurrent acquisition, retained failures and the remaining clock and observer-effect gates.

## Offline interpretation

The decoder accepts the saved status and CSV exports. Use `python3 analyze.py --help` for its interface; its default provenance is unverified input. Synthetic tests exercise the data contract, not the hardware.

Historical ABI 1 exports remain readable, explicitly without raw-counter alignment. No counter ticks are fabricated from their nanosecond timestamps. For ABI 2, a valid sampled register word and a valid counter bracket are separate properties: a later counter failure must not erase the word or make it eligible for correlation.

From the repository root, run `python3 -m unittest discover -s experiments/linux-pcpm-sampler -p 'test_*.py'` for the decoder, `python3 experiments/linux-pcpm-sampler/check_control_parser.py` for the command grammar, and `python3 experiments/linux-pcpm-sampler/check_pmgr_selection.py` for source-derived PMGR bank selection. The checks extract the actual C functions from the patch and do not execute kernel or MMIO code. The selector check accepts optional `--asahi-dts` and `--aurora-dts` paths to verify the compact fixtures against the complete pinned source bytes. See the [review](REVIEW.md) for corrected draft assumptions and remaining gates.

Only successful raw words support numeric `ACTUAL = (raw >> 4) & 15` and `TARGET = raw & 15` decoding. Preserve all codes, errors, read brackets, CPU identities, schedule losses and raw sticky bits. A frequency table of sampled values is neither time-weighted residency nor a physical-state classification. The decoder cannot authenticate a capture or calibrate the register by itself.

## Later native session

The [pre-acquisition calibration protocol](NATIVE-CALIBRATION-PROTOCOL.md) fixes the first records-only qualification, four-P workload, matched controls, cadence, analysis guards and failure rules before the first PCPM read.

1. First complete a new ARM64 object/final-link review of the corrected patch on the actual Aurora source and target configuration. Recheck the booted board, immutable kernel/configuration, both DT PMGR banks, firmware and normal PMGR driver initialization. Prepare recovery and retain the unmodified baseline.
2. Save `status` and `samples` before acquisition, then both again after the command, even when the command reports failure. Retain the exact command and its exit status. Do not retry until the failed packet has been retained and reviewed.
3. Across separately booted, matched windows compare no collector, `records` mode, and sparse `mmio` mode. Preserve AC/battery state, USB/display state, thermal drift, background load, kernel tracing configuration and delivered work. One-shot collection requires a separate boot for another mode or phase; do not silently add a reset/rearm interface to avoid that constraint.
4. Apply the signal decision's active-P, one-active-P and overlapping-P-software-idle conditions with repeated cadence/phase variations. Record an independent software-idle timeline. For a paired APSC observer capture, use the ABI 2 raw-counter brackets and the [joint-capture procedure](JOINT-CAPTURE.md); qualify cross-CPU comparisons explicitly. Do not equate the monotonic clock with raw physical ticks.
5. Report failed reads, stalls, losses, constant values and observer effects as results. A repeatable code difference can establish a PMGR-reported state discriminator; rail-off duration and energy benefit need independent evidence.

No P-core IPI, allocation, printing or remote streaming occurs inside the sample loop. Ordinary regmap operations can have tracing and locking effects. Keep regmap tracing disabled during the proposed physical measurement and record that configuration. For independent energy measurement, follow the signal decision's fallback rather than extrapolating power from a register label.
