/* SPDX-License-Identifier: GPL-2.0-only */
#pragma once
#include "WcnPower.h"
#ifdef __cplusplus
extern "C" {
#endif
/* Call from the native PCIe provider after real endpoint identity/SID checks,
 * in sleepable thread context. Token is the stable provider instance and must
 * survive until platform reset. No Linux struct device layout is assumed. */
typedef struct {
    const void *provider;
    uint32_t vendor,device,rid,sid;
    /* Must stop new PCIe/MHI requests and prove DMA quiescence before reset.
     * Called in thread context during explicit stop and platform recovery. */
    int (*quiesce)(const void *provider,uint64_t epoch,uint64_t deadline_us);
} EldenWlanIdentity;
int elden_wlan_power_acquire(const EldenWlanIdentity *,uint64_t *epoch);
int elden_wlan_power_check(const void *provider,uint64_t epoch);
int elden_wlan_power_cpr(const void *provider,uint64_t epoch,const EldenWcnPmuParam *,size_t);
int elden_wlan_power_stop(const void *provider,uint64_t epoch);
#ifdef __cplusplus
}
#endif
