# M1 CPU Idle Research

A public research notebook on how macOS 27 controls CPU idle on a base M1 (T8103), how the inspected Asahi Linux, Omacom, and Aurora Silicon implementations compare, and what must be measured before changing Linux. The reference machine is a MacBook Air (J313 / MacBookAir10,1). This repository is an evidence handoff, not a finished power-saving patch.

The most concrete current lead is a **static control-path difference**: the inspected macOS `AppleT8103PMGR` last-active-core idle path conditionally waits for the cluster DVFS/APSC command's BUSY bit to clear; the pinned Linux CPU-idle path has no explicit matching wait. The local configuration predicts that macOS enables the wait. We have **not** measured how often it runs, whether Linux ever overlaps an outstanding command with deep WFI, or whether any difference affects physical power state or energy. See [macOS control path](wiki/MacOS-Control-Path.md) and [experiment backlog](wiki/Experiment-Backlog.md).

A Mac-only reanalysis of the saved five-second trace found a **timing lead**: apparent last E-core idle-entry callbacks soon after one PMGR performance-request marker were longer than callbacks without a recent marker. That marker is not a command-register read or proof that the APSC wait ran. The [reproducible correlation note](notes/mac-ktrace-perf-request-correlation.md) gives the counts, controls, and limits.

Another build-specific finding: `cpu-power-gate-latency-us = 50000` reaches XNU's **nanosecond** software latency input unchanged, yielding **50 microseconds** in the checked running build. This is not a measured hardware exit latency and should not be copied into Linux cpuidle metadata. The chain is recorded in [macOS control path](wiki/MacOS-Control-Path.md).

## Start here

| If you want to… | Read |
|---|---|
| Orient a new investigator or coding agent | [Agent Orientation](wiki/Agent-Orientation.md), then [AGENTS.md](AGENTS.md) |
| Understand exactly what is known | [Evidence Standard](wiki/Evidence-Standard.md) and [Findings Index](wiki/Findings-Index.md) |
| Follow the macOS binary and assembly evidence | [macOS Control Path](wiki/MacOS-Control-Path.md) |
| Check what Asahi, Omacom, and Aurora already implement | [Linux fork baseline](wiki/Linux-and-Aurora-Baseline.md) and [Omacom source audit](notes/omacom-linux-source-audit.md) |
| Investigate the running Mac without rebooting | [Non-Reboot Investigation](wiki/Non-Reboot-Investigation.md) |
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
- No Linux idle change, boot configuration change, reboot, privileged hardware-register access, or physical power claim is part of this repository's completed result.

If you point an agent here, use this handoff: **“Read `AGENTS.md` and `wiki/Agent-Orientation.md`, choose one open hypothesis from `wiki/Experiment-Backlog.md`, verify pinned source and target identity, and report a falsifiable result with evidence tier and limitations. Preserve existing observations.”**

Investigation snapshot: **2026-10-01**. Hardware, operating-system builds, branch heads, and available boot media can change; refresh them before a new runtime experiment.
