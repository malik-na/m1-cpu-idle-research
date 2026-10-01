# PCPM sampler ABI 1

This is a later-native acquisition contract against Asahi Linux commit
`77cb8f24c2381a8abb7272d7bbdec548d6426a8a`. It is not a native capture.
Enable `CONFIG_APPLE_PCPM_SAMPLER=y` explicitly; the default is off. No dependency
select turns it on. The experiment adds no power-state write, runtime-PM reference,
new mapping, or idle/governor change.

## Control and lifetime

Root debugfs directory: `/sys/kernel/debug/t8103_pcpm_sampler`. Files are `control`
(mode 0200), `status` (0400), and `samples` (0400). The control writer also requires
`CAP_SYS_ADMIN`. Write exactly one of:

```
records COUNT PERIOD_MS PHASE_MS
mmio COUNT PERIOD_MS PHASE_MS
```

Use single spaces or single tabs between four tokens; a final newline is allowed.
Numbers are unsigned decimal digits, with no sign. COUNT is 1..1000, PERIOD_MS is
10..1000, PHASE_MS is 0..PERIOD_MS-1, and
`PHASE_MS + COUNT * PERIOD_MS <= 10000`. Product/addition are checked. No default
period is implicit. A first exploratory request can use `mmio 50 100 0` only in an
authorized, qualified native session.

Syntactically invalid input does not consume the one shot. The first valid command
consumes it even if qualification or a read fails; further valid commands return
`-EALREADY`. This is one acquisition per boot, including records mode. Preserve
both exports after a failed write. No retries silently replace failure evidence.
The write waits for the worker and its join; export is deferred until completion.
Neither scheduling nor a potentially stalled MMIO read has a hard realtime bound.

The controller holds the CPU hotplug read lock across topology checks and the
worker lifetime. Eight possible/online logical CPUs numbered 0..7 must describe
four Icestorm and four Firestorm CPUs, independently checked from DT compatible,
boot-cached MIDR model, and MPIDR Aff0/Aff1. Logical E/P numbering is not assumed.
Aff0 must cover 0..3 once per cluster. Aff1 and Aff2 are both 0 for E and
both 1 for P (the pinned P-core DT IDs are `0x10100`..`0x10103`); Aff3 is zero. The first qualified logical E CPU runs a normal-priority, nice-0 kernel
thread, bound before it starts. Qualification reads cached metadata without
remote calls. The sampling loop has no P-core IPI, allocation, printing, remote
streaming, or power reference. E-core wakeups and timer traffic remain observers.

## Mapping qualification

The unique matching `apple,t8103-pmgr` node must be available and must also be `syscon`/`simple-mfd`.
Its first resource must be exactly base `0x23b700000`, size `0x14000`; these are
qualification assertions, not an arbitrary-address interface. The fixed read is
32 bits at offset `0x48`. Reject clocks, resets, hwlocks, big/native endian
properties, or a non-4-byte/malformed `reg-io-width`. The checked T8103 tree is
little endian; explicit little-endian is also compatible.

A configuration-gated syscon accessor searches the existing registry only. It
never registers a map, calls `of_iomap`, attaches a clock, or deasserts a reset.
Missing registration returns `-EPROBE_DEFER`. Externally registered maps and generic
maps with an attached clock return `-EOPNOTSUPP`. A provenance bit is set only on
successful generic, clockless syscon construction; external registrations remain
false. The boot-owned generic registry has no unregister in this pinned source.
Existing map stride and value width must both be 4. Both acquisition modes run the
same qualification, but records mode performs no register read. Runtime changes
to this fixed DT or regmap configuration are outside the qualified experiment.
The sampler neither takes ownership of nor destroys the shared map.

## Schedule and timestamp meaning

`ktime_get_ns()` is the monotonic nanosecond clock for task-context scheduling and
read bracketing. It uses normal timekeeping synchronization; the less expensive
fast accessor does not guarantee monotonicity across timekeeping updates. No
cross-clock equality with the APSC observer's raw counter is asserted here.

Let `P = period_ms * 1000000`, `F = phase_ms * 1000000` and `S = start_ns`.
Nominal slot `i` (zero based) is due at `S + F + (i+1)*P`.
`budget_end_ns = S + F + requested*P` is the **last nominal slot**, not an enforced
execution deadline. `end_ns` can exceed it. Before taking a sample, skip nominal
slots when the worker's scheduling check sees `now >= due+P`, or when
`due < previous t_after_ns + P/2`. Sleep on an absolute pinned monotonic hrtimer
when earlier than the selected due time. This deliberately skips observations
rather than issuing a catch-up polling burst. Actual read brackets have at least
`P/2` separation from previous read end to next read start (minimum 5 ms at the
smallest permitted nominal period). Nominal period is not a minimum actual gap.
A preemption after the scheduling check can make a retained sample still later;
there is no claim that every retained timestamp lies below `due+P`.

