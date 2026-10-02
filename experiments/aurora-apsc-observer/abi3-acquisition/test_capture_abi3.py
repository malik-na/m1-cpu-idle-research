#!/usr/bin/env python3
"""Synthetic safety tests; none can open debugfs or arm the observer."""

import csv
import hashlib
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import capture_abi3 as collector


def workload(rows=200, wrong=None):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(collector.WORKLOAD_FIELDS)
    for pulse in range(rows):
        start = 1_000_000_000 + pulse * collector.PERIOD_NS + 1_000_000
        end = start + 2_000_000
        if wrong == ('late', pulse):
            start += collector.PERIOD_NS
        if wrong == ('overlap', pulse):
            end += collector.PERIOD_NS
        if wrong == ('iterations', pulse):
            iterations = 12
        else:
            iterations = collector.ITERATIONS
        writer.writerow([1, pulse, iterations, start, end, pulse])
    return output.getvalue().encode()


def status(mode='wfi_mmio'):
    record = {'abi': '3', 'state': 'complete', 'mode': mode, 'interrupted': '0',
              'wfi_pending_after_drain': '0', 'wfi_prepare_after_stop': '0',
              'wfi_prepare_bad_mapping': '0', 'inside_start_ns': '1200000000',
              'inside_stop_ns': '10900000000', 'start_online_mask': '0xff',
              'end_online_mask': '0xff'}
    for kind, indexes in (('idle', range(8)), ('wfi', range(8)), ('dvfs', range(2))):
        for index in indexes:
            name = f'{kind}{index}'
            record[name + '_attempts'] = '0'
            record[name + '_committed'] = '0'
            record[name + '_overflow'] = '0'
            record[name + '_missing_commit'] = '0'
    return record


