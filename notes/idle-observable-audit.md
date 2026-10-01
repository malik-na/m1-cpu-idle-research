# Native M1 idle observable audit

2026-10-01. Static source and saved-artifact audit only. No hardware registers were accessed, no driver was loaded, and no power controls were changed.

## Nomination

The smallest useful first observation is **a timestamped, read-only 32-bit snapshot of the PCPM PMGR power-state register**, specifically its `ACTUAL` field, from a collector running on an E core during native Linux. On this captured T8103 ADT its address resolves to **`0x23b700048`**, PMGR offset `0x48`.

The justified result would be: “At this instant, the PMGR register assigned to PCPM reported current state N.” This is independent of Linux's time spent inside its cpuidle callback. It is **not yet a validated measurement of entire P-cluster rail-off residency**, cache retention, or a specific macOS APSC substate. Whether this field changes during ordinary Linux deep WFI is an experimental question, not established by its name.

Do not begin with arbitrary raw PMU event numbers or a whole MMIO dump. No independently decoded CPU idle-residency PMU event was established by this audit.

## Mapping and decoding are supported by source

The saved [local device map](raw/pmgr-device-map.json) and [raw CPU/PMGR ADT properties](raw/cpu-idle-adt.json) give `ps-regs[3] = { reg: 0, offset: 0, mask: 0x3ff }`. PCPM is a real device entry with flags 0, `psreg=3`, `psidx=9`. Its address is PMGR register-bank-0 base plus `9 * 8`. The [pinned native Linux DTS](https://github.com/AsahiLinux/linux/blob/77cb8f24c2381a8abb7272d7bbdec548d6426a8a/arch/arm64/boot/dts/apple/t8103.dtsi#L1049) places that PMGR bank at `0x23b700000`.

| Local entry | ID | PS3 index | Address |
|---|---:|---:|---|
| ECPU0–ECPU3 | 1–4 | 0–3 | `0x23b700000` through `0x23b700018` |
| PCPU0–PCPU1 | 5–6 | 4–5 | `0x23b700020`, `0x23b700028` |
| PCPU2–PCPU3 | 211–212 | 6–7 | `0x23b700030`, `0x23b700038` |
| ECPM | 7 | 8 | `0x23b700040` |
| PCPM | 8 | 9 | `0x23b700048` |

PCPU2/3 occur later in the device list: do not infer index from device ID or array order. Entries named just `ECPU` and `PCPU`, IDs 209/210, have virtual/no-PS flag `0x10` and must not be treated as additional physical registers.

The CPU-bank interpretation is stronger than extrapolating an unrelated peripheral layout: [m1n1's pinned PMGR decoder](https://github.com/AsahiLinux/m1n1/blob/3e354a2467f4f724f254362626cae0633918e0c1/proxyclient/m1n1/hw/pmgr.py) explicitly assigns the ten PS3 slots at offsets `0,8,...,0x48` the same `R_PSTATE` type. It defines **ACTUAL = bits 7:4; DESIRED = bits 3:0**. The low nibble alone is the requested state, not the observed current state.

The [pinned Linux PMGR driver](https://github.com/AsahiLinux/linux/blob/77cb8f24c2381a8abb7272d7bbdec548d6426a8a/drivers/pmdomain/apple/pmgr-pwrstate.c) uses the same fields and assigns `0xf = active`, `0x4 = clock-gated`, `0x0 = power-gated`. Preserve the raw word, target nibble, and actual nibble; preserve other values as unknown/intermediate rather than forcing them into those three labels. Bits 8/9 are named `WAS_PWRGATED`/`WAS_CLKGATED`, but their reset/latch semantics have not been validated as an interval counter. Do not clear them or derive residence time from them.

The historical preboot observations of 15 and 0 are supporting evidence that these registers are readable in that boot environment, not proof of ordinary Linux-idle behavior. The existing [native Linux evidence boundary](../wiki/Prior-Native-Linux-Results.md) reports software CPU PD selection but no raw MMIO observation. Current macOS CPU IOReport's aggregate IDLE bin does not supply an independent depth calibration either.

## Read side effects and driver ownership

There is positive source evidence for ordinary status reads: [m1n1 `pmgr.c`](https://github.com/AsahiLinux/m1n1/blob/3e354a2467f4f724f254362626cae0633918e0c1/src/pmgr.c) repeatedly reads and polls this register type; Linux uses `regmap_read()` and `regmap_read_poll_timeout_atomic()` to inspect `ACTUAL`. Neither path acknowledges status by reading it or documents read-to-clear behavior. A 32-bit status read therefore has a substantially better basis than a guessed register access.

This is still reverse-engineered behavioral evidence, not a silicon guarantee that reading PCPM is inert in every deepest state. MMIO traffic can perturb fabric power, and an inaccessible domain can fault or stall. A read's lack of an explicit write does not guarantee no physical side effect.

The parent PMGR bank is already a shared `syscon` / `simple-mfd` resource. The checked [T8103 PMGR child DTS](https://github.com/AsahiLinux/linux/blob/77cb8f24c2381a8abb7272d7bbdec548d6426a8a/arch/arm64/boot/dts/apple/t8103-pmgr.dtsi) starts normal domain controls at offset `0x100` and has no CPU/CPM child controls for PS3. This does not make the parent MMIO space ownerless. Its normal regmap ownership should be reused; do not request exclusive ownership of the whole region, rebind PMGR, construct a conflicting cacheable mapping, or call power-on APIs merely to make a sample readable.

A read through the existing uncached regmap does not change target/reset/auto-enable fields and serializes normally with users of that regmap. It is not an atomic snapshot of concurrent autonomous state changes, and other code using separate mappings may operate outside its lock. The native kernel's actual regmap configuration, bindings, resource size, and access rules must be checked before a helper is loaded. Do not accidentally create a new regmap/clock-enable path while expecting to reuse an existing one.

## Why `cpu-impl-reg + 0x100` is not the better first observable

[m1n1's `smp_stop_cpu`](https://github.com/AsahiLinux/m1n1/blob/3e354a2467f4f724f254362626cae0633918e0c1/src/smp.c#L214) polls `read64(cpu->impl_reg + 0x100) & 0xff` and considers zero evidence of stopped completion after its explicit stop request. That proves a narrow stopped-status use. It does not decode individual bits into WFI depth, nor show that returning deep WFI clears the byte.

For full deep sleep that same function deliberately does not poll the register: its comment says stopping the last core in a cluster removes register access. This makes it a poor first probe for the very state we want to observe. The known local addresses include PCPU0 `0x211050100` through PCPU3 `0x211350100`, but address knowledge alone is insufficient to authorize safe runtime reads during cluster-off.

The [pinned hypervisor implementation](https://github.com/AsahiLinux/m1n1/blob/3e354a2467f4f724f254362626cae0633918e0c1/src/hv/hv.c#L40) installs a hook at each `cpu-impl-reg + 0x100`. For a 32-bit read it reads the physical register, then **clears its low byte when the guest has not started that CPU**. Thus the guest can see a synthesized stopped state while the physical core is used by m1n1. These readings under the hypervisor are not an independent native hardware-state oracle. The Python hypervisor also reserves these hooks and intercepts `CYC_OVRD` writes.

## Smallest later native C acquisition

This is an instrumentation design, not a proposed power-management fix or an executed experiment.

1. Confirm native T8103 boot, exact kernel/DT/m1n1 versions, current CPU topology, and the existing PMGR regmap. Reconfirm offset `0x48` against that boot's retained ADT/DT evidence. Abort rather than guess if the topology/resource differs.
2. Use a small temporary kernel C helper sharing the already-established PMGR regmap. The capture operation is one `regmap_read(map, 0x48, &raw)` bracketed by monotonic timestamps, with return code and executing CPU ID stored to preallocated memory. No inline assembly is required for MMIO; Linux accessors supply the ordering and width contract. A direct future `readl()` implementation would need the owner's existing proper `__iomem` mapping, not an integer-address dereference. [Linux MMIO documentation](https://docs.kernel.org/driver-api/device-io.html)
3. Run the observer on one verified E core so sampling does not itself execute on and wake the P cluster. Avoid printing, SSH streaming, allocation, or IPIs to P cores in the capture loop. Initially take sparse, bounded samples, not a tight polling loop. A short run could retain `{t_before,t_after,cpu,raw,ret}` and return data after completion.
4. First establish readable and repeatable values with ordinary P-core activity. Then compare a settled interval in which all P cores' software CPU PD intervals overlap, keeping the same E-core observer. Preserve trace loss and time-alignment uncertainty. A changed PCPM `ACTUAL` value is the desired independent observation; a constant value is also meaningful evidence that this candidate has not distinguished the states under those conditions.
5. If the candidate differentiates conditions, test whether sampling rate changes the result before extending to duration estimates. Sparse point samples estimate occupancy only under explicit sampling assumptions; they cannot recover precise transition counts or short-state residency. Maintain a separate untraced/uninstrumented energy baseline.

Conceptual capture, assuming a previously verified existing regmap:

```c
sample.t_before = ktime_get_mono_fast_ns();
sample.ret = regmap_read(pmgr_map, 0x48, &sample.raw);
sample.t_after = ktime_get_mono_fast_ns();
/* Record raw and error. Decode later: actual = (raw >> 4) & 0xf. */
```

This excludes power-state writes, sticky-flag clearing, governor changes, hotplug, forced idle, retention-bit changes, PMU programming, and clock/power reference acquisition. If reading requires powering PCPM up, the proposed observation is unsuitable.

## Interpretation boundary

The first successful result can establish that PMGR's **reported current PCPM state** differs between native execution conditions. It cannot yet prove a CPU-idle defect, a lost Linux transition, full-cluster rail state, macOS equivalence, or energy savings. Stronger claims require validating what PCPM's state machine represents and showing that the observer does not prevent the transition.

Asahi and Aurora's checked CPU idle routines are equivalent for this purpose: both already request the deeper WFI mode and account software time. Their implementations supply the software reference, not the independent observable. [Asahi driver](https://github.com/AsahiLinux/linux/blob/77cb8f24c2381a8abb7272d7bbdec548d6426a8a/drivers/cpuidle/cpuidle-apple.c), [Aurora driver](https://github.com/aurora-silicon/linux/blob/1d2904fd3301c63620f07c81ae79f2486a81a9a6/drivers/cpuidle/cpuidle-apple.c).
