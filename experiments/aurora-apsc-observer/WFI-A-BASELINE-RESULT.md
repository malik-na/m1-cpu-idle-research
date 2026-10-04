# Native ABI 2 unarmed A baseline, 3 October 2026

On a fifth distinct fresh boot of `Aurora-APSC-research-wfi-seam`, the A
`baseline` mode ran the pinned CPU 1/5 workload for a bounded 2,000.167 ms
external window while leaving the APSC observer **unarmed**. Its status
remained `state=ready`, with zero idle, DVFS and WFI attempts or commits;
both event files contain headers only. Those zeros are an instrument-state
control, not a claim that the CPUs did not enter idle or that no DVFS
command was pending.

The boot reported release `7.1.12-ARCH-apsc-20261002-wfi`, GNU Build-ID
`11e80be6d8b358eee9aa847a0f814aff02b66c43`, configuration SHA-256
`f86b80f4dcef277be874f476293d8b8055053072f7209625586b60e2227f905d`,
and the WFI Limine entry. Its private boot ID differs from D/E/C/B. Same-boot
FDT topology, eight CPUs, cpuidle, observer ABI, module-package, Wi-Fi and
visible 155→40→155 brightness checks passed before capture. AC stayed
connected and brightness was 155 at both capture endpoints.

Each workload completed all 44 pulses and exited successfully. Exactly
**39 pulses per CPU, indices 4–42**, were fully inside A's actual window;
the [five-packet comparator](wfi-abi2-first-block-comparison.json) therefore
uses only these common indices for its matched worker-duration summary.
Pre/post counter phases each
completed 1,792 exchanges under the declared conditional model. They do
not establish a guaranteed cross-CPU clock-error bound over the unsampled
window. All private acquisition hashes verify, and the
[publication receipt](wfi-a-baseline-receipt.json) independently checks the
unarmed status, same-boot qualification, counter/workload record and
[public numerical packet](native-evidence/A-abi2/status.txt).

The battery was charging at 94%; thermal zone 0 was 33.7°C at both
endpoints. Wi-Fi remained up and passed traffic across the broad packet
interval; no USB device was listed. Online CPUs, cpuidle settings and
cpufreq policy settings matched; instantaneous reported frequencies varied.
The private kernel log was byte-identical before and after
capture. These endpoints do not establish background or thermal
equivalence throughout the window or across the five boots. The
[build receipt](wfi-build-receipt.json) lacks a build-time WFI patch or
source-tree digest, so the later source-file hash is not a cryptographic
source-to-image proof. The [matched-block result](WFI-ABI2-BLOCK-RESULT.md)
states what the five captures establish and what remains unobserved.
