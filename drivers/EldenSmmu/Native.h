/* SPDX-License-Identifier: BSD-2-Clause-Patent */
#pragma once
#include <stdint.h>
typedef struct {
    uint32_t version,run,ready,stopping,stage;
    int32_t error;
    uint32_t bank,slot,asid,translations,global_irq,context_irq;
    uint32_t selection_reads,table_pages,leaf_pages,context_sctlr,context_tcr2;
    uint32_t translation_mode; /* 2 means hardware ATOS is unavailable; DMA remains untested. */
    uint32_t software_pages;
    uint32_t fault_claimed,fault_complete,fault_kind,fault_status,fault_syndrome,fault_reads_failed;
    uint32_t spurious_global,spurious_context;
    uint64_t data_physical,table_physical,last_iova,last_par,fault_address;
} EldenWifiSmmuStatus;
#ifdef __cplusplus
extern "C" {
#endif
int elden_wifi_smmu_early_initialize(void);
int elden_wifi_smmu_ready(void);
int elden_wifi_smmu_status(EldenWifiSmmuStatus *);
void elden_wifi_smmu_stop_begin(void);
#ifdef __cplusplus
}
#endif
