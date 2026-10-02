#!/usr/bin/env python3
"""Fail closed on changes to the reviewed first-attempt deep-WFI machine code.

This is a static artifact check, not a runtime or physical-power observation.
Pass the original capacity cpuidle object, candidate cpuidle and observer
objects, and the linked candidate vmlinux. The candidate is intentionally
pinned to the exact reviewed assembly sequence; any revision requires a fresh
disassembly and review.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import mmap
import os
from pathlib import Path
import re
import struct
import subprocess


BASELINE_SHA256 = "c8fd716fccb949e9f35aa2937a87787942b39f0b5df5e088d46f88253479b88c"
BASELINE_BYTES = 100
PREFIX_BYTES = 40  # Through the original power-control MSR.
PROBE_OFFSET = 44  # After the new `mov x1, x0` and the original prefix.
PROBE_BYTES = 80
CANDIDATE_BYTES = 184
NOP = struct.pack("<I", 0xd503201f)

# Exact AArch64 words reviewed with llvm-objdump. Branch encodings fix the
# clock/MMIO choice, publication path and retry target. The only load through
# the MMIO address (x3) is the one marked below; all STR/STP writes target the
# preallocated slot (x1/x7). No instruction writes through x3.
PROBE = (
    (0xb4000281, "cbz x1, original DSB; absent slot skips probe"),
    (0xd5033fdf, "isb before first counter"),
    (0xd53be022, "mrs x2, CNTPCT_EL0"),
    (0xb9403426, "ldr w6, [x1, #52]; slot mode"),
    (0x710008df, "cmp w6, #2; MMIO mode"),
    (0x540000c1, "b.ne second counter; clock-only mode"),
    (0xf9400023, "ldr x3, [x1]; slot command address"),
    (0xf9400064, "ldr x4, [x3]; sole MMIO read"),
    (0xd50331bf, "dmb oshld; readq ordering"),
    (0xca040087, "eor x7, x4, x4; read-to-counter dependency"),
    (0xb5000007, "cbnz x7, self; impossible after xor"),
    (0xd5033fdf, "isb before second counter"),
    (0xd53be025, "mrs x5, CNTPCT_EL0"),
    (0xa9009422, "stp x2, x5, [x1, #8]; bracket"),
    (0x710008df, "cmp w6, #2; MMIO mode"),
    (0x54000041, "b.ne publication; clock-only mode"),
    (0xf9000c24, "str x4, [x1, #24]; raw command"),
    (0x9100e027, "add x7, x1, #56; commit address"),
    (0x52800028, "mov w8, #1"),
    (0x889ffce8, "stlr w8, [x7]; publish before DSB/WFI"),
)
PROBE_WORDS = tuple(word for word, _ in PROBE)
EXPECTED_PROBE = struct.pack("<" + "I" * len(PROBE_WORDS), *PROBE_WORDS)
EXPECTED_SAVED_SLOT = struct.pack("<I", 0xaa0003e1)  # mov x1, x0
WFI_WORD = struct.pack("<I", 0xd503207f)
MMIO_READ_WORD = struct.pack("<I", 0xf9400064)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def artifact_identity(stat: os.stat_result) -> tuple[int, int, int, int, int]:
    return (stat.st_dev, stat.st_ino, stat.st_size,
            stat.st_mtime_ns, stat.st_ctime_ns)


def file_hash_stable(path: Path) -> str:
    with path.open("rb") as file:
        before = os.fstat(file.fileno())
        digest = hashlib.sha256()
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
        after = os.fstat(file.fileno())
    if artifact_identity(before) != artifact_identity(after) or artifact_identity(after) != artifact_identity(path.stat()):
        raise ValueError(f"{path}: build artifact changed during validation")
    return digest.hexdigest()


class ElfImage:
    """Small mmap-backed ELF64 reader; never copies linked .text in full."""

    SECTION = "<IIQQQQIIQQ"
    SYMBOL = "<IBBHQQ"

    def __init__(self, path: Path, *, linked: bool):
        self.path = path
        self.file = path.open("rb")
        self.initial_stat = os.fstat(self.file.fileno())
        self.data = mmap.mmap(self.file.fileno(), 0, access=mmap.ACCESS_READ)
        if self.data[:6] != b"\x7fELF\x02\x01":
            raise ValueError(f"{path}: expected ELF64 little-endian")
        header = struct.unpack_from("<16sHHIQQQIHHHHHH", self.data)
        if header[2] != 183 or header[1] not in ((2, 3) if linked else (1,)):
            raise ValueError(f"{path}: expected AArch64 {'linked image' if linked else 'object'}")
        table_offset, entry_size, count, names_index = header[6], header[11], header[12], header[13]
        if entry_size != 64 or not 0 < names_index < count:
            raise ValueError(f"{path}: unsupported section table")
        if table_offset + count * entry_size > len(self.data):
            raise ValueError(f"{path}: truncated section table")
        self.sections = [struct.unpack_from(self.SECTION, self.data, table_offset + i * 64)
                         for i in range(count)]
        names = self.section_bytes(names_index)
        self.names = [self.string(names, section[0]) for section in self.sections]
        self.symbols = []
        for index, section in enumerate(self.sections):
            if section[1] != 2:  # SHT_SYMTAB
                continue
            if section[9] != 24:
                raise ValueError(f"{path}: unsupported symbol table")
            strings = self.section_bytes(section[6])
            entries = self.section_bytes(index)
            for offset in range(0, len(entries), 24):
                name, info, _other, shndx, value, size = struct.unpack_from(self.SYMBOL, entries, offset)
                if info & 15 == 2 and 0 < shndx < count:  # STT_FUNC
                    self.symbols.append((self.string(strings, name), shndx, value, size))

    def close(self) -> None:
        self.data.close()
        self.file.close()

    def artifact_sha256(self) -> str:
        """Hash the mapped inode and reject a file changed during validation."""
        digest = hashlib.sha256(self.data).hexdigest()
        current_fd = os.fstat(self.file.fileno())
        current_path = self.path.stat()
        if (artifact_identity(self.initial_stat) != artifact_identity(current_fd) or
                artifact_identity(current_fd) != artifact_identity(current_path)):
            raise ValueError(f"{self.path}: build artifact changed during validation")
        return digest

    def __enter__(self) -> "ElfImage":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    @staticmethod
    def string(table: bytes, offset: int) -> str:
        if offset >= len(table):
            raise ValueError("invalid ELF string offset")
        end = table.find(b"\0", offset)
        if end < 0:
            raise ValueError("unterminated ELF string")
        return table[offset:end].decode("ascii")

    def section_bytes(self, index: int) -> bytes:
        if not 0 <= index < len(self.sections):
            raise ValueError("invalid ELF section index")
        section = self.sections[index]
        offset, size = section[4], section[5]
        if section[1] == 8:  # SHT_NOBITS
            return b""
        if offset + size > len(self.data):
            raise ValueError("truncated ELF section")
        return self.data[offset:offset + size]

    def routine(self, *, length: int, linked: bool) -> bytes:
        matches = [symbol for symbol in self.symbols if symbol[0] == "apple_cpu_deep_wfi"]
        if len(matches) != 1:
            raise ValueError(f"{self.path}: missing or ambiguous deep-WFI symbol")
        _, section_index, value, size = matches[0]
        section = self.sections[section_index]
        expected_section = ".text" if linked else ".cpuidle.text"
        if self.names[section_index] != expected_section or not section[2] & 4:
            raise ValueError(f"{self.path}: deep-WFI symbol in unexpected section")
        start = value - section[3]
        if start < 0 or start + length > section[5]:
            raise ValueError(f"{self.path}: deep-WFI exceeds section bounds")
        later = [other[2] - section[3] for other in self.symbols
                 if other[1] == section_index and other[2] > value]
        end = min(later) if later else section[5]
        if size and size != length:
            raise ValueError(f"{self.path}: deep-WFI symbol size changed")
        if end < start + length or end > start + length + 32:
            raise ValueError(f"{self.path}: unexpected deep-WFI extent")
        whole = self.data[section[4] + start:section[4] + end]
        padding = whole[length:]
        if len(padding) % 4 or padding != NOP * (len(padding) // 4):
            raise ValueError(f"{self.path}: non-NOP instructions follow reviewed routine")
        if not linked:
            for index, reloc in enumerate(self.sections):
                if reloc[1] not in (4, 9) or reloc[7] != section_index:
                    continue
                stride = 24 if reloc[1] == 4 else 16
                if reloc[9] != stride:
                    raise ValueError(f"{self.path}: unsupported relocation size")
                entries = self.section_bytes(index)
                for offset in range(0, len(entries), stride):
                    target = struct.unpack_from("<Q", entries, offset)[0]
                    if start <= target < start + length:
                        raise ValueError(f"{self.path}: relocation in deep-WFI routine")
        return whole[:length]


def validate_bytes(baseline: bytes, candidate: bytes, linked: bytes) -> dict:
    """Checks both preserved original code and the exact reviewed insertion."""
    if len(baseline) != BASELINE_BYTES or sha256(baseline) != BASELINE_SHA256:
        raise ValueError("original deep-WFI bytes differ from pinned capacity baseline")
    if len(candidate) != CANDIDATE_BYTES:
        raise ValueError("candidate deep-WFI routine has unexpected length")
    if candidate[:4] != EXPECTED_SAVED_SLOT:
        raise ValueError("candidate no longer saves the optional slot in x1")
    if candidate[4:PROBE_OFFSET] != baseline[:PREFIX_BYTES]:
        raise ValueError("original save/power-control MSR prefix changed")
    actual_probe = candidate[PROBE_OFFSET:PROBE_OFFSET + PROBE_BYTES]
    if actual_probe != EXPECTED_PROBE:
        mismatch = next((i for i, (actual, expected) in enumerate(zip(actual_probe, EXPECTED_PROBE))
                         if actual != expected), None)
        instruction = mismatch // 4 if mismatch is not None else -1
        detail = PROBE[instruction][1] if instruction >= 0 else "unknown"
        raise ValueError(f"first-attempt probe changed at instruction {instruction}: {detail}")
    if candidate[PROBE_OFFSET + PROBE_BYTES:] != baseline[PREFIX_BYTES:]:
        raise ValueError("original DSB/WFI/retry/restore tail changed")
    if candidate.count(WFI_WORD) != 1 or candidate.count(MMIO_READ_WORD) != 1:
        raise ValueError("unexpected WFI or command MMIO read count")
    if linked != candidate:
        raise ValueError("linked vmlinux deep-WFI bytes differ from candidate object")
    return {
        "baseline_routine_sha256": sha256(baseline),
        "candidate_routine_sha256": sha256(candidate),
        "linked_routine_sha256": sha256(linked),
        "original_prefix_bytes": PREFIX_BYTES,
        "original_tail_bytes": BASELINE_BYTES - PREFIX_BYTES,
        "inserted_probe_bytes": PROBE_BYTES,
        "wfi_instructions": 1,
        "mmio_command_reads": 1,
        "mmio_command_writes": 0,
        "mode_slot_offset": 52,
        "tick_slot_offset": 8,
        "command_slot_offset": 24,
        "commit_slot_offset": 56,
        "commit_instruction": "STLR before original DSB/WFI",
        "retry_target": "original DSB, skipping inserted probe",
    }


EXPECTED_LAYOUT = {
    "cmd_addr": (0, 8), "t0": (8, 8), "t1": (16, 8), "cmd": (24, 8),
    "token": (32, 8), "seq": (40, 4), "cpu": (44, 4),
    "cluster": (48, 4), "mode": (52, 4), "committed": (56, 4),
}


def validate_layout(observer_object: Path) -> dict:
    """Compare compiled DWARF field offsets to the assembly's slot accesses."""
    before = observer_object.stat()
    result = subprocess.run(
        ["pahole", "-C", "apsc_wfi_sample", str(observer_object)],
        text=True, capture_output=True, check=True,
    )
    if artifact_identity(before) != artifact_identity(observer_object.stat()):
        raise ValueError(f"{observer_object}: changed during DWARF layout validation")
    layout = {}
    for line in result.stdout.splitlines():
        match = re.search(r"\b(\w+);\s*/\*\s*(\d+)\s+(\d+)\s*\*/", line)
        if match:
            layout[match[1]] = (int(match[2]), int(match[3]))
    size = re.search(r"/\* size: (\d+),", result.stdout)
    if layout != EXPECTED_LAYOUT or size is None or int(size[1]) != 64:
        raise ValueError(f"{observer_object}: compiled WFI slot layout changed: {layout}")
    return {field: {"offset": offset, "bytes": width}
            for field, (offset, width) in layout.items()}


