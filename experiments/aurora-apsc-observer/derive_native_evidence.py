#!/usr/bin/env python3
"""Reproduce the saved native observer summaries from public event streams."""

from __future__ import annotations

import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


HERE = Path(__file__).resolve().parent
EVIDENCE = HERE / "native-evidence"
ANALYZER = HERE.parent / "linux-apsc-observer" / "analyze.py"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    output = {
        "analyzer": "experiments/linux-apsc-observer/analyze.py",
        "analyzer_sha256": digest(ANALYZER.read_bytes()),
        "runs": {},
    }
    for label in ("B", "C"):
        source = EVIDENCE / label
        compressed = (source / "events.csv.gz").read_bytes()
        status = (source / "status.txt").read_bytes()
        with tempfile.TemporaryDirectory(prefix="native-evidence-") as directory:
            events = Path(directory) / "events.csv"
            events.write_bytes(gzip.decompress(compressed))
            for variant, options in (("unbounded", ()), ("assumed-E240", ("--pairwise-clock-error-ticks", "240"))):
                args = [sys.executable, str(ANALYZER), str(events), str(source / "status.txt"), *options]
                completed = subprocess.run(args, capture_output=True, check=True,
                                           env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
                parsed = json.loads(completed.stdout)
                published = (json.dumps(parsed, indent=2, sort_keys=True) + "\n").encode()
                name = f"analysis-{variant}.json"
                (source / name).write_bytes(published)
                output["runs"][f"{label}/{name}"] = {
                    "events_csv_gz_sha256": digest(compressed),
                    "events_csv_sha256": digest(events.read_bytes()),
                    "status_sha256": digest(status),
                    "options": list(options),
                    "output_sha256": digest(published),
                }
    (EVIDENCE / "analysis-receipt.json").write_text(json.dumps(output, indent=2) + "\n")


if __name__ == "__main__":
    main()
