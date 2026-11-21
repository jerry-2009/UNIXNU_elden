#!/usr/bin/env python3
"""Build the current Elden kernel/boot from a clone and declared original inputs.

macOS/Xcode is the native build host. This tool does not open a tablet. A state
journal only reuses outputs produced by completed steps in this exact run and
with the same source/configuration fingerprints; it never consumes v99 builds.
"""
from pathlib import Path
import argparse,hashlib,json,os,subprocess,sys,time
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())
def main():
    if sys.flags.optimize:raise ValueError('Assertions must remain enabled')
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--inputs',type=Path,required=True,help='JSON with original inputs/toolchains; paths relative to JSON')
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--target',choices=('kernel','boot'),default='boot')
    p.add_argument('--variant',choices=('bluetooth','gui'),default='bluetooth',help='Frozen v121 Bluetooth diagnostics or v109 8GiB GUI')
    p.add_argument('--bt-exit-stack',action='store_true',help='Bluetooth only: bounded native first-exit call-stack diagnostic')
    p.add_argument('--software-keystore',action='store_true',help='Bluetooth exit-stack candidate: software key operations on volatile Data')
    p.add_argument('--bluetool-launch',action='store_true',help='Qualify the exact owned BlueTool on its RAM overlay')
    p.add_argument('--bt-transport-trace',action='store_true',help='Bounded bootstrap sysctl and H4 callback phase logs')
    p.add_argument('--bt-syscall-trace',action='store_true',help='Bounded original-bluetoothd socket and controller-query phases')
    p.add_argument('--bluetool-lifecycle',action='store_true',help='Build and stage the signed BlueTool launchd lifecycle cache')
    p.add_argument('--bt-registry',action='store_true',help='Publish matching Bluetooth DeviceTree/platform-service properties')
    p.add_argument('--bt-helper-trace',action='store_true',help='Observe typed script/result/reply stages in the owned BlueTool')
    p.add_argument('--bt-process-lifetime',action='store_true',help='Keep H4 process references local to each callback')
    p.add_argument('--charge-verification',action='store_true',help='Require fresh charging readback and bound verification waits on the current address baseline')
    p.add_argument('--charge-window-handoff',action='store_true',help='Include verification and return from bypass to OEM automatic charging windows')
    p.add_argument('--charge-link-recovery',action='store_true',help='Independent charging pair retaining possible manual inhibit across transport loss')
    p.add_argument('--spmi-translation-survey',action='store_true',help='Include window handoff and compare SPMI page read/write translation without FIFO access')
    p.add_argument('--backlight-service',action='store_true',help='Enable the qualified native brightness service on the window-handoff baseline')
    p.add_argument('--backlight-power-trial',action='store_true',help='Bounded baseline/dim/restore power observation; separate from brightness service use')
    p.add_argument('--pd-power-trial',action='store_true',help='Require confirmed legacy PD handoff before the bounded brightness observation')
    p.add_argument('--pd-gui',action='store_true',help='Build the same PD integration kernel but select the normal GUI brightness service')
    p.add_argument('--cpu-power-observation',action='store_true',help='Read-only eight-core load/PERF observation with normal GUI and confirmed PD')
    p.add_argument('--cpu-governor',action='store_true',help='Bounded governor plus recovery hook over the CPU observation/PD baseline')
    p.add_argument('--storage-medium',action='store_true',help='UFS/RAM solid-state properties over the unchanged observation/PD baseline')
    p.add_argument('--early-storage-guard',action='store_true',help='Move qualified watchdog arming ahead of UFS while retaining later SMP admission')
    p.add_argument('--ufs-wait-trial',action='store_true',help='Guarded UFS IRQ waiting plus bounded pinned-block polling/hybrid comparison')
    p.add_argument('--ufs-queue-trial',action='store_true',help='Owned DMA multi-slot queue and QD1/8/32 comparison')
    p.add_argument('--ufs-idle-trial',action='store_true',help='Stock5000us automatic Hibern8 and qualified restore')
    p.add_argument('--data-capacity-2g',action='store_true',help='UFS idle baseline with2GiB sparse Data and the actual software KeyStore adapter')
    p.add_argument('--data-ui-replay',action='store_true',help='Explicit2GiB software UI trial without PMIC log/CPU sampling diagnostics')
    p.add_argument('--bt-address17',action='store_true',help='Wait for the actual IOKit Bluetooth address and retain discovery accounting')
    p.add_argument('--bt-discovery17',action='store_true',help='Wait for the real Bluetooth address and count native discovery delivery')
    p.add_argument('--bt-scan-roles17',action='store_true',help='Correct native17 standard/vendor scan selector roles; includes capability observation')
    p.add_argument('--bt-scan-observe17',action='store_true',help='Read native supported commands and scan flags at initialization completion')
    p.add_argument('--bt-scan-ready17',action='store_true',help='Republish supported extended scan flags after HCI completion; includes scan17')
    p.add_argument('--bt-scan17',action='store_true',help='Native17 standard extended scanning from real controller support; includes complete17')
    p.add_argument('--bt-complete17',action='store_true',help='Use real HCI support bits and the native completion result; includes optional17 callbacks')
    p.add_argument('--bt-optional17',action='store_true',help='Allow native17 initialization without three optional HCI features')
    p.add_argument('--jobs',type=int,choices=range(1,9),default=4)
    p.add_argument('--resume',action='store_true',help='Resume completed stages of this exact source/input run')
    a=p.parse_args()
    if a.bt_exit_stack and a.variant!='bluetooth':raise ValueError('--bt-exit-stack requires the Bluetooth variant')
    if a.software_keystore and not a.bt_exit_stack:raise ValueError('--software-keystore requires --bt-exit-stack')
    if a.bluetool_launch and not a.software_keystore:raise ValueError('--bluetool-launch requires --software-keystore')
    if a.bt_transport_trace and not a.bluetool_launch:raise ValueError('--bt-transport-trace requires --bluetool-launch')
    if a.bt_syscall_trace and not a.bt_transport_trace:raise ValueError('--bt-syscall-trace requires --bt-transport-trace')
    if a.bluetool_lifecycle and (not a.bt_transport_trace or a.bt_syscall_trace):raise ValueError('--bluetool-lifecycle requires transport trace without syscall trace')
    if a.bt_registry and not a.bluetool_lifecycle:raise ValueError('--bt-registry requires --bluetool-lifecycle')
    if a.bt_helper_trace and not a.bt_registry:raise ValueError('--bt-helper-trace requires --bt-registry')
    if a.bt_process_lifetime and not a.bt_helper_trace:raise ValueError('--bt-process-lifetime requires --bt-helper-trace')
    if a.bt_optional17 and not a.bt_process_lifetime:raise ValueError('--bt-optional17 requires --bt-process-lifetime')
    if a.bt_complete17 and (not a.bt_process_lifetime or a.bt_optional17):raise ValueError('--bt-complete17 requires --bt-process-lifetime without --bt-optional17')
    if a.bt_scan17 and (not a.bt_process_lifetime or a.bt_optional17 or a.bt_complete17):raise ValueError('--bt-scan17 requires --bt-process-lifetime without --bt-optional17/--bt-complete17')
    if a.bt_scan_ready17 and (not a.bt_process_lifetime or a.bt_optional17 or a.bt_complete17 or a.bt_scan17):raise ValueError('--bt-scan-ready17 requires --bt-process-lifetime without other native17 options')
    if a.bt_scan_observe17 and (not a.bt_process_lifetime or a.bt_optional17 or a.bt_complete17 or a.bt_scan17 or a.bt_scan_ready17):raise ValueError('--bt-scan-observe17 requires --bt-process-lifetime without other native17 options')
    if a.bt_scan_roles17 and (not a.bt_process_lifetime or a.bt_optional17 or a.bt_complete17 or a.bt_scan17 or a.bt_scan_ready17 or a.bt_scan_observe17):raise ValueError('--bt-scan-roles17 requires --bt-process-lifetime without other native17 options')
    if a.bt_discovery17 and (not a.bt_process_lifetime or a.bt_optional17 or a.bt_complete17 or a.bt_scan17 or a.bt_scan_ready17 or a.bt_scan_observe17 or a.bt_scan_roles17):raise ValueError('--bt-discovery17 requires --bt-process-lifetime without other native17 options')
    if a.bt_address17 and (not a.bt_process_lifetime or a.bt_optional17 or a.bt_complete17 or a.bt_scan17 or a.bt_scan_ready17 or a.bt_scan_observe17 or a.bt_scan_roles17 or a.bt_discovery17):raise ValueError('--bt-address17 requires --bt-process-lifetime without other native17 options')
    if a.data_capacity_2g and (a.variant!='bluetooth' or not a.bt_address17):raise ValueError('--data-capacity-2g requires the qualified Bluetooth/address17 chain')
    if a.data_ui_replay and not a.data_capacity_2g:raise ValueError('--data-ui-replay requires --data-capacity-2g')
    if a.data_capacity_2g:a.ufs_idle_trial=True
    if a.ufs_idle_trial:a.ufs_queue_trial=True
    if a.ufs_queue_trial:a.ufs_wait_trial=True
    if a.ufs_wait_trial:a.early_storage_guard=True
    if a.early_storage_guard:a.storage_medium=True
    if a.storage_medium and (a.cpu_governor or a.cpu_power_observation or a.pd_gui):raise ValueError('Storage medium uses its own observation/PD chain')
    if a.storage_medium:a.cpu_power_observation=True
    if a.cpu_governor and (a.cpu_power_observation or a.pd_gui):raise ValueError('Governor already includes CPU observation/GUI stages; omit their explicit options')
    if a.cpu_governor:a.cpu_power_observation=True
    if a.cpu_power_observation and a.pd_gui:raise ValueError('CPU observation already selects GUI; omit --pd-gui')
    if a.pd_gui or a.cpu_power_observation:a.pd_power_trial=True
    if a.pd_power_trial:a.backlight_power_trial=True
    if a.backlight_power_trial:a.backlight_service=True
    if a.backlight_service and a.spmi_translation_survey:raise ValueError('Use separate backlight and translation variants')
    if a.spmi_translation_survey or a.backlight_service:a.charge_window_handoff=True
    if a.charge_link_recovery:
        if a.variant!='bluetooth' or not a.bt_address17:
            raise ValueError('--charge-link-recovery requires the qualified Bluetooth/address17 chain')
        if any((a.spmi_translation_survey,a.backlight_service,a.backlight_power_trial,
                a.pd_power_trial,a.pd_gui,a.cpu_power_observation,a.cpu_governor,
                a.storage_medium,a.early_storage_guard,a.ufs_wait_trial,
                a.ufs_queue_trial,a.ufs_idle_trial,a.data_capacity_2g)):
            raise ValueError('--charge-link-recovery requires its separate charge/address17 chain')
        a.charge_window_handoff=True
    if a.charge_window_handoff:a.charge_verification=True
    if a.charge_verification and not a.bt_address17:raise ValueError('--charge-verification currently requires the qualified --bt-address17 baseline')
    if sys.platform!='darwin':raise SystemExit('Native build requires macOS with Xcode/iPhoneOS SDK. Windows/WSL can inspect sources and flash separately.')
    config=a.inputs.resolve();data=read(config);out=a.output.resolve()
    def input_path(name):
        value=Path(data[name]);return (value if value.is_absolute() else config.parent/value).resolve(strict=True)
    needed=['llvm','original_agent','nvt_firmware','original_kernelcache']
    if a.variant=='bluetooth':needed+=['wcn_firmware']
    if a.target=='boot':needed+=['os_image','crypto','mu_repository','unixnu_repository','stock_boot','parent_vbmeta','avbtool','signing_key']
    elif a.bluetool_lifecycle or a.data_capacity_2g:needed+=['os_image']
    missing=[name for name in needed if name not in data]
    if missing:raise SystemExit('Missing declared inputs: '+', '.join(missing))
    inputs={name:input_path(name) for name in needed}
    from clean_input_check import check
    check(inputs,a.variant,a.target)
    # Source-only journal: untracked new source files are intentionally included.
    sources={}
    for folder in ('tools','profiles','drivers','scripts','patches'):
        for f in (ROOT/folder).rglob('*'):
            if f.is_file() and f.suffix in ('.py','.json','.c','.cpp','.h','.inc','.s','.S','.patch','.inf','.dsc','.fdf','.toml') and '__pycache__' not in f.parts:
                sources[f.relative_to(ROOT).as_posix()]=sha(f)
    identity={'sources':sources,'inputs':{n:str(v) for n,v in inputs.items()},'config_sha256':sha(config),'target':a.target,'variant':a.variant,'bt_exit_stack':a.bt_exit_stack}
    identity['software_keystore']=a.software_keystore
    identity['bluetool_launch']=a.bluetool_launch
    identity['bt_transport_trace']=a.bt_transport_trace
    identity['bt_syscall_trace']=a.bt_syscall_trace
    identity['bluetool_lifecycle']=a.bluetool_lifecycle
    identity['bt_registry']=a.bt_registry
    identity['bt_helper_trace']=a.bt_helper_trace
    identity['bt_process_lifetime']=a.bt_process_lifetime
    identity['bt_optional17']=a.bt_optional17
    identity['bt_complete17']=a.bt_complete17
    identity['bt_scan17']=a.bt_scan17
    identity['bt_scan_ready17']=a.bt_scan_ready17
    identity['bt_scan_observe17']=a.bt_scan_observe17
    identity['bt_scan_roles17']=a.bt_scan_roles17
    identity['bt_discovery17']=a.bt_discovery17
    identity['bt_address17']=a.bt_address17
    identity['charge_window_handoff']=a.charge_window_handoff
    identity['charge_link_recovery']=a.charge_link_recovery
    identity['spmi_translation_survey']=a.spmi_translation_survey
    identity['backlight_service']=a.backlight_service
    identity['backlight_power_trial']=a.backlight_power_trial
    identity['pd_power_trial']=a.pd_power_trial
    identity['pd_gui']=a.pd_gui
    identity['cpu_power_observation']=a.cpu_power_observation
    identity['cpu_governor']=a.cpu_governor
    identity['storage_medium']=a.storage_medium
    identity['early_storage_guard']=a.early_storage_guard
    identity['ufs_wait_trial']=a.ufs_wait_trial
    identity['ufs_queue_trial']=a.ufs_queue_trial
    identity['ufs_idle_trial']=a.ufs_idle_trial
    identity['data_capacity_2g']=a.data_capacity_2g
    identity['data_ui_replay']=a.data_ui_replay
    identity['charge_verification']=a.charge_verification
    stamp=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest();journal=out/'build-state.json'
    if out.exists():
        if not a.resume or not journal.exists():raise ValueError('Use a new output, or explicitly resume this run')
        state=read(journal)
        if state['identity_sha256']!=stamp:raise ValueError('Source or declared input configuration changed; use a new output')
    else:
        out.mkdir(parents=True);state={'identity_sha256':stamp,'completed':{},'device_operations':False};(out/'build-inputs.json').write_text(json.dumps(identity,indent=2)+'\n')
    def save():journal.write_text(json.dumps(state,indent=2)+'\n')
    save();logs=out/'logs';logs.mkdir(exist_ok=True)
    def stage(name,command,proof):
        proof=out/proof
        if name in state['completed']:
            if not proof.is_file() or sha(proof)!=state['completed'][name]['proof_sha256']:raise ValueError('Completed stage proof changed: '+name)
            return
        state['active']=name;save();print('Building '+name,flush=True)
        with (logs/(name+'.log')).open('ab') as f:r=subprocess.run(list(map(str,command)),cwd=ROOT,stdout=f,stderr=subprocess.STDOUT)
        if r.returncode:raise SystemExit(name+' failed; inspect '+str(logs/(name+'.log')))
        if not proof.is_file():raise ValueError('Missing stage proof: '+name)
        state['completed'][name]={'proof':str(proof.relative_to(out)),'proof_sha256':sha(proof)};state.pop('active',None);save()
    def script(name,*args):return [sys.executable,'-B',ROOT/'tools'/name,*args]
    deps=out/'dependencies';deps.mkdir(exist_ok=True)
    locks=read(ROOT/'profiles/v91/native-build/plan.json')['dependencies']
    locks.update(xnu={'url':'https://github.com/apple-oss-distributions/xnu.git','commit':'d8b80295118ef25ac3a784134bcf95cd8e88109f'},
                 XnuPrelink={'url':'https://github.com/UniXNU/XnuPrelink.git','commit':read(ROOT/'profiles/v91/image-build/plan.json')['prelink']['commit']})
    for name,row in locks.items():
        repo=deps/name
        if not repo.exists():
            subprocess.run(['git','init','--quiet',repo],check=True);subprocess.run(['git','-C',repo,'remote','add','origin',row['url']],check=True)
        result=subprocess.run(['git','-C',repo,'cat-file','-e',row['commit']+'^{commit}'],capture_output=True)
        if result.returncode:subprocess.run(['git','-C',repo,'-c','http.version=HTTP/1.1','fetch','--depth=1','origin',row['commit']],check=True)
        # Object-store access only; no checkout/reset or source-host directory reuse.
    stage('reconstruct',script('reconstruct_v91.py','--xnu-repository',deps/'xnu','--output',out/'source'),'source/result.json')
    stage('icon',script('build_icon_v91.py','--output',out/'icon'),'icon/result.json')
    stage('agent',script('prepare_icon_agent_v91.py','--original-agent',inputs['original_agent'],'--library',out/'icon/EldenIconCpuMode.dylib','--output',out/'agent'),'agent/result.json')
    stage('nvt',script('generate_nvt_firmware_header.py','--firmware',inputs['nvt_firmware'],'--output',out/'nvt/EldenNvtFirmware.h'),'nvt/EldenNvtFirmware.h')
    if a.variant=='bluetooth':stage('generated',script('prepare_current_generated.py','--firmware',inputs['wcn_firmware'],'--library',out/'icon/EldenIconCpuMode.dylib','--agent',out/'agent/iconservicesagent','--output',out/'generated'),'generated/providers.json')
    stage('xnu',script('build_v91_xnu_objects.py','--xnu-source',out/'source/xnu','--xnu-repository',deps/'xnu','--payload-header',out/'agent/EldenIconCpuPayload.h','--output',out/'xnu','--jobs',a.jobs),'xnu/build/summary.json')
    stage('native',script('build_v91_native_archives.py','--xnu-source',out/'source/xnu','--xnu-repository',deps/'xnu','--dependencies',deps,'--nvt-header',out/'nvt/EldenNvtFirmware.h','--payload-header',out/'agent/EldenIconCpuPayload.h','--llvm-objcopy',inputs['llvm']/'llvm-objcopy','--output',out/'native','--jobs',a.jobs),'native/archives/firehose/result.json')
    generated_args=['--generated',out/'generated'] if a.variant=='bluetooth' else []
    stage('current-units',script('build_current_units.py','--variant',a.variant,'--xnu-source',out/'source/xnu','--dependencies',deps,'--icon-header',out/'agent/EldenIconCpuPayload.h','--nvt-header',out/'nvt/EldenNvtFirmware.h',*generated_args,'--llvm',inputs['llvm'],'--output',out/'units','--jobs',a.jobs),'units/result.json')
    stage('link',script('link_current_kernel.py','--variant',a.variant,'--xnu-objects',out/'xnu/build','--native-archives',out/'native/archives','--units',out/'units','--prelink-repository',deps/'XnuPrelink','--original-kernelcache',inputs['original_kernelcache'],'--output',out/'linked'),'linked/result.json')
    kernel_folder=out/'linked'
    runtime_folder=out/'generated/runtime'
    if a.bt_exit_stack:
        stage('bt-exit-stack',script('build_bt_exit_stack.py','--clean-build',out,'--original-kernelcache',inputs['original_kernelcache'],'--llvm',inputs['llvm'],'--output',out/'exit-stack'),'exit-stack/result.json')
        kernel_folder=out/'exit-stack'
    if a.software_keystore:
        stage('software-keystore',script('build_elden_keystore.py','--clean-build',out,'--exit-stack',out/'exit-stack','--original-kernelcache',inputs['original_kernelcache'],'--llvm',inputs['llvm'],'--output',out/'keystore'),'keystore/result.json')
        kernel_folder=out/'keystore'
    if a.bluetool_launch:
        stage('bluetool-launch',script('build_bluetool_launch.py','--clean-build',out,'--keystore-build',out/'keystore','--original-kernelcache',inputs['original_kernelcache'],'--llvm',inputs['llvm'],'--output',out/'bluetool-launch'),'bluetool-launch/result.json')
        kernel_folder=out/'bluetool-launch'
    if a.bt_transport_trace:
        stage('bt-transport-trace',script('build_bt_transport_trace.py','--clean-build',out,'--bluetool-build',out/'bluetool-launch','--original-kernelcache',inputs['original_kernelcache'],'--llvm',inputs['llvm'],'--output',out/'bt-transport-trace'),'bt-transport-trace/result.json')
        kernel_folder=out/'bt-transport-trace'
    if a.bt_syscall_trace:
        stage('bt-syscall-trace',script('build_bt_syscall_trace.py','--clean-build',out,'--transport-build',out/'bt-transport-trace','--original-kernelcache',inputs['original_kernelcache'],'--llvm',inputs['llvm'],'--output',out/'bt-syscall-trace'),'bt-syscall-trace/result.json')
        kernel_folder=out/'bt-syscall-trace'
    if a.bluetool_lifecycle:
        stage('bluetool-cache',script('build_bluetool_job_cache.py','--os-image',inputs['os_image'],'--trust-cache',runtime_folder/'runtime.trustcache','--output',out/'bluetool-cache'),'bluetool-cache/result.json')
        stage('bluetool-lifecycle',script('build_bluetool_lifecycle.py','--clean-build',out,'--transport-build',out/'bt-transport-trace','--cache-build',out/'bluetool-cache','--original-kernelcache',inputs['original_kernelcache'],'--llvm',inputs['llvm'],'--output',out/'bluetool-lifecycle'),'bluetool-lifecycle/result.json')
        kernel_folder=out/'bluetool-lifecycle';runtime_folder=kernel_folder/'runtime'
    if a.bt_registry:
        stage('bt-registry',script('build_bt_registry.py','--clean-build',out,'--lifecycle-build',out/'bluetool-lifecycle','--original-kernelcache',inputs['original_kernelcache'],'--llvm',inputs['llvm'],'--output',out/'bt-registry'),'bt-registry/result.json')
        kernel_folder=out/'bt-registry';runtime_folder=kernel_folder/'runtime'
    if a.bt_helper_trace:
        stage('helper-userland',script('build_bluetool_trace.py','--output',out/'helper-userland'),'helper-userland/result.json')
        stage('bt-helper-trace',script('build_bt_helper_trace.py','--clean-build',out,'--registry-build',out/'bt-registry','--helper-build',out/'helper-userland','--original-kernelcache',inputs['original_kernelcache'],'--llvm',inputs['llvm'],'--output',out/'bt-helper-trace'),'bt-helper-trace/result.json')
        kernel_folder=out/'bt-helper-trace';runtime_folder=kernel_folder/'runtime'
    if a.bt_process_lifetime:
        stage('bt-process-lifetime',script('build_bt_process_lifetime.py','--clean-build',out,'--helper-trace-build',out/'bt-helper-trace','--original-kernelcache',inputs['original_kernelcache'],'--llvm',inputs['llvm'],'--output',out/'bt-process-lifetime'),'bt-process-lifetime/result.json')
        kernel_folder=out/'bt-process-lifetime';runtime_folder=kernel_folder/'runtime'
    if a.bt_optional17:
        stage('bt-optional-runtime',script('prepare_bt_optional17.py','--os-image',inputs['os_image'],'--runtime',runtime_folder,'--output',out/'bt-optional-runtime'),'bt-optional-runtime/result.json')
        stage('bt-optional17',script('build_bt_optional17.py','--clean-build',out,'--process-build',out/'bt-process-lifetime','--optional-runtime',out/'bt-optional-runtime/runtime','--original-kernelcache',inputs['original_kernelcache'],'--llvm',inputs['llvm'],'--output',out/'bt-optional17'),'bt-optional17/result.json')
        kernel_folder=out/'bt-optional17';runtime_folder=kernel_folder/'runtime'
    if a.bt_complete17:
        stage('bt-complete-runtime',script('prepare_bt_complete17.py','--os-image',inputs['os_image'],'--runtime',runtime_folder,'--output',out/'bt-complete-runtime'),'bt-complete-runtime/result.json')
        stage('bt-complete17',script('build_bt_complete17.py','--clean-build',out,'--process-build',out/'bt-process-lifetime','--complete-runtime',out/'bt-complete-runtime/runtime','--original-kernelcache',inputs['original_kernelcache'],'--llvm',inputs['llvm'],'--output',out/'bt-complete17'),'bt-complete17/result.json')
        kernel_folder=out/'bt-complete17';runtime_folder=kernel_folder/'runtime'
    if a.bt_scan17:
        stage('bt-scan-runtime',script('prepare_bt_scan17.py','--os-image',inputs['os_image'],'--runtime',runtime_folder,'--output',out/'bt-scan-runtime'),'bt-scan-runtime/result.json')
        stage('bt-scan17',script('build_bt_scan17.py','--clean-build',out,'--process-build',out/'bt-process-lifetime','--scan-runtime',out/'bt-scan-runtime/runtime','--original-kernelcache',inputs['original_kernelcache'],'--llvm',inputs['llvm'],'--output',out/'bt-scan17'),'bt-scan17/result.json')
        kernel_folder=out/'bt-scan17';runtime_folder=kernel_folder/'runtime'
    if a.bt_scan_ready17:
        stage('bt-scan-ready-runtime',script('prepare_bt_scan_ready17.py','--os-image',inputs['os_image'],'--runtime',runtime_folder,'--output',out/'bt-scan-ready-runtime'),'bt-scan-ready-runtime/result.json')
        stage('bt-scan-ready17',script('build_bt_scan_ready17.py','--clean-build',out,'--process-build',out/'bt-process-lifetime','--scan-runtime',out/'bt-scan-ready-runtime/runtime','--original-kernelcache',inputs['original_kernelcache'],'--llvm',inputs['llvm'],'--output',out/'bt-scan-ready17'),'bt-scan-ready17/result.json')
        kernel_folder=out/'bt-scan-ready17';runtime_folder=kernel_folder/'runtime'
    if a.bt_scan_observe17:
        stage('bt-scan-observe-runtime',script('prepare_bt_scan_observe17.py','--os-image',inputs['os_image'],'--runtime',runtime_folder,'--output',out/'bt-scan-observe-runtime'),'bt-scan-observe-runtime/result.json')
        stage('bt-scan-observe17',script('build_bt_scan_observe17.py','--clean-build',out,'--process-build',out/'bt-process-lifetime','--scan-runtime',out/'bt-scan-observe-runtime/runtime','--original-kernelcache',inputs['original_kernelcache'],'--llvm',inputs['llvm'],'--output',out/'bt-scan-observe17'),'bt-scan-observe17/result.json')
        kernel_folder=out/'bt-scan-observe17';runtime_folder=kernel_folder/'runtime'
    if a.bt_scan_roles17:
        stage('bt-scan-roles-runtime',script('prepare_bt_scan_roles17.py','--os-image',inputs['os_image'],'--runtime',runtime_folder,'--output',out/'bt-scan-roles-runtime'),'bt-scan-roles-runtime/result.json')
        stage('bt-scan-roles17',script('build_bt_scan_roles17.py','--clean-build',out,'--process-build',out/'bt-process-lifetime','--scan-runtime',out/'bt-scan-roles-runtime/runtime','--original-kernelcache',inputs['original_kernelcache'],'--llvm',inputs['llvm'],'--output',out/'bt-scan-roles17'),'bt-scan-roles17/result.json')
        kernel_folder=out/'bt-scan-roles17';runtime_folder=kernel_folder/'runtime'
    if a.bt_discovery17:
        stage('bt-discovery-runtime',script('prepare_bt_discovery17.py','--os-image',inputs['os_image'],'--runtime',runtime_folder,'--output',out/'bt-discovery-runtime'),'bt-discovery-runtime/result.json')
        stage('bt-discovery17',script('build_bt_discovery17.py','--clean-build',out,'--process-build',out/'bt-process-lifetime','--scan-runtime',out/'bt-discovery-runtime/runtime','--original-kernelcache',inputs['original_kernelcache'],'--llvm',inputs['llvm'],'--output',out/'bt-discovery17'),'bt-discovery17/result.json')
        kernel_folder=out/'bt-discovery17';runtime_folder=kernel_folder/'runtime'
    if a.bt_address17:
        stage('bt-address-runtime',script('prepare_bt_address17.py','--os-image',inputs['os_image'],'--runtime',runtime_folder,'--output',out/'bt-address-runtime'),'bt-address-runtime/result.json')
        stage('bt-address17',script('build_bt_address17.py','--clean-build',out,'--process-build',out/'bt-process-lifetime','--scan-runtime',out/'bt-address-runtime/runtime','--original-kernelcache',inputs['original_kernelcache'],'--llvm',inputs['llvm'],'--output',out/'bt-address17'),'bt-address17/result.json')
        kernel_folder=out/'bt-address17';runtime_folder=kernel_folder/'runtime'
    if a.charge_verification:
        charge_name='charge-link-recovery' if a.charge_link_recovery else 'charge-window-handoff' if a.charge_window_handoff else 'charge-verification'
        charge_args=['--link-recovery'] if a.charge_link_recovery else ['--window-handoff'] if a.charge_window_handoff else []
        if a.spmi_translation_survey:charge_name='spmi-translation-survey';charge_args+=['--translation-survey']
        stage(charge_name,script('build_charge_verification.py','--clean-build',out,'--parent-build',kernel_folder,'--original-kernelcache',inputs['original_kernelcache'],'--llvm',inputs['llvm'],'--output',out/charge_name,*charge_args),charge_name+'/result.json')
        kernel_folder=out/charge_name;runtime_folder=kernel_folder/'runtime'
    if a.backlight_service:
        backlight_name='backlight-power-trial' if a.backlight_power_trial else 'backlight-service'
        backlight_args=['--backlight-power-trial'] if a.backlight_power_trial else []
        stage(backlight_name,script('build_charge_verification.py','--backlight-service',*backlight_args,'--clean-build',out,'--parent-build',kernel_folder,'--original-kernelcache',inputs['original_kernelcache'],'--llvm',inputs['llvm'],'--output',out/backlight_name),backlight_name+'/result.json')
        kernel_folder=out/backlight_name;runtime_folder=kernel_folder/'runtime'
    if a.pd_power_trial:
        stage('pd-power-trial',script('build_charge_verification.py','--pd-power-trial','--clean-build',out,'--parent-build',kernel_folder,'--original-kernelcache',inputs['original_kernelcache'],'--llvm',inputs['llvm'],'--output',out/'pd-power-trial'),'pd-power-trial/result.json')
        kernel_folder=out/'pd-power-trial';runtime_folder=kernel_folder/'runtime'
    if a.cpu_power_observation:
        stage('cpu-power-observation',script('build_charge_verification.py','--cpu-power-observation','--clean-build',out,'--parent-build',kernel_folder,'--original-kernelcache',inputs['original_kernelcache'],'--llvm',inputs['llvm'],'--output',out/'cpu-power-observation'),'cpu-power-observation/result.json')
        kernel_folder=out/'cpu-power-observation';runtime_folder=kernel_folder/'runtime'
    if a.cpu_governor:
        stage('cpu-governor',script('build_charge_verification.py','--cpu-governor','--clean-build',out,'--parent-build',kernel_folder,'--original-kernelcache',inputs['original_kernelcache'],'--llvm',inputs['llvm'],'--output',out/'cpu-governor'),'cpu-governor/result.json')
        kernel_folder=out/'cpu-governor';runtime_folder=kernel_folder/'runtime'
    if a.storage_medium:
        stage('storage-medium',script('build_charge_verification.py','--storage-medium','--clean-build',out,'--parent-build',kernel_folder,'--original-kernelcache',inputs['original_kernelcache'],'--llvm',inputs['llvm'],'--output',out/'storage-medium'),'storage-medium/result.json')
        kernel_folder=out/'storage-medium';runtime_folder=kernel_folder/'runtime'
    if a.early_storage_guard:
        stage('early-storage-guard',script('build_charge_verification.py','--early-storage-guard','--clean-build',out,'--parent-build',kernel_folder,'--original-kernelcache',inputs['original_kernelcache'],'--llvm',inputs['llvm'],'--output',out/'early-storage-guard'),'early-storage-guard/result.json')
        kernel_folder=out/'early-storage-guard';runtime_folder=kernel_folder/'runtime'
    if a.ufs_wait_trial:
        stage('ufs-wait-trial',script('build_charge_verification.py','--ufs-wait-trial','--clean-build',out,'--parent-build',kernel_folder,'--original-kernelcache',inputs['original_kernelcache'],'--llvm',inputs['llvm'],'--output',out/'ufs-wait-trial'),'ufs-wait-trial/result.json')
        kernel_folder=out/'ufs-wait-trial';runtime_folder=kernel_folder/'runtime'
    if a.ufs_queue_trial:
        stage('ufs-queue-trial',script('build_charge_verification.py','--ufs-queue-trial','--clean-build',out,'--parent-build',kernel_folder,'--original-kernelcache',inputs['original_kernelcache'],'--llvm',inputs['llvm'],'--output',out/'ufs-queue-trial'),'ufs-queue-trial/result.json')
        kernel_folder=out/'ufs-queue-trial';runtime_folder=kernel_folder/'runtime'
    if a.ufs_idle_trial:
        stage('ufs-idle-trial',script('build_charge_verification.py','--ufs-idle-trial','--clean-build',out,'--parent-build',kernel_folder,'--original-kernelcache',inputs['original_kernelcache'],'--llvm',inputs['llvm'],'--output',out/'ufs-idle-trial'),'ufs-idle-trial/result.json')
        kernel_folder=out/'ufs-idle-trial';runtime_folder=kernel_folder/'runtime'
    if a.data_capacity_2g:
        stage('data',script('build_v91_data_seed.py','--size-mib','2048','--os-image',inputs['os_image'],'--output',out/'data'),'data/result.json')
        stage('data-capacity-2g-key',script('build_data_capacity_kernel.py','--parent-build',kernel_folder,'--core-build',out/'bt-address17','--keystore-build',out/'keystore','--clean-build',out,'--seed-build',out/'data','--original-kernelcache',inputs['original_kernelcache'],'--llvm',inputs['llvm'],'--output',out/'data-capacity-2g-key'),'data-capacity-2g-key/result.json')
        kernel_folder=out/'data-capacity-2g-key';runtime_folder=kernel_folder/'runtime'
    if a.target=='boot':
        stage('firmware',script('build_v91_firmware.py','--mu-root',inputs['mu_repository'],'--unixnu-root',inputs['unixnu_repository'],'--crypto-path',inputs['crypto'],'--llvm',inputs['llvm'],'--output',out/'firmware','--jobs',a.jobs),'firmware/result.json')
        stage('loader',script('build_v91_payload_loader.py','--mu-root',out/'firmware/project/third_party/mu_wide_platforms','--unixnu-root',out/'firmware/project/third_party/UniXNU','--llvm',inputs['llvm'],'--output',out/'loader'),'loader/result.json')
        if not a.data_capacity_2g:stage('data',script('build_v91_data_seed.py','--os-image',inputs['os_image'],'--output',out/'data'),'data/result.json')
        ep={'candidate_sha256':read(kernel_folder/'result.json')['kernel_sha256'],'original_executable_sha256':read(ROOT/'profiles/v91/image-build/plan.json')['prelink']['original_executable_sha256']};(out/'entry-plan.json').write_text(json.dumps(ep,indent=2)+'\n')
        stage('entry',script('prepare_v91_entry.py','--kernel',kernel_folder/'kernel.macho','--plan',out/'entry-plan.json','--clang',inputs['llvm']/'clang','--output',out/'entry'),'entry/result.json')
        variant_args=['--wcn-report',kernel_folder/'result.json','--bt-runtime',runtime_folder] if a.variant=='bluetooth' else ['--hid-report',kernel_folder/'result.json']
        if a.pd_gui:variant_args+=['--pd-gui']
        if a.data_capacity_2g:variant_args+=['--expanded-data','--keep-packed-data']
        if a.data_ui_replay:variant_args+=['--data-ui-replay']
        stage('boot',script('build_v91_boot.py','--portable-fat','--kernel',out/'entry/kernel.macho','--entry-report',out/'entry/result.json','--fd',out/'firmware/UEFI.fd','--loader',out/'loader/EldenPayloadLoader.efi','--data',out/'data/data.packed','--data-report',out/'data/result.json','--library',out/'icon/EldenIconCpuMode.dylib','--agent',out/'agent/iconservicesagent','--stock-boot',inputs['stock_boot'],'--avbtool',inputs['avbtool'],'--key',inputs['signing_key'],'--clang',inputs['llvm']/'clang',*variant_args,'--output',out/'boot'),'boot/result.json')
        stage('boot-audit',script('audit_v91_boot.py','--image',out/'boot/boot-signed.img','--entry-kernel',out/'entry/kernel.macho','--entry-report',out/'entry/result.json','--stock-boot',inputs['stock_boot'],'--parent-vbmeta',inputs['parent_vbmeta'],'--data-report',out/'data/result.json',*variant_args,'--output',out/'boot/audit.json'),'boot/audit.json')
    state['complete']=True;save();print('Completed '+a.target+'; no device operation performed',flush=True)
if __name__=='__main__':main()
