"""Rebuild one PCI unit with the exact OEM Peach no-local-cache window policy."""
import argparse,hashlib,json,re,shlex,subprocess,sys
from pathlib import Path
from replay_xnu_objects import global_symbols,sections
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'drivers/EldenWifi/peach'))
from WindowReselectPatch import patch


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())
def symbols(p,d):return {n for n,v in global_symbols(p).items() if bool(v[0]&0x0e)==d}


def main():
    if sys.flags.optimize:raise ValueError('Assertions required')
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('runtime-build','parent-build','umac-build','llvm','output'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();base=a.runtime_build.resolve();parent=a.parent_build.resolve();umac=a.umac_build.resolve();out=a.output.resolve();prior=read(parent/'result.json');up=read(umac/'result.json')
    if prior.get('ce3_timeline_trial') is not True or prior.get('ce3_direct_trial') or sha(parent/'WifiRuntimeMsiBinding.o')!=prior['binding_sha256']:
        raise ValueError('Qualified original-shadow timeline parent required')
    original=umac/'pci.c';old=umac/'ath12k_pci.o'
    if sha(old)!=prior['pci_object_sha256'] or sha(old)!=up['pci_object_sha256']:raise ValueError('Exact PCI object changed')
    out.mkdir(parents=True,exist_ok=False);source=out/'pci.c';source.write_bytes(patch(original.read_bytes()))
    cmd=list(up['pci_command']);raw=out/'ath12k_pci.raw.o';obj=out/'ath12k_pci.o';dep=out/'pci.d'
    cmd[cmd.index(str(original))]=str(source);cmd[cmd.index('-o')+1]=str(raw);cmd[cmd.index('-MF')+1]=str(dep)
    r=subprocess.run(cmd,cwd=out,capture_output=True);(out/'compile.log').write_bytes(r.stdout+r.stderr);r.check_returncode()
    deps=shlex.split(dep.read_text().replace('\\\n',' ').split(':',1)[1])
    if set(deps)-{str(source)}!=set(up['pci_consumed_inputs'])-{str(original)}:raise ValueError('PCI dependency set changed')
    for n in deps:
        if n!=str(source) and sha(Path(n))!=up['pci_consumed_inputs'][n]:raise ValueError('PCI header changed')
    subprocess.run([str(a.llvm/'llvm-objcopy'),'--redefine-syms='+str(base/'objects/rename.txt'),str(raw),str(obj)],check=True)
    rename=dict(l.split() for l in (base/'objects/rename.txt').read_text().splitlines())
    if global_symbols(obj)!={rename.get(n,n):v for n,v in global_symbols(raw).items()} or sections(raw)!=sections(obj):raise ValueError('PCI rename changed code/data')
    if symbols(obj,True)!=symbols(old,True) or symbols(obj,False)!=symbols(old,False):raise ValueError('PCI interface changed')
    asm=subprocess.check_output([str(a.llvm/'llvm-objdump'),'-dr',obj],text=True);(out/'pci.asm').write_text(asm)
    if any(n.endswith('/__mod_init_func') for n in sections(obj)) or re.search(r'^\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+.*\b[qvdshb]\d+(?:\b|\.)',asm,re.M):raise ValueError('Unexpected PCI initializer/SIMD')
    link=list(prior['link']);objects=[Path(v) for i,v in enumerate(link) if v.endswith('.o') and link[i-1]!='-o']
    if len(objects)!=125 or objects.count(old)!=1:raise ValueError('Wrong retained timeline runtime')
    retained={str(p):sha(p) for p in objects if p!=old};target=out/'WifiRuntimeMsiBinding.o'
    link[link.index('-o')+1]=str(target);link=[str(obj) if v==str(old) else v for v in link]
    lr=subprocess.run(link,capture_output=True);(out/'link.log').write_bytes(lr.stdout+lr.stderr);lr.check_returncode()
    if symbols(target,True)!=symbols(parent/'WifiRuntimeMsiBinding.o',True) or symbols(target,False)!=symbols(parent/'WifiRuntimeMsiBinding.o',False):raise ValueError('Combined runtime interface changed')
    for n,h in retained.items():
        if sha(Path(n))!=h:raise ValueError('Retained runtime changed')
    own=['tools/build_wifi_window_reselect.py','tools/test_wifi_window_reselect.py','drivers/EldenWifi/peach/WindowReselectPatch.py']
    proof=dict(prior);proof.update(window_reselect_trial=True,window_delta_reversible=True,window_peach_only=True,window_lock_value_readback_preserved=True,
        parent_timeline_binding_sha256=prior['binding_sha256'],binding_sha256=sha(target),pci_reselect_object_sha256=sha(obj),
        pci_reselect_source_sha256=sha(source),pci_reselect_warning_count=r.stderr.count(b'warning:'),
        reselect_command=cmd,reselect_consumed_inputs={n:sha(Path(n)) for n in deps},
        link=link,retained_objects=retained,source_inputs={**prior['source_inputs'],**{n:sha(ROOT/n) for n in own}},hardware_tested=False)
    (out/'result.json').write_text(json.dumps(proof,indent=2)+'\n')
    print(json.dumps({n:proof[n] for n in ['compiled','window_reselect_trial','binding_sha256','pci_reselect_warning_count','hardware_tested']}))


if __name__=='__main__':main()
