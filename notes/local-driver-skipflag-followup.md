# APSC idle-wait skip flag: static configuration resolved

2026-10-01 follow-up to [local-driver-notes.md](local-driver-notes.md), using the same UUID-matched macOS kernelcache. All inspection remained read-only. Addresses below are unslid static virtual addresses, with the common `fffffe000` prefix omitted where shown compactly.

**Result:** the flag at `AppleT8103PMGR this+0x73a52` is set when PMGR feature 2, named **`cpu-tvm`**, is nonzero. That feature defaults to zero, and **`cpu-tvm` is absent from this machine's captured PMGR device-tree and IOService provider properties**. The object allocator requests zeroed memory. Thus the checked initialization path leaves the skip flag clear, and the already-identified last-active-core callback is expected to execute `_waitAPSCPending` on this machine.

This upgrades the earlier unresolved-condition finding to a **static configuration prediction**. It is not a live read of the private flag and does not measure how frequently the pending bit is set or whether the wait improves power use. It also does not prove the absence of every possible indirect memory write; the relevant constructors, property loader, feature reader, initialization chain, and direct accesses were checked.

## Exact write and read

In `AppleT8101PMGR::initDriver(IOService*)`:

```asm
9e94a48: mov  x20, x0                    ; this
9e94a4c: add  x8, x0, #0x73, lsl #12
9e94a50: add  x22, x8, #0x93a             ; x22 = this + 0x7393a
...
9e94adc: mov  x0, x20
9e94ae0: mov  w1, #0x2                   ; Feature 2
9e94ae4: bl   ApplePMGR::getFeatureValue
9e94ae8: cbz  w0, 9e94af4
9e94aec: mov  w8, #0x1
9e94af0: strb w8, [x22, #0x118]          ; this + 0x73a52 = 1
```

The previously identified consumer is:

```asm
9e991f4: add  x20, x0, #0x73, lsl #12
...
9e99228: ldrb w8, [x20, #0xa52]          ; this + 0x73a52
9e9922c: tbnz w8, #0, 9e9924c            ; skip pending wait if set
...
9e99248: bl   AppleT8101PMGR::_waitAPSCPending
```

The field is a cached initialization boolean for the tested feature, not the value of the pending-DVFS bit itself. Its only identified direct setter is the conditional byte store above. Nearby `this+0x73a51`, `+0x73a53`, and `+0x73a54` are distinct fields; quiesce/restore writes to `+0x73a53` do not modify this flag.

Full instructions and bytes are in [driver-skipflag-init-and-read.disasm](raw/driver-skipflag-init-and-read.disasm).

## Feature identity and default

The ApplePMGR constructor copies a `0x918`-byte feature table (97 rows, 24 bytes each) from VM `8227c70` to `this+0x1d50` at `9ade780`–`9ade790`. Row 2 begins at VM `8227ca0`, full kernelcache file offset `0x1223ca0`:

```text
58 53 6c 00 00 00 30 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
```

Its chained string pointer is `0x00300000006c5358`; the target is full-file offset `0x6c5358`, string `cpu-tvm`. The value at row offset `+0x0c` is zero. `ApplePMGR::getFeatureValue`, VM `9adfc94`, reads exactly:

```text
*(uint32_t *)(this + 0x1d50 + 24 * feature_id + 0x0c)
```

Feature 0 is `cpu-apsc`, feature 1 is `soc-apsc`, and feature 2 is `cpu-tvm`. The presence of `cpu-apsc=1` on this M1 must not be confused with the feature controlling this skip flag. No expansion of the acronym TVM is established here.

Evidence: [raw feature bytes and provider property inventory](raw/driver-skipflag-feature-and-adt.json), [constructor, value reader and property loader](raw/driver-skipflag-feature-loading.disasm).

## Why absence leaves the value zero

`ApplePMGR::start` walks the feature rows. At `9adedd0`, it calls `getDTProperty` with the row's name. If the property is missing, `9adedd4` jumps directly to the next row at `9adee34`, preserving the constructor's default. If present, it copies the 32-bit property to row `+0x0c` at `9adede0`. The potential boot-argument override is downstream of the successful-property branch and uses that same name. Recorded running boot arguments are only `-v` in any case.

`getDTProperty` at `9adf9b8` looks up the supplied name on the provider at `this+0x88`, checks that the result is OSData, and copies its first 32-bit value without a fallback to another feature name. Both captured trees contain a PMGR provider with no `cpu-tvm` property. They do contain `cpu-apsc=1`, `soc-tvm=1`, and `apsc-snooze=1`; none of those is feature 2's property.

The evidence file records the full property-name inventory so the absence is independently checkable. This conclusion uses the captured provider metadata; no private live feature array was read.

## Why the flag begins clear

`AppleT8103PMGR::MetaClass::alloc`, VM `9ec47c0`, requests `0x783d0` bytes through `_OSObject_typed_operator_new` at `9ec47e4`, then invokes the T8101 constructor. The exact local kernel's `_OSObject_typed_operator_new` at `c2ab7dc` passes flag `4` to `_kalloc_type_impl_external` at `c2ab824`. Its oversized fallback also includes bit `4` (`0x41004`).

Pinned public Apple XNU identifies `4` as `Z_ZERO`, and `OSObject_typed_operator_new` uses `Z_WAITOK_ZERO` for both allocation branches. This source supports the interpretation of the local assembly rather than replacing it: [OSObject.cpp](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/libkern/c%2B%2B/OSObject.cpp#L312), [zalloc.h](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/osfmk/kern/zalloc.h#L461). The public code is linked rather than copied here.

The T8101 constructor copies its vector defaults to `this+0x73948` through exclusive end `this+0x73a44`; this does not reach `this+0x73a52`. Its subsequent explicit writes target other fields. The T8103 constructor sets its vtable after calling T8101 and does not overwrite the flag. Consequently the flag remains at its allocated zero until the conditional `cpu-tvm` setter.

Exact local allocator instructions: [driver-skipflag-allocator.disasm](raw/driver-skipflag-allocator.disasm).

## Actual T8103 initialization reaches the setter

Near the end of `AppleT8103PMGR::initDriver`, instructions `9ec54a4`–`9ec54c4` load the parent T8101 vtable at `82f19b8`, fetch its slot at absolute offset `+0xcc8`, and call it with the original `this` and provider. The raw pointer at VM `82f2680` is `0x8011e86802e90a1c`, resolving to `9e94a1c`, the T8101 `initDriver` containing the setter. This closes the inheritance seam: the setter is not merely code for an unrelated chip.

The resolved pointer and raw bytes are preserved in [driver-skipflag-feature-and-adt.json](raw/driver-skipflag-feature-and-adt.json), and both complete init functions are in [driver-skipflag-init-and-read.disasm](raw/driver-skipflag-init-and-read.disasm).

## Updated interpretation

The trace target can now be stated more strongly: **this M1's captured configuration selects the last-active-core pending-APSC wait path in the inspected driver initialization**. The branch still needs runtime confirmation if the question is what actually happened during a specific idle transition. The proposed experiment should retain the skip flag and pending-DVFS register in its capture, but the former is now an expected-clear check rather than an unexplained configuration variable.

This still establishes no Linux bug or demonstrated energy saving. The concrete physical polling targets remain `0x210e20020` and `0x211e20020`, bit 31, as resolved in the earlier report.
