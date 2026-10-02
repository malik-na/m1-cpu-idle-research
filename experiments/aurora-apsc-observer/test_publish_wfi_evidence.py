"""Artificial private packets for the ABI 2 publication boundary; no native run."""

from __future__ import annotations

import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest import mock

import analyze_wfi
import collect_native
import publish_wfi_evidence as publisher
import test_analyze_wfi as wfi_fixtures

REAL_BUILD_CHAIN = publisher.checked_build_chain

COUNTER_TESTS = Path(__file__).resolve().parents[1] / "linux-counter-qualification" / "test_analyze.py"
spec = importlib.util.spec_from_file_location("counter_test_fixtures_for_wfi_publication", COUNTER_TESTS)
counter_fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(counter_fixtures)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def workload(cpu: int) -> bytes:
    rows = ["cpu,pulse,iterations,start_monotonic_ns,end_monotonic_ns,checksum\n"]
    for pulse in range(44):
        start = 5_850_000_000 + pulse * 50_000_000
        rows.append(f"{cpu},{pulse},1048576,{start},{start + 1000},{pulse}\n")
    return "".join(rows).encode()


def snapshot(first_tick: int) -> bytes:
    fields = {
        "/sys/devices/system/cpu/online": "0-7",
        "/sys/devices/system/cpu/cpuidle/current_driver": "apple_idle",
        "/sys/devices/system/cpu/cpuidle/current_governor_ro": "menu",
        "/sys/class/power_supply/macsmc-ac/online": "1",
        "/sys/class/power_supply/macsmc-battery/status": "Charging",
        "/sys/class/power_supply/macsmc-battery/capacity": "52",
        "/sys/class/power_supply/macsmc-battery/current_now": "-354000",
        "/sys/class/power_supply/macsmc-battery/voltage_now": "11688000",
        "/sys/class/backlight/apple-panel-bl/brightness": "155",
        "/sys/class/backlight/apple-panel-bl/actual_brightness": "164",
        "/sys/class/backlight/apple-panel-bl/max_brightness": "420",
        "/sys/class/thermal/thermal_zone0/temp": "34200",
    }
    for cpu in range(8):
        fields[f"/sys/devices/system/cpu/cpu{cpu}/cpuidle/state1/disable"] = "0"
    for policy, cpus in ((0, "0 1 2 3"), (4, "4 5 6 7")):
        for field, value in {
            "related_cpus": cpus, "affected_cpus": cpus,
            "scaling_driver": "apple-cpufreq", "scaling_governor": "schedutil",
            "scaling_min_freq": "600000", "scaling_max_freq": "2064000",
            "scaling_cur_freq": "1704000",
        }.items():
            fields[f"/sys/devices/system/cpu/cpufreq/policy{policy}/{field}"] = value
    rows = [{"path": path, "observed_monotonic_ns": first_tick + index,
             "raw_text": value + "\n"}
            for index, (path, value) in enumerate(fields.items())]
    rows.append({"path": "/sys/class/net/wlan0/address",
                 "observed_monotonic_ns": first_tick + len(rows),
                 "raw_text": "00:11:22:33:44:55\n"})
    return (json.dumps(rows) + "\n").encode()


def environment_observation(before: bool) -> bytes:
    base = 100 if before else 8_250_000_100
    offset = 0 if before else 500
    network = []
    for index, (name, iftype, state, carrier) in enumerate((
            ("lo", 772, "unknown", 1), ("wlan0", 1, "up", 1))):
        network.append({
            "name": name, "iftype": iftype, "operstate": state, "carrier": carrier,
            "rx_bytes": 1000 + index * 100 + offset,
            "tx_bytes": 2000 + index * 100 + offset,
            "rx_packets": 10 + index + offset // 100,
            "tx_packets": 20 + index + offset // 100,
            "observed_monotonic_ns": base + index + 1,
        })
    result = {
        "schema": 1,
        "observed_monotonic_ns_begin": base,
        "observed_monotonic_ns_end": base + 10,
        "network": network,
        "usb_devices": [
            {"node": "1-1", "id_vendor": "abcd", "id_product": "def0",
             "device_class": "00", "observed_monotonic_ns": base + 3},
            {"node": "usb1", "id_vendor": "1d6b", "id_product": "0002",
             "device_class": "09", "observed_monotonic_ns": base + 4},
        ],
        "proc_stat": {
            "cpu_jiffies_first_eight": [100 + offset] * 8,
            "context_switches": 1000 + offset,
            "procs_running": 2, "procs_blocked": 0,
            "clock_ticks_per_second": 100,
            "observed_monotonic_ns": base + 10,
        },
    }
    return (json.dumps(result) + "\n").encode()


