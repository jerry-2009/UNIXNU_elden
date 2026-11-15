"""Qualify the explicit charging variants over the frozen native HCI baseline."""
from pathlib import Path
import hashlib,json,sys,struct
from link_v91_kernel import native_identity,verify_original_executables
from audit_entry_relocation import entry
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'drivers/EldenBluetooth/runtime'))
sys.path.insert(0,str(ROOT/'drivers/EldenBluetooth'))
sys.path.insert(0,str(ROOT/'drivers/EldenBluetooth/userland'))
from Native17Optional import SITES
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def qualify(report_path,entry_path,runtime):
    folder=Path(report_path).parent;r=json.loads(Path(report_path).read_text());e=json.loads(Path(entry_path).read_text());runtime=Path(runtime)
    profile=r.get('profile')
    units={'BacklightRuntime'} if profile in ('backlight-service','backlight-power-trial') else {'PmicClient','ChargePolicy'}
    if profile=='pd-power-trial':units={'PmicClient','BacklightRuntime'}
    if profile=='cpu-power-observation':units={'CpuPerfSurvey'}
    if profile=='cpu-governor':units={'CpuPerfSurvey','ShengUfs'}
    if profile=='storage-medium':units={'ShengUfs','NativeRamBlock'}
    if profile=='early-storage-guard':units={'ShengUfs'}
    if profile=='ufs-wait-trial':units={'ArmCpu','ShengUfs'}
    if profile not in ('charge-verification','charge-window-handoff','spmi-translation-survey','backlight-service','backlight-power-trial','pd-power-trial','cpu-power-observation','cpu-governor','storage-medium','early-storage-guard','ufs-wait-trial') or r['changed_core_objects']!=0 or r['changed_native_objects']!=len(units) or set(r['native_objects'])!=units or not r['core_filelist_unchanged'] or not r['scalar']:raise ValueError('Wrong diagnostic build')
    if profile=='ufs-wait-trial':
        sys.path.insert(0,str(ROOT/'drivers/EldenUfsWait'))
        from TrialSource import source,recovery,commands,cpu_source,completion
        row=r['native_objects']['ShengUfs']
        for field,data in [('source_sha256',source()),('recovery_sha256',recovery()),('commands_sha256',commands()),('completion_sha256',completion())]:
            if hashlib.sha256(data).hexdigest()!=row[field]:raise ValueError('UFS trial input differs: '+field)
        if hashlib.sha256(cpu_source()).hexdigest()!=r['native_objects']['ArmCpu']['source_sha256'] or not all(r['native_objects'][u]['initializers_preserved'] for u in units):raise ValueError('UFS trial CPU/initializer differs')
    if profile=='early-storage-guard':
        sys.path.insert(0,str(ROOT/'drivers/EldenCpuActivation'))
        from EarlyStorageSource import source,recovery
        row=r['native_objects']['ShengUfs']
        if hashlib.sha256(source()).hexdigest()!=row['source_sha256'] or hashlib.sha256(recovery()).hexdigest()!=row['recovery_sha256'] or not row['initializers_preserved']:raise ValueError('Early guard source/recovery differs')
    if profile=='storage-medium':
        sys.path.insert(0,str(ROOT/'drivers/EldenStorageMedium'))
        from MediumSource import source
        for unit in units:
            if hashlib.sha256(source(unit)).hexdigest()!=r['native_objects'][unit]['source_sha256'] or not r['native_objects'][unit].get('initializers_preserved'):raise ValueError('Storage medium source/initializer differs')
    if profile=='cpu-governor':
        sys.path.insert(0,str(ROOT/'drivers/EldenCpuPower'))
        from RuntimeSource import source,recovery
        from GovernorSource import policy
        from cpu_governor_build import audit_stop_link
        if hashlib.sha256(source()).hexdigest()!=r['native_objects']['CpuPerfSurvey']['source_sha256'] or hashlib.sha256(recovery()).hexdigest()!=r['native_objects']['ShengUfs']['source_sha256']:raise ValueError('Governor source/recovery differs')
        if hashlib.sha256(policy()).hexdigest()!=r['generated_policy_sha256'] or not r['native_objects']['ShengUfs'].get('initializers_preserved'):raise ValueError('Governor policy/initializer contract differs')
        if audit_stop_link(folder/'native.macho',folder/'kernel.macho')!=r['stop_hook']:raise ValueError('Governor stop linkage differs')
    if profile=='cpu-power-observation':
        sys.path.insert(0,str(ROOT/'drivers/EldenCpuPower'))
        from SurveySource import source
        if hashlib.sha256(source()).hexdigest()!=r['native_objects']['CpuPerfSurvey']['source_sha256']:raise ValueError('CPU observer source differs')
    if profile=='pd-power-trial':
        sys.path[:0]=[str(ROOT/'drivers/EldenPmicGlink'),str(ROOT/'drivers/EldenBacklight')]
        from PdStartupSource import client
        from PdPowerSource import source
        for unit,data in [('PmicClient',client()),('BacklightRuntime',source())]:
            if hashlib.sha256(data).hexdigest()!=r['native_objects'][unit]['source_sha256']:raise ValueError('PD integration source differs')
    if profile in ('backlight-service','backlight-power-trial'):
        sys.path.insert(0,str(ROOT/'drivers/EldenBacklight'))
        from BootSource import source
        if profile=='backlight-power-trial':
            from PowerTrialSource import source
        if hashlib.sha256(source()).hexdigest()!=r['native_objects']['BacklightRuntime']['source_sha256']:raise ValueError('Backlight source differs from declared derivation')
    if profile in ('charge-window-handoff','spmi-translation-survey'):
        sys.path.insert(0,str(ROOT/'drivers/EldenPmicGlink'))
        from WindowSource import policy
        from VerificationSource import client
        if profile=='spmi-translation-survey':
            from TranslationSource import client
        for unit,data in [('ChargePolicy',policy()),('PmicClient',client())]:
            if hashlib.sha256(data).hexdigest()!=r['native_objects'][unit]['source_sha256']:raise ValueError('Window source differs from declared derivation')
    trace=json.loads((runtime/'trace-runtime.json').read_text())
    optional=r['optional_runtime']
    fixed_rules=json.loads((ROOT/'profiles/bt-address17/runtime-report.json').read_text())
    if optional!=fixed_rules or optional['table_count']!=59:raise ValueError('Native completion rules differ')
    for path,h in optional['source_inputs'].items():
        if sha(ROOT/path)!=h:raise ValueError('Optional source changed')
    for name,h in optional['files'].items():
        if sha(runtime/name)!=h:raise ValueError('Optional runtime changed')
    for path,h in trace['helper_report']['source_inputs'].items():
        if sha(ROOT/path)!=h:raise ValueError('Helper source changed: '+path)
    for path,h in r['source_inputs'].items():
        if sha(ROOT/path)!=h:raise ValueError('Diagnostic source/tool changed: '+path)
    for name in ('kernel','native'):
        if sha(folder/(name+'.macho'))!=r[name+'_sha256']:raise ValueError('Diagnostic artifact changed')
    contract=ROOT/'profiles'/profile/'native-contract.json';expected=json.loads(contract.read_text());s,c,h=native_identity(folder/'native.macho')
    if (s,c,h)!=(expected['sections'],expected['commands'],expected['symbols']):raise ValueError('Diagnostic loaded content differs')
    originals=json.loads((ROOT/'profiles/v91/image-build/plan.json').read_text())['prelink']['original_executable_sha256']
    verify_original_executables(folder/'kernel.macho',json.loads((folder/'kernel.json').read_text()),originals)
    start,target,word=entry((folder/'kernel.macho').read_bytes())
    if target-start!=7124 or e['entry']['entry_target']!=target or e['source_sha256']!=r['kernel_sha256'] or r['entry_return_target']!=hex(target):raise ValueError('Entry contract differs')
    p=json.loads((ROOT/'profiles/v119-bt-exit/plan.json').read_text());table=json.loads((ROOT/'profiles/v118-native17/runtime-report.json').read_text())['text_fixups_after_hex']
    cache=json.loads((runtime/'cache-report.json').read_text());fixed=json.loads((ROOT/'docs/evidence/bluetool-job-cache.json').read_text())
    for k in ('cache_sha256','signature_sha256','cdhash','trust_sha256','header_sha256','source_sha256'):
        if cache[k]!=fixed[k]:raise ValueError('Cache input differs')
    if sha(runtime/'BlueTool')!=trace['helper_sha256']:raise ValueError('Helper changed')
    native=(folder/'native.macho').read_bytes()
    if native.count(bytes.fromhex(optional['table_hex']))!=1:raise ValueError('Full rule table not embedded exactly once')
    for name,key in [('launchd.plist','cache_sha256'),('launchd.plist.sig','signature_sha256'),('EldenBtLaunchCache.h','header_sha256')]:
        if sha(runtime/name)!=cache[key]:raise ValueError('Lifecycle asset changed: '+name)
        if name in ('launchd.plist','launchd.plist.sig') and native.count((runtime/name).read_bytes())!=1:raise ValueError('Cache asset not embedded exactly once')
    if sha(runtime/'runtime.trustcache')!=trace['trust_sha256'] or native.count((runtime/'BlueTool').read_bytes())!=1:raise ValueError('Helper/trust embedding differs')
    return {'profile':profile,'profile_sha256':sha(contract),'trust_sha256':trace['trust_sha256'],'cache_cdhash':cache['cdhash'],'cache_input_trust_sha256':trace['cache_input_trust_sha256'],'helper_sha256':trace['helper_sha256'],
            'entry_return_target':hex(target),'entry_assembly_sha256':'818ed81e39f38ee6f13bdbf4f166e9e7a5d72f4b7a652d52872e2ba85ea53cc1','mode':4,'key_state':2,'text_fixups_hex':optional['table_hex'],'table_count':59,'hardware_tested':False}
