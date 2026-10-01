"""Artificial ABI fixtures; none of these tests is native counter evidence."""

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
SPEC = importlib.util.spec_from_file_location("counter_analyze", MODULE)
analyze = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(analyze)


def fixture(*, rounds=2, reference=0, base=1000, offset=0):
    """Each synthetic remote CPU has the same constant offset from reference."""
    status = {
        "abi": 1, "possible_mask": "0xff", "cluster0_cpus": "0xf",
        "cluster1_cpus": "0xf0", "config_ool_workaround": 1,
        "ecv_alternative": 0, "capacity_per_phase": 1792,
    }
    rows = []
    for phase_no, phase in enumerate(analyze.PHASES):
        start = base + phase_no * 10000
        for key, value in {
            "state": "complete", "reference_cpu": reference, "rounds": rounds,
            "attempted": rounds * 7, "completed": rounds * 7, "error": 0,
            "metadata_completed": 8, "start_tick": start,
            "end_tick": start + rounds * 700 + 10,
            "start_online_mask": "0xff", "end_online_mask": "0xff",
        }.items():
            status[f"{phase}_{key}"] = value
        for cpu in range(8):
            for key, value in {
                "valid": 1, "actual": cpu, "error": 0, "cntfrq": 24000000,
                "cntkctl": "0x2", "mmfr0": "0x0", "workaround_present": 0,
                "phys_read_workaround": 0,
            }.items():
                status[f"{phase}_cpu{cpu}_{key}"] = value
        index = 0
        for round_no in range(rounds):
            for target in range(8):
                if target == reference:
                    continue
                a0 = start + 10 + index * 100
                seq = len(rows) + 1
                rows.append(dict(zip(analyze.HEADER, (
                    phase, round_no, seq, seq, reference, reference, reference,
                    target, target, a0, a0 + 2 + offset, a0 + 3 + offset,
                    a0 + 5, 24000000, 24000000, 0, 15,
                ))))
                index += 1
    return rows, status


def serialize(rows, status):
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=analyze.HEADER, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue(), "".join(f"{key}={value}\n" for key, value in status.items())