def counter_files() -> dict[str, bytes]:
    rows, status = counter_fixtures.fixture(rounds=2)
    post_csv, post_status = counter_fixtures.serialize(rows, status)
    pre_status = dict(status)
    pre_status.update(post_state="unused", post_reference_cpu=-1, post_rounds=0,
                      post_attempted=0, post_completed=0, post_error=0,
                      post_metadata_completed=0, post_start_tick="", post_end_tick="",
                      post_start_online_mask="0x0", post_end_online_mask="0x0")
    for cpu in range(8):
        for field in publisher.counter_decoder.META_FIELDS:
            pre_status[f"post_cpu{cpu}_{field}"] = {
                "actual": -1, "error": 0, "valid": 0,
            }.get(field, "")
    pre_csv, pre_status_text = counter_fixtures.serialize(
        [row for row in rows if row["phase"] == "pre"], pre_status)
    pre = publisher.counter_decoder.analyze_text(
        pre_csv, pre_status_text, pairwise_tolerance_ticks=240, endpoint_uncertainty_ticks=4)
    post = publisher.counter_decoder.analyze_text(
        post_csv, post_status, pairwise_tolerance_ticks=240, endpoint_uncertainty_ticks=4)
    assert pre["phases"]["pre"]["acquisition_eligible_for_conditional_model"]
    assert post["shared_pre_post_model"]["both_phases_eligible"]
    return {
        "counter-pre-events.csv": pre_csv.encode(),
        "counter-pre-status.txt": pre_status_text.encode(),
        "counter-pre-analysis.stdout": (json.dumps(pre) + "\n").encode(),
        "counter-events.csv": post_csv.encode(),
        "counter-status.txt": post_status.encode(),
        "counter-analysis.stdout": (json.dumps(post) + "\n").encode(),
    }


