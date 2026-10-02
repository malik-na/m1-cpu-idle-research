# ABI 3 ticket source, object, and linked-build packet

The source/object portion was frozen **before** the full ABI 3 `Image modules
dtbs` build completed. The linked-build addendum below was recorded after the
build exited successfully. This is preparation for the [prospective native run
plan](../WFI-ABI3-RUN-PLAN.md); this packet alone does not establish an
installed, booted or captured result. The subsequent installation has a
separate [sanitized deployment receipt](../abi3-deployment-receipt.json).
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
128-byte E/P elements.

The [linked-build result](LINKED-BUILD-RESULT.md), [receipt](linked-build-receipt.json),
[build status](full-build-status.json), and [proof script](make_linked_receipt.py)
pin a successful `Image modules dtbs` build. The linked Image SHA-256 is
`1368f40aed236c770485eb8b1b2b0b0bc496915c21fc01fbf608f5f60243a537`
and vmlinux GNU Build-ID is `6fbc0dc67bb746466a7244ba2fc096ecae7e6476`.
The receipt covers 1,867 ABI 3-vermagic modules, 111 Apple DTBs including
T8103/J313, the two linked `ldaddal` tickets, the single conditional APSC
read, 128-byte-separated counters, and the unchanged original DSB/WFI retry
tail. The [linked disassembly excerpt](linked-code-evidence.txt) exposes the
checked instruction bytes. The full build log remains private; its hash is in
the build status.

The read-only [ABI 3 packet validator](validate_tickets.py) rejects missing
or duplicate tickets, incomplete tokens, stream loss, policy/DVFS mismatch,
bad WFI slots and clock-marker contradictions before reporting any software
candidate. Its [30 synthetic tests](test_validate_tickets.py) pass with:

```sh
cd experiments/aurora-apsc-observer/abi3-prototype
python3 -m unittest -q test_validate_tickets.py
```

Source/object and linked-build success do not establish a successful native
boot, live LSE support, a BUSY result, physical idle, energy, or an idle-policy
benefit. The distinct module package and UKI have since been installed and
read back, but fresh-boot qualification and matched controls remain separate
gates.
