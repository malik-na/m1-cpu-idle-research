#!/usr/bin/env python3
"""Decode sparse PCPM samples, without calibrating state codes or residency.

Syntax errors reject the input. Acquisition contradictions remain visible beside
all raw records. Integer arithmetic does not wrap at the kernel's uint64 limit.
"""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import io
import json
from pathlib import Path
import re


HEADER = (
    "seq,slot,scheduled_ns,skipped_before,t_before_ns,t_after_ns,cpu_before,"
    "cpu_after,read_attempted,raw_valid,raw,read_errno"
).split(",")
HEADER_V2 = HEADER[:6] + ["counter_before", "counter_after", "counter_flags"] + HEADER[6:]
FIELDS = {
    "abi", "state", "mode", "error", "requested", "period_ms", "phase_ms",
    "start_ns", "end_ns", "budget_end_ns", "worker_cpu", "start_online_mask",
    "end_online_mask", "e_mask", "p_mask", "pmgr_phys", "pmgr_size",
    "register_offset", "regmap_existing", "regmap_internal_clockless",
    "regmap_stride", "regmap_val_bytes", "attempted", "missed_slots",
    "unattempted_after_error", "trailing_missed", "read_errors", "cpu_errors",
} | {f"cpu{cpu}.{field}" for cpu in range(8) for field in ("midr", "mpidr", "kind")}
COUNTER_VALUES = {
    "counter_cntfrq", "counter_cntkctl", "counter_mmfr0",
    "counter_workaround_present", "counter_phys_read_workaround",
}
COUNTER_FIELDS = COUNTER_VALUES | {
    "config_ool_workaround", "ecv_alternative", "counter_metadata_valid",
    "counter_metadata_cpu", "counter_metadata_error", "counter_errors", "time_errors",
}
FIELDS_BY_ABI = {1: FIELDS, 2: FIELDS | COUNTER_FIELDS}
HEADERS_BY_ABI = {1: HEADER, 2: HEADER_V2}
HEX_FIELDS = {
    "start_online_mask", "end_online_mask", "e_mask", "p_mask", "pmgr_phys",
    "pmgr_size",
}
FLAGS = {"regmap_existing", "regmap_internal_clockless", "read_attempted", "raw_valid",
         "config_ool_workaround", "ecv_alternative", "counter_metadata_valid",
         "counter_workaround_present", "counter_phys_read_workaround"}
UINT64_MAX = (1 << 64) - 1
NS_PER_MS = 1000000
DECIMAL = re.compile(r"(?:0|[1-9][0-9]*)\Z")
SIGNED = re.compile(r"(?:0|-?[1-9][0-9]*)\Z")
HEX = re.compile(r"0x[0-9a-fA-F]+\Z")


class AnalysisError(ValueError):
    """The input does not follow the versioned export syntax."""


def number(text, label, *, bits=64, signed=False, hexadecimal=False, optional=False):
    if optional and text == "":
        return None
    pattern = HEX if hexadecimal else SIGNED if signed else DECIMAL
    if not pattern.fullmatch(text):
        raise AnalysisError(f"{label}: invalid integer representation")
    try:
        value = int(text, 16 if hexadecimal else 10)
    except ValueError as error:
        raise AnalysisError(f"{label}: integer cannot be decoded") from error
    low = -(1 << (bits - 1)) if signed else 0
    high = (1 << (bits - int(signed))) - 1
    if not low <= value <= high:
        raise AnalysisError(f"{label}: outside {'int' if signed else 'uint'}{bits}")
    return value


def choice(value, values, label):
    if value not in values:
        raise AnalysisError(f"{label}: unsupported value {value!r}")
    return value


