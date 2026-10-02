#!/usr/bin/env python3
"""Fail-closed, prospective A/B/C/D/E comparison for ABI 2 issue #5 packets.

All input paths stay private. A public result contains only numerical summaries,
packet-manifest/receipt hashes and the limits of the conditional clock model.
This program cannot authenticate that omitted failed attempts do not exist.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import statistics
import tempfile

import analyze_wfi
import publish_wfi_evidence as publisher


BLOCK_ORDERS = (
    ("wfi_clock", "wfi_mmio", "mmio", "records", "baseline"),
    ("baseline", "records", "mmio", "wfi_mmio", "wfi_clock"),
)
RUN_KEYS = {"mode", "packet", "qualification", "device_acceptance", "receipt", "evidence"}
ERROR = analyze_wfi.ASSUMED_PAIRWISE_ERROR_TICKS


class ComparisonError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ComparisonError(message)


def utc(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError) as error:
        raise ComparisonError("invalid private acquisition UTC") from error
    require(parsed.tzinfo is not None, "private acquisition UTC lacks offset")
    return parsed


def read_spec(path: Path) -> list[list[dict]]:
    obj = json.loads(path.read_text())
    require(isinstance(obj, dict) and set(obj) == {"schema", "blocks"} and obj["schema"] == 1,
            "comparison input schema differs")
    blocks = obj["blocks"]
    require(isinstance(blocks, list) and 1 <= len(blocks) <= 2,
            "comparison requires one or two complete prospective blocks")
    result = []
    for index, block in enumerate(blocks):
        require(isinstance(block, list) and len(block) == 5,
                "each block must contain exactly five acquisitions")
        require(all(isinstance(run, dict) and set(run) == RUN_KEYS for run in block),
                "run input fields differ")
        require(tuple(run["mode"] for run in block) == BLOCK_ORDERS[index],
                "prospective block order differs")
        for run in block:
            require(all(isinstance(run[key], str) and run[key] for key in RUN_KEYS - {"mode"}),
                    "missing private packet or publication input path")
        result.append(block)
    return result


def check_public_evidence(expected: Path, actual: Path) -> None:
    require(actual.is_dir() and not actual.is_symlink(), "published evidence directory missing")
    expected_names = {path.name for path in expected.iterdir()}
    require({path.name for path in actual.iterdir()} == expected_names,
            "published evidence file set differs")
    for name in expected_names:
        path = actual / name
        require(path.is_file() and not path.is_symlink()
                and publisher.file_sha256(path) == publisher.file_sha256(expected / name),
                "published evidence bytes differ from private packet replay")


def checked_run(run: dict, identity: publisher.Identity = publisher.WFI_IDENTITY) -> dict:
    mode = run["mode"]
    packet = Path(run["packet"])
    receipt_path = Path(run["receipt"])
    evidence = Path(run["evidence"])
    require(receipt_path.is_file() and not receipt_path.is_symlink(),
            "published receipt missing")
    # The existing publisher replays every private SHA256SUMS entry, the
    # acquisition-time collector, boot/device qualification, both counter
    # exchanges, raw observer decoding, endpoint checks, and public projection.
    # Exact replay also binds the receipt/evidence to this packet and source
    # revision. A changed publisher source requires the original checkout.
    with tempfile.TemporaryDirectory(prefix="wfi-block-replay-") as temporary:
        temp = Path(temporary)
        derived = publisher.publish(packet, mode, temp / "evidence", temp / "receipt.json",
                                    Path(run["qualification"]), Path(run["device_acceptance"]),
                                    identity)
        require(receipt_path.read_bytes() == (temp / "receipt.json").read_bytes(),
                "public receipt differs from private packet replay")
        check_public_evidence(temp / "evidence", evidence)

    records = json.loads((packet / "acquisition-record.json").read_text())
    begin, complete = records[0], records[-1]
    started, finished = utc(begin["utc"]), utc(complete["utc"])
    require(started < finished, "capture UTC interval is reversed")
    boot_id = (packet / "boot-id.txt").read_text().strip()
    require(boot_id, "private boot ID missing")
    before_rows, before = publisher.project_snapshot(packet, "before-snapshot.json")
    after_rows, after = publisher.project_snapshot(packet, "after-snapshot.json")
    publisher.check_conditions(before, after)
    observer, _ = publisher.check_analysis(packet, mode)
    require(derived["integrity_clean"] is True and
            derived["counter_pre_post_eligible_under_declared_model"] is True,
            "packet quality gate differs")
    policy = {key: value for key, value in before.items()
              if key.startswith("policy") and key != "policy0.scaling_cur_freq"
              and key != "policy4.scaling_cur_freq"}
    require(all(after[key] == value for key, value in policy.items()),
            "policy endpoints changed")
    require(derived["conditions"]["charger_online"] == 1
            and derived["conditions"]["brightness"] == 155,
            "AC1/brightness155 baseline differs")
    workers = {str(cpu): publisher.check_workload((packet / f"workload-cpu{cpu}.csv").read_bytes(), cpu)
               for cpu in (1, 5)}
    interior = derived["worker_pulses_fully_inside_external_window_by_cpu"]
    require(all(interior[str(cpu)] for cpu in (1, 5)), "missing interior worker pulses")

    return {
        "mode": mode, "packet": packet, "receipt": derived, "observer": observer,
        "boot_id": boot_id, "started": started, "finished": finished,
        "before": before, "after": after, "policy": policy,
        "workers": workers, "interior": interior,
        "packet_manifest_sha256": derived["packet_sha256s_sha256"],
        "public_receipt_sha256": publisher.file_sha256(receipt_path),
        "collector_sha256": derived["collector_acquisition_sha256"],
    }


def worker_summary(runs: list[dict], common: dict[str, list[int]]) -> list[dict]:
    result = []
    for run in runs:
        per_cpu = {}
        for cpu in ("1", "5"):
            values = [int(run["workers"][cpu][index]["end_monotonic_ns"])
                      - int(run["workers"][cpu][index]["start_monotonic_ns"])
                      for index in common[cpu]]
            per_cpu[cpu] = {"count": len(values), "median_ns": statistics.median(values),
                            "max_ns": max(values)}
        result.append({"mode": run["mode"], "per_cpu": per_cpu})
    return result


def interior_busy_rows(run: dict) -> list[dict]:
    packet = run["packet"]
    _, status, _, _ = analyze_wfi.parse_abi2_status((packet / "status.txt").read_text())
    samples, _ = analyze_wfi.parse_wfi_events((packet / "wfi-events.csv").read_text(),
                                               status, "wfi_mmio")
    rows = []
    for sample in samples:
        if (status["start_tick"] + ERROR < sample["t0"]
                and sample["t1"] + ERROR < status["stop_tick"]
                and sample["cmd"] & (1 << 31)):
            rows.append({"cpu": sample["cpu"], "cluster": sample["cluster"],
                         "token": sample["token"], "t0": sample["t0"], "t1": sample["t1"],
                         "raw_command": hex(sample["cmd"]),
                         "site": "first-attempt pre-DSB probe",
                         "capture_interior": "conditional_on_unproven_E240_cross_CPU_error"})
    return rows


def verify_bracket_lags(screen: dict, site: str) -> None:
    """Independently reject minimum-gap counts masquerading as <=600 exposure.

    A successful SET occurs somewhere in its writer bracket and a read occurs
    somewhere in its probe bracket. The maximum possible submission-to-read
    lag is therefore sample.t1 - SET.t0 (+ assumed E for different CPUs).
    """
    for decision in screen["decisions"]:
        if decision["status"] not in ("primary_pair", "exploratory_only_pair"):
            continue
        source, sample = decision["set"], decision["sample"]
        writer = source["cpu"] if site == "E" else source["writer_cpu"]
        sampler = sample["cpu"] if site == "E" else sample["sampling_cpu"]
        applied_error = 0 if writer == sampler else ERROR
        largest = sample["t1"] - source["t0"] + applied_error
        require(decision["largest_lag_under_model_ticks"] == largest
                and decision["set_sample_order_error_ticks"] == applied_error,
                f"{site} decoder underbounds write-to-read bracket lag")
        if decision["status"] == "primary_pair":
            require(largest <= analyze_wfi.PRIMARY_PAIR_TICKS,
                    f"{site} primary pair exceeds declared conservative lag")
        else:
            require(analyze_wfi.PRIMARY_PAIR_TICKS < largest
                    <= analyze_wfi.EXPLORATORY_PAIR_TICKS,
                    f"{site} exploratory pair exceeds declared conservative lag")


def compare(blocks: list[list[dict]],
            identity: publisher.Identity = publisher.WFI_IDENTITY) -> dict:
    require(1 <= len(blocks) <= 2, "one or two blocks required")
    runs = []
    for index, block in enumerate(blocks):
        require(tuple(run["mode"] for run in block) == BLOCK_ORDERS[index],
                "prospective block order differs")
        runs.extend(checked_run(run, identity) for run in block)
    require(len({run["boot_id"] for run in runs}) == len(runs),
            "private boot IDs repeat across acquisitions")
    require(all(earlier["finished"] < later["started"]
                for earlier, later in zip(runs, runs[1:])),
            "recorded UTC acquisition order differs")
    for field in ("collector_sha256",):
        require(len({run[field] for run in runs}) == 1,
                "acquisition-time collector source differs across packets")
    for field in ("release", "kernel_config_sha256", "gnu_build_id", "selected_entry",
                  "workload_sha256", "build_chain"):
        require(all(run["receipt"][field] == runs[0]["receipt"][field] for run in runs),
                f"same-image/workload field differs: {field}")
    require(all(run["policy"] == runs[0]["policy"] for run in runs),
            "policy endpoints differ between packets")
    common = {cpu: sorted(set.intersection(*(set(run["interior"][cpu]) for run in runs)))
              for cpu in ("1", "5")}
    require(all(common.values()), "no common fully interior worker pulse indices")

    cumulative = {cluster: {"e_primary_pairs": 0, "e_primary_busy": 0,
                            "e_exploratory_pairs": 0, "e_exploratory_busy": 0,
                            "c_primary_pairs": 0, "c_primary_busy": 0,
                            "c_exploratory_pairs": 0, "c_exploratory_busy": 0}
                  for cluster in ("0", "1")}
    public_blocks = []
    all_positive = []
    for block_index in range(len(blocks)):
        selected = runs[block_index * 5:(block_index + 1) * 5]
        by_mode = {run["mode"]: run for run in selected}
        e = by_mode["wfi_mmio"]
        c = by_mode["mmio"]
        e_pairs = e["observer"]["paired_opportunities"]
        c_pairs = c["observer"]["c_hook_comparable_lag"]
        require(e_pairs["status"] == c_pairs["status"] == "conditional_software_screen"
                and e_pairs["assumed_pairwise_clock_error_ticks"] == ERROR
                and c_pairs["assumed_pairwise_clock_error_ticks"] == ERROR,
                "C/E lag screen model differs")
        verify_bracket_lags(e_pairs, "E")
        verify_bracket_lags(c_pairs, "C")
        for cluster in ("0", "1"):
            ec, cc = e_pairs["by_cluster"][cluster], c_pairs["by_cluster"][cluster]
            for prefix, counts in (("e", ec), ("c", cc)):
                for stratum in ("primary", "exploratory"):
                    cumulative[cluster][f"{prefix}_{stratum}_pairs"] += counts[f"{stratum}_pairs"]
                    cumulative[cluster][f"{prefix}_{stratum}_busy"] += counts[f"{stratum}_busy"]
        positives = interior_busy_rows(e)
        all_positive.extend({"block": block_index + 1, **row} for row in positives)
        public_blocks.append({
            "block": block_index + 1,
            "recorded_mode_order": [run["mode"] for run in selected],
            "packets": [{"mode": run["mode"],
                         "packet_manifest_sha256": run["packet_manifest_sha256"],
                         "public_receipt_sha256": run["public_receipt_sha256"],
                         "interior_pulse_indices_by_cpu": run["interior"],
                         "thermal_zone0_millidegree_before_after": [
                             run["before"]["thermal_zone0.millidegree_celsius"],
                             run["after"]["thermal_zone0.millidegree_celsius"]],
                         "observer_loss_and_drain": run["receipt"]["observer_loss_and_drain"]}
                        for run in selected],
            "c_primary_by_cluster": c_pairs["by_cluster"],
            "e_primary_by_cluster": e_pairs["by_cluster"],
            "wfi_bracket_ticks": {mode: by_mode[mode]["observer"]["wfi_probe"]["bracket_ticks"]
                                  for mode in ("wfi_clock", "wfi_mmio")},
            "c_hook_bracket_ticks": {
                mode: by_mode[mode]["observer"]["established_event_analysis"]
                ["accessor_spans"]["by_kind"]["idle_enter"][operation]
                for mode, operation in (("records", "records_no_read"), ("mmio", "mmio_valid"))},
            "matched_worker_pulse_duration": worker_summary(selected, common),
        })

    enough = all(cumulative[cluster]["e_primary_pairs"] >= 20 for cluster in ("0", "1"))
    c_control = all(cumulative[cluster]["c_primary_busy"] >= 1 for cluster in ("0", "1"))
    zero_pairs = all(cumulative[cluster]["e_primary_busy"] == 0 for cluster in ("0", "1"))
    if all_positive:
        decision = "first_attempt_pre_DSB_BUSY_observed"
    elif enough and c_control and zero_pairs:
        decision = "exposure_gate_met_but_environment_comparability_unverified_inconclusive"
    elif len(blocks) == 1:
        decision = "first_block_inconclusive_second_block_permitted"
    else:
        decision = "underexposed_or_C_control_unmet_inconclusive_stop"
    if len(blocks) == 2:
        first_positive = any(row["block"] == 1 for row in all_positive)
        require(not first_positive,
                "second block was not needed under first-block decision gates")
    return {
        "scope": "prospective fresh-boot ABI2 A/B/C/D/E conditional software comparison",
        "native_status": "derived_from_supplied_private_packets_only",
        "block_count": len(blocks), "packet_count": len(runs),
        "identity": {field: runs[0]["receipt"][field] for field in
                     ("release", "kernel_config_sha256", "gnu_build_id", "selected_entry",
                      "workload_sha256", "collector_acquisition_sha256")},
        "acquisition_order": "distinct private boot IDs and strictly increasing recorded UTC intervals; wall-clock correction and omitted failed attempts are not independently excluded",
        "conditions": {"charger_online_at_checked_endpoints": 1,
                       "brightness_at_checked_endpoints": 155,
                       "policy_endpoints_equal": True,
                       "interior_changes": "not_observed",
                       "usb_network_background_activity": "unknown_not_fully_observed",
                       "thermal_band_and_trend_comparability": "unverified_no_predeclared_numeric_band",
                       "C_E_sensitive_contrast": "not_established"},
        "common_fully_interior_worker_pulse_indices_by_cpu": common,
        "assumed_pairwise_cross_CPU_error_ticks": ERROR,
        "cross_CPU_clock_bound": "unproven_through_capture",
        "blocks": public_blocks,
        "c_e_lag_screen_cumulative_by_cluster": cumulative,
        "descriptive_E_20_primary_pairs_each_cluster": enough,
        "descriptive_E_zero_BUSY_in_primary_pairs": zero_pairs,
        "C_pending_primary_lag_control_each_cluster": c_control,
        "positive_first_attempt_interior_busy_rows": all_positive,
        "decision": decision,
        "claim_boundary": "BUSY is observed at the first-attempt pre-DSB probe only; this comparison does not establish a final-core software candidate or a physically asleep peer. WFI-instruction state, physical rail power, energy, command completion and a guaranteed cross-CPU clock bound are unobserved",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_json", type=Path, help="private manifest naming packets, qualifications, receipts and public evidence")
    parser.add_argument("--out", type=Path, help="new sanitized comparison JSON path; stdout if omitted")
    args = parser.parse_args()
    try:
        result = compare(read_spec(args.input_json))
        encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
        if args.out:
            require(not args.out.exists(), "comparison output already exists")
            args.out.write_text(encoded)
        else:
            print(encoded, end="")
    except (OSError, UnicodeError, KeyError, TypeError, ValueError,
            analyze_wfi.legacy.AnalysisError) as error:
        parser.exit(2, f"ABI2 matched-block comparison rejected: {error}\n")


if __name__ == "__main__":
    main()
