# T8103 `LAST_CHG_TIME` calibration helper prototype (disabled)

**Status (2026-10-04): built offline, never loaded or run.** `lct_probe.c` is
an out-of-tree module prototype for the retained ABI3 build. Its shipped
constants set `LCT_REVIEWED_WIDTH_BITS=0`, `LCT_READ_SAFETY_PROVEN=0`, and
`LCT_COMMAND_ONLY_REVIEWED=0`.
The default object retains inline code for the known-register command read,
but its sample path is unreachable at runtime: the disabled build never maps
the resource or registers the probe, and `hardware_ready` remains false.
The `+0x38` read function returns `-EOPNOTSUPP` in this build. Even
`allow_mmio=1` cannot start a sample. It is not an instruction-
boundary observer and supplies no #5 result by itself.

## Pinned provenance and boot gate

The private reference source and build are identified by the public
[ABI 3 linked-build receipt](../abi3-prototype/linked-build-receipt.json). That receipt names release
`7.1.12-ARCH-apsc-20261002-wfi-pcpm-abi3`, vmlinux Build-ID
`6fbc0dc67bb746466a7244ba2fc096ecae7e6476`, image SHA-256
`1368f40aed236c770485eb8b1b2b0b0bc496915c21fc01fbf608f5f60243a537`,
source-tree digest `e703916291104ece7de51f24ecdd042fa8ac01463448ebeb1c337b85f647f462`,
and configuration SHA-256
`f4df15bf0c94e82210a503c91a9dd408b848d98aed45b0a2a09d691efbcf70a5`.
The source files this prototype depends on hash to:

| File in pinned source | SHA-256 |
|---|---|
| `drivers/cpufreq/apple-soc-cpufreq.c` | `0c0e5606d3274110d2833f60d51e1486e82b333247890e3cee3655ed20d24653` |
| `drivers/cpuidle/apple-apsc-observer.c` | `6939e428f19f1f8af0f4124d68d091995d6af507f6eb293f1e1c78bea3c2d505` |
| `include/linux/soc/apple/apsc-observer.h` | `94f186c572f3e1df7a62a7530981b39ee10359af7f5ec23457cf720a754ef1a5` |

Before any future load, rerun the retained private read-only preflight and independently check
the running Build-ID, release, config, source and module hashes against a new
signed-off build receipt. `vermagic` alone does not establish source-to-binary
identity. The module's own enable path also checks exact release, T8103
compatibility, eight online CPUs, each CPU's performance-domain phandle,
`apple,t8103-cluster-cpufreq`, exact E/P resource starts
`0x210e20000`/`0x211e20000`, minimum span through `+0x50`, and the four-CPU
cpufreq policy masks. At sample time the helper holds the CPU-hotplug read
lock across the entire bounded loop and checks all eight online CPUs and
both exact policy masks before and after sampling. A pre-sample mismatch
aborts before a register read; a post-sample mismatch invalidates the trial.
Any mismatch aborts or invalidates the trial. Keep stock
and working research Limine entries available.
Mapping setup resets its error state before checking **each** CPU, so a
missing later CPU node or phandle cannot inherit a prior success; it also
requires both cluster mappings to exist before returning success.

## Width and read-safety decision, currently **NO-GO**

The pinned cpufreq source defines `APPLE_DVFS_LAST_CHG_TIME` as `+0x38` with
only “Same timebase as CPU counter (24MHz).” It does not read this register or
specify width, atomicity, reset/wrap, update edge, BUSY relationship, or
read side effects. The adjacent command read is 64-bit and status read is
32-bit; neither selects the width of `+0x38`. A timebase match does not prove
an epoch or completion invariant. Do **not** choose 32 or 64 by trial read.

An independent register contract or equally strong hardware-specific evidence
must justify both (1) a 32/64-bit access width and (2) that a read is safe and
side-effect-free on this T8103 revision. Record its exact source/revision and
review in the eventual private build receipt. Only then may a new reviewed
build change both compile-time gates. That build also requires deliberate
`allow_mmio=1` at module load. The read routine has no fallback width. An
access fault may halt the kernel before an error can be recorded; a later
stop rule cannot make an unqualified first read safe.

## Prototype acquisition path, if the gates are ever qualified

