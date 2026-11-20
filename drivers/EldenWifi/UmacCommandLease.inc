/* SPDX-License-Identifier: BSD-3-Clause-Clear */
/* Match the OEM force-wake scope to a command, retaining the platform hold. */
static unsigned elden_umac_command_notes;
int elden_wifi_umac_command_begin(struct ath12k_base *ab,u32 command,bool *taken)
{
    struct ath12k_pci *pci;
    struct mhi_device *dev;
    u32 request,before,after=0xffffffffU;
    unsigned checks;
    int rc;
    if(!taken)return -EINVAL;
    *taken=false;
    if(!ab||ab->hw_rev!=ATH12K_HW_PEACH_HW20||!elden_umac_device)return 0;
    pci=ath12k_pci_priv(ab);dev=pci&&pci->mhi_ctrl?pci->mhi_ctrl->mhi_dev:NULL;
    if(dev!=elden_umac_device||elden_umac_owner!=ab||!ab->mem||ab->mem_len<0x84044U)return -ENODEV;
    request=ath12k_pci_read32(ab,ELDEN_UMAC_WAKE_OFFSET);
    before=ath12k_pci_read32(ab,ELDEN_UMAC_SCRATCH_OFFSET);
    rc=mhi_device_get_sync(dev);
    if(rc)return rc;
    ath12k_pci_write32(ab,ELDEN_UMAC_WAKE_OFFSET,1);
    for(checks=0;checks<ELDEN_UMAC_CHECKS;checks++){
        after=ath12k_pci_read32(ab,ELDEN_UMAC_SCRATCH_OFFSET);
        if(after==ELDEN_UMAC_AWAKE||after==0xffffffffU)break;
        if(checks+1<ELDEN_UMAC_CHECKS)udelay(ELDEN_UMAC_DELAY_US);
    }
    rc=after==ELDEN_UMAC_AWAKE?0:after==0xffffffffU?-EIO:-ETIMEDOUT;
    if(rc){
        if(request<=1)ath12k_pci_write32(ab,ELDEN_UMAC_WAKE_OFFSET,request);
        mhi_device_put(dev);
    }else *taken=true;
    if(elden_umac_command_notes++<32)
        ath12k_warn(ab,"ELDEN_UMAC_COMMAND cmd=%x rc=%d old=%x/%x new=%x checks=%u extra-ref=%u; no-ring-writes\n",
            command,rc,request,before,after,checks<ELDEN_UMAC_CHECKS?checks+1:ELDEN_UMAC_CHECKS,*taken);
    return rc;
}
void elden_wifi_umac_command_end(struct ath12k_base *ab,bool taken)
{
    if(!taken)return;
    /* Same serialized wireless executor and retained platform owner. A mismatch
     * cannot be balanced by guessing another controller; retain to reset. */
    if(elden_umac_owner!=ab||!elden_umac_device){
        ath12k_warn(ab,"ELDEN_UMAC_COMMAND end-refused owner-changed=1\n");return;
    }
    mhi_device_put(elden_umac_device);
}