Each skipped slot is accounted exactly once. The finite slot loop does at most
COUNT sample attempts and visits at most COUNT slots. A first read error or CPU
identity mismatch stops future samples, retaining the failed row and unattempted
tail. The raw value may still be valid if a CPU mismatch is detected after a
successful read. A successful read establishes only a PMGR-reported word within
its bracket. It does not establish an atomic transition time, rail state, idle
depth, transition count, residency, or energy saving.

## `status`: fixed key=value fields

Decimal numbers are used except the explicitly hexadecimal fields below. Unsigned
timestamps are 64-bit nanoseconds; counts/period/phase are 32-bit. Error is signed
32-bit (0 or a negative kernel errno). Worker CPU is signed (-1 before selection). MIDR/MPIDR exports are unsigned
64-bit cached words; row CPU IDs are unsigned 32-bit. The queried regmap stride
and value-byte fields are signed 32-bit so failed preflight can retain a negative
query result.
No keys are repeated. `unused` emits all counters/times/map fields zero, worker -1,
mode `none`, register_offset 72, and all CPU kinds `unknown`.

| Key | Meaning |
| --- | --- |
| abi | Exactly 1. |
| state | `unused`, `complete`, or `failed`; readers block during capture. |
| mode | `none`, `records`, or `mmio`. |
| error | Terminal acquisition errno; CPU mismatch takes precedence as `-EXDEV`. |
| requested, period_ms, phase_ms | Accepted request, or zero when unused. |
| start_ns, end_ns | Worker start/end. Both zero if preflight/thread creation failed. |
| budget_end_ns | Last nominal slot, as defined above; zero without worker schedule. |
| worker_cpu | Qualified logical E CPU, or -1 before selection. |
| start_online_mask, end_online_mask | Hex low-eight online masks at controller boundaries; successful qualification requires `0xff`. |
| e_mask, p_mask | Hex qualified logical CPU membership. Failed preflight can leave partial metadata. |
| pmgr_phys, pmgr_size | Hex first resource base/size, or zero before resolution. |
| register_offset | Decimal 72 (`0x48`), fixed even when unused. |
| regmap_existing, regmap_internal_clockless | Boolean 0/1 qualification observations, both required for completed capture. |
| regmap_stride, regmap_val_bytes | Existing map query outputs; 4/4 required for completion. |
| attempted | Number of exported sample rows, including a failed row. |
| missed_slots | Sum of all rows' skipped_before plus trailing_missed. |
| unattempted_after_error | Slots not attempted because acquisition failed, including preflight failures. |
| trailing_missed | Skipped slots after the final exported row (or all slots if no rows). |
| read_errors | Number of actual `regmap_read` calls returning nonzero. |
| cpu_errors | Number of rows whose before or after CPU differs from worker_cpu. |
| cpuN.midr, cpuN.mpidr | Hex cached boot identity for each N=0..7; zero before inspected. |
| cpuN.kind | `E`, `P`, or `unknown`; partial metadata is possible on failure. |

For every consumed command:
`requested = attempted + missed_slots + unattempted_after_error`.
A completed capture has no acquisition/read/CPU errors and no unattempted tail,
but can have missed slots, including all slots. Such loss cannot support a
negative-state conclusion. Failed captures retain partial evidence. A read that
never returns also prevents this export; no timeout can make a hung bus safe.

## `samples`: CSV

Exact header:

```
seq,slot,scheduled_ns,skipped_before,t_before_ns,t_after_ns,cpu_before,cpu_after,read_attempted,raw_valid,raw,read_errno
```

`seq` is contiguous 0..attempted-1; `slot` is the original nominal slot. Slot 0 is
not required to survive scheduling. `skipped_before` counts missed slots since the
previous row (or since slot 0 for the first row). `scheduled_ns` preserves the
formula above. `t_before_ns` and `t_after_ns` bracket the optional `regmap_read`;
the CPU IDs are observed immediately outside the bracket. Fields are decimal
except `raw`, which is zero-padded 32-bit hexadecimal when valid and an empty
field otherwise. A raw word of `0x00000000` is valid data when raw_valid=1.

`read_attempted`/`raw_valid` are 0 or 1. Records mode always reports no read, raw
invalid/empty, and read_errno=0. MMIO mode attempts the read only if the first CPU
observation matches worker_cpu. `read_errno` is strictly the regmap return, zero
when no read was attempted. raw_valid=1 iff a read was attempted and returned 0;
otherwise raw stays blank. A CPU error is in the status rather than fabricated as
a register-read errno. The first read error or CPU error ends the capture.

Decode `(raw >> 4) & 15` and `raw & 15` only when raw_valid=1. Keep unknown codes
and the entire word, including sticky bits. No latch is cleared. Counts of sampled
codes are sample counts; they are not durations or physical-state calibration.
