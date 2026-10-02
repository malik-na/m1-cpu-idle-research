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
    def test_control_write_disposition_after_success_exception_and_no_attempt(self):
        class FakePacket:
            def mark(self, action, **fields):
                pass

        packet = FakePacket()
        control = {'state': collector.CONTROL_NOT_ATTEMPTED}
        with patch.object(collector.time, 'monotonic_ns', return_value=1000), \
                patch.object(collector.os, 'open', return_value=99), \
                patch.object(collector.os, 'write', return_value=len(b'wfi_mmio 10000\n')), \
                patch.object(collector.os, 'close'):
            collector.write_capture(packet, 'wfi_mmio 10000\n', 2000, control)
        self.assertEqual(collector.control_disposition(control), {
            'control_write_state': collector.CONTROL_WRITE_COMPLETED,
            'control_write_attempted': True, 'capture_armed': True,
            'one_shot_consumption': 'confirmed'})

        control = {'state': collector.CONTROL_NOT_ATTEMPTED}
        with patch.object(collector.time, 'monotonic_ns', return_value=1000), \
                patch.object(collector.os, 'open', return_value=99), \
                patch.object(collector.os, 'write', side_effect=OSError('consumed')), \
                patch.object(collector.os, 'close'):
            with self.assertRaises(OSError):
                collector.write_capture(packet, 'wfi_mmio 10000\n', 2000, control)
        self.assertEqual(collector.control_disposition(control)['one_shot_consumption'],
                         'unknown')
        self.assertIsNone(collector.control_disposition(control)['capture_armed'])

        control = {'state': collector.CONTROL_NOT_ATTEMPTED}
        with patch.object(collector.time, 'monotonic_ns', return_value=3000), \
                patch.object(collector.os, 'open') as opened:
            with self.assertRaises(collector.CaptureError):
                collector.write_capture(packet, 'wfi_mmio 10000\n', 2000, control)
            opened.assert_not_called()
        self.assertFalse(collector.control_disposition(control)['capture_armed'])

    def test_boot_ledger_rejects_any_prior_packet_on_same_boot(self):
        current_id = '-'.join(('a' * 8, 'a' * 4, 'a' * 4, 'a' * 4, 'a' * 12))
        other_id = '-'.join(('b' * 8, 'b' * 4, 'b' * 4, 'b' * 4, 'b' * 12))
        with tempfile.TemporaryDirectory() as location:
            root = Path(location)
            old = root / 'abi3-A-20261003T000000Z'
            old.mkdir()
            (old / 'boot-id.txt').write_text(other_id + '\n')
            current = root / 'abi3-E-20261003T000200Z'
            current.mkdir()
            (current / 'boot-id.txt').write_text(current_id + '\n')
            with patch.object(collector, 'HERE', root):
                self.assertEqual(len(collector.boot_ledger(current_id, current)), 1)
                (old / 'boot-id.txt').write_text(current_id + '\n')
                with self.assertRaisesRegex(collector.CaptureError,
                                            'already exists for this boot'):
                    collector.boot_ledger(current_id, current)

    def test_boot_qualification_requires_current_user_report(self):
        boot_id = '-'.join(('a' * 8, 'a' * 4, 'a' * 4, 'a' * 4, 'a' * 12))
        identity = {'release': 'test-abi3', 'entry_title': 'Aurora-APSC-research-wfi-abi3'}
        review = {'schema': 'abi3-user-boot-qualification-v1',
                  'boot_id': boot_id, 'release': identity['release'],
                  'entry_title': identity['entry_title'],
                  'source': 'user-confirmed-current-boot',
                  'wifi_page_loaded': True, 'brightness_start': 155,
                  'brightness_test_low': 40, 'brightness_restored': 155,
                  'dim_visible': True, 'restore_visible': True,
                  'confirmed_utc': '2026-10-03T00:00:00Z'}
        with tempfile.TemporaryDirectory() as location:
            path = Path(location) / 'review.json'
            path.write_text(json.dumps(review))
            self.assertEqual(collector.boot_qualification(path, boot_id, identity,
                                                          'A', None)[0], review)
            with self.assertRaises(collector.CaptureError):
                collector.boot_qualification(path,
                    '-'.join(('b' * 8, 'b' * 4, 'b' * 4, 'b' * 4, 'b' * 12)),
                    identity, 'A', None)
            review['dim_visible'] = False
            path.write_text(json.dumps(review))
            with self.assertRaises(collector.CaptureError):
                collector.boot_qualification(path, boot_id, identity, 'A', None)

            later = {'schema': 'abi3-user-current-boot-wifi-v1',
                     'phase': 'D', 'boot_id': boot_id,
                     'release': identity['release'],
                     'entry_title': identity['entry_title'],
                     'source': 'user-confirmed-current-boot',
                     'wifi_page_loaded': True,
                     'first_a_visual_receipt_sha256': 'a' * 64,
                     'confirmed_utc': '2026-10-03T00:00:00Z'}
            path.write_text(json.dumps(later))
            self.assertEqual(collector.boot_qualification(path, boot_id, identity,
                                                          'D', 'a' * 64)[0], later)
            with self.assertRaises(collector.CaptureError):
                collector.boot_qualification(path, boot_id, identity, 'D', 'b' * 64)
            later['brightness_test_low'] = 40
            path.write_text(json.dumps(later))
            with self.assertRaisesRegex(collector.CaptureError, 'schema changed'):
                collector.boot_qualification(path, boot_id, identity, 'D', 'a' * 64)

    def test_first_a_visual_proof_survives_clean_chain_without_retesting(self):
        boot_id = '-'.join(('a' * 8, 'a' * 4, 'a' * 4, 'a' * 4, 'a' * 12))
        a_sha = 'a' * 64
        with tempfile.TemporaryDirectory() as location:
            prior = Path(location)
            (prior / 'boot-id.txt').write_text(boot_id + '\n')
            check = {'phase': 'A', 'current_boot_id': boot_id,
                     'current_boot_wifi_user_confirmed': True,
                     'current_boot_visible_brightness_confirmed': True,
                     'brightness_visible_checked_on_first_abi3_boot': True,
                     'receipt_sha256': a_sha,
                     'first_a_visual_receipt_sha256': a_sha}
            path = prior / 'user-boot-qualification-check.json'
            path.write_text(json.dumps(check))
            self.assertEqual(collector.first_a_visual_proof(
                prior, 'D', {'user-boot-qualification.json': a_sha}), a_sha)
            for incoming, prior_phase in (('E', 'D'), ('C', 'E')):
                check['phase'] = prior_phase
                check['current_boot_visible_brightness_confirmed'] = False
                check['receipt_sha256'] = 'b' * 64
                path.write_text(json.dumps(check))
                self.assertEqual(collector.first_a_visual_proof(
                    prior, incoming, {'user-boot-qualification.json': 'b' * 64}), a_sha)
            check['current_boot_visible_brightness_confirmed'] = True
            path.write_text(json.dumps(check))
            with self.assertRaises(collector.CaptureError):
                collector.first_a_visual_proof(
                    prior, 'C', {'user-boot-qualification.json': 'b' * 64})
            check['current_boot_visible_brightness_confirmed'] = False
            check['current_boot_id'] = 'b' * 36
            path.write_text(json.dumps(check))
            with self.assertRaises(collector.CaptureError):
                collector.first_a_visual_proof(
                    prior, 'C', {'user-boot-qualification.json': 'b' * 64})

    def test_backlight_interface_and_requested_readback_gate(self):
        endpoint = {'ac_online': '1', 'backlight_interface_present': True,
                    'brightness': '155'}
        collector.require_power_endpoints(endpoint, 'synthetic')
        for invalid in (dict(endpoint, backlight_interface_present=False),
                        dict(endpoint, brightness='154')):
            with self.assertRaises(collector.CaptureError):
                collector.require_power_endpoints(invalid, 'synthetic')

    def test_c_review_binds_clean_e_manifest_and_both_cluster_rationales(self):
        with tempfile.TemporaryDirectory() as location:
            prior = Path(location) / 'prior'
            prior.mkdir()
            (prior / 'MANIFEST.sha256').write_text('synthetic manifest\n')
            manifest_sha = collector.file_digest(prior / 'MANIFEST.sha256')
            report_sha = 'a' * 64
            summary = {'phase': 'E', 'abi3_validator_summary': {
                'candidate_count': 0, 'report_sha256': report_sha}}
            item = {'potential_primary_opportunities': 20,
                    'exposure_basis': 'Twenty reviewed primary opportunities.',
                    'why_control_needed': 'Check command read sensitivity on this cluster.'}
            review = {'schema': 'abi3-c-control-review-v1', 'decision': 'run_c',
                      'e_manifest_sha256': manifest_sha, 'e_report_sha256': report_sha,
                      'e_candidate_count': 0, 'per_cluster': {'0': item, '1': dict(item)},
                      'control_purpose': 'comparable-lag-command-read-sensitivity',
                      'reviewed_utc': '2026-10-03T00:00:00Z'}
            path = Path(location) / 'review.json'
            path.write_text(json.dumps(review))
            entries = {'abi3-validator-report.json': report_sha}
            self.assertEqual(collector.c_review(path, prior, summary, entries)[0], review)
            review['per_cluster']['1']['potential_primary_opportunities'] = 19
            path.write_text(json.dumps(review))
            with self.assertRaises(collector.CaptureError):
                collector.c_review(path, prior, summary, entries)
            review['per_cluster']['1']['potential_primary_opportunities'] = 20
            review['e_report_sha256'] = 'b' * 64
            path.write_text(json.dumps(review))
            with self.assertRaises(collector.CaptureError):
                collector.c_review(path, prior, summary, entries)

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
            control = {'state': collector.CONTROL_NOT_ATTEMPTED}
            def successful_control_write(*args):
                control['state'] = collector.CONTROL_WRITE_COMPLETED
            with patch.object(collector.subprocess, 'Popen', side_effect=children), \
                    patch.object(collector.time, 'sleep'), \
                    patch.object(collector, 'wait_until_arm', return_value=1_150_000_000), \
                    patch.object(collector, 'power_endpoints', return_value={
                        'ac_online': '1', 'backlight_interface_present': True,
                        'brightness': '155'}), \
                    patch.object(collector, 'write_capture', side_effect=successful_control_write), \
                    patch.object(collector, 'check_aux_unused'), \
                    patch.object(collector, 'raw_after',
                                 return_value=((status_bytes, b'', b'', b'pcpm', b'counter'), [])):
                with self.assertRaisesRegex(collector.CaptureError, 'idle0'):
                    collector.run_capture(packet, {}, 'E', {}, control=control)
            self.assertEqual([child.inputs for child in children], [[b'E'], [b'E']])
            self.assertEqual(packet.saved['workload-cpu1.csv'], b'worker-output')
            self.assertEqual(packet.saved['workload-cpu5.csv'], b'worker-output')
            self.assertEqual(collector.control_disposition(control)['capture_armed'], True)

        # The debugfs write can consume the one-shot and still return an error.
        # Preserve both worker streams before reporting that failure.
        children = [FakeChild(), FakeChild()]
        with tempfile.TemporaryDirectory() as location:
            packet = FakePacket(Path(location))
            control = {'state': collector.CONTROL_NOT_ATTEMPTED}
            def consumed_then_failed(*args):
                control['state'] = collector.CONTROL_WRITE_UNKNOWN
                raise OSError('consumed then failed')
            with patch.object(collector.subprocess, 'Popen', side_effect=children), \
                    patch.object(collector, 'wait_until_arm', return_value=1_150_000_000), \
                    patch.object(collector, 'power_endpoints', return_value={
                        'ac_online': '1', 'backlight_interface_present': True,
                        'brightness': '155'}), \
                    patch.object(collector, 'write_capture', side_effect=consumed_then_failed), \
                    patch.object(collector, 'check_aux_unused'), \
                    patch.object(collector, 'raw_after',
                                 return_value=((status_bytes, b'', b'', b'pcpm', b'counter'), [])):
                with self.assertRaisesRegex(collector.CaptureError, 'capture write failed'):
                    collector.run_capture(packet, {}, 'E', {}, control=control)
            self.assertEqual([child.inputs for child in children], [[b'E'], [b'E']])
            self.assertEqual(packet.saved['workload-cpu1.csv'], b'worker-output')
            self.assertEqual(packet.saved['workload-cpu5.csv'], b'worker-output')
            self.assertIsNone(collector.control_disposition(control)['capture_armed'])

    def test_prearm_failure_preserves_both_worker_streams(self):
        class FakeChild:
            def __init__(self, cpu):
                self.cpu = cpu
                self.returncode = None
                self.received = []

            def poll(self):
                return self.returncode

            def communicate(self, token=None, timeout=None):
                self.received.append(token)
                self.returncode = 0
                return f'cpu{self.cpu}-rows'.encode(), f'cpu{self.cpu}-stderr'.encode()

        class FakePacket:
            owner = SimpleNamespace(pw_uid=1000, pw_gid=1000)

            def __init__(self):
                self.saved = {}

            def json(self, name, value):
                self.saved[name] = value

            def save(self, name, data):
                self.saved[name] = data

            def mark(self, action, **fields):
                pass

        children = [FakeChild(1), FakeChild(5)]
        packet = FakePacket()
        control = {'state': collector.CONTROL_NOT_ATTEMPTED}
        with patch.object(collector.subprocess, 'Popen', side_effect=children), \
                patch.object(collector, 'wait_until_arm',
                             side_effect=collector.CaptureError('pre-arm timing failed')):
            with self.assertRaisesRegex(collector.CaptureError, 'pre-arm timing failed'):
                collector.run_capture(packet, {}, 'E', {}, control=control)
        self.assertEqual([child.received for child in children], [[b'E'], [b'E']])
        self.assertEqual(packet.saved['workload-cpu1.csv'], b'cpu1-rows')
        self.assertEqual(packet.saved['workload-cpu5.stderr'], b'cpu5-stderr')
        self.assertEqual(collector.control_disposition(control)['one_shot_consumption'],
                         'none')


if __name__ == '__main__':
    unittest.main()
