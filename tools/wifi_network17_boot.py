"""Qualify only the new iOS17 network bridge and its retained service runtime."""
from pathlib import Path
import hashlib,importlib.util,json,sys,subprocess
ROOT=Path(__file__).resolve().parents[1]
PARENT_KERNEL='b6b0d1b8daa2e19f69b3e3a909a6654ba148289da79b180cd25ee49d3cb873b4'


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def qualify_vdev_array(runtime):
    if runtime.get('umac_hold_trial') is not True or runtime.get('vdev_array_delta_reversible') is not True or runtime.get('vdev_array_peach_only') is not True or runtime.get('vdev_other_and_mlo_streams_unchanged') is not True or (runtime.get('vdev_array_tag'),runtime.get('vdev_array_bytes'),runtime.get('vdev_array_vendor_commit'))!=(18,4,'d50b305f7da9e14715a25120a4ac7b1a4b8b97c3'):
        raise ValueError('Wrong exact OEM VDEV array repair')
    if runtime.get('vdev_parent_wmi_source_sha256')!='0c2e215a5c0fd6e65766959b4e076b0e5db340b941000730c6ed649a24fbdbd5' or runtime.get('vdev_fixed_wmi_source_sha256')!='8a64e386a5ad6fadf3639a694ded604f3509aafa6795c7e93c500d1849f195ee':
        raise ValueError('Wrong exact VDEV WMI sources')


def qualify_ce3_direct(runtime):
    if runtime.get('umac_hold_trial') is not True or runtime.get('vdev_empty_mlo_array') is not True or runtime.get('ce3_direct_delta_reversible') is not True or runtime.get('ce3_only') is not True or runtime.get('ce3_qmi_shadow_config_unchanged') is not True or runtime.get('other_ce_mhi_irq_firmware_policy_unchanged') is not True or (runtime.get('ce3_ring_id'),runtime.get('ce3_hp_offset'))!=(67,0x1b86400) or runtime.get('changed_units')!=['ath12k_wmi.o','ath12k_pci.o','w7_hal.o']:
        raise ValueError('Wrong exact CE3 direct-HP contrast')


def qualify_ce3_inspect(runtime,worker):
    if runtime.get('umac_hold_trial') is not True or runtime.get('vdev_empty_mlo_array') is not True or runtime.get('ce3_direct_trial') or runtime.get('ce3_inspect_delta_reversible') is not True or runtime.get('first_failure_only') is not True or runtime.get('no_payload_or_command_value_logging') is not True or (runtime.get('max_descriptor_records'),runtime.get('register_read_count'))!=(4,18) or runtime.get('added_inspect_native_import')!='_elden_wifi_dma_inspect' or worker.get('ce3_inspect_trial') is not True:
        raise ValueError('Wrong bounded first-CE3 inspection pair')


def qualify_ce3_timeline(runtime):
    if runtime.get('ce3_inspect_trial') is not True or runtime.get('ce3_direct_trial') or runtime.get('timeline_delta_reversible') is not True or (runtime.get('timeline_events_max'),runtime.get('timeline_reads_per_event'))!=(16,9) or runtime.get('runtime_added_exports')!=['_elden_ce3_timeline'] or runtime.get('changed_units')!=['ath12k_wmi.o','ath12k_pci.o','ath12k_core.o']:
        raise ValueError('Wrong bounded CE3 start timeline')


def qualify_window_reselect(runtime):
    if runtime.get('ce3_timeline_trial') is not True or runtime.get('ce3_direct_trial') or runtime.get('window_delta_reversible') is not True or runtime.get('window_peach_only') is not True or runtime.get('window_lock_value_readback_preserved') is not True:
        raise ValueError('Wrong exact OEM window reselection')


def qualify_pci_state_trace(runtime):
    if runtime.get('window_reselect_trial') is not True or runtime.get('pci_state_trace_reversible') is not True or (runtime.get('pci_state_write_records_max'),runtime.get('pci_state_read_records_max'))!=(32,16) or runtime.get('pci_state_no_new_mmio_writes') is not True or runtime.get('pci_state_existing_hook_not_replaced') is not True or runtime.get('pci_state_hook_owned_restore') is not True or runtime.get('pci_state_payload_logging') is not False:
        raise ValueError('Wrong bounded passive PCI state observation')


