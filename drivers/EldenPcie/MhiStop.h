/* SPDX-License-Identifier: GPL-2.0-only */
#pragma once
#include "Config.h"
#ifdef __cplusplus
extern "C" {
#endif
typedef struct {
    void *context;EldenPcieConfigAccess *config;
    int (*admit)(void *); /* worker returned; owned BAR/clock/power held */
    int (*read)(void *,uint32_t,uint32_t *);
    int (*write)(void *,uint32_t,uint32_t);
    uint64_t (*now_us)(void *);void (*delay_us)(void *,unsigned);
} EldenMhiStopIo;
typedef struct {
    unsigned attempted,phase,reset_requested,reset_observed,master_off,transactions_idle;
    uint32_t control,status,command,device_status;
    int error;
} EldenMhiStop;
/* Protocol quiescence only. Keep all DMA buffers/maps until platform reset;
 * this is not permission to recycle memory or power down unrelated fabric. */
int elden_mhi_stop(EldenMhiStop *,const EldenMhiStopIo *,uint64_t deadline_us);
#ifdef __cplusplus
}
#endif
