"""Compile matched first-access PCI/WMI units over the qualified state observer."""
import argparse,hashlib,json,re,shlex,subprocess,sys
from pathlib import Path
from replay_xnu_objects import global_symbols,sections
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'drivers/EldenWifi/peach'))
from UmacAccessPatch import patch


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def symbols(p,d):return {n for n,v in global_symbols(p).items() if bool(v[0]&0x0e)==d}


def main():
    if sys.flags.optimize:raise ValueError('Assertions required')
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('runtime-build','parent-build','timeline-build','llvm','output'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();base=a.runtime_build.resolve();parent=a.parent_build.resolve();timeline=a.timeline_build.resolve();out=a.output.resolve()
    prior=json.loads((parent/'result.json').read_text())
    if not prior.get('pci_state_trace_trial') or prior.get('ce3_direct_trial') or sha(parent/'WifiRuntimeMsiBinding.o')!=prior['binding_sha256']:raise ValueError('Qualified original-shadow observer parent required')
    out.mkdir(parents=True,exist_ok=False);changes={};units={}
    for name in ('pci.c','wmi.c'):
        report=prior if name=='pci.c' else prior['timeline_units']['ath12k_wmi.o']
        cmd=list(report['pci_state_command'] if name=='pci.c' else report['command'])
        original=parent/'pci.c' if name=='pci.c' else timeline/'wmi.c'
        old=parent/'ath12k_pci.o' if name=='pci.c' else timeline/'ath12k_wmi.o'
        source=out/name;source.write_bytes(patch(name,original.read_bytes()));raw=out/(name[:-2]+'.raw.o');obj=out/('ath12k_'+name[:-2]+'.o');dep=out/(name[:-2]+'.d')
        cmd[cmd.index(str(original))]=str(source);cmd[cmd.index('-o')+1]=str(raw);cmd[cmd.index('-MF')+1]=str(dep)
        if name=='wmi.c':cmd+=['-iquote',str(original.parent)]
        r=subprocess.run(cmd,cwd=out,capture_output=True);(out/(name+'.log')).write_bytes(r.stdout+r.stderr);r.check_returncode()
        deps=shlex.split(dep.read_text().replace('\\\n',' ').split(':',1)[1]);inherited=report['pci_state_consumed_inputs'] if name=='pci.c' else report['consumed_inputs']
        if set(deps)-{str(source)}!=set(inherited)-{str(original)}:raise ValueError('First-access dependencies changed')
        for n in deps:
            if n!=str(source) and sha(Path(n))!=inherited[n]:raise ValueError('First-access input changed')
        subprocess.run([str(a.llvm/'llvm-objcopy'),'--redefine-syms='+str(base/'objects/rename.txt'),str(raw),str(obj)],check=True)
        rename=dict(l.split() for l in (base/'objects/rename.txt').read_text().splitlines())
        if global_symbols(obj)!={rename.get(n,n):v for n,v in global_symbols(raw).items()} or sections(obj)!=sections(raw):raise ValueError('First-access rename changed code/data')
        if symbols(obj,True)!=symbols(old,True)|({'_elden_wifi_umac_access_first'} if name=='pci.c' else set()) or symbols(obj,False)!=symbols(old,False)|({'_elden_wifi_umac_access_first'} if name=='wmi.c' else set()):raise ValueError('First-access interface changed')
        asm=subprocess.check_output([str(a.llvm/'llvm-objdump'),'-dr',obj],text=True);(out/(name+'.asm')).write_text(asm)
        if any(n.endswith('/__mod_init_func') for n in sections(obj)) or re.search(r'^\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+.*\b[qvdshb]\d+(?:\b|\.)',asm,re.M):raise ValueError('First-access initializer/SIMD')
        changes[str(old)]=str(obj);units[name]=dict(source_sha256=sha(source),object_sha256=sha(obj),warnings=r.stderr.count(b'warning:'),command=cmd,consumed_inputs={n:sha(Path(n)) for n in deps})
    link=list(prior['link']);objects=[Path(v) for i,v in enumerate(link) if v.endswith('.o') and link[i-1]!='-o']
    if len(objects)!=125 or not set(changes)<=set(map(str,objects)):raise ValueError('Wrong retained first-access objects')
    retained={str(n):sha(n) for n in objects if str(n) not in changes};target=out/'WifiRuntimeMsiBinding.o';link[link.index('-o')+1]=str(target);link=[changes.get(v,v) for v in link]
    r=subprocess.run(link,capture_output=True);(out/'link.log').write_bytes(r.stdout+r.stderr);r.check_returncode()
    if symbols(target,True)!=symbols(parent/'WifiRuntimeMsiBinding.o',True)|{'_elden_wifi_umac_access_first'} or symbols(target,False)!=symbols(parent/'WifiRuntimeMsiBinding.o',False):raise ValueError('Combined first-access interface changed')
    for n,h in retained.items():
        if sha(Path(n))!=h:raise ValueError('Retained runtime changed')
    own=['tools/build_wifi_umac_access.py','tools/test_wifi_umac_access.py','drivers/EldenWifi/UmacAccess.inc','drivers/EldenWifi/peach/UmacAccessPatch.py']
    proof=dict(prior);proof.update(umac_access_trial=True,umac_access_reversible=True,umac_access_first_pmf_only=True,umac_access_balanced_extra_mhi=True,
        umac_access_poll_bound_ms=50,umac_access_ring_writes=0,binding_sha256=sha(target),runtime_added_exports=['_elden_ce3_timeline','_elden_wifi_umac_access_first'],
        access_units=units,link=link,retained_objects=retained,source_inputs={**prior['source_inputs'],**{n:sha(ROOT/n) for n in own}},hardware_tested=False)
    (out/'result.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps({k:proof[k] for k in ['compiled','umac_access_trial','binding_sha256','hardware_tested']}))


if __name__=='__main__':main()
