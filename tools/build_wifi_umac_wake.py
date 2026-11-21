"""Compile the distinct OEM MHI+UMAC wake trial over the normal stride runtime."""
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
from UmacWakePatch import patch


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def symbols(path, defined):
    return {n for n,v in global_symbols(path).items() if bool(v[0]&0x0e)==defined}


def main():
    if sys.flags.optimize:
        raise ValueError('Assertions required')
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('runtime-build','stride-build','llvm','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    base=args.runtime_build.resolve(); parent=args.stride_build.resolve(); out=args.output.resolve()
    prior=read(parent/'result.json')
    if prior.get('mac_phy_stride_fix') is not True or prior['changed_units']!=['ath12k_wmi.o'] or sha(parent/'WifiRuntimeMsiBinding.o')!=prior['binding_sha256']:
        raise ValueError('Qualified normal full-stride runtime required')
    manifest=read(base/'objects/build-report.json')
    row,=[row for row in manifest['objects'] if Path(row['path']).name=='ath12k_pci.o']
    original=Path(row['source']); old=Path(row['path'])
    if sha(original)!=row['source_sha256'] or sha(old)!=row['object_sha256']:
        raise ValueError('Original PCI source/object changed')
    out.mkdir(parents=True,exist_ok=False)
    source=out/'pci.c'; source.write_bytes(patch(original.read_bytes()))
    identity=read(base/'objects/raw/ath12k_pci.inputs.json')
    command=list(identity['command']); raw=out/'ath12k_pci.raw.o'; obj=out/'ath12k_pci.o'; dep=out/'pci.d'
    if command[command.index('-target')+1]!='arm64-apple-ios17.0' or '-mgeneral-regs-only' not in command:
        raise ValueError('Wrong scalar iOS17 compilation')
    command[command.index(str(original))]=str(source)
    command[command.index('-o')+1]=str(raw); command[command.index('-MF')+1]=str(dep)
    result=subprocess.run(command,cwd=out,capture_output=True)
    (out/'compile.log').write_bytes(result.stdout+result.stderr); result.check_returncode()
    deps=shlex.split(dep.read_text().replace('\\\n',' ').split(':',1)[1])
    if set(deps)-{str(source)}!=set(identity['dependencies'])-{str(original)}:
        raise ValueError('PCI dependency set changed')
    for name in deps:
        if sha(Path(name))!=(sha(source) if name==str(source) else identity['dependencies'][name]):
            raise ValueError('PCI dependency changed')
    subprocess.run([str(args.llvm/'llvm-objcopy'),'--redefine-syms='+str(base/'objects/rename.txt'),str(raw),str(obj)],check=True)
    calls={'_elden_wifi_umac_hold_requested','_nwk_mhi_device_get_sync','_nwk_mhi_device_put','_nwk_lx_delay_us'}
    if symbols(obj,True)!=symbols(old,True) or symbols(obj,False)!=symbols(old,False)|calls:
        raise ValueError('Unexpected PCI interface delta')
    rename=dict(line.split() for line in (base/'objects/rename.txt').read_text().splitlines())
    if global_symbols(obj)!={rename.get(n,n):v for n,v in global_symbols(raw).items()} or sections(obj)!=sections(raw):
        raise ValueError('PCI symbol rename changed code/data')
    if any(name.endswith('/__mod_init_func') for name in sections(obj)):
        raise ValueError('PCI initializer introduced')
    assembly=subprocess.check_output([str(args.llvm/'llvm-objdump'),'-dr',obj],text=True)
    (out/'pci.asm').write_text(assembly)
    if re.search(r'^\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+.*\b[qvdshb]\d+(?:\b|\.)',assembly,re.M):
        raise ValueError('Unexpected PCI SIMD')
    link=list(prior['link'])
    objects=[Path(v) for i,v in enumerate(link) if v.endswith('.o') and link[i-1]!='-o']
    retained={str(path):sha(path) for path in objects}
    if len(objects)!=125 or objects.count(old)!=1:
        raise ValueError('Wrong retained runtime link')
    target=out/'WifiRuntimeMsiBinding.o'
    link[link.index('-o')+1]=str(target); link=[str(obj) if v==str(old) else v for v in link]
    linked=subprocess.run(link,capture_output=True)
    (out/'link.log').write_bytes(linked.stdout+linked.stderr); linked.check_returncode()
    if symbols(target,True)!=symbols(parent/'WifiRuntimeMsiBinding.o',True) or symbols(target,False)!=symbols(parent/'WifiRuntimeMsiBinding.o',False)|{'_elden_wifi_umac_hold_requested'}:
        raise ValueError('Unexpected combined UMAC-wake import delta')
    for name,digest in retained.items():
        if sha(Path(name))!=digest:
            raise ValueError('Retained runtime changed')
    own=['tools/build_wifi_umac_wake.py','tools/test_wifi_umac_wake.py',
         'drivers/EldenWifi/UmacWake.inc','drivers/EldenWifi/peach/UmacWakePatch.py']
    proof=dict(prior)
    proof.update(umac_hold_trial=True,umac_delta_reversible=True,native_opt_in_only=True,
        mhi_reference_and_umac_handshake=True,umac_request_offset=0x3004,umac_status_offset=0x1e04040,
        umac_ready_value=2,umac_polling_bound_ms=50,mhi_hold_trial=False,
        binding_sha256=sha(target),parent_stride_binding_sha256=prior['binding_sha256'],
        pci_object_sha256=sha(obj),changed_units=['ath12k_wmi.o','ath12k_pci.o'],
        other_ce_mhi_pci_irq_firmware_objects_unchanged=False,other_ce_mhi_irq_firmware_objects_unchanged=True,
        source_inputs={**prior['source_inputs'],**{name:sha(ROOT/name) for name in own}},
        imports_exports_unchanged=False,added_native_import='_elden_wifi_umac_hold_requested',link=link,
        pci_command=command,pci_consumed_inputs={name:sha(Path(name)) for name in deps},
        pci_warning_count=result.stderr.count(b'warning:'),
        retained_objects={name:digest for name,digest in retained.items() if name!=str(old)},hardware_tested=False)
    (out/'result.json').write_text(json.dumps(proof,indent=2)+'\n')
    print(json.dumps({key:proof[key] for key in ('compiled','umac_hold_trial','binding_sha256','pci_warning_count','hardware_tested')}))


if __name__=='__main__':
    main()
