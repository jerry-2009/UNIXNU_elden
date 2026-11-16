"""Explicit v99/v101 runtime boot contracts; no device operations."""
from pathlib import Path
import copy,hashlib,json,tomllib,struct,sys
from fbwc_boot import template as framebuffer_template
from battery_boot import template as battery_template,arguments
from audit_entry_relocation import entry as inspect_entry
ROOT=Path(__file__).resolve().parents[1]
FIXUP=b'bluetoothd,ddd20,a0050034,1f2003d5\0'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def qualify(report_path,entry_path,runtime):
    if not report_path or not entry_path or not runtime:raise ValueError('Complete v99 build, entry and runtime inputs required')
    report=json.loads(Path(report_path).read_text());entry=json.loads(Path(entry_path).read_text());runtime=Path(runtime)
    name=report.get('profile')
    if name in ('wifi-control-transport','wifi-init-trace','wifi-mhi-runtime','pcie-root-trial','pcie-endpoint-trial','smmu-domain-trial','smmu-memory-detail','smmu-segmented-memory','smmu-unique-memory','smmu-prefault-memory'):
        from pcie_root_boot import qualify as qualify_pcie
        return qualify_pcie(report_path,entry_path,runtime)
    if name in ('charge-verification','charge-window-handoff','spmi-translation-survey','backlight-service','backlight-power-trial','pd-power-trial','cpu-power-observation','cpu-governor','storage-medium','early-storage-guard','early-storage-stall','ufs-wait-trial','ufs-queue-trial','ufs-idle-trial'):
        from charge_verification_boot import qualify as qualify_charge
        return qualify_charge(report_path,entry_path,runtime)
    if name=='bt-address17':
        from bt_address17_boot import qualify as qualify_address
        return qualify_address(report_path,entry_path,runtime)
    if name=='bt-discovery17':
        from bt_discovery17_boot import qualify as qualify_discovery
        return qualify_discovery(report_path,entry_path,runtime)
    if name=='bt-scan-roles17':
        from bt_scan_roles17_boot import qualify as qualify_scan_roles
        return qualify_scan_roles(report_path,entry_path,runtime)
    if name=='bt-scan-observe17':
        from bt_scan_observe17_boot import qualify as qualify_scan_observe
        return qualify_scan_observe(report_path,entry_path,runtime)
    if name=='bt-scan-ready17':
        from bt_scan_ready17_boot import qualify as qualify_scan_ready
        return qualify_scan_ready(report_path,entry_path,runtime)
    if name=='bt-scan17':
        from bt_scan17_boot import qualify as qualify_scan
        return qualify_scan(report_path,entry_path,runtime)
    if name=='bt-complete17':
        from bt_complete17_boot import qualify as qualify_complete
        return qualify_complete(report_path,entry_path,runtime)
    if name=='bt-optional17':
        from bt_optional17_boot import qualify as qualify_optional
        return qualify_optional(report_path,entry_path,runtime)
    if name=='bt-process-lifetime':
        from bt_process_lifetime_boot import qualify as qualify_process
        return qualify_process(report_path,entry_path,runtime)
    if name=='bt-helper-trace':
        from bt_helper_trace_boot import qualify as qualify_helper
        return qualify_helper(report_path,entry_path,runtime)
    if name=='bt-registry':
        from bt_registry_boot import qualify as qualify_registry
        return qualify_registry(report_path,entry_path,runtime)
    if name=='bluetool-lifecycle':
        from bluetool_lifecycle_boot import qualify as qualify_lifecycle
        return qualify_lifecycle(report_path,entry_path,runtime)
    if name=='bt-syscall-trace':
        from bt_syscall_trace_boot import qualify as qualify_syscalls
        return qualify_syscalls(report_path,entry_path,runtime)
    if name=='bt-transport-trace':
        from bt_transport_trace_boot import qualify as qualify_trace
        return qualify_trace(report_path,entry_path,runtime)
    if name=='bluetool-owner-launch':
        from bluetool_launch_boot import qualify as qualify_owner
        return qualify_owner(report_path,entry_path,runtime)
    if name=='elden-software-keystore':
        from elden_keystore_boot import qualify as qualify_keystore
        return qualify_keystore(report_path,entry_path,runtime)
    if name=='bt-exit-stack':
        from bt_exit_stack_boot import qualify as qualify_exit_stack
        return qualify_exit_stack(report_path,entry_path,runtime)
    if report.get('native_contract_matches') is True:
        from current_boot import qualify as qualify_current
        return qualify_current(report_path,entry_path,runtime)
    if name=='v112-uart-route':raise ValueError('Withdrawn v112 has an incorrect GIC MMIO base; use v113 or later')
    if name not in ('v99-bt-runtime','v101-bt-clock','v102-bt-wake','v103-bt-version','v110-bt-fifo','v111-spmi-gate','v112-uart-route','v113-uart-gic','v114-hci-length','v115-ibs-wake','v116-hci-reset','v117-hci-debug','v118-native17','v119-bt-exit','v120-bt-xpc','v121-bt-stderr'):raise ValueError('Unsupported Bluetooth runtime profile')
    profile=ROOT/'profiles'/name/'plan.json';plan=json.loads(profile.read_text())
    if name in ('v111-spmi-gate','v112-uart-route','v113-uart-gic','v114-hci-length','v115-ibs-wake','v116-hci-reset','v117-hci-debug','v118-native17','v119-bt-exit','v120-bt-xpc','v121-bt-stderr'):
        audit=json.loads((Path(report_path).parent/'kernel-audit.json').read_text())
        filelist_ok=audit.get('only_two_declared_core_replacements') is True and audit['core_filelist_equal'] is False if name in ('v118-native17','v119-bt-exit','v120-bt-xpc','v121-bt-stderr') else audit['core_filelist_equal']
        if name=='v121-bt-stderr':filelist_ok=audit.get('only_declared_stderr_replacement') is True and audit['core_filelist_equal'] is False
        core_ok=audit['accepted_static'] and audit['one_gate_state'] and filelist_ok and audit['kernel_sha256']==report['kernel_sha256'] and audit['profile_sha256']==sha(profile)
    else:core_ok=report.get('recompiled_core_objects')==2
    if report['profile_sha256']!=sha(profile) or not core_ok or report['original_apple_executables_hashed']!=30:
        raise ValueError('Unqualified v99 core build')
    if entry['source_sha256']!=report['kernel_sha256']:raise ValueError('Entry is not the v99 kernel')
    source=Path(report_path).parent/'kernel.macho';layout=json.loads((Path(report_path).parent/'entry-layout.json').read_text())
    if sha(source)!=report['kernel_sha256'] or layout['source_kernel_sha256']!=sha(source) or not layout['assembly_sections_equal'] or not layout['same_object_in_both_filelists']:
        raise ValueError('Missing qualified entry-layout proof')
    start,target,word=inspect_entry(source.read_bytes())
    contract=json.loads((profile.parent/'entry-assembly.json').read_text())
    if target-start!=contract['target_delta'] or layout['entry_word']!=word or layout['return_target']!=hex(target) or entry['entry']['entry_target']!=target:
        raise ValueError('Entry return does not match the unchanged startup assembly')
    if sha(runtime/'BlueTool')!=plan['runtime_helper_sha256'] or sha(runtime/'runtime.trustcache')!=plan['runtime_trust_sha256'] or sha(runtime/'EldenBtRuntimePayload.h')!=plan['runtime_header_sha256']:
        raise ValueError('Runtime inputs differ from compiled profile')
    result={'profile':name,'profile_sha256':sha(profile),'trust_sha256':plan['runtime_trust_sha256'],
            'helper_sha256':plan['runtime_helper_sha256'],'entry_return_target':hex(target),'entry_assembly_sha256':layout['assembly_sha256'],'mode':4,'hardware_tested':False}
    if name in ('v118-native17','v119-bt-exit','v120-bt-xpc','v121-bt-stderr'):
        rr=json.loads((runtime/'report.json').read_text());table=bytes.fromhex(rr['text_fixups_after_hex'])
        header='#include <stdint.h>\nstatic const uint8_t elden_bt_runtime_payload[]={\n'+','.join(str(v) for v in (runtime/'BlueTool').read_bytes())+'\n};\n'
        header+='static const uint8_t elden_bt_runtime_fixups[]={'+','.join(str(v) for v in table)+'};\n'
        if hashlib.sha256(header.encode()).hexdigest()!=plan['runtime_header_sha256'] or sha(runtime/'EldenBtTextGuard.h')!=plan['guard_sha256']:
            raise ValueError('Native17 table/guard differs from compiled identity')
        result['text_fixups_hex']=table.hex()
    return result
