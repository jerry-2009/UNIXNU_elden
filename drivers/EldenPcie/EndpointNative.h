/* SPDX-License-Identifier: GPL-2.0-only */
#pragma once
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
typedef struct {
    uint32_t version,requested,state,stage;
    int32_t error;
    uint32_t chip_version,major,minor,command,writes,mapped,remap_restored,confirmed,stopped;
    uint32_t last_window,last_offset,last_value;
    uint64_t epoch,bar0,bar0_bytes,bar2,bar2_bytes;
} EldenPcieEndpointStatus;
/* Same terminal-only publication boundary as root status; -11 while active.
 * confirmed is withdrawn on stop; register values remain historical samples. */
int elden_pcie_endpoint_status(EldenPcieEndpointStatus *);
#ifdef __cplusplus
}
#endif