The module maps only the two DT-declared cpufreq resources. Its only MMIO
operations are ordered reads: existing `+0x20` command (`readq`), the
reviewed-width `+0x38` timestamp, and existing `+0x50` status (`readl`). It
issues **no** MMIO write, does not change the idle callback or WFI, and adds
no wait there. Each of the three reads has its own before/after ordered
`CNTPCT_EL0` stamps. The counter routine uses the same `mb()` +
`arch_timer_read_cntpct_el0()` + `arch_counter_enforce_ordering()` + `mb()`
form as the retained counter-qualification helper. A sample runs pinned to
one CPU for at most 64 triplets, with a fixed 2 µs gap, once per cluster per
module load. The debugfs `sample` write can only shorten that count, not
increase it. The 64 triplets are a *cap*, not a promise that BUSY will be
observed.
Every valid row must satisfy the exact field order
`command.t0 ≤ command.t1 ≤ last.t0 ≤ last.t1 ≤ status.t0 ≤ status.t1` in
timestamp mode, or `command.t0 ≤ command.t1 ≤ status.t0 ≤ status.t1` in
command-only mode. The first command stamp must follow the sample-window
start, each later row must follow the preceding status stamp, and every
status stamp must precede the stop marker. The helper also verifies the
24 MHz counter frequency on the sampling CPU at both ends. Any regression
sets a row error or a window-level invalid flag; no value is silently
reordered or treated as a valid update edge.

A kretprobe on the verified ABI3 symbol
`apple_apsc_observer_dvfs_write` brackets each call that submits the normal
driver SET. Its ARM64 entry arguments record **entry CPU**, target policy CPU,
request index/P-state, pre-command and submitted command; its return stamp
and **return CPU** complete the bracket. Neither CPU is guaranteed to be the
CPU executing the store: the wrapper disables preemption only after function
entry and reenables it before return. The pinned cpufreq source routes its usual `writeq` via
this symbol. It is the **existing driver's** SET, not a helper register write.
The bracket contains the SET but is wider than the exact store. Samples and
SET records are sequence-numbered and published with release/acquire; the
fixed 2048-SET buffer, kretprobe `nmissed`, and uncommitted slots are exposed
as invalidating loss conditions. Its ticket allocator saturates at 2048;
callbacks beyond that set an overflow latch without advancing or wrapping
the signed index, and no slot is overwritten. All **probed** driver SETs from every CPU are
recorded during the sample window, including background governors and cross-cluster
writers. A same-CPU stream would miss legal cross-CPU writes. The probe records
every call **from registration onward**, even before a sample starts, so a
call that entered before the sample and writes during it remains in the ring.
The sample refuses to start with an outstanding probed call and publishes
start/stop ticks plus SET sequence counts. This removes the entry-side
`capture_active` race from the prototype. A call that entered **before
kretprobe registration** could still be preempted before its store and escape
the ring. No finite quiet wait proves otherwise. The status therefore always
reports `pre_registration_coverage_unknown=1` and
`actual_writer_cpu_qualified=0`. Complete Linux SET coverage and exact writer
CPU would require instrumentation at the actual store in a new kernel image,
active from boot, or a separately proved quiescence boundary. Before enabling
the helper, inspect the linked call site and function entry to confirm the
six ARM64 arguments are still live in `x0`–`x5` at the kretprobe entry;
`vermagic` alone does not prove that calling-convention assumption.

The module does not prove that firmware or an unrelated kernel writer cannot
touch the controller. Review the source and boot configuration for alternate
paths; retain an explicit `unknown_writer_possible` field in the acquisition
record. Without an independently justified whole-controller writer bound,
classify any apparent update edge as provisional. A kretprobe registration
failure, symbol mismatch, return loss, buffer overflow, missing commit,
unexpected policy/DT, counter regression, read error, or changed boot identity
invalidates the trial. A bus fault may preempt recording entirely.

The 2048-entry SET ring is bounded but **not self-resetting**. For a future
qualified run, load the module immediately before the trials, reject any
pre-sample overflow or probe miss, run at most one sample per cluster, then
write the separate `seal` control promptly. `seal` unregisters the kretprobe,
checks remaining in-flight/missed/overflow state, and freezes the private CSV
exports; `samples.csv` and `sets.csv` return `-EAGAIN` before sealing. If the
ring fills before or between samples, preserve its rows and classify the run
invalid; never wrap, overwrite, or silently reset. The overflow latch records
that at least one callback was dropped, not the number of dropped callbacks.
If `set_inflight` remains
after unregister, preserve an invalid status and treat any incomplete bracket
as loss. The module currently lacks an automatic lifetime deadline, so this
seal protocol is mandatory for a bounded deployment and must be strengthened
before live use if unattended execution is possible.

