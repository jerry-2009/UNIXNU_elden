"""Compile native early SMMU owner and bind its concrete memory/table providers."""
import argparse,hashlib,json,re,subprocess
from pathlib import Path
from replay_xnu_objects import global_symbols,sections
ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,indent=2)+'\n',encoding='utf-8')
def defs(p):return {n for n,v in global_symbols(p).items() if v[0]&0x0e}
def refs(p):return {n for n,v in global_symbols(p).items() if not v[0]&0x0e}
def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ['clean-build','memory-build','selection-build','route-build','reference-kernel','llvm','output']:p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);d=ROOT/'drivers/EldenSmmu';base=a.clean_build.resolve()
    row=read(base/'units/result.json')['units']['WcnPowerNative'];cmd=list(row['command']);ov=read(Path(cmd[cmd.index('-ivfsoverlay')+1]));assert ov['fallthrough'] is False
    directories=set();inherited={}
    for item in ov['roots']:
        old=Path(item['external-contents']);inherited[str(old)]=sha(old)
        if item['name'].endswith('/WcnPowerNative.cpp'):
            assert sha(old)=='5c16106e90622150686b90706fcfc8c674cf3c4d563ed782fd7d57fc864e2c72'
            directories.add(str(Path(item['name']).parent));item['external-contents']=str(d/'Native.cpp')
    assert directories
    files={n:d/n for n in ['Native.h','DmaMemory.h','DmaTables.h','Domain.h','Select.h','BootRoute.h','Irqs.h']}
    files.update({'upstream/'+f.name:f for f in (d/'upstream').glob('*.h')})
    names={i['name'] for i in ov['roots']}
    for folder in directories:
        for name,path in files.items():
            key=str(Path(folder)/name);assert key not in names;ov['roots'].append({'type':'file','name':key,'external-contents':str(path)})
    write(out/'overlay.json',ov);cmd[cmd.index('-ivfsoverlay')+1]=str(out/'overlay.json');cmd[cmd.index('-o')+1]=str(out/'Native.o')
    records={}
    for name,command,cwd in [('Native',cmd,base/'units/working/WcnPowerNative'),('Domain',['xcrun','--sdk','iphoneos','clang','-target','arm64-apple-ios17.0','-std=c11','-O2','-Wall','-Wextra','-Werror','-ffreestanding','-fno-builtin','-fno-stack-protector','-mgeneral-regs-only','-I'+str(d),'-c',str(d/'Domain.c'),'-o',str(out/'Domain.o')],out)]:
        r=subprocess.run(command,cwd=cwd,capture_output=True);(out/(name+'.log')).write_bytes(r.stdout+r.stderr);r.check_returncode();obj=out/(name+'.o')
        asm=subprocess.check_output([str(a.llvm/'llvm-objdump'),'-dr',str(obj)],text=True);(out/(name+'.asm')).write_text(asm,encoding='utf-8')
        assert not re.search(r'^\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+.*\b[qvdshb]\d+(?:\b|\.)',asm,re.M)
        assert not any(n.endswith('/__mod_init_func') for n in sections(obj))
        records[name]={'sha256':sha(obj),'exports':sorted(defs(obj)),'imports':sorted(refs(obj)),'warnings':r.stderr.count(b'warning:')}
    memory=read(a.memory_build/'result.json');selection=read(a.selection_build/'result.json');route=read(a.route_build/'result.json')
    source_inputs={}
    for report in [memory,selection,route]:
        for name,h in report['source_inputs'].items():assert sha(ROOT/name)==h,name;source_inputs[name]=h
    objects=[out/'Native.o',out/'Domain.o']
    for name,row in memory['objects'].items():
        obj=a.memory_build/(name+'.o');assert sha(obj)==row['sha256'];objects.append(obj)
    for obj,h in [(a.selection_build/'Select.o',selection['object_sha256']),(a.route_build/'BootRoute.o',route['objects']['BootRoute']['object_sha256'])]:assert sha(obj)==h;objects.append(obj)
    target=out/'SmmuNativeBinding.o';r=subprocess.run(['xcrun','ld','-r','-arch','arm64','-platform_version','ios','17.0','17.0','-o',str(target),*map(str,objects)],capture_output=True)
    (out/'link.log').write_bytes(r.stdout+r.stderr);r.check_returncode();union=set().union(*(defs(p) for p in objects));pending=set().union(*(refs(p) for p in objects))-union
    assert defs(target)==union and refs(target)==pending
    missing=pending-defs(a.reference_kernel);assert missing=={'_elden_wifi_smmu_early_guard'},missing
    for p,h in inherited.items():assert sha(Path(p))==h
    for f in [d/'Native.cpp',d/'Domain.c',*files.values()]:source_inputs[str(f.relative_to(ROOT))]=sha(f)
    result={'compiled':True,'objects':records,'binding_sha256':sha(target),'input_objects':{str(p):sha(p) for p in objects},'component_count':len(objects),
            'remaining_imports':sorted(pending),'requires_ufs_guard':True,'source_inputs':source_inputs,'kernel_linked':False,'hardware':False}
    write(out/'result.json',result);print(json.dumps({k:result[k] for k in ['compiled','binding_sha256','component_count','remaining_imports']}))
if __name__=='__main__':main()