def qualify_components(report):
    parent=report['retained_parent_report']
    if report['profile']!='wifi-network-17' or parent['profile']!='wifi-service-scan' or parent['kernel_sha256']!=PARENT_KERNEL:
        raise ValueError('Wrong network bridge baseline')
    if report['retained_parent_kernel_sha256']!=PARENT_KERNEL or report['retained_parent_native_sha256']!=parent['native_sha256']:
        raise ValueError('Wrong retained native baseline')
    stride=report.get('mac_phy_stride_runtime')
    battery=report.get('battery_admission')
    if bool(report.get('wifi_battery_runtime_trial'))!=bool(battery):raise ValueError('Radio-only admission report mismatch')
    if report.get('ce_wmi_firmware_objects_unchanged') is not (not bool(stride)) or report.get('core_filelist_unchanged') is not True or (report['changed_core_objects'],report['changed_native_objects'],report['added_native_objects'])!=(0,(2 if stride else 1)+int(bool(battery)),1):
        raise ValueError('Wrong network-only composition')
    for name in ('core','service_assets','optional_runtime','service_native','runtime_snapshot'):
        if report.get(name)!=parent.get(name):raise ValueError('Retained service changed: '+name)
    sys.path.insert(0,str(ROOT/'drivers/EldenWifi/net'))
    from Net17Source import source
    from Net17NativeSource import generated
    net=report['network_bridge'];worker=report['network_worker']
    hold=report.get('mhi_hold_trial') is True
    umac=report.get('umac_hold_trial') is True
    direct=report.get('ce3_direct_trial') is True
    inspect=report.get('ce3_inspect_trial') is True
    timeline=report.get('ce3_timeline_trial') is True
    if hold and umac:raise ValueError('Mutually exclusive wake trials')
    if hold!=bool(worker.get('mhi_hold_trial')) or hold!=bool(stride and stride.get('mhi_hold_trial')):raise ValueError('MHI wake pair mismatch')
    if umac!=bool(worker.get('umac_hold_trial')) or umac!=bool(stride and stride.get('umac_hold_trial')):raise ValueError('UMAC wake pair mismatch')
    if bool(report.get('vdev_empty_mlo_array'))!=bool(stride and stride.get('vdev_empty_mlo_array')):raise ValueError('VDEV repair report mismatch')
    if direct!=bool(stride and stride.get('ce3_direct_trial')):raise ValueError('CE3 direct report mismatch')
    if inspect!=bool(stride and stride.get('ce3_inspect_trial')) or inspect!=bool(worker.get('ce3_inspect_trial')):raise ValueError('CE3 inspection report mismatch')
    if timeline!=bool(stride and stride.get('ce3_timeline_trial')):raise ValueError('CE3 timeline report mismatch')
    if bool(report.get('window_reselect_trial'))!=bool(stride and stride.get('window_reselect_trial')):raise ValueError('Window reselection report mismatch')
    if bool(report.get('pci_state_trace_trial'))!=bool(stride and stride.get('pci_state_trace_trial')):raise ValueError('PCI state observation report mismatch')
    if bool(worker.get('wifi_battery_runtime_trial'))!=bool(battery):raise ValueError('Radio-only admission worker mismatch')
    if net['source_sha256']!=hashlib.sha256(source()).hexdigest() or worker['generated_sources']!={name:hashlib.sha256(data).hexdigest() for name,data in generated(hold,umac,inspect,bool(battery)).items()}:
        raise ValueError('Network bridge source differs')
    if not worker['platform_physical_fence_preserved'] or not worker['no_ce_wmi_firmware_changes'] or not net['late_initializer_owned'] or not net['other_sections_preserved']:
        raise ValueError('Network lifecycle/late initializer not qualified')
    for name,digest in {**net['source_inputs'],**worker['source_inputs']}.items():
        if sha(ROOT/name)!=digest:raise ValueError('Network input changed: '+name)
    components=report['component_objects']
    if battery:
        if battery.get('compiled') is not True or battery.get('radio_only_no_charger_set') is not True or battery.get('chemistry_two_gauges_epoch_age_checked') is not True or battery.get('controls_and_charger_permission_unchanged') is not True:raise ValueError('Radio-only admission gates not qualified')
        sys.path.insert(0,str(ROOT/'drivers/EldenWifi'));import BatteryAdmissionSource as battery_source
        for unit,data in [('PmicClient',battery_source.client()),('WcnPowerNative',battery_source.wcn())]:
            row=battery['consumers'][unit]
            if hashlib.sha256(data).hexdigest()!=row['source_sha256']:raise ValueError('Radio-only consumer source differs')
        for name,digest in battery['source_inputs'].items():
            if sha(ROOT/name)!=digest:raise ValueError('Radio-only admission input changed')
        if sha(Path(battery['pmic_archive']))!=battery['pmic_archive_sha256']:raise ValueError('Radio-only PMIC archive differs')
        if worker.get('battery_provider_sha256')!=battery['consumers']['PmicClient']['object_sha256']:raise ValueError('Radio-only worker provider differs')
        loaded=report.get('battery_loaded_archives',{})
        if set(loaded)!={'pmic','wcn'}:raise ValueError('Actual PMIC/WCN archive binding missing')
        for key,unit,member in [('pmic','PmicClient','PmicClient.o'),('wcn','WcnPowerNative','WcnPowerNative.o')]:
            row=loaded[key]
            if row['member']!=member or row['member_sha256']!=battery['consumers'][unit]['object_sha256'] or sha(Path(row['path']))!=row['sha256'] or hashlib.sha256(subprocess.check_output(['ar','p',row['path'],member])).hexdigest()!=row['member_sha256']:
                raise ValueError('Actual loaded battery provider member differs')
        wcn=components['WcnPowerNative.o']
        if wcn['sha256']!=battery['consumers']['WcnPowerNative']['object_sha256'] or sha(Path(wcn['path']))!=wcn['sha256']:raise ValueError('Radio-only WCN consumer differs')
    if stride:
        if stride.get('mac_phy_stride_fix') is not True or (not (hold or umac) and (stride.get('imports_exports_unchanged') is not True or stride.get('other_ce_mhi_pci_irq_firmware_objects_unchanged') is not True or stride.get('changed_units')!=['ath12k_wmi.o'])) or stride['base_binding_sha256']!=parent['component_objects']['WifiRuntimeMsiBinding.o']['sha256']:
            raise ValueError('Wrong MAC/PHY-only runtime repair')
        if hold and (stride.get('lease_delta_reversible') is not True or stride.get('native_opt_in_only') is not True or stride.get('other_ce_mhi_irq_firmware_objects_unchanged') is not True or stride.get('changed_units')!=['ath12k_wmi.o','ath12k_pci.o'] or stride.get('added_native_import')!='_elden_wifi_mhi_hold_requested'):
            raise ValueError('Wrong bounded MHI wake lease')
        if umac and (stride.get('umac_delta_reversible') is not True or stride.get('native_opt_in_only') is not True or (not direct and stride.get('other_ce_mhi_irq_firmware_objects_unchanged') is not True) or stride.get('changed_units')!=['ath12k_wmi.o','ath12k_pci.o']+(['w7_hal.o'] if direct else ['ath12k_core.o'] if timeline else []) or stride.get('added_native_import')!='_elden_wifi_umac_hold_requested' or stride.get('mhi_reference_and_umac_handshake') is not True or (stride.get('umac_request_offset'),stride.get('umac_status_offset'),stride.get('umac_ready_value'),stride.get('umac_polling_bound_ms'))!=(0x3004,0x1e04040,2,50)):
            raise ValueError('Wrong exact OEM UMAC wake contract')
        if stride.get('vdev_empty_mlo_array'):qualify_vdev_array(stride)
        if direct:qualify_ce3_direct(stride)
        if inspect:qualify_ce3_inspect(stride,worker)
        if timeline:qualify_ce3_timeline(stride)
        if stride.get('window_reselect_trial'):qualify_window_reselect(stride)
        if stride.get('pci_state_trace_trial'):qualify_pci_state_trace(stride)
        runtime=components['WifiRuntimeMsiBinding.o']
        if runtime['sha256']!=stride['binding_sha256'] or sha(Path(runtime['path']))!=stride['binding_sha256']:
            raise ValueError('MAC/PHY runtime object differs')
        for name,digest in stride['source_inputs'].items():
            if sha(ROOT/name)!=digest:raise ValueError('MAC/PHY input changed')
    for name,proof in [('Native.o',worker),('EldenWifiNet17.late.o',net)]:
        if components[name]['sha256']!=proof['object_sha256'] or sha(Path(components[name]['path']))!=proof['object_sha256']:
            raise ValueError('Network component object differs')
    for name,component in parent['component_objects'].items():
        if name!='Native.o' and not (stride and name=='WifiRuntimeMsiBinding.o') and not (battery and name=='WcnPowerNative.o') and components[name]!=component:raise ValueError('Retained hardware component changed')


