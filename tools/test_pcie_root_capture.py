"""Reject false root-trial acceptance using rehashed mutations of a real capture.

Evidence is retained in --output; no original capture is modified or removed.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path

from assess_pcie_root_capture import assess, read


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('run', 'audit', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    baseline = assess(args.run, args.audit)
    args.output.mkdir(parents=True, exist_ok=False)
    capture, = (args.run / 'usb').glob('*.bin')
    raw = capture.read_bytes()
    documents = {
        'usb/capture.json': read(capture.with_suffix('.json')),
        'supervisor.json': read(args.run / 'supervisor.json'),
        'flash/result.json': read(args.run / 'flash/result.json'),
        'restore/result.json': read(args.run / 'restore/result.json'),
        'audit.json': read(args.audit),
    }

    def replace(old, new):
        assert raw.count(old) == 1, old
        return raw.replace(old, new, 1)

    cases = [
        ('wrong-root', replace(b'root=011c17cb ep=', b'root=011cffff ep='), None),
        ('bus-master', replace(b'last=6:00000004=00100000', b'last=6:00000004=00100004'), None),
        ('missing-stage', replace(b'ELDEN_PCIE stage=5 ', b'OMITTED_PCIE stage=5 '), None),
        ('missing-quiesce', replace(b'ELDEN_PCIE quiesced=1', b'ELDEN_PCIE quiesced=0'), None),
        ('missing-reset', replace(b'ELDEN_RPC RESET_AFTER_SYNC route=sdam-v7', b'ELDEN_RPC RESET_NOT_CONFIRMED route=sdam-v7'), None),
        ('early-storage-error', b'device is not ready\n' + raw, None),
        ('early-ufs-stop', b'ELDEN_UFS_IDLE stop=0 phase=4 error=0 active=0\n' + raw, None),
        ('bad-stock-sha', raw, ('restore/result.json', 'full_readback_sha256', '0' * 64)),
        ('wrong-session', raw, ('usb/capture.json', 'candidate_session', '0' * 16)),
        ('discontinuity', raw, ('usb/capture.json', 'discontinuities', [{'reason': 'injected'}])),
        ('failed-restore', raw, ('restore/result.json', 'success', False)),
        ('charge-not-restored', raw, ('supervisor.json', 'charging_after', ['0', '095100', '095100'])),
        ('scan-not-restored', raw, ('supervisor.json', 'scan_settings_after', ['0', '0'])),
        ('wrong-floor', raw, ('audit.json', 'rollback_index', 1738713601)),
    ]
    rejected = []
    for name, mutated, edit in cases:
        folder = args.output / name
        docs = copy.deepcopy(documents)
        docs['usb/capture.json']['bytes'] = len(mutated)
        docs['usb/capture.json']['raw_sha256'] = hashlib.sha256(mutated).hexdigest()
        if edit:
            file, key, value = edit
            docs[file][key] = value
        for file, doc in docs.items():
            destination = folder / file
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(json.dumps(doc, indent=2) + '\n', encoding='utf-8')
        (folder / 'usb/capture.bin').write_bytes(mutated)
        try:
            assess(folder, folder / 'audit.json')
        except AssertionError:
            rejected.append(name)
        else:
            raise AssertionError('False acceptance: ' + name)
    result = {'passed': True, 'baseline_sha256': baseline['capture_sha256'],
              'rehash_mutations': True, 'rejected': rejected}
    (args.output / 'result.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
