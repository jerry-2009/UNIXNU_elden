"""Rebuild one WMI unit with the OEM non-MLO array contract, retaining UMAC."""
import argparse
import hashlib
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path
from replay_xnu_objects import global_symbols,sections

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'drivers/EldenWifi/peach'))
from VdevMloArrayPatch import patch


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_text())
def symbols(path,defined):return {n for n,v in global_symbols(path).items() if bool(v[0]&0x0e)==defined}


def main():
    if sys.flags.optimize:raise ValueError('Assertions required')
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('runtime-build','stride-build','umac-build','llvm','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args();base=args.runtime_build.resolve();stride=args.stride_build.resolve()
    parent=args.umac_build.resolve();out=args.output.resolve();prior=read(parent/'result.json');sp=read(stride/'result.json')
    if prior.get('umac_hold_trial') is not True or prior.get('umac_delta_reversible') is not True or prior.get('mhi_hold_trial') or prior['parent_stride_binding_sha256']!=sp['binding_sha256'] or sha(parent/'WifiRuntimeMsiBinding.o')!=prior['binding_sha256']:
        raise ValueError('Qualified distinct OEM UMAC runtime required')
    original=stride/'wmi.c';old=stride/'ath12k_wmi.o'
    if sha(original)!=sp['derived_source_sha256'] or sha(old)!=sp['object_sha256']:
        raise ValueError('Retained full-stride WMI changed')
    out.mkdir(parents=True,exist_ok=False);source=out/'wmi.c';source.write_bytes(patch(original.read_bytes()))
    command=list(sp['command']);identity=read(base/'objects/raw/ath12k_wmi.inputs.json')
    raw=out/'ath12k_wmi.raw.o';obj=out/'ath12k_wmi.o';dep=out/'wmi.d'
    command[command.index(str(original))]=str(source);command[command.index('-o')+1]=str(raw);command[command.index('-MF')+1]=str(dep)
    if command[command.index('-target')+1]!='arm64-apple-ios17.0' or '-mgeneral-regs-only' not in command:
        raise ValueError('Wrong scalar iOS17 WMI command')
    compiled=subprocess.run(command,cwd=out,capture_output=True)
    (out/'compile.log').write_bytes(compiled.stdout+compiled.stderr);compiled.check_returncode()
    deps=shlex.split(dep.read_text().replace('\\\n',' ').split(':',1)[1])
    if set(deps)-{str(source)}!=set(sp['consumed_inputs'])-{str(original)}:
        raise ValueError('WMI dependencies changed')
    for name in deps:
        if name!=str(source) and sha(Path(name))!=identity['dependencies'][name]:
            raise ValueError('WMI header input changed')
    subprocess.run([str(args.llvm/'llvm-objcopy'),'--redefine-syms='+str(base/'objects/rename.txt'),str(raw),str(obj)],check=True)
    rename=dict(line.split() for line in (base/'objects/rename.txt').read_text().splitlines())
    if global_symbols(obj)!={rename.get(n,n):v for n,v in global_symbols(raw).items()} or sections(raw)!=sections(obj):
        raise ValueError('WMI rename changed code/data')
    if symbols(obj,True)!=symbols(old,True) or symbols(obj,False)!=symbols(old,False):
        raise ValueError('WMI interface changed')
    if any(n.endswith('/__mod_init_func') for n in sections(obj)):raise ValueError('WMI initializer introduced')
    asm=subprocess.check_output([str(args.llvm/'llvm-objdump'),'-dr',obj],text=True);(out/'wmi.asm').write_text(asm)
    if re.search(r'^\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+.*\b[qvdshb]\d+(?:\b|\.)',asm,re.M):raise ValueError('Unexpected WMI SIMD')
    link=list(prior['link']);objects=[Path(v) for i,v in enumerate(link) if v.endswith('.o') and link[i-1]!='-o']
    if len(objects)!=125 or objects.count(old)!=1:raise ValueError('Expected exact125-object UMAC runtime')
    retained={str(p):sha(p) for p in objects if p!=old}
    target=out/'WifiRuntimeMsiBinding.o';link[link.index('-o')+1]=str(target)
    link=[str(obj) if v==str(old) else v for v in link]
    linked=subprocess.run(link,capture_output=True);(out/'link.log').write_bytes(linked.stdout+linked.stderr);linked.check_returncode()
    if symbols(target,True)!=symbols(parent/'WifiRuntimeMsiBinding.o',True) or symbols(target,False)!=symbols(parent/'WifiRuntimeMsiBinding.o',False):
        raise ValueError('Complete runtime interface changed')
    for name,digest in retained.items():
        if sha(Path(name))!=digest:raise ValueError('Retained runtime object changed')
    own=['tools/build_wifi_vdev_mlo_array.py','tools/test_wifi_vdev_mlo_array.py','drivers/EldenWifi/peach/VdevMloArrayPatch.py']
    proof=dict(prior)
    proof.update(vdev_empty_mlo_array=True,vdev_array_delta_reversible=True,
        vdev_array_peach_only=True,vdev_other_and_mlo_streams_unchanged=True,
        vdev_array_tag=18,vdev_array_bytes=4,vdev_array_vendor_commit='d50b305f7da9e14715a25120a4ac7b1a4b8b97c3',
        parent_umac_binding_sha256=prior['binding_sha256'],binding_sha256=sha(target),
        wmi_object_sha256=sha(obj),vdev_parent_wmi_source_sha256=sha(original),
        vdev_fixed_wmi_source_sha256=sha(source),vdev_wmi_command=command,vdev_wmi_warnings=compiled.stderr.count(b'warning:'),
        source_inputs={**prior['source_inputs'],**{n:sha(ROOT/n) for n in own}},
        vdev_consumed_inputs={n:sha(Path(n)) for n in deps},retained_objects=retained,link=link,hardware_tested=False)
    (out/'result.json').write_text(json.dumps(proof,indent=2)+'\n')
    print(json.dumps({n:proof[n] for n in ['compiled','vdev_empty_mlo_array','binding_sha256','vdev_wmi_warnings','hardware_tested']}))


if __name__=='__main__':main()
