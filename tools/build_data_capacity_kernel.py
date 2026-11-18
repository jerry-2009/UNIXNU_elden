"""Rebuild the current core/UFS capacity guards over the exact tested v156 image."""
import argparse,hashlib,importlib.util,io,json,os,re,shutil,subprocess,sys,tarfile
from pathlib import Path
from replay_xnu_objects import global_symbols,sections
from link_v91_kernel import native_identity,verify_original_executables
from audit_entry_relocation import entry
from verify_v91_assets import verify_packed_seed
from data_capacity_boot import source_inputs,SOURCE_MANIFEST
ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads(p.read_text())
def write(p,v):p.write_text(json.dumps(v,indent=2)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def defs(p):return {n for n,v in global_symbols(p).items() if v[0]&0x0e}
def refs(p):return {n for n,v in global_symbols(p).items() if not v[0]&0x0e}
def main():
    if sys.flags.optimize:raise ValueError('Assertions required')
    p=argparse.ArgumentParser(description=__doc__)
    for n in ['parent-build','core-build','clean-build','seed-build','original-kernelcache','llvm','output']:p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--keystore-build',type=Path,help='Also rebuild the actual separately archived KeyStore adapter')
    a=p.parse_args();parent=a.parent_build.resolve();core=a.core_build.resolve();out=a.output.resolve();prior=read(parent/'result.json')
    assert prior['profile']=='ufs-idle-trial'
    expected=read(ROOT/'profiles/ufs-idle-trial/native-contract.json');assert native_identity(parent/'native.macho')==(expected['sections'],expected['commands'],expected['symbols'])
    assert sha(parent/'kernel.macho')==prior['kernel_sha256']
    seed=verify_packed_seed(a.seed_build/'data.packed',a.seed_build/'result.json',expected_bytes=2147483648)
    spec=importlib.util.spec_from_file_location('data_capacity_guards',ROOT/'drivers/EldenDataCapacity/GuardSource.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    out.mkdir(parents=True,exist_ok=False);source=out/'source';source.mkdir();records={};inherited={};changed={}
    oldlist=(parent/'link.filelist').read_text().splitlines();oldcore,=[v for v in oldlist if Path(v).name=='kern_exec.o']
    core_row=read(core/'result.json')['objects']['kern_exec'];ufs_row=prior['native_objects']['ShengUfs']
    old_ufs=Path(ufs_row['command'][ufs_row['command'].index('-o')+1]);assert sha(old_ufs)==ufs_row['object_sha256']
    jobs=[('kern_exec',core_row,Path(oldcore),a.clean_build/'units/working/kern_exec'),('ShengUfs',ufs_row,old_ufs,Path(ufs_row['cwd']))]
    if a.keystore_build:
        key=read(a.keystore_build/'result.json')['objects']['EldenKeyEventsGlue.cpp'];oldkey=Path(key['object']);assert sha(oldkey)==key['sha256']
        cap=read(a.clean_build/'native/capture.json');oldroot=read(ROOT/'profiles/v91/native-build/plan.json')['virtual_root']
        directory=cap['jobs'][592]['directory'];assert directory.startswith(oldroot+'/')
        relative=directory[len(oldroot)+1:]
        if relative.startswith('research/'):relative='records/'+relative[len('research/'):]
        assert not read(a.clean_build/'native/build/results.json')['592']['objcopy']
        jobs.append(('EldenKeyEventsGlue',key,oldkey,a.clean_build/'native/build/project'/relative))
    for name,row,old,cwd in jobs:
        if name=='kern_exec':assert sha(old)==row['sha256']
        command=list(row['command']);overlay=read(Path(command[command.index('-ivfsoverlay')+1]));assert overlay['fallthrough'] is False
        replacements={};bindings=[];count=0
        for item in overlay['roots']:
            f=Path(item['external-contents']);h=sha(f);inherited[str(f)]=h
            if Path(item['name']).suffix not in ('.h','.inc','.c','.cpp'):continue
            if name=='EldenKeyEventsGlue':
                if not item['name'].endswith('/EldenKeyEventsGlue.cpp'):continue
                assert h==row['source_sha256']
            if h not in replacements:
                data=f.read_bytes()
                if b'native_owner_data_seed_size' not in data:replacements[h]=None;continue
                updated,n=m.patch(data)
                if not n:replacements[h]=None;continue
                target=source/(name+'-'+h+'.inc');target.write_bytes(updated);replacements[h]=(target,n);count+=n
            if replacements[h]:
                target,n=replacements[h];item['external-contents']=str(target)
                bindings.append({'virtual':item['name'],'old_sha256':h,'new_sha256':sha(target),'predicates':n})
        assert count=={'kern_exec':3,'ShengUfs':5,'EldenKeyEventsGlue':2}[name],(name,count)
        vfs=out/(name+'.overlay.json');write(vfs,overlay);command[command.index('-ivfsoverlay')+1]=str(vfs)
        obj=out/(name+'.o');command[command.index('-o')+1]=str(obj)
        run=subprocess.run(command,cwd=cwd,capture_output=True);(out/(name+'.log')).write_bytes(run.stdout+run.stderr);run.check_returncode()
        assert defs(obj)==defs(old) and refs(obj)==refs(old)
        oldsec,newsec=sections(old),sections(obj)
        init={key for key in oldsec if key.endswith('/__mod_init_func')}
        assert init=={key for key in newsec if key.endswith('/__mod_init_func')}
        for key in init:assert oldsec[key][:2]==newsec[key][:2]
        if init:
            pattern=r'RELOCATION RECORDS FOR \[__mod_init_func\]:\n(.*?)(?:\n\n|\Z)'
            old_reloc=subprocess.check_output([str(a.llvm/'llvm-objdump'),'--reloc',old],text=True)
            new_reloc=subprocess.check_output([str(a.llvm/'llvm-objdump'),'--reloc',obj],text=True)
            before_init=re.findall(pattern,old_reloc,re.S);after_init=re.findall(pattern,new_reloc,re.S)
            assert before_init and before_init==after_init
        asm=subprocess.check_output([str(a.llvm/'llvm-objdump'),'-dr',obj],text=True);(out/(name+'.asm')).write_text(asm)
        assert not re.search(r'^\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+.*\b[qvdshb]\d+(?:\b|\.)',asm,re.M)
        records[name]={'old_sha256':sha(old),'object_sha256':sha(obj),'command':command,'bindings':bindings,'unique_predicates':count,'warnings':run.stderr.count(b'warning:')};changed[name]=obj
    command=read(parent/'link-command.json');arpath,=[x.split(',')[-1] for x in command if x.endswith('/libShengUfs.a')];oldar=Path(arpath)
    folder=out/'ufs';folder.mkdir();names=[n for n in subprocess.check_output(['ar','t',oldar],text=True).splitlines() if not n.startswith('__.SYMDEF')];assert names.count('ShengUfs.o')==1
    members={}
    for n in names:
        data=changed['ShengUfs'].read_bytes() if n=='ShengUfs.o' else subprocess.check_output(['ar','p',oldar,n]);(folder/n).write_bytes(data);members[n]=hashlib.sha256(data).hexdigest()
    archive=folder/'libShengUfs.a';subprocess.run(['ar','rcs',str(archive),*names],cwd=folder,env=dict(os.environ,ZERO_AR_DATE='1'),check=True)
    for n in names:
        data=subprocess.check_output(['ar','p',archive,n]);wanted=(folder/n).read_bytes();assert data==wanted or data==wanted+b'\n'*((-len(wanted))%8)
    key_archive=None;key_members={};key_arpath=None
    if a.keystore_build:
        key_arpath,=[x.split(',')[-1] for x in command if x.endswith('/libNativeLegacyDisplay.late.a')]
        key_folder=out/'display';key_folder.mkdir()
        key_names=[n for n in subprocess.check_output(['ar','t',key_arpath],text=True).splitlines() if not n.startswith('__.SYMDEF')]
        assert key_names.count('EldenKeyEventsGlue.o')==1
        for n in key_names:
            original_member=subprocess.check_output(['ar','p',key_arpath,n])
            if n=='EldenKeyEventsGlue.o':
                expected_old=oldkey.read_bytes();assert original_member==expected_old or original_member==expected_old+b'\n'*((-len(expected_old))%8)
            data=changed['EldenKeyEventsGlue'].read_bytes() if n=='EldenKeyEventsGlue.o' else original_member
            (key_folder/n).write_bytes(data);key_members[n]=hashlib.sha256(data).hexdigest()
        key_archive=key_folder/'libNativeLegacyDisplay.late.a'
        subprocess.run(['ar','rcs',str(key_archive),*key_names],cwd=key_folder,env=dict(os.environ,ZERO_AR_DATE='1'),check=True)
        for n in key_names:
            got=subprocess.check_output(['ar','p',key_archive,n]);wanted=(key_folder/n).read_bytes();assert got==wanted or got==wanted+b'\n'*((-len(wanted))%8)
    inherited_objects={n:sha(Path(n)) for n in oldlist}
    for arg in command:
        f=arg.split(',')[-1]
        if f.endswith(('.o','.a')) and Path(f).is_file():inherited_objects[f]=sha(Path(f))
    oldfl,=[x.split(',')[-1] for x in command if x.endswith('link.filelist')];filelist=out/'link.filelist'
    filelist.write_text('\n'.join(str(changed['kern_exec']) if n==oldcore else n for n in oldlist)+'\n')
    command=[v.replace(str(parent/'native.macho'),str(out/'native.macho')).replace(oldfl,str(filelist)).replace(arpath,str(archive)) for v in command];write(out/'link-command.json',command)
    if key_archive:
        command=[v.replace(key_arpath,str(key_archive)) for v in command];write(out/'link-command.json',command)
    env=dict(os.environ,CCC_OVERRIDE_OPTIONS='+-Wno-unknown-warning-option');env.pop('SDKROOT',None)
    with (out/'link.log').open('x') as f:subprocess.run(command,cwd=out,env=env,stdout=f,stderr=subprocess.STDOUT,check=True)
    assert defs(out/'native.macho')==defs(parent/'native.macho')
    for f,h in {**inherited,**inherited_objects}.items():assert sha(Path(f))==h,f
    pre=read(ROOT/'profiles/v91/image-build/plan.json')['prelink'];assert sha(a.original_kernelcache)==pre['original_kernelcache_sha256']
    kit=out/'prelink-tool';kit.mkdir()
    with tarfile.open(fileobj=io.BytesIO(subprocess.check_output(['git','-C',str(a.clean_build/'dependencies/XnuPrelink'),'archive',pre['commit']]))) as t:t.extractall(kit,filter='data')
    cmd=[sys.executable,str(kit/'emit_prelink.py'),'--kernel',str(out/'native.macho'),'--prelinked',str(a.original_kernelcache.resolve()),'--slide='+pre['slide'],'--output',str(out/'kernel.macho')]
    for n in pre['roots']:cmd+=['--root',n]
    for n in pre['early_security_initializers']:cmd+=['--early-security-init',n]
    with (out/'prelink.log').open('x') as f:subprocess.run(cmd,cwd=out,stdout=f,stderr=subprocess.STDOUT,check=True)
    assert verify_original_executables(out/'kernel.macho',read(out/'kernel.json'),pre['original_executable_sha256'])==30
    before=entry((parent/'kernel.macho').read_bytes());after=entry((out/'kernel.macho').read_bytes());assert before[2]==after[2] and before[1]-before[0]==after[1]-after[0]==7124
    shutil.copytree(parent/'runtime',out/'runtime')
    own=source_inputs()
    reports={'parent':parent/'result.json','core':core/'result.json','clean':a.clean_build/'units/result.json','seed':a.seed_build/'result.json'}
    if a.keystore_build:reports['keystore']=a.keystore_build/'result.json'
    inherited_reports={name:{'path':str(path.resolve()),'sha256':sha(path)} for name,path in reports.items()}
    result={'profile':'data-capacity-2g-key' if a.keystore_build else 'data-capacity-2g','kernel_sha256':sha(out/'kernel.macho'),'native_sha256':sha(out/'native.macho'),'parent_kernel_sha256':prior['kernel_sha256'],
        'base_report':prior,'optional_runtime':prior['optional_runtime'],'source_inputs':own,'capacity_source_manifest_sha256':own[SOURCE_MANIFEST],'inherited_build_reports':inherited_reports,'inherited_sources':inherited,'inherited_objects':inherited_objects,
        'objects':records,'archive_members':members,'key_archive_members':key_members,'actual_keystore_adapter_rebuilt':bool(a.keystore_build),'seed':seed,'seed_report':read(a.seed_build/'result.json'),'expected_data_bytes':2147483648,'changed_core_objects':1,'changed_native_objects':2 if a.keystore_build else 1,
        'original_apple_executables_hashed':30,'entry_return_target':hex(after[1]),'scalar':True,'boot_packaged':False,'hardware_tested':False}
    write(out/'result.json',result);print(json.dumps({k:result[k] for k in ['profile','kernel_sha256','expected_data_bytes']}))
if __name__=='__main__':main()
