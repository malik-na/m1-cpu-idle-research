"""Synthetic boundary tests for the observation-only T8103 APSC CSV decoder.

Every capture below is artificial ABI input, not a hardware observation.
"""

from __future__ import annotations

import csv
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


MODULE = Path(__file__).with_name("analyze.py")
SPEC = importlib.util.spec_from_file_location("apsc_analyze", MODULE)
analyze = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(analyze)

HEADER = "kind,seq,cpu,cluster,policy_cpu,policy_mask,fast_switch,requested_index,requested_pstate,token,t0,t1,pre_cmd,cmd,ret,flags"


def status(*, mode="mmio", overrides=None, abi="1", state="complete", start="0",
           stop="90", end="100", interrupted="0", policy_overrides=None):
    overrides = overrides or {}
    policy_overrides = policy_overrides or {}
    lines = [
        f"abi={abi}", f"state={state}", f"mode={mode}", "cntfrq=24000000",
        f"start_tick={start}", f"stop_tick={stop}", f"end_tick={end}",
        f"interrupted={interrupted}",
        "start_online_mask=0xff", "end_online_mask=0xff",
        "cluster0_cpus=0x0f", "cluster1_cpus=0xf0",
    ]
    defaults = {
        0: {"policy_mask": "0x0f", "policy_cpu": "0", "fast_switch": "1"},
        1: {"policy_mask": "0xf0", "policy_cpu": "4", "fast_switch": "1"},
    }
    for cluster in range(2):
        lines.append(f"cluster{cluster}_cmd_phys={('0x210e20020', '0x211e20020')[cluster]}")
        lines.append(f"cluster{cluster}_resource_size=0x1000")
        for edge in ("start", "end"):
            for field in ("policy_mask", "policy_cpu", "fast_switch"):
                key = f"cluster{cluster}_{field}_{edge}"
                lines.append(f"{key}={policy_overrides.get(key, defaults[cluster][field])}")
    for stream in [*(f"idle{cpu}" for cpu in range(8)), "dvfs0", "dvfs1"]:
        attempts, committed, overflow, missing = overrides.get(stream, (0, 0, 0, 0))
        for key, value in zip(
            ("attempts", "committed", "overflow", "missing_commit"),
            (attempts, committed, overflow, missing),
        ):
            lines.append(f"{stream}_{key}={value}")
    return "\n".join(lines) + "\n"


def record(kind, seq, cpu, cluster, *, policy_cpu="", policy_mask="", fast_switch="",
           requested_index=None, requested_pstate=None,
           token="", t0="10", t1="11", pre_cmd="", cmd="", ret="0", flags="0"):
    if requested_index is None:
        requested_index = 0 if kind == "dvfs" else ""
    if requested_pstate is None:
        requested_pstate = 0 if kind == "dvfs" else ""
    return [kind, str(seq), str(cpu), str(cluster), str(policy_cpu), str(policy_mask),
            str(fast_switch), str(requested_index), str(requested_pstate),
            str(token), str(t0), str(t1), str(pre_cmd), str(cmd),
            str(ret), str(flags)]


def event_csv(*rows, header=HEADER):
    out = io.StringIO()
    out.write(header + "\n")
    writer = csv.writer(out, lineterminator="\n")
    writer.writerows(rows)
    return out.getvalue()


def good_rows():
    # A zero pre-poll word is real data, not a missing cell.
    return (
        record("dvfs", 0, 4, 0, policy_cpu=0, policy_mask="0x0f", fast_switch=1,
               t0=10, t1=11, pre_cmd="0x0", cmd="0x2000000"),
        record("idle_enter", 0, 0, 0, token=1, t0=20, t1=21,
               cmd="0x80000000", flags=1),
        record("idle_exit", 1, 0, 0, token=1, t0=40, t1=40),
    )


def candidate_rows():
    # CPU 3 enters after its three peers; all four complete before stop.
    rows = [record("dvfs", 0, 4, 0, policy_cpu=0, policy_mask="0x0f", fast_switch=1,
                   t0=5, t1=6, pre_cmd="0x0", cmd="0x2000000")]
    for cpu in range(4):
        entry = 30 if cpu == 3 else 10 + cpu * 3
        rows.extend((
            record("idle_enter", 0, cpu, 0, token=1, t0=entry, t1=entry + 1,
                   cmd="0x80000000" if cpu == 3 else "0x0", flags=1),
            record("idle_exit", 1, cpu, 0, token=1, t0=60 + cpu, t1=60 + cpu),
        ))
    return rows


