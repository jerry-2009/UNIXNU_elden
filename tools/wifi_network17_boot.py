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
    exports=['_elden_ce3_timeline']+(['_elden_wifi_umac_access_first'] if runtime.get('umac_access_trial') else ['_elden_wifi_umac_command_begin','_elden_wifi_umac_command_end'] if runtime.get('umac_command_lease_trial') else [])+(['_elden_wifi_first_failure_sample'] if runtime.get('first_failure_trial') else [])
    if runtime.get('ce3_inspect_trial') is not True or runtime.get('ce3_direct_trial') or runtime.get('timeline_delta_reversible') is not True or (runtime.get('timeline_events_max'),runtime.get('timeline_reads_per_event'))!=(16,9) or runtime.get('runtime_added_exports')!=exports or runtime.get('changed_units')!=['ath12k_wmi.o','ath12k_pci.o','ath12k_core.o']+(['ath12k_qmi.o'] if runtime.get('host_wake_capability_trial') else []):
        raise ValueError('Wrong bounded CE3 start timeline')


def qualify_window_reselect(runtime):
    if runtime.get('ce3_timeline_trial') is not True or runtime.get('ce3_direct_trial') or runtime.get('window_delta_reversible') is not True or runtime.get('window_peach_only') is not True or runtime.get('window_lock_value_readback_preserved') is not True:
        raise ValueError('Wrong exact OEM window reselection')


def qualify_pci_state_trace(runtime):
    if runtime.get('window_reselect_trial') is not True or runtime.get('pci_state_trace_reversible') is not True or (runtime.get('pci_state_write_records_max'),runtime.get('pci_state_read_records_max'))!=(32,16) or runtime.get('pci_state_no_new_mmio_writes') is not True or runtime.get('pci_state_existing_hook_not_replaced') is not True or runtime.get('pci_state_hook_owned_restore') is not True or runtime.get('pci_state_payload_logging') is not False:
        raise ValueError('Wrong bounded passive PCI state observation')


def qualify_umac_access(runtime):
    if runtime.get('pci_state_trace_trial') is not True or runtime.get('umac_access_reversible') is not True or runtime.get('umac_access_first_pmf_only') is not True or runtime.get('umac_access_balanced_extra_mhi') is not True or (runtime.get('umac_access_poll_bound_ms'),runtime.get('umac_access_ring_writes'))!=(50,0):raise ValueError('Wrong first-access OEM contrast')


def qualify_umac_command_lease(runtime):
    if runtime.get('pci_state_trace_trial') is not True or runtime.get('umac_access_trial') or runtime.get('umac_access_reversible') is not True or runtime.get('umac_access_first_pmf_only') is not False or runtime.get('umac_access_balanced_extra_mhi') is not True or runtime.get('umac_lease_spans_original_send') is not True or (runtime.get('umac_access_poll_bound_ms'),runtime.get('umac_access_ring_writes'))!=(50,0):raise ValueError('Wrong command-scoped OEM lease')


def qualify_oem_init(runtime):
    if runtime.get('pci_state_trace_trial') is not True or runtime.get('umac_access_trial') or runtime.get('umac_command_lease_trial') or any(runtime.get(k) is not True for k in ['oem_init_delta_reversible','oem_init_peach_only','oem_init_firmware_preferred_mode','oem_init_firmware_physical_band_map','oem_init_single_pdev_alias_unchanged','oem_init_no_post_ready_switch']):raise ValueError('Wrong exact OEM initialization mode/map contract')


def qualify_startup_contract(runtime):
    flags = ['startup_contract_reversible', 'startup_contract_no_new_device_writes',
             'startup_contract_par_cpu_only', 'startup_contract_fw_status_parsed',
             'startup_contract_wake_db_owner_checked']
    if runtime.get('pci_state_trace_trial') is not True or any(runtime.get(k) is not True for k in flags) or runtime.get('startup_contract_par_reads_max') != 3 or runtime.get('startup_contract_payload_logging') is not False:
        raise ValueError('Wrong consolidated startup contract observation')
    if runtime.get('umac_access_trial') or runtime.get('umac_command_lease_trial') or runtime.get('oem_init_mode_trial'):
        raise ValueError('Startup evidence requires unchanged functional parent')


