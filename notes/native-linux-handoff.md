# First native Omarchy / Aurora session

**2 October follow-up:** A [read-only qualification](linux-native-qualification-20261002.md) records the visible Linux kernel/configuration, installed-image hashes, build-ID linkage, reported firmware and CPU policies. Protected EFI/FDT/log inspection corroborated the native stock boot. The original stock source/build recipe and dirty stage-1 source remain unresolved. A separate instrumented image was then built and booted for the [native A/B/C result](../experiments/aurora-apsc-observer/NATIVE-RESULT.md). The original preparation below remains the historical run protocol.

The separate research kernel is now installed. Its first requested test
restart selected stock; the [outcome receipt](../experiments/aurora-apsc-observer/restart-outcome-receipt.json)
preserves that unresolved result. Select `Aurora-APSC-research` at the menu
and verify the actual native boot before using the [prepared collector](../experiments/aurora-apsc-observer/NATIVE-PLAN.md).

A subsequent direct research boot exposed missing Wi-Fi and brightness. The
[regression record](../experiments/aurora-apsc-observer/driver-regression-receipt.json)
shows a prior stock boot removed the unowned research modules. A verified
local module package now protects that tree from the same cleanup condition;
the operator's next research boot had working Wi-Fi and brightness. The
later capacity-image boots produced the reviewed A/B/C capture above.

Prepared 2 October 2026 for the base-M1 MacBook Air (J313 / T8103), before the subsequent Omarchy/Aurora installation and native research boots. The first research session was intended to establish the unmodified native baseline and exact source identity before preparing an instrumented kernel.