class DecoderTests(unittest.TestCase):
    def decode(self, rows, *, counters, mode="mmio", pairwise_clock_error_ticks=None, **status_options):
        return analyze.analyze_text(
            event_csv(*rows), status(mode=mode, overrides=counters, **status_options),
            evidence_origin="synthetic_fixture",
            pairwise_clock_error_ticks=pairwise_clock_error_ticks,
        )

    def test_candidate_screen_requires_explicit_bound_and_retains_peer_evidence(self):
        counters = {**{f"idle{cpu}": (2, 2, 0, 0) for cpu in range(4)}, "dvfs0": (1, 1, 0, 0)}
        default = self.decode(candidate_rows(), counters=counters)
        self.assertEqual(default["analysis_abi"], 2)
        self.assertEqual(default["conditional_final_entrants"]["status"], "unavailable_without_clock_bound")
        self.assertEqual(default["conditional_final_entrants"]["candidates"], [])
        result = self.decode(candidate_rows(), counters=counters, pairwise_clock_error_ticks=2)
        screen = result["conditional_final_entrants"]
        self.assertEqual(screen["status"], "conditional_software_screen")
        self.assertEqual(screen["counts"]["candidates"], 1)
        candidate = screen["candidates"][0]
        self.assertEqual(candidate["cpu"], 3)
        self.assertTrue(candidate["busy_bit31"])
        self.assertEqual([peer["cpu"] for peer in candidate["peer_interval_witnesses"]], [0, 1, 2])
        write = candidate["target_cluster_dvfs"]["nearest_by_recorded_t1_definitely_before"]
        self.assertEqual((write["cpu"], write["cluster"], write["clock_error_applied_ticks"]), (4, 0, 2))
        self.assertEqual(result["evidence_origin"], "synthetic_fixture")
        self.assertFalse(screen["claim_boundary"]["hardware_clock_qualified"])
        self.assertFalse(screen["claim_boundary"]["negative_conclusion_supported"])
        self.assertEqual(result["claim_boundary"]["physical_idle_state"], "not_observed")

    def test_candidate_inference_stops_on_loss_but_retains_raw_counts(self):
        counters = {**{f"idle{cpu}": (2, 2, 0, 0) for cpu in range(4)}, "dvfs0": (2, 1, 1, 0)}
        result = self.decode(candidate_rows(), counters=counters, pairwise_clock_error_ticks=0)
        self.assertEqual(result["conditional_final_entrants"]["status"], "suppressed_integrity_failure")
        self.assertEqual(result["conditional_final_entrants"]["candidates"], [])
        self.assertEqual(result["observed_records"]["idle_busy_bit31_valid_samples"], 1)

    def test_contradictory_incomplete_idle_grammar_suppresses_candidate_screen(self):
        rows = (
            record("idle_enter", 0, 0, 0, token=1, t0=10, t1=11, cmd="0x0", flags=1),
            record("idle_enter", 1, 0, 0, token=2, t0=20, t1=21, cmd="0x0", flags=1),
            record("idle_exit", 2, 0, 0, token=2, t0=40, t1=40),
        )
        result = self.decode(rows, counters={"idle0": (3, 3, 0, 0)}, pairwise_clock_error_ticks=0)
        self.assertTrue(result["integrity"]["clean"])
        self.assertEqual(result["conditional_final_entrants"]["status"], "suppressed_contradictory_idle_stream")
        self.assertEqual(result["observed_records"]["total"], 3)
        self.assertFalse(result["claim_boundary"]["complete_software_interval_screen_eligible"])

    def test_candidate_api_rejects_invalid_clock_bounds(self):
        for bound in (True, -1, 1 << 64, 0.0, "0"):
            with self.subTest(bound=bound), self.assertRaisesRegex(analyze.AnalysisError, "pairwise_clock_error_ticks"):
                analyze.analyze_text(event_csv(), status(), pairwise_clock_error_ticks=bound)

    def test_valid_synthetic_capture_preserves_zero_and_reports_only_sampled_busy(self):
        result = self.decode(good_rows(), counters={"dvfs0": (1, 1, 0, 0), "idle0": (2, 2, 0, 0)})
        self.assertTrue(result["integrity"]["clean"])
        self.assertEqual(result["evidence_origin"], "synthetic_fixture")
        self.assertEqual(result["observed_records"]["dvfs_successful_attempted_writes"], 1)
        self.assertEqual(result["observed_records"]["dvfs_pre_poll_errors_no_write"], 0)
        self.assertEqual(result["observed_records"]["idle_valid_mmio_samples"], 1)
        self.assertEqual(result["observed_records"]["idle_busy_bit31_valid_samples"], 1)
        self.assertEqual(result["idle_intervals"]["complete_pairs"], 1)
        self.assertTrue(result["claim_boundary"]["complete_software_interval_screen_eligible"])
        self.assertEqual(result["claim_boundary"]["actual_wfi_overlap"], "not_observed")
        self.assertEqual(result["claim_boundary"]["dvfs_device_completion"], "not_observed")

    def test_record_only_mode_has_no_fake_mmio_sample(self):
        rows = (
            record("idle_enter", 0, 0, 0, token=1, t0=20, t1=20),
            record("idle_exit", 1, 0, 0, token=1, t0=30, t1=30),
        )
        result = self.decode(rows, counters={"idle0": (2, 2, 0, 0)}, mode="records")
        self.assertTrue(result["integrity"]["clean"])
        self.assertEqual(result["observed_records"]["idle_valid_mmio_samples"], 0)
        self.assertEqual(result["observed_records"]["idle_busy_bit31_valid_samples"], 0)

    def test_overflow_and_missing_commit_prevent_clean_capture(self):
        rows = good_rows()
        overflow = self.decode(rows, counters={"dvfs0": (1, 1, 0, 0), "idle0": (3, 2, 1, 0)})
        self.assertFalse(overflow["integrity"]["clean"])
        self.assertIn("idle0: overflow=1", overflow["integrity"]["reasons"])
        gap_rows = (rows[0], rows[1], record("idle_exit", 2, 0, 0, token=1, t0=40, t1=40))
        missing = self.decode(gap_rows, counters={"dvfs0": (1, 1, 0, 0), "idle0": (3, 2, 0, 1)})
        self.assertFalse(missing["integrity"]["clean"])
        self.assertEqual(missing["integrity"]["streams"]["idle0"]["sequence_gaps"], 1)
        self.assertIn("idle0: missing_commit=1", missing["integrity"]["reasons"])

    def test_unreported_gap_is_integrity_failure(self):
        rows = (record("idle_enter", 0, 0, 0, token=1, t0=20, t1=20, cmd="0x0", flags=1),
                record("idle_exit", 2, 0, 0, token=1, t0=30, t1=30))
        result = self.decode(rows, counters={"idle0": (3, 2, 1, 0)})
        self.assertFalse(result["integrity"]["clean"])
        self.assertTrue(any("sequence outside retained" in reason for reason in result["integrity"]["reasons"]))

    def test_incomplete_and_capture_edge_pairs_are_excluded(self):
        rows = (
            record("idle_enter", 0, 0, 0, token=1, t0=0, t1=1, cmd="0x0", flags=1),
            record("idle_exit", 1, 0, 0, token=1, t0=20, t1=20),
            record("idle_enter", 2, 0, 0, token=2, t0=30, t1=31, cmd="0x0", flags=1),
            record("idle_exit", 3, 0, 0, token=3, t0=50, t1=50),
        )
        result = self.decode(rows, counters={"idle0": (4, 4, 0, 0)})
        self.assertEqual(result["idle_intervals"]["complete_pairs"], 0)
        self.assertEqual(result["idle_intervals"]["boundary_pair_excluded"], 1)
        self.assertEqual(result["idle_intervals"]["missing_exit"], 1)
        self.assertEqual(result["idle_intervals"]["missing_enter"], 1)
        self.assertTrue(result["integrity"]["clean"])
        self.assertFalse(result["claim_boundary"]["complete_software_interval_screen_eligible"])

    def test_each_incomplete_idle_case_blocks_full_interval_screen_independently(self):
        cases = (
            ("missing_exit", (
                record("idle_enter", 0, 0, 0, token=1, t0=20, t1=21, cmd="0x0", flags=1),
            )),
            ("missing_enter", (
                record("idle_exit", 0, 0, 0, token=1, t0=20, t1=20),
            )),
            ("boundary_pair_excluded", (
                record("idle_enter", 0, 0, 0, token=1, t0=20, t1=21, cmd="0x0", flags=1),
                record("idle_exit", 1, 0, 0, token=1, t0=90, t1=90),
            )),
        )
        for excluded, rows in cases:
            with self.subTest(excluded=excluded):
                result = self.decode(rows, counters={"idle0": (len(rows), len(rows), 0, 0)})
                self.assertTrue(result["integrity"]["clean"])
                self.assertEqual(result["idle_intervals"][excluded], 1)
                self.assertFalse(result["claim_boundary"]["complete_software_interval_screen_eligible"])

    def test_failed_idle_read_and_dvfs_poll_are_not_successes(self):
        rows = (
            record("dvfs", 0, 0, 0, policy_cpu=0, policy_mask="0x0f", fast_switch=1,
                   t0=10, t1=10, pre_cmd="0x80000000", cmd="", ret=-5),
            record("idle_enter", 0, 0, 0, token=1, t0=20, t1=21, cmd="", ret=-19, flags=0),
            record("idle_exit", 1, 0, 0, token=1, t0=40, t1=40),
        )
        result = self.decode(rows, counters={"dvfs0": (1, 1, 0, 0), "idle0": (2, 2, 0, 0)})
        observed = result["observed_records"]
        self.assertEqual(observed["dvfs_successful_attempted_writes"], 0)
        self.assertEqual(observed["dvfs_pre_poll_errors_no_write"], 1)
        self.assertEqual(observed["idle_valid_mmio_samples"], 0)
        self.assertEqual(observed["idle_busy_bit31_valid_samples"], 0)
        self.assertEqual(observed["idle_mmio_read_errors"], 1)

    def test_positive_cpu_pm_notifier_failure_is_retained(self):
        rows = (record("cpu_pm_fail", 0, 0, 0, token=1, t0=20, t1=20, ret=2),)
        result = self.decode(rows, counters={"idle0": (1, 1, 0, 0)})
        self.assertEqual(result["idle_intervals"]["cpu_pm_fail"], 1)
        self.assertEqual(result["idle_intervals"]["complete_pairs"], 0)

    def test_post_stop_drain_event_is_retained_but_not_a_complete_capture_interval(self):
        rows = (
            record("idle_enter", 0, 0, 0, token=1, t0=70, t1=71, cmd="0x0", flags=1),
            record("idle_exit", 1, 0, 0, token=1, t0=95, t1=95),
        )
        result = self.decode(rows, counters={"idle0": (2, 2, 0, 0)})
        self.assertTrue(result["integrity"]["clean"])
        self.assertEqual(result["capture"]["stop_tick"], 90)
        self.assertEqual(result["capture"]["end_tick"], 100)
        self.assertEqual(result["idle_intervals"]["complete_pairs"], 0)
        self.assertEqual(result["idle_intervals"]["boundary_pair_excluded"], 1)
        self.assertFalse(result["claim_boundary"]["complete_software_interval_screen_eligible"])

    def test_stop_boundary_partitions_records_without_dropping_drain_events(self):
        rows = (
            record("dvfs", 0, 4, 0, policy_cpu=0, policy_mask="0x0f", fast_switch=1,
                   t0=89, t1=90, pre_cmd="0x0", cmd="0x2000001"),
            record("dvfs", 1, 4, 0, policy_cpu=0, policy_mask="0x0f", fast_switch=1,
                   t0=90, t1=91, pre_cmd="0x0", cmd="0x2000002"),
            record("dvfs", 2, 4, 0, policy_cpu=0, policy_mask="0x0f", fast_switch=1,
                   t0=91, t1=100, pre_cmd="0x0", cmd="0x2000003"),
            record("idle_enter", 0, 0, 0, token=1, t0=90, t1=90, cmd="0x0", flags=1),
            record("idle_enter", 0, 1, 0, token=1, t0=90, t1=91, cmd="0x80000000", flags=1),
            record("idle_enter", 0, 2, 0, token=1, t0=91, t1=100, cmd="0x80000000", flags=1),
        )
        result = self.decode(rows, counters={
            "dvfs0": (3, 3, 0, 0), "idle0": (1, 1, 0, 0),
            "idle1": (1, 1, 0, 0), "idle2": (1, 1, 0, 0),
        })
        self.assertTrue(result["integrity"]["clean"])
        self.assertEqual(result["observed_records"]["total"], 6)
        self.assertEqual(result["observed_records"]["idle_busy_bit31_valid_samples"], 2)
        windows = result["capture_window_records"]
        for name, busy_count in (("in_window", 0), ("straddling_stop", 1), ("post_stop_drain", 1)):
            with self.subTest(window=name):
                self.assertEqual(windows[name]["total"], 2)
                self.assertEqual(windows[name]["by_kind"]["dvfs"], 1)
                self.assertEqual(windows[name]["by_kind"]["idle_enter"], 1)
                self.assertEqual(windows[name]["dvfs_successful_attempted_writes"], 1)
                self.assertEqual(windows[name]["idle_valid_mmio_samples"], 1)
                self.assertEqual(windows[name]["idle_busy_bit31_valid_samples"], busy_count)
        self.assertEqual(sum(windows[name]["total"] for name in (
            "in_window", "straddling_stop", "post_stop_drain"
        )), result["observed_records"]["total"])

    def test_event_outside_recorded_through_drain_bounds_is_rejected(self):
        for t0, t1 in ((9, 10), (100, 101)):
            with self.subTest(t0=t0, t1=t1):
                row = record("idle_enter", 0, 0, 0, token=1, t0=t0, t1=t1, cmd="0x0", flags=1)
                with self.assertRaisesRegex(analyze.AnalysisError, "event outside capture ticks"):
                    self.decode((row,), counters={"idle0": (1, 1, 0, 0)}, start="10")

    def test_policy_metadata_change_or_interruption_prevents_clean_capture(self):
        changed = self.decode(
            (), counters={}, policy_overrides={"cluster0_fast_switch_end": "0"}
        )
        self.assertFalse(changed["integrity"]["clean"])
        self.assertIn("cluster0: policy metadata changed during capture", changed["integrity"]["reasons"])
        interrupted = self.decode((), counters={}, interrupted="1")
        self.assertFalse(interrupted["integrity"]["clean"])
        self.assertIn("capture was interrupted", interrupted["integrity"]["reasons"])

    def test_dvfs_reservation_sequence_need_not_order_timestamps(self):
        rows = (
            record("dvfs", 0, 0, 0, policy_cpu=0, policy_mask="0x0f", fast_switch=1,
                   t0=30, t1=31, pre_cmd="0x0", cmd="0x2000001"),
            record("dvfs", 1, 4, 0, policy_cpu=0, policy_mask="0x0f", fast_switch=1,
                   t0=20, t1=21, pre_cmd="0x0", cmd="0x2000002"),
        )
        result = self.decode(rows, counters={"dvfs0": (2, 2, 0, 0)})
        self.assertTrue(result["integrity"]["clean"])
        self.assertEqual(result["observed_records"]["dvfs_seq_timestamp_inversions_tolerated"], 1)
        self.assertEqual(result["observed_records"]["dvfs_successful_attempted_writes"], 2)

    def test_disjoint_idle_intervals_cannot_reverse_time_in_reservation_order(self):
        rows = (
            record("idle_enter", 0, 0, 0, token=1, t0=50, t1=51, cmd="0x0", flags=1),
            record("idle_exit", 1, 0, 0, token=1, t0=60, t1=60),
            record("idle_enter", 2, 0, 0, token=2, t0=20, t1=21, cmd="0x0", flags=1),
            record("idle_exit", 3, 0, 0, token=2, t0=30, t1=30),
        )
        with self.assertRaisesRegex(analyze.AnalysisError, "idle0: idle stream timestamp order reversed between seq 1 .* and seq 2"):
            self.decode(rows, counters={"idle0": (4, 4, 0, 0)})

    def test_idle_order_check_includes_unpaired_entries_exits_and_pm_failures(self):
        preceding = record("cpu_pm_fail", 0, 0, 0, token=1, t0=50, t1=50, ret=2)
        following = (
            record("idle_enter", 1, 0, 0, token=2, t0=20, t1=21, cmd="0x0", flags=1),
            record("idle_exit", 1, 0, 0, token=2, t0=20, t1=20),
            record("cpu_pm_fail", 1, 0, 0, token=2, t0=20, t1=20, ret=2),
        )
        for later in following:
            with self.subTest(kind=later[0]), self.assertRaisesRegex(analyze.AnalysisError, "idle stream timestamp order reversed"):
                self.decode((preceding, later), counters={"idle0": (2, 2, 0, 0)})

    def test_sequential_idle_probe_brackets_cannot_overlap(self):
        rows = (
            record("idle_enter", 0, 0, 0, token=1, t0=20, t1=30, cmd="0x0", flags=1),
            record("cpu_pm_fail", 1, 0, 0, token=2, t0=25, t1=25, ret=2),
        )
        with self.assertRaisesRegex(analyze.AnalysisError, "idle stream timestamp order reversed"):
            self.decode(rows, counters={"idle0": (2, 2, 0, 0)})

    def test_idle_order_uses_sequence_and_accepts_shuffled_csv_rows(self):
        rows = (
            record("idle_exit", 1, 0, 0, token=1, t0=30, t1=30),
            record("idle_enter", 0, 0, 0, token=1, t0=20, t1=21, cmd="0x0", flags=1),
        )
        result = self.decode(rows, counters={"idle0": (2, 2, 0, 0)})
        self.assertTrue(result["integrity"]["clean"])
        self.assertEqual(result["idle_intervals"]["complete_pairs"], 1)

    def test_dvfs_request_fields_are_required_uint32_even_on_failed_polls(self):
        for field in ("requested_index", "requested_pstate"):
            for value, expected in (("", "must be present and fit uint32"), (1 << 32, "must be present and fit uint32"), (-1, "unsigned decimal"), ("0x1", "unsigned decimal")):
                for failed in (False, True):
                    with self.subTest(field=field, value=value, failed=failed):
                        row = record(
                            "dvfs", 0, 0, 0, policy_cpu=0, policy_mask="0x0f", fast_switch=1,
                            t0=10, t1=10 if failed else 11,
                            pre_cmd="0x80000000" if failed else "0x0",
                            cmd="" if failed else "0x2000000", ret=-5 if failed else 0,
                            **{field: value},
                        )
                        with self.assertRaisesRegex(analyze.AnalysisError, expected):
                            self.decode((row,), counters={"dvfs0": (1, 1, 0, 0)})

    def test_dvfs_request_metadata_preserves_zero_and_full_uint32(self):
        rows = (
            record("dvfs", 0, 0, 0, policy_cpu=0, policy_mask="0x0f", fast_switch=1,
                   requested_index=0, requested_pstate=(1 << 32) - 1,
                   t0=10, t1=10, pre_cmd="0x80000000", ret=-5),
            record("dvfs", 1, 0, 0, policy_cpu=0, policy_mask="0x0f", fast_switch=1,
                   requested_index=(1 << 32) - 1, requested_pstate=0,
                   t0=20, t1=21, pre_cmd="0x0", cmd="0x2000000"),
        )
        metadata = analyze.parse_status(status(overrides={"dvfs0": (2, 2, 0, 0)}))
        events, _ = analyze.parse_events(event_csv(*rows), metadata)
        self.assertEqual(events[0]["requested_index"], 0)
        self.assertEqual(events[0]["requested_pstate"], (1 << 32) - 1)
        self.assertEqual(events[1]["requested_index"], (1 << 32) - 1)
        self.assertEqual(events[1]["requested_pstate"], 0)

    def test_idle_and_pm_failure_rows_cannot_contain_dvfs_request_metadata(self):
        for field in ("requested_index", "requested_pstate"):
            for kind in ("idle_enter", "idle_exit", "cpu_pm_fail"):
                with self.subTest(field=field, kind=kind):
                    row = record(kind, 0, 0, 0, token=1, t0=10, t1=10,
                                 cmd="0x0" if kind == "idle_enter" else "",
                                 flags=1 if kind == "idle_enter" else 0,
                                 ret=2 if kind == "cpu_pm_fail" else 0,
                                 **{field: 0})
                    with self.assertRaisesRegex(analyze.AnalysisError, "idle policy/request fields must be blank"):
                        self.decode((row,), counters={"idle0": (1, 1, 0, 0)})

    def test_accessor_spans_report_median_nearest_rank_p95_and_nanoseconds(self):
        rows = tuple(
            record("dvfs", index, 0, 0, policy_cpu=0, policy_mask="0x0f", fast_switch=1,
                   t0=10 + index * 1000, t1=10 + index * 1000 + 24 * (index + 1),
                   pre_cmd="0x0", cmd="0x2000000")
            for index in range(20)
        )
        result = self.decode(rows, counters={"dvfs0": (20, 20, 0, 0)}, stop="29900", end="30000")
        spans = result["accessor_spans"]
        self.assertEqual(spans["capture_mode"], "mmio")
        self.assertIn("exclude record construction/publication overhead", spans["definition"])
        summary = spans["by_kind"]["dvfs"]["submitted_write"]
        self.assertEqual(summary["count"], 20)
        self.assertEqual(summary["ticks"], {"min": 24, "median": 252, "p95": 456, "max": 480})
        self.assertEqual(summary["nanoseconds"], {"min": 1000, "median": 10500, "p95": 19000, "max": 20000})
        absent = spans["by_kind"]["dvfs"]["failed_poll_marker"]
        self.assertEqual(absent["count"], 0)
        self.assertTrue(all(value is None for value in absent["ticks"].values()))
        self.assertTrue(all(value is None for value in absent["nanoseconds"].values()))

    def test_accessor_spans_separate_read_modes_errors_and_timestamp_markers(self):
        rows = (
            record("dvfs", 0, 0, 0, policy_cpu=0, policy_mask="0x0f", fast_switch=1,
                   t0=10, t1=10, pre_cmd="0x80000000", ret=-5),
            record("idle_enter", 0, 0, 0, token=1, t0=20, t1=23, cmd="0x0", flags=1),
            record("idle_exit", 1, 0, 0, token=1, t0=30, t1=30),
            record("idle_enter", 2, 0, 0, token=2, t0=40, t1=41, ret=-19),
            record("idle_exit", 3, 0, 0, token=2, t0=50, t1=50),
            record("cpu_pm_fail", 4, 0, 0, token=3, t0=60, t1=60, ret=2),
        )
        result = self.decode(rows, counters={"dvfs0": (1, 1, 0, 0), "idle0": (5, 5, 0, 0)})
        groups = result["accessor_spans"]["by_kind"]
        self.assertEqual(groups["dvfs"]["failed_poll_marker"]["ticks"]["max"], 0)
        self.assertEqual(groups["idle_enter"]["mmio_valid"]["ticks"]["max"], 3)
        self.assertEqual(groups["idle_enter"]["mmio_error"]["ticks"]["max"], 1)
        self.assertEqual(groups["idle_enter"]["records_no_read"]["count"], 0)
        self.assertEqual(groups["idle_exit"]["timestamp_only"]["count"], 2)
        self.assertEqual(groups["cpu_pm_fail"]["timestamp_only"]["ticks"]["max"], 0)
        record_only = self.decode(
            (record("idle_enter", 0, 0, 0, token=1, t0=20, t1=22),),
            counters={"idle0": (1, 1, 0, 0)}, mode="records",
        )["accessor_spans"]
        self.assertEqual(record_only["capture_mode"], "records")
        self.assertEqual(record_only["by_kind"]["idle_enter"]["records_no_read"]["ticks"]["min"], 2)
        self.assertEqual(record_only["by_kind"]["idle_enter"]["mmio_valid"]["count"], 0)

    def test_failed_dvfs_poll_marker_does_not_imply_measured_poll_duration(self):
        row = record("dvfs", 0, 0, 0, policy_cpu=0, policy_mask="0x0f", fast_switch=1,
                     t0=10, t1=11, pre_cmd="0x80000000", ret=-5)
        with self.assertRaisesRegex(analyze.AnalysisError, "failed dvfs poll must be a timestamp marker"):
            self.decode((row,), counters={"dvfs0": (1, 1, 0, 0)})

    def test_successful_dvfs_write_requires_clear_busy_and_set_command(self):
        cases = (
            ("0x0", "0x0"),
            ("0x80000000", "0x2000000"),
            ("0x0", "0x82000000"),
        )
        for pre_cmd, cmd in cases:
            with self.subTest(pre_cmd=pre_cmd, cmd=cmd):
                row = record(
                    "dvfs", 0, 0, 0, policy_cpu=0, policy_mask="0x0f", fast_switch=1,
                    pre_cmd=pre_cmd, cmd=cmd,
                )
                with self.assertRaisesRegex(analyze.AnalysisError, "poll/SET invariants"):
                    self.decode((row,), counters={"dvfs0": (1, 1, 0, 0)})

    def test_failed_dvfs_poll_cannot_contain_a_submitted_command(self):
        row = record(
            "dvfs", 0, 0, 0, policy_cpu=0, policy_mask="0x0f", fast_switch=1,
            pre_cmd="0x80000000", cmd="0x2000000", ret=-5,
        )
        with self.assertRaisesRegex(analyze.AnalysisError, "dvfs write/error fields disagree"):
            self.decode((row,), counters={"dvfs0": (1, 1, 0, 0)})

    def test_overlapping_same_cpu_idle_attempts_are_rejected(self):
        rows = (
            record("idle_enter", 0, 0, 0, token=1, t0=20, t1=21, cmd="0x0", flags=1),
            record("idle_enter", 1, 0, 0, token=2, t0=30, t1=31, cmd="0x0", flags=1),
            record("idle_exit", 2, 0, 0, token=1, t0=50, t1=50),
            record("idle_exit", 3, 0, 0, token=2, t0=60, t1=60),
        )
        with self.assertRaisesRegex(analyze.AnalysisError, "overlapping idle intervals"):
            self.decode(rows, counters={"idle0": (4, 4, 0, 0)})

    def test_adjacent_same_cpu_and_overlapping_other_cpu_intervals_are_valid(self):
        rows = (
            record("idle_enter", 0, 0, 0, token=1, t0=20, t1=21, cmd="0x0", flags=1),
            record("idle_exit", 1, 0, 0, token=1, t0=40, t1=40),
            record("idle_enter", 2, 0, 0, token=2, t0=40, t1=41, cmd="0x0", flags=1),
            record("idle_exit", 3, 0, 0, token=2, t0=60, t1=60),
            record("idle_enter", 0, 1, 0, token=1, t0=30, t1=31, cmd="0x0", flags=1),
            record("idle_exit", 1, 1, 0, token=1, t0=50, t1=50),
        )
        result = self.decode(rows, counters={"idle0": (4, 4, 0, 0), "idle1": (2, 2, 0, 0)})
        self.assertTrue(result["integrity"]["clean"])
        self.assertEqual(result["idle_intervals"]["complete_pairs"], 3)
        self.assertTrue(result["claim_boundary"]["complete_software_interval_screen_eligible"])
        self.assertEqual(result["claim_boundary"]["candidate_software_final_entrant"], "unavailable_without_clock_bound")

    def test_partial_online_mask_cannot_be_a_clean_v1_capture(self):
        actual = status().replace("start_online_mask=0xff", "start_online_mask=0x01")
        actual = actual.replace("end_online_mask=0xff", "end_online_mask=0x01")
        result = analyze.analyze_text(event_csv(), actual, evidence_origin="synthetic_fixture")
        self.assertFalse(result["integrity"]["clean"])
        self.assertIn("T8103 capture requires all eight CPUs online", result["integrity"]["reasons"])

    def test_zero_idle_token_is_not_emitted_by_v1_observer(self):
        row = record("idle_enter", 0, 0, 0, token=0, cmd="0x0", flags=1)
        with self.assertRaisesRegex(analyze.AnalysisError, "missing token"):
            self.decode((row,), counters={"idle0": (1, 1, 0, 0)})

    def test_malformed_header_unknown_abi_kind_and_flags_are_rejected(self):
        with self.assertRaisesRegex(analyze.AnalysisError, "CSV header"):
            analyze.analyze_text(event_csv(header="kind,seq"), status())
        with self.assertRaisesRegex(analyze.AnalysisError, "unsupported status ABI"):
            analyze.analyze_text(event_csv(), status(abi="2"))
        with self.assertRaisesRegex(analyze.AnalysisError, "unknown kind"):
            self.decode((record("physical_off", 0, 0, 0, token=1),), counters={"idle0": (1, 1, 0, 0)})
        with self.assertRaisesRegex(analyze.AnalysisError, "unknown flag bits"):
            self.decode((record("idle_enter", 0, 0, 0, token=1, flags=2),), counters={"idle0": (1, 1, 0, 0)})

    def test_duplicate_sequence_and_token_are_rejected(self):
        rows = (record("idle_enter", 0, 0, 0, token=1, cmd="0x0", flags=1),
                record("idle_exit", 0, 0, 0, token=1, t0=30, t1=30))
        with self.assertRaisesRegex(analyze.AnalysisError, "duplicate sequence"):
            self.decode(rows, counters={"idle0": (2, 2, 0, 0)})
        rows = (record("idle_enter", 0, 0, 0, token=1, cmd="0x0", flags=1),
                record("idle_enter", 1, 0, 0, token=1, t0=20, t1=21, cmd="0x0", flags=1))
        with self.assertRaisesRegex(analyze.AnalysisError, "duplicate idle_enter"):
            self.decode(rows, counters={"idle0": (2, 2, 0, 0)})

    def test_negative_or_overflowed_time_and_timestamp_reversal_are_rejected(self):
        cases = (
            (record("idle_enter", 0, 0, 0, token=1, t0=-1, t1=10, cmd="0x0", flags=1), "unsigned decimal"),
            (record("idle_enter", 0, 0, 0, token=1, t0=1 << 64, t1=10, cmd="0x0", flags=1), "exceeds uint64"),
            (record("idle_enter", 0, 0, 0, token=1, t0=21, t1=20, cmd="0x0", flags=1), "timestamp reversal"),
        )
        for row, expected in cases:
            with self.subTest(expected=expected), self.assertRaisesRegex(analyze.AnalysisError, expected):
                self.decode((row,), counters={"idle0": (1, 1, 0, 0)})

    def test_cli_json_labels_synthetic_fixture_and_does_not_invent_hardware_data(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            events_path = folder / "events.csv"
            status_path = folder / "status"
            events_path.write_text(event_csv(*good_rows()))
            status_path.write_text(status(overrides={"dvfs0": (1, 1, 0, 0), "idle0": (2, 2, 0, 0)}))
            result = subprocess.run(
                [sys.executable, str(MODULE), "--synthetic-fixture", str(events_path), str(status_path)],
                capture_output=True, text=True, check=False,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["evidence_origin"], "synthetic_fixture")
        self.assertEqual(output["claim_boundary"]["physical_idle_state"], "not_observed")

    def test_cli_clock_option_is_strict_and_keeps_input_unverified(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            events_path, status_path = folder / "events.csv", folder / "status"
            events_path.write_text(event_csv(*candidate_rows()))
            status_path.write_text(status(overrides={
                **{f"idle{cpu}": (2, 2, 0, 0) for cpu in range(4)}, "dvfs0": (1, 1, 0, 0),
            }))
            for bound in ("2", "-1", str(1 << 64), "true", "2.0", "02"):
                result = subprocess.run(
                    [sys.executable, str(MODULE), str(events_path), str(status_path),
                     f"--pairwise-clock-error-ticks={bound}"], capture_output=True, text=True, check=False,
                )
                with self.subTest(bound=bound):
                    if bound == "2":
                        self.assertEqual(result.returncode, 0, result.stderr)
                        output = json.loads(result.stdout)
                        self.assertEqual(output["evidence_origin"], "unverified_input")
                        self.assertEqual(output["conditional_final_entrants"]["counts"]["candidates"], 1)
                        self.assertFalse(output["conditional_final_entrants"]["claim_boundary"]["hardware_clock_qualified"])
                    else:
                        self.assertEqual(result.returncode, 2, result.stderr)
                        self.assertIn("pairwise-clock-error-ticks", json.loads(result.stderr)["analysis_error"])
                        self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
