#!/usr/bin/env python3
"""Bounded authorized native acquisition; save raw private files and failures."""
import argparse
import csv
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import struct
import subprocess
import sys
import time
from datetime import datetime, timezone

RELEASE = '7.1.12-ARCH-apsc-20261002'
CONFIG_SHA = 'f86b80f4dcef277be874f476293d8b8055053072f7209625586b60e2227f905d'
BUILD_ID = 'eb8fe1838f2c34f24f83ec53da25d2f9ae150b12'
ENTRY = 'Aurora-APSC-research-capacity'
WORKLOAD_SHA = '82f4ce1145c8135c8b28246a9681d2316083cd1bb1a936a736b8a6cd03102d2b'
DURATION_MS = 2000


def values(text):
    pairs = [line.split('=', 1) for line in text.splitlines()]
    if any(len(p) != 2 for p in pairs) or len({p[0] for p in pairs}) != len(pairs):
        raise ValueError('invalid status keys')
    return dict(pairs)


def note_ids(data):
    ids = []
    offset = 0
    while offset + 12 <= len(data):
        namesz, size, kind = struct.unpack_from('<III', data, offset)
        offset += 12
        name = data[offset:offset + namesz]
        offset += (namesz + 3) & ~3
        value = data[offset:offset + size]
        offset += (size + 3) & ~3
        if name == b'GNU\0' and kind == 3:
            ids.append(value.hex())
    return ids


