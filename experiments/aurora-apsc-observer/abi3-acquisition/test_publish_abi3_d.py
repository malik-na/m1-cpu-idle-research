"""Offline checks for the public ABI 3 D publisher and stage replay."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest

import capture_abi3 as collector
import publish_abi3_a as a
import publish_abi3_d as d


HERE = Path(__file__).resolve().parent
DEFAULT_STAGE = HERE.parent / "native-evidence" / "abi3-D"


def reviewed_stage(test: unittest.TestCase) -> Path:
    stage = Path(os.environ.get("ABI3_D_PUBLIC_STAGE", DEFAULT_STAGE))
    if not stage.is_dir():
        test.skipTest("reviewed public D packet has not been installed")
    return stage


class PublishAbi3DPublicTests(unittest.TestCase):
    def test_review_copy_and_validator_source_are_bound(self):
        d.verify_public_source_binding()

    def test_ticket_stream_rejects_wfi_command_data(self):
        columns = collector.WFI_HEADER.split(",")
        values = {key: "0" for key in columns}
        values.update(mode="wfi_clock", cmd="", cmd_valid="0")
        line = ",".join(values[key] for key in columns)
        stream = (collector.WFI_HEADER + "\n" + line + "\n").encode()
        d.exact_stream(stream, "wfi")
        values.update(cmd="0x80000000", cmd_valid="1")
        modified = (collector.WFI_HEADER + "\n" +
                    ",".join(values[key] for key in columns) + "\n").encode()
        with self.assertRaises(a.PublicationError):
            d.exact_stream(modified, "wfi")

    def test_timeline_accepts_paired_auxiliary_reads_and_rejects_repeat_write(self):
        start, stop = 1_000, 2_000
        sequence = [
            (100, "begin", {"phase": "D"}),
            (200, "read_begin", {}), (300, "read_end", {}),
            (900, "window_begin", {"phase": "D", "mode": "wfi_clock"}),
            (920, "capture_write_begin", {"command": "wfi_clock 10000"}),
            (930, "capture_write_attempted", {"bytes": 16}),
            (940, "capture_write_end", d.CONTROL),
            (2_100, "window_end", {}),
            (2_200, "observer_raw_drained", {"errors": []}),
            (2_300, "workload_release_begin",
             {"token": "E", "reason": "window_ended", "cpus": [1, 5]}),
            (2_400, "workload_release_end", {"cpu": 1, "exit_status": 0}),
            (2_500, "workload_release_end", {"cpu": 5, "exit_status": 0}),
            (2_600, "command_begin", {}), (2_700, "command_end", {}),
            (2_800, "complete", {"phase": "D"}),
        ]
        with tempfile.TemporaryDirectory() as directory:
            packet = Path(directory)

            def save(rows):
                (packet / "timeline.jsonl").write_text("".join(
                    json.dumps({"monotonic_ns": tick, "action": action, **fields}) + "\n"
                    for tick, action, fields in rows))

            save(sequence)
            projected = d.check_timeline(packet, start, stop)
            self.assertEqual([row["action"] for row in projected], [
                row[1] for row in sequence if row[1] not in
                {"read_begin", "read_end", "command_begin", "command_end"}])
            save(sequence[:7] + [(950, "capture_write_attempted", {"bytes": 16})] +
                 sequence[7:])
            with self.assertRaises(a.PublicationError):
                d.check_timeline(packet, start, stop)

    def test_reviewed_public_packet_replays(self):
        d.verify_public_source_binding()
        d.verify_public_stage(reviewed_stage(self))

    def test_modified_public_packet_is_rejected(self):
        source = reviewed_stage(self)
        with tempfile.TemporaryDirectory() as directory:
            stage = Path(directory) / "abi3-D"
            shutil.copytree(source, stage)
            target = stage / "capture.json"
            target.write_bytes(target.read_bytes() + b"\n")
            with self.assertRaises(a.PublicationError):
                d.verify_public_stage(stage)

    def test_unmanifested_readme_does_not_change_data_replay(self):
        source = reviewed_stage(self)
        with tempfile.TemporaryDirectory() as directory:
            stage = Path(directory) / "abi3-D"
            shutil.copytree(source, stage)
            (stage / "README.md").write_text("Repository explanation; outside the data manifest.\n")
            d.verify_public_stage(stage)


if __name__ == "__main__":
    unittest.main()