def parse_status(source):
    raw = {}
    for line_no, line in enumerate(source.splitlines(), 1):
        if not line:
            continue
        if line.count("=") != 1:
            raise AnalysisError(f"status line {line_no}: expected key=value")
        key, value = line.split("=", 1)
        if not key or key in raw:
            raise AnalysisError(f"status line {line_no}: missing or duplicate key")
        raw[key] = value
    if "abi" not in raw:
        raise AnalysisError("status: missing abi")
    abi = choice(number(raw["abi"], "abi", bits=32), {1, 2}, "abi")
    fields = FIELDS_BY_ABI[abi]
    if raw.keys() != fields:
        raise AnalysisError(f"status keys: missing={sorted(fields - raw.keys())}, "
                            f"unknown={sorted(raw.keys() - fields)}")
    status = {}
    for key, value in raw.items():
        if key == "state":
            status[key] = choice(value, {"unused", "complete", "failed"}, key)
        elif key == "mode":
            status[key] = choice(value, {"none", "records", "mmio"}, key)
        elif key.endswith(".kind"):
            status[key] = choice(value, {"E", "P", "unknown"}, key)
        elif key in HEX_FIELDS or key.endswith((".midr", ".mpidr")) or key in {"counter_cntkctl", "counter_mmfr0"}:
            status[key] = number(value, key, hexadecimal=True,
                                 bits=32 if key.endswith("_mask") else 64,
                                 optional=key in COUNTER_VALUES)
        elif key in {"error", "worker_cpu", "regmap_stride", "regmap_val_bytes",
                     "counter_metadata_cpu", "counter_metadata_error"}:
            status[key] = number(value, key, bits=32, signed=True)
        else:
            status[key] = number(value, key, bits=64 if key.endswith("_ns") else 32,
                                 optional=key in COUNTER_VALUES)
        if key in FLAGS and status[key] is not None:
            choice(status[key], {0, 1}, key)
    return status


def parse_events(source, abi=1):
    reader = csv.DictReader(io.StringIO(source), strict=True)
    rows = []
    try:
        if reader.fieldnames != HEADERS_BY_ABI[abi]:
            raise AnalysisError(f"CSV header differs from ABI {abi}")
        for line_no, cells in enumerate(reader, 2):
            if None in cells or any(value is None for value in cells.values()):
                raise AnalysisError(f"CSV row {line_no}: wrong number of cells")
            row = {}
            for key, value in cells.items():
                label = f"row {line_no} {key}"
                row[key] = number(value, label,
                                  bits=64 if key.endswith("_ns") or key in {"counter_before", "counter_after"} else 32,
                                  signed=key == "read_errno",
                                  hexadecimal=key == "raw",
                                  optional=key in {"raw", "counter_before", "counter_after"})
                if key in FLAGS:
                    choice(row[key], {0, 1}, label)
                if key == "counter_flags" and row[key] & ~0x3f:
                    raise AnalysisError(f"{label}: unsupported flag bits")
            rows.append(row)
            if len(rows) > 1000:
                raise AnalysisError("CSV exceeds ABI capacity of 1000 rows")
    except csv.Error as error:
        raise AnalysisError(f"malformed CSV: {error}") from error
    return rows


def statistics(values, unit="ns"):
    """Exact integer/rational descriptions, without float or wraparound."""
    if not values:
        return {"count": 0, f"minimum_{unit}": None, f"maximum_{unit}": None,
                f"sum_{unit}": 0, f"mean_{unit}": None}
    return {"count": len(values), f"minimum_{unit}": min(values), f"maximum_{unit}": max(values),
            f"sum_{unit}": sum(values),
            f"mean_{unit}": {"numerator": sum(values), "denominator": len(values)}}


