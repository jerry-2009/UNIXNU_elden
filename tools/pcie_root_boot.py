"""Exact v157 root-only diagnostic profile and unchanged runtime asset contract."""
import hashlib,json,sys,tomllib
from pathlib import Path
from battery_boot import arguments
from audit_pcie_kernel_hooks import audit as audit_hooks
from charge_verification_boot import qualify_shared_assets
ROOT=Path(__file__).resolve().parents[1]
def qualify(report_path,entry_path,runtime):
    report_path=Path(report_path);r=json.loads(report_path.read_text());folder=report_path.parent
    fence=r.get('profile')=='wifi-platform-fence';budget=fence or r.get('profile')=='wifi-platform-budget';platform=budget or r.get('profile')=='wifi-platform-shutdown';qmi_trace=r.get('profile')=='wifi-qmi-wire-trace';stop_trace=qmi_trace or r.get('profile')=='wifi-stop-trace';drain=platform or stop_trace or r.get('profile')=='wifi-drain-lifetime';qdss=drain or r.get('profile')=='wifi-qdss-config';control=qdss or r.get('profile')=='wifi-control-transport';trace=bool(r.get('runtime_init_trace')) if control else r.get('profile')=='wifi-init-trace';mhi=control or trace or r.get('profile')=='wifi-mhi-runtime';prefault=mhi or r.get('profile')=='smmu-prefault-memory';unique=prefault or r.get('profile')=='smmu-unique-memory';segmented=unique or r.get('profile')=='smmu-segmented-memory';detail=segmented or r.get('profile')=='smmu-memory-detail';smmu=detail or r.get('profile')=='smmu-domain-trial';endpoint=smmu or r.get('profile')=='pcie-endpoint-trial'
    if r.get('profile') not in ('wifi-platform-fence','wifi-platform-budget','wifi-platform-shutdown','wifi-qmi-wire-trace','wifi-stop-trace','wifi-drain-lifetime','wifi-qdss-config','wifi-control-transport','wifi-init-trace','wifi-mhi-runtime','pcie-root-trial','pcie-endpoint-trial','smmu-domain-trial','smmu-memory-detail','smmu-segmented-memory','smmu-unique-memory','smmu-prefault-memory') or r['changed_core_objects']!=0 or r['changed_native_objects']!=(5 if smmu else 3) or r['added_native_objects']!=(148 if fence else 147 if mhi else 16 if smmu else 4+int(endpoint)):
        raise ValueError('Wrong root kernel build')
    if fence and r.get('platform_physical_fence') is not True:raise ValueError('Physical reset fence not qualified')
    if budget and r.get('runtime_platform_budget') is not True:raise ValueError('Platform budget not qualified')
    if platform and r.get('runtime_platform_shutdown') is not True:raise ValueError('Platform shutdown not qualified')
    if qmi_trace and r.get('runtime_qmi_trace') is not True:raise ValueError('QMI trace not qualified')
    if stop_trace and r.get('runtime_stop_trace') is not True:raise ValueError('Stop trace not qualified')
    if drain and r.get('runtime_owned_cleanup') is not True:raise ValueError('Owned cleanup not qualified')
    if qdss and r.get('firmware_qdss_config') is not True:raise ValueError('QDSS config not qualified')
    if control and r.get('control_transport_bound') is not True:raise ValueError('Control transport not qualified')
    if trace and r.get('runtime_init_trace') is not True:raise ValueError('Init trace not qualified')
    if detail and r.get('memory_report_version')!=1:raise ValueError('Memory report not qualified')
    if segmented:
        sys.path.insert(0,str(ROOT/'drivers/EldenSmmu'));from SegmentSource import source as segmented_source
        if unique:
            from UniqueSource import source as segmented_source
        if prefault:
            from PrefaultSource import source as segmented_source
        if r.get('allocator_variant')!=('prefault' if prefault else 'unique' if unique else 'segmented') or r.get('allocator_source_sha256')!=hashlib.sha256(segmented_source()).hexdigest():raise ValueError('Allocator input differs')
    if not all(r.get(k) is True for k in ['core_filelist_unchanged','scalar','ufs_diagnostic_removed','ufs_ah8_retained','root_worker_bound']):
        raise ValueError('Root/idle integration contract missing')
    components={'Native.o','Root.o','Phy.o','Power.o','WcnPowerNative.o','WcnPower.o'}
    if endpoint:components.add('Endpoint.o')
    if smmu:components|={'SmmuNativeBinding.o','EldenNvtDmaRoute.o'}
    if mhi:
        if fence:components.add('PlatformFence.o')
        components|={'Config.o','Msi.o','MhiStop.o','WifiRuntimeMsiBinding.o','QmiPower.o','FirmwareCache.o'}
        if not r.get('mhi_runtime_bound') or not r.get('modem_reader_reused') or r.get('linux_runtime_objects')!=125:raise ValueError('MHI runtime not qualified')
    if set(r['native_objects'])!=({'ArmCpu','ShengUfs'} if smmu else {'ShengUfs'}) or set(r['component_objects'])!=components:
        raise ValueError('Wrong root object set')
    if endpoint:
        sys.path.insert(0,str(ROOT/'drivers/EldenPcie'));from EndpointNativeSource import generated
        if smmu:
            sys.path.insert(0,str(ROOT/'drivers/EldenSmmu'));import EarlySource
            generated=EarlySource.pcie_generated
            if not r.get('smmu_domain_bound') or r.get('smmu_component_count')!=(12 if mhi else 11) or not r.get('owned_sgi_guard'):raise ValueError('SMMU owner/CPU guard not qualified')
            if hashlib.sha256(EarlySource.cpu()).hexdigest()!=r['native_objects']['ArmCpu']['source_sha256']:raise ValueError('Owned SGI source differs')
        if mhi:
            from MhiRuntimeSource import generated
        if control:
            from ControlNativeSource import generated
        if stop_trace:
            from StopTraceSource import generated
        if qmi_trace:
            from QmiTraceSource import generated
        if platform:
            from PlatformShutdownSource import generated
        if fence:
            from PlatformFenceSource import generated
        if not r.get('endpoint_worker_bound') or r['endpoint_generated_sources']!={n:hashlib.sha256(b).hexdigest() for n,b in generated().items()}:
            raise ValueError('Endpoint worker source/qualification differs')
    sys.path.insert(0,str(ROOT/'drivers/EldenUfsIdle'));import IdleSource as ah8
    sys.path.insert(0,str(ROOT/'drivers/EldenUfsQueue'));import NativeSource as q
    expected={'RootCommands.h':q.commands(),'EldenSdamRecovery.inc':ah8.recovery(),'EldenUfsCompletion.inc':q.completion(),
              'RootQueue.h':q.root_queue(),'RootTransportLayout.h':q.layout(),'EldenQueuePrelude.inc':q.prelude(),
              'EldenPinnedRootXnu.inc':q.pinned_root(),'EldenUfsPrdtAlgorithm.h':q.header(),'TransferPoll.h':ah8.transfer(),
              'EldenUfsIdle.inc':ah8.normal_runtime()}
    row=r['native_objects']['ShengUfs']
    ufs_source=ah8.normal_source
    if smmu:
        expected['EldenSdamRecovery.inc']=EarlySource.recovery();ufs_source=EarlySource.ufs
    if not row['initializers_preserved'] or hashlib.sha256(ufs_source()).hexdigest()!=row['source_sha256']:
        raise ValueError('Root UFS source/initializer differs')
    if {k:hashlib.sha256(v).hexdigest() for k,v in expected.items()}!=row['generated_sources']:
        raise ValueError('Root UFS dependencies differ')
    hooks=audit_hooks(folder/'native.macho',folder/'kernel.macho',endpoint,smmu,mhi,control,drain,platform,budget,fence)
    result=qualify_shared_assets(report_path,entry_path,runtime)
    result.update(mode=0,root_trial=True,root_hooks=hooks,endpoint_trial=endpoint,smmu_domain=smmu,memory_detail=detail,segmented_memory=segmented,unique_memory=unique,prefault_memory=prefault,mhi_runtime=mhi,runtime_init_trace=trace,control_transport_bound=control,firmware_qdss_config=qdss,runtime_owned_cleanup=drain,runtime_stop_trace=stop_trace,runtime_qmi_trace=qmi_trace,runtime_platform_shutdown=platform,runtime_platform_budget=budget,platform_physical_fence=fence)
    return result

