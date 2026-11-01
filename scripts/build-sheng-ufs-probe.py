#!/usr/bin/env python3
"""Build the ShengUfs probe archive for the elden SM8750 UFS controller.

The catalog entry for ShengUfs is pinned to an SM8550 controller layout. The
board patch in ``scripts/driver-patches/sheng-ufs-sm8750.patch`` adds the SM8750 GCC
branch registers, the SM8750 root partition name and the LUN discovery code
without touching the upstream checkout. This script checks that revision out
into ``build/sheng-ufs/src``, applies the board patch there, compiles
``NativeUfs.cpp`` against the source-kernel ABI and writes the archive where
the kernel build expects it (``build/sheng-ufs/libShengUfs.a``).

Only probe mode is built here: no personality installs a block device and no
IOBlockStorageDevice import is allowed. Root publication stays a later stage.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import struct
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]
RECORD = ROOT / 'build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/iokit/DEVELOPMENT/IOPlatformExpert.cpo.json'
IDENTIFIER = 'ShengUfs'
DEFINES = ['-DNATIVE_UFS_SM8750=1', '-DNATIVE_UFS_READ_ONLY=1', '-DNATIVE_UFS_PROBE_ONLY=1']


def catalog_entry():
    catalog = tomllib.loads((ROOT / 'components.toml').read_text())
    for entry in catalog['component']:
        if entry['id'] == IDENTIFIER:
            return entry
    raise SystemExit(f'{IDENTIFIER} is missing from components.toml')


def board_patch():
    patch = ROOT / 'scripts/driver-patches/sheng-ufs-sm8750.patch'
    if not patch.is_file():
        raise SystemExit(f'SM8750 board patch is missing: {patch}')
    return patch


def checkout(entry):
    source = ROOT / 'build/sheng-ufs/src'
    repository, revision = entry['repository'], entry['revision']
    if (source / '.git').is_dir():
        head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=source, text=True).strip()
        if head == revision:
            return source
        subprocess.run(['git', 'fetch', '--quiet', 'origin', revision], cwd=source, check=True)
    else:
        shutil.rmtree(source, ignore_errors=True)
        source.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(['git', 'clone', '--quiet', repository, str(source)], check=True)
    subprocess.run(['git', 'checkout', '--quiet', '--force', revision], cwd=source, check=True)
    subprocess.run(['git', 'clean', '-qfd'], cwd=source, check=True)
    return source


def apply_patch(source, patch):
    check = subprocess.run(['git', 'apply', '--check', str(patch)], cwd=source,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if check.returncode:
        reverse = subprocess.run(['git', 'apply', '--reverse', '--check', str(patch)], cwd=source,
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        if reverse.returncode:
            raise SystemExit(f'board patch does not apply:\n{check.stdout[-2000:]}')
        return False
    subprocess.run(['git', 'apply', str(patch)], cwd=source, check=True)
    return True


def compile_command(source_file, destination):
    record = json.loads(RECORD.read_text().strip().rstrip(','))
    command, arguments, index = [], record['arguments'], 0
    while index < len(arguments):
        value = arguments[index]
        if value == record['file']:
            command.append(str(source_file))
        elif value == '-o':
            command.extend(['-o', str(destination)])
            index += 1
        elif value == '-Xclang' and arguments[index + 1].startswith('-W'):
            index += 1
        elif not value.startswith('-W'):
            command.append(value)
        index += 1
    command.extend(['-Wall', '-Wextra', '-Wno-unused-parameter', '-Wno-unused-function',
                    '-Wno-c99-designator', '-Wno-reorder-init-list',
                    '-Wno-deprecated-enum-enum-conversion', '-Wno-unnecessary-virtual-specifier',
                    '-I', str(ROOT / '.cache/xnu-work/osfmk'), '-I', str(source_file.parent)])
    command.extend(DEFINES)
    return command, record['directory']


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    entry = catalog_entry()
    patch = board_patch()
    source = checkout(entry)
    if apply_patch(source, patch):
        print(f'applied {patch.name} to {source.relative_to(ROOT)}')
    output = ROOT / 'build/sheng-ufs'
    output.mkdir(parents=True, exist_ok=True)
    obj = output / f'{IDENTIFIER}.o'
    command, directory = compile_command(source / 'NativeUfs.cpp', obj)
    (output / 'compile-command.json').write_text(json.dumps(command, indent=2) + '\n')
    result = subprocess.run(command, cwd=directory, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    (output / 'compile.log').write_text(result.stdout)
    if result.returncode:
        sys.stderr.write(result.stdout[-4000:])
        raise SystemExit('ShengUfs probe build failed')
    data = obj.read_bytes()
    magic, cpu, subtype, kind = struct.unpack_from('<4I', data)
    if (magic, cpu, subtype, kind) != (0xfeedfacf, 0x100000c, 0, 1):
        raise SystemExit('ShengUfs: expected an ordinary ARM64 Mach-O object')
    imports = subprocess.check_output(['xcrun', 'nm', '-u', obj], text=True)
    if 'IOBlockStorageDevice' in imports:
        raise SystemExit('Probe build unexpectedly requires prelinked IOStorageFamily')
    archive = output / f'lib{IDENTIFIER}.a'
    archive.unlink(missing_ok=True)
    subprocess.run(['xcrun', 'ar', 'rcs', str(archive), str(obj)], check=True)
    print(f'{archive.relative_to(ROOT)} ({archive.stat().st_size} bytes)')


if __name__ == '__main__':
    main()
