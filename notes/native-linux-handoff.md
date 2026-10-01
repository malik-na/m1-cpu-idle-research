# First native Omarchy / Aurora session

Prepared 2 October 2026 for the base-M1 MacBook Air (J313 / T8103). The operator has chosen to install Omarchy with an Aurora Linux kernel. That is a planned target: the current session has not verified an installed or booted Linux system. The first research session should establish the unmodified native baseline and exact source identity before preparing an instrumented kernel.

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

Use the module `pkgbase` and package-file ownership to identify the running kernel's package; record `pacman -Qi <verified-package-name>`, its exact version, package archive hash, packaging-repository commit, source commit, applied patches, build configuration and toolchain. Identify and hash the **actually booted** image and DT; a release suffix, package name, or arbitrary `/boot` file does not prove source identity. Record m1n1, U-Boot and firmware provenance from verified boot artifacts/logs, along with boot arguments privately. If any source-to-image link is unresolved, label it unknown. The fuller evidence contract is in [NATIVE-RUN.md](../experiments/linux-apsc-observer/NATIVE-RUN.md).

All three prepared patches currently target [Asahi Linux `77cb8f24c2381a8abb7272d7bbdec548d6426a8a`](https://github.com/AsahiLinux/linux/tree/77cb8f24c2381a8abb7272d7bbdec548d6426a8a): [APSC observer](../experiments/linux-apsc-observer/README.md), [counter qualification](../experiments/linux-counter-qualification/README.md), and [PCPM sampler](../experiments/linux-pcpm-sampler/README.md). Their review/build results do not establish Aurora compatibility. Before applying or rebasing, compare the exact target's cpuidle assembly/hooks, cpufreq write/poll paths, counter access, DT topology/resources and syscon/regmap ownership/lifetime. Review changed contracts and generated code under the actual target configuration; a clean patch application alone is insufficient.

The [dated Aurora baseline](../wiki/Linux-and-Aurora-Baseline.md) found identical CPU-idle code at its named revisions, but also documented later cpufreq/DT differences. Use those pinned comparisons as a starting point, not identification of the newly installed kernel. Do not enable or run an instrument until target qualification, review and the separately authorized native-run protocol are complete.

## Preserve the baseline and hand off evidence

Keep a known-working stock Aurora kernel, its matching initramfs/DT and a selectable boot entry as the fallback; verify the recovery route before a later instrumented installation. Capture stock CPU policy and normal operation first. Record power source, charging, display, USB, thermals and background activity; do not change governors, frequency limits, CPU-online masks or idle-disable flags as part of this inventory.

Keep full config, DT, package/boot logs, image hashes and raw outputs in a private run packet. Publish only reviewed identifiers, configuration excerpts and sanitized findings under the [publication boundary](../PROVENANCE.md); omit credentials, private addresses, unrelated machine IDs and raw boot arguments. This handoff provides preparation, not a native measurement, patch installation or power-saving result. The next decision is which source-qualified observation to authorize, using the existing [APSC checklist](../experiments/linux-apsc-observer/NATIVE-RUN.md) and [joint-capture gates](../experiments/linux-pcpm-sampler/JOINT-CAPTURE.md).
