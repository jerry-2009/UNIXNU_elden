/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Interoperability declarations for Ath12kWifi5f7f5a8 include/nw_abi.h.
 * Keep these layouts checked against that exact public ABI. */
#pragma once
#include <stdint.h>
#include <stddef.h>
#ifdef __cplusplus
extern "C" {
#endif
struct lx_platform {
    uint64_t (*now_ms)(void);void (*sleep_ms)(unsigned);void (*poll)(void);
    void (*log)(int,const char *);void (*halt)(void);
    void *(*alloc)(size_t);void (*free)(void *);
    void *(*dma_alloc)(size_t,uint64_t *);void (*dma_free)(size_t,void *,uint64_t);
    uint64_t (*dma_map)(void *,size_t,int);void (*dma_sync)(uint64_t,size_t,int);
    int (*fw_get)(const char *,const uint8_t **,size_t *);
    uint64_t (*now_ns)(void);uint64_t (*boottime_ns)(void);
    void (*busy_delay_us)(unsigned);void (*preempt_disable)(void);void (*preempt_enable)(void);
};
struct nw_board {
    void *bar;size_t bar_len;uint16_t device_id,msi_cap;int irq_base;
    int (*cfg_read)(int,int,uint32_t *);int (*cfg_write)(int,int,uint32_t);
    int (*msi_target)(uint32_t *,uint32_t *,uint32_t *);
    void *(*map_phys)(uint64_t,size_t);unsigned diagnostics;
};
struct nw_wifi_stats {uint32_t stage,scans,frames,beacons,bss_seen;int last_err;};
extern struct nw_wifi_stats nw_wifi_stats;
void nw_wifi_set_platform(const struct lx_platform *);
int nw_wifi_start(const struct lx_platform *,const struct nw_board *);
void nw_wifi_stop(void);int nw_wifi_step(void);void nw_wifi_poll(void);
void nw_wifi_irq_mode(int);void nw_wifi_irq_pending(uint32_t);
unsigned nw_wifi_wait_ms(unsigned);
int nw_wifi_scan(const uint8_t *,size_t);int nw_wifi_bss_count(void);
#ifdef __cplusplus
}
static_assert(sizeof(lx_platform)==136&&sizeof(nw_board)==64,"frozen board ABI");
static_assert(offsetof(nw_board,cfg_read)==24&&sizeof(struct nw_wifi_stats)==24,"frozen ABI offsets");
#endif
