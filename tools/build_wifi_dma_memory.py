"""Compile real IOKit allocation and pinned 4K table code; no device activation."""
import argparse,hashlib,importlib.util,json,re,subprocess
from pathlib import Path
from replay_xnu_objects import global_symbols,sections
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def write(p,v):p.write_text(json.dumps(v,indent=2)+'\n',encoding='utf-8')
def defs(p):return {n for n,v in global_symbols(p).items() if v[0]&0x0e}
def refs(p):return {n for n,v in global_symbols(p).items() if not v[0]&0x0e}
def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ['clean-build','reference-kernel','llvm','output']:p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--segmented',action='store_true')
    p.add_argument('--unique-map',action='store_true')
    p.add_argument('--prefault',action='store_true')
    a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);d=ROOT/'drivers/EldenSmmu';up=d/'upstream';base=a.clean_build.resolve()
    manifest=read(up/'source.json');allocator_source=d/'DmaMemory.cpp'
    if a.prefault:a.unique_map=True
    if a.unique_map:a.segmented=True
    if a.segmented:
        spec=importlib.util.spec_from_file_location('segments',d/'SegmentSource.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
        allocator_source=out/'DmaMemory.cpp';allocator_source.write_bytes(mod.source())
    if a.unique_map:
        import sys;sys.path.insert(0,str(d));from UniqueSource import source as unique_source;allocator_source.write_bytes(unique_source())
    if a.prefault:
        from PrefaultSource import source as prefault_source;allocator_source.write_bytes(prefault_source())
    for row in manifest['files'].values():assert sha(up/row['output'])==row['output_sha256']
    row=read(base/'units/result.json')['units']['WcnPowerNative'];command=list(row['command']);overlay=read(Path(command[command.index('-ivfsoverlay')+1]));assert overlay['fallthrough'] is False
    directories=set();inherited={}
    for item in overlay['roots']:
        path=Path(item['external-contents']);h=sha(path);inherited[str(path)]=h
        if item['name'].endswith('/WcnPowerNative.cpp'):
            assert h=='5c16106e90622150686b90706fcfc8c674cf3c4d563ed782fd7d57fc864e2c72'
            directories.add(str(Path(item['name']).parent));item['external-contents']=str(allocator_source)
    assert directories
    files={'DmaMemory.h':d/'DmaMemory.h','DmaTables.h':d/'DmaTables.h'}
    files.update({'upstream/'+r['output']:up/r['output'] for r in manifest['files'].values() if r['output'].endswith('.h')})
    existing={x['name'] for x in overlay['roots']}
    for folder in directories:
        for name,path in files.items():
            key=str(Path(folder)/name);assert key not in existing
            overlay['roots'].append({'type':'file','name':key,'external-contents':str(path)})
    write(out/'overlay.json',overlay);command[command.index('-ivfsoverlay')+1]=str(out/'overlay.json');command[command.index('-o')+1]=str(out/'DmaMemory.o')
    objects=[];records={}
    for name,cmd,cwd in [('DmaMemory',command,base/'units/working/WcnPowerNative')]+[
        (source.stem,['xcrun','--sdk','iphoneos','clang','-target','arm64-apple-ios17.0','-std=c11','-O2','-Wall','-Wextra','-Werror','-ffreestanding','-fno-builtin','-fno-stack-protector','-mgeneral-regs-only','-I'+str(d),'-I'+str(up),'-c',str(source),'-o',str(out/(source.stem+'.o'))],out)
        for source in [d/'DmaTables.c',*[up/r['output'] for r in manifest['files'].values() if r['output'].endswith('.c')]]]:
        obj=out/(name+'.o');objects.append(obj);r=subprocess.run(cmd,cwd=cwd,capture_output=True);(out/(name+'.log')).write_bytes(r.stdout+r.stderr);r.check_returncode()
        asm=subprocess.check_output([str(a.llvm/'llvm-objdump'),'-dr',str(obj)],text=True);(out/(name+'.asm')).write_text(asm,encoding='utf-8')
        assert not re.search(r'^\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+.*\b[qvdshb]\d+(?:\b|\.)',asm,re.M)
        assert not any(n.endswith('/__mod_init_func') for n in sections(obj))
        records[name]={'sha256':sha(obj),'exports':sorted(defs(obj)),'imports':sorted(refs(obj)),'warnings':r.stderr.count(b'warning:'),'command':cmd}
    target=out/'WifiDmaMemoryBinding.o';r=subprocess.run(['xcrun','ld','-r','-arch','arm64','-platform_version','ios','17.0','17.0','-o',str(target),*map(str,objects)],capture_output=True)
    (out/'link.log').write_bytes(r.stdout+r.stderr);r.check_returncode()
    union=set().union(*(defs(f) for f in objects));pending=set().union(*(refs(f) for f in objects))-union
    assert defs(target)==union and refs(target)==pending
    assert pending<=defs(a.reference_kernel),sorted(pending-defs(a.reference_kernel))
    for path,h in inherited.items():assert sha(Path(path))==h,path
    own=[d/'DmaMemory.cpp',d/'DmaMemory.h',d/'DmaTables.c',d/'DmaTables.h',up/'source.json']+[up/r['output'] for r in manifest['files'].values()]
    if a.segmented:own.append(d/'SegmentSource.py')
    if a.unique_map:own.append(d/'UniqueSource.py')
    if a.prefault:own.append(d/'PrefaultSource.py')
    result={'compiled':True,'objects':records,'binding_sha256':sha(target),'remaining_kernel_imports':sorted(pending),'kernel_imports_verified':True,
            'source_inputs':{str(f.relative_to(ROOT)):sha(f) for f in own},'inherited_sdk_inputs':len(inherited),'scalar':True,
            'allocator_variant':'prefault' if a.prefault else 'unique' if a.unique_map else 'segmented' if a.segmented else 'detail','allocator_source_sha256':sha(allocator_source),
            'kernel_linked':False,'native_allocator_run':False,'smmu_enabled':False,'hardware_tested':False}
    write(out/'result.json',result);print(json.dumps({k:result[k] for k in ['compiled','binding_sha256','remaining_kernel_imports','kernel_linked']}))
if __name__=='__main__':main()
