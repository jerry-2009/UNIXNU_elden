/* SPDX-License-Identifier: GPL-2.0-only */
static Context *runtime_context;
static uint64_t runtime_ns(){uint64_t t;__asm__ volatile("mrs %0,cntpct_el0":"=r"(t));return (t/12)*625+(t%12)*625/12;}
static uint64_t runtime_ms(){return runtime_ns()/1000000;}
static void runtime_sleep(unsigned ms){IOSleep(ms);}
static void runtime_busy(unsigned us){IODelay(us);}
static void runtime_preempt_off(){_disable_preemption();}
static void runtime_preempt_on(){_enable_preemption();}
struct RuntimeAllocation {size_t bytes;uint64_t magic;};
static void *runtime_alloc(size_t bytes){
    if(bytes>SIZE_MAX-sizeof(RuntimeAllocation))return nullptr;
    size_t total=bytes+sizeof(RuntimeAllocation);auto *h=(RuntimeAllocation *)IOMalloc(total);
    if(!h)return nullptr;h->bytes=total;h->magic=0x454c44454e574946ull;return h+1;
}
static void runtime_free(void *p){
    if(!p)return;auto *h=(RuntimeAllocation *)p-1;
    if(h->magic!=0x454c44454e574946ull||h->bytes<sizeof(*h))panic("ELDEN_WIFI invalid heap release");
    size_t bytes=h->bytes;h->magic=0;IOFree(h,bytes);
}
static void runtime_log(int level,const char *line){
    Context *c=runtime_context;if(!line)return;
    size_t length=strlen(line);
    if(c&&level>=6&&length<sizeof(c->runtime_log_lines[0])){
        for(unsigned i=0;i<8;i++)if(!strcmp(c->runtime_log_lines[i],line)){c->runtime_log_repeats++;return;}
        unsigned slot=c->runtime_log_cursor++%8;memcpy(c->runtime_log_lines[slot],line,length+1);
    }
    log("\nELDEN_ATH12K level=%d %s\n",level,line);
}
static void runtime_halt(){panic("ELDEN_WIFI Linux runtime halt");}
static void runtime_poll(){
    Context *c=runtime_context;if(!c||!c->runtime_entered||c->runtime_returned)return;
    uint32_t pending=elden_pcie_msi_pending(&c->msi);c->runtime_irq_seen|=pending;
    /* Upstream starts by polling. Switch only after an actual nonzero MSI
     * status has been received; an empty/spurious IRQ is not that proof. */
    nw_wifi_irq_mode(c->runtime_irq_seen!=0);
    if(pending)nw_wifi_irq_pending(pending);
    nw_wifi_poll();
}
static int runtime_config_read(int offset,int size,uint32_t *value){
    Context *c=runtime_context;if(!c||!c->runtime_entered||c->runtime_returned)return -19;
    return elden_pcie_cfg_read(&c->config,offset,size,value,c->transport_cleanup);
}
static int runtime_config_write(int offset,int size,uint32_t value){
    Context *c=runtime_context;if(!c||!c->runtime_entered||c->runtime_returned)return -19;
    return elden_pcie_cfg_write(&c->config,offset,size,value,c->transport_cleanup);
}
static void *runtime_map_phys(uint64_t pa,size_t bytes){
    Context *c=runtime_context;if(!c||!c->runtime_entered||c->runtime_returned||!bytes)return nullptr;
    if(transport_admit(c,c->transport_cleanup))return nullptr;
    uint64_t start=c->endpoint.bars[0].address,length=c->endpoint.bars[0].bytes;
    if(pa<start||pa-start>=length||bytes>length-(pa-start))return nullptr;
    return reinterpret_cast<void *>(c->bar0_map.va+(uintptr_t)(pa-start));
}
static int runtime_msi_target(uint32_t *lo,uint32_t *hi,uint32_t *data){
    if(!lo||!hi||!data)return -22;Context *c=runtime_context;
    if(!c||!c->runtime_entered||c->runtime_returned||c->transport_cleanup)return -19;
    uint64_t sink=0;int rc=elden_wifi_dma_msi_sink(&sink);if(rc)return rc;
    *lo=(uint32_t)sink;*hi=(uint32_t)(sink>>32);*data=0;return 0;
}
static int runtime_master_ready(void *p){
    Context *c=(Context *)p;if(c!=runtime_context||!c->runtime_entered||!c->runtime_prepared||
       c->runtime_returned||!c->runtime_consumer||c->transport_cleanup||c->msi.state!=EldenMsiArmed)return -19;
    int rc=transport_msi_admit(c);if(rc)return rc;
    EldenWifiFirmwareStatus s={};rc=elden_wifi_firmware_status(&s);
    return rc?rc:(s.run==2&&!s.stopping&&!s.error&&s.loaded==6&&s.epoch==c->wlan_epoch)?0:-11;
}
static int runtime_stop_admit(void *p){Context *c=(Context *)p;return c->runtime_returned?transport_admit(c,true):-16;}
static int runtime_bar_read(void *p,uint32_t off,uint32_t *v){
    if(off!=0x38&&off!=0x48)return -22;return ((Context *)p)->bar0_map.read(off,v);
}
static int runtime_bar_write(void *p,uint32_t off,uint32_t value){
    if(off!=0x38)return -22;return ((Context *)p)->bar0_map.write(off,value);
}
static int runtime_quiesced(Context *c){
    if(!c->runtime_quiesced||!c->runtime_returned||c->runtime_consumer||c->mhi_stop.phase!=6||
       !c->mhi_stop.master_off||!c->mhi_stop.transactions_idle)return -16;
    uint32_t id=0,command=0;int rc=elden_pcie_cfg_read(&c->config,0,4,&id,true);if(rc)return rc;
    if(id!=0x110e17cb)return -19;
    rc=elden_pcie_cfg_read(&c->config,4,2,&command,true);return rc?rc:(command&7)==2?0:-71;
}
static int runtime_finish(Context *c){
    c->runtime_stage=4;c->transport_cleanup=true;c->transport_ready=false;
    elden_wifi_firmware_stop_begin();elden_wifi_dma_stop_begin();
    /* nw_wifi_start() already calls its stop path when it returns an error. */
    if(c->runtime_stack_started)nw_wifi_stop();
    c->runtime_returned=true;
    EldenMhiStopIo io={c,&c->config,runtime_stop_admit,runtime_bar_read,runtime_bar_write,now,delay};
    int rc=elden_mhi_stop(&c->mhi_stop,&io,now(nullptr)+3000000);
    if(!rc&&c->runtime_consumer)rc=-16;
    if(!rc){c->runtime_quiesced=true;c->runtime_stage=5;rc=elden_pcie_msi_stop(&c->msi,now(nullptr)+100000);}
    if(!rc){(void)elden_pcie_msi_pending(&c->msi);c->runtime_stage=6;}
    c->runtime_stop_error=rc;
    log("\nELDEN_WIFI_RUNTIME stop=%d stage=%u reset=%u/%u ctl=%x status=%x command=%x transactions=%x consumer=%u\n",rc,
        c->runtime_stage,c->mhi_stop.reset_requested,c->mhi_stop.reset_observed,c->mhi_stop.control,c->mhi_stop.status,
        c->mhi_stop.command,c->mhi_stop.device_status,c->runtime_consumer!=nullptr);
    return rc;
}
static void runtime_run(Context *c){
    c->runtime_stage=1;int rc=transport_msi_admit(c);
    if(!rc&&elden_recovery_deadline_remaining()<60)rc=-11;
    static const char *const files[]={"amss.bin","m3.bin","aux_ucode.bin","tmel.bin","regdb.bin","board.bin"};
    for(unsigned i=0;!rc&&i<6;i++){
        const uint8_t *data=nullptr;size_t bytes=0;rc=elden_wifi_firmware_get(files[i],&data,&bytes);
        log("\nELDEN_WIFI_RUNTIME firmware=%s rc=%d bytes=%llu\n",files[i],rc,(unsigned long long)bytes);
    }
    if(rc){c->runtime_error=rc;return;}
    runtime_context=c;c->runtime_prepared=true;
    c->runtime_platform={runtime_ms,runtime_sleep,runtime_poll,runtime_log,runtime_halt,runtime_alloc,runtime_free,
        elden_wifi_dma_alloc,elden_wifi_dma_free,elden_wifi_dma_map,elden_wifi_dma_sync,elden_wifi_firmware_get,
        runtime_ns,runtime_ns,runtime_busy,runtime_preempt_off,runtime_preempt_on};
    c->runtime_board={reinterpret_cast<void *>(c->bar0_map.va),(size_t)c->endpoint.bars[0].bytes,0x110e,
        (uint16_t)c->config.msi_cap,1000,runtime_config_read,runtime_config_write,runtime_msi_target,runtime_map_phys,0};
    c->runtime_stage=2;c->runtime_entered=true;
    nw_wifi_set_platform(&c->runtime_platform);nw_wifi_irq_mode(0);
    rc=nw_wifi_start(&c->runtime_platform,&c->runtime_board);c->runtime_start_error=rc;c->runtime_stack_started=!rc;
    log("\nELDEN_WIFI_RUNTIME start=%d linux-stage=%u master=%u command=%x\n",rc,nw_wifi_stats.stage,(unsigned)c->config.master_attempted,c->config.command);
    uint64_t report_at=0,slice=now(nullptr),scan_at=0;bool scan=false;unsigned scan_attempts=0;
    while(!rc&&!__atomic_load_n(&stop_requested,__ATOMIC_ACQUIRE)&&elden_recovery_deadline_remaining()>20){
        c->runtime_stage=3;
        int fault=__atomic_load_n(&c->msi.irq_error,__ATOMIC_ACQUIRE);
        if(fault){rc=fault;break;}
        if(!elden_wifi_smmu_ready()){rc=-5;break;}
        int busy=nw_wifi_step();c->runtime_rounds++;
        if(__atomic_load_n(&stop_requested,__ATOMIC_ACQUIRE))break;
        uint64_t t=now(nullptr);
        if(!scan&&scan_attempts<3&&t>=scan_at&&nw_wifi_stats.stage>=4){
            int r=nw_wifi_scan(nullptr,0);scan=!r;scan_attempts++;scan_at=t+1000000;log("\nELDEN_WIFI_RUNTIME scan=%d\n",r);
        }
        if(t>=report_at){
            c->runtime_bss=nw_wifi_bss_count();
            log("\nELDEN_WIFI_RUNTIME live stage=%u error=%d rounds=%llu irq=%u vectors=%x bss=%d repeats=%u\n",
                nw_wifi_stats.stage,nw_wifi_stats.last_err,(unsigned long long)c->runtime_rounds,
                __atomic_load_n(&c->msi.irq_count,__ATOMIC_RELAXED),c->runtime_irq_seen,c->runtime_bss,c->runtime_log_repeats);
            report_at=t+1000000;
        }
        if(!busy){unsigned ms=nw_wifi_wait_ms(20);if(ms)IOSleep(ms);slice=now(nullptr);}
        else if(t-slice>=10000){IOSleep(1);slice=now(nullptr);}
    }
    c->runtime_error=rc;
    int stop=runtime_finish(c);if(!c->runtime_error)c->runtime_error=stop;
}
