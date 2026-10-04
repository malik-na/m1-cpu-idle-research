# Prospective native ABI 3 ticket block

This plan was fixed before the ABI 3 full build or any native ABI 3 capture.
It extends the [ticket protocol](WFI-ABI3-TICKET-PROTOCOL.md) for
[issue #5](https://github.com/malik-na/m1-cpu-idle-research/issues/5).
The hypothesis is that a first-attempt **pre-DSB command read** can return
BUSY while all three peer CPUs have recorded, enclosing software idle-hook
intervals, with candidate and peer order proven by a per-cluster atomic
ticket stream. A clean BUSY read without enclosing peer intervals is a
counterexample to that *candidate* classification, not evidence that such an
overlap never occurs. Even a positive ticket witness does not establish
BUSY or peer sleep at the subsequent WFI instruction.

## Fixed machine and program

Use only a separately qualified T8103/J313 Aurora ABI 3 image whose exact
source patch/tree, configuration, linked Image/modules/DTBs, installed UKI,
GNU Build-ID and live release are bound by hashes. Keep the stock Omarchy
default and the already qualified PCPM research image bootable. On each
fresh boot, check the selected Limine entry, all eight online CPUs, E/P
device-tree command resources and policy masks, `apple_idle`/`menu`, LSE
`atomics` support on every CPU, observer ABI/status and Wi-Fi before arming.
On the first boot of this new image, verify visible brightness control once
as a display-regression check; later boots need a working backlight interface
and the fixed setting, without repeating a visual dimming test unless a
regression is reported. Require AC online `1` and panel
brightness `155` at preflight and both capture endpoints. Record thermal,
network/USB and policy snapshots rather than assuming equal background
conditions. A failed boot or device check produces an incident record, not
an APSC observation.

Each measurement boot runs the same pinned
[`pulse_workload_abi3.c`](pulse_workload_abi3.c) on CPUs 1 and 5. This is
200 normally scheduled pulses per CPU, 50 ms apart, with 1,048,576
iterations per pulse. Start the workers one second in the future; begin a
10,000 ms observer window 150 ms after their scheduled start. Retain every
worker row and use only pulses fully inside a conservative kernel-reported
`CLOCK_MONOTONIC` interior interval for matched comparisons: the start
marker must be taken after activation and the stop marker before
deactivation. Observer counter ticks and worker nanoseconds cannot be
compared directly. Reject incomplete work, CPU migration, overlapping or
missed pulse periods; report the actual interior count. Workers export rows
only after the collector sends the explicit `E` release token. The
prepared workload source SHA-256 is
`a9b5dedf8b42c7013ebb87cc3754dce1f80fce293a02911b5e8175d61d4eff73`;
`cc -O2 -std=c11 -Wall -Wextra -Werror` with GCC 16.1.1 produced a private
binary SHA-256 of
`2b4ed83c6f81be68eeb4e9aa448eb81493852f1bf114edb249f75a1e55234a89`.
Recheck those bytes on the acquisition boot. The
collector must save its own source/binary hashes, the workload source and
binary hashes, raw observer status/events/WFI events, exact read/write
timing, a private boot/source identity, pre/post machine environment and
kernel logs, and a byte-exact private manifest. Public export removes
machine IDs, credentials, network identifiers and full boot arguments while
retaining replayable numerical streams and hashes.

## Boot order and decisions

1. A: unarmed baseline on a fresh ABI 3 boot with the same workload. The
   observer remains `ready`; no capture command is issued.
2. D: ticket-only `wfi_clock` on a new boot. It executes the same ticket,
   barrier and record work as E while omitting the command load. Reject D
   if any stream loses records or if ticket/slot accounting fails.
3. E: `wfi_mmio` on another new boot. A single command load is made on the
   first deep-WFI attempt only. Preserve all BUSY and clear words, plus
   every rejected or incomplete ticket candidate and its reason.
4. If E has no ticket-qualified BUSY candidate and the primary exposure
   gate below might be met, run a fresh-boot C idle-enter `mmio` read
   control under the same workload to check comparable-lag command-read
   sensitivity on both clusters. C is not a substitute for E and cannot
   recover WFI-time state.

One successful or failed one-shot acquisition consumes that boot. No
same-boot retry is an independent replicate. Stop after a clean positive
ticket witness or after the declared negative-sensitivity decision; any
additional design needs its own protocol. The historical ABI 2 D/E/C/B/A
block is context, not a matched control for this shared-atomic instrument.

Before classifying E, require a complete capture, zero idle/DVFS/WFI
overflow or missing commits, unique contiguous per-cluster tickets between
start/stop sentinels, stable topology/policies, valid command and local
counter brackets, and no CPU-PM failure or contradictory token interval.
The offline validator must rederive these checks from raw rows, not trust
`state=complete` alone. A positive is a BUSY-bit read with the strict
software-hook ticket inequalities in the ticket protocol. Report its raw
command, CPU, cluster, token, peer intervals, and every recorded SET
writer/target and timing ambiguity. Only same-CPU SET-to-read order is
direct without a separately qualified cross-CPU bound.

A zero is a sensitive negative only if E contains at least 20 clean
candidate-specific primary SET-to-probe opportunities **per cluster**,
each with a conservative ≤600-tick upper lag using same-CPU order or a
separately qualified clock bound, and C demonstrates comparable-lag BUSY
read sensitivity on both clusters under adequately matched work and
environment. A positive outside 600 ticks remains a positive at its
actual read; the 600-tick criterion applies to negative sensitivity.
If these gates fail, report underexposure or mismatch rather than absence.
Compare A/D/E delivered work and probe/ticket costs without calling the
difference energy, latency, or an isolated causal observer effect. No
Linux idle-policy change follows from this block.
