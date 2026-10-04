"""Offline checks for the public ABI 3 E exporter and staged packet."""

from __future__ import annotations

import csv
import gzip
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest

import capture_abi3 as collector
import publish_abi3_a as a
import publish_abi3_e as e


HERE = Path(__file__).resolve().parent
DEFAULT_STAGE = HERE.parent / "native-evidence" / "abi3-E"


def reviewed_stage(test: unittest.TestCase) -> Path:
    stage = Path(os.environ.get("ABI3_E_PUBLIC_STAGE", DEFAULT_STAGE))
    if not stage.is_dir():
        test.skipTest("reviewed public E packet has not been installed")
    return stage


def reseal_public(stage: Path) -> None:
    receipt_path = stage / "publication-receipt.json"
    receipt = json.loads(receipt_path.read_bytes())
    for name in receipt["artifacts"]:
        receipt["artifacts"][name]["public_sha256"] = a.file_digest(stage / name)
    receipt_path.write_bytes(a.encode_json(receipt))
    (stage / "MANIFEST.sha256").write_text("".join(
        f"{a.file_digest(stage / name)}  {name}\n" for name in sorted(e.PUBLIC_NAMES)))


class PublishAbi3EPublicTests(unittest.TestCase):
    def test_review_copy_and_dependency_sources_are_bound(self):
        e.verify_public_source_binding()

    def test_wfi_command_words_are_numeric_and_required(self):
        columns = collector.WFI_HEADER.split(",")
        values = {key: "0" for key in columns}
        values.update(mode="wfi_mmio", cmd="0x1", cmd_valid="1")

        def stream() -> bytes:
            return (collector.WFI_HEADER + "\n" +
                    ",".join(values[key] for key in columns) + "\n").encode()

        e.exact_stream(stream(), "wfi")
        values["cmd"] = "0x80000000"
        e.exact_stream(stream(), "wfi")
        values["cmd"] = ""
        with self.assertRaises(a.PublicationError):
            e.exact_stream(stream(), "wfi")
        values["cmd"] = "/home/private"
        with self.assertRaises(a.PublicationError):
            e.exact_stream(stream(), "wfi")

    def test_reviewed_stage_replays_and_retains_all_command_words(self):
        stage = reviewed_stage(self)
        e.verify_public_stage(stage)
        report = json.loads((stage / "validator-report.json").read_bytes())
        capture = json.loads((stage / "capture.json").read_bytes())
        raw = gzip.decompress((stage / "apsc-wfi-events.csv.gz").read_bytes())
        rows = list(csv.DictReader(io.StringIO(raw.decode("ascii"))))
        busy = [row for row in rows if int(row["cmd"], 16) & (1 << 31)]
        clear = [row for row in rows if not int(row["cmd"], 16) & (1 << 31)]
        self.assertTrue(all(row["cmd_valid"] == "1" and
                            row["mode"] == "wfi_mmio" for row in rows))
        self.assertEqual((len(rows), len(busy), len(clear)), (2185, 71, 2114))
        self.assertEqual((report["busy_rows"], report["candidate_count"]), (71, 18))
        self.assertEqual(sum(bool(row["reasons"])
                             for row in report["busy_screen"]), 53)
        self.assertEqual((capture["first_attempt_pre_dsb_command_reads"],
                          capture["raw_wfi_clear_rows"],
                          capture["rejected_busy_rows"]), (2185, 2114, 53))

    def test_resealed_command_word_change_fails_validator_replay(self):
        source = reviewed_stage(self)
        with tempfile.TemporaryDirectory() as directory:
            stage = Path(directory) / "abi3-E"
            shutil.copytree(source, stage)
            path = stage / "apsc-wfi-events.csv.gz"
            raw = gzip.decompress(path.read_bytes())
            before = raw.count(b"0x80000002,wfi_mmio,1,")
            if before == 0:
                # Use any BUSY word in the reviewed packet without inventing a row.
                reader = csv.DictReader(io.StringIO(raw.decode("ascii")))
                word = next(row["cmd"] for row in reader
                            if int(row["cmd"], 16) & (1 << 31))
                old = (word + ",wfi_mmio,1,").encode()
            else:
                old = b"0x80000002,wfi_mmio,1,"
            self.assertIn(old, raw)
            new = b"0x0,wfi_mmio,1,"
            path.write_bytes(gzip.compress(raw.replace(old, new, 1), mtime=0))
            reseal_public(stage)
            with self.assertRaisesRegex(a.PublicationError,
                                        "validator report differs"):
                e.verify_public_stage(stage)

    def test_resealed_rejection_reason_change_fails_validator_replay(self):
        source = reviewed_stage(self)
        with tempfile.TemporaryDirectory() as directory:
            stage = Path(directory) / "abi3-E"
            shutil.copytree(source, stage)
            path = stage / "validator-report.json"
            report = json.loads(path.read_bytes())
            rejected = next(row for row in report["busy_screen"] if row["reasons"])
            rejected["reasons"] = []
            path.write_bytes(a.encode_json(report))
            reseal_public(stage)
            with self.assertRaisesRegex(a.PublicationError,
                                        "validator report differs"):
                e.verify_public_stage(stage)

    def test_readme_does_not_change_data_replay(self):
        source = reviewed_stage(self)
        with tempfile.TemporaryDirectory() as directory:
            stage = Path(directory) / "abi3-E"
            shutil.copytree(source, stage)
            (stage / "README.md").write_text("Repository explanation outside the data manifest.\n")
            e.verify_public_stage(stage)

    def test_isolated_private_restage_matches_reviewed_stage_byte_for_byte(self):
        source = reviewed_stage(self)
        names = ("ABI3_E_PRIVATE_PACKET", "ABI3_D_PRIVATE_PACKET",
                 "ABI3_A_PRIVATE_PACKET")
        if any(name not in os.environ for name in names):
            self.skipTest("private sealed packet paths were not supplied")
        e_packet, d_packet, a_packet = (Path(os.environ[name]) for name in names)
        with tempfile.TemporaryDirectory() as directory:
            stage = Path(directory) / "restaged-E"
            public = e.build_public(e_packet, d_packet, a_packet)
            e.write_stage(public, e_packet, d_packet, a_packet, stage)
            e.verify_public_stage(stage)
            self.assertEqual((stage / "MANIFEST.sha256").read_bytes(),
                             (source / "MANIFEST.sha256").read_bytes())
            for name in e.PUBLIC_NAMES:
                self.assertEqual((stage / name).read_bytes(), (source / name).read_bytes(),
                                 name)


if __name__ == "__main__":
    unittest.main()
