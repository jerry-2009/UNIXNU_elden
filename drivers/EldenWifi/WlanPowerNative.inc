/* SPDX-License-Identifier: GPL-2.0-only */
/* Inserted in WcnPowerNative's namespace after existing physical primitives. */
static unsigned platform_init_state,platform_io_busy,platform_stopping;
static unsigned wlan_api_busy;
static const void *wlan_provider;
static int (*wlan_quiesce)(const void *,uint64_t,uint64_t);
static uint64_t wlan_epoch,wlan_next_epoch,wlan_endpoint_epoch;
static int platform_enter(uint64_t deadline=0){
    /* Serialize maps/preflight/physical callbacks with the existing BT survey.
     * Read-only lease checks do not take this gate. No register transaction is
     * retried; a busy peer gets up to1s to finish its bounded operation. */
    uint64_t local_deadline=now_us(nullptr)+1000000;
    if(!deadline||deadline>local_deadline)deadline=local_deadline;
    for(unsigned n=0;n<1000&&now_us(nullptr)<deadline;n++){
        unsigned expected=0;
        if(__atomic_compare_exchange_n(&platform_io_busy,&expected,1,false,__ATOMIC_ACQUIRE,__ATOMIC_RELAXED))return 0;
        IOSleep(1);
    }
    return -11;
}
static void platform_leave(){__atomic_store_n(&platform_io_busy,0,__ATOMIC_RELEASE);}
static int wlan_read(void *p,unsigned off,uint32_t *value){
    if(off!=0&&off!=4&&off!=8)return -22;
    *value=static_cast<Context *>(p)->wlan.read(off);return *value==0xffffffffu?-5:0;
}
static int wlan_write(void *p,unsigned off,uint32_t value){
    if(off!=0&&off!=4)return -22;
    Context *c=static_cast<Context *>(p);c->wlan.write(off,value);
    uint32_t actual=c->wlan.read(off);
    return actual==0xffffffffu?-5:((actual^value)&(off==4?2u:0x3ffu))?-71:0;
}
static int wlan_set(void *p,bool high){return elden_wlan_gpio_set(&static_cast<Context *>(p)->wlan_gpio,high);}
static int platform_get(Context **out){
    if(__atomic_load_n(&platform_stopping,__ATOMIC_ACQUIRE))return -11;
    if(!elden_recovery_armed()||native_owner_data_status||!elden_init_exec_accepted)return -11;
    unsigned state=__atomic_load_n(&platform_init_state,__ATOMIC_ACQUIRE);
    if(state==2){*out=__atomic_load_n(&active,__ATOMIC_ACQUIRE);return 0;}
    if(state)return -11;
    unsigned expected=0;
    if(!__atomic_compare_exchange_n(&platform_init_state,&expected,1,false,__ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE))return -11;
    Context *c=new Context;
    if(!c||!c->map()){
        if(c)delete c;__atomic_store_n(&platform_init_state,3,__ATOMIC_RELEASE);return -12;
    }
    c->spmi={c,core_read,owner_read,obs_read,obs_write,chan_read,chan_write,delay};
    c->rpmh={c,rsc_read,rsc_write,delay};
    c->aoss_io={c,aoss_read,aoss_write,delay};c->ipcc_io={c,ipcc_read,ipcc_write,delay};
    Sm8750AossQmpInit(&c->qmp,&c->aoss_io,0x400,&c->ipcc_io);
    c->power.io={c,preflight,rail_read,rail_vote,qmp_send,bt_set,bt_get,wlan_get,parents,now_us,delay};
    c->wlan_gpio={c,wlan_read,wlan_write,delay,false,false};c->shared.wlan_set=wlan_set;
    __atomic_store_n(&active,c,__ATOMIC_RELEASE);
    __atomic_store_n(&platform_init_state,2,__ATOMIC_RELEASE);*out=c;return 0;
}
static int bt_power_acquire(Context *c,uint64_t epoch){
    c->bt_epoch=epoch;c->bt_state=EldenWcnPowerPreparing;
    int rc=platform_enter();if(rc){c->bt_state=EldenWcnPowerFailed;return rc;}
    if(__atomic_load_n(&platform_stopping,__ATOMIC_ACQUIRE))rc=-11;
    else rc=elden_wcn_shared_acquire(&c->shared,EldenWcnBluetooth,epoch);
    c->bt_state=rc?EldenWcnPowerFailed:EldenWcnPowerReady;platform_leave();return rc;
}
static int bt_power_stop(Context *c,uint64_t epoch){
    int rc=platform_enter();if(rc)return rc;
    rc=elden_wcn_shared_stop(&c->shared,EldenWcnBluetooth,epoch);
    c->bt_state=rc?EldenWcnPowerFailed:EldenWcnPowerStopped;platform_leave();return rc;
}
static int bt_power_finish(Context *c,uint64_t epoch){
    if(epoch!=c->bt_epoch||c->bt_state!=EldenWcnPowerStopped)return -11;
    c->bt_state=EldenWcnPowerClosed;return 0;
}
static int wlan_api_enter(){
    unsigned expected=0;
    return __atomic_compare_exchange_n(&wlan_api_busy,&expected,1,false,__ATOMIC_ACQUIRE,__ATOMIC_RELAXED)?0:-11;
}
static int wlan_api_leave(int rc){__atomic_store_n(&wlan_api_busy,0,__ATOMIC_RELEASE);return rc;}
static int wlan_check(const void *provider,uint64_t epoch){
    if(!provider||!epoch)return -22;
    if(provider!=__atomic_load_n(&wlan_provider,__ATOMIC_ACQUIRE)||
       epoch!=__atomic_load_n(&wlan_epoch,__ATOMIC_ACQUIRE))return -11;
    Context *c=__atomic_load_n(&active,__ATOMIC_ACQUIRE);
    return c?elden_wcn_shared_check(&c->shared,EldenWcnWlan,epoch):-11;
}
static int wlan_stop_locked(const void *provider,uint64_t epoch,uint64_t deadline){
    int rc=wlan_check(provider,epoch);if(rc)return rc;
    /* Withdraw future calls before asking the device driver to drain DMA. */
    __atomic_store_n(&wlan_endpoint_epoch,0,__ATOMIC_RELEASE);
    __atomic_store_n(&wlan_epoch,0,__ATOMIC_RELEASE);
    if(now_us(nullptr)>=deadline)return -110;
    rc=wlan_quiesce(provider,epoch,deadline);if(rc)return rc;
    if(now_us(nullptr)>=deadline)return -110;
    rc=platform_enter(deadline);if(rc)return rc;
    Context *c=__atomic_load_n(&active,__ATOMIC_ACQUIRE);
    rc=elden_wcn_shared_stop(&c->shared,EldenWcnWlan,epoch);platform_leave();return rc;
}
static int wlan_shutdown(uint64_t deadline){
    /* Caller has closed admission. Wait only for the existing API transaction;
     * failed quiescence retains resources until the established platform reset. */
    for(unsigned n=0;n<900&&now_us(nullptr)<deadline;n++){
        if(!wlan_api_enter()){
            uint64_t epoch=__atomic_load_n(&wlan_epoch,__ATOMIC_ACQUIRE);
            const void *provider=__atomic_load_n(&wlan_provider,__ATOMIC_ACQUIRE);
            int rc=epoch?wlan_stop_locked(provider,epoch,deadline):0;
            Context *c=__atomic_load_n(&active,__ATOMIC_ACQUIRE);
            EldenWcnSharedSnapshot snap={};
            if(c&&(elden_wcn_shared_snapshot(&c->shared,&snap)||snap.held||snap.state[EldenWcnWlan]!=EldenWcnLeaseOff))rc=-71;
            return wlan_api_leave(rc);
        }
        IOSleep(10);
    }
    return -110;
}
