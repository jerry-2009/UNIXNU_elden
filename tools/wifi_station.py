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
    if r.get('oem_eapol_critical'):
        return qualify_oem_eapol_critical(r)
    if r.get('station_ready'):
        return qualify_ready(r)
    if r.get('station_wire'):
        return qualify_wire(r)
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


def qualify_oem_eapol_critical(r):
    fields = ['compiled', 'oem_eapol_critical', 'station_tx_critical',
              'oem_flow_override', 'oem_high_priority_notify',
              'no_payload_logging']
    if any(r.get(k) is not True for k in fields):
        raise ValueError('Unqualified OEM EAPOL critical TX path')
    single_pdev_bank=r.get('oem_single_pdev_bank',False)
    if type(single_pdev_bank) is not bool or r.get('no_board_ring_bank_clock_timeout_change') is not (not single_pdev_bank):
        raise ValueError('OEM station bank choice differs')
    oem_index_bank=r.get('oem_index_bank',False)
    if type(oem_index_bank) is not bool or (oem_index_bank and not (single_pdev_bank and r.get('oem_srng_size') is True)):
        raise ValueError('OEM index bank requires the single-PDEV and OEM SRNG baseline')
    oem_target_pdev=r.get('oem_target_pdev',False)
    if type(oem_target_pdev) is not bool or (oem_target_pdev and not oem_index_bank):
        raise ValueError('OEM target PDEV requires the OEM index bank baseline')
    if r.get('hardware_tested') is not False:
        raise ValueError('An offline descriptor build cannot claim hardware acceptance')
    if len(r.get('retained_objects', {})) != 125:
        raise ValueError('OEM EAPOL TX did not retain the qualified station ring')
    prior=r['base']
    if (not prior.get('station_ready') or prior.get('oem_eapol_critical') or
            any(prior.get(k) or r.get(k) for k in ('eapol_voice','oem_tcl_v1'))):
        raise ValueError('Critical TX requires the original eight-byte HTT station baseline')
    qualify_runtime(prior)
    from StationOemEapolCritical import DP_SOURCE_SHA, dp_header, station
    parent_source = Path(r['parent_source']).read_bytes()
    expected_source = station(parent_source, oem_target_pdev=oem_target_pdev)
    if (r['parent_source'] != prior['source'] or sha(r['parent_source']) != r['parent_source_sha256'] or
            expected_source != Path(r['source']).read_bytes()):
        raise ValueError('OEM EAPOL station source derivation differs')
    original_dp = STA / 'upstream/WifiDp.h'
    generated_dp = dp_header(original_dp.read_bytes(),single_pdev_bank=single_pdev_bank,oem_index_bank=oem_index_bank)
    if (sha(original_dp) != DP_SOURCE_SHA or generated_dp != Path(r['dp_header']).read_bytes() or
            sha(r['dp_header']) != r['dp_header_sha256']):
        raise ValueError('OEM TCL critical field derivation differs')
    headers=dict(prior['consumed_inputs'])
    headers.pop(prior['source'])
    dp_paths=[path for path in headers if Path(path).name=='WifiDp.h']
    if len(dp_paths)!=1 or headers.pop(dp_paths[0])!=DP_SOURCE_SHA:
        raise ValueError('Missing original DP header')
    expected_overlay = read(prior['base']['overlay'])
    expected_overlay['roots'].append({
        'type': 'file',
        'name': str(Path(dp_paths[0]).resolve()),
        'external-contents': r['dp_header'],
    })
    headers[r['dp_header']]=r['dp_header_sha256']
    from ScanHttDrain import LINK_SHA,HTT_SHA,link_header,oem_srng_header
    if r.get('oem_srng_size') and r.get('wait_htt_drain') is not True:
        raise ValueError('The OEM SRNG size requires HTT source-ring drain')
    for flag, key, name, frozen_digest, derive in (
        ('wait_htt_drain','link_header','WifiLink.h',LINK_SHA,link_header),
        ('oem_srng_size','htt_header','WifiHtt.h',HTT_SHA,oem_srng_header),
    ):
        enabled=r.get(flag,False)
        if type(enabled) is not bool:
            raise ValueError('Invalid station HTT option: '+flag)
        if not enabled:
            if key in r or key+'_sha256' in r:
                raise ValueError('Unexpected station header: '+name)
            continue
        paths=[path for path in headers if Path(path).name==name]
        if len({Path(path).resolve() for path in paths})!=1 or any(headers[path]!=frozen_digest for path in paths):
            raise ValueError('Missing original '+name)
        for path in paths:
            headers.pop(path)
        original=STA.parent/'upstream'/name
        generated=r[key]
        digest=r[key+'_sha256']
        if derive(original.read_bytes())!=Path(generated).read_bytes() or sha(generated)!=digest:
            raise ValueError('Station header derivation differs: '+name)
        expected_overlay['roots'].append({'type':'file','name':str(Path(paths[0]).resolve()),'external-contents':generated})
        headers[generated]=digest
    if (read(r['overlay']) != expected_overlay or
            sha(r['overlay']) != r['overlay_sha256'] or
            r['command'].count('-ivfsoverlay') != 1 or
            r['command'][r['command'].index('-ivfsoverlay') + 1] != r['overlay']):
        raise ValueError('OEM TCL critical overlay differs')
    if r['retained_objects']!=prior['retained_objects'] or r['consumed_inputs']!={**headers,r['source']:r['source_sha256']}:
        raise ValueError('OEM TCL critical compile inputs differ')
    for key, digest in (('source', 'source_sha256'), ('object', 'object_sha256')):
        if sha(r[key]) != r[digest]:
            raise ValueError('OEM critical station ' + key + ' changed')
    for path, digest in {**r['retained_objects'], **r['consumed_inputs']}.items():
        if sha(path) != digest:
            raise ValueError('OEM critical input changed: ' + path)
    binding = r['link'][r['link'].index('-o') + 1]
    if sha(binding) != r['binding_sha256']:
        raise ValueError('OEM critical combined binding changed')
    for name, digest in r['source_inputs'].items():
        if sha(ROOT / name) != digest:
            raise ValueError('OEM critical source pin differs: ' + name)
    return True

