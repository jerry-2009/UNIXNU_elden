"""Exact v157 root-only diagnostic profile and unchanged runtime asset contract."""
import hashlib,json,sys,tomllib
from pathlib import Path
from battery_boot import arguments
from audit_pcie_kernel_hooks import audit as audit_hooks
from charge_verification_boot import qualify_shared_assets
ROOT=Path(__file__).resolve().parents[1]
def qualify(report_path,entry_path,runtime):
    report_path=Path(report_path);r=json.loads(report_path.read_text());folder=report_path.parent
    smmu=r.get('profile')=='smmu-domain-trial';endpoint=smmu or r.get('profile')=='pcie-endpoint-trial'
    if r.get('profile') not in ('pcie-root-trial','pcie-endpoint-trial','smmu-domain-trial') or r['changed_core_objects']!=0 or r['changed_native_objects']!=(5 if smmu else 3) or r['added_native_objects']!=(16 if smmu else 4+int(endpoint)):
        raise ValueError('Wrong root kernel build')
    if not all(r.get(k) is True for k in ['core_filelist_unchanged','scalar','ufs_diagnostic_removed','ufs_ah8_retained','root_worker_bound']):
        raise ValueError('Root/idle integration contract missing')
    components={'Native.o','Root.o','Phy.o','Power.o','WcnPowerNative.o','WcnPower.o'}
    if endpoint:components.add('Endpoint.o')
    if smmu:components|={'SmmuNativeBinding.o','EldenNvtDmaRoute.o'}
    if set(r['native_objects'])!=({'ArmCpu','ShengUfs'} if smmu else {'ShengUfs'}) or set(r['component_objects'])!=components:
        raise ValueError('Wrong root object set')
    if endpoint:
        sys.path.insert(0,str(ROOT/'drivers/EldenPcie'));from EndpointNativeSource import generated
        if smmu:
            sys.path.insert(0,str(ROOT/'drivers/EldenSmmu'));import EarlySource
            generated=EarlySource.pcie_generated
            if not r.get('smmu_domain_bound') or r.get('smmu_component_count')!=11 or not r.get('owned_sgi_guard'):raise ValueError('SMMU owner/CPU guard not qualified')
            if hashlib.sha256(EarlySource.cpu()).hexdigest()!=r['native_objects']['ArmCpu']['source_sha256']:raise ValueError('Owned SGI source differs')
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
    hooks=audit_hooks(folder/'native.macho',folder/'kernel.macho',endpoint,smmu)
    result=qualify_shared_assets(report_path,entry_path,runtime)
    result.update(mode=0,root_trial=True,root_hooks=hooks,endpoint_trial=endpoint,smmu_domain=smmu)
    return result

def menu(qualification):
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
