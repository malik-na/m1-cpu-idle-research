// AArch64 EL0-only arithmetic probe. Reads architectural virtual time counter.
// x0: duration in counter ticks; x1: arithmetic seed; returns updated seed.
// No privileged system-register writes, WFI, cache controls, or MMIO.
.text
.p2align 2
.globl _idle_burst
_idle_burst:
    isb
    mrs x2, cntvct_el0
    add x2, x2, x0
    mov x3, #0x5851
    movk x3, #0x4c95, lsl #16
    movk x3, #0xf42d, lsl #32
    movk x3, #0x1405, lsl #48
1:
    .rept 32
    madd x1, x1, x3, x3
    eor x1, x1, x1, lsr #17
    .endr
    isb
    mrs x4, cntvct_el0
    cmp x4, x2
    b.lo 1b
    mov x0, x1
    ret