def qualify(report_path,entry_path,runtime):
    report=json.loads(Path(report_path).read_text());folder=Path(report_path).parent
    qualify_components(report)
    from charge_verification_boot import qualify_shared_assets
    from audit_pcie_kernel_hooks import audit
    hooks=audit(folder/'native.macho',folder/'kernel.macho',True,True,True,True,True,True,True,True)
    result=qualify_shared_assets(report_path,entry_path,runtime,wifi_service=True)
    result.update(mode=0,root_trial=True,root_hooks=hooks,endpoint_trial=True,smmu_domain=True,memory_detail=True,
        segmented_memory=True,unique_memory=True,prefault_memory=True,mhi_runtime=True,control_transport_bound=True,
        firmware_qdss_config=True,runtime_owned_cleanup=True,runtime_platform_shutdown=True,runtime_platform_budget=True,
        platform_physical_fence=True,network_bridge=True)
    result['mhi_hold_trial']=report.get('mhi_hold_trial') is True
    result['umac_hold_trial']=report.get('umac_hold_trial') is True
    result['vdev_empty_mlo_array']=report.get('vdev_empty_mlo_array') is True
    result['ce3_direct_trial']=report.get('ce3_direct_trial') is True
    result['ce3_inspect_trial']=report.get('ce3_inspect_trial') is True
    result['ce3_timeline_trial']=report.get('ce3_timeline_trial') is True
    result['window_reselect_trial']=report.get('window_reselect_trial') is True
    result['pci_state_trace_trial']=report.get('pci_state_trace_trial') is True
    result['wifi_battery_runtime_trial']=report.get('wifi_battery_runtime_trial') is True
    return result


