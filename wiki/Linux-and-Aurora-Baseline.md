# Linux and Aurora Silicon Baseline

This page exists to prevent rediscovering implemented power control. The comparison was pinned on 2026-10-01; branch heads can move. The complete source audit, including exact hashes and Aurora pull requests, is in [`notes/aurora-cpu-idle.md`](../notes/aurora-cpu-idle.md) and [`notes/asahi-known-gaps.md`](../notes/asahi-known-gaps.md).

## Checked revisions

| Project | Commit |
|---|---|
| [Asahi Linux `asahi`](https://github.com/AsahiLinux/linux/tree/77cb8f24c2381a8abb7272d7bbdec548d6426a8a) | `77cb8f24c2381a8abb7272d7bbdec548d6426a8a` |
| [Asahi Linux `asahi-wip`](https://github.com/AsahiLinux/linux/tree/94fb23346d522edf53722357c426a3e58030beea) | `94fb23346d522edf53722357c426a3e58030beea` |
| [Aurora Linux `aurora-stable`](https://github.com/aurora-silicon/linux/tree/076290b7c9a25aebf65d6a60561a4df38d4dad2c) | `076290b7c9a25aebf65d6a60561a4df38d4dad2c` |
| [Aurora Linux `aurora-wip`](https://github.com/aurora-silicon/linux/tree/1d2904fd3301c63620f07c81ae79f2486a81a9a6) | `1d2904fd3301c63620f07c81ae79f2486a81a9a6` |
| [Asahi m1n1 `main`](https://github.com/AsahiLinux/m1n1/tree/3e354a2467f4f724f254362626cae0633918e0c1) | `3e354a2467f4f724f254362626cae0633918e0c1` |
| [Aurora m1n1 `aurora-wip`](https://github.com/aurora-silicon/m1n1/tree/ae94c931bbbaef6ce97e6caf1fcef453edb3e3e6) | `ae94c931bbbaef6ce97e6caf1fcef453edb3e3e6` |

At all four checked Linux revisions, `drivers/cpuidle/cpuidle-apple.c` has the same Git blob ID (`3d2b804df8a2de18b8d8f031857b00d7198dab4c`). This is an **exact file comparison**, not a statement that all Asahi and Aurora code is identical. [Asahi file](https://github.com/AsahiLinux/linux/blob/77cb8f24c2381a8abb7272d7bbdec548d6426a8a/drivers/cpuidle/cpuidle-apple.c), [Aurora file](https://github.com/aurora-silicon/linux/blob/1d2904fd3301c63620f07c81ae79f2486a81a9a6/drivers/cpuidle/cpuidle-apple.c).

## What is already implemented

| State | Driver implementation | Declared exit latency | Declared target residency |
|---|---|---:|---:|
| `WFI` | Ordinary `cpu_do_idle()`, described as clock gated | 1 μs | 1 μs |
| `CPU PD` | CPU PM save/restore around returning Apple deep WFI | 10 μs | 10,000 μs |

The `CPU PD` assembly saves x18–x30, selects `CYC_OVRD` WFI mode 3 using bits 25:24, executes `DSB SY; WFI`, loops until an interrupt is pending, then restores the prior return mode and registers. Notifiers account for other lost state. These fields and numbers are source declarations, **not native measurements** of exit time or physical cluster shutdown. [Driver implementation](https://github.com/AsahiLinux/linux/blob/77cb8f24c2381a8abb7272d7bbdec548d6426a8a/drivers/cpuidle/cpuidle-apple.c#L21-L94).

The boot firmware also configures M1 APSC and snooze behavior. The pinned Aurora and Asahi M1 `src/chickens.c` files are identical; `src/cpufreq.c` differences do not change their inspected M1 setup. These boot-time writes are already prior art, although a runtime policy difference may remain. [Aurora CPU setup](https://github.com/aurora-silicon/m1n1/blob/ae94c931bbbaef6ce97e6caf1fcef453edb3e3e6/src/chickens.c), [Aurora cluster setup](https://github.com/aurora-silicon/m1n1/blob/ae94c931bbbaef6ce97e6caf1fcef453edb3e3e6/src/cpufreq.c).

Asahi m1n1 has a **non-returning** deeper sleep/stop-start path that can disable WFI retention and arrange CPU restart through PMGR. Linux's ordinary cpuidle callback needs a reliable return/restart contract: state save and restoration, reset vector, timer and interrupt recovery, last-core coordination, concurrent wakeup handling, and firmware ownership. The existence of low-level stop/start primitives does not make the full runtime idle state ready. [m1n1 sleep code](https://github.com/AsahiLinux/m1n1/blob/3e354a2467f4f724f254362626cae0633918e0c1/src/utils.c#L249), [SMP source](https://github.com/AsahiLinux/m1n1/blob/3e354a2467f4f724f254362626cae0633918e0c1/src/smp.c).

## Aurora-specific boundaries

Aurora has substantial independent platform work, but its checked M1 CPU-idle driver is the same file. An [Aurora J700/T8140 experiment](https://github.com/aurora-silicon/linux/pull/54) reports a freeze with CPU PD enabled for that newer chip; it must not be generalized to T8103. Aurora's [PMP report driver](https://github.com/aurora-silicon/linux/blob/1d2904fd3301c63620f07c81ae79f2486a81a9a6/drivers/pmdomain/apple/pmp-report.c) matches later chip families, not base T8103, in the checked revision. Project source/history supports these narrow statements; it does not establish what anyone has discovered privately.

For this project, the useful gap is **policy and achieved state**: last-active-core and DVFS ordering, WFE selection, peripheral wake constraints, validated hardware residency, and possibly the deeper restart contract. A new result must beat this baseline with an independent observation, not just a different name for deep WFI.
