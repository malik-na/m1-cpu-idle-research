#!/usr/bin/env python3
"""Read-only replay of the first public ABI-2 PCPM sparse-MMIO packet.

The reported word and ACTUAL/TARGET fields are numerical observations only.
The predeclared one-boot phase contrast failed. Cross-CPU E=240 ticks remains
an assumption, and this replay does not establish physical power state.
"""

from __future__ import annotations

import argparse
from collections import Counter
import gzip
import json
from pathlib import Path
import re
import statistics

from verify_records_export import (
    EvidenceError, complete_p_intervals, csv_rows, four_p_witness, getint,
    load_packet as load_records_packet, measured_release_window, sha256, status,
)


PACKET = Path(__file__).resolve().parent / "native-evidence" / "mmio-abi2"
RECORDS = Path(__file__).resolve().parent / "native-evidence" / "records-abi2"
PRIVATE_MANIFEST_SHA = "5c71b6d9e7b2a38f39f74fc6d604c1e1e82dd6268885606d3c813e3b51633c13"
GUARD_NS = 300_000_000
EXPECTED_CSV = {
    "pcpm-samples.csv.gz": 90,
    "apsc-events.csv.gz": 10_625,
    "apsc-wfi-events.csv.gz": 0,
    "counter-pre-events.csv.gz": 1792,
    "counter-post-events.csv.gz": 3584,
}
EXPECTED_FILES = set(EXPECTED_CSV) | {
    "pcpm-status-before.txt", "pcpm-status-after.txt",
    "apsc-status-before.txt", "apsc-status-after.txt",
    "counter-pre-status.txt", "counter-post-status.txt",
    "schedule.json", "control-writes.json", "workload-ready.jsonl",
    "workload-result.jsonl", "workload-validation.json",
    "mmio-phase-screen.json", "mmio-review.json",
    "before-snapshot.json", "after-snapshot.json", "timeline.jsonl",
    "environment-comparison-before.json", "environment-comparison-after.json",
}
PHASE_NAMES = ("four_p_active", "one_p_active", "four_p_released", "four_p_wake")


def require(ok: bool, message: str) -> None:
    if not ok:
        raise EvidenceError(message)


def load_public(packet: Path) -> tuple[dict, dict[str, bytes]]:
    receipt_bytes = (packet / "export-receipt.json").read_bytes()
    receipt = json.loads(receipt_bytes)
    require(receipt.get("schema") == "pcpm-native-mmio-export-v1", "unexpected export schema")
    require(receipt.get("private_manifest_sha256") == PRIVATE_MANIFEST_SHA,
            "private packet manifest pin changed")
    require(set(receipt["files"]) == EXPECTED_FILES, "receipt file set changed")
    require({p.name for p in packet.iterdir()} -
            {"README.md", "MATCHED-COMPARISON.md", "export-receipt.json"} == EXPECTED_FILES,
            "published file set changed")
    data = {}
    for name, entry in receipt["files"].items():
        require(Path(name).name == name and not (packet / name).is_symlink(),
                f"unsafe evidence file {name}")
        require(all(re.fullmatch(r"[0-9a-f]{64}", entry[key]) for key in
                    ("published_sha256", "private_input_sha256")),
                f"invalid hash for {name}")
        published = (packet / name).read_bytes()
        require(sha256(published) == entry["published_sha256"],
                f"published hash mismatch: {name}")
        if name.endswith(".csv.gz"):
            require(entry["transformation"].startswith("gzip level 9"),
                    f"unexpected compression: {name}")
            decoded = gzip.decompress(published)
            require(sha256(decoded) == entry["private_input_sha256"] and
                    len(decoded) == entry["uncompressed_bytes"],
                    f"uncompressed source mismatch: {name}")
        elif entry["transformation"] == "byte-exact":
            decoded = published
            require(sha256(decoded) == entry["private_input_sha256"] and
                    len(decoded) == entry["uncompressed_bytes"],
                    f"byte-exact source mismatch: {name}")
        else:
            require("projection" in entry["transformation"],
                    f"unrecognized transform: {name}")
            decoded = published
        data[name] = decoded
    receipt["public_receipt_sha256"] = sha256(receipt_bytes)
    return receipt, data


