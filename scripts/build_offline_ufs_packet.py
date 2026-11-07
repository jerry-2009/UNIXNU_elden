#!/usr/bin/env python3
"""Build/verify the elden UFS candidate from existing inputs; no device I/O.

Run on the configured Mac. The FD must be extracted from the accepted 11-01
image; do not rebuild firmware as part of the payload-size experiment.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--fd', type=Path, required=True)
    p.add_argument('--source-payload', type=Path, required=True)
    p.add_argument('--kernel', type=Path, required=True, help='independent compiled kernel to compare')
    p.add_argument('--work', type=Path, default=ROOT / 'out/offline-20261105')
    p.add_argument('--clang', default='/usr/bin/clang')
    args = p.parse_args()
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env['PATH'] = str(ROOT / '.cache/mtools/bin') + os.pathsep + env['PATH']
    log = []

    def run(*cmd):
        cmd = list(map(str, cmd))
        result = subprocess.run(cmd, cwd=ROOT, env=env, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        log.append({'command': cmd, 'returncode': result.returncode, 'output': result.stdout})
        (work / 'build-log.json').write_text(json.dumps(log, indent=2) + '\n')
        print(result.stdout, end='', flush=True)
        result.check_returncode()

    payload = work / 'payload.img'
    if payload == args.source_payload.resolve():
        p.error('--source-payload must differ from the work copy')
    shutil.copyfile(args.source_payload, payload)
    run('mlabel', '-i', payload, '::ELDENRAM')
    run('mcopy', '-o', '-i', payload, ROOT / 'package/phase3-ufs-marker-unixnu.toml',
        '::EFI/UniXNU/unixnu.toml')
    for name in ('kernel.macho', 'kernel.macho.adt'):
        run('mcopy', '-o', '-i', payload, '::EFI/UniXNU/Payloads/' + name, work / name)
    if digest(work / 'kernel.macho') != digest(args.kernel):
        raise SystemExit('payload kernel differs from the independent compiled kernel')
    run(sys.executable, ROOT / 'scripts/darwinboot_preflight.py',
        '--kernel', work / 'kernel.macho', '--adt', work / 'kernel.macho.adt')
    image = work / 'ufsprobe-embed56.img'
    run(sys.executable, ROOT / 'scripts/build_phase2_image.py', '--kind', 'boot',
        '--fd', args.fd, '--payload', payload, '--output', image,
        '--embed-payload', '--work', work, '--clang', args.clang)
    run(sys.executable, ROOT / 'scripts/verify_phase2_artifact.py', '--kind', 'boot',
        '--image', image, '--fd', args.fd, '--shim', work / 'shim-boot-embed.bin',
        '--embed-payload', '--payload', payload,
        '--expect-kernel-bytes', (work / 'kernel.macho').stat().st_size,
        '--expect-kernel-sha256', digest(args.kernel), '--xnu-title', 'ELDEN 3 UFS PROBE',
        '--report', work / 'verify.json')
    files = [args.fd, args.source_payload, args.kernel, payload, image,
             work / 'shim-boot-embed.bin', work / 'kernel.macho.adt']
    report = {str(f): {'bytes': f.stat().st_size, 'sha256': digest(f)} for f in files}
    (work / 'inputs-and-products.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
