#!/usr/bin/env python3
"""Check the scratch ABI 3 first-attempt path against the PCPM object."""

import hashlib
import json
from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parent
CANDIDATE = ROOT / "build/drivers/cpuidle/cpuidle-apple.o"
BASELINE = ROOT.parent / "pcpm-preflight-20261003/build/drivers/cpuidle/cpuidle-apple.o"
LINE = re.compile(r"^\s*([0-9a-f]+):\s+([0-9a-f]{8})\s+([a-z0-9_.]+)\s*(.*)$")


def instructions(path):
    text = subprocess.check_output(("/usr/bin/objdump", "-dr", str(path)), text=True)
    start = text.index("<apple_cpu_deep_wfi>:\n")
    body = text[start:].split("\n\n", 1)[0]
    rows = []
    for line in body.splitlines()[1:]:
        match = LINE.match(line)
        if match:
            rows.append((int(match[1], 16), match[2], match[3], match[4]))
    assert rows and rows[0][0] == 0, path
    return rows


candidate = instructions(CANDIDATE)
baseline = instructions(BASELINE)


def one(rows, mnemonic, operand):
    matches = [i for i, row in enumerate(rows)
               if row[2] == mnemonic and row[3].startswith(operand)]
    assert len(matches) == 1, (mnemonic, operand, matches)
    return matches[0]


read = one(candidate, "ldr", "x4, [x3]")
assert candidate[read - 1][2] == "b.ne"
assert int(candidate[read - 1][3].split()[0], 16) == candidate[read + 1][0]
assert candidate[read + 1][2:] == ("dmb", "oshld")
pre, post = [i for i, row in enumerate(candidate) if row[2] == "ldaddal"]
assert pre < read < post
assert [row[3] for row in (candidate[pre], candidate[post])] == [
    "x10, x11, [x9]", "x10, x11, [x9]"
]
assert [candidate[i][3] for i in (pre + 2, post + 2)] == [
    "x11, [x1, #64]", "x11, [x1, #72]"
]
assert [i for i, row in enumerate(candidate) if row[2:] == ("dmb", "sy")] == [
    pre + 3, post - 1
]
assert one(candidate, "mov", "x4, xzr") < read
assert one(candidate, "str", "x4, [x1, #24]") > post
assert one(candidate, "stlr", "w8, [x7]") > post

dsb = one(candidate, "dsb", "sy")
assert candidate[dsb + 1][2] == "wfi"
retry = one(candidate, "cbz", "x0,")
assert int(candidate[retry][3].split()[1], 16) == candidate[dsb][0]
assert one(candidate, "cbz", "x1,") < pre
assert len([row for row in candidate if row[2] == "wfi"]) == 1

baseline_dsb = one(baseline, "dsb", "sy")
baseline_ret = one(baseline, "ret", "")
candidate_ret = one(candidate, "ret", "")
baseline_tail = [row[1] for row in baseline[baseline_dsb:baseline_ret + 1]]
candidate_tail = [row[1] for row in candidate[dsb:candidate_ret + 1]]
assert candidate_tail == baseline_tail

receipt = {
    "schema": 1,
    "baseline_object_sha256": hashlib.sha256(BASELINE.read_bytes()).hexdigest(),
    "candidate_object_sha256": hashlib.sha256(CANDIDATE.read_bytes()).hexdigest(),
    "candidate_ticket_offsets": [candidate[pre][0], candidate[post][0]],
    "candidate_mmio_read_offset": candidate[read][0],
    "candidate_dsb_offset": candidate[dsb][0],
    "candidate_wfi_offset": candidate[dsb + 1][0],
    "baseline_dsb_offset": baseline[baseline_dsb][0],
    "original_dsb_through_ret_bytes_identical": True,
    "clock_branch_skips_only_apsc_load": True,
    "first_attempt_ticket_count": 2,
    "first_attempt_apsc_read_count": 1,
}
(ROOT / "object-validation.json").write_text(json.dumps(receipt, indent=2) + "\n")
print(json.dumps(receipt, indent=2))