def check_apsc(rows: list[dict], before: dict, after: dict, wfi: list[dict]) -> dict:
    require(before["state"] == "ready" and after["abi"] == "2" and
            after["state"] == "complete" and after["mode"] == "records" and
            getint(after, "cntfrq") == 24_000_000, "APSC control/status mismatch")
    require(not wfi, "unexpected WFI seam command records")
    for key in ("interrupted", "wfi_pending_after_drain", "wfi_prepare_after_stop",
                "wfi_prepare_bad_mapping"):
        require(getint(after, key) == 0, f"APSC {key} nonzero")
    streams = Counter()
    sequences: dict[tuple[str, int], list[int]] = {}
    for row in rows:
        kind = row["kind"]
        require(kind in {"idle_enter", "idle_exit", "dvfs"}, f"APSC kind {kind}")
        stream = ("dvfs", getint(row, "cluster")) if kind == "dvfs" else ("idle", getint(row, "cpu"))
        streams[stream] += 1
        sequences.setdefault(stream, []).append(getint(row, "seq"))
    for cpu in range(8):
        for suffix in ("overflow", "missing_commit"):
            require(getint(after, f"idle{cpu}_{suffix}") == 0 and
                    getint(after, f"wfi{cpu}_{suffix}") == 0, f"APSC CPU{cpu} loss")
        count = streams[("idle", cpu)]
        require(count == getint(after, f"idle{cpu}_attempts") ==
                getint(after, f"idle{cpu}_committed") and
                sorted(sequences.get(("idle", cpu), [])) == list(range(count)),
                f"APSC idle{cpu} stream differs")
        require(getint(after, f"wfi{cpu}_attempts") ==
                getint(after, f"wfi{cpu}_committed") == 0,
                f"APSC CPU{cpu} unexpected WFI records")
    for cluster in (0, 1):
        count = streams[("dvfs", cluster)]
        require(count == getint(after, f"dvfs{cluster}_attempts") ==
                getint(after, f"dvfs{cluster}_committed") and
                sorted(sequences.get(("dvfs", cluster), [])) == list(range(count)) and
                getint(after, f"dvfs{cluster}_overflow") ==
                getint(after, f"dvfs{cluster}_missing_commit") == 0,
                f"APSC DVFS{cluster} stream differs")
    return {"idle_commits": {str(cpu): streams[("idle", cpu)] for cpu in range(8)},
            "dvfs_commits": {str(cluster): streams[("dvfs", cluster)] for cluster in (0, 1)}}


def check_counter(pre_status: dict, post_status: dict,
                  pre_rows: list[dict], post_rows: list[dict]) -> None:
    require(pre_status["abi"] == post_status["abi"] == "1", "counter ABI differs")
    require(pre_rows == post_rows[:1792], "counter pre stream changed in post export")
    for phase, source, rows in (("pre", pre_status, pre_rows),
                                ("post", post_status, post_rows[1792:])):
        require(source[f"{phase}_state"] == "complete", f"counter {phase} incomplete")
        for suffix, expected in (("attempted", 1792), ("completed", 1792),
                                 ("metadata_completed", 8), ("error", 0)):
            require(getint(source, f"{phase}_{suffix}") == expected,
                    f"counter {phase} {suffix} differs")
        seen = set()
        for row in rows:
            require(row["phase"] == phase and
                    getint(row, "ack_seq") == getint(row, "request_seq") and
                    getint(row, "call_status") == 0 and
                    getint(row, "flags") == 15 and
                    getint(row, "source_cntfrq") ==
                    getint(row, "target_cntfrq") == 24_000_000,
                    f"counter {phase} failed exchange")
            round_no, target = getint(row, "round"), getint(row, "target_requested")
            require(0 <= round_no < 256 and 1 <= target <= 7 and
                    getint(row, "source_requested") ==
                    getint(row, "source_before") ==
                    getint(row, "source_after") == 0 and
                    getint(row, "target_actual") == target,
                    f"counter {phase} topology/round differs")
            seen.add((round_no, target))
        require(len(seen) == 1792, f"counter {phase} missing/duplicate round")
        for cpu in range(8):
            require(getint(source, f"{phase}_cpu{cpu}_cntfrq") == 24_000_000,
                    f"counter {phase} CPU{cpu} frequency differs")
    for key, value in pre_status.items():
        if key.startswith("pre_"):
            require(post_status[key] == value, f"counter post changed pre field {key}")


