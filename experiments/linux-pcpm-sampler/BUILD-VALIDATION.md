# PCPM sampler ABI 2 build validation

The build and object results below apply to the **former** patch SHA-256
`5a737c38f0f9856147ac03959f5ebc7ed202c49ad54aa9e09db971d8d839a4ee`,
which passed standalone and combined application checks and ARM64 object builds on
2 October 2026. A later audit found that version would reject the real T8103
PMGR mini bank before sampling. The [current patch](0001-t8103-pcpm-sampler.patch),
SHA-256 `4a7fc879a3ed377d813e01f8986306fc62679679d39718fe83183ae466ab3b56`,
corrects selection and passes a host check of the actual C function against
both pinned DTS resource sets, plus `git apply --check` on the exact Aurora
source. The corrected patch subsequently passed a complete Aurora ARM64 build
and linked-code review, recorded separately in the
[3 October build receipt](aurora-wfi-pcpm-build-receipt.json). The older Asahi
object hashes and instruction locations below apply only to the former patch;
the new receipt identifies the corrected compiled bytes. The separate new
image and module package were later installed under guarded preflight; the
[deployment receipt](aurora-wfi-pcpm-deployment-receipt.json) records that
state. The new image subsequently booted with Wi-Fi and brightness working.
The [first records preflight](pcpm-records-preflight-incident-receipt.json)
stopped before acquisition, then a [corrected records-only run](NATIVE-RECORDS-RESULT.md)
completed without a PCPM register read.

