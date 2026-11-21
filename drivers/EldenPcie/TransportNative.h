/* SPDX-License-Identifier: GPL-2.0-only */
#pragma once
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
typedef struct {
    uint32_t version,requested,ready,stage,pcie_cap,msi_cap,receiver_state;
    int32_t error,irq_error;
    uint32_t pending,irq_count,irq_calls,master_attempted,master_known,command;
    uint64_t epoch;
} EldenPcieTransportStatus;
int elden_pcie_transport_status(EldenPcieTransportStatus *);
#ifdef __cplusplus
}
#endif
