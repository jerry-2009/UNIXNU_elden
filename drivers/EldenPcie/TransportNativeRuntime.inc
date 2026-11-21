/* SPDX-License-Identifier: GPL-2.0-only */
static int transport_admit(void *p,bool cleanup){
    Context *c=static_cast<Context *>(p);
    if(!c||c!=__atomic_load_n(&active,__ATOMIC_ACQUIRE)||!c->endpoint_confirmed||
       c->endpoint.epoch!=c->wlan_epoch||!c->root.clocks_ready||!c->root.perst_high||
       !c->bar0_map.va||__atomic_load_n(&stopped,__ATOMIC_ACQUIRE)||ml_at_interrupt_context())return -19;
    if(cleanup)return c->transport_cleanup?0:-11;
    int rc=admit(c,c->wlan_epoch);return rc?rc:elden_wlan_power_ready(c,c->wlan_epoch);
}
static int transport_cfg_read(void *p,uint32_t off,uint32_t *value){return static_cast<Context *>(p)->maps[EldenPcieConfig].read(off,value);}
static int transport_cfg_write(void *p,uint32_t off,uint32_t value){return static_cast<Context *>(p)->maps[EldenPcieConfig].write(off,value);}
/* This component does not include the MHI execution/drain provider yet.
 * Refuse master enable until that provider is wired and independently checked. */
