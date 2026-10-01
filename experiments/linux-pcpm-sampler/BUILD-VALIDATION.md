# PCPM sampler build validation

The exact [patch](0001-t8103-pcpm-sampler.patch), SHA-256
`713c7590d5c88e0c03ce9c2a48a24ae8f3b423618cd6986c537dbc5437f4978c`,
passed standalone and combined application checks and ARM64 object builds on
2 October 2026. No code was installed, booted, or executed on the M1. These are
source/compile/instruction-review results, not a native PCPM measurement.

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
[observer receipt](../linux-apsc-observer/BUILD-VALIDATION.md). All eight tool
fingerprints were rechecked against the previously verified toolchain record.
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
They are not qualified target boot configurations. Changed instrumentation,
compiler, LTO, DT, or owner implementation requires renewed review.

## Compilation and instruction evidence

All variants built `drivers/soc/apple/`, `drivers/mfd/syscon.o`,
`drivers/cpuidle/cpuidle-apple.o`, and `drivers/cpufreq/apple-soc-cpufreq.o`.
Combined additionally built `drivers/cpuidle/apple-apsc-observer.o`.
The enabled Apple archive contains the sampler; combined contains both the
sampler and counter helper. Disabled contains neither, and has no sampler object.
The new existing-map accessor symbol exists only with the sampler enabled.
All completed compile logs contain no compiler `warning:` or `error:` lines.

Independent source readback identified and corrected an initial draft's overly
restrictive MPIDR Aff2 guard: pinned P-core DT IDs `0x10100`..`0x10103` have Aff2=1.
The initial draft would have rejected the target before reading. The corrected
exact patch above was reapplied and rebuilt in all three variants, and the decoder
fixture explicitly rejects the old incorrect affinity assumption.

| Final standalone patched source | SHA-256 |
| --- | --- |
| `drivers/soc/apple/apple-pcpm-sampler.c` | `244a9032298811dc4d66f56f89015167abf21bce771db6f689748060bcf6590c` |
| `drivers/mfd/syscon.c` | `a903e342814c1c8d7bb941e9799c0d4c57e028f1791d05b3381ea5ecb1842df5` |
| `include/linux/mfd/syscon.h` | `cd230f9f269b9ad84e29611ad9e5d5fc51c7ce12931257fc237515b7e63c9552` |
| `drivers/soc/apple/Kconfig` | `5621438f4ae36ee44c8c800222d700a99de821b1cc07300aefd490893332d785` |
| `drivers/soc/apple/Makefile` | `cc4194288b23523ee68e3ee54f5d4d57ddc0d56c3f0616c25f8aa84e8adfc8c4` |

| Variant / object | SHA-256 |
| --- | --- |
| Enabled sampler | `c5240851f043bb4d09c7b28bf76d811f7ee9072c78f47c3036147ff708867bb8` |
| Combined sampler | `a7e8b856dbb773180cb882ed4b50cdebd885df69aa3b015f6f317b821b5430dd` |
| Enabled syscon | `dc711093af48b22737f6452e01dedee20a67a210454cbc4a6bd5a05599accd0a` |
| Disabled syscon | `443dd8aa8af1918ed518eafd7c6661922025a594f3023d0ad73c4c6078e089df` |
| Combined syscon | `d5f33e2692e80403d126700423393401c02e8119900161f9f2214c888ba4c879` |

Objects are AArch64 relocatable ELF. Whole-object hashes include directory-dependent
DWARF and are artifact identifiers, not a promise of reproducible bytes elsewhere.
The enabled and combined sampler have byte-identical executable sections and
associated relocation records:

| Section | Bytes | SHA-256 |
| --- | ---: | --- |
| `.text` | 5292 | `6be4288b8a584798419a99a2d305c4a5cf97d46d728e773c101d1cdf31e6620e` |
| `.rela.text` | 10632 | `023142f5f86518c8a35b36fc42504722cafc6f70ea9e9d46fbaef62f3c9866a5` |
| `.init.text` | 304 | `2d1246749173a7d4cd7878a13d3bc7d83afce26dc95a07b2bb43fd5d53564acd` |
| `.rela.init.text` | 552 | `7c91f86d038d399409d101d4567c02f9b73298c1cf1f9835e8f9b9616ddb7b54` |

The original 100-byte `apple_cpu_deep_wfi` routine is identical in pristine,
standalone enabled, disabled, and combined objects, SHA-256
`c8fd716fccb949e9f35aa2937a87787942b39f0b5df5e088d46f88253479b88c`.
The PCPM patch does not change the idle or cpufreq source. The combined observer
instrumentation remains governed by its own review boundary.

In the sampler's final `.text`, `pcpm_worker` starts at `0xac4`. Its selected sample
bracket calls `ktime_get` at `0xc50`, conditionally calls `regmap_read` at `0xc9c`
with the literal register offset `0x48` loaded at `0xc8c`, then calls `ktime_get`
at `0xcb0`. There is one read call site and no retry on read failure. The sleep
call is `schedule_hrtimeout_range` at `0xbec`. The object contains no MSR, WFI, or
WFE instruction; source/relocation review finds no new mapping, register-write,
clock-enable, PM-reference, remote SMP-call, or idle/governor operation.
This describes the sampler itself: ordinary kernel scheduling and regmap services
have observer effects and are not claimed inert.

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

## Build reproduction and remaining gap

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

Kbuild also generated normal preparation artifacts and VDSOs. No final `vmlinux`
link, module `modpost`, native boot, debugfs capture, calibrated PCPM state,
clock-domain alignment, or energy result is claimed. Build success cannot close
the [native calibration ticket](https://github.com/malik-na/m1-cpu-idle-research/issues/6).
