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
        if name=='station':changed['station_trial']=False
        elif name=='donor':changed['station_runtime']['station_donor']['commit']='0'*40
        elif name=='object':changed['station_runtime']['binding_sha256']='0'*64
        elif name=='native':changed['station_worker']['object_sha256']='0'*64
        elif name=='owner':changed['station_worker']['real_privileged_socket']=False
        elif name=='firmware':changed['station_runtime']['firmware_board_power_retained']=False
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
    q=dict(r,**assets,network_bridge=True,mode=0,root_trial=True,endpoint_trial=True,smmu_domain=True,memory_detail=True,segmented_memory=True,
      unique_memory=True,prefault_memory=True,mhi_runtime=True,control_transport_bound=True,firmware_qdss_config=True,runtime_owned_cleanup=True,
      runtime_platform_shutdown=True,runtime_platform_budget=True,platform_physical_fence=True)
    config=tomllib.loads(menu(q))
    if config['boot']!={'timeout':8,'fallback_timeout':120,'default':'xnu'} or len(config['entry'][0]['args'].replace('@SESSION@','0'*16).encode())>1023:
        raise AssertionError('Station fallback/argument limits differ')
    result=dict(passed=True,rejected_mutations=count,full_assets_owner_and_return=True,hardware_tested=False)
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