def measured_bounds(workload: dict) -> dict[str, list[int]]:
    require(workload["schema"] == 1 and workload["clean"] is True and
            workload["p_cpus"] == [4, 5, 6, 7] and workload["e_cpu"] == 0,
            "workload identity/health differs")
    start = workload["start_ns"]
    offsets = (0, 2_000_000_000, 4_000_000_000, 7_000_000_000, 9_000_000_000)
    transitions = workload["transition_actual_ns"]
    require(len(transitions) == 5 and len(workload["workers"]) == 4,
            "workload phase/worker count differs")
    for actual, offset in zip(transitions, offsets):
        require(start + offset <= actual <= start + offset + 50_000_000,
                "workload transition late/early")
    bounds = {}
    for i, name in enumerate(PHASE_NAMES):
        entries = [transitions[i]]
        exits = [transitions[i + 1]]
        for index, worker in enumerate(workload["workers"]):
            cpu = index + 4
            require(worker["cpu"] == cpu and worker["error"] == 0 and
                    len(worker["phases"]) == 4, f"workload CPU{cpu} differs")
            row = worker["phases"][i]
            require(row["phase"] == i + 1 and
                    row["entered_cpu"] == row["exited_cpu"] == cpu,
                    f"workload CPU{cpu} phase identity/affinity differs")
            target_start, target_end = start + offsets[i], start + offsets[i + 1]
            require(target_start <= row["entered_ns"] <= target_start + GUARD_NS and
                    target_end <= row["exited_ns"] <= target_end + GUARD_NS,
                    f"workload CPU{cpu} phase boundary late/early")
            active = i in (0, 3) or (i == 1 and index == 0)
            require((row["iterations"] > 0) == active and
                    row["iterations"] % 32768 == 0,
                    f"workload CPU{cpu} phase work differs")
            if active:
                require(row["first_cpu"] == row["last_cpu"] == cpu and
                        row["entered_ns"] <= row["first_ns"] <=
                        row["last_ns"] <= row["exited_ns"] and
                        row["first_ns"] <= target_start + GUARD_NS and
                        row["last_ns"] >= target_end - GUARD_NS,
                        f"workload CPU{cpu} phase migration/boundary")
            else:
                require(row["first_ns"] == row["last_ns"] == 0,
                        f"workload CPU{cpu} unexpected inactive work")
            entries.append(row["entered_ns"])
            exits.append(row["exited_ns"])
        low, high = max(entries) + GUARD_NS, min(exits) - GUARD_NS
        require(low < high, f"empty guarded phase {name}")
        bounds[name] = [low, high]
    return bounds


