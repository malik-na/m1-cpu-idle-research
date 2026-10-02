"""Mutation checks for the pinned WFI-seam machine-code validator."""

from __future__ import annotations

import json
from pathlib import Path
import unittest

import validate_wfi_seam as seam


class SeamValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        receipt = json.loads((Path(__file__).with_name("source-object-receipt.json")).read_text())
        cls.baseline = bytes.fromhex(receipt["objects"]["deep_wfi"]["on"]["hex"])
        cls.candidate = (seam.EXPECTED_SAVED_SLOT + cls.baseline[:seam.PREFIX_BYTES]
                         + seam.EXPECTED_PROBE + cls.baseline[seam.PREFIX_BYTES:])
        # Independent saved same-release object receipt, reviewed in disassembly.
        assert seam.sha256(cls.candidate) == "2545c4ce2e5dcfd433dffa4edbd187b11adc544bbda496a882f1fb61fdccaa82"

    def test_reviewed_routine_accepts_same_linked_bytes(self):
        result = seam.validate_bytes(self.baseline, self.candidate, self.candidate)
        self.assertEqual(result["wfi_instructions"], 1)
        self.assertEqual(result["mmio_command_writes"], 0)

    def test_changed_original_power_control_prefix_is_rejected(self):
        changed = bytearray(self.candidate)
        changed[4 + 36] ^= 1  # The power-control MSR, not the new probe.
        with self.assertRaisesRegex(ValueError, "prefix changed"):
            seam.validate_bytes(self.baseline, bytes(changed), bytes(changed))

    def test_changed_original_wfi_retry_tail_is_rejected(self):
        changed = bytearray(self.candidate)
        changed[seam.PROBE_OFFSET + seam.PROBE_BYTES + 4] ^= 1  # Original WFI.
        with self.assertRaisesRegex(ValueError, "tail changed"):
            seam.validate_bytes(self.baseline, bytes(changed), bytes(changed))

    def test_mutated_mmio_load_is_rejected(self):
        changed = bytearray(self.candidate)
        changed[0x48] ^= 1  # Sole load through the command address in x3.
        with self.assertRaisesRegex(ValueError, "probe changed at instruction 7"):
            seam.validate_bytes(self.baseline, bytes(changed), bytes(changed))

    def test_mutated_skip_branch_is_rejected(self):
        changed = bytearray(self.candidate)
        changed[0x2c] ^= 1  # Null-slot branch must target original DSB.
        with self.assertRaisesRegex(ValueError, "probe changed at instruction 0"):
            seam.validate_bytes(self.baseline, bytes(changed), bytes(changed))

    def test_linked_routine_must_match_object(self):
        changed_link = bytearray(self.candidate)
        changed_link[0x30] ^= 1
        with self.assertRaisesRegex(ValueError, "linked vmlinux"):
            seam.validate_bytes(self.baseline, self.candidate, bytes(changed_link))


if __name__ == "__main__":
    unittest.main()
