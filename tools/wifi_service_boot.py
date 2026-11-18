"""Explicit real-supplicant profile; preserve all v173 recovery/power contracts."""
import hashlib,importlib.util,json,plistlib,struct,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PARENT='f0771691887fced6a21ae6357b659560414bcbeacee2540a9a2896c89339a5d0'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())

def qualify_runtime_snapshot(snap,native,base_binding,profile):
    window=profile=='wifi-pci-window-trace';srng=profile in ('wifi-srng-trace','wifi-pci-window-trace');credit=profile in ('wifi-credit-trace','wifi-srng-trace','wifi-pci-window-trace')
    if profile not in ('wifi-wmi-snapshot','wifi-credit-trace','wifi-srng-trace','wifi-pci-window-trace'):raise ValueError('Wrong snapshot profile')
    if bool(snap.get('credit_trace'))!=credit or bool(native.get('credit_trace'))!=credit:raise ValueError('Wrong credit trace variant')
    if not snap.get('append_only_observer') or snap.get('rebuilt_units')!=(6 if window else 5 if srng else 4 if credit else 1) or snap.get('retained_units')!=(119 if window else 120 if srng else 121 if credit else 124) or snap.get('base_binding_sha256')!=base_binding:raise ValueError('Wrong runtime snapshot boundary')
    if credit and (not snap.get('reversible_counter_insertions') or not snap.get('inherited_irq_observer') or snap.get('compiled_this_step')!=(3 if window else 2 if srng else 3)):raise ValueError('Wrong credit trace boundary')
    if bool(snap.get('srng_trace'))!=srng or bool(native.get('srng_trace'))!=srng:raise ValueError('Wrong SRNG trace variant')
    if srng and (not snap.get('reversible_srng_insertions') or snap.get('producer_credit_timeout_changes') is not False):raise ValueError('Wrong SRNG observer boundary')
    if bool(snap.get('pci_window_trace'))!=window or bool(native.get('pci_window_trace'))!=window:raise ValueError('Wrong PCI window trace variant')
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def trust_append(original,digests):
    sys.path.insert(0,str(ROOT/'tools/legacy-workbench'));from icon_cpu_trust import parts
    values=parts(original);digests=sorted(bytes.fromhex(h) for h in digests)
    if len(digests)!=2 or len(set(digests))!=2 or any(len(h)!=20 for h in digests):raise ValueError('Expected two new SHA256 CDHashes')
    if any(h==v[i:i+20] for h in digests for v in values for i in range(24,len(v),24)):raise ValueError('Duplicate service trust')
    module=struct.pack('<I16sI',2,hashlib.sha256(original+b''.join(digests)).digest()[:16],2)+b''.join(h+bytes([2,0,0,0]) for h in digests)
    values=values+[module];at=4*(len(values)+1);offsets=[]
    for value in values:offsets.append(at);at+=len(value)
    result=struct.pack('<I',len(values))+struct.pack('<'+'I'*len(offsets),*offsets)+b''.join(values)
    if parts(result)[:-1]!=parts(original):raise ValueError('Original trust modules changed')
    return result

