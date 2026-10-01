"""Conditional screen of recorded software idle intervals, never hardware proof.

``screen`` consumes the typed, ABI-checked events/status produced by analyze.py.
The caller must first run its idle-pair validation and pass every capture-wide
integrity reason. This module additionally rejects contradictory idle grammar.
Supplying a clock-error bound is an assumption, not clock qualification.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from typing import Optional


UINT64_MAX = (1 << 64) - 1
BUSY_BIT = 1 << 31
AMBIGUOUS_ID_LIMIT = 32
GRAMMAR_REASON_LIMIT = 32


def _identity(event: dict) -> dict:
    return {name: event[name] for name in ("kind", "stream", "seq", "cpu", "cluster", "t0", "t1")}


def _interval(entry: dict, exit_event: dict, status: dict, error: int) -> dict:
    return {
        "cpu": entry["cpu"],
        "cluster": entry["cluster"],
        "token": entry["token"],
        "entry_seq": entry["seq"],
        "exit_seq": exit_event["seq"],
        "entry_t0": entry["t0"],
        "entry_t1": entry["t1"],
        "exit_t0": exit_event["t0"],
        "exit_t1": exit_event["t1"],
        "start_margin_ticks": entry["t0"] - status["start_tick"] - error,
        "stop_margin_ticks": status["stop_tick"] - exit_event["t1"] - error,
    }


def _pair_events(events: list[dict]) -> tuple[list[tuple[dict, dict]], dict, list[str], int]:
    """A lossless one-shot recorder permits only a trailing unmatched entry."""
    by_cpu = defaultdict(list)
    for event in events:
        if event["kind"] != "dvfs":
            by_cpu[event["cpu"]].append(event)
    pairs = []
    counts = Counter()
    reasons = []
    reason_count = 0

    def contradiction(reason: str) -> None:
        nonlocal reason_count
        reason_count += 1
        if len(reasons) < GRAMMAR_REASON_LIMIT:
            reasons.append(reason)

    for cpu, stream in sorted(by_cpu.items()):
        pending = None
        for event in sorted(stream, key=lambda row: row["seq"]):
            kind = event["kind"]
            if kind == "idle_enter":
                if pending is not None:
                    counts["interior_unmatched_enter"] += 1
                    contradiction(f"idle{cpu}: entry seq {event['seq']} while token {pending['token']} is open")
                pending = event
            elif kind == "idle_exit":
                if pending is None:
                    counts["orphan_exit"] += 1
                    contradiction(f"idle{cpu}: exit seq {event['seq']} has no open entry")
                elif pending["token"] != event["token"]:
                    counts["mismatched_exit"] += 1
                    contradiction(f"idle{cpu}: exit token {event['token']} disagrees with open token {pending['token']}")
                    pending = None
                else:
                    pairs.append((pending, event))
                    pending = None
            else:
                counts["cpu_pm_fail"] += 1
                if pending is not None:
                    counts["cpu_pm_fail_inside_open_interval"] += 1
                    contradiction(f"idle{cpu}: CPU-PM failure seq {event['seq']} while token {pending['token']} is open")
        if pending is not None:
            counts["trailing_unmatched_enter"] += 1
    return pairs, {name: counts[name] for name in (
        "trailing_unmatched_enter", "interior_unmatched_enter", "orphan_exit",
        "mismatched_exit", "cpu_pm_fail", "cpu_pm_fail_inside_open_interval",
    )}, reasons, reason_count


class _WriteIndex:
    """Count interval relations and fetch a bounded overlap sample efficiently."""

    def __init__(self, events: list[dict]):
        self.by_start = sorted(events, key=lambda row: (row["t0"], row["t1"], row["seq"]))
        self.by_end = sorted(events, key=lambda row: (row["t1"], row["t0"], row["seq"]))
        self.starts = [row["t0"] for row in self.by_start]
        self.ends = [row["t1"] for row in self.by_end]
        # Range-maximum pruning avoids rescanning every prior write to recover
        # a few ambiguous IDs. Python integers deliberately cannot wrap here.
        size = 1
        while size < len(events):
            size *= 2
        self.size = size
        self.max_end = [-1] * (size * 2)
        for index, event in enumerate(self.by_start):
            self.max_end[size + index] = event["t1"]
        for index in range(size - 1, 0, -1):
            self.max_end[index] = max(self.max_end[index * 2], self.max_end[index * 2 + 1])

    def relations(self, sample: dict, error: int, limit: int) -> tuple[int, int, int, Optional[dict], list[dict]]:
        lower = sample["t0"] - error
        upper = sample["t1"] + error
        before = bisect_left(self.ends, lower)
        not_after = bisect_right(self.starts, upper)
        after = len(self.by_start) - not_after
        ambiguous = len(self.by_start) - before - after
        nearest = self.by_end[before - 1] if before else None
        selected = []
        if ambiguous and limit:
            stack = [(1, 0, self.size)]
            while stack and len(selected) < limit:
                node, start, end = stack.pop()
                if start >= not_after or self.max_end[node] < lower:
                    continue
                if end - start == 1:
                    selected.append(self.by_start[start])
                else:
                    middle = (start + end) // 2
                    stack.append((node * 2 + 1, middle, end))
                    stack.append((node * 2, start, middle))
        return before, after, ambiguous, nearest, selected


def _write_witness(event: dict, sample: dict, error: int) -> dict:
    return {
        **_identity(event),
        "requested_index": event["requested_index"],
        "requested_pstate": event["requested_pstate"],
        "policy_cpu": event["policy_cpu"],
        "policy_mask": hex(event["policy_mask"]),
        "fast_switch": event["fast_switch"],
        "raw_pre_command": hex(event["pre_cmd"]),
        "raw_submitted_command": hex(event["cmd"]),
        "clock_error_applied_ticks": error,
        "strict_before_margin_ticks": sample["t0"] - event["t1"] - error,
    }


def _correlate(sample: dict, indices: dict, error: int) -> dict:
    counts = Counter()
    nearest = None
    nearest_error = None
    ambiguous_ids = []
    for cpu, index in sorted(indices.items()):
        applied_error = 0 if cpu == sample["cpu"] else error
        before, after, ambiguous, selected, ambiguous_rows = index.relations(
            sample, applied_error, AMBIGUOUS_ID_LIMIT - len(ambiguous_ids)
        )
        counts["definitely_before"] += before
        counts["definitely_after"] += after
        counts["temporally_ambiguous"] += ambiguous
        if selected is not None and (nearest is None or (
            selected["t1"], selected["t0"], selected["cpu"], selected["seq"]
        ) > (nearest["t1"], nearest["t0"], nearest["cpu"], nearest["seq"])):
            nearest = selected
            nearest_error = applied_error
        ambiguous_ids.extend({**_identity(row), "clock_error_applied_ticks": applied_error} for row in ambiguous_rows)
    return {
        "scope": "all committed successful attempted writes to this target cluster, including drain records",
        "counts": {name: counts[name] for name in ("definitely_before", "definitely_after", "temporally_ambiguous")},
        "nearest_by_recorded_t1_definitely_before": (
            _write_witness(nearest, sample, nearest_error) if nearest is not None else None
        ),
        "temporally_ambiguous_ids": ambiguous_ids,
        "ambiguous_id_limit": AMBIGUOUS_ID_LIMIT,
        "ambiguous_ids_truncated": counts["temporally_ambiguous"] > len(ambiguous_ids),
        "ambiguous_ids_omitted": counts["temporally_ambiguous"] - len(ambiguous_ids),
        "ambiguous_id_selection": "writer CPU ascending, then recorded t0, t1 and sequence ascending",
        "causal_busy_source": "not_established",
    }


def screen(events: list[dict], status: dict, *, integrity_reasons: list[str],
           pairwise_clock_error_ticks: Optional[int]) -> dict:
    """Screen validated records under an explicitly supplied clock assumption.

    The bound covers relative clock error for every pair of participating CPUs
    throughout the capture (including drift and the unrecorded control CPU).
    Equal endpoints never establish ordering. Arithmetic does not wrap at 64
    bits. Same-CPU DVFS comparisons use zero cross-CPU clock error.
    """
    error = pairwise_clock_error_ticks
    if error is not None and (isinstance(error, bool) or not isinstance(error, int)
                              or not 0 <= error <= UINT64_MAX):
        raise ValueError("pairwise_clock_error_ticks must be None or an unsigned uint64 integer, not bool")
    pairs, exclusions, grammar_reasons, grammar_reason_count = _pair_events(events)
    candidates = []
    eligible_pairs = []
    exclusions["recorded_capture_boundary_pairs"] = 0
    exclusions["clock_margin_boundary_pairs"] = 0
    for entry, exit_event in pairs:
        if entry["t0"] <= status["start_tick"] or exit_event["t1"] >= status["stop_tick"]:
            exclusions["recorded_capture_boundary_pairs"] += 1
        elif error is not None and (
            entry["t0"] <= status["start_tick"] + error
            or exit_event["t1"] + error >= status["stop_tick"]
        ):
            exclusions["clock_margin_boundary_pairs"] += 1
        else:
            eligible_pairs.append((entry, exit_event))

    if integrity_reasons:
        screen_status = "suppressed_integrity_failure"
    elif grammar_reason_count:
        screen_status = "suppressed_contradictory_idle_stream"
    elif error is None:
        screen_status = "unavailable_without_clock_bound"
    else:
        screen_status = "conditional_software_screen"

    rejected = 0
    if screen_status == "conditional_software_screen":
        by_cpu = defaultdict(list)
        for pair in eligible_pairs:
            by_cpu[pair[0]["cpu"]].append(pair)
        ends = {}
        for cpu, intervals in by_cpu.items():
            intervals.sort(key=lambda pair: (pair[0]["t1"], pair[0]["seq"]))
            ends[cpu] = [pair[0]["t1"] for pair in intervals]
        writes = defaultdict(lambda: defaultdict(list))
        for event in events:
            if event["kind"] == "dvfs" and event["ret"] == 0:
                writes[event["cluster"]][event["cpu"]].append(event)
        indices = {
            cluster: {cpu: _WriteIndex(rows) for cpu, rows in writers.items()}
            for cluster, writers in writes.items()
        }
        for entry, exit_event in sorted(eligible_pairs, key=lambda pair: (
            pair[0]["t0"], pair[0]["cpu"], pair[0]["seq"]
        )):
            peers = [cpu for cpu in range(8) if cpu != entry["cpu"]
                     and status["clusters"][entry["cluster"]] & (1 << cpu)]
            witnesses = []
            for peer in peers:
                position = bisect_left(ends.get(peer, []), entry["t0"] - error) - 1
                if position < 0:
                    break
                peer_entry, peer_exit = by_cpu[peer][position]
                exit_margin = peer_exit["t0"] - entry["t1"] - error
                if exit_margin <= 0:
                    break
                witnesses.append({
                    **_interval(peer_entry, peer_exit, status, error),
                    "entry_before_sample_margin_ticks": entry["t0"] - peer_entry["t1"] - error,
                    "exit_after_sample_margin_ticks": exit_margin,
                })
            if len(witnesses) != len(peers):
                rejected += 1
                continue
            sample_valid = entry["flags"] == 1 and entry["ret"] == 0 and entry["cmd"] is not None
            candidates.append({
                **_interval(entry, exit_event, status, error),
                "cluster_cpu_mask": hex(status["clusters"][entry["cluster"]]),
                "sample_t0": entry["t0"],
                "sample_t1": entry["t1"],
                "sample_flags": entry["flags"],
                "sample_ret": entry["ret"],
                "raw_command": hex(entry["cmd"]) if sample_valid else None,
                "busy_bit31": bool(entry["cmd"] & BUSY_BIT) if sample_valid else None,
                "peer_interval_witnesses": witnesses,
                "target_cluster_dvfs": _correlate(entry, indices.get(entry["cluster"], {}), error),
            })

    return {
        "screen_abi": 1,
        "status": screen_status,
        "pairwise_clock_error_ticks": error,
        "clock_qualification": "unqualified; a supplied bound is an assumption only",
        "clock_bound_scope": "absolute relative error between any CPU pair throughout the capture, including drift and the unrecorded capture-control CPU",
        "definition": "complete software entry/exit intervals strictly inside clock-margin-adjusted capture bounds; every same-cluster peer entry ends before the candidate sample starts and its exit starts after that sample ends, each by more than the pairwise bound",
        "dvfs_order_definition": "write.t1+E<sample.t0 is definitely before; sample.t1+E<write.t0 is definitely after; otherwise ambiguous; E=0 for the same CPU; these order recorded software brackets, never device completion",
        "nearest_write_limit": "nearest by recorded t1 among definitely-before writes may not be the most recent actual write across CPUs and is not a causal BUSY source",
        "integrity_reasons": list(integrity_reasons),
        "idle_grammar": {
            "consistent": grammar_reason_count == 0,
            "reason_count": grammar_reason_count,
            "reasons": grammar_reasons,
            "reason_limit": GRAMMAR_REASON_LIMIT,
            "reasons_truncated": grammar_reason_count > len(grammar_reasons),
        },
        "interval_exclusions": exclusions,
        "counts": {
            "complete_recorded_pairs": len(pairs),
            "interior_pairs_after_supplied_clock_margin": len(eligible_pairs) if error is not None else None,
            "pairs_screened": len(eligible_pairs) if screen_status == "conditional_software_screen" else 0,
            "pairs_without_all_peer_witnesses": rejected,
            "candidates": len(candidates),
            "candidates_busy": sum(row["busy_bit31"] is True for row in candidates),
            "candidates_clear": sum(row["busy_bit31"] is False for row in candidates),
            "candidates_without_valid_sample": sum(row["busy_bit31"] is None for row in candidates),
        },
        "candidates": candidates,
        "claim_boundary": {
            "candidate_kind": "conditional_software_final_entrant",
            "hardware_clock_qualified": False,
            "actual_last_active_core": "not_established",
            "actual_wfi_overlap": "not_observed",
            "physical_idle_state": "not_observed",
            "dvfs_device_completion": "not_observed",
            "causal_busy_source": "not_established",
            "negative_conclusion_supported": False,
            "coverage_note": "no candidates or no BUSY candidates cannot establish absence of hardware overlap; incomplete/boundary intervals, clock assumptions, workload opportunities and observer effects limit coverage",
        },
    }
