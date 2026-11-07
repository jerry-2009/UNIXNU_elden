#!/usr/bin/env python3
"""Bind NativeUfsBlock to the audited original iOS IOBlockStorageDevice.

The public reference object only describes the ABI. It is never linked into
the kernel. All bindings below point to the owned candidate's original
IOStorageFamily code/data, using its fixed NativePrelink slide.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'kits/XnuPrelink'))
import native_prelink as np

ORIGINAL_SHA = 'f18b4df865405f2a287b84977d7aca745e056d656d9fc9df1662970ce2969de7'
STORAGE_REVISION = 'e45fbe30a7879e0b16e26dddb78538f1b00e0bff'


def require(value, message):
    if not value:
        raise SystemExit(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--directory', type=Path, required=True)
    args = parser.parse_args()
    out = args.directory.resolve()
    audit = json.loads(args.audit.read_text())
    plan = json.loads(args.plan.read_text())
    candidate_sha = digest(args.candidate)
    require(candidate_sha == audit['candidate_sha256'] == plan['candidate_sha256'],
            'Storage audit, candidate and NativePrelink plan must have the same identity')
    require(plan['original_sha256'] == ORIGINAL_SHA and
            audit['public_source_revision'] == STORAGE_REVISION and
            audit['original_executable_code_unchanged'] and
            audit['live_native_4k'] and audit['method_slots'] == 190 and
            audit['abstract_complete_destructors_trap'] and
            audit['live_instance_sizes'] == dict(IOBlockStorageDevice=0x90, IOService=0x88),
            'First qualify the original storage code, dispatch and live class metadata')
    observed = audit.get('sctlr_instruction_observation', {})
    require(observed.get('encoding') == '0xd5181000' and
            observed.get('input_x0') == observed.get('rsp_after') and
            observed.get('guest_code_modified') is False,
            'Storage audit lacks the original kernel SCTLR instruction observation')

    component = 'NativeUfsBlock'
    mangled = str(len(component)) + component
    obj_path = out / 'ShengUfs.o'
    obj = obj_path.read_bytes()
    image = np.macho(obj)
    require(image['kind'] == 1 and struct.unpack_from('<3I', obj)[1:] == (0x100000c, 0),
            'Expected an ordinary ARM64 concrete UFS object')
    offset = next(at for command, at, size in image['commands'] if command == 2)
    sy, count, st, _ = struct.unpack_from('<4I', obj, offset + 8)
    symbols = []
    for i in range(count):
        ix, kind, _, _, value = struct.unpack_from('<IBBHQ', obj, sy + i * 16)
        name = obj[st + ix:obj.index(b'\0', st + ix)].decode()
        symbols.append((name, value, kind))
    vtable = next(value for name, value, kind in symbols if name == '__ZTV' + mangled)
    relocations = {}
    for segment in image['segments']:
        for section in segment['sections']:
            if section['va'] <= vtable < section['va'] + section['size']:
                ro, rc = struct.unpack_from('<II', obj, section['command_offset'] + 56)
                for i in range(rc):
                    address, word = struct.unpack_from('<II', obj, ro + i * 8)
                    if word >> 27 & 1 and word >> 28 == 0 and word >> 25 & 3 == 3:
                        relocations[section['va'] + address] = symbols[word & 0xffffff][0]
    compiled = [relocations.get(vtable + 16 + i * 8) for i in range(190)]
    require(all(compiled) and vtable + 16 + 190 * 8 not in relocations and
            '___cxa_pure_virtual' not in compiled,
            'Concrete UFS class has missing, additional or pure virtual methods')
    names = list(dict.fromkeys(compiled + [row['reference_name'] for row in audit['methods']]))
    demangled = subprocess.check_output(['xcrun', 'c++filt', '--no-strip-underscore'],
        input='\n'.join(name[1:] for name in names) + '\n', text=True).splitlines()
    require(len(demangled) == len(names), 'Incomplete C++ signature demangling')
    readable = dict(zip(names, demangled))
    (out / 'dispatch-audit.json').write_text(json.dumps([
        dict(slot=row['slot'], expected=row['reference_name'], actual=actual,
             expected_signature=readable[row['reference_name']], actual_signature=readable[actual])
        for row, actual in zip(audit['methods'], compiled)], indent=2) + '\n')
    overrides = 0
    for row, actual in zip(audit['methods'], compiled):
        expected = row['reference_name']
        own = actual.startswith(('__ZN' + mangled, '__ZNK' + mangled))
        if expected == '___cxa_pure_virtual':
            require(own, 'A required UFS transport operation is not implemented')
        elif actual != expected:
            require(own and (row['slot'] in (0, 1) or ('::' in readable[actual] and '::' in readable[expected] and
                    readable[actual].split('::', 1)[1] == readable[expected].split('::', 1)[1])),
                    'Concrete UFS dispatch signature mismatch at slot ' + str(row['slot']) +
                    ': ' + readable[actual] + ' versus ' + readable[expected])
        overrides += own

    possible = {row['reference_name']: int(row['candidate_target'], 16)
                for row in audit['methods'] if not row['kernel_names'] or
                'IOBlockStorageDevice' in row['reference_name']}
    possible.update({
        '__ZN20IOBlockStorageDeviceC2EPK11OSMetaClass': int(audit['original_protected_constructor'], 16),
        '__ZN20IOBlockStorageDeviceD2Ev': int(audit['original_base_destructor'], 16),
        '__ZN20IOBlockStorageDevice10gMetaClassE': int(audit['original_metaclass'], 16),
        '__ZTV20IOBlockStorageDevice': int(audit['vtable'], 16),
    })
    undefined = [name for name, value, kind in symbols
                 if kind == 1 and 'IOBlockStorageDevice' in name]
    require(undefined and all(name in possible for name in undefined),
            'Unqualified original IOBlockStorageDevice import')
    # The abstract class's D1/D0 slots are BRK traps, not usable destructors.
    require(not any(re.search(r'IOBlockStorageDeviceD[01]Ev$', name) for name in undefined),
            'UFS must only call the qualified original base D2 destructor')
    bindings = {name: possible[name] for name in undefined}
    candidate = args.candidate.read_bytes()
    native = np.macho(candidate)
    for name, address in bindings.items():
        np.backed_offset(native['segments'], address, 8, len(candidate))
    assembly = out / 'original-bindings.S'
    assembly.write_text(''.join(f'.globl {name}\n.set {name}, {value:#x}\n'
                               for name, value in sorted(bindings.items())))
    bound_obj = out / 'original-bindings.o'
    subprocess.run(['xcrun', 'clang', '-target', 'arm64-apple-ios17.0', '-Werror',
                    '-Wno-incompatible-sysroot', '-c', assembly, '-o', bound_obj], check=True)
    archive = out / 'libShengUfs.a'
    archive.unlink(missing_ok=True)
    subprocess.run(['xcrun', 'ar', 'rcs', archive, obj_path, bound_obj], check=True)
    record = dict(original_candidate_sha256=candidate_sha, original_sha256=ORIGINAL_SHA,
        audit_sha256=digest(args.audit), plan_sha256=digest(args.plan),
        public_source_revision=STORAGE_REVISION, compiled_object_sha256=digest(obj_path),
        binding_object_sha256=digest(bound_obj), archive_sha256=digest(archive),
        virtual_methods_checked=190, pure_virtual_operations_implemented=14,
        concrete_overrides=overrides, unresolved_original_imports=0,
        bindings={name: hex(value) for name, value in sorted(bindings.items())},
        original_code_modified=False, live_base_metadata_qualified=True,
        actual_io_qualified=False, hardware_tested=False)
    (out / 'bindings.json').write_text(json.dumps(record, indent=2) + '\n')
    print(f'PASS: 190 concrete UFS slots, {overrides} overrides, {len(bindings)} genuine original imports')
    print(f'{archive} ({archive.stat().st_size} bytes); UFS hardware I/O remains untested')


if __name__ == '__main__':
    main()