def verify_packet(packet: Path = PACKET) -> dict:
    receipt, data = load_public(packet)
    records_receipt, records_data = load_records_packet(RECORDS)
    require(receipt["prior_records_manifest_sha256"] ==
            records_receipt["private_manifest_sha256"] and
            receipt["identity"] == records_receipt["identity"],
            "records baseline image/manifest differs")
    rows = {name: csv_rows(data[name], name) for name in EXPECTED_CSV}
    for name, expected in EXPECTED_CSV.items():
        require(len(rows[name]) == expected, f"{name}: row count differs")
    pcpm_before = status(data["pcpm-status-before.txt"].decode())
    pcpm = status(data["pcpm-status-after.txt"].decode())
    apsc_before = status(data["apsc-status-before.txt"].decode())
    apsc = status(data["apsc-status-after.txt"].decode())
    counter_pre = status(data["counter-pre-status.txt"].decode())
    counter_post = status(data["counter-post-status.txt"].decode())
    require(pcpm_before["abi"] == "2" and pcpm_before["state"] == "unused" and
            pcpm_before["mode"] == "none" and getint(pcpm_before, "attempted") == 0,
            "PCPM was not unused before MMIO acquisition")
    require(pcpm["abi"] == "2" and pcpm["state"] == "complete" and
            pcpm["mode"] == "mmio", "PCPM MMIO capture incomplete")
    for key, expected in {"error": 0, "requested": 90, "period_ms": 100,
                          "phase_ms": 0, "attempted": 90, "missed_slots": 0,
                          "unattempted_after_error": 0, "trailing_missed": 0,
                          "read_errors": 0, "cpu_errors": 0,
                          "counter_errors": 0, "time_errors": 0,
                          "worker_cpu": 0, "counter_metadata_valid": 1,
                          "counter_metadata_cpu": 0, "counter_metadata_error": 0,
                          "counter_cntfrq": 24_000_000,
                          "start_online_mask": 0xff, "end_online_mask": 0xff,
                          "e_mask": 0xf, "p_mask": 0xf0,
                          "pmgr_phys": 0x23b700000, "pmgr_size": 0x14000,
                          "register_offset": 0x48, "regmap_existing": 1,
                          "regmap_internal_clockless": 1,
                          "regmap_stride": 4, "regmap_val_bytes": 4}.items():
        require(getint(pcpm, key) == expected, f"PCPM {key} differs")
    for cpu in range(8):
        expected_e = cpu < 4
        require(pcpm[f"cpu{cpu}.kind"] == ("E" if expected_e else "P") and
                getint(pcpm, f"cpu{cpu}.midr") ==
                (0x611f0221 if expected_e else 0x611f0231) and
                getint(pcpm, f"cpu{cpu}.mpidr") ==
                (cpu if expected_e else 0x10100 + cpu - 4),
                f"PCPM CPU{cpu} topology differs")
    apsc_counts = check_apsc(rows["apsc-events.csv.gz"], apsc_before, apsc,
                             rows["apsc-wfi-events.csv.gz"])
    check_counter(counter_pre, counter_post, rows["counter-pre-events.csv.gz"],
                  rows["counter-post-events.csv.gz"])
    schedule = json.loads(data["schedule.json"])
    controls = json.loads(data["control-writes.json"])
    workload = json.loads(data["workload-result.jsonl"])
    validation = json.loads(data["workload-validation.json"])
    screen = json.loads(data["mmio-phase-screen.json"])
    review = json.loads(data["mmio-review.json"])
    require(validation == {"errors": [], "returncode": 0} and
            review["errors"] == [] and review["first_boot_machine_screen_passed"] is True,
            "workload/machine review failed")
    require(schedule["workload_start_ns"] == workload["start_ns"] and
            schedule["phase_guard_ns"] == GUARD_NS and
            schedule["pcpm_command"] == controls["pcpm"]["command"] ==
            "mmio 90 100 0\n" and
            schedule["apsc_command"] == controls["apsc"]["command"] ==
            "records 9500\n", "schedule/control identity differs")
    starts = [controls[name]["started_ns"] for name in ("apsc", "pcpm")]
    require(all(controls[name]["error"] is None and
                controls[name]["bytes_written"] == len(controls[name]["command"])
                for name in ("apsc", "pcpm")) and
            max(starts) - min(starts) <= 50_000_000 and
            all(workload["start_ns"] - 400_000_000 <= x <=
                workload["start_ns"] - 100_000_000 for x in starts) and
            controls["apsc"]["returned_ns"] >= schedule["workload_end_ns"] and
            controls["pcpm"]["returned_ns"] >=
            schedule["workload_start_ns"] + 8_000_000_000,
            "control write timing/return differs")
    bounds = measured_bounds(workload)
    require(bounds == screen["measured_phase_interior_bounds_ns"] and
            screen["guard_ns"] == GUARD_NS, "measured phase bounds differ")
    included = {name: [] for name in PHASE_NAMES}
    excluded = []
    raw_words = []
    brackets = []
    for seq, row in enumerate(rows["pcpm-samples.csv.gz"]):
        before, after = getint(row, "t_before_ns"), getint(row, "t_after_ns")
        word = getint(row, "raw")
        require(getint(row, "seq") == getint(row, "slot") == seq and
                getint(row, "skipped_before") == 0 and
                getint(row, "scheduled_ns") ==
                getint(pcpm, "start_ns") + (seq + 1) * 100_000_000 and
                getint(row, "cpu_before") == getint(row, "cpu_after") == 0 and
                getint(row, "counter_flags") == 3 and
                getint(row, "counter_before") <= getint(row, "counter_after") and
                getint(row, "read_attempted") == getint(row, "raw_valid") == 1 and
                getint(row, "read_errno") == 0 and
                getint(row, "scheduled_ns") <= before <= after and
                getint(pcpm, "start_ns") <= before <= after <= getint(pcpm, "end_ns"),
                f"PCPM sample {seq} has timing/read/slot error")
        raw_words.append(word)
        brackets.append(after - before)
        matches = [name for name, (low, high) in bounds.items()
                   if low <= before <= after <= high]
        require(len(matches) <= 1, f"PCPM sample {seq} spans guarded phases")
        if matches:
            included[matches[0]].append(seq)
        else:
            excluded.append(seq)
    require(set(raw_words) == {0x21f0}, "MMIO word was not constant 0x21f0")
    require({name: len(seq) for name, seq in included.items()} ==
            screen["valid_full_bracket_counts"] ==
            {"four_p_active": 14, "one_p_active": 14,
             "four_p_released": 24, "four_p_wake": 14},
            "phase interior counts differ")
    require(all(seq == [row["seq"] for row in screen["included"][name]]
                for name, seq in included.items()) and
            excluded == [row["seq"] for row in screen["excluded"]] and
            all(row["reasons"] == ["outside_measured_phase_interior"]
                for row in screen["excluded"]),
            "phase inclusion/exclusion differs")
    require(screen["first_boot_phase_coverage_passed"] is True and
            screen["first_boot_numeric_pattern"]["meets_one_boot_pattern"] is False and
            all(item["unique_modal_actual_code"] == 15 and
                item["modal_fraction_at_least_80_percent"] is True
                for item in screen["first_boot_numeric_pattern"]["modes"].values()) and
            receipt["screen"]["first_boot_numeric_pattern_passed"] is False,
            "published numeric outcome differs")
    for name, source in (("before", "before-snapshot.json"),
                         ("after", "after-snapshot.json")):
        snapshot = json.loads(data[source])
        require(snapshot["ac_online"] == "1" and snapshot["battery_percent"] == "100" and
                snapshot["brightness"] == "155" and snapshot["online_cpus"] == "0-7" and
                snapshot["cpuidle_driver"] == "apple_idle" and
                snapshot["cpuidle_governor"] == "menu" and
                snapshot["usb"] == [] and
                all(value == "0" for value in snapshot["cpuidle_state1_disabled"].values()),
                f"{name} environment differs")
    require(json.loads(data["environment-comparison-before.json"])["errors"] == [] and
            json.loads(data["environment-comparison-after.json"])["errors"] == [],
            "environment comparison failed")
    timeline = [json.loads(line) for line in data["timeline.jsonl"].decode().splitlines()]
    require(timeline[-1]["action"] == "complete" and
            not any(row["action"] in {"failed", "postcapture_step_failed", "raw_export_failed"}
                    for row in timeline) and
            all("utc" not in row and "pid" not in row for row in timeline),
            "timeline incomplete or unsanitized")
    intervals = complete_p_intervals(rows["apsc-events.csv.gz"],
                                     getint(apsc, "start_tick"), getint(apsc, "stop_tick"))
    released = [rows["pcpm-samples.csv.gz"][seq] for seq in included["four_p_released"]]
    conditional = [getint(row, "seq") for row in released if four_p_witness(row, intervals)]
    require(len(conditional) == 8, "conditional four-P witness count differs")
    records_rows = csv_rows(records_data["pcpm-samples.csv.gz"], "records samples")
    records_apsc = csv_rows(records_data["apsc-events.csv.gz"], "records APSC")
    records_status = status(records_data["apsc-status-after.txt"].decode())
    records_workload = json.loads(records_data["workload-result.jsonl"])
    rlo, rhi = measured_release_window(records_workload)
    records_released = [row for row in records_rows if
                        rlo < getint(row, "t_before_ns") and
                        getint(row, "t_after_ns") < rhi]
    records_intervals = complete_p_intervals(records_apsc,
                                            getint(records_status, "start_tick"),
                                            getint(records_status, "stop_tick"))
    records_conditional = [getint(row, "seq") for row in records_released
                           if four_p_witness(row, records_intervals)]
    require(len(records_released) == len(released) == 24 and
            len(records_conditional) == 21,
            "records versus MMIO guarded comparison changed")
    records_brackets = [getint(row, "t_after_ns") - getint(row, "t_before_ns")
                        for row in records_rows]
    records_before = json.loads(records_data["before-snapshot.json"])
    records_after = json.loads(records_data["after-snapshot.json"])
    mmio_before = json.loads(data["before-snapshot.json"])
    mmio_after = json.loads(data["after-snapshot.json"])
    require(records_before["policies"] == records_after["policies"] ==
            mmio_before["policies"] == mmio_after["policies"] and
            mmio_before["usb"] == mmio_after["usb"] == [],
            "matched CPU policy or MMIO USB state differs")

    def delivered(report: dict) -> dict[str, int]:
        return {name: sum(worker["phases"][i]["iterations"]
                          for worker in report["workers"])
                for i, name in enumerate(PHASE_NAMES)}

    return {
        "result": "public sparse-MMIO packet replayed",
        "receipt_sha256": receipt["public_receipt_sha256"],
        "row_counts": {name: len(value) for name, value in sorted(rows.items())},
        "loss": {"pcpm_missed_slots": 0, "pcpm_read_errors": 0,
                 "apsc_overflow_or_missing_commit": 0, "counter_call_errors": 0},
        "raw_word_counts": {"0x21f0": 90},
        "actual_code_counts": {"15": 90},
        "target_code_counts": {"0": 90},
        "phase_interior_counts": {name: len(seq) for name, seq in included.items()},
        "excluded_edge_rows": len(excluded),
        "first_boot_numeric_pattern_passed": False,
        "conditional_four_p_software_witnesses": {
            "assumed_pairwise_E_ticks": 240,
            "E_verified_for_capture": False,
            "guard_ticks": 24_000,
            "records_boot": len(records_conditional),
            "mmio_boot": len(conditional),
            "denominator_each": 24,
        },
        "apsc_idle_commits": apsc_counts["idle_commits"],
        "median_pcpm_bracket_ns": {
            "records": statistics.median(records_brackets),
            "mmio": statistics.median(brackets),
        },
        "matched_boot_context": {
            "apsc_p_idle_commits": {
                "records": {str(cpu): getint(records_status, f"idle{cpu}_committed")
                            for cpu in range(4, 8)},
                "mmio": {str(cpu): getint(apsc, f"idle{cpu}_committed")
                         for cpu in range(4, 8)},
            },
            "apsc_dvfs_commits": {
                "records": [getint(records_status, f"dvfs{i}_committed")
                            for i in (0, 1)],
                "mmio": [getint(apsc, f"dvfs{i}_committed") for i in (0, 1)],
            },
            "workload_iterations": {
                "records": delivered(records_workload),
                "mmio": delivered(workload),
            },
            "thermal_millidegrees": {
                "records": [records_before["thermal_millidegrees"],
                            records_after["thermal_millidegrees"]],
                "mmio": [mmio_before["thermal_millidegrees"],
                         mmio_after["thermal_millidegrees"]],
            },
            "public_cpu_policy_snapshots_match": True,
            "mmio_usb_snapshots_empty": True,
            "records_usb_state_replayable_from_public_files": False,
            "network_deltas_replayable_from_public_files": False,
        },
        "boundary": "numeric phase screen only; no physical-state, energy, residency, or causal observer-effect claim",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", type=Path, default=PACKET)
    args = parser.parse_args()
    try:
        result = verify_packet(args.packet)
    except (EvidenceError, OSError, KeyError, TypeError, ValueError, gzip.BadGzipFile) as error:
        parser.exit(1, f"MMIO export verification failed: {error}\n")
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