def validate(baseline_object: Path, candidate_object: Path,
             observer_object: Path, vmlinux: Path) -> dict:
    with ElfImage(baseline_object, linked=False) as original:
        baseline = original.routine(length=BASELINE_BYTES, linked=False)
        baseline_sha = original.artifact_sha256()
    with ElfImage(candidate_object, linked=False) as instrumented:
        candidate = instrumented.routine(length=CANDIDATE_BYTES, linked=False)
        candidate_sha = instrumented.artifact_sha256()
    with ElfImage(vmlinux, linked=True) as image:
        linked = image.routine(length=CANDIDATE_BYTES, linked=True)
        image_sha = image.artifact_sha256()
    layout = validate_layout(observer_object)
    return {
        "scope": "static AArch64 object and linked-image byte proof; no native execution",
        "artifacts": {
            "baseline_object": {"path": str(baseline_object), "sha256": baseline_sha},
            "candidate_object": {"path": str(candidate_object), "sha256": candidate_sha},
            "observer_object": {"path": str(observer_object), "sha256": file_hash_stable(observer_object)},
            "candidate_vmlinux": {"path": str(vmlinux), "sha256": image_sha},
        },
        "checks": validate_bytes(baseline, candidate, linked),
        "compiled_slot_layout": layout,
        "limits": "Does not prove runtime execution, DT mapping correctness, transient clock order, physical sleep, or energy.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline_object", type=Path)
    parser.add_argument("candidate_object", type=Path)
    parser.add_argument("observer_object", type=Path,
                        help="compiled apple-apsc-observer.o with DWARF layout")
    parser.add_argument("candidate_vmlinux", type=Path)
    args = parser.parse_args()
    try:
        result = validate(args.baseline_object, args.candidate_object,
                          args.observer_object, args.candidate_vmlinux)
    except (OSError, ValueError, struct.error, subprocess.CalledProcessError) as error:
        parser.exit(2, f"WFI seam validation failed: {error}\n")
    print(json.dumps(result, indent=2))
