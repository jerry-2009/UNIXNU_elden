"""Compile UFS IRQ/wait and SPI registration in the source-rebuilt OS17 contexts.

This produces two reviewed objects, not a flashable image. No old external v99
package is needed: --clean-build is the repository's source-built baseline.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from replay_xnu_objects import sections, global_symbols

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'drivers/EldenUfsWait'))
from Source import source, commands, recovery, cpu_source, CPU_SHA, COMMANDS_SHA
from EarlyStorageSource import RECOVERY_SHA
from MediumSource import INPUTS


def read(p):
    return json.loads(p.read_text())


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def exports(p):
    return {k for k, v in global_symbols(p).items() if v[0] & 0x0e}


def compile_units(base, parent, out, llvm, trial=False):
    objects, records, archives, inherited, new_imports = {}, {}, {}, {}, {}
    native = read(base / 'native/build/results.json')
    capture = read(base / 'native/capture.json')
    current = read(base / 'units/result.json')
    plan = read(ROOT / 'profiles/current-build/plan.json')
    if not current['complete'] or current['profile_sha256'] != sha(ROOT / 'profiles/current-build/plan.json'):
        raise ValueError('Current units changed')
    derive=source
    if trial:
        from TrialSource import source as derive, completion
        (out/'source/EldenUfsCompletion.inc').write_bytes(completion())
    for name, data in {'NativeUfs.cpp': derive(), 'ArmCpu.cpp': cpu_source(),
                       'RootCommands.h': commands(), 'EldenSdamRecovery.inc': recovery()}.items():
        (out / 'source' / name).write_bytes(data)
    for unit in ('ArmCpu', 'ShengUfs'):
        if unit == 'ShengUfs':
            row = current['units'][unit]
            old = Path(row['object'])
            command = list(row['command'])
            cwd = base / 'units/working' / unit
            job = next(j for j in plan['jobs'] if j['name'] == unit)
            if not row['accepted'] or not row['closed_overlay'] or sha(old) != row['sha256']:
                raise ValueError('Current UFS object changed')
            if sections(old) != job['expected_sections'] or global_symbols(old) != job['expected_symbols']:
                raise ValueError('Current UFS capture differs from source replay')
            expected = {'NativeUfs.cpp': INPUTS['ShengUfs'][1], 'RootCommands.h': COMMANDS_SHA,
                        'EldenSdamRecovery.inc': RECOVERY_SHA}
            member, archive = 'ShengUfs.o', 'libShengUfs.a'
            added = {'_elden_ufs_wait_shutdown'}
        else:
            rows = [r for r in native.values() if r['source'].endswith('/ArmCpu.cpp')]
            if len(rows) != 1:
                raise ValueError('ArmCpu source capture ambiguous')
            row = rows[0]
            old = Path(row['output'])
            command = list(row['command'])
            if not row['accepted'] or sha(old) != row['sha256'] or row.get('objcopy') or row.get('postprocess'):
                raise ValueError('Unexpected ArmCpu compile context')
            job = next(j for j in capture['jobs'] if j['file'] == row['source'])
            virtual = read(ROOT / 'profiles/v91/native-build/plan.json')['virtual_root'].rstrip('/')
            if not job['directory'].startswith(virtual + '/'):
                raise ValueError('ArmCpu build directory outside virtual tree')
            rel = job['directory'][len(virtual) + 1:]
            if rel.startswith('research/'):
                rel = 'records/' + rel[9:]
            cwd = (base / 'native/build/project' / rel).resolve()
            if not cwd.is_relative_to((base / 'native/build/project').resolve()) or not cwd.is_dir():
                raise ValueError('ArmCpu reconstructed directory missing')
            member, archive = Path(job['original_object']).name, 'libArmCpu.a'
            if member != 'ArmCpu.o':
                raise ValueError('Unexpected ArmCpu member')
            expected = {'ArmCpu.cpp': CPU_SHA}
            added = {'_armcpu_spi_mask'}
        at = command.index('-ivfsoverlay') + 1
        overlay = read(Path(command[at]))
        if overlay.get('fallthrough') is not False:
            raise ValueError('Open source overlay')
        bindings, extra = {n: [] for n in expected}, []
        for item in overlay['roots']:
            path = Path(item['external-contents'])
            inherited[str(path)] = sha(path)
            if unit == 'ShengUfs' and (path.resolve().parent != (base / 'units/source').resolve()
                                     or path.name not in plan['providers'] or sha(path) != path.name):
                raise ValueError('UFS provider differs')
            name = Path(item['name']).name
            if name not in expected:
                continue
            if sha(path) != expected[name]:
                raise ValueError('Wrong frozen source: ' + name)
            item['external-contents'] = str(out / 'source' / name)
            bindings[name].append(item['name'])
            if name == 'NativeUfs.cpp':
                for folder, header in [('EldenStorageMedium', 'EldenStorageMedium.h'),
                                       ('EldenUfsWait', 'EldenUfsCompletion.inc')]:
                    extra.append({'type': 'file', 'name': str(Path(item['name']).parent / header),
                                  'external-contents': str(out/'source'/header if trial and header=='EldenUfsCompletion.inc' else ROOT / 'drivers' / folder / header)})
                if trial:
                    for header in ('EldenUfsReadTrial.inc','UfsReadTrial.h'):
                        extra.append({'type':'file','name':str(Path(item['name']).parent/header),
                                      'external-contents':str(ROOT/'drivers/EldenUfsWait'/header)})
        if not all(bindings.values()):
            raise ValueError('Derived input not bound: ' + repr(bindings))
        known = {r['name'] for r in overlay['roots']}
        for item in extra:
            if item['name'] in known:
                raise ValueError('Overlay header collision')
            overlay['roots'].append(item)
            known.add(item['name'])
        vfs = out / (unit + '.overlay.json')
        vfs.write_text(json.dumps(overlay, indent=2) + '\n')
        command[at] = str(vfs)
        obj = out / member
        command[command.index('-o') + 1] = str(obj)
        env = dict(os.environ, CCC_OVERRIDE_OPTIONS='+-Wno-unknown-warning-option')
        env.pop('SDKROOT', None)
        r = subprocess.run(command, cwd=cwd, env=env, capture_output=True)
        (out / (unit + '.log')).write_bytes(r.stdout + r.stderr)
        r.check_returncode()
        if exports(obj) != exports(old) | added:
            raise ValueError('Unexpected exports: ' + repr(exports(obj) ^ (exports(old) | added)))
        before, after = sections(old), sections(obj)
        init = {n for n in before if n.endswith('/__mod_init_func')}
        if init != {n for n in after if n.endswith('/__mod_init_func')} or any(before[n][:2] != after[n][:2] for n in init):
            raise ValueError('Initializer layout changed')
        reloc = subprocess.check_output([str(llvm / 'llvm-objdump'), '--reloc', str(obj)], text=True)
        if init:
            prior = subprocess.check_output([str(llvm / 'llvm-objdump'), '--reloc', str(old)], text=True)
            pattern = r'RELOCATION RECORDS FOR \[__mod_init_func\]:\n(.*?)(?:\n\n|\Z)'
            x, y = re.search(pattern, prior, re.S), re.search(pattern, reloc, re.S)
            if not x or not y or x[1] != y[1]:
                raise ValueError('Initializer targets changed')
        asm = subprocess.check_output([str(llvm / 'llvm-objdump'), '-dr', str(obj)], text=True)
        (out / (unit + '.asm')).write_text(asm)
        (out / (unit + '.reloc')).write_text(reloc)
        if re.search(r'^\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+.*\b[qvdshb]\d+(?:\b|\.)', asm, re.M):
            raise ValueError('FP/SIMD present')
        objects[member], archives[member] = obj, archive
        imports = lambda p: {n for n, v in global_symbols(p).items() if not v[0] & 0x0e}
        new_imports[member] = imports(obj) - imports(old)
        records[unit] = {'object_sha256': sha(obj), 'command': command, 'cwd': str(cwd),
                         'source_sha256': sha(out / 'source' / ('ArmCpu.cpp' if unit == 'ArmCpu' else 'NativeUfs.cpp')),
                         'bindings': bindings, 'initializers_preserved': True,
                         'new_exports': sorted(added), 'new_imports': sorted(new_imports[member]),
                         'prior_object_sha256': sha(old), 'prior_object':str(old), 'warnings': r.stderr.count(b'warning:')}
        if unit=='ShengUfs':
            records[unit].update(recovery_sha256=sha(out/'source/EldenSdamRecovery.inc'),
                                 commands_sha256=sha(out/'source/RootCommands.h'),
                                 completion_sha256=sha(out/'source/EldenUfsCompletion.inc') if trial else sha(ROOT/'drivers/EldenUfsWait/EldenUfsCompletion.inc'))
    available = exports(parent / 'native.macho')
    for obj in objects.values():
        available |= exports(obj)
    for name, obj in objects.items():
        # Existing unresolved imports are bound by the qualified original-Apple
        # prelink map, not the native nlist. Check only changes here; full prelink
        # remains mandatory before an image can be tested.
        if new_imports[name] - available:
            raise ValueError('Unavailable new native imports: ' + repr(new_imports[name] - available))
    for path, digest in inherited.items():
        if sha(Path(path)) != digest:
            raise ValueError('Source changed during compilation')
    return objects, records, archives, inherited


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for arg in ('clean-build', 'parent-build', 'llvm', 'output'):
        p.add_argument('--' + arg, type=Path, required=True)
    a = p.parse_args()
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    (out / 'source').mkdir()
    objects, records, archives, inputs = compile_units(a.clean_build.resolve(), a.parent_build.resolve(), out, a.llvm.resolve())
    report = {'profile': 'ufs-wait-objects', 'passed': True, 'native_objects': records,
              'archives': archives, 'inherited_sources': inputs,
              'whole_kernel': False, 'hardware': False}
    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'passed': True, 'objects': {name: sha(path) for name, path in objects.items()}}))


if __name__ == '__main__':
    main()