def qualify_board_state(runtime, battery):
    if runtime.get('oem_init_mode_trial') is not True or runtime.get('board_state_no_device_controls') is not True or runtime.get('board_state_reversible') is not True or runtime.get('board_state_boundaries') != [12,9,90] or runtime.get('board_state_added_import') != '_elden_wifi_board_state':
        raise ValueError('Wrong physical board-state runtime scope')
    if not battery or battery.get('board_state_trial') is not True or battery.get('sideband_pins_trial') is not True or battery.get('board_state_no_device_controls') is not True or battery.get('board_state_gpio_indices') != [16,18,19,202] or battery.get('board_state_rails') != 6:
        raise ValueError('Physical board-state provider mismatch')


def qualify_host_wake_capability(runtime):
    if runtime.get('oem_init_mode_trial') is not True or any(runtime.get(k) is not True for k in ['host_wake_capability_reversible','host_wake_capability_peach_only','host_wake_callback_derived','host_wake_no_credit_timeout_ring_change']) or (runtime.get('host_wake_msi_vector_count'),runtime.get('host_wake_msi_base'),runtime.get('host_wake_qmi_tlv')) != (1,13,0x11) or runtime.get('host_wake_vendor_commit') != 'd50b305f7da9e14715a25120a4ac7b1a4b8b97c3':
        raise ValueError('Wrong OEM callback-derived WAKE host capability')


def qualify_posted_reset(runtime):
    sys.path.insert(0, str(ROOT / 'drivers/EldenWifi/peach'))
    from PostedResetPatch import EXPECTED, UPSTREAM, READBACK, patch
    flags = ['posted_reset_reversible', 'posted_reset_writes_unchanged',
             'posted_reset_ring_credit_firmware_unchanged']
    if runtime.get('host_wake_capability_trial') is not True or any(runtime.get(k) is not True for k in flags) or (runtime.get('posted_reset_readbacks'), runtime.get('posted_reset_delay_ms'), runtime.get('posted_reset_upstream_commit'), runtime.get('posted_reset_parent_source_sha256')) != (2, 10, UPSTREAM, EXPECTED):
        raise ValueError('Wrong pinned TB322FC posted-reset contract')
    command = runtime['pci_state_command']
    candidates = [Path(v) for v in command if v.endswith('/pci.c')]
    if len(candidates) != 1:
        raise ValueError('Posted-reset consumed source missing')
    source = candidates[0]
    data = source.read_bytes()
    if runtime.get('umac_register_trial'):
        data = Path(runtime['umac_register_parent_source']).read_bytes()
    restored = data.decode().replace(READBACK, '').encode()
    if hashlib.sha256(restored).hexdigest() != EXPECTED or patch(restored) != data or hashlib.sha256(data).hexdigest() != runtime['posted_reset_source_sha256'] or (not runtime.get('umac_register_trial') and runtime['pci_state_source_sha256'] != runtime['posted_reset_source_sha256']):
        raise ValueError('Posted-reset source does not reproduce the exact patch')
    obj = (Path(runtime['umac_register_parent_source']) if runtime.get('umac_register_trial') else source).parent / 'ath12k_pci.o'
    if sha(obj) != runtime['posted_reset_object_sha256'] or (not runtime.get('umac_register_trial') and runtime['pci_state_object_sha256'] != runtime['posted_reset_object_sha256']):
        raise ValueError('Posted-reset consumed object differs')


def qualify_umac_register(runtime):
    sys.path.insert(0,str(ROOT/'drivers/EldenWifi/peach'))
    from UmacRegisterPatch import EXPECTED, VENDOR, patch
    flags=['umac_register_reversible','umac_register_peach_only','umac_register_raw_no_recursion',
           'umac_register_balanced_refs','umac_register_failure_suppresses_access',
           'umac_register_ring_credit_firmware_unchanged','umac_register_failed_handshake_latched']
    if runtime.get('posted_reset_trial') is not True or any(runtime.get(k) is not True for k in flags) or runtime.get('umac_register_startup_hold') is not False or (runtime.get('umac_register_threshold'),runtime.get('umac_register_checks'),runtime.get('umac_register_vendor_commit'),runtime.get('umac_register_parent_source_sha256'))!=(0xfe0,11,VENDOR,EXPECTED):
        raise ValueError('Wrong OEM per-register UMAC contract')
    parent=Path(runtime['umac_register_parent_source'])
    candidates=[Path(v) for v in runtime['pci_state_command'] if v.endswith('/pci.c')]
    source=candidates[0] if len(candidates)==1 else None
    obj=source.parent/'ath12k_pci.o' if source else None
    if runtime.get('first_failure_trial'):
        source=Path(runtime['first_failure_parent_units']['pci.c']['source'])
        obj=Path(runtime['first_failure_parent_units']['pci.c']['object'])
    if len(candidates)!=1 or sha(parent)!=EXPECTED or patch(parent.read_bytes())!=source.read_bytes() or sha(source)!=runtime['umac_register_source_sha256'] or (not runtime.get('first_failure_trial') and runtime['pci_state_source_sha256']!=runtime['umac_register_source_sha256']):
        raise ValueError('UMAC register source does not reproduce the exact patch')
    if sha(obj)!=runtime['umac_register_object_sha256'] or (not runtime.get('first_failure_trial') and runtime['pci_state_object_sha256']!=runtime['umac_register_object_sha256']):
        raise ValueError('UMAC register consumed object differs')


