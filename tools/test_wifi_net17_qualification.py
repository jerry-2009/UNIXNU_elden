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
    if report.get('mhi_hold_trial'):
        for name in ('lease','pair','scope','import'):
            selected=copy.deepcopy(report)
            if name=='lease':selected['mac_phy_stride_runtime']['lease_delta_reversible']=False
            elif name=='pair':selected['network_worker']['mhi_hold_trial']=False
            elif name=='scope':selected['mac_phy_stride_runtime']['changed_units']=['ath12k_wmi.o','ath12k_ce.o']
            else:selected['mac_phy_stride_runtime']['added_native_import']='_other_hold'
            try:qualify_components(selected)
            except ValueError:cases+=1
            else:raise AssertionError('Mutated MHI lease accepted: '+name)
    if report.get('umac_hold_trial'):
        for name in ('reversible','pair','scope','import','request','status','ready','bound','both'):
            selected=copy.deepcopy(report);runtime=selected['mac_phy_stride_runtime']
            if name=='reversible':runtime['umac_delta_reversible']=False
            elif name=='pair':selected['network_worker']['umac_hold_trial']=False
            elif name=='scope':runtime['changed_units']=['ath12k_wmi.o','ath12k_ce.o']
            elif name=='import':runtime['added_native_import']='_other_hold'
            elif name=='request':runtime['umac_request_offset']=0x3008
            elif name=='status':runtime['umac_status_offset']=0x4040
            elif name=='ready':runtime['umac_ready_value']=1
            elif name=='bound':runtime['umac_polling_bound_ms']=500
            else:selected['mhi_hold_trial']=True
            try:qualify_components(selected)
            except ValueError:cases+=1
            else:raise AssertionError('Mutated OEM UMAC wake accepted: '+name)
    if report.get('vdev_empty_mlo_array'):
        for name in ('reversible','tag','bytes','parent','source','scope','report'):
            selected=copy.deepcopy(report);runtime=selected['mac_phy_stride_runtime']
            if name=='reversible':runtime['vdev_array_delta_reversible']=False
            elif name=='tag':runtime['vdev_array_tag']=0
            elif name=='bytes':runtime['vdev_array_bytes']=8
            elif name=='parent':runtime['vdev_parent_wmi_source_sha256']='0'*64
            elif name=='source':runtime['vdev_fixed_wmi_source_sha256']='0'*64
            elif name=='scope':runtime['vdev_other_and_mlo_streams_unchanged']=False
            else:selected['vdev_empty_mlo_array']=False
            try:qualify_components(selected)
            except ValueError:cases+=1
            else:raise AssertionError('Mutated VDEV array repair accepted: '+name)
    if report.get('ce3_direct_trial'):
        for name in ('reversible','ring','offset','qmi','policy','report'):
            selected=copy.deepcopy(report);runtime=selected['mac_phy_stride_runtime']
            if name=='reversible':runtime['ce3_direct_delta_reversible']=False
            elif name=='ring':runtime['ce3_ring_id']=68
            elif name=='offset':runtime['ce3_hp_offset']=0x1b88400
            elif name=='qmi':runtime['ce3_qmi_shadow_config_unchanged']=False
            elif name=='policy':runtime['other_ce_mhi_irq_firmware_policy_unchanged']=False
            else:selected['ce3_direct_trial']=False
            try:qualify_components(selected)
            except ValueError:cases+=1
            else:raise AssertionError('Mutated CE3 direct contrast accepted: '+name)
    if report.get('ce3_inspect_trial'):
        for name in ('first','count','reads','privacy','worker','import','report'):
            selected=copy.deepcopy(report);runtime=selected['mac_phy_stride_runtime']
            if name=='first':runtime['first_failure_only']=False
            elif name=='count':runtime['max_descriptor_records']=100
            elif name=='reads':runtime['register_read_count']=100
            elif name=='privacy':runtime['no_payload_or_command_value_logging']=False
            elif name=='worker':selected['network_worker']['ce3_inspect_trial']=False
            elif name=='import':runtime['added_inspect_native_import']='_unexpected'
            else:selected['ce3_inspect_trial']=False
            try:qualify_components(selected)
            except ValueError:cases+=1
            else:raise AssertionError('Mutated CE3 inspection accepted: '+name)
    if report.get('ce3_timeline_trial'):
        for name in ('reversible','events','reads','exports','scope','report'):
            selected=copy.deepcopy(report);runtime=selected['mac_phy_stride_runtime']
            if name=='reversible':runtime['timeline_delta_reversible']=False
            elif name=='events':runtime['timeline_events_max']=100
            elif name=='reads':runtime['timeline_reads_per_event']=100
            elif name=='exports':runtime['runtime_added_exports']=['_unexpected']
            elif name=='scope':runtime['changed_units']=['ath12k_wmi.o','ath12k_pci.o']
            else:selected['ce3_timeline_trial']=False
            try:qualify_components(selected)
            except ValueError:cases+=1
            else:raise AssertionError('Mutated CE3 timeline accepted: '+name)
    if report.get('window_reselect_trial'):
        for name in ('reversible','peach','order','report'):
            selected=copy.deepcopy(report);runtime=selected['mac_phy_stride_runtime']
            if name=='reversible':runtime['window_delta_reversible']=False
            elif name=='peach':runtime['window_peach_only']=False
            elif name=='order':runtime['window_lock_value_readback_preserved']=False
            else:selected['window_reselect_trial']=False
            try:qualify_components(selected)
            except ValueError:cases+=1
            else:raise AssertionError('Mutated window reselection accepted: '+name)
    if report.get('pci_state_trace_trial'):
        for name in ('reversible','count','reads','writes','existing','restore','privacy','report'):
            selected=copy.deepcopy(report);runtime=selected['mac_phy_stride_runtime']
            if name=='reversible':runtime['pci_state_trace_reversible']=False
            elif name=='count':runtime['pci_state_write_records_max']=100
            elif name=='reads':runtime['pci_state_read_records_max']=100
            elif name=='writes':runtime['pci_state_no_new_mmio_writes']=False
            elif name=='existing':runtime['pci_state_existing_hook_not_replaced']=False
            elif name=='restore':runtime['pci_state_hook_owned_restore']=False
            elif name=='privacy':runtime['pci_state_payload_logging']=True
            else:selected['pci_state_trace_trial']=False
            try:qualify_components(selected)
            except ValueError:cases+=1
            else:raise AssertionError('Mutated PCI state observation accepted: '+name)
    if report.get('wifi_battery_runtime_trial'):
        for name in ('pair','chemistry','no_set','controls','report','archive','loaded','loaded-member'):
            selected=copy.deepcopy(report)
            if name=='pair':selected['network_worker']['wifi_battery_runtime_trial']=False
            elif name=='chemistry':selected['battery_admission']['chemistry_two_gauges_epoch_age_checked']=False
            elif name=='no_set':selected['battery_admission']['radio_only_no_charger_set']=False
            elif name=='controls':selected['battery_admission']['controls_and_charger_permission_unchanged']=False
            elif name=='report':selected['wifi_battery_runtime_trial']=False
            elif name=='archive':selected['battery_admission']['pmic_archive_sha256']='0'*64
            elif name=='loaded':selected.pop('battery_loaded_archives')
            else:selected['battery_loaded_archives']['wcn']['member_sha256']='0'*64
            try:qualify_components(selected)
            except ValueError:cases+=1
            else:raise AssertionError('Mutated radio-only admission accepted: '+name)
    if report.get('umac_access_trial'):
        for name in ('reversible','first','pair','bound','ring','report'):
            selected=copy.deepcopy(report);runtime=selected['mac_phy_stride_runtime']
            if name=='reversible':runtime['umac_access_reversible']=False
            elif name=='first':runtime['umac_access_first_pmf_only']=False
            elif name=='pair':runtime['umac_access_balanced_extra_mhi']=False
            elif name=='bound':runtime['umac_access_poll_bound_ms']=500
            elif name=='ring':runtime['umac_access_ring_writes']=1
            else:selected['umac_access_trial']=False
            try:qualify_components(selected)
            except ValueError:cases+=1
            else:raise AssertionError('Mutated first-access contrast accepted: '+name)
    if report.get('umac_command_lease_trial'):
        for name in ('reversible','first','pair','bound','ring','report','send','both'):
            selected=copy.deepcopy(report);runtime=selected['mac_phy_stride_runtime']
            if name=='reversible':runtime['umac_access_reversible']=False
            elif name=='first':runtime['umac_access_first_pmf_only']=True
            elif name=='pair':runtime['umac_access_balanced_extra_mhi']=False
            elif name=='bound':runtime['umac_access_poll_bound_ms']=500
            elif name=='ring':runtime['umac_access_ring_writes']=1
            elif name=='report':selected['umac_command_lease_trial']=False
            elif name=='send':runtime['umac_lease_spans_original_send']=False
            else:runtime['umac_access_trial']=True
            try:qualify_components(selected)
            except ValueError:cases+=1
            else:raise AssertionError('Mutated command-scoped lease accepted: '+name)
    if report.get('oem_init_mode_trial'):
        for name in ('oem_init_delta_reversible','oem_init_peach_only','oem_init_firmware_preferred_mode','oem_init_firmware_physical_band_map','oem_init_single_pdev_alias_unchanged','oem_init_no_post_ready_switch','report'):
            selected=copy.deepcopy(report)
            if name=='report':selected['oem_init_mode_trial']=False
            else:selected['mac_phy_stride_runtime'][name]=False
            try:qualify_components(selected)
            except ValueError:cases+=1
            else:raise AssertionError('Mutated OEM-init contract accepted: '+name)
    if report.get('sideband_pins_trial'):
        for name in ('pins','cold','retained','report'):
            selected=copy.deepcopy(report)
            if name=='pins':selected['battery_admission']['sideband_gpio_indices']=[18,19,201]
            elif name=='cold':selected['battery_admission']['sideband_cold_before_votes']=False
            elif name=='retained':selected['battery_admission']['sideband_unknown_state_retained']=False
            else:selected['sideband_pins_trial']=False
            try:qualify_components(selected)
            except ValueError:cases+=1
            else:raise AssertionError('Mutated sideband pin contract accepted: '+name)
    if report.get('startup_contract_trial'):
        for name in ('startup_contract_reversible','startup_contract_no_new_device_writes',
                     'startup_contract_par_cpu_only','startup_contract_fw_status_parsed',
                     'startup_contract_wake_db_owner_checked','reads','payload','report'):
            selected=copy.deepcopy(report)
            if name=='report':selected['startup_contract_trial']=False
            elif name=='reads':selected['mac_phy_stride_runtime']['startup_contract_par_reads_max']=4
            elif name=='payload':selected['mac_phy_stride_runtime']['startup_contract_payload_logging']=True
            else:selected['mac_phy_stride_runtime'][name]=False
            try:qualify_components(selected)
            except ValueError:cases+=1
            else:raise AssertionError('Mutated startup contract accepted: '+name)
    if report.get('board_state_trial'):
        for name in ('pair','controls','boundaries','import','provider','pins','rails','report'):
            selected=copy.deepcopy(report)
            if name=='pair':selected['battery_admission']['board_state_trial']=False
            elif name=='controls':selected['mac_phy_stride_runtime']['board_state_no_device_controls']=False
            elif name=='boundaries':selected['mac_phy_stride_runtime']['board_state_boundaries']=[12,9]
            elif name=='import':selected['mac_phy_stride_runtime']['board_state_added_import']='_other'
            elif name=='provider':selected['battery_admission']['board_state_no_device_controls']=False
            elif name=='pins':selected['battery_admission']['board_state_gpio_indices']=[16,18,19,201]
            elif name=='rails':selected['battery_admission']['board_state_rails']=7
            else:selected['board_state_trial']=False
            try:qualify_components(selected)
            except ValueError:cases+=1
            else:raise AssertionError('Mutated board state accepted: '+name)
    q=dict(profile='wifi-network-17',network_bridge=True,wifi_service=True,
        mode=0,root_trial=True,endpoint_trial=True,smmu_domain=True,memory_detail=True,
        segmented_memory=True,unique_memory=True,prefault_memory=True,mhi_runtime=True,
        control_transport_bound=True,firmware_qdss_config=True,runtime_owned_cleanup=True,
        runtime_platform_shutdown=True,runtime_platform_budget=True,platform_physical_fence=True)
    if menu(q)!=route_menu(q):raise AssertionError('Boot dispatcher missed new route')
    if report.get('mhi_hold_trial'):
        held=dict(q,mhi_hold_trial=True)
        import tomllib
        if tomllib.loads(menu(held))['entry'][0]['args']!=tomllib.loads(menu(q))['entry'][0]['args']:
            raise AssertionError('MHI lease changed inherited boot arguments')
    if report.get('umac_hold_trial'):
        held=dict(q,umac_hold_trial=True)
        import tomllib
        if tomllib.loads(menu(held))['entry'][0]['args']!=tomllib.loads(menu(q))['entry'][0]['args']:
            raise AssertionError('UMAC trial changed inherited boot arguments')
    text=menu(q)
    if report.get('wifi_battery_runtime_trial'):
        import tomllib
        original=tomllib.loads(text);new=tomllib.loads(menu(dict(q,wifi_battery_runtime_trial=True)))
        if new['entry'][0]['args']!=original['entry'][0]['args'].replace('epd=2','epd=0',1) or new['entry'][1:]!=original['entry'][1:] or new['boot']!=original['boot']:
            raise AssertionError('Radio-only mode changed options beyond disabling PD experiment')
    import tomllib
    config=tomllib.loads(text)
    if config['boot']!={'timeout':8,'fallback_timeout':120,'default':'xnu'}:raise AssertionError('Countdown or fallback changed')
    if len(config['entry'][0]['args'].replace('@SESSION@','0'*16).encode())>1023:raise AssertionError('Boot argument ABI exceeded')
    result=dict(passed=True,mutation_cases=cases,menu_dispatch=True,countdown_and_fallback_preserved=True,
        actual_component_report_qualified=True,hardware_tested=False)
    args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))


if __name__=='__main__':main()
