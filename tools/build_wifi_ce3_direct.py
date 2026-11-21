"""Build the narrow direct-HP CE3 contrast over the qualified VDEV/UMAC runtime."""
import argparse,hashlib,json,re,shlex,subprocess,sys
from pathlib import Path
from replay_xnu_objects import global_symbols,sections
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'drivers/EldenWifi/peach'))
from Ce3DirectPointerPatch import patch


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())
def symbols(p,d):return {n for n,v in global_symbols(p).items() if bool(v[0]&0x0e)==d}


def main():
    if sys.flags.optimize:raise ValueError('Assertions required')
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('runtime-build','parent-build','llvm','output'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();base=a.runtime_build.resolve();parent=a.parent_build.resolve();out=a.output.resolve();prior=read(parent/'result.json')
    if prior.get('vdev_empty_mlo_array') is not True or prior.get('umac_hold_trial') is not True or prior.get('mhi_hold_trial') or sha(parent/'WifiRuntimeMsiBinding.o')!=prior['binding_sha256']:
        raise ValueError('Qualified VDEV/UMAC runtime required')
    row,=[r for r in read(base/'objects/build-report.json')['objects'] if Path(r['path']).name=='w7_hal.o']
    source=Path(row['source']);old=Path(row['path'])
    if sha(source)!=row['source_sha256'] or sha(old)!=row['object_sha256']:raise ValueError('Frozen actual wifi7 HAL changed')
    out.mkdir(parents=True,exist_ok=False);derived=out/'hal.c';derived.write_bytes(patch(source.read_bytes()))
    identity=read(base/'objects/raw/w7_hal.inputs.json');cmd=list(identity['command'])
    raw=out/'w7_hal.raw.o';obj=out/'w7_hal.o';dep=out/'hal.d'
    cmd[cmd.index(str(source))]=str(derived);cmd[cmd.index('-o')+1]=str(raw);cmd[cmd.index('-MF')+1]=str(dep)
    # The original unit lives in wifi7/. Preserve its quoted-header namespace
    # before the root -I paths; otherwise hw.h resolves to a different file.
    cmd[1:1]=['-iquote',str(source.parent)]
    if cmd[cmd.index('-target')+1]!='arm64-apple-ios17.0' or '-mgeneral-regs-only' not in cmd:raise ValueError('Wrong scalar iOS17 HAL command')
    r=subprocess.run(cmd,cwd=out,capture_output=True);(out/'compile.log').write_bytes(r.stdout+r.stderr);r.check_returncode()
    deps=shlex.split(dep.read_text().replace('\\\n',' ').split(':',1)[1])
    if set(deps)-{str(derived)}!=set(identity['dependencies'])-{str(source)}:raise ValueError('HAL dependencies changed')
    for n in deps:
        if n!=str(derived) and sha(Path(n))!=identity['dependencies'][n]:raise ValueError('HAL header changed')
    subprocess.run([str(a.llvm/'llvm-objcopy'),'--redefine-syms='+str(base/'objects/rename.txt'),str(raw),str(obj)],check=True)
    rename=dict(l.split() for l in (base/'objects/rename.txt').read_text().splitlines())
    if global_symbols(obj)!={rename.get(n,n):v for n,v in global_symbols(raw).items()} or sections(raw)!=sections(obj):raise ValueError('HAL rename changed code/data')
    if symbols(obj,True)!=symbols(old,True) or symbols(obj,False)!=symbols(old,False):raise ValueError('HAL interface changed')
    asm=subprocess.check_output([str(a.llvm/'llvm-objdump'),'-dr',obj],text=True);(out/'hal.asm').write_text(asm)
    if any(n.endswith('/__mod_init_func') for n in sections(obj)) or re.search(r'^\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+.*\b[qvdshb]\d+(?:\b|\.)',asm,re.M):raise ValueError('Unexpected HAL initializer/SIMD')
    link=list(prior['link']);objects=[Path(v) for i,v in enumerate(link) if v.endswith('.o') and link[i-1]!='-o']
    if len(objects)!=125 or objects.count(old)!=1:raise ValueError('Wrong retained runtime link')
    retained={str(p):sha(p) for p in objects if p!=old};target=out/'WifiRuntimeMsiBinding.o'
    link[link.index('-o')+1]=str(target);link=[str(obj) if v==str(old) else v for v in link]
    lr=subprocess.run(link,capture_output=True);(out/'link.log').write_bytes(lr.stdout+lr.stderr);lr.check_returncode()
    if symbols(target,True)!=symbols(parent/'WifiRuntimeMsiBinding.o',True) or symbols(target,False)!=symbols(parent/'WifiRuntimeMsiBinding.o',False):raise ValueError('Combined runtime interface changed')
    for n,d in retained.items():
        if sha(Path(n))!=d:raise ValueError('Retained runtime changed')
    own=['tools/build_wifi_ce3_direct.py','tools/test_wifi_ce3_direct.py','drivers/EldenWifi/peach/Ce3DirectPointerPatch.py']
    proof=dict(prior);proof.update(ce3_direct_trial=True,ce3_direct_delta_reversible=True,ce3_only=True,
        ce3_ring_id=67,ce3_hp_offset=0x1b86400,ce3_qmi_shadow_config_unchanged=True,
        changed_units=['ath12k_wmi.o','ath12k_pci.o','w7_hal.o'],parent_vdev_binding_sha256=prior['binding_sha256'],
        binding_sha256=sha(target),hal_object_sha256=sha(obj),hal_fixed_source_sha256=sha(derived),
        ce3_direct_warning_count=r.stderr.count(b'warning:'),other_ce_mhi_irq_firmware_objects_unchanged=False,
        other_ce_mhi_irq_firmware_policy_unchanged=True,link=link,retained_objects=retained,
        hal_command=cmd,hal_consumed_inputs={n:sha(Path(n)) for n in deps},
        source_inputs={**prior['source_inputs'],**{n:sha(ROOT/n) for n in own}},hardware_tested=False)
    (out/'result.json').write_text(json.dumps(proof,indent=2)+'\n')
    print(json.dumps({n:proof[n] for n in ['compiled','ce3_direct_trial','binding_sha256','ce3_direct_warning_count','hardware_tested']}))


if __name__=='__main__':main()
