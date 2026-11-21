"""Rebuild the profile-ready station object with EAPOL WMM priority."""

import argparse
import json
import re
import shlex
import subprocess
from pathlib import Path

from build_wifi_station_ready import ROOT, STA, defs, refs, sha
from replay_xnu_objects import sections
from wifi_station import qualify_runtime
from StationTxPriority import station


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('parent-build', 'llvm', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    parent = args.parent_build.resolve()
    output = args.output.resolve()
    prior = json.loads((parent / 'result.json').read_text())
    qualify_runtime(prior)
    if not prior.get('station_ready') or prior.get('eapol_voice'):
        raise ValueError('Expected the original profile-ready station build')

    generated = station(Path(prior['source']).read_bytes())
    output.mkdir(parents=True, exist_ok=False)
    source = output / 'Station.cpp'
    source.write_bytes(generated)
    obj = output / 'Station.o'
    dep = output / 'Station.d'
    cmd = list(prior['command'])
    cmd[cmd.index(prior['source'])] = str(source)
    cmd[cmd.index('-o') + 1] = str(obj)
    cmd[cmd.index('-MF') + 1] = str(dep)
    with (output / 'compile.log').open('xb') as log:
        subprocess.run(cmd, cwd=output, stdout=log, stderr=subprocess.STDOUT, check=True)

    deps = shlex.split(dep.read_text().replace('\\\n', ' ').split(':', 1)[1])
    consumed = {path: sha(path) for path in deps}
    old_headers = {path: digest for path, digest in prior['consumed_inputs'].items()
                   if path != prior['source']}
    if {path: digest for path, digest in consumed.items() if path != str(source)} != old_headers:
        raise ValueError('TX priority changed the station header inputs')

    asm = subprocess.check_output([str(args.llvm / 'llvm-objdump'), '-dr', str(obj)], text=True)
    (output / 'Station.asm').write_text(asm)
    if defs(obj) != defs(prior['object']) or refs(obj) != refs(prior['object']):
        raise ValueError('TX priority changed the station object interface')
    if (any(name.endswith('/__mod_init_func') for name in sections(obj)) or
            re.search(r'^\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+.*\b[qvdshb]\d+(?:\b|\.)', asm, re.M)):
        raise ValueError('TX priority introduced a global initializer or SIMD')

    link = [str(obj) if value == prior['object'] else value for value in prior['link']]
    binding = output / 'WifiRuntimeMsiBinding.o'
    link[link.index('-o') + 1] = str(binding)
    with (output / 'link.log').open('xb') as log:
        subprocess.run(link, stdout=log, stderr=subprocess.STDOUT, check=True)
    old_binding = parent / binding.name
    if defs(binding) != defs(old_binding) or refs(binding) != refs(old_binding):
        raise ValueError('TX priority changed the combined runtime interface')

    pins = dict(prior['source_inputs'])
    for path in (Path(__file__).resolve(), STA / 'StationTxPriority.py'):
        pins[path.relative_to(ROOT).as_posix()] = sha(path)
    result = dict(prior, eapol_voice=True, source=str(source), source_sha256=sha(source),
                  object=str(obj), object_sha256=sha(obj), command=cmd, consumed_inputs=consumed,
                  link=link, binding_sha256=sha(binding), source_inputs=pins, hardware_tested=False)
    qualify_runtime(result)
    (output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'compiled': True, 'binding_sha256': result['binding_sha256']}))


if __name__ == '__main__':
    main()
