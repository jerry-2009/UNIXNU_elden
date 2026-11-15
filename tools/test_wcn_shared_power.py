"""Exercise the production WCN owner with recorded physical callbacks; no device I/O."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / 'drivers/EldenBluetooth'

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--wsl-distro')
    p.add_argument('--compiler', default='cc')
    a = p.parse_args()
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    def path(v):
        v = str(Path(v).resolve())
        return '/mnt/' + v[0].lower() + v[2:].replace('\\', '/') if a.wsl_distro else v
    prefix = ['wsl', '-d', a.wsl_distro, '--'] if a.wsl_distro else []
    command = [a.compiler, '-std=c11', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
               '-Wno-misleading-indentation', '-fsanitize=address,undefined',
               '-fno-omit-frame-pointer', '-pthread']
    if a.wsl_distro: command += ['-fno-pie', '-no-pie']
    rev='2062ad1d2591b0b0095363b3e601fd04d7eaf09b'
    old=out/'legacy';old.mkdir()
    for name in ['WcnPower.c','WcnPower.h']:
        (old/name).write_bytes(subprocess.check_output(['git','-C',str(ROOT),'show',rev+':drivers/EldenBluetooth/'+name]))
    names=['elden_wcn_rail_specs','elden_wcn_power_acquire','elden_wcn_power_stop',
           'elden_wcn_power_finish','elden_wcn_power_check','elden_wcn_parent_decode',
           'elden_wcn_cpr_adjust','elden_wcn_cpr_plan_details','elden_wcn_cpr_rail_name',
           'elden_wcn_cpr_pdc_name','elden_wcn_cpr_plan','elden_wcn_power_cpr']
    old_obj=out/'legacy.o'
    old_command=command+['-D'+n+'=legacy_'+n for n in names]+['-c',path(old/'WcnPower.c'),'-o',path(old_obj)]
    exe = out / 'test-shared'
    command += [path(D/'WcnPower.c'), path(D/'TestWcnSharedPower.c'),path(old_obj), '-o', path(exe)]
    for name, args in [('legacy-compile',old_command),('compile',command),('run',[path(exe)])]:
        r = subprocess.run(prefix+args,capture_output=True,timeout=120)
        (out/(name+'.stdout')).write_bytes(r.stdout)
        (out/(name+'.stderr')).write_bytes(r.stderr)
        r.check_returncode()
    inputs = ['WcnPower.c','WcnPower.h','WcnSharedPower.h','WcnSharedPower.inc','TestWcnSharedPower.c']
    report = {'passed':True,'result':r.stdout.decode().strip(),'asan_ubsan':True,'legacy_revision':rev,
              'legacy_source_sha256':hashlib.sha256((old/'WcnPower.c').read_bytes()).hexdigest(),
              'callbacks_modeled':True,'native_adapter_connected':False,'hardware_operations':False,
              'source_sha256':{n:hashlib.sha256((D/n).read_bytes()).hexdigest() for n in inputs}}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report))

if __name__=='__main__':main()
