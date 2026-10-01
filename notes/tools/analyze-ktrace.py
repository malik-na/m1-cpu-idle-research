#!/usr/bin/env python3
"""Reduce a macOS ktrace NDJSON CPU-idle capture without publishing raw trace data.

Only PERF_CPU_IDLE begin/end records are used for callback timing. A candidate
last-core entry has all three peer cores in its cluster in their completed idle
state and no peer callback in progress at its begin timestamp. This is a
software-state reconstruction, not a measurement of PMGR physical residency.
"""

import argparse
import collections
import gzip
import hashlib
import json
from pathlib import Path

CPU_IDLE_BEGIN = 0x27001001
CPU_IDLE_END = 0x27001002
CLPC_WFE_RECOMMENDATION = 0x328C00C0


def percentile(values, probability):
    ordered = sorted(values)
    return ordered[int((len(ordered) - 1) * probability)]


def timing_summary(values):
    return {
        "count": len(values),
        "minimum_ns": min(values),
        "median_ns": percentile(values, 0.5),
        "p90_ns": percentile(values, 0.9),
        "p99_ns": percentile(values, 0.99),
        "maximum_ns": max(values),
        "mean_ns": round(sum(values) / len(values), 1),
    }


def analyze(path):
    digest = hashlib.sha256()
    event_counts = collections.Counter()
    samples = []
    unparsable = 0
    last_timestamp = None
    out_of_order = 0
    first_timestamp = None
    final_timestamp = None
    first_walltime = None
    final_walltime = None

    opener = gzip.open if path.suffix == ".gz" else Path.open
    with opener(path, "rb") as stream:
        for line in stream:
            digest.update(line)
            if not line.strip():
                continue
            try:
                event = json.loads(line)
                timestamp = int(event["timestampns"])
                debugid = int(event["debugid"])
            except (ValueError, KeyError, TypeError):
                unparsable += 1
                continue
            event_counts[f"0x{debugid:08x}"] += 1
            if first_timestamp is None:
                first_timestamp = timestamp
                first_walltime = event.get("walltime")
            final_timestamp = timestamp
            final_walltime = event.get("walltime")
            if last_timestamp is not None and timestamp < last_timestamp:
                out_of_order += 1
            last_timestamp = timestamp
            if debugid in (CPU_IDLE_BEGIN, CPU_IDLE_END):
                samples.append(event)

    # ktrace normally emits monotonic records; sort for deterministic treatment
    # if a later capture contains reordered records.
    samples.sort(key=lambda event: int(event["timestampns"]))
    states = {cpu: None for cpu in range(8)}  # 1 = idle, 0 = active
    in_callback = {}
    durations = collections.defaultdict(list)
    per_cpu = collections.defaultdict(list)
    anomalies = collections.Counter()
    matched_pairs = 0

    for event in samples:
        cpu = int(event["cpuid"])
        args = event.get("args", [])
        if cpu not in states or len(args) < 2:
            anomalies["invalid_cpu_or_args"] += 1
            continue
        try:
            arg_cpu, direction = int(args[0]), int(args[1])
        except (TypeError, ValueError):
            anomalies["invalid_cpu_or_args"] += 1
            continue
        if arg_cpu != cpu or direction not in (0, 1):
            anomalies["cpu_or_direction_mismatch"] += 1
            continue

        timestamp = int(event["timestampns"])
        if int(event["debugid"]) == CPU_IDLE_BEGIN:
            if cpu in in_callback:
                anomalies["nested_begin"] += 1
                continue
            peers = range(0, 4) if cpu < 4 else range(4, 8)
            peers = [peer for peer in peers if peer != cpu]
            if any(states[peer] is None or peer in in_callback for peer in peers):
                group = "unknown"
            elif all(states[peer] == 1 for peer in peers):
                group = "apparent_last_core"
            else:
                group = "other_core_active"
            in_callback[cpu] = (timestamp, direction, group)
            continue

        prior = in_callback.pop(cpu, None)
        if prior is None:
            anomalies["orphan_end"] += 1
            continue
        start, prior_direction, group = prior
        if prior_direction != direction:
            anomalies["direction_mismatch"] += 1
        if timestamp < start:
            anomalies["negative_interval"] += 1
            continue
        if states[cpu] is not None and states[cpu] == direction:
            anomalies["nonalternating_core_state"] += 1
        matched_pairs += 1
        if direction == 1:
            cluster = "E" if cpu < 4 else "P"
            duration = timestamp - start
            durations[(cluster, group)].append(duration)
            per_cpu[(cpu, group)].append(duration)
        states[cpu] = direction

    anomalies["unmatched_begin_at_capture_end"] = len(in_callback)
    return {
        "method": "PERF_CPU_IDLE callback begin/end; entering arg=1; apparent last core reconstructed from peer callback-completion state",
        "limitations": [
            "Callback duration is software execution time, not WFI or physical power-gated residency.",
            "A last-core classification does not isolate the APSC busy wait from other cluster transition work.",
            "The filtered system-wide trace may perturb the idle workload; these observations are not an energy benchmark.",
        ],
        "source_sha256": digest.hexdigest(),
        "first_walltime": first_walltime,
        "last_walltime": final_walltime,
        "first_timestamp_ns": first_timestamp,
        "last_timestamp_ns": final_timestamp,
        "span_ns": None if first_timestamp is None else final_timestamp - first_timestamp,
        "event_counts": dict(sorted(event_counts.items())),
        "clpc_wfe_recommendation_count": event_counts[f"0x{CLPC_WFE_RECOMMENDATION:08x}"],
        "unparsable_nonblank_lines": unparsable,
        "out_of_order_records": out_of_order,
        "matched_idle_callback_pairs": matched_pairs,
        "anomalies": dict(sorted(anomalies.items())),
        "entry_callback_timing_by_cluster_and_peer_state": {
            f"{cluster}/{group}": timing_summary(values)
            for (cluster, group), values in sorted(durations.items())
        },
        "entry_callback_timing_by_cpu_and_peer_state": {
            f"cpu{cpu}/{group}": timing_summary(values)
            for (cpu, group), values in sorted(per_cpu.items())
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path, help="local ktrace --ndjson capture")
    args = parser.parse_args()
    print(json.dumps(analyze(args.trace), indent=2))


if __name__ == "__main__":
    main()
