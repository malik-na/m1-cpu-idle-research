#!/usr/bin/env python3
"""Read-only source/build checks for the private, never-loaded LCT prototype.

Default mode reads retained files only. --live also reads kernel identity and
notes, never MMIO or debugfs capture controls. A PASS is necessary, not
sufficient, for any future hardware trial: access width and read safety are
currently unqualified.
"""

import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent / "abi3-ticket-prototype-20261003"
RELEASE = "7.1.12-ARCH-apsc-20261002-wfi-pcpm-abi3"
REVIEWED_SOURCE_SHA256 = "c5b9b8edc8cb2a9969d655a71bf891ece2e5cd447c605983cbc8f9833fd9d587"
REVIEWED_MODULE_SHA256 = "47a63f0d0f6506fadef03233538963dd46cccabf4d33aa59ea49ee52867b1470"
FILES = {
    "source/drivers/cpufreq/apple-soc-cpufreq.c": "0c0e5606d3274110d2833f60d51e1486e82b333247890e3cee3655ed20d24653",
    "source/drivers/cpuidle/apple-apsc-observer.c": "6939e428f19f1f8af0f4124d68d091995d6af507f6eb293f1e1c78bea3c2d505",
    "source/include/linux/soc/apple/apsc-observer.h": "94f186c572f3e1df7a62a7530981b39ee10359af7f5ec23457cf720a754ef1a5",
    "build/.config": "f4df15bf0c94e82210a503c91a9dd408b848d98aed45b0a2a09d691efbcf70a5",
}
NO_HARDWARE_SYMBOLS = ("readq", "readl", "ioread", "of_iomap", "register_kretprobe")


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def built_build_id(vmlinux):
    output = subprocess.check_output(["readelf", "-n", str(vmlinux)], text=True)
    match = re.search(r"Build ID: ([0-9a-f]+)", output)
    if not match:
        raise RuntimeError("vmlinux has no readable GNU Build-ID")
    return match.group(1)


def live_build_id(path):
    """Parse ELF note records in /sys/kernel/notes, without device access."""
    data = path.read_bytes()
    offset = 0
    while offset + 12 <= len(data):
        name_size, desc_size, note_type = struct.unpack_from("<III", data, offset)
        offset += 12
        name = data[offset : offset + name_size]
        offset += (name_size + 3) & ~3
        desc = data[offset : offset + desc_size]
        offset += (desc_size + 3) & ~3
        if note_type == 3 and name.rstrip(b"\0") == b"GNU":
            return desc.hex()
    raise RuntimeError("running kernel notes have no GNU Build-ID")


def check(label, actual, expected, results):
    ok = actual == expected
    results.append({"check": label, "passed": ok, "actual": actual, "expected": expected})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="also inspect read-only running-kernel identity")
    args = parser.parse_args()
    results = []
    receipt = json.loads((ROOT / "linked-build-receipt.json").read_text())
    check("receipt_release", receipt["release"], RELEASE, results)
    for relative, expected in FILES.items():
        check(relative, digest(ROOT / relative), expected, results)
    check("config_vs_receipt", digest(ROOT / "build/.config"), receipt["config_sha256"], results)
    check("built_image_sha256", digest(ROOT / "build/arch/arm64/boot/Image"), receipt["image_sha256"], results)
    check("built_vmlinux_build_id", built_build_id(ROOT / "build/vmlinux"), receipt["vmlinux_build_id"], results)
    module = HERE / "lct_probe.ko"
    check("reviewed_helper_source_sha256", digest(HERE / "lct_probe.c"), REVIEWED_SOURCE_SHA256, results)
    check("module_exists", module.exists(), True, results)
    if module.exists():
        check("reviewed_helper_module_sha256", digest(module), REVIEWED_MODULE_SHA256, results)
        vermagic = subprocess.check_output(["modinfo", "-F", "vermagic", str(module)], text=True).strip()
        check("module_vermagic_release", vermagic.split()[0], RELEASE, results)
        undefined = subprocess.check_output(["nm", "-u", str(module)], text=True)
        hardware_references = [word for word in NO_HARDWARE_SYMBOLS if re.search(rf"\b{word}\b", undefined)]
        check("disabled_object_hardware_symbols", hardware_references, [], results)
    source = (HERE / "lct_probe.c").read_text()
    check("source_width_gate", bool(re.search(r"^#define LCT_REVIEWED_WIDTH_BITS 0$", source, re.M)), True, results)
    check("source_safety_gate", bool(re.search(r"^#define LCT_READ_SAFETY_PROVEN 0$", source, re.M)), True, results)
    check("source_command_only_gate", bool(re.search(r"^#define LCT_COMMAND_ONLY_REVIEWED 0$", source, re.M)), True, results)
    if args.live:
        check("running_release", os.uname().release, RELEASE, results)
        check("running_build_id", live_build_id(Path("/sys/kernel/notes")), receipt["vmlinux_build_id"], results)
        config_gz = Path("/proc/config.gz")
        check("running_config_available", config_gz.exists(), True, results)
        if config_gz.exists():
            live_config_hash = hashlib.sha256(gzip.decompress(config_gz.read_bytes())).hexdigest()
            check("running_config", live_config_hash, receipt["config_sha256"], results)
    output = {"scope": "read-only preflight; no register access", "checks": results, "passed": all(x["passed"] for x in results)}
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0 if output["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