def counter_metadata(status, rows):
    """Check the recorded reader gate, without authenticating the hardware."""
    if status["abi"] == 1:
        return {"available": False, "reader_qualified_by_recorded_metadata": False,
                "errors": [], "status": "unavailable_in_abi1"}
    errors = []
    valid = status["counter_metadata_valid"]
    cpu, error = status["counter_metadata_cpu"], status["counter_metadata_error"]
    if any((status[key] is not None) != bool(valid) for key in COUNTER_VALUES):
        errors.append("counter_metadata_presence_disagrees_with_valid_flag")
    if error > 0:
        errors.append("positive_counter_metadata_error")
    if valid:
        if cpu != status["worker_cpu"] or cpu not in range(8):
            errors.append("counter_metadata_cpu_mismatch")
        if status["counter_phys_read_workaround"] == 1 and status["counter_workaround_present"] != 1:
            errors.append("counter_physical_workaround_without_pointer")
        if not status["config_ool_workaround"] and status["counter_workaround_present"] == 1:
            errors.append("counter_workaround_present_with_support_disabled")
        expected_error = (-34 if status["counter_cntfrq"] == 0 else
                          -95 if status["counter_phys_read_workaround"] == 1 else 0)
        if error != expected_error:
            errors.append("counter_metadata_reader_gate_error_mismatch")
    elif cpu == -1:
        if error:
            errors.append("unattempted_counter_metadata_has_error")
    elif cpu not in range(8) or cpu == status["worker_cpu"] or error != -18:
        errors.append("absent_counter_metadata_not_explained_by_cpu_failure")
    if error:
        if status["state"] != "failed" or status["error"] != error:
            errors.append("counter_metadata_failure_terminal_state_mismatch")
        if rows or any(status[key] for key in ("start_ns", "end_ns", "budget_end_ns")):
            errors.append("counter_metadata_failure_has_schedule_or_rows")
    qualified = bool(valid and not error and not errors and
                     status["counter_cntfrq"] and status["counter_phys_read_workaround"] == 0)
    if (rows or status["state"] == "complete") and not qualified:
        errors.append("scheduled_capture_has_no_qualified_counter_reader")
    return {"available": True, "reader_qualified_by_recorded_metadata": qualified,
            "errors": errors,
            "status": "recorded_reader_gate_passed" if qualified else
                      "recorded_reader_gate_rejected" if error else "metadata_unavailable_or_inconsistent"}


def summarize_counter(row, status, prior):
    if status["abi"] == 1:
        return {"counter_errors": [], "counter_bracket_duration_ticks": None,
                "eligible_counter_bracket": False}
    errors = []
    before, after, flags = (row[key] for key in ("counter_before", "counter_after", "counter_flags"))
    if bool(flags & 1) != (before is not None) or bool(flags & 2) != (after is not None):
        errors.append("counter_presence_disagrees_with_valid_flags")
    if flags & 3 != (3 if row["cpu_before"] == status["worker_cpu"] else 0):
        errors.append("counter_valid_flags_disagree_with_cpu_gate")
    reversal = 0
    if before is not None and after is not None and after < before:
        reversal |= 4
        errors.append("counter_reversal_within_row")
    if prior and before is not None and prior["counter_after"] is not None and before < prior["counter_after"]:
        reversal |= 8
        errors.append("counter_reversal_from_previous_row")
    if row["t_after_ns"] < row["t_before_ns"]:
        reversal |= 16
    if prior and row["t_before_ns"] < prior["t_after_ns"]:
        reversal |= 32
    if flags & 0x3c != reversal:
        errors.append("counter_or_time_reversal_flags_disagree_with_timestamps")
    return {"counter_errors": errors,
            "counter_bracket_duration_ticks": None if before is None or after is None else after - before,
            "eligible_counter_bracket": not errors and flags == 3}


