/* SPDX-License-Identifier: BSD-3-Clause-Clear */
/* The OEM sends the preferred capability mode and physical band mappings in
 * WMI_INIT. A logical single-pdev interface is not a physical band table. */
static int elden_wifi_oem_init_mode(struct ath12k_base *ab,
    struct ath12k_wmi_init_cmd_arg *arg)
{
    u32 count,i,j;
    struct ath12k_wmi_pdev_band_arg bands[WMI_HOST_MAX_PDEV];
    memset(bands,0,sizeof(bands));
    if(ab->hw_rev!=ATH12K_HW_PEACH_HW20||!ab->hw_params->single_pdev_only)return 0;
    if(ab->wmi_ab.preferred_hw_mode==WMI_HOST_HW_MODE_SINGLE)return 0;
    if(ab->wmi_ab.preferred_hw_mode>=WMI_HOST_HW_MODE_MAX)return -EINVAL;
    count=ab->fw_pdev_count;
    if(!count||count>WMI_HOST_MAX_PDEV||count>MAX_RADIOS)return -EINVAL;
    for(i=0;i<count;i++){
        struct ath12k_fw_pdev *fw=&ab->fw_pdev[i];
        struct ath12k_wmi_hal_reg_capabilities_ext_arg *cap;
        if(!fw->pdev_id||fw->phy_id>=MAX_RADIOS||
           (fw->supported_bands!=WMI_HOST_WLAN_2GHZ_CAP&&
            fw->supported_bands!=WMI_HOST_WLAN_5GHZ_CAP&&
            fw->supported_bands!=WMI_HOST_WLAN_2GHZ_5GHZ_CAP))return -EINVAL;
        for(j=0;j<i;j++)if(ab->fw_pdev[j].pdev_id==fw->pdev_id||ab->fw_pdev[j].phy_id==fw->phy_id)return -EINVAL;
        cap=&ab->hal_reg_cap[fw->phy_id];
        if(cap->phy_id!=fw->phy_id)return -EINVAL;
        bands[i].pdev_id=fw->pdev_id;
        bands[i].start_freq=fw->supported_bands&WMI_HOST_WLAN_2GHZ_CAP?cap->low_2ghz_chan:cap->low_5ghz_chan;
        bands[i].end_freq=fw->supported_bands&WMI_HOST_WLAN_5GHZ_CAP?cap->high_5ghz_chan:cap->high_2ghz_chan;
        if(!bands[i].start_freq||bands[i].start_freq>bands[i].end_freq)return -EINVAL;
    }
    /* Do not change the runtime single-pdev alias0. Only WMI_INIT's metadata
     * uses the physical IDs, as in OEM init_deinit_derive_band_to_mac_param. */
    arg->hw_mode_id=ab->wmi_ab.preferred_hw_mode;arg->num_band_to_mac=count;
    memcpy(arg->band_to_mac,bands,sizeof(bands));
    ath12k_warn(ab,"ELDEN_OEM_INIT prepared-mode=%u physical-bands=%u; firmware-apply-unverified\n",arg->hw_mode_id,count);
    return 0;
}
