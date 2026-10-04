# Native ABI 3 ticket-only D control, 4 October 2026

The fresh-boot D control in the [fixed ABI 3 run plan](WFI-ABI3-RUN-PLAN.md)
completed one `wfi_clock` capture on the T8103/J313 Aurora image. It recorded
**1,873 first-attempt WFI-path slots** with a per-cluster ticket before and
after the probe work. This mode deliberately omitted the APSC command-register
load at that seam. Every WFI row has `cmd_valid=0` and an empty `cmd` field;
the D packet therefore has **no WFI-path BUSY or clear observation**. D tests
the ticket stream and supplies a same-instrument, no-command-load control for
a later fresh-boot E capture. It is not a negative BUSY result.

The selected Limine entry was `Aurora-APSC-research-wfi-pcpm-abi3`, and the
running release was `7.1.12-ARCH-apsc-20261002-wfi-pcpm-abi3`. The boot gate
checked the same GNU Build-ID (`6fbc0dc67bb746466a7244ba2fc096ecae7e6476`),
configuration SHA-256 (`f4df15bf0c94e82210a503c91a9dd408b848d98aed45b0a2a09d691efbcf70a5`),
linked Image and installed UKI hashes as the separately qualified
[A baseline](ABI3-A-BASELINE-RESULT.md). The private D packet binds its own
fresh boot, EFI readback, source/collector/validator hashes and the earlier
A packet before arming. The stock default and PCPM fallback image hashes were
also checked. The operator confirmed that a page loaded over Wi-Fi on this
D boot. Visible brightness had been verified on the first ABI 3 boot; this
later boot had a working backlight interface and setting 155 without a repeat
visual test.

The requested capture duration was 10,000 ms. The kernel-reported interior
markers span **10.446344953 seconds**. The observer source calls
`msleep_interruptible(duration)` between those markers, and the saved status
reports `interrupted=0`; the measured span, rather than the requested sleep,
sets D's actual comparison window. The packet does not isolate what caused
the extra 446 ms of elapsed time. The same pinned workload scheduled
200 pulses on each of CPUs 1 and 5 at 50 ms intervals, with 1,048,576
iterations per pulse. Both workers completed all 200 pulses without migration,
missed periods or checksum disagreement. Exactly **196 pulses per CPU,
indices 4–199**, fell fully inside the kernel-reported interior interval.
Their summed row durations were 2.086953056 seconds on CPU 1 and 2.042750530
seconds on CPU 5. The checksum sequence matched between workers and the prior
A baseline. These are delivered-work durations, not CPU energy or idle latency.

The after-status reports `abi=3`, `state=complete`, `mode=wfi_clock`, with all
eight CPUs online, unchanged cluster/policy masks, zero interruption and no
pending WFI slot after drain. The raw streams contain 3,741 idle rows
(1,873 enters and 1,868 exits), 1,873 WFI rows, and 469 DVFS rows. Cluster 0
has 1,524 WFI slots and 369 DVFS rows; cluster 1 has 349 WFI slots and 100
DVFS rows. Every stream reports attempts equal to commits, with zero overflow
and missing commits. The offline validator replayed the raw status and CSVs,
confirmed unique contiguous cluster tickets between the start and stop
sentinels (6,095 recorded tickets in cluster 0 and 1,392 in cluster 1), and
found no CPU-PM failure, bad mapping or after-stop WFI preparation. Five
idle-enter tokens were still open when recording stopped. The accepted
one-shot stream retains those incomplete intervals; they cannot qualify a
positive candidate requiring a completed peer interval.

An exploratory ticket-only geometry screen found 68 WFI slots in cluster 0
and 177 in cluster 1 for which the candidate's completed idle interval and
all three peers' completed intervals obeyed
`peer_enter < candidate_enter < ticket_pre < ticket_post < peer_exit`, with
`ticket_post < candidate_exit`. This applies the
[protocol's](WFI-ABI3-TICKET-PROTOCOL.md) software-hook order while omitting
its command-value test. None is a BUSY witness because D made no WFI-path
command read. The saved validator's `candidate_count=0` counts full
command-qualified witnesses, not this separate geometry screen.

As a descriptive local bracket measure, WFI-row `t1−t0` spans had median
3 ticks and 95th percentile 3 ticks on each cluster; the largest was 7 ticks
in cluster 0 and 5 in cluster 1. The recorded counter frequency was 24 MHz.
The bracket includes ticket atomics, barriers and mode selection, but ends
before the later slot-commit store; timer resolution allows zero-tick rows.
It is neither isolated instrument overhead nor the time from probe to the
executed WFI. The unarmed A baseline has no comparable WFI bracket. Its 196
interior worker rows per
CPU summed to 1.763893162 and 1.966471576 seconds, respectively; those
fresh-boot differences are observational. D's window was longer, the sampled
thermal zone read 38.8°C at both endpoints versus A's 33.4°C, and the battery
read 61% then 62% rather than A's 100%. AC was online and brightness 155 at
D's preflight, arm and endpoint checks. `apple_idle`, `menu`, the two
`schedutil` policies, online CPUs and state availability agreed across D's
endpoint snapshots; saved network/USB inventories and thermal reading also
agreed between those endpoints. Endpoint agreement does not establish equal
background conditions during the windows.

The 469 DVFS records belong to the ordinary cpufreq path. They retain a
`pre_cmd` command read before a requested SET, and every recorded `pre_cmd`
BUSY bit was clear. The `cmd` value in those rows is the submitted command,
not a WFI-path readback. These values do not change D's no-command-load
classification or establish command state near a WFI instruction. The
validator's `busy_rows=0` and `candidate_count=0` are expected for
`wfi_clock`, because the WFI rows have no command value to screen.

The sealed private D packet has 64 manifest-listed files; their SHA-256
entries, the exact file set and the saved validator report were independently
replayed. Its manifest SHA-256 is
`bf1bc8c08e58c02661183cef4a1b878c93bb09dd5c557b6c789915f6a78df159`.
The private packet retains the boot ID, operator receipt, full logs and boot
arguments, FDT, network/USB identities and absolute timestamps. The
[public D numerical packet](native-evidence/abi3-D/README.md) retains
reviewed status, events, tickets, workload and bounded endpoint projections,
with a separate public manifest and replay command. The historical
[ABI 2 D pilot](WFI-D-RESULT.md) is context, not a matched control for ABI 3's
shared atomic and barriers.

Next, the plan calls for `wfi_mmio` E on a **different fresh boot**, with the
same pinned workload and device/environment gates. E must be judged against
the [ticket protocol](WFI-ABI3-TICKET-PROTOCOL.md)'s raw command, strict peer
software-interval, stream-loss and exposure criteria. Even a positive E
pre-DSB read would not prove BUSY at the later executed WFI, physical peer
sleep, cluster power, energy, wake latency or a Linux idle-policy improvement.
