/* SPDX-License-Identifier: GPL-2.0-only */
extern "C" int elden_wlan_power_acquire(const EldenWlanIdentity *id,uint64_t *epoch){
    if(!id||!epoch||!id->provider||!id->quiesce)return -22;
    if(id->expected_vendor!=ELDEN_WIFI_PCI_VENDOR||id->expected_device!=ELDEN_WIFI_PCI_DEVICE||
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
        __atomic_store_n(&wlan_endpoint_epoch,0,__ATOMIC_RELEASE);
        __atomic_store_n(&wlan_provider,id->provider,__ATOMIC_RELEASE);
        __atomic_store_n(&wlan_epoch,next,__ATOMIC_RELEASE);*epoch=next;
    }
    return wlan_api_leave(rc);
}
extern "C" int elden_wlan_power_check(const void *provider,uint64_t epoch){
    if(__atomic_load_n(&platform_stopping,__ATOMIC_ACQUIRE))return -11;
    return wlan_check(provider,epoch);
}
extern "C" int elden_wlan_power_ready(const void *provider,uint64_t epoch){
    int rc=elden_wlan_power_check(provider,epoch);if(rc)return rc;
    return __atomic_load_n(&wlan_endpoint_epoch,__ATOMIC_ACQUIRE)==epoch?0:-11;
}
extern "C" int elden_wlan_power_confirm_endpoint(const void *provider,uint64_t epoch,uint32_t vendor_device,uint32_t soc_major){
    if(__atomic_load_n(&platform_stopping,__ATOMIC_ACQUIRE))return -11;
    int rc=wlan_api_enter();if(rc)return rc;
    rc=wlan_check(provider,epoch);
    if(!rc){
        if(vendor_device!=((ELDEN_WIFI_PCI_DEVICE<<16)|ELDEN_WIFI_PCI_VENDOR)||soc_major!=2){
            __atomic_store_n(&wlan_endpoint_epoch,0,__ATOMIC_RELEASE);rc=-19;
        }else __atomic_store_n(&wlan_endpoint_epoch,epoch,__ATOMIC_RELEASE);
    }
    return wlan_api_leave(rc);
}
extern "C" int elden_wlan_power_cpr(const void *provider,uint64_t epoch,const EldenWcnPmuParam *params,size_t count){
    if(__atomic_load_n(&platform_stopping,__ATOMIC_ACQUIRE))return -11;
    int rc=wlan_api_enter();if(rc)return rc;
    rc=wlan_check(provider,epoch);
    if(!rc&&__atomic_load_n(&wlan_endpoint_epoch,__ATOMIC_ACQUIRE)!=epoch)rc=-11;
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