def pd_gui(qualification):
    """Select the existing GUI brightness branch after full PD-kernel qualification."""
    if not qualification or qualification.get('profile')!='pd-power-trial' or qualification.get('table_count')!=59 or qualification.get('key_state')!=2:
        raise ValueError('PD GUI requires the qualified PD integration kernel')
    return dict(qualification,profile='pd-gui',native_profile='pd-power-trial',menu_only_gui=True)

def early_stall(qualification):
    if not qualification or qualification.get('profile')!='early-storage-guard':raise ValueError('Stall requires qualified early-guard kernel')
    return dict(qualification,profile='early-storage-stall',native_profile='early-storage-guard',controlled_stall=True)

def menu(qualification=None):
    if qualification and qualification.get('profile') in ('wifi-control-transport','wifi-init-trace','wifi-mhi-runtime','pcie-root-trial','pcie-endpoint-trial','smmu-domain-trial','smmu-memory-detail','smmu-segmented-memory','smmu-unique-memory','smmu-prefault-memory'):
        from pcie_root_boot import menu as pcie_menu
        return pcie_menu(qualification)
    before=battery_template(framebuffer_template(True));config=tomllib.loads(before)
    first=config['entry'][0];original=first['args'];tokens=original.split()
    # This trial uses real input and Bluetooth logs, not the one-shot software
    # Settings replay or its UIKit trace. Keep every physical input/charge guard.
    removed={'elden-ui-replay','elden-ui'}
    result=[t for t in tokens if t.partition('=')[0] not in removed]+['elden-wcn-power=4']
    expected=arguments(original)
    for key in removed:expected.pop(key)
    expected['elden-wcn-power']='4'
    if qualification and qualification.get('profile') in ('elden-software-keystore','bluetool-owner-launch','bt-transport-trace','bt-syscall-trace','bluetool-lifecycle','bt-registry','bt-helper-trace','bt-process-lifetime','bt-optional17','bt-complete17','bt-scan17','bt-scan-ready17','bt-scan-observe17','bt-scan-roles17','bt-discovery17','bt-address17','charge-verification','charge-window-handoff','spmi-translation-survey','backlight-service','backlight-power-trial','pd-power-trial','pd-gui','cpu-power-observation','cpu-governor','storage-medium','early-storage-guard','early-storage-stall','ufs-wait-trial','ufs-queue-trial','ufs-idle-trial'):
        slots=[i for i,t in enumerate(result) if t.partition('=')[0]=='elden-key-state']
        if len(slots)!=1 or expected.get('elden-key-state')!='1':raise ValueError('Expected old state mode1')
        result[slots[0]]='elden-key-state=2'
        expected['elden-key-state']='2'
    if qualification and qualification.get('profile') in ('backlight-service','backlight-power-trial','pd-power-trial','pd-gui','cpu-power-observation','cpu-governor','storage-medium','early-storage-guard','early-storage-stall','ufs-wait-trial','ufs-queue-trial','ufs-idle-trial'):
        if 'elden-backlight' in expected or 'ebl' in expected:raise ValueError('Backlight already selected')
        mode='5' if qualification['profile'] in ('backlight-power-trial','pd-power-trial') else '6'
        result.append('ebl='+mode);expected['ebl']=mode
    if qualification and qualification.get('profile') in ('pd-power-trial','pd-gui','cpu-power-observation','cpu-governor','storage-medium','early-storage-guard','early-storage-stall','ufs-wait-trial','ufs-queue-trial','ufs-idle-trial'):
        for key,old_value,new_value in [('elden-thermal','2','3'),('smp-hold','240','600')]:
            if expected.get(key)!=old_value:raise ValueError('Unexpected PD trial baseline '+key)
            slots=[i for i,t in enumerate(result) if t.partition('=')[0]==key]
            if len(slots)!=1:raise ValueError('Ambiguous PD trial option')
            result[slots[0]]=key+'='+new_value;expected[key]=new_value
        for key in ('elden-battery','elden-battery-profile'):
            if result.count(key+'=1')!=1:raise ValueError('Unexpected battery option')
            result[result.index(key+'=1')]=key
        if 'epd' in expected or 'elden-pd-bootstrap' in expected:raise ValueError('PD already selected')
        result.append('epd=2');expected['epd']='2'
    if qualification and qualification.get('profile') in ('cpu-power-observation','cpu-governor','storage-medium','early-storage-guard','early-storage-stall','ufs-wait-trial','ufs-queue-trial','ufs-idle-trial'):
        # PE_parse_boot_argn treats bare numeric-one flags as 1, and 334=0x14e.
        # Preserve every option and its numeric value within the 1024-byte ABI.
        for key in ('security-mode-change-enable','amfi_get_out_of_my_way'):
            if result.count(key+'=1')!=1:raise ValueError('Unexpected numeric-one option')
            result[result.index(key+'=1')]=key
        if result.count('debug=0x14e')!=1:raise ValueError('Unexpected debug mask')
        result[result.index('debug=0x14e')]='debug=334';expected['debug']='334'
        mode='3' if qualification['profile']=='cpu-governor' else '2'
        result.append('ecp='+mode);expected['ecp']=mode
    if qualification and qualification.get('profile') in ('early-storage-guard','early-storage-stall','ufs-wait-trial','ufs-queue-trial','ufs-idle-trial'):
        if result.count('vdog=2')!=1:raise ValueError('Unexpected watchdog baseline')
        mode='4' if qualification['profile']=='early-storage-stall' else '3'
        result[result.index('vdog=2')]='vdog='+mode;expected['vdog']=mode
    text=before.replace('args = "'+original+'"','args = "'+' '.join(result)+'"',1)
    title='UFS idle power + wake - TEST' if qualification and qualification.get('profile')=='ufs-idle-trial' else 'UFS queue + DMA trial - TEST' if qualification and qualification.get('profile')=='ufs-queue-trial' else 'UFS completion read trial - TEST' if qualification and qualification.get('profile')=='ufs-wait-trial' else 'Bluetooth runtime + battery - TEST'
    text=text.replace('title = "'+first['title']+'"','title = "'+title+'"',1)
    new=tomllib.loads(text)
    if arguments(new['entry'][0]['args'])!=expected or len(new['entry'][0]['args'].replace('@SESSION@','0'*16).encode())>1023:
        raise ValueError('Bluetooth option contract or length differs')
    if new['entry'][1:]!=config['entry'][1:] or new['boot']!=config['boot']:raise ValueError('Fallback/menu behavior changed')
    return text
