/* SPDX-License-Identifier: MIT */
#ifndef ELDEN_WIFI_SMMU_4K_AUDIT_H
#define ELDEN_WIFI_SMMU_4K_AUDIT_H
#include "EldenWifiSmmu4KProgram.h"
#ifdef __cplusplus
extern "C" {
#endif
typedef struct {
    void *cookie;
    /* Read the actual descriptor at an owned physical address. No generated,
     * cached reference-table or translated/shadow-table substitute. Return 0
     * on success. Platform supplies a real coherent CPU mapping and ownership. */
    int (*read_descriptor)(void *,uint64_t physical,uint64_t *);
} EldenWifiSmmu4KTableIo;
typedef struct {
    const EldenWifiSmmu4KRange *ranges;
    size_t range_count,capacity_pages,read_budget;
    /* Scratch: one byte per pool page, reset by each audit. Disjoint from all
     * inputs, outputs, mapped resources, physical tables and other scratch. */
    unsigned char *visited;
    size_t visited_bytes;
} EldenWifiSmmu4KAuditRegion;
typedef struct {
    EldenWifiSmmu4KTableIo io;
    const EldenWifiSmmu4KAuditRegion *lower,*upper; /* exactly the enabled regions */
} EldenWifiSmmu4KAuditConfig;
typedef struct {
    size_t descriptor_reads,table_pages,leaf_pages;
    uint64_t descriptor_physical,descriptor,iova,expected_descriptor;
    unsigned level,complete;
} EldenWifiSmmu4KTableAuditResult;
typedef struct {
    EldenWifiSmmu4KTableAuditResult lower,upper;
    EldenWifiSmmu4KProgramResult before,after;
    unsigned phase,complete;
} EldenWifiSmmu4KAuditResult;
/* Walk the physical graph, including every unused slot, with a strict read
 * budget and bounded depth (four levels). Reject blocks, cycles, aliases of
 * table pages, extra/missing mappings, permissions/attributes differing from
 * declared resources, foreign PAs and nonzero reserved descriptor bits.
 * No allocation, descriptor writes, rebuilding, conversion or MMIO. Each
 * expected resource must appear exactly once, in ascending native IOVA order.
 * Caller holds immutable tables/ranges/results and exclusive leases throughout;
 * all masters are quiesced. Scratch and physical callback are trusted kernel
 * boundaries. Declared bounds do NOT establish physical ownership/provenance. */
EldenWifiSmmu4KStatus EldenWifiSmmu4KAuditTables(const EldenWifiSmmu4KTableIo *,
    const EldenWifiSmmu4KConfig *,const EldenWifiSmmu4KResult *,const EldenWifiSmmu4KAuditRegion *,
    uint64_t root_physical,EldenWifiSmmu4KTableAuditResult *);
/* Pre-activation audit of BOTH declared physical regions; also rejects pool
 * overlap and resource access to either entire pool, including spare pages.
 * This is not an observation of an active context. */
EldenWifiSmmu4KStatus EldenWifiSmmu4KAuditDeclaredContext(const EldenWifiSmmu4KContextConfig *,
    const EldenWifiSmmu4KAuditConfig *,EldenWifiSmmu4KAuditResult *);
/* Read actual context before AND after the physical walks; use its observed
 * TTBR addresses as traversal roots. Require exact enabled 4K state and no
 * faults at both observations. No writes, activation or hardware timing proof.
 * Exclusive ownership/quiescence and coherent immutable tables are mandatory;
 * two observations cannot detect an unowned writer changing and restoring state. */
EldenWifiSmmu4KStatus EldenWifiSmmu4KObserveAuditedContext(const EldenWifiSmmu4KIo *,unsigned bank,
    const EldenWifiSmmu4KContextConfig *,const EldenWifiSmmu4KAuditConfig *,EldenWifiSmmu4KAuditResult *);
#ifdef __cplusplus
}
#endif
#endif
