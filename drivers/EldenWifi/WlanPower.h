/* SPDX-License-Identifier: GPL-2.0-only */
#pragma once
#include "WcnPower.h"
#ifdef __cplusplus
extern "C" {
#endif
/* Cold start: the native board provider first verifies TB322FC/SM8750 platform
 * resources and the expected endpoint/SID from the board description. A powered
 * down endpoint cannot supply live PCI identity yet. Acquire authorizes power
 * and link preparation only; confirm_endpoint must receive fresh config/BAR
 * identity before ready/QMI/CPR. Token survives until platform reset. */
typedef struct {
    const void *provider;
    uint32_t expected_vendor,expected_device,rid,sid;
    /* Must stop new PCIe/MHI requests and prove DMA quiescence before reset.
     * Called in thread context during explicit stop and platform recovery. */
    int (*quiesce)(const void *provider,uint64_t epoch,uint64_t deadline_us);
} EldenWlanIdentity;
int elden_wlan_power_acquire(const EldenWlanIdentity *,uint64_t *epoch);
int elden_wlan_power_check(const void *provider,uint64_t epoch);
int elden_wlan_power_confirm_endpoint(const void *provider,uint64_t epoch,
                                      uint32_t vendor_device,uint32_t soc_major);
int elden_wlan_power_ready(const void *provider,uint64_t epoch);
int elden_wlan_power_cpr(const void *provider,uint64_t epoch,const EldenWcnPmuParam *,size_t);
int elden_wlan_power_stop(const void *provider,uint64_t epoch);
#ifdef __cplusplus
}
#endif
