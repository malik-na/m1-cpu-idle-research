#!/usr/bin/env python3
"""Decode ABI 1 counter exchanges without certifying clocks or native provenance.

All arithmetic uses Python integers; raw counter values are never subtracted
modulo 2**64. A finite causal constraint is not a bound for an unsampled gap.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import sys


HEADER = (
    "phase,round,request_seq,ack_seq,source_requested,source_before,source_after,"
    "target_requested,target_actual,a0,b0,b1,a1,source_cntfrq,target_cntfrq,"
    "call_status,flags"
).split(",")
PHASES = ("pre", "post")
CPUS = range(8)
UINT64_MAX = (1 << 64) - 1
UINT32_MAX = (1 << 32) - 1
DECIMAL = re.compile(r"(?:0|[1-9][0-9]*)\Z")
SIGNED = re.compile(r"(?:0|-?[1-9][0-9]*)\Z")
HEX = re.compile(r"0x[0-9a-fA-F]+\Z")
GLOBAL_FIELDS = {
    "abi", "possible_mask", "cluster0_cpus", "cluster1_cpus",
    "config_ool_workaround", "ecv_alternative", "capacity_per_phase",
}
PHASE_FIELDS = {
    "state", "reference_cpu", "rounds", "attempted", "completed", "error",
    "metadata_completed", "start_tick", "end_tick", "start_online_mask",
    "end_online_mask",
}
META_FIELDS = {
    "valid", "actual", "error", "cntfrq", "cntkctl", "mmfr0",
    "workaround_present", "phys_read_workaround",
}


class AnalysisError(ValueError):
    """An input does not follow the versioned export syntax."""


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


def choice(value, choices, label):
    if value not in choices:
        raise AnalysisError(f"{label}: unsupported value {value!r}")
    return value


def cpu(text, label, *, actual=False):
    return choice(number(text, label, bits=32, signed=actual),
                  range(-1 if actual else 0, 8), label)


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
    expected = GLOBAL_FIELDS | {
        f"{phase}_{field}" for phase in PHASES for field in PHASE_FIELDS
    } | {
        f"{phase}_cpu{n}_{field}"
        for phase in PHASES for n in CPUS for field in META_FIELDS
    }
    if raw.keys() != expected:
        raise AnalysisError(f"status keys: missing={sorted(expected - raw.keys())}, "
                            f"unknown={sorted(raw.keys() - expected)}")
    parsed = {}
    for key, value in raw.items():
        if key.endswith("_state"):
            parsed[key] = choice(value, {"unused", "running", "complete", "failed"}, key)
        elif key.endswith(("_actual", "_reference_cpu")):
            parsed[key] = cpu(value, key, actual=True)
        elif key.endswith("_error"):
            parsed[key] = number(value, key, bits=32, signed=True)
        elif key.endswith(("_cntfrq", "_start_tick", "_end_tick")):
            parsed[key] = number(value, key, bits=32 if key.endswith("_cntfrq") else 64,
                                 optional=True)
        elif key.endswith(("_cntkctl", "_mmfr0")):
            parsed[key] = number(value, key, hexadecimal=True, optional=True)
        elif key.endswith(("_mask", "_cpus")):
            parsed[key] = number(value, key, hexadecimal=True)
            if parsed[key] & ~0xff:
                raise AnalysisError(f"{key}: includes CPUs outside 0..7")
        elif key.endswith(("_valid", "_workaround_present", "_phys_read_workaround")):
            parsed[key] = choice(number(value, key, bits=32,
                                       optional=not key.endswith("_valid")),
                                 {0, 1} if key.endswith("_valid") else {0, 1, None}, key)
        else:
            parsed[key] = number(value, key, bits=32)
    choice(parsed["abi"], {1}, "abi")
    choice(parsed["capacity_per_phase"], {1792}, "capacity_per_phase")
    for key in ("config_ool_workaround", "ecv_alternative"):
        choice(parsed[key], {0, 1}, key)
    for phase in PHASES:
        if parsed[f"{phase}_rounds"] > 256:
            raise AnalysisError(f"{phase}_rounds: exceeds ABI limit")
        for n in CPUS:
            prefix = f"{phase}_cpu{n}_"
            values = [parsed[prefix + field] for field in
                      ("cntfrq", "cntkctl", "mmfr0", "workaround_present", "phys_read_workaround")]
            valid = parsed[prefix + "valid"]
            if (valid and any(v is None for v in values)) or (not valid and any(v is not None for v in values)):
                raise AnalysisError(f"{prefix}valid: metadata presence disagrees with valid flag")
    return parsed


def parse_events(source):
    reader = csv.DictReader(io.StringIO(source), strict=True)
    rows = []
    try:
        if reader.fieldnames != HEADER:
            raise AnalysisError("CSV header differs from ABI 1")
        for line_no, cells in enumerate(reader, 2):
            if None in cells or any(value is None for value in cells.values()):
                raise AnalysisError(f"CSV row {line_no}: wrong number of cells")
            row = {"phase": choice(cells["phase"], PHASES, f"row {line_no} phase")}
            for key in HEADER[1:]:
                label = f"row {line_no} {key}"
                if key in ("source_requested", "target_requested"):
                    row[key] = cpu(cells[key], label)
                elif key in ("source_before", "source_after", "target_actual"):
                    row[key] = cpu(cells[key], label, actual=True)
                elif key == "call_status":
                    row[key] = number(cells[key], label, bits=32, signed=True)
                else:
                    row[key] = number(cells[key], label,
                                      bits=32 if key in ("round", "flags", "source_cntfrq", "target_cntfrq") else 64,
                                      optional=key in ("a0", "a1", "b0", "b1", "source_cntfrq", "target_cntfrq"))
            if row["flags"] & ~15:
                raise AnalysisError(f"row {line_no}: unknown flag bits")
            for field, bit in (("a0", 1), ("b0", 2), ("b1", 4), ("a1", 8)):
                if bool(row["flags"] & bit) != (row[field] is not None):
                    raise AnalysisError(f"row {line_no}: {field} presence disagrees with flags")
            if row["round"] > 255:
                raise AnalysisError(f"row {line_no}: round outside ABI range")
            rows.append(row)
            if len(rows) > 3584:
                raise AnalysisError("CSV exceeds both phase capacities")
    except csv.Error as error:
        raise AnalysisError(f"malformed CSV: {error}") from error
    return rows


def interval(lower, upper):
    return {"lower": lower, "upper": upper, "width": upper - lower}


def classification(bounds, tolerance, uncertainty):
    if tolerance is None:
        return "unavailable_without_predeclared_tolerance"
    if uncertainty is None:
        return "unavailable_without_endpoint_uncertainty"
    if bounds["lower"] > bounds["upper"]:
        return "empty_interval_falsifies_model"
    if -tolerance <= bounds["lower"] and bounds["upper"] <= tolerance:
        return "constrained_within_tolerance_under_model"
    if bounds["upper"] < -tolerance or bounds["lower"] > tolerance:
        return "contradicts_tolerance_under_model"
    return "inconclusive"


def row_summary(row, status, uncertainty, tolerance):
    errors = []
    phase = row["phase"]
    source, target = row["source_requested"], row["target_requested"]
    if row["call_status"]:
        errors.append("recorded_acquisition_error")
    if row["request_seq"] == 0 or row["ack_seq"] != row["request_seq"]:
        errors.append("request_ack_mismatch")
    if source == target or source != status[f"{phase}_reference_cpu"]:
        errors.append("requested_cpu_mismatch")
    if (row["source_before"] != source or row["source_after"] != source or row["target_actual"] != target):
        errors.append("actual_cpu_mismatch")
    freqs = [row["source_cntfrq"], row["target_cntfrq"],
             status[f"{phase}_cpu{source}_cntfrq"], status[f"{phase}_cpu{target}_cntfrq"]]
    if any(not f for f in freqs) or len(set(freqs)) != 1:
        errors.append("counter_frequency_mismatch_or_missing")
    raw = expanded = None
    if row["flags"] != 15:
        errors.append("missing_timestamp")
    else:
        raw = interval(row["b1"] - row["a1"], row["b0"] - row["a0"])
        if row["a1"] < row["a0"] or row["b1"] < row["b0"]:
            errors.append("local_counter_reversal_or_wrap")
        if raw["width"] < 0:
            errors.append("negative_causal_interval_width")
        if uncertainty is not None:
            expanded = interval(raw["lower"] - uncertainty, raw["upper"] + uncertainty)
    return {
        "raw": row, "errors": errors, "eligible_exchange": not errors,
        "raw_offset_interval_ticks": raw,
        "uncertainty_adjusted_interval_ticks": expanded,
        "tolerance_classification": (
            "suppressed_invalid_exchange" if errors else
            classification(expanded or raw, tolerance, uncertainty)
        ),
    }


def stable_model(rows, reference, field, tolerance, uncertainty):
    """Intersection is conditional on one offset per CPU for every included row."""
    if any(row[field] is None for row in rows):
        return {"status": "unavailable_without_endpoint_uncertainty", "star_intersections": [], "derived_pairs": []}
    offsets = {reference: interval(0, 0)}
    stars = []
    for target in CPUS:
        if target == reference:
            continue
        matching = [row[field] for row in rows if row["raw"]["target_requested"] == target]
        bounds = interval(max(b["lower"] for b in matching), min(b["upper"] for b in matching))
        offsets[target] = bounds
        stars.append({"source": reference, "target": target, "sample_count": len(matching),
                      "interval_ticks": bounds, "empty": bounds["width"] < 0})
    if any(bounds["width"] < 0 for bounds in offsets.values()):
        return {"status": "empty_intersection_falsifies_stable_offset_model",
                "star_intersections": stars, "derived_pairs": []}
    pairs = []
    for source in CPUS:
        for target in range(source + 1, 8):
            a, b = offsets[source], offsets[target]
            bounds = interval(b["lower"] - a["upper"], b["upper"] - a["lower"])
            pairs.append({"source": source, "target": target,
                          "interval_ticks": bounds,
                          "tolerance_classification": classification(bounds, tolerance, uncertainty)})
    return {"status": "nonempty_conditional_constraints", "star_intersections": stars,
            "derived_pairs": pairs}


def phase_summary(phase, rows, status, global_errors, tolerance, uncertainty):
    errors = list(global_errors)
    get = lambda key: status[f"{phase}_{key}"]
    reference, rounds = get("reference_cpu"), get("rounds")
    expected = [(r, target) for r in range(rounds) for target in CPUS if target != reference]
    observed = [(row["raw"]["round"], row["raw"]["target_requested"]) for row in rows]
    if get("state") != "complete":
        errors.append("phase_not_complete")
    if phase == "post" and (
        status["pre_state"] != "complete"
        or reference != status["pre_reference_cpu"]
        or rounds != status["pre_rounds"]
    ):
        errors.append("post_phase_violates_pre_phase_contract")
    if reference < 0 or rounds == 0:
        errors.append("reference_or_rounds_unavailable")
    if get("error"):
        errors.append("recorded_phase_error")
    if get("attempted") != len(rows) or get("completed") != sum(row["raw"]["call_status"] == 0 for row in rows):
        errors.append("exported_count_mismatch")
    if observed != expected or get("attempted") != rounds * 7 or get("completed") != rounds * 7:
        errors.append("incomplete_or_out_of_order_star_coverage")
    if any(row["errors"] for row in rows):
        errors.append("invalid_exchange_present")
    if get("start_online_mask") != 0xff or get("end_online_mask") != 0xff:
        errors.append("online_topology_changed_or_incomplete")
    if get("metadata_completed") != 8 or sum(status[f"{phase}_cpu{n}_valid"] for n in CPUS) != 8:
        errors.append("incomplete_metadata")
    freqs = set()
    for n in CPUS:
        prefix = f"{phase}_cpu{n}_"
        if phase == "post" and any(
            status[prefix + field] != status[f"pre_cpu{n}_{field}"]
            for field in META_FIELDS
        ):
            errors.append(f"cpu{n}_pre_post_metadata_mismatch")
        if status[prefix + "actual"] != n or status[prefix + "error"]:
            errors.append(f"cpu{n}_metadata_identity_or_error")
        freq = status[prefix + "cntfrq"]
        freqs.add(freq)
        if not freq:
            errors.append(f"cpu{n}_missing_or_zero_frequency")
        if status[prefix + "phys_read_workaround"] != 0:
            errors.append(f"cpu{n}_raw_counter_reader_unqualified")
        if status[prefix + "phys_read_workaround"] == 1 and status[prefix + "workaround_present"] != 1:
            errors.append(f"cpu{n}_contradictory_workaround_metadata")
        if not status["config_ool_workaround"] and status[prefix + "workaround_present"] == 1:
            errors.append(f"cpu{n}_workaround_present_with_support_disabled")
    if len(freqs) != 1:
        errors.append("metadata_counter_frequency_mismatch")
    start, end = get("start_tick"), get("end_tick")
    if start is None or end is None or start > end:
        errors.append("phase_timestamp_missing_or_reversed")
    prior_source = start
    prior_targets = {}
    for row in rows:
        raw = row["raw"]
        a0, a1, b0, b1 = (raw[key] for key in ("a0", "a1", "b0", "b1"))
        if a0 is not None and prior_source is not None and a0 < prior_source:
            errors.append("source_counter_reversed_between_rounds")
        if a1 is not None:
            prior_source = a1
            if end is not None and a1 > end:
                errors.append("round_outside_phase_reference_bracket")
        target = raw["target_requested"]
        if b0 is not None and target in prior_targets and b0 < prior_targets[target]:
            errors.append("target_counter_reversed_between_rounds")
        if b1 is not None:
            prior_targets[target] = b1
    result = {
        "state": get("state"), "errors": sorted(set(errors)),
        "expected_rows": rounds * 7, "exported_rows": len(rows),
        "acquisition_eligible_for_conditional_model": not errors,
        "model_assumption": "equal effective rates and one constant offset per CPU throughout this phase",
    }
    if errors:
        result["raw_stable_offset_model"] = result["uncertainty_adjusted_stable_offset_model"] = {"status": "suppressed_acquisition_failure"}
    else:
        result["raw_stable_offset_model"] = stable_model(rows, reference, "raw_offset_interval_ticks", None, None)
        result["uncertainty_adjusted_stable_offset_model"] = stable_model(rows, reference, "uncertainty_adjusted_interval_ticks", tolerance, uncertainty)
    return result


def option_uint(value, label):
    if value is not None and (isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= UINT64_MAX):
        raise AnalysisError(f"{label}: expected an integer from 0 through uint64 maximum")


def analyze_text(events_text, status_text, *, pairwise_tolerance_ticks=None,
                 endpoint_uncertainty_ticks=None, evidence_origin="unverified_input"):
    option_uint(pairwise_tolerance_ticks, "pairwise_tolerance_ticks")
    option_uint(endpoint_uncertainty_ticks, "endpoint_uncertainty_ticks")
    choice(evidence_origin, {"unverified_input", "synthetic_fixture"}, "evidence_origin")
    status = parse_status(status_text)
    raw_rows = parse_events(events_text)
    global_errors = []
    if status["possible_mask"] != 0xff:
        global_errors.append("unsupported_possible_topology")
    c0, c1 = status["cluster0_cpus"], status["cluster1_cpus"]
    if bin(c0).count("1") != 4 or bin(c1).count("1") != 4 or c0 & c1 or c0 | c1 != 0xff:
        global_errors.append("cluster_masks_do_not_partition_two_four_cpu_clusters")
    if [row["phase"] for row in raw_rows] != sorted((row["phase"] for row in raw_rows), key=PHASES.index):
        global_errors.append("phase_export_order_mismatch")
    if [row["request_seq"] for row in raw_rows] != list(range(1, len(raw_rows) + 1)):
        global_errors.append("request_sequence_gap_or_duplicate")
    rows = [row_summary(row, status, endpoint_uncertainty_ticks, pairwise_tolerance_ticks) for row in raw_rows]
    phases = {phase: phase_summary(phase, [r for r in rows if r["raw"]["phase"] == phase],
                                   status, global_errors, pairwise_tolerance_ticks, endpoint_uncertainty_ticks)
              for phase in PHASES}
    joint_errors = []
    if not all(p["acquisition_eligible_for_conditional_model"] for p in phases.values()):
        joint_errors.append("both_complete_eligible_phases_required")
    for field in ("reference_cpu", "rounds"):
        if status[f"pre_{field}"] != status[f"post_{field}"]:
            joint_errors.append(f"pre_post_{field}_mismatch")
    for n in CPUS:
        if any(status[f"pre_cpu{n}_{field}"] != status[f"post_cpu{n}_{field}"] for field in META_FIELDS):
            joint_errors.append(f"cpu{n}_pre_post_metadata_mismatch")
    pre_end, post_start = status["pre_end_tick"], status["post_start_tick"]
    if pre_end is None or post_start is None or pre_end > post_start:
        joint_errors.append("pre_post_reference_time_missing_or_reversed")
    for n in CPUS:
        before = [r["raw"]["b1"] for r in rows if r["raw"]["phase"] == "pre" and r["raw"]["target_requested"] == n and r["raw"]["b1"] is not None]
        after = [r["raw"]["b0"] for r in rows if r["raw"]["phase"] == "post" and r["raw"]["target_requested"] == n and r["raw"]["b0"] is not None]
        if before and after and max(before) > min(after):
            joint_errors.append(f"cpu{n}_pre_post_counter_reversal")
    joint = {
        "errors": joint_errors,
        "model_assumption": "common boot and one constant offset per CPU across both phases, including the unsampled gap; this assumption is not established by these files",
        "both_phases_eligible": not joint_errors,
    }
    for field, output, tolerance, uncertainty in (
        ("raw_offset_interval_ticks", "raw_stable_offset_model", None, None),
        ("uncertainty_adjusted_interval_ticks", "uncertainty_adjusted_stable_offset_model", pairwise_tolerance_ticks, endpoint_uncertainty_ticks),
    ):
        joint[output] = ({"status": "suppressed_acquisition_failure"} if joint_errors else
                         stable_model(rows, status["pre_reference_cpu"], field, tolerance, uncertainty))
    return {
        "schema": "counter-qualification-analysis-v1", "evidence_origin": evidence_origin,
        "inputs_sha256": {"events.csv": hashlib.sha256(events_text.encode()).hexdigest(),
                          "status.txt": hashlib.sha256(status_text.encode()).hexdigest()},
        "assumptions": {"predeclared_pairwise_tolerance_ticks": pairwise_tolerance_ticks,
                        "endpoint_uncertainty_ticks": endpoint_uncertainty_ticks,
                        "endpoint_uncertainty_meaning": "outward margin applied once to each causal interval endpoint; provenance and sufficiency are external assumptions"},
        "raw_status": status, "global_errors": global_errors, "exchanges": rows,
        "phases": phases, "shared_pre_post_model": joint,
        "claim_boundary": {
            "native_provenance": "not_authenticated",
            "common_boot_and_capture_bracketing": "requires_external_evidence_packet",
            "counter_comparison": "finite_causal_constraints_under_audited_acquisition_and_stated_rate_offset_uncertainty_assumptions",
            "guaranteed_pairwise_error_bound": "not_established",
            "unsampled_capture_interval": "not_qualified",
            "observer_clock_bound_export": "never_automatic",
            "physical_state_or_idle_policy": "no_conclusion",
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("events", type=Path)
    parser.add_argument("status", type=Path)
    parser.add_argument("--pairwise-tolerance-ticks", type=lambda value: number(value, "tolerance"),
                        help="predeclared absolute pairwise tolerance; does not qualify the observer's bound")
    parser.add_argument("--endpoint-uncertainty-ticks", type=lambda value: number(value, "uncertainty"),
                        help="assumed outward margin per derived endpoint; explicit 0 is an assumption, omission disables tolerance classification")
    parser.add_argument("--synthetic-fixture", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = analyze_text(args.events.read_bytes().decode("utf-8"),
                              args.status.read_bytes().decode("utf-8"),
                              pairwise_tolerance_ticks=args.pairwise_tolerance_ticks,
                              endpoint_uncertainty_ticks=args.endpoint_uncertainty_ticks,
                              evidence_origin="synthetic_fixture" if args.synthetic_fixture else "unverified_input")
    except (AnalysisError, OSError, UnicodeError) as error:
        parser.exit(2, f"counter qualification input error: {error}\n")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
