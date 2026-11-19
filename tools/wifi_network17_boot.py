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
    if report.get('ce_wmi_firmware_objects_unchanged') is not True or report.get('core_filelist_unchanged') is not True or (report['changed_core_objects'],report['changed_native_objects'],report['added_native_objects'])!=(0,1,1):
        raise ValueError('Wrong network-only composition')
    for name in ('core','service_assets','optional_runtime','service_native','runtime_snapshot'):
        if report.get(name)!=parent.get(name):raise ValueError('Retained service changed: '+name)
    sys.path.insert(0,str(ROOT/'drivers/EldenWifi/net'))
    from Net17Source import source
    from Net17NativeSource import generated
    net=report['network_bridge'];worker=report['network_worker']
    if net['source_sha256']!=hashlib.sha256(source()).hexdigest() or worker['generated_sources']!={name:hashlib.sha256(data).hexdigest() for name,data in generated().items()}:
        raise ValueError('Network bridge source differs')
    if not worker['platform_physical_fence_preserved'] or not worker['no_ce_wmi_firmware_changes'] or not net['late_initializer_owned'] or not net['other_sections_preserved']:
        raise ValueError('Network lifecycle/late initializer not qualified')
    for name,digest in {**net['source_inputs'],**worker['source_inputs']}.items():
        if sha(ROOT/name)!=digest:raise ValueError('Network input changed: '+name)
    components=report['component_objects']
    for name,proof in [('Native.o',worker),('EldenWifiNet17.late.o',net)]:
        if components[name]['sha256']!=proof['object_sha256'] or sha(Path(components[name]['path']))!=proof['object_sha256']:
            raise ValueError('Network component object differs')
    for name,component in parent['component_objects'].items():
        if name!='Native.o' and components[name]!=component:raise ValueError('Retained hardware component changed')


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
    return result


def menu(qualification):
    if qualification.get('profile')!='wifi-network-17' or not qualification.get('network_bridge') or not qualification.get('wifi_service'):
        raise ValueError('Unqualified network profile')
    from pcie_root_boot import menu as root_menu
    return root_menu(dict(qualification,profile='wifi-platform-fence')).replace(
        'Wi-Fi physical reset + USB - TEST','Wi-Fi iOS17 network bridge + USB - TEST',1)