def qualify_first_failure(runtime,worker):
    sys.path.insert(0,str(ROOT/'drivers/EldenWifi/peach'))
    from FirstFailurePatch import EXPECTED,patch
    flags=['first_failure_reversible','first_failure_no_new_control_writes','first_failure_raw_no_wake','first_failure_readclear_excluded']
    if runtime.get('umac_register_trial') is not True or any(runtime.get(k) is not True for k in flags) or runtime.get('first_failure_stages')!=[12,90] or (runtime.get('first_failure_raw_count'),runtime.get('first_failure_physical_count'))!=(21,47):raise ValueError('Wrong consolidated first-failure scope')
    if worker.get('first_failure_physical') is not True or worker.get('first_failure_readonly') is not True or worker.get('first_failure_no_new_maps') is not True or worker.get('first_failure_no_control_writes') is not True or worker.get('first_failure_sample_stages')!=[12,90] or runtime.get('first_failure_worker_sha256')!=worker['object_sha256']:raise ValueError('First-failure physical worker mismatch')
    for n in ['pci.c','core.c']:
        parent=runtime['first_failure_parent_units'][n];row=runtime['first_failure_units'][n]
        old=Path(parent['source']);source=Path(row['source']);obj=Path(row['object'])
        if sha(old)!=EXPECTED[n] or sha(old)!=parent['source_sha256'] or patch(n,old.read_bytes())!=source.read_bytes() or sha(source)!=row['source_sha256'] or sha(obj)!=row['object_sha256']:raise ValueError('First-failure source/object differs: '+n)


def qualify_eager_memory(runtime):
    sys.path.insert(0,str(ROOT/'drivers/EldenWifi/peach'))
    from EagerMemoryPatch import EXPECTED,VENDOR,patch
    flags=['eager_memory_peach_only','eager_memory_reversible','eager_memory_oem_tlv33_absent','eager_memory_memory_request_protocol_unchanged','eager_memory_no_firmware_power_ring_change']
    if runtime.get('first_failure_trial') is not True or any(runtime.get(k) is not True for k in flags) or runtime.get('eager_memory_vendor_commit')!=VENDOR:raise ValueError('Wrong OEM eager-memory capability contract')
    original=Path(runtime['eager_memory_parent_source']);source=Path(runtime['eager_memory_source']);obj=Path(runtime['eager_memory_object'])
    if sha(original)!=EXPECTED or sha(original)!=runtime['eager_memory_parent_source_sha256'] or patch(original.read_bytes())!=source.read_bytes() or sha(source)!=runtime['eager_memory_source_sha256'] or sha(obj)!=runtime['eager_memory_object_sha256']:raise ValueError('Eager memory consumed source/object differs')


