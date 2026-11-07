#!/usr/bin/env python3
"""Build the ShengUfs probe archive for the elden SM8750 UFS controller.

The catalog entry for ShengUfs is pinned to an SM8550 controller layout. The
board patch in ``scripts/driver-patches/sheng-ufs-sm8750.patch`` adds the SM8750 GCC
branch registers, the SM8750 root partition name and the LUN discovery code
without touching the upstream checkout. This script checks that revision out
into ``build/sheng-ufs/src``, applies the board patch there, compiles
``NativeUfs.cpp`` against the source-kernel ABI and writes the archive where
the kernel build expects it (``build/sheng-ufs/libShengUfs.a``).

Default builds only probe mode. The explicit root-check configuration also
builds the read-only block interface and requires an owned, qualified storage
ABI audit before creating the final archive. Hardware root publication remains
a separate acceptance step.
"""
import argparse
import os
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
ROOT_CHECK = os.environ.get('XNU_ELDEN_UFS_ROOTCHECK') == '1'
PINNED_ROOT = os.environ.get('XNU_ELDEN_UFS_PINNED_ROOT') == '1'
USB_DEBUG = os.environ.get('XNU_ELDEN_USB_DEBUG') == '1'
if USB_DEBUG and not PINNED_ROOT:
    raise SystemExit('current USB prototype uses the qualified pinned-root build context')
if PINNED_ROOT and not ROOT_CHECK:
    raise SystemExit('pinned root requires the full read-only block interface')
