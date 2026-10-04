# M1 CPU Idle Research Wiki

This wiki tracks one question: **which CPU-idle decisions made by macOS on base M1 are absent or different in Linux, and does that difference change native hardware residency or energy?** The investigated machine is a T8103 MacBook Air, running macOS 27.0 build 26A428 for the local binary and IOReport work. The repository is a dated research snapshot, so current software and boot state must be rechecked.

## Navigation

| Topic | Page |
|---|---|
| How an agent should take over | [Agent Orientation](Agent-Orientation.md) |
| Claim levels and reproducibility | [Evidence Standard](Evidence-Standard.md) |
| Supported conclusions and unresolved claims | [Findings Index](Findings-Index.md) |
| ApplePMGR, CLPC, WFI, APSC, and exact local assembly | [macOS Control Path](MacOS-Control-Path.md) |
| AArch64 PMGR command and performance-marker ordering | [Instruction-order audit](../notes/mac-pmgr-command-order.md) |
| Safe user-mode `MRS` probe and access boundary | [EL0 capability probe](../notes/el0-capability-probe.md) |
| Asahi, Omacom, and Aurora source comparison | [Linux fork baseline](Linux-and-Aurora-Baseline.md) and [Omacom source audit](../notes/omacom-linux-source-audit.md) |
| Host macOS investigation without reboot | [Non-Reboot Investigation](Non-Reboot-Investigation.md) |
| Five-second privileged ktrace capture | [Live Mac Tracing](Live-Mac-Tracing.md) |
| Mac-only timing analysis of saved performance-request markers | [Trace correlation audit](../notes/mac-ktrace-perf-request-correlation.md) |
| Earlier native Linux measurements | [Prior Native Linux Results](Prior-Native-Linux-Results.md) |
| Falsifiable next experiments | [Experiment Backlog](Experiment-Backlog.md) |

The detailed [research report](../notes/README.md) and [supporting notes](../notes/) are the record behind this guide. The strongest candidate is the **macOS last-active-core APSC/DVFS wait**. Its binary path and static enablement are evidenced. Its runtime frequency, silicon effect, and relevance to a Linux change remain open.

## Quick state of the research

| Question | Current answer | Evidence tier |
|---|---|---|
| Does Linux already request deep WFI on M1? | Yes, in the pinned Asahi/Omacom/Aurora `apple_idle` driver. | Pinned public source; historical native software counts |
| Does the checked macOS PMGR path have a last-core DVFS/APSC wait? | Yes; local disassembly identifies the path and register reads. | Matching local binary |
| Is that wait enabled on this Mac? | Static configuration predicts yes; live branch frequency still needs tracing. | Local binary plus captured properties |
| Do nearby performance requests coincide with longer last-E-core callbacks? | In one retrospective five-second trace, yes for one request marker; cause remains unknown. | Live software markers and callback timing |
| Does Linux reach the same physical core/cluster-off residency as macOS? | Unknown. | No independent native state/residency qualification |
| Is adding a BUSY wait to Linux correct or energy-saving? | Unknown. ABI 3 observed BUSY before WFI, but not at the instruction or in a characterized physical state. | [Native A/D/E packet](../experiments/aurora-apsc-observer/ABI3-E-TICKET-RESULT.md); no energy measurement |
| Can a normal macOS app use Hypervisor.framework to inspect its running host at EL2? | The documented API creates isolated guests and maps guest memory from the app; host PMGR access does not follow from it. | Inference from Apple API design |

The table is a finding map, not a maturity score. Follow the linked pages for proof, caveats, and the next discriminating measurement.
