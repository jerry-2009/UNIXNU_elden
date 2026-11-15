"""Qualify balanced process-reference callbacks with the observed helper."""
from pathlib import Path
import hashlib,json,sys
from link_v91_kernel import native_identity,verify_original_executables
from audit_entry_relocation import entry
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'drivers/EldenBluetooth/runtime'))
sys.path.insert(0,str(ROOT/'drivers/EldenBluetooth'))
from ProcessLifetimeSource import source as fixed_source
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def qualify(report_path,entry_path,runtime):
    folder=Path(report_path).parent;r=json.loads(Path(report_path).read_text());e=json.loads(Path(entry_path).read_text());runtime=Path(runtime)
    if r.get('profile')!='bt-process-lifetime' or r['changed_native_objects']!=1 or not r['core_filelist_unchanged']:raise ValueError('Wrong diagnostic build')
    trace=json.loads((runtime/'trace-runtime.json').read_text())
    if r['objects']['NativeHost.cpp']['source_sha256']!=hashlib.sha256(fixed_source()).hexdigest():raise ValueError('Process lifetime source differs')
    for path,h in trace['helper_report']['source_inputs'].items():
        if sha(ROOT/path)!=h:raise ValueError('Helper source changed: '+path)
    for path,h in r['source_inputs'].items():
        if sha(ROOT/path)!=h:raise ValueError('Diagnostic source/tool changed: '+path)
    for name in ('kernel','native'):
        if sha(folder/(name+'.macho'))!=r[name+'_sha256']:raise ValueError('Diagnostic artifact changed')
    contract=ROOT/'profiles/bt-process-lifetime/native-contract.json';expected=json.loads(contract.read_text());s,c,h=native_identity(folder/'native.macho')
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
    for name,key in [('launchd.plist','cache_sha256'),('launchd.plist.sig','signature_sha256'),('EldenBtLaunchCache.h','header_sha256')]:
        if sha(runtime/name)!=cache[key]:raise ValueError('Lifecycle asset changed: '+name)
        if name in ('launchd.plist','launchd.plist.sig') and native.count((runtime/name).read_bytes())!=1:raise ValueError('Cache asset not embedded exactly once')
    if sha(runtime/'runtime.trustcache')!=trace['trust_sha256'] or native.count((runtime/'BlueTool').read_bytes())!=1:raise ValueError('Helper/trust embedding differs')
    return {'profile':'bt-process-lifetime','profile_sha256':sha(contract),'trust_sha256':trace['trust_sha256'],'cache_cdhash':cache['cdhash'],'cache_input_trust_sha256':trace['cache_input_trust_sha256'],'helper_sha256':trace['helper_sha256'],
            'entry_return_target':hex(target),'entry_assembly_sha256':'818ed81e39f38ee6f13bdbf4f166e9e7a5d72f4b7a652d52872e2ba85ea53cc1','mode':4,'key_state':2,'text_fixups_hex':table,'hardware_tested':False}
