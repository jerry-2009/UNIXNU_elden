"""Link native root/WCN power into the verified v156 kernel; no boot/flash."""
import argparse,hashlib,io,json,os,shutil,subprocess,sys,tarfile
from pathlib import Path
from replay_xnu_objects import global_symbols,sections
from link_v91_kernel import native_identity,verify_original_executables
from audit_entry_relocation import entry
ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def write(p,v):p.write_text(json.dumps(v,indent=2)+'\n',encoding='utf-8')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def exports(p):return {n for n,v in global_symbols(p).items() if v[0]&0x0e}
def main():
    if sys.flags.optimize:raise ValueError('Assertions required')
    p=argparse.ArgumentParser(description=__doc__)
    for n in ['clean-build','parent-build','native-build','wlan-build','root-build','power-build','wcn-build','original-kernelcache','llvm','output']:p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();base=a.clean_build.resolve();parent=a.parent_build.resolve();out=a.output.resolve()
    contract=read(ROOT/'profiles/ufs-idle-trial/native-contract.json');assert native_identity(parent/'native.macho')==(contract['sections'],contract['commands'],contract['symbols'])
    previous=read(parent/'result.json');assert previous['profile']=='ufs-idle-trial' and sha(parent/'kernel.macho')==previous['kernel_sha256']
    out.mkdir(parents=True,exist_ok=False);(out/'source').mkdir()
    from build_ufs_wait_objects import compile_units
    changed,records,_,inherited=compile_units(base,parent,out,a.llvm,queue=True,idle=True,idle_normal=True)
    assert set(changed)=={'ShengUfs.o'}
    nr=read(a.native_build/'result.json');wr=read(a.wlan_build/'result.json');rr=read(a.root_build/'result.json');pr=read(a.power_build/'result.json');cr=read(a.wcn_build/'result.json')
    assert nr['native_root_worker_bound'] and wr['root_worker_hooks'] and wr['root_power_provider']
    supplied={'Native.o':(a.native_build/'Native.o',nr['object_sha256']),
              'Root.o':(a.root_build/'Root.o',rr['objects']['Root']['object_sha256']),
              'Phy.o':(a.root_build/'Phy.o',rr['objects']['Phy']['object_sha256']),
              'Power.o':(a.power_build/'Power.o',pr['plan_object_sha256']),
              'WcnPowerNative.o':(a.wlan_build/'WcnPowerNative.o',wr['object_sha256']),
              'WcnPower.o':(a.wcn_build/'WcnPower.o',cr['objects']['WcnPower']['object_sha256'])}
    for file,h in supplied.values():assert sha(file)==h,file
    for report,key,prefix in [(nr,'source_inputs',ROOT),(wr,'source_inputs',ROOT),(rr,'source_sha256',ROOT/'drivers/EldenPcie'),(pr,'source_sha256',ROOT)]:
        for file,h in report[key].items():assert sha(prefix/file)==h,file
    shared_sources={'drivers/EldenBluetooth/WcnPower.c':cr['objects']['WcnPower']['source_sha256']}
    for name in ['WcnPower.h','WcnSharedPower.h','WcnSharedPower.inc']:
        shared_sources['drivers/EldenBluetooth/'+name]=cr['headers_sha256'][name]
    for file,h in shared_sources.items():assert sha(ROOT/file)==h,file
    link=read(parent/'link-command.json');replacements={};member_hashes={}
    groups={'libShengUfs.a':{'ShengUfs.o':changed['ShengUfs.o']},
            'libEldenBluetooth.a':{name:supplied[name][0] for name in ['WcnPower.o','WcnPowerNative.o']}}
    for archive_name,selected in groups.items():
        found=[x.split(',')[-1] for x in link if x.endswith('/'+archive_name)];assert len(found)==1;old=Path(found[0])
        folder=out/archive_name.removesuffix('.a');folder.mkdir()
        names=[n for n in subprocess.check_output(['ar','t',str(old)],text=True).splitlines() if not n.startswith('__.SYMDEF')];assert set(selected)<=set(names)
        members={}
        for name in names:
            data=selected[name].read_bytes() if name in selected else subprocess.check_output(['ar','p',str(old),name])
            (folder/name).write_bytes(data);members[name]=hashlib.sha256(data).hexdigest()
        target=folder/archive_name;subprocess.run(['ar','rcs',str(target),*names],cwd=folder,env=dict(os.environ,ZERO_AR_DATE='1'),check=True)
        for name in names:
            actual=subprocess.check_output(['ar','p',str(target),name]);expected=(folder/name).read_bytes()
            assert actual==expected or actual==expected+b'\n'*((-len(expected))%8)
        replacements[str(old)]=str(target);member_hashes[archive_name]=members
    pcie=out/'libEldenPcie.a';subprocess.run(['ar','rcs',str(pcie),*[str(supplied[n][0]) for n in ['Native.o','Root.o','Phy.o','Power.o']]],env=dict(os.environ,ZERO_AR_DATE='1'),check=True)
    inherited_inputs={str(parent/'link.filelist'):sha(parent/'link.filelist')}
    for file in (parent/'link.filelist').read_text().splitlines():inherited_inputs[file]=sha(Path(file))
    for arg in link:
        file=arg.split(',')[-1]
        if file.endswith(('.o','.a')) and Path(file).is_file():inherited_inputs[file]=sha(Path(file))
    files=[x.split(',')[-1] for x in link if x.endswith('link.filelist')];assert len(files)==1
    (out/'link.filelist').write_bytes((parent/'link.filelist').read_bytes())
    command=[x.replace(str(parent/'native.macho'),str(out/'native.macho')).replace(files[0],str(out/'link.filelist')) for x in link]
    for old,new in replacements.items():command=[x.replace(old,new) for x in command]
    command.append('-Wl,-force_load,'+str(pcie));write(out/'link-command.json',command)
    env=dict(os.environ,CCC_OVERRIDE_OPTIONS='+-Wno-unknown-warning-option');env.pop('SDKROOT',None)
    with (out/'link.log').open('x') as log:subprocess.run(command,cwd=out,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
    expected=exports(parent/'native.macho')|set().union(*(exports(p) for p,h in supplied.values()))
    assert exports(out/'native.macho')==expected
    for file,h in {**inherited_inputs,**inherited}.items():assert sha(Path(file))==h,file
    pre=read(ROOT/'profiles/v91/image-build/plan.json')['prelink'];assert sha(a.original_kernelcache)==pre['original_kernelcache_sha256']
    kit=out/'prelink-tool';kit.mkdir()
    packed=subprocess.check_output(['git','-C',str(base/'dependencies/XnuPrelink'),'archive',pre['commit']])
    with tarfile.open(fileobj=io.BytesIO(packed)) as archive:archive.extractall(kit,filter='data')
    command=[sys.executable,str(kit/'emit_prelink.py'),'--kernel',str(out/'native.macho'),'--prelinked',str(a.original_kernelcache.resolve()),'--slide='+pre['slide'],'--output',str(out/'kernel.macho')]
    for value in pre['roots']:command+=['--root',value]
    for value in pre['early_security_initializers']:command+=['--early-security-init',value]
    with (out/'prelink.log').open('x') as log:subprocess.run(command,cwd=out,stdout=log,stderr=subprocess.STDOUT,check=True)
    assert verify_original_executables(out/'kernel.macho',read(out/'kernel.json'),pre['original_executable_sha256'])==30
    before=entry((parent/'kernel.macho').read_bytes());after=entry((out/'kernel.macho').read_bytes())
    assert before[2]==after[2] and before[1]-before[0]==after[1]-after[0]==7124
    shutil.copytree(parent/'runtime',out/'runtime')
    own={**nr['source_inputs'],**wr['source_inputs'],**{'drivers/EldenPcie/'+n:h for n,h in rr['source_sha256'].items()},**pr['source_sha256'],**shared_sources}
    for path in ['tools/build_pcie_root_kernel.py','tools/build_ufs_wait_objects.py','drivers/EldenUfsIdle/IdleSource.py']:own[path]=sha(ROOT/path)
    sources={**previous['source_inputs'],**own}
    report={'profile':'pcie-root-trial','kernel_sha256':sha(out/'kernel.macho'),'native_sha256':sha(out/'native.macho'),
            'source_inputs':sources,'optional_runtime':previous['optional_runtime'],'core_filelist_unchanged':True,'changed_core_objects':0,'scalar':True,
            'changed_native_objects':3,'added_native_objects':4,'native_objects':records,'archive_members':member_hashes,
            'component_objects':{n:{'path':str(p),'sha256':h} for n,(p,h) in supplied.items()},
            'parent_kernel_sha256':previous['kernel_sha256'],'original_apple_executables_hashed':30,'entry_return_target':hex(after[1]),
            'ufs_diagnostic_removed':True,'ufs_ah8_retained':True,'root_worker_bound':True,'boot_packaged':False,'hardware_tested':False}
    write(out/'result.json',report);print(json.dumps({k:v for k,v in report.items() if k in ['profile','kernel_sha256','changed_native_objects','added_native_objects','original_apple_executables_hashed','boot_packaged']}))
if __name__=='__main__':main()
