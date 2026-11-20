/* SPDX-License-Identifier: BSD-2-Clause-Patent */
#pragma once
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
/* All callbacks run on the retained native Wi-Fi worker. Addresses are chip
 * offsets; DMA uses the existing checked 32-bit IOVA/NC-memory allocation. */
struct EldenPortableIo {
    void *owner;
    uint32_t (*read)(void *,uint32_t);
    void (*write)(void *,uint32_t,uint32_t);
    void (*note)(void *,int,const char *);
};
struct EldenPortableStatus {
    int step,error;
    uint32_t ready,commands,events,credit_reports,credit_waits;
    uint32_t scans,started,completed,bss,management_frames;
    uint32_t ce_sent,ce_received,ce_completions,ce_dropped,htt_announced;
};
int elden_wifi_portable_requested(void);
int elden_wifi_portable_prepare(const struct EldenPortableIo *,void *,uint64_t,uint32_t,
                                const uint8_t *,uint64_t);
int elden_wifi_portable_tick(void *,uint64_t,struct EldenPortableStatus *);
int elden_wifi_portable_stop_tick(void *,uint64_t);
void elden_wifi_portable_disable(void *);
/* C runtime adapter exports: real firmware start; no fake cfg80211 station. */
int elden_wifi_portable_begin(void *);
int elden_wifi_portable_runtime_step(void);
int elden_wifi_portable_runtime_stop(void);
int elden_wifi_portable_bss_count(void);
#ifdef __cplusplus
}
static_assert(sizeof(EldenPortableIo)==32&&sizeof(EldenPortableStatus)==68,"portable ABI");
#endif