def adt(base,qualification=None):
    if qualification and qualification.get('profile') in ('wifi-control-transport','wifi-init-trace','wifi-mhi-runtime','pcie-root-trial','pcie-endpoint-trial','smmu-domain-trial','smmu-memory-detail','smmu-segmented-memory','smmu-unique-memory','smmu-prefault-memory'):
        qualification=dict(qualification,profile='ufs-idle-trial') # unchanged v156 ADT/runtime only
    result=copy.deepcopy(base);found=[]
    def visit(n):
        for p in n['properties']:
            if p['name']=='text-fixups':found.append(p)
        for c in n['children']:visit(c)
    visit(result['tree'])
    if len(found)!=1:raise ValueError('Expected original fixup table')
    old=bytes.fromhex(found[0]['hex'])
    if not old.endswith(b'\0') or b'bluetoothd,' in old:raise ValueError('Prior Bluetooth fixup is not allowed')
    updated=old+FIXUP
    if qualification and qualification['profile'] in ('v118-native17','v119-bt-exit','v120-bt-xpc','v121-bt-stderr','current-source','bt-exit-stack','elden-software-keystore','bluetool-owner-launch','bt-transport-trace','bt-syscall-trace','bluetool-lifecycle','bt-registry','bt-helper-trace','bt-process-lifetime','bt-optional17','bt-complete17','bt-scan17','bt-scan-ready17','bt-scan-observe17','bt-scan-roles17','bt-discovery17','bt-address17','charge-verification','charge-window-handoff','spmi-translation-survey','backlight-service','backlight-power-trial','pd-power-trial','pd-gui','cpu-power-observation','cpu-governor','storage-medium','early-storage-guard','early-storage-stall','ufs-wait-trial','ufs-queue-trial','ufs-idle-trial'):
        updated=bytes.fromhex(qualification['text_fixups_hex'])
        expected_count=59 if qualification['profile'] in ('bt-address17','charge-verification','charge-window-handoff','spmi-translation-survey','backlight-service','backlight-power-trial','pd-power-trial','pd-gui','cpu-power-observation','cpu-governor','storage-medium','early-storage-guard','early-storage-stall','ufs-wait-trial','ufs-queue-trial','ufs-idle-trial') else 55 if qualification['profile']=='bt-discovery17' else 40 if qualification['profile'] in ('bt-scan-ready17','bt-scan-observe17','bt-scan-roles17','bt-discovery17','bt-address17','charge-verification','charge-window-handoff','spmi-translation-survey','backlight-service','backlight-power-trial','pd-power-trial','pd-gui','cpu-power-observation','cpu-governor','storage-medium','early-storage-guard','early-storage-stall','ufs-wait-trial','ufs-queue-trial','ufs-idle-trial') else 38 if qualification['profile']=='bt-scan17' else 32 if qualification['profile']=='bt-complete17' else 25 if qualification['profile']=='bt-optional17' else 31 if qualification['profile']=='v120-bt-xpc' else 22
        if not updated.startswith(old+FIXUP) or len([x for x in updated.split(b'\0') if x])!=expected_count:raise ValueError('Native17 table contract differs')
    found[0]['hex']=updated.hex();result.pop('sha256',None)
    if qualification and qualification['profile'] in ('bt-registry','bt-helper-trace','bt-process-lifetime','bt-optional17','bt-complete17','bt-scan17','bt-scan-ready17','bt-scan-observe17','bt-scan-roles17','bt-discovery17','bt-address17','charge-verification','charge-window-handoff','spmi-translation-survey','backlight-service','backlight-power-trial','pd-power-trial','pd-gui','cpu-power-observation','cpu-governor','storage-medium','early-storage-guard','early-storage-stall','ufs-wait-trial','ufs-queue-trial','ufs-idle-trial'):
        from bt_registry_adt import apply as registry_adt
        result=registry_adt(result)
    return result
