"""Synthetic PCPM export fixtures; these tests are not native evidence."""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


MODULE = Path(__file__).with_name("analyze.py")
SPEC = importlib.util.spec_from_file_location("pcpm_analyze", MODULE)
analyze = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(analyze)


def fixture(*, mode="mmio", requested=3, base=1000000000, worker=0):
    status = {
        "abi": 1, "state": "complete", "mode": mode, "error": 0,
        "requested": requested, "period_ms": 10, "phase_ms": 1,
        "start_ns": base, "end_ns": base + (2 + requested * 10) * 1000000,
        "budget_end_ns": base + (1 + requested * 10) * 1000000, "worker_cpu": worker,
        "start_online_mask": "0xff", "end_online_mask": "0xff",
        "e_mask": "0xf", "p_mask": "0xf0", "pmgr_phys": "0x23b700000",
        "pmgr_size": "0x14000", "register_offset": 72,
        "regmap_existing": 1, "regmap_internal_clockless": 1,
        "regmap_stride": 4, "regmap_val_bytes": 4, "attempted": requested,
        "missed_slots": 0, "unattempted_after_error": 0, "trailing_missed": 0,
        "read_errors": 0, "cpu_errors": 0,
    }
    for cpu in range(8):
        status[f"cpu{cpu}.midr"] = "0x610f0220" if cpu < 4 else "0x610f0230"
        status[f"cpu{cpu}.mpidr"] = hex((cpu // 4) * 0x10100 + cpu % 4)
        status[f"cpu{cpu}.kind"] = "E" if cpu < 4 else "P"
    rows = []
    for index in range(requested):
        scheduled = base + (1 + (index + 1) * 10) * 1000000
        rows.append(dict(zip(analyze.HEADER, (
            index, index, scheduled, 0, scheduled + 50, scheduled + 150,
            worker, worker, int(mode == "mmio"), int(mode == "mmio"),
            "0xf0" if mode == "mmio" else "", 0,
        ))))
    return rows, status


def serialize(rows, status, *, newline="\n"):
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=analyze.HEADER, lineterminator=newline)
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue(), "".join(f"{key}={value}{newline}" for key, value in status.items())


class PCPMDecoderTests(unittest.TestCase):
    def decode(self, rows=None, status=None, **kwargs):
        if rows is None:
            rows, status = fixture()
        return analyze.analyze_text(*serialize(rows, status), evidence_origin="synthetic_fixture", **kwargs)

    def test_numeric_actual_and_target_remain_distinct(self):
        result = self.decode()
        self.assertTrue(result["integrity"]["complete_lossless_schedule"])
        self.assertEqual(result["sampling"]["actual_code_counts"], [{"code": 15, "samples": 3}])
        self.assertEqual(result["sampling"]["target_code_counts"], [{"code": 0, "samples": 3}])
        self.assertEqual(result["sampling"]["actual_target_counts"], [{"actual_code": 15, "target_code": 0, "samples": 3}])
        self.assertEqual(result["claim_boundary"]["time_occupancy_or_residency"], "not_estimated")
        self.assertEqual(result["claim_boundary"]["rail_state_energy_or_linux_policy"], "no_conclusion")

    def test_zero_unknown_and_sticky_bits_are_raw_values(self):
        rows, status = fixture()
        for row, raw in zip(rows, ("0x0", "0x376", "0xffffffff")):
            row["raw"] = raw
        result = self.decode(rows, status)
        self.assertEqual(result["samples"][0]["raw_fields"]["actual_code"], 0)
        self.assertEqual(result["samples"][1]["raw_fields"], {
            "actual_code": 7, "target_code": 6, "sticky_bit8": 1, "sticky_bit9": 1})
        self.assertEqual(result["sampling"]["actual_code_counts"], [
            {"code": 0, "samples": 1}, {"code": 7, "samples": 1}, {"code": 15, "samples": 1}])
        self.assertNotIn("residency", result["sampling"])

    def test_records_only_has_no_state_and_no_mmio_duration(self):
        rows, status = fixture(mode="records")
        result = self.decode(rows, status)
        self.assertTrue(result["integrity"]["internally_consistent"])
        self.assertEqual(result["sampling"]["actual_code_counts"], [])
        self.assertEqual(result["sampling"]["read_attempts"], 0)
        self.assertEqual(result["sampling"]["mmio_attempt_bracket_ns"]["count"], 0)
        self.assertEqual(result["sampling"]["timing_bracket_ns"]["count"], 3)
        self.assertTrue(all(row["raw_fields"] is None for row in result["samples"]))

    def test_failed_read_retains_error_prior_success_and_unattempted_tail(self):
        rows, status = fixture()
        rows = rows[:2]
        rows[1].update(raw_valid=0, raw="", read_errno=-5)
        status.update(state="failed", error=-5, attempted=2, read_errors=1,
                      unattempted_after_error=1)
        result = self.decode(rows, status)
        self.assertTrue(result["integrity"]["internally_consistent"])
        self.assertFalse(result["integrity"]["complete_lossless_schedule"])
        self.assertEqual(result["samples"][1]["raw"]["read_errno"], -5)
        self.assertIsNone(result["samples"][1]["raw_fields"])
        self.assertEqual(result["sampling"]["eligible_successful_reads"], 1)
        self.assertEqual(result["sampling"]["unattempted_after_error"], 1)
        self.assertEqual(result["sampling"]["missed_slots"], 0)

    def test_skipped_and_trailing_slots_do_not_become_residency(self):
        rows, status = fixture(requested=4)
        rows = [rows[0], rows[2]]
        rows[1].update(seq=1, skipped_before=1)
        status.update(attempted=2, missed_slots=2, trailing_missed=1)
        result = self.decode(rows, status)
        self.assertTrue(result["integrity"]["internally_consistent"])
        self.assertFalse(result["integrity"]["complete_lossless_schedule"])
        self.assertEqual(result["sampling"]["eligible_successful_reads"], 2)
        self.assertEqual(result["sampling"]["missed_slots"], 2)
        self.assertEqual(result["sampling"]["unattempted_after_error"], 0)

    def test_all_slots_skipped_is_consistent_but_not_negative_state_evidence(self):
        _, status = fixture()
        status.update(attempted=0, missed_slots=3, trailing_missed=3)
        result = self.decode([], status)
        self.assertTrue(result["integrity"]["internally_consistent"])
        self.assertFalse(result["integrity"]["complete_lossless_schedule"])
        self.assertEqual(result["sampling"]["actual_code_counts"], [])
        self.assertEqual(result["sampling"]["missed_slots"], 3)
        self.assertEqual(result["sampling"]["unattempted_after_error"], 0)

    def test_terminal_errno_matches_read_or_cpu_error(self):
        rows, status = fixture(requested=1)
        rows[0].update(raw_valid=0, raw="", read_errno=-5)
        status.update(state="failed", error=-12, read_errors=1)
        self.assertIn("read_error_terminal_errno_mismatch", self.decode(rows, status)["integrity"]["errors"])
        rows[0]["cpu_after"] = 4
        status.update(error=-18, cpu_errors=1)
        result = self.decode(rows, status)
        self.assertNotIn("read_error_terminal_errno_mismatch", result["integrity"]["errors"])
        self.assertNotIn("cpu_error_terminal_errno_mismatch", result["integrity"]["errors"])

    def test_sequence_slot_and_missed_accounting_contradictions(self):
        mutations = (
            (lambda rows, status: rows[1].update(seq=0), "sequence_gap_duplicate_or_reordering"),
            (lambda rows, status: rows[1].update(slot=0), "slot_order_or_skipped_count_mismatch"),
            (lambda rows, status: rows[1].update(skipped_before=1), "slot_order_or_skipped_count_mismatch"),
        )
        for mutate, expected in mutations:
            rows, status = fixture()
            mutate(rows, status)
            result = self.decode(rows, status)
            self.assertIn(expected, result["samples"][1]["errors"])
            self.assertEqual(len(result["samples"]), 3)
            self.assertFalse(result["integrity"]["internally_consistent"])
        rows, status = fixture()
        status["missed_slots"] = 1
        result = self.decode(rows, status)
        self.assertIn("requested_slot_accounting_mismatch", result["integrity"]["errors"])
        self.assertIn("missed_slot_accounting_mismatch", result["integrity"]["errors"])

    def test_state_and_error_agreement(self):
        for updates, expected in (
            ({"error": -5}, "capture_state_error_mismatch"),
            ({"state": "failed"}, "capture_state_error_mismatch"),
            ({"error": 5}, "positive_capture_error"),
            ({"unattempted_after_error": 1}, "unattempted_tail_without_capture_failure"),
        ):
            rows, status = fixture()
            status.update(updates)
            self.assertIn(expected, self.decode(rows, status)["integrity"]["errors"])

    def test_read_validity_and_mode_contradictions_preserve_raw(self):
        for updates, expected in (
            ({"raw_valid": 0}, "raw_presence_disagrees_with_valid_flag"),
            ({"raw": ""}, "raw_presence_disagrees_with_valid_flag"),
            ({"read_errno": -5}, "read_status_disagrees_with_valid_flag"),
            ({"read_attempted": 0}, "unattempted_read_has_result"),
            ({"read_errno": 5}, "positive_read_errno"),
        ):
            rows, status = fixture()
            rows[0].update(updates)
            result = self.decode(rows, status)
            self.assertIn(expected, result["samples"][0]["errors"])
            self.assertFalse(result["samples"][0]["eligible_successful_read"])
        rows, status = fixture()
        status["mode"] = "records"
        self.assertIn("read_attempted_outside_mmio_worker_contract", self.decode(rows, status)["samples"][0]["errors"])

    def test_missing_mmio_attempt_is_distinct_from_read_error(self):
        rows, status = fixture()
        rows[0].update(read_attempted=0, raw_valid=0, raw="")
        result = self.decode(rows, status)
        self.assertIn("mmio_read_missing_on_worker", result["samples"][0]["errors"])
        self.assertEqual(result["sampling"]["read_errors"], 0)
        self.assertEqual(result["sampling"]["read_attempts"], 2)

    def test_cpu_before_mismatch_can_prevent_read(self):
        rows, status = fixture()
        rows = rows[:1]
        rows[0].update(cpu_before=4, cpu_after=4, read_attempted=0, raw_valid=0, raw="")
        status.update(state="failed", error=-18, attempted=1, cpu_errors=1,
                      unattempted_after_error=2)
        result = self.decode(rows, status)
        self.assertIn("actual_cpu_mismatch", result["samples"][0]["errors"])
        self.assertEqual(result["sampling"]["read_attempts"], 0)
        self.assertEqual(result["sampling"]["read_errors"], 0)

    def test_cpu_after_mismatch_retains_successful_raw_but_disqualifies_row(self):
        rows, status = fixture()
        rows = rows[:1]
        rows[0]["cpu_after"] = 4
        status.update(state="failed", error=-18, attempted=1, cpu_errors=1,
                      unattempted_after_error=2)
        result = self.decode(rows, status)
        self.assertEqual(result["samples"][0]["raw_fields"]["actual_code"], 15)
        self.assertFalse(result["samples"][0]["eligible_successful_read"])
        self.assertEqual(result["sampling"]["actual_code_counts"], [])

    def test_stop_after_first_read_error(self):
        rows, status = fixture()
        rows[0].update(read_errno=-5, raw_valid=0, raw="")
        status.update(state="failed", error=-5, read_errors=1)
        result = self.decode(rows, status)
        self.assertIn("capture_continued_after_acquisition_error", result["integrity"]["errors"])

    def test_schedule_time_and_lateness(self):
        result = self.decode()
        self.assertEqual(result["sampling"]["schedule_lateness_ns"], {
            "count": 3, "minimum_ns": 50, "maximum_ns": 50, "sum_ns": 150,
            "mean_ns": {"numerator": 150, "denominator": 3}})
        self.assertEqual(result["sampling"]["mmio_attempt_bracket_ns"]["mean_ns"], {
            "numerator": 300, "denominator": 3})
        rows, status = fixture()
        rows[0]["scheduled_ns"] += 1
        self.assertIn("scheduled_time_does_not_match_slot", self.decode(rows, status)["samples"][0]["errors"])

    def test_half_period_gap_and_postcheck_preemption(self):
        rows, status = fixture()
        rows[0]["t_after_ns"] = rows[1]["t_before_ns"] - 4999999
        self.assertIn("sample_gap_below_half_period", self.decode(rows, status)["samples"][1]["errors"])
        rows[0]["t_after_ns"] -= 1
        self.assertNotIn("sample_gap_below_half_period", self.decode(rows, status)["samples"][1]["errors"])
        # Preemption after the worker's scheduling check may carry a retained
        # read beyond due+period; that is lateness evidence, not a contradiction.
        rows, status = fixture(requested=1)
        rows[0]["t_before_ns"] += 10000000
        rows[0]["t_after_ns"] += 10000000
        status["end_ns"] = rows[0]["t_after_ns"] + 1
        self.assertTrue(self.decode(rows, status)["integrity"]["internally_consistent"])

    def test_negative_durations_retained_never_wrapped(self):
        rows, status = fixture()
        rows[0]["t_after_ns"] = rows[0]["t_before_ns"] - 1
        result = self.decode(rows, status)
        self.assertEqual(result["samples"][0]["bracket_duration_ns"], -1)
        self.assertIn("sample_clock_reversal_or_wrap", result["samples"][0]["errors"])
        self.assertEqual(result["sampling"]["timing_bracket_ns"]["count"], 2)

    def test_uint64_limit_schedule_math_and_exact_mean(self):
        rows, status = fixture(base=(1 << 63) - 10000000000)
        self.assertTrue(self.decode(rows, status)["integrity"]["internally_consistent"])
        rows, status = fixture(base=analyze.UINT64_MAX - 10000000000)
        self.assertIn("worker_schedule_budget_mismatch_or_overflow", self.decode(rows, status)["integrity"]["errors"])
        rows[0]["slot"] = (1 << 32) - 1
        result = self.decode(rows, status)
        self.assertIn("scheduled_time_does_not_match_slot", result["samples"][0]["errors"])
        values = [analyze.UINT64_MAX, analyze.UINT64_MAX - 1]
        stats = analyze.statistics(values)
        self.assertEqual(stats["sum_ns"], 2 * analyze.UINT64_MAX - 1)
        self.assertEqual(stats["mean_ns"]["denominator"], 2)

    def test_request_limits_and_budget(self):
        for updates, expected in (
            ({"requested": 1001}, "request_parameters_outside_abi_limits"),
            ({"period_ms": 9}, "request_parameters_outside_abi_limits"),
            ({"period_ms": 1001}, "request_parameters_outside_abi_limits"),
            ({"phase_ms": 10}, "request_parameters_outside_abi_limits"),
            ({"requested": 1000, "phase_ms": 1}, "requested_schedule_exceeds_ten_second_limit"),
        ):
            rows, status = fixture()
            status.update(updates)
            self.assertIn(expected, self.decode(rows, status)["integrity"]["errors"])
        rows, status = fixture()
        status["budget_end_ns"] += 1
        self.assertIn("worker_schedule_budget_mismatch_or_overflow", self.decode(rows, status)["integrity"]["errors"])

    def test_topology_and_resource_contradictions(self):
        for key, value, expected in (
            ("e_mask", "0xf0", "cpu_masks_do_not_partition_four_e_and_four_p_cpus"),
            ("end_online_mask", "0x7f", "online_topology_incomplete_or_changed"),
            ("worker_cpu", 4, "worker_is_not_recorded_e_cpu"),
            ("cpu0.midr", "0x610f0230", "cpu0_midr_kind_mismatch_or_unknown"),
            ("cpu0.mpidr", "0x1", "duplicate_cpu_affinity_identity"),
            ("cpu0.mpidr", "0x100", "cpu0_mpidr_topology_mismatch"),
            ("cpu4.mpidr", "0x100", "cpu4_mpidr_topology_mismatch"),
            ("pmgr_phys", "0x23b700004", "pmgr_phys_does_not_match_qualified_mapping_contract"),
            ("pmgr_size", "0x48", "register_outside_parent_resource"),
            ("regmap_existing", 0, "regmap_existing_does_not_match_qualified_mapping_contract"),
            ("regmap_internal_clockless", 0, "regmap_internal_clockless_does_not_match_qualified_mapping_contract"),
            ("regmap_stride", 8, "regmap_stride_does_not_match_qualified_mapping_contract"),
        ):
            rows, status = fixture()
            status[key] = value
            result = self.decode(rows, status)
            self.assertIn(expected, result["integrity"]["errors"])
            self.assertEqual(len(result["samples"]), 3)

    def test_logical_cpu_numbering_not_assumed(self):
        rows, status = fixture(worker=7)
        status.update(e_mask="0xf0", p_mask="0xf")
        for cpu in range(8):
            physical = (cpu + 4) % 8
            status[f"cpu{cpu}.midr"] = "0x610f0220" if physical < 4 else "0x610f0230"
            status[f"cpu{cpu}.mpidr"] = hex((physical // 4) * 0x10100 + physical % 4)
            status[f"cpu{cpu}.kind"] = "E" if physical < 4 else "P"
        self.assertTrue(self.decode(rows, status)["integrity"]["internally_consistent"])

    def test_unused_export_has_no_acquisition(self):
        _, status = fixture()
        for key in status:
            status[key] = "unknown" if key.endswith(".kind") else "0x0" if key in analyze.HEX_FIELDS or key.endswith((".midr", ".mpidr")) else 0
        status.update(abi=1, state="unused", mode="none", worker_cpu=-1, register_offset=72)
        result = self.decode([], status)
        self.assertTrue(result["integrity"]["internally_consistent"])
        self.assertFalse(result["integrity"]["complete_lossless_schedule"])
        self.assertEqual(result["sampling"]["eligible_successful_reads"], 0)

    def test_preflight_failure_preserves_partial_metadata_and_no_timing(self):
        _, status = fixture()
        status.update(state="failed", error=-19, attempted=0, unattempted_after_error=3,
                      start_ns=0, end_ns=0, budget_end_ns=0, worker_cpu=-1,
                      e_mask="0x0", p_mask="0x0")
        result = self.decode([], status)
        self.assertTrue(result["integrity"]["internally_consistent"])
        self.assertEqual(result["raw_status"]["error"], -19)
        self.assertEqual(result["sampling"]["timing_bracket_ns"]["count"], 0)
        # Existing regmap queries return signed ints, including error values.
        status.update(regmap_stride=-22, regmap_val_bytes=-22)
        self.assertEqual(self.decode([], status)["raw_status"]["regmap_val_bytes"], -22)

    def test_strict_schema_flags_widths_and_numbers(self):
        rows, status = fixture()
        events, info = serialize(rows, status)
        for bad_events, bad_status in (
            (events, info + "abi=1\n"), (events, info + "new=0\n"),
            (events, info.replace("abi=1\n", "abi=2\n")),
            (events, info.replace("requested=3\n", "requested=03\n")),
            (events, info.replace("requested=3\n", "requested=4294967296\n")),
            (events, info.replace("worker_cpu=0\n", "worker_cpu=-2147483649\n")),
            (events, info.replace("e_mask=0xf\n", "e_mask=0x100000000\n")),
            (events, info.replace("regmap_existing=1\n", "regmap_existing=2\n")),
            (events.replace("0xf0", "0x100000000", 1), info),
            (events.replace("0xf0", "240", 1), info),
            (events.replace(",1,1,0xf0,", ",2,1,0xf0,", 1), info),
            (events.replace("seq,", "sequence,", 1), info),
            (events + "0,0\n", info),
        ):
            with self.subTest(events=bad_events[:70], status=bad_status[:70]):
                with self.assertRaises(analyze.AnalysisError):
                    analyze.analyze_text(bad_events, bad_status)

    def test_default_input_origin_and_exact_byte_hashes(self):
        events, status = serialize(*fixture(), newline="\r\n")
        result = analyze.analyze_text(events, status)
        self.assertEqual(result["evidence_origin"], "unverified_input")
        self.assertEqual(result["inputs_sha256"]["events.csv"], hashlib.sha256(events.encode()).hexdigest())
        self.assertEqual(result["inputs_sha256"]["status.txt"], hashlib.sha256(status.encode()).hexdigest())
        with self.assertRaises(analyze.AnalysisError):
            analyze.analyze_text(events, status, evidence_origin="native")

    def test_cli_raw_bytes_and_errors_without_traceback(self):
        events, status = serialize(*fixture(), newline="\r\n")
        with tempfile.TemporaryDirectory() as directory:
            csv_path, status_path = Path(directory) / "events.csv", Path(directory) / "status.txt"
            csv_path.write_bytes(events.encode())
            status_path.write_bytes(status.encode())
            command = [sys.executable, str(MODULE), str(csv_path), str(status_path)]
            result = subprocess.run(command + ["--synthetic-fixture"], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            output = json.loads(result.stdout)
            self.assertEqual(output["evidence_origin"], "synthetic_fixture")
            self.assertEqual(output["inputs_sha256"]["events.csv"], hashlib.sha256(events.encode()).hexdigest())
            csv_path.write_bytes(b"\xff")
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertIn("PCPM sampler input error:", result.stderr)
            self.assertNotIn("Traceback", result.stderr)
            csv_path.write_text("wrong\n")
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
