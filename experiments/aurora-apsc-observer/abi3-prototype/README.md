# Provisional ABI 3 ticket source and object packet

This source-only packet was frozen **before** the full ABI 3 `Image modules
dtbs` build completed. It is preparation for the [prospective native run
plan](../WFI-ABI3-RUN-PLAN.md), not an installed, booted or captured result.
The [ticket protocol](../WFI-ABI3-TICKET-PROTOCOL.md) limits a positive to
software final-entrant order at a first-attempt **pre-DSB** command read;
it cannot place BUSY or peers at the later WFI instruction.

The [incremental patch](0001-abi3-cluster-tickets.patch) has SHA-256
`2775fd894e7d62432b806e45f0db7a94e9d6c789dcaa0a57e7d72d0f9d7d3486`.
It applies to the exact private PCPM source tree behind the earlier
[PCPM full-build receipt](../../linux-pcpm-sampler/aurora-wfi-pcpm-build-receipt.json),
whose previous tree SHA-256 is
`9733d6cb7f1fb8bed30bbaffc6a7b22a42b68dac2acc636fe2125c3faed1d19f`.
The [new source receipt](source-hash-receipt.json) checks 100,233 tree entries
under its stated hashing algorithm, confirms only
`drivers/cpuidle/apple-apsc-observer.c` and `cpuidle-apple.c` changed, and
records candidate tree SHA-256
`e703916291104ece7de51f24ecdd042fa8ac01463448ebeb1c337b85f647f462`.
The patch applies forward to that exact PCPM source and reverses from the
candidate. It is not a standalone patch against pristine Aurora Linux.

The private enabled object build passed. The [object proof](object-validation.json)
pins baseline and candidate object SHA-256s and confirms two first-attempt
`ldaddal` tickets, one conditional APSC Device load, the ticket-only branch
skipping that load, and byte-identical original `dsb sy; wfi` through `ret`
tail. The [proof script](validate_object.py) documents the disassembly
assertions; it expects the private scratch object layout and is not a public
binary reproduction. The ticket counter object has separately aligned
128-byte E/P elements. Linked-image checks remain pending.

The read-only [ABI 3 packet validator](validate_tickets.py) rejects missing
or duplicate tickets, incomplete tokens, stream loss, policy/DVFS mismatch,
bad WFI slots and clock-marker contradictions before reporting any software
candidate. Its [30 synthetic tests](test_validate_tickets.py) pass with:

```sh
cd experiments/aurora-apsc-observer/abi3-prototype
python3 -m unittest -q test_validate_tickets.py
```

Source/object success alone does not establish a bootable image, live LSE
support, a native BUSY result, physical idle, energy, or an idle-policy
benefit. A full linked build, guarded deployment, fresh-boot qualification
and matched controls are separate gates.
