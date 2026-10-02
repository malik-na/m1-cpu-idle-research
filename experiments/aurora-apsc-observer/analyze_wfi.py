#!/usr/bin/env python3
"""Fail-closed ABI 2 integrity check for raw first-attempt WFI-seam records.

The probe runs after the CPU power-control MSR and before the existing DSB/WFI
sequence. A sampled BUSY bit is a software/MMIO observation at that probe,
not proof that BUSY remained set at WFI or that the CPU entered a power state.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import io
import json
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "linux-apsc-observer"))
import analyze as legacy  # noqa: E402


WFI_HEADER = ["seq", "cpu", "cluster", "token", "t0", "t1", "cmd", "mode"]
WFI_MODES = {"wfi_clock", "wfi_mmio"}
ALL_MODES = {"records", "mmio", *WFI_MODES}
WFI_FIELDS = ("attempts", "committed", "overflow", "missing_commit")


def parse_abi2_status(source: str) -> tuple[dict, dict, dict, str]:
    raw = {}
    for line_number, line in enumerate(source.splitlines(), 1):
        if not line or line.count("=") != 1:
            raise legacy.AnalysisError(f"status line {line_number}: expected key=value")
        key, value = line.split("=", 1)
        if not key or not value or key in raw:
            raise legacy.AnalysisError(f"status line {line_number}: empty or duplicate key/value")
        raw[key] = value
    if raw.get("abi") != "2":
        raise legacy.AnalysisError("WFI analyzer requires observer ABI 2")
    if raw.get("mode") not in ALL_MODES:
        raise legacy.AnalysisError("unknown observer ABI 2 capture mode")

    extra = {"wfi_pending_after_drain", "wfi_prepare_after_stop", "wfi_prepare_bad_mapping"}
    extra.update(f"wfi{cpu}_{field}" for cpu in legacy.CPU_IDS for field in WFI_FIELDS)
    if not extra <= raw.keys():
        raise legacy.AnalysisError(f"ABI 2 status missing {sorted(extra - raw.keys())}")
    wfi_numbers = {key: legacy.unsigned(raw[key], f"status {key}") for key in extra}
    for cpu in legacy.CPU_IDS:
        if any(wfi_numbers[f"wfi{cpu}_{field}"] > legacy.UINT32_MAX for field in WFI_FIELDS):
            raise legacy.AnalysisError(f"wfi{cpu}: counter exceeds uint32")
    for key in ("wfi_pending_after_drain", "wfi_prepare_after_stop", "wfi_prepare_bad_mapping"):
        if wfi_numbers[key] > legacy.INT32_MAX:
            raise legacy.AnalysisError(f"{key} exceeds signed atomic counter range")

    # The original event stream is byte-for-byte ABI 1. Project only the
    # added ABI 2 status keys so the established parser can validate it.
    projected = dict(raw)
    for key in extra:
        del projected[key]
    projected["abi"] = "1"
    if projected["mode"] in WFI_MODES:
        projected["mode"] = "records"  # C idle-enter hook does not sample in WFI modes.
    projected_text = "\n".join(f"{key}={value}" for key, value in projected.items()) + "\n"
    parsed = legacy.parse_status(projected_text)
    return raw, parsed, wfi_numbers, projected_text


def parse_wfi_events(source: str, status: dict, mode: str) -> tuple[list[dict], dict[int, list[int]]]:
    reader = csv.DictReader(io.StringIO(source, newline=""), restval=None)
    if reader.fieldnames != WFI_HEADER:
        raise legacy.AnalysisError(f"WFI CSV header differs from ABI 2: expected {','.join(WFI_HEADER)}")

    samples = []
    sequences = defaultdict(list)
    for line_number, row in enumerate(reader, 2):
        if None in row or any(value is None for value in row.values()):
            raise legacy.AnalysisError(f"WFI CSV line {line_number}: field count differs from header")
        sample = {field: legacy.unsigned(row[field], f"WFI CSV line {line_number} {field}")
                  for field in ("seq", "cpu", "cluster", "token", "t0", "t1")}
        sample["cmd"] = legacy.optional_unsigned(row["cmd"], f"WFI CSV line {line_number} cmd", hexadecimal=True)
        sample["mode"] = row["mode"]
        cpu, cluster = sample["cpu"], sample["cluster"]
        if sample["seq"] > legacy.UINT32_MAX or cpu not in legacy.CPU_IDS or cluster not in legacy.CLUSTER_IDS:
            raise legacy.AnalysisError(f"WFI CSV line {line_number}: invalid seq/CPU/cluster")
        if not status["clusters"][cluster] & (1 << cpu):
            raise legacy.AnalysisError(f"WFI CSV line {line_number}: CPU and cluster disagree with topology")
        if sample["token"] == 0 or sample["t0"] > sample["t1"]:
            raise legacy.AnalysisError(f"WFI CSV line {line_number}: zero token or reversed probe bracket")
        if sample["t0"] < status["start_tick"] or sample["t1"] > status["end_tick"]:
            raise legacy.AnalysisError(f"WFI CSV line {line_number}: outside capture/drain ticks")
        if mode not in WFI_MODES or sample["mode"] != mode:
            raise legacy.AnalysisError(f"WFI CSV line {line_number}: sample mode disagrees with capture mode")
        if (sample["cmd"] is not None) != (mode == "wfi_mmio"):
            raise legacy.AnalysisError(f"WFI CSV line {line_number}: command presence disagrees with mode")
        sequences[cpu].append(sample["seq"])
        samples.append(sample)

    for cpu, seqs in sequences.items():
        if len(seqs) != len(set(seqs)):
            raise legacy.AnalysisError(f"wfi{cpu}: duplicate sequence")
        ordered = sorted((sample for sample in samples if sample["cpu"] == cpu), key=lambda s: s["seq"])
        for earlier, later in zip(ordered, ordered[1:]):
            if later["t0"] < earlier["t1"]:
                raise legacy.AnalysisError(f"wfi{cpu}: probe brackets overlap or reverse in sequence")
    return samples, sequences


def analyze_text(events_csv: str, status_text: str, wfi_csv: str) -> dict:
    raw_status, projected_status, wfi_numbers, projected_text = parse_abi2_status(status_text)
    mode = raw_status["mode"]
    established = legacy.analyze_text(events_csv, projected_text)
    samples, sequences = parse_wfi_events(wfi_csv, projected_status, mode)
    events, _ = legacy.parse_events(events_csv, projected_status)

    reasons = list(established["integrity"]["reasons"])
    streams = {}
    for cpu in sorted(legacy.CPU_IDS):
        prefix = f"wfi{cpu}_"
        counters = {field: wfi_numbers[prefix + field] for field in WFI_FIELDS}
        attempts, committed, overflow, missing = (counters[field] for field in WFI_FIELDS)
        retained = attempts - overflow if attempts >= overflow else -1
        seqs = set(sequences.get(cpu, ()))
        gaps = retained - len(seqs)
        if attempts != committed + overflow + missing:
            reasons.append(f"wfi{cpu}: status counters do not reconcile")
        if retained < 0 or any(seq >= retained for seq in seqs):
            reasons.append(f"wfi{cpu}: sequence outside retained attempts")
        if len(seqs) != committed:
            reasons.append(f"wfi{cpu}: CSV rows differ from committed count")
        if gaps != missing:
            reasons.append(f"wfi{cpu}: sequence gaps differ from missing_commit count")
        if overflow:
            reasons.append(f"wfi{cpu}: overflow={overflow}")
        if missing:
            reasons.append(f"wfi{cpu}: missing_commit={missing}")
        streams[str(cpu)] = {**counters, "csv_rows": len(seqs), "sequence_gaps": max(gaps, 0)}
    if wfi_numbers["wfi_pending_after_drain"]:
        reasons.append(f"wfi_pending_after_drain={wfi_numbers['wfi_pending_after_drain']}")
    if wfi_numbers["wfi_prepare_bad_mapping"]:
        reasons.append(f"wfi_prepare_bad_mapping={wfi_numbers['wfi_prepare_bad_mapping']}")

    # The same-CPU idle-enter is the software precursor for each assembly
    # sample. Missing or contradictory matches invalidate a clean capture.
    idle_enters = {(event["cpu"], event["token"]): event for event in events
                   if event["kind"] == "idle_enter"}
    idle_exits = {(event["cpu"], event["token"]): event for event in events
                  if event["kind"] == "idle_exit"}
    wfi_by_attempt = defaultdict(list)
    for sample in samples:
        key = (sample["cpu"], sample["token"])
        wfi_by_attempt[key].append(sample)
        entry = idle_enters.get(key)
        if entry is None:
            reasons.append(f"wfi{sample['cpu']} seq {sample['seq']}: no matching idle_enter")
        elif entry["cluster"] != sample["cluster"] or entry["t1"] > sample["t0"]:
            reasons.append(f"wfi{sample['cpu']} seq {sample['seq']}: idle_enter order/topology mismatch")
        exit_event = idle_exits.get(key)
        if exit_event is not None and sample["t1"] > exit_event["t0"]:
            reasons.append(f"wfi{sample['cpu']} seq {sample['seq']}: sample after recorded idle_exit")

    coverage_counts = Counter()
    coverage_by_cpu = {str(cpu): Counter() for cpu in sorted(legacy.CPU_IDS)}
    coverage_tokens = []
    if mode in WFI_MODES:
        for key, entry in sorted(idle_enters.items()):
            cpu, token = key
            exit_event = idle_exits.get(key)
            matching = wfi_by_attempt.get(key, ())
            if len(matching) > 1:
                reasons.append(f"CPU {cpu} token {token}: multiple first-attempt WFI samples")
            if matching:
                disposition = "matched_wfi_sample"
            elif exit_event is not None:
                # Both hooks checked the one-shot active flag on the same CPU;
                # the WFI preparation runs between them. This does not depend
                # on comparing that CPU's counter to stop_tick on another CPU.
                disposition = "unexplained_paired_path_without_sample"
                reasons.append(f"CPU {cpu} token {token}: active-gated idle pair lacks WFI sample")
            else:
                # An entry without its exit may straddle stop or remain asleep.
                # The after-stop counter is aggregate and cannot name a token.
                disposition = "open_interval_without_sample_unresolved"
            coverage_counts[disposition] += 1
            coverage_by_cpu[str(cpu)][disposition] += 1
            coverage_tokens.append({
                "cpu": cpu, "cluster": entry["cluster"], "token": token,
                "idle_enter_seq": entry["seq"], "idle_enter_t0": entry["t0"],
                "idle_enter_t1": entry["t1"],
                "idle_exit_seq": exit_event["seq"] if exit_event else None,
                "idle_exit_t0": exit_event["t0"] if exit_event else None,
                "wfi_seq": matching[0]["seq"] if matching else None,
                "wfi_t0": matching[0]["t0"] if matching else None,
                "wfi_t1": matching[0]["t1"] if matching else None,
                "disposition": disposition,
            })

    def empty_cluster_counts() -> dict[str, dict]:
        return {str(cluster): {"samples": 0,
                               "busy_bit31": 0 if mode == "wfi_mmio" else None,
                               "set_bit25": 0 if mode == "wfi_mmio" else None}
                for cluster in sorted(legacy.CLUSTER_IDS)}

    partitions = {name: {"total": 0, "by_cluster": empty_cluster_counts()}
                  for name in ("in_window", "straddling_stop", "post_stop_drain")}
    for sample in samples:
        if sample["t1"] <= projected_status["stop_tick"]:
            partition = "in_window"
        elif sample["t0"] <= projected_status["stop_tick"]:
            partition = "straddling_stop"
        else:
            partition = "post_stop_drain"
        partitions[partition]["total"] += 1
        group = partitions[partition]["by_cluster"][str(sample["cluster"])]
        group["samples"] += 1
        if sample["cmd"] is not None:
            group["busy_bit31"] += bool(sample["cmd"] & legacy.BUSY_BIT)
            group["set_bit25"] += bool(sample["cmd"] & legacy.SET_BIT)

    return {
        "observer_abi": 2,
        "capture_mode": mode,
        "integrity": {"clean": not reasons, "reasons": reasons,
                      "wfi_pending_after_drain": wfi_numbers["wfi_pending_after_drain"],
                      "wfi_prepare_after_stop": wfi_numbers["wfi_prepare_after_stop"],
                      "wfi_prepare_bad_mapping": wfi_numbers["wfi_prepare_bad_mapping"],
                      "wfi_streams": streams},
        "reverse_coverage": {
            "status": "classified_per_idle_entry" if mode in WFI_MODES else "not_applicable_in_non_wfi_mode",
            "definition": "a captured same-CPU/token idle_enter and idle_exit pair witnesses an active-gated path through WFI preparation; missing WFI sample in that pair fails integrity",
            "boundary_limit": "an entry lacking a captured exit may straddle capture stop or remain open; raw cross-CPU start/stop ticks do not establish exact interior without clock qualification",
            "after_stop_diagnostic": "wfi_prepare_after_stop is aggregate and cannot be assigned to an idle token",
            "wfi_prepare_after_stop": wfi_numbers["wfi_prepare_after_stop"],
            "idle_entries": len(idle_enters),
            "all_captured_entries_have_sample": (
                coverage_counts["matched_wfi_sample"] == len(idle_enters)
                if mode in WFI_MODES else None
            ),
            "all_captured_paired_paths_have_sample": (
                coverage_counts["unexplained_paired_path_without_sample"] == 0
                if mode in WFI_MODES else None
            ),
            "counts": {name: coverage_counts[name] for name in (
                "matched_wfi_sample", "unexplained_paired_path_without_sample",
                "open_interval_without_sample_unresolved")},
            "by_cpu": {cpu: {name: counts[name] for name in (
                "matched_wfi_sample", "unexplained_paired_path_without_sample",
                "open_interval_without_sample_unresolved")}
                for cpu, counts in coverage_by_cpu.items()},
            "per_token": coverage_tokens,
        },
        "wfi_probe": {
            "site": "first deep-idle attempt after power-control MSR, before original DSB/WFI",
            "scope": "all committed rows retained in the raw CSV; by_cluster contains only the recorded in-window stratum",
            "capture_partition": "in_window t1<=stop_tick; straddling_stop t0<=stop_tick<t1; post_stop_drain t0>stop_tick",
            "capture_partition_limit": "stop_tick may be from a different CPU; these numeric strata require a separately justified clock model for temporal claims",
            "command_bit_counts": "available only in wfi_mmio mode; null means no command read",
            "total": len(samples),
            "in_window": partitions["in_window"]["total"],
            "straddling_stop": partitions["straddling_stop"]["total"],
            "post_stop_drain": partitions["post_stop_drain"]["total"],
            "by_cluster": partitions["in_window"]["by_cluster"],
            "by_capture_partition": partitions,
            "bracket_ticks": legacy.span_summary([sample["t1"] - sample["t0"] for sample in samples],
                                                  projected_status["cntfrq"]),
        },
        "claim_boundary": {
            "wfi_instruction_command_state": "not_observed",
            "cross_cpu_order": "requires separately justified counter comparability over the capture",
            "device_command_completion": "not_observed",
            "physical_cpu_power_state": "not_observed",
            "raw_inputs_authoritative": ["events.csv", "status.txt", "wfi-events.csv"],
        },
        "established_event_analysis": established,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("events_csv", type=Path)
    parser.add_argument("status", type=Path)
    parser.add_argument("wfi_csv", type=Path)
    args = parser.parse_args()
    try:
        result = analyze_text(args.events_csv.read_text(), args.status.read_text(), args.wfi_csv.read_text())
    except (OSError, UnicodeError, legacy.AnalysisError) as error:
        parser.exit(2, f"WFI observer input invalid: {error}\n")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