if ROOT_CHECK:
    root_name = os.environ.get('XNU_ELDEN_UFS_ROOT_PARTITION', 'ARMADA_BACKUP').strip('"')
    if not root_name or len(root_name) > 35 or not root_name.replace('_','').isalnum():
        raise SystemExit('invalid elden root partition name')
    DEFINES = ['-DNATIVE_UFS_SM8750=1', '-DNATIVE_UFS_READ_ONLY=1', '-DNATIVE_UFS_PROBE_ONLY=0',
               '-DELDEN_INHERITED_UFS_DMA=1', f'-DUFS_ROOT_PARTITION="{root_name}"']
    if PINNED_ROOT:
        if root_name != 'ipados':
            raise SystemExit('pinned profile is restricted to the dedicated ipados partition')
        DEFINES.append('-DELDEN_PINNED_ROOT=1')
    if USB_DEBUG:
        DEFINES.append('-DELDEN_USB_DEBUG=1')
        if all(os.environ.get(name) == '1' for name in ('XNU_OWNER_CACHE_STARTUP', 'XNU_OWNER_DATA_MOUNT', 'XNU_OWNER_BOOT_MANIFEST')):
            DEFINES.append('-DELDEN_OWNER_STARTUP=1')


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
    if ROOT_CHECK:
        audit_input = os.environ.get('ELDEN_STORAGE_ABI_AUDIT')
        if not audit_input:
            raise SystemExit('root-check requires ELDEN_STORAGE_ABI_AUDIT from the qualified owned candidate')
        storage_headers = Path(audit_input).resolve().parent / 'include'
        if not storage_headers.is_dir():
            raise SystemExit('root-check requires the prepared, pinned IOStorageFamily ABI headers')
        command[1:1] = ['-I', str(ROOT / '.cache/xnu-work/osfmk'),
                        '-I', str(storage_headers)]
    return command, record['directory']


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    entry = catalog_entry()
    patch = board_patch()
    source = checkout(entry)
    usb = ROOT / 'scripts/driver-patches/sheng-ufs-elden-usb-debug.patch'
    if usb.is_file() and subprocess.run(['git', 'apply', '--reverse', '--check', str(usb)],
            cwd=source, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
        subprocess.run(['git', 'apply', '--reverse', str(usb)], cwd=source, check=True)
    pinned = ROOT / 'scripts/driver-patches/sheng-ufs-elden-pinned-root.patch'
    if pinned.is_file() and subprocess.run(['git', 'apply', '--reverse', '--check', str(pinned)],
            cwd=source, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
        subprocess.run(['git', 'apply', '--reverse', str(pinned)], cwd=source, check=True)
    # Remove our independent MMIO layer before rechecking older patch context.
    mmio = ROOT / 'scripts/driver-patches/sheng-ufs-elden-mmio-load.patch'
    if mmio.is_file() and subprocess.run(['git', 'apply', '--reverse', '--check', str(mmio)],
            cwd=source, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
        subprocess.run(['git', 'apply', '--reverse', str(mmio)], cwd=source, check=True)
    # The lifecycle layer changes context also used by the earlier root-check
    # patch. Remove just this known layer before testing that earlier layer;
    # unrelated source edits still fail the normal git-apply checks.
    lifecycle = ROOT / 'scripts/driver-patches/sheng-ufs-elden-storage-lifecycle.patch'
    if lifecycle.is_file() and subprocess.run(['git', 'apply', '--reverse', '--check', str(lifecycle)],
            cwd=source, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
        subprocess.run(['git', 'apply', '--reverse', str(lifecycle)], cwd=source, check=True)
    already_root = ROOT_CHECK and subprocess.run(
        ['git','apply','--reverse','--check',str(ROOT / 'scripts/driver-patches/sheng-ufs-elden-rootcheck.patch')],
        cwd=source,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode == 0
    if not already_root and apply_patch(source, patch):
        print(f'applied {patch.name} to {source.relative_to(ROOT)}')
    if ROOT_CHECK:
        extra = ROOT / 'scripts/driver-patches/sheng-ufs-elden-rootcheck.patch'
        apply_patch(source, extra)
        shutil.copyfile(ROOT / 'scripts/driver-patches/EldenUfsIdentity.h', source / 'EldenUfsIdentity.h')
        apply_patch(source, lifecycle)
        apply_patch(source, mmio)
        if PINNED_ROOT:
            for name in ('EldenPinnedRoot.h', 'EldenPinnedRootXnu.inc', 'EldenPinnedRootBridge.inc'):
                shutil.copyfile(ROOT / 'scripts/driver-patches' / name, source / name)
            apply_patch(source, pinned)
        if USB_DEBUG:
            import hashlib
            core = Path(os.environ['ELDEN_DWC3_SOURCE'])
            expected = {'Dwc3.c': 'c7d9c98235d0c2b5422fb1a3e10a4ecc5834bb011c6790a9b2f81ce9b2ea7635',
                        'Dwc3.h': '18dc05fba18820df14cc8e0e6739afa1d8ff364568df8e2c8d52a6a48d4e9f41',
                        'Dwc3Regs.h': '2ceb1e04662f2e65dd05a3a990cf39014feef19f177c11414ed15345c5ffc18d'}
            for name, digest in expected.items():
                if hashlib.sha256((core / name).read_bytes()).hexdigest() != digest:
                    raise SystemExit('generic USB core identity changed: ' + name)
                shutil.copyfile(core / name, source / name)
            shutil.copyfile(core / 'LICENSE.m1n1', source / 'LICENSE.m1n1')
            shutil.copyfile(Path(os.environ['ELDEN_USB_RESOURCE_HEADER']), source / 'EldenUsbResources.h')
            shutil.copyfile(ROOT / 'scripts/driver-patches/EldenUsbDebugXnu.inc', source / 'EldenUsbDebugXnu.inc')
            apply_patch(source, usb)
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
    if 'IOBlockStorageDevice' in imports and not ROOT_CHECK:
        raise SystemExit('Probe build unexpectedly requires prelinked IOStorageFamily')
    if ROOT_CHECK and 'IOBlockStorageDevice' not in imports:
        raise SystemExit('Root-check build did not include the expected block-device interface')
    if ROOT_CHECK:
        required = ('ELDEN_STORAGE_ABI_AUDIT', 'ELDEN_STORAGE_ABI_CANDIDATE', 'ELDEN_STORAGE_ABI_PLAN')
        if not all(os.environ.get(name) for name in required):
            raise SystemExit('root-check requires qualified storage audit, candidate and prelink plan paths')
        subprocess.run([sys.executable, ROOT / 'scripts/build-elden-ufs-bindings.py',
            '--audit', os.environ[required[0]], '--candidate', os.environ[required[1]],
            '--plan', os.environ[required[2]], '--directory', output], check=True)
        if USB_DEBUG:
            cobj = output / 'EldenDwc3.o'
            ccommand, cdirectory = compile_command(source / 'Dwc3.c', cobj)
            filtered = []
            skip = False
            for item in ccommand:
                if skip:
                    skip = False
                    continue
                if item == '-x':
                    skip = True
                    continue
                if item in ('-fno-rtti', '-fno-exceptions', '-fapple-kext', '-fsized-deallocation', '-fno-c++-static-destructors') or item.startswith(('-std=', '-xc++', '--driver-mode=')):
                    continue
                filtered.append(item)
            ccommand = filtered
            # clang applies -x to subsequent source arguments only.
            ccommand[1:1] = ['-x', 'c', '-std=gnu11']
            (output / 'usb-compile-command.json').write_text(json.dumps(ccommand, indent=2)+'\n')
            subprocess.run(ccommand, cwd=cdirectory, check=True)
            subprocess.run(['xcrun', 'ar', 'rcs', str(output/'libShengUfs.a'), str(cobj)], check=True)
        return
    archive = output / f'lib{IDENTIFIER}.a'
    archive.unlink(missing_ok=True)
    subprocess.run(['xcrun', 'ar', 'rcs', str(archive), str(obj)], check=True)
    print(f'{archive.relative_to(ROOT)} ({archive.stat().st_size} bytes)')


if __name__ == '__main__':
    main()
