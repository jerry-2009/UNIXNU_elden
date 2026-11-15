"""Exact v157 root-only diagnostic profile and unchanged runtime asset contract."""
import hashlib,json,sys,tomllib
from pathlib import Path
from battery_boot import arguments
from audit_pcie_kernel_hooks import audit as audit_hooks
from charge_verification_boot import qualify_shared_assets
ROOT=Path(__file__).resolve().parents[1]
def qualify(report_path,entry_path,runtime):
    report_path=Path(report_path);r=json.loads(report_path.read_text());folder=report_path.parent
    if r.get('profile')!='pcie-root-trial' or r['changed_core_objects']!=0 or r['changed_native_objects']!=3 or r['added_native_objects']!=4:
        raise ValueError('Wrong root kernel build')
    if not all(r.get(k) is True for k in ['core_filelist_unchanged','scalar','ufs_diagnostic_removed','ufs_ah8_retained','root_worker_bound']):
        raise ValueError('Root/idle integration contract missing')
    if set(r['native_objects'])!={'ShengUfs'} or set(r['component_objects'])!={'Native.o','Root.o','Phy.o','Power.o','WcnPowerNative.o','WcnPower.o'}:
        raise ValueError('Wrong root object set')
    sys.path.insert(0,str(ROOT/'drivers/EldenUfsIdle'));import IdleSource as ah8
    sys.path.insert(0,str(ROOT/'drivers/EldenUfsQueue'));import NativeSource as q
    expected={'RootCommands.h':q.commands(),'EldenSdamRecovery.inc':ah8.recovery(),'EldenUfsCompletion.inc':q.completion(),
              'RootQueue.h':q.root_queue(),'RootTransportLayout.h':q.layout(),'EldenQueuePrelude.inc':q.prelude(),
              'EldenPinnedRootXnu.inc':q.pinned_root(),'EldenUfsPrdtAlgorithm.h':q.header(),'TransferPoll.h':ah8.transfer(),
              'EldenUfsIdle.inc':ah8.normal_runtime()}
    row=r['native_objects']['ShengUfs']
    if not row['initializers_preserved'] or hashlib.sha256(ah8.normal_source()).hexdigest()!=row['source_sha256']:
        raise ValueError('Root UFS source/initializer differs')
    if {k:hashlib.sha256(v).hexdigest() for k,v in expected.items()}!=row['generated_sources']:
        raise ValueError('Root UFS dependencies differ')
    hooks=audit_hooks(folder/'native.macho',folder/'kernel.macho')
    result=qualify_shared_assets(report_path,entry_path,runtime)
    result.update(mode=0,root_trial=True,root_hooks=hooks)
    return result

def menu(qualification):
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
