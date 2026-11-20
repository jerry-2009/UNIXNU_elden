"""Compile one PCI unit with bounded passive write/MHI state observation."""
import argparse,hashlib,json,re,shlex,subprocess,sys
from pathlib import Path
from replay_xnu_objects import global_symbols,sections
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'drivers/EldenWifi/peach'))
from PciStateTracePatch import patch


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def symbols(p,d):return {n for n,v in global_symbols(p).items() if bool(v[0]&0x0e)==d}


def main():
    if sys.flags.optimize:raise ValueError('Assertions required')
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('runtime-build','parent-build','llvm','output'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();base=a.runtime_build.resolve();parent=a.parent_build.resolve();out=a.output.resolve()
    prior=json.loads((parent/'result.json').read_text())
    if not prior.get('window_reselect_trial') or prior.get('ce3_direct_trial') or sha(parent/'WifiRuntimeMsiBinding.o')!=prior['binding_sha256']:
        raise ValueError('Qualified original-shadow window-reselect parent required')
    old=parent/'ath12k_pci.o';original=parent/'pci.c'
    if sha(old)!=prior['pci_reselect_object_sha256'] or sha(original)!=prior['pci_reselect_source_sha256']:
        raise ValueError('PCI parent source/object changed')
    out.mkdir(parents=True,exist_ok=False);source=out/'pci.c';source.write_bytes(patch(original.read_bytes()))
    cmd=list(prior['reselect_command']);raw=out/'ath12k_pci.raw.o';obj=out/'ath12k_pci.o';dep=out/'pci.d'
    cmd[cmd.index(str(original))]=str(source);cmd[cmd.index('-o')+1]=str(raw);cmd[cmd.index('-MF')+1]=str(dep)
    r=subprocess.run(cmd,cwd=out,capture_output=True);(out/'compile.log').write_bytes(r.stdout+r.stderr);r.check_returncode()
    deps=shlex.split(dep.read_text().replace('\\\n',' ').split(':',1)[1])
    if set(deps)-{str(source)}!=set(prior['reselect_consumed_inputs'])-{str(original)}:
        raise ValueError('Passive PCI dependency set changed')
    for n in deps:
        if n!=str(source) and sha(Path(n))!=prior['reselect_consumed_inputs'][n]:raise ValueError('PCI header changed')
    subprocess.run([str(a.llvm/'llvm-objcopy'),'--redefine-syms='+str(base/'objects/rename.txt'),str(raw),str(obj)],check=True)
    rename=dict(l.split() for l in (base/'objects/rename.txt').read_text().splitlines())
    if global_symbols(obj)!={rename.get(n,n):v for n,v in global_symbols(raw).items()} or sections(obj)!=sections(raw):
        raise ValueError('Passive PCI rename changed code/data')
    if symbols(obj,True)!=symbols(old,True) or symbols(obj,False)!=symbols(old,False):raise ValueError('PCI interface changed')
    asm=subprocess.check_output([str(a.llvm/'llvm-objdump'),'-dr',obj],text=True);(out/'pci.asm').write_text(asm)
    if any(n.endswith('/__mod_init_func') for n in sections(obj)) or re.search(r'^\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+.*\b[qvdshb]\d+(?:\b|\.)',asm,re.M):
        raise ValueError('PCI initializer/SIMD introduced')
    link=list(prior['link']);objects=[Path(v) for i,v in enumerate(link) if v.endswith('.o') and link[i-1]!='-o']
    if len(objects)!=125 or objects.count(old)!=1:raise ValueError('Wrong retained runtime')
    retained={str(n):sha(n) for n in objects if n!=old};target=out/'WifiRuntimeMsiBinding.o'
    link[link.index('-o')+1]=str(target);link=[str(obj) if v==str(old) else v for v in link]
    rlink=subprocess.run(link,capture_output=True);(out/'link.log').write_bytes(rlink.stdout+rlink.stderr);rlink.check_returncode()
    if symbols(target,True)!=symbols(parent/'WifiRuntimeMsiBinding.o',True) or symbols(target,False)!=symbols(parent/'WifiRuntimeMsiBinding.o',False):
        raise ValueError('Combined interface changed')
    for n,h in retained.items():
        if sha(Path(n))!=h:raise ValueError('Retained runtime changed')
    own=['tools/build_wifi_pci_state_trace.py','tools/test_wifi_pci_state_trace.py','drivers/EldenWifi/peach/PciStateTracePatch.py','drivers/EldenWifi/PciStateTrace.inc']
    proof=dict(prior);proof.update(pci_state_trace_trial=True,pci_state_trace_reversible=True,
        pci_state_write_records_max=32,pci_state_read_records_max=16,pci_state_no_new_mmio_writes=True,
        pci_state_existing_hook_not_replaced=True,pci_state_hook_owned_restore=True,pci_state_payload_logging=False,
        parent_state_binding_sha256=prior['binding_sha256'],binding_sha256=sha(target),pci_state_object_sha256=sha(obj),
        pci_state_source_sha256=sha(source),pci_state_warning_count=r.stderr.count(b'warning:'),
        pci_state_command=cmd,pci_state_consumed_inputs={n:sha(Path(n)) for n in deps},link=link,retained_objects=retained,
        source_inputs={**prior['source_inputs'],**{n:sha(ROOT/n) for n in own}},hardware_tested=False)
    (out/'result.json').write_text(json.dumps(proof,indent=2)+'\n')
    print(json.dumps({k:proof[k] for k in ['compiled','pci_state_trace_trial','binding_sha256','pci_state_warning_count','hardware_tested']}))


if __name__=='__main__':main()