The selected distribution is now specifically [iconidentify/aurora-linux](https://github.com/iconidentify/aurora-linux), using its `releases/latest/download/install-aurora-sep.sh` entry point. The [release/source audit](iconidentify-aurora-kernel-target.md) records the observed installer, package hashes, embedded config and required patch adaptations. The default repository branch is not the custom release selected by that installer; resolve the actual downloaded release again when installing.

## Read-only first-boot inventory

Run these only after the operator has completed installation and booted Linux. Retain the output privately, including missing-file or permission errors. No command below changes kernel configuration, CPU policy, or hardware registers.

```sh
uname -r
uname -v
cat /etc/os-release
systemd-detect-virt
tr '\000' '\n' </proc/device-tree/compatible
pacman -Q | rg '^(linux|m1n1|uboot|u-boot|asahi|aurora|omarchy)'
if test -r "/usr/lib/modules/$(uname -r)/pkgbase"; then
    cat "/usr/lib/modules/$(uname -r)/pkgbase"
else
    printf 'unavailable: /usr/lib/modules/%s/pkgbase\n' "$(uname -r)"
fi
if test -r /proc/config.gz; then
    zcat /proc/config.gz | sha256sum
    zcat /proc/config.gz | rg '(ARCH_APPLE|SMP|CPU_IDLE|CPU_FREQ|ARM_APPLE_CPUIDLE|ARM_APPLE_SOC_CPUFREQ|DEBUG_FS|IKCONFIG|ARM_ARCH_TIMER_OOL_WORKAROUND|MFD_SYSCON|REGMAP|APPLE_PMGR_PWRSTATE|ARM_APPLE_APSC_OBSERVER|APPLE_COUNTER_QUALIFICATION|APPLE_PCPM_SAMPLER)'
else
    printf 'unavailable: /proc/config.gz\n'
fi
cat /sys/devices/system/cpu/possible /sys/devices/system/cpu/online
cat /sys/devices/system/cpu/cpuidle/current_driver
cat /sys/devices/system/cpu/cpuidle/current_governor_ro
for s in /sys/devices/system/cpu/cpu*/cpuidle/state*; do
    test -d "$s" || { printf 'unavailable: %s\n' "$s"; continue; }
    printf '%s\n' "$s"
    for f in name disable latency residency usage time; do
        if test -r "$s/$f"; then
            printf '%s=' "$f"; cat "$s/$f"
        else
            printf 'unavailable: %s/%s\n' "$s" "$f"
        fi
    done
done
for p in /sys/devices/system/cpu/cpufreq/policy*; do
    test -d "$p" || { printf 'unavailable: %s\n' "$p"; continue; }
    printf '%s\n' "$p"
    for f in related_cpus affected_cpus scaling_driver scaling_governor scaling_min_freq scaling_max_freq scaling_cur_freq; do
        if test -r "$p/$f"; then
            printf '%s=' "$f"; cat "$p/$f"
        else
            printf 'unavailable: %s/%s\n' "$p" "$f"
        fi
    done
done
```

`unavailable` means the path was absent or unreadable; it does not establish which cause applies. Keep that distinction unresolved until checked. `systemd-detect-virt` is one check, not independent proof of native boot; record the actual boot route. A missing `/proc/config.gz` means obtain the configuration tied to the booted package/image. Missing experimental options or interfaces are expected on a stock kernel: this repository's instruments are not claimed to be included in Aurora. Sysfs state names and accumulated idle times establish software configuration/accounting, not physical power gating.

## Qualify the actual Aurora build

Also retain the installed versions of `linux-aurora`, `linux-aurora-headers`, `m1n1-aurora`, `aurora-touchid`, `libfprint`, `fprintd` and any `avd-fw` package, plus enabled SEP/Touch ID services and installer package pins. The selected installer changes these components and boot device trees as well as the kernel; preserve that configuration as the baseline.

Use the module `pkgbase` and package-file ownership to identify the running kernel's package; record `pacman -Qi <verified-package-name>`, its exact version, package archive hash, packaging-repository commit, source commit, applied patches, build configuration and toolchain. Identify and hash the **actually booted** image and DT; a release suffix, package name, or arbitrary `/boot` file does not prove source identity. Record m1n1, U-Boot and firmware provenance from verified boot artifacts/logs, along with boot arguments privately. If any source-to-image link is unresolved, label it unknown. The fuller evidence contract is in [NATIVE-RUN.md](../experiments/linux-apsc-observer/NATIVE-RUN.md).

All three prepared patches currently target [Asahi Linux `77cb8f24c2381a8abb7272d7bbdec548d6426a8a`](https://github.com/AsahiLinux/linux/tree/77cb8f24c2381a8abb7272d7bbdec548d6426a8a): [APSC observer](../experiments/linux-apsc-observer/README.md), [counter qualification](../experiments/linux-counter-qualification/README.md), and [PCPM sampler](../experiments/linux-pcpm-sampler/README.md). Their review/build results do not establish Aurora compatibility. Before applying or rebasing, compare the exact target's cpuidle assembly/hooks, cpufreq write/poll paths, counter access, DT topology/resources and syscon/regmap ownership/lifetime. Review changed contracts and generated code under the actual target configuration; a clean patch application alone is insufficient.

A separate [Aurora observer/counter port](../experiments/aurora-apsc-observer/README.md), prepared on 2 October 2026, preserves those original patches and targets the exact selected iconidentify release source. It passes scoped application checks and preliminary object builds against the installed prepared headers, with actual GCC/configuration differences recorded. Its [build record](../experiments/aurora-apsc-observer/BUILD-VALIDATION.md) includes complete-source Kconfig, final linking and linked instruction checks, with separate installation and [native result](../experiments/aurora-apsc-observer/NATIVE-RESULT.md) records. The PCPM sampler has not been ported by this increment.

The [dated Aurora baseline](../wiki/Linux-and-Aurora-Baseline.md) found identical CPU-idle code at its named revisions, but also documented later cpufreq/DT differences. Use those pinned comparisons as a starting point, not identification of the newly installed kernel. Do not enable or run an instrument until target qualification, review and the separately authorized native-run protocol are complete.

## Preserve the baseline and hand off evidence

Keep a known-working stock Aurora kernel, its matching initramfs/DT and a selectable boot entry as the fallback; verify the recovery route before a later instrumented installation. Capture stock CPU policy and normal operation first. Record power source, charging, display, USB, thermals and background activity; do not change governors, frequency limits, CPU-online masks or idle-disable flags as part of this inventory.

Keep full config, DT, package/boot logs, image hashes and raw outputs in a private run packet. Publish only reviewed identifiers, configuration excerpts and sanitized findings under the [publication boundary](../PROVENANCE.md); omit credentials, private addresses, unrelated machine IDs and raw boot arguments. This handoff provides preparation, not a native measurement, patch installation or power-saving result. The next decision is which source-qualified observation to authorize, using the existing [APSC checklist](../experiments/linux-apsc-observer/NATIVE-RUN.md) and [joint-capture gates](../experiments/linux-pcpm-sampler/JOINT-CAPTURE.md).
