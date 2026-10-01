# Asahi, Omacom, and Aurora Silicon Baseline

This page exists to prevent rediscovering implemented power control. The comparison was pinned on 2026-10-01; branch heads can move. The detailed source audits, including exact hashes and Aurora pull requests, are in [`notes/asahi-known-gaps.md`](../notes/asahi-known-gaps.md), [`notes/omacom-linux-source-audit.md`](../notes/omacom-linux-source-audit.md), and [`notes/aurora-cpu-idle.md`](../notes/aurora-cpu-idle.md).

## Checked revisions

| Project | Commit |
|---|---|
| [Asahi Linux `asahi`](https://github.com/AsahiLinux/linux/tree/77cb8f24c2381a8abb7272d7bbdec548d6426a8a) | `77cb8f24c2381a8abb7272d7bbdec548d6426a8a` |
| [Asahi Linux `asahi-wip`](https://github.com/AsahiLinux/linux/tree/94fb23346d522edf53722357c426a3e58030beea) | `94fb23346d522edf53722357c426a3e58030beea` |
| [Omacom Linux `asahi`](https://github.com/omacom/linux/tree/77cb8f24c2381a8abb7272d7bbdec548d6426a8a) | `77cb8f24c2381a8abb7272d7bbdec548d6426a8a` |
| [Omacom Linux `aurora-wip`](https://github.com/omacom/linux/tree/4ec597a7427da2cf03c899406b7997c875d4a9fb) | `4ec597a7427da2cf03c899406b7997c875d4a9fb` |
| [Aurora Linux `aurora-stable`](https://github.com/aurora-silicon/linux/tree/076290b7c9a25aebf65d6a60561a4df38d4dad2c) | `076290b7c9a25aebf65d6a60561a4df38d4dad2c` |
| [Aurora Linux `aurora-wip`](https://github.com/aurora-silicon/linux/tree/1d2904fd3301c63620f07c81ae79f2486a81a9a6) | `1d2904fd3301c63620f07c81ae79f2486a81a9a6` |
| [Asahi m1n1 `main`](https://github.com/AsahiLinux/m1n1/tree/3e354a2467f4f724f254362626cae0633918e0c1) | `3e354a2467f4f724f254362626cae0633918e0c1` |
| [Aurora m1n1 `aurora-wip`](https://github.com/aurora-silicon/m1n1/tree/ae94c931bbbaef6ce97e6caf1fcef453edb3e3e6) | `ae94c931bbbaef6ce97e6caf1fcef453edb3e3e6` |

At all six checked Linux revisions, `drivers/cpuidle/cpuidle-apple.c` has the same Git blob ID (`3d2b804df8a2de18b8d8f031857b00d7198dab4c`). This is an **exact file comparison**, not a statement that all three kernel trees are identical. Omacom `asahi` is the exact same commit as Asahi `asahi`; Omacom `aurora-wip` is a separate branch from Aurora Silicon `aurora-wip`. [Asahi file](https://github.com/AsahiLinux/linux/blob/77cb8f24c2381a8abb7272d7bbdec548d6426a8a/drivers/cpuidle/cpuidle-apple.c), [Omacom file](https://github.com/omacom/linux/blob/4ec597a7427da2cf03c899406b7997c875d4a9fb/drivers/cpuidle/cpuidle-apple.c), [Aurora file](https://github.com/aurora-silicon/linux/blob/1d2904fd3301c63620f07c81ae79f2486a81a9a6/drivers/cpuidle/cpuidle-apple.c).

## What Omacom adds to the comparison

At the pinned Omacom `asahi` and `aurora-wip` revisions, the Apple cpufreq driver, T8103 device tree, generic PMGR driver, and T8103 PMGR include also have identical Git blobs to the Asahi `asahi` revision. The Omacom `aurora-wip` name must not be read as evidence of Aurora Silicon's later changes. Omacom's M1 cpufreq path [polls the command BUSY bit before a new request, writes that request, then returns](https://github.com/omacom/linux/blob/4ec597a7427da2cf03c899406b7997c875d4a9fb/drivers/cpufreq/apple-soc-cpufreq.c#L171-L201); it does not add an explicit last-core idle wait. [Exact hashes and branch inventory](../notes/omacom-linux-source-audit.md).

Aurora Silicon's later `aurora-wip` cpufreq file has [optional post-write verification](https://github.com/aurora-silicon/linux/blob/1d2904fd3301c63620f07c81ae79f2486a81a9a6/drivers/cpufreq/apple-soc-cpufreq.c#L243-L258), but its [T8103 data](https://github.com/aurora-silicon/linux/blob/1d2904fd3301c63620f07c81ae79f2486a81a9a6/drivers/cpufreq/apple-soc-cpufreq.c#L95-L103) leaves that option unset; the [T8140 data](https://github.com/aurora-silicon/linux/blob/1d2904fd3301c63620f07c81ae79f2486a81a9a6/drivers/cpufreq/apple-soc-cpufreq.c#L113-L125) enables it. Aurora's changed T8103 device-tree/PMGR include files add USB4-related nodes and two always-on ATC PCIe domains, rather than a CPU idle transition. Those domains may matter when comparing **whole-machine** idle energy. This source comparison does not identify the code or configuration of any currently booted Linux kernel. [Omacom/Aurora file audit](../notes/omacom-linux-source-audit.md).

## What is already implemented

| State | Driver implementation | Declared exit latency | Declared target residency |
|---|---|---:|---:|
| `WFI` | Ordinary `cpu_do_idle()`, described as clock gated | 1 μs | 1 μs |
| `CPU PD` | CPU PM save/restore around returning Apple deep WFI | 10 μs | 10,000 μs |

The `CPU PD` assembly saves x18–x30, selects `CYC_OVRD` WFI mode 3 using bits 25:24, executes `DSB SY; WFI`, loops until an interrupt is pending, then restores the prior return mode and registers. Notifiers account for other lost state. These fields and numbers are source declarations, **not native measurements** of exit time or physical cluster shutdown. [Driver implementation](https://github.com/AsahiLinux/linux/blob/77cb8f24c2381a8abb7272d7bbdec548d6426a8a/drivers/cpuidle/cpuidle-apple.c#L21-L94).

The boot firmware also configures M1 APSC and snooze behavior. The pinned Aurora and Asahi M1 `src/chickens.c` files are identical; `src/cpufreq.c` differences do not change their inspected M1 setup. These boot-time writes are already prior art, although a runtime policy difference may remain. [Aurora CPU setup](https://github.com/aurora-silicon/m1n1/blob/ae94c931bbbaef6ce97e6caf1fcef453edb3e3e6/src/chickens.c), [Aurora cluster setup](https://github.com/aurora-silicon/m1n1/blob/ae94c931bbbaef6ce97e6caf1fcef453edb3e3e6/src/cpufreq.c).

Asahi m1n1 has a **non-returning** deeper sleep/stop-start path that can disable WFI retention and arrange CPU restart through PMGR. Linux's ordinary cpuidle callback needs a reliable return/restart contract: state save and restoration, reset vector, timer and interrupt recovery, last-core coordination, concurrent wakeup handling, and firmware ownership. The existence of low-level stop/start primitives does not make the full runtime idle state ready. [m1n1 sleep code](https://github.com/AsahiLinux/m1n1/blob/3e354a2467f4f724f254362626cae0633918e0c1/src/utils.c#L249), [SMP source](https://github.com/AsahiLinux/m1n1/blob/3e354a2467f4f724f254362626cae0633918e0c1/src/smp.c).

## Operator-selected distribution fork

On 2 October 2026 the operator selected the latest-release installer from `iconidentify/aurora-linux`. This is a separate repository from Aurora Silicon and was not one of the six revisions in the original comparison. Its default `asahi` branch matches the old experiment base, while its installer selects a newer `custom/sep` release. The [dedicated audit](../notes/iconidentify-aurora-kernel-target.md) records exact commits, downloaded package/configuration evidence and two research patches that require adaptation. None of these source or archive checks identifies an actually booted kernel.

## Aurora-specific boundaries

Aurora has substantial independent platform work, but its checked M1 CPU-idle driver is the same file. An [Aurora J700/T8140 experiment](https://github.com/aurora-silicon/linux/pull/54) reports a freeze with CPU PD enabled for that newer chip; it must not be generalized to T8103. Aurora's [PMP report driver](https://github.com/aurora-silicon/linux/blob/1d2904fd3301c63620f07c81ae79f2486a81a9a6/drivers/pmdomain/apple/pmp-report.c) matches later chip families, not base T8103, in the checked revision. Project source/history supports these narrow statements; it does not establish what anyone has discovered privately.

For this project, the useful gap is **policy and achieved state**: last-active-core and DVFS ordering, WFE selection, peripheral wake constraints, validated hardware residency, and possibly the deeper restart contract. A new result must beat this baseline with an independent observation, not just a different name for deep WFI.
