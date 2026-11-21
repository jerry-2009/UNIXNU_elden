/* SPDX-License-Identifier: BSD-2-Clause-Patent */
#pragma once
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif
enum { EldenWifiArenaEmpty, EldenWifiArenaRunning, EldenWifiArenaStopping };
enum { EldenWifiArenaMaxBlocks=16384, EldenWifiArenaMaxBytes=128u<<20 };
typedef struct {
    uint32_t offset,bytes,requested,used;
} EldenWifiDmaBlock;
/* Caller serializes every operation, including stop. This core neither owns
 * an IOKit mapping nor proves hardware quiescence. Keep mapping and metadata
 * alive until the native owner has independently drained DMA or reset. */
typedef struct {
    const void *owner;
    uint64_t epoch,iova;
    uint8_t *cpu;
    EldenWifiDmaBlock *blocks;
    uint32_t state,bytes,capacity,count,live,used,peak;
    uint64_t allocation_failures;
} EldenWifiDmaArena;
int elden_wifi_dma_arena_init(EldenWifiDmaArena *,const void *owner,uint64_t epoch,
    void *cpu,uint64_t iova,uint32_t bytes,EldenWifiDmaBlock *,uint32_t capacity);
int elden_wifi_dma_arena_alloc(EldenWifiDmaArena *,const void *owner,uint64_t epoch,
    size_t bytes,void **cpu,uint64_t *bus);
/* QRTR/MHI uses zero bytes/bus when only the original allocation pointer is
 * available. Nonzero metadata must match; interior/double frees are rejected. */
int elden_wifi_dma_arena_free(EldenWifiDmaArena *,const void *owner,uint64_t epoch,
    size_t bytes,void *cpu,uint64_t bus);
int elden_wifi_dma_arena_map(const EldenWifiDmaArena *,const void *owner,uint64_t epoch,
    const void *cpu,size_t bytes,int direction,uint64_t *bus);
/* Validate before the native NC-memory ordering barrier, including draining
 * existing buffers after stop. This is not a cache operation or completion.
 * Directions are Linux bidirectional/TO/FROM. */
int elden_wifi_dma_arena_bus_range(const EldenWifiDmaArena *,const void *owner,uint64_t epoch,
    uint64_t bus,size_t bytes,int direction);
int elden_wifi_dma_arena_stop(EldenWifiDmaArena *,const void *owner,uint64_t epoch);
#ifdef __cplusplus
}
#endif
