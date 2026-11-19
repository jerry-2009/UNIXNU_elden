"""Compose the real iOS17 network objects onto the qualified service baseline.

This operation retains CE/WMI/firmware and core objects; it does not continue
the interrupted mode-response candidate, package a boot or access a device.
"""
import argparse,hashlib,io,json,os,shutil,subprocess,sys,tarfile
from pathlib import Path
from replay_xnu_objects import global_symbols
from link_v91_kernel import native_identity,verify_original_executables
from audit_entry_relocation import entry
ROOT=Path(__file__).resolve().parents[1]


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_text())
def write(path,data):path.write_text(json.dumps(data,indent=2)+'\n')
def defs(path):return {n for n,v in global_symbols(path).items() if v[0]&0x0e}
def refs(path):return {n for n,v in global_symbols(path).items() if not v[0]&0x0e}


def main():
    if sys.flags.optimize:raise ValueError('Assertions required')
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('parent-build','worker-build','net-build','clean-build','original-kernelcache','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args();parent=args.parent_build.resolve();out=args.output.resolve()
    prior=read(parent/'result.json');worker=read(args.worker_build/'result.json');net=read(args.net_build/'result.json')
    if prior['profile']!='wifi-service-scan' or not worker['platform_physical_fence_preserved'] or not worker['no_ce_wmi_firmware_changes']:
        raise ValueError('Use the retained service scan and physical-fence baseline')
    for name in ('native','kernel'):
        if sha(parent/(name+'.macho'))!=prior[name+'_sha256']:raise ValueError('Parent kernel identity changed')
    if not worker['compiled'] or not net['compiled'] or worker['net_object_sha256']!=net['object_sha256']:
        raise ValueError('Worker and network pair not qualified')
    if sha(args.worker_build/'Native.o')!=worker['object_sha256'] or sha(args.net_build/'EldenWifiNet17.late.o')!=net['object_sha256']:
        raise ValueError('New object identity changed')
    for proof in (worker,net):
        for name,digest in proof['source_inputs'].items():
            if sha(ROOT/name)!=digest:raise ValueError('New source changed: '+name)
    old_worker=prior['component_objects']['Native.o']
    if old_worker['sha256']!=worker['base_object_sha256']:raise ValueError('Wrong retained worker')
    old_defs=defs(parent/'native.macho');new_net_defs=defs(args.net_build/'EldenWifiNet17.late.o')
    collision=old_defs&new_net_defs
    if collision:raise ValueError('Existing Apple/network classes conflict: '+', '.join(sorted(collision)))
    out.mkdir(parents=True,exist_ok=False);folder=out/'pcie';folder.mkdir()
    command=read(parent/'link-command.json');oldar=[p.split(',')[-1] for p in command if p.endswith('/libEldenPcie.a')]
    if len(oldar)!=1:raise ValueError('Expected one retained PCIe archive')
    oldar=Path(oldar[0]);names=[n for n in subprocess.check_output(['ar','t',oldar],text=True).splitlines() if not n.startswith('__.SYMDEF')]
    if len(names)!=len(set(names)) or names.count('Native.o')!=1 or 'EldenWifiNet17.late.o' in names:
        raise ValueError('Ambiguous retained archive')
    retained={};members={}
    for name in names:
        old=subprocess.check_output(['ar','p',oldar,name]);retained[name]=hashlib.sha256(old).hexdigest()
        data=(args.worker_build/'Native.o').read_bytes() if name=='Native.o' else old
        (folder/name).write_bytes(data);members[name]=hashlib.sha256(data).hexdigest()
    name='EldenWifiNet17.late.o';data=(args.net_build/name).read_bytes();(folder/name).write_bytes(data)
    names.append(name);members[name]=hashlib.sha256(data).hexdigest()
    archive=folder/'libEldenPcie.a';subprocess.run(['ar','rcs',archive,*names],cwd=folder,env=dict(os.environ,ZERO_AR_DATE='1'),check=True)
    for name in names:
        actual=subprocess.check_output(['ar','p',archive,name]);wanted=(folder/name).read_bytes()
        if actual!=wanted and actual!=wanted+b'\n'*((-len(wanted))%8):raise ValueError('Archive contents differ: '+name)
    filelist=(parent/'link.filelist').read_bytes();(out/'link.filelist').write_bytes(filelist)
    inherited={line:sha(Path(line)) for line in filelist.decode().splitlines()}
    for value in command:
        path=Path(value.split(',')[-1])
        if path.suffix in ('.o','.a') and path.is_file():inherited[str(path)]=sha(path)
    oldlists=[p.split(',')[-1] for p in command if p.endswith('link.filelist')]
    if len(oldlists)!=1:raise ValueError('Expected one core filelist')
    command=[value.replace(str(parent/'native.macho'),str(out/'native.macho')).replace(str(oldar),str(archive))
                   .replace(oldlists[0],str(out/'link.filelist')) for value in command]
    write(out/'link-command.json',command)
    env=dict(os.environ,CCC_OVERRIDE_OPTIONS='+-Wno-unknown-warning-option');env.pop('SDKROOT',None)
    with (out/'link.log').open('x') as log:subprocess.run(command,cwd=out,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
    added=set(worker['added_exports'])|new_net_defs
    if defs(out/'native.macho')!=old_defs|added:raise ValueError('Unexpected complete native export set')
    if refs(out/'native.macho')!=refs(parent/'native.macho'):raise ValueError('Unresolved complete native imports changed')
    for path,digest in inherited.items():
        if sha(Path(path))!=digest:raise ValueError('Retained object changed: '+path)
    pre=read(ROOT/'profiles/v91/image-build/plan.json')['prelink']
    if sha(args.original_kernelcache)!=pre['original_kernelcache_sha256']:raise ValueError('Wrong original Apple kernel')
    kit=out/'prelink-tool';kit.mkdir()
    data=subprocess.check_output(['git','-C',str(args.clean_build/'dependencies/XnuPrelink'),'archive',pre['commit']])
    with tarfile.open(fileobj=io.BytesIO(data)) as source:source.extractall(kit,filter='data')
    call=[sys.executable,str(kit/'emit_prelink.py'),'--kernel',str(out/'native.macho'),
          '--prelinked',str(args.original_kernelcache.resolve()),'--slide='+pre['slide'],'--output',str(out/'kernel.macho')]
    for name in pre['roots']:call+=['--root',name]
    for name in pre['early_security_initializers']:call+=['--early-security-init',name]
    with (out/'prelink.log').open('x') as log:subprocess.run(call,cwd=out,stdout=log,stderr=subprocess.STDOUT,check=True)
    if verify_original_executables(out/'kernel.macho',read(out/'kernel.json'),pre['original_executable_sha256'])!=30:
        raise ValueError('Original Apple executable regions differ')
    before=entry((parent/'kernel.macho').read_bytes());after=entry((out/'kernel.macho').read_bytes())
    if before[1]-before[0]!=after[1]-after[0] or after[1]-after[0]!=7124:raise ValueError('Entry branch contract changed')
    s,c,h=native_identity(out/'native.macho');write(out/'native-contract.json',dict(sections=s,commands=c,symbols=h))
    own={**net['source_inputs'],**worker['source_inputs'],'tools/build_wifi_net17_kernel.py':sha(Path(__file__))}
    policy=['tools/wifi_network17_boot.py','tools/wifi_service_boot.py','tools/charge_verification_boot.py','tools/bt_runtime_boot.py',
            'tools/build_charge_verification.py','tools/build_wifi_service_native.py','tools/build_wifi_service_kernel.py']
    changed_policy={name:dict(parent_sha256=prior['source_inputs'].get(name),current_sha256=sha(ROOT/name)) for name in policy}
    inputs={**prior['source_inputs'],**own,**{name:item['current_sha256'] for name,item in changed_policy.items()}}
    plan='profiles/current-build/plan.json'
    if plan in inputs and sha(ROOT/plan)!=inputs[plan]:
        from build_wifi_service_kernel import relocated_baseline_plan
        relocated_baseline_plan((ROOT/plan).read_bytes(),inputs[plan]);inputs[plan]=sha(ROOT/plan)
        frozen='profiles/current-build/frozen/WcnPower-feb9fefa74ee.c';inputs[frozen]=sha(ROOT/frozen)
    for name,digest in inputs.items():
        if sha(ROOT/name)!=digest:raise ValueError('Inherited source differs: '+name)
    shutil.copytree(parent/'runtime',out/'runtime')
    components=dict(prior['component_objects']);components['Native.o']=dict(path=str(args.worker_build/'Native.o'),sha256=worker['object_sha256'])
    components['EldenWifiNet17.late.o']=dict(path=str(args.net_build/'EldenWifiNet17.late.o'),sha256=net['object_sha256'])
    proof=dict(prior)
    proof.update(profile='wifi-network-17',kernel_sha256=sha(out/'kernel.macho'),native_sha256=sha(out/'native.macho'),
        retained_parent_profile=prior['profile'],retained_parent_kernel_sha256=prior['kernel_sha256'],
        retained_parent_native_sha256=prior['native_sha256'],retained_parent_source_inputs=prior['source_inputs'],
        retained_parent_report=prior,source_inputs=inputs,changed_core_objects=0,
        changed_native_objects=1,added_native_objects=1,retained_pcie_members=retained,archive_members=members,
        core_filelist_unchanged=(out/'link.filelist').read_bytes()==filelist,ce_wmi_firmware_objects_unchanged=True,
        all_actual_imports_resolved=True,original_apple_executables_hashed=30,entry_return_target=hex(after[1]),entry_delta=7124,
        native_contract_sha256=sha(out/'native-contract.json'),hardware_tested=False,boot_packaged=False,
        component_objects=components,network_worker=worker,network_bridge=net,parent_policy_updates=changed_policy,
        native_identity_contract=dict(path='native-contract.json',sha256=sha(out/'native-contract.json'),native_sha256=sha(out/'native.macho')))
    write(out/'result.json',proof)
    print(json.dumps({key:proof[key] for key in ('profile','kernel_sha256','native_sha256','all_actual_imports_resolved','hardware_tested')}))


if __name__=='__main__':main()
