/* SPDX-License-Identifier: GPL-2.0-only */
#pragma once
#include "Config.h"
#ifdef __cplusplus
extern "C" {
#endif
typedef struct {
    void *context;EldenPcieConfigAccess *config;
    int (*admit)(void *); /* real platform callback returned and consumer unbound */
    uint64_t (*now_us)(void *);void (*delay_us)(void *,unsigned);
} EldenPlatformFenceIo;
typedef struct {
    unsigned attempted,phase,master_off,transactions_sampled,transactions_idle;
    uint32_t identity,command,device_status;
    int error;
} EldenPlatformFence;
/* Host DMA fence only. Full shutdown additionally needs MSI drain and actual
 * PERST assertion. Keep all backing memory and tables until platform reset. */
int elden_pcie_platform_fence(EldenPlatformFence *,const EldenPlatformFenceIo *,uint64_t deadline_us);
#ifdef __cplusplus
}
#endif
