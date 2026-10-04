#!/usr/bin/env python3
"""Offline, fail-closed projection and public replay of ABI 3 E evidence.

This public review copy has no debugfs, control, worker, or live-kernel
operations. It reads sealed E, D and A packets to write a new review stage,
or replays a public E stage without private inputs.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile

import capture_abi3 as collector
import publish_abi3_a as a
import publish_abi3_d as d


HERE = Path(__file__).resolve().parent
VALIDATOR_SOURCE = HERE.parent / "abi3-prototype" / "validate_tickets.py"
E_PUBLISHER_REDACTION = HERE / "E-PUBLISHER-REDACTION-RECEIPT.json"
spec = importlib.util.spec_from_file_location("abi3_public_validate_tickets", VALIDATOR_SOURCE)
if spec is None or spec.loader is None:
    raise RuntimeError("public ABI 3 validator source unavailable")
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


PACKET_NAME = re.compile(r"abi3-E-[0-9TZ]+\Z")
REQUIRED_E = d.REQUIRED_D
PUBLIC_NAMES = (
    "capture.json", "environment.json", "timeline.json",
    "validator-report.json", "workload-cpu1.csv.gz", "workload-cpu5.csv.gz",
    "apsc-status-before.txt", "apsc-status-after.txt",
    "pcpm-status-before.txt", "pcpm-status-after.txt",
    "counter-status-before.txt", "counter-status-after.txt",
    "apsc-events.csv.gz", "apsc-wfi-events.csv.gz", "publication-receipt.json",
)
CONTROL = collector.control_disposition({"state": collector.CONTROL_WRITE_COMPLETED})
INTERPRETATION = "raw record integrity only; no WFI-instruction state proof"
MAX_STREAM = collector.MAX_RAW
MAX_STAGE_FILE = collector.MAX_RAW
EVENT_KINDS = {"idle_enter", "idle_exit", "cpu_pm_fail", "dvfs"}
SAFE_CELL = re.compile(r"(?:|-?(?:0|[1-9][0-9]{0,19})|0x[0-9a-fA-F]{1,16})\Z")


def require(ok: bool, message: str) -> None:
    a.require(ok, message)


def verify_public_source_binding() -> None:
    """Bind this review copy to the reviewed A/D and collector sources."""
    d.verify_public_source_binding()
    receipt = json.loads(a.bounded(E_PUBLISHER_REDACTION, 64 * 1024),
                         object_pairs_hook=a.unique_object)
    require(receipt.get("schema") == "abi3-e-publisher-public-copy-v1" and
            isinstance(receipt.get("private_publisher_sha256"), str) and
            a.HEX64.fullmatch(receipt["private_publisher_sha256"]) is not None and
            receipt.get("public_publisher_sha256") == a.file_digest(Path(__file__)) and
            receipt.get("d_publisher_redaction_receipt_sha256") ==
            a.file_digest(d.D_PUBLISHER_REDACTION) and
            receipt.get("public_d_publisher_sha256") ==
            a.file_digest(Path(d.__file__)) and
            receipt.get("a_publisher_redaction_receipt_sha256") ==
            a.file_digest(a.PUBLISHER_REDACTION) and
            receipt.get("collector_redaction_receipt_sha256") ==
            a.file_digest(a.COLLECTOR_REDACTION) and
            receipt.get("private_collector_sha256") == a.reviewed_collector_hash() and
            receipt.get("public_collector_sha256") ==
            a.file_digest(Path(collector.__file__)) and
            receipt.get("validator_source_sha256") ==
            a.file_digest(VALIDATOR_SOURCE),
            "public E publisher differs from reviewed source receipt")


def exact_status(raw: bytes, kind: str, point: str, public: bool = False):
    """Allow only the fixed status key set and narrow, key-specific grammar."""
    if kind != "apsc":
        return a.parse_status_exact(raw, kind, public)
    expected = a.APSC_PUBLIC_KEYS if public else a.APSC_FULL_KEYS
    require(raw.endswith(b"\n") and b"\r" not in raw, "APSC status newline changed")
    parsed, lines = {}, []
    literals = {"abi": "3", "state": "ready" if point == "before" else "complete",
                "mode": "records" if point == "before" else "wfi_mmio"}
    for line in raw.splitlines(keepends=True):
        try:
            text = line[:-1].decode("ascii")
        except UnicodeError as error:
            raise a.PublicationError("non-ASCII APSC status") from error
        key, separator, value = text.partition("=")
        require(separator == "=" and key in expected and key not in parsed,
                "APSC status key set changed")
        if key in literals:
            require(value == literals[key], f"APSC {point} literal changed: {key}")
        elif key in a.APSC_HEX_KEYS:
            require(re.fullmatch(r"0x[0-9a-f]{1,16}", value) is not None,
                    f"APSC hex value invalid: {key}")
        else:
            require(re.fullmatch(r"-?(?:0|[1-9][0-9]{0,19})", value) is not None,
                    f"APSC number invalid: {key}")
        parsed[key] = value
        lines.append((key, line))
    require(set(parsed) == expected, "APSC status key set changed")
    return parsed, lines


def sanitized_status(raw: bytes, kind: str, point: str) -> bytes:
    _, lines = exact_status(raw, kind, point)
    result = b"".join(line for key, line in lines if key in a.STATUS_SCHEMAS[kind][1])
    exact_status(result, kind, point, public=True)
    return result


def exact_stream(raw: bytes, kind: str) -> None:
    """Gate every raw CSV cell before byte-exact publication.

    The ticket validator deliberately ignores some fields for some record
    kinds; this gate keeps those fields from becoming a text exfiltration path.
    """
    header = collector.EVENT_HEADER if kind == "events" else collector.WFI_HEADER
    require(raw.endswith(b"\n") and b"\r" not in raw and b'"' not in raw and
            b"\\" not in raw and b"\0" not in raw,
            f"{kind} CSV bytes changed")
    try:
        text = raw.decode("ascii")
    except UnicodeError as error:
        raise a.PublicationError(f"non-ASCII {kind} CSV") from error
    lines = text.splitlines()
    require(lines and lines[0] == header, f"{kind} CSV header changed")
    keys = header.split(",")
    for number, line in enumerate(lines[1:], 2):
        cells = line.split(",")
        require(len(cells) == len(keys), f"{kind}:{number} column count changed")
        row = dict(zip(keys, cells))
        if kind == "events":
            require(row["kind"] in EVENT_KINDS, f"events:{number} kind changed")
        else:
            require(row["mode"] == "wfi_mmio" and row["cmd_valid"] == "1" and
                    re.fullmatch(r"0x[0-9a-fA-F]{1,16}", row["cmd"]) is not None,
                    f"wfi:{number} has no raw MMIO command word")
        for key, value in row.items():
            if key in ("kind", "mode"):
                continue
            require(SAFE_CELL.fullmatch(value) is not None,
                    f"{kind}:{number} unsafe {key} cell")


def verify_e_manifest(packet: Path) -> tuple[dict[str, str], str]:
    require(PACKET_NAME.fullmatch(packet.name) is not None,
            "expected an ABI 3 E packet")
    require(packet.is_dir() and not packet.is_symlink() and
            stat.S_IMODE(packet.stat().st_mode) == 0o700,
            "private E packet must be a 0700 directory")
    manifest = packet / "MANIFEST.sha256"
    require(manifest.is_file() and not manifest.is_symlink() and
            stat.S_IMODE(manifest.stat().st_mode) == 0o600 and
            manifest.stat().st_uid == packet.stat().st_uid,
            "private E manifest ownership/mode changed")
    raw = a.bounded(manifest)
    require(raw and raw.endswith(b"\n"), "private E manifest unterminated")
    try:
        lines = raw.decode("ascii").splitlines()
    except UnicodeError as error:
        raise a.PublicationError("non-ASCII private E manifest") from error
    entries = {}
    for line in lines:
        match = a.ENTRY.fullmatch(line)
        require(match is not None, "malformed private E manifest")
        sha, name = match.groups()
        require(name not in entries and name != "MANIFEST.sha256",
                "duplicate/unsafe private E name")
        item = packet / name
        require(item.is_file() and not item.is_symlink() and
                item.stat().st_uid == packet.stat().st_uid and
                stat.S_IMODE(item.stat().st_mode) == 0o600,
                f"nonregular or permissive private E item: {name}")
        require(a.file_digest(item) == sha, f"private E manifest mismatch: {name}")
        entries[name] = sha
    require(set(entries) | {"MANIFEST.sha256"} == {p.name for p in packet.iterdir()} and
            REQUIRED_E <= set(entries), "private E packet file set changed")
    return entries, a.digest(raw)


def check_provenance(packet: Path, entries: dict[str, str], prior: Path,
                     prior_entries: dict[str, str], prior_manifest_sha: str,
                     prior_identity: dict, first_a_visual_sha: str) -> tuple[dict, str]:
    identity = collector.identity_schema(packet / "expected-identity.json")
    require(identity == prior_identity, "E build identity differs from sealed D")
    immutable = (
        "expected-identity.json", "source-hashes.json", "collector-source.py",
        "workload-source.c", "workload-binary", "validator-source.py",
        "patch-source.bin", "source_receipt-source.bin", "linked_receipt-source.bin",
        "running.config", "config.gz", "kernel-notes.bin", "limine.conf",
        "installed-image-hashes.json",
    )
    require(all(entries[name] == prior_entries[name] for name in immutable),
            "E build/source/installed image evidence differs from sealed D")
    require(("Current Entry: " + identity["entry_title"] + "\n").encode() in
            a.bounded(packet / "bootctl.stdout") and
            b"0 altered files" in a.bounded(packet / "module-package-check.stdout") and
            a.bounded(packet / "kernel-log-before.stdout").strip() and
            a.bounded(packet / "kernel-log-after.stdout").strip(),
            "E boot selection, module or log evidence absent")
    boot_id = a.bounded(packet / "boot-id.txt", 128).decode("ascii").strip()
    prior_boot_id = a.bounded(prior / "boot-id.txt", 128).decode("ascii").strip()
    require(collector.BOOT_ID_PATTERN.fullmatch(boot_id) is not None and
            boot_id != prior_boot_id, "E did not use a fresh boot")
    require(a.json_file(packet, "prior-packet-gate.json") == {
        "prior_manifest_sha256": prior_manifest_sha, "prior_phase": "D",
        "prior_boot_id": prior_boot_id, "current_boot_id": boot_id,
    }, "E prior-packet gate differs")
    _, receipt_raw = collector.boot_qualification(
        packet / "user-boot-qualification.json", boot_id, identity,
        "E", first_a_visual_sha)
    require(a.json_file(packet, "user-boot-qualification-check.json") == {
        "phase": "E", "receipt_sha256": a.digest(receipt_raw),
        "current_boot_id": boot_id, "current_boot_wifi_user_confirmed": True,
        "current_boot_visible_brightness_confirmed": False,
        "brightness_visible_checked_on_first_abi3_boot": True,
        "first_a_visual_receipt_sha256": first_a_visual_sha,
        "current_boot_backlight_readback_expected": "155",
    }, "E current-boot user qualification binding differs")
    previous = a.json_file(prior, "environment-before.json")
    before = a.json_file(packet, "environment-before.json")
    require(all(before[key] == previous[key] for key in (
        "ac_online", "backlight_interface_present", "brightness", "online_cpus",
        "cpuidle_driver", "cpuidle_governor", "cpuidle_state1_disabled", "policies")),
        "E policy/power baseline differs from D")
    return identity, a.digest(receipt_raw)


def check_timeline(packet: Path, start: int, stop: int) -> list[dict]:
    raw = a.bounded(packet / "timeline.jsonl", 4 * 1024 * 1024)
    require(raw.endswith(b"\n"), "E timeline unterminated")
    try:
        rows = [json.loads(line, object_pairs_hook=a.unique_object)
                for line in raw.splitlines()]
    except (UnicodeError, json.JSONDecodeError) as error:
        raise a.PublicationError("invalid E timeline") from error
    wanted = ["begin", "window_begin", "capture_write_begin",
              "capture_write_attempted", "capture_write_end", "window_end",
              "observer_raw_drained", "workload_release_begin",
              "workload_release_end", "workload_release_end", "complete"]
    auxiliary = {"read_begin", "read_end", "command_begin", "command_end"}
    actions = [row.get("action") for row in rows]
    require(actions and actions[0] == "begin" and actions[-1] == "complete" and
            set(actions) <= set(wanted) | auxiliary,
            "E timeline has an unknown or failed action")
    for index, action in enumerate(actions):
        if action in {"read_begin", "command_begin"}:
            require(index + 1 < len(actions) and
                    actions[index + 1] == action.removesuffix("begin") + "end",
                    "E timeline auxiliary action is unpaired")
        elif action in {"read_end", "command_end"}:
            require(index > 0 and
                    actions[index - 1] == action.removesuffix("end") + "begin",
                    "E timeline auxiliary action is unpaired")
    primary = [row for row in rows if row.get("action") in wanted]
    require([row["action"] for row in primary] == wanted,
            "E timeline failed, repeated, or changed action sequence")
    ticks = [row.get("monotonic_ns") for row in rows]
    require(all(type(tick) is int and tick > 0 for tick in ticks) and
            ticks == sorted(ticks), "E timeline ticks invalid")
    require(primary[0].get("phase") == primary[-1].get("phase") == "E" and
            primary[1].get("phase") == "E" and primary[1].get("mode") == "wfi_mmio" and
            primary[2].get("command") == "wfi_mmio 10000" and
            primary[3].get("bytes") == len(b"wfi_mmio 10000\n") and
            all(primary[4].get(key) == value for key, value in CONTROL.items()) and
            primary[6].get("errors") == [] and
            primary[7].get("token") == "E" and
            primary[7].get("reason") == "window_ended" and
            primary[7].get("cpus") == [1, 5] and
            {row.get("cpu") for row in primary[8:10]} == {1, 5} and
            all(row.get("exit_status") == 0 for row in primary[8:10]) and
            primary[1]["monotonic_ns"] <= start < stop <= primary[5]["monotonic_ns"],
            "E write/window/drain/release timeline differs")
    return [{"action": row["action"],
             "relative_monotonic_ns": row["monotonic_ns"] - start,
             **({"cpu": row["cpu"], "exit_status": 0}
                if row["action"] == "workload_release_end" else {})}
            for row in primary]


def validator_result(status: bytes, events: bytes, wfi: bytes) -> dict:
    exact_stream(events, "events")
    exact_stream(wfi, "wfi")
    try:
        result = validator.analyze(status.decode("ascii"), events.decode("ascii"),
                                   wfi.decode("ascii"))
    except (UnicodeError, validator.TicketError) as error:
        raise a.PublicationError(f"ticket validator rejected E: {error}") from error
    require(result["abi"] == 3 and result["mode"] == "wfi_mmio" and
            result["busy_rows"] == len(result["busy_screen"]) and
            result["candidate_count"] == len(result["witnesses"]) and
            result["candidate_count"] <= result["busy_rows"] <= result["wfi_rows"],
            "E ticket report counts are inconsistent")
    return {**result, "input_sha256": {
        "status": a.digest(status), "events": a.digest(events),
        "wfi_events": a.digest(wfi)}}


def worker_aggregates(workloads: dict) -> dict:
    return {cpu: {"pulses": check["pulses"],
                  "interior_pulses": check["interior_pulses"],
                  "work_ns": check["work_ns"],
                  "interior_work_ns": check["interior_work_ns"],
                  "checksum_sequence_sha256": check["checksum_sequence_sha256"]}
            for cpu, check in workloads.items()}


def build_public(packet: Path, prior_d: Path, prior_a: Path) -> dict[str, bytes]:
    verify_public_source_binding()
    entries, manifest_sha = verify_e_manifest(packet)
    # Replay the whole D publication gate, including its sealed A ancestry.
    # A manifest hash alone would allow an internally inconsistent predecessor.
    d.build_public(prior_d, prior_a)
    prior_entries, prior_manifest_sha = d.verify_d_manifest(prior_d)
    a_entries, a_manifest_sha = a.verify_manifest(prior_a)
    prior_identity = collector.identity_schema(prior_d / "expected-identity.json")
    _, first_visual_sha = a.check_provenance(prior_a, a_entries)
    identity, user_receipt_sha = check_provenance(
        packet, entries, prior_d, prior_entries, prior_manifest_sha,
        prior_identity, first_visual_sha)
    require(a.bounded(packet / "boot-id.txt", 128) !=
            a.bounded(prior_a / "boot-id.txt", 128),
            "E reused the earlier A boot")
    require(a.file_digest(Path(validator.__file__)) == entries["validator-source.py"],
            "offline validator source differs from captured validator")
    events = a.bounded(packet / "apsc-events.csv", MAX_STREAM)
    wfi = a.bounded(packet / "apsc-wfi-events.csv", MAX_STREAM)
    public = {
        "apsc-events.csv.gz": gzip.compress(events, compresslevel=9, mtime=0),
        "apsc-wfi-events.csv.gz": gzip.compress(wfi, compresslevel=9, mtime=0),
    }
    statuses = {}
    for kind in a.STATUS_SCHEMAS:
        before_raw = a.bounded(packet / f"{kind}-status-before.txt", 64 * 1024)
        after_raw = a.bounded(packet / f"{kind}-status-after.txt", 64 * 1024)
        before, _ = exact_status(before_raw, kind, "before")
        after, _ = exact_status(after_raw, kind, "after")
        if kind != "apsc":
            require(before_raw == after_raw, f"E {kind} helper changed")
        statuses[kind] = (before, after)
        public[f"{kind}-status-before.txt"] = sanitized_status(before_raw, kind, "before")
        public[f"{kind}-status-after.txt"] = sanitized_status(after_raw, kind, "after")
    ready, complete = statuses["apsc"]
    collector.check_unarmed_ready(ready, (collector.EVENT_HEADER + "\n").encode(),
                                  (collector.WFI_HEADER + "\n").encode())
    require(all(ready.get(key) == value for key, value in {
        "cluster0_cpus": "0xf", "cluster1_cpus": "0xf0",
        "cluster0_cmd_phys": "0x210e20020", "cluster1_cmd_phys": "0x211e20020",
        "cluster0_resource_size": "0x1000", "cluster1_resource_size": "0x1000",
    }.items()), "E APSC ready topology differs")
    collector.check_aux_unused(a.bounded(packet / "pcpm-status-after.txt", 64 * 1024),
                               a.bounded(packet / "counter-status-after.txt", 64 * 1024))
    stream_check = collector.check_stream_status(complete, "wfi_mmio")
    require(a.json_file(packet, "stream-status-check.json") == stream_check,
            "saved E stream check differs")
    private_report = validator_result(
        a.bounded(packet / "apsc-status-after.txt", 64 * 1024), events, wfi)
    require(a.json_file(packet, "abi3-validator-report.json") == private_report,
            "saved private ticket report differs from independent replay")
    require(a.bounded(packet / "abi3-validator.stderr", 64 * 1024) == b"" and
            json.loads(a.bounded(packet / "abi3-validator.stdout", 1024 * 1024),
                       object_pairs_hook=a.unique_object) ==
            private_report, "captured validator command output differs")
    public_report = validator_result(public["apsc-status-after.txt"], events, wfi)
    public["validator-report.json"] = a.encode_json(public_report)
    summary = a.json_file(packet, "acquisition-summary.json")
    require(type(summary) is dict and summary.get("phase") == "E" and
            summary.get("mode") == "wfi_mmio" and summary.get("result") == "clean" and
            all(summary.get(key) == value for key, value in CONTROL.items()) and
            summary.get("abi3_validator_summary") == {
                "busy_rows": private_report["busy_rows"],
                "candidate_count": private_report["candidate_count"],
                "report_sha256": entries["abi3-validator-report.json"]} and
            summary.get("interpretation") == INTERPRETATION,
            "E is not a clean, consumed WFI-MMIO capture")
    schedule = a.json_file(packet, "schedule.json")
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
        schedule["arm_offset_ns"] == 150_000_000,
        "E schedule changed")
    start, stop = stream_check["inside_start_ns"], stream_check["inside_stop_ns"]
    markers = a.json_file(packet, "window-markers.json")
    require(markers == {"source": "kernel-CLOCK_MONOTONIC",
                        "start_ns": start, "stop_ns": stop, **CONTROL} and
            schedule["start_monotonic_ns"] < start < stop and
            9_900_000_000 <= stop - start <= 12_500_000_000,
            "E kernel window markers differ")
    timeline = check_timeline(packet, start, stop)
    workloads = {}
    for cpu in (1, 5):
        name = f"workload-cpu{cpu}.csv"
        raw = a.bounded(packet / name, 64 * 1024)
        workloads[str(cpu)] = collector.validate_workload_csv(
            raw, cpu, schedule["start_monotonic_ns"], (start, stop))
        require(a.bounded(packet / f"workload-cpu{cpu}.stderr", 64 * 1024) == b"",
                f"E CPU{cpu} emitted stderr")
        public[f"{name}.gz"] = gzip.compress(a.project_workload(
            raw, cpu, schedule["start_monotonic_ns"], (start, stop)),
            compresslevel=9, mtime=0)
    prior_workloads = a.json_file(prior_d, "workload-check.json")
    sequence = collector.check_workload_checksums(workloads, prior_workloads)
    require(a.json_file(packet, "workload-check.json") == workloads and
            summary.get("workloads") == workloads and
            a.json_file(packet, "workload-checksum-match.json") == {
                "cpu1_cpu5_equal": True, "prior_phase_equal": True,
                "sequence_sha256": sequence},
            "E saved worker checks differ from replay/D")
    environment = a.check_environment(packet)
    environment["schema"] = "abi3-e-environment-projection-v1"
    public["environment.json"] = a.encode_json(environment)
    public["timeline.json"] = a.encode_json({
        "schema": "abi3-e-timeline-projection-v1",
        "relative_to": "window_start", "events": timeline})
    capture = {
        "schema": "abi3-e-capture-projection-v1", "phase": "E", "mode": "wfi_mmio",
        "observer_abi": 3, "observer_state_before_after": ["ready", "complete"],
        "observer_armed": True, "observer_control_write_completed": True,
        "one_shot_consumption": "confirmed",
        "first_attempt_pre_dsb_command_reads": private_report["wfi_rows"],
        "raw_wfi_busy_rows": private_report["busy_rows"],
        "raw_wfi_clear_rows": private_report["wfi_rows"] - private_report["busy_rows"],
        "rejected_busy_rows": private_report["busy_rows"] - private_report["candidate_count"],
        "observer_event_rows": private_report["idle_rows"],
        "observer_wfi_event_rows": private_report["wfi_rows"],
        "observer_streams_loss_free": True,
        "pcpm_and_counter_helpers_unused": True,
        "validator_busy_rows": private_report["busy_rows"],
        "validator_candidate_count": private_report["candidate_count"],
        "window_source": "kernel-CLOCK_MONOTONIC",
        "window_start_relative_to_schedule_ns": start - schedule["start_monotonic_ns"],
        "window_stop_relative_to_schedule_ns": stop - schedule["start_monotonic_ns"],
        "window_duration_ns": stop - start,
        "workers": worker_aggregates(workloads),
        "user_current_boot_wifi_receipt_checked": True,
        "first_a_visual_receipt_proof_checked": True,
        "interpretation": "read-only APSC command samples at first-attempt pre-DSB seam; ticket-qualified software-hook candidates only; no WFI-instruction state, physical power state, energy, or wake proof",
    }
    public["capture.json"] = a.encode_json(capture)
    artifact_inputs = {
        "capture.json": ("acquisition-summary.json", "schedule.json", "window-markers.json",
                         "stream-status-check.json", "workload-check.json",
                         "workload-checksum-match.json", "prior-packet-gate.json",
                         "user-boot-qualification-check.json", "abi3-validator-report.json"),
        "environment.json": ("environment-before.json", "environment-after.json",
                             "environment-drift.json", "power-at-arm.json",
                             "power-at-window-end.json"),
        "timeline.json": ("timeline.jsonl", "window-markers.json"),
        "validator-report.json": ("abi3-validator-report.json", "apsc-status-after.txt",
                                  "apsc-events.csv", "apsc-wfi-events.csv"),
        **{f"workload-cpu{cpu}.csv.gz": (f"workload-cpu{cpu}.csv", "schedule.json",
                                         "window-markers.json") for cpu in (1, 5)},
        "apsc-events.csv.gz": ("apsc-events.csv",),
        "apsc-wfi-events.csv.gz": ("apsc-wfi-events.csv",),
        **{f"{kind}-status-{point}.txt": (f"{kind}-status-{point}.txt",)
           for kind in a.STATUS_SCHEMAS for point in ("before", "after")},
    }
    receipt = {
        "schema": "abi3-e-publication-receipt-v1", "private_packet_phase": "E",
        "private_manifest_sha256": manifest_sha,
        "prior_d_manifest_sha256": prior_manifest_sha,
        "prior_a_manifest_sha256": a_manifest_sha,
        "source_collector_sha256": entries["collector-source.py"],
        "source_validator_sha256": entries["validator-source.py"],
        "source_workload_sha256": entries["workload-binary"],
        "source_user_current_boot_receipt_sha256": user_receipt_sha,
        "source_first_a_visual_receipt_sha256": first_visual_sha,
        "source_identity_sha256": entries["expected-identity.json"],
        "qualified_build": {
            "release": identity["release"], "gnu_build_id": identity["build_id"],
            "config_sha256": identity["config_sha256"],
            "source_tree_sha256": identity["source_tree_sha256"],
            "patch_sha256": identity["patch_sha256"],
            "image_sha256": identity["image_sha256"],
            "uki_sha256": identity["uki_sha256"],
        },
        "artifacts": {name: {
            "public_sha256": a.digest(public[name]),
            "private_inputs_sha256": {source: entries[source] for source in sources},
        } for name, sources in artifact_inputs.items()},
        "projection": "whitelisted status lines, byte-exact ticket CSVs with every BUSY and clear command word, full replayed BUSY screen including rejected reasons, relative worker times; no raw boot, account, network, USB, command line or kernel log content",
    }
    public["publication-receipt.json"] = a.encode_json(receipt)
    require(set(public) == set(PUBLIC_NAMES), "internal E public file set changed")
    for name, data in public.items():
        require(a.PRIVATE_TEXT.search(data) is None, f"private-looking content in {name}")
    require(verify_e_manifest(packet) == (entries, manifest_sha) and
            d.verify_d_manifest(prior_d) == (prior_entries, prior_manifest_sha) and
            a.verify_manifest(prior_a) == (a_entries, a_manifest_sha),
            "private A/D/E packet changed during projection")
    return public


def verify_public_stage(stage: Path) -> None:
    verify_public_source_binding()
    require(stage.is_dir() and not stage.is_symlink(), "public E stage absent")
    raw_manifest = a.bounded(stage / "MANIFEST.sha256")
    require(raw_manifest and raw_manifest.endswith(b"\n"), "public E manifest invalid")
    names = set()
    for line in raw_manifest.decode("ascii").splitlines():
        match = a.ENTRY.fullmatch(line)
        require(match is not None, "malformed public E manifest")
        sha, name = match.groups()
        require(name in PUBLIC_NAMES and name not in names and
                (stage / name).is_file() and not (stage / name).is_symlink() and
                a.file_digest(stage / name) == sha,
                "public E manifest hash/file mismatch")
        names.add(name)
    actual = {p.name for p in stage.iterdir()}
    require(names == set(PUBLIC_NAMES) and
            actual in (names | {"MANIFEST.sha256"},
                       names | {"MANIFEST.sha256", "README.md"}) and
            ("README.md" not in actual or
             ((stage / "README.md").is_file() and
              not (stage / "README.md").is_symlink())),
            "public E stage file set changed")
    staged = {name: a.bounded(stage / name, MAX_STAGE_FILE) for name in names}
    decompressed = {name: a.gunzip_bounded(data, MAX_STREAM) if name.endswith(".gz")
                    else data for name, data in staged.items()}
    for name, data in decompressed.items():
        require(a.PRIVATE_TEXT.search(data) is None,
                f"private-looking public E content: {name}")
    receipt = json.loads(staged["publication-receipt.json"],
                         object_pairs_hook=a.unique_object)
    qualified = receipt.get("qualified_build", {})
    require(receipt.get("schema") == "abi3-e-publication-receipt-v1" and
            receipt.get("private_packet_phase") == "E" and
            receipt.get("source_validator_sha256") == a.file_digest(VALIDATOR_SOURCE) and
            set(receipt.get("artifacts", {})) == names - {"publication-receipt.json"} and
            all(receipt["artifacts"][name]["public_sha256"] == a.digest(staged[name])
                for name in receipt["artifacts"]) and
            set(qualified) == {"release", "gnu_build_id", "config_sha256",
                               "source_tree_sha256", "patch_sha256", "image_sha256",
                               "uki_sha256"} and
            re.fullmatch(r"7\.1\.12-ARCH-apsc-[A-Za-z0-9._-]{1,80}",
                         qualified["release"]) is not None and
            re.fullmatch(r"[0-9a-f]{40}", qualified["gnu_build_id"]) is not None and
            all(isinstance(qualified[key], str) and a.HEX64.fullmatch(qualified[key])
                for key in ("config_sha256", "source_tree_sha256", "patch_sha256",
                            "image_sha256", "uki_sha256")),
            "public E receipt hashes/build fields invalid")
    for kind in a.STATUS_SCHEMAS:
        before_raw = decompressed[f"{kind}-status-before.txt"]
        after_raw = decompressed[f"{kind}-status-after.txt"]
        before, _ = exact_status(before_raw, kind, "before", public=True)
        after, _ = exact_status(after_raw, kind, "after", public=True)
        if kind == "apsc":
            collector.check_unarmed_ready(before,
                (collector.EVENT_HEADER + "\n").encode(),
                (collector.WFI_HEADER + "\n").encode())
            stream_check = collector.check_stream_status(after, "wfi_mmio")
        else:
            require(before_raw == after_raw, f"public E {kind} helper changed")
    collector.check_aux_unused(decompressed["pcpm-status-after.txt"],
                               decompressed["counter-status-after.txt"])
    report = validator_result(decompressed["apsc-status-after.txt"],
                              decompressed["apsc-events.csv.gz"],
                              decompressed["apsc-wfi-events.csv.gz"])
    require(json.loads(staged["validator-report.json"],
                       object_pairs_hook=a.unique_object) == report,
            "public E validator report differs from replay")
    capture = json.loads(staged["capture.json"], object_pairs_hook=a.unique_object)
    require(capture.get("schema") == "abi3-e-capture-projection-v1" and
            capture.get("phase") == "E" and capture.get("mode") == "wfi_mmio" and
            capture.get("observer_abi") == 3 and
            capture.get("observer_state_before_after") == ["ready", "complete"] and
            capture.get("observer_armed") is True and
            capture.get("observer_control_write_completed") is True and
            capture.get("one_shot_consumption") == "confirmed" and
            capture.get("first_attempt_pre_dsb_command_reads") == report["wfi_rows"] and
            capture.get("raw_wfi_busy_rows") == report["busy_rows"] and
            capture.get("raw_wfi_clear_rows") == report["wfi_rows"] - report["busy_rows"] and
            capture.get("rejected_busy_rows") ==
                report["busy_rows"] - report["candidate_count"] and
            capture.get("observer_streams_loss_free") is True and
            capture.get("pcpm_and_counter_helpers_unused") is True and
            capture.get("validator_busy_rows") == report["busy_rows"] and
            capture.get("validator_candidate_count") == report["candidate_count"] and
            capture.get("observer_event_rows") == report["idle_rows"] and
            capture.get("observer_wfi_event_rows") == report["wfi_rows"] and
            capture.get("window_source") == "kernel-CLOCK_MONOTONIC" and
            capture.get("user_current_boot_wifi_receipt_checked") is True and
            capture.get("first_a_visual_receipt_proof_checked") is True,
            "public E capture projection differs from replay")
    window = (capture["window_start_relative_to_schedule_ns"],
              capture["window_stop_relative_to_schedule_ns"])
    require(type(window[0]) is type(window[1]) is int and
            0 < window[0] < window[1] and
            capture["window_duration_ns"] == window[1] - window[0] and
            window[1] - window[0] == stream_check["inside_stop_ns"] -
            stream_check["inside_start_ns"], "public E window differs from status")
    for cpu in (1, 5):
        raw = decompressed[f"workload-cpu{cpu}.csv.gz"]
        reader = csv.DictReader(io.StringIO(raw.decode("ascii")))
        rows = list(reader)
        require(reader.fieldnames == ["cpu", "pulse", "iterations",
                                       "relative_start_ns", "duration_ns", "checksum",
                                       "fully_inside_window"] and
                len(rows) == collector.PULSES, "public E workload shape differs")
        interior_count = work_ns = interior_work_ns = 0
        checksums = []
        for pulse, row in enumerate(rows):
            require(None not in row and all(value is not None and
                    re.fullmatch(r"[0-9]+", value) for value in row.values()),
                    "public E workload cell malformed")
            number = {key: int(value) for key, value in row.items()}
            begin, duration = number["relative_start_ns"], number["duration_ns"]
            inside = int(window[0] < begin and begin + duration < window[1])
            require(number["cpu"] == cpu and number["pulse"] == pulse and
                    number["iterations"] == collector.ITERATIONS and
                    pulse * collector.PERIOD_NS <= begin and
                    begin + duration < (pulse + 1) * collector.PERIOD_NS and
                    number["fully_inside_window"] == inside and
                    0 <= number["checksum"] < 1 << 64,
                    "public E workload relative replay failed")
            interior_count += inside
            work_ns += duration
            interior_work_ns += inside * duration
            checksums.append(number["checksum"])
        sequence = a.digest("".join(f"{pulse}:{checksum}\n" for pulse, checksum
                                    in enumerate(checksums)).encode())
        require(capture["workers"][str(cpu)] == {
            "pulses": collector.PULSES, "interior_pulses": interior_count,
            "work_ns": work_ns, "interior_work_ns": interior_work_ns,
            "checksum_sequence_sha256": sequence},
            "public E workload aggregate differs from replay")
    require(capture["workers"]["1"]["checksum_sequence_sha256"] ==
            capture["workers"]["5"]["checksum_sequence_sha256"],
            "public E CPU workload checksums differ")


def write_stage(public: dict[str, bytes], packet: Path, prior_d: Path,
                prior_a: Path, out: Path) -> None:
    require(out.is_absolute() and not out.exists() and not out.is_symlink(),
            "output must be a new absolute directory")
    parent = out.parent
    require(parent.is_dir() and not parent.is_symlink(), "output parent must exist")
    for private in (packet, prior_d, prior_a):
        require(os.path.commonpath((str(private.resolve()), str(out.resolve()))) !=
                str(private.resolve()), "output cannot be inside a private packet")
    staging = Path(tempfile.mkdtemp(prefix=".abi3-E-stage-", dir=parent))
    try:
        staging.chmod(0o700)
        for name, data in sorted(public.items()):
            target = staging / name
            with target.open("xb") as stream:
                stream.write(data)
            target.chmod(0o600)
        (staging / "MANIFEST.sha256").write_text("".join(
            f"{a.file_digest(staging / name)}  {name}\n" for name in sorted(public)))
        (staging / "MANIFEST.sha256").chmod(0o600)
        verify_public_stage(staging)
        require(not out.exists() and not out.is_symlink(),
                "output appeared during staging")
        staging.rename(out)
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--packet", type=Path, help="sealed private ABI 3 E packet")
    action.add_argument("--verify-public-stage", type=Path,
                        help="replay one public E stage without private packets")
    parser.add_argument("--prior-d", type=Path, help="sealed private ABI 3 D packet")
    parser.add_argument("--prior-a", type=Path, help="sealed private ABI 3 A packet")
    parser.add_argument("--out", type=Path, help="new absolute review-stage directory")
    args = parser.parse_args()
    try:
        verify_public_source_binding()
        if args.verify_public_stage is not None:
            require(args.prior_d is None and args.prior_a is None and args.out is None,
                    "stage replay takes no private packet or output")
            verify_public_stage(args.verify_public_stage)
            print(json.dumps({"verified": str(args.verify_public_stage), "phase": "E",
                              "public_manifest_sha256": a.file_digest(
                                  args.verify_public_stage / "MANIFEST.sha256")},
                             sort_keys=True))
        else:
            require(args.prior_d is not None and args.prior_a is not None and
                    args.out is not None,
                    "E projection requires --prior-d, --prior-a and --out")
            packet = args.packet.absolute()
            prior_d, prior_a = args.prior_d.absolute(), args.prior_a.absolute()
            public = build_public(packet, prior_d, prior_a)
            write_stage(public, packet, prior_d, prior_a, args.out)
            print(json.dumps({"staged": str(args.out), "phase": "E",
                              "public_manifest_sha256": a.file_digest(
                                  args.out / "MANIFEST.sha256")}, sort_keys=True))
    except (a.PublicationError, collector.CaptureError, validator.TicketError,
            OSError, ValueError, KeyError, TypeError, UnicodeError) as error:
        parser.exit(2, f"E publication rejected: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
