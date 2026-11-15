/* SPDX-License-Identifier: GPL-2.0-only */
extern "C" int elden_wlan_power_acquire(const EldenWlanIdentity *id,uint64_t *epoch){
    if(!id||!epoch||!id->provider||!id->quiesce)return -22;
    if(id->vendor!=ELDEN_WIFI_PCI_VENDOR||id->device!=ELDEN_WIFI_PCI_DEVICE||
       id->rid!=ELDEN_WIFI_ENDPOINT_RID||id->sid!=ELDEN_WIFI_ENDPOINT_SID)return -19;
    unsigned enabled=0;PE_parse_boot_argn("elden-wlan-power",&enabled,sizeof(enabled));
    if(enabled!=1||__atomic_load_n(&platform_stopping,__ATOMIC_ACQUIRE))return -11;
    int rc=wlan_api_enter();if(rc)return rc;
    if(wlan_epoch||(wlan_provider&&wlan_provider!=id->provider))return wlan_api_leave(-11);
    if(wlan_next_epoch==UINT64_MAX)return wlan_api_leave(-11);
    Context *c=nullptr;rc=platform_get(&c);if(rc)return wlan_api_leave(rc);
    rc=platform_enter();if(rc)return wlan_api_leave(rc);
    uint64_t next=++wlan_next_epoch;
    if(__atomic_load_n(&platform_stopping,__ATOMIC_ACQUIRE))rc=-11;
    else rc=elden_wcn_shared_acquire(&c->shared,EldenWcnWlan,next);
    platform_leave();
    if(!rc){
        wlan_quiesce=id->quiesce;
        __atomic_store_n(&wlan_provider,id->provider,__ATOMIC_RELEASE);
        __atomic_store_n(&wlan_epoch,next,__ATOMIC_RELEASE);*epoch=next;
    }
    return wlan_api_leave(rc);
}
extern "C" int elden_wlan_power_check(const void *provider,uint64_t epoch){
    if(__atomic_load_n(&platform_stopping,__ATOMIC_ACQUIRE))return -11;
    return wlan_check(provider,epoch);
}
extern "C" int elden_wlan_power_cpr(const void *provider,uint64_t epoch,const EldenWcnPmuParam *params,size_t count){
    if(__atomic_load_n(&platform_stopping,__ATOMIC_ACQUIRE))return -11;
    int rc=wlan_api_enter();if(rc)return rc;
    rc=wlan_check(provider,epoch);
    if(!rc){
        rc=platform_enter();
        if(!rc){
            if(__atomic_load_n(&platform_stopping,__ATOMIC_ACQUIRE))rc=-11;
            else{
                Context *c=__atomic_load_n(&active,__ATOMIC_ACQUIRE);
                rc=elden_wcn_shared_cpr(&c->shared,EldenWcnWlan,epoch,params,count);
            }
            platform_leave();
        }
    }
    return wlan_api_leave(rc);
}
extern "C" int elden_wlan_power_stop(const void *provider,uint64_t epoch){
    int rc=wlan_api_enter();if(rc)return rc;
    return wlan_api_leave(wlan_stop_locked(provider,epoch,now_us(nullptr)+9000000));
}
