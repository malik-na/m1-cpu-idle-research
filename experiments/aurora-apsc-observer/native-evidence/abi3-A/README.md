# Public ABI 3 unarmed A evidence

This packet supports the [native ABI 3 A baseline result](../../ABI3-A-BASELINE-RESULT.md)
under the [fixed run plan](../../WFI-ABI3-RUN-PLAN.md). A ran the pinned CPU
1/5 workload on the first qualified ABI 3 boot while the APSC observer stayed
`ready` and unarmed. It is an instrument-state and delivered-work baseline
for later fresh-boot D/E controls. It contains no APSC command read or
first-attempt ticket evidence.

An offline publisher checked the sealed private packet's complete
`MANIFEST.sha256`, file modes, source and boot identity chain, operator
first-boot Wi-Fi/visible-brightness receipt, unarmed statuses and empty event
streams, workload schedule and all 200 rows per CPU, endpoint conditions and
absence of a control-write attempt. The publisher replayed the saved worker
summary, wrote a separate reviewed projection, then rechecked that the
private manifest had not changed. The [public collector logic review copy](../../abi3-acquisition/README.md)
describes the one-shot acquisition checks; its redaction receipt binds that
copy to the private executable collector source.

| File | Publication transformation |
| --- | --- |
| `apsc-events.csv.gz`, `apsc-wfi-events.csv.gz` | Deterministic gzip of the byte-exact private CSV streams. Decompressed, each is its original header with zero data rows. |
| `apsc-status-before.txt`, `apsc-status-after.txt` | Original lines and order for retained keys. Physical command-resource addresses are omitted; retained values and the zero loss/commit fields are unchanged. |
| `pcpm-status-before.txt`, `pcpm-status-after.txt`, `counter-status-before.txt`, `counter-status-after.txt` | Original lines and order for retained unused-helper fields. Physical mapping, register, per-CPU identity and unused counter-metadata fields are omitted. |
| `workload-cpu1.csv.gz`, `workload-cpu5.csv.gz` | All 200 rows per CPU, with CPU, pulse, iterations and checksum values retained. `relative_start_ns` is original monotonic start minus the scheduled start; `duration_ns` is original end minus start; `fully_inside_window` is recomputed with strict interior bounds. |
| `baseline.json` | Derived A mode, observer state and row counts, relative window bounds and duration, worker counts, duration sums and checksum-sequence hashes. It contains no absolute worker timestamps. |
| `environment.json` | Whitelisted endpoint context: AC/brightness gate, CPU/idle/policy settings, battery and thermal readings, network traffic totals and counts, and USB count/equality. Interface names, addresses and device identities are removed. Endpoint checks do not describe the whole window. |
| `timeline.json` | Selected acquisition actions and worker exit statuses only; monotonic times are relative to the A window start. The complete timeline remains private. |
| `publication-receipt.json` | SHA-256 of the sealed private manifest, qualified build identity, captured source/receipt hashes, and each public data artifact's hash with its private input hashes. |
| `MANIFEST.sha256` | SHA-256 over the 14 staged public data files, including the publication receipt. This README is repository documentation outside that staged data manifest. |

The public data permit a bounded replay. Run `sha256sum -c MANIFEST.sha256`
in this directory to check the published bytes. For each worker CSV,
`baseline.json` gives the window start and stop relative to the scheduled
start. A row is fully interior exactly when
`window_start < relative_start_ns` and
`relative_start_ns + duration_ns < window_stop`. Sum all durations and the
interior durations, count the 200 rows and 196 interior rows per CPU, and
hash the ASCII sequence `pulse:checksum\n` in pulse order to rederive each
worker aggregate. The two decompressed APSC streams have only headers;
the retained status lines show `state=ready`, zero attempts, commits,
overflow and missing commits, and unused PCPM/counter helpers.

The publication receipt binds this projection to the private 59-file
manifest and names the private input hash for each data artifact. Public
readers can check the public manifest, replay numerical worker summaries,
and compare the published build hashes with the
[linked-build packet](../../abi3-prototype/README.md) and
[deployment receipt](../../abi3-deployment-receipt.json). Rechecking the
full boot, operator device report, complete timeline or private source
chain requires the sealed private packet. Boot ID, account paths, full
configuration and logs, boot arguments, FDT, network/USB identities,
operator receipt text and absolute timestamps are withheld.

The window markers are userspace `CLOCK_MONOTONIC` values. A has no armed
kernel start/stop sentinels or ticket stream. Zero observer rows result from
leaving the observer unarmed; they do not show that CPUs did not idle or
that no command was pending. This packet cannot establish BUSY at an APSC
read, peer sleep at WFI, physical power state, energy or wake behavior.
