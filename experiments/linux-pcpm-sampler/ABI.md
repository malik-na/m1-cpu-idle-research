# PCPM sampler ABI 2

This is a later-native acquisition contract against Asahi Linux commit
`77cb8f24c2381a8abb7272d7bbdec548d6426a8a`. It is not a native capture.
Enable `CONFIG_APPLE_PCPM_SAMPLER=y` explicitly; the default is off. No dependency
select turns it on. The experiment adds no power-state write, runtime-PM reference,
new mapping, or idle/governor change.

ABI 2 adds raw physical-counter brackets without changing nanosecond scheduling.
[ABI 1](https://github.com/malik-na/m1-cpu-idle-research/blob/cb0b41e62ad500225c1a06bfc827b2fd8e24b1ec/experiments/linux-pcpm-sampler/ABI.md)
remains a distinct historical format: its nanosecond timestamps are not raw
counter ticks. A decoder must dispatch on `abi` and reject unknown versions;
never reinterpret ABI 1 as counter-qualified ABI 2.

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

Among `apple,t8103-pmgr` nodes, exactly one must have first resource base
`0x23b700000`, size `0x14000`; that node must be available and must also be
`syscon`/`simple-mfd`. T8103's `pmgr_mini` is another node with the same
compatible but a different resource, so it is not an ambiguity. Duplicate
nodes with the expected resource are rejected. The expected address and size are
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

Before starting the schedule, the bound worker records its actual CPU and raw
`CNTFRQ_EL0`, `CNTKCTL_EL1`, `ID_AA64MMFR0_EL1`, and the presence of an out-of-line
counter workaround and its physical-read callback. It rejects the wrong worker
CPU with `-EXDEV`, zero frequency with `-ERANGE`, or a physical-read workaround
with `-EOPNOTSUPP`, before any counter stamp or PMGR read. If zero frequency and
a physical workaround coexist, `-ERANGE` takes precedence. This metadata gate
runs in records mode too. Global `CONFIG_ARM_ARCH_TIMER_OOL_WORKAROUND` and the
final `ARM64_HAS_ECV` alternative decision are always exported. No remote CPU is
called. Metadata validity denotes collection, not reader suitability.

Every row with a matching initial worker CPU has this nested sequence:

```
CPU-before
counter-before: mb(); arch_timer_read_cntpct_el0(); arch_counter_enforce_ordering(); mb()
ktime-before
optional regmap_read
ktime-after
counter-after:  mb(); arch_timer_read_cntpct_el0(); arch_counter_enforce_ordering(); mb()
CPU-after
```

The accessor is the same raw physical counter accessor as the separate
[counter qualification helper](../linux-counter-qualification/ABI.md). Its ECV
alternative can select the self-synchronized physical register; these exports
are physical-counter ticks, not nanoseconds. `CNTFRQ` is retained metadata, not
permission to infer a cross-clock conversion or cross-CPU equality. Joint
interpretation with P-core observer intervals needs separately justified
cross-CPU error bounds over the actual capture, matching reader/target metadata,
and complete event coverage. Nearby qualification exchanges alone do not prove
an intervening bound. The barriers and counter reads add observation cost in
both records and MMIO modes, so ABI 1 and ABI 2 baselines are not interchangeable.
Metadata is a worker preflight snapshot, not a per-sample requalification or a
proof that firmware/hypervisor counter behavior stays invariant.

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
COUNT sample attempts and visits at most COUNT slots. A first read error, CPU
identity mismatch, or flagged time/counter reversal stops future samples,
retaining the failed row and unattempted tail. The raw value may still be valid
if a CPU mismatch is detected after a successful read. A successful read establishes only a PMGR-reported word within
its bracket. It does not establish an atomic transition time, rail state, idle
depth, transition count, residency, or energy saving.

## `status`: fixed key=value fields

Decimal numbers are used except the explicitly hexadecimal fields below. Unsigned
nanosecond timestamps and raw counter ticks are separate unsigned 64-bit fields;
counts/period/phase are 32-bit. Error is signed
32-bit (0 or a negative kernel errno). Worker CPU is signed (-1 before selection). MIDR/MPIDR exports are unsigned
64-bit cached words; row CPU IDs are unsigned 32-bit. The queried regmap stride
and value-byte fields are signed 32-bit so failed preflight can retain a negative
query result.
No keys are repeated. `unused` emits all acquisition counters/times/map fields zero, worker -1,
mode `none`, register_offset 72, and all CPU kinds `unknown`. Counter metadata
is invalid, its observed CPU is -1, its error is 0, and its optional values are
blank. The two global counter configuration fields still describe the kernel.

| Key | Meaning |
| --- | --- |
| abi | Exactly 2. |
| state | `unused`, `complete`, or `failed`; readers block during capture. |
| mode | `none`, `records`, or `mmio`. |
| error | Terminal acquisition errno; row precedence is CPU mismatch `-EXDEV`, then real read errno, then time/counter reversal `-ERANGE`. |
| requested, period_ms, phase_ms | Accepted request, or zero when unused. |
| start_ns, end_ns | Worker schedule start/end. Both zero if preflight, thread creation, or worker counter-metadata qualification failed. |
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
| counter_errors | Rows with at least one counter reversal (`counter_flags & 0x0c`), not number of flags. |
| time_errors | Rows with at least one monotonic-nanosecond reversal (`counter_flags & 0x30`). |
| config_ool_workaround | Boolean kernel configuration value; always present. |
| ecv_alternative | Boolean final `ARM64_HAS_ECV` decision; always present. |
| counter_metadata_valid | Boolean; all five optional counter metadata values below are present iff 1. |
| counter_metadata_cpu | Actual worker CPU observed at metadata qualification; -1 before worker. A mismatched CPU is retained with invalid metadata. |
| counter_metadata_error | Metadata-gate errno: 0 before attempted/success, `-EXDEV` for wrong CPU, `-ERANGE` for zero frequency, `-EOPNOTSUPP` for physical-read workaround. |
| counter_cntfrq | Raw architectural frequency, unsigned 32-bit decimal, or blank. |
| counter_cntkctl, counter_mmfr0 | Raw unsigned 64-bit system-register words in hex, or blank. |
| counter_workaround_present | Per-CPU OOL workaround pointer was present; Boolean or blank. When OOL config is 0 this is 0 on valid metadata. |
| counter_phys_read_workaround | The workaround had a physical-counter-read callback; Boolean or blank. 1 implies workaround_present=1 and acquisition fails before all stamps/reads. |
| cpuN.midr, cpuN.mpidr | Hex cached boot identity for each N=0..7; zero before inspected. |
| cpuN.kind | `E`, `P`, or `unknown`; partial metadata is possible on failure. |

For every consumed command:
`requested = attempted + missed_slots + unattempted_after_error`.
A completed capture has valid, successful counter metadata, no
acquisition/read/CPU/counter/time errors and no unattempted tail,
but can have missed slots, including all slots. Such loss cannot support a
negative-state conclusion. Failed captures retain partial evidence. A read that
never returns also prevents this export; no timeout can make a hung bus safe.

## `samples`: CSV

Exact header:

```
seq,slot,scheduled_ns,skipped_before,t_before_ns,t_after_ns,counter_before,counter_after,counter_flags,cpu_before,cpu_after,read_attempted,raw_valid,raw,read_errno
```

`seq` is contiguous 0..attempted-1; `slot` is the original nominal slot. Slot 0 is
not required to survive scheduling. `skipped_before` counts missed slots since the
previous row (or since slot 0 for the first row). `scheduled_ns` preserves the
formula above. `t_before_ns` and `t_after_ns` bracket the optional `regmap_read`;
the CPU IDs are observed outside the enclosing counter bracket. Fields are decimal
except `raw`, which is zero-padded 32-bit hexadecimal when valid and an empty
field otherwise. A raw word of `0x00000000` is valid data when raw_valid=1.

`read_attempted`/`raw_valid` are 0 or 1. Records mode always reports no read, raw
invalid/empty, and read_errno=0. MMIO mode attempts the read only if the first CPU
observation matches worker_cpu and no comparison with the previous row has
already found a backward counter or nanosecond timestamp. `read_errno` is strictly
the regmap return, zero when no read was attempted. raw_valid=1 iff a read was attempted and returned 0;
otherwise raw stays blank. A CPU error is in the status rather than fabricated as
a register-read errno. The first read error, CPU error, or flagged counter/time
reversal ends the capture.

Decode `(raw >> 4) & 15` and `raw & 15` only when raw_valid=1. Keep unknown codes
and the entire word, including sticky bits. No latch is cleared. Counts of sampled
codes are sample counts; they are not durations or physical-state calibration.

## ABI 2 counter values and flags

`counter_before` and `counter_after` are unsigned 64-bit raw counter values in
decimal, or blank when the corresponding validity bit is clear. A zero value
with validity set is data; unavailable is never encoded as zero. `counter_flags`
is an unsigned 32-bit decimal mask with no bits beyond `0x3f`:

| Bit | Name | Exact meaning |
| --- | --- | --- |
| 0 (`0x01`) | BEFORE_VALID | `counter_before` was read. |
| 1 (`0x02`) | AFTER_VALID | `counter_after` was read. |
| 2 (`0x04`) | COUNTER_REVERSE | Both valid and `counter_after < counter_before`. |
| 3 (`0x08`) | COUNTER_PREVIOUS_REVERSE | Before valid and `counter_before < previous row counter_after`. Never set for row 0. |
| 4 (`0x10`) | TIME_REVERSE | `t_after_ns < t_before_ns`. |
| 5 (`0x20`) | TIME_PREVIOUS_REVERSE | `t_before_ns < previous row t_after_ns`. Never set for row 0. |

Both validity bits are set exactly when `cpu_before == worker_cpu`; otherwise
both counter fields are blank. Nanosecond observations and their reversal checks
still occur on a row whose initial CPU mismatches. A later CPU mismatch does not
erase the two actual counter values or a successful register value: it makes the
row unsuitable for qualified ordering. The normal thread binding and held CPU
hotplug lock are required independently of these diagnostic observations.

Previous-row comparisons use the immediately preceding attempted row. Such a
prior row cannot already contain an acquisition error because the first error
stops the loop. Bits 3 and 5 are known before the optional read, so either one
suppresses that read in MMIO mode (`read_attempted=0`, `read_errno=0`, blank raw).
Bits 2 and 4 can be known only after the bracket; they preserve a read already
performed. Counter and nanosecond reversals are strict decreases, not equality;
no wrap correction, clock-frequency conversion, inferred offset, or automatic
cross-CPU bound is applied. Raw words in a failed capture remain evidence of
what was returned, with ordering/calibration usability reported separately.
