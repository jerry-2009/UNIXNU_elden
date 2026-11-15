"""Test transformed UFS completion/submit and SPI registration, with modeled hardware."""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'drivers/EldenUfsWait'))
from Source import source, recovery, commands, cpu_source


def function(text, signature):
    start = text.index(signature)
    brace = text.index('{', start)
    depth, end = 1, brace + 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cxx', required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--trial',action='store_true')
    a = p.parse_args()
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    driver = ROOT / 'drivers/EldenUfsWait'
    command_text, cpu = commands().decode(), cpu_source().decode()
    transfer = ROOT / 'profiles/v91/native-build/extra/30ec996e2f0b/TransferPoll.h'
    layout = ROOT / 'profiles/v91/native-build/extra/77699362f09e/RootTransportLayout.h'
    completion = (driver / 'EldenUfsCompletion.inc').read_text()
    if a.trial:
        from TrialSource import completion as trial_completion
        completion=trial_completion().decode()
    (out / 'transport.inc').write_text(
        completion + '\n' + function(command_text, 'struct HardwareTransferPort') + ';\n' +
        function(command_text, 'static uint32_t loadBe32') + '\n' +
        function(command_text, 'static IOReturn hostSubmit') + '\n' +
        function(command_text, 'static bool hostClearUcd') + '\n', encoding='utf-8')
    spi = '\n'.join(function(cpu, sig) for sig in (
        'static IOReturn eldenSpiAttachUnlocked',
        'extern "C" IOReturn armcpu_spi_attach(',
        'extern "C" IOReturn armcpu_spi_mask('))
    assert spi.count('__asm__ volatile') == 2
    # Only ARM barriers are replaced. Registration, validation and MMIO remain
    # the actual transformed bodies; the host models GIC register semantics.
    import re
    spi = re.sub(r'__asm__ volatile\s*\("dsb sy"\s*:::\s*"memory"\);',
                 'std::atomic_thread_fence(std::memory_order_seq_cst);', spi)
    assert '__asm__' not in spi
    (out / 'spi.inc').write_text('static IOLock *gEldenSpiRegistrationLock;\n' + spi, encoding='utf-8')
    outputs = {}
    for name in (('Completion','Spi','ReadTrial') if a.trial else ('Completion','Spi')):
        exe = out / name.lower()
        cmd = [a.cxx, '-std=c++17', '-O1', '-g', '-pthread', '-fsanitize=address,undefined',
               '-fno-omit-frame-pointer', '-I', str(out), '-I', str(transfer.parent),
               '-I', str(layout.parent),str(driver / ('Test' + name + '.cpp')), '-o', str(exe)]
        if a.trial:cmd+=['-DELDEN_UFS_WAIT_TRIAL=1']
        if sys.platform.startswith('linux'):
            cmd[1:1] = ['-fno-pie', '-no-pie']
        for stage, command in [('compile', cmd), ('run', [str(exe)])]:
            r = subprocess.run(command, capture_output=True, timeout=120)
            (out / (name + '-' + stage + '.log')).write_bytes(r.stdout + r.stderr)
            r.check_returncode()
        outputs[name] = r.stdout.decode().strip()
    src, rec = source(), recovery()
    if a.trial:
        from TrialSource import source as trial_source
        src=trial_source()
    assert src.index(b'#include <kern/sched_prim.h>') < src.index(b'namespace {')
    assert command_text.count('eldenUfsIrqStop();gHost.poisoned = true;') == 6
    assert rec.index(b'\n  elden_ufs_wait_shutdown();') < rec.index(b'if(elden_wcn_request_stop)')
    inputs = {'ufs': src, 'commands': commands(), 'cpu': cpu_source(), 'recovery': rec,
              'completion': completion.encode(),
              'transfer_poll_unchanged': transfer.read_bytes()}
    report = {'passed': True, 'outputs': outputs, 'asan_ubsan': True,
              'actual_transformed_functions': True, 'hardware_and_scheduler_modeled': True,
              'native_build': False, 'hardware': False,
              'trial':a.trial,
              'sha256': {k: hashlib.sha256(v).hexdigest() for k, v in inputs.items()}}
    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
