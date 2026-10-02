#!/usr/bin/env python3
"""Read-only replay of the first public ABI-2 PCPM records-only packet.

This verifies numerical export integrity and a *conditional software-interval*
screen. E=240 ticks is a predeclared but unverified pairwise cross-CPU clock
error assumption, not a measured capture-wide bound. No PCPM MMIO read or
physical-state claim follows from this packet.
"""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path
import re


PACKET = Path(__file__).resolve().parent / "native-evidence" / "records-abi2"
E_ASSUMED_TICKS = 240
G_TICKS = 24_000
GUARD_NS = 300_000_000
EXPECTED_CSV = {
    "pcpm-samples.csv.gz": 90,
    "apsc-events.csv.gz": 6884,
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
    "pcpm-phase-coverage.json", "first-boot-review.json",
    "before-snapshot.json", "after-snapshot.json", "timeline.jsonl",
}
HEX_SHA = re.compile(r"[0-9a-f]{64}\Z")


class EvidenceError(ValueError):
    """A public packet field contradicts the declared acquisition."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise EvidenceError(message)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def integer(value: str | int, label: str) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    require(isinstance(value, str) and bool(re.fullmatch(r"(?:0x[0-9a-fA-F]+|0|-?[1-9][0-9]*)", value)),
            f"{label}: invalid integer")
    return int(value, 16 if value.startswith("0x") else 10)


def status(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in text.splitlines():
        require(line.count("=") == 1, "malformed status line")
        key, value = line.split("=", 1)
        require(key and key not in result, f"duplicate/empty status field {key!r}")
        result[key] = value
    return result


def getint(mapping: dict, key: str) -> int:
    require(key in mapping, f"missing {key}")
    return integer(mapping[key], key)


def csv_rows(data: bytes, name: str) -> list[dict[str, str]]:
    try:
        reader = csv.DictReader(io.StringIO(data.decode("utf-8")), strict=True)
        require(reader.fieldnames is not None and len(reader.fieldnames) == len(set(reader.fieldnames)),
                f"{name}: missing/duplicate header")
        rows = list(reader)
    except (csv.Error, UnicodeError) as error:
        raise EvidenceError(f"{name}: invalid CSV: {error}") from error
    require(all(None not in row and all(value is not None for value in row.values()) for row in rows),
            f"{name}: wrong row width")
    return rows


def load_packet(packet: Path) -> tuple[dict, dict[str, bytes]]:
    receipt_bytes = (packet / "export-receipt.json").read_bytes()
    receipt = json.loads(receipt_bytes)
    require(set(receipt["files"]) == EXPECTED_FILES, "receipt file set differs from first packet")
    require(bool(HEX_SHA.fullmatch(receipt["private_manifest_sha256"])), "invalid private manifest hash")
    data = {}
    for name, entry in receipt["files"].items():
        require(Path(name).name == name, f"unsafe receipt path: {name}")
        for key in ("published_sha256", "private_input_sha256"):
            require(bool(HEX_SHA.fullmatch(entry[key])), f"invalid {key} for {name}")
        raw = (packet / name).read_bytes()
        require(sha256(raw) == entry["published_sha256"], f"published hash mismatch: {name}")
        transformation = entry["transformation"]
        if name.endswith(".csv.gz"):
            require(transformation.startswith("gzip level 9"), f"unexpected compression: {name}")
            try:
                decoded = gzip.decompress(raw)
            except OSError as error:
                raise EvidenceError(f"invalid gzip: {name}") from error
            require(sha256(decoded) == entry["private_input_sha256"],
                    f"uncompressed source hash mismatch: {name}")
        else:
            decoded = raw
            if transformation == "byte-exact":
                require(sha256(raw) == entry["private_input_sha256"],
                        f"byte-exact source hash mismatch: {name}")
            else:
                require("projection" in transformation, f"unrecognized transform: {name}")
        if transformation == "byte-exact" or name.endswith(".csv.gz"):
            require(len(decoded) == entry["uncompressed_bytes"],
                    f"source byte length mismatch: {name}")
        data[name] = decoded
    receipt["public_receipt_sha256"] = sha256(receipt_bytes)
    return receipt, data


def complete_p_intervals(rows: list[dict], start_tick: int, stop_tick: int) -> dict[int, list[tuple[dict, dict]]]:
    """Enforce one non-reentrant idle stream per P CPU; omit capture-edge tails."""
    result: dict[int, list[tuple[dict, dict]]] = {}
    for cpu in range(4, 8):
        events = sorted((row for row in rows if getint(row, "cpu") == cpu and
                         row["kind"].startswith("idle")), key=lambda row: getint(row, "seq"))
        open_entry = None
        pairs = []
        for event in events:
            require(getint(event, "cluster") == 1, f"CPU {cpu}: wrong cluster")
            require(getint(event, "ret") == 0 and getint(event, "flags") == 0,
                    f"CPU {cpu}: failed/flagged idle record")
            require(getint(event, "t0") <= getint(event, "t1"), f"CPU {cpu}: reversed event")
            if event["kind"] == "idle_enter":
                require(open_entry is None, f"CPU {cpu}: nested idle_enter")
                open_entry = event
            elif event["kind"] == "idle_exit":
                require(open_entry is not None, f"CPU {cpu}: unmatched idle_exit")
                require(event["token"] == open_entry["token"], f"CPU {cpu}: changed token")
                require(getint(open_entry, "t1") <= getint(event, "t0"),
                        f"CPU {cpu}: reversed interval")
                if start_tick < getint(open_entry, "t0") and getint(event, "t1") < stop_tick:
                    pairs.append((open_entry, event))
                open_entry = None
            else:
                raise EvidenceError(f"CPU {cpu}: unsupported idle kind")
        result[cpu] = pairs
    return result


def strict_contains(entry: dict, exit_event: dict, p0: int, p1: int,
                    e_ticks: int = E_ASSUMED_TICKS, guard_ticks: int = G_TICKS) -> bool:
    """Strict JOINT-CAPTURE inequalities; E is an assumption, never a proof."""
    require(0 <= p0 <= p1 and e_ticks >= 0 and guard_ticks >= 0, "invalid bracket/model")
    return (getint(entry, "t1") + e_ticks + guard_ticks < p0 and
            p1 + e_ticks + guard_ticks < getint(exit_event, "t0"))


def four_p_witness(sample: dict, intervals: dict[int, list[tuple[dict, dict]]],
                   e_ticks: int = E_ASSUMED_TICKS, guard_ticks: int = G_TICKS) -> dict | None:
    p0, p1 = getint(sample, "counter_before"), getint(sample, "counter_after")
    peers = {}
    for cpu in range(4, 8):
        found = [(entry, exit_event) for entry, exit_event in intervals[cpu]
                 if strict_contains(entry, exit_event, p0, p1, e_ticks, guard_ticks)]
        require(len(found) <= 1, f"CPU {cpu}: ambiguous matching intervals")
        if not found:
            return None
        entry, exit_event = found[0]
        peers[str(cpu)] = {
            "token": getint(entry, "token"),
            "entry_seq": getint(entry, "seq"),
            "exit_seq": getint(exit_event, "seq"),
            "entry_t1": getint(entry, "t1"),
            "exit_t0": getint(exit_event, "t0"),
            "entry_margin_ticks": p0 - getint(entry, "t1") - e_ticks - guard_ticks,
            "exit_margin_ticks": getint(exit_event, "t0") - p1 - e_ticks - guard_ticks,
        }
    return peers


def measured_release_window(workload: dict, guard_ns: int = GUARD_NS) -> tuple[int, int]:
    workers = workload["workers"]
    require({getint(worker, "cpu") for worker in workers} == {4, 5, 6, 7} and len(workers) == 4,
            "workload is not four distinct P-pinned workers")
    phases = []
    for worker in workers:
        cpu = getint(worker, "cpu")
        require(getint(worker, "error") == 0, f"CPU {cpu}: workload error")
        by_number = {getint(phase, "phase"): phase for phase in worker["phases"]}
        require(set(by_number) == {1, 2, 3, 4}, f"CPU {cpu}: missing workload phase")
        for number, phase in by_number.items():
            require(getint(phase, "entered_cpu") == cpu and getint(phase, "exited_cpu") == cpu,
                    f"CPU {cpu} phase {number}: affinity violation")
            expected_active = number in {1, 4} or (number == 2 and cpu == 4)
            require((getint(phase, "iterations") > 0) == expected_active,
                    f"CPU {cpu} phase {number}: workload did not match plan")
        phases.append(by_number[3])
    start = max(getint(phase, "entered_ns") for phase in phases) + guard_ns
    end = min(getint(phase, "exited_ns") for phase in phases) - guard_ns
    require(start < end, "no measured guarded release interval")
    return start, end


def verify_packet(packet: Path = PACKET) -> dict:
    receipt, data = load_packet(packet)
    rows = {name: csv_rows(data[name], name) for name in EXPECTED_CSV}
    for name, count in EXPECTED_CSV.items():
        require(len(rows[name]) == count, f"{name}: unexpected row count")

    pcpm_before = status(data["pcpm-status-before.txt"].decode())
    pcpm = status(data["pcpm-status-after.txt"].decode())
    apsc_before = status(data["apsc-status-before.txt"].decode())
    apsc = status(data["apsc-status-after.txt"].decode())
    counter_pre = status(data["counter-pre-status.txt"].decode())
    counter_post = status(data["counter-post-status.txt"].decode())
    require(pcpm_before["state"] == "unused" and getint(pcpm_before, "attempted") == 0,
            "PCPM was not unused before acquisition")
    require(pcpm["abi"] == "2" and pcpm["state"] == "complete" and pcpm["mode"] == "records",
            "PCPM did not complete ABI-2 records-only mode")
    for key, expected in {"error": 0, "requested": 90, "period_ms": 100, "phase_ms": 0,
                          "attempted": 90, "missed_slots": 0, "unattempted_after_error": 0,
                          "trailing_missed": 0, "read_errors": 0, "cpu_errors": 0,
                          "counter_errors": 0, "time_errors": 0, "worker_cpu": 0,
                          "counter_metadata_valid": 1, "counter_metadata_error": 0,
                          "counter_cntfrq": 24_000_000, "counter_phys_read_workaround": 0,
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
                getint(pcpm, f"cpu{cpu}.midr") == (0x611f0221 if expected_e else 0x611f0231) and
                getint(pcpm, f"cpu{cpu}.mpidr") == (cpu if expected_e else 0x10100 + cpu - 4),
                f"PCPM CPU {cpu} T8103 topology differs")
    require(apsc_before["state"] == "ready" and apsc["abi"] == "2" and
            apsc["state"] == "complete" and apsc["mode"] == "records" and
            getint(apsc, "cntfrq") == 24_000_000, "APSC mode/clock mismatch")
    for key in ("interrupted", "wfi_pending_after_drain", "wfi_prepare_after_stop",
                "wfi_prepare_bad_mapping"):
        require(getint(apsc, key) == 0, f"APSC {key} nonzero")
    for cpu in range(8):
        for suffix in ("overflow", "missing_commit"):
            require(getint(apsc, f"idle{cpu}_{suffix}") == 0, f"idle{cpu} {suffix} nonzero")
            require(getint(apsc, f"wfi{cpu}_{suffix}") == 0, f"wfi{cpu} {suffix} nonzero")
        require(getint(apsc, f"idle{cpu}_attempts") == getint(apsc, f"idle{cpu}_committed"),
                f"idle{cpu} loss")
        require(getint(apsc, f"wfi{cpu}_attempts") == getint(apsc, f"wfi{cpu}_committed") == 0,
                f"unexpected WFI seam records on CPU {cpu}")
    for cluster in (0, 1):
        require(getint(apsc, f"dvfs{cluster}_attempts") ==
                getint(apsc, f"dvfs{cluster}_committed"), f"dvfs{cluster} loss")
        for suffix in ("overflow", "missing_commit"):
            require(getint(apsc, f"dvfs{cluster}_{suffix}") == 0,
                    f"dvfs{cluster} {suffix} nonzero")
    require(not rows["apsc-wfi-events.csv.gz"], "unexpected WFI seam rows")
    apsc_rows = rows["apsc-events.csv.gz"]
    streams = Counter()
    sequences: dict[tuple[str, int], list[int]] = {}
    for row in apsc_rows:
        kind = row["kind"]
        require(kind in {"idle_enter", "idle_exit", "dvfs"}, f"unsupported APSC kind {kind}")
        stream = ("dvfs", getint(row, "cluster")) if kind == "dvfs" else ("idle", getint(row, "cpu"))
        streams[stream] += 1
        sequences.setdefault(stream, []).append(getint(row, "seq"))
    for cpu in range(8):
        stream = ("idle", cpu)
        require(streams[stream] == getint(apsc, f"idle{cpu}_committed") and
                sorted(sequences.get(stream, [])) == list(range(streams[stream])),
                f"idle{cpu} count/sequence mismatch")
    for cluster in (0, 1):
        stream = ("dvfs", cluster)
        require(streams[stream] == getint(apsc, f"dvfs{cluster}_committed") and
                sorted(sequences.get(stream, [])) == list(range(streams[stream])),
                f"dvfs{cluster} count/sequence mismatch")

    for phase, status_map, expected_rows in (("pre", counter_pre, 1792),
                                             ("post", counter_post, 1792)):
        require(status_map["abi"] == "1" and status_map[f"{phase}_state"] == "complete",
                f"counter {phase} incomplete")
        for key, expected in {f"{phase}_attempted": expected_rows,
                              f"{phase}_completed": expected_rows, f"{phase}_error": 0,
                              f"{phase}_metadata_completed": 8}.items():
            require(getint(status_map, key) == expected, f"counter {key} differs")
        for cpu in range(8):
            require(getint(status_map, f"{phase}_cpu{cpu}_cntfrq") == 24_000_000,
                    f"counter {phase} CPU {cpu} frequency differs")
    pre_rows = rows["counter-pre-events.csv.gz"]
    post_export = rows["counter-post-events.csv.gz"]
    require(pre_rows == post_export[:1792], "counter pre rows changed in post export")
    for phase, phase_rows in (("pre", pre_rows), ("post", post_export[1792:])):
        require(len(phase_rows) == 1792 and all(row["phase"] == phase for row in phase_rows),
                f"counter {phase} rows incomplete")
        combinations = set()
        for row in phase_rows:
            require(getint(row, "ack_seq") == getint(row, "request_seq") and
                    getint(row, "call_status") == 0 and getint(row, "flags") == 15 and
                    getint(row, "source_cntfrq") == getint(row, "target_cntfrq") == 24_000_000,
                    f"counter {phase} exchange failed")
            round_no, target = getint(row, "round"), getint(row, "target_requested")
            require(0 <= round_no < 256 and 1 <= target <= 7 and
                    getint(row, "source_requested") == getint(row, "source_before") ==
                    getint(row, "source_after") == 0 and
                    getint(row, "target_actual") == target,
                    f"counter {phase} exchange topology/round differs")
            combinations.add((round_no, target))
        require(len(combinations) == 1792, f"counter {phase} duplicate/missing round-target pairs")

    samples = rows["pcpm-samples.csv.gz"]
    for seq, row in enumerate(samples):
        require(getint(row, "seq") == getint(row, "slot") == seq and
                getint(row, "skipped_before") == 0, f"PCPM sample {seq} sequence/slot loss")
        require(getint(row, "cpu_before") == getint(row, "cpu_after") == 0 and
                getint(row, "counter_flags") == 3 and
                getint(row, "counter_before") <= getint(row, "counter_after") and
                getint(row, "t_before_ns") <= getint(row, "t_after_ns"),
                f"PCPM sample {seq} bracket invalid")
        require(getint(row, "read_attempted") == getint(row, "raw_valid") ==
                getint(row, "read_errno") == 0 and row["raw"] == "",
                f"PCPM sample {seq}: records-only read violation")
    require(getint(samples[0], "t_before_ns") >= getint(pcpm, "start_ns") and
            getint(samples[-1], "t_after_ns") <= getint(pcpm, "end_ns"),
            "PCPM samples outside recorded acquisition")

    schedule = json.loads(data["schedule.json"])
    controls = json.loads(data["control-writes.json"])
    workload = json.loads(data["workload-result.jsonl"])
    validation = json.loads(data["workload-validation.json"])
    coverage = json.loads(data["pcpm-phase-coverage.json"])
    before = json.loads(data["before-snapshot.json"])
    after = json.loads(data["after-snapshot.json"])
    for snapshot in (before, after):
        require(snapshot["ac_online"] == "1" and snapshot["brightness"] == "155" and
                snapshot["online_cpus"] == "0-7" and
                snapshot["cpuidle_driver"] == "apple_idle" and
                snapshot["cpuidle_governor"] == "menu",
                "power/display/CPU environment changed or unsupported")
    require(schedule["pcpm_command"] == controls["pcpm"]["command"] == "records 90 100 0\n" and
            schedule["apsc_command"] == controls["apsc"]["command"] == "records 9500\n",
            "control commands differ from schedule")
    require(controls["pcpm"]["error"] is None and controls["apsc"]["error"] is None and
            validation == {"errors": [], "returncode": 0}, "control/workload error")
    require(getint(schedule, "phase_guard_ns") == GUARD_NS and
            getint(coverage, "guard_ns") == GUARD_NS, "phase guard changed")
    release_start, release_end = measured_release_window(workload)
    released = [row for row in samples if release_start < getint(row, "t_before_ns") and
                getint(row, "t_after_ns") < release_end]
    require(len(released) == 24, "measured release phase did not have 24 guarded brackets")
    require(getint(coverage["full_bracket_interior_row_count"], "four_p_released") == 24,
            "published phase coverage disagrees")

    intervals = complete_p_intervals(apsc_rows, getint(apsc, "start_tick"),
                                     getint(apsc, "stop_tick"))
    conditional = {}
    for row in released:
        require(getint(row, "counter_flags") == 3, "released sample has no valid counter bracket")
        witness = four_p_witness(row, intervals)
        if witness is not None:
            conditional[getint(row, "seq")] = witness
    require(len(conditional) == 21 and 58 in conditional,
            "conditional 21/24 or sequence-58 witness did not replay")
    seq58 = next(row for row in released if getint(row, "seq") == 58)
    return {
        "result": "public records-only packet replayed",
        "receipt_sha256": receipt["public_receipt_sha256"],
        "row_counts": {name: len(value) for name, value in sorted(rows.items())},
        "loss": {"pcpm_missed_slots": 0, "pcpm_read_errors": 0,
                 "apsc_overflow_or_missing_commit": 0, "counter_call_errors": 0},
        "measured_four_p_release": {
            "guarded_start_ns": release_start,
            "guarded_end_ns": release_end,
            "guarded_pcpm_brackets": len(released),
            "conditional_four_p_software_interval_brackets": len(conditional),
            "excluded_seq": sorted(getint(row, "seq") for row in released
                                   if getint(row, "seq") not in conditional),
        },
        "sequence_58": {"counter_before": getint(seq58, "counter_before"),
                        "counter_after": getint(seq58, "counter_after"),
                        "conditional_p_cpu_witnesses": conditional[58]},
        "model_and_boundary": {
            "assumed_pairwise_cross_cpu_error_ticks": E_ASSUMED_TICKS,
            "pairwise_error_verified_for_capture": False,
            "software_boundary_guard_ticks": G_TICKS,
            "pcpm_register_reads": 0,
            "physical_idle_or_power_claim": False,
            "strict_final_wfi_command_claim": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", type=Path, default=PACKET,
                        help="published records-abi2 packet directory")
    args = parser.parse_args()
    try:
        result = verify_packet(args.packet)
    except (EvidenceError, OSError, KeyError, TypeError, ValueError) as error:
        parser.exit(1, f"records export verification failed: {error}\n")
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
