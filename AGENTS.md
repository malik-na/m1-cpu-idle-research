# Research agent instructions

This repository studies base-M1 (T8103) CPU idle across macOS and Linux. Treat it as an evidence notebook. Start with [Agent Orientation](wiki/Agent-Orientation.md) and choose one question from [Experiment Backlog](wiki/Experiment-Backlog.md).

1. **Pin the target.** Record chip/board, running OS and kernel/build, boot firmware, relevant source commit, configuration, and whether the result is static or runtime. For a public-source claim, cite the exact file and immutable revision. Completion: another investigator can identify the same target and code.
2. **State a falsifiable hypothesis.** Name the observable, expected result, counterexample, and instrumentation effect before a hardware experiment. Use [Evidence Standard](wiki/Evidence-Standard.md) to select the claim level. Completion: a negative result would also be interpretable.
3. **Preserve the baseline.** Add derived notes or bounded experiment records without replacing earlier data. Keep raw event values, units, timestamps, error/drop counts, and the transformation that produced a summary. Completion: the summary can be reconstructed from retained evidence.
4. **Compare against prior work.** Consult [Linux fork baseline](wiki/Linux-and-Aurora-Baseline.md), the [Omacom source audit](notes/omacom-linux-source-audit.md), the pinned upstream code, and relevant Asahi/Aurora reports before calling a mechanism new. A fork name alone does not imply different code. Completion: the proposed contribution differs from a named, checked baseline.
5. **Report the result and its boundary.** Distinguish source-permitted behavior, local binary behavior, software accounting, guest trace, native hardware observation, and measured energy. Include contrary explanations and what would resolve them. Completion: no physical-power or novelty claim rests only on a name, counter, static branch, or search absence.

For macOS assembly and PMGR questions, read [macOS Control Path](wiki/MacOS-Control-Path.md) and [`notes/local-driver-notes.md`](notes/local-driver-notes.md). For Linux concurrency, read [`notes/linux-dvfs-idle-concurrency.md`](notes/linux-dvfs-idle-concurrency.md). For live macOS work, read [Non-Reboot Investigation](wiki/Non-Reboot-Investigation.md). For m1n1 guest tracing, read [`notes/trace-validity.md`](notes/trace-validity.md) before interpreting any trace.

Keep public artifacts free of passwords, private network addresses, account names, host paths, machine identifiers unrelated to the chip/build, and unreviewed proprietary binaries. Obtain the target operator's authorization before root sessions, reboots, security-policy changes, hardware-register writes, or kernel/firmware installation. Keep observation-only variants separate from experiments that alter idle behavior.

Before publishing an update, run `python3 tools/verify_repository.py`. Read [provenance and publication boundary](PROVENANCE.md) before adding raw captures or third-party source.
