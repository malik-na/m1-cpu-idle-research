# Exact local kernel WFI instruction landmarks

These are additional read-only observations from the same UUID-matched running kernel image. No instructions were executed from these analysis copies.

At unslid `0xfffffe000bcdba1c`, the kernel calls its registered idle notification pointer after placing `1` in `w1` and supplying a stack pointer for an output value. After intervening timer/accounting work it reaches `dsb sy` at `0xfffffe000bcdba80` and calls `0xfffffe000bafd6cc`. That helper executes `wfi`, then returns when the link register is nonzero. This resembles the public XNU `cpu_idle` callback/WFI sequence, but the export labels displayed by the disassembler are only nearest-symbol annotations: this stripped internal routine is **not** `copyout` despite that label in the output. Evidence: [callback and WFI call](raw/kernel-idle-callback-and-wfi.disasm), [WFI helper](raw/kernel-wfi-primitives.disasm).

A separate non-returning helper begins at `0xfffffe000bafd630`. Its nonzero-argument branch modifies `S3_5_C15_C6_0` (the known ACC override register). Both argument paths subsequently OR `0x03000001` into `S3_5_C15_C5_0` (CYC_OVRD): WFI mode bits25:24 plus disable-retention bit0. It enters a repeating `dsb sy; isb; wfi` sequence with no normal return. Its argument affects preparation before that loop. The adjacent helper at `0xfffffe000bafd6a8` ORs only bit25 and returns.

These instructions corroborate the distinction between a returning WFI path and explicit non-returning shutdown preparation. They do not establish that ordinary idle invokes the non-returning helper, that either path achieved physical power-off during this session, or that the complete Linux save/restart contract can be inferred from this short sequence. The public XNU source and existing m1n1 sleep implementation already describe such primitives; their presence is not a novelty claim.

The disassembler's `_Switch_context+...` labels are also nearest-export annotations, not proven names for the internal helpers. Preserve addresses, instruction words, running-kernel UUID and call-site context together when using this evidence.