This receipt covers the new [ABI 2](ABI.md) counter-bracket implementation.
The prior ABI 1 patch and its validation remain preserved at
[commit cb0b41e62ad500225c1a06bfc827b2fd8e24b1ec](https://github.com/malik-na/m1-cpu-idle-research/blob/cb0b41e62ad500225c1a06bfc827b2fd8e24b1ec/experiments/linux-pcpm-sampler/BUILD-VALIDATION.md).
New source and output directories were used; those prior artifacts were retained.

## Pinned inputs

Source is AsahiLinux/linux
[`77cb8f24c2381a8abb7272d7bbdec548d6426a8a`](https://github.com/AsahiLinux/linux/tree/77cb8f24c2381a8abb7272d7bbdec548d6426a8a).
Two fresh private source copies were extracted from its immutable archive,
rechecked SHA-256
`aef64ada57e626996093c066bdacb595672cccb0b18fed661363fdbde48f387c`.
Earlier reference sources and builds were retained. The combined copy received,
in order, the [APSC observer](../linux-apsc-observer/0001-t8103-apsc-observer.patch),
the [counter helper](../linux-counter-qualification/0001-t8103-counter-qualification.patch),
and the PCPM patch. All three applied successfully; the PCPM Kconfig/Makefile
insertions use different anchors from the counter helper.

The observer patch hash is
`205c28ba1830cd794c6c59efff0b3aaeb6102335f48a7f98515a05704fbf378a`;
the counter patch hash is
`4d56b79a6de142726602085466f7ba8835d1d6f5737f02ffc3fd776f01b77b7b`.

The x86-64 Linux cross-build host used Clang/LLVM 22.1.8, GNU Make 4.4.1,
`ARCH=arm64 LLVM=1`, and the isolated LLD/bc tools described in the
[observer receipt](../linux-apsc-observer/BUILD-VALIDATION.md). Clang and Make version strings were rechecked for this build.
There was no system package installation or privileged build.

All configurations start with the pinned arm64 defconfig. The standalone enabled
variant adds `APPLE_PCPM_SAMPLER=y`; disabled leaves it unset. Combined also enables
`APPLE_COUNTER_QUALIFICATION=y`, `ARM_APPLE_APSC_OBSERVER=y`, and built-in
`ARM_APPLE_SOC_CPUFREQ=y`. `olddefconfig` accepted each variant. Prerequisites
include `APPLE_PMGR_PWRSTATE=y`, `MFD_SYSCON=y`, `SMP=y`, and `DEBUG_FS=y`.

| Variant | `.config` SHA-256 |
| --- | --- |
| Standalone enabled | `13be3a73b57a82cd58634d32af3841b1eca9b2a8a55041ce2cea3af7487d5cef` |
| Disabled | `ab5cfe9fac9b94a8052b88748cff2d7a849ecc06027eeb4a8e9d55c37a1246f6` |
| Combined | `f244298af1cbd77e5252a05150b2a4df570847ef2c6646518d967f62866d203d` |

These are generic compile configurations with `NR_CPUS=512`, 4 KiB pages,
`PREEMPT=y`, `PREEMPT_RCU=y`, `LTO_NONE=y`, and no FTRACE/KASAN/UBSAN/KCOV.
They enable `ARM_ARCH_TIMER_OOL_WORKAROUND=y` and
`ARM64_ERRATUM_858921=y`, so the worker preflight rejection path for an installed
physical-read workaround is compiled. They are not qualified target boot configurations. Changed instrumentation,
compiler, LTO, DT, or owner implementation requires renewed review.

## Compilation and instruction evidence

All variants built `drivers/soc/apple/`, `drivers/mfd/syscon.o`,
`drivers/cpuidle/cpuidle-apple.o`, and `drivers/cpufreq/apple-soc-cpufreq.o`.
Combined additionally built `drivers/cpuidle/apple-apsc-observer.o`.
The enabled Apple archive contains the sampler; combined contains both the
sampler and counter helper. Disabled contains neither, and has no sampler object.
The new existing-map accessor symbol exists only with the sampler enabled.
All completed compile logs contain no compiler `warning:` or `error:` lines.

The ABI 1 qualification, scheduling, read-only mapping, and request parser remain
in the ABI 2 source. In particular, pinned P-core DT IDs `0x10100`..`0x10103` retain
the corrected Aff2=1 requirement. The additional counter metadata gate precedes
the schedule and all raw stamps/MMIO. No remote metadata call or register write
was introduced.

| Final standalone patched source | SHA-256 |
| --- | --- |
| `drivers/soc/apple/apple-pcpm-sampler.c` | `f4916f7f8f6d26c971b62dc052db89ff21ca66afad99d20357a074dc91fb9a97` |
| `drivers/mfd/syscon.c` | `a903e342814c1c8d7bb941e9799c0d4c57e028f1791d05b3381ea5ecb1842df5` |
| `include/linux/mfd/syscon.h` | `cd230f9f269b9ad84e29611ad9e5d5fc51c7ce12931257fc237515b7e63c9552` |
| `drivers/soc/apple/Kconfig` | `5621438f4ae36ee44c8c800222d700a99de821b1cc07300aefd490893332d785` |
| `drivers/soc/apple/Makefile` | `cc4194288b23523ee68e3ee54f5d4d57ddc0d56c3f0616c25f8aa84e8adfc8c4` |

| Variant / object | SHA-256 |
| --- | --- |
| Enabled sampler | `a495613df8d69681dbed4bac489701501e6f0a34f80b472acabc47c3e11548be` |
| Combined sampler | `aaacc17b8882e1bf9096a8ecab99c11a036c5578a394e0f4007c29be47ab56a2` |
| Enabled syscon | `aa973ed2dd3580556b924127a2ab92aee0bc93ddcddf1578deb6064d215e66f7` |
| Disabled syscon | `7f378e4811e6c8ede69c8ebf16184a7c647d42710e384186aacf0acb6feeb6ca` |
| Combined syscon | `093cc336e0c34c1aaf80d312e0be772a9c423e9e74bde5fbe9ddcb460385a093` |

Objects are AArch64 relocatable ELF. Whole-object hashes include directory-dependent
DWARF and are artifact identifiers, not a promise of reproducible bytes elsewhere.
The enabled and combined sampler have byte-identical executable sections and
associated relocation records:

| Section | Bytes | SHA-256 |
| --- | ---: | --- |
| `.text` | 6364 | `a699cc92d177bfb5230e88081c88c601f59b3752541c491d8246ce8f019a7bc7` |
| `.rela.text` | 13560 | `e757c702fe1639717f940bf3b5853e3bf8113dee687d8f57e3e6835e59de4a91` |
| `.init.text` | 304 | `2d1246749173a7d4cd7878a13d3bc7d83afce26dc95a07b2bb43fd5d53564acd` |
| `.rela.init.text` | 552 | `4d09f5a3245899c6716bc83d7f1e69357b1378c84b3bc002ac06d95321aaad36` |

The original 100-byte `apple_cpu_deep_wfi` routine is identical in pristine,
standalone enabled, disabled, and combined objects, SHA-256
`c8fd716fccb949e9f35aa2937a87787942b39f0b5df5e088d46f88253479b88c`.
The PCPM patch does not change the idle or cpufreq source. The combined observer
instrumentation remains governed by its own review boundary.

In the sampler's final `.text`, `pcpm_worker` starts at `0xac4`. Metadata reads
are `CNTFRQ_EL0` at `0xb34`, `CNTKCTL_EL1` at `0xb44`, and `ID_AA64MMFR0_EL1`
at `0xb50`, followed by the worker-local workaround inspection and gate. The
selected row has these instruction/relocation locations:

| Operation | Object location |
| --- | --- |
| Before counter stamp | `0xd54` DSB SY; `0xd58` ISB; `0xd5c` MRS CNTPCT; `0xd60`..`0xd68` counter-derived EOR/ADD/dependent-load; `0xd6c` DSB SY |
| Nanosecond before | `0xdb4` call relocation to `ktime_get` |
| Optional PCPM read | Literal offset `0x48` at `0xe34`; sole `regmap_read` call at `0xe44` |
| Nanosecond after | `0xe58` call relocation to `ktime_get` |
| After counter stamp | `0xe68` DSB SY; `0xe6c` ISB; `0xe70` MRS CNTPCT; `0xe74`..`0xe7c` counter-derived dependency; `0xe80` DSB SY |
| Monotonic sleep | `0xce0` call relocation to `schedule_hrtimeout_range` |

The compiler retained both ECV replacement sequences: NOP/MRS CNTPCTSS at
`0x18c8`/`0x18cc` and `0x18d0`/`0x18d4`. Runtime alternatives select the effective
counter reader; exported `ecv_alternative` records the final kernel decision.
These object offsets describe this build, not runtime kernel virtual addresses.

The read is conditional on matching initial worker CPU and absence of an
already detected previous-row counter/nanosecond reversal. Both timestamp
brackets are retained on success and read failure. Records mode has the same
counter and nanosecond bracket overhead without the optional map read. Source
and instruction inspection find one read call site, no retry on read failure,
and no MSR, WFI, or WFE instruction. There is no new mapping, register-write,
clock-enable, PM-reference, remote SMP-call, or idle/governor operation in the
sampler. Ordinary scheduling, barriers, counters, and regmap services still have
observer effects; none is claimed inert.

## Host parser boundary check

[check_control_parser.py](check_control_parser.py) extracts the actual
`parse_request` function from the published patch and compiles it with host type,
u32 conversion, and overflow substitutes. It does not duplicate the parser's
control logic. On Apple Clang 21.0.0 (`clang-2100.3.34.2`), all 31 cases passed
with AddressSanitizer and UndefinedBehaviorSanitizer enabled. They cover valid
limits, decimal overflow, negative/signed tokens, whitespace, extra/missing
tokens, final newline handling, phase bounds, and the ten-second nominal budget.
This does not test kernel `copy_from_user`, capability checks, debugfs lifetime,
worker timing, register access, or kernel error paths.

```sh
python3 experiments/linux-pcpm-sampler/check_control_parser.py
python3 -m unittest discover -s experiments/linux-pcpm-sampler -p 'test_*.py' -v
```

## Historical Asahi build reproduction and remaining gap

Use fresh private source/output directories and the immutable archive above.
Set `pcpm_source` to a pristine extracted tree and `pcpm_output` to a new build
directory; point PATH/library search at the validated toolchain as needed.

```sh
: "${pcpm_source:?set the extracted pinned source path}"
: "${pcpm_output:?set a fresh build output path}"
git -C "$pcpm_source" apply --check /path/to/0001-t8103-pcpm-sampler.patch
git -C "$pcpm_source" apply /path/to/0001-t8103-pcpm-sampler.patch
make -j4 -C "$pcpm_source" O="$pcpm_output" ARCH=arm64 LLVM=1 defconfig
"$pcpm_source/scripts/config" --file "$pcpm_output/.config" --enable APPLE_PCPM_SAMPLER
make -j4 -C "$pcpm_source" O="$pcpm_output" ARCH=arm64 LLVM=1 olddefconfig
make -j4 -C "$pcpm_source" O="$pcpm_output" ARCH=arm64 LLVM=1 \
  drivers/soc/apple/ drivers/mfd/syscon.o \
  drivers/cpuidle/cpuidle-apple.o drivers/cpufreq/apple-soc-cpufreq.o
llvm-ar t "$pcpm_output/drivers/soc/apple/built-in.a"
llvm-objdump -dr "$pcpm_output/drivers/soc/apple/apple-pcpm-sampler.o"
```

For disabled coverage, use another fresh output and leave the sampler unset.
For combined coverage, apply the observer and counter patches before PCPM,
enable all three options plus built-in Apple cpufreq, and build the observer
object in addition to the targets above.

For this historical Asahi build, Kbuild also generated normal preparation artifacts
and VDSOs. It had no final `vmlinux` link or module `modpost`.

## Corrected Aurora full build, 3 October 2026

The [sanitized build receipt](aurora-wfi-pcpm-build-receipt.json) fixes the
copied working WFI source tree, corrected patch, patched tree, target
configuration, complete `Image modules dtbs` outputs, linked GNU Build-ID,
module inventory and checks. The Aurora source commit inherited from the
prior WFI receipt is `90a95335a49aec3a0045a76da140452ad6585eb3`; the
copied and patched source-tree SHA-256 values are
`10fcd125fbf18bf8b88c9f5a543aee9be7bc57e29e81336c62297d8ec79056dd`
and `9733d6cb7f1fb8bed30bbaffc6a7b22a42b68dac2acc636fe2125c3faed1d19f`.
The sole added configuration option relative to the working WFI build is
`CONFIG_APPLE_PCPM_SAMPLER=y`; candidate configuration SHA-256 is
`f4df15bf0c94e82210a503c91a9dd408b848d98aed45b0a2a09d691efbcf70a5`.
The release is `7.1.12-ARCH-apsc-20261002-wfi-pcpm` and linked Build-ID is
`83a213307311f91eefb44d70718db21fea3e067c`.

The first full `-j4` attempt stopped at the unrelated `usb8xxx.o` target
without a diagnostic that established the cause. That target passed a focused
`-j1` retry; a full `-j2 Image modules dtbs` retry then exited successfully
with no warning or error lines. The final Image, `vmlinux`, J313 DTB and all
1,867 matching-release modules are hash-pinned in the receipt. Static checks
found one sampler `regmap_read` relocation, zero `regmap_write` relocations,
and no sampler WFI or MSR instruction. The linked WFI seam retained its
previously reviewed probe shape. Source-derived selector, extracted-parser
and decoder tests passed 14, 31 and 49 cases respectively.

The full build establishes local source/configuration-to-binary linkage for
this candidate. The later guarded deployment establishes installation, and
live release/Build-ID/config and device checks establish a booted candidate.
The records-only run qualified the existing internal clockless PMGR regmap
on that boot. It made no register read, so these records do not establish
read success, observer effects, calibrated PCPM state, a cross-CPU
clock bound, physical rail state or energy benefit.
Those gates remain open in the
[native calibration ticket](https://github.com/malik-na/m1-cpu-idle-research/issues/6).
