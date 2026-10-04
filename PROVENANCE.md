# Provenance and publication boundary

This repository is a curated public handoff from an October 2026 investigation. Its [`notes/`](notes/README.md) pages record the original reasoning; [`wiki/`](wiki/Home.md) supplies navigation and open experiments. The checked host was a base-M1 MacBook Air (MacBookAir10,1 / J313 / T8103) running macOS 27.0 build 26A428, XNU `13432.1.9~1`, kernel UUID `1F15A5DA-11D6-39EE-88D2-153E2F90F066`. The installed kernelcache SHA-256 and decompressed-image SHA-256 are in the [sanitized extraction metadata](notes/raw/driver-kernelcache-metadata.json). The local [running-kernel identity](notes/raw/driver-running-kernel-identity.txt) was compared with the inspected image. Public XNU source at [`f6217f8`](https://github.com/apple-oss-distributions/xnu/tree/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea) is a semantic cross-check, not a claim that Apple published source matching this installed binary.

Public Linux/m1n1 comparisons are pinned in [the Asahi report](notes/asahi-known-gaps.md), [the Omacom source audit](notes/omacom-linux-source-audit.md), [the Aurora report](notes/aurora-cpu-idle.md), and the [17-file SHA-256 manifest](notes/concurrency-sources/manifest.json). Those source trees are linked at immutable commits rather than vendored. PR status and branch heads are dated observations and may have changed.

The [live trace note](notes/live-mac-trace.md) records the root-authorized five-second command and interpretation. The original 22 MB NDJSON trace remains local because it includes system-wide process metadata; its SHA-256 is in the note. [`sanitize-ktrace.py`](notes/tools/sanitize-ktrace.py) removed process/thread IDs, names and wall-clock timestamps from reviewed event IDs, producing the [published compressed event stream](notes/raw/ktrace/idle-5s-events.jsonl.gz). [`analyze-ktrace.py`](notes/tools/analyze-ktrace.py) yields the [saved summary](notes/raw/ktrace/idle-5s-summary.json); running it on the public stream reproduces the event counts and per-core/per-cluster callback timings. The full IORegistry plists and kernelcache images are not published because the plists contain machine identifiers and the binaries are not needed to reproduce the analysis method. Derived JSON projections and short disassembly extracts are preserved instead. The disassembly is build-specific evidence derived from Apple's installed binary; no ownership or license claim is made over Apple's code.

The [performance-request timing audit](notes/mac-ktrace-perf-request-correlation.md) derives an additional exploratory comparison from that same sanitized event stream. It includes the marker definitions, classification, age bins and runnable calculation; it is not a second capture or independent hardware measurement.

The later [instruction-order audit](notes/mac-pmgr-command-order.md) uses the same UUID-matched installed kernelcache, with short [AArch64 excerpts](notes/raw/driver-pmgr-perf-marker-order.disasm) only. [`marker-scope.py`](notes/tools/marker-scope.py) rechecks callback overlap in the existing public stream; it does not add a live capture. The [EL0 capability probe](notes/el0-capability-probe.md) was compiled and run directly on the Mac from the published [C and inline-assembly source](notes/tools/el0-capabilities.c). It reports register access status, frequency, and a logical CPU/cluster sample while deliberately withholding the thread-pointer and absolute-counter values. No executable, kernelcache copy, or private machine identity is published for these follow-ups.

Historical native Linux summary files under [`notes/t480-references/`](notes/t480-references/evidence__alarm-cpu-idle-03-summary.json) are limited copies of an earlier experiment. Their original raw captures and private working-tree paths are not here, so the exact native results cannot be fully reconstructed from this repository alone. The [prior-results page](wiki/Prior-Native-Linux-Results.md) states that boundary. Current Linux boot state must be rechecked before using any historical capture as a runtime baseline.

The [privileged FBT inventory](notes/raw/mac-fbt-inventory-26A428.json) is a separate operator-authenticated listing attempt on the same macOS build. It retains the complete DTrace stdout/stderr and original zero exit status; the collector's local user ID was omitted. No trace probe was enabled by the command. The revised [collector](tools/macos_fbt_inventory.py) now explicitly rejects an unusable header-only listing instead of treating that exit status as success.

The [Linux observer experiment](experiments/linux-apsc-observer/README.md) publishes a patch against an immutable Asahi Linux source revision, with a decoder, conditional candidate-final-entrant analysis, synthetic tests, and a native-run checklist. Cross-CPU candidate analysis requires an explicitly supplied pairwise clock-error assumption; it never authenticates that bound or the capture. The separate [counter-qualification experiment](experiments/linux-counter-qualification/README.md) implements the [protocol](experiments/linux-apsc-observer/CLOCK-QUALIFICATION.md)'s star route in a default-off kernel patch and offline decoder. Its raw evidence contract retains both phases, failures and per-CPU metadata, and its decoder reports conditional offset constraints rather than a guaranteed clock bound. The full downloaded Linux tree, intermediate overlays, objects, and private build environment are not publication artifacts. Patch source, cross-build validation, synthetic parser tests, and native hardware evidence are separate tiers. The later native Aurora run is recorded separately below; neither instrument demonstrates a CPU-power or Linux policy improvement.

The [PCPM sampler preparation](experiments/linux-pcpm-sampler/README.md) adds a separate default-off C patch and offline decoder for the native calibration question. It requires the captured T8103 topology and PMGR resource and reuses only a normally created, clockless generic syscon regmap. The observation adds no power-state write or Linux idle-policy wait. The corrected patch's [Aurora full-build receipt](experiments/linux-pcpm-sampler/aurora-wfi-pcpm-build-receipt.json) pins its source, configuration, final Image/modules/DTB and linked checks. Its [guarded deployment receipt](experiments/linux-pcpm-sampler/aurora-wfi-pcpm-deployment-receipt.json) records the new installed module tree and UKI, stock default and working WFI fallback, and independent readback. The new image booted with release, Build-ID and configuration matching the build, and Wi-Fi/brightness working. The [first records preflight](experiments/linux-pcpm-sampler/pcpm-records-preflight-incident-receipt.json) failed before either one-shot control; the corrected collector then completed a [records-only native run](experiments/linux-pcpm-sampler/NATIVE-RECORDS-RESULT.md) with [sanitized numerical evidence](experiments/linux-pcpm-sampler/native-evidence/records-abi2/README.md) and zero PCPM register reads. Its 21 release-phase all-P software witnesses depend on an unverified capture-wide 240-tick cross-CPU assumption. The following fresh-boot [sparse-MMIO packet](experiments/linux-pcpm-sampler/native-evidence/mmio-abi2/README.md) made 90 successful read-only PCPM accesses, all returning `0x000021f0`; its predeclared ACTUAL contrast failed. The [matched diagnostic comparison](experiments/linux-pcpm-sampler/native-evidence/mmio-abi2/MATCHED-COMPARISON.md) cannot establish a causal sampling effect. Neither native packet calibrates a hardware state or energy saving, and the cross-CPU clock bound remains unverified. ABI 2 adds raw physical-counter brackets while preserving nanosecond scheduling; its decoder also retains explicit support for historical ABI 1 exports without fabricating counter timestamps. The [joint-capture procedure](experiments/linux-pcpm-sampler/JOINT-CAPTURE.md) and [native calibration protocol](experiments/linux-pcpm-sampler/NATIVE-CALIBRATION-PROTOCOL.md) govern these MMIO and matched controls. Their hardware-state and clock-alignment gates remain open.

The later [PCPU PS3 protocol](experiments/linux-pcpm-sampler/PCPU-PS3-PROTOCOL.md) is a prospective, source-pinned response to that constant PCPM result. It identifies four distinct per-core PMGR status slots, requires a new existing-map-only built-in accessor, separates a bounded access/variability pilot from a balanced per-core confirmation, and limits any result to calibrated PMGR-reported codes. Its [default-disabled built-in prototype](experiments/linux-pcpm-sampler/ps3-prototype/README.md) was validated at patch/object level, including a separate offline compile of the dormant read path. A later [full-target incremental linked build](experiments/linux-pcpm-sampler/ps3-prototype/LINKED-DISABLED-BUILD-RESULT.md) passed source-to-Image, all-module and Apple DTB checks with both read gates off. That image was not installed or booted; no PCPU register read or physical-power observation resulted.

After ABI 3 booted successfully, the older PCPM menu entry and EFI image were [retired under pinned read-only provenance and independent readback](experiments/linux-pcpm-sampler/PCPM-EFI-RETIREMENT-RECEIPT.json). The stock default and working ABI 3 image remain, and the PCPM image is hash-verified in a private off-EFI backup. EFI use fell from 73.75% to 55.62%. This maintenance involved no reboot or new register read; the edited menu has not itself been boot-tested. The active Limine config path is supported by deterministic search and the earlier ABI 3 selection, not a measured boot digest.

The [iconidentify Aurora target audit](notes/iconidentify-aurora-kernel-target.md) resolves the operator-selected installer separately from the earlier Aurora Silicon baseline. Public release archives and the installer were downloaded and inspected as data, without executing package contents or installing anything. The [sanitized release receipt](notes/raw/iconidentify-aurora-release-11.18.json) records selected package metadata, image/configuration hashes and config excerpts; the full image, package archive and config remain outside the publication packet. The [20-file source comparison](notes/raw/iconidentify-aurora-source-comparison.json) retains immutable source URLs, blob/content hashes and scoped patch-check output. These records establish inspected source/artifact identities and textual patch mismatches, not a reproducible source-to-binary chain or native execution.

The subsequent [Linux qualification](notes/linux-native-qualification-20261002.md) is an unprivileged, sequential inventory from a containerized research session. Its [reviewed receipt](notes/raw/native-linux-readonly-qualification-20261002.json) retains a whitelist of raw software configuration/accounting values, timestamps, reported firmware versions, artifact/configuration hashes, kernel note bytes, immutable source digests and complete scoped patch-check failures. The private packet retains the original command stdout/stderr, source responses, boot arguments, full configuration and installed image plus the collector/derivation scripts. Those private data are outside this repository. Config/image/build-ID agreement supplies scoped artifact linkage; it does not recover the source-to-binary build recipe, prove the native boot route, or demonstrate command BUSY, physical state, energy or wake behavior. No research instrument was enabled or installed for this inventory.

The separate [Aurora observer port](experiments/aurora-apsc-observer/README.md) preserves the Asahi patches and publishes two explicitly pinned integration patches, a sanitized [preliminary build receipt](experiments/aurora-apsc-observer/build-receipt.json), and an [ELF byte-comparison script](experiments/aurora-apsc-observer/compare_objects.py). All touched existing files were checked against the selected Git tree; individual objects compiled against private copies of the installed prepared headers, with enabled options supplied by compiler definitions. The full config, private build paths, logs, objects, downloaded tool archives and upstream source remain outside the public packet. That preliminary stage alone did not establish full-tree Kconfig/final-link acceptance, an installed instrument or a qualified native capture. The later full build, deployment and native observations have separate records below; none measures energy or wake behavior.

The [GitHub Pages website](https://malik-na.github.io/m1-cpu-idle-research/) is a generated view of the published packet. The [builder](site/README.md) reads research content from an immutable Git commit, excludes untracked files, and preserves the original evidence bytes alongside rendered Markdown. Its short homepage is an editorial summary; the detailed records retain their evidence boundaries. The website does not collect machine telemetry or authenticate hardware results.

[`MANIFEST.sha256`](MANIFEST.sha256) hashes every tracked publication file except itself. Run `python3 tools/verify_repository.py` to check the manifest, local documentation links and public-trace summary. This check establishes repository consistency; it does not validate the physical CPU power state or claim a battery improvement. The manifest covers repository sources, including the site generator; generated HTML is a separate deployment artifact.

The later [complete build receipt](experiments/aurora-apsc-observer/full-build-receipt.json) verifies the exact whole source, accepted configuration, final Image/modules/DTB build, embedded config, linked WFI/helper/initcall checks and matching private EFI/module set. The [protected boot receipt](notes/raw/native-linux-boot-qualification-20261002.json) publishes reviewed bundle/FDT hashes and DT topology while retaining raw EFI bundles, logs, boot arguments and full FDT privately. The [deployment receipt](experiments/aurora-apsc-observer/deployment-receipt.json) records an explicitly authorized separate research-kernel installation with the working stock default and artifacts preserved. These records establish source/local-binary/deployment identity; the subsequent native result has its own packet.

The [restart outcome](experiments/aurora-apsc-observer/restart-outcome-receipt.json)
publishes reviewed boot-selection values and artifact checks. Full current/prior
kernel logs, boot-entry lists, configuration and the bounded diagnostic script
remain private. The authorized restart selected stock; absence of the one-shot
request and empty pstore do not establish why, or prove a research-kernel failure.

The later [driver regression receipt](experiments/aurora-apsc-observer/driver-regression-receipt.json)
records the actual research release boot, the earlier Omarchy cleanup of its
unowned module tree, and the operator's Wi-Fi/brightness report. Full journals,
the local package/archive, module bytes, root command output and the failed
first package metadata check stay private. The published packet includes
only scoped hashes, failure details, and the successful package integrity
result. The operator subsequently booted the repaired research image and
reported Wi-Fi and brightness working; the live check found `wlan0` and
the panel backlight. The later capacity image and A/B/C captures are separate.

The [native result](experiments/aurora-apsc-observer/NATIVE-RESULT.md)
records three distinct boots of the capacity image, including one C
APSC command-register BUSY sample after a same-CPU SET. The reviewed
[public event packet](experiments/aurora-apsc-observer/native-evidence/README.md)
retains raw numerical event values, 24 MHz timestamps, workload rows,
counter exchanges, status/drop/error counts, bounded sysfs snapshots,
chronology, exact export hashes and reproducible conditional analysis.
Raw CSV files are byte-exact after deterministic gzip; status/snapshots are
byte-exact; chronology is field-filtered by the published exporter. The
original acquisition-time `SHA256SUMS` files, full boot arguments, FDTs,
logs, complete configuration, image and private command paths remain in
the local mode-0700 packets. The analysis's 240-tick cross-CPU bound is
explicitly assumed and unproven through the window. This packet does not
identify the WFI instruction state, physical cluster power, energy, wake
latency or a Linux defect.

The [ABI 2 build receipt](experiments/aurora-apsc-observer/wfi-build-receipt.json)
records the separate `-wfi` kernel, statically reviewed first-attempt seam,
matching module package and checked boot bundle. The later
[deployment receipt](experiments/aurora-apsc-observer/wfi-deployment-receipt.json)
records installed package and EFI hashes, integrity checks, preserved
fallback entries and remaining EFI space. The source patch and protocol are
published; package/archive contents, raw boot configuration, installation
logs and host paths remain private. The new kernel was unbooted at that
checkpoint. The later [native ABI 2 D pilot](experiments/aurora-apsc-observer/WFI-D-RESULT.md)
has a separate [public receipt](experiments/aurora-apsc-observer/wfi-clock-pilot-receipt.json)
and [numerical packet](experiments/aurora-apsc-observer/native-evidence/D/status.txt).
Its 660 matched clock-only first-attempt probes demonstrate a usable native
capture path with no command-register read. The private hashed packet retains
the boot ID, FDT, full logs and command arguments; the public packet retains
only reviewed numerical streams, statuses, filtered chronology and endpoint
projections. The D result does not establish APSC BUSY, a physical power
state, energy, wake latency or a guaranteed cross-CPU clock bound.

The subsequent [EFI retirement receipt](experiments/aurora-apsc-observer/wfi-efi-retirement-receipt.json)
records the removal of the obsolete first research entry and image after the
qualified WFI boot and D pilot. The original image and before/after Limine
configuration have verified private backups. Its reviewed public subset
retains the removed image hash, configuration hashes, fallback checks and EFI
usage; private boot ID, backup location and full configuration stay local.

The next fresh-boot [E result](experiments/aurora-apsc-observer/WFI-E-RESULT.md)
records four raw APSC BUSY-bit reads at the first-attempt pre-DSB probe,
with same-CPU preceding SETs. Its [public numerical packet](experiments/aurora-apsc-observer/native-evidence/E/status.txt)
and [reviewed receipt](experiments/aurora-apsc-observer/wfi-mmio-receipt.json)
retain replayable event/counter/workload values, status and hash links while
withholding boot identifiers, full FDT, boot arguments and logs. One BUSY
row passes a conditional software peer-interval screen under assumed E=240,
but no physical sleep or WFI-instruction state follows. The later
[C-hook control](experiments/aurora-apsc-observer/WFI-C-CONTROL-RESULT.md)
has a separate [numerical packet](experiments/aurora-apsc-observer/native-evidence/C-abi2/status.txt)
and [publication receipt](experiments/aurora-apsc-observer/wfi-c-control-receipt.json).
It independently replays 13 raw BUSY C reads in cluster 0, ten of them in
primary comparable-lag SET-to-C pairs under the unmeasured 240-tick
cross-CPU model; cluster 1 had no primary pair. The first requested C reboot
selected stock and yielded no packet, as the
[incident record](experiments/aurora-apsc-observer/WFI-C-BOOT-SELECTION-INCIDENT.md)
states. The subsequent [B records-only control](experiments/aurora-apsc-observer/WFI-B-CONTROL-RESULT.md)
has a separate [numerical packet](experiments/aurora-apsc-observer/native-evidence/B-abi2/status.txt)
and [publication receipt](experiments/aurora-apsc-observer/wfi-b-control-receipt.json).
It replays 1,066 event rows without stream loss or command reads. Its
C-hook timestamp brackets can be compared observationally with C; the
packets do not isolate total observer cost. The
[A unarmed baseline](experiments/aurora-apsc-observer/WFI-A-BASELINE-RESULT.md)
has a [numerical packet](experiments/aurora-apsc-observer/native-evidence/A-abi2/status.txt)
and [receipt](experiments/aurora-apsc-observer/wfi-a-baseline-receipt.json)
showing zero observer rows and 39 fully interior worker pulses per CPU. The
[accepted D/E/C/B/A comparison](experiments/aurora-apsc-observer/WFI-ABI2-BLOCK-RESULT.md)
and [sanitized verifier output](experiments/aurora-apsc-observer/wfi-abi2-first-block-comparison.json)
replay all five distinct private packets. Four E first-attempt pre-DSB BUSY
reads include one conditional software final-entrant candidate under an
unmeasured cross-CPU clock assumption; no WFI-instruction state, physically
asleep peer, rail power, energy, wake or Linux policy improvement follows.
The thermal/background match and sensitive negative gates are unmet.

After the qualified WFI image booted with Wi-Fi and brightness working, the
older capacity Limine entry and EFI image were retired to preserve boot space.
The [reviewed retirement receipt](experiments/aurora-apsc-observer/wfi-capacity-efi-retirement-receipt.json)
records exact before/after configuration and image hashes, the verified stock
default, retained stock/WFI images, EFI usage, and a hash-linked private
backup. The capacity source patch and findings remain published; this
operation adds no CPU-idle or physical-power observation.

After the distinct PCPM image booted and passed Wi-Fi, brightness and
observer checks, the obsolete WFI-seam menu entry and EFI image were retired
under exact menu/image pins. The [sanitized retirement receipt](experiments/aurora-apsc-observer/WFI-EFI-RETIREMENT-RECEIPT.json)
records independent post-change stock-default and PCPM readback, the removed
image hash and off-EFI retention, and EFI usage falling from 73.74% to
55.62%. The original WFI source, build/deployment receipts and native
findings remain in this branch. This maintenance does not add hardware-idle
evidence.

The [ABI 3 source/object and linked-build packet](experiments/aurora-apsc-observer/abi3-prototype/README.md)
is a frozen two-file delta against the prior PCPM source tree, with a
tree-inventory receipt, object instruction proof, 30 synthetic offline
validator tests, and a later linked-build addendum. The full `Image modules
dtbs` build exited successfully; the public receipt hashes its linked Image,
vmlinux Build-ID, 1,867 modules and 111 Apple DTBs, while the build log remains
private and hash-pinned. The separate [sanitized deployment receipt](experiments/aurora-apsc-observer/abi3-deployment-receipt.json)
binds the distinct module package and UKI to that build and records the
preserved stock default and PCPM fallback, EFI reserve and independent
post-install readback. At that checkpoint the ABI 3 image was unbooted;
the [prospective run plan](experiments/aurora-apsc-observer/WFI-ABI3-RUN-PLAN.md)
fixed the later native gates.

The [ABI 3 acquisition logic review copy](experiments/aurora-apsc-observer/abi3-acquisition/README.md)
retains the prospective one-shot A/D/E/conditional-C collector and its eighteen
synthetic tests. Its redaction receipt binds the private executable source to
the public copy, with only the local repository path and account name
replaced. The linked build and installed-image identity are now separately
recorded. The synthetic logic checks are separate from a native capture.

The first fresh ABI 3 boot completed an [unarmed A baseline](experiments/aurora-apsc-observer/ABI3-A-BASELINE-RESULT.md)
under that plan. The reviewed [public numerical packet](experiments/aurora-apsc-observer/native-evidence/abi3-A/README.md)
retains filtered status lines, byte-exact header-only APSC streams after
deterministic gzip, worker rows with times relative to their scheduled start,
relative timeline actions, and projected endpoint context. Its receipt binds
each public data artifact to the sealed private manifest and source file hashes.
The private packet retains the boot identifier, operator receipt text,
configuration, FDT, boot arguments, full logs, network/USB identities and
absolute timestamps. Both workers completed 200 pulses, 196 per CPU fully
inside the 10.000120857-second A window; the observer stayed unarmed and
produced zero rows. The operator's first-boot Wi-Fi and visible-brightness
receipt and the live source/build/deployment checks are privately bound,
not independently proved by the public worker rows. This A packet is an
instrument-state and delivered-work baseline, with no command-BUSY,
WFI-instruction-state, physical-power, energy or wake finding. D/E require
their own fresh boots and validation.

The second fresh ABI 3 boot completed the [ticket-only D control](experiments/aurora-apsc-observer/ABI3-D-TICKET-CONTROL-RESULT.md). Its [reviewed numerical packet](experiments/aurora-apsc-observer/native-evidence/abi3-D/README.md) retains byte-exact idle/DVFS and WFI event streams after deterministic gzip, filtered loss/status lines, relative worker and timeline records, a validator report, and projected endpoint context. A public manifest and input-hash receipt bind those values to the sealed 64-file private packet; full boot logs, identifiers, FDT, boot arguments and source binaries remain private. The independently replayed ticket stream had 1,873 first-attempt WFI-path slots with no missing records. D deliberately omitted the extra APSC command read at that seam, so its empty WFI command fields and zero BUSY candidates are structural, not a negative command-state observation. The 10.446-second D interval and warmer, differently charged fresh boot limit causal comparison with A. The next E command-read phase still requires its own qualified boot.

The third fresh ABI 3 boot completed the [ticket-plus-command-read E result](experiments/aurora-apsc-observer/ABI3-E-TICKET-RESULT.md). Its [public numerical packet](experiments/aurora-apsc-observer/native-evidence/abi3-E/README.md) retains byte-exact compressed APSC event and WFI streams, all 2,185 raw command words (71 BUSY and 2,114 clear), 18 strict cluster-1 software ticket witnesses and all 53 rejected BUSY rows with reasons, filtered status, relative worker/timeline records, and a hash-linked projection of endpoints. The sealed 64-file private packet holds the boot and operator receipts, full logs, FDT, configuration, device identities, wall-clock times and original worker timestamps. The independent replay confirmed contiguous tickets and zero relevant loss. The WFI-path command was read before the original `dsb sy; wfi`; the result proves BUSY while all three peers had enclosing **software idle-hook** intervals at that read, not BUSY at the later executed instruction or physical sleep. A stricter post-hoc screen finds six witnesses whose peers' callbacks remained unreturned through the candidate's WFI, but still has no WFI-time BUSY value. A/D/E differ in temperature, battery and external USB presence, so their workload and probe-bracket differences are descriptive rather than isolated observer cost. The fixed plan stops after this positive; conditional C is not run. Issue #5's exact-WFI/physical-state boundary remains open.

The [EL2 WFI-trap feasibility note](experiments/aurora-apsc-observer/WFI-EL2-TRAP-FEASIBILITY.md)
is a source-pinned static assessment of an unimplemented m1n1 guest route.
It does not add a native trace or instruction-state observation.
The [T8103 `LAST_CHG_TIME` calibration feasibility review](experiments/aurora-apsc-observer/LAST-CHG-TIME-CALIBRATION-FEASIBILITY.md)
is likewise a source-pinned proposal, not a register read. The cited driver
defines offset `0x38` and a 24 MHz timebase but supplies no width, read-safety,
completion-edge, command-association or BUSY-continuity contract. A later
native test must qualify those premises before using that register to infer
command state at the WFI instruction.
The [ABI 3 writer-identity audit](experiments/aurora-apsc-observer/WFI-WRITER-IDENTITY-AUDIT.md)
replays the public E events: the nearest prior recorded cluster-1 SET word
matches each of 18 BUSY witnesses after removing SET/BUSY bits. That
consistency is not a proven command identity. The active-branch wrapper
can omit a SET whose writer passed its inactive check just before capture
activation; capture-start has no grace-period exclusion for that in-flight
write. Zero reported DVFS stream loss covers the recording branch, while
unobserved writers and cross-CPU order still need qualification.

The [prospective command-BUSY calibration protocol](experiments/aurora-apsc-observer/WFI-APSC-CMD-BUSY-CALIBRATION-PROTOCOL.md)
is a static design, not a new capture. The separately reviewed
[disabled helper source](experiments/aurora-apsc-observer/lct-prototype/README.md)
is published with its exact SHA-256 and a whitelist-only offline validation
result and the archived read-only preflight source. The private module binary
and build tree remain outside the repository. The helper has never been loaded; its default build
does not map an APSC resource or register a writer probe. It cannot meet
the protocol's complete writer-coverage, remote-sampling or block-journal
gates, and `+0x38` read safety/width remain unqualified. Neither static
artifact adds an exact-WFI command-state or physical-power observation.
The [issue #5 route decision](experiments/aurora-apsc-observer/ISSUE5-INSTRUCTION-STATE-DECISION.md)
is a static synthesis of the saved E packet, source audits and retained
macOS disassembly excerpts. It records an excerpt-scoped negative search and
the remaining measurement gates, not a new native register or power result.
