#!/usr/bin/env python3
"""Fail-closed summary of the T8103 APSC observer's v1 CSV and status files.

This describes recorded software events and sampled command words. It cannot
locate the WFI instruction, establish device-command completion, or measure a
physical CPU power state. The input remains the authoritative raw evidence.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import io
import json
from pathlib import Path
import re
import statistics
import sys

from final_entrant import screen as screen_final_entrants


HEADER = [
    "kind", "seq", "cpu", "cluster", "policy_cpu", "policy_mask",
    "fast_switch", "requested_index", "requested_pstate", "token", "t0", "t1",
    "pre_cmd", "cmd", "ret", "flags",
]
KINDS = {"dvfs", "idle_enter", "idle_exit", "cpu_pm_fail"}
BASE_STATUS = {
    "abi", "state", "mode", "cntfrq", "start_tick", "stop_tick", "end_tick",
    "start_online_mask", "end_online_mask", "interrupted",
}
COUNTERS = {"attempts", "committed", "overflow", "missing_commit"}
UINT64_MAX = (1 << 64) - 1
UINT32_MAX = (1 << 32) - 1
INT32_MIN = -(1 << 31)
INT32_MAX = (1 << 31) - 1
BUSY_BIT = 1 << 31
SET_BIT = 1 << 25
CPU_IDS = set(range(8))
CLUSTER_IDS = {0, 1}
DECIMAL = re.compile(r"(?:0|[1-9][0-9]*)\Z")
SIGNED = re.compile(r"(?:0|-?[1-9][0-9]*)\Z")
HEX = re.compile(r"0x[0-9a-fA-F]+\Z")


class AnalysisError(ValueError):
    """Input violates the observer ABI or has malformed records."""


def unsigned(value: str, label: str, *, hexadecimal: bool = False) -> int:
    pattern = HEX if hexadecimal else DECIMAL
    if not pattern.fullmatch(value):
        raise AnalysisError(f"{label}: expected {'0x hexadecimal' if hexadecimal else 'unsigned decimal'} integer")
    number = int(value, 16 if hexadecimal else 10)
    if number > UINT64_MAX:
        raise AnalysisError(f"{label}: exceeds uint64")
    return number


def optional_unsigned(value: str, label: str, *, hexadecimal: bool = False) -> int | None:
    return None if value == "" else unsigned(value, label, hexadecimal=hexadecimal)


def signed32(value: str, label: str) -> int:
    if not SIGNED.fullmatch(value):
        raise AnalysisError(f"{label}: expected signed decimal integer")
    number = int(value, 10)
    if not INT32_MIN <= number <= INT32_MAX:
        raise AnalysisError(f"{label}: exceeds int32")
    return number


def parse_status(source: str) -> dict:
    raw = {}
    for line_number, line in enumerate(source.splitlines(), 1):
        if not line:
            continue
        if line.count("=") != 1:
            raise AnalysisError(f"status line {line_number}: expected key=value")
        key, value = line.split("=", 1)
        if not key or not value or key in raw:
            raise AnalysisError(f"status line {line_number}: missing value or duplicate key")
        raw[key] = value

    expected = set(BASE_STATUS)
    expected.update(f"cluster{n}_cpus" for n in CLUSTER_IDS)
    expected.update(f"cluster{n}_{field}" for n in CLUSTER_IDS for field in ("cmd_phys", "resource_size"))
    expected.update(
        f"cluster{n}_{field}_{edge}"
        for n in CLUSTER_IDS
        for field in ("policy_mask", "policy_cpu", "fast_switch")
        for edge in ("start", "end")
    )
    expected.update(f"idle{n}_{field}" for n in CPU_IDS for field in COUNTERS)
    expected.update(f"dvfs{n}_{field}" for n in CLUSTER_IDS for field in COUNTERS)
    if set(raw) != expected:
        raise AnalysisError(
            f"status keys differ from ABI v1: missing={sorted(expected - set(raw))}, "
            f"unknown={sorted(set(raw) - expected)}"
        )
    if raw["abi"] != "1":
        raise AnalysisError(f"unsupported status ABI {raw['abi']!r}")
    if raw["state"] not in {"ready", "active", "complete", "invalid"}:
        raise AnalysisError("status state is outside ABI v1")
    if raw["mode"] not in {"records", "mmio"}:
        raise AnalysisError("status mode must be records or mmio")

    numbers = {
        key: unsigned(
            value, f"status {key}",
            hexadecimal=key.endswith("_mask") or "_mask_" in key or key.endswith("_cpus")
            or key.endswith("_phys") or key.endswith("_size"),
        )
        for key, value in raw.items()
        if key not in {"abi", "state", "mode"}
    }
    if numbers["cntfrq"] == 0 and raw["state"] == "complete":
        raise AnalysisError("status cntfrq must be nonzero")
    if not numbers["start_tick"] <= numbers["stop_tick"] <= numbers["end_tick"]:
        raise AnalysisError("status capture ticks reversed")
    if numbers["interrupted"] not in (0, 1):
        raise AnalysisError("status interrupted must be 0 or 1")

    clusters = {n: numbers[f"cluster{n}_cpus"] for n in CLUSTER_IDS}
    if not clusters[0] or not clusters[1] or clusters[0] & clusters[1] or (clusters[0] | clusters[1]) != 0xff:
        raise AnalysisError("status cluster masks must partition T8103 CPUs 0..7")
    for key in ("start_online_mask", "end_online_mask"):
        if numbers[key] & ~0xff:
            raise AnalysisError(f"status {key} includes an unmapped CPU")

    streams = {}
    for kind, ids in (("idle", CPU_IDS), ("dvfs", CLUSTER_IDS)):
        for number in ids:
            name = f"{kind}{number}"
            streams[name] = {field: numbers[f"{name}_{field}"] for field in COUNTERS}
            if any(value > UINT32_MAX for value in streams[name].values()):
                raise AnalysisError(f"status {name}: stream counter exceeds uint32")

    policies = {
        n: {
            edge: {field: numbers[f"cluster{n}_{field}_{edge}"] for field in (
                "policy_mask", "policy_cpu", "fast_switch"
            )}
            for edge in ("start", "end")
        }
        for n in CLUSTER_IDS
    }

    return {
        "abi": 1,
        "state": raw["state"],
        "mode": raw["mode"],
        "cntfrq": numbers["cntfrq"],
        "start_tick": numbers["start_tick"],
        "stop_tick": numbers["stop_tick"],
        "end_tick": numbers["end_tick"],
        "interrupted": numbers["interrupted"],
        "start_online_mask": numbers["start_online_mask"],
        "end_online_mask": numbers["end_online_mask"],
        "clusters": clusters,
        "resources": {
            n: {field: numbers[f"cluster{n}_{field}"] for field in ("cmd_phys", "resource_size")}
            for n in CLUSTER_IDS
        },
        "policies": policies,
        "streams": streams,
    }


def parse_events(source: str, status: dict) -> tuple[list[dict], dict[str, list[int]]]:
    reader = csv.DictReader(io.StringIO(source, newline=""), restval=None)
    if reader.fieldnames != HEADER:
        raise AnalysisError(f"CSV header differs from ABI v1: expected {','.join(HEADER)}")

    events = []
    sequences = defaultdict(list)
    for line_number, row in enumerate(reader, 2):
        if None in row or any(value is None for value in row.values()):
            raise AnalysisError(f"CSV line {line_number}: field count differs from header")
        kind = row["kind"]
        if kind not in KINDS:
            raise AnalysisError(f"CSV line {line_number}: unknown kind {kind!r}")
        event = {"kind": kind}
        for field in ("seq", "cpu", "cluster", "t0", "t1", "flags"):
            event[field] = unsigned(row[field], f"CSV line {line_number} {field}")
        if event["seq"] > UINT32_MAX:
            raise AnalysisError(f"CSV line {line_number}: seq exceeds uint32")
        for field in ("policy_cpu", "fast_switch", "requested_index", "requested_pstate", "token"):
            event[field] = optional_unsigned(row[field], f"CSV line {line_number} {field}")
        for field in ("policy_mask", "pre_cmd", "cmd"):
            event[field] = optional_unsigned(row[field], f"CSV line {line_number} {field}", hexadecimal=True)
        event["ret"] = signed32(row["ret"], f"CSV line {line_number} ret")

        if event["cpu"] not in CPU_IDS or event["cluster"] not in CLUSTER_IDS:
            raise AnalysisError(f"CSV line {line_number}: CPU or cluster outside T8103 topology")
        if event["t0"] > event["t1"]:
            raise AnalysisError(f"CSV line {line_number}: timestamp reversal")
        if event["t0"] < status["start_tick"] or event["t1"] > status["end_tick"]:
            raise AnalysisError(f"CSV line {line_number}: event outside capture ticks")
        if event["flags"] & ~1:
            raise AnalysisError(f"CSV line {line_number}: unknown flag bits")
        if not status["clusters"][event["cluster"]] & (1 << event["cpu"]) and kind != "dvfs":
            raise AnalysisError(f"CSV line {line_number}: idle CPU/cluster disagree with topology")

        if kind == "dvfs":
            if event["token"] is not None or event["flags"] or event["pre_cmd"] is None:
                raise AnalysisError(f"CSV line {line_number}: malformed dvfs fields")
            if event["policy_cpu"] not in CPU_IDS or event["policy_mask"] is None:
                raise AnalysisError(f"CSV line {line_number}: missing dvfs policy identity")
            if not event["policy_mask"] & (1 << event["policy_cpu"]):
                raise AnalysisError(f"CSV line {line_number}: policy CPU is outside policy mask")
            if event["policy_mask"] & ~status["clusters"][event["cluster"]]:
                raise AnalysisError(f"CSV line {line_number}: policy mask extends outside target cluster")
            if event["fast_switch"] not in (0, 1):
                raise AnalysisError(f"CSV line {line_number}: fast_switch must be 0 or 1")
            for field in ("requested_index", "requested_pstate"):
                if event[field] is None or event[field] > UINT32_MAX:
                    raise AnalysisError(f"CSV line {line_number}: dvfs {field} must be present and fit uint32")
            if event["ret"] > 0 or (event["ret"] == 0) != (event["cmd"] is not None):
                raise AnalysisError(f"CSV line {line_number}: dvfs write/error fields disagree")
            if event["ret"] < 0 and event["t0"] != event["t1"]:
                raise AnalysisError(f"CSV line {line_number}: failed dvfs poll must be a timestamp marker")
            if event["ret"] == 0 and (
                event["pre_cmd"] & BUSY_BIT or event["cmd"] & BUSY_BIT or not event["cmd"] & SET_BIT
            ):
                raise AnalysisError(f"CSV line {line_number}: successful dvfs command violates poll/SET invariants")
            stream = f"dvfs{event['cluster']}"
        else:
            if event["token"] in (None, 0) or event["pre_cmd"] is not None:
                raise AnalysisError(f"CSV line {line_number}: missing token or unexpected pre_cmd")
            if any(event[field] is not None for field in (
                "policy_cpu", "policy_mask", "fast_switch", "requested_index", "requested_pstate"
            )):
                raise AnalysisError(f"CSV line {line_number}: idle policy/request fields must be blank")
            if kind == "idle_enter":
                valid_mmio = status["mode"] == "mmio" and event["ret"] == 0
                if status["mode"] == "records" and event["ret"] != 0:
                    raise AnalysisError(f"CSV line {line_number}: records-only idle entry has a read error")
                if event["ret"] > 0 or (event["cmd"] is not None) != valid_mmio or event["flags"] != int(valid_mmio):
                    raise AnalysisError(f"CSV line {line_number}: idle MMIO validity fields disagree")
            elif kind == "idle_exit":
                if event["ret"] != 0 or event["cmd"] is not None or event["flags"] or event["t0"] != event["t1"]:
                    raise AnalysisError(f"CSV line {line_number}: malformed idle_exit")
            else:
                if event["ret"] == 0 or event["cmd"] is not None or event["flags"] or event["t0"] != event["t1"]:
                    raise AnalysisError(f"CSV line {line_number}: malformed cpu_pm_fail")
            stream = f"idle{event['cpu']}"

        event["stream"] = stream
        sequences[stream].append(event["seq"])
        events.append(event)

    for stream, seqs in sequences.items():
        if len(seqs) != len(set(seqs)):
            raise AnalysisError(f"duplicate sequence in {stream}")
        if stream.startswith("idle"):
            ordered = sorted((event for event in events if event["stream"] == stream), key=lambda event: event["seq"])
            for earlier, later in zip(ordered, ordered[1:]):
                if later["t0"] < earlier["t1"]:
                    raise AnalysisError(
                        f"{stream}: idle stream timestamp order reversed between seq {earlier['seq']} "
                        f"({earlier['t0']}..{earlier['t1']}) and seq {later['seq']} "
                        f"({later['t0']}..{later['t1']})"
                    )
    return events, sequences


def span_summary(spans: list[int], cntfrq: int) -> dict:
    """Summarize probe brackets, retaining empty groups as absent observations."""
    values = sorted(spans)
    metrics = {name: None for name in ("min", "median", "p95", "max")}
    if values:
        metrics = {
            "min": values[0],
            "median": statistics.median(values),
            "p95": values[(95 * len(values) + 99) // 100 - 1],
            "max": values[-1],
        }
    return {
        "count": len(values),
        "ticks": metrics,
        "nanoseconds": {
            name: value * 1_000_000_000 / cntfrq if value is not None and cntfrq else None
            for name, value in metrics.items()
        },
    }


def accessor_spans(events: list[dict], status: dict) -> dict:
    groups = {
        "dvfs": {"submitted_write": [], "failed_poll_marker": []},
        "idle_enter": {"records_no_read": [], "mmio_valid": [], "mmio_error": []},
        "idle_exit": {"timestamp_only": []},
        "cpu_pm_fail": {"timestamp_only": []},
    }
    for event in events:
        kind = event["kind"]
        if kind == "dvfs":
            operation = "submitted_write" if event["ret"] == 0 else "failed_poll_marker"
        elif kind == "idle_enter":
            if status["mode"] == "records":
                operation = "records_no_read"
            else:
                operation = "mmio_valid" if event["flags"] == 1 else "mmio_error"
        else:
            operation = "timestamp_only"
        groups[kind][operation].append(event["t1"] - event["t0"])
    return {
        "capture_mode": status["mode"],
        "scope": "all_committed_rows_including_straddling_and_drain",
        "definition": "t1-t0 probe brackets exclude record construction/publication overhead; failed-poll, idle-exit and CPU-PM-failure markers do not time those operations",
        "median_method": "middle value for odd counts; arithmetic mean of two middle values for even counts",
        "p95_method": "nearest rank: sorted value at ceil(0.95*count), one-based",
        "conversion": "nanoseconds=ticks*1000000000/cntfrq; converted values and even-count medians use approximate JSON numbers; null for absent observations or unknown frequency",
        "by_kind": {
            kind: {operation: span_summary(spans, status["cntfrq"]) for operation, spans in operations.items()}
            for kind, operations in groups.items()
        },
    }


def idle_pairs(events: list[dict], status: dict) -> dict:
    by_attempt = defaultdict(dict)
    for event in events:
        if event["kind"] == "dvfs":
            continue
        key = (event["cpu"], event["token"])
        attempt = by_attempt[key]
        if event["kind"] in attempt:
            raise AnalysisError(f"duplicate {event['kind']} for CPU {key[0]} token {key[1]}")
        attempt[event["kind"]] = event

    counts = Counter()
    per_cpu = {str(cpu): 0 for cpu in sorted(CPU_IDS)}
    paired_windows = defaultdict(list)
    for (cpu, token), attempt in by_attempt.items():
        if "cpu_pm_fail" in attempt:
            if len(attempt) != 1:
                raise AnalysisError(f"CPU {cpu} token {token}: cpu_pm_fail also has idle records")
            counts["cpu_pm_fail"] += 1
            continue
        entry = attempt.get("idle_enter")
        exit_event = attempt.get("idle_exit")
        if entry is None:
            counts["missing_enter"] += 1
        elif exit_event is None:
            counts["missing_exit"] += 1
        else:
            if exit_event["seq"] <= entry["seq"] or exit_event["t0"] < entry["t1"]:
                raise AnalysisError(f"CPU {cpu} token {token}: idle entry/exit order reversed")
            paired_windows[cpu].append((entry["t0"], exit_event["t1"], token))
            if entry["t0"] <= status["start_tick"] or exit_event["t1"] >= status["stop_tick"]:
                counts["boundary_pair_excluded"] += 1
            else:
                counts["complete_pairs"] += 1
                per_cpu[str(cpu)] += 1

    for cpu, windows in paired_windows.items():
        ordered = sorted(windows)
        for earlier, later in zip(ordered, ordered[1:]):
            if later[0] < earlier[1]:
                raise AnalysisError(
                    f"CPU {cpu}: overlapping idle intervals for tokens {earlier[2]} and {later[2]}"
                )

    return {
        **{name: counts[name] for name in (
            "complete_pairs", "boundary_pair_excluded", "missing_enter", "missing_exit", "cpu_pm_fail"
        )},
        "complete_pairs_by_cpu": per_cpu,
        "definition": "paired pre-WFI idle_enter and later idle_exit records, strictly inside capture bounds; not WFI residency",
    }


def analyze_text(events_csv: str, status_text: str, *, evidence_origin: str = "unverified_input",
                 pairwise_clock_error_ticks: int | None = None) -> dict:
    if evidence_origin not in {"unverified_input", "synthetic_fixture"}:
        raise AnalysisError("evidence_origin must be unverified_input or synthetic_fixture")
    status = parse_status(status_text)
    events, sequences = parse_events(events_csv, status)
    integrity_reasons = []
    stream_summaries = {}
    for name, counters in sorted(status["streams"].items()):
        attempts = counters["attempts"]
        committed = counters["committed"]
        overflow = counters["overflow"]
        missing = counters["missing_commit"]
        seqs = set(sequences.get(name, []))
        capacity_attempts = attempts - overflow if attempts >= overflow else -1
        if attempts != committed + overflow + missing:
            integrity_reasons.append(f"{name}: status counters do not reconcile")
        if capacity_attempts < 0 or any(seq >= capacity_attempts for seq in seqs):
            integrity_reasons.append(f"{name}: sequence outside retained attempts")
        if len(seqs) != committed:
            integrity_reasons.append(f"{name}: CSV rows differ from committed count")
        gaps = capacity_attempts - len(seqs)
        if gaps != missing:
            integrity_reasons.append(f"{name}: sequence gaps differ from missing_commit count")
        if overflow:
            integrity_reasons.append(f"{name}: overflow={overflow}")
        if missing:
            integrity_reasons.append(f"{name}: missing_commit={missing}")
        stream_summaries[name] = {**counters, "csv_rows": len(seqs), "sequence_gaps": max(gaps, 0)}

    if status["state"] != "complete":
        integrity_reasons.append(f"status state is {status['state']}, not complete")
    if status["interrupted"]:
        integrity_reasons.append("capture was interrupted")
    if status["stop_tick"] <= status["start_tick"]:
        integrity_reasons.append("active capture interval is empty")
    if status["start_online_mask"] != status["end_online_mask"]:
        integrity_reasons.append("online CPU mask changed during capture")
    if status["start_online_mask"] != 0xff or status["end_online_mask"] != 0xff:
        integrity_reasons.append("T8103 capture requires all eight CPUs online")
    if any(not (status["start_online_mask"] & (1 << event["cpu"])) for event in events):
        integrity_reasons.append("event writer CPU outside starting online mask")

    for cluster, endpoints in sorted(status["policies"].items()):
        resource = status["resources"][cluster]
        if resource["cmd_phys"] < 0x20 or resource["resource_size"] < 0x28:
            integrity_reasons.append(f"cluster{cluster}: invalid command-resource metadata")
        for edge, policy in endpoints.items():
            mask = policy["policy_mask"]
            cpu = policy["policy_cpu"]
            if mask != status["clusters"][cluster] or cpu not in CPU_IDS or not mask & (1 << cpu):
                integrity_reasons.append(f"cluster{cluster}: invalid {edge} policy identity")
            if policy["fast_switch"] not in (0, 1):
                integrity_reasons.append(f"cluster{cluster}: invalid {edge} fast_switch value")
        if endpoints["start"] != endpoints["end"]:
            integrity_reasons.append(f"cluster{cluster}: policy metadata changed during capture")

    dvfs = [event for event in events if event["kind"] == "dvfs"]
    for cluster in sorted(CLUSTER_IDS):
        reference = status["policies"][cluster]["start"]
        if any(
            event["policy_cpu"] != reference["policy_cpu"]
            or event["policy_mask"] != reference["policy_mask"]
            or event["fast_switch"] != reference["fast_switch"]
            for event in dvfs if event["cluster"] == cluster
        ):
            integrity_reasons.append(f"cluster{cluster}: DVFS event policy metadata differs from start")

    # Reservation order can differ from t0 order for nested/concurrent writers.
    # Count that condition without discarding otherwise valid DVFS rows.
    dvfs_seq_timestamp_inversions = 0
    for cluster in sorted(CLUSTER_IDS):
        ordered = sorted((event for event in dvfs if event["cluster"] == cluster), key=lambda event: event["seq"])
        dvfs_seq_timestamp_inversions += sum(
            later["t0"] < earlier["t0"] for earlier, later in zip(ordered, ordered[1:])
        )

    kind_counts = Counter(event["kind"] for event in events)
    idle_entries = [event for event in events if event["kind"] == "idle_enter"]
    valid_idle_samples = [event for event in idle_entries if event["flags"] == 1 and event["ret"] == 0]
    pairs = idle_pairs(events, status)
    try:
        final_entrants = screen_final_entrants(
            events, status, integrity_reasons=integrity_reasons,
            pairwise_clock_error_ticks=pairwise_clock_error_ticks,
        )
    except ValueError as exc:
        raise AnalysisError(str(exc)) from exc
    windows = {}
    for name, selected in (
        ("in_window", [event for event in events if event["t1"] <= status["stop_tick"]]),
        ("straddling_stop", [event for event in events if event["t0"] <= status["stop_tick"] < event["t1"]]),
        ("post_stop_drain", [event for event in events if event["t0"] > status["stop_tick"]]),
    ):
        by_kind = Counter(event["kind"] for event in selected)
        samples = [event for event in selected if event["kind"] == "idle_enter" and event["flags"] == 1]
        windows[name] = {
            "total": len(selected),
            "by_kind": {kind: by_kind[kind] for kind in sorted(KINDS)},
            "dvfs_successful_attempted_writes": sum(
                event["kind"] == "dvfs" and event["ret"] == 0 for event in selected
            ),
            "idle_valid_mmio_samples": len(samples),
            "idle_busy_bit31_valid_samples": sum(bool(event["cmd"] & BUSY_BIT) for event in samples),
        }
    incomplete_intervals = pairs["missing_enter"] + pairs["missing_exit"] + pairs["boundary_pair_excluded"]
    return {
        "analysis_abi": 2,
        "evidence_origin": evidence_origin,
        "capture": {
            "target": "T8103 observer ABI v1",
            "state": status["state"],
            "mode": status["mode"],
            "cntfrq_hz": status["cntfrq"],
            "start_tick": status["start_tick"],
            "stop_tick": status["stop_tick"],
            "end_tick": status["end_tick"],
            "interrupted": bool(status["interrupted"]),
            "active_duration_ticks": status["stop_tick"] - status["start_tick"],
            "drain_duration_ticks": status["end_tick"] - status["stop_tick"],
            "start_online_mask": hex(status["start_online_mask"]),
            "end_online_mask": hex(status["end_online_mask"]),
            "cluster_cpu_masks": {str(n): hex(mask) for n, mask in sorted(status["clusters"].items())},
            "cluster_command_resources": {
                str(n): {"cmd_phys": hex(resource["cmd_phys"]), "resource_size": hex(resource["resource_size"])}
                for n, resource in sorted(status["resources"].items())
            },
            "policy_endpoints": {
                str(n): {
                    edge: {
                        "policy_cpu": policy["policy_cpu"],
                        "policy_mask": hex(policy["policy_mask"]),
                        "fast_switch": policy["fast_switch"],
                    }
                    for edge, policy in endpoints.items()
                }
                for n, endpoints in sorted(status["policies"].items())
            },
        },
        "integrity": {
            "clean": not integrity_reasons,
            "scope": "ABI/status consistency and recorded-stream completeness; incomplete idle intervals are assessed separately",
            "reasons": integrity_reasons,
            "streams": stream_summaries,
        },
        "observed_records": {
            "scope": "all_committed_rows_including_straddling_and_drain",
            "total": len(events),
            "by_kind": {kind: kind_counts[kind] for kind in sorted(KINDS)},
            "dvfs_successful_attempted_writes": sum(event["ret"] == 0 for event in dvfs),
            "dvfs_pre_poll_errors_no_write": sum(event["ret"] < 0 for event in dvfs),
            "dvfs_seq_timestamp_inversions_tolerated": dvfs_seq_timestamp_inversions,
            "idle_valid_mmio_samples": len(valid_idle_samples),
            "idle_busy_bit31_valid_samples": sum(bool(event["cmd"] & (1 << 31)) for event in valid_idle_samples),
            "idle_mmio_read_errors": sum(event["ret"] < 0 for event in idle_entries),
        },
        "capture_window_records": {
            "definition": "in_window t1<=stop_tick; straddling_stop t0<=stop_tick<t1; post_stop_drain t0>stop_tick; all bounded by end_tick",
            **windows,
        },
        "accessor_spans": accessor_spans(events, status),
        "idle_intervals": pairs,
        "conditional_final_entrants": final_entrants,
        "claim_boundary": {
            "candidate_software_final_entrant": final_entrants["status"],
            "actual_wfi_overlap": "not_observed",
            "physical_idle_state": "not_observed",
            "dvfs_device_completion": "not_observed",
            "complete_software_interval_screen_eligible": (
                not integrity_reasons and not incomplete_intervals
                and final_entrants["idle_grammar"]["consistent"]
            ),
            "complete_software_interval_screen_note": "whole-stream completeness precondition only: requires a clean capture and no incomplete, boundary or contradictory idle pairs; conditional candidates may still exist among complete interior pairs; opportunity coverage and cross-CPU clock qualification remain required; never establishes actual WFI overlap",
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("events_csv", type=Path)
    parser.add_argument("status", type=Path)
    parser.add_argument("--synthetic-fixture", action="store_true", help="label test input as synthetic")
    parser.add_argument(
        "--pairwise-clock-error-ticks",
        help="assumed maximum pairwise counter-comparison error over the entire capture, as uint64 ticks; enables a conditional software screen, not clock qualification",
    )
    args = parser.parse_args(argv)
    try:
        result = analyze_text(
            args.events_csv.read_text(),
            args.status.read_text(),
            evidence_origin="synthetic_fixture" if args.synthetic_fixture else "unverified_input",
            pairwise_clock_error_ticks=(
                unsigned(args.pairwise_clock_error_ticks, "pairwise-clock-error-ticks")
                if args.pairwise_clock_error_ticks is not None else None
            ),
        )
    except (AnalysisError, OSError) as exc:
        print(json.dumps({"analysis_error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
