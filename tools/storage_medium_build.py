"""Compile the two medium-property deltas in their exact existing contexts."""
from pathlib import Path
import hashlib,json,os,re,subprocess,sys
from replay_xnu_objects import sections,global_symbols
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'drivers/EldenStorageMedium'))
from MediumSource import source,INPUTS
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def exports(p):return {k for k,v in global_symbols(p).items() if v[0]&0x0e}
def compile_units(base,parent,out,llvm,early=False):
    objects={};records={};archives={};inherited={}
    native=read(base/'native/build/results.json');capture=read(base/'native/capture.json')
    current=read(base/'units/result.json');plan=read(ROOT/'profiles/current-build/plan.json')
    if not current['complete'] or current['profile_sha256']!=sha(ROOT/'profiles/current-build/plan.json'):raise ValueError('Current units changed')
    if early:
        sys.path.insert(0,str(ROOT/'drivers/EldenCpuActivation'))
        from EarlyStorageSource import source as early_source,recovery as early_recovery,RECOVERY_SHA
        recovery_path=out/'source/EldenSdamRecovery.inc';recovery_path.write_bytes(early_recovery())
    for unit in (('ShengUfs',) if early else ('ShengUfs','NativeRamBlock')):
        if unit=='ShengUfs':
            row=current['units'][unit];old=Path(row['object']);command=list(row['command']);cwd=base/'units/working'/unit;member='ShengUfs.o'
            if not row['accepted'] or not row['closed_overlay'] or sha(old)!=row['sha256']:raise ValueError('Current UFS object changed')
            job=next(j for j in plan['jobs'] if j['name']==unit)
            if sections(old)!=job['expected_sections'] or global_symbols(old)!=job['expected_symbols']:raise ValueError('Current UFS source identity differs')
        else:
            rows=[r for r in native.values() if r['source'].endswith('/NativeRamBlock.cpp')]
            if len(rows)!=1:raise ValueError('RAM unit ambiguous')
            row=rows[0];old=Path(row['output']);command=list(row['command'])
            if not row['accepted'] or sha(old)!=row['sha256'] or row.get('objcopy') or row.get('postprocess'):raise ValueError('Unexpected RAM compile context')
            job=next(j for j in capture['jobs'] if j['file']==row['source']);virtual=read(ROOT/'profiles/v91/native-build/plan.json')['virtual_root'].rstrip('/')
            rel=job['directory'][len(virtual)+1:];assert job['directory'].startswith(virtual+'/')
            if rel.startswith('research/'):rel='records/'+rel[9:]
            cwd=base/'native/build/project'/rel;member=Path(job['original_object']).name
            if member!='NativeRamBlock.o':raise ValueError('Unexpected RAM archive member')
        at=command.index('-ivfsoverlay')+1;overlay=read(Path(command[at]));assert overlay['fallthrough'] is False
        path,digest=INPUTS[unit];name=Path(path).name;derived=out/'source'/name;derived.write_bytes(early_source() if early else source(unit));bindings=[];extra=[];recovery_bindings=[]
        for item in overlay['roots']:
            f=Path(item['external-contents']);inherited[str(f)]=sha(f)
            if unit=='ShengUfs' and (f.resolve().parent!=(base/'units/source').resolve() or f.name not in plan['providers'] or sha(f)!=f.name):raise ValueError('UFS source provider changed')
            if early and item['name'].endswith('/EldenSdamRecovery.inc'):
                if sha(f)!=RECOVERY_SHA:raise ValueError('Early guard recovery parent differs')
                item['external-contents']=str(recovery_path);recovery_bindings.append(item['name'])
            if item['name'].endswith('/'+name):
                if sha(f)!=digest:raise ValueError('Wrong consumed storage source')
                item['external-contents']=str(derived);bindings.append(item['name'])
                extra.append({'type':'file','name':str(Path(item['name']).parent/'EldenStorageMedium.h'),'external-contents':str(ROOT/'drivers/EldenStorageMedium/EldenStorageMedium.h')})
        if not bindings:raise ValueError('Storage source not bound')
        if early and not recovery_bindings:raise ValueError('Early guard recovery not bound')
        known={r['name'] for r in overlay['roots']}
        for item in extra:
            if item['name'] in known:raise ValueError('Storage helper path collision')
            overlay['roots'].append(item);known.add(item['name'])
        vfs=out/(unit+'.overlay.json');vfs.write_text(json.dumps(overlay,indent=2)+'\n');command[at]=str(vfs)
        obj=out/member;command[command.index('-o')+1]=str(obj)
        env=dict(os.environ,CCC_OVERRIDE_OPTIONS='+-Wno-unknown-warning-option');env.pop('SDKROOT',None)
        r=subprocess.run(command,cwd=cwd,env=env,capture_output=True);(out/(unit+'.log')).write_bytes(r.stdout+r.stderr);r.check_returncode()
        if exports(obj)!=exports(old):raise ValueError('Storage exports changed')
        before,after=sections(old),sections(obj);names={n for n in before if n.endswith('/__mod_init_func')}
        if names!={n for n in after if n.endswith('/__mod_init_func')} or any(before[n][:2]!=after[n][:2] for n in names):raise ValueError('Initializer layout changed')
        if names:
            def targets(p):
                text=subprocess.check_output([str(llvm/'llvm-objdump'),'--reloc',str(p)],text=True)
                found=re.search(r'RELOCATION RECORDS FOR \[__mod_init_func\]:\n(.*?)(?:\n\n|\Z)',text,re.S)
                if not found:raise ValueError('Initializer target missing')
                return found[1]
            if targets(old)!=targets(obj):raise ValueError('Initializer target changed')
        asm=subprocess.check_output([str(llvm/'llvm-objdump'),'-dr',str(obj)],text=True);(out/(unit+'.asm')).write_text(asm)
        if re.search(r'^\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+.*\b[qvdshb]\d+(?:\b|\.)',asm,re.M):raise ValueError('Storage SIMD/FP found')
        imports=lambda p:{k for k,v in global_symbols(p).items() if not v[0]&0x0e}
        added=imports(obj)-imports(old)
        if not added<=exports(parent/'native.macho'):raise ValueError('New storage dependency unavailable: '+repr(added-exports(parent/'native.macho')))
        objects[member]=obj;archives[member]='libShengUfs.a' if unit=='ShengUfs' else 'libRamBlock.a'
        records[unit]={'source_sha256':sha(derived),'object_sha256':sha(obj),'command':command,'cwd':str(cwd),'bindings':bindings,'initializers_preserved':True,'new_imports':sorted(added),'warnings':r.stderr.decode().count('warning:')}
        if early:records[unit].update(recovery_sha256=sha(recovery_path),recovery_bindings=recovery_bindings)
    return objects,records,archives,inherited
