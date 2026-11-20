"""Qualify the complete station path, assets and original physical return."""
import hashlib,json,plistlib,sys
from pathlib import Path
from replay_xnu_objects import global_symbols
ROOT=Path(__file__).resolve().parents[1];STA=ROOT/'drivers/EldenWifi/portable/station'
sys.path.insert(0,str(STA));from StationRuntimeSource import EXPECTED,patch
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def defs(p):return {n for n,v in global_symbols(Path(p)).items() if v[0]&0x0e}
def refs(p):return {n for n,v in global_symbols(Path(p)).items() if not v[0]&0x0e}

def qualify_runtime(r):
    if r.get('station_diagnostic'):
        return qualify_diagnostic(r)
    if r.get('station_hif'):
        return qualify_hif(r)
    if r.get('station_trial') is not True or r.get('compiled') is not True or r.get('runtime_count')!=126:
        raise ValueError('Unqualified station runtime')
    if r.get('firmware_board_power_retained') is not True or r.get('actual_wpa2_helper') is not True:
        raise ValueError('Station board/crypto scope differs')
    if r['station_donor']!=read(STA/'upstream/source.json') or r['station_donor']['commit']!='2438556c77c90c22c7b76e57eb8b40c44b35f1af':
        raise ValueError('Wrong hardware-tested station donor')
    from wifi_portable_scan import qualify
    qualify(r['scan_parent'])
    for row in r['station_donor']['files']:
        if sha(STA/'upstream'/row['path'])!=row['sha256']:raise ValueError('Station donor bytes differ')
    if set(r['units'])!=set(EXPECTED) or len(r['retained_objects'])!=121:raise ValueError('Station object delta differs')
    for name,row in r['units'].items():
        if sha(row['parent_source'])!=EXPECTED[name] or patch(name,Path(row['parent_source']).read_bytes())!=Path(row['source']).read_bytes() or sha(row['source'])!=row['source_sha256'] or sha(row['object'])!=row['object_sha256']:
            raise ValueError('Station actual source/object differs: '+name)
        for path,digest in row['consumed_inputs'].items():
            if sha(path)!=digest:raise ValueError('Station header differs: '+path)
    for path,digest in r['native']['consumed_inputs'].items():
        if sha(path)!=digest:raise ValueError('Station native input differs')
    for path,digest in r['retained_objects'].items():
        if sha(path)!=digest:raise ValueError('Retained station object differs')
    if sha(r['native']['object'])!=r['native']['object_sha256'] or sha(r['link'][r['link'].index('-o')+1])!=r['binding_sha256']:
        raise ValueError('Station native/binding differs')
    for name,digest in r['source_inputs'].items():
        if sha(ROOT/name)!=digest:raise ValueError('Station source pin differs: '+name)
    return True

def qualify_diagnostic(r):
    if any(r.get(k) is not True for k in ['compiled','station_diagnostic','readonly_registers','no_payload_logging','one_first_tx_sample']):raise ValueError('Wrong consolidated TX diagnostic')
    qualify_runtime(r['base'])
    from StationDiagnosticSource import source,EXPECTED
    if sha(r['parent_source'])!=EXPECTED or source(Path(r['parent_source']).read_bytes())!=Path(r['source']).read_bytes() or sha(r['source'])!=r['source_sha256'] or sha(r['object'])!=r['object_sha256']:
        raise ValueError('TX diagnostic source/object differs')
    if len(r['retained_objects'])!=125:raise ValueError('TX diagnostic retained objects differ')
    for path,digest in {**r['retained_objects'],**r['consumed_inputs']}.items():
        if sha(path)!=digest:raise ValueError('TX diagnostic actual input changed')
    if sha(r['link'][r['link'].index('-o')+1])!=r['binding_sha256']:raise ValueError('TX diagnostic binding differs')
    for name,digest in r['source_inputs'].items():
        if sha(ROOT/name)!=digest:raise ValueError('TX diagnostic source pin differs')
    return True

def qualify_hif(r):
    if any(r.get(k) is not True for k in ['compiled','station_hif','init_done_and_owned_umac','held_real_mhi_wake','release_after_protocol_stop','no_linux_ce_start','no_board_or_firmware_change']):
        raise ValueError('Wrong owned portable HIF lifetime')
    qualify_runtime(r['base'])
    from PortableHifPatch import EXPECTED as expected,patch as hif_patch
    if set(r['units'])!=set(expected) or len(r['retained_objects'])!=124:raise ValueError('HIF object boundary differs')
    for name,row in r['units'].items():
        if sha(row['parent_source'])!=expected[name] or hif_patch(name,Path(row['parent_source']).read_bytes())!=Path(row['source']).read_bytes() or sha(row['object'])!=row['object_sha256'] or sha(row['source'])!=row['source_sha256']:
            raise ValueError('HIF actual consumed source differs')
        for path,digest in row['consumed_inputs'].items():
            if sha(path)!=digest:raise ValueError('HIF header differs')
    for path,digest in r['retained_objects'].items():
        if sha(path)!=digest:raise ValueError('Retained HIF object differs')
    if sha(r['link'][r['link'].index('-o')+1])!=r['binding_sha256']:raise ValueError('HIF binding differs')
    for name,digest in r['source_inputs'].items():
        if sha(ROOT/name)!=digest:raise ValueError('HIF source pin differs: '+name)
    return True

