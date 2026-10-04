#!/usr/bin/env python3
"""Pin the completed private ABI 3 build and its linked WFI instructions."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys


if sys.flags.optimize:
    raise RuntimeError("linked proof requires Python assertions enabled")


ROOT = Path(__file__).resolve().parent
BUILD = ROOT / "build"
SOURCE_RECEIPT = ROOT / "source-hash-receipt.json"
BUILD_STATUS = ROOT / "full-build-status.json"
LINE = re.compile(r"^\s*([0-9a-f]+):\s+([0-9a-f]{8})\s+([a-z0-9_.]+)\s*(.*)$")


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def instructions(path):
    output = subprocess.check_output(
        ("objdump", "-dr", "--disassemble=apple_cpu_deep_wfi", str(path)),
        text=True)
    body = output.split("<apple_cpu_deep_wfi>:\n", 1)[1].split("\n\n", 1)[0]
    rows = []
    for line in body.splitlines():
        match = LINE.match(line)
        if match:
            rows.append((int(match[1], 16), match[2], match[3], match[4]))
    assert rows, path
    return rows


def one(rows, mnemonic, operand):
    matches = [i for i, row in enumerate(rows)
               if row[2] == mnemonic and row[3].startswith(operand)]
    assert len(matches) == 1, (mnemonic, operand, matches)
    return matches[0]


def symbol(path, name):
    output = subprocess.check_output(("readelf", "-sW", str(path)), text=True)
    matches = []
    for line in output.splitlines():
        parts = line.split()
        if len(parts) >= 8 and parts[7] == name and parts[0].endswith(":"):
            matches.append((int(parts[1], 16), int(parts[2])))
    assert len(matches) == 1, (name, matches)
    return matches[0]


def build_id(path):
    output = subprocess.check_output(("readelf", "-n", str(path)), text=True)
    match = re.search(r"Build ID: ([0-9a-f]+)", output)
    assert match, "linked vmlinux lacks Build-ID"
    return match.group(1)


def hashes(paths):
    return {path.relative_to(BUILD).as_posix(): sha256(path) for path in paths}


def manifest_sha(items):
    data = "".join(json.dumps([key, value], separators=(",", ":")) + "\n"
                   for key, value in sorted(items.items()))
    return hashlib.sha256(data.encode("ascii")).hexdigest()


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--baseline-vmlinux", type=Path, required=True)
args = parser.parse_args()
baseline_vmlinux = args.baseline_vmlinux

source_receipt = json.loads(SOURCE_RECEIPT.read_text())
build_status = json.loads(BUILD_STATUS.read_text())
assert build_status["exit_status"] == 0
assert build_status["targets"] == ["Image", "modules", "dtbs"]
assert build_status["full_build_log_sha256"] == sha256(ROOT / "full-build.log")
assert sha256(BUILD / ".config") == source_receipt["scratch_config_sha256"]
for relative, entry in source_receipt["file_sha256"].items():
    assert sha256(ROOT / "source" / relative) == entry["candidate"]
assert (BUILD / "include/config/kernel.release").read_text().strip() == \
    source_receipt["scratch_release"]
image = BUILD / "arch/arm64/boot/Image"
ikconfig = subprocess.check_output(
    (str(ROOT / "source/scripts/extract-ikconfig"), str(image)))
ikconfig_sha = hashlib.sha256(ikconfig).hexdigest()
assert ikconfig_sha == sha256(BUILD / ".config")

candidate = instructions(BUILD / "vmlinux")
baseline = instructions(baseline_vmlinux)
pre, post = [index for index, row in enumerate(candidate) if row[2] == "ldaddal"]
read = one(candidate, "ldr", "x4, [x3]")
assert pre < read < post
assert candidate[read - 1][2] == "b.ne"
assert int(candidate[read - 1][3].split()[0], 16) == candidate[read + 1][0]
assert candidate[read + 1][2:] == ("dmb", "oshld")
assert [candidate[index][3] for index in (pre, post)] == \
    ["x10, x11, [x9]", "x10, x11, [x9]"]
assert [candidate[index][3] for index in (pre + 2, post + 2)] == \
    ["x11, [x1, #64]", "x11, [x1, #72]"]
assert [index for index, row in enumerate(candidate)
        if row[2:] == ("dmb", "sy")] == [pre + 3, post - 1]
assert one(candidate, "mov", "x4, xzr") < read
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
assert [row[1] for row in candidate[dsb:candidate_ret + 1]] == \
    [row[1] for row in baseline[baseline_dsb:baseline_ret + 1]]

counter_address, counter_size = symbol(BUILD / "vmlinux", "cluster_ticket")
assert counter_address % 128 == 0 and counter_size == 256

module_paths = sorted(BUILD.rglob("*.ko"))
modules = hashes(module_paths)
ordered_modules = {Path(line).with_suffix(".ko").as_posix()
                   for line in (BUILD / "modules.order").read_text().splitlines()}
assert modules and set(modules) == ordered_modules, \
    "module artifacts differ from modules.order"
vermagic_prefix = ("vermagic=" + source_receipt["scratch_release"] + " ").encode()
assert all(vermagic_prefix in path.read_bytes() for path in module_paths), \
    "module vermagic release differs from Image release"
dtbs = hashes(sorted(BUILD.glob("arch/arm64/boot/dts/apple/*.dtb")))
assert "arch/arm64/boot/dts/apple/t8103-j313.dtb" in dtbs, \
    "T8103 J313 DTB absent"
receipt = {
    "schema": 1,
    "scope": "completed private scratch build; no installation or runtime claim",
    "full_build_targets": ["Image", "modules", "dtbs"],
    "full_build_exit_status": build_status["exit_status"],
    "full_build_status_sha256": sha256(BUILD_STATUS),
    "source_receipt_sha256": sha256(SOURCE_RECEIPT),
    "candidate_source_tree_sha256": source_receipt["candidate_manifest_tree_sha256"],
    "patch_sha256": source_receipt["patch_sha256"],
    "linked_proof_script_sha256": sha256(ROOT / "make_linked_receipt.py"),
    "object_proof_script_sha256": sha256(ROOT / "validate_object.py"),
    "object_validation_receipt_sha256": sha256(ROOT / "object-validation.json"),
    "ticket_validator_sha256": sha256(ROOT / "validate_tickets.py"),
    "ticket_validator_tests_sha256": sha256(ROOT / "test_validate_tickets.py"),
    "full_build_log_sha256": sha256(ROOT / "full-build.log"),
    "config_sha256": sha256(BUILD / ".config"),
    "release": source_receipt["scratch_release"],
    "vmlinux_sha256": sha256(BUILD / "vmlinux"),
    "vmlinux_build_id": build_id(BUILD / "vmlinux"),
    "baseline_vmlinux_sha256": sha256(baseline_vmlinux),
    "baseline_vmlinux_build_id": build_id(baseline_vmlinux),
    "image_sha256": sha256(image),
    "image_size_bytes": image.stat().st_size,
    "image_ikconfig_sha256": ikconfig_sha,
    "module_count": len(modules),
    "module_sha256": modules,
    "module_manifest_sha256": manifest_sha(modules),
    "modules_order_sha256": sha256(BUILD / "modules.order"),
    "module_vermagic_release_checked": True,
    "apple_dtb_count": len(dtbs),
    "apple_dtb_sha256": dtbs,
    "apple_dtb_manifest_sha256": manifest_sha(dtbs),
    "linked_cluster_ticket_address": f"0x{counter_address:x}",
    "linked_cluster_ticket_size": counter_size,
    "linked_cluster_counter_addresses": [f"0x{counter_address + offset:x}"
                                         for offset in (0, 128)],
    "linked_ticket_instruction_addresses": [f"0x{candidate[index][0]:x}"
                                            for index in (pre, post)],
    "linked_apsc_read_address": f"0x{candidate[read][0]:x}",
    "linked_dsb_address": f"0x{candidate[dsb][0]:x}",
    "linked_wfi_address": f"0x{candidate[dsb + 1][0]:x}",
    "linked_clock_branch_skips_only_apsc_load": True,
    "linked_original_dsb_through_ret_bytes_identical": True,
}
(ROOT / "linked-build-receipt.json").write_text(
    json.dumps(receipt, indent=2, sort_keys=True) + "\n")
print(json.dumps({key: value for key, value in receipt.items()
                  if key not in ("module_sha256", "apple_dtb_sha256")},
                 indent=2, sort_keys=True))
