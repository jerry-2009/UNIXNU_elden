#!/usr/bin/env python3
"""Reconstruct the v91 firmware from Git objects in a new directory; no device I/O."""
from pathlib import Path
import argparse
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import PurePosixPath
from firmware_contract import verify_firmware

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / 'profiles/v91/firmware-build'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stage_crypto_package(source, destination, expected):
    """Copy the pinned external inputs under an EDK II package search root."""
    source = source.resolve(strict=True)
    destination = destination.resolve()
    if destination.exists():
        raise ValueError('Staged CryptoBin destination already exists')
    destination.mkdir(parents=True)
    expected_names = set(expected)
    for relative, digest in expected.items():
        name = PurePosixPath(relative)
        if name.is_absolute() or '..' in name.parts or '\\' in relative or ':' in relative:
            raise ValueError('Unsafe CryptoBin manifest path: ' + relative)
        original = source.joinpath(*name.parts)
        if (original.is_symlink() or not original.is_file() or
                not original.resolve(strict=True).is_relative_to(source)):
            raise ValueError('CryptoBin source path is not a regular package member: ' + relative)
        if sha(original) != digest:
            raise ValueError('CryptoBin input mismatch: ' + relative)
        staged = destination.joinpath(*name.parts)
        staged.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, staged)
        if sha(staged) != digest:
            raise ValueError('Staged CryptoBin input mismatch: ' + relative)
    actual_names = {
        path.relative_to(destination).as_posix()
        for path in destination.rglob('*')
        if path.is_file()
    }
    if actual_names != expected_names:
        raise ValueError('Staged CryptoBin package has unexpected files')
    return dict(
        destination=destination.relative_to(destination.parents[1]).as_posix(),
        files=len(expected_names),
        files_sha256=sha256_json(expected),
        verified=True,
    )