def augment_trust(original,qualification):
    if qualification.get('profile') in ('wifi-control-transport','wifi-init-trace','wifi-mhi-runtime','pcie-root-trial','pcie-endpoint-trial','smmu-domain-trial','smmu-memory-detail','smmu-segmented-memory','smmu-unique-memory','smmu-prefault-memory'):
        qualification=dict(qualification,profile='ufs-idle-trial') # identical qualified cache/trust assets
    if qualification.get('profile') not in ('bluetool-lifecycle','bt-registry','bt-helper-trace','bt-process-lifetime','bt-optional17','bt-complete17','bt-scan17','bt-scan-ready17','bt-scan-observe17','bt-scan-roles17','bt-discovery17','bt-address17','charge-verification','charge-window-handoff','spmi-translation-survey','backlight-service','backlight-power-trial','pd-power-trial','pd-gui','cpu-power-observation','cpu-governor','storage-medium','early-storage-guard','early-storage-stall','ufs-wait-trial','ufs-queue-trial','ufs-idle-trial'):return original
    if hashlib.sha256(original).hexdigest()!=qualification['cache_input_trust_sha256']:raise ValueError('Unexpected trust before cache')
    sys.path.insert(0,str(ROOT/'tools/legacy-workbench'))
    from icon_cpu_trust import parts
    old=parts(original);digest=bytes.fromhex(qualification['cache_cdhash'])
    if len(digest)!=20 or any(p[i:i+20]==digest for p in old for i in range(24,len(p),24)):raise ValueError('Duplicate/invalid cache hash')
    module=struct.pack('<I16sI',2,hashlib.sha256(original+digest).digest()[:16],1)+digest+bytes([2,0,0,0])
    values=old+[module];position=4*(len(values)+1);offsets=[]
    for value in values:offsets.append(position);position+=len(value)
    result=struct.pack('<I',len(values))+struct.pack('<'+'I'*len(offsets),*offsets)+b''.join(values)
    if parts(result)[:-1]!=old or hashlib.sha256(result).hexdigest()!=qualification['trust_sha256']:raise ValueError('Cache trust mismatch')
    return result
