/* SPDX-License-Identifier: GPL-2.0-only */
extern "C" int elden_pcie_dma_cleanup_admit(const void *provider,uint64_t epoch){
    Context *c=runtime_context;
    if(!c||provider!=c||epoch!=c->wlan_epoch||!c->runtime_thread||current_thread()!=c->runtime_thread||
       !c->runtime_entered||!c->runtime_stack_started||c->runtime_returned||c->runtime_stage!=4||
       !c->runtime_cleanup_deadline||now(nullptr)>=c->runtime_cleanup_deadline)return -19;
    /* cleanup admission checks retained root/endpoint state, not the revoked
     * public WLAN epoch. Power/PERST cannot be released before quiescence. */
    int fault=__atomic_load_n(&c->msi.irq_error,__ATOMIC_ACQUIRE);if(fault)return fault;
    int rc=transport_admit(c,true);return rc?rc:elden_wifi_smmu_ready()?0:-5;
}
extern "C" int elden_wifi_runtime_bind(void *consumer){
    Context *c=runtime_context;
    if(!consumer||!c||!c->runtime_entered||c->runtime_returned||c->transport_cleanup||ml_at_interrupt_context())return -19;
    if(c->runtime_consumer&&c->runtime_consumer!=consumer)return -16;
    int rc=transport_admit(c,false);if(!rc)rc=elden_wlan_qmi_bind((struct device *)consumer,c,c->wlan_epoch);
    if(!rc)c->runtime_consumer=consumer;
    log("\nELDEN_WIFI_RUNTIME bind=%d epoch=%llu\n",rc,(unsigned long long)c->wlan_epoch);return rc;
}
extern "C" int elden_wifi_runtime_unbind(void *consumer){
    Context *c=runtime_context;if(!c||!consumer||consumer!=c->runtime_consumer||ml_at_interrupt_context())return -19;
    int rc=elden_wlan_qmi_unbind((struct device *)consumer,c,c->wlan_epoch);if(!rc)c->runtime_consumer=nullptr;
    log("\nELDEN_WIFI_RUNTIME unbind=%d\n",rc);return rc;
}
extern "C" int elden_wifi_runtime_enable_master(void){
    Context *c=runtime_context;if(!c)return -19;
    uint32_t msi=0;int rc=runtime_master_ready(c);
    if(!rc)rc=elden_pcie_cfg_read(&c->config,(int)c->config.msi_cap,4,&msi,false);
    if(!rc&&!(msi&(1u<<16)))rc=-11;
    if(!rc)rc=elden_pcie_cfg_master(&c->config,true);
    log("\nELDEN_WIFI_RUNTIME master=%d command=%x attempted=%u\n",rc,c->config.command,(unsigned)c->config.master_attempted);return rc;
}
