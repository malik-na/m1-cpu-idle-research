#!/usr/bin/env python3
"""Private, one-shot ABI 3 A/D/E/C acquisition; never run without --execute.

The packet is deliberately private.  A successful kernel ``state=complete``
does not establish stream integrity; validate_tickets.py must accept the raw
status and both CSV streams before a capture receives a clean classification.
This collector neither installs a kernel nor changes power policy.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import pwd
import re
import stat
import struct
import subprocess
import sys
import time


HERE = Path(__file__).resolve().parent
REPO = Path('/REDACTED/RESEARCH_REPOSITORY')
APSC = Path('/sys/kernel/debug/apple_apsc_observer')
COUNTER = Path('/sys/kernel/debug/apple_counter_qualification')
PCPM = Path('/sys/kernel/debug/t8103_pcpm_sampler')
WORKLOAD_SOURCE = REPO / 'experiments/aurora-apsc-observer/pulse_workload_abi3.c'
WORKLOAD = HERE / 'pulse_workload_abi3'
VALIDATOR = HERE / 'validate_tickets.py'
EXPECTED_WORKLOAD_SOURCE_SHA = 'a9b5dedf8b42c7013ebb87cc3754dce1f80fce293a02911b5e8175d61d4eff73'
EXPECTED_WORKLOAD_SHA = '2b4ed83c6f81be68eeb4e9aa448eb81493852f1bf114edb249f75a1e55234a89'
CPUS = (1, 5)
PULSES = 200
PERIOD_NS = 50_000_000
ITERATIONS = 1_048_576
DURATION_MS = 10_000
ARM_SLIP_LIMIT_NS = 25_000_000
MAX_RAW = 128 * 1024 * 1024
MODES = {'A': 'baseline', 'D': 'wfi_clock', 'E': 'wfi_mmio', 'C': 'mmio'}
PRIOR = {'D': 'A', 'E': 'D', 'C': 'E'}
HEX64 = re.compile(r'[0-9a-f]{64}\Z')
HEX40 = re.compile(r'[0-9a-f]{40}\Z')
WORKLOAD_FIELDS = ['cpu', 'pulse', 'iterations', 'start_monotonic_ns',
                   'end_monotonic_ns', 'checksum']
EVENT_HEADER = ('kind,seq,cpu,cluster,policy_cpu,policy_mask,fast_switch,'
                'requested_index,requested_pstate,token,t0,t1,pre_cmd,cmd,ret,flags,ticket')
WFI_HEADER = 'seq,cpu,cluster,token,t0,t1,cmd,mode,cmd_valid,ticket_pre,ticket_post'


class CaptureError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CaptureError(message)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def read_bounded(path: Path, maximum: int = MAX_RAW) -> bytes:
    require(0 < maximum <= MAX_RAW, 'invalid read bound')
    content = bytearray()
    with path.open('rb') as source:
        while True:
            block = source.read(min(64 * 1024, maximum + 1 - len(content)))
            if not block:
                return bytes(content)
            content.extend(block)
            require(len(content) <= maximum, f'oversized input: {path}')


def status_map(data: bytes) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in data.decode('ascii').splitlines():
        key, marker, value = line.partition('=')
        require(bool(marker and key and key not in result), 'malformed/duplicate status key')
        result[key] = value
    return result


def build_ids(notes: bytes) -> list[str]:
    result = []
    offset = 0
    while offset + 12 <= len(notes):
        namesz, valuesz, kind = struct.unpack_from('<III', notes, offset)
        offset += 12
        require(offset + namesz <= len(notes), 'truncated note name')
        name = notes[offset:offset + namesz]
        offset += (namesz + 3) & ~3
        require(offset + valuesz <= len(notes), 'truncated note value')
        value = notes[offset:offset + valuesz]
        offset += (valuesz + 3) & ~3
        if name == b'GNU\0' and kind == 3:
            result.append(value.hex())
    return result


def cpu_features(cpuinfo: bytes) -> dict[int, set[str]]:
    features = {}
    for section in cpuinfo.decode('ascii').strip().split('\n\n'):
        fields = {}
        for line in section.splitlines():
            key, marker, value = line.partition(':')
            if marker:
                fields[key.strip()] = value.strip()
        if 'processor' in fields:
            cpu = int(fields['processor'])
            require(cpu not in features, 'duplicate /proc/cpuinfo processor')
            features[cpu] = set(fields.get('Features', '').split())
    return features


def validate_workload_csv(data: bytes, cpu: int, scheduled_ns: int,
                          interior: tuple[int, int]) -> dict:
    start_inside, stop_inside = interior
    require(0 < start_inside < stop_inside, 'invalid workload interior markers')
    reader = csv.DictReader(io.StringIO(data.decode('ascii')))
    require(reader.fieldnames == WORKLOAD_FIELDS, f'CPU{cpu}: workload header changed')
    rows = list(reader)
    require(len(rows) == PULSES, f'CPU{cpu}: incomplete pulse block')
    previous_end = 0
    interior_count = 0
    work_ns = 0
    interior_work_ns = 0
    checksums = []
    for pulse, row in enumerate(rows):
        require(None not in row and all(value is not None for value in row.values()),
                f'CPU{cpu} pulse {pulse}: malformed CSV row')
        try:
            identity = tuple(int(row[key]) for key in ('cpu', 'pulse', 'iterations'))
            start = int(row['start_monotonic_ns'])
            end = int(row['end_monotonic_ns'])
            checksum = int(row['checksum'])
        except ValueError as error:
            raise CaptureError(f'CPU{cpu} pulse {pulse}: nonnumeric row') from error
        require(identity == (cpu, pulse, ITERATIONS),
                f'CPU{cpu} pulse {pulse}: identity/iteration mismatch')
        lower = scheduled_ns + pulse * PERIOD_NS
        upper = lower + PERIOD_NS
        require(lower <= start < upper and start >= previous_end and start <= end < upper,
                f'CPU{cpu} pulse {pulse}: missed/overlapping period')
        require(0 <= checksum < 1 << 64, f'CPU{cpu} pulse {pulse}: invalid checksum')
        checksums.append(checksum)
        previous_end = end
        work_ns += end - start
        if start_inside < start and end < stop_inside:
            interior_count += 1
            interior_work_ns += end - start
    require(interior_count > 0, f'CPU{cpu}: no fully interior pulse')
    checksum_bytes = ''.join(f'{pulse}:{checksum}\n' for pulse, checksum
                             in enumerate(checksums)).encode('ascii')
    return {'cpu': cpu, 'pulses': PULSES, 'interior_pulses': interior_count,
            'work_ns': work_ns, 'interior_work_ns': interior_work_ns,
            'checksum_sequence_sha256': digest(checksum_bytes),
            'first_start_ns': int(rows[0]['start_monotonic_ns']),
            'last_end_ns': previous_end}


def check_workload_checksums(current: dict, prior: dict | None) -> str:
    require(set(current) == {'1', '5'}, 'workload CPU set changed')
    left = current['1'].get('checksum_sequence_sha256')
    right = current['5'].get('checksum_sequence_sha256')
    require(isinstance(left, str) and HEX64.fullmatch(left) is not None and left == right,
            'CPU1/CPU5 deterministic pulse checksums differ')
    if prior is not None:
        require(set(prior) == {'1', '5'} and
                prior['1'].get('checksum_sequence_sha256') == left and
                prior['5'].get('checksum_sequence_sha256') == left,
                'deterministic pulse checksums differ from prior clean phase')
    return left


def check_stream_status(status: dict[str, str], mode: str) -> dict:
    require(status.get('abi') == '3' and status.get('state') == 'complete' and
            status.get('mode') == mode, 'ABI 3 completion/mode mismatch')
    require(status.get('interrupted') == '0' and
            status.get('wfi_pending_after_drain') == '0' and
            status.get('wfi_prepare_after_stop') == '0' and
            status.get('wfi_prepare_bad_mapping') == '0',
            'capture interrupted or WFI slot accounting failed')
    start, stop = (int(status[name]) for name in ('inside_start_ns', 'inside_stop_ns'))
    require(0 < start < stop, 'kernel interior markers invalid')
    require(status.get('start_online_mask') == status.get('end_online_mask') == '0xff',
            'online CPU mask changed')
    counts = {}
    for stream, ids in (('idle', range(8)), ('wfi', range(8)), ('dvfs', range(2))):
        for index in ids:
            name = f'{stream}{index}'
            try:
                attempts = int(status[f'{name}_attempts'])
                committed = int(status[f'{name}_committed'])
                overflow = int(status[f'{name}_overflow'])
                missing = int(status[f'{name}_missing_commit'])
            except (KeyError, ValueError) as error:
                raise CaptureError(f'{name}: missing/invalid stream status') from error
            require(attempts >= 0 and attempts == committed and overflow == missing == 0,
                    f'{name}: overflow/missing commit/count mismatch')
            counts[name] = committed
    return {'inside_start_ns': start, 'inside_stop_ns': stop,
            'stream_committed': counts}


def check_unarmed_ready(status: dict[str, str], events: bytes, wfi: bytes) -> None:
    require(status.get('abi') == '3' and status.get('state') == 'ready',
            'A baseline unexpectedly consumed observer')
    require(status.get('wfi_prepare_after_stop') == '0' and
            status.get('wfi_prepare_bad_mapping') == '0',
            'unarmed A observer has WFI accounting errors')
    for stream, ids in (('idle', range(8)), ('wfi', range(8)), ('dvfs', range(2))):
        for index in ids:
            name = f'{stream}{index}'
            require(all(status.get(f'{name}_{suffix}') == '0' for suffix in
                        ('attempts', 'committed', 'overflow', 'missing_commit')),
                    f'A baseline {name} stream unexpectedly used')
    require(events.decode('ascii').strip() == EVENT_HEADER and
            wfi.decode('ascii').strip() == WFI_HEADER,
            'unarmed A observer returned event rows or changed headers')


def check_aux_unused(pcpm: bytes, counter: bytes) -> None:
    pcpm_status = status_map(pcpm)
    counter_status = status_map(counter)
    require(pcpm_status.get('abi') == '2' and
            pcpm_status.get('state') == 'unused' and
            pcpm_status.get('mode') == 'none',
            'PCPM control was used during ABI 3 block')
    require(counter_status.get('abi') == '1' and
            counter_status.get('pre_state') == 'unused' and
            counter_status.get('post_state') == 'unused',
            'counter qualification control was used during ABI 3 block')


def identity_schema(path: Path) -> dict:
    identity = json.loads(read_bounded(path, 64 * 1024))
    required = {'schema', 'release', 'build_id', 'config_sha256', 'entry_title',
                'uki_path', 'uki_sha256', 'limine_conf_sha256', 'source_tree_sha256',
                'patch_path', 'patch_sha256', 'source_receipt_path',
                'source_receipt_sha256', 'linked_receipt_path',
                'linked_receipt_sha256', 'validator_sha256', 'image_sha256',
                'module_manifest_sha256', 'apple_dtb_manifest_sha256',
                'module_package', 'fallback_ukis'}
    require(isinstance(identity, dict) and set(identity) == required,
            'expected identity keys changed')
    require(identity['schema'] == 'abi3-native-identity-v1', 'identity schema mismatch')
    for name in ('config_sha256', 'uki_sha256', 'limine_conf_sha256',
                 'source_tree_sha256', 'patch_sha256', 'source_receipt_sha256',
                 'linked_receipt_sha256', 'validator_sha256', 'image_sha256',
                 'module_manifest_sha256', 'apple_dtb_manifest_sha256'):
        require(isinstance(identity[name], str) and HEX64.fullmatch(identity[name]),
                f'invalid {name}')
    require(isinstance(identity['build_id'], str) and HEX40.fullmatch(identity['build_id']),
            'invalid GNU Build-ID')
    require(isinstance(identity['release'], str) and
            identity['release'].startswith('7.1.12-ARCH-apsc-') and
            'abi3' in identity['release'], 'unexpected release')
    require(isinstance(identity['module_package'], str) and
            re.fullmatch(r'linux-aurora-apsc-[a-z0-9-]+-modules',
                         identity['module_package']) is not None,
            'unexpected module package')
    require(isinstance(identity['entry_title'], str) and
            identity['entry_title'].startswith('Aurora-APSC-research-wfi-') and
            'abi3' in identity['entry_title'], 'unexpected ABI 3 entry title')
    for name in ('uki_path', 'patch_path', 'source_receipt_path', 'linked_receipt_path'):
        require(isinstance(identity[name], str) and Path(identity[name]).is_absolute(),
                f'{name}: absolute path required')
    fallbacks = identity['fallback_ukis']
    require(isinstance(fallbacks, dict) and set(fallbacks) == {'stock', 'pcpm'},
            'stock and PCPM fallbacks required')
    for name, item in fallbacks.items():
        require(isinstance(item, dict) and set(item) == {'path', 'sha256', 'entry_title'} and
                Path(item['path']).is_absolute() and HEX64.fullmatch(item['sha256']) and
                item['entry_title'], f'invalid fallback {name}')
    return identity


def verify_receipts(identity: dict) -> None:
    source = json.loads(read_bounded(Path(identity['source_receipt_path']), 1_000_000))
    linked = json.loads(read_bounded(Path(identity['linked_receipt_path']), 4_000_000))
    require(source.get('candidate_manifest_tree_sha256') == identity['source_tree_sha256'] and
            source.get('patch_sha256') == identity['patch_sha256'] and
            source.get('scratch_release') == identity['release'],
            'source receipt does not bind tree/patch/release')
    require(linked.get('source_receipt_sha256') == identity['source_receipt_sha256'] and
            linked.get('candidate_source_tree_sha256') == identity['source_tree_sha256'] and
            linked.get('patch_sha256') == identity['patch_sha256'] and
            linked.get('config_sha256') == identity['config_sha256'] and
            linked.get('release') == identity['release'] and
            linked.get('vmlinux_build_id') == identity['build_id'] and
            linked.get('ticket_validator_sha256') == identity['validator_sha256'] and
            linked.get('image_sha256') == identity['image_sha256'] and
            linked.get('module_manifest_sha256') == identity['module_manifest_sha256'] and
            linked.get('apple_dtb_manifest_sha256') == identity['apple_dtb_manifest_sha256'] and
            linked.get('full_build_exit_status') == 0 and
            linked.get('full_build_targets') == ['Image', 'modules', 'dtbs'] and
            linked.get('linked_clock_branch_skips_only_apsc_load') is True and
            linked.get('linked_original_dsb_through_ret_bytes_identical') is True,
            'linked build receipt does not bind reviewed source/binary')


def verify_manifest(path: Path) -> dict[str, str]:
    require(path.is_dir() and not path.is_symlink(), 'prior packet unavailable')
    manifest = read_bounded(path / 'MANIFEST.sha256', 1_000_000).decode('ascii')
    entries = {}
    for line in manifest.splitlines():
        match = re.fullmatch(r'([0-9a-f]{64})  ([^/]+)', line)
        require(match is not None, 'malformed prior packet manifest')
        sha, name = match.groups()
        require(name not in ('', '.', '..', 'MANIFEST.sha256') and name not in entries,
                'duplicate/unsafe manifest name')
        entries[name] = sha
    require(entries and {entry.name for entry in path.iterdir()} ==
            set(entries) | {'MANIFEST.sha256'}, 'prior packet file set changed')
    for name, sha in entries.items():
        candidate = path / name
        require(candidate.is_file() and not candidate.is_symlink() and
                file_digest(candidate) == sha, f'prior packet changed: {name}')
    return entries


class Packet:
    def __init__(self, path: Path, owner: pwd.struct_passwd):
        require(path.is_absolute() and path.parent == HERE and
                re.fullmatch(r'abi3-[ADEC]-[0-9TZ]+', path.name) is not None and
                not path.exists() and not path.is_symlink(), 'unsafe/used packet path')
        parent = HERE.stat()
        require(not HERE.is_symlink() and parent.st_uid == owner.pw_uid and
                stat.S_IMODE(parent.st_mode) == 0o700, 'private parent ownership/mode changed')
        path.mkdir(mode=0o700)
        os.chown(path, owner.pw_uid, owner.pw_gid)
        self.path = path
        self.owner = owner
        self.log = (path / 'timeline.jsonl').open('xb')
        (path / 'timeline.jsonl').chmod(0o600)
        os.chown(path / 'timeline.jsonl', owner.pw_uid, owner.pw_gid)

    def mark(self, action: str, **fields) -> None:
        row = {'action': action, 'utc': datetime.now(timezone.utc).isoformat(),
               'monotonic_ns': time.monotonic_ns(), **fields}
        self.log.write((json.dumps(row, sort_keys=True) + '\n').encode())
        self.log.flush()
        os.fsync(self.log.fileno())

    def save(self, name: str, data: bytes) -> None:
        require(re.fullmatch(r'[A-Za-z0-9_.-]+', name) is not None and
                name not in ('.', '..', 'MANIFEST.sha256'), 'unsafe packet filename')
        path = self.path / name
        with path.open('xb') as target:
            target.write(data)
            target.flush()
            os.fsync(target.fileno())
        path.chmod(0o600)
        os.chown(path, self.owner.pw_uid, self.owner.pw_gid)

    def json(self, name: str, value) -> None:
        self.save(name, (json.dumps(value, indent=2, sort_keys=True) + '\n').encode())

    def capture(self, name: str, source: Path, maximum: int = MAX_RAW) -> bytes:
        self.mark('read_begin', name=name, source=str(source))
        data = read_bounded(source, maximum)
        self.mark('read_end', name=name, bytes=len(data), sha256=digest(data))
        self.save(name, data)
        return data

    def command(self, name: str, argv: list[str], timeout: int = 90) -> subprocess.CompletedProcess:
        self.json(name + '-argv.json', argv)
        self.mark('command_begin', name=name)
        result = subprocess.run(argv, capture_output=True, timeout=timeout,
                                env=dict(os.environ, SYSTEMD_COLORS='0',
                                         SYSTEMD_URLIFY='0', LC_ALL='C'))
        self.mark('command_end', name=name, exit_status=result.returncode)
        self.save(name + '.stdout', result.stdout)
        self.save(name + '.stderr', result.stderr)
        return result

    def finish(self) -> None:
        self.log.close()
        entries = []
        for path in sorted(self.path.iterdir()):
            require(path.is_file() and not path.is_symlink(), 'nonregular packet item')
            entries.append(f'{file_digest(path)}  {path.name}')
        data = ('\n'.join(entries) + '\n').encode()
        manifest = self.path / 'MANIFEST.sha256'
        with manifest.open('xb') as target:
            target.write(data)
            target.flush()
            os.fsync(target.fileno())
        manifest.chmod(0o600)
        os.chown(manifest, self.owner.pw_uid, self.owner.pw_gid)
        directory = os.open(self.path, os.O_DIRECTORY | os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)


def value(path: str) -> str:
    return Path(path).read_text().strip()


def environment() -> dict:
    result = {
        'utc': datetime.now(timezone.utc).isoformat(),
        'monotonic_ns': time.monotonic_ns(),
        'ac_online': value('/sys/class/power_supply/macsmc-ac/online'),
        'battery_percent': value('/sys/class/power_supply/macsmc-battery/capacity'),
        'brightness': value('/sys/class/backlight/apple-panel-bl/brightness'),
        'online_cpus': value('/sys/devices/system/cpu/online'),
        'cpuidle_driver': value('/sys/devices/system/cpu/cpuidle/current_driver'),
        'cpuidle_governor': value('/sys/devices/system/cpu/cpuidle/current_governor_ro'),
        'cpuidle_state1_disabled': {
            str(cpu): value(f'/sys/devices/system/cpu/cpu{cpu}/cpuidle/state1/disable')
            for cpu in range(8)},
        'policies': {}, 'thermal_millidegrees': {}, 'network': {}, 'usb': [],
        'proc_stat_sha256': file_digest(Path('/proc/stat')),
    }
    for policy in sorted(Path('/sys/devices/system/cpu/cpufreq').glob('policy*')):
        result['policies'][policy.name] = {
            key: value(str(policy / key)) for key in ('related_cpus', 'affected_cpus',
                'scaling_driver', 'scaling_governor', 'scaling_min_freq', 'scaling_max_freq')}
    for zone in sorted(Path('/sys/class/thermal').glob('thermal_zone*')):
        if (zone / 'temp').exists():
            result['thermal_millidegrees'][zone.name] = value(str(zone / 'temp'))
    for interface in sorted(Path('/sys/class/net').iterdir()):
        if interface.is_dir():
            result['network'][interface.name] = {
                key: value(str(interface / 'statistics' / key)) for key in
                ('rx_bytes', 'tx_bytes', 'rx_packets', 'tx_packets')}
    for device in sorted(Path('/sys/bus/usb/devices').iterdir()):
        if (device / 'idVendor').exists() and (device / 'idProduct').exists():
            result['usb'].append({'node': device.name, 'vendor': value(str(device / 'idVendor')),
                                  'product': value(str(device / 'idProduct'))})
    return result


def check_environment(pre: dict, post: dict) -> dict:
    required = ('ac_online', 'brightness', 'online_cpus', 'cpuidle_driver',
                'cpuidle_governor', 'cpuidle_state1_disabled', 'policies')
    require(pre['ac_online'] == post['ac_online'] == '1' and
            pre['brightness'] == post['brightness'] == '155' and
            pre['online_cpus'] == post['online_cpus'] == '0-7' and
            pre['cpuidle_driver'] == post['cpuidle_driver'] == 'apple_idle' and
            pre['cpuidle_governor'] == post['cpuidle_governor'] == 'menu' and
            all(x == '0' for x in pre['cpuidle_state1_disabled'].values()) and
            all(x == '0' for x in post['cpuidle_state1_disabled'].values()),
            'power/brightness/CPU-idle baseline changed')
    require(all(pre[key] == post[key] for key in required),
            'capture policy or power environment changed')
    return {'network_interfaces_equal': set(pre['network']) == set(post['network']),
            'usb_equal': pre['usb'] == post['usb'],
            'thermal_before': pre['thermal_millidegrees'],
            'thermal_after': post['thermal_millidegrees']}


def preflight(packet: Packet, identity: dict, phase: str, prior: Path | None) -> dict:
    require(os.geteuid() == 0 and not sys.flags.optimize, 'administrator execution required')
    require(file_digest(WORKLOAD_SOURCE) == EXPECTED_WORKLOAD_SOURCE_SHA,
            'pinned workload source changed')
    require(file_digest(WORKLOAD) == EXPECTED_WORKLOAD_SHA, 'pinned workload binary changed')
    require(file_digest(VALIDATOR) == identity['validator_sha256'], 'validator changed')
    for name in ('patch', 'source_receipt', 'linked_receipt'):
        path = Path(identity[name + '_path'])
        require(file_digest(path) == identity[name + '_sha256'], f'{name} changed')
        packet.capture(name + '-source.bin', path, 32 * 1024 * 1024)
    verify_receipts(identity)
    packet.json('source-hashes.json', {
        'collector_sha256': file_digest(Path(__file__).resolve()),
        'workload_source_sha256': EXPECTED_WORKLOAD_SOURCE_SHA,
        'workload_binary_sha256': EXPECTED_WORKLOAD_SHA,
        'validator_sha256': identity['validator_sha256'],
        'patch_sha256': identity['patch_sha256'],
        'source_tree_sha256': identity['source_tree_sha256'],
        'linked_receipt_sha256': identity['linked_receipt_sha256'],
    })
    packet.capture('collector-source.py', Path(__file__).resolve(), 1_000_000)
    packet.capture('workload-source.c', WORKLOAD_SOURCE, 1_000_000)
    packet.capture('workload-binary', WORKLOAD, 1_000_000)
    packet.capture('validator-source.py', VALIDATOR, 1_000_000)
    packet.json('expected-identity.json', identity)
    require(os.uname().release == identity['release'], 'running release mismatch')
    notes = packet.capture('kernel-notes.bin', Path('/sys/kernel/notes'), 16 * 1024 * 1024)
    require(build_ids(notes) == [identity['build_id']], 'running GNU Build-ID mismatch')
    config = gzip.decompress(packet.capture('config.gz', Path('/proc/config.gz'), 2 * 1024 * 1024))
    packet.save('running.config', config)
    require(digest(config) == identity['config_sha256'], 'running kernel config mismatch')
    require(b'CONFIG_ARM_APPLE_APSC_OBSERVER=y\n' in config, 'APSC observer not built in')
    packet.capture('boot-fdt.bin', Path('/sys/firmware/fdt'), 8 * 1024 * 1024)
    packet.capture('boot-cmdline.txt', Path('/proc/cmdline'), 4096)
    packet.capture('proc-stat-before', Path('/proc/stat'), 1_000_000)
    boot_id = packet.capture('boot-id.txt', Path('/proc/sys/kernel/random/boot_id'), 128).decode().strip()
    require(re.fullmatch(r'[0-9a-f-]{36}', boot_id) is not None, 'invalid boot ID')
    packet.capture('cpuinfo.txt', Path('/proc/cpuinfo'), 64 * 1024)
    features = cpu_features((packet.path / 'cpuinfo.txt').read_bytes())
    require(set(features) == set(range(8)) and
            all('atomics' in features[cpu] for cpu in range(8)), 'LSE atomics absent on a CPU')
    boot = packet.command('bootctl', ['/usr/bin/bootctl', 'status', '--no-pager'])
    require(boot.returncode == 0 and
            ('Current Entry: ' + identity['entry_title'] + '\n').encode() in boot.stdout,
            'selected Limine entry mismatch')
    packet.capture('limine.conf', Path('/boot/efi/limine.conf'), 64 * 1024)
    limine = (packet.path / 'limine.conf').read_bytes()
    require(digest(limine) == identity['limine_conf_sha256'] and
            ('/' + identity['entry_title'] + '\n').encode() in limine and
            all(('/' + item['entry_title'] + '\n').encode() in limine
                for item in identity['fallback_ukis'].values()),
            'Limine configuration or fallback entry changed')
    hashes = {'candidate': file_digest(Path(identity['uki_path']))}
    require(hashes['candidate'] == identity['uki_sha256'], 'candidate UKI changed')
    for name, item in identity['fallback_ukis'].items():
        hashes[name] = file_digest(Path(item['path']))
        require(hashes[name] == item['sha256'], f'{name} fallback changed')
    packet.json('installed-image-hashes.json', hashes)
    modules = packet.command('module-package-check',
                             ['/usr/bin/pacman', '-Qkk', identity['module_package']], timeout=180)
    require(modules.returncode == 0 and b'0 altered files' in modules.stdout,
            'installed module package failed integrity check')
    if phase in PRIOR:
        require(prior is not None, 'prior fresh-boot packet required')
        verify_manifest(prior)
        prior_summary = json.loads(read_bounded(prior / 'acquisition-summary.json', 64 * 1024))
        prior_identity = json.loads(read_bounded(prior / 'expected-identity.json', 64 * 1024))
        prior_id = read_bounded(prior / 'boot-id.txt', 128).decode().strip()
        require(prior_summary.get('phase') == PRIOR[phase] and
                prior_summary.get('result') == 'clean' and prior_id != boot_id and
                prior_identity == identity,
                'prior phase or fresh-boot gate failed')
        if phase == 'C':
            previous_report = json.loads(read_bounded(prior / 'abi3-validator-report.json', 16 * 1024 * 1024))
            require(previous_report.get('candidate_count') == 0,
                    'C control is conditional on zero E ticket witnesses')
        packet.json('prior-packet-gate.json', {
            'prior_manifest_sha256': file_digest(prior / 'MANIFEST.sha256'),
            'prior_phase': PRIOR[phase], 'prior_boot_id': prior_id,
            'current_boot_id': boot_id})
    else:
        require(prior is None, 'A baseline must not inherit a prior packet')
    before = environment()
    packet.json('environment-before.json', before)
    require(before['ac_online'] == '1' and before['brightness'] == '155' and
            before['online_cpus'] == '0-7' and before['cpuidle_driver'] == 'apple_idle' and
            before['cpuidle_governor'] == 'menu' and
            all(v == '0' for v in before['cpuidle_state1_disabled'].values()),
            'AC/brightness/topology/cpuidle preflight mismatch')
    require(set(before['policies']) == {'policy0', 'policy4'} and
            before['policies']['policy0']['related_cpus'] == '0 1 2 3' and
            before['policies']['policy4']['related_cpus'] == '4 5 6 7' and
            all(policy['scaling_driver'] == 'apple-cpufreq'
                for policy in before['policies'].values()),
            'E/P cpufreq policies differ from qualified topology')
    if prior is not None:
        previous_environment = json.loads(read_bounded(prior / 'environment-before.json', 64 * 1024))
        require(all(before[key] == previous_environment[key] for key in
                    ('ac_online', 'brightness', 'online_cpus', 'cpuidle_driver',
                     'cpuidle_governor', 'cpuidle_state1_disabled', 'policies')),
                'phase policy/power setup differs from prior boot')
    ready = status_map(packet.capture('apsc-status-before.txt', APSC / 'status', 64 * 1024))
    require(ready.get('abi') == '3' and ready.get('state') == 'ready' and
            ready.get('cluster0_cpus') == '0xf' and ready.get('cluster1_cpus') == '0xf0' and
            ready.get('cluster0_cmd_phys') == '0x210e20020' and
            ready.get('cluster1_cmd_phys') == '0x211e20020' and
            ready.get('cluster0_resource_size') == '0x1000' and
            ready.get('cluster1_resource_size') == '0x1000',
            'ABI 3 observer/topology/resource not ready')
    pcpm_before = packet.capture('pcpm-status-before.txt', PCPM / 'status', 64 * 1024)
    counter_before = packet.capture('counter-status-before.txt', COUNTER / 'status', 64 * 1024)
    check_aux_unused(pcpm_before, counter_before)
    log = packet.command('kernel-log-before', ['/usr/bin/journalctl', '-k', '-b',
                         '--no-pager', '-o', 'short-monotonic'])
    require(log.returncode == 0 and log.stdout.strip(), 'current-boot kernel log unavailable')
    return before


def write_capture(packet: Packet, command: str, deadline_ns: int) -> None:
    data = command.encode('ascii')
    packet.mark('capture_write_begin', command=command.strip())
    require(time.monotonic_ns() <= deadline_ns,
            'collector missed arm offset before control write')
    descriptor = os.open(APSC / 'capture', os.O_WRONLY | os.O_CLOEXEC)
    try:
        written = os.write(descriptor, data)
        require(written == len(data), 'short capture control write')
    finally:
        os.close(descriptor)
        packet.mark('capture_write_end')


def wait_until_arm(target_ns: int) -> int:
    while True:
        current = time.monotonic_ns()
        if current >= target_ns:
            break
        time.sleep((target_ns - current) / 1e9)
    require(current - target_ns <= ARM_SLIP_LIMIT_NS,
            'collector missed the declared 150 ms arm offset')
    return current


def raw_after(packet: Packet) -> tuple[tuple[bytes | None, ...], list[str]]:
    raw = []
    errors = []
    for name, path, maximum in (
        ('apsc-status-after.txt', APSC / 'status', 64 * 1024),
        ('apsc-events.csv', APSC / 'events.csv', MAX_RAW),
        ('apsc-wfi-events.csv', APSC / 'wfi-events.csv', MAX_RAW),
        ('pcpm-status-after.txt', PCPM / 'status', 64 * 1024),
        ('counter-status-after.txt', COUNTER / 'status', 64 * 1024)):
        try:
            raw.append(packet.capture(name, path, maximum))
        except BaseException as error:
            raw.append(None)
            errors.append(f'{name}: {error!r}')
            packet.mark('raw_read_failed', name=name, error=repr(error))
    packet.mark('observer_raw_drained', errors=errors)
    return tuple(raw), errors


def run_capture(packet: Packet, identity: dict, phase: str, before: dict,
                prior: Path | None = None) -> dict:
    mode = MODES[phase]
    owner = packet.owner
    children = []
    armed = False
    write_error = None
    try:
        start_ns = time.monotonic_ns() + 1_000_000_000
        packet.json('schedule.json', {'workers': list(CPUS), 'start_monotonic_ns': start_ns,
                                      'period_ns': PERIOD_NS, 'pulses': PULSES,
                                      'iterations': ITERATIONS, 'duration_ms': DURATION_MS,
                                      'arm_offset_ns': 150_000_000})
        for cpu in CPUS:
            children.append(subprocess.Popen([str(WORKLOAD), str(cpu), str(start_ns)],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, user=owner.pw_uid, group=owner.pw_gid))
        target_ns = start_ns + 150_000_000
        actual_arm_ns = wait_until_arm(target_ns)
        require(all(child.poll() is None for child in children),
                'workload exited before observer window')
        packet.mark('window_begin', phase=phase, mode=mode,
                    scheduled_arm_ns=target_ns, checked_arm_ns=actual_arm_ns)
        if phase == 'A':
            baseline_start_ns = time.monotonic_ns()
            require(baseline_start_ns <= target_ns + ARM_SLIP_LIMIT_NS,
                    'baseline window missed declared arm offset')
            time.sleep(DURATION_MS / 1000)
            baseline_stop_ns = time.monotonic_ns()
        else:
            armed = True
            try:
                write_capture(packet, f'{mode} {DURATION_MS}\n',
                              target_ns + ARM_SLIP_LIMIT_NS)
            except BaseException as error:
                # A debugfs write may fail after the one-shot was consumed.
                # Continue through raw export and both explicit E releases.
                write_error = error
                packet.mark('capture_write_failed', error=repr(error))
        packet.mark('window_end', phase=phase)
        (status_raw, events_raw, wfi_raw, pcpm_raw, counter_raw), raw_errors = raw_after(packet)
        # The explicit export token follows the completed capture, including
        # when a raw read failed.  Preserve both worker streams before any
        # status/CSV screening can reject this one-shot.
        packet.mark('workload_release_begin', token='E')
        workload_bytes = {}
        release_errors = []
        for cpu, child in zip(CPUS, children):
            try:
                stdout, stderr = child.communicate(b'E', timeout=25)
            except subprocess.TimeoutExpired:
                child.kill()
                stdout, stderr = child.communicate()
                release_errors.append(f'CPU{cpu}: export timed out')
            packet.save(f'workload-cpu{cpu}.csv', stdout)
            packet.save(f'workload-cpu{cpu}.stderr', stderr)
            packet.mark('workload_release_end', cpu=cpu, exit_status=child.returncode)
            if child.returncode != 0:
                release_errors.append(f'CPU{cpu}: workload exited {child.returncode}')
            workload_bytes[cpu] = stdout
        require(not raw_errors, 'observer raw export failed: ' + '; '.join(raw_errors))
        require(not release_errors, '; '.join(release_errors))
        require(write_error is None, f'capture write failed: {write_error!r}')
        check_aux_unused(pcpm_raw, counter_raw)
        require(pcpm_raw == (packet.path / 'pcpm-status-before.txt').read_bytes() and
                counter_raw == (packet.path / 'counter-status-before.txt').read_bytes(),
                'PCPM/counter helper status changed during capture')
        status = status_map(status_raw)
        if phase == 'A':
            check_unarmed_ready(status, events_raw, wfi_raw)
            interior = (baseline_start_ns, baseline_stop_ns)
            stream_check = {'unarmed': True}
        else:
            stream_check = check_stream_status(status, mode)
            interior = (stream_check['inside_start_ns'], stream_check['inside_stop_ns'])
        packet.json('window-markers.json', {'source': 'userspace' if phase == 'A' else
                    'kernel-CLOCK_MONOTONIC', 'start_ns': interior[0],
                    'stop_ns': interior[1], 'capture_armed': armed})
        packet.json('stream-status-check.json', stream_check)
        workloads = {}
        validation_errors = []
        for cpu in CPUS:
            try:
                workloads[str(cpu)] = validate_workload_csv(workload_bytes[cpu], cpu,
                                                            start_ns, interior)
            except CaptureError as error:
                validation_errors.append(str(error))
        require(not validation_errors, '; '.join(validation_errors))
        prior_workloads = (json.loads(read_bounded(prior / 'workload-check.json', 64 * 1024))
                           if prior is not None else None)
        checksum_sha = check_workload_checksums(workloads, prior_workloads)
        packet.json('workload-checksum-match.json',
                    {'cpu1_cpu5_equal': True, 'prior_phase_equal': prior is not None,
                     'sequence_sha256': checksum_sha})
        packet.json('workload-check.json', workloads)
        if phase != 'A':
            validator = packet.command('abi3-validator', ['/usr/bin/python3', str(VALIDATOR),
                '--status', str(packet.path / 'apsc-status-after.txt'),
                '--events', str(packet.path / 'apsc-events.csv'),
                '--wfi-events', str(packet.path / 'apsc-wfi-events.csv')], timeout=90)
            require(validator.returncode == 0, 'ABI 3 offline ticket validator rejected raw streams')
            report = json.loads(validator.stdout)
            require(report.get('abi') == 3 and report.get('mode') == mode,
                    'ABI 3 validator report mode mismatch')
            packet.json('abi3-validator-report.json', report)
        else:
            report = None
        after = environment()
        packet.json('environment-after.json', after)
        drift = check_environment(before, after)
        packet.json('environment-drift.json', drift)
        packet.capture('proc-stat-after', Path('/proc/stat'), 1_000_000)
        log = packet.command('kernel-log-after', ['/usr/bin/journalctl', '-k', '-b',
                             '--no-pager', '-o', 'short-monotonic'])
        require(log.returncode == 0 and log.stdout.strip(), 'kernel log after unavailable')
        return {'phase': phase, 'mode': mode, 'result': 'clean',
                'capture_armed': armed, 'workloads': workloads,
                'abi3_validator_summary': ({'busy_rows': report['busy_rows'],
                    'candidate_count': report['candidate_count'],
                    'report_sha256': file_digest(packet.path / 'abi3-validator-report.json')}
                    if report is not None else None),
                'interpretation': 'raw record integrity only; no WFI-instruction state proof'}
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
                try:
                    child.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.communicate()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=tuple(MODES))
    parser.add_argument('--identity-json', type=Path)
    parser.add_argument('--prior-packet', type=Path)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if not args.execute:
        print(json.dumps({'dry_run': True, 'phase': args.phase, 'mode': MODES[args.phase],
                          'duration_ms': DURATION_MS, 'workers': list(CPUS),
                          'kernel_capture_write': args.phase != 'A',
                          'packet_created': False}, sort_keys=True))
        return 0
    require(args.identity_json is not None, 'reviewed expected identity JSON required')
    require(not sys.flags.optimize, 'Python optimization invalid for acquisition')
    owner = pwd.getpwnam('REDACTED_USER')
    require(os.geteuid() == 0, 'administrator execution required')
    identity = identity_schema(args.identity_json)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    packet = Packet(HERE / f'abi3-{args.phase}-{stamp}', owner)
    outcome = {'phase': args.phase, 'mode': MODES[args.phase], 'result': 'failed',
               'capture_armed': False}
    try:
        packet.mark('begin', phase=args.phase)
        before = preflight(packet, identity, args.phase, args.prior_packet)
        outcome = run_capture(packet, identity, args.phase, before, args.prior_packet)
        packet.mark('complete', phase=args.phase)
    except BaseException as error:
        packet.mark('failed', phase=args.phase, error=repr(error))
        outcome['error'] = repr(error)
        # A failed one-shot still has a private, hash-sealed incident packet.
        for name, action in (
            ('apsc-status-incident.txt', lambda: packet.capture('apsc-status-incident.txt', APSC / 'status', 64 * 1024)),
            ('environment-incident.json', lambda: packet.json('environment-incident.json', environment())),
            ('kernel-log-incident', lambda: packet.command('kernel-log-incident',
                ['/usr/bin/journalctl', '-k', '-b', '--no-pager', '-o', 'short-monotonic']))):
            try:
                action()
            except BaseException as incident_error:
                packet.mark('incident_export_failed', name=name, error=repr(incident_error))
    finally:
        packet.json('acquisition-summary.json', outcome)
        packet.finish()
        print(json.dumps({'packet': str(packet.path), 'phase': args.phase,
                          'result': outcome['result'],
                          'manifest_sha256': file_digest(packet.path / 'MANIFEST.sha256')},
                         sort_keys=True))
    return 0 if outcome['result'] == 'clean' else 2


if __name__ == '__main__':
    raise SystemExit(main())