def qualify_assets(report,runtime,native,base_trust_sha):
    fixed=read(ROOT/'profiles'/report['profile']/'assets-contract.json');actual=read(runtime/'wifi-service-assets.json')
    for key,value in fixed.items():
        if actual.get(key)!=value:raise ValueError('Service asset contract differs: '+key)
    if actual!=report['service_assets'] or actual!=report['core']['assets']:raise ValueError('Service/core assets differ')
    if base_trust_sha!=actual['input_trust_sha256']:raise ValueError('Service trust parent differs')
    for name,key in [('launchd.plist','cache_sha256'),('launchd.plist.sig','signature_sha256'),
        ('EldenWifiServiceAssets.h','header_sha256'),('unixnu-wpa_supplicant','helper_sha256'),('wpa_supplicant.conf','config_sha256'),('runtime.trustcache','trust_sha256')]:
        if sha(runtime/name)!=actual[key]:raise ValueError('Service asset changed: '+name)
        if name in ['launchd.plist','launchd.plist.sig','unixnu-wpa_supplicant'] and native.count((runtime/name).read_bytes())!=1:raise ValueError('Service blob must be embedded once: '+name)
    before=plistlib.loads((runtime/'base-launchd.plist').read_bytes());after=plistlib.loads((runtime/'launchd.plist').read_bytes())
    key='/System/Library/LaunchDaemons/org.unixnu.wifi.supplicant.plist'
    if len(before['LaunchDaemons'])!=561 or len(after['LaunchDaemons'])!=562 or after['LaunchDaemons'].pop(key)!=actual['job'] or after!=before:
        raise ValueError('Original jobs/top-level cache changed')
    digests=[actual['helper_cdhash'],actual['cache_cdhash']]
    if trust_append((runtime/'base-runtime.trustcache').read_bytes(),digests)!=(runtime/'runtime.trustcache').read_bytes():raise ValueError('Service trust reconstruction differs')
    return {'trust_sha256':actual['trust_sha256'],'base_trust_sha256':base_trust_sha,'wifi_service_cdhashes':digests,'wifi_service':True}

def qualify(report_path,entry_path,runtime):
    from charge_verification_boot import qualify_shared_assets
    from audit_pcie_kernel_hooks import audit
    r=read(Path(report_path));folder=Path(report_path).parent;base=r['base_report']
    if r['profile'] not in ['wifi-service','wifi-service-owner','wifi-service-control-trace','wifi-service-scan','wifi-wmi-snapshot','wifi-credit-trace','wifi-srng-trace','wifi-pci-window-trace'] or r['parent_kernel_sha256']!=PARENT or base['kernel_sha256']!=PARENT:raise ValueError('Wrong service parent')
    if bool(r['core'].get('owner_launch_required'))!=(r['profile']!='wifi-service'):raise ValueError('Wrong service launch rule')
    if r['profile']!='wifi-service':
        expected=read(ROOT/'profiles/wifi-service-owner/owner-contract.json')
        if r['core']['owner_common_sha256']!=expected['common_sha256'] or sha(ROOT/'drivers/EldenWifi/OwnerLaunchSource.py')!=expected['generator_sha256']:raise ValueError('Owner rule differs')
    srng=r['profile'] in ('wifi-srng-trace','wifi-pci-window-trace');credit=r['profile'] in ['wifi-credit-trace','wifi-srng-trace','wifi-pci-window-trace'];wmi=r['profile'] in ['wifi-wmi-snapshot','wifi-credit-trace','wifi-srng-trace','wifi-pci-window-trace']
    if (r['changed_core_objects'],r['changed_native_objects'],r['added_native_objects'],r['core_filelist_unchanged'])!=(1,2 if wmi else 1,0,False):raise ValueError('Wrong service object delta')
    if bool(r['service_native'].get('wmi_snapshot'))!=wmi or bool(r.get('runtime_snapshot'))!=wmi:raise ValueError('Wrong WMI snapshot variant')
    if wmi:
        snap=r['runtime_snapshot']
        qualify_runtime_snapshot(snap,r['service_native'],base['component_objects']['WifiRuntimeMsiBinding.o']['sha256'],r['profile'])
    for key in ['platform_physical_fence','runtime_platform_budget','runtime_platform_shutdown','runtime_owned_cleanup',
        'firmware_qdss_config','control_transport_bound','mhi_runtime_bound','ufs_ah8_retained','ufs_diagnostic_removed','root_worker_bound','smmu_domain_bound','owned_sgi_guard','scalar']:
        if r.get(key) is not True or base.get(key) is not True:raise ValueError('Prior protection missing: '+key)
    if r['native_objects']!=base['native_objects'] or r['linux_runtime_objects']!=125:raise ValueError('Unrelated native object changed')
    for name,row in r['component_objects'].items():
        if name not in ({'Native.o','WifiRuntimeMsiBinding.o'} if wmi else {'Native.o'}) and row!=base['component_objects'].get(name):raise ValueError('Unrelated component changed')
    if set(r['component_objects'])!=set(base['component_objects']):raise ValueError('Component set changed')
    if set(r['service_archive_members'])!=set(r['base_archive_members']):raise ValueError('Archive members changed')
    for name,h in r['service_archive_members'].items():
        if name not in ({'Native.o','WifiRuntimeMsiBinding.o'} if wmi else {'Native.o'}) and h!=r['base_archive_members'][name]:raise ValueError('Unrelated archive member changed')
    core=module('service_core_source',ROOT/'drivers/EldenWifi/ServiceRuntimeSource.py')
    if hashlib.sha256(core.source()).hexdigest()!=r['core']['runtime_sha256']:raise ValueError('Service runtime source differs')
    generator=module('service_native_source',ROOT/'drivers/EldenWifi/ServiceNativeSource.py')
    trace=r['profile'] in ['wifi-service-control-trace','wifi-service-scan','wifi-wmi-snapshot','wifi-credit-trace','wifi-srng-trace','wifi-pci-window-trace']
    if bool(r['service_native'].get('control_trace'))!=trace:raise ValueError('Wrong control trace variant')
    if trace:generator=module('service_trace_source',ROOT/'drivers/EldenWifi/ServiceControlTraceSource.py')
    scan=r['profile'] in ['wifi-service-scan','wifi-wmi-snapshot','wifi-credit-trace','wifi-srng-trace','wifi-pci-window-trace']
    if bool(r['service_native'].get('service_scan'))!=scan:raise ValueError('Wrong session scan variant')
    if scan:generator=module('service_scan_source',ROOT/'drivers/EldenWifi/ServiceScanSource.py')
    if wmi:generator=module('service_wmi_source',ROOT/'drivers/EldenWifi/ServiceWmiSource.py')
    if credit:generator=module('service_credit_source',ROOT/'drivers/EldenWifi/ServiceCreditSource.py')
    if {n:hashlib.sha256(b).hexdigest() for n,b in generator.generated().items()}!=r['service_native']['generated_sources']:raise ValueError('Service native source differs')
    hooks=audit(folder/'native.macho',folder/'kernel.macho',True,True,True,True,True,True,True,True)
    q=qualify_shared_assets(report_path,entry_path,runtime,wifi_service=True)
    q.update(mode=0,root_trial=True,root_hooks=hooks,endpoint_trial=True,smmu_domain=True,memory_detail=True,segmented_memory=True,
        unique_memory=True,prefault_memory=True,mhi_runtime=True,control_transport_bound=True,firmware_qdss_config=True,
        runtime_owned_cleanup=True,runtime_platform_shutdown=True,runtime_platform_budget=True,platform_physical_fence=True)
    return q

