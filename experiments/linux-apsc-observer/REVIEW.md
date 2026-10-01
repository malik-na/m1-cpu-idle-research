# Observer preparation review

Reviewed against the worktree baseline `d2a24ce54c2b3255b4d9f3ac68f7abfd8f210d85`,
the repository's evidence rules, the [selected trace method](../../notes/linux-dvfs-wfi-trace-choice.md),
and the [native capture ticket](https://github.com/malik-na/m1-cpu-idle-research/issues/5).
The final kernel patch SHA-256 is
`205c28ba1830cd794c6c59efff0b3aaeb6102335f48a7f98515a05704fbf378a`.

## Code and evidence standards

Separate source and generated-code reviews found no remaining actionable
defect in the reviewed patch. Earlier revisions were corrected for capture
mode ownership, snapshot/publication ordering, MMIO-read ordering, reads
after buffer exhaustion, initialization cleanup, and IRQ-safe preemption
restoration. Review checked the independent DT mapping lifetime, bounded
streams, one original command write, producer drain, and the scalar-only
idle token. The [build receipt](BUILD-VALIDATION.md) preserves the exact
configuration and instruction comparisons. It does not claim a full kernel
link, ARM64 objtool/noinstr pass, or native safety validation.

## Specification

Independent review caught and rechecked fixes for overlapping and reversed
same-CPU idle intervals, impossible successful DVFS words, invalid online
masks, omitted request metadata on failed polls, and conflation of active
window records with draining producers. The analyzer distinguishes valid
record syntax from complete idle-interval coverage, preserves legitimate
concurrent DVFS sequence inversions, and labels synthetic tests explicitly.
Accessor spans have defined units and exclude unmeasured publication work.

There is no unresolved defect from those reviews, but the capture ticket is
**not complete**. The subsequent [conditional candidate screen](README.md)
implements software final-entrant reconstruction under an explicitly supplied
pairwise clock-error assumption. A future run still needs a qualified native boot and actual
kernel configuration, final link and boot checks, cross-CPU counter
qualification, adequate opportunities with loss and observer controls,
and the resulting reconstructible data. A C sample before idle entry does
not locate the WFI instruction or prove physical power state. The separate
PCPM calibration and Linux-policy decision gates remain open. The
[clock-qualification protocol](CLOCK-QUALIFICATION.md) is a design for that
future session; no helper or clock result is claimed.

The [Mac FBT result](../../notes/mac-apsc-direct-observation-route.md) closes
only the availability question for the tested native SIP configuration.
It supplies no executed APSC branch or BUSY read, and does not exhaust the
later qualified-guest route. That hardware-observation ticket stays open too.

## Conditional analyzer review

Two separate reviewers checked `779116ed4f0a4dfdafa11dcbc878ac31f80efe66`
through `ab064dc646ea855e6a45cc4d6e69467c7d80f66b` on 2026-10-01.
This increment changes offline analysis and future-run documentation; the
kernel patch and its build receipt are unchanged.

**Standards:** no actionable findings. The review checked preserved raw
witnesses, strict clock/error boundaries, failed and incomplete observations,
explicit synthetic/unverified-input labels, bounded ambiguous identifiers,
publication privacy, and the separation of software inference from hardware
claims. No code-smell change was recommended.

**Specification:** no actionable findings. The review checked the selected
method's offline final-entrant requirement, complete peer witnesses, topology,
same-CPU versus remote-writer ordering, target-cluster correlation, missing
sample handling, and CLI/API defaults. The native ticket's boot identity,
instrument-overhead measurements, and positive/negative hardware windows
remain required. No native ticket was completed by this increment.

The full suite passed **64 synthetic tests** on Python 3.9, including separate
brute-force reference checks of interval reconstruction and write ordering.
The specification reviewer independently reran the same suite successfully.
Python compilation, documentation links, publication manifest, and reproduction
of the saved public macOS trace summary also passed. These checks validate
software and packet consistency, not clock behavior or CPU power state.

The clock protocol received a separate pinned-kernel-source review of timer
access, counter-read ordering, SMP completion and caller pinning, plus its
interval mathematics. The final specification reviewer checked the formulas
and evidence boundaries but could not independently fetch the pinned source
links; that review does not claim a second line-level source verification.
The qualification helper remains unimplemented and unrun.
