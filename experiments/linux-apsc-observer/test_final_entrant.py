"""Artificial software-interval fixtures; no test is a hardware observation."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import random
import unittest


SPEC = importlib.util.spec_from_file_location("final_entrant", Path(__file__).with_name("final_entrant.py"))
final_entrant = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(final_entrant)


def event(kind, seq, cpu, *, cluster=0, token=1, t0=10, t1=None,
          raw=0, ret=0, valid=True):
    t1 = t0 if t1 is None else t1
    dvfs = kind == "dvfs"
    entry = kind == "idle_enter"
    return {
        "kind": kind, "seq": seq, "cpu": cpu, "cluster": cluster,
        "stream": f"dvfs{cluster}" if dvfs else f"idle{cpu}",
        "token": None if dvfs else token, "t0": t0, "t1": t1,
        "policy_cpu": (0 if cluster == 0 else 4) if dvfs else None,
        "policy_mask": (0x0f if cluster == 0 else 0xf0) if dvfs else None,
        "fast_switch": 1 if dvfs else None,
        "requested_index": seq if dvfs else None,
        "requested_pstate": seq if dvfs else None,
        "pre_cmd": 0 if dvfs else None,
        "cmd": ((1 << 25) | raw) if dvfs and ret == 0 else raw if entry and valid else None,
        "ret": ret,
        "flags": int(entry and valid),
    }


def status(clusters=None, start=0, stop=100):
    return {"clusters": clusters or {0: 0x0f, 1: 0xf0}, "start_tick": start,
            "stop_tick": stop, "end_tick": stop + 10, "mode": "mmio"}


def fixture(cpus=(0, 1, 2, 3), *, raw=0x80000000, valid=True):
    result = []
    for index, cpu in enumerate(cpus):
        result.append(event("idle_enter", 0, cpu, t0=10 * (index + 1),
                            t1=10 * (index + 1) + 1, raw=raw, valid=valid))
        result.append(event("idle_exit", 1, cpu, t0=60 if index == 3 else 80))
    return result


class FinalEntrantTests(unittest.TestCase):
    def screen(self, rows=None, *, error=0, reasons=None, capture=None):
        return final_entrant.screen(
            fixture() if rows is None else rows,
            status() if capture is None else capture,
            integrity_reasons=[] if reasons is None else reasons,
            pairwise_clock_error_ticks=error,
        )

    def candidate(self, rows=None, **options):
        result = self.screen(rows, **options)
        self.assertEqual(result["counts"]["candidates"], 1)
        return result["candidates"][0]

    def test_known_four_core_final_entrant_has_explicit_peer_proofs(self):
        candidate = self.candidate()
        self.assertEqual((candidate["cpu"], candidate["entry_seq"], candidate["token"]), (3, 0, 1))
        self.assertEqual((candidate["sample_t0"], candidate["sample_t1"]), (40, 41))
        self.assertEqual(candidate["raw_command"], "0x80000000")
        self.assertIs(candidate["busy_bit31"], True)
        self.assertEqual([row["cpu"] for row in candidate["peer_interval_witnesses"]], [0, 1, 2])
        for peer in candidate["peer_interval_witnesses"]:
            self.assertGreater(peer["entry_before_sample_margin_ticks"], 0)
            self.assertGreater(peer["exit_after_sample_margin_ticks"], 0)
            self.assertEqual(peer["exit_seq"], 1)

    def test_noncanonical_cluster_partition_is_taken_from_status(self):
        candidate = self.candidate(fixture((0, 2, 4, 6)), capture=status({0: 0x55, 1: 0xaa}))
        self.assertEqual(candidate["cpu"], 6)
        self.assertEqual(candidate["cluster_cpu_mask"], "0x55")
        self.assertEqual([row["cpu"] for row in candidate["peer_interval_witnesses"]], [0, 2, 4])

    def test_peer_interval_ended_or_never_observed_cannot_be_witness(self):
        for missing in (False, True):
            rows = fixture()
            if missing:
                rows = [row for row in rows if row["cpu"] != 0]
            else:
                rows[1]["t0"] = rows[1]["t1"] = 15
            with self.subTest(missing=missing):
                result = self.screen(rows)
                self.assertEqual(result["counts"]["candidates"], 0)
                self.assertFalse(result["claim_boundary"]["negative_conclusion_supported"])

    def test_strict_entry_margin_excludes_tie_and_exact_bound(self):
        self.assertEqual(self.screen(error=8)["counts"]["candidates"], 1)
        self.assertEqual(self.screen(error=9)["counts"]["candidates"], 0)
        rows = fixture()
        rows[4]["t1"] = 40
        self.assertEqual(self.screen(rows)["counts"]["candidates"], 0)

    def test_strict_exit_margin_excludes_tie_and_exact_bound(self):
        rows = fixture()
        rows[1]["t0"] = rows[1]["t1"] = 46
        self.assertEqual(self.screen(rows, error=4)["counts"]["candidates"], 1)
        self.assertEqual(self.screen(rows, error=5)["counts"]["candidates"], 0)
        rows[1]["t0"] = rows[1]["t1"] = 41
        self.assertEqual(self.screen(rows, error=0)["counts"]["candidates"], 0)

    def test_increasing_uncertainty_cannot_add_candidates(self):
        previous = {(3, 1)}
        for error in range(101):
            current = {(row["cpu"], row["token"]) for row in self.screen(error=error)["candidates"]}
            self.assertTrue(current <= previous)
            previous = current

    def test_repeated_interval_screen_matches_brute_force_peer_search(self):
        rng = random.Random(1127)
        capture = status({0: 0x55, 1: 0xaa}, stop=1000)
        witnessed = 0
        for trial in range(40):
            rows = []
            pairs = []
            for cpu in range(8):
                tick = rng.randrange(1, 40)
                for token in range(1, 5):
                    entry = event("idle_enter", (token - 1) * 2, cpu,
                                  cluster=cpu % 2, token=token,
                                  t0=tick, t1=tick + rng.randrange(1, 4))
                    exit_event = event("idle_exit", (token - 1) * 2 + 1, cpu,
                                       cluster=cpu % 2, token=token,
                                       t0=tick + rng.randrange(30, 140))
                    rows.extend((entry, exit_event))
                    pairs.append((entry, exit_event))
                    tick = exit_event["t1"] + rng.randrange(1, 60)
            error = rng.randrange(20)
            eligible = [(entry, exit_event) for entry, exit_event in pairs
                        if error < entry["t0"] and exit_event["t1"] + error < 1000]
            expected = set()
            for entry, _ in eligible:
                peers = [cpu for cpu in range(8)
                         if cpu != entry["cpu"] and cpu % 2 == entry["cluster"]]
                if all(any(peer_entry["cpu"] == cpu
                           and peer_entry["t1"] + error < entry["t0"]
                           and entry["t1"] + error < peer_exit["t0"]
                           for peer_entry, peer_exit in eligible) for cpu in peers):
                    expected.add((entry["cpu"], entry["token"]))
            actual = {(row["cpu"], row["token"]) for row in
                      self.screen(rows, capture=capture, error=error)["candidates"]}
            with self.subTest(trial=trial):
                self.assertEqual(actual, expected)
            witnessed += len(actual)
        self.assertGreater(witnessed, 0)

    def test_capture_edges_apply_clock_margin_to_candidate_and_peers(self):
        self.assertEqual(self.screen(error=5)["counts"]["candidates"], 1)
        cases = [("start_tick", 5, 5), ("stop_tick", 85, 5)]
        for key, value, error in cases:
            capture = status()
            capture[key] = value
            with self.subTest(edge=key):
                result = self.screen(error=error, capture=capture)
                self.assertEqual(result["counts"]["candidates"], 0)
                self.assertGreater(result["interval_exclusions"]["clock_margin_boundary_pairs"], 0)

    def test_no_bound_is_unavailable_and_never_implicitly_zero(self):
        result = self.screen(error=None)
        self.assertEqual(result["status"], "unavailable_without_clock_bound")
        self.assertEqual(result["counts"]["pairs_screened"], 0)
        self.assertIsNone(result["counts"]["interior_pairs_after_supplied_clock_margin"])
        self.assertFalse(result["claim_boundary"]["hardware_clock_qualified"])
        self.assertEqual(result["candidates"], [])

    def test_invalid_bounds_raise_and_uint64_max_does_not_wrap(self):
        for error in (True, False, -1, 1.5, "0", 1 << 64):
            with self.subTest(error=error), self.assertRaisesRegex(ValueError, "uint64"):
                self.screen(error=error)
        result = self.screen(error=(1 << 64) - 1)
        self.assertEqual(result["counts"]["candidates"], 0)
        self.assertEqual(result["interval_exclusions"]["clock_margin_boundary_pairs"], 4)

    def test_large_counter_ticks_retain_exact_margins_without_float_conversion(self):
        offset = (1 << 64) - 200
        rows = fixture()
        for row in rows:
            row["t0"] += offset
            row["t1"] += offset
        candidate = self.candidate(rows, error=5, capture=status(start=offset, stop=offset + 100))
        self.assertEqual(candidate["sample_t0"], offset + 40)
        self.assertEqual(candidate["peer_interval_witnesses"][-1]["entry_before_sample_margin_ticks"], 4)

    def test_trailing_unmatched_entries_elsewhere_do_not_erase_valid_candidate(self):
        rows = fixture() + [
            event("idle_enter", 2, 0, token=2, t0=90, t1=91),
            event("idle_enter", 0, 4, cluster=1, t0=20, t1=21),
        ]
        result = self.screen(rows)
        self.assertEqual(result["counts"]["candidates"], 1)
        self.assertEqual(result["interval_exclusions"]["trailing_unmatched_enter"], 2)
        self.assertTrue(result["idle_grammar"]["consistent"])

    def test_complete_boundary_pair_elsewhere_does_not_erase_candidate(self):
        rows = fixture() + [
            event("idle_enter", 0, 4, cluster=1, t0=0),
            event("idle_exit", 1, 4, cluster=1, t0=100),
        ]
        result = self.screen(rows)
        self.assertEqual(result["counts"]["candidates"], 1)
        self.assertEqual(result["interval_exclusions"]["recorded_capture_boundary_pairs"], 1)

    def test_own_incomplete_or_boundary_pair_is_never_a_candidate(self):
        incomplete = fixture()[:-1]
        self.assertEqual(self.screen(incomplete)["counts"]["candidates"], 0)
        boundary = fixture()
        boundary[-1]["t0"] = boundary[-1]["t1"] = 100
        self.assertEqual(self.screen(boundary)["counts"]["candidates"], 0)

    def test_loss_and_invalid_capture_suppress_all_candidates(self):
        for reason in ("idle0: overflow=1", "dvfs0: missing_commit=1", "status state is invalid, not complete"):
            with self.subTest(reason=reason):
                result = self.screen(reasons=[reason])
                self.assertEqual(result["status"], "suppressed_integrity_failure")
                self.assertEqual(result["integrity_reasons"], [reason])
                self.assertEqual(result["candidates"], [])

    def test_contradictory_lossless_grammar_suppresses_global_inference(self):
        contradictions = [
            [event("idle_enter", 0, 4, cluster=1, token=1, t0=10),
             event("idle_enter", 1, 4, cluster=1, token=2, t0=20),
             event("idle_exit", 2, 4, cluster=1, token=2, t0=80)],
            [event("idle_exit", 0, 4, cluster=1, t0=10)],
            [event("idle_enter", 0, 4, cluster=1, token=1, t0=10),
             event("cpu_pm_fail", 1, 4, cluster=1, token=2, t0=20, ret=-1)],
            [event("idle_enter", 0, 4, cluster=1, token=1, t0=10),
             event("idle_exit", 1, 4, cluster=1, token=2, t0=20)],
        ]
        for rows in contradictions:
            with self.subTest(kinds=[row["kind"] for row in rows]):
                result = self.screen(fixture() + rows)
                self.assertEqual(result["status"], "suppressed_contradictory_idle_stream")
                self.assertFalse(result["idle_grammar"]["consistent"])
                self.assertTrue(result["idle_grammar"]["reasons"])
                self.assertEqual(result["candidates"], [])

    def test_cpu_pm_failure_between_intervals_is_not_a_contradiction(self):
        rows = fixture() + [event("cpu_pm_fail", 2, 0, token=2, t0=90, ret=2)]
        result = self.screen(rows)
        self.assertEqual(result["counts"]["candidates"], 1)
        self.assertEqual(result["interval_exclusions"]["cpu_pm_fail"], 1)

    def test_records_only_and_failed_reads_are_unknown_never_clear(self):
        candidate = self.candidate(fixture(raw=None, valid=False))
        self.assertIsNone(candidate["raw_command"])
        self.assertIsNone(candidate["busy_bit31"])
        rows = fixture(raw=None, valid=False)
        for row in rows:
            if row["kind"] == "idle_enter":
                row["ret"] = -19
        self.assertIsNone(self.candidate(rows)["busy_bit31"])

    def test_clear_raw_zero_is_retained(self):
        candidate = self.candidate(fixture(raw=0))
        self.assertEqual(candidate["raw_command"], "0x0")
        self.assertIs(candidate["busy_bit31"], False)

    def test_dvfs_relations_include_remote_writers_and_same_cpu_zero_error(self):
        writes = [
            event("dvfs", 0, 4, t0=30, t1=32),  # remote before
            event("dvfs", 1, 3, t0=38, t1=39),  # same CPU before with E=0
            event("dvfs", 2, 4, t0=50, t1=51),  # remote after
            event("dvfs", 3, 3, t0=42, t1=43),  # same CPU after with E=0
            event("dvfs", 4, 4, t0=30, t1=35),  # exact before bound
            event("dvfs", 5, 4, t0=46, t1=47),  # exact after bound
            event("dvfs", 6, 4, t0=39, t1=42),  # overlapping
            event("dvfs", 7, 4, t0=20, ret=-5),  # no write
            event("dvfs", 0, 4, cluster=1, t0=20),  # different target
        ]
        relation = self.candidate(fixture() + writes, error=5)["target_cluster_dvfs"]
        self.assertEqual(relation["counts"], {
            "definitely_before": 2, "definitely_after": 2, "temporally_ambiguous": 3,
        })
        nearest = relation["nearest_by_recorded_t1_definitely_before"]
        self.assertEqual((nearest["cpu"], nearest["seq"], nearest["clock_error_applied_ticks"]), (3, 1, 0))
        self.assertEqual(nearest["strict_before_margin_ticks"], 1)
        self.assertEqual({row["seq"] for row in relation["temporally_ambiguous_ids"]}, {4, 5, 6})
        self.assertEqual(relation["causal_busy_source"], "not_established")

    def test_dvfs_order_uses_timestamps_not_reservation_sequence(self):
        writes = [event("dvfs", 0, 4, t0=50, t1=51),
                  event("dvfs", 1, 4, t0=30, t1=31),
                  event("dvfs", 2, 4, t0=20, t1=21)]
        relation = self.candidate(fixture() + writes)["target_cluster_dvfs"]
        self.assertEqual(relation["counts"]["definitely_before"], 2)
        self.assertEqual(relation["counts"]["definitely_after"], 1)
        self.assertEqual(relation["nearest_by_recorded_t1_definitely_before"]["seq"], 1)

    def test_no_definitely_before_write_has_no_invented_witness(self):
        writes = [event("dvfs", 0, 4, t0=40, t1=42)]
        relation = self.candidate(fixture() + writes)["target_cluster_dvfs"]
        self.assertIsNone(relation["nearest_by_recorded_t1_definitely_before"])
        self.assertEqual(relation["counts"]["temporally_ambiguous"], 1)

    def test_ambiguity_list_is_bounded_with_exact_total_and_truncation(self):
        writes = [event("dvfs", index, 4, t0=40, t1=41) for index in range(100)]
        relation = self.candidate(fixture() + writes)["target_cluster_dvfs"]
        self.assertEqual(relation["counts"]["temporally_ambiguous"], 100)
        self.assertEqual(len(relation["temporally_ambiguous_ids"]), 32)
        self.assertTrue(relation["ambiguous_ids_truncated"])
        self.assertEqual(relation["ambiguous_ids_omitted"], 68)
        self.assertEqual([row["seq"] for row in relation["temporally_ambiguous_ids"]], list(range(32)))

    def test_indexed_relations_match_independent_brute_force_oracle(self):
        rng = random.Random(731)
        for trial in range(60):
            writes = []
            for index in range(rng.randrange(120)):
                t0 = rng.randrange(1, 95)
                writes.append(event("dvfs", index, rng.choice((0, 3, 4, 7)),
                                    t0=t0, t1=rng.randrange(t0, 100)))
            error = rng.randrange(9)
            relation = self.candidate(fixture() + writes, error=error)["target_cluster_dvfs"]
            counts = {"definitely_before": 0, "definitely_after": 0, "temporally_ambiguous": 0}
            ambiguous = set()
            for write in writes:
                bound = 0 if write["cpu"] == 3 else error
                if write["t1"] + bound < 40:
                    counts["definitely_before"] += 1
                elif 41 + bound < write["t0"]:
                    counts["definitely_after"] += 1
                else:
                    counts["temporally_ambiguous"] += 1
                    ambiguous.add(write["seq"])
            with self.subTest(trial=trial):
                self.assertEqual(relation["counts"], counts)
                self.assertTrue({row["seq"] for row in relation["temporally_ambiguous_ids"]} <= ambiguous)
                self.assertEqual(len(relation["temporally_ambiguous_ids"]), min(32, len(ambiguous)))

    def test_order_determinism_no_input_mutation_and_json_serialization(self):
        rows = fixture() + [event("dvfs", 0, 4, t0=20, t1=21)]
        capture = status()
        original = copy.deepcopy((rows, capture))
        result = self.screen(rows, capture=capture)
        self.assertEqual(result, self.screen(list(reversed(rows)), capture=capture))
        self.assertEqual((rows, capture), original)
        self.assertEqual(json.loads(json.dumps(result)), result)

    def test_claims_remain_conditional_even_with_busy_and_prior_write(self):
        result = self.screen(fixture() + [event("dvfs", 0, 4, t0=20, t1=21)])
        self.assertEqual(result["status"], "conditional_software_screen")
        boundary = result["claim_boundary"]
        self.assertEqual(boundary["candidate_kind"], "conditional_software_final_entrant")
        self.assertFalse(boundary["hardware_clock_qualified"])
        self.assertFalse(boundary["negative_conclusion_supported"])
        for field in ("actual_last_active_core", "causal_busy_source"):
            self.assertEqual(boundary[field], "not_established")
        for field in ("actual_wfi_overlap", "physical_idle_state", "dvfs_device_completion"):
            self.assertEqual(boundary[field], "not_observed")
        self.assertIn("may not be the most recent actual write", result["nearest_write_limit"])


if __name__ == "__main__":
    unittest.main()
