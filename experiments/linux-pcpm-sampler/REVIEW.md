# PCPM preparation review

Reviewed against the native calibration question, the [signal decision](../../notes/native-pcpm-signal-decision.md), [ABI 1](ABI.md), repository evidence rules and Asahi Linux `77cb8f24c2381a8abb7272d7bbdec548d6426a8a`. This review covers acquisition preparation and offline interpretation. It is not approval evidence for a completed native experiment.

## Source and contract findings

An independent pinned-source audit found that public syscon lookup helpers can create a mapping, attach a clock and deassert reset. The sampler therefore uses an added existing-only accessor. Generic clockless-map provenance is recorded during normal syscon creation; external map registrations remain ineligible. The collector qualifies the fixed DT resource and width without taking ownership, changing regmap flags or forcing normal driver probing. The pinned registry has no successful-map teardown. These properties require re-audit after kernel or DT changes.

Review corrected three draft issues before publication:

- The control parser initially trimmed whitespace more broadly than the documented command grammar. It now accepts exactly the documented separators and optional final newline; the host check compiles the actual C parser extracted from the patch.
- A single-value DT width check could accept an extra cell. The qualifier now requires exactly one `reg-io-width` cell when the property exists.
- The draft CPU guard incorrectly required zero MPIDR Aff2 for Firestorm. The pinned T8103 DTS records P cores at `0x10100` through `0x10103`, with Aff1 and Aff2 both 1. The patch, decoder and fixtures now require that exact topology; the decoder reviewer independently checked the source. A synthetic fixture matching a mistaken draft would not have found this error.

The scheduling clock uses `ktime_get_ns()` because the proposed fast accessor can move backward across timekeeper updates. Nominal schedule limits and actual timing are distinct. The record preserves lateness and misses; finite slots do not impose a hard timeout on a stalled MMIO operation.

Independent ABI/spec review found no remaining actionable defect in the corrected source's mapping qualification, cached CPU identity, worker lifetime, sparse schedule, first-error retention or exported contract. Review confirms the absence of a new power-state write, runtime-PM reference, new mapping or idle-policy wait in this patch. It cannot show that the instrument is physically non-disruptive.

## Decoder checks and remaining gates

The 26 synthetic decoder tests distinguish valid zero from missing data; separate ACTUAL/TARGET and unknown codes; retain read/CPU errors, skipped slots and an unattempted tail; check resource/topology and schedule contradictions; and preserve exact-byte input hashes. The decoder retains partial observations alongside capture-integrity failures and never converts irregular sampled counts into residency.

The native ticket remains open. Required evidence includes the actual booted source/configuration/firmware, successful bounded acquisition, matched controls for observer effects, alignment to independent software-idle timing, active/idle/wake calibration and negative results. Neither source review nor a cross-build establishes PCPM rail meaning or a useful Linux APSC wait policy.
