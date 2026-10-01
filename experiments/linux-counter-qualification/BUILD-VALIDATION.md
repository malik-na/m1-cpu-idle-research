# ARM64 counter-helper build validation

The exact [counter-qualification patch](0001-t8103-counter-qualification.patch),
SHA-256 `4d56b79a6de142726602085466f7ba8835d1d6f5737f02ffc3fd776f01b77b7b`,
passed `git apply --check` and ARM64 Kbuild compilation on 2026-10-01.
The helper compiled both independently and together with the existing
[APSC observer](../linux-apsc-observer/README.md). Its disabled configuration
excluded the helper from the Apple SoC archive. These are object-build and
manual instruction-review results; no helper was installed, booted or run
on the M1 target.

## Source, tools and configuration

The source pin is AsahiLinux/linux
[`77cb8f24c2381a8abb7272d7bbdec548d6426a8a`](https://github.com/AsahiLinux/linux/tree/77cb8f24c2381a8abb7272d7bbdec548d6426a8a).
Fresh independent source copies were extracted from its
[immutable archive](https://codeload.github.com/AsahiLinux/linux/tar.gz/77cb8f24c2381a8abb7272d7bbdec548d6426a8a),
whose SHA-256 was rechecked as
`aef64ada57e626996093c066bdacb595672cccb0b18fed661363fdbde48f387c`.
Existing reference sources and earlier builds were preserved. The combined
copy first received the observer patch, SHA-256
`205c28ba1830cd794c6c59efff0b3aaeb6102335f48a7f98515a05704fbf378a`,
then the counter patch. Both application checks passed. The counter patch
changes only the Apple SoC Kconfig/Makefile and its new C source.

The x86-64 Linux host used Clang/LLVM 22.1.8, GNU Make 4.4.1,
`ARCH=arm64 LLVM=1`, and the isolated LLD/bc tools described in the
[observer build receipt](../linux-apsc-observer/BUILD-VALIDATION.md).
All eight executable fingerprints and both package-archive fingerprints
were rechecked and matched that receipt. No package installation or root
session was needed for these builds.

All variants derive from the pinned arm64 defconfig. Relative to the
pristine configuration, the disabled variant adds only the explicit
`APPLE_COUNTER_QUALIFICATION=n` entry. The standalone enabled variant
sets that option to `y`; the combined variant also enables
`ARM_APPLE_APSC_OBSERVER=y` and changes `ARM_APPLE_SOC_CPUFREQ=m` to `y`.
`olddefconfig` accepted each configuration.

| Configuration | SHA-256 of `.config` |
| --- | --- |
| Pristine baseline | `9fe86b00e2e805813d50fcc2f52083be3007cbb5b63dc0cac274302ff7de471d` |
| Counter helper disabled | `e6a51cee399af9c5075939e3e97790036767281f10fa236674ede556ecad02cb` |
| Counter helper enabled | `bff67bf977deb9fabb79e8543d5d00a1aa9ffd6f9f1d9da1219bde2ddd7f315a` |
| Counter helper and observer enabled | `250ae95726bf0e3efcb54061c83d2d92e2198d68a525a9764a95b56586ae6541` |

These builds use `ARM64=y`, `ARCH_APPLE=y`, `SMP=y`, `NR_CPUS=512`,
`ARM64_4K_PAGES=y`, `DEBUG_FS=y`, `ARM_ARCH_TIMER_OOL_WORKAROUND=y`,
`PREEMPT=y`, `PREEMPT_RCU=y`, and `LTO_NONE=y`. FTRACE, KASAN, UBSAN and
KCOV are disabled. This is a generic compile configuration, not a verified
configuration for booting this Mac. A different native configuration,
compiler, LTO or instrumentation requires renewed generated-code review.

## Checks and fingerprints

The standalone helper object, the helper-disabled Apple SoC directory,
and all four combined objects compiled successfully. The enabled Apple
SoC directory was also built: its `built-in.a` contains the helper. The
disabled archive has no helper member, and no helper object exists in
that fresh disabled output directory. The existing idle and cpufreq
objects also compiled in the disabled configuration. All final compile
logs had no compiler `warning:` or `error:` lines.

An earlier draft failed compilation on two removed kernel API names.
The final patch uses `nonseekable_open` without a `no_llseek` member and
uses `cpus_have_final_cap`; the passing results apply to the exact patch
hash above, not that earlier draft.

| Final patched source | SHA-256 |
| --- | --- |
| `drivers/soc/apple/apple-counter-qualification.c` | `c799cef6221c1b1bb4d2d310dcaa0d43542ac778c0a5490b2514025efba363f7` |
| `drivers/soc/apple/Kconfig` | `f52d4c566ab9e1b14f20d618e03798426248f1fd16f46cc30298d9cbae99c814` |
| `drivers/soc/apple/Makefile` | `29d1153e0fd3b517978b76dc8c31f1b70529182bc8cc7f9d84ced46ba6cdc0a4` |

| Variant | Object basename | SHA-256 |
| --- | --- | --- |
| Standalone enabled | `apple-counter-qualification.o` | `4ebff17af068a7295b903896e20c27f4edf37c2ac66db4ac3c1928b3cd356bcf` |
| Combined | `apple-counter-qualification.o` | `edb1ab5fecfdb11b701e6932df96ee22aa2c3f86bd2c924f3dd25bd711cfa427` |
| Combined | `cpuidle-apple.o` | `1a0da81f2f16cb19b000a3d824ab94fba459db69b635e8292cf5480a3439301e` |
| Combined | `apple-apsc-observer.o` | `a60170995e0b1cf2c374a065117057475ca795d8b0a242a0d9e6508edc705015` |
| Combined | `apple-soc-cpufreq.o` | `a23763ff1975f4532bbf6c7510fb653a4ca23ee55b3ba57647f6a9453c025e09` |
| Disabled | `cpuidle-apple.o` | `0502e15984d7e9078be2d4e4daf176dc5964d531267e378bcfe014f99525e236` |
| Disabled | `apple-soc-cpufreq.o` | `59c79eeca0d7e7cf156a599eab851c322e70f5118dcd3d4796f32441338c5da6` |

These identify the inspected ELF64 little-endian AArch64 relocatable
artifacts. Whole-object hashes include build-directory-dependent DWARF
metadata; they are not a promise of byte-identical objects in another
directory. Exact section bytes were extracted using ELF section-header
offsets and compared independently of disassembler formatting.

The helper's following sections are byte-identical in standalone and
combined builds, including their relocation records:

| Section | Bytes | SHA-256 |
| --- | ---: | --- |
| `.text` | 5392 | `805fab11b940f7699dcf927d6a3b86b60f39aabc058de78384064bfda024d884` |
| `.rela.text` | 5448 | `679878c8d16e3363e38c59a67086af61cedbdb31a324dfd31787165ae3e1e361` |
| `.init.text` | 980 | `dd91c40be50290990b8e027304f31ce2ef7dab2eabaa3f1ca648e495de90042e` |
| `.rela.init.text` | 1536 | `e6afd1da39d0b0969f7bfd116cf0e009db185e4570dff4f953e674ed3ec889a1` |
| `.altinstructions` | 192 | `122269217378108dea6cd18c182c2de12d94a24a349d93e6c882ab454fba87a4` |
| `.rela.altinstructions` | 768 | `9f2775ae5a989dda32a3bc64afff859f8245e00f3f794ce784a0aca0a53e32bb` |

Every executable section and its relocations in the helper-disabled
`cpuidle-apple.o` and `apple-soc-cpufreq.o` match the pristine baseline.
The complete existing 100-byte `apple_cpu_deep_wfi` routine at
`.cpuidle.text[0:0x64]` is identical in pristine, disabled and combined
objects, SHA-256
`c8fd716fccb949e9f35aa2937a87787942b39f0b5df5e088d46f88253479b88c`.
The helper does not add idle-hook or cpufreq code; the observer's separate
instrumentation remains subject to its own validation boundary.

## Generated-instruction review

Clang inlines `cq_tick` and `cq_round` into their callers in this
configuration. All six stamp sites—phase start/end, source a0/a1 and
target b0/b1—have the default sequence:

```asm
dsb sy
isb
mrs x8, CNTPCT_EL0
eor x9, x8, x8
add x9, sp, x9
ldr xzr, [x9]
dsb sy
```

The target uses x10/x11 instead of x8/x9. The ECV replacements
(`NOP; MRS CNTPCTSS_EL0`) and their alternative descriptors are present.
This is pre-boot code review: it does not establish the target's selected
alternative or workaround state. Native export records those separately.

In the worker's `.text`, the a0 stamp starts at `0x954`; the request
publication is `STLR` at `0x99c`, followed by the relocation to
`smp_call_function_single` at `0x9a0`. The acknowledgment `LDAR` at
`0x9b0` precedes the a1 stamp starting at `0xa34`. The source preemption
pin spans both readings and the call; unpinning follows the source-after
CPU check. Rescheduling paths are outside that pinned exchange.

`cq_target` starts at `0xce4`. Its request `LDAR` at `0xcf4` precedes
the b0 and b1 stamp sequences at `0xd6c` and `0xd98`; its acknowledgment
`STLR` is at `0xdec`. The target and metadata callbacks contain no
`BL`/`BLR` instructions or external call/jump relocations. Thus this
configuration adds no allocation, scheduling, printing or nested SMP
call inside those callbacks. The worker and debugfs control path do call
normal kernel scheduling and synchronization services.

The helper object contains no `MSR`, `WFI` or `WFE` instruction.
Its system-register reads are CNTPCT/CNTPCTSS, CNTFRQ, CNTKCTL,
ID_AA64MMFR0, DAIF and the kernel's SP/TPIDR CPU/task context reads.
Source and relocation review found no MMIO mapping/access, power-register
access, governor change or idle-policy operation. These checks concern
the helper's own code, not a claim that its ordinary SMP calls have no
system-wide effects: they deliberately wake CPUs and disturb idle.

## Reproduction and limits

Use fresh private source/output directories, the verified archive and
the exact public patches. `counter_build_root` below is a neutral local
workspace containing those inputs and the isolated tools. For the
combined source, apply the observer patch first, then this helper patch.

```sh
: "${counter_build_root:?set a private build workspace}"
export PATH="$counter_build_root/toolchain/usr/bin:$PATH"
export LD_LIBRARY_PATH="$counter_build_root/toolchain/usr/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

git -C "$counter_build_root/source" apply --check "$counter_build_root/0001-t8103-counter-qualification.patch"
git -C "$counter_build_root/source" apply "$counter_build_root/0001-t8103-counter-qualification.patch"
make -j4 -C "$counter_build_root/source" O="$counter_build_root/on" ARCH=arm64 LLVM=1 defconfig
"$counter_build_root/source/scripts/config" --file "$counter_build_root/on/.config" --enable APPLE_COUNTER_QUALIFICATION
make -j4 -C "$counter_build_root/source" O="$counter_build_root/on" ARCH=arm64 LLVM=1 olddefconfig
make -j4 -C "$counter_build_root/source" O="$counter_build_root/on" ARCH=arm64 LLVM=1 drivers/soc/apple/
llvm-ar t "$counter_build_root/on/drivers/soc/apple/built-in.a"
llvm-objdump -dr "$counter_build_root/on/drivers/soc/apple/apple-counter-qualification.o"
llvm-readelf -rWs "$counter_build_root/on/drivers/soc/apple/apple-counter-qualification.o"
```

For the disabled variant, start with another defconfig and leave
`APPLE_COUNTER_QUALIFICATION` disabled; build `drivers/soc/apple/` and
both existing driver objects. For the combined variant, enable both
diagnostics and built-in Apple cpufreq, then build these exact targets:

```text
drivers/soc/apple/apple-counter-qualification.o
drivers/cpuidle/cpuidle-apple.o
drivers/cpuidle/apple-apsc-observer.o
drivers/cpufreq/apple-soc-cpufreq.o
```

Kbuild also generated its normal preparation artifacts and arm64/compat
VDSOs. No final `vmlinux` link, module `modpost`, native debugfs operation,
clock calibration, APSC overlap, physical idle state or energy result is
claimed. The pinned arm64 tree has no supported objtool/noinstr validation;
this receipt is manual generated-code review. Native boot, error-path
behavior and qualification remain outstanding under the separately
authorized [native procedure](README.md#later-native-procedure).
