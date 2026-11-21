"""Compile one consolidated first-failure observation without changing controls."""
import argparse,hashlib,json,re,shlex,subprocess,sys
from pathlib import Path
from replay_xnu_objects import global_symbols,sections
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'drivers/EldenWifi/peach'))
from FirstFailurePatch import patch


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def symbols(p,d):return {n for n,v in global_symbols(p).items() if bool(v[0]&0x0e)==d}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('runtime-build','parent-build','worker-build','llvm','output'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();base,parent,out=a.runtime_build.resolve(),a.parent_build.resolve(),a.output.resolve();prior=json.loads((parent/'result.json').read_text());worker=json.loads((a.worker_build/'result.json').read_text())
    if prior.get('umac_register_trial') is not True or worker.get('first_failure_physical') is not True or sha(parent/'WifiRuntimeMsiBinding.o')!=prior['binding_sha256']:raise ValueError('Qualified UMAC-register and first-failure worker required')
    out.mkdir(parents=True,exist_ok=False);changes={};units={};parents={}
    for n in ('pci.c','core.c'):
        row=prior if n=='pci.c' else prior['board_state_units'][n]
        cmd=list(row['pci_state_command'] if n=='pci.c' else row['command'])
        original,=[Path(v) for v in cmd if v.endswith('/'+n)]
        name='ath12k_'+n[:-2]+'.o';old,=[Path(v) for v in prior['link'] if v.endswith('/'+name)]
        sh=row['pci_state_source_sha256'] if n=='pci.c' else row['source_sha256'];oh=row['pci_state_object_sha256'] if n=='pci.c' else row['object_sha256']
        if sha(original)!=sh or sha(old)!=oh:raise ValueError('First-failure parent source/object changed: '+n)
        parents[n]=dict(source=str(original),source_sha256=sh,object=str(old),object_sha256=oh)
        source,raw,obj,dep=out/n,out/(n[:-2]+'.raw.o'),out/name,out/(n[:-2]+'.d');source.write_bytes(patch(n,original.read_bytes()))
        cmd[cmd.index(str(original))]=str(source);cmd[cmd.index('-o')+1]=str(raw);cmd[cmd.index('-MF')+1]=str(dep)
        r=subprocess.run(cmd,cwd=out,capture_output=True);(out/(n+'.log')).write_bytes(r.stdout+r.stderr);r.check_returncode()
        deps=shlex.split(dep.read_text().replace('\\\n',' ').split(':',1)[1]);inherited=row['pci_state_consumed_inputs'] if n=='pci.c' else row['consumed_inputs']
        if set(deps)-{str(source)}!=set(inherited)-{str(original)}:raise ValueError('First-failure dependency set changed: '+n)
        for v in deps:
            if v!=str(source) and sha(Path(v))!=inherited[v]:raise ValueError('First-failure header changed: '+v)
        subprocess.run([str(a.llvm/'llvm-objcopy'),'--redefine-syms='+str(base/'objects/rename.txt'),str(raw),str(obj)],check=True)
        rename=dict(line.split() for line in (base/'objects/rename.txt').read_text().splitlines())
        if global_symbols(obj)!={rename.get(k,k):v for k,v in global_symbols(raw).items()} or sections(obj)!=sections(raw):raise ValueError('First-failure rename changed code/data')
        expected_defs=symbols(old,True)|({'_elden_wifi_first_failure_sample'} if n=='pci.c' else set())
        expected_refs=symbols(old,False)|({'_elden_wifi_first_failure_physical'} if n=='pci.c' else {'_elden_wifi_first_failure_sample'})
        if symbols(obj,True)!=expected_defs or symbols(obj,False)!=expected_refs:raise ValueError('First-failure unit interface changed: '+n)
        asm=subprocess.check_output([str(a.llvm/'llvm-objdump'),'-dr',obj],text=True);(out/(n+'.asm')).write_text(asm)
        if any(k.endswith('/__mod_init_func') for k in sections(obj)) or re.search(r'^\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+.*\b[qvdshb]\d+(?:\b|\.)',asm,re.M):raise ValueError('First-failure initializer/SIMD')
        changes[str(old)]=str(obj);units[n]=dict(source=str(source),source_sha256=sha(source),object=str(obj),object_sha256=sha(obj),command=cmd,consumed_inputs={v:sha(Path(v)) for v in deps},warnings=r.stderr.count(b'warning:'))
    link=list(prior['link']);objects=[Path(v) for i,v in enumerate(link) if v.endswith('.o') and link[i-1]!='-o']
    if len(objects)!=125 or not set(changes)<=set(map(str,objects)):raise ValueError('Wrong first-failure runtime object list')
    retained={str(v):sha(v) for v in objects if str(v) not in changes};target=out/'WifiRuntimeMsiBinding.o'
    link[link.index('-o')+1]=str(target);link=[changes.get(v,v) for v in link];r=subprocess.run(link,capture_output=True);(out/'link.log').write_bytes(r.stdout+r.stderr);r.check_returncode()
    if symbols(target,True)!=symbols(parent/'WifiRuntimeMsiBinding.o',True)|{'_elden_wifi_first_failure_sample'} or symbols(target,False)!=symbols(parent/'WifiRuntimeMsiBinding.o',False)|{'_elden_wifi_first_failure_physical'}:raise ValueError('First-failure combined interface differs')
    for n,h in retained.items():
        if sha(Path(n))!=h:raise ValueError('Retained first-failure object changed')
    own=['tools/build_wifi_first_failure.py','tools/test_wifi_first_failure.py','drivers/EldenWifi/peach/FirstFailurePatch.py','drivers/EldenWifi/FirstFailurePci.inc']
    proof=dict(prior);proof.update(first_failure_trial=True,first_failure_reversible=True,first_failure_no_new_control_writes=True,first_failure_raw_no_wake=True,
        first_failure_stages=[12,90],first_failure_raw_count=21,first_failure_physical_count=47,first_failure_readclear_excluded=True,
        first_failure_worker_sha256=worker['object_sha256'],first_failure_parent_units=parents,first_failure_units=units,
        binding_sha256=sha(target),link=link,retained_objects=retained,runtime_added_exports=prior['runtime_added_exports']+['_elden_wifi_first_failure_sample'],
        pci_state_source_sha256=units['pci.c']['source_sha256'],pci_state_object_sha256=units['pci.c']['object_sha256'],pci_state_command=units['pci.c']['command'],pci_state_consumed_inputs=units['pci.c']['consumed_inputs'],
        source_inputs={**prior['source_inputs'],**{n:sha(ROOT/n) for n in own}},hardware_tested=False)
    (out/'result.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps({k:proof[k] for k in ('compiled','first_failure_trial','binding_sha256','hardware_tested')}))


if __name__=='__main__':main()
