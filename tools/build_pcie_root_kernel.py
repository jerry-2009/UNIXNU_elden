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
    p.add_argument('--endpoint-build',type=Path,help='Add the explicitly built BAR/Peach transaction')
    p.add_argument('--smmu-build',type=Path,help='Add the concrete early DMA/SMMU owner')
    p.add_argument('--route-build',type=Path,help='Matched boot registry and derived touch route')
    p.add_argument('--memory-detail',action='store_true',help='Explicit allocator diagnostics profile')
    p.add_argument('--segmented-memory',action='store_true',help='Verify all pages across descriptor segments')
    p.add_argument('--unique-memory',action='store_true',help='Require a distinct NC alias')
    p.add_argument('--prefault-memory',action='store_true',help='Populate the wired alias before PAR checks')
    p.add_argument('--mhi-runtime',action='store_true',help='Include qualified native runtime, firmware and protocol stop')
    a=p.parse_args();base=a.clean_build.resolve();parent=a.parent_build.resolve();out=a.output.resolve()
    if bool(a.smmu_build)!=bool(a.route_build) or (a.smmu_build and not a.endpoint_build):raise ValueError('SMMU needs endpoint and route builds together')
    if a.memory_detail and not a.smmu_build:raise ValueError('Memory diagnostics require SMMU build')
    if a.segmented_memory and not a.memory_detail:raise ValueError('Segmented memory requires diagnostics')
    if a.unique_memory and not a.segmented_memory:raise ValueError('Unique memory requires segmented proof')
    if a.prefault_memory and not a.unique_memory:raise ValueError('Prefault memory requires a unique mapping')
    if a.mhi_runtime and not a.prefault_memory:raise ValueError('MHI requires the verified prefault DMA mapping')
    contract=read(ROOT/'profiles/ufs-idle-trial/native-contract.json');assert native_identity(parent/'native.macho')==(contract['sections'],contract['commands'],contract['symbols'])
    previous=read(parent/'result.json');assert previous['profile']=='ufs-idle-trial' and sha(parent/'kernel.macho')==previous['kernel_sha256']
    out.mkdir(parents=True,exist_ok=False);(out/'source').mkdir()
    from build_ufs_wait_objects import compile_units
    providers=[a.smmu_build/'SmmuNativeBinding.o'] if a.smmu_build else []
    changed,records,_,inherited=compile_units(base,parent,out,a.llvm,queue=True,idle=True,idle_normal=True,early_smmu=bool(a.smmu_build),providers=providers)
    assert set(changed)==({'ShengUfs.o','ArmCpu.o'} if a.smmu_build else {'ShengUfs.o'})
    nr=read(a.native_build/'result.json');wr=read(a.wlan_build/'result.json');rr=read(a.root_build/'result.json');pr=read(a.power_build/'result.json');cr=read(a.wcn_build/'result.json')
    assert nr['native_root_worker_bound'] and wr['root_worker_hooks'] and wr['root_power_provider']
    assert bool(nr.get('endpoint_worker_bound'))==bool(a.endpoint_build)
    assert bool(nr.get('smmu_domain_required'))==bool(a.smmu_build) and bool(wr.get('smmu_stop_hook'))==bool(a.smmu_build)
    assert bool(nr.get('mhi_runtime_bound'))==a.mhi_runtime and bool(wr.get('mhi_deferred_smmu_stop'))==a.mhi_runtime
    supplied={'Native.o':(a.native_build/'Native.o',nr['object_sha256']),
              'Root.o':(a.root_build/'Root.o',rr['objects']['Root']['object_sha256']),
              'Phy.o':(a.root_build/'Phy.o',rr['objects']['Phy']['object_sha256']),
              'Power.o':(a.power_build/'Power.o',pr['plan_object_sha256']),
              'WcnPowerNative.o':(a.wlan_build/'WcnPowerNative.o',wr['object_sha256']),
              'WcnPower.o':(a.wcn_build/'WcnPower.o',cr['objects']['WcnPower']['object_sha256'])}
    endpoint_sources={}
    if a.endpoint_build:
        er=read(a.endpoint_build/'result.json')
        supplied['Endpoint.o']=(a.endpoint_build/'Endpoint.o',er['object_sha256'])
        endpoint_sources={'drivers/EldenPcie/'+n:h for n,h in er['source_sha256'].items()}
        for name,h in endpoint_sources.items():assert sha(ROOT/name)==h,name
    smmu_sources={};smmu_count=0
    if a.smmu_build:
        sr=read(a.smmu_build/'result.json');tr=read(a.route_build/'result.json');smmu_count=sr['component_count'];assert smmu_count==(12 if a.mhi_runtime else 11)
        if a.memory_detail:assert sr.get('memory_report_version')==1
        if a.segmented_memory:assert sr.get('allocator_variant')==('prefault' if a.prefault_memory else 'unique' if a.unique_memory else 'segmented')
        supplied['SmmuNativeBinding.o']=(a.smmu_build/'SmmuNativeBinding.o',sr['binding_sha256'])
        supplied['EldenNvtDmaRoute.o']=(a.route_build/'DmaRoute.o',tr['objects']['DmaRoute']['object_sha256'])
        for report in [sr,tr]:
            for path,h in report['source_inputs'].items():assert sha(ROOT/path)==h,path;smmu_sources[path]=h
        smmu_sources['drivers/EldenSmmu/EarlySource.py']=sha(ROOT/'drivers/EldenSmmu/EarlySource.py')
    mhi_members=[];reused_reader=False
    if a.mhi_runtime:
        assert nr['transport_worker_bound'] and nr['firmware_cache_bound'] and sr['dma_provider_bound']
        def component(name):
            found=[(Path(p),h) for p,h in nr['input_objects'].items() if Path(p).name==name];assert len(found)==1,name
            path,h=found[0];assert sha(path)==h;return path,h
        for name in ['Config.o','Msi.o','MhiStop.o','WifiRuntimeMsiBinding.o','QmiPower.o']:
            supplied[name]=component(name);mhi_members.append(name)
        fw_binding,_=component('FirmwareCacheBinding.o');fw=read(fw_binding.parent/'result.json')
        fw_obj=fw_binding.parent/'FirmwareCache.o';assert sha(fw_obj)==fw['objects']['FirmwareCache']['sha256']
        supplied['FirmwareCache.o']=(fw_obj,sha(fw_obj));mhi_members.append('FirmwareCache.o')
        # The parent already contains the exact original reader. Do not force
        # a second ModemFiles copy into the kernel through the cache binding.
        for name in ['ModemFiles.c','ModemFiles.h']:
            h=sha(ROOT/'drivers/EldenWifi'/name)
            assert h==sha(ROOT/'profiles/v91/sources/tree/drivers/EldenWifi'/name)
        required_reader={'_elden_wifi_file_open','_elden_wifi_file_read','_elden_wifi_files_init'}
        assert required_reader<=exports(parent/'native.macho');reused_reader=True
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
    if a.smmu_build:
        groups['libArmCpu.a']={'ArmCpu.o':changed['ArmCpu.o']}
        groups['libNativeLegacyDisplay.late.a']={'EldenNvtDmaRoute.o':supplied['EldenNvtDmaRoute.o'][0]}
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
    pcie_members=['Native.o','Root.o','Phy.o','Power.o']+(['Endpoint.o'] if a.endpoint_build else [])
    if a.smmu_build:pcie_members.append('SmmuNativeBinding.o')
    pcie_members+=mhi_members
    pcie=out/'libEldenPcie.a';subprocess.run(['ar','rcs',str(pcie),*[str(supplied[n][0]) for n in pcie_members]],env=dict(os.environ,ZERO_AR_DATE='1'),check=True)
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
    expected=exports(parent/'native.macho')|set().union(*(exports(p) for p,h in supplied.values()))|set().union(*(exports(p) for p in changed.values()))
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
    own={**nr['source_inputs'],**wr['source_inputs'],**{'drivers/EldenPcie/'+n:h for n,h in rr['source_sha256'].items()},**pr['source_sha256'],**shared_sources,**endpoint_sources,**smmu_sources}
    for path in ['tools/build_pcie_root_kernel.py','tools/build_ufs_wait_objects.py','drivers/EldenUfsIdle/IdleSource.py']:own[path]=sha(ROOT/path)
    sources={**previous['source_inputs'],**own}
    report={'profile':'wifi-platform-budget' if nr.get('runtime_platform_budget') else 'wifi-platform-shutdown' if nr.get('runtime_platform_shutdown') else 'wifi-qmi-wire-trace' if nr.get('runtime_qmi_trace') else 'wifi-stop-trace' if nr.get('runtime_stop_trace') else 'wifi-drain-lifetime' if nr.get('runtime_owned_cleanup') else 'wifi-qdss-config' if nr.get('control_transport_bound') and nr.get('firmware_qdss_config') else 'wifi-control-transport' if nr.get('control_transport_bound') else 'wifi-init-trace' if a.mhi_runtime and nr.get('runtime_init_trace') else 'wifi-mhi-runtime' if a.mhi_runtime else 'smmu-prefault-memory' if a.prefault_memory else 'smmu-unique-memory' if a.unique_memory else 'smmu-segmented-memory' if a.segmented_memory else 'smmu-memory-detail' if a.memory_detail else 'smmu-domain-trial' if a.smmu_build else 'pcie-endpoint-trial' if a.endpoint_build else 'pcie-root-trial','kernel_sha256':sha(out/'kernel.macho'),'native_sha256':sha(out/'native.macho'),
            'source_inputs':sources,'optional_runtime':previous['optional_runtime'],'core_filelist_unchanged':True,'changed_core_objects':0,'scalar':True,
            'changed_native_objects':5 if a.smmu_build else 3,'added_native_objects':len(pcie_members)+(smmu_count-1 if a.smmu_build else 0)+(124 if a.mhi_runtime else 0),'native_objects':records,'archive_members':member_hashes,
            'component_objects':{n:{'path':str(p),'sha256':h} for n,(p,h) in supplied.items()},
            'parent_kernel_sha256':previous['kernel_sha256'],'original_apple_executables_hashed':30,'entry_return_target':hex(after[1]),
            'ufs_diagnostic_removed':True,'ufs_ah8_retained':True,'root_worker_bound':True,
            'endpoint_worker_bound':bool(a.endpoint_build),'endpoint_generated_sources':nr.get('generated_sources',{}),
            'smmu_domain_bound':bool(a.smmu_build),'smmu_component_count':smmu_count,'owned_sgi_guard':bool(a.smmu_build),
            'memory_report_version':1 if a.memory_detail else 0,
            'allocator_variant':sr.get('allocator_variant') if a.smmu_build else None,
            'allocator_source_sha256':sr.get('allocator_source_sha256') if a.smmu_build else None,
            'mhi_runtime_bound':a.mhi_runtime,'modem_reader_reused':reused_reader,'linux_runtime_objects':125 if a.mhi_runtime else 0,
            'runtime_init_trace':bool(a.mhi_runtime and nr.get('runtime_init_trace')),
            'control_transport_bound':bool(nr.get('control_transport_bound')),
            'firmware_qdss_config':bool(nr.get('firmware_qdss_config')),'runtime_owned_cleanup':bool(nr.get('runtime_owned_cleanup')),'runtime_stop_trace':bool(nr.get('runtime_stop_trace')),'runtime_qmi_trace':bool(nr.get('runtime_qmi_trace')),'runtime_platform_shutdown':bool(nr.get('runtime_platform_shutdown')),'runtime_platform_budget':bool(nr.get('runtime_platform_budget')),
            'boot_packaged':False,'hardware_tested':False}
    write(out/'result.json',report);print(json.dumps({k:v for k,v in report.items() if k in ['profile','kernel_sha256','changed_native_objects','added_native_objects','original_apple_executables_hashed','boot_packaged']}))
if __name__=='__main__':main()
