/* SPDX-License-Identifier: BSD-2-Clause-Patent */
#pragma once
#include "DmaTables.h"
#include "Select.h"
typedef struct {
    void *context;
    /* Real early lease, physically quiesced WLAN, live mapped registers,
     * claimed data/tables and both owned fault handlers must remain valid. */
    int (*admit)(void *);
    uint64_t (*now_us)(void *);
    void (*delay_us)(void *,unsigned);
    void (*progress)(void *,unsigned stage,unsigned translations);
    EldenWifiSmmu4KIo io;
} EldenSmmuDomainOps;
typedef struct {
    EldenSmmuSelection selection;
    EldenWifiSmmu4KContextConfig config;
    EldenWifiSmmu4KProgramResult program;
    EldenWifiSmmu4KAuditResult audit;
    EldenWifiSmmu4KTableAuditResult table_audit;
    uint8_t visited[EldenWifiTablePages];
    uint32_t stage,translations,attempted,reserved,route_writes,ready;
    uint32_t translation_mode; /* 1=ATOS, 2=audited page tables (ID0.ATOSNS). Not DMA completion. */
    uint32_t software_pages;
    uint64_t last_iova,last_par;
    int error;
} EldenSmmuDomain;
#ifdef __cplusplus
extern "C" {
#endif
/* No allocation or fault-handler substitution. Uses real callbacks and the
 * pinned context programmer/walker; caller owns stable selection/tables and
 * never enables endpoint bus mastering here. Retain all resources on failure. */
int elden_smmu_domain_start(EldenSmmuDomain *,const EldenSmmuDomainOps *,
    const EldenSmmuSelection *,const EldenWifiDmaTables *);
#ifdef __cplusplus
}
#endif