def sha256_json(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def git(repository, *args):
    return subprocess.check_output(['git', '-C', str(repository), *args])


def install_clang_wrapper(llvm, wrappers, project, plan):
    target = wrappers / 'clang'
    if target.exists() or target.is_symlink():
        raise ValueError('Compiler wrapper path must be new')
    clocks = {str(project / 'third_party/mu_wide_platforms' / name): epoch
              for name, epoch in plan['compiler_clock_epochs'].items()}
    target.write_text('#!' + sys.executable + '\nimport sys,os\n'
                      'a=sys.argv[1:]\nclocks=' + repr(clocks) + '\n'
                      'env=dict(os.environ)\n'
                      'for arg in a:\n'
                      ' if arg in clocks:env["SOURCE_DATE_EPOCH"]=str(clocks[arg])\n'
                      'os.execve(' + repr(str(llvm / 'clang')) + ',['
                      + repr(str(llvm / 'clang')) + ']+a+["-fno-file-reproducible"],env)\n')
    target.chmod(0o755)


def export(repository, commit, destination, records, submodules=None):
    """Read immutable objects, never reset or copy the caller's working changes."""
    actual = git(repository, 'rev-parse', commit + '^{commit}').decode().strip()
    if actual != commit:
        raise ValueError('A full commit identity is required')
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(git(repository, 'archive', commit))) as archive:
        archive.extractall(destination, filter='data')
    records.append({'commit': commit, 'destination': str(destination)})
    for item in git(repository, 'ls-tree', '-rz', commit).split(b'\0'):
        if not item:
            continue
        meta, name = item.split(b'\t', 1)
        mode, kind, object_id = meta.decode().split()
        relative = name.decode()
        if mode != '160000' or (submodules is not None and relative not in submodules):
            continue
        export(repository / relative, object_id, destination / relative, records)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mu-root', type=Path, required=True)
    parser.add_argument('--unixnu-root', type=Path, required=True)
    parser.add_argument('--crypto-path', type=Path, required=True)
    parser.add_argument('--llvm', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--jobs', type=int, default=4)
    args = parser.parse_args()
    plan = json.loads((PROFILE / 'plan.json').read_text())
    out = args.output.resolve()
    if out.exists():
        raise ValueError('Output must be a new directory')
    llvm = args.llvm.resolve(strict=True)
    for name in ('clang', 'lld-link', 'llvm-lib', 'llvm-rc'):
        if not (llvm / name).is_file():
            raise ValueError('Missing LLVM tool: ' + name)
    crypto = args.crypto_path.resolve(strict=True)
    for relative, expected in plan['crypto_files'].items():
        if sha(crypto / relative) != expected:
            raise ValueError('Crypto input mismatch: ' + relative)
    for relative, expected in plan['repository_files'].items():
        if sha(ROOT / relative) != expected:
            raise ValueError('Frozen repository source changed: ' + relative)
    out.mkdir(parents=True)
    project = out / 'project'
    mu = project / 'third_party/mu_wide_platforms'
    unixnu = project / 'third_party/UniXNU'
    records = []
    export(args.mu_root.resolve(strict=True), plan['mu_commit'], mu, records)
    export(args.unixnu_root.resolve(strict=True), plan['unixnu_commit'], unixnu,
           records, submodules=['drivers/DarwinBoot'])
    darwin = git(args.unixnu_root / 'drivers/DarwinBoot', 'rev-parse',
                 plan['darwin_commit'] + '^{commit}').decode().strip()
    if darwin != plan['darwin_commit']:
        raise ValueError('DarwinBoot input mismatch')
    # GenFds resolves DSC includes through PACKAGES_PATH. A CryptoBin path
    # outside those roots is shortened as a workspace-relative include by
    # BaseTools. Stage only the hash-locked manifest into this disposable
    # source workspace, then pass its short in-workspace package path.
    staged_crypto = mu / 'Platforms' / 'EldenBaseCrypto'
    crypto_stage = stage_crypto_package(args.crypto_path, staged_crypto,
                                       plan['crypto_files'])
    for relative in plan['repository_files']:
        source = ROOT / relative
        destination = project / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    for name, target in [('mu_wide_platforms', mu), ('UniXNU', unixnu)]:
        base = project / 'patches/overlays' / name
        for source in base.rglob('*'):
            if source.is_file():
                target_file = target / source.relative_to(base)
                target_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target_file)
    for name, package in [('EldenRamDiskDxe', 'EldenPhase1Pkg'),
                          ('EldenPayloadDxe', 'EldenPhase2Pkg')]:
        for source in (project / 'drivers' / name).iterdir():
            if source.is_file():
                destination = mu / 'Platforms' / package / source.name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, destination)
    main_file = unixnu / 'package/UniXNUPkg/Library/UniXNULib/Main.c'
    if sha(main_file) != plan['main_c_sha256']:
        raise ValueError('The accepted firmware uses the original ConnectAll order')
    # Source assertion strings and CodeView path lengths affect PE layout.
    virtual = plan['virtual_project']
    dsc = mu / 'Platforms/PakalaPkg/PakalaNoSb.dsc'
    dsc.write_text(dsc.read_text() + '\n[BuildOptions]\n'
                   '  *_CLANGPDB_AARCH64_CC_FLAGS = -ffile-prefix-map='
                   + str(project) + '=' + virtual + '\n')
    wrappers = out / 'toolchain'
    wrappers.mkdir()
    for tool in llvm.iterdir():
        if tool.name not in ('lld-link', 'clang'):
            (wrappers / tool.name).symlink_to(tool)
    install_clang_wrapper(llvm, wrappers, project, plan)
    wrapper = wrappers / 'lld-link'
    wrapper.write_text('#!' + sys.executable + '\nimport sys,os\nfrom pathlib import Path\n'
                       'a=sys.argv[1:]\n'
                       'out=next(x[5:] for x in a if x.upper().startswith("/OUT:"))\n'
                       'pdb=str(Path(out).with_suffix(".pdb")).replace('
                       + repr(str(project)) + ',' + repr(virtual) + ')\n'
                       'os.execv(' + repr(str(llvm / 'lld-link')) + ',['
                       + repr(str(llvm / 'lld-link')) + ']+a+["/PDBALTPATH:"+pdb])\n')
    wrapper.chmod(0o755)
    # Use a fresh BaseTools build too; no old target objects or project archives.
    env = dict(os.environ)
    for name in ('SDKROOT', 'BIN_CACHE_SOURCE', 'BIN_CACHE_DESTINATION'):
        env.pop(name, None)
    env['PYTHON_COMMAND'] = sys.executable
    commands = [
        ['make', '-C', str(mu / 'MU_BASECORE/BaseTools'), '-j' + str(args.jobs)],
        [sys.executable, str(project / 'scripts/build_phase2_firmware.py'),
         '--target', 'DEBUG', '--toolchain', str(wrappers),
         '--crypto-path', str(staged_crypto), '--jobs', str(args.jobs), '--keep-build-tree'],
    ]
    (out / 'commands.json').write_text(json.dumps(commands, indent=2) + '\n')
    (out / 'source-export.json').write_text(json.dumps(records, indent=2) + '\n')
    (out / 'crypto-package.json').write_text(json.dumps({
        'source_release_sha256': sha256_json(plan['crypto_files']),
        'staged': crypto_stage,
        'external_crypto_path': str(crypto),
        'build_uses_staged_package': str(staged_crypto),
    }, indent=2) + '\n')
    report = {'device_operation': False, 'copied_old_build_objects': False,
              'profile_sha256': sha(PROFILE / 'plan.json'), 'returncode': None}
    with (out / 'build.log').open('x') as log:
        for command in commands:
            result = subprocess.run(command, cwd=project, env=env,
                                    stdout=log, stderr=subprocess.STDOUT)
            report['returncode'] = result.returncode
            if result.returncode:
                break
    fd = project / 'out/phase2.3/SILICIUM_UEFI.fd'
    if report['returncode'] == 0:
        shutil.copyfile(fd, out / 'UEFI.fd')
        report.update(sha256=sha(fd), bytes=fd.stat().st_size)
        try:
            report['qualification'] = verify_firmware(fd)
        except ValueError as error:
            report.update(returncode=2, qualification_error=str(error))
    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    if report['returncode']:
        raise SystemExit((out / 'build.log').read_text()[-5000:])


if __name__ == '__main__':
    main()
