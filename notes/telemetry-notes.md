# M1 macOS IOReport observations, 1 October 2026

This is an observation-only collector running as UID 501 on the host macOS 27.0 build 26A428. It uses IOReport channel enumeration, reporting subscriptions, samples and sample deltas. No power policy, SMC, hardware register, boot or kernel writes were made. IOReport subscriptions may enable reporting and add measurement overhead; that is distinct from setting a power mode. The tool sandbox allowed enumeration but rejected subscription; the identical collector succeeded outside that sandbox as the same ordinary user, without sudo.

## Reproduce

```sh
xcrun clang -std=c11 -O2 -Wall -Wextra -Werror -framework CoreFoundation tools/ioreport.c -o tools/ioreport-c
tools/ioreport-c inventory > raw/ioreport/inventory.json
tools/ioreport-c '@idle' 10 1 > raw/ioreport/experiment.jsonl
python3 tools/ioreport-summary.py raw/ioreport/experiment.jsonl > raw/ioreport/experiment-summary.json
```

Run from this research directory. `@idle` selects 278 channels: all CPU Stats and SoC Stats, plus PMP reporting state, power and ECPU/PCPU energy. A literal group name, count, interval seconds, and optional subgroup may be supplied instead. The collector is bounded to 1–10,000 samples and 0.05–60 seconds/sample. The final collector is plain C with no Objective-C runtime. It links the CoreFoundation C API and opens `/usr/lib/libIOReport.dylib` from the dyld shared cache. The library does not need an on-disk dylib file. Xcode SDK `usr/lib/libIOReport.tbd` confirms all used symbol exports. The initial samples were obtained using the preserved Objective-C prototype `tools/ioreport.m`; the C port uses identical selection, subscription and decoding logic. All 7,749 channel identities and metadata matched exactly between both inventory runs. C subscription/sample validation is left to the coordinated experiment so this agent does not disturb the baseline with additional samples.

## What exists here

Full inventory contains **7,749 channels**; focus groups have CPU Stats: 16, SoC Stats: 251, PMP: 197, Energy Model: 97. Inventory metadata includes group/subgroup/name, driver ID, channel ID, format, unit and encoded unit. Files preserve raw counter values, state names, residency and in-transition counts.

- CPU Stats / CPU Core Performance States: ECPU0–3 and PCPU0–3. Every core has one `IDLE` state plus voltage/performance states. There is no C1/C2/core-retention/core-off split in these channels.
- CPU Stats / CPU Complex Performance States: ECPU, PCPU, ECPM, PCPM. ECPU and PCPU have useful IDLE residency and entry counts. ECPM and PCPM IDLE bins remained zero, so their active frequency distributions cannot be used as CPU idle percentages.
- CPU Stats also exposes two complex voltage-state channels and two DVD-state channels. The DVD channels stayed at 100%; this observation alone does not establish DVD semantics.
- SoC Stats / Events: AWAKE, SLP_S2R, DEEP_WAIT, SOC/DCS/DISP voltage-state events, CPU adaptive-clock/dither triggers and several shutdown/undervoltage signals. The shutdown labels must not be interpreted as ordinary CPU idle power-gating without driver evidence.
- SoC Stats / PMGR Counters: 162 `CLK###`, `PWR###`, `EVT###`, and `DEV###` simple counters with no unit label. Their exact register/domain mapping is not established here. These are useful correlation candidates, not proof of CPU power-off.
- PMP / Power: OFF and ON in microseconds, plus sleep/wake counts. The provider is RTBuddyIOReportingEndpoint for the PMP firmware: these states refer to that coprocessor, not the host CPU clusters.
- PMP / Energy Counters exposes ECPU and PCPU in millijoules. Dividing differences by elapsed time yields average modeled watts, not an external electrical power measurement.

## Verified simultaneous awake-idle evidence

`raw/ioreport/combined-ambient-1.jsonl` sampled three intervals totaling 6.039335 seconds, with ordinary desktop/agent activity still present. This is an ambient observation, not a clean controlled idle baseline.

