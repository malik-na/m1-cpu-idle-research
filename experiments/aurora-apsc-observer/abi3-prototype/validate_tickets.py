#!/usr/bin/env python3
"""Read-only ABI 3 ticket integrity and software-candidate screen."""

import argparse
import csv
import hashlib
import io
import json
import re
from pathlib import Path


CPUS = 8
CLUSTERS = 2
U64_MAX = (1 << 64) - 1
BUSY_BIT = 1 << 31
EVENT_HEADER = (
    "kind,seq,cpu,cluster,policy_cpu,policy_mask,fast_switch,"
    "requested_index,requested_pstate,token,t0,t1,pre_cmd,cmd,ret,flags,ticket"
)
WFI_HEADER = "seq,cpu,cluster,token,t0,t1,cmd,mode,cmd_valid,ticket_pre,ticket_post"


class TicketError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise TicketError(message)


def decimal(value, name, maximum=U64_MAX):
    require(isinstance(value, str) and re.fullmatch(r"[0-9]+", value),
            f"{name}: expected unsigned decimal")
    result = int(value)
    require(result <= maximum, f"{name}: out of range")
    return result


def signed_decimal(value, name):
    require(isinstance(value, str) and re.fullmatch(r"-?[0-9]+", value),
            f"{name}: expected signed decimal")
    result = int(value)
    require(-(1 << 31) <= result < (1 << 31), f"{name}: out of range")
    return result


def hexword(value, name):
    require(isinstance(value, str) and re.fullmatch(r"0x[0-9a-fA-F]{1,16}", value),
            f"{name}: expected 64-bit hex word")
    return int(value, 16)


def status_map(raw):
    result = {}
    for line in raw.splitlines():
        require("=" in line, "status: malformed line")
        key, value = line.split("=", 1)
        require(key and key not in result, f"status: duplicate or empty key {key!r}")
        result[key] = value
    return result


def rows(raw, header, name):
    reader = csv.DictReader(io.StringIO(raw))
    require(reader.fieldnames == header.split(","), f"{name}: ABI 3 header mismatch")
    result = []
    for number, row in enumerate(reader, 2):
        require(None not in row and all(value is not None for value in row.values()),
                f"{name}:{number}: wrong column count")
        result.append(row)
    return result


