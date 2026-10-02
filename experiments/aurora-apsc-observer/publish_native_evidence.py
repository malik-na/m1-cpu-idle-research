#!/usr/bin/env python3
"""Export a small, reviewed subset of private native capture packets.

The original packets and their acquisition-time SHA256SUMS remain untouched.
Only the named numerical event/status/workload streams, bounded sysfs snapshots,
and a whitelist projection of the chronology enter the public evidence set.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re


FILES = (
    "events.csv", "status.txt", "counter-pre-events.csv",
    "counter-pre-status.txt", "counter-events.csv", "counter-status.txt",
    "workload-cpu1.csv", "workload-cpu5.csv",
    "before-snapshot.json", "after-snapshot.json",
)
CHRONOLOGY_FIELDS = {
    "action", "utc", "monotonic_ns", "mode", "duration_ms", "release",
    "workload_sha256", "exit_status", "cpu", "seconds",
    "clock_bound_not_exported",
}
CHRONOLOGY_ACTIONS = {
    "begin", "counter_pre_begin", "counter_pre_end", "settling_begin",
    "settling_end", "window_begin", "window_end", "observer_drained",
    "workload_complete", "counter_post_begin", "counter_post_end", "complete",
}
SYSFS_PREFIXES = (
    "/sys/devices/system/cpu/", "/sys/class/power_supply/",
    "/sys/class/backlight/", "/sys/class/thermal/",
)
PRIVATE_PATTERN = re.compile(rb"(/home/|/root/|/Users/|root=UUID=|machine-id|serial_number|password|passwd|BEGIN [A-Z ]*PRIVATE KEY)", re.I)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_manifest(packet: Path) -> dict[str, str]:
    result = {}
    for line in (packet / "SHA256SUMS").read_text().splitlines():
        checksum, name = line.split("  ", 1)
        if not re.fullmatch(r"[0-9a-f]{64}", checksum) or name in result:
            raise ValueError(f"invalid private manifest in {packet.name}")
        result[name] = checksum
    for name, checksum in result.items():
        if digest((packet / name).read_bytes()) != checksum:
            raise ValueError(f"private packet hash mismatch: {packet.name}/{name}")
    return result


def checked_export_bytes(name: str, raw: bytes) -> bytes:
    if PRIVATE_PATTERN.search(raw):
        raise ValueError(f"private-looking content in {name}")
    if name.endswith("snapshot.json"):
        rows = json.loads(raw)
        if not isinstance(rows, list) or not rows:
            raise ValueError(f"invalid snapshot: {name}")
        for row in rows:
            if set(row) - {"path", "observed_monotonic_ns", "raw_text", "error"}:
                raise ValueError(f"unexpected snapshot field in {name}")
            if not row["path"].startswith(SYSFS_PREFIXES):
                raise ValueError(f"unexpected snapshot path in {name}")
            if any(part in row["path"].lower() for part in ("serial", "uevent", "address", "device_id")):
                raise ValueError(f"identifying snapshot path in {name}")
    return raw


def export_packet(label: str, packet: Path, destination: Path) -> dict:
    manifest = read_manifest(packet)
    status = (packet / "status.txt").read_text()
    expected = ("state=ready\nmode=records\n" if label == "A" else
                f"state=complete\nmode={'records' if label == 'B' else 'mmio'}\n")
    if expected not in status:
        raise ValueError(f"packet mode mismatch: {label}")
    destination.mkdir(parents=True, exist_ok=True)
    exported = {}
    for name in FILES:
        if name not in manifest:
            raise ValueError(f"missing private-manifest entry: {packet.name}/{name}")
        raw = checked_export_bytes(name, (packet / name).read_bytes())
        public_name = f"{name}.gz" if name.endswith(".csv") else name
        public = gzip.compress(raw, compresslevel=9, mtime=0) if name.endswith(".csv") else raw
        (destination / public_name).write_bytes(public)
        exported[public_name] = {
            "private_input_sha256": manifest[name],
            "published_sha256": digest(public),
            "uncompressed_bytes": len(raw),
        }
    chronology = json.loads((packet / "acquisition-record.json").read_text())
    projected = [{k: v for k, v in row.items() if k in CHRONOLOGY_FIELDS}
                 for row in chronology if row["action"] in CHRONOLOGY_ACTIONS]
    if not projected or projected[-1]["action"] != "complete":
        raise ValueError(f"incomplete packet: {packet.name}")
    projection = (json.dumps(projected, indent=2) + "\n").encode()
    checked_export_bytes("chronology.json", projection)
    (destination / "chronology.json").write_bytes(projection)
    exported["chronology.json"] = {
        "private_input_sha256": manifest["acquisition-record.json"],
        "published_sha256": digest(projection),
        "transformation": "retain only CHRONOLOGY_ACTIONS and CHRONOLOGY_FIELDS, original order",
    }
    return {
        "private_packet_basename": packet.name,
        "private_SHA256SUMS_sha256": digest((packet / "SHA256SUMS").read_bytes()),
        "files": exported,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for label in ("baseline", "records", "mmio"):
        parser.add_argument(f"--{label}", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    receipt = {
        "scope": "reviewed numerical native A/B/C event export; full boot packets remain private",
        "transformation": "CSV gzip level 9 with mtime=0; status/snapshots byte-exact; chronology whitelist projection",
        "packets": {},
    }
    for label, packet in (("A", args.baseline), ("B", args.records), ("C", args.mmio)):
        receipt["packets"][label] = export_packet(label, packet, args.out / label)
    (args.out / "export-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")


if __name__ == "__main__":
    main()
