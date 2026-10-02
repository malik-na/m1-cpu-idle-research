#!/usr/bin/env python3
"""Offline, fail-closed projection and public replay of ABI 3 A evidence.

The command reads a sealed private packet and writes a new review staging
directory. It never opens debugfs, starts workers, or modifies the packet.
Only enumerated numerical fields enter the staged files; boot, account,
network and device identifiers stay in the private packet. The standalone
public-stage replay needs no private packet.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile

import capture_abi3 as collector


HERE = Path(__file__).resolve().parent
COLLECTOR_REDACTION = HERE / "REDACTION-RECEIPT.json"
PUBLISHER_REDACTION = HERE / "PUBLISHER-REDACTION-RECEIPT.json"
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
ENTRY = re.compile(r"([0-9a-f]{64})  ([A-Za-z0-9_.-]+)\Z")
PACKET_NAME = re.compile(r"abi3-A-[0-9TZ]+\Z")
PRIVATE_TEXT = re.compile(
    rb"/home/|/root/|/Users/|root=UUID=|machine-id|serial_number|password|passwd|"
    rb"BEGIN [A-Z ]*PRIVATE KEY|\b[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}\b|"
    rb"\b(?:[0-9a-f]{2}:){5}[0-9a-f]{2}\b", re.I)
REQUIRED = {
    "acquisition-summary.json", "apsc-status-before.txt", "apsc-status-after.txt",
    "apsc-events.csv", "apsc-wfi-events.csv", "pcpm-status-before.txt",
    "pcpm-status-after.txt", "counter-status-before.txt", "counter-status-after.txt",
    "schedule.json", "window-markers.json", "stream-status-check.json",
    "workload-cpu1.csv", "workload-cpu5.csv", "workload-cpu1.stderr",
    "workload-cpu5.stderr", "workload-check.json", "workload-checksum-match.json",
    "timeline.jsonl", "environment-before.json", "environment-after.json",
    "environment-drift.json", "power-at-arm.json", "power-at-window-end.json",
    "expected-identity.json", "source-hashes.json", "collector-source.py",
    "workload-source.c", "workload-binary", "validator-source.py",
    "patch-source.bin", "source_receipt-source.bin", "linked_receipt-source.bin",
    "user-boot-qualification.json", "user-boot-qualification-check.json",
    "boot-id.txt", "running.config", "config.gz", "kernel-notes.bin",
    "bootctl.stdout", "limine.conf", "installed-image-hashes.json",
    "module-package-check.stdout", "kernel-log-before.stdout",
    "kernel-log-after.stdout", "proc-stat-before", "proc-stat-after",
}
PUBLIC_NAMES = (
    "baseline.json", "environment.json", "timeline.json",
    "workload-cpu1.csv.gz", "workload-cpu5.csv.gz",
    "apsc-status-before.txt", "apsc-status-after.txt",
    "pcpm-status-before.txt", "pcpm-status-after.txt",
    "counter-status-before.txt", "counter-status-after.txt",
    "apsc-events.csv.gz", "apsc-wfi-events.csv.gz", "publication-receipt.json",
)
APSC_BASE_KEYS = (
    "abi", "state", "mode", "cntfrq", "start_tick", "stop_tick", "end_tick",
    "inside_start_ns", "inside_stop_ns", "start_online_mask", "end_online_mask",
    "interrupted", "wfi_pending_after_drain", "wfi_prepare_after_stop",
    "wfi_prepare_bad_mapping",
)
APSC_CLUSTER_FIELDS = (
    "cpus", "ticket_start", "ticket_stop", "cmd_phys", "resource_size",
    "policy_mask_start", "policy_mask_end", "policy_cpu_start", "policy_cpu_end",
    "fast_switch_start", "fast_switch_end",
)
APSC_FULL_KEYS = set(APSC_BASE_KEYS) | {
    f"cluster{cluster}_{field}" for cluster in (0, 1)
    for field in APSC_CLUSTER_FIELDS
} | {
    f"{stream}{index}_{suffix}"
    for stream, count in (("idle", 8), ("wfi", 8), ("dvfs", 2))
    for index in range(count)
    for suffix in ("attempts", "committed", "overflow", "missing_commit")
}
APSC_PUBLIC_KEYS = APSC_FULL_KEYS - {"cluster0_cmd_phys", "cluster1_cmd_phys"}
PCPM_BASE_KEYS = (
    "abi", "state", "mode", "error", "requested", "period_ms", "phase_ms",
    "start_ns", "end_ns", "budget_end_ns", "worker_cpu", "start_online_mask",
    "end_online_mask", "e_mask", "p_mask", "pmgr_phys", "pmgr_size",
    "register_offset", "regmap_existing", "regmap_internal_clockless",
    "regmap_stride", "regmap_val_bytes", "attempted", "missed_slots",
    "unattempted_after_error", "trailing_missed", "read_errors", "cpu_errors",
    "counter_errors", "time_errors", "config_ool_workaround", "ecv_alternative",
    "counter_metadata_valid", "counter_metadata_cpu", "counter_metadata_error",
    "counter_cntfrq", "counter_cntkctl", "counter_mmfr0",
    "counter_workaround_present", "counter_phys_read_workaround",
)
PCPM_FULL_KEYS = set(PCPM_BASE_KEYS) | {
    f"cpu{cpu}.{field}" for cpu in range(8) for field in ("midr", "mpidr", "kind")
}
PCPM_PUBLIC_KEYS = set(PCPM_BASE_KEYS) - {
    "pmgr_phys", "pmgr_size", "register_offset", "regmap_existing",
    "regmap_internal_clockless", "regmap_stride", "regmap_val_bytes",
    "counter_cntkctl", "counter_mmfr0",
}
COUNTER_BASE_KEYS = (
    "abi", "possible_mask", "cluster0_cpus", "cluster1_cpus",
    "config_ool_workaround", "ecv_alternative", "capacity_per_phase",
)
COUNTER_PHASE_FIELDS = (
    "state", "reference_cpu", "rounds", "attempted", "completed", "error",
    "metadata_completed", "start_tick", "end_tick", "start_online_mask",
    "end_online_mask",
)
COUNTER_CPU_FIELDS = (
    "valid", "actual", "error", "cntfrq", "cntkctl", "mmfr0",
    "workaround_present", "phys_read_workaround",
)
COUNTER_FULL_KEYS = set(COUNTER_BASE_KEYS) | {
    f"{phase}_{field}" for phase in ("pre", "post") for field in COUNTER_PHASE_FIELDS
} | {
    f"{phase}_cpu{cpu}_{field}" for phase in ("pre", "post")
    for cpu in range(8) for field in COUNTER_CPU_FIELDS
}
COUNTER_PUBLIC_KEYS = set(COUNTER_BASE_KEYS) | {
    f"{phase}_{field}" for phase in ("pre", "post") for field in COUNTER_PHASE_FIELDS
} | {
    f"{phase}_cpu{cpu}_{field}" for phase in ("pre", "post")
    for cpu in range(8) for field in ("valid", "actual", "error")
}
STATUS_SCHEMAS = {
    "apsc": (APSC_FULL_KEYS, APSC_PUBLIC_KEYS),
    "pcpm": (PCPM_FULL_KEYS, PCPM_PUBLIC_KEYS),
    "counter": (COUNTER_FULL_KEYS, COUNTER_PUBLIC_KEYS),
}
APSC_HEX_KEYS = {"start_online_mask", "end_online_mask"} | {
    f"cluster{cluster}_{field}" for cluster in (0, 1)
    for field in ("cpus", "cmd_phys", "resource_size", "policy_mask_start",
                  "policy_mask_end")
}
PCPM_HEX_KEYS = {"start_online_mask", "end_online_mask", "e_mask", "p_mask",
                 "pmgr_phys", "pmgr_size"} | {
    f"cpu{cpu}.{field}" for cpu in range(8) for field in ("midr", "mpidr")
}
COUNTER_HEX_KEYS = {"possible_mask", "cluster0_cpus", "cluster1_cpus"} | {
    f"{phase}_{field}" for phase in ("pre", "post")
    for field in ("start_online_mask", "end_online_mask")
}
PCPM_EMPTY_KEYS = {"counter_cntfrq", "counter_cntkctl", "counter_mmfr0",
                   "counter_workaround_present", "counter_phys_read_workaround"}
COUNTER_EMPTY_KEYS = {
    f"{phase}_{field}" for phase in ("pre", "post")
    for field in ("start_tick", "end_tick")
} | {
    f"{phase}_cpu{cpu}_{field}" for phase in ("pre", "post")
    for cpu in range(8)
    for field in ("cntfrq", "cntkctl", "mmfr0", "workaround_present",
                  "phys_read_workaround")
}
STATUS_HEX_KEYS = {"apsc": APSC_HEX_KEYS, "pcpm": PCPM_HEX_KEYS,
                   "counter": COUNTER_HEX_KEYS}
STATUS_EMPTY_KEYS = {"apsc": set(), "pcpm": PCPM_EMPTY_KEYS,
                     "counter": COUNTER_EMPTY_KEYS}
STATUS_LITERALS = {
    "apsc": {"abi": "3", "state": "ready", "mode": "records"},
    "pcpm": {"abi": "2", "state": "unused", "mode": "none",
             **{f"cpu{cpu}.kind": "unknown" for cpu in range(8)}},
    "counter": {"abi": "1", "pre_state": "unused", "post_state": "unused"},
}


class PublicationError(ValueError):
    pass


def require(ok: bool, message: str) -> None:
    if not ok:
        raise PublicationError(message)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def bounded(path: Path, limit: int = 1024 * 1024) -> bytes:
    with path.open("rb") as source:
        data = source.read(limit + 1)
    require(len(data) <= limit, f"oversized private input: {path.name}")
    return data


def gunzip_bounded(data: bytes, limit: int) -> bytes:
    with gzip.GzipFile(fileobj=io.BytesIO(data)) as stream:
        result = stream.read(limit + 1)
    require(len(result) <= limit, "oversized decompressed input")
    return result


def json_file(packet: Path, name: str, limit: int = 1024 * 1024):
    try:
        return json.loads(bounded(packet / name, limit), object_pairs_hook=unique_object)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise PublicationError(f"invalid JSON in {name}") from error


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate JSON key")
        result[key] = value
    return result


def reviewed_collector_hash() -> str:
    try:
        receipt = json.loads(bounded(COLLECTOR_REDACTION, 64 * 1024),
                             object_pairs_hook=unique_object)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise PublicationError("collector redaction receipt invalid") from error
    require(receipt.get("schema") == "abi3-collector-redaction-v1" and
            receipt.get("public_collector_sha256") == file_digest(Path(collector.__file__)) and
            isinstance(receipt.get("private_collector_sha256"), str) and
            HEX64.fullmatch(receipt["private_collector_sha256"]) is not None,
            "public collector differs from its reviewed redaction receipt")
    return receipt["private_collector_sha256"]


def verify_public_source_binding() -> None:
    try:
        receipt = json.loads(bounded(PUBLISHER_REDACTION, 64 * 1024),
                             object_pairs_hook=unique_object)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise PublicationError("publisher redaction receipt invalid") from error
    require(receipt.get("schema") == "abi3-a-publisher-public-copy-v1" and
            receipt.get("public_publisher_sha256") == file_digest(Path(__file__)) and
            receipt.get("collector_redaction_receipt_sha256") ==
            file_digest(COLLECTOR_REDACTION) and
            receipt.get("private_collector_sha256") == reviewed_collector_hash() and
            receipt.get("public_collector_sha256") == file_digest(Path(collector.__file__)) and
            isinstance(receipt.get("private_publisher_sha256"), str) and
            HEX64.fullmatch(receipt["private_publisher_sha256"]) is not None,
            "public publisher differs from its reviewed source receipt")


def parse_status_exact(raw: bytes, kind: str, public: bool = False) -> tuple[dict[str, str], list[tuple[str, bytes]]]:
    full, published = STATUS_SCHEMAS[kind]
    expected = published if public else full
    require(raw.endswith(b"\n") and b"\r" not in raw, f"{kind} status newline changed")
    parsed = {}
    lines = []
    for line in raw.splitlines(keepends=True):
        try:
            text = line[:-1].decode("ascii")
        except UnicodeError as error:
            raise PublicationError(f"non-ASCII {kind} status") from error
        key, separator, value = text.partition("=")
        require(separator == "=" and key in expected and key not in parsed,
                f"{kind} status key set changed")
        literal = STATUS_LITERALS[kind].get(key)
        if literal is not None:
            require(value == literal, f"{kind} status literal changed: {key}")
        elif key in STATUS_EMPTY_KEYS[kind]:
            require(value == "", f"{kind} unused metadata changed: {key}")
        elif key in STATUS_HEX_KEYS[kind]:
            require(re.fullmatch(r"0x[0-9a-f]{1,16}", value) is not None,
                    f"{kind} status hex value invalid: {key}")
        else:
            require(re.fullmatch(r"-?(?:0|[1-9][0-9]{0,19})", value) is not None,
                    f"{kind} status number invalid: {key}")
        parsed[key] = value
        lines.append((key, line))
    require(set(parsed) == expected, f"{kind} status key set changed")
    return parsed, lines


def sanitized_status(raw: bytes, kind: str) -> bytes:
    _, lines = parse_status_exact(raw, kind)
    published = STATUS_SCHEMAS[kind][1]
    result = b"".join(line for key, line in lines if key in published)
    parse_status_exact(result, kind, public=True)
    return result


def check_public_statuses(public: dict[str, bytes]) -> None:
    event = gunzip_bounded(public["apsc-events.csv.gz"], 1024)
    wfi = gunzip_bounded(public["apsc-wfi-events.csv.gz"], 1024)
    require(event == (collector.EVENT_HEADER + "\n").encode() and
            wfi == (collector.WFI_HEADER + "\n").encode(),
            "public APSC stream is not header-only")
    statuses = {}
    for kind in STATUS_SCHEMAS:
        before = public[f"{kind}-status-before.txt"]
        after = public[f"{kind}-status-after.txt"]
        require(before == after, f"public {kind} before/after status differs")
        status, _ = parse_status_exact(before, kind, public=True)
        statuses[kind] = status
    apsc = statuses["apsc"]
    collector.check_unarmed_ready(apsc, event, wfi)
    require(apsc["wfi_pending_after_drain"] == apsc["interrupted"] == "0" and
            apsc["cluster0_cpus"] == "0xf" and apsc["cluster1_cpus"] == "0xf0" and
            apsc["cluster0_resource_size"] == apsc["cluster1_resource_size"] ==
            "0x1000", "public APSC unarmed/topology status differs")
    pcpm, counter = statuses["pcpm"], statuses["counter"]
    collector.check_aux_unused(public["pcpm-status-before.txt"],
                               public["counter-status-before.txt"])
    require(all(pcpm[key] == "0" for key in ("error", "requested", "attempted",
            "missed_slots", "unattempted_after_error", "trailing_missed",
            "read_errors", "cpu_errors", "counter_errors", "time_errors")) and
            pcpm["worker_cpu"] == "-1", "public PCPM status is not unused")
    for phase in ("pre", "post"):
        require(counter[f"{phase}_reference_cpu"] == "-1" and
                all(counter[f"{phase}_{field}"] == "0" for field in (
                    "rounds", "attempted", "completed", "error", "metadata_completed")) and
                all(counter[f"{phase}_cpu{cpu}_valid"] == "0" and
                    counter[f"{phase}_cpu{cpu}_actual"] == "-1" and
                    counter[f"{phase}_cpu{cpu}_error"] == "0" for cpu in range(8)),
                "public counter helper status is not unused")


def verify_manifest(packet: Path) -> tuple[dict[str, str], str]:
    require(PACKET_NAME.fullmatch(packet.name) is not None, "expected an ABI 3 A packet")
    require(packet.is_dir() and not packet.is_symlink(), "private packet must be a directory")
    require(stat.S_IMODE(packet.stat().st_mode) == 0o700, "private packet mode must be 0700")
    manifest = packet / "MANIFEST.sha256"
    require(manifest.is_file() and not manifest.is_symlink(), "missing regular private manifest")
    raw = bounded(manifest)
    require(raw and raw.endswith(b"\n"), "empty or unterminated private manifest")
    try:
        lines = raw.decode("ascii").splitlines()
    except UnicodeError as error:
        raise PublicationError("non-ASCII private manifest") from error
    entries = {}
    owner = packet.stat().st_uid
    for line in lines:
        match = ENTRY.fullmatch(line)
        require(match is not None, "malformed private manifest entry")
        sha, name = match.groups()
        require(name not in {".", "..", "MANIFEST.sha256"} and name not in entries,
                "unsafe or duplicate private manifest name")
        item = packet / name
        require(item.is_file() and not item.is_symlink(), f"nonregular private item: {name}")
        item_stat = item.stat()
        require(stat.S_ISREG(item_stat.st_mode) and item_stat.st_uid == owner and
                stat.S_IMODE(item_stat.st_mode) == 0o600,
                f"private item ownership/mode changed: {name}")
        require(file_digest(item) == sha, f"private manifest mismatch: {name}")
        entries[name] = sha
    require(stat.S_IMODE(manifest.stat().st_mode) == 0o600 and
            manifest.stat().st_uid == owner, "private manifest ownership/mode changed")
    require(set(entries) | {"MANIFEST.sha256"} == {p.name for p in packet.iterdir()},
            "private packet has unmanifested items")
    require(REQUIRED <= set(entries), "private A packet lacks required evidence files")
    require("abi3-validator-report.json" not in entries and
            "prior-packet-gate.json" not in entries, "A packet contains later-phase evidence")
    return entries, digest(raw)


def check_provenance(packet: Path, entries: dict[str, str]) -> tuple[dict, str]:
    identity = collector.identity_schema(packet / "expected-identity.json")
    require(re.fullmatch(r"7\.1\.12-ARCH-apsc-[A-Za-z0-9._-]{1,80}",
                         identity["release"]) is not None,
            "release cannot enter public receipt")
    hashes = json_file(packet, "source-hashes.json")
    expected = {
        "collector_sha256": entries["collector-source.py"],
        "workload_source_sha256": entries["workload-source.c"],
        "workload_binary_sha256": entries["workload-binary"],
        "validator_sha256": entries["validator-source.py"],
        "patch_sha256": entries["patch-source.bin"],
        "source_tree_sha256": identity["source_tree_sha256"],
        "linked_receipt_sha256": entries["linked_receipt-source.bin"],
    }
    require(hashes == expected and
            hashes["workload_source_sha256"] == collector.EXPECTED_WORKLOAD_SOURCE_SHA and
            hashes["workload_binary_sha256"] == collector.EXPECTED_WORKLOAD_SHA and
            hashes["collector_sha256"] == reviewed_collector_hash() and
            hashes["validator_sha256"] == identity["validator_sha256"] and
            hashes["patch_sha256"] == identity["patch_sha256"] and
            entries["source_receipt-source.bin"] == identity["source_receipt_sha256"] and
            hashes["linked_receipt_sha256"] == identity["linked_receipt_sha256"],
            "saved source hashes or prepared collector differ")
    source_receipt = json_file(packet, "source_receipt-source.bin")
    linked_receipt = json_file(packet, "linked_receipt-source.bin")
    require(type(source_receipt) is dict and type(linked_receipt) is dict and
            source_receipt.get("candidate_manifest_tree_sha256") ==
            identity["source_tree_sha256"] and
            source_receipt.get("patch_sha256") == identity["patch_sha256"] and
            linked_receipt.get("candidate_source_tree_sha256") ==
            identity["source_tree_sha256"] and
            linked_receipt.get("source_receipt_sha256") ==
            identity["source_receipt_sha256"] and
            linked_receipt.get("patch_sha256") == identity["patch_sha256"] and
            linked_receipt.get("config_sha256") == identity["config_sha256"] and
            linked_receipt.get("release") == identity["release"] and
            linked_receipt.get("vmlinux_build_id") == identity["build_id"] and
            linked_receipt.get("image_sha256") == identity["image_sha256"] and
            linked_receipt.get("full_build_exit_status") == 0,
            "saved source/linked build receipt chain differs")
    config = bounded(packet / "running.config", 2 * 1024 * 1024)
    decompressed = gunzip_bounded(bounded(packet / "config.gz", 2 * 1024 * 1024),
                                  2 * 1024 * 1024)
    require(digest(config) == identity["config_sha256"] and decompressed == config and
            collector.build_ids(bounded(packet / "kernel-notes.bin", 16 * 1024 * 1024)) ==
            [identity["build_id"]], "saved kernel identity differs")
    require(("Current Entry: " + identity["entry_title"] + "\n").encode() in
            bounded(packet / "bootctl.stdout") and
            digest(bounded(packet / "limine.conf")) == identity["limine_conf_sha256"],
            "saved selected boot entry differs")
    installed = json_file(packet, "installed-image-hashes.json")
    require(installed == {"candidate": identity["uki_sha256"],
                          "stock": identity["fallback_ukis"]["stock"]["sha256"],
                          "pcpm": identity["fallback_ukis"]["pcpm"]["sha256"]},
            "saved installed image hashes differ")
    require(b"0 altered files" in bounded(packet / "module-package-check.stdout") and
            bounded(packet / "kernel-log-before.stdout").strip() and
            bounded(packet / "kernel-log-after.stdout").strip(),
            "module package or boot log evidence absent")
    boot_id = bounded(packet / "boot-id.txt", 128).decode("ascii").strip()
    require(collector.BOOT_ID_PATTERN.fullmatch(boot_id) is not None,
            "saved boot ID invalid")
    receipt, raw = collector.boot_qualification(
        packet / "user-boot-qualification.json", boot_id, identity, "A", None)
    check = json_file(packet, "user-boot-qualification-check.json")
    require(check == {
        "phase": "A", "receipt_sha256": digest(raw), "current_boot_id": boot_id,
        "current_boot_wifi_user_confirmed": True,
        "current_boot_visible_brightness_confirmed": True,
        "brightness_visible_checked_on_first_abi3_boot": True,
        "first_a_visual_receipt_sha256": digest(raw),
        "current_boot_backlight_readback_expected": "155",
    }, "A user qualification receipt binding differs")
    return identity, digest(raw)


def control_fields() -> dict:
    return collector.control_disposition({"state": collector.CONTROL_NOT_ATTEMPTED})


def check_timeline(packet: Path, start: int, stop: int) -> list[dict]:
    raw = bounded(packet / "timeline.jsonl", 4 * 1024 * 1024)
    require(raw.endswith(b"\n"), "unterminated private timeline")
    try:
        rows = [json.loads(line, object_pairs_hook=unique_object)
                for line in raw.splitlines()]
    except (UnicodeError, json.JSONDecodeError) as error:
        raise PublicationError("invalid private timeline") from error
    require(rows and all(type(row) is dict for row in rows), "empty or malformed timeline")
    ticks = [row.get("monotonic_ns") for row in rows]
    require(all(type(tick) is int and tick > 0 for tick in ticks) and ticks == sorted(ticks),
            "timeline ticks invalid or reversed")
    actions = [row.get("action") for row in rows]
    require(actions[0] == "begin" and actions[-1] == "complete" and
            rows[0].get("phase") == rows[-1].get("phase") == "A" and
            not any(action == "failed" or action.startswith("capture_write") or
                    action in {"raw_read_failed", "workload_incident_export_failed"}
                    for action in actions if isinstance(action, str)),
            "A timeline failed or attempted an observer write")
    required = ("window_begin", "window_end", "observer_raw_drained",
                "workload_release_begin", "complete")
    positions = []
    for action in required:
        found = [i for i, value in enumerate(actions) if value == action]
        require(len(found) == 1, f"missing or repeated timeline action: {action}")
        positions.append(found[0])
    require(positions == sorted(positions) and
            rows[positions[0]].get("phase") == "A" and
            rows[positions[0]].get("mode") == "baseline" and
            rows[positions[2]].get("errors") == [] and
            rows[positions[3]].get("token") == "E" and
            rows[positions[3]].get("reason") == "window_ended" and
            rows[positions[3]].get("cpus") == [1, 5] and
            ticks[positions[0]] <= start < stop <= ticks[positions[1]],
            "A window/drain/release timeline differs")
    releases = [row for row in rows if row.get("action") == "workload_release_end"]
    require(len(releases) == 2 and {row.get("cpu") for row in releases} == {1, 5} and
            all(row.get("exit_status") == 0 for row in releases) and
            all(positions[3] < rows.index(row) < positions[4] for row in releases),
            "A worker releases incomplete")
    wanted = ("begin", "window_begin", "window_end", "observer_raw_drained",
              "workload_release_begin", "workload_release_end", "complete")
    return [{"action": row["action"],
             "relative_monotonic_ns": row["monotonic_ns"] - start,
             **({"cpu": row["cpu"], "exit_status": 0}
                if row["action"] == "workload_release_end" else {})}
            for row in rows if row.get("action") in wanted]


def check_environment(packet: Path) -> dict:
    before = json_file(packet, "environment-before.json")
    after = json_file(packet, "environment-after.json")
    require(type(before) is dict and type(after) is dict, "invalid environment snapshot")
    drift = collector.check_environment(before, after)
    require(json_file(packet, "environment-drift.json") == drift,
            "saved environment drift differs")
    projected = {}
    for label, row in (("before", before), ("after", after)):
        require(set(row) == {"utc", "monotonic_ns", "ac_online", "battery_percent",
                             "backlight_interface_present", "brightness", "actual_brightness",
                             "online_cpus", "cpuidle_driver", "cpuidle_governor",
                             "cpuidle_state1_disabled", "policies", "thermal_millidegrees",
                             "network", "usb", "proc_stat_sha256"},
                "environment schema changed")
        require(row["ac_online"] == "1" and row["brightness"] == "155" and
                row["backlight_interface_present"] is True and
                row["online_cpus"] == "0-7" and row["cpuidle_driver"] == "apple_idle" and
                row["cpuidle_governor"] == "menu", "A environment baseline differs")
        require(type(row["battery_percent"]) is str and
                re.fullmatch(r"[0-9]{1,3}", row["battery_percent"]) and
                0 <= int(row["battery_percent"]) <= 100 and
                type(row["actual_brightness"]) is str and
                re.fullmatch(r"[0-9]{1,5}", row["actual_brightness"]),
                "battery or backlight reading invalid")
        require(set(row["cpuidle_state1_disabled"]) == {str(i) for i in range(8)} and
                all(value == "0" for value in row["cpuidle_state1_disabled"].values()),
                "deep idle setup differs")
        policies = row["policies"]
        require(type(policies) is dict and set(policies) == {"policy0", "policy4"},
                "CPU policy set changed")
        for name, cpus in (("policy0", "0 1 2 3"), ("policy4", "4 5 6 7")):
            policy = policies[name]
            require(set(policy) == {"related_cpus", "affected_cpus", "scaling_driver",
                                    "scaling_governor", "scaling_min_freq", "scaling_max_freq"} and
                    policy["related_cpus"] == policy["affected_cpus"] == cpus and
                    policy["scaling_driver"] == "apple-cpufreq" and
                    policy["scaling_governor"] == "schedutil" and
                    all(type(policy[key]) is str and re.fullmatch(r"[0-9]{1,9}", policy[key])
                        for key in ("scaling_min_freq", "scaling_max_freq")),
                    "CPU policy details differ")
        thermal = row["thermal_millidegrees"]
        require(type(thermal) is dict and all(re.fullmatch(r"thermal_zone[0-9]+", key) and
                type(value) is str and re.fullmatch(r"-?[0-9]{1,6}", value)
                for key, value in thermal.items()), "thermal readings invalid")
        network = row["network"]
        require(type(network) is dict and len(network) <= 64 and all(
            re.fullmatch(r"[A-Za-z0-9_.-]{1,15}", name) and type(counters) is dict and
            set(counters) == {"rx_bytes", "tx_bytes", "rx_packets", "tx_packets"} and
            all(type(value) is str and re.fullmatch(r"[0-9]{1,20}", value)
                for value in counters.values()) for name, counters in network.items()),
            "network counter schema invalid")
        usb = row["usb"]
        require(type(usb) is list and len(usb) <= 64 and all(type(device) is dict and
                set(device) == {"node", "vendor", "product"} and
                re.fullmatch(r"[A-Za-z0-9_.:-]{1,32}", device["node"]) and
                re.fullmatch(r"[0-9a-fA-F]{4}", device["vendor"]) and
                re.fullmatch(r"[0-9a-fA-F]{4}", device["product"])
                for device in usb), "USB inventory schema invalid")
        projected[label] = {
            "battery_percent": int(row["battery_percent"]),
            "actual_brightness": int(row["actual_brightness"]),
            "thermal_min_millidegrees": min(map(int, thermal.values())) if thermal else None,
            "thermal_max_millidegrees": max(map(int, thermal.values())) if thermal else None,
            "network_interface_count": len(network), "usb_device_count": len(usb),
        }
    for name in ("power-at-arm.json", "power-at-window-end.json"):
        endpoint = json_file(packet, name)
        collector.require_power_endpoints(endpoint, name)
        require(set(endpoint) == {"observed_monotonic_ns", "ac_online",
                                  "backlight_interface_present", "brightness"} and
                type(endpoint["observed_monotonic_ns"]) is int,
                "power endpoint schema differs")
    network_before, network_after = before["network"], after["network"]
    equal = set(network_before) == set(network_after)
    deltas = {}
    if equal:
        for key in ("rx_bytes", "tx_bytes", "rx_packets", "tx_packets"):
            differences = [int(network_after[name][key]) - int(network_before[name][key])
                           for name in network_before]
            if any(delta < 0 for delta in differences):
                equal = False
                break
            deltas[key] = sum(differences)
    return {"schema": "abi3-a-environment-projection-v1",
            "ac_online_at_preflight_arm_end_after": True,
            "brightness_155_at_preflight_arm_end_after": True,
            "online_cpus": "0-7", "cpuidle_driver": "apple_idle",
            "cpuidle_governor": "menu", "deep_idle_enabled_all_cpus": True,
            "policy_cpu_sets": {"policy0": "0 1 2 3", "policy4": "4 5 6 7"},
            "before_after": projected,
            "network_interface_set_equal": set(network_before) == set(network_after),
            "network_counter_deltas": deltas if equal else None,
            "usb_inventory_equal": before["usb"] == after["usb"],
            "scope": "endpoint context only; no network, USB or boot identifiers"}


def project_workload(raw: bytes, cpu: int, scheduled: int,
                     interior: tuple[int, int]) -> bytes:
    reader = csv.DictReader(io.StringIO(raw.decode("ascii")))
    rows = list(reader)
    require(reader.fieldnames == collector.WORKLOAD_FIELDS and len(rows) == 200,
            "workload CSV shape changed")
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(("cpu", "pulse", "iterations", "relative_start_ns",
                     "duration_ns", "checksum", "fully_inside_window"))
    for row in rows:
        begin, end = int(row["start_monotonic_ns"]), int(row["end_monotonic_ns"])
        writer.writerow((cpu, int(row["pulse"]), int(row["iterations"]),
                         begin - scheduled, end - begin, int(row["checksum"]),
                         int(interior[0] < begin and end < interior[1])))
    return output.getvalue().encode("ascii")


def build_public(packet: Path) -> dict[str, bytes]:
    entries, manifest_sha = verify_manifest(packet)
    identity, visual_sha = check_provenance(packet, entries)
    events = bounded(packet / "apsc-events.csv", 1024)
    wfi = bounded(packet / "apsc-wfi-events.csv", 1024)
    public = {
        "apsc-events.csv.gz": gzip.compress(events, compresslevel=9, mtime=0),
        "apsc-wfi-events.csv.gz": gzip.compress(wfi, compresslevel=9, mtime=0),
    }
    for kind in STATUS_SCHEMAS:
        private_before = bounded(packet / f"{kind}-status-before.txt", 64 * 1024)
        private_after = bounded(packet / f"{kind}-status-after.txt", 64 * 1024)
        require(private_before == private_after, f"{kind} helper changed during A")
        private_status, _ = parse_status_exact(private_before, kind)
        if kind == "apsc":
            collector.check_unarmed_ready(private_status, events, wfi)
            require(all(private_status.get(key) == value for key, value in {
                "cluster0_cpus": "0xf", "cluster1_cpus": "0xf0",
                "cluster0_cmd_phys": "0x210e20020",
                "cluster1_cmd_phys": "0x211e20020",
                "cluster0_resource_size": "0x1000",
                "cluster1_resource_size": "0x1000",
            }.items()), "ABI 3 A topology differs")
        public[f"{kind}-status-before.txt"] = sanitized_status(private_before, kind)
        public[f"{kind}-status-after.txt"] = sanitized_status(private_after, kind)
    check_public_statuses(public)
    require(json_file(packet, "stream-status-check.json") == {"unarmed": True},
            "A stream check differs")
    summary = json_file(packet, "acquisition-summary.json")
    control = control_fields()
    require(type(summary) is dict and summary.get("phase") == "A" and
            summary.get("mode") == "baseline" and summary.get("result") == "clean" and
            all(summary.get(key) == value for key, value in control.items()) and
            summary.get("abi3_validator_summary") is None and
            summary.get("interpretation") ==
            "raw record integrity only; no WFI-instruction state proof",
            "A is not a clean, unarmed baseline")
    schedule = json_file(packet, "schedule.json")
    require(type(schedule) is dict and set(schedule) == {
        "workers", "start_monotonic_ns", "period_ns", "pulses", "iterations",
        "duration_ms", "arm_offset_ns"} and
        schedule["workers"] == [1, 5] and
        type(schedule["start_monotonic_ns"]) is int and
        schedule["start_monotonic_ns"] > 0 and
        schedule["period_ns"] == collector.PERIOD_NS and
        schedule["pulses"] == collector.PULSES and
        schedule["iterations"] == collector.ITERATIONS and
        schedule["duration_ms"] == collector.DURATION_MS and
        schedule["arm_offset_ns"] == 150_000_000, "A schedule changed")
    markers = json_file(packet, "window-markers.json")
    require(type(markers) is dict and
            markers == {"source": "userspace", "start_ns": markers.get("start_ns"),
                        "stop_ns": markers.get("stop_ns"), **control} and
            type(markers["start_ns"]) is type(markers["stop_ns"]) is int and
            schedule["start_monotonic_ns"] < markers["start_ns"] < markers["stop_ns"] and
            9_900_000_000 <= markers["stop_ns"] - markers["start_ns"] <= 12_500_000_000,
            "A unarmed window markers differ")
    interior = (markers["start_ns"], markers["stop_ns"])
    timeline = check_timeline(packet, *interior)
    workloads = {}
    for cpu in (1, 5):
        name = f"workload-cpu{cpu}.csv"
        raw = bounded(packet / name, 64 * 1024)
        workloads[str(cpu)] = collector.validate_workload_csv(
            raw, cpu, schedule["start_monotonic_ns"], interior)
        require(bounded(packet / f"workload-cpu{cpu}.stderr", 64 * 1024) == b"",
                f"CPU{cpu} emitted workload stderr")
        public[f"{name}.gz"] = gzip.compress(
            project_workload(raw, cpu, schedule["start_monotonic_ns"], interior),
            compresslevel=9, mtime=0)
    sequence = collector.check_workload_checksums(workloads, None)
    require(json_file(packet, "workload-check.json") == workloads and
            summary.get("workloads") == workloads and
            json_file(packet, "workload-checksum-match.json") == {
                "cpu1_cpu5_equal": True, "prior_phase_equal": False,
                "sequence_sha256": sequence},
            "saved worker checks differ from replay")
    environment = check_environment(packet)
    baseline = {
        "schema": "abi3-a-baseline-projection-v1", "phase": "A",
        "observer_abi": 3, "observer_state_before_after": ["ready", "ready"],
        "observer_armed": False, "observer_control_write_attempted": False,
        "observer_event_rows": 0, "observer_wfi_event_rows": 0,
        "observer_streams_zero_and_loss_free": True,
        "pcpm_and_counter_helpers_unused": True,
        "window_source": "userspace CLOCK_MONOTONIC",
        "window_start_relative_to_schedule_ns": interior[0] - schedule["start_monotonic_ns"],
        "window_stop_relative_to_schedule_ns": interior[1] - schedule["start_monotonic_ns"],
        "window_duration_ns": interior[1] - interior[0],
        "workers": {cpu: {"pulses": check["pulses"],
                          "interior_pulses": check["interior_pulses"],
                          "work_ns": check["work_ns"],
                          "interior_work_ns": check["interior_work_ns"],
                          "checksum_sequence_sha256": check["checksum_sequence_sha256"]}
                    for cpu, check in workloads.items()},
        "user_current_boot_wifi_and_visible_brightness_receipt_checked": True,
        "interpretation": "unarmed work baseline; no WFI-instruction state or causal power claim",
    }
    public["baseline.json"] = encode_json(baseline)
    public["environment.json"] = encode_json(environment)
    public["timeline.json"] = encode_json({
        "schema": "abi3-a-timeline-projection-v1", "relative_to": "window_start",
        "events": timeline})
    artifact_inputs = {
        "baseline.json": ("acquisition-summary.json", "apsc-status-before.txt",
                          "apsc-status-after.txt", "apsc-events.csv", "apsc-wfi-events.csv",
                          "pcpm-status-before.txt", "pcpm-status-after.txt",
                          "counter-status-before.txt", "counter-status-after.txt",
                          "schedule.json", "window-markers.json", "stream-status-check.json",
                          "workload-check.json", "workload-checksum-match.json",
                          "user-boot-qualification-check.json"),
        "environment.json": ("environment-before.json", "environment-after.json",
                             "environment-drift.json", "power-at-arm.json",
                             "power-at-window-end.json"),
        "timeline.json": ("timeline.jsonl", "window-markers.json"),
        "workload-cpu1.csv.gz": ("workload-cpu1.csv", "schedule.json",
                                 "window-markers.json"),
        "workload-cpu5.csv.gz": ("workload-cpu5.csv", "schedule.json",
                                 "window-markers.json"),
        "apsc-events.csv.gz": ("apsc-events.csv",),
        "apsc-wfi-events.csv.gz": ("apsc-wfi-events.csv",),
        **{f"{kind}-status-{point}.txt": (f"{kind}-status-{point}.txt",)
           for kind in STATUS_SCHEMAS for point in ("before", "after")},
    }
    receipt = {
        "schema": "abi3-a-publication-receipt-v2",
        "private_manifest_sha256": manifest_sha,
        "private_packet_phase": "A",
        "source_collector_sha256": entries["collector-source.py"],
        "source_workload_sha256": entries["workload-binary"],
        "source_user_visual_receipt_sha256": visual_sha,
        "source_identity_sha256": entries["expected-identity.json"],
        "qualified_build": {
            "release": identity["release"],
            "gnu_build_id": identity["build_id"],
            "config_sha256": identity["config_sha256"],
            "source_tree_sha256": identity["source_tree_sha256"],
            "patch_sha256": identity["patch_sha256"],
            "image_sha256": identity["image_sha256"],
            "uki_sha256": identity["uki_sha256"],
        },
        "artifacts": {name: {
            "public_sha256": digest(public[name]),
            "private_inputs_sha256": {source: entries[source] for source in sources},
        } for name, sources in artifact_inputs.items()},
        "projection": "fixed A numerical fields; relative worker times; no raw boot, account, network, USB, command line or kernel log content",
    }
    public["publication-receipt.json"] = encode_json(receipt)
    require(set(public) == set(PUBLIC_NAMES), "internal public file set changed")
    for name, data in public.items():
        require(PRIVATE_TEXT.search(data) is None, f"private-looking content in {name}")
    final_entries, final_manifest_sha = verify_manifest(packet)
    require(final_entries == entries and final_manifest_sha == manifest_sha,
            "private packet changed during publication projection")
    return public


def encode_json(value) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n").encode()


def write_stage(public: dict[str, bytes], packet: Path, out: Path) -> None:
    require(out.is_absolute() and not out.exists() and not out.is_symlink(),
            "output must be a new absolute directory")
    parent = out.parent
    require(parent.is_dir() and not parent.is_symlink(), "output parent must exist")
    require(os.path.commonpath((str(packet.resolve()), str(out.resolve()))) !=
            str(packet.resolve()), "output cannot be inside the private packet")
    staging = Path(tempfile.mkdtemp(prefix=".abi3-A-stage-", dir=parent))
    try:
        staging.chmod(0o700)
        for name, data in sorted(public.items()):
            target = staging / name
            with target.open("xb") as stream:
                stream.write(data)
            target.chmod(0o600)
        lines = [f"{file_digest(staging / name)}  {name}" for name in sorted(public)]
        (staging / "MANIFEST.sha256").write_text("\n".join(lines) + "\n")
        (staging / "MANIFEST.sha256").chmod(0o600)
        verify_public_stage(staging)
        require(not out.exists() and not out.is_symlink(), "output appeared during staging")
        staging.rename(out)
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def verify_public_stage(stage: Path) -> None:
    manifest = bounded(stage / "MANIFEST.sha256")
    require(manifest.endswith(b"\n"), "public manifest unterminated")
    names = set()
    for line in manifest.decode("ascii").splitlines():
        match = ENTRY.fullmatch(line)
        require(match is not None, "malformed public manifest")
        sha, name = match.groups()
        require(name in PUBLIC_NAMES and name not in names and
                file_digest(stage / name) == sha, "public stage hash/file mismatch")
        names.add(name)
    actual = {p.name for p in stage.iterdir()}
    require(names == set(PUBLIC_NAMES) and
            actual in (names | {"MANIFEST.sha256"},
                       names | {"MANIFEST.sha256", "README.md"}) and
            ("README.md" not in actual or
             ((stage / "README.md").is_file() and
              not (stage / "README.md").is_symlink())),
            "public stage file set changed")
    staged = {name: bounded(stage / name, 1024 * 1024) for name in names}
    for name, data in staged.items():
        if name.endswith(".gz"):
            data = gunzip_bounded(data, 1024 * 1024)
        require(PRIVATE_TEXT.search(data) is None, f"private-looking public content: {name}")
    check_public_statuses(staged)
    receipt = json.loads(staged["publication-receipt.json"])
    qualified = receipt.get("qualified_build", {})
    require(receipt.get("schema") == "abi3-a-publication-receipt-v2" and
            set(receipt.get("artifacts", {})) == names - {"publication-receipt.json"} and
            all(receipt["artifacts"][name]["public_sha256"] ==
                file_digest(stage / name) for name in receipt["artifacts"]) and
            set(qualified) == {"release", "gnu_build_id", "config_sha256",
                               "source_tree_sha256", "patch_sha256", "image_sha256",
                               "uki_sha256"} and
            re.fullmatch(r"7\.1\.12-ARCH-apsc-[A-Za-z0-9._-]{1,80}",
                         qualified["release"]) is not None and
            re.fullmatch(r"[0-9a-f]{40}", qualified["gnu_build_id"]) is not None and
            all(isinstance(qualified[key], str) and HEX64.fullmatch(qualified[key])
                for key in ("config_sha256", "source_tree_sha256", "patch_sha256",
                            "image_sha256", "uki_sha256")),
            "public receipt artifact hashes differ")
    baseline = json.loads((stage / "baseline.json").read_bytes())
    require(baseline.get("schema") == "abi3-a-baseline-projection-v1" and
            baseline.get("phase") == "A" and baseline.get("observer_armed") is False and
            baseline.get("observer_control_write_attempted") is False and
            baseline.get("observer_state_before_after") == ["ready", "ready"] and
            baseline.get("observer_event_rows") ==
            baseline.get("observer_wfi_event_rows") == 0 and
            baseline.get("observer_streams_zero_and_loss_free") is True and
            baseline.get("pcpm_and_counter_helpers_unused") is True,
            "public A baseline schema differs")
    window = (baseline["window_start_relative_to_schedule_ns"],
              baseline["window_stop_relative_to_schedule_ns"])
    require(type(window[0]) is type(window[1]) is int and window[0] < window[1],
            "public window invalid")
    for cpu in (1, 5):
        raw = gunzip_bounded(bounded(stage / f"workload-cpu{cpu}.csv.gz"),
                             1024 * 1024)
        reader = csv.DictReader(io.StringIO(raw.decode("ascii")))
        rows = list(reader)
        require(reader.fieldnames == ["cpu", "pulse", "iterations", "relative_start_ns",
                                       "duration_ns", "checksum", "fully_inside_window"] and
                len(rows) == collector.PULSES, "public workload shape differs")
        interior_count = work_ns = interior_work_ns = 0
        checksums = []
        for pulse, row in enumerate(rows):
            require(None not in row and all(value is not None and
                    re.fullmatch(r"[0-9]+", value) for value in row.values()),
                    "public workload value malformed")
            number = {key: int(value) for key, value in row.items()}
            begin = number["relative_start_ns"]
            duration = number["duration_ns"]
            inside = int(window[0] < begin and begin + duration < window[1])
            require(number["cpu"] == cpu and number["pulse"] == pulse and
                    number["iterations"] == collector.ITERATIONS and
                    pulse * collector.PERIOD_NS <= begin and
                    begin + duration < (pulse + 1) * collector.PERIOD_NS and
                    number["fully_inside_window"] == inside and
                    0 <= number["checksum"] < 1 << 64,
                    "public workload failed relative replay")
            work_ns += duration
            interior_count += inside
            interior_work_ns += inside * duration
            checksums.append(number["checksum"])
        sequence = digest("".join(f"{pulse}:{checksum}\n" for pulse, checksum
                                  in enumerate(checksums)).encode())
        require(baseline["workers"][str(cpu)] == {
            "pulses": collector.PULSES, "interior_pulses": interior_count,
            "work_ns": work_ns, "interior_work_ns": interior_work_ns,
            "checksum_sequence_sha256": sequence},
            "public workload aggregate differs from replay")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", type=Path, help="sealed private ABI 3 A packet")
    parser.add_argument("--out", type=Path, help="new review staging directory")
    parser.add_argument("--verify-public-stage", type=Path,
                        help="replay an existing published A directory without private inputs")
    args = parser.parse_args()
    try:
        verify_public_source_binding()
        if args.verify_public_stage is not None:
            require(args.packet is None and args.out is None,
                    "public-stage replay cannot also stage a private packet")
            stage = args.verify_public_stage
            verify_public_stage(stage)
            print(json.dumps({"verified": str(stage), "phase": "A",
                              "public_manifest_sha256": file_digest(stage / "MANIFEST.sha256")},
                             sort_keys=True))
            return 0
        require(args.packet is not None and args.out is not None,
                "--packet and --out are required for staging")
        packet = args.packet.absolute()
        public = build_public(packet)
        write_stage(public, packet, args.out)
    except (PublicationError, collector.CaptureError, OSError, ValueError, KeyError,
            TypeError, UnicodeError) as error:
        parser.exit(2, f"A publication rejected: {error}\n")
    print(json.dumps({"staged": str(args.out), "phase": "A",
                      "public_manifest_sha256": file_digest(args.out / "MANIFEST.sha256")},
                     sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
