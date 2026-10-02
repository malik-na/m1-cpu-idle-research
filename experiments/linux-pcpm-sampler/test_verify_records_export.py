#!/usr/bin/env python3
"""Boundary and tamper tests for the public PCPM records replay."""

from pathlib import Path
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify_records_export as replay


def synthetic_workload() -> dict:
    workers = []
    for cpu, entered, exited in ((4, 100, 500), (5, 110, 490),
                                 (6, 120, 480), (7, 130, 470)):
        phases = []
        for phase in range(1, 5):
            active = phase in (1, 4) or (phase == 2 and cpu == 4)
            phases.append({"phase": phase, "entered_ns": entered,
                           "exited_ns": exited, "entered_cpu": cpu,
                           "exited_cpu": cpu, "iterations": 10 if active else 0})
        workers.append({"cpu": cpu, "error": 0, "phases": phases})
    return {"workers": workers}


class ReplayTests(unittest.TestCase):
    def test_strict_counter_boundary_and_all_four_requirement(self):
        intervals = {cpu: [({"t1": 100, "token": 1, "seq": 0},
                            {"t0": 200, "seq": 1})] for cpu in range(4, 8)}
        self.assertFalse(replay.strict_contains(*intervals[4][0], 102, 197, 1, 1))
        self.assertFalse(replay.strict_contains(*intervals[4][0], 103, 198, 1, 1))
        self.assertTrue(replay.strict_contains(*intervals[4][0], 103, 197, 1, 1))
        sample = {"counter_before": 103, "counter_after": 197}
        self.assertEqual(len(replay.four_p_witness(sample, intervals, 1, 1)), 4)
        intervals[7] = []
        self.assertIsNone(replay.four_p_witness(sample, intervals, 1, 1))

    def test_measured_release_uses_latest_entry_and_earliest_exit(self):
        self.assertEqual(replay.measured_release_window(synthetic_workload(), guard_ns=30),
                         (160, 440))
        bad = synthetic_workload()
        bad["workers"][2]["phases"][2]["iterations"] = 1
        with self.assertRaisesRegex(replay.EvidenceError, "did not match plan"):
            replay.measured_release_window(bad, guard_ns=30)

    def test_non_reentrant_idle_grammar_and_capture_edges(self):
        rows = [
            {"kind": "idle_enter", "cpu": 4, "cluster": 1, "seq": 0,
             "token": 7, "t0": 10, "t1": 11, "ret": 0, "flags": 0},
            {"kind": "idle_exit", "cpu": 4, "cluster": 1, "seq": 1,
             "token": 7, "t0": 20, "t1": 21, "ret": 0, "flags": 0},
            {"kind": "idle_enter", "cpu": 4, "cluster": 1, "seq": 2,
             "token": 8, "t0": 30, "t1": 31, "ret": 0, "flags": 0},
        ]
        self.assertEqual(len(replay.complete_p_intervals(rows, 0, 25)[4]), 1)
        nested = rows[:1] + [dict(rows[0], seq=1, token=9)]
        with self.assertRaisesRegex(replay.EvidenceError, "nested idle_enter"):
            replay.complete_p_intervals(nested, 0, 25)

    def test_public_packet_and_hash_tamper(self):
        result = replay.verify_packet()
        self.assertEqual(result["measured_four_p_release"]
                         ["conditional_four_p_software_interval_brackets"], 21)
        self.assertFalse(result["model_and_boundary"]["pairwise_error_verified_for_capture"])
        with tempfile.TemporaryDirectory() as temp:
            destination = Path(temp) / "packet"
            shutil.copytree(replay.PACKET, destination)
            victim = destination / "pcpm-samples.csv.gz"
            victim.write_bytes(victim.read_bytes() + b"x")
            with self.assertRaisesRegex(replay.EvidenceError, "published hash mismatch"):
                replay.verify_packet(destination)


if __name__ == "__main__":
    unittest.main()
