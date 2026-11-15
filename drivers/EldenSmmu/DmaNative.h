/* SPDX-License-Identifier: BSD-2-Clause-Patent */
#pragma once
#include <stdint.h>
#include <stddef.h>
#ifdef __cplusplus
extern "C" {
#endif
typedef struct {
    uint32_t version,run,stopping,calls,blocks,live,used,peak;
    int32_t first_error;
    uint64_t epoch,allocation_failures;
} EldenWifiDmaStatus;
/* One bind to the confirmed native PCIe/WLAN owner per platform boot. */
int elden_wifi_dma_bind(const void *provider,uint64_t epoch);
void *elden_wifi_dma_alloc(size_t bytes,uint64_t *bus);
void elden_wifi_dma_free(size_t bytes,void *cpu,uint64_t bus);
uint64_t elden_wifi_dma_map(void *cpu,size_t bytes,int direction);
void elden_wifi_dma_sync(uint64_t bus,size_t bytes,int direction);
int elden_wifi_dma_msi_sink(uint64_t *bus);
/* Nonblocking admission withdrawal, callable before the worker drains. */
void elden_wifi_dma_stop_begin(void);
int elden_wifi_dma_status(EldenWifiDmaStatus *);
#ifdef __cplusplus
}
#endif
