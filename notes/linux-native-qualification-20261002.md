# Linux target qualification for the command-to-WFI capture

2 October 2026. Work on [ticket #5](https://github.com/malik-na/m1-cpu-idle-research/issues/5), experiment E2. The live map's native child/dependency responses showed this ticket open with no open blocker; its method prerequisite, #3, was closed. All unblocked children were already assigned. The operator explicitly authorized continuing #5 under its existing assignment. The ticket remains open: this record qualifies parts of the target and records failed capture prerequisites; it does not supply the requested native APSC timeline.

## Result and falsifiable scope

The visible running kernel reports `7.1.12-2-11.17-sep-ARCH` on J313/T8103. Its exported configuration and the visible installed image match the hashes in the [previous release audit](iconidentify-aurora-kernel-target.md). The running kernel's GNU build ID matches the installed headers' `vmlinux` and occurs once in that image. These are stronger artifact-linkage observations than a release-name match, but they do not recover the package's source/build recipe or independently prove the native boot route.

The selected observer route is **not ready on the current kernel**. The exported config contains neither `CONFIG_ARM_APPLE_APSC_OBSERVER` nor `CONFIG_APPLE_COUNTER_QUALIFICATION`. Both unchanged research patches fail `git apply --check` on a sparse copy of their existing target files at the immutable release source revision. No privileged trace, APSC register read, kernel installation, reboot, or idle-policy change was performed.

| Proposition checked | Expected observation | Observed result and counterexample |
|---|---|---|
| The visible running config and installed image match the previously audited release artifacts. | Equal config/image hashes; consistent build ID. | Hashes and ID match. A differing retained byte digest or inconsistent exported ID would refute this limited identity result. It does not prove that every installed byte was booted or that the attributed source generated it. |
| The stock kernel is ready for the prepared direct-command recorder. | Explicitly enabled observer/helper options and a qualified interface. | Options are absent. Debugfs reads returned permission errors, which do not distinguish absent interfaces from inaccessible ones. A source/binary-qualified instrumented kernel and successful interface qualification would change this result. |
| The pinned release adds a T8103 post-command wait or changes its returning deep-WFI routine relative to the experiment base. | A T8103-applicable changed branch or instruction sequence. | Not found in the fully read, hash-checked two driver files: the optional post-write verification flag is unset for T8103; the existing deep-WFI routine and entry callback are unchanged. An applicable initializer/branch or an altered routine in these exact files would refute this source-scoped result. |

The E2 hardware hypothesis remains **untested**: a pending cluster command may overlap candidate final-core entry. A suitably instrumented, clock-qualified, low-loss run would support it with a raw BUSY sample at the declared pre-WFI seam, or weaken it with adequately sensitive controlled negative windows. This inventory contains zero APSC trace events; trace loss is **not applicable**, not a measured zero-drop capture. A missing recorder is not a no-overlap result.

## Target and artifact evidence

The [sanitized byte receipt](raw/native-linux-readonly-qualification-20261002.json) retains exact values, hashes, timestamps, units and negative read statuses. The main inventory was sequential on 2026-10-02 beginning at `04:39:18.697622 UTC`; firmware follow-up records have their own timestamps. It was collected without root in a session where `systemd-detect-virt` reports `container-other`. Device-tree and sysfs values describe the kernel visible to that session. Neither that detector nor the container's package database independently authenticates a native, non-hypervisor boot.

| Identity | Recorded value |
|---|---|
| Visible DT model / compatible | Apple MacBook Air (M1, 2020); `apple,j313`, `apple,t8103`, `apple,arm-platform` |
| Kernel release / build | `7.1.12-2-11.17-sep-ARCH`; `#1 SMP PREEMPT_DYNAMIC Thu, 01 Oct 2026 14:47:49 +0000` |
| Visible OS / kernel package | Arch Linux ARM; `linux-aurora 7.1.12.aurora2-11.17`; module `pkgbase=linux-aurora` |
| Installed image SHA-256 | `1d08d4153742e26d7012031452db79fe500cf376a84b07261fba59f97bf945e2` |
| Exported decompressed config SHA-256 | `84bb71434e905f3b1360142e075a89b0bccb5e5bd7ca82eb892a362512df260e` |
| Running kernel / installed `vmlinux` build ID | `bc3799e844d9c536bf01aef87c76c205b0e1a5d2` |
| DT-reported m1n1 stages 1 / 2 | `v1.6.1-dirty` / `v1.6.1-omarchy.aurora3` |
| DT-reported iBoot stages 1 / 2 | `mBoot-20457.1.29` / `iBoot-8422.141.2` |
| DT-reported OS / system firmware | `13.5` / `27.0` |
| DT-reported U-Boot | `2026.07` |

Firmware version strings are recorded observations, not source commits or artifact hashes. In particular, stage 1's dirty suffix leaves its source identity unresolved. The full booted FDT read returned `EACCES`. Raw boot arguments, package metadata, full configuration, kernel notes, source responses, installed image and complete command stdout/stderr remain in the private local packet, outside the public repository.

All eight CPUs were online. `apple_idle` used `menu`; each CPU exposed enabled `state1=CPU PD` with nonzero cumulative `usage` and `time`. The receipt retains all 16 state snapshots. `time` is software-accounted microseconds and `usage` is an entry count, sampled separately; neither provides simultaneous cluster-off intervals or an interval residency rate. Declared state1 latency/residency were 10/10000 microseconds, not measured transition costs. Both `apple-cpufreq` policies used `schedutil`, with related CPUs 0–3 and 4–7. Runtime `fast_switch_enabled` was not exposed by the checked paths and remains unknown.

At the inventory points, software power-supply reporting showed AC and both USB sources offline, battery discharging at 41%. This does not inventory USB devices or display state. Temperature readouts are retained with millidegree-Celsius units, but one sequential inventory does not establish a thermal trend or controlled background load. The collector itself consumes CPU and performs file/sysfs accesses; no matched-work, timing, occupancy or energy inference is made from these snapshots.

## Source verification and named prior baseline

The research checkout is the requested immutable revision `97163f91f8a6f99e79bb657b5f934af158e8d0a5`. Twelve fresh GitHub file responses were retained privately and their UTF-8 bytes checked against the returned Git blob IDs. Eight responses also matched the applicable SHA-256 entries in the prior [source comparison](raw/iconidentify-aurora-source-comparison.json). The new receipt lists every repository, revision, path, blob and content digest; this is a scoped file check, not a whole-tree comparison.

The checked old [Asahi](https://github.com/AsahiLinux/linux/blob/77cb8f24c2381a8abb7272d7bbdec548d6426a8a/drivers/cpuidle/cpuidle-apple.c), [Omacom](https://github.com/omacom/linux/blob/4ec597a7427da2cf03c899406b7997c875d4a9fb/drivers/cpuidle/cpuidle-apple.c), and [Aurora Silicon](https://github.com/aurora-silicon/linux/blob/1d2904fd3301c63620f07c81ae79f2486a81a9a6/drivers/cpuidle/cpuidle-apple.c) idle files again resolve to blob `3d2b804df8a2de18b8d8f031857b00d7198dab4c`. Their implemented returning deep WFI is the prior baseline, not a new contribution. The selected iconidentify release's [idle file](https://github.com/iconidentify/aurora-linux/blob/90a95335a49aec3a0045a76da140452ad6585eb3/drivers/cpuidle/cpuidle-apple.c) is a different blob, `67c7846111cf32dcac84627ec7671a67a981d10f`: the complete diff adds T8140 registration and a T8140-only WFI restriction. It does not alter the T8103 deep-WFI routine or its callback.

At that release pin, the [T8103 cpufreq descriptor](https://github.com/iconidentify/aurora-linux/blob/90a95335a49aec3a0045a76da140452ad6585eb3/drivers/cpufreq/apple-soc-cpufreq.c#L93-L100) leaves `verify_transition` unset. The [submission path](https://github.com/iconidentify/aurora-linux/blob/90a95335a49aec3a0045a76da140452ad6585eb3/drivers/cpufreq/apple-soc-cpufreq.c#L197-L259) polls the old command, performs the SET write, and conditionally polls afterward only when that flag is true. T8103's successful path therefore still returns without that post-write poll. This is public-source-permitted behavior, not disassembly of the running driver or proof that native BUSY overlaps WFI. Both driver files at the installer-attributed source `e11a8bc74cb8f9a690b9a6debe15962438dcc3c7` match the release's driver blobs. The installer attribution still does not verify the package's build recipe.

The unchanged observer patch (`205c28ba…`) fails its cpufreq hunk at line 174; the counter patch (`4d56b79a…`) fails its Apple SoC Makefile hunk at line 25. The receipt preserves exact patch digests, exit status 1, complete stdout/stderr and sparse-check scope. No patch was applied. The [concurrency review](linux-dvfs-idle-concurrency.md), [macOS command-order audit](mac-pmgr-command-order.md), [Omacom audit](omacom-linux-source-audit.md) and [Aurora report](aurora-cpu-idle.md) remain the comparison context. There is no novelty, defect, hardware-state or energy claim in this qualification.

## Evidence boundary and next work for #5

Evidence tiers are **public source**, **live software configuration** and **software accounting**. The build-ID check supplies artifact linkage; it is not instruction-level binary analysis. No native hardware-state or matched energy/wake tier has been reached. The running kernel may be native beneath the container, and its release/config/image/build-ID agreement strongly supports the visible artifact attribution; independent boot-route and source-to-binary provenance remain unresolved. Hardware may already serialize DVFS with collapse, or a command may complete before WFI; these alternatives remain compatible with every observation here.

Continue #5 with source/build-recipe qualification and a separate port of the default-off observer/counter helper, preserving the Asahi patches. Use the retained current configuration, review the actual target's mappings/lifetime and generated code, and complete the target build checks before any installation. Then obtain operator authorization for a native instrumented boot and root capture under [NATIVE-RUN](../experiments/linux-apsc-observer/NATIVE-RUN.md), with a verified stock fallback, pre/post counter exchanges, records-only/MMIO controls and raw loss counts. A stock tracepoint baseline can help measure software timing but cannot replace the missing raw command samples. Neither a successful future port nor a stock trace would resolve #5's BUSY question on its own.

## Subsequent port preparation

Later on the same date, the operator reported installing the current kernel with `curl -fsSL https://github.com/iconidentify/aurora-linux/releases/latest/download/install-aurora-sep.sh | bash`. This is a reported installation route, not a retained historical script. A fresh latest-release API read still selects `sep-7.1.12.aurora2-11.18`; the pinned script's bytes match the release asset's declared SHA-256 `845103d3bff8644bdb7dfe897a4a32cae06878bb9d77a8822247cc1bf1e1e11c`, and its constants select the observed `7.1.12.aurora2-11.17` package. The source-comment attribution and unresolved original kernel build recipe retain the boundary above. The script was inspected as data and was not executed by this research work.

The separate [Aurora port](../experiments/aurora-apsc-observer/README.md) now applies cleanly to all touched source files at `90a95335…` and passes preliminary GCC object compilation using a private copy of the installed prepared headers. Its [receipt](../experiments/aurora-apsc-observer/build-receipt.json) verifies unchanged disabled driver instructions/relocations and the complete deep-WFI bytes with the observer enabled. It also documents the actual strong stack-protection and debug-preemption calls that differ from the older generic Clang checks. The original failed patch checks and Asahi artifacts above remain intact. This is offline port progress, not full-tree Kconfig/final-link acceptance, installation, native APSC events, or a resolution of #5.

The subsequent [whole-source receipt](../experiments/aurora-apsc-observer/full-source-receipt.json) verifies all 94,067 files and modes against the selected Aurora Git tree. [Full-tree Kconfig acceptance](../experiments/aurora-apsc-observer/full-config-receipt.json) preserves the exported config byte-for-byte in the pristine variant; the candidate changes only both instrument options to `y` and `LOCALVERSION` to a distinctive research release. The [complete-source object checks](../experiments/aurora-apsc-observer/source-object-receipt.json) also pass, with the enabled objects' executable sections and relocations identical to the preliminary ones. Final Image/modules/DTB compilation is tracked separately in the [build status](../experiments/aurora-apsc-observer/full-build-status.json); its success must not be inferred from the completed object stages.

The operator then confirmed a normal restart into Omarchy after installation. This supports a normal native boot route beneath the container session; protected boot artifacts and the dirty stage-1 identity still need qualification. During full compilation, software battery reporting reached 15% while discharging with external sources offline. Only the task's compiler process group was temporarily suspended. After the operator connected power, reporting showed external power online and battery charging at 18%, and that same compiler group resumed. These are preparation conditions, not a controlled power experiment or energy result.

A separate [stock binary seam receipt](raw/native-linux-stock-binary-seam-20261002.json) adds instruction-level evidence for the installed `vmlinux` whose build ID matches the running notes. Its complete 100-byte deep-WFI routine matches the pinned baseline and ported objects (`c8fd716f…`). Its own DWARF places `verify_transition` at byte offset 1 in the 56-byte descriptor; raw T8103/T8140 descriptor bytes are respectively 0/1 there. A changed routine, descriptor value, layout, or artifact linkage would refute this scoped binary result. It does not trace descriptor dispatch, an executed post-write branch, command BUSY or WFI overlap, and does not recover the original PKGBUILD. Public-source, local-binary and software-accounting evidence still remain separate from #5's missing native hardware timeline.

## Completed build, protected boot check and separate installation

The [full build receipt](../experiments/aurora-apsc-observer/full-build-receipt.json) now records successful complete-source Image/modules/DTB compilation and linked instruction checks under the retained target settings. The candidate is `7.1.12-ARCH-apsc-20261002`; its embedded config matches the reviewed candidate exactly, both late initcalls resolve, and the complete deep-WFI bytes remain identical. All 1,867 matching modules and the corrected encrypted-root EFI bundle are verified. The first initramfs attempt omitted Omarchy drop-ins and failed a boot-content check; that attempt and final warnings are retained rather than reporting generation exit zero as boot readiness.

The operator authorized protected read-only inspection, then explicitly authorized the remaining task work. The [boot receipt](raw/native-linux-boot-qualification-20261002.json) retains the full current FDT hash and reviewed CPU/domain/resource values. Limine 12.9.1 identifies the current stock entry and one-shot entry support. The current configured EFI bundle contains the exact already-identified kernel/initramfs; all three configured bundles match their documented BLAKE2b hashes. The first collector used the wrong hash algorithm; original SHA-512 comparisons remain private and corrected checks are recorded. This strengthens native boot attribution beneath the container. Snapshot boot success and dirty stage-1 source remain unresolved.

The [installation receipt](../experiments/aurora-apsc-observer/deployment-receipt.json) records the separate `Aurora-APSC-research` entry and distinct image/module set. Stock files and default entry are preserved. Automatic approval review rejected an unrestricted root shell; the read-only checks and scoped installation command were separately accepted. No firmware/security/power-policy change or APSC capture was performed during installation. A first research-kernel boot and the declared matched native windows are still required; #5 remains open.

## First restart selected stock

Before the authorized restart, the EFI one-shot request was successfully
written and read back as `Aurora-APSC-research`. The [restart outcome](../experiments/aurora-apsc-observer/restart-outcome-receipt.json)
then records the running stock release and selected `Omarchy.linux-aurora`
entry. The research entry appears in the current loader-entry list, but the
one-shot variable is absent. The operator did not notice an error or menu
selection. Available current/prior kernel journals both identify stock;
the retained pstore directories are empty. These observations do not
establish that the research kernel was attempted, crashed, or booted.

Read-only checks at 11:42 UTC verify the stock artifact hashes and test EFI
bundle SHA-256/BLAKE2b entry hash. The original stock configuration prefix
and default remain intact. The post-restart config differs from the installed
proposal only by removing one blank line before the research entry. This is
live software boot/configuration evidence, with zero native APSC events.
The unresolved selection result leaves the overlap hypothesis untested.

Version-matched [Limine source](https://github.com/Limine-Bootloader/Limine/blob/c82c3708b3304be806b2492dc2ce34e219c6f989/common/lib/bli.c#L267)
deletes a one-shot request when reading it, and its [menu path](https://github.com/Limine-Bootloader/Limine/blob/c82c3708b3304be806b2492dc2ce34e219c6f989/common/menu.c#L1851)
resolves the request before applying the configured default. This is a
source explanation of one possible disappearance, not proof of the installed
bootloader's behavior or variable persistence across this restart. Select
the research entry directly at the menu, then verify the running candidate
and helper readiness before any declared native window.

## Research boot and driver regression

The operator later selected `Aurora-APSC-research` directly. The retained
kernel log starts with the distinctive `7.1.12-ARCH-apsc-20261002` release
at 17:16:55 IST. The operator reported no Wi-Fi device and nonworking
brightness controls. The [driver regression receipt](../experiments/aurora-apsc-observer/driver-regression-receipt.json)
links four raw private journal files and the local restoration checks.

The cause is visible in the *preceding stock boot*: at 13:39:18–24 IST,
`linux-modules-cleanup.service` found the research module directory neither
current nor pacman-owned, copied it to its cleanup area, then removed it.
The research boot consequently lacked matching modules on the root
filesystem. Its logs report failed loads for `crypto_user`, `i2c_dev`,
`pkcs8_key_parser`, and `apple-sep`, plus a deferred Apple DCP probe needing
the display crossbar. The stock control boot initializes Wi-Fi and Apple
display drivers. This is strong software evidence for the reported failures;
it does not prove each device's complete failure path or exclude an
additional issue once modules are restored.

The preserved build stage supplied all 1,867 matching `.ko` files. A local
package now owns the complete research module directory. After copying and
byte-checking the modules, pacman registration and metadata alignment,
`pacman -Qkk` reports 2,244 total files and zero altered files. Dry-run
dependency checks resolve `brcmfmac`, `appledrm`, the display crossbar and
`apple-sep`. The registration avoided automatic boot-bundle regeneration;
the stock boot default remains the fallback. No post-repair research boot or
APSC trace has yet been captured. The next falsifiable check is whether Wi-Fi
and brightness both work in a fresh research boot. #5 remains open.
