"""Test actual DMA allocator methods/table algorithms with modeled kernel services."""
import argparse,hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def replace_body(text,signature,body):
    start=text.index(signature);begin=text.index('{',start);depth=1;end=begin+1
    while depth:
        depth+=(text[end]=='{')-(text[end]=='}');end+=1
    return text[:begin]+body+text[end:]

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--wsl-distro');a=p.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);d=ROOT/'drivers/EldenSmmu';up=d/'upstream'
    manifest=json.loads((up/'source.json').read_text())
    for row in manifest['files'].values():assert hashlib.sha256((up/row['output']).read_bytes()).hexdigest()==row['output_sha256']
    source=(d/'DmaMemory.cpp').read_text(encoding='utf-8')
    source=replace_body(source,'static uint64_t translate(', '{return mock_translate(address,write);}')
    source=replace_body(source,'static void clean(', '{mock_clean(start,bytes,line);}')
    old='uint64_t ctr;__asm__ volatile("mrs %0,ctr_el0":"=r"(ctr));line_=4u<<((ctr>>16)&15);'
    assert source.count(old)==1;source=source.replace(old,'line_=mock_cache_line();')
    (out/'DmaMemory.cpp').write_text(source,encoding='utf-8')
    for name in ['IOKit/IOBufferMemoryDescriptor.h','IOKit/IOLib.h','kern/task.h']:
        target=out/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_text('#include "TestDmaPlatform.h"\n',encoding='utf-8')
    def path(v):
        v=str(Path(v).resolve());return '/mnt/'+v[0].lower()+v[2:].replace('\\','/') if a.wsl_distro else v
    prefix=['wsl','-d',a.wsl_distro,'--'] if a.wsl_distro else []
    flags=['-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-omit-frame-pointer']
    if a.wsl_distro:flags+=['-fno-pie','-no-pie']
    flags+=['-I'+path(v) for v in [out,d,up]]
    objects=[];commands=[]
    for file in ['EldenWifiSmmu4K.c','EldenWifiSmmu4KContext.c','EldenWifiSmmu4KProgram.c','EldenWifiSmmu4KAudit.c','EldenWifiSmmu4KTableMemory.c']:
        obj=out/(file+'.o');objects.append(obj);commands.append((file,['clang','-std=c11',*flags,'-c',path(up/file),'-o',path(obj)]))
    objects.append(out/'DmaTables.o');commands.append(('tables-compile',['clang','-std=c11',*flags,'-c',path(d/'DmaTables.c'),'-o',path(objects[-1])]))
    commands.append(('table-test-compile',['clang','-std=c11',*flags,path(d/'TestDmaTables.c'),*map(path,objects),'-o',path(out/'tables-test')]))
    commands.append(('table-test',[path(out/'tables-test')]))
    commands.append(('memory-compile',['clang++','-std=c++17',*flags,path(d/'TestDmaMemory.cpp'),path(out/'DmaMemory.cpp'),*map(path,objects),'-o',path(out/'memory-test')]))
    commands.append(('memory-test',[path(out/'memory-test')]))
    summaries={}
    for name,cmd in commands:
        r=subprocess.run(prefix+cmd,capture_output=True,timeout=120);(out/(name+'.log')).write_bytes(r.stdout+r.stderr);r.check_returncode()
        if name.endswith('test'):summaries[name]=r.stdout.decode().strip()
    files=['DmaMemory.cpp','DmaMemory.h','DmaTables.c','DmaTables.h','TestDmaMemory.cpp','TestDmaTables.c','TestDmaPlatform.h']
    report={'passed':True,'results':summaries,'asan_ubsan':True,'actual_allocator_methods':True,'physical_mapping_cache_and_iokit_modeled':True,
            'source_sha256':{n:hashlib.sha256((d/n).read_bytes()).hexdigest() for n in files},'upstream_manifest_sha256':hashlib.sha256((up/'source.json').read_bytes()).hexdigest(),
            'hardware_tested':False}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps(report))
if __name__=='__main__':main()
