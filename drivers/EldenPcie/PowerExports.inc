/* SPDX-License-Identifier: GPL-2.0-only */
extern "C" int elden_wlan_root_power(const void *provider,uint64_t epoch,unsigned max_gen){
    unsigned full_on=0;PE_parse_boot_argn("elden-pcie-full-on",&full_on,sizeof(full_on));
    if(full_on!=1||__atomic_load_n(&platform_stopping,__ATOMIC_ACQUIRE))return -11;
    if(max_gen<1||max_gen>3)return -22;
    int rc=wlan_api_enter();if(rc)return rc;
    rc=wlan_check(provider,epoch);
    if(!rc){
        rc=platform_enter();
        if(!rc){
            if(__atomic_load_n(&platform_stopping,__ATOMIC_ACQUIRE))rc=-11;
            else rc=root_power_prepare(__atomic_load_n(&active,__ATOMIC_ACQUIRE),epoch,max_gen);
            platform_leave();
        }
    }
    return wlan_api_leave(rc);
}
