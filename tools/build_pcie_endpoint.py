"""Build the standalone BAR/Peach identity transaction for ARM64/iOS17."""
import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from replay_xnu_objects import sections, global_symbols

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--llvm', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    source = ROOT/'drivers/EldenPcie'
    obj = out/'Endpoint.o'
    command = ['xcrun', '--sdk', 'iphoneos', 'clang', '-target', 'arm64-apple-ios17.0',
               '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-ffreestanding',
               '-fno-builtin', '-fno-stack-protector', '-mgeneral-regs-only',
               '-MMD', '-MF', str(out/'Endpoint.d'), '-c', str(source/'Endpoint.c'), '-o', str(obj)]
    result = subprocess.run(command, capture_output=True, check=False)
    (out/'compile.log').write_bytes(result.stdout+result.stderr)
    result.check_returncode()
    asm = subprocess.check_output([str(args.llvm/'llvm-objdump'), '-dr', str(obj)], text=True)
    (out/'Endpoint.asm').write_text(asm, encoding='utf-8')
    assert not re.search(r'^\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+.*\b[qvdshb]\d+(?:\b|\.)', asm, re.M)
    assert not any(name.endswith('/__mod_init_func') for name in sections(obj))
    symbols = global_symbols(obj)
    exports = {name for name, v in symbols.items() if v[0]&0x0e}
    imports = {name for name, v in symbols.items() if not v[0]&0x0e}
    assert exports == {'_elden_pcie_endpoint_identify'} and not imports
    inputs = {}
    for name in ('Endpoint.c', 'Endpoint.h', 'Root.h', 'Phy.h'):
        path = source/name
        assert str(path) in (out/'Endpoint.d').read_text()
        inputs[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    report = {'compiled': True, 'object_sha256': hashlib.sha256(obj.read_bytes()).hexdigest(),
              'command': command, 'source_sha256': inputs, 'exports': sorted(exports),
              'imports': sorted(imports), 'scalar': True, 'warnings': result.stderr.count(b'warning:'),
              'native_map_provider_implemented': False, 'kernel_linked': False, 'hardware_tested': False}
    (out/'result.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report))

if __name__ == '__main__':
    main()