def qualify_ready(r):
    if any(r.get(k) is not True for k in ['compiled','station_ready','current_session_generation_ready','queued_profile_not_ready','no_board_ring_bank_clock_timeout_change','no_payload_logging']):
        raise ValueError('Unqualified profile-ready runtime')
    qualify_runtime(r['base'])
    from ProfileReadySource import station,STATION_SHA
    parent_source=Path(r['parent_source']).read_bytes()
    expected_source=station(parent_source)
    if r.get('eapol_voice') is True and r.get('oem_tcl_v1') is True:
        raise ValueError('Conflicting station transmit formats')
    if r.get('eapol_voice') is True:
        from StationTxPriority import station as with_tx_priority
        expected_source=with_tx_priority(expected_source)
    if r.get('oem_tcl_v1') is True:
        from StationOemMetadata import station as with_oem_metadata
        expected_source=with_oem_metadata(expected_source)
    if sha(r['parent_source'])!=STATION_SHA or expected_source!=Path(r['source']).read_bytes():
        raise ValueError('Readiness actual parent/source differs')
    if sha(r['source'])!=r['source_sha256'] or sha(r['object'])!=r['object_sha256'] or len(r['retained_objects'])!=125:
        raise ValueError('Readiness source/object boundary differs')
    if r['command'].count('-ivfsoverlay')!=1 or r['command'][r['command'].index('-ivfsoverlay')+1]!=r['base']['overlay']:
        raise ValueError('Readiness OEM codec overlay differs')
    for path,digest in {**r['retained_objects'],**r['consumed_inputs']}.items():
        if sha(path)!=digest:raise ValueError('Readiness consumed input differs')
    if sha(r['link'][r['link'].index('-o')+1])!=r['binding_sha256']:raise ValueError('Readiness full binding differs')
    for path,digest in r['source_inputs'].items():
        if sha(ROOT/path)!=digest:raise ValueError('Readiness source pin differs')
    return True


