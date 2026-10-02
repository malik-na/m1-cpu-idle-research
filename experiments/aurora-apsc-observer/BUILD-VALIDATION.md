# Aurora build validation

2 October 2026. The [Aurora ports](README.md) passed scoped patch checks and
preliminary AArch64 Kbuild object compilation with the visible installed
kernel's prepared headers and exported configuration. All three builds
exited zero and their retained logs contain no compiler warning/error lines.
The [sanitized receipt](build-receipt.json) preserves patch/source/object/tool
hashes, config excerpts, command statuses and timestamps. Raw headers,
objects, complete config, source copies and logs remain in a private packet.

## Falsifiable result and scope

The checked proposition is that this port compiles against the installed
prepared interfaces, preserves the disabled drivers' executable sections
and relocation bytes, and preserves the original complete deep-WFI routine
with the observer enabled. Compile failure, changed disabled executable
bytes/relocations, or changed deep-WFI bytes would refute this proposition.
The checks below passed for these exact inputs. They do not verify the
remaining full-tree, final-link or native experiment requirements.

The source pin is iconidentify/aurora-linux
[`90a95335a49aec3a0045a76da140452ad6585eb3`](https://github.com/iconidentify/aurora-linux/tree/90a95335a49aec3a0045a76da140452ad6585eb3).
All six original files touched by the two patches were checked against that
commit's Git tree using their exact Git blob IDs. In a fresh sparse copy,
the observer's `git apply --check`/application and then the counter helper's
check/application all exited zero. The resulting nine files match the
compiled sparse port byte-for-byte. This sparse check covers every touched
existing file, not the rest of the source tree or its build rules.

The later [whole-tree receipt](full-source-receipt.json) extends source
qualification beyond that sparse check. GitHub archive requests returned
HTTP 429 and Git bulk fetches timed out. The retained official kernel.org
Linux 7.1.12 archive supplied 93,361 matching files; 706 changed/new files
were retrieved from the raw GitHub endpoint at the exact Aurora commit.
Every one of the resulting 94,067 files and its mode was checked. Importing
them into an isolated Git index produced tree
`a6f2a94ab1433507d1943b525854faaea04a88aa`, exactly the fetched commit's tree;
`git fsck` passed and the pristine worktree was clean. Both patch checks
and applications then passed in a separate complete worktree. The full
per-file content/mode manifest and raw retrieval records remain private.
The upstream archive SHA-256 is
`389716b3ed27e4cd520b903eea04acc33b9804c4282cb7a918f05ff14e9b5ae1`,
matching the HTTPS checksum list; no checksum-list signature verification
is claimed. Exact Aurora Git blob/tree checks determine this source identity,
independently of the archive's release name.

| Port patch | SHA-256 |
| --- | --- |
| Observer | `409c440e0977c75276bd842088862449b80b8ada5924d568efcbd7af2daec3ed` |
| Counter helper | `7b479dfe679f7c25b0e92c6b0081c244e523cd82159ece652ebd5db29a0eba07` |

The installed header tree is prepared for `7.1.12-2-11.17-sep-ARCH` and has
no full source or root Kbuild. It was copied into a private build directory;
the installed tree was not edited. Its `.config` remained byte-identical
through these builds, SHA-256
`84bb71434e905f3b1360142e075a89b0bccb5e5bd7ca82eb892a362512df260e`.
The [target qualification](../../notes/linux-native-qualification-20261002.md)
ties that exported config and the installed image/build ID to the visible
kernel. This does not recover the original package's PKGBUILD or prove the
source-to-binary chain for its entire header tree.

## Compiler and configuration

The build host is the unprivileged AArch64 research session on the visible
T8103 kernel. GCC `16.1.1 20260430`, GNU binutils `2.46.0`, Make `4.4.1` and
`ARCH=arm64 CC=gcc HOSTCC=gcc` were used. Make/flex/bison/bc/m4 and their
runtime dependencies were extracted into a private tools directory after
matching the retained local Arch Linux ARM sync database SHA-256 values.
No system package was installed; these checks do not claim package-signature
verification. The receipt identifies the actual compiler/tool executables.

The retained configuration has `ARM_APPLE_CPUIDLE=y`,
`ARM_APPLE_SOC_CPUFREQ=y`, `DEBUG_FS=y`, `ARM64_16K_PAGES=y`,
`PREEMPT_DYNAMIC=y`, `STACKPROTECTOR_STRONG=y`, `DEBUG_PREEMPT=y`,
`DEBUG_INFO_DWARF5=y`, `LTO_NONE=y`, `RUST=y` and `FTRACE=y`.
`FUNCTION_TRACER`, KASAN, KCSAN, UBSAN and KCOV are disabled. The two new
instrument options are absent from this unchanged configuration: the
enabled preliminary build supplies them through `KCFLAGS` definitions.

Each source directory uses an `obj-y` Makefile. The retained compiler
commands have no `-DMODULE`; no module was linked or loaded. These are
individual built-in-style object requests using the prepared headers.
They do **not** test full-tree Kconfig acceptance, archive selection,
symbol resolution or linking an instrumented kernel.

## Reproduce the preliminary build

Use a private copy of the installed prepared headers, pinned original
source files and the port-applied source. Set `aurora_build_root` to a
workspace containing `header-build`, `source`, `source-patched`, and
isolated `tools`. Create three flat object directories, copying the two
original drivers into `objects-pristine`, the two ported drivers into
`objects-off`, and all four ported C sources into `objects-on`. The driver
paths are `drivers/cpuidle/cpuidle-apple.c` and
`drivers/cpufreq/apple-soc-cpufreq.c`; the added sources are
`drivers/cpuidle/apple-apsc-observer.c` and
`drivers/soc/apple/apple-counter-qualification.c`.

```sh
: "${aurora_build_root:?set the private build workspace}"
export PATH="$aurora_build_root/tools/usr/bin:$PATH"
export LD_LIBRARY_PATH="$aurora_build_root/tools/usr/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export BISON_PKGDATADIR="$aurora_build_root/tools/usr/share/bison"
for variant in pristine off on; do
    printf 'obj-y := cpuidle-apple.o apple-soc-cpufreq.o' >"$aurora_build_root/objects-$variant/Makefile"
    if test "$variant" = on; then
        printf ' apple-apsc-observer.o apple-counter-qualification.o' >>"$aurora_build_root/objects-$variant/Makefile"
    fi
    printf '\nccflags-y += -I%s/source-patched/include\n' "$aurora_build_root" >>"$aurora_build_root/objects-$variant/Makefile"
done
for variant in pristine off; do
    make -C "$aurora_build_root/header-build" \
        M="$aurora_build_root/objects-$variant" ARCH=arm64 CC=gcc HOSTCC=gcc V=1 \
        cpuidle-apple.o apple-soc-cpufreq.o
done
make -C "$aurora_build_root/header-build" M="$aurora_build_root/objects-on" \
    ARCH=arm64 CC=gcc HOSTCC=gcc V=1 \
    KCFLAGS='-DCONFIG_ARM_APPLE_APSC_OBSERVER=1 -DCONFIG_APPLE_COUNTER_QUALIFICATION=1' \
    cpuidle-apple.o apple-soc-cpufreq.o apple-apsc-observer.o apple-counter-qualification.o
```

Run the [comparison script](compare_objects.py) with that private workspace.
It extracts ELF section bytes and relocations independently of disassembler
formatting, verifies AArch64 relocatable objects, and bounds deep WFI using
its symbol and the next function. Whole-object fingerprints include private
build paths/debug metadata, so they identify these retained artifacts rather
than promise a byte-identical rebuild under another directory.

The enabled build's original metadata incorrectly named its post-completion
timestamp `started_utc`. The public receipt explicitly records it as
`completion_recorded_utc`; its actual start was not retained. The later
pristine/disabled control builds have separately observed start/end times.

## Generated-code findings

Both disabled drivers have identical executable section bytes and associated
relocation bytes to their pristine controls. Source/debug/line metadata is
outside that comparison; complete ELF objects need not be identical.
The 100-byte `apple_cpu_deep_wfi` routine is identical in pristine, disabled
and enabled objects, SHA-256
`c8fd716fccb949e9f35aa2937a87787942b39f0b5df5e088d46f88253479b88c`.
Its original power-control instructions, `DSB`, WFI retry and restoration
sequence are unchanged.

Manual disassembly review found the idle-enter observer before
`ct_cpuidle_enter()` and idle-exit observer after `ct_cpuidle_exit()`.
The failed CPU-PM hook also precedes context-tracking entry. The token is
scalar state across WFI; no observer mapping or RCU reference crosses it.
The active MMIO probe has one ordered command read with counter brackets;
its ordering-dependency branch is not a BUSY-poll loop. The cpufreq wrapper
has mutually exclusive active/inactive paths, each with one original command
store; the active path brackets that store and then publishes the record.
It adds no command readback or completion wait.

GCC leaves the recorder's internal reserve helper out of line. The idle
hooks have a conditional `__stack_chk_fail` call on stack-protection failure;
healthy recording paths have no allocation, printing, scheduling or lock
call. This is a manual review of these objects, not a call-free assertion
or an automated ARM64 noinstr/objtool validation. The selected arm64 source
lacks the applicable validation pass.

GCC also leaves `cq_tick` out of line. Its counter-read ordering sequence is
`DSB; ISB; MRS CNTPCT_EL0;` dependency and load; `DSB; RET`, with no external
call. The target/metadata callbacks call `debug_smp_processor_id` under the
actual `DEBUG_PREEMPT=y` setting. The target CPU check precedes its two stamp
calls. Those normal IRQ callbacks must remain nonpreemptible in a future
native run; the debug helper can report a context violation on its error
path. This differs from the older Clang/defconfig receipt and must be retained
in final generated-code review. The helper's causal SMP exchanges disturb
idle and belong outside the APSC capture window.

No kernel was installed or booted for these checks. Full source/config
qualification, final linking and linked-instruction review, a distinctive
image/module set, verified stock fallback and authorized native controls
remain required. No raw APSC events exist in this packet; hardware trace
loss is not applicable, rather than a measured zero-loss result.

## Subsequent complete build and boot bundle

The [full build receipt](full-build-receipt.json) extends the preliminary
record above. Whole-source pristine Kconfig output is byte-identical to
the exported target configuration. The enabled variant changes only the
two instrument options and the distinctive local release; existing debug,
security, page-size and Rust settings are retained. GCC and Rust 1.93.1
build `Image modules dtbs` successfully, with no warning/error lines in the
full kernel build log. The build ran from 05:46:46.562705 to 06:23:12.305306
UTC, including the recorded temporary compiler suspension. These
preparation times are not an energy benchmark.

The linked candidate is `7.1.12-ARCH-apsc-20261002`, GNU build ID
`a53a08aa0376b26e41aea54be3d1b470d5b7b061`. Its Image SHA-256 is
`6857a188b095d4a434ae9340f6ccfcd84b0f868026fe854132351a7d76a7d1e5`;
its embedded configuration matches the reviewed candidate config exactly.
The complete linked deep-WFI routine still has the declared 100-byte digest.
Both helpers are present and their PREL32 late-initcall slots resolve to
their linked initialization functions. The comparison script's optional
`--vmlinux` check and thirteen retained linked disassemblies support this
local-binary result. A missing helper/initcall, different config, changed
WFI bytes, or failed link would refute it.

Linked review confirms the idle hooks remain outside context tracking,
the DVFS wrapper has one original store on each mutually exclusive path,
and the MMIO mode adds one ordered read. The original optional verified
Aurora branches are retained. Strong stack-check failure calls and debug
CPU checks remain as described above. No ARM64 objtool/noinstr pass is
claimed, and compilation does not qualify runtime context or observer effect.

All 1,867 modules were staged privately and checked for matching release
vermagic and exact `modules.order` coverage; all 83 currently loaded stock
module names are available. The first private initramfs generation exited
zero but failed the disk-unlock content check: copying only the main config
omitted Omarchy's six drop-ins. That failed attempt is preserved. The corrected
build uses the complete configuration, which matches the booted stock
initramfs recipe; config-time module discovery uses the private candidate
tree. It preserves encryption, keyboard, vendor-firmware and Plymouth hooks.
The corrected EFI bundle contains exactly the checked Image and initramfs,
the candidate release, and the stock command-line tokens. Boot-content checks
verify cryptsetup/generator, firmware/unlock units, Btrfs, dm-crypt and input
modules. Generic microcode/privacy-screen and optional dockchannel firmware
warnings are retained; vendor firmware still comes from the existing ESP.

The [boot inspection](../../notes/raw/native-linux-boot-qualification-20261002.json)
verifies the current stock EFI bundle and both configured snapshots against
Limine's BLAKE2b hashes. The first collector mistakenly used SHA-512; its
original comparisons are retained and corrected checks match all three
entries. Limine documents the URI hash algorithm in
[CONFIG.md](https://github.com/limine-bootloader/limine/blob/v12.x/CONFIG.md).
The current stock bundle contains the exact identified image/initramfs,
and read-only `bootctl` reports Limine 12.9.1, the current stock entry and
one-shot entry support. Snapshot integrity does not prove snapshot bootability;
dirty stage-1 source identity remains unresolved. Installation and native
captures are subsequent actions with separately recorded results.
