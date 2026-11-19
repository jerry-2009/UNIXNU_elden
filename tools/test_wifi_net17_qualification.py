"""Reject changes to the actual network component/profile declaration."""
import argparse,copy,json,sys
from pathlib import Path
from wifi_network17_boot import qualify_components,menu
from bt_runtime_boot import menu as route_menu


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();report=json.loads(args.report.read_text());qualify_components(report)
    cases=0
    for name in ('profile','parent','core','hardware','worker','net','object','shape'):
        selected=copy.deepcopy(report)
        if name=='profile':selected['profile']='wifi-ce3-flow-trace'
        elif name=='parent':selected['retained_parent_kernel_sha256']='0'*64
        elif name=='core':selected['core']={}
        elif name=='hardware':selected['ce_wmi_firmware_objects_unchanged']=not report['ce_wmi_firmware_objects_unchanged']
        elif name=='worker':selected['network_worker']['generated_sources']['MhiRuntime.inc']='0'*64
        elif name=='net':selected['network_bridge']['source_sha256']='0'*64
        elif name=='object':selected['component_objects']['EldenWifiNet17.late.o']['sha256']='0'*64
        else:selected['changed_core_objects']=1
        try:qualify_components(selected)
        except (ValueError,KeyError):cases+=1
        else:raise AssertionError('Mutated component accepted: '+name)
    q=dict(profile='wifi-network-17',network_bridge=True,wifi_service=True,
        mode=0,root_trial=True,endpoint_trial=True,smmu_domain=True,memory_detail=True,
        segmented_memory=True,unique_memory=True,prefault_memory=True,mhi_runtime=True,
        control_transport_bound=True,firmware_qdss_config=True,runtime_owned_cleanup=True,
        runtime_platform_shutdown=True,runtime_platform_budget=True,platform_physical_fence=True)
    if menu(q)!=route_menu(q):raise AssertionError('Boot dispatcher missed new route')
    text=menu(q)
    import tomllib
    config=tomllib.loads(text)
    if config['boot']!={'timeout':8,'fallback_timeout':120,'default':'xnu'}:raise AssertionError('Countdown or fallback changed')
    if len(config['entry'][0]['args'].replace('@SESSION@','0'*16).encode())>1023:raise AssertionError('Boot argument ABI exceeded')
    result=dict(passed=True,mutation_cases=cases,menu_dispatch=True,countdown_and_fallback_preserved=True,
        actual_component_report_qualified=True,hardware_tested=False)
    args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))


if __name__=='__main__':main()
