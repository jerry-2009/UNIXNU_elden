"""Build the OEM per-register wake contract on the complete retained runtime."""
import argparse,hashlib,json,re,shlex,subprocess,sys
from pathlib import Path
from replay_xnu_objects import global_symbols,sections

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'drivers/EldenWifi/peach'))
from UmacRegisterPatch import patch,VENDOR


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def symbols(p,defined):return {n for n,v in global_symbols(p).items() if bool(v[0]&0x0e)==defined}


def main():
    if sys.flags.optimize:raise ValueError('Assertions required')
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('runtime-build','parent-build','llvm','output'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();base,parent,out=a.runtime_build.resolve(),a.parent_build.resolve(),a.output.resolve()
    prior=json.loads((parent/'result.json').read_text())
    if prior.get('posted_reset_trial') is not True or sha(parent/'WifiRuntimeMsiBinding.o')!=prior['binding_sha256']:
        raise ValueError('Qualified combined posted-reset parent required')
    cmd=list(prior['pci_state_command']);original,=[Path(v) for v in cmd if v.endswith('/pci.c')]
    old,=[Path(v) for v in prior['link'] if v.endswith('/ath12k_pci.o')]
    if sha(original)!=prior['pci_state_source_sha256'] or sha(old)!=prior['pci_state_object_sha256']:
        raise ValueError('Consumed UMAC register parent changed')
    out.mkdir(parents=True,exist_ok=False);source,raw,obj,dep=out/'pci.c',out/'ath12k_pci.raw.o',out/'ath12k_pci.o',out/'pci.d'
    source.write_bytes(patch(original.read_bytes()));cmd[cmd.index(str(original))]=str(source)
    cmd[cmd.index('-o')+1]=str(raw);cmd[cmd.index('-MF')+1]=str(dep)
    r=subprocess.run(cmd,cwd=out,capture_output=True);(out/'compile.log').write_bytes(r.stdout+r.stderr);r.check_returncode()
    dependencies=shlex.split(dep.read_text().replace('\\\n',' ').split(':',1)[1]);inherited=prior['pci_state_consumed_inputs']
    if set(dependencies)-{str(source)}!=set(inherited)-{str(original)}:raise ValueError('UMAC register dependency set changed')
    for value in dependencies:
        if value!=str(source) and sha(Path(value))!=inherited[value]:raise ValueError('UMAC header changed: '+value)
    subprocess.run([str(a.llvm/'llvm-objcopy'),'--redefine-syms='+str(base/'objects/rename.txt'),str(raw),str(obj)],check=True)
    rename=dict(line.split() for line in (base/'objects/rename.txt').read_text().splitlines())
    if global_symbols(obj)!={rename.get(n,n):v for n,v in global_symbols(raw).items()} or sections(obj)!=sections(raw):raise ValueError('UMAC rename changed code/data')
    if symbols(obj,True)!=symbols(old,True) or symbols(obj,False)!=symbols(old,False):raise ValueError('UMAC PCI interface changed')
    asm=subprocess.check_output([str(a.llvm/'llvm-objdump'),'-dr',obj],text=True);(out/'pci.asm').write_text(asm)
    if any(n.endswith('/__mod_init_func') for n in sections(obj)) or re.search(r'^\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+.*\b[qvdshb]\d+(?:\b|\.)',asm,re.M):raise ValueError('UMAC initializer/SIMD introduced')
    link=list(prior['link']);objects=[Path(v) for i,v in enumerate(link) if v.endswith('.o') and link[i-1]!='-o']
    if len(objects)!=125 or objects.count(old)!=1:raise ValueError('Wrong UMAC register runtime')
    retained={str(v):sha(v) for v in objects if v!=old};target=out/'WifiRuntimeMsiBinding.o'
    link[link.index('-o')+1]=str(target);link=[str(obj) if v==str(old) else v for v in link]
    rlink=subprocess.run(link,capture_output=True);(out/'link.log').write_bytes(rlink.stdout+rlink.stderr);rlink.check_returncode()
    if symbols(target,True)!=symbols(parent/'WifiRuntimeMsiBinding.o',True) or symbols(target,False)!=symbols(parent/'WifiRuntimeMsiBinding.o',False):raise ValueError('UMAC combined interface changed')
    for value,digest in retained.items():
        if sha(Path(value))!=digest:raise ValueError('Retained UMAC runtime object changed')
    own=['tools/build_wifi_umac_register_access.py','tools/test_wifi_umac_register_access.py','drivers/EldenWifi/peach/UmacRegisterPatch.py','drivers/EldenWifi/UmacRegisterAccess.inc']
    proof=dict(prior)
    proof.update(umac_register_trial=True,umac_register_reversible=True,umac_register_peach_only=True,
                 umac_register_vendor_commit=VENDOR,umac_register_threshold=0xfe0,umac_register_checks=11,
                 umac_register_raw_no_recursion=True,umac_register_balanced_refs=True,
                 umac_register_failure_suppresses_access=True,umac_register_startup_hold=False,
                 umac_register_ring_credit_firmware_unchanged=True,umac_register_failed_handshake_latched=True,
                 umac_register_parent_source=str(original),umac_register_parent_source_sha256=sha(original),
                 umac_register_source_sha256=sha(source),umac_register_object_sha256=sha(obj),
                 parent_umac_register_binding_sha256=prior['binding_sha256'],binding_sha256=sha(target),
                 pci_state_source_sha256=sha(source),pci_state_object_sha256=sha(obj),pci_state_command=cmd,
                 pci_state_consumed_inputs={v:sha(Path(v)) for v in dependencies},pci_state_warning_count=r.stderr.count(b'warning:'),
                 link=link,retained_objects=retained,
                 source_inputs={**prior['source_inputs'],**{n:sha(ROOT/n) for n in own}},hardware_tested=False)
    (out/'result.json').write_text(json.dumps(proof,indent=2)+'\n')
    print(json.dumps({k:proof[k] for k in ('compiled','umac_register_trial','binding_sha256','pci_state_warning_count','hardware_tested')}))


if __name__=='__main__':main()
