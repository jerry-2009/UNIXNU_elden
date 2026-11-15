/* SPDX-License-Identifier: BSD-2-Clause-Patent */
#pragma once
#include "BootRoute.h"
typedef struct {
    void *context;
    /* Real exclusive early phase, before touch/other dynamic SMMU writers.
     * Read-only selection does not acquire that platform lease itself. */
    int (*admit)(void *);
    int (*read32)(void *,uint32_t offset,uint32_t *value);
} EldenSmmuSelectIo;
typedef struct {
    EldenSmmuBootRoute route;
    uint32_t id0,id1,id2,cr0,cb0_sctlr,asid;
    uint32_t selected_sctlr,selected_fsr,stage,last_offset,last_value,reads;
    int error;
    unsigned ready;
} EldenSmmuSelection;
#ifdef __cplusplus
extern "C" {
#endif
/* Fixed TB322FC boot baseline; every slot/bank checked, including slots128..131.
 * Reads enabled AArch64 contexts' TTBR ASIDs; refuses an unknown active format.
 * No context programming, route reservation, IRQ, ASID acquisition or DMA. The
 * caller must keep its real early lease through the later programming step. */
int elden_smmu_select_boot_domain(const EldenSmmuSelectIo *,EldenSmmuSelection *);
#ifdef __cplusplus
}
#endif
