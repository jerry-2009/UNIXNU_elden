/* SPDX-License-Identifier: GPL-2.0-only */
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