| Channel | IDLE residency | Entries over interval | Aggregate time per entry |
|---|---:|---:|---:|
| ECPU0 (core) | 61.471% | 14,883 | 249.4 us |
| ECPU1 (core) | 66.226% | 13,861 | 288.5 us |
| ECPU2 (core) | 70.490% | 12,533 | 339.7 us |
| ECPU3 (core) | 73.950% | 10,715 | 416.8 us |
| PCPU0 (core) | 84.888% | 5,529 | 927.2 us |
| PCPU1 (core) | 87.299% | 2,776 | 1899.1 us |
| PCPU2 (core) | 93.832% | 1,918 | 2954.4 us |
| PCPU3 (core) | 96.386% | 1,042 | 5586.1 us |
| ECPU (cluster) | 32.089% | 7,827 | 247.6 us |
| PCPU (cluster) | 75.813% | 3,139 | 1458.5 us |

The time-per-entry column is the interval IDLE residency divided by reported entries. Boundary-spanning episodes affect this ratio. It is **not a measured wake-up latency or a state-entry threshold**.

In the same window, AWAKE reported ACT 99.9424%, with **zero transitions**, while SLP_S2R and DEEP_WAIT reported zero ACT residency and zero transitions. The small AWAKE INACT residual is not sufficient evidence of a real sleep episode; counter/read timing and implementation details are unresolved. The concurrent core/cluster IDLE transitions demonstrate awake CPU idling while the suspend counters did not advance. ECPU_SW_SHUTDN and PCPU_SW_SHUTDN also remained inactive throughout this sample.

The ECPU modeled-energy delta was 839 mJ (~0.139 W over wall interval), and PCPU 2,458 mJ (~0.407 W). PMP itself reported OFF 10.33% while its firmware IOP State stayed Running; this again illustrates why a coprocessor OFF bin cannot be treated as host CPU power-off.

## Interpretation limits and next experiment

IOReport state format can carry time or event histograms. In the local PMP Bandwidth channels the unit is **events**, and residency equals intransitions. Those values are sample counts, not 24 MHz ticks. The same caution applies to other histogram-like state channels. For the CPU channels, the unit is 24Mticks: seconds = residency / 24,000,000. Percentages use the sum of all states within each channel, reducing read-timing discrepancies.

Next useful experiment is a coordinated idle → one periodic worker → sustained worker → recovery sequence while recording `@idle`. Correlate PMGR counters against core/cluster IDLE and known driver or device-tree counter mappings. Repeat worker periods and QoS settings only after a quieter baseline is characterized. This can identify thresholds/correlations; it cannot by itself reveal the underlying WFI/WFE, retention or power-collapse entry code.

No new-to-Asahi claim is justified yet. CPU IOReport sampling is already used in public monitoring projects. The precise current M1/macOS 27 inventory and awake-idle counts are reproducible local evidence. A contribution would need a defensible new mapping, semantic result, or policy difference verified against existing Asahi work.

## Primary references

- [Apple XNU IOReportTypes.h](https://github.com/apple-oss-distributions/xnu/blob/main/iokit/DriverKit/IOReportTypes.h): state reports contain state ID, in-transition count, upticks and last-intransition; time units include 24 MHz ticks. Update actions are described as having no observable side effects, while configuration actions can change reporting behavior.
- [OSHI IOReport binding](https://www.oshi.ooo/xref/oshi/jna/platform/mac/IOReport.html): user-space API declarations and subscribed-channel handling used to cross-check private ABI shapes. This is primary source for that implementation, not an Apple ABI guarantee.
- [SiliconScope measured IOReport channel map](https://github.com/kennss/SiliconScope/blob/main/docs/ioreport-channels.md): existing independent implementation documents CPU IDLE/frequency channels and warns that cluster frequency residency is not scheduler CPU usage; also demonstrates why PMP/AMC layouts must be re-verified per chip and OS.
- Local Xcode SDK `/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk/usr/lib/libIOReport.tbd`: confirms private library install name and exported functions.
