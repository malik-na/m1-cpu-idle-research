#!/usr/bin/env python3
"""Retain CPU/PMGR event data while stripping process and wall-clock fields.

This is a deliberately narrow export for this research capture. Review any new
event IDs and their argument meanings before publishing another transformed
trace. The original trace stays local.
"""

import argparse
import gzip
import json
from pathlib import Path

ALLOWED_IDS = {
    0x27001001,  # PERF_CPU_IDLE begin
    0x27001002,  # PERF_CPU_IDLE end
    0x27003010,  # performance change request
    0x27003030,  # performance domain change
    0x2700C001,  # clock gate begin
    0x2700C002,  # clock gate end
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    count = 0
    with args.source.open("r", encoding="utf-8") as source:
        with args.output.open("wb") as target:
            with gzip.GzipFile(filename="", mode="wb", fileobj=target, mtime=0) as archive:
                for line in source:
                    if not line.strip():
                        continue
                    event = json.loads(line)
                    debugid = int(event["debugid"])
                    if debugid not in ALLOWED_IDS:
                        raise ValueError(f"unreviewed event ID 0x{debugid:08x}")
                    record = {
                        "timestampns": event["timestampns"],
                        "debugid": debugid,
                        "cpuid": event["cpuid"],
                        "args": event["args"],
                    }
                    archive.write((json.dumps(record, separators=(",", ":")) + "\n").encode())
                    count += 1
    print(f"wrote {count} reviewed event records to {args.output}")


if __name__ == "__main__":
    main()
