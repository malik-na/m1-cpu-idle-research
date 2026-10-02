# PCPM preparation review

Reviewed against the native calibration question, the [signal decision](../../notes/native-pcpm-signal-decision.md), [historical ABI 1](https://github.com/malik-na/m1-cpu-idle-research/blob/cb0b41e62ad500225c1a06bfc827b2fd8e24b1ec/experiments/linux-pcpm-sampler/ABI.md), repository evidence rules and Asahi Linux `77cb8f24c2381a8abb7272d7bbdec548d6426a8a`. The initial review below is retained; the ABI 2 follow-up appears at the end. This review covers acquisition preparation and offline interpretation. It is not approval evidence for a completed native experiment.

## Source and contract findings

An independent pinned-source audit found that public syscon lookup helpers can create a mapping, attach a clock and deassert reset. The sampler therefore uses an added existing-only accessor. Generic clockless-map provenance is recorded during normal syscon creation; external map registrations remain ineligible. The collector qualifies the fixed DT resource and width without taking ownership, changing regmap flags or forcing normal driver probing. The pinned registry has no successful-map teardown. These properties require re-audit after kernel or DT changes.

Review corrected three draft issues before publication:

- The control parser initially trimmed whitespace more broadly than the documented command grammar. It now accepts exactly the documented separators and optional final newline; the host check compiles the actual C parser extracted from the patch.
- A single-value DT width check could accept an extra cell. The qualifier now requires exactly one `reg-io-width` cell when the property exists.
- The draft CPU guard incorrectly required zero MPIDR Aff2 for Firestorm. The pinned T8103 DTS records P cores at `0x10100` through `0x10103`, with Aff1 and Aff2 both 1. The patch, decoder and fixtures now require that exact topology; the decoder reviewer independently checked the source. A synthetic fixture matching a mistaken draft would not have found this error.

The scheduling clock uses `ktime_get_ns()` because the proposed fast accessor can move backward across timekeeper updates. Nominal schedule limits and actual timing are distinct. The record preserves lateness and misses; finite slots do not impose a hard timeout on a stalled MMIO operation.

The initial independent ABI/spec review found no further defect at that stage. A later source audit found the PMGR-bank selection defect documented below, so that earlier conclusion did not establish native readiness. Review confirms the absence of a new power-state write, runtime-PM reference, new mapping or idle-policy wait in this patch. It cannot show that the instrument is physically non-disruptive.

## Decoder checks and remaining gates

The 26 synthetic decoder tests distinguish valid zero from missing data; separate ACTUAL/TARGET and unknown codes; retain read/CPU errors, skipped slots and an unattempted tail; check resource/topology and schedule contradictions; and preserve exact-byte input hashes. The decoder retains partial observations alongside capture-integrity failures and never converts irregular sampled counts into residency.

The native ticket remains open. Required evidence includes the actual booted source/configuration/firmware, successful bounded acquisition, matched controls for observer effects, alignment to independent software-idle timing, active/idle/wake calibration and negative results. Neither source review nor a cross-build establishes PCPM rail meaning or a useful Linux APSC wait policy.

## ABI 2 follow-up: a common counter format

The initial nanosecond bracket could describe PCPM sampling cost but could not directly pair a sample with the APSC observer's physical-counter ticks. ABI 2 adds ordered raw-counter brackets around the existing bracket and optional read, plus worker-local reader metadata and explicit availability/reversal fields. Scheduling remains in monotonic nanoseconds. The change provides the data format needed for a later comparison; it does not establish a common boot, cross-CPU error bound or native overlap.

Independent cross-review of the kernel source against the ABI and decoder checked status/CSV names and widths, the preflight reader gate, identical timestamp work in both modes, pre-read reversal suppression, failed-row retention and CPU/read/reversal error precedence. A separate cross-review of the decoder against the source contract and repository evidence/publication rules found no actionable standards or spec issue. The added reader metadata is deliberately a worker preflight snapshot, not continuous qualification. The [build receipt](BUILD-VALIDATION.md) separately records enabled, disabled and combined ARM64 builds and emitted-instruction checks.

The decoder now retains all 26 ABI 1 tests and adds 23 ABI 2 cases. They cover version dispatch, absent versus zero timestamps, metadata qualification, counter and nanosecond reversals, malformed flags, partial failed captures and preservation of a valid register word after a counter failure. A locally valid counter bracket and a valid sampled word are separate outputs; neither authenticates the capture. The JSON schema is now `pcpm-sampler-analysis-v2`, with `input_abi` identifying either input format.

The [joint-capture procedure](JOINT-CAPTURE.md) specifies concurrent control writes, qualification outside both acquisitions, matched instrumentation controls and strict conditional association with complete software-idle intervals. It is a future procedure, not a report of a native run. The next evidence-producing step is the separately authorized native experiment described in the calibration ticket.

## 2 October PMGR-bank correction

The pinned [Asahi T8103 DTS](https://github.com/AsahiLinux/linux/blob/77cb8f24c2381a8abb7272d7bbdec548d6426a8a/arch/arm64/boot/dts/apple/t8103.dtsi#L1049) and the exact [Aurora release DTS](https://github.com/iconidentify/aurora-linux/blob/90a95335a49aec3a0045a76da140452ad6585eb3/arch/arm64/boot/dts/apple/t8103.dtsi#L1109) each contain **two** `apple,t8103-pmgr` nodes: the intended main bank at `0x23b700000`/`0x14000` and `pmgr_mini` at `0x23d280000`/`0x4000`. The live capacity-kernel device tree also exposes both resources. The previous `qualify_regmap()` rejected any second matching compatible node, so it would return `-ENODEV` on this machine before any sample. The earlier object build and review did not exercise native DT qualification.

The revised selector accepts only a unique node whose first resource equals the pinned main bank, then applies the existing availability, `syscon`/`simple-mfd`, property, existing-map, and register-width gates. The [fixture](pmgr-node-fixtures.json) records both full DTS hashes and extracted node resources. The [host check](check_pmgr_selection.py) compiles the actual C function from the patch and exercises both source orders and failure cases; the former function fails the same check on the source-order case. This corrects a deterministic preflight blocker, but neither host check nor clean patch application establishes an ARM64 build, live syscon registration, read success, observer cost, or PCPM meaning. Those remain gates before and during issue #6.
