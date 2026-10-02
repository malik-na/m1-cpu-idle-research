#!/usr/bin/env python3
"""Publish a reviewed numerical subset of one private ABI 2 WFI packet.

This does not acquire data or qualify cross-CPU clock error. The private
acquisition packet remains the authority for boot provenance, full logs and
the files deliberately withheld here.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
import gzip
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import stat
import struct
import tempfile
from datetime import datetime
import zlib

import analyze_wfi


ROOT = Path(__file__).resolve().parents[1]
COUNTER_DECODER = ROOT / "linux-counter-qualification" / "analyze.py"
spec = importlib.util.spec_from_file_location("counter_decoder_for_wfi_publication", COUNTER_DECODER)
counter_decoder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(counter_decoder)


@dataclass(frozen=True)
class Identity:
    release: str
    config_sha256: str
    gnu_build_id: str
    selected_entry: str


WFI_IDENTITY = Identity(
    release="7.1.12-ARCH-apsc-20261002-wfi",
    config_sha256="f86b80f4dcef277be874f476293d8b8055053072f7209625586b60e2227f905d",
    gnu_build_id="11e80be6d8b358eee9aa847a0f814aff02b66c43",
    selected_entry="Aurora-APSC-research-wfi-seam",
)
WORKLOAD_SHA256 = "82f4ce1145c8135c8b28246a9681d2316083cd1bb1a936a736b8a6cd03102d2b"
ALL_MODES = ("baseline", "records", "mmio", "wfi_clock", "wfi_mmio")
NUMERIC_FILES = (
    "events.csv", "status.txt", "wfi-events.csv",
    "counter-pre-events.csv", "counter-pre-status.txt",
    "counter-events.csv", "counter-status.txt",
    "workload-cpu1.csv", "workload-cpu5.csv",
)
REQUIRED_PRIVATE_FILES = set(NUMERIC_FILES) | {
    "acquisition-record.json",
    "counter-pre-analysis.stdout", "counter-analysis.stdout",
    "apsc-ready.txt", "boot-kernel-notes.bin", "boot-config.gz",
    "boot.config", "bootctl.stdout", "boot-id.txt", "boot-fdt.bin",
    "boot-cmdline.txt", "before-snapshot.json", "after-snapshot.json",
    "collector-source.py",
    "counter-ready.txt", "virtualization.stdout",
}
FILE_LINE = re.compile(r"([0-9a-f]{64})  ([A-Za-z0-9][A-Za-z0-9._-]*)\Z")
PRIVATE_TEXT = re.compile(
    rb"/home/|/root/|/Users/|root=UUID=|machine-id|serial_number|password|passwd|"
    rb"BEGIN [A-Z ]*PRIVATE KEY|\b[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}\b|"
    rb"\b(?:[0-9a-f]{2}:){5}[0-9a-f]{2}\b", re.I)
SYSFS_PREFIX = "/sys/"
POLICY_PATH = re.compile(r"/sys/devices/system/cpu/cpufreq/policy(0|4)/(related_cpus|affected_cpus|scaling_driver|scaling_governor|scaling_min_freq|scaling_max_freq|scaling_cur_freq)\Z")
DEEP_IDLE_PATH = re.compile(r"/sys/devices/system/cpu/cpu([0-7])/cpuidle/state1/disable\Z")
THERMAL_PATH = re.compile(r"/sys/class/thermal/thermal_zone([0-9]+)/temp\Z")
FIXED_SNAPSHOT_FIELDS = {
    "/sys/devices/system/cpu/online": "cpu.online",
    "/sys/devices/system/cpu/cpuidle/current_driver": "cpu.cpuidle_driver",
    "/sys/devices/system/cpu/cpuidle/current_governor_ro": "cpu.cpuidle_governor",
    "/sys/class/power_supply/macsmc-ac/online": "power.ac_online",
    "/sys/class/power_supply/macsmc-battery/status": "power.battery_status",
    "/sys/class/power_supply/macsmc-battery/capacity": "power.battery_capacity_percent",
    "/sys/class/power_supply/macsmc-battery/current_now": "power.battery_current_microamp",
    "/sys/class/power_supply/macsmc-battery/voltage_now": "power.battery_voltage_microvolt",
    "/sys/class/backlight/apple-panel-bl/brightness": "backlight.brightness",
    "/sys/class/backlight/apple-panel-bl/actual_brightness": "backlight.actual_brightness",
    "/sys/class/backlight/apple-panel-bl/max_brightness": "backlight.max_brightness",
}
POLICY_FIELDS = (
    "related_cpus", "affected_cpus", "scaling_driver", "scaling_governor",
    "scaling_min_freq", "scaling_max_freq", "scaling_cur_freq",
)
CHRONOLOGY_ACTION_FIELDS = {
    "begin": ("mode", "observer_abi", "duration_ms", "release", "workload_sha256"),
    "counter_pre_begin": (), "counter_pre_end": (),
    "settling_begin": ("seconds",), "settling_end": (),
    "window_begin": (), "window_end": (), "observer_drained": (),
    "workload_complete": ("cpu", "exit_status"),
    "counter_post_begin": (), "counter_post_end": (),
    "complete": ("clock_bound_not_exported",),
}


class PublicationError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PublicationError(message)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def packet_manifest(packet: Path, mode: str) -> tuple[dict[str, str], str]:
    require(packet.is_dir() and not packet.is_symlink(), "packet must be a private directory")
    require(stat.S_IMODE(packet.stat().st_mode) == 0o700, "packet mode must be 0700")
    manifest_path = packet / "SHA256SUMS"
    require(manifest_path.is_file() and not manifest_path.is_symlink(), "missing regular SHA256SUMS")
    manifest_bytes = manifest_path.read_bytes()
    try:
        lines = manifest_bytes.decode("ascii").splitlines()
    except UnicodeError as error:
        raise PublicationError("non-ASCII SHA256SUMS") from error
    require(bool(lines) and manifest_bytes.endswith(b"\n"), "empty or unterminated SHA256SUMS")
    entries = {}
    for line in lines:
        match = FILE_LINE.fullmatch(line)
        require(match is not None, "malformed SHA256SUMS entry")
        expected, name = match.groups()
        require(name not in (".", "..", "SHA256SUMS") and name not in entries,
                "duplicate or invalid SHA256SUMS name")
        path = packet / name
        require(path.is_file() and not path.is_symlink() and stat.S_ISREG(path.stat().st_mode),
                "manifest names a missing or non-regular file")
        require(file_sha256(path) == expected, f"SHA256SUMS mismatch for {name}")
        entries[name] = expected
    actual = {path.name for path in packet.iterdir() if path.name != "SHA256SUMS"}
    require(set(entries) == actual, "packet has unaccounted files")
    required = REQUIRED_PRIVATE_FILES | ({"observer-analysis.stdout"} if mode != "baseline" else set())
    require(required <= set(entries), "packet lacks required acquisition files")
    if mode == "baseline":
        require(not ({"observer-analysis.stdout", "observer-analysis.stderr"} & set(entries)),
                "unarmed baseline contains unexpected observer analysis")
    return entries, sha256(manifest_bytes)


def values(data: bytes, label: str) -> dict[str, str]:
    try:
        lines = data.decode("ascii").splitlines()
    except UnicodeError as error:
        raise PublicationError(f"non-ASCII {label}") from error
    rows = [line.split("=", 1) for line in lines]
    require(bool(rows) and all(len(row) == 2 and row[0] and row[1] for row in rows),
            f"invalid {label}")
    result = dict(rows)
    require(len(result) == len(rows), f"duplicate {label} key")
    return result


def build_ids(data: bytes) -> list[str]:
    offset, identifiers = 0, []
    while offset < len(data):
        require(offset + 12 <= len(data), "truncated kernel note header")
        namesz, valuesz, kind = struct.unpack_from("<III", data, offset)
        offset += 12
        name_end = offset + ((namesz + 3) & ~3)
        value_end = name_end + ((valuesz + 3) & ~3)
        require(value_end <= len(data), "truncated kernel note payload")
        name = data[offset:offset + namesz]
        value = data[name_end:name_end + valuesz]
        if name == b"GNU\0" and kind == 3:
            identifiers.append(value.hex())
        offset = value_end
    return identifiers


def check_workload(data: bytes, cpu: int) -> list[dict]:
    try:
        rows = list(csv.DictReader(io.StringIO(data.decode("ascii"), newline=""), restval=None))
    except UnicodeError as error:
        raise PublicationError("non-ASCII workload CSV") from error
    fields = ["cpu", "pulse", "iterations", "start_monotonic_ns", "end_monotonic_ns", "checksum"]
    require(len(rows) == 44 and list(rows[0]) == fields, "incomplete workload CSV")
    previous_end = 0
    for pulse, row in enumerate(rows):
        require(None not in row and all(value is not None and value.isdecimal() for value in row.values()),
                "non-numeric workload CSV")
        begin, end = int(row["start_monotonic_ns"]), int(row["end_monotonic_ns"])
        require((int(row["cpu"]), int(row["pulse"]), int(row["iterations"])) ==
                (cpu, pulse, 1048576) and previous_end <= begin <= end,
                "invalid workload row")
        require(0 <= int(row["checksum"]) < 2**64, "invalid workload checksum")
        previous_end = end
    return rows


def project_chronology(records: list[dict], mode: str, identity: Identity) -> list[dict]:
    projected = []
    previous_tick = -1
    for row in records:
        tick, utc = row.get("monotonic_ns"), row.get("utc")
        require(isinstance(tick, int) and not isinstance(tick, bool) and tick >= previous_tick,
                "acquisition chronology tick missing or reversed")
        try:
            parsed_utc = datetime.fromisoformat(utc) if isinstance(utc, str) else None
        except ValueError:
            parsed_utc = None
        require(parsed_utc is not None and parsed_utc.tzinfo is not None,
                "acquisition chronology UTC missing or invalid")
        previous_tick = tick
        action = row.get("action")
        require(isinstance(action, str), "invalid acquisition action")
        fields = CHRONOLOGY_ACTION_FIELDS.get(action)
        if fields is None:
            continue
        require(all(field in row for field in fields),
                f"missing public chronology field for {action}")
        selected = {"action": action, "utc": utc, "monotonic_ns": tick}
        selected.update({field: row[field] for field in fields})
        if action == "begin":
            require(selected["mode"] == mode
                    and type(selected["observer_abi"]) is int and selected["observer_abi"] == 2
                    and type(selected["duration_ms"]) is int and selected["duration_ms"] == 2000
                    and selected["release"] == identity.release
                    and selected["workload_sha256"] == WORKLOAD_SHA256,
                    "invalid public begin chronology values")
        elif action == "settling_begin":
            require(type(selected["seconds"]) is int and selected["seconds"] == 5,
                    "invalid settling chronology value")
        elif action == "workload_complete":
            require(type(selected["cpu"]) is int and selected["cpu"] in (1, 5)
                    and type(selected["exit_status"]) is int and selected["exit_status"] == 0,
                    "invalid workload chronology values")
            require(set(row) == set(selected), "unexpected workload chronology field")
        elif action == "complete":
            require(selected["clock_bound_not_exported"] is True,
                    "invalid completion chronology value")
        projected.append(selected)
    return projected


def snapshot_label(path: str) -> str | None:
    if path in FIXED_SNAPSHOT_FIELDS:
        return FIXED_SNAPSHOT_FIELDS[path]
    match = POLICY_PATH.fullmatch(path)
    if match:
        return f"policy{match[1]}.{match[2]}"
    match = DEEP_IDLE_PATH.fullmatch(path)
    if match:
        return f"cpu{match[1]}.deep_idle_disable"
    match = THERMAL_PATH.fullmatch(path)
    if match:
        return f"thermal_zone{match[1]}.millidegree_celsius"
    return None


def safe_snapshot_value(label: str, raw: str) -> int | str:
    value = raw.strip()
    if label == "cpu.online":
        require(value == "0-7", "CPU online set changed")
        return value
    if label == "cpu.cpuidle_driver":
        require(value == "apple_idle", "cpuidle driver changed")
        return value
    if label == "cpu.cpuidle_governor":
        require(value == "menu", "cpuidle governor changed")
        return value
    if label.endswith((".related_cpus", ".affected_cpus")):
        require(re.fullmatch(r"[0-7](?: [0-7])*", value) is not None,
                "invalid policy CPU set")
        return value
    if label.endswith((".scaling_driver", ".scaling_governor")):
        expected = "apple-cpufreq" if label.endswith(".scaling_driver") else "schedutil"
        require(value == expected, "policy driver or governor differs")
        return value
    if label == "power.battery_status":
        require(value in {"Charging", "Discharging", "Full", "Not charging", "Unknown"},
                "unknown battery status")
        return value
    require(re.fullmatch(r"-?[0-9]+", value) is not None, f"non-numeric snapshot field: {label}")
    number = int(value)
    if label.startswith("cpu") and label.endswith("deep_idle_disable"):
        require(number == 0, "deep idle state disabled")
    if label == "power.ac_online":
        require(number in (0, 1), "invalid AC online value")
    if label == "power.battery_capacity_percent":
        require(0 <= number <= 100, "invalid battery capacity")
    if label.startswith("backlight."):
        require(number >= 0, "negative brightness")
    return number


def project_snapshot(packet: Path, name: str) -> tuple[list[dict], dict[str, int | str]]:
    raw = json.loads((packet / name).read_text())
    require(isinstance(raw, list) and raw, "empty or invalid sysfs snapshot")
    projected, by_field = [], {}
    previous_tick = -1
    for row in raw:
        require(isinstance(row, dict) and isinstance(row.get("path"), str),
                "malformed sysfs snapshot row")
        label = snapshot_label(row["path"])
        if label is None:
            continue
        tick = row.get("observed_monotonic_ns")
        require(isinstance(tick, int) and not isinstance(tick, bool) and tick >= previous_tick,
                "snapshot observation tick missing or reversed")
        require(label not in by_field and isinstance(row.get("raw_text"), str),
                "duplicate or unreadable required sysfs field")
        value = safe_snapshot_value(label, row["raw_text"])
        by_field[label] = value
        projected.append({"field": label, "observed_monotonic_ns": tick, "value": value})
        previous_tick = tick
    required = set(FIXED_SNAPSHOT_FIELDS.values())
    required.update(f"cpu{cpu}.deep_idle_disable" for cpu in range(8))
    required.update(f"policy{cpu}.{field}" for cpu in (0, 4) for field in POLICY_FIELDS)
    required.add("thermal_zone0.millidegree_celsius")
    require(required <= set(by_field), "missing required sysfs condition")
    require(by_field["policy0.related_cpus"] == "0 1 2 3"
            and by_field["policy0.affected_cpus"] == "0 1 2 3"
            and by_field["policy4.related_cpus"] == "4 5 6 7"
            and by_field["policy4.affected_cpus"] == "4 5 6 7",
            "policy topology differs")
    return projected, by_field


def check_conditions(before: dict, after: dict) -> None:
    require(before["power.ac_online"] == after["power.ac_online"] == 1,
            "connected-charger baseline is absent at a snapshot endpoint")
    require(before["backlight.brightness"] == after["backlight.brightness"] == 155,
            "brightness-155 baseline is absent at a snapshot endpoint")
    stable = {"cpu.online", "cpu.cpuidle_driver", "cpu.cpuidle_governor",
              "power.ac_online", "power.battery_status", "backlight.brightness"}
    stable.update(f"cpu{cpu}.deep_idle_disable" for cpu in range(8))
    stable.update(f"policy{cpu}.{field}" for cpu in (0, 4) for field in POLICY_FIELDS
                  if field != "scaling_cur_freq")
    require(all(before[field] == after[field] for field in stable),
            "power, brightness or CPU policy endpoints differ")


def check_acquisition(packet: Path, mode: str, identity: Identity) -> tuple[list[dict], int, dict[str, list[int]]]:
    records = json.loads((packet / "acquisition-record.json").read_text())
    require(isinstance(records, list) and len(records) >= 13, "invalid acquisition record")
    require(records[0].get("action") == "begin" and records[-1].get("action") == "complete",
            "acquisition did not complete")
    require(all(isinstance(row, dict) and row.get("action") != "failed" for row in records),
            "failed acquisition record")
    ordered = ["begin", "counter_pre_begin", "counter_pre_end", "settling_begin",
               "settling_end", "window_begin", "window_end", "observer_drained",
               "counter_post_begin", "counter_post_end", "complete"]
    positions = []
    for action in ordered:
        matches = [index for index, row in enumerate(records) if row.get("action") == action]
        require(len(matches) == 1, f"missing or repeated acquisition action: {action}")
        positions.append(matches[0])
    require(positions == sorted(positions), "acquisition action order differs")
    window_begin = records[positions[5]]["monotonic_ns"]
    window_end = records[positions[6]]["monotonic_ns"]
    elapsed_ns = window_end - window_begin
    require(1_500_000_000 <= elapsed_ns <= 3_000_000_000,
            "actual capture window differs materially from requested 2,000 ms")
    workers = [row for row in records if row.get("action") == "workload_complete"]
    require({row.get("cpu") for row in workers} == {1, 5}
            and len(workers) == 2 and all(row.get("exit_status") == 0 for row in workers),
            "workload did not complete on both CPUs")
    chronology = project_chronology(records, mode, identity)
    begin = records[0]
    require(begin.get("mode") == mode and begin.get("observer_abi") == 2
            and begin.get("duration_ms") == 2000
            and begin.get("release") == identity.release
            and begin.get("expected_release") == identity.release
            and begin.get("expected_config_sha256") == identity.config_sha256
            and begin.get("expected_build_id") == identity.gnu_build_id
            and begin.get("expected_entry") == identity.selected_entry
            and begin.get("workload_sha256") == WORKLOAD_SHA256,
            "acquisition boot identity or mode differs")
    require(begin.get("collector_sha256") == file_sha256(packet / "collector-source.py"),
            "acquisition-time collector source hash differs from saved source")
    require(next(row for row in records if row.get("action") == "settling_begin").get("seconds") == 5,
            "settling interval differs")
    require(records[-1].get("native_packet_requires_review") is True
            and records[-1].get("clock_bound_not_exported") is True,
            "acquisition review boundary missing")
    ready = values((packet / "apsc-ready.txt").read_bytes(), "observer ready status")
    require(ready.get("abi") == "2" and ready.get("state") == "ready"
            and ready.get("cluster0_cpus") == "0xf" and ready.get("cluster1_cpus") == "0xf0"
            and ready.get("cluster0_cmd_phys") == "0x210e20020"
            and ready.get("cluster1_cmd_phys") == "0x211e20020",
            "observer topology or command mapping differs")
    counter_ready = values((packet / "counter-ready.txt").read_bytes(), "counter ready status")
    require(counter_ready.get("abi") == "1" and counter_ready.get("pre_state") == "unused"
            and counter_ready.get("post_state") == "unused"
            and counter_ready.get("cluster0_cpus") == "0xf"
            and counter_ready.get("cluster1_cpus") == "0xf0",
            "counter helper was not ready before capture")
    require(build_ids((packet / "boot-kernel-notes.bin").read_bytes()) == [identity.gnu_build_id],
            "boot GNU Build-ID differs")
    config = (packet / "boot.config").read_bytes()
    require(sha256(config) == identity.config_sha256, "boot configuration differs")
    require(gzip.decompress((packet / "boot-config.gz").read_bytes()) == config,
            "compressed boot configuration differs")
    boot_lines = [line.strip() for line in (packet / "bootctl.stdout").read_bytes().splitlines()
                  if line.strip().startswith(b"Current Entry:")]
    require(boot_lines == [b"Current Entry: " + identity.selected_entry.encode()],
            "selected boot entry differs")
    require((packet / "boot-id.txt").read_text().strip() != "", "boot ID missing")
    require((packet / "virtualization.stdout").read_bytes().strip() == b"none",
            "native virtualization check differs")
    interior_pulses = {}
    for cpu in (1, 5):
        rows = check_workload((packet / f"workload-cpu{cpu}.csv").read_bytes(), cpu)
        interior_pulses[str(cpu)] = [int(row["pulse"]) for row in rows
                                     if window_begin <= int(row["start_monotonic_ns"])
                                     and int(row["end_monotonic_ns"]) <= window_end]
    require(all(interior_pulses.values()), "no fully interior worker pulses")
    return chronology, elapsed_ns, interior_pulses


def check_analysis(packet: Path, mode: str) -> tuple[dict, dict]:
    status = values((packet / "status.txt").read_bytes(), "observer status")
    required_state = "ready" if mode == "baseline" else "complete"
    required_mode = "records" if mode == "baseline" else mode
    require(status.get("abi") == "2" and status.get("state") == required_state
            and status.get("mode") == required_mode, "ABI 2 observer status differs")
    if mode == "baseline":
        _, parsed, wfi_numbers, _ = analyze_wfi.parse_abi2_status((packet / "status.txt").read_text())
        events, _ = analyze_wfi.legacy.parse_events((packet / "events.csv").read_text(), parsed)
        wfi, _ = analyze_wfi.parse_wfi_events((packet / "wfi-events.csv").read_text(),
                                               parsed, required_mode)
        require(not events and not wfi and all(number == 0 for number in wfi_numbers.values())
                and all(all(value == 0 for value in stream.values()) for stream in parsed["streams"].values()),
                "unarmed baseline unexpectedly recorded events")
        observer = {
            "observer_abi": 2, "capture_mode": mode,
            "integrity": {"clean": True},
            "wfi_probe": {"total": 0, "in_window": 0, "straddling_stop": 0,
                          "post_stop_drain": 0, "by_cluster": None},
            "reverse_coverage": {"counts": None},
            "paired_opportunities": {"status": "not_applicable_unarmed_baseline",
                                     "by_cluster": None,
                                     "negative_claim_supported": False},
        }
    else:
        observer = analyze_wfi.analyze_text(
            (packet / "events.csv").read_text(),
            (packet / "status.txt").read_text(),
            (packet / "wfi-events.csv").read_text(),
        )
        stored = json.loads((packet / "observer-analysis.stdout").read_text())
        require(stored == observer and observer["observer_abi"] == 2
                and observer["capture_mode"] == mode
                and observer["integrity"]["clean"] is True,
                "ABI 2 analyzer output or integrity differs")
    pre = counter_decoder.analyze_text(
        (packet / "counter-pre-events.csv").read_text(),
        (packet / "counter-pre-status.txt").read_text(),
        pairwise_tolerance_ticks=240, endpoint_uncertainty_ticks=4,
    )
    post = counter_decoder.analyze_text(
        (packet / "counter-events.csv").read_text(),
        (packet / "counter-status.txt").read_text(),
        pairwise_tolerance_ticks=240, endpoint_uncertainty_ticks=4,
    )
    require(pre == json.loads((packet / "counter-pre-analysis.stdout").read_text())
            and post == json.loads((packet / "counter-analysis.stdout").read_text()),
            "counter analyzer output differs from raw packet")
    require(pre["phases"]["pre"]["acquisition_eligible_for_conditional_model"] is True
            and post["phases"]["post"]["acquisition_eligible_for_conditional_model"] is True
            and post["shared_pre_post_model"]["both_phases_eligible"] is True,
            "counter acquisition incomplete or ineligible")
    return observer, post


def d_pilot_model_interior_count(observer: dict, status_text: str) -> int:
    """Count matched D probes strictly interior under the *assumed* E=240 model."""
    _, status, _, _ = analyze_wfi.parse_abi2_status(status_text)
    error = analyze_wfi.ASSUMED_PAIRWISE_ERROR_TICKS
    matched = observer["reverse_coverage"]["per_token"]
    return sum(
        row["disposition"] == "matched_wfi_sample"
        and status["start_tick"] + error < row["wfi_t0"]
        and row["wfi_t1"] + error < status["stop_tick"]
        for row in matched
    )


def checked_build_chain(identity: Identity) -> dict:
    directory = Path(__file__).resolve().parent
    build_path = directory / "wfi-build-receipt.json"
    deployment_path = directory / "wfi-deployment-receipt.json"
    build = json.loads(build_path.read_text())
    deployment = json.loads(deployment_path.read_text())
    require(build["build"]["release"] == identity.release
            and build["build"]["gnu_build_id"] == identity.gnu_build_id
            and build["build"]["configuration_sha256"] == identity.config_sha256
            and deployment["release"] == identity.release
            and deployment["new_kernel_gnu_build_id"] == identity.gnu_build_id
            and deployment["configuration_sha256"] == identity.config_sha256
            and deployment["boot_entry"]["title"] == identity.selected_entry
            and deployment["boot_entry"]["uki_sha256"] == build["boot_bundle"]["uki_sha256"],
            "published build/deployment identity chain differs")
    return {
        "aurora_source_commit": build["source"]["aurora_source_commit"],
        "wfi_patch_sha256": file_sha256(directory / "0004-aurora-apsc-wfi-first-attempt.patch"),
        "wfi_build_receipt_sha256": file_sha256(build_path),
        "wfi_deployment_receipt_sha256": file_sha256(deployment_path),
        "uki_sha256_at_deployment_readback": build["boot_bundle"]["uki_sha256"],
    }


def observer_loss_summary(packet: Path) -> dict:
    status = values((packet / "status.txt").read_bytes(), "observer status")
    streams = [f"idle{cpu}" for cpu in range(8)] + ["dvfs0", "dvfs1"]
    streams += [f"wfi{cpu}" for cpu in range(8)]
    return {
        "overflow_total": sum(int(status[f"{stream}_overflow"]) for stream in streams),
        "missing_commit_total": sum(int(status[f"{stream}_missing_commit"]) for stream in streams),
        "wfi_pending_after_drain": int(status["wfi_pending_after_drain"]),
        "wfi_prepare_bad_mapping": int(status["wfi_prepare_bad_mapping"]),
        "wfi_prepare_after_stop": int(status["wfi_prepare_after_stop"]),
        "interrupted": int(status["interrupted"]),
    }


def check_private_boot_qualification(packet: Path, qualification_path: Path,
                                     identity: Identity, chronology: list[dict]) -> tuple[dict, int]:
    require(qualification_path.is_file() and not qualification_path.is_symlink()
            and stat.S_IMODE(qualification_path.stat().st_mode) == 0o600,
            "same-boot FDT qualification must be a private regular mode-0600 file")
    qualification = json.loads(qualification_path.read_text())
    require(isinstance(qualification, dict) and qualification.get("schema") == 1,
            "same-boot FDT qualification schema differs")
    boot_id = (packet / "boot-id.txt").read_text().strip()
    require(qualification.get("boot_id") == boot_id
            and qualification.get("release") == identity.release
            and qualification.get("gnu_build_id") == identity.gnu_build_id
            and qualification.get("configuration_sha256") == identity.config_sha256
            and qualification.get("selected_entry") == identity.selected_entry,
            "FDT qualification and capture boot identity differ")
    require(qualification.get("fdt_same_boot_checked") is True
            and qualification.get("native") is True
            and qualification.get("online_cpus") == "0-7"
            and qualification.get("cpuidle_driver") == "apple_idle"
            and qualification.get("cpuidle_governor") == "menu"
            and qualification.get("all_deep_idle_states_enabled") is True
            and qualification.get("observer_abi") == 2
            and qualification.get("observer_ready") is True
            and qualification.get("counter_abi") == 1
            and qualification.get("counter_unused") is True
            and qualification.get("module_package_integrity_clean") is True
            and qualification.get("charger_connected") is True,
            "same-boot FDT or native readiness qualification is incomplete")
    topology = qualification.get("fdt_topology")
    expected = {
        "validated_against_same_boot_fdt": True,
        "model": "Apple MacBook Air (M1, 2020)",
        "compatible": ["apple,j313", "apple,t8103", "apple,arm-platform"],
        "cpu_count": 8,
        "clusters": {
            "0": {"logical_cpus": [0, 1, 2, 3],
                  "performance_domain_phandle": "0xa",
                  "controller_base": "0x210e20000", "controller_bytes": 4096,
                  "command_address": "0x210e20020"},
            "1": {"logical_cpus": [4, 5, 6, 7],
                  "performance_domain_phandle": "0xd",
                  "controller_base": "0x211e20000", "controller_bytes": 4096,
                  "command_address": "0x211e20020"},
        },
    }
    require(topology == expected, "sanitized same-boot FDT topology differs from T8103 target")
    topology_digest = sha256(json.dumps(topology, sort_keys=True, separators=(",", ":")).encode())
    require(qualification.get("fdt_topology_projection_sha256") == topology_digest,
            "same-boot FDT topology projection hash differs")
    qualified_tick = qualification.get("qualified_monotonic_ns")
    require(isinstance(qualified_tick, int) and not isinstance(qualified_tick, bool)
            and 0 < qualified_tick <= chronology[0]["monotonic_ns"],
            "same-boot FDT qualification was not completed before acquisition")
    return ({"fdt_same_boot_checked": True,
             "fdt_topology": topology,
             "fdt_topology_projection_sha256": topology_digest}, qualified_tick)


def check_device_acceptance(packet: Path, acceptance_path: Path,
                            identity: Identity, chronology: list[dict], qualified_tick: int) -> dict:
    require(acceptance_path.is_file() and not acceptance_path.is_symlink()
            and stat.S_IMODE(acceptance_path.stat().st_mode) == 0o600,
            "device acceptance must be a private regular mode-0600 file")
    acceptance = json.loads(acceptance_path.read_text())
    require(isinstance(acceptance, dict) and acceptance.get("schema") == 1,
            "device acceptance schema differs")
    require(acceptance.get("boot_id") == (packet / "boot-id.txt").read_text().strip()
            and acceptance.get("release") == identity.release
            and acceptance.get("gnu_build_id") == identity.gnu_build_id
            and acceptance.get("selected_entry") == identity.selected_entry,
            "device acceptance and capture boot identity differ")
    require(acceptance.get("charger_connected") is True,
            "device acceptance does not confirm connected charger")
    accepted_tick = acceptance.get("accepted_monotonic_ns")
    require(isinstance(accepted_tick, int) and not isinstance(accepted_tick, bool)
            and qualified_tick <= accepted_tick <= chronology[0]["monotonic_ns"],
            "device acceptance was not completed before acquisition")
    wifi = acceptance.get("wifi")
    brightness = acceptance.get("brightness")
    require(isinstance(wifi, dict) and wifi.get("interface") == "wlan0"
            and wifi.get("driver") == "brcmfmac"
            and wifi.get("functional") is True
            and wifi.get("user_confirmed") is True,
            "Wi-Fi function lacks same-boot user confirmation")
    changed_to = brightness.get("changed_to") if isinstance(brightness, dict) else None
    require(isinstance(brightness, dict)
            and brightness.get("provider") == "apple-panel-bl"
            and brightness.get("driver") == "apple-dcp"
            and brightness.get("functional") is True
            and brightness.get("user_confirmed") is True
            and isinstance(changed_to, int) and not isinstance(changed_to, bool)
            and 0 <= changed_to <= 420 and changed_to != 155
            and brightness.get("restored_to") == 155
            and brightness.get("restoration_user_confirmed") is True,
            "brightness adjustment and restoration lack same-boot user confirmation")
    return {
        "basis": "same-boot operator-confirmed functionality plus private live device/readback checks; no independent Wi-Fi traffic or visual measurement",
        "wifi_user_confirmed": True,
        "brightness_adjustment_user_confirmed": True,
        "brightness_changed_to": changed_to,
        "brightness_restored_to": 155,
        "brightness_restoration_user_confirmed": True,
    }


def publish(packet: Path, mode: str, destination: Path, receipt_path: Path,
            qualification_path: Path, device_acceptance_path: Path,
            identity: Identity = WFI_IDENTITY) -> dict:
    require(mode in ALL_MODES, "unsupported ABI 2 publication mode")
    entries, manifest_sha = packet_manifest(packet, mode)
    chronology, elapsed_ns, interior_pulses = check_acquisition(packet, mode, identity)
    boot_qualification, qualified_tick = check_private_boot_qualification(
        packet, qualification_path, identity, chronology)
    device_acceptance = check_device_acceptance(
        packet, device_acceptance_path, identity, chronology, qualified_tick)
    before_rows, before = project_snapshot(packet, "before-snapshot.json")
    after_rows, after = project_snapshot(packet, "after-snapshot.json")
    check_conditions(before, after)
    observer, counter = check_analysis(packet, mode)
    d_pilot_interior_count = (
        d_pilot_model_interior_count(observer, (packet / "status.txt").read_text())
        if mode == "wfi_clock" else None
    )
    if mode == "wfi_clock":
        require(d_pilot_interior_count > 0,
                "clock pilot lacks a matched model-interior first-attempt probe")
    loss = observer_loss_summary(packet)
    build_chain = checked_build_chain(identity)
    require(not destination.exists() and not receipt_path.exists(), "publication destination already exists")
    require(destination.parent.is_dir() and receipt_path.parent.is_dir(), "publication parent missing")
    public = {}
    input_for_public = {}
    for name in NUMERIC_FILES:
        raw = (packet / name).read_bytes()
        require(sha256(raw) == entries[name], f"packet changed during publication: {name}")
        require(not PRIVATE_TEXT.search(raw), f"private-looking content in {name}")
        published_name = name + ".gz" if name.endswith(".csv") else name
        contents = gzip.compress(raw, compresslevel=9, mtime=0) if name.endswith(".csv") else raw
        public[published_name] = contents
        input_for_public[published_name] = name
    for name, rows, original in (
        ("chronology.json", chronology, "acquisition-record.json"),
        ("environment-before.json", before_rows, "before-snapshot.json"),
        ("environment-after.json", after_rows, "after-snapshot.json"),
    ):
        require(file_sha256(packet / original) == entries[original],
                f"packet changed during publication: {original}")
        public[name] = (json.dumps(rows, indent=2, sort_keys=True) + "\n").encode()
        input_for_public[name] = original
    require(all(not PRIVATE_TEXT.search(contents) for contents in public.values()),
            "private-looking content in public projection")
    evidence = {}
    for name, contents in public.items():
        original = input_for_public[name]
        evidence[name] = {
            "private_input_sha256": entries[original],
            "published_sha256": sha256(contents),
            "uncompressed_bytes": (packet / original).stat().st_size if original in NUMERIC_FILES else None,
            "transformation": ("gzip level 9, mtime=0" if name.endswith(".gz") else
                               "byte exact" if original in NUMERIC_FILES else
                               "strict action/field projection" if name == "chronology.json" else
                               "fixed-label sysfs condition projection"),
        }
    decoder_files = {
        "wfi_decoder": Path(analyze_wfi.__file__),
        "abi1_event_parser": ROOT / "linux-apsc-observer" / "analyze.py",
        "counter_decoder": COUNTER_DECODER,
        "publisher": Path(__file__),
    }
    receipt = {
        "scope": "one complete, independently decoded ABI 2 native WFI packet; full boot packet remains private",
        "release": identity.release,
        "kernel_config_sha256": identity.config_sha256,
        "gnu_build_id": identity.gnu_build_id,
        "selected_entry": identity.selected_entry,
        "workload_sha256": WORKLOAD_SHA256,
        "collector_acquisition_sha256": entries["collector-source.py"],
        "build_chain": build_chain,
        "boot_qualification": boot_qualification,
        "device_acceptance": device_acceptance,
        "mode": mode,
        "observer_abi": 2,
        "integrity_clean": True,
        "observer_loss_and_drain": loss,
        "integrity_basis": ("unarmed ready status with zero event and WFI streams" if mode == "baseline"
                            else "current ABI 2 analyzer agrees exactly with saved output and reports clean"),
        "packet_sha256s_sha256": manifest_sha,
        "observer_analysis_private_sha256": entries.get("observer-analysis.stdout"),
        "requested_window_ms": 2000,
        "external_window_elapsed_ns": elapsed_ns,
        "worker_pulses_fully_inside_external_window_by_cpu": interior_pulses,
        "counter_pre_post_eligible_under_declared_model":
            counter["shared_pre_post_model"]["both_phases_eligible"],
        "counter_decoder_options": {
            "pairwise_tolerance_ticks": 240,
            "endpoint_uncertainty_ticks": 4,
            "guaranteed_capture_clock_error_bound": False,
        },
        "source_sha256": {name: file_sha256(path) for name, path in decoder_files.items()},
        "source_sha256_scope": "publication-time decoder and publisher files; collector digest is acquisition-time saved source",
        "conditions": {
            "charger_online": before["power.ac_online"],
            "brightness": before["backlight.brightness"],
            "battery_capacity_percent_before": before["power.battery_capacity_percent"],
            "battery_capacity_percent_after": after["power.battery_capacity_percent"],
            "policy_charger_brightness_endpoints_equal": True,
            "interior_condition_changes": "not_observed",
            "usb_network_background_activity": "not_fully_observed",
        },
        "single_packet_boot_distinctness": "not_established; compare private boot IDs across packets",
        "private_boot_cmdline": "retained in hashed packet; not independently decoded here",
        "private_full_fdt": "retained in hashed packet; only selected same-boot topology was checked by the private qualification",
        "wfi_probe": {
            "total": observer["wfi_probe"]["total"],
            "in_window": observer["wfi_probe"]["in_window"],
            "straddling_stop": observer["wfi_probe"]["straddling_stop"],
            "post_stop_drain": observer["wfi_probe"]["post_stop_drain"],
            "in_window_by_cluster": observer["wfi_probe"]["by_cluster"],
        },
        "d_pilot_matched_model_interior_probe_count": d_pilot_interior_count,
        "d_pilot_capture_boundary_model": (
            "matched WFI bracket strictly inside start/stop by assumed E=240 ticks; "
            "cross-CPU error is not measured" if mode == "wfi_clock" else None
        ),
        "reverse_coverage_counts": observer["reverse_coverage"]["counts"],
        "paired_opportunity_status": observer["paired_opportunities"]["status"],
        "paired_opportunity_by_cluster": observer["paired_opportunities"]["by_cluster"],
        "paired_opportunity_model": {
            "primary_bound_ticks": observer["paired_opportunities"].get("primary_bound_ticks"),
            "exploratory_bound_ticks": observer["paired_opportunities"].get("exploratory_bound_ticks"),
            "assumed_pairwise_clock_error_ticks":
                observer["paired_opportunities"].get("assumed_pairwise_clock_error_ticks"),
            "negative_claim_supported": observer["paired_opportunities"]["negative_claim_supported"],
            "status": observer["paired_opportunities"]["status"],
            "clock_bound_is_assumed_not_measured": True,
        },
        "c_hook_comparable_lag": (
            {"status": observer["c_hook_comparable_lag"]["status"],
             "by_cluster": observer["c_hook_comparable_lag"]["by_cluster"],
             "primary_bound_ticks": observer["c_hook_comparable_lag"]["primary_bound_ticks"],
             "exploratory_bound_ticks": observer["c_hook_comparable_lag"]["exploratory_bound_ticks"],
             "assumed_pairwise_clock_error_ticks":
                 observer["c_hook_comparable_lag"]["assumed_pairwise_clock_error_ticks"]}
            if mode == "mmio" else None),
        "evidence_files": evidence,
        "claim_boundary": "first-attempt pre-DSB probe only; WFI-instruction state, physical power, energy and a guaranteed cross-CPU clock bound remain unobserved",
    }
    serialized = (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode()
    with tempfile.TemporaryDirectory(prefix=".wfi-publication-", dir=destination.parent) as temporary:
        staging = Path(temporary) / "evidence"
        staging.mkdir()
        for name, contents in public.items():
            (staging / name).write_bytes(contents)
        (Path(temporary) / "receipt.json").write_bytes(serialized)
        require(all(file_sha256(packet / name) == expected for name, expected in entries.items()),
                "packet changed before publication commit")
        os.rename(staging, destination)
        try:
            os.rename(Path(temporary) / "receipt.json", receipt_path)
        except OSError:
            for path in destination.iterdir():
                path.unlink()
            destination.rmdir()
            raise
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--mode", choices=ALL_MODES, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--qualification", type=Path, required=True,
                        help="private same-boot T8103 FDT/topology qualification receipt")
    parser.add_argument("--device-acceptance", type=Path, required=True,
                        help="private same-boot user-confirmed Wi-Fi/brightness receipt")
    args = parser.parse_args()
    try:
        publish(args.packet, args.mode, args.out, args.receipt,
                args.qualification, args.device_acceptance)
    except PublicationError as error:
        parser.exit(2, f"WFI publication rejected: {error}\n")
    except (OSError, UnicodeError, json.JSONDecodeError, EOFError, zlib.error,
            gzip.BadGzipFile, analyze_wfi.legacy.AnalysisError,
            counter_decoder.AnalysisError):
        parser.exit(2, "WFI publication rejected: malformed private packet or I/O failure; private values withheld\n")


if __name__ == "__main__":
    main()
