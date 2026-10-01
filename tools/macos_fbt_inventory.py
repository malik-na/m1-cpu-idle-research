#!/usr/bin/env python3
"""List FBT probes without enabling any; authenticate only in the caller's tty."""

import argparse
import datetime
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authenticate", action="store_true",
                        help="Run sudo -v in this terminal before the inventory")
    parser.add_argument("--output", type=Path, required=True,
                        help="New local output directory; raw listing stays private")
    args = parser.parse_args()
    if platform.system() != "Darwin":
        parser.error("This inventory requires macOS")
    if args.authenticate:
        if not sys.stdin.isatty():
            parser.error("Authenticate from an interactive terminal")
        # No password is collected, stored, or passed through this script.
        result = subprocess.run(["/usr/bin/sudo", "-v"], check=False)
        if result.returncode:
            return result.returncode
    os.umask(0o077)
    args.output.mkdir(mode=0o700, parents=False, exist_ok=False)
    command = ["/usr/bin/sudo", "-n", "/usr/sbin/dtrace", "-l", "-P", "fbt"]
    started = datetime.datetime.now(datetime.timezone.utc).isoformat()
    try:
        result = subprocess.run(command, capture_output=True, timeout=30, check=False)
        stdout, stderr, status = result.stdout, result.stderr, result.returncode
        timed_out = False
    except subprocess.TimeoutExpired as exc:
        stdout, stderr, status = exc.stdout or b"", exc.stderr or b"", None
        timed_out = True
    for name, contents in (("stdout.txt", stdout), ("stderr.txt", stderr)):
        with (args.output / name).open("xb") as output:
            output.write(contents)
    probe_rows = sum(bool(re.match(rb"^\s*\d+\s+fbt\s+", line))
                     for line in stdout.splitlines())
    listing_usable = (status == 0 and not timed_out and probe_rows > 0
                      and b"failed" not in stderr.lower())
    report = {
        "schema": "m1-fbt-inventory-v1",
        "started_utc": started,
        "command": command,
        "exit_status": status,
        "timed_out": timed_out,
        "stdout_lines": len(stdout.splitlines()),
        "probe_rows": probe_rows,
        "listing_usable": listing_usable,
        "probes_enabled": False,
        "euid_of_collector": os.geteuid(),
    }
    with (args.output / "result.json").open("x") as output:
        json.dump(report, output, indent=2)
        output.write("\n")
    print(json.dumps(report, indent=2))
    if stderr:
        print(stderr.decode("utf-8", errors="replace"), file=sys.stderr, end="")
    # DTrace can exit zero while SIP blocks every matching probe.
    return 124 if timed_out else (status or (0 if listing_usable else 1))


if __name__ == "__main__":
    raise SystemExit(main())
