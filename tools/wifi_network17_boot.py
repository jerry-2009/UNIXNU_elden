"""Qualify only the new iOS17 network bridge and its retained service runtime."""
from pathlib import Path
import hashlib,importlib.util,json,sys
ROOT=Path(__file__).resolve().parents[1]
PARENT_KERNEL='b6b0d1b8daa2e19f69b3e3a909a6654ba148289da79b180cd25ee49d3cb873b4'


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def qualify_components(report):
    parent=report['retained_parent_report']
    if report['profile']!='wifi-network-17' or parent['profile']!='wifi-service-scan' or parent['kernel_sha256']!=PARENT_KERNEL:
        raise ValueError('Wrong network bridge baseline')
    if report['retained_parent_kernel_sha256']!=PARENT_KERNEL or report['retained_parent_native_sha256']!=parent['native_sha256']:
        raise ValueError('Wrong retained native baseline')
    stride=report.get('mac_phy_stride_runtime')
    if report.get('ce_wmi_firmware_objects_unchanged') is not (not bool(stride)) or report.get('core_filelist_unchanged') is not True or (report['changed_core_objects'],report['changed_native_objects'],report['added_native_objects'])!=(0,2 if stride else 1,1):
        raise ValueError('Wrong network-only composition')
    for name in ('core','service_assets','optional_runtime','service_native','runtime_snapshot'):
        if report.get(name)!=parent.get(name):raise ValueError('Retained service changed: '+name)
    sys.path.insert(0,str(ROOT/'drivers/EldenWifi/net'))
    from Net17Source import source
    from Net17NativeSource import generated
    net=report['network_bridge'];worker=report['network_worker']
    hold=report.get('mhi_hold_trial') is True
    if hold!=bool(worker.get('mhi_hold_trial')) or hold!=bool(stride and stride.get('mhi_hold_trial')):raise ValueError('MHI wake pair mismatch')
    if net['source_sha256']!=hashlib.sha256(source()).hexdigest() or worker['generated_sources']!={name:hashlib.sha256(data).hexdigest() for name,data in generated(hold).items()}:
        raise ValueError('Network bridge source differs')
    if not worker['platform_physical_fence_preserved'] or not worker['no_ce_wmi_firmware_changes'] or not net['late_initializer_owned'] or not net['other_sections_preserved']:
        raise ValueError('Network lifecycle/late initializer not qualified')
    for name,digest in {**net['source_inputs'],**worker['source_inputs']}.items():
        if sha(ROOT/name)!=digest:raise ValueError('Network input changed: '+name)
    components=report['component_objects']
    if stride:
        if stride.get('mac_phy_stride_fix') is not True or (not hold and (stride.get('imports_exports_unchanged') is not True or stride.get('other_ce_mhi_pci_irq_firmware_objects_unchanged') is not True or stride.get('changed_units')!=['ath12k_wmi.o'])) or stride['base_binding_sha256']!=parent['component_objects']['WifiRuntimeMsiBinding.o']['sha256']:
            raise ValueError('Wrong MAC/PHY-only runtime repair')
        if hold and (stride.get('lease_delta_reversible') is not True or stride.get('native_opt_in_only') is not True or stride.get('other_ce_mhi_irq_firmware_objects_unchanged') is not True or stride.get('changed_units')!=['ath12k_wmi.o','ath12k_pci.o'] or stride.get('added_native_import')!='_elden_wifi_mhi_hold_requested'):
            raise ValueError('Wrong bounded MHI wake lease')
        runtime=components['WifiRuntimeMsiBinding.o']
        if runtime['sha256']!=stride['binding_sha256'] or sha(Path(runtime['path']))!=stride['binding_sha256']:
            raise ValueError('MAC/PHY runtime object differs')
        for name,digest in stride['source_inputs'].items():
            if sha(ROOT/name)!=digest:raise ValueError('MAC/PHY input changed')
    for name,proof in [('Native.o',worker),('EldenWifiNet17.late.o',net)]:
        if components[name]['sha256']!=proof['object_sha256'] or sha(Path(components[name]['path']))!=proof['object_sha256']:
            raise ValueError('Network component object differs')
    for name,component in parent['component_objects'].items():
        if name!='Native.o' and not (stride and name=='WifiRuntimeMsiBinding.o') and components[name]!=component:raise ValueError('Retained hardware component changed')


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
    return text