def qualify_wire(r):
    if any(r.get(k) is not True for k in ['compiled','station_wire','mandatory_nonmlo_wire','no_board_ring_bank_clock_timeout_change','no_payload_logging']):
        raise ValueError('Unqualified OEM station wire')
    qualify_runtime(r['base'])
    from StationWireSource import association,station,ASSOC_SHA,STATION_SHA
    if r['vendor_module_sha256']!='33869cd650843656e216b092809b9cd7327865abb1b6b9dfcd55399abd600d76' or r['vendor_commit']!='d50b305f7da9e14715a25120a4ac7b1a4b8b97c3':
        raise ValueError('Wrong station OEM evidence')
    if sha(r['parent_source'])!=STATION_SHA or sha(r['parent_codec'])!=ASSOC_SHA or station(Path(r['parent_source']).read_bytes())!=Path(r['source']).read_bytes() or association(Path(r['parent_codec']).read_bytes())!=Path(r['codec']).read_bytes():
        raise ValueError('Station wire source/codec differs')
    for name,key in [('source','source_sha256'),('codec','codec_sha256'),('object','object_sha256'),('overlay','overlay_sha256')]:
        if sha(r[name])!=r[key]:raise ValueError('Station wire actual '+name+' differs')
    expected={'version':0,'roots':[{'type':'file','name':r['parent_codec'],'external-contents':r['codec']}]}
    if read(r['overlay'])!=expected or r['command'].count('-ivfsoverlay')!=1 or r['command'][r['command'].index('-ivfsoverlay')+1]!=r['overlay']:
        raise ValueError('Station codec overlay differs')
    if len(r['retained_objects'])!=125:raise ValueError('Station wire retained runtime differs')
    for path,digest in {**r['retained_objects'],**r['consumed_inputs']}.items():
        if sha(path)!=digest:raise ValueError('Station wire consumed input differs')
    if sha(r['link'][r['link'].index('-o')+1])!=r['binding_sha256']:raise ValueError('Station wire binding differs')
    for name,digest in r['source_inputs'].items():
        if sha(ROOT/name)!=digest:raise ValueError('Station wire source pin differs')
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
    if a!=report['service_assets'] or a!=report['core']['assets'] or not a.get('station_assets') or not a.get('crypto_self_test'):
        raise ValueError('Station authentication/assets differ')
    if a.get('helper_profile_ready'):
        if a.get('crypto_source_unchanged') is not False or a.get('crypto_algorithms_unchanged') is not True or a.get('ready_generation_status_only') is not True:
            raise ValueError('Helper readiness scope differs')
        from build_wifi_station_assets import source as helper_base
        from ProfileReadySource import helper
        expected_helper=helper(helper_base())
    else:
        if a.get('crypto_source_unchanged') is not True:raise ValueError('Unexpected helper source change')
        from build_wifi_station_assets import source as helper_base
        expected_helper=helper_base()
    if sha(runtime/'elden-wifi-supplicant.c')!=a['helper_source_sha256'] or (runtime/'elden-wifi-supplicant.c').read_bytes()!=expected_helper:
        raise ValueError('Actual signed helper source differs')
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
    station_runtime=report['station_runtime']
    while station_runtime.get('oem_eapol_critical'):station_runtime=station_runtime['base']
    original=station_runtime
    while original.get('station_hif') or original.get('station_diagnostic') or original.get('station_wire') or original.get('station_ready'):original=original['base']
    if original['scan_parent']!=parent['portable_scan_runtime']:raise ValueError('Station scan chain differs')
    if report['network_bridge']!=parent['network_bridge'] or report['optional_runtime']!=parent['optional_runtime']:
        raise ValueError('Station OS bridge/rules changed')
    if bool(station_runtime.get('station_ready'))!=bool(report['service_assets'].get('helper_profile_ready')):
        raise ValueError('Readiness kernel/helper pairing differs')
    if report['entry_delta']!=7124 or report['original_apple_executables_hashed']!=30 or not report['original_physical_return_preserved']:
        raise ValueError('Station entry/return changed')
    for name,digest in report['source_inputs'].items():
        if sha(ROOT/name)!=digest:raise ValueError('Station full source pin differs: '+name)
    for name,key in [('Native.o',report['station_worker']['object_sha256']),('WifiRuntimeMsiBinding.o',r['binding_sha256'])]:
        row=report['component_objects'][name]
        if row['sha256']!=key or sha(row['path'])!=key:raise ValueError('Station loaded member differs')
    return True
