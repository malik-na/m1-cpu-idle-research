# Public ABI 3 ticket-plus-read E evidence

This packet supports the [native ABI 3 E result](../../ABI3-E-TICKET-RESULT.md)
under the [fixed run plan](../../WFI-ABI3-RUN-PLAN.md). On a fresh
qualified boot, E ran the pinned CPU 1/5 workload with the APSC observer
armed in `wfi_mmio` mode. The first deep-WFI attempt on each recorded idle
entry took cluster tickets before and after one read-only APSC command load.
The load is before the original `dsb sy; wfi`. All **2,185** WFI rows retain
their raw command words: **71** have BUSY bit 31 set and **2,114** do not.
The ticket validator accepts **18** of the BUSY rows as complete
software-hook final-entrant witnesses and retains the other **53** with
their exact rejection reasons. Ordinary cpufreq DVFS records retain their
own `pre_cmd` reads and submitted `cmd` values; they are separate from the
WFI-path read.

The offline [E publisher](../../abi3-acquisition/publish_abi3_e.py) checked
the sealed private E packet and its separate sealed
[D control](../abi3-D/README.md) and [A baseline](../abi3-A/README.md),
including file modes/manifests, source and running-build identity,
current-boot Wi-Fi and first-boot brightness receipts, one-shot control,
timeline, raw streams, workload and endpoint gates. It reran the
[ticket validator](../../abi3-prototype/validate_tickets.py) on the raw
streams, wrote this reviewed projection and replayed the projection
without private inputs. The [public acquisition logic](../../abi3-acquisition/README.md)
and publisher redaction receipts bind these review copies to the private
executable sources. This publisher has no live-kernel, debugfs-control or
worker-launch operation.

| File | Publication transformation |
| --- | --- |
| `apsc-events.csv.gz`, `apsc-wfi-events.csv.gz` | Deterministic gzip of the byte-exact private CSV streams. The first retains all idle-hook tickets and ordinary DVFS writer, policy, `pre_cmd` and submitted `cmd` fields. The second retains every first-attempt WFI ticket bracket and raw BUSY or clear command word with `cmd_valid=1`. |
| `apsc-status-before.txt`, `apsc-status-after.txt` | Original lines and order for allowlisted keys, including mode, counter frequency, capture markers, masks, ticket sentinels, attempts, commits, overflow and missing commits. Physical command-resource addresses are omitted. |
| `pcpm-status-before.txt`, `pcpm-status-after.txt`, `counter-status-before.txt`, `counter-status-after.txt` | Original lines and order for allowlisted unused-helper fields. Physical mapping, register, per-CPU identity and unused counter-metadata fields are omitted. |
| `workload-cpu1.csv.gz`, `workload-cpu5.csv.gz` | All 200 rows per CPU. CPU, pulse, iterations and checksum remain; `relative_start_ns` is original start minus scheduled start, `duration_ns` is original end minus start, and `fully_inside_window` is recomputed with strict kernel interior bounds. |
| `capture.json` | Derived E mode/state, BUSY/clear/rejected/witness counts, relative window bounds and duration, worker counts, duration sums and checksum-sequence hashes, and checked one-shot/device receipts. Absolute worker timestamps are omitted. |
| `validator-report.json` | Offline ticket validator rerun on the projected APSC status and byte-exact event streams. It retains every raw BUSY screen, accepted witness, peer token/ticket interval and rejection reason. Its status-input SHA-256 names the projected status; the receipt separately pins the private validator report and raw input hashes. |
| `environment.json` | Whitelisted endpoint context: AC/brightness gate, online CPUs, idle driver/governor, cpufreq policies, battery and thermal readings, aggregate network counter changes, network/USB counts and endpoint equality. Interface names, addresses and device identities are removed. |
| `timeline.json` | Selected successful acquisition actions and worker exit statuses only; monotonic times are relative to E's window start. The complete timeline remains private. |
| `publication-receipt.json` | SHA-256 of the sealed E, D and A private manifests, qualified build and source/receipt hashes, and each public artifact's hash with its private input hashes. |
| `MANIFEST.sha256` | SHA-256 over the 15 staged public data files, including the publication receipt. This README is repository documentation outside that staged data manifest. |

From this directory, run `sha256sum -c MANIFEST.sha256` to check the
published bytes, then run
`python3 -B ../../abi3-acquisition/publish_abi3_e.py --verify-public-stage .`
to replay the public status and stream checks, ticket validator, window and
worker summaries without private packets. The replay rederives the
loss-free 2,185 WFI rows, 71 BUSY reads, 18 strict software witnesses,
and complete 200-row workers with 196 strictly interior pulses each.
`capture.json` gives window bounds relative to the scheduled worker start;
a row is interior exactly when `window_start < relative_start_ns` and
`relative_start_ns + duration_ns < window_stop`. Hash the ASCII sequence
`pulse:checksum\n` in pulse order to rederive each worker's
checksum-sequence hash. The public manifest SHA-256 is
`b018320c7dabb0ce81d7b6e0d25b4e90bab7a40e18cb0ba0ec9ad7bc3f26c5a0`.

The receipt binds this projection to the sealed 64-file E manifest and
its separate D and A predecessors. Public readers can rehash and replay
the numerical packet and compare qualified build hashes with the
[linked-build packet](../../abi3-prototype/README.md) and
[deployment receipt](../../abi3-deployment-receipt.json). Rechecking the
actual boot, operator device report, complete source/EFI chain and full
timeline requires the sealed private packets. Boot identifiers, account
paths, full configuration and logs, boot arguments, FDT, network/USB
identities, operator receipt text, wall-clock times and original worker
timestamps are withheld. Raw observer counter ticks and the kernel's
monotonic capture markers remain in the public streams/status for replay.

The tickets order recorded **software idle-hook intervals** around a
first-attempt **pre-DSB command read**. They do not order cpufreq SETs
from other CPUs or place peers at the later executed WFI instruction.
Even a ticket-qualified BUSY read does not establish which SET caused it,
physical peer sleep, cluster power, energy, wake behavior or a Linux
idle-policy benefit. The fixed plan stops after this clean positive
witness; its conditional C sensitivity control is for a zero-witness E
result and is not part of this packet.