def create_packet(packet: Path, mode: str, *, post_stop_wfi: bool = False,
                  near_stop_wfi: bool = False) -> publisher.Identity:
    packet.mkdir(mode=0o700)
    config = b"CONFIG_SYNTHETIC_WFI_PUBLICATION_TEST=y\n"
    collector_source = b"# synthetic private acquisition source for publisher tests\n"
    identity = publisher.Identity(
        release=publisher.WFI_IDENTITY.release,
        config_sha256=digest(config),
        gnu_build_id=publisher.WFI_IDENTITY.gnu_build_id,
        selected_entry=publisher.WFI_IDENTITY.selected_entry,
    )
    if mode in ("wfi_clock", "wfi_mmio"):
        probe_tick = 48_000_100 if post_stop_wfi else 47_999_998 if near_stop_wfi else 1550
        events, status, wfi = wfi_fixtures.pairing_packet(
            [], [(0, 0, 1, probe_tick, probe_tick + 1, 0x80000000)], mode=mode,
            stop=48_000_000)
    elif mode == "baseline":
        events = wfi_fixtures.fixtures.event_csv()
        status = wfi_fixtures.status(mode="records", idle=(0, 0, 0, 0),
                                     wfi=(0, 0, 0, 0), start="0", stop="0", end="0")
        status = status.replace("state=complete\n", "state=ready\n")
        wfi = wfi_fixtures.WFI_HEADER
    elif mode == "records":
        events = wfi_fixtures.events()
        status = wfi_fixtures.status(mode=mode, wfi=(0, 0, 0, 0),
                                     start="0", stop="48000000", end="48001000")
        wfi = wfi_fixtures.WFI_HEADER
    else:
        events = wfi_fixtures.fixtures.event_csv()
        status = wfi_fixtures.status(mode=mode, idle=(0, 0, 0, 0),
                                     wfi=(0, 0, 0, 0),
                                     start="0", stop="48000000", end="48001000")
        wfi = wfi_fixtures.WFI_HEADER
    observer = None if mode == "baseline" else analyze_wfi.analyze_text(events, status, wfi)
    assert observer is None or observer["integrity"]["clean"]
    records = [
        {"action": "begin", "mode": mode, "observer_abi": 2, "duration_ms": 2000,
         "release": identity.release, "expected_release": identity.release,
         "expected_config_sha256": identity.config_sha256,
         "expected_build_id": identity.gnu_build_id,
         "expected_entry": identity.selected_entry,
         "workload_sha256": publisher.WORKLOAD_SHA256,
         "collector_sha256": digest(collector_source)},
        {"action": "counter_pre_begin"}, {"action": "counter_pre_end"},
        {"action": "settling_begin", "seconds": 5}, {"action": "settling_end"},
        {"action": "window_begin"}, {"action": "window_end"},
        {"action": "observer_drained"},
        {"action": "workload_complete", "cpu": 1, "exit_status": 0},
        {"action": "workload_complete", "cpu": 5, "exit_status": 0},
        {"action": "counter_post_begin"}, {"action": "counter_post_end"},
        {"action": "complete", "native_packet_requires_review": True,
         "clock_bound_not_exported": True},
    ]
    ticks = [1, 1000, 2000, 3000, 5_000_000_300, 6_000_000_000,
             8_050_000_000, 8_050_100_000, 8_100_000_000, 8_100_100_000,
             8_200_000_000, 8_200_100_000, 8_300_000_000]
    for index, row in enumerate(records):
        row["utc"] = f"2026-10-02T16:00:{index:02d}+00:00"
        row["monotonic_ns"] = ticks[index]
    note = struct.pack("<III", 4, 20, 3) + b"GNU\0" + bytes.fromhex(identity.gnu_build_id)
    files = {
        "events.csv": events.encode(), "status.txt": status.encode(),
        "wfi-events.csv": wfi.encode(),
        "acquisition-record.json": (json.dumps(records) + "\n").encode(),
        "apsc-ready.txt": (b"abi=2\nstate=ready\ncluster0_cpus=0xf\ncluster1_cpus=0xf0\n"
                           b"cluster0_cmd_phys=0x210e20020\ncluster1_cmd_phys=0x211e20020\n"),
        "counter-ready.txt": (b"abi=1\npre_state=unused\npost_state=unused\n"
                              b"cluster0_cpus=0xf\ncluster1_cpus=0xf0\n"),
        "boot-kernel-notes.bin": note,
        "boot-config.gz": gzip.compress(config), "boot.config": config,
        "bootctl.stdout": ("  Current Entry: " + identity.selected_entry + "\n").encode(),
        "boot-id.txt": b"11111111-1111-4111-8111-111111111111\n",
        "boot-fdt.bin": b"SYNTHETIC-PRIVATE-FDT-SERIAL",
        "boot-cmdline.txt": b"root=UUID=PRIVATE-TEST-VALUE\n",
        "virtualization.stdout": b"none\n",
        "collector-source.py": collector_source,
        "before-snapshot.json": snapshot(100),
        "after-snapshot.json": snapshot(8_250_000_000),
        "environment-observation-before.json": environment_observation(True),
        "environment-observation-after.json": environment_observation(False),
        "workload-cpu1.csv": workload(1), "workload-cpu5.csv": workload(5),
        **counter_files(),
    }
    if observer is not None:
        files["observer-analysis.stdout"] = (json.dumps(observer) + "\n").encode()
    for name, contents in files.items():
        (packet / name).write_bytes(contents)
    refresh_manifest(packet)
    return identity


def refresh_manifest(packet: Path) -> None:
    lines = [f"{digest(path.read_bytes())}  {path.name}"
             for path in sorted(packet.iterdir()) if path.name != "SHA256SUMS"]
    (packet / "SHA256SUMS").write_text("\n".join(lines) + "\n")


def write_qualification(packet: Path, identity: publisher.Identity) -> Path:
    topology = {
        "validated_against_same_boot_fdt": True,
        "model": "Apple MacBook Air (M1, 2020)",
        "compatible": ["apple,j313", "apple,t8103", "apple,arm-platform"],
        "cpu_count": 8,
        "clusters": {
            "0": {"logical_cpus": [0, 1, 2, 3], "performance_domain_phandle": "0xa",
                  "controller_base": "0x210e20000", "controller_bytes": 4096,
                  "command_address": "0x210e20020"},
            "1": {"logical_cpus": [4, 5, 6, 7], "performance_domain_phandle": "0xd",
                  "controller_base": "0x211e20000", "controller_bytes": 4096,
                  "command_address": "0x211e20020"},
        },
    }
    qualification = {
        "schema": 1, "qualified_utc": "2026-10-02T15:59:59+00:00",
        "qualified_monotonic_ns": 1,
        "boot_id": "11111111-1111-4111-8111-111111111111",
        "release": identity.release, "gnu_build_id": identity.gnu_build_id,
        "configuration_sha256": identity.config_sha256,
        "selected_entry": identity.selected_entry,
        "fdt_same_boot_checked": True,
        "fdt_topology": topology,
        "fdt_topology_projection_sha256": publisher.sha256(
            json.dumps(topology, sort_keys=True, separators=(",", ":")).encode()),
        "native": True, "online_cpus": "0-7", "cpuidle_driver": "apple_idle",
        "cpuidle_governor": "menu", "all_deep_idle_states_enabled": True,
        "charger_connected": True,
        "observer_abi": 2, "observer_ready": True,
        "counter_abi": 1, "counter_unused": True,
        "module_package_integrity_clean": True,
    }
    path = packet.parent / (packet.name + "-qualification.json")
    path.write_text(json.dumps(qualification))
    path.chmod(0o600)
    return path


