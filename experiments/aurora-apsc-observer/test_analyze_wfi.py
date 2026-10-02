"""Synthetic ABI 2 boundary cases; none is a hardware observation."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

import analyze_wfi


BASE_TESTS = Path(__file__).resolve().parents[1] / "linux-apsc-observer" / "test_analyze.py"
spec = importlib.util.spec_from_file_location("apsc_v1_fixtures", BASE_TESTS)
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)

WFI_HEADER = "seq,cpu,cluster,token,t0,t1,cmd,mode\n"


def status(*, mode="wfi_mmio", idle=(2, 2, 0, 0), wfi=(1, 1, 0, 0), pending=0,
           after_stop=0, bad_mapping=0):
    base = fixtures.status(mode="records", overrides={"idle0": idle})
    base = base.replace("abi=1\n", "abi=2\n").replace("mode=records\n", f"mode={mode}\n")
    lines = [f"wfi_pending_after_drain={pending}",
             f"wfi_prepare_after_stop={after_stop}",
             f"wfi_prepare_bad_mapping={bad_mapping}"]
    for cpu in range(8):
        values = wfi if cpu == 0 else (0, 0, 0, 0)
        lines.extend(f"wfi{cpu}_{field}={value}" for field, value in zip(analyze_wfi.WFI_FIELDS, values))
    return base + "\n".join(lines) + "\n"


def events():
    return fixtures.event_csv(
        fixtures.record("idle_enter", 0, 0, 0, token=1, t0=20, t1=21),
        fixtures.record("idle_exit", 1, 0, 0, token=1, t0=40, t1=40),
    )


class WfiAnalyzerTests(unittest.TestCase):
    def test_valid_mmio_busy_is_bounded_to_probe_site(self):
        result = analyze_wfi.analyze_text(
            events(), status(), WFI_HEADER + "0,0,0,1,25,26,0x80000000,wfi_mmio\n"
        )
        self.assertTrue(result["integrity"]["clean"])
        self.assertEqual(result["wfi_probe"]["by_cluster"]["0"]["busy_bit31"], 1)
        self.assertEqual(result["wfi_probe"]["in_window"], 1)
        self.assertEqual(result["reverse_coverage"]["counts"]["matched_wfi_sample"], 1)
        self.assertEqual(result["claim_boundary"]["wfi_instruction_command_state"], "not_observed")

    def test_clock_mode_requires_blank_command(self):
        valid = analyze_wfi.analyze_text(
            events(), status(mode="wfi_clock"), WFI_HEADER + "0,0,0,1,25,26,,wfi_clock\n"
        )
        self.assertTrue(valid["integrity"]["clean"])
        self.assertIsNone(valid["wfi_probe"]["by_cluster"]["0"]["busy_bit31"])
        with self.assertRaisesRegex(analyze_wfi.legacy.AnalysisError, "command presence"):
            analyze_wfi.analyze_text(
                events(), status(mode="wfi_clock"), WFI_HEADER + "0,0,0,1,25,26,0x0,wfi_clock\n"
            )

    def test_uncommitted_slot_and_pending_drain_fail_integrity(self):
        result = analyze_wfi.analyze_text(
            events(), status(wfi=(2, 1, 0, 1), pending=1),
            WFI_HEADER + "0,0,0,1,25,26,0x0,wfi_mmio\n",
        )
        self.assertFalse(result["integrity"]["clean"])
        self.assertIn("wfi0: missing_commit=1", result["integrity"]["reasons"])
        self.assertIn("wfi_pending_after_drain=1", result["integrity"]["reasons"])

    def test_sample_without_matching_idle_entry_fails_integrity(self):
        result = analyze_wfi.analyze_text(
            fixtures.event_csv(), status(idle=(0, 0, 0, 0)),
            WFI_HEADER + "0,0,0,1,25,26,0x0,wfi_mmio\n",
        )
        self.assertFalse(result["integrity"]["clean"])
        self.assertTrue(any("no matching idle_enter" in reason for reason in result["integrity"]["reasons"]))

    def test_non_wfi_capture_rejects_wfi_rows(self):
        with self.assertRaisesRegex(analyze_wfi.legacy.AnalysisError, "sample mode"):
            analyze_wfi.analyze_text(
                events(), status(mode="records"), WFI_HEADER + "0,0,0,1,25,26,0x0,wfi_mmio\n"
            )

    def test_abi2_records_capture_with_empty_wfi_stream_is_clean(self):
        result = analyze_wfi.analyze_text(
            events(), status(mode="records", wfi=(0, 0, 0, 0)), WFI_HEADER
        )
        self.assertTrue(result["integrity"]["clean"])
        self.assertEqual(result["wfi_probe"]["total"], 0)
        self.assertEqual(result["reverse_coverage"]["status"], "not_applicable_in_non_wfi_mode")

    def test_paired_active_path_without_wfi_sample_fails_even_with_after_stop_diagnostic(self):
        result = analyze_wfi.analyze_text(
            events(), status(wfi=(0, 0, 0, 0), after_stop=1), WFI_HEADER
        )
        self.assertFalse(result["integrity"]["clean"])
        self.assertEqual(result["reverse_coverage"]["counts"]["unexplained_paired_path_without_sample"], 1)
        self.assertEqual(result["reverse_coverage"]["per_token"][0]["disposition"],
                         "unexplained_paired_path_without_sample")

    def test_paired_path_check_does_not_assume_cross_cpu_stop_tick_order(self):
        edge_pair = fixtures.event_csv(
            fixtures.record("idle_enter", 0, 0, 0, token=1, t0=20, t1=21),
            fixtures.record("idle_exit", 1, 0, 0, token=1, t0=95, t1=95),
        )
        result = analyze_wfi.analyze_text(
            edge_pair, status(wfi=(0, 0, 0, 0), after_stop=1), WFI_HEADER
        )
        self.assertFalse(result["integrity"]["clean"])
        self.assertEqual(result["reverse_coverage"]["counts"]["unexplained_paired_path_without_sample"], 1)

    def test_open_interval_without_sample_is_explicitly_unresolved(self):
        entry_only = fixtures.event_csv(fixtures.record("idle_enter", 0, 0, 0, token=1, t0=20, t1=21))
        result = analyze_wfi.analyze_text(
            entry_only, status(idle=(1, 1, 0, 0), wfi=(0, 0, 0, 0), after_stop=1), WFI_HEADER
        )
        self.assertTrue(result["integrity"]["clean"])
        self.assertEqual(result["reverse_coverage"]["counts"]["open_interval_without_sample_unresolved"], 1)
        self.assertEqual(result["reverse_coverage"]["wfi_prepare_after_stop"], 1)

    def test_post_stop_busy_is_excluded_from_primary_in_window_counts(self):
        entry_only = fixtures.event_csv(fixtures.record("idle_enter", 0, 0, 0, token=1, t0=20, t1=21))
        result = analyze_wfi.analyze_text(
            entry_only, status(idle=(1, 1, 0, 0)),
            WFI_HEADER + "0,0,0,1,95,96,0x80000000,wfi_mmio\n",
        )
        self.assertTrue(result["integrity"]["clean"])
        self.assertEqual(result["wfi_probe"]["by_cluster"]["0"]["busy_bit31"], 0)
        self.assertEqual(result["wfi_probe"]["by_capture_partition"]["post_stop_drain"]["by_cluster"]["0"]["busy_bit31"], 1)

    def test_bad_mapping_counter_invalidates_capture(self):
        result = analyze_wfi.analyze_text(
            events(), status(bad_mapping=1), WFI_HEADER + "0,0,0,1,25,26,0x0,wfi_mmio\n"
        )
        self.assertFalse(result["integrity"]["clean"])
        self.assertIn("wfi_prepare_bad_mapping=1", result["integrity"]["reasons"])


if __name__ == "__main__":
    unittest.main()