## Separate known-register route

The current ABI3 image already uses 64-bit reads of `+0x20` command, and its
cpufreq driver uses 32-bit reads of `+0x50` status. A **separate** command-only
build and protocol could sample only those two registers to calibrate BUSY
transition durations and Linux SET bracketing on the current boot. The
dormant `LCT_COMMAND_ONLY_REVIEWED` branch is mutually exclusive with the
`+0x38` build gates; it skips the timestamp read and marks `last_valid=0`.
All three gates are zero in the shipped object. Before any command-only load,
review its distinct build, verify live boot/source/DT identity, choose a
low-disturbance bounded schedule, and synchronize ordinary cpufreq requests
with the sample. The current short synchronous loop may miss transitions and
needs a trial journal plus a no-read timing control before quantitative use.
Its pre-registration gap and unknown actual writer CPU prevent complete
writer attribution. It could reveal local BUSY episodes or falsify a proposed
timing bound, but it cannot establish a `+0x38` completion invariant or BUSY
at the WFI instruction.

## Controlled trials and falsification

The sampler runs only when the operator intentionally schedules it alongside
ordinary Linux cpufreq requests; those requests must be journaled separately
with policy, requested frequency, governor/policy state, start/end, outcome,
and whether they reached an actual driver SET. Since the sampling interval is
short and scheduling is nondeterministic, a trial with no overlapping verified
SET is a no-SET control, not an update-edge test. Do not label a request
suppressed by the cpufreq core a same-pstate hardware SET. Require a distinct
settled P-state transition on **each** cluster, a quiet no-SET interval, and
same-P-state requests only if the trace proves the driver emitted a SET.
Retain misses and ambiguous runs rather than repeating until a favorable
sequence appears. A slower separate read-rate control can estimate observer
disturbance; it cannot retroactively correct the target trial.

For every raw row retain the register value, chosen width, cluster/CPU,
command BUSY bit, status current/target fields, all six counter bounds,
relative phase to each verified SET bracket, return/error and committed
flags. Also retain the full SET stream, trial markers, counter frequency,
start/end kretprobe miss counts, buffer losses, sample cap, policy state,
boot/build receipt and user request journal. `samples.csv`, `sets.csv` and
`status` are private raw exports; sanitize them before repository publication.
Reject an update-edge attribution when a second verified SET, possible
unobserved writer, lost record, or overlapping read bracket permits another
explanation. Test competing models: update at SET, BUSY assertion, BUSY
clear, settled P-state, no-SET autonomous change, or no repeatable relation.
Test modulo width and one fixed offset to the physical counter; don't infer
either from the 24 MHz comment. Distinct changes within one 24 MHz tick may
alias and must be counted as unresolved.

Even a clean finite calibration only gives a local empirical relationship.
It does not prove that every command completes with one timestamp update or
that BUSY never clears and reasserts between reads. Bridging a future
pre-DSB BUSY sample to actual WFI would additionally require the **same
outstanding command**, a completion bound later than a verified WFI
instruction/return bound, all intervening writers accounted, and a proven
clock relationship. This prototype alone cannot close issue #5 or establish
physical peer sleep, cluster power, energy, or an idle-policy benefit.

## Static build result

The default module was compiled against the retained private ABI 3 build tree with
the bundled `make`. `modinfo` reports exact ABI3 `vermagic`; source gates are
all zero, and the default object has no `of_iomap` or
`register_kretprobe` dependency. An inline `+0x20` load remains in the
object, so the disabled claim is about the **unreachable runtime path**, not
absence of MMIO instructions. The source gates, absent mapping path, and
`hardware_ready` guard prevent a sample in this build. The module
was not installed, loaded or executed. An enabled build must
receive a fresh source/object/disassembly review and a bounded, separately
approved trial protocol. Do not treat this disabled build as calibration data.
The retained private preflight binds the reviewed `lct_probe.c` and
`lct_probe.ko` to their exact SHA-256 values as well as checking the ABI 3
Image/config/Build-ID. Its [offline result](offline-validation.json) is
published, but the module binary is not. Any source or module change
requires a new reviewed hash pair and validation.
