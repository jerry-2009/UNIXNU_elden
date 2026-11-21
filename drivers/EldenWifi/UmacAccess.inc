/* SPDX-License-Identifier: BSD-3-Clause-Clear */
/* One first-access contrast of the actual OEM handshake, not ring recovery. */
static unsigned elden_umac_access_seen;
int elden_wifi_umac_access_first(struct ath12k_base *ab)
{
    struct ath12k_pci *pci;
    struct mhi_device *dev;
    u32 before,request,after=0xffffffffU;
    unsigned checks;
    int rc;
    if(!ab||ab->hw_rev!=ATH12K_HW_PEACH_HW20||!elden_wifi_umac_hold_requested())return 0;
    if(__atomic_exchange_n(&elden_umac_access_seen,1u,__ATOMIC_ACQ_REL))return 0;
    pci=ath12k_pci_priv(ab);dev=pci&&pci->mhi_ctrl?pci->mhi_ctrl->mhi_dev:NULL;
    if(!dev||dev!=elden_umac_device||elden_umac_owner!=ab||!ab->mem||ab->mem_len<0x84044U)return -ENODEV;
    before=ath12k_pci_read32(ab,ELDEN_UMAC_SCRATCH_OFFSET);
    request=ath12k_pci_read32(ab,ELDEN_UMAC_WAKE_OFFSET);
    rc=mhi_device_get_sync(dev);
    if(rc){ath12k_warn(ab,"ELDEN_UMAC_ACCESS mhi-get=%d no-write=1\n",rc);return rc;}
    ath12k_pci_write32(ab,ELDEN_UMAC_WAKE_OFFSET,1);
    for(checks=0;checks<ELDEN_UMAC_CHECKS;checks++){
        after=ath12k_pci_read32(ab,ELDEN_UMAC_SCRATCH_OFFSET);
        if(after==ELDEN_UMAC_AWAKE||after==0xffffffffU)break;
        if(checks+1<ELDEN_UMAC_CHECKS)udelay(ELDEN_UMAC_DELAY_US);
    }
    rc=after==ELDEN_UMAC_AWAKE?0:after==0xffffffffU?-EIO:-ETIMEDOUT;
    /* Existing platform hold remains owned. Drop only this extra MHI reference;
     * failure restores only a known prior0/1 request, without ring writes. */
    if(rc&&(request==0||request==1))ath12k_pci_write32(ab,ELDEN_UMAC_WAKE_OFFSET,request);
    mhi_device_put(dev);
    ath12k_warn(ab,"ELDEN_UMAC_ACCESS result=%d before=%x after=%x prior-request=%x checks=%u ring-writes=0\n",
        rc,before,after,request,checks<ELDEN_UMAC_CHECKS?checks+1:ELDEN_UMAC_CHECKS);
    return rc;
}
