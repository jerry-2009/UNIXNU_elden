"""Compile physical board-state observations over exact OEM initialization."""
import argparse,hashlib,json,re,shlex,subprocess,sys
from pathlib import Path
from replay_xnu_objects import global_symbols,sections
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'drivers/EldenWifi/peach'))
from BoardStatePatch import patch


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def symbols(p,d):return {n for n,v in global_symbols(p).items() if bool(v[0]&0x0e)==d}


def main():
    if sys.flags.optimize:raise ValueError('Assertions required')
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('runtime-build','parent-build','timeline-build','llvm','output'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();base=a.runtime_build.resolve();parent=a.parent_build.resolve();timeline=a.timeline_build.resolve();out=a.output.resolve();prior=json.loads((parent/'result.json').read_text())
    if not prior.get('oem_init_mode_trial') or not prior.get('pci_state_trace_trial') or prior.get('umac_access_trial') or prior.get('umac_command_lease_trial') or sha(parent/'WifiRuntimeMsiBinding.o')!=prior['binding_sha256']:raise ValueError('Qualified passive state parent required')
    out.mkdir(parents=True,exist_ok=False);changes={};units={}
    for name in ('core.c','wmi.c'):
        objname='ath12k_'+name[:-2]+'.o';row=prior['oem_init_units'][name];original=timeline/name;old=timeline/objname;source=out/name;source.write_bytes(patch(name,original.read_bytes()))
        if sha(old)!=row['object_sha256'] or sha(original)!=row['source_sha256']:raise ValueError('Timeline source/object changed')
        cmd=list(row['command']);raw=out/(name[:-2]+'.raw.o');obj=out/objname;dep=out/(name[:-2]+'.d')
        cmd[cmd.index(str(original))]=str(source);cmd[cmd.index('-o')+1]=str(raw);cmd[cmd.index('-MF')+1]=str(dep);cmd+=['-iquote',str(original.parent)]
        r=subprocess.run(cmd,cwd=out,capture_output=True);(out/(name+'.log')).write_bytes(r.stdout+r.stderr);r.check_returncode()
        deps=shlex.split(dep.read_text().replace('\\\n',' ').split(':',1)[1])
        if set(deps)-{str(source)}!=set(row['consumed_inputs'])-{str(original)}:raise ValueError('OEM-init dependencies changed')
        for n in deps:
            if n!=str(source) and sha(Path(n))!=row['consumed_inputs'][n]:raise ValueError('OEM-init header changed')
        subprocess.run([str(a.llvm/'llvm-objcopy'),'--redefine-syms='+str(base/'objects/rename.txt'),str(raw),str(obj)],check=True)
        rename=dict(l.split() for l in (base/'objects/rename.txt').read_text().splitlines())
        additions={'_elden_wifi_board_state'}
        if global_symbols(obj)!={rename.get(n,n):v for n,v in global_symbols(raw).items()} or sections(obj)!=sections(raw) or symbols(obj,True)!=symbols(old,True) or symbols(obj,False)!=symbols(old,False)|additions:raise ValueError('OEM-init object interface/code changed unexpectedly')
        asm=subprocess.check_output([str(a.llvm/'llvm-objdump'),'-dr',obj],text=True);(out/(name+'.asm')).write_text(asm)
        if any(n.endswith('/__mod_init_func') for n in sections(obj)) or re.search(r'^\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+.*\b[qvdshb]\d+(?:\b|\.)',asm,re.M):raise ValueError('OEM-init initializer/SIMD')
        changes[str(old)]=str(obj);units[name]=dict(source_sha256=sha(source),object_sha256=sha(obj),warnings=r.stderr.count(b'warning:'),command=cmd,consumed_inputs={n:sha(Path(n)) for n in deps})
    link=list(prior['link']);objects=[Path(v) for i,v in enumerate(link) if v.endswith('.o') and link[i-1]!='-o']
    if len(objects)!=125 or not set(changes)<=set(map(str,objects)):raise ValueError('Wrong retained OEM-init objects')
    retained={str(n):sha(n) for n in objects if str(n) not in changes};target=out/'WifiRuntimeMsiBinding.o';link[link.index('-o')+1]=str(target);link=[changes.get(v,v) for v in link]
    r=subprocess.run(link,capture_output=True);(out/'link.log').write_bytes(r.stdout+r.stderr);r.check_returncode()
    if symbols(target,True)!=symbols(parent/'WifiRuntimeMsiBinding.o',True) or symbols(target,False)!=symbols(parent/'WifiRuntimeMsiBinding.o',False)|{'_elden_wifi_board_state'}:raise ValueError('Combined OEM-init interface changed')
    for n,h in retained.items():
        if sha(Path(n))!=h:raise ValueError('Retained runtime changed')
    own=['tools/build_wifi_board_state.py','tools/test_wifi_board_state.py','drivers/EldenWifi/BoardState.inc','drivers/EldenWifi/peach/BoardStatePatch.py']
    proof=dict(prior);proof.update(board_state_trial=True,board_state_no_device_controls=True,board_state_reversible=True,board_state_boundaries=[12,9,90],board_state_added_import='_elden_wifi_board_state',
        board_state_units=units,binding_sha256=sha(target),link=link,retained_objects=retained,source_inputs={**prior['source_inputs'],**{n:sha(ROOT/n) for n in own}},hardware_tested=False)
    (out/'result.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps({k:proof[k] for k in ['compiled','board_state_trial','binding_sha256','hardware_tested']}))


if __name__=='__main__':main()
