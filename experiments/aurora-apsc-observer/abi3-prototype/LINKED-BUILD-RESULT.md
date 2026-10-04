# ABI3 ticket prototype evidence

The relative-path patch applies to the exact PCPM source identified by
`source-hash-receipt.json`; only the two cpuidle source files differ. The
read-only validator and its 30 synthetic adversarial cases are included.

The private scratch build of `Image modules dtbs` exited 0. The linked
receipt pins the Image and embedded IKCONFIG, vmlinux Build-ID, every module
hash and matching ABI3 vermagic, all built Apple DTB hashes, 128-byte-separated
ticket counters, and the two linked `ldaddal` instructions around the one
first-attempt APSC load. It verifies the clock branch skips only that load
and that the original `dsb sy; wfi` retry tail is byte-identical to PCPM.
`linked-code-evidence.txt` shows the scoped PCPM and ABI3 linked instruction
sequences and the ABI3 counter symbol for direct review.
`full-build-status.json` records the exit code and build-log hash; the log
itself is outside this publication packet because it contains build-host paths.

This is source and build evidence, not a native measurement or installation.
Tickets establish software hook and first-read ordering only. They do not
establish BUSY at the later WFI instruction or physical idle/rail state.
