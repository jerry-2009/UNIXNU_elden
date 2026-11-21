"""Diagnostic wrappers around exact prepared shutdown calls; reversible bytes."""
import re

CALLS={
 'nw_wifi.c':{'void nw_wifi_stop(void)':[
  'nw_mainline_shutdown();','nw_wifi_control_shutdown();','ath12k_wifi7_pci_exit();',
  'nw_qrtr_mhi_unregister();','bus_unregister(&mhi_bus_type);','lx_exit_ieee80211_exit();',
  'lx_exit_cfg80211_exit();','nw_wifi_buffer_pool_configure(0);']},
 'pci.c':{'static void ath12k_pci_remove(struct pci_dev *pdev)':[
  'ath12k_pci_set_irq_affinity_hint(ab_pci, NULL);','ath12k_pci_power_down(ab, false);',
  'cancel_work_sync(&ab->reset_work);','cancel_work_sync(&ab->dump_work);',
  'ath12k_core_hw_group_cleanup(ab->ag);','ath12k_core_deinit(ab);','ath12k_fw_unmap(ab);',
  'ath12k_mhi_unregister(ab_pci);','ath12k_pci_free_irq(ab);','ath12k_pci_msi_free(ab_pci);',
  'ath12k_pci_free_region(ab_pci);','ath12k_hal_srng_deinit(ab);','ath12k_ce_free_pipes(ab);',
  'ab_pci->device_family_ops->arch_deinit(ab);','ath12k_core_free(ab);']},
 'core.c':{
  'void ath12k_core_hw_group_cleanup(struct ath12k_hw_group *ag)':[
   'mutex_lock(&ag->mutex);','ath12k_core_hw_group_stop(ag);','mutex_lock(&ab->core_lock);','ath12k_core_stop(ab);'],
  'static void ath12k_core_stop(struct ath12k_base *ab)':[
   'ath12k_link_sta_rhash_tbl_destroy(ab);','ath12k_core_to_group_ref_put(ab);','ath12k_qmi_firmware_stop(ab);',
   'ath12k_acpi_stop(ab);','ath12k_dp_rx_pdev_reo_cleanup(ab);','ath12k_hif_stop(ab);',
   'ath12k_wmi_detach(ab);','ath12k_dp_cmn_device_deinit(ath12k_ab_to_dp(ab));'],
  'static void ath12k_core_hw_group_stop(struct ath12k_hw_group *ag)':[
   'ath12k_mac_unregister(ag);','ath12k_core_device_cleanup(ab);','ath12k_mac_destroy(ag);'],
  'static void ath12k_core_soc_destroy(struct ath12k_base *ab)':[
   'ath12k_hif_power_down(ab, false);','ath12k_reg_free(ab);','ath12k_debugfs_soc_destroy(ab);','ath12k_qmi_deinit_service(ab);'],
  'void ath12k_core_deinit(struct ath12k_base *ab)':[
   'ath12k_core_hw_group_destroy(ab->ag);','ath12k_core_hw_group_unassign(ab);','ath12k_core_panic_notifier_unregister(ab);']}
}

def patch(name,data):
    original=data.decode();text=original;changes=[];site=0
    for signature,calls in CALLS[name].items():
        marker=signature+'\n{' if name!='nw_wifi.c' else signature+' {'
        if text.count(marker)!=1:raise ValueError('Shutdown signature differs: '+signature)
        begin=text.index(marker);end=text.index('\n}',begin)+2;body=text[begin:end]
        function=signature.split('(')[0].split()[-1]
        for call in calls:
            if body.count(call)!=1:raise ValueError('Shutdown call differs: '+call)
            site+=1;label=f'{name}:{site} {function}'
            # Compound statements preserve even an original unbraced if/else.
            before='{ lx_log(3, "ELDEN_STOP '+label+' enter\\n"); '
            after=' lx_log(3, "ELDEN_STOP '+label+' leave\\n"); }'
            replacement=before+call+after
            body=body.replace(call,replacement,1);changes.append((replacement,call))
        text=text[:begin]+body+text[end:]
    recovered=text
    for wrapper,call in reversed(changes):
        if recovered.count(wrapper)!=1:raise ValueError('Nonunique reversible wrapper')
        recovered=recovered.replace(wrapper,call,1)
    if recovered!=original:raise ValueError('Stop trace changed original statements')
    return text.encode()
