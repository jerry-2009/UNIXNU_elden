"""Validate complete station/helper/owner/return composition without device writes."""
import argparse,copy,json,tomllib
from pathlib import Path
from wifi_station import qualify_components,qualify_assets
from wifi_network17_boot import menu
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--report',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();r=json.loads(a.report.read_text());qualify_components(r)
    assets=qualify_assets(r,a.report.parent/'runtime',(a.report.parent/'native.macho').read_bytes(),r['service_assets']['input_trust_sha256'])
    count=0
    for name in ['station','donor','object','native','owner','firmware','return','profile','entry','helper','trust','private']:
        changed=copy.deepcopy(r)
        runtime=changed['station_runtime']
        while runtime.get('station_hif') or runtime.get('station_diagnostic') or runtime.get('station_wire') or runtime.get('station_ready'):runtime=runtime['base']
        if name=='station':changed['station_trial']=False
        elif name=='donor':runtime['station_donor']['commit']='0'*40
        elif name=='object':changed['station_runtime']['binding_sha256']='0'*64
        elif name=='native':changed['station_worker']['object_sha256']='0'*64
        elif name=='owner':changed['station_worker']['real_privileged_socket']=False
        elif name=='firmware':runtime['firmware_board_power_retained']=False
        elif name=='return':changed['original_physical_return_preserved']=False
        elif name=='profile':changed['profile']='wrong'
        elif name=='entry':changed['entry_delta']=0
        elif name=='helper':changed['service_assets']['helper_sha256']='0'*64
        elif name=='trust':changed['service_assets']['trust_sha256']='0'*64
        else:changed['station_worker']['private_header_sha256']='0'*64
        try:
            qualify_components(changed)
            qualify_assets(changed,a.report.parent/'runtime',(a.report.parent/'native.macho').read_bytes(),r['service_assets']['input_trust_sha256'])
        except (ValueError,KeyError):count+=1
        else:raise AssertionError('Malformed station declaration accepted: '+name)
    wire=r['station_runtime']
    while wire.get('station_ready'):wire=wire['base']
    if wire.get('station_wire'):
        for name in ['wire-disabled','wrong-oem','overlay-digest','unexpected-control-delta']:
            changed=copy.deepcopy(r)
            value=changed['station_runtime']
            while value.get('station_ready'):value=value['base']
            if name=='wire-disabled':value['mandatory_nonmlo_wire']=False
            elif name=='wrong-oem':value['vendor_module_sha256']='0'*64
            elif name=='overlay-digest':value['overlay_sha256']='0'*64
            else:value['no_board_ring_bank_clock_timeout_change']=False
            try:qualify_components(changed)
            except (ValueError,KeyError):count+=1
            else:raise AssertionError('Malformed station wire accepted: '+name)
    if r['station_runtime'].get('oem_eapol_critical'):
        for name in ('critical-declaration','flow-override','high-priority-notify','station-bank'):
            changed=copy.deepcopy(r)
            value=changed['station_runtime']
            if name=='critical-declaration':value['station_tx_critical']=False
            elif name=='flow-override':value['oem_flow_override']=False
            elif name=='high-priority-notify':value['oem_high_priority_notify']=False
            else:
                value['oem_single_pdev_bank']=not value.get('oem_single_pdev_bank',False)
                value['no_board_ring_bank_clock_timeout_change']=not value['oem_single_pdev_bank']
            try:qualify_components(changed)
            except (ValueError,KeyError):count+=1
            else:raise AssertionError('Malformed OEM critical TX declaration accepted: '+name)
    elif r['station_runtime'].get('station_ready'):
        for name in ['ready-disabled','enqueue-as-ready','wrong-session-generation','unpaired-helper']:
            changed=copy.deepcopy(r);value=changed['station_runtime']
            if name=='ready-disabled':value['station_ready']=False
            elif name=='enqueue-as-ready':value['queued_profile_not_ready']=False
            elif name=='wrong-session-generation':value['current_session_generation_ready']=False
            else:changed['service_assets']['helper_profile_ready']=False
            try:qualify_components(changed)
            except (ValueError,KeyError):count+=1
            else:raise AssertionError('Malformed profile readiness accepted: '+name)
    if r['station_runtime'].get('oem_tcl_v1'):
        changed=copy.deepcopy(r)
        changed['station_runtime']['oem_tcl_v1']=False
        try:qualify_components(changed)
        except (ValueError,KeyError):count+=1
        else:raise AssertionError('OEM metadata derivation accepted without its format declaration')
    q=dict(r,**assets,network_bridge=True,mode=0,root_trial=True,endpoint_trial=True,smmu_domain=True,memory_detail=True,segmented_memory=True,
      unique_memory=True,prefault_memory=True,mhi_runtime=True,control_transport_bound=True,firmware_qdss_config=True,runtime_owned_cleanup=True,
      runtime_platform_shutdown=True,runtime_platform_budget=True,platform_physical_fence=True)
    config=tomllib.loads(menu(q))
    if config['boot']!={'timeout':8,'fallback_timeout':120,'default':'xnu'} or len(config['entry'][0]['args'].replace('@SESSION@','0'*16).encode())>1023:
        raise AssertionError('Station fallback/argument limits differ')
    result=dict(passed=True,rejected_mutations=count,full_assets_owner_and_return=True,hardware_tested=False)
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
