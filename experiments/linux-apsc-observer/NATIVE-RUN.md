# Native T8103 run checklist for the APSC observer

This is a **future-run checklist**, not a run record. The current Mac is booted into macOS; the observer has not been installed or run on native Linux. No usable native Linux boot is currently established; prepare and verify that environment in the later authorized session. A cross-build or disassembly review does not qualify its runtime behavior. Reboot, kernel installation, root access, and any hardware experiment require the operator's separate authorization and a known boot fallback. Follow the repository [evidence standard](../../wiki/Evidence-Standard.md), [DVFS-to-WFI trace decision](../../notes/linux-dvfs-wfi-trace-choice.md), and [publication boundary](../../PROVENANCE.md).

## Go/no-go before a native boot

- [ ] Name the question before boot: can a candidate final core sample an APSC command with bit 31 (`BUSY`) set after a recorded SET submission for its target cluster? Predeclare a result that weakens it, the number of opportunities needed, and the tolerated loss. A BUSY sample is command state at one point; it is not a rail-off, energy, or defect finding.
- [ ] Review the exact target kernel source and configuration, including the Apple cpufreq and cpuidle paths, observer commit/diff, DT resource ownership, mapping lifetime, hotplug/teardown, and whether the observer is built in. Require `ARM_APPLE_CPUIDLE=y`, `ARM_APPLE_SOC_CPUFREQ=y`, `DEBUG_FS=y`, and the observer's default-off Kconfig option explicitly enabled. Any mismatch with the pinned source in the trace decision requires a fresh seam review.
- [ ] Inspect generated AArch64 disassembly and relocations. Confirm no added APSC/PMGR write, post-SET poll, wait, firmware call, dynamic allocation, printk, or lock in the idle path; preserve the original power-control sequence and WFI retry. Review the C pre-WFI probe's `__cpuidle`/RCU and instrumentation annotations against the **actual target config**. The pinned arm64 tree lacks `HAVE_NOINSTR_VALIDATION` and arm64 objtool support; do not report a passing objtool/noinstr check or treat build success as that validation.
- [ ] Arrange a fallback boot and a separate, explicitly authorized native Linux window. Do not alter CPU hotplug, governor, frequency limits, idle-state disables, boot arguments, or power policy to manufacture opportunities. If any such state changes outside the experiment, stop and record them rather than silently comparing runs.

## Identify the boot actually under test

Save a private run packet **before and after each window**: date and time; Mac/SoC/board; native versus guest; `uname` release/build; exact booted image and source commit plus dirty state; full kernel config and its hash; booted DT blob and hash with CPU `performance-domains` and PMGR/cpufreq resources; m1n1, firmware, bootloader and boot arguments; observer binary/source identity; cpuidle driver and each CPU's state names/disable flags; cpufreq policy related/online CPUs, driver, governor, min/max/current frequency; and runtime `fast_switch_enabled`. The driver's `fast_switch_possible = true` is only source capability. The observer plans `clusterN_fast_switch_start`/`clusterN_fast_switch_end` status fields even when no DVFS event fires; confirm both and reject a changed value. Matching endpoints do not rule out a transient policy change, so the run protocol must also forbid it. If runtime fast-switch state cannot be read or captured, mark it **unknown**, and do not infer a cross-policy fast-switch writer.

These commands are read-only starting points on native Linux; save raw output privately and publish only reviewed, sanitized values. A missing file is an evidence gap, not a reason to substitute a historical boot artifact:

```sh
uname -r
uname -v
tr -d '\000' </proc/device-tree/model; printf '\n'
tr '\000' '\n' </proc/device-tree/compatible
test ! -r /sys/firmware/fdt || sha256sum /sys/firmware/fdt
if test -r /proc/config.gz; then zcat /proc/config.gz | sha256sum; fi
cat /sys/devices/system/cpu/online
for p in /sys/devices/system/cpu/cpufreq/policy*; do
    test -d "$p" || continue
    printf '%s\n' "$p"
    for f in related_cpus affected_cpus scaling_driver scaling_governor scaling_min_freq scaling_max_freq scaling_cur_freq; do
        test ! -r "$p/$f" || { printf '%s=' "$f"; cat "$p/$f"; }
    done
done
for f in /proc/device-tree/cpus/cpu@*/performance-domains; do
    test ! -r "$f" || { printf '%s ' "$f"; od -An -tx1 "$f"; }
done
```

