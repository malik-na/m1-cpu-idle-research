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
           after_stop=0, bad_mapping=0, overrides=None, wfi_by_cpu=None,
           start="0", stop="90", end="100"):
    base = fixtures.status(mode="records", overrides={"idle0": idle, **(overrides or {})},
                           start=start, stop=stop, end=end)
    base = base.replace("abi=1\n", "abi=2\n").replace("mode=records\n", f"mode={mode}\n")
    lines = [f"wfi_pending_after_drain={pending}",
             f"wfi_prepare_after_stop={after_stop}",
             f"wfi_prepare_bad_mapping={bad_mapping}"]
    for cpu in range(8):
        values = (wfi_by_cpu or {}).get(cpu, wfi if cpu == 0 else (0, 0, 0, 0))
        lines.extend(f"wfi{cpu}_{field}={value}" for field, value in zip(analyze_wfi.WFI_FIELDS, values))
    return base + "\n".join(lines) + "\n"


def events():
    return fixtures.event_csv(
        fixtures.record("idle_enter", 0, 0, 0, token=1, t0=20, t1=21),
        fixtures.record("idle_exit", 1, 0, 0, token=1, t0=40, t1=40),
    )


def pairing_packet(sets, probes, *, mode="wfi_mmio", pending=0, stop=10000):
    """Valid synthetic ABI 2 packet with independently ordered stream IDs."""
    rows = []
    overrides = {"idle0": (0, 0, 0, 0)}
    for cluster in (0, 1):
        writes = sorted((item for item in sets if item[1] == cluster), key=lambda item: item[2])
        overrides[f"dvfs{cluster}"] = (len(writes), len(writes), 0, 0)
        for seq, (cpu, _, t0, t1) in enumerate(writes):
            rows.append(fixtures.record(
                "dvfs", seq, cpu, cluster, policy_cpu=0 if cluster == 0 else 4,
                policy_mask="0x0f" if cluster == 0 else "0xf0", fast_switch=1,
                t0=t0, t1=t1, pre_cmd="0x0", cmd="0x2000000",
            ))
    wfi_lines = [WFI_HEADER]
    wfi_by_cpu = {}
    for cpu in range(8):
        own = sorted((item for item in probes if item[0] == cpu), key=lambda item: item[3])
        count = len(own)
        overrides[f"idle{cpu}"] = (2 * count, 2 * count, 0, 0)
        wfi_by_cpu[cpu] = (count, count, 0, 0)
        for seq, (_, cluster, token, t0, t1, cmd) in enumerate(own):
            rows.append(fixtures.record("idle_enter", 2 * seq, cpu, cluster,
                                        token=token, t0=t0 - 10, t1=t0 - 9))
            rows.append(fixtures.record("idle_exit", 2 * seq + 1, cpu, cluster,
                                        token=token, t0=t1 + 10, t1=t1 + 10))
            wfi_lines.append(f"{seq},{cpu},{cluster},{token},{t0},{t1},"
                             f"{hex(cmd) if mode == 'wfi_mmio' else ''},{mode}\n")
    return (fixtures.event_csv(*rows),
            status(mode=mode, idle=(0, 0, 0, 0), wfi=(0, 0, 0, 0),
                   overrides=overrides, wfi_by_cpu=wfi_by_cpu,
                   start="0", stop=str(stop), end=str(stop + 1000), pending=pending),
            "".join(wfi_lines))


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

    def test_same_cpu_549_tick_busy_pair_meets_primary_gate_without_pairwise_error(self):
        result = analyze_wfi.analyze_text(*pairing_packet(
            [(0, 0, 1000, 1001)], [(0, 0, 1, 1550, 1551, 0x80000000)]
        ))
        self.assertTrue(result["integrity"]["clean"])
        pair = result["paired_opportunities"]
        self.assertEqual(pair["by_cluster"]["0"]["primary_pairs"], 1)
        self.assertEqual(pair["by_cluster"]["0"]["primary_busy"], 1)
        self.assertEqual(pair["decisions"][0]["set_sample_order_basis"],
                         "same_cpu_direct_order_and_lag")
        self.assertEqual(pair["by_cluster"]["0"]["primary_model_qualified_pairs_with_same_cpu_set_sample"], 1)
        self.assertIn("model-qualified", pair["pair_count_scope"])
        self.assertIn("not an assumption-free full paired opportunity", pair["same_cpu_local_order_scope"])
        self.assertEqual(pair["decisions"][0]["largest_lag_under_model_ticks"], 549)
        self.assertFalse(pair["by_cluster"]["0"]["primary_exposure_gate_20"])
        self.assertFalse(pair["negative_claim_supported"])

    def test_cross_cpu_requires_error_for_both_order_and_maximum_lag(self):
        result = analyze_wfi.analyze_text(*pairing_packet(
            [(0, 0, 1000, 1001)], [(1, 0, 1, 1302, 1303, 0)]
        ))
        pair = result["paired_opportunities"]
        self.assertEqual(pair["by_cluster"]["0"]["primary_model_qualified_pairs_with_cross_cpu_set_sample"], 1)
        self.assertEqual(pair["decisions"][0]["largest_lag_under_model_ticks"], 541)
        self.assertEqual(pair["decisions"][0]["set_sample_order_error_ticks"], 240)
        later = analyze_wfi.analyze_text(*pairing_packet(
            [(0, 0, 1000, 1001)], [(1, 0, 1, 1550, 1551, 0)]
        ))["paired_opportunities"]
        self.assertEqual(later["by_cluster"]["0"]["primary_pairs"], 0)
        self.assertEqual(later["by_cluster"]["0"]["exploratory_pairs"], 1)

    def test_cross_cpu_primary_threshold_includes_exact_600_only(self):
        at_bound = analyze_wfi.analyze_text(*pairing_packet(
            [(0, 0, 1000, 1001)], [(1, 0, 1, 1361, 1362, 0)]
        ))["paired_opportunities"]
        beyond = analyze_wfi.analyze_text(*pairing_packet(
            [(0, 0, 1000, 1001)], [(1, 0, 1, 1362, 1363, 0)]
        ))["paired_opportunities"]
        self.assertEqual(at_bound["by_cluster"]["0"]["primary_pairs"], 1)
        self.assertEqual(at_bound["decisions"][0]["largest_lag_under_model_ticks"], 600)
        self.assertEqual(beyond["by_cluster"]["0"]["primary_pairs"], 0)
        self.assertEqual(beyond["by_cluster"]["0"]["exploratory_pairs"], 1)

    def test_ambiguous_cross_cpu_order_blocks_a_later_sample(self):
        pair = analyze_wfi.analyze_text(*pairing_packet(
            [(0, 0, 1000, 1001)],
            [(1, 0, 1, 1200, 1201, 0), (0, 0, 1, 1550, 1551, 0)]
        ))["paired_opportunities"]
        self.assertEqual(pair["decisions"][0]["status"], "ambiguous_set_sample_order")
        self.assertEqual(pair["by_cluster"]["0"]["primary_pairs"], 0)

    def test_ambiguous_cluster_earliest_order_blocks_pair(self):
        pair = analyze_wfi.analyze_text(*pairing_packet(
            [(0, 0, 1000, 1001)],
            [(0, 0, 1, 1550, 1551, 0), (1, 0, 1, 1600, 1601, 0)]
        ))["paired_opportunities"]
        self.assertEqual(pair["decisions"][0]["status"], "ambiguous_earliest_sample")
        self.assertEqual(pair["by_cluster"]["0"]["primary_pairs"], 0)

    def test_same_cpu_candidate_is_not_full_pair_with_cross_cpu_competitor(self):
        source = (0, 0, 1000, 1001)
        same_cpu_candidate = (0, 0, 1, 1550, 1551, 0)
        competing_sample = analyze_wfi.analyze_text(*pairing_packet(
            [source], [same_cpu_candidate, (1, 0, 1, 1600, 1601, 0)]
        ))["paired_opportunities"]
        competing_write = analyze_wfi.analyze_text(*pairing_packet(
            [source, (1, 0, 1400, 1401)], [same_cpu_candidate]
        ))["paired_opportunities"]
        self.assertEqual(competing_sample["decisions"][0]["status"], "ambiguous_earliest_sample")
        self.assertEqual(competing_write["decisions"][0]["status"], "possible_intervening_set")
        self.assertEqual(competing_sample["by_cluster"]["0"]["primary_pairs"], 0)
        self.assertEqual(competing_write["by_cluster"]["0"]["primary_pairs"], 0)

    def test_intervening_cluster_set_excludes_earlier_submission(self):
        pair = analyze_wfi.analyze_text(*pairing_packet(
            [(0, 0, 1000, 1001), (1, 0, 1300, 1301)],
            [(0, 0, 1, 1550, 1551, 0)]
        ))["paired_opportunities"]
        self.assertEqual(pair["decisions"][0]["status"], "possible_intervening_set")
        self.assertEqual(pair["decisions"][1]["status"], "primary_pair")
        self.assertEqual(pair["by_cluster"]["0"]["primary_pairs"], 1)

    def test_exploratory_bound_is_separate_from_primary(self):
        pair = analyze_wfi.analyze_text(*pairing_packet(
            [(0, 0, 1000, 1001)], [(0, 0, 1, 3401, 3402, 0)]
        ))["paired_opportunities"]
        self.assertEqual(pair["decisions"][0]["status"], "exploratory_only_pair")
        self.assertEqual(pair["by_cluster"]["0"]["primary_pairs"], 0)
        self.assertEqual(pair["by_cluster"]["0"]["exploratory_pairs"], 1)

    def test_twenty_distinct_pairs_pass_only_the_exposure_count_gate(self):
        sets = [(0, 0, 1000 + i * 700, 1001 + i * 700) for i in range(20)]
        probes = [(0, 0, i + 1, 1550 + i * 700, 1551 + i * 700, 0)
                  for i in range(20)]
        pair = analyze_wfi.analyze_text(*pairing_packet(sets, probes, stop=20000))["paired_opportunities"]
        self.assertEqual(pair["by_cluster"]["0"]["successful_sets"], 20)
        self.assertEqual(pair["by_cluster"]["0"]["primary_pairs"], 20)
        self.assertEqual(
            pair["by_cluster"]["0"]["primary_model_qualified_pairs_with_same_cpu_set_sample"]
            + pair["by_cluster"]["0"]["primary_model_qualified_pairs_with_cross_cpu_set_sample"],
            20,
        )
        self.assertTrue(pair["by_cluster"]["0"]["primary_exposure_gate_20"])
        self.assertFalse(pair["by_cluster"]["1"]["primary_exposure_gate_20"])
        self.assertFalse(pair["negative_claim_supported"])

    def test_unclean_or_non_mmio_packet_reports_no_exposure(self):
        unclean = analyze_wfi.analyze_text(*pairing_packet(
            [(0, 0, 1000, 1001)], [(0, 0, 1, 1550, 1551, 0)], pending=1
        ))["paired_opportunities"]
        self.assertEqual(unclean["status"], "suppressed_integrity_failure")
        self.assertIsNone(unclean["by_cluster"])
        clock = analyze_wfi.analyze_text(*pairing_packet(
            [(0, 0, 1000, 1001)], [(0, 0, 1, 1550, 1551, 0)], mode="wfi_clock"
        ))["paired_opportunities"]
        self.assertEqual(clock["status"], "not_applicable_without_wfi_mmio")
        self.assertIsNone(clock["by_cluster"])

    def test_contradictory_idle_stream_suppresses_paired_exposure(self):
        rows = fixtures.event_csv(
            fixtures.record("dvfs", 0, 0, 0, policy_cpu=0, policy_mask="0x0f",
                            fast_switch=1, t0=1000, t1=1001,
                            pre_cmd="0x0", cmd="0x2000000"),
            fixtures.record("idle_enter", 0, 0, 0, token=1, t0=1200, t1=1201),
            fixtures.record("idle_enter", 1, 0, 0, token=2, t0=1540, t1=1541),
        )
        packet_status = status(idle=(2, 2, 0, 0), wfi=(1, 1, 0, 0),
                               overrides={"dvfs0": (1, 1, 0, 0)},
                               start="0", stop="10000", end="11000")
        result = analyze_wfi.analyze_text(
            rows, packet_status, WFI_HEADER + "0,0,0,2,1550,1551,0x0,wfi_mmio\n"
        )
        self.assertFalse(result["integrity"]["clean"])
        self.assertEqual(result["paired_opportunities"]["status"], "suppressed_integrity_failure")


if __name__ == "__main__":
    unittest.main()
