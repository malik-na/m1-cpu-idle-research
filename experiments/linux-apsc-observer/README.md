# Experimental T8103 APSC observer

This is a **source patch for a future native Linux run**, based on Asahi Linux
[`77cb8f24c2381a8abb7272d7bbdec548d6426a8a`](https://github.com/AsahiLinux/linux/tree/77cb8f24c2381a8abb7272d7bbdec548d6426a8a).
It has not been booted on the target Mac. The separate [native run
checklist](NATIVE-RUN.md) defines the hardware evidence needed before any
runtime or power claim. [Build validation](BUILD-VALIDATION.md) records the
exact patch, configurations, object checks, and unchanged WFI bytes;
[review and remaining work](REVIEW.md) separates corrected defects from
the still-open native capture ticket. The patch is observation-only: the sole APSC SET
write is the cpufreq driver's existing write, performed exactly once; the
optional idle-path APSC access is a read. It adds no power-control write,
post-SET poll, firmware call, or wait.

Apply [`0001-t8103-apsc-observer.patch`](0001-t8103-apsc-observer.patch) to
that exact commit with `git apply --check` followed by `git apply`. The built-in
`CONFIG_ARM_APPLE_APSC_OBSERVER` option defaults to `n` and requires
`CONFIG_ARM_APPLE_CPUIDLE=y`, `CONFIG_ARM_APPLE_SOC_CPUFREQ=y`,
`CONFIG_DEBUG_FS=y`, and `CONFIG_ARCH_APPLE=y`. The observer activates only on
`apple,t8103`, requires eight possible **and online** CPUs, and derives two
cluster APSC mappings from the booted CPU `performance-domains` phandles.
Mappings and fixed buffers are retained for the boot. There is no module
unload path or second capture. A config with the observer disabled compiles
the two existing drivers without the calls. An enabled but unarmed kernel
still executes small hook/wrapper checks and a preemption-disabled region
around the original SET write, so an unarmed window is not identical to a
kernel built without the patch.

Once installed and separately authorized for native Linux, debugfs exposes
`/sys/kernel/debug/apple_apsc_observer/capture`, `status`, and `events.csv`.
Writing `records <milliseconds>` or `mmio <milliseconds>` to `capture` is
synchronous. The requested interval must be 100–10000 ms; the kernel sleeps
with `msleep_interruptible`, then stops recording and drains in-flight hooks
before export. The requested duration is **not a hard real-time maximum**:
scheduling delays can extend the actual interval, which is represented by
`start_tick`, `stop_tick`, and post-drain `end_tick`. A signal ends the capture
early, makes the state invalid, and leaves records available. Capture is
one-shot even when preparation fails. `status` and `events.csv` return
`-EBUSY` during setup/capture/drain; no hot-path record is streamed to debugfs.

The CSV header is:

```text
kind,seq,cpu,cluster,policy_cpu,policy_mask,fast_switch,requested_index,requested_pstate,token,t0,t1,pre_cmd,cmd,ret,flags
```

`kind` is `dvfs`, `idle_enter`, `idle_exit`, or `cpu_pm_fail`. Idle streams are
per logical CPU and DVFS streams per target cluster; `seq` starts at zero
within each stream and counts attempted reservations, including overflow.
DVFS sequence reflects **reservation after the write**, so concurrent or
nested writers can have timestamps out of sequence. `cpu` identifies the
executing CPU, while `cluster`, `policy_cpu`, and `policy_mask` identify the
target. `policy_mask`, `pre_cmd`, and `cmd` are `0x` hexadecimal; a blank cell
means absent, never zero. Policy fields are blank on idle rows. `token` pairs
an idle entry with its return; capture stopping between them leaves an
incomplete interval. `fast_switch` is the runtime policy flag at the DVFS
record, not proof that the callback was invoked by the fast-switch path.

`requested_index` and `requested_pstate` are decimal unsigned 32-bit values
on every DVFS row, including a failed preceding BUSY poll; both are blank on
idle and CPU-PM-failure rows. `requested_index` preserves the incoming
frequency-table index before the driver's existing fallback clamp.
`requested_pstate` preserves the hardware pstate that the original driver
computes from that incoming table entry. Neither field changes the existing
clamp, pstate calculation, or write. For a successful submission, the raw
`cmd` remains authoritative for the word actually written.

`t0` and `t1` are decimal raw physical-counter ticks. For successful DVFS,
they surround the original SET write, with `pre_cmd` the raw value from the
successful BUSY poll and `cmd` the submitted word. A failed poll records
`pre_cmd` and `ret=-EIO`, with no `cmd` or write. For `idle_enter`, they
surround either the records-only no-op or one **ordered** APSC `readq` before
`ct_cpuidle_enter()`; `cmd` is present only when `flags & 1` says the MMIO
sample is valid. This `readq` includes the architecture's read ordering cost.
`idle_exit` and `cpu_pm_fail` have equal `t0`/`t1`; the latter stores the raw
nonzero CPU-PM notifier return, which need not be negative. `flags` bit 0 is
the only defined bit; other bits are zero in ABI 1. The t0/t1 probe span does
**not** include all record publication overhead. A returned MMIO value is
only command-register state at that earlier C probe; these timestamps are
not a physical WFI or command-completion marker.

`status` is `key=value` text with `abi=1`, state (`ready`, `complete`, or
`invalid` when readable), mode, `cntfrq`, `start_tick`, `stop_tick`,
`end_tick`, online masks, and `interrupted`. It includes
`clusterN_cpus`, `clusterN_cmd_phys`, `clusterN_resource_size`,
`clusterN_policy_mask_start/end`,
`clusterN_policy_cpu_start/end`, and `clusterN_fast_switch_start/end` for
N=0,1, plus `idleN_...` for N=0..7 and `dvfsN_...` for N=0,1. The command
physical address and resource size come from the booted DT and are `0x`
hexadecimal; no kernel virtual address is exported. Each stream reports
`attempts`, `committed`, `overflow`, and `missing_commit`. After drain,
`attempts = committed + overflow + missing_commit`. Idle streams have
capacity 2048 each and DVFS streams 4096 each; total storage is bounded,
but an interval can fill it. Once an idle stream fills, later idle entries
skip the optional MMIO read. Any overflow, missing commit, incomplete idle
pair, or invalid state prevents a negative/no-overlap conclusion. Endpoints
of policy/fast-switch state are sampled, but equal endpoints cannot rule out
a transient policy change during the capture; the run protocol must prohibit
such changes.

The observer holds `cpus_read_lock()` only in the sleeping capture control
task to prevent topology changes. Hooks never retain a mapping pointer or
RCU section across WFI. Disabling capture precedes an RCU grace period and
export; an in-flight event's `t1` can exceed `stop_tick` but must precede
`end_tick`. The ARM64 tree at this source pin has no applicable
`HAVE_NOINSTR_VALIDATION`/objtool pass, so a native candidate requires manual
disassembly review of the `__cpuidle` path and WFI retry target.

The offline [analyzer](analyze.py) validates the CSV/status contract, reports
loss and incomplete intervals, and separates active-window, stop-straddling,
and drain records. It reports minimum, median, nearest-rank p95, and maximum
accessor spans in ticks and approximate nanoseconds, grouped by operation.
These spans exclude some record construction/publication work; a failed
DVFS poll contributes a timestamp marker, not its poll duration. It does not
yet reconstruct candidate software final entrants or qualify cross-CPU
clock ordering. All [decoder tests](test_analyze.py) use synthetic inputs.

```sh
python3 analyze.py /path/to/private/events.csv /path/to/private/status.txt
python3 -m unittest discover -s . -p 'test_*.py'
```

Run these from this directory. Retain the original files and the separate
boot/run packet; the default `unverified_input` label deliberately avoids
authenticating a capture from its syntax alone.
