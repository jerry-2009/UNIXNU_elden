"""Fix callback process-reference lifetime over the typed-helper candidate.

No v99 paths or historical compiled objects are inputs. The required BlueTool
parent is built from the same clean output by build_bluetool_launch.py.
"""
from pathlib import Path
import argparse,hashlib,io,json,os,re,subprocess,sys,tarfile
from replay_xnu_objects import global_symbols,sections
from link_v91_kernel import native_identity,verify_original_executables
from audit_entry_relocation import entry
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'drivers/EldenBluetooth'))
from ProcessLifetimeSource import source as registry_source
HASHES={"NativeHost.cpp":"646849166bcd935a8c594cff2470a24ed56484f274c15bff1f8eeb9ca64496e3"}
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,indent=2)+'\n')
def exports(p):return {n for n,v in global_symbols(p).items() if v[0]&0x0e}
def main():
    if sys.flags.optimize:raise ValueError('Assertions required')
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('clean-build','original-kernelcache','llvm','output'):p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--helper-trace-build',type=Path,required=True)
    a=p.parse_args();base=a.clean_build.resolve();out=a.output.resolve();parent=a.helper_trace_build.resolve()
    if out.exists():raise ValueError('Fresh output required')
    contract=read(ROOT/'profiles/current-build/native-contract.json')
    assert native_identity(base/'linked/native.macho')==(contract['sections'],contract['commands'],contract['symbols'])
    contract=read(ROOT/'profiles/bt-helper-trace/native-contract.json')
    assert native_identity(parent/'native.macho')==(contract['sections'],contract['commands'],contract['symbols'])
    parent_report=read(parent/'result.json');assert sha(parent/'kernel.macho')==parent_report['kernel_sha256']
    rows=read(base/'units/result.json')['units']
    out.mkdir(parents=True);(out/'source').mkdir();objects={};records={};inherited={}
    for unit in ('NativeHost',):
        name=unit+'.cpp';data=registry_source()
        row=rows[unit];old=Path(row['object']);assert row['accepted'] and sha(old)==row['sha256']
        source=out/'source'/name;source.write_bytes(data)
        command=list(row['command']);overlay=read(Path(command[command.index('-ivfsoverlay')+1]));assert overlay['fallthrough'] is False
        bindings=[]
        for r in overlay['roots']:
            f=Path(r['external-contents']);inherited[str(f)]=sha(f)
            if r['name'].endswith('/'+name):
                # Exact baseline source; aliases may only bind identical bytes.
                assert sha(f)==HASHES[name]
                r['external-contents']=str(source);bindings.append(r['name'])
        assert bindings
        vfs=out/(name+'.overlay.json');write(vfs,overlay);command[command.index('-ivfsoverlay')+1]=str(vfs)
        obj=out/(name+'.o');command[command.index('-o')+1]=str(obj)
        cwd=base/'units/working'/unit
        r=subprocess.run(command,cwd=cwd,capture_output=True);(out/(name+'.log')).write_bytes(r.stdout+r.stderr);r.check_returncode()
        assert exports(obj)==exports(old),(name,exports(obj)^exports(old))
        assert not any(n.endswith('/__mod_init_func') for n in sections(obj))
        asm=subprocess.check_output([str(a.llvm/'llvm-objdump'),'-dr',str(obj)],text=True);(out/(name+'.asm')).write_text(asm)
        assert not re.search(r'^\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+.*\b[qvdshb]\d+(?:\b|\.)',asm,re.M)
        objects[unit+'.o']=obj
        records[name]={'object':str(obj),'sha256':sha(obj),'source_sha256':sha(source),'command':command,'bindings':bindings,'expected_exports':sorted(exports(obj))}
    oldlink=read(parent/'link-command.json');ar_paths=[x.split(',')[-1] for x in oldlink if x.endswith('/libEldenBluetooth.a')];assert len(ar_paths)==1;oldar=Path(ar_paths[0])
    folder=out/'bluetooth';folder.mkdir();names=[n for n in subprocess.check_output(['ar','t',oldar],text=True).splitlines() if not n.startswith('__.SYMDEF')]
    assert set(objects)<=set(names);member_hashes={}
    for n in names:
        data=objects[n].read_bytes() if n in objects else subprocess.check_output(['ar','p',oldar,n])
        (folder/n).write_bytes(data);member_hashes[n]=hashlib.sha256(data).hexdigest()
    archive=folder/oldar.name;subprocess.run(['ar','rcs',archive,*names],cwd=folder,env=dict(os.environ,ZERO_AR_DATE='1'),check=True)
    for n in names:
        data=subprocess.check_output(['ar','p',archive,n]);expected=(folder/n).read_bytes()
        assert data==expected or data==expected+b'\n'*((-len(expected))%8),(n,len(data),len(expected))
    link=read(parent/'link-command.json');assert sum(str(oldar) in v for v in link)==1
    inputs={str(parent/'link.filelist'):sha(parent/'link.filelist')}
    for f in (parent/'link.filelist').read_text().splitlines():inputs[f]=sha(Path(f))
    for arg in link:
        f=arg.split(',',2)[2] if arg.startswith('-Wl,-force_load,') else arg
        if Path(f).is_file() and f.endswith(('.o','.a')):inputs[f]=sha(Path(f))
    link=[v.replace(str(parent/'native.macho'),str(out/'native.macho')).replace(str(oldar),str(archive)) for v in link]
    write(out/'link-command.json',link);(out/'link.filelist').write_bytes((parent/'link.filelist').read_bytes())
    env=dict(os.environ,CCC_OVERRIDE_OPTIONS='+-Wno-unknown-warning-option');env.pop('SDKROOT',None)
    with (out/'link.log').open('x') as f:subprocess.run(link,cwd=out,env=env,stdout=f,stderr=subprocess.STDOUT,check=True)
    assert exports(out/'native.macho')==exports(parent/'native.macho')
    for f,h in {**inputs,**inherited}.items():assert sha(Path(f))==h
    pre=read(ROOT/'profiles/v91/image-build/plan.json')['prelink'];assert sha(a.original_kernelcache)==pre['original_kernelcache_sha256']
    kit=out/'prelink-tool';kit.mkdir()
    with tarfile.open(fileobj=io.BytesIO(subprocess.check_output(['git','-C',str(base/'dependencies/XnuPrelink'),'archive',pre['commit']]))) as ar:ar.extractall(kit,filter='data')
    cmd=[sys.executable,str(kit/'emit_prelink.py'),'--kernel',str(out/'native.macho'),'--prelinked',str(a.original_kernelcache.resolve()),'--slide='+pre['slide'],'--output',str(out/'kernel.macho')]
    for n in pre['roots']:cmd+=['--root',n]
    for n in pre['early_security_initializers']:cmd+=['--early-security-init',n]
    with (out/'prelink.log').open('x') as f:subprocess.run(cmd,cwd=out,stdout=f,stderr=subprocess.STDOUT,check=True)
    assert verify_original_executables(out/'kernel.macho',read(out/'kernel.json'),pre['original_executable_sha256'])==30
    before=entry((parent/'kernel.macho').read_bytes());after=entry((out/'kernel.macho').read_bytes());assert before[2]==after[2] and before[1]-before[0]==after[1]-after[0]==7124
    source_inputs={str(f.relative_to(ROOT)):sha(f) for f in [ROOT/'drivers/EldenBluetooth/NativeHost.cpp',ROOT/'drivers/EldenBluetooth/RegistrySource.py',ROOT/'drivers/EldenBluetooth/ProcessLifetimeSource.py',ROOT/'drivers/EldenBluetooth/diagnostics/TransportTrace.py',Path(__file__).resolve()]}
    write(out/'result.json',{'profile':'bt-process-lifetime','key_state':2,'kernel_sha256':sha(out/'kernel.macho'),'native_sha256':sha(out/'native.macho'),'source_inputs':source_inputs,'changed_native_objects':1,'core_filelist_unchanged':True,'objects':records,'archive_members':member_hashes,'inherited_inputs':inputs,'inherited_sources':inherited,'original_apple_executables_hashed':30,'entry_return_target':hex(after[1]),'parent_kernel_sha256':parent_report['kernel_sha256'],'bluetool_launch':True,'device_operation':False,'hardware_tested':False})
    import shutil
    shutil.copytree(parent/'runtime',out/'runtime')
    print(json.dumps({'kernel_sha256':sha(out/'kernel.macho'),'objects':1,'apple_ranges':30}))
if __name__=='__main__':main()
