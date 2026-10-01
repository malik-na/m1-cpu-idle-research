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
**not complete**. Candidate software final-entrant reconstruction remains
unimplemented. A future run still needs a qualified native boot and actual
kernel configuration, final link and boot checks, cross-CPU counter
qualification, adequate opportunities with loss and observer controls,
and the resulting reconstructible data. A C sample before idle entry does
not locate the WFI instruction or prove physical power state. The separate
PCPM calibration and Linux-policy decision gates remain open.

The [Mac FBT result](../../notes/mac-apsc-direct-observation-route.md) closes
only the availability question for the tested native SIP configuration.
It supplies no executed APSC branch or BUSY read, and does not exhaust the
later qualified-guest route. That hardware-observation ticket stays open too.
