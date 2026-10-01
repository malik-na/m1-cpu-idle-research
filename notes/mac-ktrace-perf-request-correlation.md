# Exploratory macOS performance-request versus last-core idle timing

**Target and evidence tier.** This is a retrospective analysis of the already
published, sanitized five-second macOS `ktrace` capture from a base M1
(MacBookAir10,1 / T8103), macOS 27.0 build 26A428, XNU `13432.1.9~1`. The
running-kernel and inspected-kernelcache UUID match, as recorded in the
[local driver report](local-driver-notes.md). This note adds no new live trace,
privileged operation, register read, or Linux runtime claim. Its evidence tier
is **live software trace**: it can relate software markers in time, but cannot
identify an untraced instruction, hardware BUSY state, physical idle depth, or
energy use. The original full-system trace remains private; the
[reviewed event stream](raw/ktrace/idle-5s-events.jsonl.gz) is the analysis
input (compressed SHA-256
`07d96b643f5331a172fc4cbfcac06ed414e9b0ae49f6042b8fc52649839375fc`).

## Question and prediction

The [matching local PMGR disassembly](raw/driver-pmgr-cpuidle.disasm) dispatches
an apparent final core's idle-entry callback to a routine that can call
`_waitAPSCPending`; [the focused follow-up](local-driver-skipflag-followup.md)
predicts that this Mac's static configuration enables that wait. If recent
CPU performance requests often cause pending APSC work, a final-core callback
soon after a request **might** have a longer bracket duration than one without
a recent request. No duration difference would weaken this timing-screening
idea. A longer duration does not identify which instructions consumed it:
PMGR accounting, other synchronization, request-related bookkeeping, or
tracing/scheduling effects remain alternatives. The actual APSC hypothesis
requires a branch and command-register observation, as stated in
[experiment E1](../wiki/Experiment-Backlog.md).

## Event meanings and calculation

The installed `ktrace decode 0x27003010 0x27003030` reports
`PERF_PERF_CHG_CPU` and `PERF_PERF_CHG_DOM3`, respectively. The installed
[ApplePMGR signpost definition](raw/driver-ApplePMGR.kext-PMGRSignposts.plist.json)
names those same codes `CPM1PerfStateReq` and `CPM3PerfStateReq`. These are
**performance-request software markers**, not evidence of a completed DVFS
command or its BUSY bit. The signpost labels alone do not establish a physical
cluster mapping for CPM1 and CPM3. In this sample, all 492 CPM1 and 414 CPM3
records were emitted on CPUs 0–3; an emitting CPU need not be the target of a
request. The numeric arguments remain in the sanitized stream, but their
meaning beyond the signpost's first level argument is not established here.

For idle timing, `0x27001001` and `0x27001002` bracket one
`ApplePMGR::_cpuIdle` **callback**; `args[1] == 1` means entry preparation. It
does not bracket the interval spent in WFI. Reuse the state classifier in
[`analyze-ktrace.py`](tools/analyze-ktrace.py): at an entry-callback begin, a
CPU is an *apparent last active core* only if all three peers in its four-core
cluster have completed entry callbacks and no peer callback is in progress.
Initial unknown states and concurrent peer callbacks are excluded. For each
classified entry, find the most recent *preceding* request marker of each
code; compare its begin-to-end duration with the elapsed time since that
marker. A marker at the same timestamp has age zero. “Near” below means age
**0–50,000 ns inclusive**; “far” means at least **1,000,000 ns**, or no
preceding marker. The intermediate observations are neither near nor far.

| Entry group | Preceding marker | Age | Callbacks | Median bracket duration |
|---|---|---:|---:|---:|
| E apparent last core | CPM1 / `PERF_PERF_CHG_CPU` | <10 µs | 48 | 23.000 µs |
| E apparent last core | CPM1 / `PERF_PERF_CHG_CPU` | 10–50 µs | 118 | 10.396 µs |
| E apparent last core | CPM1 / `PERF_PERF_CHG_CPU` | ≥1 ms or absent | 2,822 | 3.458 µs |
| E apparent last core | CPM3 / `PERF_PERF_CHG_DOM3` | 0–50 µs | 186 | 3.209 µs |
| E apparent last core | CPM3 / `PERF_PERF_CHG_DOM3` | ≥1 ms or absent | 2,832 | 3.584 µs |
| E with another core active | CPM1 / `PERF_PERF_CHG_CPU` | 0–50 µs | 430 | 0.333 µs |
| E with another core active | CPM1 / `PERF_PERF_CHG_CPU` | ≥1 ms or absent | 14,004 | 0.333 µs |
| P apparent last core | CPM1 / `PERF_PERF_CHG_CPU` | 0–50 µs | 14 | 2.417 µs |
| P apparent last core | CPM1 / `PERF_PERF_CHG_CPU` | ≥1 ms or absent | 606 | 2.730 µs |
| P apparent last core | CPM3 / `PERF_PERF_CHG_DOM3` | 0–50 µs | 23 | 2.542 µs |
| P apparent last core | CPM3 / `PERF_PERF_CHG_DOM3` | ≥1 ms or absent | 531 | 2.750 µs |