class CollectorTests(unittest.TestCase):
    def test_complete_workload_and_strict_interior(self):
        result = collector.validate_workload_csv(workload(), 1, 1_000_000_000,
                                                 (1_200_000_000, 10_900_000_000))
        self.assertEqual(result['pulses'], 200)
        self.assertEqual(result['interior_pulses'], 194)
        self.assertEqual(len(result['checksum_sequence_sha256']), 64)

    def test_pulse_checksums_match_both_cpus_and_prior_phase(self):
        value = {'checksum_sequence_sha256': 'a' * 64}
        current = {'1': value, '5': dict(value)}
        self.assertEqual(collector.check_workload_checksums(current, None), 'a' * 64)
        self.assertEqual(collector.check_workload_checksums(current, current), 'a' * 64)
        with self.assertRaises(collector.CaptureError):
            collector.check_workload_checksums({'1': value,
                                                '5': {'checksum_sequence_sha256': 'b' * 64}}, None)
        with self.assertRaises(collector.CaptureError):
            collector.check_workload_checksums(current,
                                               {'1': value,
                                                '5': {'checksum_sequence_sha256': 'b' * 64}})

    def test_workload_rejects_missing_late_overlap_and_wrong_work(self):
        for payload in (workload(199), workload(wrong=('late', 20)),
                        workload(wrong=('overlap', 20)),
                        workload(wrong=('iterations', 20))):
            with self.subTest(payload=hashlib.sha256(payload).hexdigest()), \
                    self.assertRaises(collector.CaptureError):
                collector.validate_workload_csv(payload, 1, 1_000_000_000,
                                                (1_200_000_000, 10_900_000_000))

    def test_zero_loss_all_streams_required(self):
        record = status()
        result = collector.check_stream_status(record, 'wfi_mmio')
        self.assertEqual(len(result['stream_committed']), 18)
        for field, changed in (('idle0_overflow', '1'),
                               ('wfi7_missing_commit', '1'),
                               ('dvfs1_attempts', '1'),
                               ('wfi_prepare_after_stop', '1'),
                               ('end_online_mask', '0xfe')):
            invalid = dict(record, **{field: changed})
            with self.subTest(field=field), self.assertRaises(collector.CaptureError):
                collector.check_stream_status(invalid, 'wfi_mmio')

    def test_unarmed_and_aux_controls_must_stay_unused(self):
        ready = status()
        ready['state'] = 'ready'
        ready['idle0_attempts'] = '0'
        collector.check_unarmed_ready(ready,
                                      (collector.EVENT_HEADER + '\n').encode(),
                                      (collector.WFI_HEADER + '\n').encode())
        used = dict(ready, idle0_attempts='1')
        with self.assertRaises(collector.CaptureError):
            collector.check_unarmed_ready(used,
                                          (collector.EVENT_HEADER + '\n').encode(),
                                          (collector.WFI_HEADER + '\n').encode())
        pcpm = b'abi=2\nstate=unused\nmode=none\n'
        counter = b'abi=1\npre_state=unused\npost_state=unused\n'
        collector.check_aux_unused(pcpm, counter)
        with self.assertRaises(collector.CaptureError):
            collector.check_aux_unused(pcpm.replace(b'unused', b'complete'), counter)

    def test_per_cpu_lse_gate_parser(self):
        text = b'processor : 0\nFeatures : fp atomics\n\nprocessor : 1\nFeatures : fp\n'
        self.assertEqual(collector.cpu_features(text), {0: {'fp', 'atomics'}, 1: {'fp'}})

    def test_arm_offset_rejects_scheduler_slip_before_capture(self):
        target = 1_000_000_000
        with patch.object(collector.time, 'monotonic_ns',
                          return_value=target + collector.ARM_SLIP_LIMIT_NS + 1):
            with self.assertRaisesRegex(collector.CaptureError, 'arm offset'):
                collector.wait_until_arm(target)

    def test_manifest_detects_tamper(self):
        with tempfile.TemporaryDirectory() as location:
            packet = Path(location)
            (packet / 'raw.txt').write_bytes(b'raw')
            sha = hashlib.sha256(b'raw').hexdigest()
            (packet / 'MANIFEST.sha256').write_text(f'{sha}  raw.txt\n')
            self.assertEqual(collector.verify_manifest(packet), {'raw.txt': sha})
            (packet / 'raw.txt').write_bytes(b'changed')
            with self.assertRaises(collector.CaptureError):
                collector.verify_manifest(packet)

    def test_one_raw_read_failure_does_not_skip_other_exports(self):
        class FakePacket:
            def __init__(self):
                self.names = []

            def capture(self, name, source, maximum):
                self.names.append(name)
                if name == 'apsc-status-after.txt':
                    raise OSError('synthetic status read failure')
                return name.encode()

            def mark(self, action, **fields):
                pass

        packet = FakePacket()
        raw, errors = collector.raw_after(packet)
        self.assertEqual(len(packet.names), 5)
        self.assertIsNone(raw[0])
        self.assertEqual(raw[4], b'counter-status-after.txt')
        self.assertEqual(len(errors), 1)

    def test_receipts_bind_exact_tree_build_and_validator(self):
        with tempfile.TemporaryDirectory() as location:
            root = Path(location)
            source = {'candidate_manifest_tree_sha256': 'a' * 64,
                      'patch_sha256': 'b' * 64, 'scratch_release': 'test-abi3'}
            linked = {'source_receipt_sha256': '', 'candidate_source_tree_sha256': 'a' * 64,
                      'patch_sha256': 'b' * 64, 'config_sha256': 'c' * 64,
                      'release': 'test-abi3', 'vmlinux_build_id': 'd' * 40,
                      'ticket_validator_sha256': 'e' * 64, 'full_build_exit_status': 0,
                      'image_sha256': 'f' * 64,
                      'module_manifest_sha256': '0' * 64,
                      'apple_dtb_manifest_sha256': '1' * 64,
                      'full_build_targets': ['Image', 'modules', 'dtbs'],
                      'linked_clock_branch_skips_only_apsc_load': True,
                      'linked_original_dsb_through_ret_bytes_identical': True}
            source_path = root / 'source.json'
            linked_path = root / 'linked.json'
            source_path.write_text(json.dumps(source))
            linked['source_receipt_sha256'] = collector.file_digest(source_path)
            linked_path.write_text(json.dumps(linked))
            identity = {'source_receipt_path': str(source_path),
                        'linked_receipt_path': str(linked_path),
                        'source_receipt_sha256': linked['source_receipt_sha256'],
                        'source_tree_sha256': 'a' * 64, 'patch_sha256': 'b' * 64,
                        'config_sha256': 'c' * 64, 'release': 'test-abi3',
                        'build_id': 'd' * 40, 'validator_sha256': 'e' * 64,
                        'image_sha256': 'f' * 64,
                        'module_manifest_sha256': '0' * 64,
                        'apple_dtb_manifest_sha256': '1' * 64}
            collector.verify_receipts(identity)
            linked['linked_clock_branch_skips_only_apsc_load'] = False
            linked_path.write_text(json.dumps(linked))
            with self.assertRaises(collector.CaptureError):
                collector.verify_receipts(identity)

    def test_failed_one_shot_releases_and_saves_both_workers(self):
        class FakeChild:
            def __init__(self):
                self.returncode = None
                self.inputs = []

            def poll(self):
                return self.returncode

            def communicate(self, token=None, timeout=None):
                self.inputs.append(token)
                self.returncode = 0
                return b'worker-output', b''

        class FakePacket:
            owner = SimpleNamespace(pw_uid=1000, pw_gid=1000)

            def __init__(self, path):
                self.path = path
                self.saved = {}
                (path / 'pcpm-status-before.txt').write_bytes(b'pcpm')
                (path / 'counter-status-before.txt').write_bytes(b'counter')

            def json(self, name, value):
                self.saved[name] = value

            def save(self, name, data):
                self.saved[name] = data

            def mark(self, action, **fields):
                pass

        children = [FakeChild(), FakeChild()]
        invalid = status()
        invalid['idle0_overflow'] = '1'
        status_bytes = ''.join(f'{key}={value}\n' for key, value in invalid.items()).encode()
        with tempfile.TemporaryDirectory() as location:
            packet = FakePacket(Path(location))
            with patch.object(collector.subprocess, 'Popen', side_effect=children), \
                    patch.object(collector.time, 'sleep'), \
                    patch.object(collector, 'wait_until_arm', return_value=1_150_000_000), \
                    patch.object(collector, 'write_capture'), \
                    patch.object(collector, 'check_aux_unused'), \
                    patch.object(collector, 'raw_after',
                                 return_value=((status_bytes, b'', b'', b'pcpm', b'counter'), [])):
                with self.assertRaisesRegex(collector.CaptureError, 'idle0'):
                    collector.run_capture(packet, {}, 'E', {})
            self.assertEqual([child.inputs for child in children], [[b'E'], [b'E']])
            self.assertEqual(packet.saved['workload-cpu1.csv'], b'worker-output')
            self.assertEqual(packet.saved['workload-cpu5.csv'], b'worker-output')

        # The debugfs write can consume the one-shot and still return an error.
        # Preserve both worker streams before reporting that failure.
        children = [FakeChild(), FakeChild()]
        with tempfile.TemporaryDirectory() as location:
            packet = FakePacket(Path(location))
            with patch.object(collector.subprocess, 'Popen', side_effect=children), \
                    patch.object(collector, 'wait_until_arm', return_value=1_150_000_000), \
                    patch.object(collector, 'write_capture', side_effect=OSError('consumed then failed')), \
                    patch.object(collector, 'check_aux_unused'), \
                    patch.object(collector, 'raw_after',
                                 return_value=((status_bytes, b'', b'', b'pcpm', b'counter'), [])):
                with self.assertRaisesRegex(collector.CaptureError, 'capture write failed'):
                    collector.run_capture(packet, {}, 'E', {})
            self.assertEqual([child.inputs for child in children], [[b'E'], [b'E']])
            self.assertEqual(packet.saved['workload-cpu1.csv'], b'worker-output')
            self.assertEqual(packet.saved['workload-cpu5.csv'], b'worker-output')


if __name__ == '__main__':
    unittest.main()
