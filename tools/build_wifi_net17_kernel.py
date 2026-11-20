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
    parser.add_argument('--mac-phy-runtime',type=Path,help='Explicit qualified full-stride WMI allocation repair')
    parser.add_argument('--battery-admission-build',type=Path,help='Matched radio-only PMIC/WCN admission; PD trial disabled')
    args=parser.parse_args();parent=args.parent_build.resolve();out=args.output.resolve()
    prior=read(parent/'result.json');worker=read(args.worker_build/'result.json');net=read(args.net_build/'result.json')
    stride=read(args.mac_phy_runtime/'result.json') if args.mac_phy_runtime else None
    battery=read(args.battery_admission_build/'result.json') if args.battery_admission_build else None
    if bool(worker.get('wifi_battery_runtime_trial'))!=bool(battery):raise ValueError('Battery admission worker pair mismatch')
    if battery:
        if not battery.get('compiled') or not battery.get('radio_only_no_charger_set') or not battery.get('chemistry_two_gauges_epoch_age_checked') or not battery.get('controls_and_charger_permission_unchanged'):
            raise ValueError('Unqualified radio-only battery admission')
        for name,digest in battery['source_inputs'].items():
            if sha(ROOT/name)!=digest:raise ValueError('Radio-only battery source changed')
        sys.path.insert(0,str(ROOT/'drivers/EldenWifi'));import BatteryAdmissionSource as battery_source
        for unit,data in [('PmicClient',battery_source.client()),('WcnPowerNative',battery_source.wcn())]:
            row=battery['consumers'][unit]
            if row['source_sha256']!=hashlib.sha256(data).hexdigest() or sha(args.battery_admission_build/(unit+'.o'))!=row['object_sha256']:
                raise ValueError('Battery admission consumer changed')
        if worker.get('battery_provider_sha256')!=battery['consumers']['PmicClient']['object_sha256']:raise ValueError('Radio-only worker provider differs')
    if stride:
        base_runtime=prior['component_objects']['WifiRuntimeMsiBinding.o']
        hold=stride.get('mhi_hold_trial') is True
        umac=stride.get('umac_hold_trial') is True
        direct=stride.get('ce3_direct_trial') is True
        inspect=stride.get('ce3_inspect_trial') is True
        timeline=stride.get('ce3_timeline_trial') is True
        if hold and umac:raise ValueError('Mutually exclusive wake trials')
        if not stride['compiled'] or stride.get('mac_phy_stride_fix') is not True or stride['base_binding_sha256']!=base_runtime['sha256'] or (not (hold or umac) and (not stride['imports_exports_unchanged'] or stride['changed_units']!=['ath12k_wmi.o'])):
            raise ValueError('Unqualified MAC/PHY stride runtime')
        if hold and (stride.get('lease_delta_reversible') is not True or stride.get('native_opt_in_only') is not True or stride.get('changed_units')!=['ath12k_wmi.o','ath12k_pci.o'] or stride.get('added_native_import')!='_elden_wifi_mhi_hold_requested' or worker.get('mhi_hold_trial') is not True):
            raise ValueError('MHI wake lease requires the exact opt-in runtime/worker pair')
        if bool(worker.get('mhi_hold_trial'))!=hold:raise ValueError('MHI wake worker/runtime mismatch')
        if umac and (stride.get('umac_delta_reversible') is not True or stride.get('native_opt_in_only') is not True or stride.get('changed_units')!=['ath12k_wmi.o','ath12k_pci.o']+(['w7_hal.o'] if direct else ['ath12k_core.o'] if timeline else []) or stride.get('added_native_import')!='_elden_wifi_umac_hold_requested' or worker.get('umac_hold_trial') is not True or stride.get('mhi_reference_and_umac_handshake') is not True or (stride.get('umac_request_offset'),stride.get('umac_status_offset'),stride.get('umac_ready_value'),stride.get('umac_polling_bound_ms'))!=(0x3004,0x1e04040,2,50)):
            raise ValueError('OEM UMAC wake requires exact contract and runtime/worker pair')
        if bool(worker.get('umac_hold_trial'))!=umac:raise ValueError('UMAC wake worker/runtime mismatch')
        if stride.get('vdev_empty_mlo_array'):
            from wifi_network17_boot import qualify_vdev_array
            qualify_vdev_array(stride)
        if direct:
            from wifi_network17_boot import qualify_ce3_direct
            qualify_ce3_direct(stride)
        if inspect:
            from wifi_network17_boot import qualify_ce3_inspect
            qualify_ce3_inspect(stride,worker)
        if bool(worker.get('ce3_inspect_trial'))!=inspect:raise ValueError('DMA inspection worker/runtime mismatch')
        if timeline:
            from wifi_network17_boot import qualify_ce3_timeline
            qualify_ce3_timeline(stride)
        if stride.get('window_reselect_trial'):
            from wifi_network17_boot import qualify_window_reselect
            qualify_window_reselect(stride)
        if stride.get('pci_state_trace_trial'):
            from wifi_network17_boot import qualify_pci_state_trace
            qualify_pci_state_trace(stride)
        if stride.get('umac_access_trial'):
            from wifi_network17_boot import qualify_umac_access
            qualify_umac_access(stride)
        if stride.get('umac_command_lease_trial'):
            from wifi_network17_boot import qualify_umac_command_lease
            qualify_umac_command_lease(stride)
        if stride.get('oem_init_mode_trial'):
            from wifi_network17_boot import qualify_oem_init
            qualify_oem_init(stride)
        if sha(args.mac_phy_runtime/'WifiRuntimeMsiBinding.o')!=stride['binding_sha256']:
            raise ValueError('MAC/PHY stride runtime artifact changed')
        for name,digest in stride['source_inputs'].items():
            if sha(ROOT/name)!=digest:raise ValueError('MAC/PHY stride source changed')
    if prior['profile']!='wifi-service-scan' or not worker['platform_physical_fence_preserved'] or not worker['no_ce_wmi_firmware_changes']:
        raise ValueError('Use the retained service scan and physical-fence baseline')
    if not stride and (worker.get('mhi_hold_trial') or worker.get('umac_hold_trial') or worker.get('ce3_inspect_trial')):
        raise ValueError('Wake worker requires its qualified runtime')
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
        if battery and name=='WcnPowerNative.o' and retained[name]!=battery['consumers']['WcnPowerNative']['parent_object_sha256']:
            raise ValueError('Loaded WCN admission parent differs')
        data=(args.worker_build/'Native.o').read_bytes() if name=='Native.o' else (args.mac_phy_runtime/'WifiRuntimeMsiBinding.o').read_bytes() if stride and name=='WifiRuntimeMsiBinding.o' else (args.battery_admission_build/'WcnPowerNative.o').read_bytes() if battery and name=='WcnPowerNative.o' else old
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
    if battery:
        oldpmic=Path(battery['parent_pmic_archive']);newpmic=Path(battery['pmic_archive'])
        if sha(oldpmic)!=battery['parent_pmic_archive_sha256'] or sha(newpmic)!=battery['pmic_archive_sha256'] or sum(v.endswith(str(oldpmic)) for v in command)!=1:
            raise ValueError('Loaded battery admission archive pair differs')
        command=[v.replace(str(oldpmic),str(newpmic)) for v in command]
        # The shared WCN object is linked from Bluetooth, not from the PCIe
        # archive. Verify the actual loaded member and replace it there.
        oldbt,=[Path(v.split(',')[-1]) for v in command if v.endswith('/libEldenBluetooth.a')]
        btfolder=out/'bluetooth';btfolder.mkdir();btnames=[n for n in subprocess.check_output(['ar','t',oldbt],text=True).splitlines() if not n.startswith('__.SYMDEF')]
        if len(btnames)!=len(set(btnames)) or btnames.count('WcnPowerNative.o')!=1:raise ValueError('Ambiguous loaded shared WCN member')
        btretained={};btmembers={}
        for name in btnames:
            data=subprocess.check_output(['ar','p',oldbt,name]);btretained[name]=hashlib.sha256(data).hexdigest()
            if name=='WcnPowerNative.o':
                if btretained[name]!=battery['consumers']['WcnPowerNative']['parent_object_sha256']:raise ValueError('Loaded shared WCN parent differs')
                data=(args.battery_admission_build/'WcnPowerNative.o').read_bytes()
            (btfolder/name).write_bytes(data);btmembers[name]=hashlib.sha256(data).hexdigest()
        newbt=btfolder/'libEldenBluetooth.a';subprocess.run(['ar','rcs',str(newbt),*btnames],cwd=btfolder,env=dict(os.environ,ZERO_AR_DATE='1'),check=True)
        loaded=subprocess.check_output(['ar','p',newbt,'WcnPowerNative.o'])
        if hashlib.sha256(loaded).hexdigest()!=battery['consumers']['WcnPowerNative']['object_sha256']:raise ValueError('Actual loaded WCN replacement differs')
        command=[v.replace(str(oldbt),str(newbt)) for v in command]
    write(out/'link-command.json',command)
    env=dict(os.environ,CCC_OVERRIDE_OPTIONS='+-Wno-unknown-warning-option');env.pop('SDKROOT',None)
    with (out/'link.log').open('x') as log:subprocess.run(command,cwd=out,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
    added=set(worker['added_exports'])|new_net_defs|set(stride.get('runtime_added_exports',[]) if stride else [])
    if battery:added.add('_elden_wifi_battery_ready')
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
    if stride:own.update(stride['source_inputs'])
    if battery:own.update(battery['source_inputs'])
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
    if stride:components['WifiRuntimeMsiBinding.o']=dict(path=str(args.mac_phy_runtime/'WifiRuntimeMsiBinding.o'),sha256=stride['binding_sha256'])
    if battery:components['WcnPowerNative.o']=dict(path=str(args.battery_admission_build/'WcnPowerNative.o'),sha256=battery['consumers']['WcnPowerNative']['object_sha256'])
    proof=dict(prior)
    proof.update(profile='wifi-network-17',kernel_sha256=sha(out/'kernel.macho'),native_sha256=sha(out/'native.macho'),
        retained_parent_profile=prior['profile'],retained_parent_kernel_sha256=prior['kernel_sha256'],
        retained_parent_native_sha256=prior['native_sha256'],retained_parent_source_inputs=prior['source_inputs'],
        retained_parent_report=prior,source_inputs=inputs,changed_core_objects=0,
        changed_native_objects=(2 if stride else 1)+int(bool(battery)),added_native_objects=1,retained_pcie_members=retained,archive_members=members,
        core_filelist_unchanged=(out/'link.filelist').read_bytes()==filelist,ce_wmi_firmware_objects_unchanged=not bool(stride),
        all_actual_imports_resolved=True,original_apple_executables_hashed=30,entry_return_target=hex(after[1]),entry_delta=7124,
        native_contract_sha256=sha(out/'native-contract.json'),hardware_tested=False,boot_packaged=False,
        component_objects=components,network_worker=worker,network_bridge=net,parent_policy_updates=changed_policy,
        mac_phy_stride_runtime=stride,station_ready_before_network_publication=True,
        mhi_hold_trial=bool(stride and stride.get('mhi_hold_trial')),
        umac_hold_trial=bool(stride and stride.get('umac_hold_trial')),
        vdev_empty_mlo_array=bool(stride and stride.get('vdev_empty_mlo_array')),
        ce3_direct_trial=bool(stride and stride.get('ce3_direct_trial')),
        ce3_inspect_trial=bool(stride and stride.get('ce3_inspect_trial')),
        ce3_timeline_trial=bool(stride and stride.get('ce3_timeline_trial')),
        window_reselect_trial=bool(stride and stride.get('window_reselect_trial')),
        pci_state_trace_trial=bool(stride and stride.get('pci_state_trace_trial')),
        wifi_battery_runtime_trial=bool(battery),battery_admission=battery,
        umac_access_trial=bool(stride and stride.get('umac_access_trial')),
        umac_command_lease_trial=bool(stride and stride.get('umac_command_lease_trial')),
        oem_init_mode_trial=bool(stride and stride.get('oem_init_mode_trial')),
        native_identity_contract=dict(path='native-contract.json',sha256=sha(out/'native-contract.json'),native_sha256=sha(out/'native.macho')))
    if battery:
        proof['battery_loaded_archives']=dict(pmic=dict(path=str(newpmic),sha256=sha(newpmic),member='PmicClient.o',member_sha256=battery['consumers']['PmicClient']['object_sha256']),
            wcn=dict(path=str(newbt),sha256=sha(newbt),member='WcnPowerNative.o',member_sha256=battery['consumers']['WcnPowerNative']['object_sha256'],retained_members=btretained,members=btmembers))
    write(out/'result.json',proof)
    print(json.dumps({key:proof[key] for key in ('profile','kernel_sha256','native_sha256','all_actual_imports_resolved','hardware_tested')}))


if __name__=='__main__':main()
