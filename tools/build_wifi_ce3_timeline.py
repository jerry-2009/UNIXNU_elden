"""Build passive start-sequence CE3 state evidence over the inspector candidate."""
import argparse,hashlib,json,re,shlex,subprocess,sys
from pathlib import Path
from replay_xnu_objects import global_symbols,sections
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'drivers/EldenWifi/peach'))
from Ce3TimelinePatch import patch


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())
def symbols(p,d):return {n for n,v in global_symbols(p).items() if bool(v[0]&0x0e)==d}


def main():
    if sys.flags.optimize:raise ValueError('Assertions required')
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('runtime-build','parent-build','llvm','output'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();base=a.runtime_build.resolve();parent=a.parent_build.resolve();out=a.output.resolve();prior=read(parent/'result.json')
    if prior.get('ce3_inspect_trial') is not True or prior.get('ce3_direct_trial') or sha(parent/'WifiRuntimeMsiBinding.o')!=prior['binding_sha256']:
        raise ValueError('Qualified original-shadow inspector runtime required')
    rows={Path(r['path']).name:r for r in read(base/'objects/build-report.json')['objects']}
    out.mkdir(parents=True,exist_ok=False)
    for n in ('Ce3Timeline.h','Ce3Timeline.inc','Ce3Inspect.inc','DmaInspect.h'):(out/n).write_bytes((ROOT/'drivers/EldenWifi'/n).read_bytes())
    changed={};proofs={};rename=dict(l.split() for l in (base/'objects/rename.txt').read_text().splitlines())
    for name,objname in [('core.c','ath12k_core.o'),('wmi.c','ath12k_wmi.o')]:
        original=Path(rows[objname]['source']) if name=='core.c' else parent/'wmi.c'
        old=Path(rows[objname]['path']) if name=='core.c' else parent/'ath12k_wmi.o'
        raw=out/objname.replace('.o','.raw.o');obj=out/objname;dep=out/objname.replace('.o','.d');source=out/name
        source.write_bytes(patch(name,original.read_bytes()))
        identity=read(base/'objects/raw'/objname.replace('.o','.inputs.json'))
        cmd=list(identity['command']) if name=='core.c' else list(prior['inspect_command'])
        cmd[cmd.index(str(original))]=str(source);cmd[cmd.index('-o')+1]=str(raw);cmd[cmd.index('-MF')+1]=str(dep)
        r=subprocess.run(cmd,cwd=out,capture_output=True);(out/(objname+'.log')).write_bytes(r.stdout+r.stderr);r.check_returncode()
        deps=shlex.split(dep.read_text().replace('\\\n',' ').split(':',1)[1])
        allowed={str(out/'Ce3Timeline.h'),str(out/'Ce3Timeline.inc')} if name=='core.c' else {str(out/n) for n in ['Ce3Timeline.h','Ce3Inspect.inc','DmaInspect.h']}
        parent_deps=identity['dependencies'] if name=='core.c' else prior['inspect_consumed_inputs']
        inherited={str(Path(n).resolve()):h for n,h in parent_deps.items() if Path(n).name not in ['core.c','wmi.c','Ce3Inspect.inc','DmaInspect.h']}
        actual={str(Path(n).resolve()) for n in deps if n!=str(source) and n not in allowed}
        if actual!=set(inherited):raise ValueError('Timeline dependency set changed: '+name)
        for n in actual:
            if sha(Path(n))!=inherited[n]:raise ValueError('Timeline header input changed')
        subprocess.run([str(a.llvm/'llvm-objcopy'),'--redefine-syms='+str(base/'objects/rename.txt'),str(raw),str(obj)],check=True)
        if global_symbols(obj)!={rename.get(n,n):v for n,v in global_symbols(raw).items()} or sections(obj)!=sections(raw):raise ValueError('Timeline rename changed code/data')
        if symbols(obj,True)!=symbols(old,True)|({'_elden_ce3_timeline'} if name=='core.c' else set()):raise ValueError('Timeline definition delta changed')
        if symbols(obj,False)!=symbols(old,False)|({'_elden_ce3_timeline'} if name=='wmi.c' else set()):raise ValueError('Timeline import delta changed')
        asm=subprocess.check_output([str(a.llvm/'llvm-objdump'),'-dr',obj],text=True);(out/(objname+'.asm')).write_text(asm)
        if any(n.endswith('/__mod_init_func') for n in sections(obj)) or re.search(r'^\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+.*\b[qvdshb]\d+(?:\b|\.)',asm,re.M):raise ValueError('Timeline initializer/SIMD')
        changed[str(old)]=str(obj);proofs[objname]=dict(source_sha256=sha(source),object_sha256=sha(obj),warnings=r.stderr.count(b'warning:'),command=cmd,consumed_inputs={n:sha(Path(n)) for n in deps})
    link=list(prior['link']);objects=[Path(v) for i,v in enumerate(link) if v.endswith('.o') and link[i-1]!='-o']
    if len(objects)!=125 or not set(changed)<=set(map(str,objects)):raise ValueError('Wrong exact retained runtime')
    retained={str(p):sha(p) for p in objects if str(p) not in changed};target=out/'WifiRuntimeMsiBinding.o'
    link[link.index('-o')+1]=str(target);link=[changed.get(v,v) for v in link]
    lr=subprocess.run(link,capture_output=True);(out/'link.log').write_bytes(lr.stdout+lr.stderr);lr.check_returncode()
    if symbols(target,True)!=symbols(parent/'WifiRuntimeMsiBinding.o',True)|{'_elden_ce3_timeline'} or symbols(target,False)!=symbols(parent/'WifiRuntimeMsiBinding.o',False):raise ValueError('Combined timeline interface changed')
    for n,h in retained.items():
        if sha(Path(n))!=h:raise ValueError('Retained runtime changed')
    own=['tools/build_wifi_ce3_timeline.py','tools/test_wifi_ce3_timeline.py','drivers/EldenWifi/peach/Ce3TimelinePatch.py','drivers/EldenWifi/Ce3Timeline.h','drivers/EldenWifi/Ce3Timeline.inc']
    proof=dict(prior);proof.update(ce3_timeline_trial=True,timeline_delta_reversible=True,timeline_events_max=12,timeline_reads_per_event=7,
        changed_units=['ath12k_wmi.o','ath12k_pci.o','ath12k_core.o'],runtime_added_exports=['_elden_ce3_timeline'],
        parent_inspect_binding_sha256=prior['binding_sha256'],binding_sha256=sha(target),timeline_units=proofs,
        link=link,retained_objects=retained,source_inputs={**prior['source_inputs'],**{n:sha(ROOT/n) for n in own}},hardware_tested=False)
    (out/'result.json').write_text(json.dumps(proof,indent=2)+'\n')
    print(json.dumps({n:proof[n] for n in ['compiled','ce3_timeline_trial','binding_sha256','runtime_added_exports','hardware_tested']}))


if __name__=='__main__':main()
