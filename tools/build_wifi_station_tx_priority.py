"""Rebuild the profile-ready station object with a selected TX adaptation."""

import argparse
import json
import re
import shlex
import subprocess
from pathlib import Path

from build_wifi_station_ready import ROOT, STA, defs, refs, sha
from replay_xnu_objects import sections
from wifi_station import qualify_runtime


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('parent-build', 'llvm', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--oem-metadata', action='store_true',
                        help='Pair the stock HTT version request with OEM TCL metadata')
    parser.add_argument('--oem-eapol-critical', action='store_true',
                        help='Add OEM EAPOL critical flow-override and TX-notify fields')
    parser.add_argument('--single-pdev-bank', action='store_true',
                        help='Match the TB322FC station bank VDEV check setting')
    parser.add_argument('--wait-htt-drain', action='store_true',
                        help='Require HTT source-ring progress before the second scan')
    args = parser.parse_args()
    if args.oem_metadata and args.oem_eapol_critical:
        parser.error('Choose one TX adaptation')
    if args.single_pdev_bank and not args.oem_eapol_critical:
        parser.error('--single-pdev-bank requires --oem-eapol-critical')
    if args.wait_htt_drain and not args.oem_eapol_critical:
        parser.error('--wait-htt-drain requires --oem-eapol-critical')
    if args.oem_eapol_critical:
        from StationOemEapolCritical import station, dp_header
        source_recipe = 'StationOemEapolCritical.py'
        flag = 'oem_eapol_critical'
    elif args.oem_metadata:
        from StationOemMetadata import station
        source_recipe = 'StationOemMetadata.py'
        flag = 'oem_tcl_v1'
    else:
        from StationTxPriority import station
        source_recipe = 'StationTxPriority.py'
        flag = 'eapol_voice'
    parent = args.parent_build.resolve()
    output = args.output.resolve()
    prior = json.loads((parent / 'result.json').read_text())
    qualify_runtime(prior)
    if not prior.get('station_ready') or prior.get('eapol_voice') or prior.get('oem_tcl_v1') or prior.get('oem_eapol_critical'):
        raise ValueError('Expected the original profile-ready station build')

    generated = station(Path(prior['source']).read_bytes())
    output.mkdir(parents=True, exist_ok=False)
    source = output / 'Station.cpp'
    source.write_bytes(generated)
    overlay_path = None
    expected_headers = dict(prior['consumed_inputs'])
    expected_headers.pop(prior['source'])
    if args.oem_eapol_critical:
        wire = prior['base']['overlay']
        overlay_value = json.loads(Path(wire).read_text())
        roots = overlay_value.get('roots')
        if not isinstance(roots, list) or len(roots) != 1:
            raise ValueError('Expected the exact existing station codec overlay')
        header_specs = [(STA / 'upstream/WifiDp.h', dp_header, {'single_pdev_bank':args.single_pdev_bank})]
        if args.wait_htt_drain:
            from ScanHttDrain import link_header
            header_specs.append((STA.parent / 'upstream/WifiLink.h', link_header, {}))
        for frozen, derive, options in header_specs:
            paths = [path for path in expected_headers if Path(path).name == frozen.name]
            if len(paths) != 1 or expected_headers.pop(paths[0]) != sha(frozen):
                raise ValueError('Profile-ready runtime did not consume ' + frozen.name)
            generated_header = output / frozen.name
            generated_header.write_bytes(derive(frozen.read_bytes(), **options))
            roots.append({'type':'file','name':paths[0],'external-contents':str(generated_header)})
            expected_headers[str(generated_header)] = sha(generated_header)
        overlay_path = output / 'overlay.json'
        overlay_path.write_text(json.dumps(overlay_value, indent=2) + '\n')
    obj = output / 'Station.o'
    dep = output / 'Station.d'
    cmd = list(prior['command'])
    cmd[cmd.index(prior['source'])] = str(source)
    if overlay_path is not None:
        cmd[cmd.index('-ivfsoverlay') + 1] = str(overlay_path)
    cmd[cmd.index('-o') + 1] = str(obj)
    cmd[cmd.index('-MF') + 1] = str(dep)
    with (output / 'compile.log').open('xb') as log:
        subprocess.run(cmd, cwd=output, stdout=log, stderr=subprocess.STDOUT, check=True)

    deps = shlex.split(dep.read_text().replace('\\\n', ' ').split(':', 1)[1])
    consumed = {path: sha(path) for path in deps}
    if consumed != {**expected_headers, str(source):sha(source)}:
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
    for path in (Path(__file__).resolve(), STA / source_recipe):
        pins[path.relative_to(ROOT).as_posix()] = sha(path)
    if args.oem_eapol_critical:
        pins['drivers/EldenWifi/portable/station/upstream/WifiDp.h'] = sha(STA / 'upstream/WifiDp.h')
    result = dict(prior, source=str(source), source_sha256=sha(source),
                  object=str(obj), object_sha256=sha(obj), command=cmd, consumed_inputs=consumed,
                  link=link, binding_sha256=sha(binding), source_inputs=pins, hardware_tested=False)
    result[flag] = True
    if args.oem_eapol_critical:
        result.update(
            station_tx_critical=True,
            base=prior,
            parent_source=prior['source'],
            parent_source_sha256=prior['source_sha256'],
            no_board_ring_bank_clock_timeout_change=not args.single_pdev_bank,
            no_payload_logging=True,
            oem_flow_override=True,
            oem_high_priority_notify=True,
            source_recipe='StationOemEapolCritical.py',
            overlay=str(overlay_path),
            overlay_sha256=sha(overlay_path),
            dp_header=str(output / 'WifiDp.h'),
            dp_header_sha256=sha(output / 'WifiDp.h'),
        )
        if args.single_pdev_bank:
            result['oem_single_pdev_bank'] = True
        if args.wait_htt_drain:
            for path in (STA/'ScanHttDrain.py',STA.parent/'upstream/WifiLink.h'):
                pins[path.relative_to(ROOT).as_posix()] = sha(path)
            result.update(wait_htt_drain=True,link_header=str(output/'WifiLink.h'),
                          link_header_sha256=sha(output/'WifiLink.h'))
    qualify_runtime(result)
    (output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'compiled': True, 'binding_sha256': result['binding_sha256']}))


if __name__ == '__main__':
    main()