def qualify_native(r,folder):
    if not r.get('station_native') or not r.get('real_privileged_socket') or not r.get('original_physical_fence_preserved'):
        raise ValueError('Station native port scope differs')
    from StationNativeSource import apply
    base=r['base'];cmd=base['command'];ov=read(cmd[cmd.index('-ivfsoverlay')+1])
    files={}
    for item in ov['roots']:
        p=Path(item['external-contents'])
        if p.name in r['generated_sources']:files[p.name]=p.read_bytes()
    # Files not referenced by the overlay still come from the exact captured
    # parent generation directory. Reconstruct via the existing parent row.
    parent=Path(cmd[cmd.index('-o')+1]).parent
    files={p.name:p.read_bytes() for p in (parent/'source').iterdir() if p.is_file()}
    new=apply(files)
    if r['generated_sources']!={n:hashlib.sha256(v).hexdigest() for n,v in new.items()}:raise ValueError('Station worker source differs')
    for path,digest in r['inherited_sources'].items():
        if sha(path)!=digest:raise ValueError('Station inherited worker pin differs')
    if sha(Path(folder)/'Native.o')!=r['object_sha256'] or sha(Path(folder)/'EldenStationProfile.h')!=r['private_header_sha256']:
        raise ValueError('Station worker/private input differs')
    for name,digest in r['source_inputs'].items():
        if sha(ROOT/name)!=digest:raise ValueError('Station native source changed')

def qualify_assets(report,runtime,native,base_trust_sha):
    from wifi_service_boot import trust_append
    runtime=Path(runtime);a=read(runtime/'wifi-service-assets.json')
    if a!=report['service_assets'] or a!=report['core']['assets'] or not a.get('station_assets') or not a.get('crypto_source_unchanged') or not a.get('crypto_self_test'):
        raise ValueError('Station authentication/assets differ')
    if a['input_trust_sha256']!=base_trust_sha or a['credentials_included'] or (a['old_jobs_unchanged'],a['jobs'],a['new_trust_entries'])!=(561,562,2):
        raise ValueError('Station cache/trust parent differs')
    for name,key in [('launchd.plist','cache_sha256'),('launchd.plist.sig','signature_sha256'),('EldenWifiServiceAssets.h','header_sha256'),
                     ('unixnu-wpa_supplicant','helper_sha256'),('wpa_supplicant.conf','config_sha256'),('runtime.trustcache','trust_sha256')]:
        if sha(runtime/name)!=a[key]:raise ValueError('Station runtime asset differs: '+name)
        if name in ['launchd.plist','launchd.plist.sig','unixnu-wpa_supplicant'] and native.count((runtime/name).read_bytes())!=1:
            raise ValueError('Station asset embedding differs: '+name)
    before=plistlib.loads((runtime/'base-launchd.plist').read_bytes());after=plistlib.loads((runtime/'launchd.plist').read_bytes())
    key='/System/Library/LaunchDaemons/org.unixnu.wifi.supplicant.plist'
    if len(before['LaunchDaemons'])!=561 or len(after['LaunchDaemons'])!=562 or after['LaunchDaemons'].pop(key)!=a['job'] or before!=after:
        raise ValueError('Original station jobs changed')
    if trust_append((runtime/'base-runtime.trustcache').read_bytes(),[a['helper_cdhash'],a['cache_cdhash']])!=(runtime/'runtime.trustcache').read_bytes():
        raise ValueError('Station trust reconstruction differs')
    return dict(trust_sha256=a['trust_sha256'],base_trust_sha256=base_trust_sha,wifi_service_cdhashes=[a['helper_cdhash'],a['cache_cdhash']],wifi_service=True,station_trial=True)

def qualify_components(report):
    if not report.get('station_trial'):raise ValueError('Not station')
    parent=report['station_parent']
    # The historical scan parent is qualified by its own bytes and generators;
    # current changes are separately checked below, never accepted by editing
    # those immutable scan hashes.
    r=report['station_runtime'];qualify_runtime(r)
    folder=Path(report['station_worker']['command'][report['station_worker']['command'].index('-o')+1]).parent
    qualify_native(report['station_worker'],folder)
    if parent['kernel_sha256']!=report['station_parent_kernel_sha256'] or report['profile']!='wifi-network-17':raise ValueError('Station parent differs')
    original=report['station_runtime']
    while original.get('station_hif') or original.get('station_diagnostic'):original=original['base']
    if original['scan_parent']!=parent['portable_scan_runtime']:raise ValueError('Station scan chain differs')
    if report['network_bridge']!=parent['network_bridge'] or report['optional_runtime']!=parent['optional_runtime']:
        raise ValueError('Station OS bridge/rules changed')
    if report['entry_delta']!=7124 or report['original_apple_executables_hashed']!=30 or not report['original_physical_return_preserved']:
        raise ValueError('Station entry/return changed')
    for name,digest in report['source_inputs'].items():
        if sha(ROOT/name)!=digest:raise ValueError('Station full source pin differs: '+name)
    for name,key in [('Native.o',report['station_worker']['object_sha256']),('WifiRuntimeMsiBinding.o',r['binding_sha256'])]:
        row=report['component_objects'][name]
        if row['sha256']!=key or sha(row['path'])!=key:raise ValueError('Station loaded member differs')
    return True
