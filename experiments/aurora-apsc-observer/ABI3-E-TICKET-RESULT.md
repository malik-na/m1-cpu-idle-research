# Native ABI 3 ticket-plus-read E result, 4 October 2026

The fresh-boot E phase in the [fixed ABI 3 run plan](WFI-ABI3-RUN-PLAN.md)
recorded **71 APSC command words with BUSY bit 31 set** at the first-attempt
**pre-DSB** WFI-path read. E's cluster-ticket stream gives **18 complete
software final-entrant witnesses**, all in cluster 1: three on CPU 4, eleven
on CPU 5 and four on CPU 6. Each has a valid raw BUSY word, the candidate's
completed idle-hook interval and three completed peer intervals in the
strict [ticket order](WFI-ABI3-TICKET-PROTOCOL.md). This is a positive
observation of a pending command **at the instrumented read** while all
three peers were inside their recorded software idle callbacks. It does not
establish BUSY at the later executed WFI instruction, peer physical sleep,
cluster power removal, energy, wake latency or a Linux idle-policy benefit.

The selected entry was `Aurora-APSC-research-wfi-pcpm-abi3`, running
`7.1.12-ARCH-apsc-20261002-wfi-pcpm-abi3` on T8103/J313. The fresh-boot
qualification bound the installed image to GNU Build-ID
`6fbc0dc67bb746466a7244ba2fc096ecae7e6476`, linked Image SHA-256
`1368f40aed236c770485eb8b1b2b0b0bc496915c21fc01fbf608f5f60243a537`,
configuration SHA-256
`f4df15bf0c94e82210a503c91a9dd408b848d98aed45b0a2a09d691efbcf70a5`,
and the previously qualified source/build/deployment receipts. Its boot
differs from the sealed D predecessor. All eight CPUs, the two cluster
resources, LSE support, observer ABI and fallback entries were checked
before arming. The operator confirmed that a page loaded over Wi-Fi on this
boot. The visible brightness change was checked on the first ABI 3 boot;
E's backlight readback was 155, with AC online `1`, at preflight, arm and
capture end. No repeat visual display test was required by the fixed plan.

The observer completed one 10,000 ms requested `wfi_mmio` capture, consuming
this boot's one-shot control. Its kernel-reported interior lasted
**10.411807702 seconds**; this actual span, rather than the requested
sleep, defines the comparison window. The raw streams contain 2,185
first-attempt WFI rows, each with `cmd_valid=1` and a raw command word;
2,185 idle enters, 2,181 idle exits and 1,696 ordinary cpufreq DVFS
records. Four idle tokens remained open when recording stopped and cannot
qualify a completed witness. The WFI rows split 1,316/869 between clusters
0/1. All stream attempts equal commits, with zero overflow or missing
commit; status reports zero interruption, pending WFI slot, bad mapping
and after-stop preparation. The saved [ABI 3 validator](abi3-prototype/validate_tickets.py)
replayed the raw status and event streams exactly and checked contiguous,
unique per-cluster tickets between capture sentinels (5,264 in cluster 0;
3,472 in cluster 1), CPU/token matching, local counter order, and no
CPU-PM failure.

The 71 BUSY words comprise 42 cluster-0 and 29 cluster-1 reads. The other
2,114 WFI-path command reads had BUSY clear (1,274 in cluster 0 and 840
in cluster 1); their raw values remain in the same packet. These are
individual clear probes within a positive window, not a separate sensitive
negative capture. The validator accepted 18 cluster-1 rows as full ticket
witnesses and retained
the other **53 BUSY rows** with their rejection reasons. All 42 cluster-0
BUSY rows lack a CPU-0 peer interval; the CPU-0 idle stream contains no
enter row in E. This is a recorded software-stream property, not a claim
about CPU-0 physical state. The rejection-reason counts are below. A row
can have several missing peers, so the counts overlap.

| Rejection reason | BUSY rows |
| --- | ---: |
| Candidate exit missing | 1 |
| Peer 0 interval missing | 42 |
| Peer 1 interval missing | 32 |
| Peer 2 interval missing | 30 |
| Peer 3 interval missing | 10 |
| Peer 4 interval missing | 1 |
| Peer 5 interval missing | 3 |
| Peer 6 interval missing | 9 |
| Peer 7 interval missing | 4 |

For example, CPU 4/token 177 read `0x0000040080104104` with BUSY set.
Its cluster's capture tickets were start `1` and stop `3474`; peer enters
were CPU 5/token 129 at `1884`, CPU 6/token 160 at `1899`, and CPU 7/token
11 at `1735`. CPU 4 entered at `1903`, bracketed the read with tickets
`1904` and `1905`, and exited at `1919`. Peer exits were `1918`, `1906`
and `2038`, respectively. Thus every peer entered before the candidate
and exited after its read bracket. The closest peer exit is only **one
ticket after** the bracket; it could precede CPU 4's subsequent WFI.
Across all 18 witnesses, the raw BUSY words are
`0x0000040080101101` (five), `0x0000040080104104` (one), and
`0x000004008010c10c` (twelve). The [numerical packet](native-evidence/abi3-E/README.md)
retains every WFI row, the three peer tokens and intervals for each
witness, and all rejected BUSY rows for independent reconstruction.