def menu(q):
    from pcie_root_boot import menu as root_menu
    if not q.get('wifi_service'):raise ValueError('Service assets not qualified')
    title='Wi-Fi PCI window read + USB - TEST' if q['profile']=='wifi-pci-window-trace' else 'Wi-Fi CE3 hardware HP + USB - TEST' if q['profile']=='wifi-srng-trace' else 'Wi-Fi credit flow + USB - TEST' if q['profile']=='wifi-credit-trace' else 'Wi-Fi WMI delivery + USB - TEST' if q['profile']=='wifi-wmi-snapshot' else 'Wi-Fi live scan + USB - TEST' if q['profile']=='wifi-service-scan' else 'Wi-Fi control trace + USB - TEST' if q['profile']=='wifi-service-control-trace' else 'Wi-Fi signed service + USB - TEST' if q['profile']=='wifi-service-owner' else 'Wi-Fi service + USB - TEST'
    return root_menu(dict(q,profile='wifi-platform-fence')).replace('Wi-Fi physical reset + USB - TEST',title,1)

def augment_trust(original,q):
    from bt_runtime_boot import augment_trust as augment_base
    base=augment_base(original,dict(q,profile='ufs-idle-trial',trust_sha256=q['base_trust_sha256']))
    result=trust_append(base,q['wifi_service_cdhashes'])
    if hashlib.sha256(result).hexdigest()!=q['trust_sha256']:raise ValueError('Service final trust differs')
    return result
