/* SPDX-License-Identifier: GPL-2.0-only */
#pragma once
#include "Root.h"
#ifdef __cplusplus
extern "C" {
#endif

enum {EldenEndpointIdle, EldenEndpointWorking, EldenEndpointIdentified, EldenEndpointRefused, EldenEndpointHeld};
enum {EldenEndpointCheck=1, EldenEndpointSize, EldenEndpointAssign, EldenEndpointWindow,
      EldenEndpointMap, EldenEndpointDecode, EldenEndpointChip, EldenEndpointComplete};
typedef struct {
    uint32_t saved_low, saved_high, mask_low, mask_high;
    uint64_t bytes, address;
    bool present, wide;
} EldenPcieBar;
typedef struct {
    void *context;
    /* Map only the supplied validated BAR0 address/size, without accessing it.
     * Keep the mapping until root reset, including on later errors. */
    int (*map_bar0)(void *,uint64_t address,uint32_t bytes);
    int (*read_bar0)(void *,uint32_t offset,uint32_t *value);
    int (*write_bar0)(void *,uint32_t offset,uint32_t value);
} EldenPcieEndpointIo;
typedef struct {
    EldenPcieRoot *root;
    EldenPcieEndpointIo io;
    EldenPcieBar bars[6];
    uint64_t epoch;
    unsigned state,stage,writes,last_window;
    uint32_t last_offset,last_value,command,chip_version,remap_saved;
    uint32_t memory_base,memory_limit;
    int error;
    bool controls_started,mapped,decode_enabled,remap_restored;
} EldenPcieEndpoint;

/* Cold CPU-MMIO-only extension of a successful root. One serialized caller,
 * same live epoch and no other config/BAR access during sizing/window selection.
 * Never enables bus mastering, DMA, MSI, MHI or firmware. Any partial failure
 * retains resources to reset; do not continue/retry a Held object.
 * Native map provider and full-kernel integration are separate requirements. */
int elden_pcie_endpoint_identify(EldenPcieEndpoint *);
#ifdef __cplusplus
}
#endif