A stricter **post-hoc software-order screen** requires every peer's
idle-exit ticket to follow the candidate's idle-exit ticket, in addition to
the predeclared read-witness inequalities. Six of the 18 BUSY witnesses pass:
CPU/token `4/241`, `5/82`, `5/97`, `5/113`, `6/92`, and `6/206`. Their
candidate exit tickets are respectively `2770`, `1198`, `1462`, `1626`,
`1070`, and `2342`; the earliest peer exits are `2786`, `1206`, `1463`,
`1627`, `1074`, and `2350`. The [linked WFI routine](abi3-prototype/linked-code-evidence.txt)
executes the original WFI before returning, and the [reviewed idle wrapper](0001-aurora-t8103-apsc-observer.patch#L795-L835)
records its exit ticket after that call and `ct_cpuidle_exit`. Thus these
peer callbacks had not returned when the candidate executed WFI. A peer may
already have left its own WFI or context-tracking idle state before its
later exit ticket. This stronger callback order does not move the earlier
BUSY read to WFI or prove BUSY continuity, physical peer sleep, or power
state; a one-ticket gap is order, not a time bound.

Every witness has a preceding successful **same-CPU** SET targeting cluster
1; the cpufreq policy representative is CPU 4 for all of them. The table
shows each witness's candidate CPU/token, raw read, and the conservative
local upper lag from the nearest preceding same-CPU successful SET:
`probe.t1 − SET.t0`. The counter frequency is 24 MHz. The submitted SET
command is preserved with its actual writer and target policy in the event
stream. A policy representative is not an observed individual hardware
target core.

| Candidate CPU / token | Raw BUSY read | Nearest same-CPU SET upper lag (ticks) |
| --- | --- | ---: |
| 4 / 177 | `0x0000040080104104` | 54 |
| 4 / 241 | `0x0000040080101101` | 74 |
| 4 / 281 | `0x0000040080101101` | 90 |
| 5 / 77 | `0x000004008010c10c` | 458 |
| 5 / 82 | `0x000004008010c10c` | 658 |
| 5 / 97 | `0x0000040080101101` | 92 |
| 5 / 103 | `0x000004008010c10c` | 528 |
| 5 / 113 | `0x000004008010c10c` | 570 |
| 5 / 168 | `0x000004008010c10c` | 474 |
| 5 / 173 | `0x000004008010c10c` | 485 |
| 5 / 178 | `0x000004008010c10c` | 630 |
| 5 / 198 | `0x000004008010c10c` | 586 |
| 5 / 203 | `0x000004008010c10c` | 630 |
| 5 / 210 | `0x000004008010c10c` | 673 |
| 6 / 92 | `0x0000040080101101` | 359 |
| 6 / 97 | `0x000004008010c10c` | 978 |
| 6 / 206 | `0x0000040080101101` | 240 |
| 6 / 265 | `0x000004008010c10c` | 758 |

Twelve nearest local lags are at most 600 ticks; six exceed that bound.
The 600-tick gate governs a **negative** exposure claim and does not erase
any positive read. These local brackets establish same-CPU SET-to-read
order, not which SET caused BUSY: cpufreq can submit a cluster command from
another CPU. E contains 213 successful cluster-1 SET records from writers
both inside and outside that cluster's CPU mask, and no independently
qualified capture-wide cross-CPU writer/clock bound. The table therefore
does **not** count twelve fully qualified primary opportunities or claim a
causal mapping from a particular SET to a BUSY read.

The linked instruction proof places two LSE `ldaddal` ticket acquisitions
around the conditional single APSC load, with reviewed full-system barriers
and the unchanged `dsb sy; wfi`/retry tail. This orders the **read** inside
the ticket bracket but leaves instructions, publication and time between
the second ticket and WFI. The tickets cover software callbacks, not
physical power state. The preceding [ABI 2 block](WFI-ABI2-BLOCK-RESULT.md)
had one candidate only under an unmeasured cross-CPU clock-error
assumption; ABI 3's ordered software witnesses remove that particular
assumption for the peer intervals without bridging the instruction-state
gap.

Both pinned workers finished 200 pulses without migration, missed periods
or checksum mismatch. Exactly **196 pulses per CPU, indices 4–199**, fell
fully inside E's kernel-reported interior, as in A and D. E's summed
interior row durations were 1.991904583 seconds on CPU 1 and 1.979450187
seconds on CPU 5; these are delivered-work durations, not energy or idle
latency. E's WFI `t1−t0` median was 13 counter ticks in each cluster,
versus D's 3; D had 1,524/349 WFI slots in clusters 0/1 and E had
1,316/869. D's `wfi_clock` rows omitted the extra command load, while E
included it, but the different boots, window spans (D 10.446344953 s;
E 10.411807702 s), event composition and background conditions prevent
isolating MMIO cost or its causal effect on workload. The E battery read
73% and thermal zone 39.5°C at both endpoints, versus D's 61→62% and
38.8°C; one external USB device present in D was absent in E. AC,
brightness, eight online CPUs, `apple_idle`/`menu`, `schedutil` policies,
network and USB inventories, and thermal readings were stable **within E's
endpoint snapshots**. That does not establish stable activity throughout
the window or match A/D conditions.

The sealed private E packet contains 64 SHA-256-manifested files; its
manifest SHA-256 is
`a65ca101c652c4968ee62e737e7ab1e833bbd14a39979245f84718836995131a`.
The manifest file set and all file hashes checked, and executing the
sealed validator source on the saved raw streams reproduced its report
byte-for-byte (SHA-256
`b290ecff1eea7f20718e00bd18fdb4eb27d41c3b026aec2c175c6474914ec163`).
The private packet retains the boot ID, full logs and boot arguments, FDT,
device identities, wall-clock times and original worker timestamps. The
public projection retains
reviewed numerical streams, transformations and hash links without those
private details.

The fixed plan says to **stop after a clean positive ticket witness**.
E met that condition, so the conditional fresh-boot C sensitivity control
is not warranted by this block. A C read at the earlier idle hook would
not recover command state at WFI. Issue #5's stronger exact-WFI and
physical-state questions remain open and require a separately validated
instruction-correlated command-state or BUSY-continuity method; this result
does not justify a Linux idle-policy change.
