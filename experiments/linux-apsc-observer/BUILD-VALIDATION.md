# ARM64 object-build validation

The exact [observer patch](0001-t8103-apsc-observer.patch) with SHA-256
`205c28ba1830cd794c6c59efff0b3aaeb6102335f48a7f98515a05704fbf378a`
passed `git apply --check` and Kbuild compilation of the three affected
AArch64 objects with the observer enabled, and the two existing drivers
with it disabled. Both final builds exited zero and their logs contained
no compiler warning/error lines. Manual disassembly confirmed the narrow
invariants below. This is an object-build result, not a boot result.

## Scope

Validation ran on 2026-10-01 on an x86-64 Linux build host, cross-compiling
for AArch64. The pristine source and the existing reference checkout were
preserved; the patch was applied to a separate source copy. There was no
kernel installation, boot, capture, power-register access, or macOS
security-policy change. These results do not establish native runtime
correctness, APSC BUSY overlap, physical idle state, or energy benefit.

The checked source is AsahiLinux/linux
[`77cb8f24c2381a8abb7272d7bbdec548d6426a8a`](https://github.com/AsahiLinux/linux/tree/77cb8f24c2381a8abb7272d7bbdec548d6426a8a).
The source archive came from its
[immutable codeload URL](https://codeload.github.com/AsahiLinux/linux/tar.gz/77cb8f24c2381a8abb7272d7bbdec548d6426a8a),
with SHA-256
`aef64ada57e626996093c066bdacb595672cccb0b18fed661363fdbde48f387c`.
The root Makefile, arm64 defconfig, both original Apple drivers,
`scripts/Makefile.build`, and `include/linux/sched.h` were also checked by
Git blob ID against the exact pinned reference checkout.

## Tools and configuration

Clang/LLVM 22.1.8 and GNU Make 4.4.1 were used with `ARCH=arm64 LLVM=1`.
The linker and `bc` were extracted into the build user's isolated tool
directory, without a system package installation:

| Package | SHA-256 |
| --- | --- |
| `lld-22.1.8-1-x86_64.pkg.tar.zst` | `3032282365f09110922c8df0ef6afc56be2427b9396044334e22dced1aadc31c` |
| `bc-1.08.2-1-x86_64.pkg.tar.zst` | `b9e5f0d61a674c9be1a0608f3fcab766d989d9a002c37e55a74ccfc8e87027ab` |

Both packages came from the Omarchy stable Arch package mirror. The setup
receipt records that they matched the local Arch sync database checksums
and passed package-signature verification: lld signer
`2191B89431BAC0A8B96DE93D244740D17C7FD0EC`; bc signer
`E75CD4814A77AD943C7AB5A3E0959FEA8B550539`. Their archive digests were
rechecked during this validation.

| Executable | SHA-256 |
| --- | --- |
| `clang` | `67ad17f2e61ed725abd3cefdd3fa1c24dc5c09ec3ed064dc03c0798e66fe8955` |
| `llvm-objdump` | `54cae7fab0f090bff3d644f2db6ce259c78048f4cba32711db299a4a0a3bbab9` |
| `llvm-objcopy` | `3af64fb4d7128a96d862189bbd5f81a99c4ef7102c3abf3552f02a51d77de259` |
| `llvm-readelf` | `a91f794619200fe146cb23cd3287e493613315e458a6ece75c6c30fceef1f089` |
| `llvm-ar` | `a6d906986e7840289870d48f29a69f0178c352c299eb5c72802b256482943c60` |
| `make` | `9018663161af324a74326c035cfd05408cba13a26c1f6b801cf5f3195f2bee40` |
| `ld.lld` | `36dc8a33f318845a94651516dc158ff588367c0cb477fd6a571fbd03e0c6a2ba` |
| `bc` | `47b8f03536b5da0f5d5bf15d572ada3842b0e217a82eeb4bb0315cf7aef57dd9` |

The baseline uses the pinned arm64 defconfig. The patched disabled build
has the identical `.config`. The enabled build changes only
`ARM_APPLE_SOC_CPUFREQ=m` to `y` and adds
`ARM_APPLE_APSC_OBSERVER=y`; `olddefconfig` accepted both configurations.

| Configuration | SHA-256 of `.config` |
| --- | --- |
| Pristine baseline and observer disabled | `9fe86b00e2e805813d50fcc2f52083be3007cbb5b63dc0cac274302ff7de471d` |
| Observer enabled | `dd60c2cb2cd895249fbf578f0819c76510fbfd1dd50f4853e1481e849002d9ab` |

Both use `ARM_APPLE_CPUIDLE=y`, `DEBUG_FS=y`, `SMP=y`, `NR_CPUS=512`,
`PREEMPT=y`, `PREEMPT_RCU=y`, `LTO_NONE=y`, and reduced default-toolchain
DWARF debug information. `FTRACE`, `KASAN`, `UBSAN`, and `KCOV` are disabled.
These flags matter: a future kernel with additional instrumentation,
different compiler, LTO, or another configuration needs a new generated-code
review. The recorder's runtime T8103/eight-CPU checks do not turn a generic
defconfig object build into hardware qualification.

## Reproduction

The following expresses the commands using neutral build directories.
Set `apsc_build_root` to a private workspace containing the verified source
archive, isolated tools, and the exact repository patch. The actual run
preserved separate baseline, disabled, and enabled outputs. The final
configuration was copied from the already prepared enabled configuration;
the `scripts/config` commands below reconstruct its two-option difference.

```sh
: "${apsc_build_root:?set a private build workspace}"
cd "$apsc_build_root"
export PATH="$apsc_build_root/toolchain/usr/bin:$PATH"
export LD_LIBRARY_PATH="$apsc_build_root/toolchain/usr/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

tar -xf asahi-linux-77cb8f24.tar.gz
mv linux-77cb8f24c2381a8abb7272d7bbdec548d6426a8a source
cp -a --reflink=auto source source-patched
git -C source-patched apply --check "$apsc_build_root/0001-t8103-apsc-observer.patch"
git -C source-patched apply "$apsc_build_root/0001-t8103-apsc-observer.patch"

make -j4 -C source O="$apsc_build_root/baseline" ARCH=arm64 LLVM=1 defconfig
make -j4 -C source O="$apsc_build_root/baseline" ARCH=arm64 LLVM=1 \
  drivers/cpuidle/cpuidle-apple.o drivers/cpufreq/apple-soc-cpufreq.o

mkdir off on
cp baseline/.config off/.config
cp baseline/.config on/.config
source-patched/scripts/config --file on/.config \
  --enable ARM_APPLE_SOC_CPUFREQ --enable ARM_APPLE_APSC_OBSERVER
make -j4 -C source-patched O="$apsc_build_root/off" ARCH=arm64 LLVM=1 olddefconfig
make -j4 -C source-patched O="$apsc_build_root/on" ARCH=arm64 LLVM=1 olddefconfig
make -j4 -C source-patched O="$apsc_build_root/off" ARCH=arm64 LLVM=1 \
  drivers/cpuidle/cpuidle-apple.o drivers/cpufreq/apple-soc-cpufreq.o
make -j4 -C source-patched O="$apsc_build_root/on" ARCH=arm64 LLVM=1 \
  drivers/cpuidle/cpuidle-apple.o drivers/cpufreq/apple-soc-cpufreq.o \
  drivers/cpuidle/apple-apsc-observer.o

llvm-objdump -dr on/drivers/cpuidle/cpuidle-apple.o
llvm-objdump -dr on/drivers/cpuidle/apple-apsc-observer.o
llvm-objdump -dr --disassemble-symbols=apple_soc_cpufreq_set_target \
  on/drivers/cpufreq/apple-soc-cpufreq.o
llvm-readelf -SW on/drivers/cpuidle/cpuidle-apple.o
llvm-readelf -rW on/drivers/cpuidle/apple-apsc-observer.o
```

The metadata revision was checked by reversing its predecessor on the
isolated source copy, applying the exact final patch, and rebuilding the
affected objects in the existing enabled/disabled output directories.
The final logs show all three enabled objects and both disabled objects
recompiled. The config hashes remained unchanged. No unrelated kernel
objects were requested for that revision.

## Exact source and object fingerprints

These are SHA-256 digests of the final patched source files:

| File | SHA-256 |
| --- | --- |
| `drivers/cpuidle/cpuidle-apple.c` | `d1679ce601bf82ad68717605b899d3933f0fbcf7f980bdc3f88a1740b8003891` |
| `drivers/cpufreq/apple-soc-cpufreq.c` | `aa9aec68f249cc68473f17feb8ca3815185882935a8bccf947f2a86af9fd012b` |
| `drivers/cpuidle/apple-apsc-observer.c` | `bfe017c930efcc9f0d4147734255a7b08ae1c1b39893dbc770dc6f41d93d201a` |
| `include/linux/soc/apple/apsc-observer.h` | `ab7c672c53ebd7877f6db9c029b9626a622f0b200fb04c5268784c133fdda811` |
| `drivers/cpuidle/Kconfig.arm` | `a3d217febf239d231374af1f2fec9ba88bd07f6e9309b2e99320e20b33a08b45` |
| `drivers/cpuidle/Makefile` | `2bd61db3705670c4202761ec7091619c05c479f33d7df4c0dc851a1c053b6e51` |

The following hashes identify the actual ELF64 little-endian AArch64
relocatable objects inspected. Whole-object hashes include DWARF paths and
other build metadata; they are receipts for these artifacts, not a promise
that building under another directory reproduces every byte.

| Variant | Object basename | SHA-256 |
| --- | --- | --- |
| Pristine | `cpuidle-apple.o` | `3f7ef2278d239b646323f878a945f118fbf5f30bab7ca00f54dfb87eb2d38562` |
| Pristine | `apple-soc-cpufreq.o` | `664f55d74bf5ae411996246b1b3d8d43fbd8aa1f5e948d5fab3eb6d83c3452fa` |
| Disabled | `cpuidle-apple.o` | `f5166d467eaa414aa11ed5ce27133c1ed3831c8c04c4960ddd0b1f97a7225ec0` |
| Disabled | `apple-soc-cpufreq.o` | `ae395d9f524983717005ab6dd956fc80b68f47b0d44700b1e85f50c3868310a5` |
| Enabled | `cpuidle-apple.o` | `b72741c89c858ee5a3f194e2cb3f4c2e5731e6cf7c496bf2024342e5244d133c` |
| Enabled | `apple-soc-cpufreq.o` | `ed0bf53647ef9850484ce910719fae17ebc61053ac9502bf496b97578239f279` |
| Enabled | `apple-apsc-observer.o` | `e76d3f9b889407dc5f1f038924dc6a3180e3eab6dd33f2fa26f6df113b4027f5` |

## Disabled-build comparison

The final disabled `apple-soc-cpufreq.o` and pristine object are identical
after `llvm-objcopy --strip-debug`, with SHA-256
`c497f9a87483005b39b833d1c19e9de83b9067e43219ab18bf670b6ee4d1afd0`.

For `cpuidle-apple.o`, all executable sections and their relocation records
are identical between pristine and disabled builds. All allocated section
bytes also match except `__bug_table`, whose existing WARN source-line
field moves from 85 to 104. Debug information and generated initcall symbol
names also reflect source-line changes, so the complete stripped objects
are **not** byte-identical. The changed field is source-location metadata;
the disabled idle instructions and call targets are unchanged.

## Generated-instruction review

ELF sections were extracted using their section-header offsets and compared
byte-for-byte, independently of the disassembler's formatting. Selected
section digests are:

| Object/variant | Section or range | Bytes | SHA-256 |
| --- | --- | ---: | --- |
| cpuidle, pristine/disabled | `.cpuidle.text` | 232 | `3b426bc0a0571e5a17ca9e6a98a9def563e6dab7eb575bd7d814d5969f13b3df` |
| cpuidle, pristine/disabled | `.rela.cpuidle.text` | 120 | `0a31217c6a4d3a0602002f42c5dbb4e60e950d048f7cfa52c4087f17d5ed668c` |
| cpuidle, enabled | `.cpuidle.text` | 252 | `2d2399453aabf7d1e91534dc3e7e08e0adf512941aa131c1a1afd7dcbe6b3b35` |
| cpuidle, enabled | `.rela.cpuidle.text` | 192 | `3f11c73ef18f75b919ad0c01e3d0993ab53854956b771ea231ed49e6e1a4c16a` |
| cpuidle, all three variants | `.cpuidle.text[0:0x64]` | 100 | `c8fd716fccb949e9f35aa2937a87787942b39f0b5df5e088d46f88253479b88c` |
| cpufreq, enabled | `.text` | 1796 | `78ab6ec393d35ec6f52019fb1f02560f8b07e670e53321641d2711b88122ce23` |
| observer, enabled | `.text` | 5268 | `7d0449ed9ec7e35dceeff0a8749a0d82c970c4467e92b743cebbf88170e334b3` |
| observer, enabled | `.init.text` | 1296 | `285ad03a8b11d801c9765903061ef98eb0a1eb36f25c66204d8e5ca7e1e23763` |
| observer, enabled | `.rela.text` | 8640 | `66a4e3703c0c7ba559c68f6635feb50290b3f1525c6dd95dc9ec18f3a19236d9` |

The 100-byte range is the complete existing `apple_cpu_deep_wfi` routine,
ending immediately before `apple_enter_wfi`. Its raw bytes are identical
in pristine, disabled, and enabled objects. In that routine the two
`MSR S3_5_C15_C5_0` instructions remain at offsets `0x24` and `0x40`, and
`CBZ x0` at `0x34` still targets `DSB SY` at `0x28`, followed by `WFI`
at `0x2c` and the `ISR_EL1` read at `0x30`. There is no recorder call in
that loop or in the power-control sequence.

In the enabled `apple_enter_idle`, call relocations place
`apple_apsc_observer_idle_enter` after successful `cpu_pm_enter` and before
`ct_idle_enter`. `apple_apsc_observer_idle_exit` follows `ct_idle_exit`
and precedes `cpu_pm_exit`. The failed CPU-PM branch calls only its failure
recorder before the existing error return. The token is held in the saved
`x20` register across the original deep-WFI routine.

The three observer idle helpers (`idle_enter`, `idle_exit`, and
`cpu_pm_fail`) have no `BL`, `BLR`, or external call/jump relocations in this
configuration. Their preemption-count changes, counter reads, atomic slot
reservation, and release publication are emitted inline. No scheduler,
allocation, mutex, printk, or tracing helper is called from those helpers.
The atomic reservation has the architecture's LSE/LL-SC alternatives;
its normal-memory atomic retry is separate from the unchanged WFI retry.
This review concerns pre-boot relocatable code, not an image after runtime
alternative patching.

The optional command sample is one 64-bit MMIO load with the existing
ARM64 `readq` ordering sequence (`DMB OSHLD` and its dependency sequence).
Counter reads use `ISB; MRS CNTPCT_EL0`. This has an observer cost and is a
C-boundary sample, not an instruction-level WFI timestamp.

The enabled cpufreq path retains the preceding BUSY poll, forms the same
command, and calls the write wrapper once on success. In
`apple_apsc_observer_dvfs_write`, the active and inactive branches each have
one `STR x5,[x1]`, at offsets `0x3c` and `0x88` respectively; the branches
are mutually exclusive and converge after their store. There is no added
command readback or post-write poll. The active branch brackets its store
with physical-counter reads and calls `apsc_record_dvfs`; that recorder
uses `_find_next_bit` to walk the policy mask. These command timestamps
therefore mark CPU instruction order, not device-command completion.

## Validation boundary

The scope is Kbuild compilation of the changed objects plus manual review
of generated instructions and relocations. Kbuild also built its required
arm64/compat VDSO preparation artifacts. No final `vmlinux` link, module
`modpost`, target boot, or debugfs capture is claimed.

At this source pin, `NOINSTR_VALIDATION` requires
`HAVE_NOINSTR_VALIDATION && DEBUG_ENTRY`; arm64 does not select the former,
and `tools/objtool/arch/` has only loongarch, powerpc, and x86 implementations.
There is **no passing arm64 objtool/noinstr validation** behind this receipt.
The [native checklist](NATIVE-RUN.md) remains mandatory before treating
this as a native observation tool.
