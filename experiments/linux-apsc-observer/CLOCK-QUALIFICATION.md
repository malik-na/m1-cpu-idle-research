# Qualifying cross-CPU physical-counter comparisons

This is a **proposed native test**, not a measurement or an implemented kernel
helper. No clock qualification has run on this Mac. The [observer](README.md)
uses physical-counter readings on different CPUs, so a candidate software
final-entrant analysis must state its cross-CPU clock assumption. A user-supplied
`pairwise-clock-error-ticks` value is an assumption, not proof that the clocks
meet it. Run the protocol below only in the separately authorized native Linux
session described by [NATIVE-RUN](NATIVE-RUN.md).

The question is falsifiable: under the identified boot and test conditions, do
causally ordered, cross-CPU exchanges constrain relative counter offsets tightly
enough for the proposed event comparisons? Missing CPUs, inconsistent intervals,
counter reversals, or intervals too wide to decide the event order are useful
failure results. Passing finite exchanges supports an explicitly conditional
comparison; it does not establish a hardware-guaranteed maximum skew throughout
an unobserved interval or across another boot.

## Why the first helper belongs in the kernel

At the pinned Asahi source revision
[`77cb8f24c2381a8abb7272d7bbdec548d6426a8a`](https://github.com/AsahiLinux/linux/tree/77cb8f24c2381a8abb7272d7bbdec548d6426a8a),
timer initialization clears user access to the physical counter and only
conditionally re-enables user access to the virtual counter. The physical-access
flag is bit 0 of `CNTKCTL_EL1`. Thus a macOS EL0 experiment that successfully
reads `CNTPCT_EL0` does not establish Linux EL0 permission. Do not change
`CNTKCTL_EL1`, substitute `clock_gettime()`, or silently use `CNTVCT_EL0` to
qualify the observer's physical-counter stream. Read from a small kernel helper
and record the actual per-CPU timer access state.
[Timer user-access setup](https://github.com/AsahiLinux/linux/blob/77cb8f24c2381a8abb7272d7bbdec548d6426a8a/drivers/clocksource/arm_arch_timer.c#L782-L805),
[access-bit definitions](https://github.com/AsahiLinux/linux/blob/77cb8f24c2381a8abb7272d7bbdec548d6426a8a/include/clocksource/arm_arch_timer.h#L54-L60).

Use a separate default-off, built-in diagnostic control path, with preallocated
normal-memory storage and deferred export. Its implementation and native
configuration need their own build/disassembly review. It must not read or write
APSC/PMGR registers, change a governor or idle setting, or modify the observer's
hooks. Its supported SMP calls will wake CPUs and add traffic; this is a
qualification phase **outside** the idle capture and energy measurement, not a
neutral background observer.

## An auditable four-timestamp exchange

The kernel's `smp_call_function_single(target, callback, payload, true)` waits for
the target callback to complete. The target invokes a synchronous callback before
release-unlocking its call record, and the sender waits with acquire ordering.
The callback must be fast and nonblocking. Invoke it from task context with
interrupts enabled. The API pins the caller internally but unpins before
returning; the diagnostic therefore needs an **outer** `get_cpu()` / `put_cpu()`
pair spanning both source timestamps. Otherwise the return timestamp could be
read after a migration.
[SMP API and restrictions](https://github.com/AsahiLinux/linux/blob/77cb8f24c2381a8abb7272d7bbdec548d6426a8a/kernel/smp.c#L662-L728),
[callback and completion](https://github.com/AsahiLinux/linux/blob/77cb8f24c2381a8abb7272d7bbdec548d6426a8a/kernel/smp.c#L563-L582),
[completion acquire](https://github.com/AsahiLinux/linux/blob/77cb8f24c2381a8abb7272d7bbdec548d6426a8a/kernel/smp.c#L350-L355).

One round has this causal sequence, using one payload and no concurrent reuse:

1. On source A, pin the task, verify its logical CPU, and read `a0`. Publish
   the unique request sequence with `smp_store_release`, then make the
   synchronous SMP call to B.
2. B checks that sequence with `smp_load_acquire`, records its actual logical
   CPU, and reads `b0` and then `b1`. It saves both readings and status in the
   preallocated payload, publishes the matching acknowledgment sequence with
   `smp_store_release`, and returns. No allocation, sleep, printing, nested SMP
   call, or deliberate wait belongs in this callback.
3. After successful completion, A checks the acknowledgment with
   `smp_load_acquire`, reads `a1`, records its CPU again, and unpins. It may
   reschedule between rounds. A failed call or mismatched identity/sequence is
   a failed round, never a zero-offset sample.

The request and acknowledgment make the particular shared-memory exchange
auditable. They supplement the SMP API's completion contract; a pair of nearby
timestamps on unrelated CPUs is not a substitute for a causal exchange.

Ordinary release/acquire annotations do not by themselves make a system-register
read behave like a memory load. The raw `arch_timer_read_cntpct_el0()` used by
the observer contains `ISB; MRS CNTPCT_EL0`, or the ECV alternative, without
`arch_counter_enforce_ordering()`. The higher-level physical-counter helpers
explicitly add that operation. For this diagnostic, use a conservatively ordered
stamp such as the following **implementation sketch**, and review the emitted
instructions on the actual configuration:

```c
static notrace u64 qualification_tick(void)
{
        u64 v;

        mb();
        v = arch_timer_read_cntpct_el0();
        arch_counter_enforce_ordering(v);
        mb();
        return v;
}
```

At this source pin, `mb()` maps to a memory-clobbered `DSB SY`.
`arch_counter_enforce_ordering(v)` inserts a counter-dependent stack load so
subsequent memory barriers order the counter read. The surrounding barriers
establish the intended memory/message boundaries; do not credit an `ISB` alone
with completing prior ordinary-memory accesses. This extra ordering is local to
the qualification helper. It intentionally widens the exchange and is not a
measurement of the observer's accessor cost. The raw helper matches the
observer's selected counter, but bypasses the stable helper's optional erratum
dispatch; record the target's timer workaround configuration and fail qualification
if that raw read is unsuitable for it.
[Raw and higher-level counter helpers](https://github.com/AsahiLinux/linux/blob/77cb8f24c2381a8abb7272d7bbdec548d6426a8a/arch/arm64/include/asm/arch_timer.h#L65-L92),
[stable/ordered physical reads](https://github.com/AsahiLinux/linux/blob/77cb8f24c2381a8abb7272d7bbdec548d6426a8a/arch/arm64/include/asm/arch_timer.h#L170-L189),
[barrier and counter-dependency implementation](https://github.com/AsahiLinux/linux/blob/77cb8f24c2381a8abb7272d7bbdec548d6426a8a/arch/arm64/include/asm/barrier.h#L27-L29),
[DSB mapping](https://github.com/AsahiLinux/linux/blob/77cb8f24c2381a8abb7272d7bbdec548d6426a8a/arch/arm64/include/asm/barrier.h#L63-L65),
[counter-ordering contract](https://github.com/AsahiLinux/linux/blob/77cb8f24c2381a8abb7272d7bbdec548d6426a8a/arch/arm64/include/asm/barrier.h#L108-L124),
[generic `mb()` mapping](https://github.com/AsahiLinux/linux/blob/77cb8f24c2381a8abb7272d7bbdec548d6426a8a/include/asm-generic/barrier.h#L29-L31).

## What the four readings bound

For one exchange, assume equal effective counter rates and a constant offset
over that exchange. Write the readings as `A(t) = t + oA` and
`B(t) = t + oB`, in counter ticks, with `delta = oB - oA`. The causal chain is
`a0 -> b0 -> b1 -> a1`. Nonnegative forward and return delays imply:

```text
lower = b1 - a1
upper = b0 - a0
lower <= delta <= upper

interval_width = upper - lower
               = (a1 - a0) - (b1 - b0)
```

Use signed, sufficiently wide arithmetic for the differences. Preserve raw
unsigned readings; reject local reversal/wrap in this short experiment instead
of hiding it with modular subtraction. Add any justified quantization or
read-order uncertainty to the endpoints explicitly and retain the unexpanded
interval as well.

The interval width includes IPI delivery, dispatch, barriers, interrupts and
other elapsed work. It is **not** the clock skew, and half the round-trip time
is not a justified point estimate unless a separate delay-symmetry assumption is
made. The protocol does not need symmetry. Intersecting successive intervals can
tighten them only under the stronger assumption that the same offset holds for
the whole batch. An empty intersection falsifies that model or the acquisition
contract; do not discard the inconvenient rounds to create a pass. A wider
envelope preserves inconsistent or drifting results but cannot repair their
interpretation.

For a predeclared absolute pairwise tolerance `E`, a complete offset interval
inside `[-E, E]` constrains that exchange under the stated model. An interval
disjoint from `[-E, E]` contradicts the tolerance; a partly overlapping interval
is inconclusive. Selecting `E` from the largest observed difference and calling
it a guaranteed bound is invalid. Deriving a rate/drift estimate from separated
batches is also empirical: scheduler and communication uncertainty remain, and
finite before/after readings cannot exclude a transient offset excursion during
idle. Report event classifications as conditional on the chosen `E`, its
provenance, and any separately justified drift margin.

## Cover all eight CPUs, then bracket the capture

The smallest pass is a star: choose one online reference CPU from the booted
topology and perform 256 exchanges with each of the other seven CPUs, in a
predeclared interleaved order. Pin a normal-priority kernel worker to the
reference and retain the outer per-round pin described above. The control task
holds `cpus_read_lock()` from preparation through worker completion, acquired
before any preemption-disabled section. Require exactly the observer's eight
online CPUs, derive E/P membership from the same booted topology, and record it;
do not assume a logical CPU number identifies a particular cluster.

Store at most 1792 records per star phase, plus bounded metadata/error records.
Run a phase before the capture, let the stated warm-up/settling criterion be
met, then run another only after capture/drain completes. Retain both phases,
their gap to the capture, and the same boot identity. Keep the helper inactive
during A/B/C windows. An optional stronger coverage pass runs all 56 directed
pairs, 256 rounds each, for 14336 records per phase; give it a separate capacity
and cost declaration. Reverse directions test a different acquisition route,
not an assumption that the network delay is symmetric.

Star results bound non-reference pairs only conditionally. If each offset
relative to reference R is constrained to `[Li, Ui]`, the inferred offset of
j relative to i lies in `[Lj - Ui, Uj - Li]`, with R's interval `[0, 0]`.
These derived intervals can be much wider than the direct star intervals.
Their use across different rounds also assumes offsets remained stable over
those rounds. All-pair exchanges can test that consistency more directly;
neither pattern proves an unsampled idle interval stayed within the envelope.

Bound storage and attempted rounds, stop on a failed exchange or exhausted
capacity, and report attempted/completed/error counts. The synchronous SMP API
waits for completion without a timeout return, so these limits are **not a
hard wall-clock bound**. A long completed round can fail a predeclared latency
criterion; it cannot retroactively guarantee that a hung target would have
returned. Keep callback work short, use the established fallback/watchdog
arrangement, and do not implement timeout-and-free of a payload that a remote
CPU might still access. [Synchronous wait path](https://github.com/AsahiLinux/linux/blob/77cb8f24c2381a8abb7272d7bbdec548d6426a8a/kernel/smp.c#L719-L726).

## Evidence packet and acceptance

Preserve the native run packet from [NATIVE-RUN](NATIVE-RUN.md): exact booted
image/source/configuration, DT and topology, native/guest status, firmware and
bootloader identity, instrumentation revision, and workload/power/thermal state.
Add helper source and object hashes, inspected instruction sequence and runtime
counter alternative/workaround selection, per-CPU `CNTFRQ_EL0` and timer-access
state, reference/pair order, requested/completed rounds, and before/after phase
times. Save raw per-round records with:

```text
phase,round,request_seq,ack_seq,source_requested,source_before,source_after,
target_requested,target_actual,a0,b0,b1,a1,source_cntfrq,target_cntfrq,
call_status,flags
```

Save every error and the complete deferred export with hashes. Retain private
boot identifiers beside the data and publish only reviewed, sanitized provenance
under [PROVENANCE](../../PROVENANCE.md). Exported logical CPU identifiers are
necessary to the experiment; unrelated host identifiers are not.

Fail the proposed cross-CPU qualification on a missing CPU/pair, migration,
request/ack mismatch, counter-frequency disagreement, local reversal, negative
interval width, lost/truncated records, unavailable target identity, changed
boot/topology, or an incompatible timer workaround. Preserve all rounds whose
latency exceeds the predeclared limit, and describe whether the acquisition
failed or the resulting interval was merely too wide. Reject a batch-stable
offset model when its interval intersection is empty. Missing post-phase data
prevents calling the capture bracketed by qualification.

Even a clean result does not automatically validate the observer's MMIO
timestamp ordering, prove actual WFI overlap, or establish a physical power
state. It supplies a separate, reproducible check of cross-CPU counter
comparability for conditional software-timeline inference. No new CPU-idle
policy follows from this check alone.
