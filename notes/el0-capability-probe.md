# AArch64 user-mode register boundary on the running M1

**Target and evidence tier:** MacBookAir10,1 / T8103, macOS 27.0 build 26A428, 1 October 2026. This is a live, unprivileged instruction probe, not a kernel trace or a physical idle-state measurement. The installed-kernel identity is recorded in [the driver investigation](local-driver-notes.md). Source: [`el0-capabilities.c`](tools/el0-capabilities.c).

The probe executes individual AArch64 `MRS` instructions in short-lived child processes. A preceding `ISB` orders the counter samples. Faulting children cannot terminate the parent, and core dumps are disabled. It writes no system register, reads no MMIO address, enters no WFI, and needs no root access or reboot. The C wrapper only handles isolation and reporting; the register access is assembly. The compiled object was checked with `xcrun llvm-objdump -d` to confirm that each intended `MRS` survived compilation. In Apple's assembler syntax, separate `ISB` and `MRS` with a newline in inline assembly: a semicolon can begin a comment and silently omit the latter instruction.

Run from the repository root:

```sh
xcrun clang -O2 -Wall -Wextra -std=c11 notes/tools/el0-capabilities.c -o /private/tmp/m1-el0-capabilities
/private/tmp/m1-el0-capabilities
xcrun llvm-objdump -d /private/tmp/m1-el0-capabilities
```

| Instruction target | Result on this Mac | Use or limit |
|---|---|---|
| `CNTVCT_EL0`, `CNTFRQ_EL0` | Readable; frequency **24,000,000 Hz** | Low-cost virtual-counter timestamps, with units established locally |
| `CNTPCT_EL0` | Readable | Physical-counter timestamp, but no direct idle-state or power measurement |
| `TPIDR_EL0` | Readable; sample decoded as logical cluster 1, CPU 4 | Label the executing CPU/cluster at a sample point |
| `TPIDRRO_EL0` | Readable; value deliberately not printed | Contains a thread pointer, not an idle signal |
| `PMCCNTR_EL0`, `PMUSERENR_EL0`, `MPIDR_EL1`, Apple `CYC_OVRD` (`S3_5_C15_C5_0`) | Each isolated read terminated with signal 4 (`SIGILL`) | No user-mode access to those registers in this configuration |

The probe also ran 10,000 bracketing comparisons. `CNTVCT_EL0` lay between paired `mach_absolute_time()` reads **10,000/10,000** times; `CNTPCT_EL0` lay between paired `CNTVCT_EL0` reads **10,000/10,000** times. The widest latter bracket was one counter tick in the saved run. `mach_timebase_info` reported **125/3 ns per tick**, consistent with 24 MHz. These observations make direct counter reads useful for a later timestamped user-space workload and show no visible counter offset at this resolution. They do not prove anything about EL2 configuration or physical idle residency.

[Apple's pinned XNU header](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/osfmk/arm64/machine_machdep.h) defines bits 0–11 of `TPIDR_EL0` as the current logical CPU and bits 12–19 as the logical cluster. [The corresponding user-space code](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/libsyscall/os/tsd.h) warns that these CPU-ID internals are not a stable ABI. This pinned public source explains the decoding; the live sample checks that the field is readable on the target, rather than proving the private macOS 27 implementation is identical. A thread may migrate between two `MRS` instructions, so a timestamp and CPU tag must be sampled as one bounded sequence and checked for migration if ordering matters.

This is the practical user-mode boundary for the [last-core APSC question](local-driver-notes.md): assembly provides a clock and current CPU label, but it cannot dereference the PMGR command register at `0x210e20020` or `0x211e20020`, determine bit 31, or alter deep WFI policy. Those require a privileged, separately qualified observation route. An EL0 `SIGILL` from `CYC_OVRD` demonstrates this process's access boundary; it does not say the register is absent from the chip.
