#!/usr/bin/env python3
"""Adversarial synthetic checks for the private ABI 3 ticket screen."""

import csv
import io
import unittest

from validate_tickets import EVENT_HEADER, WFI_HEADER, TicketError, analyze


def event(kind, cpu, seq, token, ticket):
    fields = {key: "" for key in EVENT_HEADER.split(",")}
    fields.update(kind=kind, seq=str(seq), cpu=str(cpu), cluster="0",
                  token=str(token), t0=str(100 + ticket),
                  t1=str(100 + ticket), ret="0", flags="0",
                  ticket=str(ticket))
    return fields


def dvfs_event(cluster=0, writer=4):
    fields = {key: "" for key in EVENT_HEADER.split(",")}
    fields.update(kind="dvfs", seq="0", cpu=str(writer), cluster=str(cluster),
                  policy_cpu="0" if cluster == 0 else "4",
                  policy_mask="0x0f" if cluster == 0 else "0xf0",
                  fast_switch="1", requested_index="3", requested_pstate="2",
                  t0="104", t1="105", pre_cmd="0x0", cmd="0x2",
                  ret="0", flags="0")
    return fields


def fixture():
    status = {"abi": "3", "state": "complete", "mode": "wfi_mmio",
              "interrupted": "0", "start_online_mask": "0xff",
              "end_online_mask": "0xff", "wfi_pending_after_drain": "0",
              "wfi_prepare_bad_mapping": "0", "wfi_prepare_after_stop": "0",
              "cntfrq": "24000000", "start_tick": "1000",
              "stop_tick": "2000", "end_tick": "2001",
              "inside_start_ns": "300000", "inside_stop_ns": "400000",
              "cluster0_cpus": "0x0f", "cluster1_cpus": "0xf0",
              "cluster0_ticket_start": "1", "cluster0_ticket_stop": "18",
              "cluster1_ticket_start": "1", "cluster1_ticket_stop": "2"}
    for cluster, mask, policy_cpu in ((0, "0x0f", 0), (1, "0xf0", 4)):
        status[f"cluster{cluster}_policy_mask_start"] = mask
        status[f"cluster{cluster}_policy_mask_end"] = mask
        status[f"cluster{cluster}_policy_cpu_start"] = str(policy_cpu)
        status[f"cluster{cluster}_policy_cpu_end"] = str(policy_cpu)
        status[f"cluster{cluster}_fast_switch_start"] = "1"
        status[f"cluster{cluster}_fast_switch_end"] = "1"
    for kind, count in (("idle", 8), ("wfi", 8), ("dvfs", 2)):
        for index in range(count):
            prefix = f"{kind}{index}"
            attempts = 2 if kind == "idle" and index < 4 else 0
            if kind == "wfi" and index < 4:
                attempts = 1
            status[f"{prefix}_attempts"] = str(attempts)
            status[f"{prefix}_committed"] = str(attempts)
            status[f"{prefix}_overflow"] = "0"
            status[f"{prefix}_missing_commit"] = "0"
    events = [event("idle_enter", cpu, 0, 1, ticket)
              for cpu, ticket in ((1, 2), (2, 5), (3, 8), (0, 11))]
    events += [event("idle_exit", cpu, 1, 1, ticket)
               for cpu, ticket in ((0, 14), (1, 15), (2, 16), (3, 17))]
    wfi = [{"seq": "0", "cpu": "0", "cluster": "0", "token": "1",
            "t0": "112", "t1": "113", "cmd": "0x80000001",
            "mode": "wfi_mmio", "cmd_valid": "1",
            "ticket_pre": "12", "ticket_post": "13"}]
    for cpu, pre, post in ((1, 3, 4), (2, 6, 7), (3, 9, 10)):
        wfi.append({"seq": "0", "cpu": str(cpu), "cluster": "0", "token": "1",
                    "t0": str(100 + pre), "t1": str(100 + post),
                    "cmd": "0x1", "mode": "wfi_mmio", "cmd_valid": "1",
                    "ticket_pre": str(pre), "ticket_post": str(post)})
    return status, events, wfi


def csv_text(header, items):
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=header.split(","), lineterminator="\n")
    writer.writeheader()
    writer.writerows(items)
    return output.getvalue()


def run_packet(packet):
    status, events, wfi = packet
    raw_status = "".join(f"{key}={value}\n" for key, value in status.items())
    return analyze(raw_status, csv_text(EVENT_HEADER, events),
                   csv_text(WFI_HEADER, wfi))


def row(events, kind, cpu):
    return next(item for item in events
                if item["kind"] == kind and item["cpu"] == str(cpu))


