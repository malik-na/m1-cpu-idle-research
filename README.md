# M1 CPU Idle Research

A public research notebook on how macOS 27 controls CPU idle on a base M1 (T8103), how the inspected Asahi Linux, Omacom, and Aurora Silicon implementations compare, and what must be measured before changing Linux. The reference machine is a MacBook Air (J313 / MacBookAir10,1). This repository is an evidence handoff, not a finished power-saving patch.

**[Browse the research website](https://malik-na.github.io/m1-cpu-idle-research/)** for the evidence matrix, searchable notebook, full wiki pages and [agent entry point](https://malik-na.github.io/m1-cpu-idle-research/llms.txt). Each publication identifies its source commit and preserves the original Markdown and evidence files. The [website guide](site/README.md) documents how to rebuild it.

The most concrete current lead is a **control-path difference**: the inspected macOS `AppleT8103PMGR` last-active-core idle path conditionally waits for the cluster DVFS/APSC command's BUSY bit to clear; the pinned Linux CPU-idle path has no explicit matching wait. A later [native Linux observation](experiments/aurora-apsc-observer/NATIVE-RESULT.md) read the APSC command register with BUSY set at a pre-WFI hook, following a same-CPU SET. Classifying that sample as a software candidate final entrant assumes an unproven cross-CPU clock bound. We have not observed BUSY at the WFI instruction, physical power state or energy, nor established a Linux defect. See [macOS control path](wiki/MacOS-Control-Path.md) and [experiment backlog](wiki/Experiment-Backlog.md).

A Mac-only reanalysis of the saved five-second trace found a **timing lead**: apparent last E-core idle-entry callbacks soon after one PMGR performance-request marker were longer than callbacks without a recent marker. The [AArch64 instruction-order audit](notes/mac-pmgr-command-order.md) shows that the CPU-complex emitter records its marker after `setPerfState` returns, while three other functions share the marker helper. A saved marker identifies neither its call site nor the command-write time or BUSY state. The [reproducible correlation note](notes/mac-ktrace-perf-request-correlation.md) gives the counts, controls, and limits. A [safe EL0 assembly probe](notes/el0-capability-probe.md) identified counter and CPU-tag registers usable without a reboot, and directly confirmed that user mode cannot read the power-control register here.

Another build-specific finding: `cpu-power-gate-latency-us = 50000` reaches XNU's **nanosecond** software latency input unchanged, yielding **50 microseconds** in the checked running build. This is not a measured hardware exit latency and should not be copied into Linux cpuidle metadata. The chain is recorded in [macOS control path](wiki/MacOS-Control-Path.md).

## Start here

| If you want to… | Read |
|---|---|
| Orient a new investigator or coding agent | [Agent Orientation](wiki/Agent-Orientation.md), then [AGENTS.md](AGENTS.md) |
| Coordinate the multi-session APSC/DVFS decision | [Decide whether base-M1 Linux CPU idle needs an APSC/DVFS wait](https://github.com/malik-na/m1-cpu-idle-research/issues/1) and [issue-tracker guide](docs/agents/issue-tracker.md) |
| Understand exactly what is known | [Evidence Standard](wiki/Evidence-Standard.md) and [Findings Index](wiki/Findings-Index.md) |
| Follow the macOS binary and assembly evidence | [macOS Control Path](wiki/MacOS-Control-Path.md) |
| Reproduce instruction-level command/marker order | [PMGR ordering audit](notes/mac-pmgr-command-order.md) |
| Run the bounded user-mode register probe | [EL0 probe](notes/el0-capability-probe.md) |
| Check what Asahi, Omacom, and Aurora already implement | [Linux fork baseline](wiki/Linux-and-Aurora-Baseline.md) and [Omacom source audit](notes/omacom-linux-source-audit.md) |
| Investigate the running Mac without rebooting | [Non-Reboot Investigation](wiki/Non-Reboot-Investigation.md) |
| Check the privileged native tracing gate | [macOS direct-observation route and SIP result](notes/mac-apsc-direct-observation-route.md) |
| Prepare the Linux observation experiment | [Observer patch and analyzer](experiments/linux-apsc-observer/README.md), then [future native-run checklist](experiments/linux-apsc-observer/NATIVE-RUN.md) |
| Reconstruct the completed native A/B/C observation | [Result and limits](experiments/aurora-apsc-observer/NATIVE-RESULT.md), then [public numerical packet](experiments/aurora-apsc-observer/native-evidence/README.md) |
| Check whether cross-CPU timestamps support an ordering | [Counter qualification helper and decoder](experiments/linux-counter-qualification/README.md), with [raw ABI](experiments/linux-counter-qualification/ABI.md) |
| Prepare sparse PCPM state observation | [Read-only sampler preparation](experiments/linux-pcpm-sampler/README.md) and its [raw ABI](experiments/linux-pcpm-sampler/ABI.md); native calibration remains open |
| Reproduce and interpret the five-second root trace | [Live Mac Tracing](wiki/Live-Mac-Tracing.md) |
| Follow the Mac-only performance-request timing lead | [Trace correlation audit](notes/mac-ktrace-perf-request-correlation.md) |
| Interpret the earlier Linux measurements | [Prior Native Linux Results](wiki/Prior-Native-Linux-Results.md) |
| Run a discriminating next experiment | [Experiment Backlog](wiki/Experiment-Backlog.md) |

The longer primary investigation and supporting records live in [`notes/`](notes/README.md). The notes retain local disassembly excerpts, parsed device-tree facts, pinned public-source manifests, a sanitized live trace, measurement summaries, and tools. [`wiki/`](wiki/Home.md) is the guided entry point. Links to public upstream source use commit IDs wherever possible; branch names alone are not reproducible evidence.

[Provenance and publication boundary](PROVENANCE.md) explains which local evidence was withheld and how to verify the published packet. Run `python3 tools/verify_repository.py` after edits to check links, hashes, and the reproducible trace summary.

## Current evidence boundary

- The inspected Asahi, Omacom, and Aurora base-M1 `cpuidle-apple.c` files are byte-identical at the pinned revisions. Omacom's default `asahi` branch is the exact Asahi commit already checked, so it is not independent evidence of a different M1 idle implementation. Linux already has a returning deep-WFI state; reimplementing that state is not a new result. [Pinned comparison](wiki/Linux-and-Aurora-Baseline.md).
- macOS IOReport shows CPU and cluster IDLE time and transitions on the running Mac, but exposes one undifferentiated CPU IDLE bin. It cannot identify retention, power collapse, or rail-off duration. [Measurement interpretation](wiki/Findings-Index.md).
- Historical native Linux captures show all eight CPUs entering the software `CPU PD` state, yet do not independently prove physical core/cluster power-off. [Prior results](wiki/Prior-Native-Linux-Results.md).
- A privileged DTrace FBT inventory on native macOS 27.0 / 26A428 returned only a header and a SIP restriction diagnostic, despite exit status zero. It enabled no probes and supplied no APSC branch or BUSY value. [Exact inventory](notes/raw/mac-fbt-inventory-26A428.json).
- The default-off Linux observer was ported to the selected Aurora source, built, and booted in a separate research entry. The completed three-boot block observed APSC command-register BUSY at a pre-WFI hook. The result supports no WFI-instruction, physical-power, energy, wake-latency, or policy-improvement claim. [Native result](experiments/aurora-apsc-observer/NATIVE-RESULT.md).
- The later five-boot ABI 2 block observed four BUSY command words at the first-attempt pre-DSB WFI-seam probe. One is a conditional software final-entrant candidate under an unmeasured cross-CPU clock bound; its SET-to-read lag is exploratory under the declared primary gate. No observation establishes BUSY at the WFI instruction or physical power behavior. [Matched-block result](experiments/aurora-apsc-observer/WFI-ABI2-BLOCK-RESULT.md).

If you point an agent here, use this handoff: **“Read `AGENTS.md` and `wiki/Agent-Orientation.md`, choose one open hypothesis from `wiki/Experiment-Backlog.md`, verify pinned source and target identity, and report a falsifiable result with evidence tier and limitations. Preserve existing observations.”**

Investigation snapshot: **2026-10-03**. Hardware, operating-system builds, branch heads, and available boot media can change; refresh them before a new runtime experiment.