static int transport_master_ready(void *){return -95;}
static int transport_msi_admit(void *p){
    int rc=transport_admit(p,false);if(rc)return rc;
    EldenWifiDmaStatus s={};rc=elden_wifi_dma_status(&s);
    Context *c=static_cast<Context *>(p);
    return rc?rc:(s.run==2&&!s.stopping&&!s.first_error&&s.epoch==c->wlan_epoch&&elden_wifi_smmu_ready())?0:-11;
}
static int transport_quiesced(void *p){
    Context *c=static_cast<Context *>(p);uint32_t id=0,command=0;
    /* No master write is permitted in this variant. Once one is attempted,
     * only the future real MHI shutdown provider may attest quiescence. */
    if(c->config.master_attempted)return -95;
    int rc=elden_pcie_cfg_read(&c->config,0,4,&id,c->transport_cleanup);if(rc)return rc;
    if(id!=0x110e17cb)return -19;
    rc=elden_pcie_cfg_read(&c->config,4,2,&command,c->transport_cleanup);
    return rc?rc:(command&7)==2?0:-16;
}
static int transport_dbi_read(void *p,uint32_t off,uint32_t *v){
    if(off<EldenMsiAddrLo||off>EldenMsiStatus||(off&3))return -22;
    return static_cast<Context *>(p)->maps[EldenPcieDbi].read(off,v);
}
static int transport_dbi_write(void *p,uint32_t off,uint32_t v){
    if(off<EldenMsiAddrLo||off>EldenMsiStatus||(off&3))return -22;
    return static_cast<Context *>(p)->maps[EldenPcieDbi].write(off,v);
}
static int transport_irq_attach(void *,uint32_t id,void(*handler)(void *),void *cookie,uint32_t *flags,uint64_t *router){
    if(id!=EldenMsiIntid||ml_at_interrupt_context())return -22;
    return (int)armcpu_spi_attach(id,false,handler,cookie,flags,router);
}
static int transport_irq_mask(void *,uint32_t id,bool mask){return id==EldenMsiIntid?(int)armcpu_spi_mask(id,mask):-22;}
static void transport_wake(void *p){
    Context *c=static_cast<Context *>(p);__atomic_store_n(&c->transport_wake,1u,__ATOMIC_RELEASE);
    thread_wakeup((event_t)&c->transport_wake);
}
static void transport_run(Context *c){
    c->transport_stage=1;int rc=transport_admit(c,false);
    if(!rc)rc=elden_wifi_dma_bind(c,c->wlan_epoch);
    uint64_t sink=0;if(!rc)rc=elden_wifi_dma_msi_sink(&sink);
    c->config.io={c,transport_admit,transport_cfg_read,transport_cfg_write,transport_master_ready};
    if(!rc){c->transport_stage=2;rc=elden_pcie_cfg_open(&c->config,sink);}
    c->msi.io={c,transport_msi_admit,transport_quiesced,transport_dbi_read,transport_dbi_write,
               transport_irq_attach,transport_irq_mask,transport_wake,now,delay};
    /* This image's boot CPU/GIC affinity is0, already checked by the early
     * SMMU owner. A different route is refused, not silently accepted. */
    if(!rc){c->transport_stage=3;rc=elden_pcie_msi_prepare(&c->msi,sink,0);}
    if(!rc){c->transport_stage=4;rc=elden_pcie_msi_arm(&c->msi);}
    if(!rc)rc=transport_msi_admit(c);
    c->transport_result=rc;c->transport_ready=!rc;
    log("\nELDEN_WIFI_TRANSPORT rc=%d stage=%u cfg=%x/%x msi=%u BM=0 MHI=0\n",rc,c->transport_stage,c->config.pcie_cap,c->config.msi_cap,c->msi.state);
}
static int transport_stop(Context *c,uint64_t deadline){
    if(!c->transport_requested)return 0;
    bool locked=false;
    for(unsigned i=0;i<9000&&now(nullptr)<deadline;i++){
        unsigned expected=0;
        if(__atomic_compare_exchange_n(&c->transport_gate,&expected,1u,false,__ATOMIC_ACQUIRE,__ATOMIC_RELAXED)){locked=true;break;}
        IOSleep(1);
    }
    if(!locked)return -110;
    c->transport_cleanup=true;c->transport_ready=false;elden_wifi_dma_stop_begin();
    /* The worker is already terminal when this callback is reached. Keep DBI
     * and the cookie until reset; an entered IRQ must finish before PERST. */
    int rc=0;
    if(c->msi.state!=EldenMsiIdle)rc=elden_pcie_msi_stop(&c->msi,deadline);
    if(!rc&&c->config.ready)rc=transport_quiesced(c);
    log("\nELDEN_WIFI_TRANSPORT stop=%d msi=%u irq-active=%u master-attempted=%u\n",rc,c->msi.state,__atomic_load_n(&c->msi.irq_calls,__ATOMIC_SEQ_CST),(unsigned)c->config.master_attempted);
    __atomic_store_n(&c->transport_gate,0u,__ATOMIC_RELEASE);
    return rc;
}
static int transport_snapshot(Context *c,EldenPcieTransportStatus *s){
    if(!c){*s={};s->version=1;return 0;}
    unsigned expected=0;
    if(!__atomic_compare_exchange_n(&c->transport_gate,&expected,1u,false,__ATOMIC_ACQUIRE,__ATOMIC_RELAXED))return -11;
    *s={};s->version=1;
    s->requested=c->transport_requested;s->ready=c->transport_ready&&!__atomic_load_n(&stop_requested,__ATOMIC_ACQUIRE);
    s->stage=c->transport_stage;s->pcie_cap=c->config.pcie_cap;s->msi_cap=c->config.msi_cap;s->receiver_state=c->msi.state;
    s->error=c->transport_result;s->irq_error=__atomic_load_n(&c->msi.irq_error,__ATOMIC_ACQUIRE);
    s->pending=__atomic_load_n(&c->msi.pending,__ATOMIC_ACQUIRE);s->irq_count=__atomic_load_n(&c->msi.irq_count,__ATOMIC_ACQUIRE);
    s->irq_calls=__atomic_load_n(&c->msi.irq_calls,__ATOMIC_SEQ_CST);s->master_attempted=c->config.master_attempted;
    s->master_known=c->config.master_known;s->command=c->config.command;s->epoch=c->wlan_epoch;if(s->irq_error)s->ready=0;
    __atomic_store_n(&c->transport_gate,0u,__ATOMIC_RELEASE);return 0;
}
