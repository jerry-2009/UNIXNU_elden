/* SPDX-License-Identifier: BSD-2-Clause-Patent */
#pragma once
#include <stdint.h>
typedef struct {
    uint64_t physical, expected_physical, par_read, par_write, mapped_bus;
    uint32_t smmu_ready, smmu_fault, dma_error, live;
} EldenWifiDmaInspect;
#ifdef __cplusplus
extern "C" {
#endif
int elden_wifi_dma_inspect(const void *cpu,uint64_t bus,uint32_t bytes,EldenWifiDmaInspect *);
#ifdef __cplusplus
}
#endif
