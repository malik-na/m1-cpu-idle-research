# Counter qualification capture ABI 1

This is the proposed kernel helper's raw export contract. It does not declare a
counter tolerance qualified. Native execution is deferred to an authorized
Linux session. The patch targets Asahi Linux
`77cb8f24c2381a8abb7272d7bbdec548d6426a8a` and adds the default-off built-in
`CONFIG_APPLE_COUNTER_QUALIFICATION` under `drivers/soc/apple/`. It can coexist
with the independent APSC observer patch without editing its files or hooks.

## Control and lifetime

Debugfs directory: `apple_counter_qualification`.

- `control` is root-write-only (0200). Write `pre <reference_cpu> <rounds>` once,
  with logical reference CPU 0..7 and rounds 1..256. Then, only after the pre
  phase completes successfully and the separate capture has drained, write
  `post`. Post reuses the pre phase's reference and round count. Malformed or
  out-of-order commands are rejected without consuming a phase.
- `status` and `events.csv` are root-read-only (0400). Their readers and the
  control writer share a mutex; export waits until a running phase finishes.
- Valid phase commands are consumed before preparation. A failed phase retains
  its metadata, attempted rows and error, and cannot be repeated in this boot.
  There is no reset, abort, retry or background activity. Both phases stay in
  separate fixed storage until reboot. No record is overwritten.
- A normal-priority kernel worker is bound to the reference CPU. CPU hotplug is
  read-locked for preparation through worker completion. Each round has an
  additional preemption-disabled source section with interrupts enabled, which
  spans both source timestamps and the synchronous SMP call. Callbacks perform
  no allocations, sleeps, nested calls or printing.
- Storage is 1792 records per phase: at most 256 interleaved rounds visiting
  targets in ascending logical CPU order, skipping the reference. The first
  failed round stops that phase and remains an attempted row. Synchronous SMP
  calls have no timeout return; the record bound is not a wall-clock guarantee.
  The task cannot free a payload while a remote callback still uses it. An extra
  task reference is held from before wake until after `kthread_stop()` joins the
  exited worker, as required by the pinned
  [kthread lifetime contract](https://github.com/AsahiLinux/linux/blob/77cb8f24c2381a8abb7272d7bbdec548d6426a8a/kernel/kthread.c#L733-L785).
- The helper does not know when the separate observer is active. The operator
  must keep qualification phases outside observer and energy windows. Merely
  enabling its config causes no SMP exchange; phases require explicit writes.

## Status

UTF-8 `key=value` lines, no duplicate keys, decimal unsigned integers unless
specified. Empty value means unavailable; it must not be interpreted as zero.
Global keys:

| Key | Meaning |
| --- | --- |
| `abi` | `1` |
| `possible_mask` | Hex mask; supported topology is `0xff` |
| `cluster0_cpus`, `cluster1_cpus` | Two disjoint four-CPU hex masks derived from boot DT performance-domain phandles, in first-logical-CPU encounter order; not hard-coded efficiency/performance labels |
| `config_ool_workaround` | Whether `CONFIG_ARM_ARCH_TIMER_OOL_WORKAROUND` was built |
| `ecv_alternative` | System `ARM64_HAS_ECV` capability selecting the raw counter instruction alternative |
| `capacity_per_phase` | `1792` |

For each `P` in `pre`, `post`:

| Key | Meaning |
| --- | --- |
| `P_state` | `unused`, `running`, `complete`, or `failed` |
| `P_reference_cpu` | Requested logical CPU; signed `-1` before phase use |
| `P_rounds` | Requested rounds per target, 0 before use |
| `P_attempted`, `P_completed` | Exported row count and successful row count |
| `P_error` | Signed Linux errno, 0 if no failure has been recorded; state still matters |
| `P_metadata_completed` | Number of metadata callbacks that returned valid register records (even if validation subsequently fails) |
| `P_start_tick`, `P_end_tick` | Ordered physical ticks on the bound reference; empty if unavailable; start is after successful all-CPU metadata preflight, end after rounds |
| `P_start_online_mask`, `P_end_online_mask` | Hex online masks; 0 if not yet captured |

For every `P_cpuN` where N is 0..7:

| Suffix | Meaning |
| --- | --- |
| `_valid` | 0 or 1: metadata callback collected its registers |
| `_actual` | Signed actual CPU, `-1` if callback did not run |
| `_error` | Signed errno including call, identity, frequency, or raw-reader suitability error |
| `_cntfrq` | Raw `CNTFRQ_EL0` via the unsigned 32-bit kernel accessor, decimal; empty if invalid |
| `_cntkctl` | Raw `CNTKCTL_EL1`, hex; empty if invalid |
| `_mmfr0` | Raw `ID_AA64MMFR0_EL1`, hex; empty if invalid; retain for per-CPU ECV interpretation |
| `_workaround_present` | 0/1 per-CPU timer workaround pointer presence; empty if invalid |
| `_phys_read_workaround` | 0/1 active physical-read function in that workaround; empty if invalid |

An active physical-read workaround makes the raw-reader protocol fail closed.
A pointer with only other functions does not by itself make raw CNTPCT reads
incompatible. A zero pointer, particularly with workaround support compiled out,
is not proof that all possible hardware errata are absent. Per-CPU metadata is
collected anew and retained separately in both phases. Post requires the same
frequencies, timer access state, raw MMFR0 and workaround metadata as pre;
changes fail the acquisition rather than silently combining different states.

## CSV

Exact header:

```text
phase,round,request_seq,ack_seq,source_requested,source_before,source_after,target_requested,target_actual,a0,b0,b1,a1,source_cntfrq,target_cntfrq,call_status,flags
```

Rows export pre then post, each in acquisition order. `round` starts at 0. The
unique `request_seq` starts at 1 in pre; post continues immediately after the
number of attempted pre records. `ack_seq` is 0 if no acknowledgment was
published, otherwise the sequence seen and acknowledged by the target.
Requested CPUs are 0..7; actual CPU fields are signed and use `-1` if absent.
Frequencies are unsigned 32-bit decimal and empty if their CPU was not sampled. Timestamps are
raw unsigned 64-bit decimal, empty when their flag is absent. Flags are an
unsigned decimal bitmap:

| Bit value | Meaning |
| --- | --- |
| 1 | `a0` valid |
| 2 | `b0` valid |
| 4 | `b1` valid |
| 8 | `a1` valid |

Successful rows have flags 15, matching request/ack, expected CPU identities,
equal nonzero frequencies, and `call_status=0`. `call_status` is the first
nonzero acquisition/validation error for the round, including an SMP-call return
error, unsuitable reader, CPU mismatch, acknowledgment mismatch, changed
frequency, or local counter reversal. It is not exclusively the API's return
value. Failure rows may still have all four timestamps. Raw values and errors
are retained; `completed` increments only after all round checks succeed.

The helper checks only local ordering `a0 <= a1` and `b0 <= b1`; it never tests
cross-CPU timestamps as if their offset were known. Wide signed interval
arithmetic and causal-model consistency checks belong in the offline decoder.
`a0 -> b0 -> b1 -> a1` relies on the audited SMP call, release/acquire request
and acknowledgment, and ordered stamp implementation; it is not inferred merely
from the printed numeric values. A complete phase means acquisition finished,
not that any pairwise tolerance or stable-offset model passed.

Preserve both files, exact image/config/source/patch hashes, boot identity,
native-versus-guest status, CPU topology, phase/capture timing and declared
uncertainty assumptions. ABI data alone cannot authenticate a common boot or
prove that the observer ran between these phases, and finite pre/post samples
cannot bound an unobserved transient excursion.