def menu(qualification):
    if qualification.get('profile')=='wifi-platform-fence':
        if qualification.get('platform_physical_fence') is not True:raise ValueError('Explicit physical fence qualification required')
        return menu(dict(qualification,profile='wifi-platform-budget')).replace('Wi-Fi bounded reset + USB - TEST','Wi-Fi physical reset + USB - TEST',1)
    if qualification.get('profile')=='wifi-platform-budget':
        if qualification.get('runtime_platform_budget') is not True:raise ValueError('Explicit platform budget qualification required')
        return menu(dict(qualification,profile='wifi-platform-shutdown')).replace('Wi-Fi platform reset + USB - TEST','Wi-Fi bounded reset + USB - TEST',1)
    if qualification.get('profile')=='wifi-platform-shutdown':
        if qualification.get('runtime_platform_shutdown') is not True:raise ValueError('Explicit platform shutdown qualification required')
        return menu(dict(qualification,profile='wifi-drain-lifetime')).replace('Wi-Fi shutdown + USB - TEST','Wi-Fi platform reset + USB - TEST',1)
    if qualification.get('profile')=='wifi-qmi-wire-trace':
        if qualification.get('runtime_qmi_trace') is not True:raise ValueError('Explicit QMI trace qualification required')
        return menu(dict(qualification,profile='wifi-stop-trace')).replace('Wi-Fi stop trace + USB - TEST','Wi-Fi QMI shutdown + USB - TEST',1)
    if qualification.get('profile')=='wifi-stop-trace':
        if qualification.get('runtime_stop_trace') is not True:raise ValueError('Explicit stop trace qualification required')
        return menu(dict(qualification,profile='wifi-drain-lifetime')).replace('Wi-Fi shutdown + USB - TEST','Wi-Fi stop trace + USB - TEST',1)
    if qualification.get('profile')=='wifi-drain-lifetime':
        if qualification.get('runtime_owned_cleanup') is not True:raise ValueError('Explicit owned cleanup qualification required')
        return menu(dict(qualification,profile='wifi-qdss-config')).replace('Wi-Fi firmware + USB - TEST','Wi-Fi shutdown + USB - TEST',1)
    if qualification.get('profile')=='wifi-qdss-config':
        if qualification.get('firmware_qdss_config') is not True:raise ValueError('Explicit QDSS config qualification required')
        return menu(dict(qualification,profile='wifi-control-transport')).replace('Wi-Fi control + USB - TEST','Wi-Fi firmware + USB - TEST',1)
    if qualification.get('profile')=='wifi-control-transport':
        if qualification.get('control_transport_bound') is not True:raise ValueError('Explicit control transport qualification required')
        return menu(dict(qualification,profile='wifi-mhi-runtime')).replace('Wi-Fi MHI + USB - TEST','Wi-Fi control + USB - TEST',1)
    if qualification.get('profile')=='wifi-init-trace':
        if qualification.get('runtime_init_trace') is not True:raise ValueError('Explicit init trace qualification required')
        return menu(dict(qualification,profile='wifi-mhi-runtime')).replace('Wi-Fi MHI + USB - TEST','Wi-Fi initialization + USB - TEST',1)
    if qualification.get('profile')=='wifi-mhi-runtime':
        if qualification.get('mhi_runtime') is not True:raise ValueError('Explicit MHI runtime qualification required')
        base=menu(dict(qualification,profile='smmu-prefault-memory'));old=tomllib.loads(base);args=old['entry'][0]['args'];value=args+' ewt'
        if len(value.replace('@SESSION@','0'*16).encode())>1023:raise ValueError('MHI menu exceeds parser contract')
        return base.replace('args = "'+args+'"','args = "'+value+'"',1).replace('Wi-Fi DMA setup + USB - TEST','Wi-Fi MHI + USB - TEST',1)
    if qualification.get('profile')=='smmu-prefault-memory':
        if qualification.get('prefault_memory') is not True:raise ValueError('Explicit prefault mapping required')
        return menu(dict(qualification,profile='smmu-unique-memory')).replace('Wi-Fi NC memory + USB - TEST','Wi-Fi DMA setup + USB - TEST',1)
    if qualification.get('profile')=='smmu-unique-memory':
        if qualification.get('unique_memory') is not True:raise ValueError('Explicit unique mapping required')
        return menu(dict(qualification,profile='smmu-segmented-memory')).replace('Wi-Fi mapped memory + USB - TEST','Wi-Fi NC memory + USB - TEST',1)
    if qualification.get('profile')=='smmu-segmented-memory':
        if qualification.get('segmented_memory') is not True:raise ValueError('Explicit segmented allocator required')
        return menu(dict(qualification,profile='smmu-memory-detail')).replace('Wi-Fi DMA memory details - TEST','Wi-Fi mapped memory + USB - TEST',1)
    if qualification.get('profile')=='smmu-memory-detail':
        if qualification.get('memory_detail') is not True:raise ValueError('Explicit memory detail required')
        return menu(dict(qualification,profile='smmu-domain-trial')).replace('Wi-Fi DMA mapping + USB - TEST','Wi-Fi DMA memory details - TEST',1)
    if qualification.get('profile')=='smmu-domain-trial':
        if qualification.get('smmu_domain') is not True:raise ValueError('Explicit qualified SMMU intent required')
        base=menu(dict(qualification,profile='pcie-endpoint-trial'));old=tomllib.loads(base);args=old['entry'][0]['args'];value=args+' esm'
        if len(value.replace('@SESSION@','0'*16).encode())>1023:raise ValueError('SMMU menu exceeds parser contract')
        return base.replace('args = "'+args+'"','args = "'+value+'"',1).replace('Wi-Fi chip identity + USB - TEST','Wi-Fi DMA mapping + USB - TEST',1)
    if qualification.get('profile')=='pcie-endpoint-trial':
        if qualification.get('endpoint_trial') is not True:raise ValueError('Explicit qualified endpoint intent required')
        base=menu(dict(qualification,profile='pcie-root-trial'));old=tomllib.loads(base);args=old['entry'][0]['args']
        value=args+' epe'
        if len(value.replace('@SESSION@','0'*16).encode())>1023:raise ValueError('Endpoint menu exceeds parser contract')
        return base.replace('args = "'+args+'"','args = "'+value+'"',1).replace('PCIe root + USB - TEST','Wi-Fi chip identity + USB - TEST',1)
    if qualification.get('profile')!='pcie-root-trial' or qualification.get('mode')!=0 or qualification.get('root_trial') is not True:
        raise ValueError('Explicit qualified root-only intent required')
    import bt_runtime_boot
    base=bt_runtime_boot.menu({'profile':'ufs-idle-trial'});old=tomllib.loads(base)
    first=old['entry'][0];args=arguments(first['args']);tokens=first['args'].split()
    if args.get('elden-wcn-power')!='4' or args.get('ecp')!='2':raise ValueError('Unexpected baseline observer/radio mode')
    # The first root trial omits already-accepted CPU observation and BT bringup;
    # power/thermal/watchdog/USB/recovery/SSV protections are retained.
    removed=['ecp','elden-wcn-power','elden-frame-preview','elden-userfault-log']
    tokens=[t for t in tokens if t.partition('=')[0] not in removed]
    # Native defaults are BT0 and PCIeGen3; no need to consume buffer space.
    # Frame previews and user-fault tracing are unrelated to this root-only run.
    tokens+=['elden-pcie-root=1','elden-wlan-power=1','elden-pcie-full-on=1']
    # PE_parse_boot_argn numeric-one equivalence is already qualified by v96.
    tokens=[t[:-2] if t.endswith('=1') else t for t in tokens]
    expected=dict(args)
    for key in removed:expected.pop(key)
    expected.update({'elden-pcie-root':'1','elden-wlan-power':'1','elden-pcie-full-on':'1'})
    value=' '.join(tokens)
    if arguments(value)!=expected or len(value.replace('@SESSION@','0'*16).encode())>1023:raise ValueError('Root menu exceeds parser contract')
    text=base.replace('args = "'+first['args']+'"','args = "'+value+'"',1).replace('title = "'+first['title']+'"','title = "PCIe root + USB - TEST"',1)
    result=tomllib.loads(text)
    if result['entry'][1:]!=old['entry'][1:] or result['boot']!=old['boot']:raise ValueError('Root fallback/countdown changed')
    return text
