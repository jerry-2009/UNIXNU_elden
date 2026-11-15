/* SPDX-License-Identifier: BSD-2-Clause-Patent */
#pragma once
#include "upstream/EldenWifiSmmu4KTableMemory.h"
#ifdef __cplusplus
extern "C" {
#endif
enum {EldenWifiDmaBytes=128u<<20,EldenWifiDmaIova=0x10000000u,EldenWifiTablePages=66};
typedef struct {
    EldenWifiSmmu4KConfig config;
    EldenWifiSmmu4KRange range;
    EldenWifiSmmu4KResult result;
    EldenWifiSmmu4KTableMemory memory;
    EldenWifiSmmu4KTableIo io;
    unsigned char visited[EldenWifiTablePages];
    uint32_t id0,id2,attempted,ready;
} EldenWifiDmaTables;
unsigned elden_wifi_dma_output_bits(uint32_t id0,uint32_t id2);
/* Inactive tables only. Real allocator owns/pins the two distinct PA ranges,
 * verifies their CPU mappings and retains them. One call per zeroed stable
 * object. No MMIO/cache publishing/ASID ownership or device activation. */
int elden_wifi_dma_tables_build(EldenWifiDmaTables *,uint32_t id0,uint32_t id2,
    uint64_t data_physical,uint64_t table_physical,uint64_t *table_mapping,size_t bytes);
int elden_wifi_dma_tables_audit(EldenWifiDmaTables *,EldenWifiSmmu4KTableAuditResult *);
/* ASID must be exclusively reserved by native preflight. This encodes values,
 * not an enabled context or proof that the provided IDs were read live. */
int elden_wifi_dma_context_image(EldenWifiDmaTables *,unsigned asid,EldenWifiSmmu4KContextImage *);
#ifdef __cplusplus
}
#endif
