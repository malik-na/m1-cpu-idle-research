# Counter qualification review and remaining work

Reviewed on 2026-10-01 against baseline
`1805c68be77539008c34076c2f7d4300c3809486`, the repository's evidence rules,
the [clock protocol](../linux-apsc-observer/CLOCK-QUALIFICATION.md), and the
[open native-capture ticket](https://github.com/malik-na/m1-cpu-idle-research/issues/5).
The exact kernel patch SHA-256 is
`4d56b79a6de142726602085466f7ba8835d1d6f5737f02ffc3fd776f01b77b7b`.

## Standards review

A reviewer independent of the helper and decoder implementations found no
remaining actionable documented-standard violation or code-smell finding.
The review checked target/source pinning, retained errors and missing values,
immutable phase records, raw input hashes, explicit uncertainty assumptions,
conditional inference, bounded acquisition and publication privacy. It included
the final post-phase contract regression. That reviewer authored the separate
build receipt, which the coordinating reviewer checked against the frozen
patch and local applied-source fingerprints; it was not self-reviewed as part
of the Standards result.

## Specification and implementation review

An independent design audit checked the pinned timer, barrier and SMP APIs
and the causal interval mathematics before implementation. A subsequent
reviewer, who authored the decoder but not the kernel helper, checked the
kernel source, ABI and native procedure against the star-exchange protocol.
No actionable kernel/specification finding remained. The review covered source
CPU pinning, request/ack ordering, callback restrictions, stack payload lifetime,
retained task reference through worker join, fixed storage, error retention,
per-CPU metadata and separation from idle windows.

The coordinating reviewer separately audited the decoder. Corrections with
regressions cover unsigned 32-bit counter frequencies, two four-CPU cluster
masks, malformed CSV headers, byte-exact hashes with CRLF input, and rejection
of a post phase that contradicts its required pre phase. Successful individual
exchanges do not automatically make a complete or consistent phase. Raw and
uncertainty-expanded stable-offset models are reported separately; an empty
intersection is retained as a contradiction of that model.

## Validation performed

- The exact patch applies to the pinned pristine source and alongside the
  unchanged APSC observer patch. Standalone enabled, disabled and combined
  Kbuild checks passed; the [build receipt](BUILD-VALIDATION.md) records exact
  configuration, source, object and section hashes and the scope of each check.
- Generated AArch64 review confirms the ordered physical-counter sequence,
  request/ack ordering, callback restrictions and absence of helper MMIO or
  power-control instructions. The original 100-byte WFI routine is unchanged.
- All **23 counter-decoder synthetic tests** and **64 existing observer tests**
  passed on Python 3.9. The Standards reviewer independently reran the 23
  counter tests. Cases include malformed/partial captures, tolerance boundary
  conditions, clock-model contradictions, pre/post identity failures, uint64
  counters and signed differences beyond the int64 range.
- Python compilation and applied-source whitespace checks passed. Publication
  links, manifest and saved macOS trace reproduction are checked separately by
  the repository verifier before publishing.

## Outstanding evidence

This implements the protocol's bounded star route. The optional direct
all-pairs route remains unimplemented and is not required to run the documented
star experiment. No native phase has run. Object compilation is not a final
kernel link, native boot, error-path runtime test or clock qualification.

A later authorized session must establish the actual boot/configuration and
fallback, inspect the target's selected alternatives/workarounds, exercise the
control and failure paths, and retain before/after phases with the separate
observer capture and its workload/overhead evidence. The two interfaces do
not enforce a mutual exclusion interlock: scheduling qualification outside
idle/energy windows remains an explicit run-protocol requirement.

Finite observations constrain offsets only under the stated acquisition,
rate, offset-stability and uncertainty assumptions. The unsampled gap is never
automatically qualified, and the decoder never writes a clock bound into the
APSC analyzer. Native DVFS/idle overlap, PCPM calibration, a causal power or wake
consequence, and the eventual Linux policy decision all remain open.