class CounterDecoderTests(unittest.TestCase):
    def decode(self, rows=None, status=None, **kwargs):
        if rows is None:
            rows, status = fixture()
        return analyze.analyze_text(*serialize(rows, status), evidence_origin="synthetic_fixture", **kwargs)

    def test_complete_star_and_pair_differences(self):
        result = self.decode(pairwise_tolerance_ticks=4, endpoint_uncertainty_ticks=0)
        self.assertTrue(result["shared_pre_post_model"]["both_phases_eligible"])
        model = result["phases"]["pre"]["uncertainty_adjusted_stable_offset_model"]
        self.assertEqual(len(model["derived_pairs"]), 28)
        refpair = next(p for p in model["derived_pairs"] if p["source"] == 0 and p["target"] == 1)
        remote = next(p for p in model["derived_pairs"] if p["source"] == 1 and p["target"] == 2)
        self.assertEqual(refpair["interval_ticks"], {"lower": -2, "upper": 2, "width": 4})
        self.assertEqual(remote["interval_ticks"], {"lower": -4, "upper": 4, "width": 8})
        self.assertTrue(all(p["tolerance_classification"] == "constrained_within_tolerance_under_model" for p in model["derived_pairs"]))
        self.assertEqual(result["claim_boundary"]["unsampled_capture_interval"], "not_qualified")
        self.assertEqual(result["claim_boundary"]["guaranteed_pairwise_error_bound"], "not_established")

    def test_defaults_show_raw_constraints_without_classifying(self):
        result = self.decode()
        self.assertEqual(result["exchanges"][0]["raw_offset_interval_ticks"]["lower"], -2)
        self.assertEqual(result["exchanges"][0]["tolerance_classification"], "unavailable_without_predeclared_tolerance")
        self.assertIsNone(result["exchanges"][0]["uncertainty_adjusted_interval_ticks"])
        self.assertEqual(result["phases"]["pre"]["uncertainty_adjusted_stable_offset_model"]["status"], "unavailable_without_endpoint_uncertainty")
        result = self.decode(pairwise_tolerance_ticks=4)
        self.assertEqual(result["exchanges"][0]["tolerance_classification"], "unavailable_without_endpoint_uncertainty")

    def test_positive_and_negative_offsets_and_nonzero_reference(self):
        for offset in (-20, 20):
            rows, status = fixture(offset=offset, reference=4)
            result = self.decode(rows, status, pairwise_tolerance_ticks=10, endpoint_uncertainty_ticks=0)
            interval = result["exchanges"][0]["raw_offset_interval_ticks"]
            self.assertEqual((interval["lower"], interval["upper"]), (offset - 2, offset + 2))
            self.assertEqual(result["exchanges"][0]["tolerance_classification"], "contradicts_tolerance_under_model")
            # Stored unordered pair 0 -> 4 is the inverse of sampled 4 -> 0.
            pairs = result["phases"]["pre"]["uncertainty_adjusted_stable_offset_model"]["derived_pairs"]
            inverse = next(p for p in pairs if p["source"] == 0 and p["target"] == 4)
            self.assertEqual(inverse["interval_ticks"]["lower"], -offset - 2)

    def test_closed_tolerance_boundaries_and_partial_intersection(self):
        for bounds, expected in (
            ((-4, 4), "constrained_within_tolerance_under_model"),
            ((4, 6), "inconclusive"), ((-6, -4), "inconclusive"),
            ((5, 6), "contradicts_tolerance_under_model"),
            ((-6, -5), "contradicts_tolerance_under_model"),
        ):
            self.assertEqual(analyze.classification(analyze.interval(*bounds), 4, 0), expected)

    def test_outward_uncertainty_applied_once_and_never_silently_zero(self):
        result = self.decode(pairwise_tolerance_ticks=2, endpoint_uncertainty_ticks=1)
        row = result["exchanges"][0]
        self.assertEqual(row["uncertainty_adjusted_interval_ticks"], {"lower": -3, "upper": 3, "width": 6})
        self.assertEqual(row["tolerance_classification"], "inconclusive")
        result = self.decode(endpoint_uncertainty_ticks=analyze.UINT64_MAX)
        self.assertLess(result["exchanges"][0]["uncertainty_adjusted_interval_ticks"]["lower"], -analyze.UINT64_MAX)

    def test_uint64_boundary_preserves_raw_and_signed_math(self):
        for base, offset in (
            (analyze.UINT64_MAX - 20000, -100),
            (1000, analyze.UINT64_MAX - 20000),
            (analyze.UINT64_MAX - 20000, -(analyze.UINT64_MAX - 30000)),
        ):
            rows, status = fixture(base=base, offset=offset)
            result = self.decode(rows, status)
            with self.subTest(base=base, offset=offset):
                self.assertTrue(result["shared_pre_post_model"]["both_phases_eligible"])
                self.assertEqual(result["exchanges"][0]["raw"]["a0"], rows[0]["a0"])
                self.assertEqual(result["exchanges"][0]["raw_offset_interval_ticks"]["lower"], offset - 2)

    def test_local_reversal_and_negative_width_are_not_fixed_by_uncertainty(self):
        for update, expected in (({"a1": 1009}, "local_counter_reversal_or_wrap"),
                                 ({"b1": 1020}, "negative_causal_interval_width")):
            rows, status = fixture()
            rows[0].update(update)
            result = self.decode(rows, status, endpoint_uncertainty_ticks=100)
            self.assertIn(expected, result["exchanges"][0]["errors"])
            self.assertFalse(result["phases"]["pre"]["acquisition_eligible_for_conditional_model"])
            self.assertIsNotNone(result["exchanges"][0]["raw_offset_interval_ticks"])

    def test_empty_intersection_retains_every_round_and_falsifies_model(self):
        rows, status = fixture()
        rows[7]["b0"] += 10
        rows[7]["b1"] += 10
        result = self.decode(rows, status, endpoint_uncertainty_ticks=0)
        self.assertEqual(len(result["exchanges"]), 28)
        phase = result["phases"]["pre"]
        self.assertTrue(phase["acquisition_eligible_for_conditional_model"])
        model = phase["uncertainty_adjusted_stable_offset_model"]
        self.assertEqual(model["status"], "empty_intersection_falsifies_stable_offset_model")
        self.assertEqual(model["derived_pairs"], [])
        self.assertTrue(model["star_intersections"][0]["empty"])

    def test_raw_and_uncertainty_adjusted_models_remain_distinct(self):
        rows, status = fixture()
        rows[7]["b0"] += 5
        rows[7]["b1"] += 5
        result = self.decode(rows, status, endpoint_uncertainty_ticks=1)
        phase = result["phases"]["pre"]
        self.assertEqual(phase["raw_stable_offset_model"]["status"], "empty_intersection_falsifies_stable_offset_model")
        self.assertEqual(phase["uncertainty_adjusted_stable_offset_model"]["status"], "nonempty_conditional_constraints")

    def test_pre_post_consistency_requires_stronger_stability_model(self):
        rows, status = fixture()
        for row in rows:
            if row["phase"] == "post":
                row["b0"] += 10
                row["b1"] += 10
        result = self.decode(rows, status, endpoint_uncertainty_ticks=0)
        self.assertTrue(all(p["acquisition_eligible_for_conditional_model"] for p in result["phases"].values()))
        self.assertEqual(result["shared_pre_post_model"]["raw_stable_offset_model"]["status"], "empty_intersection_falsifies_stable_offset_model")

    def test_missing_row_sequence_duplicate_and_wrong_target_order(self):
        for mutation in (lambda rows: rows.pop(2),
                         lambda rows: rows[1].update(request_seq=1),
                         lambda rows: rows[1].update(target_requested=1)):
            rows, status = fixture()
            mutation(rows)
            result = self.decode(rows, status)
            self.assertFalse(result["shared_pre_post_model"]["both_phases_eligible"])
            self.assertFalse(result["phases"]["pre"]["acquisition_eligible_for_conditional_model"])

    def test_failed_phase_preserves_errors_missing_fields_and_counts(self):
        rows, status = fixture()
        rows[0].update(call_status=-6, flags=9, b0="", b1="", target_actual=-1,
                       target_cntfrq="", ack_seq=0)
        status.update(pre_state="failed", pre_error=-6, pre_completed=13)
        result = self.decode(rows, status)
        row = result["exchanges"][0]
        self.assertEqual(row["raw"]["call_status"], -6)
        self.assertIsNone(row["raw"]["b0"])
        self.assertIsNone(row["raw_offset_interval_ticks"])
        self.assertIn("recorded_phase_error", result["phases"]["pre"]["errors"])

    def test_unused_post_retains_pre_only_without_bracketing_claim(self):
        rows, status = fixture()
        rows = [row for row in rows if row["phase"] == "pre"]
        status.update(post_state="unused", post_reference_cpu=-1, post_rounds=0,
                      post_attempted=0, post_completed=0, post_error=0,
                      post_metadata_completed=0, post_start_tick="", post_end_tick="",
                      post_start_online_mask="0x0", post_end_online_mask="0x0")
        for n in range(8):
            for field in analyze.META_FIELDS:
                status[f"post_cpu{n}_{field}"] = {"actual": -1, "error": 0, "valid": 0}.get(field, "")
        result = self.decode(rows, status)
        self.assertTrue(result["phases"]["pre"]["acquisition_eligible_for_conditional_model"])
        self.assertFalse(result["shared_pre_post_model"]["both_phases_eligible"])

    def test_frequency_identity_ack_or_reader_errors_suppress_inference(self):
        for key, value in (("source_cntfrq", 0), ("target_cntfrq", 24000001),
                           ("source_after", 2), ("target_actual", -1), ("ack_seq", 0)):
            rows, status = fixture()
            rows[0][key] = value
            self.assertFalse(self.decode(rows, status)["exchanges"][0]["eligible_exchange"])
        rows, status = fixture()
        status["pre_cpu1_phys_read_workaround"] = 1
        result = self.decode(rows, status)
        self.assertIn("cpu1_raw_counter_reader_unqualified", result["phases"]["pre"]["errors"])

    def test_metadata_changes_and_phase_time_reversal_suppress_joint_model(self):
        for field, value in (("post_cpu2_cntkctl", "0x3"), ("post_reference_cpu", 1),
                             ("post_start_tick", 0), ("post_cpu1_mmfr0", "0x100")):
            rows, status = fixture()
            status[field] = value
            result = self.decode(rows, status)
            self.assertFalse(result["shared_pre_post_model"]["both_phases_eligible"])

    def test_impossible_post_contract_is_not_an_eligible_individual_phase(self):
        for field, value in (("pre_state", "failed"), ("pre_rounds", 3),
                             ("pre_reference_cpu", 1), ("post_cpu2_cntkctl", "0x3")):
            rows, status = fixture()
            status[field] = value
            result = self.decode(rows, status)
            with self.subTest(field=field):
                self.assertFalse(result["phases"]["post"]["acquisition_eligible_for_conditional_model"])
                self.assertEqual(result["phases"]["post"]["raw_stable_offset_model"]["status"],
                                 "suppressed_acquisition_failure")

    def test_topology_requires_two_four_cpu_clusters(self):
        rows, status = fixture()
        status.update(cluster0_cpus="0x1", cluster1_cpus="0xfe")
        result = self.decode(rows, status)
        self.assertIn("cluster_masks_do_not_partition_two_four_cpu_clusters", result["global_errors"])
        self.assertFalse(result["phases"]["pre"]["acquisition_eligible_for_conditional_model"])

    def test_frequency_width_is_uint32_in_metadata_and_rows(self):
        for location in ("metadata", "source_cntfrq", "target_cntfrq"):
            rows, status = fixture()
            if location == "metadata":
                status["pre_cpu0_cntfrq"] = 1 << 32
            else:
                rows[0][location] = 1 << 32
            with self.assertRaises(analyze.AnalysisError):
                self.decode(rows, status)

    def test_local_monotonicity_across_rounds(self):
        rows, status = fixture()
        for field in ("a0", "a1", "b0", "b1"):
            rows[7][field] -= 700
        result = self.decode(rows, status)
        self.assertIn("source_counter_reversed_between_rounds", result["phases"]["pre"]["errors"])

    def test_malformed_key_flags_integer_width_and_missing_cell_rejected(self):
        for key, value in (("flags", 16), ("flags", 7), ("a0", 1 << 64),
                           ("round", 1 << 32), ("source_requested", 8),
                           ("source_before", -2), ("a0", "01")):
            rows, status = fixture()
            rows[0][key] = value
            with self.assertRaises(analyze.AnalysisError, msg=key):
                self.decode(rows, status)
        rows, status = fixture()
        status["future_key"] = 1
        with self.assertRaises(analyze.AnalysisError):
            self.decode(rows, status)
        del status["future_key"]
        text, status_text = serialize(rows, status)
        with self.assertRaises(analyze.AnalysisError):
            analyze.analyze_text(text, status_text + "abi=1\n")
        with self.assertRaises(analyze.AnalysisError):
            analyze.analyze_text(text.replace(",0,15\n", ",0\n", 1), status_text)
        with self.assertRaises(analyze.AnalysisError):
            analyze.analyze_text('"unfinished header', status_text)

    def test_option_validation(self):
        for value in (True, -1, 1 << 64, 0.5, "0"):
            with self.assertRaises(analyze.AnalysisError):
                self.decode(pairwise_tolerance_ticks=value)
            with self.assertRaises(analyze.AnalysisError):
                self.decode(endpoint_uncertainty_ticks=value)

    def test_cli_labels_synthetic_and_defaults_unverified(self):
        events, status = serialize(*fixture())
        with tempfile.TemporaryDirectory() as folder:
            events_path, status_path = Path(folder) / "events.csv", Path(folder) / "status.txt"
            events_path.write_text(events)
            status_path.write_text(status)
            command = [sys.executable, str(MODULE), str(events_path), str(status_path)]
            for extra, label in (([], "unverified_input"), (["--synthetic-fixture"], "synthetic_fixture")):
                completed = subprocess.run(command + extra, capture_output=True, text=True, check=True)
                self.assertEqual(json.loads(completed.stdout)["evidence_origin"], label)
            completed = subprocess.run(command + ["--pairwise-tolerance-ticks", "-1"], capture_output=True, text=True)
            self.assertEqual(completed.returncode, 2)
            self.assertNotIn("Traceback", completed.stderr)

    def test_cli_hashes_exact_crlf_input_bytes(self):
        events, status = serialize(*fixture())
        events = events.replace("\n", "\r\n").encode("utf-8")
        status = status.replace("\n", "\r\n").encode("utf-8")
        with tempfile.TemporaryDirectory() as folder:
            events_path, status_path = Path(folder) / "events.csv", Path(folder) / "status.txt"
            events_path.write_bytes(events)
            status_path.write_bytes(status)
            completed = subprocess.run([sys.executable, str(MODULE), str(events_path), str(status_path)],
                                       capture_output=True, text=True, check=True)
            hashes = json.loads(completed.stdout)["inputs_sha256"]
            self.assertEqual(hashes["events.csv"], hashlib.sha256(events).hexdigest())
            self.assertEqual(hashes["status.txt"], hashlib.sha256(status).hexdigest())


if __name__ == "__main__":
    unittest.main()
