# Aurora Silicon and M1 CPU idle: pinned source investigation

Date: 2026-10-01, India time. Scope: base M1 T8103, particularly the user's MacBook Air J313. Read-only source investigation; no kernel loading, register writes, firmware changes, privileged machine access, or hardware power measurements were performed for this report.

## Result

**Aurora's current M1 CPU-idle driver is byte-identical to Asahi's current driver.** Aurora is a useful source of additional platform work and evidence, but the public sources inspected do not establish that Aurora independently solved an M1 CPU-idle gap left by Asahi. They show that Linux already has a CPU/cluster power-down path on M1. They do not establish that Linux reaches all of macOS's idle substates, with the same policy or energy cost.

The promising investigation is therefore the difference between macOS's *policy and achieved hardware residency* and Linux's existing deep-WFI path, including the cluster APSC configuration, last-core behavior, wakeup distribution, and peripherals preventing larger power domains from becoming idle. Reimplementing WFI or merely registering an `apple_idle` driver would not be new work.

This is a narrow equivalence result for the named files at the pinned revisions. **It is not a claim that the entire Aurora and Asahi projects or kernel trees are identical.** Aurora has substantial work elsewhere, including platform enablement and device drivers outside this CPU-idle investigation.

## Revisions actually inspected

The branch names below were resolved through GitHub's public API during this investigation. A branch is mutable; the links use immutable commit IDs.

| Repository / branch | Commit |
|---|---|
| Aurora Linux `aurora-stable` (current default) | `076290b7c9a25aebf65d6a60561a4df38d4dad2c` |
| Aurora Linux `aurora-wip` | `1d2904fd3301c63620f07c81ae79f2486a81a9a6` |
| Asahi Linux `asahi` | `77cb8f24c2381a8abb7272d7bbdec548d6426a8a` |
| Asahi Linux `asahi-wip` | `94fb23346d522edf53722357c426a3e58030beea` |
| Aurora m1n1 `aurora-wip` | `ae94c931bbbaef6ce97e6caf1fcef453edb3e3e6` |
| Asahi m1n1 `main` | `3e354a2467f4f724f254362626cae0633918e0c1` |

The checked upstream files are linked at immutable commits below rather than copied into this public repository. GitHub contents API responses supplied Git blob SHA-1 identifiers, which give an exact content comparison rather than a similarity judgment.

## What the M1 kernel already does

In **all four Linux revisions above**, `drivers/cpuidle/cpuidle-apple.c` has the same Git blob ID:

`3d2b804df8a2de18b8d8f031857b00d7198dab4c`

The driver allows T8103 and exposes two states:

| State | Source description | Exit latency | Target residency |
|---|---|---:|---:|
| `WFI` | CPU clock gated | 1 microsecond | 1 microsecond |
| `CPU PD` | CPU/cluster powered down | 10 microseconds | 10,000 microseconds |

These are the driver's declared parameters, **not measurements made on this machine**. In particular, a target residency is a governor decision parameter, not a claim that hardware physically spends that long powered off.

For `CPU PD`, the path enters the CPU PM notifier chain, enters idle context tracking, saves callee-saved general registers, sets bits 24 and 25 of `s3_5_c15_c5_0`, executes `dsb sy; wfi`, and loops until `ISR_EL1` shows an interrupt. On return it clears bit 24, restores registers, leaves idle context tracking and exits the CPU PM notifier chain. The code explicitly accounts for deep WFI clobbering FP state through CPU PM callbacks. Both states also have an `enter_s2idle` callback.

This driver does not invoke PSCI. Its original introduction, commit `30284f0d1c367b62671e1dce6a2a0d17e67be8e8` by Hector Martin, describes it as a downstream solution pending a PSCI discussion. Subsequent history in the inspected Aurora branch consists of machine eligibility changes, including avoiding M4's incompatible register and adding M3 families. The presence of this driver establishes an implemented control path, not its actual use in the user's installed kernel or equivalence to macOS's full power controller.