def analyze(status_raw, events_raw, wfi_raw):
    status = status_map(status_raw)
    require(status.get("abi") == "3", "status: expected abi=3")
    require(status.get("state") == "complete", "status: capture is not complete")
    mode = status.get("mode")
    require(mode in ("records", "mmio", "wfi_clock", "wfi_mmio"),
            "status: unknown mode")
    require(decimal(status.get("interrupted"), "interrupted") == 0,
            "status: interrupted capture")
    require(decimal(status.get("wfi_pending_after_drain"),
                    "wfi_pending_after_drain") == 0,
            "status: uncommitted WFI slots")
    require(decimal(status.get("wfi_prepare_bad_mapping"),
                    "wfi_prepare_bad_mapping") == 0,
            "status: bad WFI mapping")
    after_stop = decimal(status.get("wfi_prepare_after_stop"),
                         "wfi_prepare_after_stop")
    require(after_stop == 0, "status: WFI prepare after stop")
    frequency = decimal(status.get("cntfrq"), "cntfrq")
    start_tick = decimal(status.get("start_tick"), "start_tick")
    stop_tick = decimal(status.get("stop_tick"), "stop_tick")
    end_tick = decimal(status.get("end_tick"), "end_tick")
    inside_start_ns = decimal(status.get("inside_start_ns"), "inside_start_ns")
    inside_stop_ns = decimal(status.get("inside_stop_ns"), "inside_stop_ns")
    require(frequency > 0 and 0 < start_tick < stop_tick <= end_tick,
            "status: invalid counter frequency or control-task tick bracket")
    require(0 < inside_start_ns < inside_stop_ns,
            "status: invalid monotonic capture-interior bracket")
    start_online = hexword(status.get("start_online_mask"), "start_online_mask")
    end_online = hexword(status.get("end_online_mask"), "end_online_mask")
    require(start_online == end_online == 0xff, "status: online CPU mask changed")

    masks = []
    sentinels = []
    policies = []
    for cluster in range(CLUSTERS):
        mask = hexword(status.get(f"cluster{cluster}_cpus"),
                       f"cluster{cluster}_cpus")
        start = decimal(status.get(f"cluster{cluster}_ticket_start"),
                        f"cluster{cluster}_ticket_start")
        stop = decimal(status.get(f"cluster{cluster}_ticket_stop"),
                       f"cluster{cluster}_ticket_stop")
        require(start > 0 and start < stop, f"cluster{cluster}: invalid sentinels")
        policy_mask_start = hexword(status.get(f"cluster{cluster}_policy_mask_start"),
                                    f"cluster{cluster}_policy_mask_start")
        policy_mask_end = hexword(status.get(f"cluster{cluster}_policy_mask_end"),
                                  f"cluster{cluster}_policy_mask_end")
        policy_cpu_start = decimal(status.get(f"cluster{cluster}_policy_cpu_start"),
                                   f"cluster{cluster}_policy_cpu_start", CPUS - 1)
        policy_cpu_end = decimal(status.get(f"cluster{cluster}_policy_cpu_end"),
                                 f"cluster{cluster}_policy_cpu_end", CPUS - 1)
        fast_start = decimal(status.get(f"cluster{cluster}_fast_switch_start"),
                             f"cluster{cluster}_fast_switch_start", 1)
        fast_end = decimal(status.get(f"cluster{cluster}_fast_switch_end"),
                           f"cluster{cluster}_fast_switch_end", 1)
        require(policy_mask_start == policy_mask_end == mask,
                f"cluster{cluster}: policy mask differs from CPU mask")
        require(policy_cpu_start == policy_cpu_end and
                mask & (1 << policy_cpu_start),
                f"cluster{cluster}: policy CPU changed or is outside cluster")
        require(fast_start == fast_end,
                f"cluster{cluster}: fast-switch state changed")
        masks.append(mask)
        sentinels.append((start, stop))
        policies.append((policy_cpu_start, fast_start))
    require(masks[0] & masks[1] == 0 and masks[0] | masks[1] == 0xff,
            "status: cluster masks do not partition CPUs 0-7")

    event_rows = rows(events_raw, EVENT_HEADER, "events")
    wfi_rows = rows(wfi_raw, WFI_HEADER, "wfi-events")
    grouped = {(kind, index): [] for kind, count in
               (("idle", CPUS), ("wfi", CPUS), ("dvfs", CLUSTERS))
               for index in range(count)}
    ticket_values = [[] for _ in range(CLUSTERS)]
    idle_by_cpu = [[] for _ in range(CPUS)]

    for number, row in enumerate(event_rows, 2):
        label = f"events:{number}"
        kind = row["kind"]
        require(kind in ("idle_enter", "idle_exit", "cpu_pm_fail", "dvfs"),
                f"{label}: invalid kind")
        cpu = decimal(row["cpu"], f"{label}:cpu", CPUS - 1)
        cluster = decimal(row["cluster"], f"{label}:cluster", CLUSTERS - 1)
        seq = decimal(row["seq"], f"{label}:seq", (1 << 32) - 1)
        t0 = decimal(row["t0"], f"{label}:t0")
        t1 = decimal(row["t1"], f"{label}:t1")
        require(t0 <= t1, f"{label}: reversed local counter bracket")
        stream = "dvfs" if kind == "dvfs" else "idle"
        grouped[(stream, cluster if stream == "dvfs" else cpu)].append(seq)
        row = dict(row, seq_num=seq, cpu_num=cpu, cluster_num=cluster,
                   t0_num=t0, t1_num=t1)
        signed_decimal(row["ret"], f"{label}:ret")
        decimal(row["flags"], f"{label}:flags", (1 << 32) - 1)
        if stream == "idle":
            require(masks[cluster] & (1 << cpu), f"{label}: CPU/cluster mismatch")
            require(all(row[field] == "" for field in
                        ("policy_cpu", "policy_mask", "fast_switch",
                         "requested_index", "requested_pstate", "pre_cmd")),
                    f"{label}: idle row carries DVFS-only fields")
            if kind == "idle_enter":
                require(row["ret"] == "0", f"{label}: idle enter failed")
                if mode == "mmio":
                    require(row["flags"] == "1" and row["cmd"],
                            f"{label}: idle MMIO command missing")
                    hexword(row["cmd"], f"{label}:cmd")
                else:
                    require(row["flags"] == "0" and row["cmd"] == "",
                            f"{label}: unexpected idle command")
            elif kind == "idle_exit":
                require(row["ret"] == "0" and row["flags"] == "0" and
                        row["cmd"] == "", f"{label}: malformed idle exit")
            else:
                require(row["ret"] != "0" and row["flags"] == "0" and
                        row["cmd"] == "", f"{label}: malformed PM failure")
            token = decimal(row["token"], f"{label}:token")
            require(token > 0, f"{label}: zero idle token")
            row["token_num"] = token
            idle_by_cpu[cpu].append(row)
            if kind in ("idle_enter", "idle_exit"):
                ticket = decimal(row["ticket"], f"{label}:ticket")
                require(ticket > 0, f"{label}: zero idle ticket")
                row["ticket_num"] = ticket
                ticket_values[cluster].append(ticket)
            else:
                require(row["ticket"] == "", f"{label}: PM fail has ticket")
        else:
            require(row["ticket"] == "", f"{label}: DVFS has idle ticket")
            require(row["token"] == "", f"{label}: DVFS has idle token")
            require(row["flags"] == "0", f"{label}: unexpected DVFS flags")
            policy_cpu = decimal(row["policy_cpu"], f"{label}:policy_cpu", CPUS - 1)
            policy_mask = hexword(row["policy_mask"], f"{label}:policy_mask")
            fast_switch = decimal(row["fast_switch"], f"{label}:fast_switch", 1)
            require(policy_cpu == policies[cluster][0] and
                    policy_mask == masks[cluster] and
                    fast_switch == policies[cluster][1],
                    f"{label}: DVFS target/policy snapshot mismatch")
            decimal(row["requested_index"], f"{label}:requested_index", (1 << 32) - 1)
            decimal(row["requested_pstate"], f"{label}:requested_pstate", (1 << 32) - 1)
            hexword(row["pre_cmd"], f"{label}:pre_cmd")
            if row["cmd"]:
                hexword(row["cmd"], f"{label}:cmd")
                require(row["ret"] == "0", f"{label}: successful SET has failure code")
            else:
                require(signed_decimal(row["ret"], f"{label}:ret") < 0,
                        f"{label}: failed poll has no error")

    parsed_wfi = []
    for number, row in enumerate(wfi_rows, 2):
        label = f"wfi-events:{number}"
        cpu = decimal(row["cpu"], f"{label}:cpu", CPUS - 1)
        cluster = decimal(row["cluster"], f"{label}:cluster", CLUSTERS - 1)
        seq = decimal(row["seq"], f"{label}:seq", (1 << 32) - 1)
        token = decimal(row["token"], f"{label}:token")
        t0 = decimal(row["t0"], f"{label}:t0")
        t1 = decimal(row["t1"], f"{label}:t1")
        pre = decimal(row["ticket_pre"], f"{label}:ticket_pre")
        post = decimal(row["ticket_post"], f"{label}:ticket_post")
        require(token > 0 and pre > 0 and pre < post,
                f"{label}: invalid token or ticket bracket")
        require(t0 <= t1, f"{label}: reversed local counter bracket")
        require(masks[cluster] & (1 << cpu), f"{label}: CPU/cluster mismatch")
        require(mode in ("wfi_clock", "wfi_mmio") and row["mode"] == mode,
                f"{label}: WFI mode mismatch")
        valid = decimal(row["cmd_valid"], f"{label}:cmd_valid", 1)
        require(valid == int(mode == "wfi_mmio"),
                f"{label}: command validity mismatch")
        if valid:
            cmd = hexword(row["cmd"], f"{label}:cmd")
        else:
            require(row["cmd"] == "", f"{label}: invalid raw command present")
            cmd = None
        grouped[("wfi", cpu)].append(seq)
        ticket_values[cluster].extend((pre, post))
        parsed_wfi.append(dict(row, cpu_num=cpu, cluster_num=cluster,
                               token_num=token, t0_num=t0, t1_num=t1,
                               seq_num=seq, ticket_pre_num=pre,
                               ticket_post_num=post, cmd_num=cmd))

    for (kind, index), seqs in grouped.items():
        name = f"{kind}{index}"
        capacity = 8192 if kind == "dvfs" else 16384
        attempts = decimal(status.get(f"{name}_attempts"),
                           f"{name}_attempts", capacity)
        committed = decimal(status.get(f"{name}_committed"),
                            f"{name}_committed", capacity)
        overflow = decimal(status.get(f"{name}_overflow"), f"{name}_overflow")
        missing = decimal(status.get(f"{name}_missing_commit"),
                          f"{name}_missing_commit")
        require(overflow == missing == 0 and attempts == committed,
                f"{name}: stream overflow, missing commit, or count mismatch")
        require(len(seqs) == committed,
                f"{name}: CSV row count does not match status")
        require(all(actual == expected for expected, actual in enumerate(sorted(seqs))),
                f"{name}: sequence numbers do not match status")

    for cluster, values in enumerate(ticket_values):
        start, stop = sentinels[cluster]
        require(all(start < ticket < stop for ticket in values),
                f"cluster{cluster}: ticket crosses start/stop sentinel")
        require(len(values) == stop - start - 1,
                f"cluster{cluster}: missing or extra ticket")
        for expected, actual in enumerate(sorted(values), start + 1):
            require(actual == expected,
                    f"cluster{cluster}: duplicate, missing, or out-of-range ticket")

    entered = {}
    completed = {cpu: [] for cpu in range(CPUS)}
    for cpu, stream in enumerate(idle_by_cpu):
        open_enter = None
        previous_ticket = 0
        previous_t1 = None
        expected_token = 1
        for row in sorted(stream, key=lambda item: item["seq_num"]):
            kind = row["kind"]
            token = row["token_num"]
            require(previous_t1 is None or previous_t1 <= row["t0_num"],
                    f"idle{cpu}: local counter order contradicts stream order")
            previous_t1 = row["t1_num"]
            if kind == "cpu_pm_fail":
                raise TicketError(f"idle{cpu}: CPU PM failure disqualifies witnesses")
            ticket = row["ticket_num"]
            require(ticket > previous_ticket,
                    f"idle{cpu}: ticket order contradicts stream order")
            previous_ticket = ticket
            if kind == "idle_enter":
                require(open_enter is None, f"idle{cpu}: nested idle enter")
                require(token == expected_token,
                        f"idle{cpu}: idle token is not contiguous from one")
                expected_token += 1
                open_enter = row
                entered[(cpu, token)] = row
            else:
                require(open_enter is not None, f"idle{cpu}: orphan idle exit")
                require(token == open_enter["token_num"],
                        f"idle{cpu}: mismatched idle token")
                require(open_enter["t1_num"] <= row["t0_num"],
                        f"idle{cpu}: exit counter precedes enter counter")
                completed[cpu].append((open_enter, row))
                open_enter = None

    for cpu in range(CPUS):
        previous_t1 = None
        for row in sorted((item for item in parsed_wfi if item["cpu_num"] == cpu),
                          key=lambda item: item["seq_num"]):
            require(previous_t1 is None or previous_t1 <= row["t0_num"],
                    f"wfi{cpu}: local counter order contradicts stream order")
            previous_t1 = row["t1_num"]

    seen_probes = set()
    busy_screen = []
    witnesses = []
    for row in parsed_wfi:
        cpu, cluster, token = row["cpu_num"], row["cluster_num"], row["token_num"]
        key = (cpu, token)
        require(key not in seen_probes, f"wfi{cpu}: repeated probe token {token}")
        seen_probes.add(key)
        require(key in entered, f"wfi{cpu}: probe has no matching idle enter")
        own_enter = entered[key]
        pre, post = row["ticket_pre_num"], row["ticket_post_num"]
        require(own_enter["ticket_num"] < pre,
                f"wfi{cpu}: probe precedes matching idle enter")
        require(own_enter["t1_num"] <= row["t0_num"],
                f"wfi{cpu}: probe counter precedes matching idle enter")
        own_pairs = [pair for pair in completed[cpu]
                     if pair[0]["token_num"] == token]
        require(len(own_pairs) <= 1, f"wfi{cpu}: duplicate matching idle interval")
        own_exit = own_pairs[0][1] if own_pairs else None
        if own_exit is not None:
            require(post < own_exit["ticket_num"],
                    f"wfi{cpu}: probe follows matching idle exit")
            require(row["t1_num"] <= own_exit["t0_num"],
                    f"wfi{cpu}: probe counter follows matching idle exit")
        if row["cmd_num"] is None or not row["cmd_num"] & BUSY_BIT:
            continue
        reasons = []
        peers = []
        if own_exit is None:
            reasons.append("candidate_exit_missing")
        for peer in range(CPUS):
            if peer == cpu or not masks[cluster] & (1 << peer):
                continue
            matches = [(start, end) for start, end in completed[peer]
                       if start["ticket_num"] < own_enter["ticket_num"]
                       and post < end["ticket_num"]]
            require(len(matches) <= 1, f"peer{peer}: contradictory intervals")
            if not matches:
                reasons.append(f"peer{peer}_interval_missing")
            else:
                start, end = matches[0]
                peers.append({"cpu": peer, "token": start["token_num"],
                              "enter_ticket": start["ticket_num"],
                              "exit_ticket": end["ticket_num"]})
        screen = {"cluster": cluster, "cpu": cpu, "token": token,
                  "raw_cmd": f"0x{row['cmd_num']:016x}",
                  "capture_start_ticket": sentinels[cluster][0],
                  "capture_stop_ticket": sentinels[cluster][1],
                  "ticket_pre": pre, "ticket_post": post,
                  "candidate_enter_ticket": own_enter["ticket_num"],
                  "candidate_exit_ticket": own_exit["ticket_num"] if own_exit else None,
                  "peers": peers, "reasons": reasons}
        busy_screen.append(screen)
        if not reasons:
            witnesses.append(screen)

    if mode in ("wfi_clock", "wfi_mmio"):
        require(seen_probes == set(entered),
                "wfi: recorded idle enter lacks first-attempt WFI slot")

    return {"abi": 3, "mode": mode,
            "scope": "ticket-ordered software-hook candidate at first-attempt pre-DSB read",
            "wfi_prepare_after_stop": after_stop,
            "idle_rows": sum(len(stream) for stream in idle_by_cpu),
            "wfi_rows": len(parsed_wfi),
            "busy_rows": len(busy_screen),
            "candidate_count": len(witnesses),
            "busy_screen": busy_screen, "witnesses": witnesses}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status", type=Path, required=True)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--wfi-events", type=Path, required=True)
    args = parser.parse_args()
    raw = {"status": args.status.read_bytes(), "events": args.events.read_bytes(),
           "wfi_events": args.wfi_events.read_bytes()}
    try:
        result = analyze(raw["status"].decode("utf-8"),
                         raw["events"].decode("utf-8"),
                         raw["wfi_events"].decode("utf-8"))
    except TicketError as error:
        parser.exit(2, f"ABI 3 reject: {error}\n")
    result["input_sha256"] = {name: hashlib.sha256(data).hexdigest()
                              for name, data in raw.items()}
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