The E/CPM1 near group is **166 callbacks, median 14.251 µs** when the two
near-age rows are combined. Each has a distinct nearest preceding CPM1
marker, so one marker was not repeatedly counted as the nearest event for
multiple callbacks. They occurred on all four E cores: CPU 0 had 50 callbacks
(median 15.583 µs), CPU 1 had 53 (12.708 µs), CPU 2 had 35 (15.083 µs), and
CPU 3 had 28 (12.437 µs). These occupied 41 distinct 100 ms bins across the
five-second capture. The marker and callback were on the same emitting CPU in
135 of the 166 instances; the other 31 show that callback CPU cannot simply
be assumed from the marker. Excluding callbacks also preceded by a CPM3 marker
within 50 µs leaves 145 E/CPM1-near callbacks, median **15.583 µs**. Only six
of all 492 CPM1 markers had another CPM1 marker within 50 µs before them.
These checks reduce the simplest single-burst explanation, but **do not remove
workload or scheduling confounding**.

The following small script reproduces the principal E-cluster counts and
medians from the public stream. Run it from the repository root; it writes no
files. `statistics.median` averages the middle two values for even-sized
groups, which explains the half-nanosecond combined median.

```sh
python3 - <<'PY'
import bisect, collections, gzip, json, statistics

path = 'notes/raw/ktrace/idle-5s-events.jsonl.gz'
with gzip.open(path, 'rt') as source:
    events = [json.loads(line) for line in source]
markers = {
    code: [int(e['timestampns']) for e in events if int(e['debugid']) == code]
    for code in (0x27003010, 0x27003030)
}
state = {cpu: None for cpu in range(8)}
in_callback = {}
entries = []
for event in events:
    code = int(event['debugid'])
    if code not in (0x27001001, 0x27001002):
        continue
    cpu, timestamp = int(event['cpuid']), int(event['timestampns'])
    direction = int(event['args'][1])
    peers = [other for other in (range(4) if cpu < 4 else range(4, 8))
             if other != cpu]
    if code == 0x27001001:
        if any(state[other] is None or other in in_callback for other in peers):
            group = 'unknown'
        elif all(state[other] == 1 for other in peers):
            group = 'last'
        else:
            group = 'other'
        in_callback[cpu] = (timestamp, direction, group)
    else:
        start, began_direction, group = in_callback.pop(cpu)
        if began_direction == direction == 1:
            entries.append((cpu, group, start, timestamp - start))
        state[cpu] = direction

for code, times in markers.items():
    for group in ('last', 'other'):
        bins = collections.defaultdict(list)
        for cpu, entry_group, start, duration in entries:
            if cpu >= 4 or entry_group != group:
                continue
            index = bisect.bisect_right(times, start) - 1
            age = start - times[index] if index >= 0 else float('inf')
            bucket = ('near' if age <= 50_000 else
                      'far' if age >= 1_000_000 else 'middle')
            bins[bucket].append(duration)
        print(hex(code), group,
              {name: (len(values), statistics.median(values))
               for name, values in bins.items()})
PY
```

## What this result can and cannot support

The proximity pattern is specific in this capture: it is much larger for
apparent last E callbacks following the CPU-performance marker than for E
callbacks with another core active, for the other recorded performance marker,
or for the small P near groups. This is a **workload-selection lead** for a
narrower trace. It is not a causal estimate: the five-second window was not a
randomized experiment, nearby callbacks share workload history, the PMGR
trace itself may perturb timing, and the sanitized stream has no independent
kernel trace-loss counter. A signpost request is not a DVFS register write or
completion. Neither marker identifies `_waitAPSCPending`, its skip flag, bit 31
of `0x210e20020`/`0x211e20020`, two clear polls, or physical cluster state.
Even if this timing relationship repeats, another PMGR operation on the same
last-core path could explain it.

The safe next **Mac-only** step is to repeat short, bounded software traces
under recorded idle and CPU-work phases, preserving marker counts, full
callback pairs, trace loss, and whole-machine conditions. Compare the same
predeclared 50 µs age bins and E/CPM3 control across independent runs rather
than tuning a window after seeing each trace. An independent branch/BUSY
observation would be needed to attribute any duration to the APSC wait; a
native Linux trace and physical-state or energy measurement would still be
needed to assess a Linux change. The [existing trace note](live-mac-trace.md)
describes why ordinary root `ktrace` on this SIP-enabled Mac cannot provide
those private branch and MMIO values.
