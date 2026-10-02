# Aurora T8103 observer port

This separate port and native run address [ticket #5](https://github.com/malik-na/m1-cpu-idle-research/issues/5)
on the operator's iconidentify Aurora kernel. It targets
[`90a95335a49aec3a0045a76da140452ad6585eb3`](https://github.com/iconidentify/aurora-linux/tree/90a95335a49aec3a0045a76da140452ad6585eb3),
the source pin selected by the [release audit](../../notes/iconidentify-aurora-kernel-target.md).
It preserves the original [Asahi observer](../linux-apsc-observer/README.md)
and [counter helper](../linux-counter-qualification/README.md) patches.

Both ports apply cleanly to all six existing files they touch at that pin.
The subsequent [whole-tree receipt](full-source-receipt.json) verifies all
94,067 files and modes against the pinned Git tree and clean application
of both patches to a separate full checkout.
Whole-source [Kconfig checks](full-config-receipt.json) and
[object builds](source-object-receipt.json) also passed. The pristine config
is byte-identical to the exported target config; the enabled config changes
only the two instrument options and a distinctive release name. The four
enabled objects' executable/relocation bytes match the preliminary builds.
Preliminary GCC object builds against a private copy of the installed
prepared headers succeeded with the hooks enabled and disabled. Disabled
driver instructions and relocations match the pristine drivers; the complete
100-byte deep-WFI routine matches in all three variants. Those preliminary
checks are **source and local object evidence**. The subsequent
[full build receipt](full-build-receipt.json) records successful
Image/modules/DTB compilation, linked instruction checks, and a matching
private module/initramfs/EFI bundle. Those build stages alone provide no
native capture, BUSY result, or energy measurement. The later native result
is recorded below. The [build record](BUILD-VALIDATION.md)
and [byte receipt](build-receipt.json) state the exact scope.

## Apply to the pinned source

On a fresh private checkout at the exact revision, apply the observer and
then the counter helper. Set `aurora_patch_dir` to this directory:

```sh
: "${aurora_patch_dir:?set the directory containing the reviewed port patches}"
git rev-parse HEAD
git apply --check "$aurora_patch_dir/0001-aurora-t8103-apsc-observer.patch"
git apply "$aurora_patch_dir/0001-aurora-t8103-apsc-observer.patch"
git apply --check "$aurora_patch_dir/0002-aurora-t8103-counter-qualification.patch"
git apply "$aurora_patch_dir/0002-aurora-t8103-counter-qualification.patch"
```

The options remain built-in, default-off `ARM_APPLE_APSC_OBSERVER` and
`APPLE_COUNTER_QUALIFICATION`. The native candidate used the qualified
target configuration, explicitly enabled both options, retained its existing
debug/security settings, and received a distinctive kernel release name.
Enabling options with compiler defines in the preliminary build does not
validate their Kconfig integration or establish a bootable candidate. The
subsequent complete-source configuration checks accept both options. The
final linked candidate is `7.1.12-ARCH-apsc-20261002`; its 1,867 staged modules
all match that release. Installation and native checks have separate records.

## Integration differences

The selected Aurora cpufreq driver adds pstate-range checks, a retained
transition-failure check, and optional verification for T8140. This port
preserves every one of those branches. It records a failed preceding BUSY
poll before the existing error handling and wraps the original command
write exactly once. T8103's descriptor leaves `verify_transition` unset;
the port adds no post-write poll. Early range/retained-failure rejection and
the optional verified no-op return are not command submissions and produce
no DVFS record. The existing new Apple SoC Makefile entries are retained
when adding the counter helper.

The observer C source, public header and counter-helper C source are
byte-identical to the original Asahi patches. Idle hooks and the scalar
token placement are unchanged. Their CSV/status ABIs, one-shot capture
limits, DT mapping requirements and bounded buffers remain as documented
in the original experiments. The existing decoders apply without changes.

For this Aurora port, `requested_index` and `requested_pstate` describe the
incoming table request after the existing range checks. This driver has
no old fallback clamp; the original observer README's clamp discussion
describes its Asahi base. The submitted raw command remains authoritative.

## Actual-configuration review and native outcome

The installed configuration uses GCC, strong stack protection,
`DEBUG_PREEMPT=y`, 16 KiB pages and Rust. Generated code differs from the
earlier generic Clang build: observer hooks have a failure-only
`__stack_chk_fail` call, and counter callbacks call `debug_smp_processor_id`.
The hooks remain outside the context-tracking idle region; the counter
CPU check occurs outside its b0/b1 stamp pair. The [linked review](full-build-receipt.json)
retained those stack-failure and debug-CPU-check calls. The target
configuration was not weakened to reproduce an earlier call-free
disassembly result.

The [protected boot inspection](../../notes/raw/native-linux-boot-qualification-20261002.json)
links the configured current EFI bundle to the stock image/initramfs and
the operator-reported successful boot. All three configured bundle hashes
match; the two snapshot bundles have not been boot-tested by this work.
The [native protocol](../linux-apsc-observer/NATIVE-RUN.md) required
a qualified native boot, verified fallback, operator authorization for
installation/reboot/root capture, pre/post clock exchanges, matched
inactive/records-only/MMIO controls, adequate opportunities and retained
loss counts. A BUSY sample at the C seam means pending command state before
context tracking and WFI; it does not prove BUSY at the WFI instruction,
physical cluster collapse, a defect, or a benefit. The first native
[pilot](native-pilot-receipt.json) contains a complete baseline and a
records capture invalidated by CPU-0 ring overflow. It has no MMIO sample
or complete-stream overlap result; it did not answer #5 on its own.

The [deployment receipt](deployment-receipt.json) records the explicitly authorized separate `Aurora-APSC-research` entry. The working stock files and default remain intact. Installation is not a test-boot or capture result.

The [first restart outcome](restart-outcome-receipt.json) records a stock
boot despite successful pre-restart [one-shot readback](one-shot-selection-receipt.json).
The research entry remains listed, its bundle/hash checks pass, and the stock
default is preserved. The one-shot request is absent after restart; why
the stock entry was selected remains unresolved. Empty retained pstore does
not exclude a boot failure. The later research boot is recorded below and
in the predeclared [native plan](NATIVE-PLAN.md).

A later direct menu selection did boot the research release. Wi-Fi and
brightness then failed. The [driver regression receipt](driver-regression-receipt.json)
ties this to Omarchy's earlier cleanup of the manually installed, unowned
module directory. The matching module tree has now been restored as a local
pacman-owned package; all 1,867 module bytes and 2,244 package paths pass
their checks. The operator then reported working Wi-Fi and brightness on
the research boot, and read-only checks found `wlan0`, the panel backlight
and loaded drivers. The [adaptive plan](NATIVE-PLAN.md) retains the failed
records packet. The [capacity revision receipt](capacity-revision-receipt.json)
qualifies a larger-buffer image and a separate boot entry. The completed
[three-boot A/B/C result](NATIVE-RESULT.md) has loss-free B/C streams and
one native cluster-1 APSC BUSY sample at the C pre-WFI hook after a
same-CPU SET. Its [public evidence packet](native-evidence/README.md)
preserves numerical raw streams, statuses, workload and counter records,
bounded snapshots, acquisition hashes and reproducible decoder outputs.
The sample is a conditional software-final-entrant candidate only under
the predeclared, unproven 240-tick cross-CPU clock-error assumption. It
does not establish BUSY at WFI, a physical power state, energy or a defect.
The [WFI-seam extension plan](WFI-PLAN.md) and
[source delta](0004-aurora-apsc-wfi-first-attempt.patch) predeclare a
closer, first-attempt probe and stricter paired-opportunity rules. That
variant has no native result yet.
The [ABI 2 build receipt](wfi-build-receipt.json) records a separate
`-wfi` release, matching staged modules, a checked initramfs and the
linked first-attempt instructions. It is a build result only; the new
entry has not been booted or measured.
