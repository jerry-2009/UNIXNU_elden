"""Compile the optional real MHI lease with the retained full-stride runtime."""
import argparse,hashlib,json,re,shlex,subprocess,sys
from pathlib import Path
from replay_xnu_objects import global_symbols,sections
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'drivers/EldenWifi/peach'))
from MhiLeasePatch import patch


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_text())
def symbols(path,defined):return {n for n,v in global_symbols(path).items() if bool(v[0]&0x0e)==defined}


def main():
    if sys.flags.optimize:raise ValueError('Assertions required')
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('runtime-build','stride-build','llvm','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args();base=args.runtime_build.resolve();parent=args.stride_build.resolve();out=args.output.resolve()
    prior=read(parent/'result.json')
    if prior.get('mac_phy_stride_fix') is not True or prior['changed_units']!=['ath12k_wmi.o'] or sha(parent/'WifiRuntimeMsiBinding.o')!=prior['binding_sha256']:
        raise ValueError('Qualified plain full-stride runtime required')
    manifest=read(base/'objects/build-report.json');rows=[row for row in manifest['objects'] if Path(row['path']).name=='ath12k_pci.o']
    if len(rows)!=1:raise ValueError('Expected one plain PCI unit')
    row=rows[0];original=Path(row['source']);old=Path(row['path'])
    if sha(original)!=row['source_sha256'] or sha(old)!=row['object_sha256']:raise ValueError('PCI source/object changed')
    out.mkdir(parents=True,exist_ok=False);source=out/'pci.c';source.write_bytes(patch(original.read_bytes()))
    identity=read(base/'objects/raw/ath12k_pci.inputs.json');command=list(identity['command']);raw=out/'ath12k_pci.raw.o';obj=out/'ath12k_pci.o';dep=out/'pci.d'
    command[command.index(str(original))]=str(source);command[command.index('-o')+1]=str(raw);command[command.index('-MF')+1]=str(dep)
    result=subprocess.run(command,cwd=out,capture_output=True);(out/'compile.log').write_bytes(result.stdout+result.stderr);result.check_returncode()
    deps=shlex.split(dep.read_text().replace('\\\n',' ').split(':',1)[1])
    if set(deps)-{str(source)}!=set(identity['dependencies'])-{str(original)}:raise ValueError('PCI dependency set changed')
    for name in deps:
        if sha(Path(name))!=(sha(source) if name==str(source) else identity['dependencies'][name]):raise ValueError('PCI dependency changed')
    subprocess.run([str(args.llvm/'llvm-objcopy'),'--redefine-syms='+str(base/'objects/rename.txt'),str(raw),str(obj)],check=True)
    added_calls={'_elden_wifi_mhi_hold_requested','_nwk_mhi_device_get_sync','_nwk_mhi_device_put'}
    if symbols(obj,True)!=symbols(old,True) or symbols(obj,False)!=symbols(old,False)|added_calls:
        raise ValueError('Unexpected PCI interface delta')
    if sections(obj)!=sections(raw) or any(name.endswith('/__mod_init_func') for name in sections(obj)):raise ValueError('PCI section/initializer changed')
    assembly=subprocess.check_output([str(args.llvm/'llvm-objdump'),'-dr',obj],text=True);(out/'pci.asm').write_text(assembly)
    if re.search(r'^\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+.*\b[qvdshb]\d+(?:\b|\.)',assembly,re.M):raise ValueError('PCI unexpected SIMD')
    link=list(prior['link']);objects=[Path(item) for i,item in enumerate(link) if item.endswith('.o') and link[i-1]!='-o'];retained={str(path):sha(path) for path in objects}
    if len(objects)!=125 or objects.count(old)!=1:raise ValueError('Wrong retained runtime link')
    target=out/'WifiRuntimeMsiBinding.o';link[link.index('-o')+1]=str(target);link=[str(obj) if item==str(old) else item for item in link]
    result_link=subprocess.run(link,capture_output=True);(out/'link.log').write_bytes(result_link.stdout+result_link.stderr);result_link.check_returncode()
    if symbols(target,True)!=symbols(parent/'WifiRuntimeMsiBinding.o',True) or symbols(target,False)!=symbols(parent/'WifiRuntimeMsiBinding.o',False)|{'_elden_wifi_mhi_hold_requested'}:
        raise ValueError('Unexpected combined MHI-lease import delta')
    for name,digest in retained.items():
        if sha(Path(name))!=digest:raise ValueError('Retained runtime object changed')
    own=['tools/build_wifi_mhi_lease.py','tools/test_wifi_mhi_lease.py','drivers/EldenWifi/MhiLease.inc','drivers/EldenWifi/peach/MhiLeasePatch.py']
    proof=dict(prior);proof.update(mhi_hold_trial=True,lease_delta_reversible=True,native_opt_in_only=True,
        binding_sha256=sha(target),parent_stride_binding_sha256=prior['binding_sha256'],pci_object_sha256=sha(obj),
        changed_units=['ath12k_wmi.o','ath12k_pci.o'],other_ce_mhi_pci_irq_firmware_objects_unchanged=False,
        other_ce_mhi_irq_firmware_objects_unchanged=True,source_inputs={**prior['source_inputs'],**{name:sha(ROOT/name) for name in own}},
        imports_exports_unchanged=False,added_native_import='_elden_wifi_mhi_hold_requested',link=link,
        pci_command=command,pci_consumed_inputs={name:sha(Path(name)) for name in deps},
        pci_warning_count=result.stderr.count(b'warning:'),retained_objects={name:digest for name,digest in retained.items() if name!=str(old)},
        hardware_tested=False)
    (out/'result.json').write_text(json.dumps(proof,indent=2)+'\n')
    print(json.dumps({key:proof[key] for key in ('compiled','mhi_hold_trial','binding_sha256','pci_warning_count','hardware_tested')}))


if __name__=='__main__':main()