def topology_errors(status):
    errors = []
    e_mask, p_mask = status["e_mask"], status["p_mask"]
    if (e_mask | p_mask != 0xff or e_mask & p_mask or
            bin(e_mask).count("1") != 4 or bin(p_mask).count("1") != 4):
        errors.append("cpu_masks_do_not_partition_four_e_and_four_p_cpus")
    if status["start_online_mask"] != 0xff or status["end_online_mask"] != 0xff:
        errors.append("online_topology_incomplete_or_changed")
    identities = []
    for cpu in range(8):
        midr, mpidr, kind = (status[f"cpu{cpu}.{field}"] for field in ("midr", "mpidr", "kind"))
        model = midr & 0xff0ffff0
        expected = "E" if model == 0x610f0220 else "P" if model == 0x610f0230 else "unknown"
        if kind == "unknown" or kind != expected:
            errors.append(f"cpu{cpu}_midr_kind_mismatch_or_unknown")
        if bool(e_mask & (1 << cpu)) != (kind == "E") or bool(p_mask & (1 << cpu)) != (kind == "P"):
            errors.append(f"cpu{cpu}_kind_mask_mismatch")
        aff0, aff1 = mpidr & 0xff, (mpidr >> 8) & 0xff
        aff2, aff3 = (mpidr >> 16) & 0xff, (mpidr >> 32) & 0xff
        cluster = 0 if kind == "E" else 1
        if aff0 > 3 or aff1 != cluster or aff2 != cluster or aff3:
            errors.append(f"cpu{cpu}_mpidr_topology_mismatch")
        identities.append((aff0, aff1, aff2, aff3))
    if len(set(identities)) != 8:
        errors.append("duplicate_cpu_affinity_identity")
    worker = status["worker_cpu"]
    if worker not in range(8) or not e_mask & (1 << worker):
        errors.append("worker_is_not_recorded_e_cpu")
    return errors


def resource_errors(status):
    errors = []
    for key, expected in (("pmgr_phys", 0x23b700000), ("pmgr_size", 0x14000),
                          ("register_offset", 72), ("regmap_existing", 1),
                          ("regmap_internal_clockless", 1), ("regmap_stride", 4),
                          ("regmap_val_bytes", 4)):
        if status[key] != expected:
            errors.append(f"{key}_does_not_match_qualified_mapping_contract")
    if status["register_offset"] + 4 > status["pmgr_size"]:
        errors.append("register_outside_parent_resource")
    if status["pmgr_phys"] + status["pmgr_size"] > UINT64_MAX:
        errors.append("parent_resource_address_overflow")
    return errors


def summarize_row(row, status, prior, index):
    errors = []
    if row["seq"] != index:
        errors.append("sequence_gap_duplicate_or_reordering")
    previous_slot = prior["slot"] if prior else -1
    if (row["slot"] <= previous_slot or row["slot"] >= status["requested"] or
            row["skipped_before"] != row["slot"] - previous_slot - 1):
        errors.append("slot_order_or_skipped_count_mismatch")
    expected = (status["start_ns"] + status["phase_ms"] * NS_PER_MS +
                (row["slot"] + 1) * status["period_ms"] * NS_PER_MS)
    if expected > UINT64_MAX or row["scheduled_ns"] != expected:
        errors.append("scheduled_time_does_not_match_slot")
    before, after = row["t_before_ns"], row["t_after_ns"]
    if before > after:
        errors.append("sample_clock_reversal_or_wrap")
    if before < row["scheduled_ns"]:
        errors.append("sample_before_scheduled_time")
    if before < status["start_ns"] or after > status["end_ns"]:
        errors.append("sample_outside_recorded_capture")
    if prior and before < prior["t_after_ns"] + status["period_ms"] * NS_PER_MS // 2:
        errors.append("sample_gap_below_half_period")
    if prior and row["scheduled_ns"] < prior["t_after_ns"] + status["period_ms"] * NS_PER_MS // 2:
        errors.append("scheduled_slot_before_required_gap")
    if row["cpu_before"] != status["worker_cpu"] or row["cpu_after"] != status["worker_cpu"]:
        errors.append("actual_cpu_mismatch")
    if row["raw_valid"] != int(row["raw"] is not None):
        errors.append("raw_presence_disagrees_with_valid_flag")
    if row["read_errno"] > 0:
        errors.append("positive_read_errno")
    if not row["read_attempted"] and (row["read_errno"] or row["raw_valid"]):
        errors.append("unattempted_read_has_result")
    if row["read_attempted"] and (status["mode"] != "mmio" or
                                  row["cpu_before"] != status["worker_cpu"]):
        errors.append("read_attempted_outside_mmio_worker_contract")
    pre_read_reversal = status["abi"] == 2 and bool(row["counter_flags"] & 0x28)
    if row["read_attempted"] and pre_read_reversal:
        errors.append("read_attempted_after_preread_counter_or_time_reversal")
    if status["mode"] == "mmio" and row["cpu_before"] == status["worker_cpu"] and not pre_read_reversal and not row["read_attempted"]:
        errors.append("mmio_read_missing_on_worker")
    if row["read_attempted"] and row["raw_valid"] != int(row["read_errno"] == 0):
        errors.append("read_status_disagrees_with_valid_flag")
    # Even invalid acquisition retains the raw bitfield extraction. It is not a
    # sample claim until the read/mode/identity contract also holds.
    fields = None if not row["raw_valid"] or row["raw"] is None else {
        "actual_code": (row["raw"] >> 4) & 0xf,
        "target_code": row["raw"] & 0xf,
        "sticky_bit8": (row["raw"] >> 8) & 1,
        "sticky_bit9": (row["raw"] >> 9) & 1,
    }
    counter = summarize_counter(row, status, prior)
    counter["eligible_counter_bracket"] &= not errors
    return {"raw": row, "errors": errors, "raw_fields": fields, **counter,
            "eligible_successful_read": not errors and bool(row["read_attempted"] and row["raw_valid"]),
            "bracket_duration_ns": after - before,
            "schedule_lateness_ns": before - row["scheduled_ns"]}


