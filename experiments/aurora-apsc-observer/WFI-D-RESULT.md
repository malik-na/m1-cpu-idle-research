# Native ABI 2 WFI clock pilot, 2 October 2026

The first fresh boot of `Aurora-APSC-research-wfi-seam` passed the planned
`wfi_clock` D pilot. It recorded 660 matched first-attempt, pre-DSB WFI-path
probes with no command-register read, ring loss, missing commit or unresolved
slot. This establishes that the closer probe can be captured and decoded on
this T8103 machine. It makes **no BUSY or physical power-state claim**; the
separate `wfi_mmio` E boot is needed for command-state evidence.

The selected release was `7.1.12-ARCH-apsc-20261002-wfi`, GNU build ID
`11e80be6d8b358eee9aa847a0f814aff02b66c43`, and exported configuration
SHA-256 `f86b80f4dcef277be874f476293d8b8055053072f7209625586b60e2227f905d`.
The private same-boot qualification checked J313/T8103, eight CPUs, the two
cluster controller resources, the live observer ABI, module integrity and
the selected boot entry. The operator confirmed working Wi-Fi and a visible
brightness change from 155 to 40 and back. The same-boot acceptance and FDT checks are
summarized in the [publication receipt](wfi-clock-pilot-receipt.json); complete
boot details and logs remain private.

The [predeclared plan](WFI-PLAN.md) required one clean D pilot before E on a
different boot. The 2,000 ms requested acquisition had a measured external
window of 2,031.296 ms, with both CPU 1 and CPU 5 completing 40 fully interior
worker pulses. The 660 probes comprise 451 on cluster 0 and 209 on cluster 1.
All 660 were matched to the paired software path and strictly inside the
recorded window **under the assumed, unmeasured 240-tick cross-CPU error
model**. There were no open intervals without a sample, unexplained paired
paths, post-stop probes, bad mappings, or pending slots after drain. Every
observer stream reported zero overflow and missing commits. The counter
qualifier completed 1,792 pre and 1,792 post exchanges under the declared
conditional model; those endpoint checks do not guarantee the clock error
throughout capture.

The [public D packet](native-evidence/D/status.txt) retains the raw numerical
observer, WFI, counter and workload streams, status/error counts, filtered
chronology and bounded environment observations. The
[publisher](publish_wfi_evidence.py) verified acquisition hashes, replayed
the ABI 2 analysis and produced deterministic compressed streams. Its
[receipt](wfi-clock-pilot-receipt.json) links input and output hashes and
explicitly marks the cross-CPU bound as unproven. The full private packet
retains the original manifest, full FDT, boot arguments and kernel logs. The
pre- and post-capture kernel logs were byte-identical in a local check, but
their contents are not part of the public packet.

The charger was online and panel brightness was 155 at both capture
endpoints; battery charge rose from 44% to 45%. Endpoint network and USB
observations do not establish matched background conditions during the
window. Whole-system CPU counters include the workers and collector. These
limits matter when comparing later fresh boots. D's clock-only path did not
read the APSC command register, so its peer-candidate screen is exploratory
software timing only. Neither D nor the earlier C-hook result identifies the
state at the later WFI instruction, a physical sleep transition, energy or
wake latency.

Next, acquire `wfi_mmio` E on a fresh boot with the same charger/brightness
baseline and device checks, followed by C/B/A controls on separate boots.
Apply the already declared paired-opportunity and comparability gates before
interpreting a positive or zero E result.
