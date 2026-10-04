# Native ABI 3 unarmed A baseline, October 2026

The first fresh boot of the ABI 3 T8103/J313 Aurora image completed the
predeclared [A baseline](WFI-ABI3-RUN-PLAN.md) with the APSC observer unarmed.
Each worker completed all 200 scheduled pulses on CPUs 1 and 5. Exactly
**196 pulses per CPU, indices 4–199**, were fully inside the
10.000120857-second userspace window. This is a delivered-work and instrument-state
baseline for later fresh-boot D/E comparisons, not an APSC command or WFI
observation.

The selected Limine entry was `Aurora-APSC-research-wfi-pcpm-abi3`; the live
release was `7.1.12-ARCH-apsc-20261002-wfi-pcpm-abi3`. The boot checks matched
GNU Build-ID `6fbc0dc67bb746466a7244ba2fc096ecae7e6476`, configuration
SHA-256 `f4df15bf0c94e82210a503c91a9dd408b848d98aed45b0a2a09d691efbcf70a5`,
linked Image SHA-256 `1368f40aed236c770485eb8b1b2b0b0bc496915c21fc01fbf608f5f60243a537`,
and installed UKI SHA-256 `3c00f38bce07ad99d18c762acd4aa1f318e99d06bde8e7142e86d4ef02568530`.
The checked source-tree SHA-256 was
`e703916291104ece7de51f24ecdd042fa8ac01463448ebeb1c337b85f647f462`,
with ABI 3 patch SHA-256
`2775fd894e7d62432b806e45f0db7a94e9d6c789dcaa0a57e7d72d0f9d7d3486`.
The [source and linked-build packet](abi3-prototype/README.md) and
[deployment receipt](abi3-deployment-receipt.json) describe the source,
module, Image, DTB and installed UKI checks. The private A packet retains the
boot-specific readback and full qualification evidence.

All eight CPUs were online, with `apple_idle` and `menu` reported. The
operator's first-boot receipt reports that a Wi-Fi page loaded and that the
panel visibly dimmed and restored during a 155→40→155 brightness check.
That receipt is a user-observed device check; the saved endpoint readbacks
separately show the backlight interface present and brightness 155. AC online
was `1` at both endpoints. The battery read 100%, the sampled thermal zone
read 33.4°C at both endpoints, and the saved USB and network inventories did
not change between endpoint snapshots. Endpoint agreement does not prove
constant background load during the window or a match to later boots.

The pinned [workload](pulse_workload_abi3.c) scheduled 200 pulses per CPU at
50 ms spacing, with 1,048,576 iterations per pulse. Its source SHA-256 was
`a9b5dedf8b42c7013ebb87cc3754dce1f80fce293a02911b5e8175d61d4eff73`
and the acquisition binary SHA-256 was
`2b4ed83c6f81be68eeb4e9aa448eb81493852f1bf114edb249f75a1e55234a89`.
The saved summary reports 1.763893162 seconds of work across CPU 1's 196
interior pulses and 1.966471576 seconds across CPU 5's 196 interior pulses.
These are sums of worker-row durations, not energy or idle latency. Both
workers completed all 200 pulses; the 196 interior rows per CPU are the
eligible A rows for a later matched comparison.

The APSC status remained `abi=3`, `state=ready` before and after the window.
No capture command or control write was attempted. Both APSC event files
contained headers only: **zero idle, DVFS and WFI observer rows**, with zero
attempts, commits, overflow and missing commits in the status fields. The
counter and PCPM helpers stayed unused. These zeros follow from the unarmed
instrument and do not mean the CPUs did not idle or that no DVFS command was
pending. The saved A window uses userspace monotonic markers; it has no armed
kernel start/stop sentinels or ticket stream. It therefore cannot classify a
BUSY command read, software peer overlap at a first-attempt pre-DSB probe,
peer sleep at WFI, physical power state, energy or wake behavior.

The sealed private A packet's 59 manifest-listed files rechecked against
SHA-256 with no missing, changed or extra files. The numerical rows and
status, rather than the private boot identifier, full logs, command line,
network identifiers or local paths, are the publication boundary for this
result. The [public A packet](native-evidence/abi3-A/README.md) has its own
SHA-256 manifest (`df7c683a7f21743f1b9b54e14346caa2f79e7cc7b15ea397a10b9498df182446`)
and a receipt that binds each projection to hashed private inputs. Its
[offline verifier](abi3-acquisition/publish_abi3_a.py) replays the public
worker and unarmed-status checks without the private boot packet. Later D/E
captures require their own fresh-boot qualification and
the [ticket protocol](WFI-ABI3-TICKET-PROTOCOL.md)'s independent validation.
