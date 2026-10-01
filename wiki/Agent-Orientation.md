# Agent Orientation

This page is the shortest handoff for a new research agent. The objective is a **validated, Linux-relevant explanation** of any remaining macOS/base-M1 CPU-idle difference. Prefer a small observation that can refute a hypothesis over an early power-policy patch.

The coordinated APSC/DVFS investigation lives in the [Wayfinder decision map](https://github.com/malik-na/m1-cpu-idle-research/issues/1). For that effort, take one open, unblocked, unassigned child ticket and claim it before work. The [issue-tracker guide](../docs/agents/issue-tracker.md) explains the GitHub sub-issue and blocking conventions. The map is the decision index; this page remains the evidence handoff.

## Read path

1. Read repository [AGENTS.md](../AGENTS.md) and [Evidence Standard](Evidence-Standard.md). Completion: identify the evidence tier required by your intended claim.
2. Read [Findings Index](Findings-Index.md), [macOS Control Path](MacOS-Control-Path.md), [Linux fork baseline](Linux-and-Aurora-Baseline.md), and the [Omacom source audit](../notes/omacom-linux-source-audit.md). Completion: name one checked behavior already implemented by Linux and one actual unanswered question.
3. Select one item from [Experiment Backlog](Experiment-Backlog.md). Completion: write the expected observation, a result that would weaken the hypothesis, target/source identity, and instrumentation effect.
4. Follow the relevant detailed note under [`notes/`](../notes/README.md) and its raw/source evidence. Completion: point to the exact record or pinned upstream line supporting every technical premise.
5. Run a bounded observation, preserve raw values and failures, and update the finding only to the level the evidence supports. Completion: a reader can reconstruct the conclusion and its limits.

## The two leading leads

**Last-core APSC/DVFS ordering.** The matching macOS kernelcache disassembly connects `ApplePMGR::_cpuIdle`'s last-active-core branch to `cpuComplexIdleEnter` and `_waitAPSCPending`, which polls the DVFS command BUSY bit. The local `cpu-tvm` configuration predicts that the wait is enabled. Linux's inspected cpufreq path waits before issuing a *new* command, whereas its idle driver has no corresponding explicit post-request wait. The checked Omacom fork does not add one for M1. A [Mac-only trace correlation](../notes/mac-ktrace-perf-request-correlation.md) found longer apparent last-E-core callbacks soon after one performance marker, but still did not observe the wait or BUSY bit. Read the [exact-build marker-order audit](../notes/mac-pmgr-command-order.md) before using that correlation: the CPU-complex emitter records after `setPerfState` return, but three other callers share the marker helper and a saved event does not identify its origin. This is a testable difference, not yet a Linux defect. Begin at [macOS Control Path](MacOS-Control-Path.md), [Omacom source audit](../notes/omacom-linux-source-audit.md), and [`notes/linux-dvfs-idle-concurrency.md`](../notes/linux-dvfs-idle-concurrency.md).

**Physical state observability.** macOS IOReport and Linux `state1/time` record software-reported idle, not independently calibrated rail-off time. An audited PCPM PMGR state register is a candidate read-only native observable, but its exact power-domain meaning and observer effect must be validated. Begin at [`notes/idle-observable-audit.md`](../notes/idle-observable-audit.md).

## Reproducibility packet for every new result

Record: date/time; device and SoC; running OS/build/kernel; exact source and firmware revisions; relevant boot arguments and configuration; whether the target is native or a guest; power source, display, USB, thermal and background-load conditions; instrumentation version and clock units; raw event/measurement file; transformation script; loss/error counts; expected-versus-observed result; competing explanation. A versioned source snapshot and a physical hardware observation are different evidence, even if they agree.

Avoid broad novelty claims. The checked public code and literature provide a baseline, while a bounded search cannot prove that Asahi or Aurora researchers have never found something. A publishable contribution can be narrower: a reproducible build-specific control-path mapping, a validated state observable, or a measured policy difference with a Linux implementation contract.