Sources: [Aurora driver](https://github.com/aurora-silicon/linux/blob/1d2904fd3301c63620f07c81ae79f2486a81a9a6/drivers/cpuidle/cpuidle-apple.c), [Asahi driver](https://github.com/AsahiLinux/linux/blob/77cb8f24c2381a8abb7272d7bbdec548d6426a8a/drivers/cpuidle/cpuidle-apple.c), [original driver commit](https://github.com/aurora-silicon/linux/commit/30284f0d1c367b62671e1dce6a2a0d17e67be8e8).

### A misleading old comment

The current T8103 device tree still contains a comment saying turbo states are unavailable until deep sleep exists, immediately above enabled turbo OPPs. Read literally, that comment would incorrectly suggest that deep sleep remains unimplemented. Commit `458108b6a23e6ce1a341b89682d5ed29c3e91b0a` enabled those turbo states specifically because cpuidle had become available. Check node properties and history, not that isolated comment.

Sources: [T8103 device tree](https://github.com/aurora-silicon/linux/blob/1d2904fd3301c63620f07c81ae79f2486a81a9a6/arch/arm64/boot/dts/apple/t8103.dtsi), [turbo enablement commit](https://github.com/aurora-silicon/linux/commit/458108b6a23e6ce1a341b89682d5ed29c3e91b0a).

## Boot initialization already covers APSC and snooze

At the pinned m1n1 revisions, the M1 initialization in Aurora and Asahi is the same:

- `src/chickens.c` is exactly identical: blob `916a1f0f2beff69799d2539d62f42a2a75f35ed9`. M1 uses `SLEEP_GLOBAL`; initialization enables NEX power gating on performance cores, unmasks external interrupts, configures the WFI mode and retention, and configures branch prediction retention across ACC sleep.
- `src/cpufreq.c` differs only in M3 Ultra / T6032 handling; M1 behavior is unchanged. For M1, initialization consults the ADT feature `cpu-apsc`, adjusts APSC enable/disable state, enables the existing APSC snooze bit at cluster base plus `0x200f8`, bit 40, copies the selected APSC P-state table pair, and selects a default P-state. This is boot initialization, not evidence that every macOS runtime policy has been reproduced.
- `src/smp.c` differs only in a T6032 case. Its deep-sleep stop path explicitly warns that switching off the last core in a cluster removes access to its registers.
- `proxyclient/hv/trace_pmp.py`, `proxyclient/experiments/pmp_init.py`, and `proxyclient/m1n1/fw/pmp.py` are exactly identical in the two trees (respectively blobs `048a25b86a148bbe6f268509a1e73ce43c6f51d7`, `c0b275c7c4edb642d35822c34bbc1dd3ad665c66`, and `fbfef4517785be041bd693040d2ab0db7ee10dae`). Their existence in Aurora should not be mistaken for new Aurora research.

The earlier Asahi-origin initialization commit `88df8a63354f9987224ce507f7952abb3ec97258` is particularly useful research context: its author stated that several initialization details were still incompletely understood while being brought closer to observed macOS behavior. Replicated register writes and fully understood semantics are different levels of knowledge.

Sources: [Aurora CPU initialization](https://github.com/aurora-silicon/m1n1/blob/ae94c931bbbaef6ce97e6caf1fcef453edb3e3e6/src/chickens.c), [Aurora cluster setup](https://github.com/aurora-silicon/m1n1/blob/ae94c931bbbaef6ce97e6caf1fcef453edb3e3e6/src/cpufreq.c), [Asahi cluster setup](https://github.com/AsahiLinux/m1n1/blob/3e354a2467f4f724f254362626cae0633918e0c1/src/cpufreq.c), [SMP stop path](https://github.com/aurora-silicon/m1n1/blob/ae94c931bbbaef6ce97e6caf1fcef453edb3e3e6/src/smp.c), [initialization history](https://github.com/aurora-silicon/m1n1/commit/88df8a63354f9987224ce507f7952abb3ec97258).

## Actual Aurora work and its boundaries

### T8140 / J700 CPU idle is explicitly unresolved

Open [PR #54](https://github.com/aurora-silicon/linux/pull/54), head `0a1ed8ce6d3c04e27f4b8adabbd3a7d0ea5dfa79`, registers `apple_idle` on J700 with only WFI. Its author reports that enabling CPU PD for a bounded twenty-second test froze a J700 and required a hard reset. The failing instruction/core had not been identified. This is valuable negative experimental evidence; it is **not** a demonstration that base M1 CPU PD is broken. T8140 is a different SoC generation.

### Proposed PMP-v2 work was parked

Merged [PR #22](https://github.com/aurora-silicon/linux/pull/22), merge commit `ed4fd3a576b49c5d104c99a131104e2c00193490`, includes T8140 cpufreq and interim J700 thermal-policy work. Its own description says the entire proposed PMP-v2 driver stack was left out pending a design based on `pmp.rs` and `apple-dart`, and says the rewritten form had not yet been run on hardware at that point. Do not cite the earlier experimental stack as shipped power-management support, or transfer J700 thermal observations to this M1 Air.

### PMP report-lock fix is real but does not establish base-M1 support

Merged [PR #56](https://github.com/aurora-silicon/linux/pull/56), commit `583b9fa52fbf6a47f150736ad4a1aaa0d616ac02`, initializes an omitted spinlock in the PMP state-reporting driver; its author records J416s/M2 Pro lockdep validation. The current driver's matching table is T6000, T6020 and T8112; it contains no T8103 match. This interface reports desired device states via shared SRAM. Its build configuration or presence on disk is insufficient to establish that it operates on a base-M1 Air.

Source: [PMP report driver](https://github.com/aurora-silicon/linux/blob/1d2904fd3301c63620f07c81ae79f2486a81a9a6/drivers/pmdomain/apple/pmp-report.c).

## What this narrows for new research

1. **Establish actual Linux registration and entry.** On the native Linux boot, capture the exact kernel/DT/m1n1 revisions, current cpuidle driver and governor, and each core's state names, disable bits, entry counts, residency deltas, rejected/above/below counts where exposed, plus wakeup sources. The macOS-side installed artifact cannot establish these runtime facts.
2. **Separate software time from hardware time.** `state1/time` counts Linux's time in the callback; it is not independently calibrated CPU or cluster off-time. A useful new result would map it against macOS IOReport residency counters or a independently validated hardware counter.
3. **Test the existing 10 ms policy boundary.** Short inter-wakeup intervals may fail to select the state even if its nominal 10 microsecond exit latency would allow it. The 10 ms target is a concrete research variable, not evidence of a bug. Controlled comparisons should sweep idle gaps, isolate E/P clusters, and measure wake latency and energy before considering a parameter change.
4. **Investigate cluster coordination.** Compare one core sleeping with the final active core sleeping; correlate the APSC state, requested performance level and observable cluster residency. Last-core shutdown is already known; a validated explanation of an unaccounted macOS substate or eligibility condition could be new.
5. **Pin the firmware version and boot initialization.** Existing M1 APSC/snooze programming is not absent. A repeatable delta between the current macOS controller and existing m1n1 initialization would be a stronger lead than generic speculation about a missing power driver.

No novelty claim follows from this source audit. It excludes several rediscoveries and yields a more targeted experiment. This inspection covered the named public repository revisions, relevant file histories, the returned Aurora Linux PR index (PRs 1 through 69), selected PR descriptions, the public documentation repository's research index, and the public research site. It was not an exhaustive search of every repository, unmerged branch, issue comment, IRC/Discord archive, or researcher fork; it cannot establish what Aurora or Asahi researchers know privately or have not yet published.

## Project identity and research availability

The relevant project is [Aurora Silicon](https://github.com/aurora-silicon), with a Linux fork whose upstream parent is `omacom/linux`, and a separate m1n1 fork. The separate [Omacom source audit](omacom-linux-source-audit.md) pins that parent fork's M1 paths and distinguishes its `aurora-wip` branch from Aurora Silicon's branch of the same name. Its public website is Windows oriented, labels itself incomplete, and its research index currently lists HAL, GPU, networking and security topics without a CPU-idle article. That absence means this investigation relies on code and patch evidence; it does not mean no CPU research exists in private discussion. See [research overview](https://aurorasilicon.org/research/overview/) and [project overview](https://aurorasilicon.org/project/overview/).

All source hashes, code comparisons and PR status observations above were refreshed for this dated investigation. Recheck mutable PR state and branch heads before relying on their current status.