Also inspect each `/sys/devices/system/cpu/cpu*/cpuidle/state*/{name,disable,usage,time}` and the booted DT's cpufreq/PMGR nodes. If `/sys/firmware/fdt` is absent, record how the running DT was reconstructed and hash that saved artifact. Identify the *actually booted* kernel image rather than hashing an arbitrary file under `/boot`. Obtain m1n1/firmware identity from boot artifacts or a private boot log; there is no assumed universal sysfs value. Keep raw `/proc/cmdline`, boot logs, host paths, partition IDs, addresses, credentials, and unrelated machine IDs out of the public repository.

## Predeclare matched windows

Use the same built-in observer kernel/configuration and unchanged power settings for three variants: **A** no capture; **B** records-only capture; **C** records plus one APSC MMIO sample on the C pre-WFI path. Schedule short, quiet idle windows and separately controlled completed-work opportunities for same-cluster and remote writers. Pin workload placement only if that placement is part of the declared protocol; record it, and do not use CPU hotplug. Match completed work, warm-up, window length, power source/charging, external USB connection, display state/brightness, network/background activity, ambient/thermal trend, and wake schedule. Record any deviations.

The capture is **one-shot per boot**. Do not treat a second write or an immediate rerun as a repeat. Randomize or reverse A/B/C order across matched, independently booted sessions after operator authorization; allow thermal and charging conditions to return to the declared band. A has no observer events, so use the same external workload completion and software accounting for comparison. With the observer built in, A still executes inactive hook checks and the DVFS wrapper. A separate build with the observer option disabled is needed to assess that fixed cost against the original driver; A/B/C alone cannot measure it. B estimates normal-memory record/timing overhead. C adds the read's possible fabric and timing effect. None of these variants changes the idle policy or proves energy savings by itself.

## Capture only in the authorized Linux session

The v1 interface is built-in and default-off: `/sys/kernel/debug/apple_apsc_observer/capture` accepts one synchronous `records <ms>` or `mmio <ms>` write, with **100–10000 ms** inclusive. The collector sleeps for the requested interval; scheduling delay can extend it, so use the saved start/stop/end ticks for actual duration rather than assuming a hard real-time deadline; do not spin in a userspace loop or stream from the idle path. Check that debugfs, `capture`, `status`, and `events.csv` exist; verify `status` is ready **before** arming. Root access is needed for debugfs capture. Let the operator authenticate locally; never put a password in a command, log, or repository file. Example for a separately authorized B session (C substitutes `mmio` on a different boot):

```sh
: "${apsc_run_dir:?set to a private writable directory outside the repository}"
printf 'records 1000\n' | sudo tee /sys/kernel/debug/apple_apsc_observer/capture >/dev/null
sudo cat /sys/kernel/debug/apple_apsc_observer/status >"$apsc_run_dir/status.txt"
sudo cat /sys/kernel/debug/apple_apsc_observer/events.csv >"$apsc_run_dir/events.csv"
```

Preserve the complete private files, their SHA-256 hashes, the exact capture command/duration, boot packet, workload definition, and completion/thermal/power logs. Do not publish raw captures until reviewed against [PROVENANCE](../../PROVENANCE.md). Set `apsc_run_dir` to an operator-controlled directory outside the repository before running the example.

## Validate before interpretation

Run the offline analyzer against the saved files (from this repository root):

```sh
python3 experiments/linux-apsc-observer/analyze.py "$apsc_run_dir/events.csv" "$apsc_run_dir/status.txt"
```

