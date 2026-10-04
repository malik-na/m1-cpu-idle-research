#!/usr/bin/env python3
"""Compare retained AArch64 object and optional linked-kernel bytes offline."""

import argparse
import hashlib
import json
import struct
from pathlib import Path


def digest(data):
    return hashlib.sha256(data).hexdigest()


def elf(path, linked=False):
    data = path.read_bytes()
    header = struct.unpack_from('<16sHHIQQQIHHHHHH', data)
    if (header[0][:6] != b'\x7fELF\x02\x01' or header[2] != 183 or
            header[1] not in ((2, 3) if linked else (1,))):
        raise ValueError('expected ELF64 little-endian AArch64 ' +
                         ('linked image' if linked else 'relocatable object'))
    offset, entry_size, count, names_index = header[6], header[11], header[12], header[13]
    if entry_size != 64 or not 0 < names_index < count:
        raise ValueError('unsupported ELF section table')
    headers = [struct.unpack_from('<IIQQQQIIQQ', data, offset + i * entry_size) for i in range(count)]

    def contents(h):
        if h[1] == 8:  # SHT_NOBITS has no bytes in the file.
            return b''
        result = data[h[4]:h[4] + h[5]]
        if len(result) != h[5]:
            raise ValueError('truncated ELF section')
        return result

    names = contents(headers[names_index])

    def string(table, start):
        end = table.find(b'\0', start)
        if end < start:
            raise ValueError('invalid ELF string')
        return table[start:end].decode('ascii')

    sections = []
    for index, h in enumerate(headers):
        sections.append({'name': string(names, h[0]), 'type': h[1], 'flags': h[2], 'address': h[3],
                         'index': index, 'link': h[6], 'info': h[7], 'entry_size': h[9],
                         'bytes': contents(h)})
    symbols = []
    for section in sections:
        if section['type'] != 2:
            continue
        if section['entry_size'] != 24:
            raise ValueError('unsupported symbol size')
        strings = sections[section['link']]['bytes']
        for i in range(0, len(section['bytes']), 24):
            name, info, other, shndx, value, size = struct.unpack_from('<IBBHQQ', section['bytes'], i)
            symbols.append({'name': string(strings, name), 'type': info & 15,
                            'section': shndx, 'value': value, 'size': size})
    return data, sections, symbols


def executable_payloads(sections):
    result = {}
    for section in sections:
        if not section['flags'] & 4:  # SHF_EXECINSTR
            continue
        result[section['name']] = section['bytes']
        for relocation in sections:
            if relocation['type'] in (4, 9) and relocation['info'] == section['index']:
                result[relocation['name']] = relocation['bytes']
    if not result:
        raise ValueError('object contains no executable sections')
    return result


def deep_wfi(sections, symbols, linked=False):
    matches = [s for s in symbols if s['name'] == 'apple_cpu_deep_wfi']
    if len(matches) != 1:
        raise ValueError('missing or ambiguous deep-WFI symbol')
    symbol = matches[0]
    section = sections[symbol['section']]
    later = [s['value'] for s in symbols if s['type'] == 2 and
             s['section'] == symbol['section'] and s['value'] > symbol['value']]
    end = min(later) if later else section['address'] + len(section['bytes'])
    expected_section = '.text' if linked else '.cpuidle.text'
    if section['name'] != expected_section or end - symbol['value'] != 100:
        raise ValueError('unexpected deep-WFI bounds; review this build before comparing')
    start = symbol['value'] - section['address']
    return section['bytes'][start:end - section['address']]


def compare(root, full_source=False, vmlinux=None):
    scope = 'full-source Kbuild object bytes' if full_source else 'preliminary object bytes'
    result = {'scope': scope + (' and linked-kernel checks; no native execution'
                              if vmlinux is not None else '; no final link or native execution'),
              'objects': {}, 'disabled_executable_changes': {}, 'deep_wfi': {}}
    loaded = {}
    for variant, names in (
        ('pristine', ('cpuidle-apple', 'apple-soc-cpufreq')),
        ('off', ('cpuidle-apple', 'apple-soc-cpufreq')),
        ('on', ('cpuidle-apple', 'apple-soc-cpufreq', 'apple-apsc-observer', 'apple-counter-qualification')),
    ):
        for name in names:
            if full_source:
                driver = ('soc/apple' if name == 'apple-counter-qualification' else
                          'cpufreq' if name == 'apple-soc-cpufreq' else 'cpuidle')
                path = root / ('build-' + variant) / 'drivers' / driver / (name + '.o')
            else:
                path = root / ('objects-' + variant) / (name + '.o')
            loaded[variant, name] = elf(path)
            result['objects'][str(path.relative_to(root))] = digest(loaded[variant, name][0])
    for name in ('cpuidle-apple', 'apple-soc-cpufreq'):
        original = executable_payloads(loaded['pristine', name][1])
        disabled = executable_payloads(loaded['off', name][1])
        result['disabled_executable_changes'][name] = sorted(
            key for key in original.keys() | disabled.keys() if original.get(key) != disabled.get(key))
    for variant in ('pristine', 'off', 'on'):
        data, sections, symbols = loaded[variant, 'cpuidle-apple']
        routine = deep_wfi(sections, symbols)
        result['deep_wfi'][variant] = {'bytes': len(routine), 'sha256': digest(routine), 'hex': routine.hex()}
    if vmlinux is not None:
        data, sections, symbols = elf(vmlinux, linked=True)
        routine = deep_wfi(sections, symbols, linked=True)
        result['deep_wfi']['linked'] = {'bytes': len(routine), 'sha256': digest(routine), 'hex': routine.hex()}
        required = ('apple_apsc_observer_idle_enter', 'apple_apsc_observer_idle_exit',
                    'apple_apsc_observer_dvfs_write', 'apple_apsc_observer_cpu_pm_fail',
                    'apsc_observer_init', 'cq_target', 'cq_cpu_metadata', 'cq_init')
        present = {s['name'] for s in symbols if 0 < s['section'] < len(sections)}
        missing = sorted(set(required) - present)
        if missing:
            raise ValueError('missing linked instrument symbols: ' + ', '.join(missing))
        result['linked_vmlinux'] = {'sha256': digest(data), 'required_symbols_present': list(required)}
    if full_source:
        result['configuration_sha256'] = {
            variant: digest((root / ('build-' + variant) / '.config').read_bytes())
            for variant in ('pristine', 'off', 'on')
        }
    else:
        result['copied_header_config_sha256'] = digest((root / 'header-build/.config').read_bytes())
    if any(result['disabled_executable_changes'].values()):
        raise ValueError('disabled driver instructions or relocations differ')
    if {x['sha256'] for x in result['deep_wfi'].values()} != {
        'c8fd716fccb949e9f35aa2937a87787942b39f0b5df5e088d46f88253479b88c'
    }:
        raise ValueError('deep-WFI bytes differ from the declared baseline')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('build_root', type=Path)
    parser.add_argument('--full-source', action='store_true', help='use the complete-source build-pristine/off/on directories')
    parser.add_argument('--vmlinux', type=Path, help='also verify linked WFI bytes and required instrument symbols')
    args = parser.parse_args()
    print(json.dumps(compare(args.build_root, args.full_source, args.vmlinux), indent=2))
