/* Platform reset: retained software owner -> host DMA fence -> MSI -> PERST.
 * MHI register snapshots remain diagnostic and never stand in for that proof. */
static int platform_fence_admit(void *p){
    Context *c=static_cast<Context *>(p);
    if(!c||c!=runtime_context||!c->platform_callback_returned||!c->runtime_returned||
       c->runtime_consumer||platform_config_error||c->runtime_thread!=current_thread())return -16;
    return transport_admit(c,true);
}
static int platform_dma_ready(Context *c){
    if(!c)return -22;
    const auto &f=c->platform_fence;
    if(!c->platform_callback_returned||!c->runtime_returned||c->runtime_consumer||
       !c->runtime_quiesced||f.error||f.phase!=3||!f.master_off||!f.transactions_sampled||!f.transactions_idle)return -16;
    uint32_t id=0,command=0,status=0;
    int rc=elden_pcie_cfg_read(&c->config,0,4,&id,true);if(rc)return rc;
    if(id!=0x110e17cb)return -19;
    rc=elden_pcie_cfg_read(&c->config,4,2,&command,true);if(rc)return rc;
    rc=elden_pcie_cfg_read(&c->config,(int)0x8000000a,2,&status,true);if(rc)return rc;
    return (command&7)==2&&!(status&32)?0:-71;
}
static int platform_fence_run(Context *c){
    /* No active reset-state value is accepted by this host-fence path. Keep the
     * observed MHI state/error for diagnosis, then require independent checks. */
    int admitted=platform_fence_admit(c);if(admitted)return admitted;
    int ctl=c->bar0_map.read(0x38,&c->mhi_stop.control);
    int status=c->bar0_map.read(0x48,&c->mhi_stop.status);
    log("\nELDEN_PLATFORM_MHI snapshot control=%x status=%x reads=%d/%d warm-reset=unverified\n",c->mhi_stop.control,c->mhi_stop.status,ctl,status);
    EldenPlatformFenceIo io={c,&c->config,platform_fence_admit,now,delay};
    return elden_pcie_platform_fence(&c->platform_fence,&io,now(nullptr)+1000000);
}
static int platform_assert_perst(Context *c,uint64_t deadline){
    if(c->platform_callback_returned){
        int ready=platform_dma_ready(c);if(ready)return ready;
        if(c->msi.state!=EldenMsiStopped||__atomic_load_n(&c->msi.irq_calls,__ATOMIC_SEQ_CST))return -16;
        if(!c->pins.initialized||c->pins.held)return -16;
    }
    if(now(nullptr)>=deadline)return -110;
    int rc=elden_pcie_pins_set(&c->pins,false);if(rc)return rc;
    uint64_t before=now(nullptr);IODelay(1000);uint64_t after=now(nullptr);
    if(after<before||after-before<1000||after>=deadline)return -110;
    uint32_t io=UINT32_MAX;rc=c->pin_map.read(4,&io);
    if(rc||io==UINT32_MAX||(io&3u))return rc?rc:-71;
    c->platform_perst_verified=true;return 0;
}
