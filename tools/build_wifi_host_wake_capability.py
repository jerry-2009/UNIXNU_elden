"""Compile only the missing OEM WAKE host capability onto the retained runtime."""
import argparse
import hashlib
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path
from replay_xnu_objects import global_symbols, sections

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'drivers/EldenWifi/peach'))
from HostWakeCapabilityPatch import patch


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def symbols(p, defined):
    return {n for n, v in global_symbols(p).items() if bool(v[0] & 0x0e) == defined}


def main():
    if sys.flags.optimize:
        raise ValueError('Assertions required')
    parser = argparse.ArgumentParser(description=__doc__)
    for n in ('runtime-build', 'parent-build', 'llvm', 'output'):
        parser.add_argument('--' + n, type=Path, required=True)
    args = parser.parse_args()
    base, parent, out = args.runtime_build.resolve(), args.parent_build.resolve(), args.output.resolve()
    prior = json.loads((parent / 'result.json').read_text())
    if not prior.get('oem_init_mode_trial') or sha(parent / 'WifiRuntimeMsiBinding.o') != prior['binding_sha256']:
        raise ValueError('Qualified OEM init parent required')
    rows = json.loads((base / 'objects/build-report.json').read_text())['objects']
    row, = [r for r in rows if Path(r['path']).name == 'ath12k_qmi.o']
    original, old = Path(row['source']), Path(row['path'])
    if sha(original) != row['source_sha256'] or sha(old) != row['object_sha256']:
        raise ValueError('Original QMI source/object changed')
    identity = json.loads((base / 'objects/raw/ath12k_qmi.inputs.json').read_text())
    out.mkdir(parents=True, exist_ok=False)
    source, raw, obj, dep = out / 'qmi.c', out / 'ath12k_qmi.raw.o', out / 'ath12k_qmi.o', out / 'qmi.d'
    source.write_bytes(patch(original.read_bytes()))
    cmd = list(identity['command'])
    cmd[cmd.index(str(original))] = str(source)
    cmd[cmd.index('-o') + 1] = str(raw)
    cmd[cmd.index('-MF') + 1] = str(dep)
    cmd += ['-iquote', str(original.parent)]
    result = subprocess.run(cmd, cwd=out, capture_output=True)
    (out / 'compile.log').write_bytes(result.stdout + result.stderr)
    result.check_returncode()
    warning_count = result.stderr.count(b'warning:')
    dependencies = shlex.split(dep.read_text().replace('\\\n', ' ').split(':', 1)[1])
    old_headers = {str(Path(n).resolve()): h for n, h in identity['dependencies'].items() if n != str(original)}
    actual_headers = {str(Path(n).resolve()) for n in dependencies if n != str(source)}
    additions = actual_headers - set(old_headers)
    pci_identity = json.loads((base / 'objects/raw/ath12k_pci.inputs.json').read_text())
    allowed = {str(Path(n).resolve()): h for n, h in pci_identity['dependencies'].items()}
    if set(old_headers) - actual_headers or len(additions) != 1 or not next(iter(additions)).endswith('/hif.h') or not additions <= set(allowed):
        raise ValueError('QMI capability dependency delta changed')
    old_headers.update({n: allowed[n] for n in additions})
    for n in dependencies:
        if n != str(source) and sha(Path(n)) != old_headers[str(Path(n).resolve())]:
            raise ValueError('QMI capability header changed: ' + n)
    subprocess.run([str(args.llvm / 'llvm-objcopy'), '--redefine-syms=' + str(base / 'objects/rename.txt'), str(raw), str(obj)], check=True)
    rename = dict(line.split() for line in (base / 'objects/rename.txt').read_text().splitlines())
    if global_symbols(obj) != {rename.get(n, n): v for n, v in global_symbols(raw).items()} or sections(obj) != sections(raw):
        raise ValueError('QMI rename changed code/data')
    if symbols(obj, True) != symbols(old, True) or symbols(obj, False) != symbols(old, False):
        raise ValueError('QMI capability interface changed')
    assembly = subprocess.check_output([str(args.llvm / 'llvm-objdump'), '-dr', obj], text=True)
    (out / 'qmi.asm').write_text(assembly)
    if any(n.endswith('/__mod_init_func') for n in sections(obj)) or re.search(r'^\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+.*\b[qvdshb]\d+(?:\b|\.)', assembly, re.M):
        raise ValueError('QMI capability initializer/SIMD')
    link = list(prior['link'])
    objects = [Path(v) for i, v in enumerate(link) if v.endswith('.o') and link[i - 1] != '-o']
    if len(objects) != 125 or objects.count(old) != 1:
        raise ValueError('Wrong retained QMI capability runtime')
    retained = {str(p): sha(p) for p in objects if p != old}
    target = out / 'WifiRuntimeMsiBinding.o'
    link[link.index('-o') + 1] = str(target)
    link = [str(obj) if v == str(old) else v for v in link]
    result = subprocess.run(link, capture_output=True)
    (out / 'link.log').write_bytes(result.stdout + result.stderr)
    result.check_returncode()
    if symbols(target, True) != symbols(parent / 'WifiRuntimeMsiBinding.o', True) or symbols(target, False) != symbols(parent / 'WifiRuntimeMsiBinding.o', False):
        raise ValueError('Combined capability interface changed')
    for n, h in retained.items():
        if sha(Path(n)) != h:
            raise ValueError('Retained runtime object changed')
    own = ['tools/build_wifi_host_wake_capability.py', 'tools/test_wifi_host_wake_capability.py', 'drivers/EldenWifi/HostWakeCapability.inc', 'drivers/EldenWifi/peach/HostWakeCapabilityPatch.py']
    proof = dict(prior)
    proof.update(host_wake_capability_trial=True, host_wake_capability_reversible=True,
                 host_wake_capability_peach_only=True, host_wake_callback_derived=True,
                 host_wake_msi_vector_count=1, host_wake_msi_base=13,
                 host_wake_qmi_tlv=0x11, host_wake_vendor_commit='d50b305f7da9e14715a25120a4ac7b1a4b8b97c3',
                 host_wake_no_credit_timeout_ring_change=True,
                 host_wake_qmi_source_sha256=sha(source), host_wake_qmi_object_sha256=sha(obj),
                 host_wake_qmi_warnings=warning_count,
                 host_wake_qmi_command=cmd, host_wake_consumed_inputs={n: sha(Path(n)) for n in dependencies},
                 changed_units=prior['changed_units'] + ['ath12k_qmi.o'],
                 parent_host_wake_binding_sha256=prior['binding_sha256'], binding_sha256=sha(target),
                 link=link, retained_objects=retained, source_inputs={**prior['source_inputs'], **{n: sha(ROOT / n) for n in own}}, hardware_tested=False)
    (out / 'result.json').write_text(json.dumps(proof, indent=2) + '\n')
    print(json.dumps({k: proof[k] for k in ['compiled', 'host_wake_capability_trial', 'binding_sha256', 'hardware_tested']}))


if __name__ == '__main__':
    main()