def analyze_text(events_text, status_text, *, evidence_origin="unverified_input"):
    choice(evidence_origin, {"unverified_input", "synthetic_fixture"}, "evidence_origin")
    status = parse_status(status_text)
    raw_rows = parse_events(events_text, status["abi"])
    errors = []
    requested, period, phase = (status[key] for key in ("requested", "period_ms", "phase_ms"))
    if status["register_offset"] != 72:
        errors.append("fixed_register_offset_mismatch")
    if status["state"] == "unused":
        if status["mode"] != "none" or raw_rows:
            errors.append("unused_capture_has_mode_or_rows")
        for key in FIELDS - {"abi", "state", "mode", "register_offset", "worker_cpu"}:
            expected = "unknown" if key.endswith(".kind") else 0
            if status[key] != expected:
                errors.append(f"unused_capture_nondefault_{key}")
        if status["worker_cpu"] != -1 or status["register_offset"] != 72:
            errors.append("unused_capture_worker_or_offset_mismatch")
        if status["abi"] == 2:
            for key in COUNTER_FIELDS - {"config_ool_workaround", "ecv_alternative"}:
                expected = None if key in COUNTER_VALUES else -1 if key == "counter_metadata_cpu" else 0
                if status[key] != expected:
                    errors.append(f"unused_capture_nondefault_{key}")
    else:
        if status["mode"] not in {"records", "mmio"}:
            errors.append("consumed_capture_has_no_mode")
        if not 1 <= requested <= 1000 or not 10 <= period <= 1000 or not 0 <= phase < period:
            errors.append("request_parameters_outside_abi_limits")
        if phase + requested * period > 10000:
            errors.append("requested_schedule_exceeds_ten_second_limit")
        if status["state"] == "complete" or raw_rows:
            errors += topology_errors(status) + resource_errors(status)
    if status["state"] == "complete" or raw_rows:
        expected_budget = status["start_ns"] + (phase + requested * period) * NS_PER_MS
        if expected_budget > (1 << 63) - 1 or status["budget_end_ns"] != expected_budget:
            errors.append("worker_schedule_budget_mismatch_or_overflow")
    elif status["start_ns"] == 0 and (status["end_ns"] or status["budget_end_ns"]):
        errors.append("preworker_failure_has_partial_time_bracket")
    if status["error"] > 0:
        errors.append("positive_capture_error")
    if (status["state"] == "failed") != (status["error"] < 0):
        errors.append("capture_state_error_mismatch")
    if status["attempted"] != len(raw_rows):
        errors.append("attempted_count_differs_from_exported_rows")
    if requested != status["attempted"] + status["missed_slots"] + status["unattempted_after_error"]:
        errors.append("requested_slot_accounting_mismatch")
    if status["missed_slots"] != sum(row["skipped_before"] for row in raw_rows) + status["trailing_missed"]:
        errors.append("missed_slot_accounting_mismatch")
    if status["state"] != "failed" and status["unattempted_after_error"]:
        errors.append("unattempted_tail_without_capture_failure")
    if status["end_ns"] < status["start_ns"]:
        errors.append("capture_clock_reversal_or_wrap")
    rows = [summarize_row(row, status, raw_rows[index - 1] if index else None, index)
            for index, row in enumerate(raw_rows)]
    metadata = counter_metadata(status, raw_rows)
    errors += metadata["errors"]
    for row in rows:
        row["eligible_counter_bracket"] &= metadata["reader_qualified_by_recorded_metadata"]
    observed_read_errors = sum(row["read_attempted"] and row["read_errno"] != 0 for row in raw_rows)
    observed_cpu_errors = sum(row["cpu_before"] != status["worker_cpu"] or row["cpu_after"] != status["worker_cpu"] for row in raw_rows)
    if status["read_errors"] != observed_read_errors or status["cpu_errors"] != observed_cpu_errors:
        errors.append("acquisition_error_count_mismatch")
    if observed_cpu_errors and status["error"] != -18:
        errors.append("cpu_error_terminal_errno_mismatch")
    elif observed_read_errors and not observed_cpu_errors and status["error"] != raw_rows[-1]["read_errno"]:
        errors.append("read_error_terminal_errno_mismatch")
    observed_counter_errors = observed_time_errors = 0
    if status["abi"] == 2:
        observed_counter_errors = sum(bool(row["counter_flags"] & 0x0c) for row in raw_rows)
        observed_time_errors = sum(bool(row["counter_flags"] & 0x30) for row in raw_rows)
        if status["counter_errors"] != observed_counter_errors or status["time_errors"] != observed_time_errors:
            errors.append("counter_or_time_error_count_mismatch")
        if (observed_counter_errors or observed_time_errors) and not (observed_cpu_errors or observed_read_errors) and status["error"] != -34:
            errors.append("counter_or_time_terminal_errno_mismatch")
    for index, row in enumerate(raw_rows):
        counter_failure = status["abi"] == 2 and bool(row["counter_flags"] & 0x3c)
        if row["read_errno"] or row["cpu_before"] != status["worker_cpu"] or row["cpu_after"] != status["worker_cpu"] or counter_failure:
            if index != len(raw_rows) - 1:
                errors.append("capture_continued_after_acquisition_error")
            if status["state"] != "failed":
                errors.append("acquisition_error_without_failed_capture")
    if raw_rows:
        consumed = raw_rows[-1]["slot"] + 1
        if requested - consumed != status["trailing_missed"] + status["unattempted_after_error"]:
            errors.append("tail_slot_accounting_mismatch")
    if any(row["errors"] for row in rows):
        errors.append("invalid_sample_present")
    if any(row["counter_errors"] for row in rows):
        errors.append("invalid_counter_sample_present")
    # Counts describe observed words only. Missing slots are never denominator
    # corrections and unequal sampling gaps are never converted to occupancy.
    eligible = [row for row in rows if row["eligible_successful_read"]]
    actual = Counter(row["raw_fields"]["actual_code"] for row in eligible)
    target = Counter(row["raw_fields"]["target_code"] for row in eligible)
    pairs = Counter((row["raw_fields"]["actual_code"], row["raw_fields"]["target_code"]) for row in eligible)
    timing_rows = [row for row in rows if not row["errors"]]
    return {
        "schema": "pcpm-sampler-analysis-v2", "input_abi": status["abi"], "evidence_origin": evidence_origin,
        "inputs_sha256": {"events.csv": hashlib.sha256(events_text.encode("utf-8")).hexdigest(),
                          "status.txt": hashlib.sha256(status_text.encode("utf-8")).hexdigest()},
        "raw_status": status, "samples": rows,
        "integrity": {"errors": sorted(set(errors)), "internally_consistent": not errors,
                      "complete_lossless_schedule": not errors and status["state"] == "complete" and status["missed_slots"] == 0},
        "sampling": {
            "requested_slots": requested, "exported_rows": len(rows),
            "missed_slots": status["missed_slots"], "trailing_missed": status["trailing_missed"],
            "unattempted_after_error": status["unattempted_after_error"],
            "read_attempts": sum(row["raw"]["read_attempted"] for row in rows),
            "read_errors": status["read_errors"], "cpu_errors": status["cpu_errors"],
            "eligible_successful_reads": len(eligible),
            "actual_code_counts": [{"code": code, "samples": count} for code, count in sorted(actual.items())],
            "target_code_counts": [{"code": code, "samples": count} for code, count in sorted(target.items())],
            "actual_target_counts": [{"actual_code": a, "target_code": t, "samples": count}
                                     for (a, t), count in sorted(pairs.items())],
            "timing_bracket_ns": statistics([row["bracket_duration_ns"] for row in timing_rows]),
            "mmio_attempt_bracket_ns": statistics([row["bracket_duration_ns"] for row in timing_rows if row["raw"]["read_attempted"]]),
            "schedule_lateness_ns": statistics([row["schedule_lateness_ns"] for row in timing_rows]),
            "summary_scope": "descriptive_counts_of_row_valid_samples_only; capture_integrity_and_missing_slots_remain_separate",
            "counts_status": "row_valid_counts_from_inconsistent_capture" if errors else "row_valid_counts_without_physical_calibration",
        },
        "counter_domain": {
            **metadata,
            "recorded_counter_error_rows": status.get("counter_errors"),
            "recorded_time_error_rows": status.get("time_errors"),
            "eligible_brackets": sum(row["eligible_counter_bracket"] for row in rows),
            "bracket_ticks": statistics([row["counter_bracket_duration_ticks"] for row in rows
                                          if row["eligible_counter_bracket"]], "ticks"),
            "summary_scope": "locally_valid_row_brackets_only_not_capture_or_cross_cpu_clock_qualification",
            "ns_conversion": "not_performed_no_epoch_or_rate_equality_assumed",
            "cross_cpu_error_bound": "not_established_or_supplied",
            "apsc_correlation": "not_performed_requires_common_boot_reader_and_clock_qualification",
        },
        "claim_boundary": {
            "native_provenance": "not_authenticated",
            "actual_and_target": "numeric_bitfields_only_no_calibrated_pcpm_state_meaning",
            "read_bracket": "asynchronous_register_snapshot_not_transition_timestamp",
            "sticky_bits": "raw_flags_only_no_entry_count_or_residency",
            "time_occupancy_or_residency": "not_estimated",
            "pcpm_calibration": "requires_separate_matched_native_workload_windows_and_software_idle_timing",
            "observer_effect": "requires_absent_records_only_and_sparse_mmio_comparisons",
            "rail_state_energy_or_linux_policy": "no_conclusion",
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("events", type=Path)
    parser.add_argument("status", type=Path)
    parser.add_argument("--synthetic-fixture", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = analyze_text(args.events.read_bytes().decode("utf-8"),
                              args.status.read_bytes().decode("utf-8"),
                              evidence_origin="synthetic_fixture" if args.synthetic_fixture else "unverified_input")
    except (AnalysisError, OSError, UnicodeError) as error:
        parser.exit(2, f"PCPM sampler input error: {error}\n")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