class TicketValidationTests(unittest.TestCase):
    def test_exact_busy_witness(self):
        result = run_packet(fixture())
        self.assertEqual(result["candidate_count"], 1)
        witness = result["witnesses"][0]
        self.assertEqual(witness["raw_cmd"], "0x0000000080000001")
        self.assertEqual((witness["candidate_enter_ticket"],
                          witness["ticket_pre"], witness["ticket_post"],
                          witness["candidate_exit_ticket"]), (11, 12, 13, 14))
        self.assertEqual([(peer["cpu"], peer["enter_ticket"],
                           peer["exit_ticket"]) for peer in witness["peers"]],
                         [(1, 2, 15), (2, 5, 16), (3, 8, 17)])

    def test_clock_mode_keeps_tickets_without_raw_command(self):
        packet = fixture()
        packet[0]["mode"] = "wfi_clock"
        for wfi_row in packet[2]:
            wfi_row.update(mode="wfi_clock", cmd="", cmd_valid="0")
        result = run_packet(packet)
        self.assertEqual((result["wfi_rows"], result["busy_rows"],
                          result["candidate_count"]), (4, 0, 0))

    def test_clear_word_is_not_busy(self):
        packet = fixture()
        packet[2][0]["cmd"] = "0x00000001"
        self.assertEqual(run_packet(packet)["candidate_count"], 0)

    def test_early_peer_exit_rejects_busy_candidate(self):
        packet = fixture()
        status, events, wfi = packet
        row(events, "idle_exit", 1)["ticket"] = "11"
        row(events, "idle_exit", 1)["t0"] = "111"
        row(events, "idle_exit", 1)["t1"] = "111"
        row(events, "idle_enter", 0)["ticket"] = "12"
        row(events, "idle_enter", 0)["t0"] = "112"
        row(events, "idle_enter", 0)["t1"] = "112"
        wfi[0]["ticket_pre"] = "13"
        wfi[0]["ticket_post"] = "14"
        wfi[0]["t0"] = "113"
        wfi[0]["t1"] = "114"
        row(events, "idle_exit", 0)["ticket"] = "15"
        row(events, "idle_exit", 0)["t0"] = "115"
        row(events, "idle_exit", 0)["t1"] = "115"
        result = run_packet(packet)
        self.assertEqual(result["busy_rows"], 1)
        self.assertEqual(result["candidate_count"], 0)
        self.assertIn("peer1_interval_missing", result["busy_screen"][0]["reasons"])

    def test_duplicate_ticket_rejected(self):
        packet = fixture()
        row(packet[1], "idle_exit", 1)["ticket"] = "16"
        with self.assertRaisesRegex(TicketError, "ticket"):
            run_packet(packet)

    def test_missing_ticket_rejected(self):
        packet = fixture()
        packet[0]["cluster0_ticket_stop"] = "19"
        with self.assertRaisesRegex(TicketError, "missing or extra ticket"):
            run_packet(packet)

    def test_sentinel_boundary_rejected(self):
        packet = fixture()
        packet[2][0]["ticket_pre"] = packet[0]["cluster0_ticket_start"]
        with self.assertRaisesRegex(TicketError, "ticket"):
            run_packet(packet)

    def test_stop_sentinel_boundary_rejected(self):
        packet = fixture()
        row(packet[1], "idle_exit", 3)["ticket"] = packet[0]["cluster0_ticket_stop"]
        with self.assertRaisesRegex(TicketError, "start/stop sentinel"):
            run_packet(packet)

    def test_nested_idle_rejected(self):
        packet = fixture()
        exit_row = row(packet[1], "idle_exit", 1)
        exit_row.update(kind="idle_enter", token="2")
        with self.assertRaisesRegex(TicketError, "nested idle enter"):
            run_packet(packet)

    def test_mismatched_token_rejected(self):
        packet = fixture()
        row(packet[1], "idle_exit", 1)["token"] = "99"
        with self.assertRaisesRegex(TicketError, "mismatched idle token"):
            run_packet(packet)

    def test_noncontiguous_idle_token_rejected(self):
        packet = fixture()
        row(packet[1], "idle_enter", 1)["token"] = "2"
        row(packet[1], "idle_exit", 1)["token"] = "2"
        with self.assertRaisesRegex(TicketError, "idle token is not contiguous"):
            run_packet(packet)

    def test_reordered_probe_rejected_with_complete_ticket_set(self):
        packet = fixture()
        row(packet[1], "idle_enter", 0)["ticket"] = "12"
        packet[2][0]["ticket_pre"] = "11"
        with self.assertRaisesRegex(TicketError, "probe precedes matching idle enter"):
            run_packet(packet)

    def test_idle_overflow_rejected(self):
        packet = fixture()
        packet[0]["idle1_overflow"] = "1"
        with self.assertRaisesRegex(TicketError, "idle1: stream overflow"):
            run_packet(packet)

    def test_dvfs_missing_commit_rejected(self):
        packet = fixture()
        packet[0]["dvfs0_missing_commit"] = "1"
        with self.assertRaisesRegex(TicketError, "dvfs0: stream overflow"):
            run_packet(packet)

    def test_wfi_overflow_rejected(self):
        packet = fixture()
        packet[0]["wfi0_overflow"] = "1"
        with self.assertRaisesRegex(TicketError, "wfi0: stream overflow"):
            run_packet(packet)

    def test_pm_failure_disqualifies_witness(self):
        packet = fixture()
        packet[1].append(event("cpu_pm_fail", 1, 2, 2, 0))
        packet[1][-1]["ticket"] = ""
        packet[1][-1]["t0"] = "118"
        packet[1][-1]["t1"] = "118"
        packet[1][-1]["ret"] = "-1"
        packet[0]["idle1_attempts"] = "3"
        packet[0]["idle1_committed"] = "3"
        with self.assertRaisesRegex(TicketError, "CPU PM failure"):
            run_packet(packet)

    def test_raw_validity_mismatch_rejected(self):
        packet = fixture()
        packet[2][0]["cmd_valid"] = "0"
        with self.assertRaisesRegex(TicketError, "command validity mismatch"):
            run_packet(packet)

    def test_omitted_wfi_probe_rejected_with_complete_ticket_set(self):
        packet = fixture()
        status, events, wfi = packet
        wfi.pop(3)
        status["wfi3_attempts"] = "0"
        status["wfi3_committed"] = "0"
        status["cluster0_ticket_stop"] = "16"
        for item in events:
            if item["ticket"] and int(item["ticket"]) > 10:
                item["ticket"] = str(int(item["ticket"]) - 2)
        for item in wfi:
            for field in ("ticket_pre", "ticket_post"):
                if int(item[field]) > 10:
                    item[field] = str(int(item[field]) - 2)
        with self.assertRaisesRegex(TicketError, "lacks first-attempt WFI slot"):
            run_packet(packet)

    def test_policy_mask_instability_rejected(self):
        packet = fixture()
        packet[0]["cluster0_policy_mask_end"] = "0x07"
        with self.assertRaisesRegex(TicketError, "policy mask differs"):
            run_packet(packet)

    def test_policy_cpu_instability_rejected(self):
        packet = fixture()
        packet[0]["cluster0_policy_cpu_end"] = "1"
        with self.assertRaisesRegex(TicketError, "policy CPU changed"):
            run_packet(packet)

    def test_fast_switch_instability_rejected(self):
        packet = fixture()
        packet[0]["cluster0_fast_switch_end"] = "0"
        with self.assertRaisesRegex(TicketError, "fast-switch state changed"):
            run_packet(packet)

    def test_dvfs_target_mismatch_rejected(self):
        packet = fixture()
        packet[1].append(dvfs_event())
        packet[1][-1]["policy_cpu"] = "1"
        packet[0]["dvfs0_attempts"] = "1"
        packet[0]["dvfs0_committed"] = "1"
        with self.assertRaisesRegex(TicketError, "DVFS target/policy snapshot mismatch"):
            run_packet(packet)

    def test_dvfs_policy_mask_mismatch_rejected(self):
        packet = fixture()
        packet[1].append(dvfs_event())
        packet[1][-1]["policy_mask"] = "0x07"
        packet[0]["dvfs0_attempts"] = "1"
        packet[0]["dvfs0_committed"] = "1"
        with self.assertRaisesRegex(TicketError, "DVFS target/policy snapshot mismatch"):
            run_packet(packet)

    def test_remote_dvfs_writer_accepted_as_provenance(self):
        packet = fixture()
        packet[1].append(dvfs_event(writer=4))
        packet[0]["dvfs0_attempts"] = "1"
        packet[0]["dvfs0_committed"] = "1"
        self.assertEqual(run_packet(packet)["candidate_count"], 1)

    def test_after_stop_prepare_rejected(self):
        packet = fixture()
        packet[0]["wfi_prepare_after_stop"] = "1"
        with self.assertRaisesRegex(TicketError, "WFI prepare after stop"):
            run_packet(packet)

    def test_status_tick_bracket_rejected(self):
        packet = fixture()
        packet[0]["end_tick"] = "1999"
        with self.assertRaisesRegex(TicketError, "tick bracket"):
            run_packet(packet)

    def test_monotonic_interior_bracket_rejected(self):
        packet = fixture()
        packet[0]["inside_stop_ns"] = packet[0]["inside_start_ns"]
        with self.assertRaisesRegex(TicketError, "monotonic capture-interior"):
            run_packet(packet)

    def test_absurd_status_attempt_count_rejected_without_allocation(self):
        packet = fixture()
        packet[0]["idle1_attempts"] = str((1 << 64) - 1)
        with self.assertRaisesRegex(TicketError, "idle1_attempts: out of range"):
            run_packet(packet)

    def test_idle_local_counter_order_rejected(self):
        packet = fixture()
        row(packet[1], "idle_exit", 1)["t0"] = "101"
        row(packet[1], "idle_exit", 1)["t1"] = "101"
        with self.assertRaisesRegex(TicketError, "local counter order"):
            run_packet(packet)

    def test_probe_local_counter_order_rejected(self):
        packet = fixture()
        packet[2][0]["t0"] = "104"
        packet[2][0]["t1"] = "104"
        with self.assertRaisesRegex(TicketError, "probe counter precedes"):
            run_packet(packet)


if __name__ == "__main__":
    unittest.main()
