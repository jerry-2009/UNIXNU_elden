"""Rebuild only the qualified worker with two read-only physical snapshots."""
import argparse,hashlib,json,re,subprocess,sys
from pathlib import Path
from replay_xnu_objects import global_symbols,sections
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'drivers/EldenWifi/net'))
from Net17NativeSource import generated


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def symbols(p,d):return {n for n,v in global_symbols(p).items() if bool(v[0]&0x0e)==d}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('parent-native','reference-kernel','clean-build','llvm','output'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();parent,out=a.parent_native.resolve(),a.output.resolve();prior=json.loads((parent/'result.json').read_text())
    if not all(prior.get(n) for n in ('compiled','umac_hold_trial','ce3_inspect_trial','wifi_battery_runtime_trial','platform_physical_fence_preserved')) or sha(parent/'Native.o')!=prior['object_sha256']:
        raise ValueError('Qualified radio-only/UMAC/inspection worker required')
    out.mkdir(parents=True,exist_ok=False);source=out/'source';source.mkdir()
    before=generated(False,True,True,True,False);after=generated(False,True,True,True,True)
    if prior['generated_sources']!={n:hashlib.sha256(data).hexdigest() for n,data in before.items()}:raise ValueError('Retained generated worker differs')
    for n,data in after.items():(source/n).write_bytes(data)
    overlay=json.loads((parent/'overlay.json').read_text());inherited={};changed=[]
    if overlay.get('fallthrough') is not False:raise ValueError('Strict worker overlay required')
    for row in overlay['roots']:
        old=Path(row['external-contents']);inherited[str(old)]=sha(old)
        n=old.name
        if n in before and old.read_bytes()==before[n]:
            row['external-contents']=str(source/n);changed.append(row['name'])
    if len(changed)!=len(before):raise ValueError('Every exact generated source must be bound once')
    vfs=out/'overlay.json';vfs.write_text(json.dumps(overlay,indent=2)+'\n')
    cmd=list(prior['command']);cmd[cmd.index('-ivfsoverlay')+1]=str(vfs);cmd[cmd.index('-o')+1]=str(out/'Native.o')
    r=subprocess.run(cmd,cwd=a.clean_build/'units/working/WcnPowerNative',capture_output=True);(out/'compile.log').write_bytes(r.stdout+r.stderr);r.check_returncode()
    obj=out/'Native.o';added={'_elden_wifi_first_failure_physical'}
    if symbols(obj,True)!=symbols(parent/'Native.o',True)|added or symbols(obj,False)!=symbols(parent/'Native.o',False):raise ValueError('First-failure worker interface delta changed')
    if symbols(obj,False)-symbols(a.reference_kernel,True):raise ValueError('First-failure worker has unresolved actual imports')
    asm=subprocess.check_output([str(a.llvm/'llvm-objdump'),'-dr',obj],text=True);(out/'Native.asm').write_text(asm)
    if any(n.endswith('/__mod_init_func') for n in sections(obj)) or re.search(r'^\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+.*\b[qvdshb]\d+(?:\b|\.)',asm,re.M):raise ValueError('First-failure worker initializer/SIMD')
    for n,h in inherited.items():
        if sha(Path(n))!=h:raise ValueError('Retained worker overlay input changed')
    own=['tools/build_wifi_first_failure_native.py','tools/test_wifi_first_failure.py','drivers/EldenWifi/FirstFailureNativeSource.py','drivers/EldenWifi/FirstFailurePhysical.inc','drivers/EldenWifi/net/Net17NativeSource.py']
    proof=dict(prior);proof.update(first_failure_physical=True,first_failure_readonly=True,first_failure_sample_stages=[12,90],
        first_failure_no_new_maps=True,first_failure_no_control_writes=True,object_sha256=sha(obj),base_object_sha256=prior['base_object_sha256'],
        first_failure_parent_worker_sha256=prior['object_sha256'],
        generated_sources={n:hashlib.sha256(data).hexdigest() for n,data in after.items()},command=cmd,
        source_inputs={**prior['source_inputs'],**{n:sha(ROOT/n) for n in own}},added_exports=sorted(set(prior['added_exports'])|added),
        warnings=r.stderr.count(b'warning:'),hardware_tested=False)
    (out/'result.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps({k:proof[k] for k in ('compiled','first_failure_physical','object_sha256','warnings','hardware_tested')}))


if __name__=='__main__':main()