def write_device_acceptance(packet: Path, identity: publisher.Identity) -> Path:
    acceptance = {
        "schema": 1, "accepted_utc": "2026-10-02T15:59:59+00:00",
        "accepted_monotonic_ns": 1,
        "boot_id": "11111111-1111-4111-8111-111111111111",
        "release": identity.release, "gnu_build_id": identity.gnu_build_id,
        "selected_entry": identity.selected_entry,
        "charger_connected": True,
        "wifi": {"interface": "wlan0", "driver": "brcmfmac",
                 "functional": True, "user_confirmed": True},
        "brightness": {"provider": "apple-panel-bl", "driver": "apple-dcp",
                       "functional": True, "user_confirmed": True,
                       "changed_to": 140, "restored_to": 155,
                       "restoration_user_confirmed": True},
    }
    path = packet.parent / (packet.name + "-device-acceptance.json")
    path.write_text(json.dumps(acceptance))
    path.chmod(0o600)
    return path


class PublishWfiEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.packet = self.root / "private-packet"
        self.out = self.root / "evidence"
        self.receipt = self.root / "receipt.json"
        self.identity = create_packet(self.packet, "wfi_clock")
        self.qualification = write_qualification(self.packet, self.identity)
        self.device_acceptance = write_device_acceptance(self.packet, self.identity)
        chain_patcher = mock.patch.object(publisher, "checked_build_chain",
                                          return_value={"synthetic_fixture": True})
        chain_patcher.start()
        self.addCleanup(chain_patcher.stop)

    def test_clock_pilot_receipt_and_only_numeric_public_files(self):
        result = publisher.publish(self.packet, "wfi_clock", self.out, self.receipt,
                                   self.qualification, self.device_acceptance, self.identity)
        self.assertEqual(result["release"], self.identity.release)
        self.assertEqual(result["gnu_build_id"], self.identity.gnu_build_id)
        self.assertEqual(result["selected_entry"], self.identity.selected_entry)
        self.assertEqual(result["mode"], "wfi_clock")
        self.assertTrue(result["integrity_clean"])
        self.assertEqual(result["packet_sha256s_sha256"], digest((self.packet / "SHA256SUMS").read_bytes()))
        self.assertEqual(result["collector_acquisition_sha256"],
                         digest((self.packet / "collector-source.py").read_bytes()))
        self.assertNotEqual(result["collector_acquisition_sha256"],
                            publisher.file_sha256(Path(publisher.__file__).with_name("collect_native.py")))
        self.assertEqual(result["wfi_probe"]["total"], 1)
        self.assertEqual(result["d_pilot_matched_model_interior_probe_count"], 1)
        self.assertTrue(result["boot_qualification"]["fdt_same_boot_checked"])
        self.assertTrue(result["device_acceptance"]["wifi_user_confirmed"])
        expected_public = {name + ".gz" if name.endswith(".csv") else name
                           for name in publisher.NUMERIC_FILES}
        expected_public |= {"chronology.json", "environment-before.json", "environment-after.json",
                            "activity-summary.json"}
        self.assertEqual({path.name for path in self.out.iterdir()}, expected_public)
        self.assertEqual(gzip.decompress((self.out / "wfi-events.csv.gz").read_bytes()),
                         (self.packet / "wfi-events.csv").read_bytes())
        public_bytes = self.receipt.read_bytes() + b"".join(path.read_bytes() for path in self.out.iterdir())
        for private in (b"PRIVATE-TEST-VALUE", b"PRIVATE-FDT-SERIAL", b"00:11:22:33:44:55",
                        b"11111111-1111-4111-8111-111111111111", str(self.packet).encode(),
                        str(self.qualification).encode(), str(self.device_acceptance).encode(),
                        b"/sys/class/net/wlan0/address"):
            self.assertNotIn(private, public_bytes)
        self.assertEqual(result["conditions"]["charger_online"], 1)
        self.assertEqual(result["conditions"]["brightness"], 155)
        activity = result["activity_summary"]
        self.assertTrue(activity["usb"]["vendor_product_class_multiset_equal"])
        self.assertEqual(activity["network"]["wlan0_traffic_delta"]["rx_bytes"], 500)
        self.assertEqual(activity["aggregate_cpu"]["cpu_total_jiffies_delta"], 4000)
        self.assertEqual(activity, json.loads((self.out / "activity-summary.json").read_text()))
        self.assertNotIn("abcd", json.dumps(activity))
        self.assertNotIn("wlan0", json.dumps(activity.get("usb")))
        self.assertEqual(json.loads((self.out / "environment-before.json").read_text())[0]["field"],
                         "cpu.online")

    def test_mmio_packet_can_be_published_without_clock_pilot_fields_changing(self):
        second = self.root / "private-mmio"
        identity = create_packet(second, "wfi_mmio")
        qualification = write_qualification(second, identity)
        acceptance = write_device_acceptance(second, identity)
        result = publisher.publish(second, "wfi_mmio", self.out, self.receipt,
                                   qualification, acceptance, identity)
        self.assertTrue(result["integrity_clean"])
        self.assertEqual(result["wfi_probe"]["in_window_by_cluster"]["0"]["busy_bit31"], 1)
        self.assertEqual(result["paired_opportunity_status"], "conditional_software_screen")

    def test_abi2_same_image_controls_have_mode_specific_integrity(self):
        for mode in ("baseline", "records", "mmio"):
            with self.subTest(mode=mode):
                packet = self.root / ("private-" + mode)
                identity = create_packet(packet, mode)
                qualification = write_qualification(packet, identity)
                acceptance = write_device_acceptance(packet, identity)
                out = self.root / ("evidence-" + mode)
                receipt = self.root / ("receipt-" + mode + ".json")
                result = publisher.publish(packet, mode, out, receipt,
                                           qualification, acceptance, identity)
                self.assertEqual(result["mode"], mode)
                self.assertTrue(result["integrity_clean"])
                self.assertEqual(result["wfi_probe"]["total"], 0)
                self.assertEqual(result["observer_analysis_private_sha256"] is None, mode == "baseline")
                self.assertGreater(len(result["worker_pulses_fully_inside_external_window_by_cpu"]["1"]), 0)

    def test_unarmed_baseline_rejects_unexpected_observer_analysis(self):
        packet = self.root / "private-baseline-with-extra-analysis"
        identity = create_packet(packet, "baseline")
        (packet / "observer-analysis.stdout").write_text("{}\n")
        refresh_manifest(packet)
        qualification = write_qualification(packet, identity)
        acceptance = write_device_acceptance(packet, identity)
        with self.assertRaisesRegex(publisher.PublicationError, "unexpected observer analysis"):
            publisher.publish(packet, "baseline", self.out, self.receipt,
                              qualification, acceptance, identity)

    def test_repository_build_chain_matches_pinned_identity(self):
        chain = REAL_BUILD_CHAIN(publisher.WFI_IDENTITY)
        self.assertEqual(chain["aurora_source_commit"], "90a95335a49aec3a0045a76da140452ad6585eb3")
        self.assertEqual(chain["wfi_patch_file_sha256_at_publication"],
                         publisher.file_sha256(Path(publisher.__file__).with_name(
                             "0004-aurora-apsc-wfi-first-attempt.patch")))
        self.assertFalse(chain["build_time_wfi_patch_or_source_digest_recorded"])
        self.assertIn("does not cryptographically bind", chain["wfi_patch_hash_scope"])
        self.assertNotIn("wfi_patch_sha256", chain)
        self.assertEqual(chain["uki_sha256_at_deployment_readback"],
                         "4868e3547c1eafe884520238da801684069d547ffe2dc5915666b42d3ad66ce7")

    def test_same_boot_qualification_rejects_other_boot_id(self):
        qualification = json.loads(self.qualification.read_text())
        qualification["boot_id"] = "22222222-2222-4222-8222-222222222222"
        self.qualification.write_text(json.dumps(qualification))
        with self.assertRaisesRegex(publisher.PublicationError, "boot identity differ"):
            publisher.publish(self.packet, "wfi_clock", self.out, self.receipt,
                              self.qualification, self.device_acceptance, self.identity)
        self.assertFalse(self.receipt.exists())

    def test_same_boot_qualification_rejects_changed_topology_projection(self):
        qualification = json.loads(self.qualification.read_text())
        qualification["fdt_topology"]["clusters"]["0"]["command_address"] = "0x210e20024"
        qualification["fdt_topology_projection_sha256"] = publisher.sha256(
            json.dumps(qualification["fdt_topology"], sort_keys=True, separators=(",", ":")).encode())
        self.qualification.write_text(json.dumps(qualification))
        with self.assertRaisesRegex(publisher.PublicationError, "topology differs"):
            publisher.publish(self.packet, "wfi_clock", self.out, self.receipt,
                              self.qualification, self.device_acceptance, self.identity)

    def test_same_boot_qualification_must_precede_capture(self):
        qualification = json.loads(self.qualification.read_text())
        qualification["qualified_monotonic_ns"] = 2
        self.qualification.write_text(json.dumps(qualification))
        with self.assertRaisesRegex(publisher.PublicationError, "before acquisition"):
            publisher.publish(self.packet, "wfi_clock", self.out, self.receipt,
                              self.qualification, self.device_acceptance, self.identity)

    def test_device_acceptance_requires_same_boot_and_pre_capture_confirmation(self):
        acceptance = json.loads(self.device_acceptance.read_text())
        acceptance["boot_id"] = "22222222-2222-4222-8222-222222222222"
        self.device_acceptance.write_text(json.dumps(acceptance))
        with self.assertRaisesRegex(publisher.PublicationError, "device acceptance and capture boot"):
            publisher.publish(self.packet, "wfi_clock", self.out, self.receipt,
                              self.qualification, self.device_acceptance, self.identity)
        acceptance["boot_id"] = "11111111-1111-4111-8111-111111111111"
        acceptance["accepted_monotonic_ns"] = 2
        self.device_acceptance.write_text(json.dumps(acceptance))
        with self.assertRaisesRegex(publisher.PublicationError, "before acquisition"):
            publisher.publish(self.packet, "wfi_clock", self.out, self.receipt,
                              self.qualification, self.device_acceptance, self.identity)

    def test_device_acceptance_requires_user_confirmed_brightness_restoration(self):
        acceptance = json.loads(self.device_acceptance.read_text())
        acceptance["brightness"]["restoration_user_confirmed"] = False
        self.device_acceptance.write_text(json.dumps(acceptance))
        with self.assertRaisesRegex(publisher.PublicationError, "brightness adjustment and restoration"):
            publisher.publish(self.packet, "wfi_clock", self.out, self.receipt,
                              self.qualification, self.device_acceptance, self.identity)

    def test_workload_chronology_cannot_leak_injected_boot_uuid(self):
        records = json.loads((self.packet / "acquisition-record.json").read_text())
        next(row for row in records if row["action"] == "workload_complete")["mode"] = (
            "11111111-1111-4111-8111-111111111111")
        (self.packet / "acquisition-record.json").write_text(json.dumps(records))
        refresh_manifest(self.packet)
        with self.assertRaisesRegex(publisher.PublicationError, "unexpected workload chronology field"):
            publisher.publish(self.packet, "wfi_clock", self.out, self.receipt,
                              self.qualification, self.device_acceptance, self.identity)
        self.assertFalse(self.out.exists())
        self.assertFalse(self.receipt.exists())

    def test_after_stop_only_clock_probe_cannot_qualify_d_pilot(self):
        packet = self.root / "private-after-stop-only-clock"
        identity = create_packet(packet, "wfi_clock", post_stop_wfi=True)
        qualification = write_qualification(packet, identity)
        acceptance = write_device_acceptance(packet, identity)
        with self.assertRaisesRegex(publisher.PublicationError, "matched model-interior"):
            publisher.publish(packet, "wfi_clock", self.out, self.receipt,
                              qualification, acceptance, identity)

    def test_raw_in_window_near_stop_clock_probe_cannot_qualify_d_pilot(self):
        packet = self.root / "private-near-stop-clock"
        identity = create_packet(packet, "wfi_clock", near_stop_wfi=True)
        qualification = write_qualification(packet, identity)
        acceptance = write_device_acceptance(packet, identity)
        raw = analyze_wfi.analyze_text((packet / "events.csv").read_text(),
                                       (packet / "status.txt").read_text(),
                                       (packet / "wfi-events.csv").read_text())
        self.assertEqual(raw["wfi_probe"]["in_window"], 1)
        with self.assertRaisesRegex(publisher.PublicationError, "matched model-interior"):
            publisher.publish(packet, "wfi_clock", self.out, self.receipt,
                              qualification, acceptance, identity)

    def test_connected_charger_required_in_capture_not_only_preflight(self):
        for name in ("before-snapshot.json", "after-snapshot.json"):
            rows = json.loads((self.packet / name).read_text())
            next(row for row in rows if row["path"].endswith("macsmc-ac/online"))["raw_text"] = "0\n"
            (self.packet / name).write_text(json.dumps(rows))
        refresh_manifest(self.packet)
        with self.assertRaisesRegex(publisher.PublicationError, "connected-charger baseline"):
            publisher.publish(self.packet, "wfi_clock", self.out, self.receipt,
                              self.qualification, self.device_acceptance, self.identity)

    def test_condition_change_rejects_clean_publication(self):
        rows = json.loads((self.packet / "after-snapshot.json").read_text())
        next(row for row in rows if row["path"].endswith("apple-panel-bl/brightness"))["raw_text"] = "99\n"
        (self.packet / "after-snapshot.json").write_text(json.dumps(rows))
        refresh_manifest(self.packet)
        with self.assertRaisesRegex(publisher.PublicationError, "brightness-155 baseline"):
            publisher.publish(self.packet, "wfi_clock", self.out, self.receipt, self.qualification, self.device_acceptance, self.identity)

    def test_matching_nonbaseline_brightness_endpoints_still_reject(self):
        for name in ("before-snapshot.json", "after-snapshot.json"):
            rows = json.loads((self.packet / name).read_text())
            next(row for row in rows if row["path"].endswith("apple-panel-bl/brightness"))["raw_text"] = "99\n"
            (self.packet / name).write_text(json.dumps(rows))
        refresh_manifest(self.packet)
        with self.assertRaisesRegex(publisher.PublicationError, "brightness-155 baseline"):
            publisher.publish(self.packet, "wfi_clock", self.out, self.receipt,
                              self.qualification, self.device_acceptance, self.identity)

    def test_acquisition_collector_hash_mismatch_rejects(self):
        records = json.loads((self.packet / "acquisition-record.json").read_text())
        records[0]["collector_sha256"] = "0" * 64
        (self.packet / "acquisition-record.json").write_text(json.dumps(records))
        refresh_manifest(self.packet)
        with self.assertRaisesRegex(publisher.PublicationError, "collector source hash"):
            publisher.publish(self.packet, "wfi_clock", self.out, self.receipt, self.qualification, self.device_acceptance, self.identity)

    def test_actual_window_duration_mismatch_rejects(self):
        records = json.loads((self.packet / "acquisition-record.json").read_text())
        next(row for row in records if row["action"] == "window_end")["monotonic_ns"] = 6_500_000_000
        (self.packet / "acquisition-record.json").write_text(json.dumps(records))
        refresh_manifest(self.packet)
        with self.assertRaisesRegex(publisher.PublicationError, "actual capture window"):
            publisher.publish(self.packet, "wfi_clock", self.out, self.receipt, self.qualification, self.device_acceptance, self.identity)

    def test_missing_completion_rejects_before_writing(self):
        records = json.loads((self.packet / "acquisition-record.json").read_text())
        records[-1]["action"] = "failed"
        (self.packet / "acquisition-record.json").write_text(json.dumps(records))
        refresh_manifest(self.packet)
        with self.assertRaisesRegex(publisher.PublicationError, "did not complete"):
            publisher.publish(self.packet, "wfi_clock", self.out, self.receipt, self.qualification, self.device_acceptance, self.identity)
        self.assertFalse(self.out.exists())
        self.assertFalse(self.receipt.exists())

    def test_wrong_build_identity_rejects_even_with_fresh_manifest(self):
        records = json.loads((self.packet / "acquisition-record.json").read_text())
        records[0]["expected_build_id"] = "0" * 40
        (self.packet / "acquisition-record.json").write_text(json.dumps(records))
        refresh_manifest(self.packet)
        with self.assertRaisesRegex(publisher.PublicationError, "identity"):
            publisher.publish(self.packet, "wfi_clock", self.out, self.receipt, self.qualification, self.device_acceptance, self.identity)

    def test_hash_mismatch_rejects(self):
        (self.packet / "wfi-events.csv").write_text("changed\n")
        with self.assertRaisesRegex(publisher.PublicationError, "SHA256SUMS mismatch"):
            publisher.publish(self.packet, "wfi_clock", self.out, self.receipt, self.qualification, self.device_acceptance, self.identity)

    def test_stored_analyzer_mismatch_rejects_even_with_fresh_manifest(self):
        stored = json.loads((self.packet / "observer-analysis.stdout").read_text())
        stored["integrity"]["clean"] = False
        (self.packet / "observer-analysis.stdout").write_text(json.dumps(stored))
        refresh_manifest(self.packet)
        with self.assertRaisesRegex(publisher.PublicationError, "analyzer output"):
            publisher.publish(self.packet, "wfi_clock", self.out, self.receipt, self.qualification, self.device_acceptance, self.identity)

    def test_private_looking_numeric_content_rejects(self):
        (self.packet / "workload-cpu1.csv").write_bytes(
            (self.packet / "workload-cpu1.csv").read_bytes() + b"/home/private\n")
        refresh_manifest(self.packet)
        with self.assertRaisesRegex(publisher.PublicationError, "workload"):
            publisher.publish(self.packet, "wfi_clock", self.out, self.receipt, self.qualification, self.device_acceptance, self.identity)

    def test_unlisted_file_rejects(self):
        (self.packet / "private-extra").write_text("no")
        with self.assertRaisesRegex(publisher.PublicationError, "unaccounted"):
            publisher.publish(self.packet, "wfi_clock", self.out, self.receipt, self.qualification, self.device_acceptance, self.identity)

    def test_manifest_path_escape_rejects(self):
        with (self.packet / "SHA256SUMS").open("a") as stream:
            stream.write("0" * 64 + "  ../outside\n")
        with self.assertRaisesRegex(publisher.PublicationError, "malformed"):
            publisher.publish(self.packet, "wfi_clock", self.out, self.receipt, self.qualification, self.device_acceptance, self.identity)

    def test_usb_identity_change_is_visible_without_exporting_vid_pid(self):
        path = self.packet / "environment-observation-after.json"
        raw = json.loads(path.read_text())
        raw["usb_devices"][0]["id_product"] = "f001"
        path.write_text(json.dumps(raw))
        refresh_manifest(self.packet)
        result = publisher.publish(self.packet, "wfi_clock", self.out, self.receipt,
                                   self.qualification, self.device_acceptance, self.identity)
        self.assertFalse(result["activity_summary"]["usb"]["vendor_product_class_multiset_equal"])
        public = (self.out / "activity-summary.json").read_text()
        self.assertNotIn("f001", public)
        self.assertNotIn("abcd", public)

    def test_usb_serial_in_private_observation_rejected(self):
        path = self.packet / "environment-observation-before.json"
        raw = json.loads(path.read_text())
        raw["usb_devices"][0]["serial"] = "should-never-be-collected"
        path.write_text(json.dumps(raw))
        refresh_manifest(self.packet)
        with self.assertRaisesRegex(publisher.PublicationError, "USB observation fields differ"):
            publisher.publish(self.packet, "wfi_clock", self.out, self.receipt,
                              self.qualification, self.device_acceptance, self.identity)

    def test_environment_capture_time_must_bracket_window(self):
        path = self.packet / "environment-observation-before.json"
        raw = json.loads(path.read_text())
        raw["observed_monotonic_ns_begin"] = 6_100_000_000
        raw["observed_monotonic_ns_end"] = 6_100_000_100
        for row in raw["network"] + raw["usb_devices"]:
            row["observed_monotonic_ns"] = 6_100_000_050
        raw["proc_stat"]["observed_monotonic_ns"] = 6_100_000_100
        path.write_text(json.dumps(raw))
        refresh_manifest(self.packet)
        with self.assertRaisesRegex(publisher.PublicationError, "do not bracket the capture"):
            publisher.publish(self.packet, "wfi_clock", self.out, self.receipt,
                              self.qualification, self.device_acceptance, self.identity)

    def test_read_only_collector_observation_never_reads_usb_serial(self):
        net = self.root / "fake-net"
        usb = self.root / "fake-usb"
        proc = self.root / "fake-proc-stat"
        wlan = net / "wlan0"
        (wlan / "statistics").mkdir(parents=True)
        for name, value in {"type": "1", "operstate": "up", "carrier": "1"}.items():
            (wlan / name).write_text(value + "\n")
        for name in ("rx_bytes", "tx_bytes", "rx_packets", "tx_packets"):
            (wlan / "statistics" / name).write_text("2\n")
        device = usb / "1-1"
        device.mkdir(parents=True)
        for name, value in {"idVendor": "abcd", "idProduct": "def0",
                            "bDeviceClass": "00", "serial": "PRIVATE-SERIAL"}.items():
            (device / name).write_text(value + "\n")
        proc.write_text("cpu 1 2 3 4 5 6 7 8 9 10\nctxt 11\nprocs_running 2\nprocs_blocked 0\n")
        raw = collect_native.observe_environment(net, usb, proc)
        self.assertEqual(len(raw["usb_devices"]), 1)
        self.assertNotIn("PRIVATE-SERIAL", json.dumps(raw))


if __name__ == "__main__":
    unittest.main()