def validate_workload_csv(data, cpu, scheduled_start):
    expected_fields = ['cpu', 'pulse', 'iterations', 'start_monotonic_ns', 'end_monotonic_ns', 'checksum']
    rows = list(csv.DictReader(io.StringIO(data.decode('utf-8'))))
    if not rows or list(rows[0]) != expected_fields or len(rows) != 44:
        raise ValueError(f'cpu{cpu}: incomplete or malformed workload CSV')
    previous_end = 0
    for pulse, row in enumerate(rows):
        if (int(row['cpu']), int(row['pulse']), int(row['iterations'])) != (cpu, pulse, 1048576):
            raise ValueError(f'cpu{cpu}: workload identity or pulse mismatch at {pulse}')
        begin, end, checksum = (int(row[key]) for key in ('start_monotonic_ns', 'end_monotonic_ns', 'checksum'))
        if begin < scheduled_start + pulse * 50_000_000 or begin < previous_end or end < begin or not 0 <= checksum < 2**64:
            raise ValueError(f'cpu{cpu}: invalid workload timing or checksum at {pulse}')
        previous_end = end


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('packet_root', type=Path)
    parser.add_argument('mode', choices=('baseline', 'records', 'mmio', 'wfi_clock', 'wfi_mmio'))
    parser.add_argument('--workload', type=Path, required=True)
    parser.add_argument('--observer-abi', type=int, choices=(1, 2), default=1)
    parser.add_argument('--expected-release')
    parser.add_argument('--expected-config-sha256')
    parser.add_argument('--expected-build-id')
    parser.add_argument('--expected-entry')
    args = parser.parse_args()
    if args.observer_abi == 1:
        if args.mode.startswith('wfi_'):
            parser.error('WFI capture requires --observer-abi 2')
        expected_release = args.expected_release or RELEASE
        expected_config_sha = args.expected_config_sha256 or CONFIG_SHA
        expected_build_id = args.expected_build_id or BUILD_ID
        expected_entry = args.expected_entry or ENTRY
    else:
        missing = [name for name, value in (
            ('--expected-release', args.expected_release),
            ('--expected-config-sha256', args.expected_config_sha256),
            ('--expected-build-id', args.expected_build_id),
            ('--expected-entry', args.expected_entry),
        ) if not value]
        if missing:
            parser.error('ABI 2 requires exact boot identity: ' + ', '.join(missing))
        expected_release = args.expected_release
        expected_config_sha = args.expected_config_sha256
        expected_build_id = args.expected_build_id
        expected_entry = args.expected_entry
    if not re.fullmatch(r'[0-9a-f]{64}', expected_config_sha):
        parser.error('expected config SHA-256 must be 64 lowercase hexadecimal digits')
    if not re.fullmatch(r'[0-9a-f]{40}', expected_build_id):
        parser.error('expected GNU build ID must be 40 lowercase hexadecimal digits')
    if sys.flags.optimize:
        raise RuntimeError('Python optimization disables acquisition safety checks')
    assert os.geteuid() == 0, 'authorized administrator acquisition required'
    owner = args.packet_root.stat()
    assert owner.st_uid != 0 and stat.S_IMODE(owner.st_mode) == 0o700
    assert not args.packet_root.is_symlink()
    output = args.packet_root / ('native-' + args.mode + '-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    output.mkdir(mode=0o700)
    os.chown(output, owner.st_uid, owner.st_gid)
    records, children = [], []

    def save(name, data):
        path = output / name
        with path.open('xb') as f:
            f.write(data)
        path.chmod(0o600)
        os.chown(path, owner.st_uid, owner.st_gid)
        return path

    def mark(action, **extra):
        records.append(dict(action=action, utc=datetime.now(timezone.utc).isoformat(), monotonic_ns=time.monotonic_ns(), **extra))

    def read(path, name):
        data = Path(path).read_bytes()
        save(name, data)
        return data

    def command(argv, name, unprivileged=False):
        mark('command_begin', argv=argv)
        kwargs = {'user': owner.st_uid, 'group': owner.st_gid} if unprivileged else {}
        p = subprocess.run(argv, capture_output=True, env=dict(os.environ, SYSTEMD_COLORS='0', SYSTEMD_URLIFY='0'), **kwargs)
        save(name + '.stdout', p.stdout)
        save(name + '.stderr', p.stderr)
        mark('command_end', argv=argv, exit_status=p.returncode)
        return p

    def snapshot(label):
        paths = [Path('/sys/devices/system/cpu/online'), Path('/sys/devices/system/cpu/cpuidle/current_driver'),
                 Path('/sys/devices/system/cpu/cpuidle/current_governor_ro')]
        for policy in sorted(Path('/sys/devices/system/cpu/cpufreq').glob('policy*')):
            paths += [policy / f for f in ('related_cpus', 'affected_cpus', 'scaling_driver', 'scaling_governor',
                                          'scaling_min_freq', 'scaling_max_freq', 'scaling_cur_freq')]
        paths += sorted(Path('/sys/devices/system/cpu').glob('cpu*/cpuidle/state*/*'))
        paths += [p / f for p in Path('/sys/class/power_supply').iterdir() for f in ('online', 'status', 'capacity', 'current_now', 'voltage_now') if (p / f).exists()]
        paths += [p / f for p in Path('/sys/class/backlight').iterdir() for f in ('brightness', 'actual_brightness', 'max_brightness') if (p / f).exists()]
        paths += sorted(Path('/sys/class/thermal').glob('thermal_zone*/temp'))
        data = []
        for path in paths:
            if not path.is_file():
                continue
            item = {'path': str(path), 'observed_monotonic_ns': time.monotonic_ns()}
            try:
                item['raw_text'] = path.read_text()
            except OSError as e:
                item.update(errno=e.errno, error=str(e))
            data.append(item)
        save(label + '-snapshot.json', (json.dumps(data, indent=2) + '\n').encode())
        return {x['path']: x['raw_text'].strip() for x in data if 'raw_text' in x}

    apsc = Path('/sys/kernel/debug/apple_apsc_observer')
    counter = Path('/sys/kernel/debug/apple_counter_qualification')
    try:
        workload_sha = hashlib.sha256(args.workload.read_bytes()).hexdigest()
        mark('begin', mode=args.mode, observer_abi=args.observer_abi, duration_ms=DURATION_MS,
             release=os.uname().release, expected_release=expected_release,
             expected_config_sha256=expected_config_sha, expected_build_id=expected_build_id,
             expected_entry=expected_entry, workload_sha256=workload_sha)
        assert workload_sha == WORKLOAD_SHA, 'unexpected workload binary'
        assert os.uname().release == expected_release
        config = gzip.decompress(read('/proc/config.gz', 'boot-config.gz'))
        save('boot.config', config)
        assert hashlib.sha256(config).hexdigest() == expected_config_sha
        assert note_ids(read('/sys/kernel/notes', 'boot-kernel-notes.bin')) == [expected_build_id]
        read('/sys/firmware/fdt', 'boot-fdt.bin')
        read('/proc/cmdline', 'boot-cmdline.txt')
        read('/proc/sys/kernel/random/boot_id', 'boot-id.txt')
        boot = command(['/usr/bin/bootctl', 'status', '--no-pager'], 'bootctl')
        assert boot.returncode == 0 and ('Current Entry: ' + expected_entry).encode() in boot.stdout
        vm = command(['/usr/bin/systemd-detect-virt'], 'virtualization')
        assert vm.stdout.strip() == b'none', 'native provenance needs further qualification'
        before = snapshot('before')
        assert before['/sys/devices/system/cpu/online'] == '0-7'
        assert before['/sys/devices/system/cpu/cpuidle/current_driver'] == 'apple_idle'
        assert before['/sys/devices/system/cpu/cpuidle/current_governor_ro'] == 'menu'
        assert all(before[f'/sys/devices/system/cpu/cpu{i}/cpuidle/state1/disable'] == '0' for i in range(8))
        ready = values(read(apsc / 'status', 'apsc-ready.txt').decode())
        cqready = values(read(counter / 'status', 'counter-ready.txt').decode())
        assert ready['abi'] == str(args.observer_abi) and ready['state'] == 'ready'
        assert (ready['cluster0_cpus'], ready['cluster1_cpus']) == ('0xf', '0xf0')
        assert (ready['cluster0_cmd_phys'], ready['cluster1_cmd_phys']) == ('0x210e20020', '0x211e20020')
        assert cqready['abi'] == '1' and cqready['pre_state'] == cqready['post_state'] == 'unused'
        mark('counter_pre_begin', control='pre 0 256')
        counter.joinpath('control').write_text('pre 0 256\n')
        mark('counter_pre_end')
        pre = values(read(counter / 'status', 'counter-pre-status.txt').decode())
        read(counter / 'events.csv', 'counter-pre-events.csv')
        decode = command(['/usr/bin/python3', str(Path(__file__).resolve().parents[1] / 'linux-counter-qualification/analyze.py'),
                          str(output / 'counter-pre-events.csv'), str(output / 'counter-pre-status.txt'),
                          '--pairwise-tolerance-ticks', '240', '--endpoint-uncertainty-ticks', '4'], 'counter-pre-analysis', True)
        assert decode.returncode == 0
        analysis = json.loads(decode.stdout)
        assert analysis['phases']['pre']['acquisition_eligible_for_conditional_model']
        assert pre['pre_state'] == 'complete' and pre['pre_completed'] == pre['pre_attempted'] == '1792'
        assert pre['pre_error'] == '0' and pre['pre_metadata_completed'] == '8'
        assert all(pre[f'pre_cpu{i}_cntfrq'] == '24000000' for i in range(8))
        times = {x['action']: x['monotonic_ns'] for x in records if x['action'].startswith('counter_pre_')}
        assert times['counter_pre_end'] - times['counter_pre_begin'] <= 5_000_000_000, 'pre phase exceeds declared latency'
        mark('settling_begin', seconds=5)
        time.sleep(5)
        mark('settling_end')
        start = time.monotonic_ns() + 1_000_000_000
        for cpu in (1, 5):
            children.append(subprocess.Popen([str(args.workload), str(cpu), str(start)], stdin=subprocess.PIPE,
                                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, user=owner.st_uid, group=owner.st_gid))
        time.sleep(max(0, (start + 150_000_000 - time.monotonic_ns()) / 1e9))
        assert all(child.poll() is None for child in children), 'workload exited before observer arming'
        mark('window_begin')
        if args.mode == 'baseline':
            time.sleep(DURATION_MS / 1000)
        else:
            apsc.joinpath('capture').write_text(f'{args.mode} {DURATION_MS}\n')
        mark('window_end')
        captured_status = values(read(apsc / 'status', 'status.txt').decode())
        read(apsc / 'events.csv', 'events.csv')
        if args.observer_abi == 2:
            read(apsc / 'wfi-events.csv', 'wfi-events.csv')
        mark('observer_drained')
        assert captured_status['abi'] == str(args.observer_abi), 'observer ABI changed during capture'
        if args.mode == 'baseline':
            assert captured_status['state'] == 'ready', 'baseline unexpectedly consumed observer'
        else:
            assert captured_status['mode'] == args.mode, 'observer capture mode differs from request'
        for cpu, child in zip((1, 5), children):
            out, err = child.communicate(b'E', timeout=15)
            save(f'workload-cpu{cpu}.csv', out); save(f'workload-cpu{cpu}.stderr', err)
            mark('workload_complete', cpu=cpu, exit_status=child.returncode)
            assert child.returncode == 0
            validate_workload_csv(out, cpu, start)
        mark('counter_post_begin', control='post')
        counter.joinpath('control').write_text('post\n')
        mark('counter_post_end')
        post = values(read(counter / 'status', 'counter-status.txt').decode())
        read(counter / 'events.csv', 'counter-events.csv')
        decode = command(['/usr/bin/python3', str(Path(__file__).resolve().parents[1] / 'linux-counter-qualification/analyze.py'),
                          str(output / 'counter-events.csv'), str(output / 'counter-status.txt'),
                          '--pairwise-tolerance-ticks', '240', '--endpoint-uncertainty-ticks', '4'], 'counter-analysis', True)
        assert decode.returncode == 0, 'post counter analysis failed'
        analysis = json.loads(decode.stdout)
        assert analysis['phases']['post']['acquisition_eligible_for_conditional_model']
        assert analysis['shared_pre_post_model']['both_phases_eligible']
        assert post['post_state'] == 'complete' and post['post_completed'] == post['post_attempted'] == '1792'
        assert post['post_error'] == '0' and post['post_metadata_completed'] == '8'
        assert all(post[f'post_cpu{i}_cntfrq'] == '24000000' for i in range(8))
        if args.mode != 'baseline':
            if args.observer_abi == 1:
                decoder = Path(__file__).resolve().parents[1] / 'linux-apsc-observer/analyze.py'
                decoder_args = [str(output / 'events.csv'), str(output / 'status.txt')]
            else:
                decoder = Path(__file__).resolve().parent / 'analyze_wfi.py'
                decoder_args = [str(output / 'events.csv'), str(output / 'status.txt'),
                                str(output / 'wfi-events.csv')]
            decode = command(['/usr/bin/python3', str(decoder), *decoder_args], 'observer-analysis', True)
            assert decode.returncode == 0, 'observer analysis failed'
            assert json.loads(decode.stdout)['integrity']['clean'], 'observer capture integrity failed'
        after = snapshot('after')
        policy_fields = ('online', 'current_driver', 'current_governor_ro', 'related_cpus', 'affected_cpus',
                         'scaling_driver', 'scaling_governor', 'scaling_min_freq', 'scaling_max_freq', 'disable')
        assert all(after.get(k) == v for k, v in before.items() if Path(k).name in policy_fields), 'policy or online state changed'
        command(['/usr/bin/journalctl', '--boot', '--dmesg', '--no-pager', '--output=short-monotonic'], 'kernel-log')
        mark('complete', native_packet_requires_review=True, clock_bound_not_exported=True)
    except Exception as error:
        mark('failed', error=repr(error))
        raise
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
                try:
                    child.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill(); child.communicate()
        save('acquisition-record.json', (json.dumps(records, indent=2) + '\n').encode())
        hashes = [f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}' for p in sorted(output.iterdir()) if p.is_file()]
        save('SHA256SUMS', ('\n'.join(hashes) + '\n').encode())
        print(json.dumps({'private_output': str(output), 'last_action': records[-1]['action']}))


if __name__ == '__main__':
    main()
