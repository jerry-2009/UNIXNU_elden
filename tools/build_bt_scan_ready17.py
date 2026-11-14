"""Build native HCI completion and capability-gated optional initialization."""
from pathlib import Path
import argparse,hashlib,io,json,os,re,shutil,subprocess,sys,tarfile
from replay_xnu_objects import sections,global_symbols
from link_v91_kernel import native_identity,verify_original_executables
from audit_entry_relocation import entry
from prepare_bt_helper_trace import common
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'drivers/EldenBluetooth/runtime'))
from LaunchCacheSource import source as cache_source,ORIGINAL as RUNTIME_ORIGINAL
sys.path.insert(0,str(ROOT/'drivers/EldenBluetooth'))
from ScanInitSource import host as native_host,bridge as native_bridge
from FixupCapacitySource import source as page_parser_source,ORIGINAL as PAGE_PARSER_ORIGINAL
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,indent=2)+'\n')
def exports(p):return {k for k,v in global_symbols(p).items() if v[0]&0x0e}

def native_archive(base,parent,out,llvm):
    rows=read(base/'units/result.json')['units'];records={};inherited={};objects={}
    source_dir=out/'source';source_dir.mkdir()
    for unit,name,expected in [('NativeHost','NativeHost.cpp','646849166bcd935a8c594cff2470a24ed56484f274c15bff1f8eeb9ca64496e3'),('BtBridge','BtBridge.c','7fddbf007f66d1055dd463432358708c5db4c8f743bab5a4985e2b88d86dd571')]:
        row=rows[unit];old=Path(row['object']);assert row['accepted'] and sha(old)==row['sha256']
        cmd=list(row['command']);ov=read(Path(cmd[cmd.index('-ivfsoverlay')+1]));assert ov['fallthrough'] is False
        source=source_dir/name;bindings=[]
        for item in ov['roots']:
            f=Path(item['external-contents']);h=sha(f);inherited[str(f)]=h
            if item['name'].endswith('/'+name):
                assert h==expected,(name,h)
                data=native_host() if unit=='NativeHost' else native_bridge(f.read_bytes())
                if source.exists():assert source.read_bytes()==data
                else:source.write_bytes(data)
                item['external-contents']=str(source);bindings.append(item['name'])
        assert bindings
        vfs=out/(unit+'.overlay.json');write(vfs,ov);cmd[cmd.index('-ivfsoverlay')+1]=str(vfs)
        obj=out/(unit+'.o');cmd[cmd.index('-o')+1]=str(obj)
        r=subprocess.run(cmd,cwd=base/'units/working'/unit,capture_output=True);(out/(unit+'.log')).write_bytes(r.stdout+r.stderr);r.check_returncode()
        addition={'_elden_bt_native_init_result'} if unit=='NativeHost' else set()
        assert exports(obj)==exports(old)|addition and not any(k.endswith('/__mod_init_func') for k in sections(obj))
        asm=subprocess.check_output([str(llvm/'llvm-objdump'),'-dr',obj],text=True);(out/(unit+'.asm')).write_text(asm)
        assert not re.search(r'^\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+.*\b[qvdshb]\d+(?:\b|\.)',asm,re.M)
        records[unit]={'source_sha256':sha(source),'object_sha256':sha(obj),'command':cmd,'bindings':bindings};objects[unit+'.o']=obj
    link=read(parent/'link-command.json');matches=[x.split(',')[-1] for x in link if x.endswith('/libEldenBluetooth.a')];assert len(matches)==1;oldar=Path(matches[0])
    folder=out/'bluetooth';folder.mkdir();names=[n for n in subprocess.check_output(['ar','t',oldar],text=True).splitlines() if not n.startswith('__.SYMDEF')]
    assert set(objects)<=set(names);members={}
    for n in names:
        data=objects[n].read_bytes() if n in objects else subprocess.check_output(['ar','p',oldar,n])
        (folder/n).write_bytes(data);members[n]=hashlib.sha256(data).hexdigest()
    archive=folder/oldar.name;subprocess.run(['ar','rcs',archive,*names],cwd=folder,env=dict(os.environ,ZERO_AR_DATE='1'),check=True)
    for n in names:
        data=subprocess.check_output(['ar','p',archive,n]);expected=(folder/n).read_bytes()
        assert data==expected or data==expected+b'\n'*((-len(expected))%8)
    return oldar,archive,records,members,inherited