def menu(qualification):
    if qualification.get('profile')!='wifi-network-17' or not qualification.get('network_bridge') or not qualification.get('wifi_service'):
        raise ValueError('Unqualified network profile')
    from pcie_root_boot import menu as root_menu
    text=root_menu(dict(qualification,profile='wifi-platform-fence')).replace(
        'Wi-Fi physical reset + USB - TEST','Wi-Fi iOS17 network bridge + USB - TEST',1)
    if qualification.get('mhi_hold_trial'):
        import tomllib
        from battery_boot import arguments
        first=tomllib.loads(text)['entry'][0]['args']
        if arguments(first).get('ewt')!='1' or len(first.replace('@SESSION@','0'*16).encode())>1023:raise ValueError('MHI lease requires the existing owned runtime intent')
        # The opt-in is the compiled/qualified runtime-worker pair, not a
        # further command-line flag. Keep all1023 inherited argument bytes.
        text=text.replace('Wi-Fi iOS17 network bridge + USB - TEST','Wi-Fi MHI wake lease + USB - TEST',1)
    if qualification.get('umac_hold_trial'):
        if qualification.get('mhi_hold_trial'):raise ValueError('Mutually exclusive wake trials')
        import tomllib
        from battery_boot import arguments
        first=tomllib.loads(text)['entry'][0]['args']
        if arguments(first).get('ewt')!='1' or len(first.replace('@SESSION@','0'*16).encode())>1023:
            raise ValueError('UMAC wake requires the inherited owned runtime intent')
        text=text.replace('Wi-Fi iOS17 network bridge + USB - TEST','Wi-Fi OEM UMAC wake + USB - TEST',1)
    if qualification.get('vdev_empty_mlo_array'):
        if not qualification.get('umac_hold_trial'):raise ValueError('VDEV repair requires its qualified UMAC parent')
        text=text.replace('Wi-Fi OEM UMAC wake + USB - TEST','Wi-Fi VDEV array repair + USB - TEST',1)
    if qualification.get('ce3_direct_trial'):
        if not qualification.get('vdev_empty_mlo_array'):raise ValueError('CE3 direct requires the qualified VDEV/UMAC parent')
        text=text.replace('Wi-Fi VDEV array repair + USB - TEST','Wi-Fi CE3 direct HP + USB - TEST',1)
    if qualification.get('ce3_inspect_trial'):
        if qualification.get('ce3_direct_trial') or not qualification.get('vdev_empty_mlo_array'):raise ValueError('CE3 inspection requires original shadow VDEV parent')
        text=text.replace('Wi-Fi VDEV array repair + USB - TEST','Wi-Fi CE3 DMA inspect + USB - TEST',1)
    if qualification.get('ce3_timeline_trial'):
        if not qualification.get('ce3_inspect_trial'):raise ValueError('CE3 timeline requires paired inspector parent')
        text=text.replace('Wi-Fi CE3 DMA inspect + USB - TEST','Wi-Fi CE3 start timeline + USB - TEST',1)
    if qualification.get('window_reselect_trial'):
        if not qualification.get('ce3_timeline_trial'):raise ValueError('Window repair requires its exact timeline parent')
        text=text.replace('Wi-Fi CE3 start timeline + USB - TEST','Wi-Fi window reselection + USB - TEST',1)
    if qualification.get('pci_state_trace_trial'):
        if not qualification.get('window_reselect_trial'):raise ValueError('PCI state observation requires its window parent')
        text=text.replace('Wi-Fi window reselection + USB - TEST','Wi-Fi PCI state observation + USB - TEST',1)
    if qualification.get('wifi_battery_runtime_trial'):
        import tomllib
        from battery_boot import arguments
        before=tomllib.loads(text);first=before['entry'][0];args=first['args']
        if arguments(args).get('epd')!='2' or args.split().count('epd=2')!=1:raise ValueError('Unexpected PD trial parent')
        value=args.replace('epd=2','epd=0',1)
        text=text.replace('args = "'+args+'"','args = "'+value+'"',1)
        if tomllib.loads(text)['entry'][1:]!=before['entry'][1:] or tomllib.loads(text)['boot']!=before['boot']:raise ValueError('Radio-only fallback changed')
    return text
