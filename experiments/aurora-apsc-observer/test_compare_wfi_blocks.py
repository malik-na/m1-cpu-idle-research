"""Synthetic ABI 2 matched-block comparison tests; no native packets."""

from __future__ import annotations

from datetime import datetime, timedelta
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import analyze_wfi
import compare_wfi_blocks as comparator
import publish_wfi_evidence as publisher
import test_publish_wfi_evidence as fixtures


class CompareWfiBlocksTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        patcher = mock.patch.object(publisher, "checked_build_chain",
                                    return_value={"synthetic_fixture": True})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.identity = None

    def block(self, index: int = 0, duplicate_boot: bool = False) -> list[dict]:
        result = []
        for position, mode in enumerate(comparator.BLOCK_ORDERS[index]):
            ordinal = index * 5 + position
            packet = self.root / f"packet-{ordinal}"
            identity = fixtures.create_packet(packet, mode)
            if mode == "wfi_mmio":
                wfi = (packet / "wfi-events.csv").read_text().replace("0x80000000", "0x0")
                (packet / "wfi-events.csv").write_text(wfi)
                observer = analyze_wfi.analyze_text((packet / "events.csv").read_text(),
                                                     (packet / "status.txt").read_text(), wfi)
                (packet / "observer-analysis.stdout").write_text(json.dumps(observer) + "\n")
            if self.identity is None:
                self.identity = identity
            else:
                self.assertEqual(identity, self.identity)
            boot_id = f"11111111-1111-4111-8111-{(1 if duplicate_boot else ordinal + 1):012d}"
            (packet / "boot-id.txt").write_text(boot_id + "\n")
            records = json.loads((packet / "acquisition-record.json").read_text())
            offset = timedelta(minutes=ordinal)
            for row in records:
                row["utc"] = (datetime.fromisoformat(row["utc"]) + offset).isoformat()
            (packet / "acquisition-record.json").write_text(json.dumps(records) + "\n")
            fixtures.refresh_manifest(packet)
            qualification = fixtures.write_qualification(packet, identity)
            acceptance = fixtures.write_device_acceptance(packet, identity)
            for path in (qualification, acceptance):
                data = json.loads(path.read_text())
                data["boot_id"] = boot_id
                path.write_text(json.dumps(data))
            evidence = self.root / f"public-{ordinal}"
            receipt = self.root / f"receipt-{ordinal}.json"
            publisher.publish(packet, mode, evidence, receipt,
                              qualification, acceptance, identity)
            result.append({"mode": mode, "packet": str(packet),
                           "qualification": str(qualification),
                           "device_acceptance": str(acceptance),
                           "receipt": str(receipt), "evidence": str(evidence)})
        return result

    def test_one_block_replays_private_and_public_without_leaking_boot_ids(self):
        block = self.block()
        result = comparator.compare([block], self.identity)
        self.assertEqual(result["packet_count"], 5)
        self.assertEqual(result["decision"], "first_block_inconclusive_second_block_permitted")
        self.assertEqual(result["conditions"]["charger_online_at_checked_endpoints"], 1)
        self.assertTrue(result["common_fully_interior_worker_pulse_indices_by_cpu"]["1"])
        encoded = json.dumps(result)
        self.assertNotIn("11111111-1111-4111", encoded)
        self.assertNotIn(str(self.root), encoded)

    def test_second_reversed_block_and_ten_distinct_boots(self):
        blocks = [self.block(0), self.block(1)]
        result = comparator.compare(blocks, self.identity)
        self.assertEqual(result["packet_count"], 10)
        self.assertEqual(result["block_count"], 2)
        self.assertEqual(result["decision"], "underexposed_or_C_control_unmet_inconclusive_stop")
        self.assertEqual(result["blocks"][1]["recorded_mode_order"],
                         list(comparator.BLOCK_ORDERS[1]))

    def test_public_receipt_tamper_rejected(self):
        block = self.block()
        path = Path(block[1]["receipt"])
        path.write_text(path.read_text() + "\n")
        with self.assertRaisesRegex(comparator.ComparisonError, "public receipt differs"):
            comparator.compare([block], self.identity)

    def test_public_evidence_tamper_rejected(self):
        block = self.block()
        path = Path(block[1]["evidence"]) / "wfi-events.csv.gz"
        path.write_bytes(path.read_bytes() + b"tamper")
        with self.assertRaisesRegex(comparator.ComparisonError, "published evidence bytes differ"):
            comparator.compare([block], self.identity)

    def test_reused_boot_id_rejected(self):
        block = self.block(duplicate_boot=True)
        with self.assertRaisesRegex(comparator.ComparisonError, "private boot IDs repeat"):
            comparator.compare([block], self.identity)

    def test_wrong_order_rejected_before_selection(self):
        block = self.block()
        block[0], block[1] = block[1], block[0]
        with self.assertRaisesRegex(comparator.ComparisonError, "prospective block order"):
            comparator.compare([block], self.identity)

    def test_conservative_maximum_bracket_lag_rejects_old_decoder_bug(self):
        for site, writer_key, sampler_key in (("E", "cpu", "cpu"),
                                              ("C", "writer_cpu", "sampling_cpu")):
            screen = {"decisions": [{
                "status": "primary_pair",
                "set": {writer_key: 0, "t0": 1000, "t1": 1300},
                "sample": {sampler_key: 0, "t0": 1850, "t1": 2000},
                "largest_lag_under_model_ticks": 550,
                "set_sample_order_error_ticks": 0,
            }]}
            with self.subTest(site=site), self.assertRaisesRegex(
                    comparator.ComparisonError, "underbounds write-to-read bracket lag"):
                comparator.verify_bracket_lags(screen, site)

    def test_repaired_conservative_bracket_is_exploratory_only(self):
        screen = {"decisions": [{
            "status": "exploratory_only_pair",
            "set": {"cpu": 0, "t0": 1000, "t1": 1300},
            "sample": {"cpu": 0, "t0": 1850, "t1": 2000},
            "largest_lag_under_model_ticks": 1000,
            "set_sample_order_error_ticks": 0,
        }]}
        comparator.verify_bracket_lags(screen, "E")


if __name__ == "__main__":
    unittest.main()
