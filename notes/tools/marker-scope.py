#!/usr/bin/env python3
"""Count PMGR performance markers inside CPUIdle callback brackets.

Input is the curated, timestamp-ordered event stream. This does not infer
hardware command state or physical CPU idle residency.
"""

from collections import Counter
import gzip
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "raw/ktrace/idle-5s-events.jsonl.gz"
BEGIN, END = 0x27001001, 0x27001002
MARKERS = {0x27003010, 0x27003030}


def main():
    active = {}
    counts = Counter()
    with gzip.open(INPUT, "rt") as source:
        for line in source:
            event = json.loads(line)
            code, cpu = event["debugid"], event["cpuid"]
            if code == BEGIN:
                if cpu in active:
                    raise ValueError(f"nested CPUIdle begin on CPU {cpu}")
                active[cpu] = int(event["args"][1])
            elif code == END:
                if cpu not in active:
                    raise ValueError(f"unmatched CPUIdle end on CPU {cpu}")
                active.pop(cpu)
            elif code in MARKERS:
                counts[(code, "total")] += 1
                if cpu in active:
                    counts[(code, "same_cpu_callback")] += 1
                    counts[(code, "same_cpu_direction_" + str(active[cpu]))] += 1
                if active:
                    counts[(code, "any_cpu_callback")] += 1
    if active:
        raise ValueError(f"unfinished CPUIdle callbacks: {sorted(active)}")
    for code in sorted(MARKERS):
        print(f"{code:#x}: total={counts[code, 'total']}, "
              f"same_cpu_callback={counts[code, 'same_cpu_callback']}, "
              f"any_cpu_callback={counts[code, 'any_cpu_callback']}")


if __name__ == "__main__":
    main()
