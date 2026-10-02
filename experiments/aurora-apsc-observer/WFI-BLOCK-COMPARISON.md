# Prospective ABI 2 matched-block comparison

[`compare_wfi_blocks.py`](compare_wfi_blocks.py) implements the cross-boot
comparison declared in the [first-attempt protocol](WFI-PLAN.md). This is
analysis preparation. The [single-packet D pilot](WFI-D-RESULT.md) has been
published, but **no complete native ABI 2 block has been supplied to or
accepted by this verifier at this checkpoint.** Its
[tests](test_compare_wfi_blocks.py) use synthetic private packets only.

The private input JSON has schema `1` and a `blocks` array with one or two
five-element arrays. Each element has exactly `mode`, `packet`,
`qualification`, `device_acceptance`, `receipt`, and `evidence` keys naming
the private acquisition packet, its same-boot qualification and device
acceptance, and its published receipt/evidence directory. Block one must be
ordered `wfi_clock`, `wfi_mmio`, `mmio`, `records`, `baseline` (D/E/C/B/A).
Only if its declared decision gates remain unmet may block two be added in
the reverse order A/B/C/E/D. The verifier processes all supplied runs; it
does not select the best packet or silently drop a failed one. The operator
must retain failed acquisition packets separately, because this input alone
cannot prove that none were omitted.

Run from this directory with a private specification and a **new** public
output path:

```sh
python3 compare_wfi_blocks.py "$private_spec" --out "$new_reviewed_comparison"
```

For each acquisition, the verifier replays the single-packet publisher on
the original private files and requires the resulting receipt and all
published evidence bytes to match exactly. This rechecks every
acquisition-time `SHA256SUMS` entry, saved collector source, pinned image and
configuration, T8103 same-boot qualification, Wi-Fi/brightness acceptance,
counter exchanges, observer integrity and endpoint conditions. The source
checkout must match the publication-time decoder/publisher hashes for exact
replay. It then checks distinct private boot IDs, strictly increasing
recorded UTC capture intervals, matching collector/workload/image/policy,
AC online `1` and brightness `155` at the checked endpoints, and the
intersection of fully interior CPU 1/5 worker pulse indices over **all**
included packets. UTC order is recorded process evidence; wall-clock
correction or omitted attempts cannot be independently ruled out.

E and C use the predeclared 600-tick primary and 2,400-tick exploratory
pair screens with the explicitly assumed, unmeasured 240-tick pairwise
cross-CPU error. The verifier independently checks that the decoder's
maximum SET-to-read bracket lag is `sample.t1 - SET.t0 + error`, so a
minimum-gap calculation cannot falsely satisfy the 600-tick gate. It
totals distinct E primary opportunities per cluster, E BUSY counts and C
primary BUSY controls without pairing events across different boots.
A clean model-interior E BUSY row yields only a first-attempt pre-DSB positive.
The output separately reports whether E has at least 20 clean primary paired
opportunities **per cluster**, zero BUSY in those pairs and at least one
primary C BUSY pair per cluster. It does **not** call that a sensitive matched
C/E negative: no predeclared numerical thermal band exists and USB, network
and background activity are not fully observed. Even when the numerical
gates pass, the comparison decision remains inconclusive on environmental
comparability. If the gates remain unmet after two blocks, the result is
underexposed/inconclusive. A first inconclusive block permits the declared
second block.

The output includes hashes, per-block numerical counts, all model-interior
E BUSY rows, bracket summaries, common-pulse timing and thermal endpoints.
It withholds packet paths, boot IDs and private logs. Endpoint readings do
not establish conditions throughout the window; USB, network and background
activity remain incompletely observed. The 240-tick cross-CPU bound is not
calibrated through the capture. Neither a positive nor a qualified zero says
what the command bit was at the later WFI instruction, whether a peer was
physically asleep, or what happened to a rail or energy use. The verifier
also reports a separate conditional software candidate-final-entrant screen:
the E sample and all four same-cluster software idle intervals must be
complete and model-interior, with the three peers enclosing the candidate's
entry and sample under assumed `E=240`. It counts candidate-qualified E
primary pairs per cluster against their own 20-pair gate. These labels remain
conditional on the unmeasured clock bound and do not prove peer physical
sleep or a physical final core. The generic 20-pair command-timing gate does
not substitute for candidate-specific exposure.