def qualify_components(report):
    parent=report['retained_parent_report']
    if report['profile']!='wifi-network-17' or parent['profile']!='wifi-service-scan' or parent['kernel_sha256']!=PARENT_KERNEL:
        raise ValueError('Wrong network bridge baseline')
    if report['retained_parent_kernel_sha256']!=PARENT_KERNEL or report['retained_parent_native_sha256']!=parent['native_sha256']:
        raise ValueError('Wrong retained native baseline')
    stride=report.get('mac_phy_stride_runtime')
    battery=report.get('battery_admission')
    if bool(report.get('wifi_battery_runtime_trial'))!=bool(battery):raise ValueError('Radio-only admission report mismatch')
    if bool(report.get('sideband_pins_trial'))!=bool(battery and battery.get('sideband_pins_trial')):raise ValueError('Sideband report mismatch')
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
    if bool(report.get('umac_access_trial'))!=bool(stride and stride.get('umac_access_trial')):raise ValueError('UMAC first-access report mismatch')
    if bool(report.get('umac_command_lease_trial'))!=bool(stride and stride.get('umac_command_lease_trial')):raise ValueError('UMAC command lease report mismatch')
    if bool(report.get('oem_init_mode_trial'))!=bool(stride and stride.get('oem_init_mode_trial')):raise ValueError('OEM init report mismatch')
    if bool(report.get('startup_contract_trial'))!=bool(stride and stride.get('startup_contract_trial')):raise ValueError('Startup contract report mismatch')
    if bool(report.get('board_state_trial'))!=bool(stride and stride.get('board_state_trial')) or bool(report.get('board_state_trial'))!=bool(battery and battery.get('board_state_trial')):raise ValueError('Board-state pair mismatch')
    if bool(report.get('host_wake_capability_trial'))!=bool(stride and stride.get('host_wake_capability_trial')):raise ValueError('Host wake capability report mismatch')
    if bool(report.get('posted_reset_trial'))!=bool(stride and stride.get('posted_reset_trial')):raise ValueError('Posted-reset report mismatch')
    if bool(report.get('umac_register_trial'))!=bool(stride and stride.get('umac_register_trial')):raise ValueError('UMAC register report mismatch')
    if bool(report.get('first_failure_trial'))!=bool(stride and stride.get('first_failure_trial')) or bool(report.get('first_failure_trial'))!=bool(worker.get('first_failure_physical')):raise ValueError('First-failure report mismatch')
    if bool(report.get('eager_memory_trial'))!=bool(stride and stride.get('eager_memory_trial')):raise ValueError('Eager memory report mismatch')
    if bool(worker.get('wifi_battery_runtime_trial'))!=bool(battery):raise ValueError('Radio-only admission worker mismatch')
    if net['source_sha256']!=hashlib.sha256(source()).hexdigest() or worker['generated_sources']!={name:hashlib.sha256(data).hexdigest() for name,data in generated(hold,umac,inspect,bool(battery),bool(report.get('first_failure_trial'))).items()}:
        raise ValueError('Network bridge source differs')
    if not worker['platform_physical_fence_preserved'] or not worker['no_ce_wmi_firmware_changes'] or not net['late_initializer_owned'] or not net['other_sections_preserved']:
        raise ValueError('Network lifecycle/late initializer not qualified')
    for name,digest in {**net['source_inputs'],**worker['source_inputs']}.items():
        if sha(ROOT/name)!=digest:raise ValueError('Network input changed: '+name)
    components=report['component_objects']
    if battery:
        if battery.get('compiled') is not True or battery.get('radio_only_no_charger_set') is not True or battery.get('chemistry_two_gauges_epoch_age_checked') is not True or battery.get('controls_and_charger_permission_unchanged') is not True:raise ValueError('Radio-only admission gates not qualified')
        sys.path.insert(0,str(ROOT/'drivers/EldenWifi'));import BatteryAdmissionSource as battery_source
        wcn_data=battery_source.wcn()
        if battery.get('sideband_pins_trial'):
            from SidebandSource import source as sideband_source
            if battery.get('sideband_gpio_indices')!=[18,19,202] or battery.get('sideband_cold_before_votes') is not True or battery.get('sideband_unknown_state_retained') is not True:raise ValueError('Sideband physical contract changed')
            wcn_data=sideband_source(bool(battery.get('board_state_trial')))
        for unit,data in [('PmicClient',battery_source.client()),('WcnPowerNative',wcn_data)]:
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
        if umac and (stride.get('umac_delta_reversible') is not True or stride.get('native_opt_in_only') is not True or (not direct and stride.get('other_ce_mhi_irq_firmware_objects_unchanged') is not True) or stride.get('changed_units')!=['ath12k_wmi.o','ath12k_pci.o']+(['w7_hal.o'] if direct else ['ath12k_core.o'] if timeline else [])+(['ath12k_qmi.o'] if stride.get('host_wake_capability_trial') else []) or stride.get('added_native_import')!='_elden_wifi_umac_hold_requested' or stride.get('mhi_reference_and_umac_handshake') is not True or (stride.get('umac_request_offset'),stride.get('umac_status_offset'),stride.get('umac_ready_value'),stride.get('umac_polling_bound_ms'))!=(0x3004,0x1e04040,2,50)):
            raise ValueError('Wrong exact OEM UMAC wake contract')
        if stride.get('vdev_empty_mlo_array'):qualify_vdev_array(stride)
        if direct:qualify_ce3_direct(stride)
        if inspect:qualify_ce3_inspect(stride,worker)
        if timeline:qualify_ce3_timeline(stride)
        if stride.get('window_reselect_trial'):qualify_window_reselect(stride)
        if stride.get('pci_state_trace_trial'):qualify_pci_state_trace(stride)
        if stride.get('umac_access_trial'):qualify_umac_access(stride)
        if stride.get('umac_command_lease_trial'):qualify_umac_command_lease(stride)
        if stride.get('oem_init_mode_trial'):qualify_oem_init(stride)
        if stride.get('startup_contract_trial'):qualify_startup_contract(stride)
        if stride.get('board_state_trial'):qualify_board_state(stride,battery)
        if stride.get('host_wake_capability_trial'):qualify_host_wake_capability(stride)
        if stride.get('posted_reset_trial'):qualify_posted_reset(stride)
        if stride.get('umac_register_trial'):qualify_umac_register(stride)
        if stride.get('first_failure_trial'):qualify_first_failure(stride,worker)
        if stride.get('eager_memory_trial'):qualify_eager_memory(stride)
        runtime=components['WifiRuntimeMsiBinding.o']
        portable=report.get('portable_scan_runtime')
        if bool(report.get('portable_scan_trial'))!=bool(portable):raise ValueError('Portable report pairing differs')
        if portable:
            from wifi_portable_scan import qualify as qualify_portable
            qualify_portable(portable)
            if portable['portable_parent']!=stride:raise ValueError('Portable inherited runtime differs')
        runtime_hash=portable['binding_sha256'] if portable else stride['binding_sha256']
        if runtime['sha256']!=runtime_hash or sha(Path(runtime['path']))!=runtime_hash:
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
    result['umac_access_trial']=report.get('umac_access_trial') is True
    result['umac_command_lease_trial']=report.get('umac_command_lease_trial') is True
    result['oem_init_mode_trial']=report.get('oem_init_mode_trial') is True
    result['sideband_pins_trial']=report.get('sideband_pins_trial') is True
    result['startup_contract_trial']=report.get('startup_contract_trial') is True
    result['board_state_trial']=report.get('board_state_trial') is True
    result['host_wake_capability_trial']=report.get('host_wake_capability_trial') is True
    result['posted_reset_trial']=report.get('posted_reset_trial') is True
    result['umac_register_trial']=report.get('umac_register_trial') is True
    result['first_failure_trial']=report.get('first_failure_trial') is True
    result['eager_memory_trial']=report.get('eager_memory_trial') is True
    result['portable_scan_trial']=report.get('portable_scan_trial') is True
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
    if qualification.get('umac_access_trial'):
        if not qualification.get('pci_state_trace_trial'):raise ValueError('First-access contrast requires its state parent')
        text=text.replace('Wi-Fi PCI state observation + USB - TEST','Wi-Fi OEM first-access wake + USB - TEST',1)
    if qualification.get('umac_command_lease_trial'):
        if not qualification.get('pci_state_trace_trial') or qualification.get('umac_access_trial'):raise ValueError('Command lease requires its exact state parent')
        text=text.replace('Wi-Fi PCI state observation + USB - TEST','Wi-Fi OEM command wake + USB - TEST',1)
    if qualification.get('oem_init_mode_trial'):
        if not qualification.get('pci_state_trace_trial') or qualification.get('umac_access_trial') or qualification.get('umac_command_lease_trial'):raise ValueError('OEM init requires its exact state parent')
        text=text.replace('Wi-Fi PCI state observation + USB - TEST','Wi-Fi OEM init mode + USB - TEST',1)
    if qualification.get('sideband_pins_trial'):
        if not qualification.get('wifi_battery_runtime_trial'):raise ValueError('Sideband requires its qualified real power owner')
        text=text.replace('Wi-Fi PCI state observation + USB - TEST','Wi-Fi board sideband pins + USB - TEST',1)
    if qualification.get('startup_contract_trial'):
        if not qualification.get('pci_state_trace_trial'):raise ValueError('Startup evidence requires its actual observer parent')
        text=text.replace('Wi-Fi board sideband pins + USB - TEST','Wi-Fi startup contract + USB - TEST',1)
    if qualification.get('portable_scan_trial'):
        if not qualification.get('eager_memory_trial'):raise ValueError('Portable scan requires the fixed OEM firmware parent')
        import tomllib
        current=tomllib.loads(text)['entry'][0]['name'] if 'name' in tomllib.loads(text)['entry'][0] else tomllib.loads(text)['entry'][0]['title']
        text=text.replace(current,'Wi-Fi SM8750 portable scan + USB - TEST',1)
    return text
