"""Test the actual CPU-MMIO-only endpoint transaction with modeled callbacks."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--wsl-distro')
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    source = ROOT / 'drivers/EldenPcie'
    def path(value):
        value = str(Path(value).resolve())
        return '/mnt/' + value[0].lower() + value[2:].replace('\\', '/') if args.wsl_distro else value
    prefix = ['wsl', '-d', args.wsl_distro, '--'] if args.wsl_distro else []
    command = ['cc', '-std=c11', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
               '-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    if args.wsl_distro:
        command += ['-fno-pie', '-no-pie']
    command += [path(source/'TestEndpoint.c'), path(source/'Endpoint.c'), '-o', path(out/'test')]
    for label, cmd in [('compile', command), ('run', [path(out/'test')])]:
        result = subprocess.run(prefix + cmd, capture_output=True, timeout=120)
        (out/(label+'.log')).write_bytes(result.stdout + result.stderr)
        result.check_returncode()
    report = {'passed': True, 'result': result.stdout.decode().strip(), 'asan_ubsan': True,
              'hardware_callbacks_modeled': True, 'hardware': False,
              'source_sha256': {name: hashlib.sha256((source/name).read_bytes()).hexdigest()
                                for name in ('Endpoint.c', 'Endpoint.h', 'Root.h', 'Phy.h', 'TestEndpoint.c')}}
    (out/'result.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report))

if __name__ == '__main__':
    main()
