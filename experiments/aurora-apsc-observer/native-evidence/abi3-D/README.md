# Public ABI 3 ticket-only D evidence

This packet supports the [native ABI 3 D result](../../ABI3-D-TICKET-CONTROL-RESULT.md)
under the [fixed run plan](../../WFI-ABI3-RUN-PLAN.md). On a fresh qualified
boot, D ran the pinned CPU 1/5 workload with the APSC observer armed in
`wfi_clock` mode. Each first-attempt WFI-path slot took two cluster tickets
and a counter bracket but omitted the additional APSC command load.
Ordinary cpufreq DVFS records in the same packet retain their own command
values; they are not WFI-path samples.

The offline [D publisher](../../abi3-acquisition/publish_abi3_d.py) checked
the sealed private D packet, its preceding sealed
[A baseline](../abi3-A/README.md), file modes and manifests, source and
running-build identity, current-boot Wi-Fi receipt, first-boot brightness
receipt, one-shot control and timeline, all raw stream/status fields,
workload rows and endpoint gates. It reran the
[ticket validator](../../abi3-prototype/validate_tickets.py) against the raw
streams. It then wrote this separate reviewed projection and replayed it
without private inputs. The [public acquisition logic](../../abi3-acquisition/README.md)
and publisher redaction receipts bind their review copies to the private
executable source. The publisher has no live-kernel, debugfs-control or
worker-launch operation.

| File | Publication transformation |
| --- | --- |
| `apsc-events.csv.gz`, `apsc-wfi-events.csv.gz` | Deterministic gzip of the byte-exact private CSV streams. The first retains idle-hook tickets and ordinary DVFS `pre_cmd`/submitted `cmd` fields; the second retains first-attempt WFI tickets with every WFI `cmd` empty and `cmd_valid=0`. |
| `apsc-status-before.txt`, `apsc-status-after.txt` | Original lines and order for allowlisted keys, including mode, counter frequency, start/stop markers, masks, ticket sentinels, attempts, commits, overflow and missing commits. Physical command-resource addresses are omitted. |
| `pcpm-status-before.txt`, `pcpm-status-after.txt`, `counter-status-before.txt`, `counter-status-after.txt` | Original lines and order for allowlisted unused-helper fields. Physical mapping, register, per-CPU identity and unused counter-metadata fields are omitted. |
| `workload-cpu1.csv.gz`, `workload-cpu5.csv.gz` | All 200 rows per CPU, with CPU, pulse, iterations and checksum retained. `relative_start_ns` is original start minus scheduled start; `duration_ns` is original end minus start; `fully_inside_window` is recomputed with strict kernel interior bounds. |
| `capture.json` | Derived D mode, state and row counts, relative window bounds and duration, worker counts, duration sums and checksum-sequence hashes, and the checked one-shot/device receipts. No absolute worker timestamps. |
| `validator-report.json` | Offline ticket validator rerun against the projected APSC status and byte-exact event streams. Its status-input SHA-256 therefore names the projected status, while the receipt separately pins the private validator report and raw input hashes. |
| `environment.json` | Whitelisted endpoint context: AC/brightness gate, CPU/idle/policy settings, battery and thermal readings, aggregate network traffic, network/USB counts and endpoint equality. Interface names, addresses and device identities are removed. |
| `timeline.json` | Selected successful acquisition actions and worker exit statuses only; monotonic times are relative to the D window start. The complete timeline remains private. |
| `publication-receipt.json` | SHA-256 of the sealed D and preceding A private manifests, qualified build and source/receipt hashes, and each public data artifact's hash with its private input hashes. |
| `MANIFEST.sha256` | SHA-256 over the 15 staged public data files, including the publication receipt. This README is repository documentation outside that staged data manifest. |

Run `sha256sum -c MANIFEST.sha256` from this directory to check the published
bytes. Then run
`python3 -B ../../abi3-acquisition/publish_abi3_d.py --verify-public-stage .`
to replay the public status/stream checks, ticket validator, window and
worker summaries without the private packets. That replay checks zero
stream loss, contiguous per-cluster tickets, 1,873 WFI slots with empty
command values, all 200 worker rows per CPU and 196 strictly interior rows
per CPU. `capture.json` gives window bounds relative to the scheduled worker
start; a worker row is interior exactly when
`window_start < relative_start_ns` and
`relative_start_ns + duration_ns < window_stop`. Hash the ASCII sequence
`pulse:checksum\n` in pulse order to rederive each checksum-sequence hash.

The receipt binds this projection to the sealed 64-file D manifest and its
separate A predecessor. Public readers can rehash and replay the numerical
packet and compare its qualified build hashes with the
[linked-build packet](../../abi3-prototype/README.md) and
[deployment receipt](../../abi3-deployment-receipt.json). Rechecking the
actual boot, operator device report, complete source/EFI chain and full
timeline requires the sealed private packets. Boot identifiers, account
paths, full configuration and logs, boot arguments, FDT, network/USB
identities, operator receipt text and absolute timestamps are withheld.

The ticket order constrains recorded **software idle hooks**. D's WFI probe
did not read the command register; ordinary DVFS-path command values cannot
be substituted. `busy_rows=0` and `candidate_count=0` in this ticket-only
mode are not evidence that the command was clear at a WFI probe. The
`t0`/`t1` bracket includes instrumentation work and ends before the later
executed WFI; it does not isolate observer overhead. Neither this packet nor
its comparison with the unarmed A boot establishes BUSY at WFI, physical
sleep, cluster power, energy, wake behavior or a Linux idle-policy benefit.
