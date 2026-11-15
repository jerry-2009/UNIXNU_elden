/* SPDX-License-Identifier: GPL-2.0-only */
#pragma once
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
typedef struct {
    uint32_t version,run,state,stage;
    int32_t error;
    uint32_t root_id,endpoint_id,link_status,last_window,last_offset,last_value;
    uint32_t writes,phy_writes,gcc_held,perst_high,stopped;
    uint64_t epoch;
} EldenPcieNativeStatus;
void elden_pcie_native_start(void);
void elden_pcie_native_stop_begin(void);
/* Terminal snapshot only; -11 while the worker owns mutable state. */
int elden_pcie_native_status(EldenPcieNativeStatus *);
#ifdef __cplusplus
}
#endif