def main():
    if sys.flags.optimize:raise ValueError('Assertions required')
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('clean-build','process-build','scan-runtime','original-kernelcache','llvm','output'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();base=a.clean_build.resolve();parent=a.process_build.resolve();out=a.output.resolve()
    if out.exists():raise ValueError('Fresh output required')
    c=read(ROOT/'profiles/bt-process-lifetime/native-contract.json');assert native_identity(parent/'native.macho')==(c['sections'],c['commands'],c['symbols'])
    parent_report=read(parent/'result.json');assert sha(parent/'kernel.macho')==parent_report['kernel_sha256']
    runtime_record=read(a.scan_runtime/'optional-report.json');assert runtime_record['table_count']==40
    for f,h in runtime_record['source_inputs'].items():assert sha(ROOT/f)==h
    for f,h in runtime_record['files'].items():assert sha(a.scan_runtime/f)==h
    out.mkdir(parents=True);runtime=out/'runtime';shutil.copytree(a.scan_runtime,runtime)
    trace=read(runtime/'trace-runtime.json');common_file=out/'EldenIconCpuCommon.inc';common_text=common(trace['helper_cdhash']).decode();marker='void elden_icon_cpu_user_marker(proc_t p,uint32_t code,uint64_t status,uint64_t mode,uint64_t version,uint64_t magic)\n{'
    assert common_text.count(marker)==1
    common_file.write_bytes(common_text.replace(marker,marker+'\n'+(ROOT/'drivers/EldenBluetooth/diagnostics/NativeInitMarker.inc').read_text()).encode())
    oldar,newar,native_records,members,native_sources=native_archive(base,parent,out,a.llvm)
    rt=out/'EldenBtRuntime.inc';rt.write_bytes(cache_source());rows=read(base/'units/result.json')['units'];oldlist=(parent/'link.filelist').read_text().splitlines();replace={};records={};inherited={}
    for unit in ('kern_exec','ubc_subr'):
        row=rows[unit];old=Path(row['object']);assert row['accepted'] and sha(old)==row['sha256']
        cmd=list(row['command']);ov=read(Path(cmd[cmd.index('-ivfsoverlay')+1]));assert ov['fallthrough'] is False
        changed=[];extra=[]
        for item in ov['roots']:
            f=Path(item['external-contents']);h=sha(f);inherited[str(f)]=h
            target=None
            if unit=='kern_exec':
                if h=='beea14cef600c7607a9d381cde30647ec806ec580624c22c37ead94715144dec':target=common_file
                if h==RUNTIME_ORIGINAL:
                    target=rt;extra.append({'type':'file','name':str(Path(item['name']).parent/'EldenBtLaunchCache.h'),'external-contents':str(runtime/'EldenBtLaunchCache.h')})
                if item['name'].endswith('/EldenBtRuntimePayload.h'):
                    assert h=='3032579d4d29194f526a11b4683a32a36643277bb1348570bb5119ff49cbe2f2';target=runtime/'EldenBtRuntimePayload.h'
            elif item['name'].endswith('/ubc_subr.c'):
                assert h==PAGE_PARSER_ORIGINAL
                target=out/'source/ubc_subr.c';data=page_parser_source(f.read_bytes())
                if target.exists():assert target.read_bytes()==data
                else:target.write_bytes(data)
            elif item['name'].endswith('/EldenBtTextGuard.h'):
                assert h=='00b61380b46a485d09c1011a11ae0971ff810e204ba4b4baa26a2e4009fd1012';target=runtime/'EldenBtTextGuard.h'
            if target:item['external-contents']=str(target);changed.append(item['name'])
        assert changed;ov['roots']+=extra;vfs=out/(unit+'.overlay.json');write(vfs,ov);cmd[cmd.index('-ivfsoverlay')+1]=str(vfs);obj=out/(unit+'.o');cmd[cmd.index('-o')+1]=str(obj)
        r=subprocess.run(cmd,cwd=base/'units/working'/unit,capture_output=True);(out/(unit+'.log')).write_bytes(r.stdout+r.stderr);r.check_returncode()
        assert exports(obj)==exports(old) and not any(k.endswith('/__mod_init_func') for k in sections(obj))
        asm=subprocess.check_output([str(a.llvm/'llvm-objdump'),'-dr',obj],text=True);(out/(unit+'.asm')).write_text(asm);assert not re.search(r'^\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+.*\b[qvdshb]\d+(?:\b|\.)',asm,re.M)
        prior=next(n for n in oldlist if Path(n).name=='kern_exec.o') if unit=='kern_exec' else str(old)
        assert oldlist.count(prior)==1 and sha(Path(prior))==parent_report['inherited_inputs'][prior];replace[prior]=str(obj);records[unit]={'sha256':sha(obj),'command':cmd,'changed_bindings':changed}
    filelist=out/'link.filelist';filelist.write_text('\n'.join(replace.get(n,n) for n in oldlist)+'\n');link=read(parent/'link-command.json');fl=[x.split(',')[-1] for x in link if x.endswith('link.filelist')];assert len(fl)==1
    inputs={n:sha(Path(n)) for n in oldlist}
    for arg in link:
        f=arg.split(',',2)[2] if arg.startswith('-Wl,-force_load,') else arg
        if Path(f).is_file() and f.endswith(('.a','.o')):inputs[f]=sha(Path(f))
    cmd=[x.replace(fl[0],str(filelist)).replace(str(parent/'native.macho'),str(out/'native.macho')).replace(str(oldar),str(newar)) for x in link];write(out/'link-command.json',cmd)
    env=dict(os.environ,CCC_OVERRIDE_OPTIONS='+-Wno-unknown-warning-option');env.pop('SDKROOT',None)
    with (out/'link.log').open('x') as f:subprocess.run(cmd,cwd=out,env=env,stdout=f,stderr=subprocess.STDOUT,check=True)
    assert exports(out/'native.macho')==exports(parent/'native.macho')|{'_elden_bt_native_init_result'}
    for f,h in {**inputs,**inherited,**native_sources}.items():assert sha(Path(f))==h
    pre=read(ROOT/'profiles/v91/image-build/plan.json')['prelink'];assert sha(a.original_kernelcache)==pre['original_kernelcache_sha256'];kit=out/'prelink-tool';kit.mkdir()
    with tarfile.open(fileobj=io.BytesIO(subprocess.check_output(['git','-C',str(base/'dependencies/XnuPrelink'),'archive',pre['commit']]))) as t:t.extractall(kit,filter='data')
    cmd=[sys.executable,str(kit/'emit_prelink.py'),'--kernel',str(out/'native.macho'),'--prelinked',str(a.original_kernelcache.resolve()),'--slide='+pre['slide'],'--output',str(out/'kernel.macho')]
    for n in pre['roots']:cmd+=['--root',n]
    for n in pre['early_security_initializers']:cmd+=['--early-security-init',n]
    with (out/'prelink.log').open('x') as f:subprocess.run(cmd,cwd=out,stdout=f,stderr=subprocess.STDOUT,check=True)
    assert verify_original_executables(out/'kernel.macho',read(out/'kernel.json'),pre['original_executable_sha256'])==30
    before=entry((parent/'kernel.macho').read_bytes());after=entry((out/'kernel.macho').read_bytes());assert before[2]==after[2] and before[1]-before[0]==after[1]-after[0]==7124
    files=[Path(__file__).resolve(),ROOT/'tools/prepare_bt_helper_trace.py',ROOT/'drivers/EldenBluetooth/runtime/LaunchCacheSource.py',ROOT/'drivers/EldenBluetooth/runtime/LaunchCache.inc',ROOT/'drivers/EldenBluetooth/NativeInitSource.py',ROOT/'drivers/EldenBluetooth/ScanInitSource.py',ROOT/'drivers/EldenBluetooth/FixupCapacitySource.py',ROOT/'drivers/EldenBluetooth/ProcessLifetimeSource.py',ROOT/'drivers/EldenBluetooth/RegistrySource.py',ROOT/'drivers/EldenBluetooth/NativeHost.cpp',ROOT/'drivers/EldenBluetooth/diagnostics/TransportTrace.py',ROOT/'drivers/EldenBluetooth/diagnostics/NativeInitMarker.inc']
    report={'profile':'bt-scan-ready17','kernel_sha256':sha(out/'kernel.macho'),'native_sha256':sha(out/'native.macho'),'changed_core_objects':2,'changed_native_objects':2,'native_objects':native_records,'archive_members':members,'native_sources':native_sources,'scalar':True,'source_inputs':{str(f.relative_to(ROOT)):sha(f) for f in files},'optional_runtime':runtime_record,'objects':records,'inherited_inputs':inputs,'inherited_sources':inherited,'entry_return_target':hex(after[1]),'parent_kernel_sha256':parent_report['kernel_sha256'],'original_apple_executables_hashed':30,'hardware':False}
    write(out/'result.json',report);print(json.dumps({'kernel_sha256':report['kernel_sha256'],'table_count':40}))
if __name__=='__main__':main()