Its `unverified_input` label is intentional: parsing cannot authenticate a boot or prove that the supplied records came from hardware. Keep the run packet beside the output. Use `--synthetic-fixture` only for artificial test data. By default it leaves cross-CPU candidate reconstruction unavailable. With `--pairwise-clock-error-ticks E` it runs the [conditional software screen](README.md), treating unsigned integer `E` as an explicit assumption about maximum pairwise timestamp error over the entire capture. No supplied value, including zero, establishes clock qualification. Preserve its rationale and any [clock-qualification evidence](CLOCK-QUALIFICATION.md) beside the result. The qualification helper is planned, not implemented or run.

- [ ] Save `status` even on errors or empty captures. It reports ABI/state/mode, `CNTFRQ`, start/end ticks, online/cluster masks, per-cluster runtime fast-switch start/end, and each stream's attempts, committed, overflow, and missing-commit counts. Require a complete capture and **zero overflow and missing commits** for a negative/no-BUSY timeline claim; retain failed runs but do not silently omit them. Check CSV sequence gaps, duplicates, malformed rows, and unknown flags against status.
- [ ] Preserve raw CSV `kind,seq,cpu,cluster,policy_cpu,policy_mask,fast_switch,requested_index,requested_pstate,token,t0,t1,pre_cmd,cmd,ret,flags`. `seq` is per stream (idle per CPU; DVFS per cluster), ticks are raw physical-counter ticks, masks/command words are hexadecimal, and empty fields mean absent data. Record units, decode BUSY and SET offline, and retain unrecognized values. Use `policy_cpu`/mask for the target and `cpu` for the executing writer; they are not interchangeable. Preserve `requested_index` and `requested_pstate` even when the preceding BUSY poll fails; these are the incoming frequency-table index and hardware-state request, not a measured resulting frequency.
- [ ] Check `CNTFRQ`, `t0 <= t1`, interval bounds, per-stream order, and timestamp reversals. Follow the [clock-qualification protocol](CLOCK-QUALIFICATION.md) for a controlled, kernel-side cross-CPU exchange before asserting one CPU's recorded submission preceded another CPU's idle read. Preserve raw exchange intervals and drift/read-order assumptions; communication latency is not clock skew, and finite before/after samples cannot guarantee a bound throughout idle. If qualification fails or the uncertainty is too wide, keep within-CPU order only and label cross-CPU order unresolved.
- [ ] Reconstruct only **conditional candidate software final entrants** from complete interior entry/return intervals and online masks. Require complete witnesses from every cluster peer, with strict clock-error margins at capture boundaries and both sides of the sample. Inspect grammar failures and all interval exclusions. Match command target cluster, the raw preceding poll value and submitted command word (there is no new post-write readback), return/error status, runtime fast-switch state, and MMIO sample validity (`flags` bit 0). Preserve ambiguous write ordering. A nearest recorded predecessor is not a causal BUSY attribution. A missing mapping/read or a failed preceding BUSY poll is an explicit failed observation, not a clear bit; no-candidate output is not proof of no overlap.
- [ ] Report minimum, median and tail accessor duration (`t1 - t0`), event counts/opportunities, and drop counts for B/C. Those brackets exclude some record construction and publication work, so they are not total hook cost. A has no event brackets. Use a separately described measurement for wake latency and completed work across A/B/C. Compare B to A and C to B for observer effect. If MMIO sampling changes idle or timing, or if loss/counter uncertainty exceeds the predeclared bound, stop short of a frequency or causal claim.

The v1 sample is in C **before** `ct_cpuidle_enter()` and before the assembly path reaches its original `dsb sy; wfi`. It is not an instruction-level WFI marker or a sample of every retry. A BUSY value establishes only that the command was pending at this pre-WFI read. A clear value does not rule out a remote write after the read, a command completing before WFI, or uninstrumented overlap. Neither result identifies rail power state; that needs the separate [PCPM calibration](../../notes/native-pcpm-signal-decision.md) or another independent signal.
