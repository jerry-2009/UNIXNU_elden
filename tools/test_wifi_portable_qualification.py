"""Check actual portable source/object/owner declaration and menu boundaries."""
import argparse,copy,json,tomllib
from pathlib import Path
from wifi_network17_boot import qualify_components,menu

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();report=json.loads(args.report.read_text());qualify_components(report)
    if not report.get('portable_scan_trial'):raise ValueError('Not a portable candidate')
    q=dict(report,network_bridge=True,wifi_service=True,mode=0,root_trial=True,
        endpoint_trial=True,smmu_domain=True,memory_detail=True,segmented_memory=True,
        unique_memory=True,prefault_memory=True,mhi_runtime=True,control_transport_bound=True,
        firmware_qdss_config=True,runtime_owned_cleanup=True,runtime_platform_shutdown=True,
        runtime_platform_budget=True,platform_physical_fence=True)
    cases=0
    for mutation in ['pair','count','scope','donor','unit','native','opt-in','memory','reset','network','actual-link']:
        changed=copy.deepcopy(report);runtime=changed['portable_scan_runtime']
        if mutation=='pair':changed['portable_scan_trial']=False
        elif mutation=='count':runtime['new_runtime_count']=125
        elif mutation=='scope':runtime['changed_runtime_units']=['qmi.c']
        elif mutation=='donor':runtime['donor']['commit']='0'*40
        elif mutation=='unit':runtime['portable_units']['core.c']['source_sha256']='0'*64
        elif mutation=='native':runtime['portable_native']['object_sha256']='0'*64
        elif mutation=='opt-in':runtime['portable_native']['command'].remove('-DELDEN_WIFI_PORTABLE_SCAN_TRIAL=1')
        elif mutation=='memory':runtime['original_firmware_memory_lifecycle_retained']=False
        elif mutation=='reset':runtime['physical_return_contract_retained']=False
        elif mutation=='network':runtime['no_fake_network_interface']=False
        else:runtime['link']=runtime['portable_parent']['link']
        try:qualify_components(changed)
        except (ValueError,KeyError):cases+=1
        else:raise AssertionError('Portable malformed candidate accepted: '+mutation)
    chosen=tomllib.loads(menu(q));normal=tomllib.loads(menu(dict(q,portable_scan_trial=False)))
    if chosen['boot']!=normal['boot'] or chosen['entry'][1:]!=normal['entry'][1:] or chosen['entry'][0]['args']!=normal['entry'][0]['args']:
        raise AssertionError('Portable changes boot args or recovery/fallback')
    result=dict(passed=True,rejected_mutations=cases,actual_code_and_binding_qualified=True,original_args_and_return_preserved=True,hardware_tested=False)
    args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

if __name__=='__main__':main()
