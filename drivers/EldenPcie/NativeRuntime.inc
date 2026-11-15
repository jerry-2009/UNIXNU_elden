/* SPDX-License-Identifier: GPL-2.0-only */
struct Context {
    static void *operator new(size_t n) noexcept{return IOMalloc(n);}
    static void operator delete(void *p) noexcept{if(p)IOFree(p,sizeof(Context));}
    Region maps[EldenPcieWindowCount],pin_map,wlan_observer;
    EldenPcieRoot root={};EldenPciePins pins={};
    uint64_t wlan_epoch=0;uint32_t battery_epoch=0,printed_stage=0;
    bool power_ready=false;
    bool map(){
        for(unsigned i=0;i<EldenPcieWindowCount;i++){
            if(!maps[i].map(elden_pcie_window_base(i),elden_pcie_window_bytes(i))){
                log("\nELDEN_PCIE map-failed window=%u pa=%llx bytes=%x\n",i,(unsigned long long)elden_pcie_window_base(i),elden_pcie_window_bytes(i));
                return false;
            }
        }
        if(!pin_map.map(0x0f166000,0x2000)){log("\nELDEN_PCIE map-failed pins\n");return false;}
        if(!wlan_observer.map(0x0f110000,0x1000)){log("\nELDEN_PCIE map-failed WLAN observer\n");return false;}
        return true;
    }
};
static Context *active;
static bool fresh(uint32_t expected,uint32_t *epoch=nullptr){
    if(__atomic_load_n(&stop_requested,__ATOMIC_ACQUIRE)||ml_at_interrupt_context()||!elden_recovery_armed()||
       !elden_recovery_rpc_ready()||elden_recovery_deadline_remaining()<15||!elden_charge_policy_ready())return false;
    int t=0;uint32_t e=0,cycle=0;
    if(!elden_battery_temperature_get(&t,&e,&cycle)||!e||!cycle||t<500||t>3800||(expected&&expected!=e))return false;
    if(epoch)*epoch=e;
    return true;
}
static int admit(void *p,uint64_t epoch){
    Context *c=static_cast<Context *>(p);
    if(!fresh(c->battery_epoch))return -11;
    if(epoch){
        if(epoch!=c->wlan_epoch||!c->power_ready)return -11;
        return elden_wlan_power_check(c,epoch);
    }
    uint32_t io=UINT32_MAX;int rc=c->wlan_observer.read(4,&io);
    return rc?rc:io==UINT32_MAX?-5:(io&1)?-16:0;
}
static void trace(Context *c,unsigned w,uint32_t off){
    if(c->printed_stage==c->root.stage)return;
    c->printed_stage=c->root.stage;
    log("\nELDEN_PCIE stage=%u window=%u offset=%08x epoch=%llu\n",c->root.stage,w,off,(unsigned long long)c->wlan_epoch);
}
static int read(void *p,unsigned w,uint32_t off,uint32_t *v){
    Context *c=static_cast<Context *>(p);if(w>=EldenPcieWindowCount)return -22;
    trace(c,w,off);return c->maps[w].read(off,v);
}
static int write(void *p,unsigned w,uint32_t off,uint32_t v){
    Context *c=static_cast<Context *>(p);if(w>=EldenPcieWindowCount)return -22;
    trace(c,w,off);return c->maps[w].write(off,v);
}
static int pin_read(void *p,unsigned off,uint32_t *v){return static_cast<Context *>(p)->pin_map.read(off,v);}
static int pin_write(void *p,unsigned off,uint32_t v){return static_cast<Context *>(p)->pin_map.write(off,v);}
static int pins(void *p,bool high){Context *c=static_cast<Context *>(p);trace(c,99,0);return elden_pcie_pins_set(&c->pins,high);}
static int gcc_gate(void *,bool take){
    if(!take){
        uint32_t expected=GccOwner;
        return __atomic_compare_exchange_n(&sm8750_gcc_vote_owner,&expected,0u,false,__ATOMIC_RELEASE,__ATOMIC_RELAXED)?0:-71;
    }
    for(unsigned n=0;n<100;n++){
        uint32_t expected=0;
        if(__atomic_compare_exchange_n(&sm8750_gcc_vote_owner,&expected,GccOwner,false,__ATOMIC_ACQUIRE,__ATOMIC_RELAXED))return 0;
        IODelay(1);
    }
    return -16;
}
static int quiesce(const void *provider,uint64_t epoch,uint64_t deadline){
    Context *c=static_cast<Context *>(const_cast<void *>(provider));
    if(!c||c!=__atomic_load_n(&active,__ATOMIC_ACQUIRE))return -19;
    __atomic_store_n(&stop_requested,1u,__ATOMIC_RELEASE);
    for(unsigned i=0;i<9000&&__atomic_load_n(&run,__ATOMIC_ACQUIRE)!=2&&now(nullptr)<deadline;i++)IOSleep(1);
    if(__atomic_load_n(&run,__ATOMIC_ACQUIRE)!=2||now(nullptr)>=deadline)return -110;
    if(epoch!=c->wlan_epoch)return -19;
    /* This cold worker never creates a DMA window or enables EP bus master.
     * Once it is terminal, assert its owned reset and verify it remains low.
     * Replace this contract with MHI/DMA draining before adding DMA operation. */
    int rc=elden_pcie_pins_set(&c->pins,false);if(rc)return rc;
    uint64_t before=now(nullptr);IODelay(1000);uint64_t after=now(nullptr);
    if(after<before||after-before<1000||after>=deadline)return -110;
    uint32_t io=UINT32_MAX;rc=c->pin_map.read(4,&io);
    if(rc||io==UINT32_MAX||(io&3u))return rc?rc:-71;
    __atomic_store_n(&stopped,1u,__ATOMIC_RELEASE);
    log("\nELDEN_PCIE quiesced=1 perst-low=1 dma-enabled-by-driver=0\n");return 0;
}
static int power_up(void *p,unsigned gen,uint64_t *epoch){
    Context *c=static_cast<Context *>(p);trace(c,99,1);
    EldenWlanIdentity id={c,ELDEN_WIFI_PCI_VENDOR,ELDEN_WIFI_PCI_DEVICE,ELDEN_WIFI_ENDPOINT_RID,ELDEN_WIFI_ENDPOINT_SID,quiesce};
    uint64_t e=0;int rc=elden_wlan_power_acquire(&id,&e);if(rc)return rc;
    c->wlan_epoch=e;*epoch=e;
    rc=elden_wlan_root_power(c,e,gen);if(!rc)c->power_ready=true;return rc;
}
static void finish(Context *c,int error){
    terminal.version=1;terminal.run=2;terminal.error=error;
    if(c){
        const EldenPcieRoot &r=c->root;terminal.state=r.state;terminal.stage=r.stage;terminal.root_id=r.root_id;
        terminal.endpoint_id=r.endpoint_id;terminal.link_status=r.link_status;terminal.last_window=r.last_window;
        terminal.last_offset=r.last_offset;terminal.last_value=r.last_value;terminal.writes=r.writes;
        terminal.phy_writes=r.phy.writes;terminal.gcc_held=r.gcc_held;terminal.perst_high=r.perst_high;terminal.epoch=r.epoch;
    }
    log("\nELDEN_PCIE end rc=%d state=%u stage=%u root=%08x ep=%08x link=%08x last=%u:%08x=%08x writes=%u phy=%u gcc-held=%u\n",
        error,terminal.state,terminal.stage,terminal.root_id,terminal.endpoint_id,terminal.link_status,
        terminal.last_window,terminal.last_offset,terminal.last_value,terminal.writes,terminal.phy_writes,terminal.gcc_held);
    __atomic_store_n(&run,2u,__ATOMIC_RELEASE);
}
static void worker(void *arg,wait_result_t){
    unsigned gen=(unsigned)(uintptr_t)arg;uint32_t epoch=0;bool ready=false;
    for(unsigned n=0;n<12000&&!__atomic_load_n(&stop_requested,__ATOMIC_ACQUIRE);n++){
        if(fresh(0,&epoch)&&elden_recovery_deadline_remaining()>=120){ready=true;break;}IOSleep(10);
    }
    if(!ready){finish(nullptr,-11);thread_terminate(current_thread());return;}
    Context *c=new Context;
    if(!c||!c->map()){if(c)delete c;finish(nullptr,-12);thread_terminate(current_thread());return;}
    c->battery_epoch=epoch;c->pins={c,pin_read,pin_write,delay,false,false};
    c->root.io={c,admit,pins,power_up,gcc_gate,read,write,now,delay};
    __atomic_store_n(&active,c,__ATOMIC_RELEASE);
    int rc=elden_pcie_root_start(&c->root,gen);finish(c,rc);
    /* Context/maps remain until platform reset, including failed transactions. */
    thread_terminate(current_thread());
}
